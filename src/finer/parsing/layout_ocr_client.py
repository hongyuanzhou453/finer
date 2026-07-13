"""Layout-aware OCR client — Qwen-VL-OCR advanced_recognition → layout_regions.

F1 geometry sidecar. The MiMo chat-vision path ("看图写 Markdown") returns text
with NO coordinates, so OCR-derived ContentBlocks have ``bbox=None`` and can only
be traced to page/file level. This client calls Qwen-VL-OCR's
``advanced_recognition`` task, which natively returns **pixel-level** boxes per
text line/cell, and groups those into semantic regions that the existing
``ImageOCRLayoutStandardizer._build_blocks_from_regions`` consumer already knows
how to turn into ContentBlocks with ``bbox``.

Design (validated in Phase 1, docs/specs/2026-06-13-self-improving-annotation-loop.md
§10 task D): single engine, no cross-engine alignment. advanced_recognition gives
text+box together, so each region is text↔box 1:1 — no fuzzy matching, no drift.

Engine access mirrors ingestion/bilibili_adapter.py: raw HTTP POST to DashScope
with the existing ``DASHSCOPE_API_KEY``. Zero new pip dependency (the installed
dashscope SDK is too old to expose ``ocr_options``).

Coordinates returned are in the **pixel space of the image bytes passed in**. For
standalone images that is the raw image; for a rendered PDF page it is the
rendered raster (record the render DPI alongside so a viewer can map back).
"""

from __future__ import annotations

import base64
import logging
import os
import time
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Beijing endpoint — matches the DASHSCOPE_API_KEY account the repo already uses.
_OCR_ENDPOINT = os.getenv(
    "QWEN_OCR_ENDPOINT",
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
)
_DEFAULT_MODEL = os.getenv("QWEN_OCR_MODEL", "qwen-vl-ocr-latest")
# Generous max_pixels — financial screenshots have small axis labels / footnote
# numbers that get lost at low resolution.
_MIN_PIXELS = 3072
_MAX_PIXELS = 8_388_608

# --- grouping heuristics (tuned on the Phase 1 gold set) ---------------------
# Two cells share a row when their y-centers are within this fraction of the
# taller cell's height.
_ROW_Y_TOL_RATIO = 0.6
# A vertical center-to-center gap larger than this multiple of the median row
# height starts a new block (a blank line between paragraphs).
_BLOCK_GAP_RATIO = 1.7
# A standalone single-cell row taller than this multiple of the median cell
# height is treated as a heading/title.
_TITLE_HEIGHT_RATIO = 1.3

# A 4-point polygon as returned by advanced_recognition: [x1,y1,x2,y2,x3,y3,x4,y4]
Bbox = Tuple[float, float, float, float]


class LayoutOCRError(Exception):
    """Raised on a hard OCR failure (caller should fall back to chat-vision)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class LayoutOCRClient:
    """Calls Qwen-VL-OCR advanced_recognition and returns grouped layout regions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        endpoint: str = _OCR_ENDPOINT,
        timeout: int = 90,
    ) -> None:
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self._model = model
        self._endpoint = endpoint
        self._timeout = timeout
        self.last_error: Optional[str] = None

    @property
    def available(self) -> bool:
        """True if a credential is present (caller can decide to skip otherwise)."""
        return bool(self._api_key)

    @property
    def model(self) -> str:
        """The OCR model id, for BlockProvenance.model_name."""
        return self._model

    def extract_layout_regions(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> Optional[List[Dict[str, Any]]]:
        """OCR ``image_bytes`` and return grouped layout regions, or None on failure.

        Each region dict is shaped for ``_build_blocks_from_regions``:
            {"type": "table"|"text"|"title", "text": str,
             "bbox": {"x0","y0","x1","y1"}, "line_boxes": [[x0,y0,x1,y1], ...]}

        None signals the caller to fall back to the chat-vision text path
        (preserving robustness); ``self.last_error`` carries the reason.
        """
        self.last_error = None
        if not self._api_key:
            self.last_error = "no_dashscope_key"
            logger.warning("LayoutOCRClient: DASHSCOPE_API_KEY missing; skipping layout OCR")
            return None

        cells = self._call_advanced_recognition(image_bytes, mime_type)
        if cells is None:
            return None  # last_error already set
        if not cells:
            self.last_error = "empty_words_info"
            return None
        return group_cells_into_regions(cells)

    # ------------------------------------------------------------------
    # DashScope call (raw HTTP, mirrors bilibili_adapter pattern)
    # ------------------------------------------------------------------

    def _call_advanced_recognition(
        self, image_bytes: bytes, mime_type: str
    ) -> Optional[List[Dict[str, Any]]]:
        """POST to DashScope; return list of {text, aabb} cells, or None on failure.

        Retries on 429 with exponential backoff (2/4/8/16s) so a throttle is not
        mistaken for an engine failure (mirrors the adapter's rate-limit handling).
        """
        b64 = base64.b64encode(image_bytes).decode("ascii")
        mime = mime_type if mime_type.startswith("image/") else "image/png"
        data_uri = f"data:{mime};base64,{b64}"
        body = {
            "model": self._model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": data_uri,
                                "min_pixels": _MIN_PIXELS,
                                "max_pixels": _MAX_PIXELS,
                            }
                        ],
                    }
                ]
            },
            "parameters": {"ocr_options": {"task": "advanced_recognition"}},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                resp = requests.post(
                    self._endpoint, headers=headers, json=body, timeout=self._timeout
                )
            except requests.RequestException as e:
                self.last_error = f"request_exception: {e}"
                logger.warning("Layout OCR request failed: %s", e)
                return None

            if resp.status_code == 429 and attempt < max_attempts - 1:
                backoff = 2.0 * (2 ** attempt)
                self.last_error = "rate_limited"
                logger.warning(
                    "Layout OCR rate-limited, retry %d/%d after %.0fs",
                    attempt + 1, max_attempts - 1, backoff,
                )
                time.sleep(backoff)
                continue
            if resp.status_code != 200:
                self.last_error = f"http_{resp.status_code}"
                logger.warning("Layout OCR HTTP %d: %s", resp.status_code, resp.text[:200])
                return None

            try:
                data = resp.json()
            except ValueError as e:
                self.last_error = f"bad_json: {e}"
                return None
            return _parse_words_info(data)

        self.last_error = "rate_limited_exhausted"
        return None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_words_info(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract [{text, aabb}] cells from the documented response nesting.

    Response shape:
        output.choices[0].message.content[<part>].ocr_result.words_info[]
    Each entry: {"text": str, "location": [x1,y1,...,x4,y4], "rotate_rect": [...]}
    """
    try:
        content = data["output"]["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logger.warning("Layout OCR: unexpected response shape")
        return []

    words_info: List[Dict[str, Any]] = []
    parts = content if isinstance(content, list) else [content]
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("ocr_result"), dict):
            words_info = part["ocr_result"].get("words_info") or []
            break

    cells: List[Dict[str, Any]] = []
    for w in words_info:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        aabb = _polygon_to_aabb(w.get("location")) or _rotate_rect_to_aabb(w.get("rotate_rect"))
        if aabb is None:
            continue
        cells.append({"text": text, "aabb": aabb})
    return cells


def _polygon_to_aabb(location: Optional[List[float]]) -> Optional[Bbox]:
    """8-coord polygon [x1,y1,...,x4,y4] → axis-aligned (x0,y0,x1,y1), clamped >=0."""
    if not location or len(location) < 8:
        return None
    xs = [max(0.0, float(location[i])) for i in range(0, 8, 2)]
    ys = [max(0.0, float(location[i])) for i in range(1, 8, 2)]
    return (min(xs), min(ys), max(xs), max(ys))


def _rotate_rect_to_aabb(rr: Optional[List[float]]) -> Optional[Bbox]:
    """[cx,cy,w,h,angle] → axis-aligned box (angle ignored), clamped >=0."""
    if not rr or len(rr) < 4:
        return None
    cx, cy, w, h = float(rr[0]), float(rr[1]), float(rr[2]), float(rr[3])
    return (max(0.0, cx - w / 2), max(0.0, cy - h / 2), max(0.0, cx + w / 2), max(0.0, cy + h / 2))


# ---------------------------------------------------------------------------
# Geometric grouping (pure; unit-tested without network)
# ---------------------------------------------------------------------------

def group_cells_into_regions(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group OCR cells into semantic regions using their own geometry.

    Pipeline: cells → rows (y-cluster) → blocks (vertical-gap split) → typed
    regions. A table block is rendered as markdown; a tall standalone line is a
    title; everything else is body text. The region bbox is the union of its
    member cells; per-cell boxes are retained under ``line_boxes`` for
    fine-grained traceability.
    """
    cells = [c for c in cells if c.get("text") and c.get("aabb")]
    if not cells:
        return []

    med_h = median([max(1.0, c["aabb"][3] - c["aabb"][1]) for c in cells]) or 1.0
    rows = _cells_to_rows(cells)
    segments = _segment_blocks(rows, med_h)
    return [_segment_to_region(kind, seg_rows, med_h) for kind, seg_rows in segments if seg_rows]


def _cells_to_rows(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cluster cells into rows by vertical-center proximity; sort within row by x."""
    ordered = sorted(cells, key=lambda c: (c["aabb"][1] + c["aabb"][3]) / 2)
    rows: List[Dict[str, Any]] = []
    for c in ordered:
        x0, y0, x1, y1 = c["aabb"]
        cy = (y0 + y1) / 2
        h = max(1.0, y1 - y0)
        placed = False
        for row in rows:
            if abs(cy - row["cy"]) <= _ROW_Y_TOL_RATIO * max(h, row["h"]):
                row["cells"].append(c)
                n = row["n"]
                row["cy"] = (row["cy"] * n + cy) / (n + 1)
                row["h"] = (row["h"] * n + h) / (n + 1)
                row["n"] = n + 1
                placed = True
                break
        if not placed:
            rows.append({"cy": cy, "h": h, "n": 1, "cells": [c]})
    rows.sort(key=lambda r: r["cy"])
    for r in rows:
        r["cells"].sort(key=lambda c: c["aabb"][0])
    return rows


def _segment_blocks(
    rows: List[Dict[str, Any]], med_h: float
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Split rows into ('table'|'text', rows) segments.

    Tables are detected by COLUMN structure, not vertical gaps: a run of >=2
    consecutive multi-cell rows is a table (table rows have real whitespace
    between them, so gap-based splitting would shred them). Remaining "loose"
    rows are grouped into text segments, split on large vertical gaps
    (paragraph breaks).
    """
    n = len(rows)
    if n == 0:
        return []

    is_multi = [len(r["cells"]) >= 2 for r in rows]
    in_table = [False] * n
    i = 0
    while i < n:
        if is_multi[i]:
            j = i
            while j < n and is_multi[j]:
                j += 1
            if j - i >= 2:  # >=2 aligned multi-cell rows → a table
                for k in range(i, j):
                    in_table[k] = True
            i = j
        else:
            i += 1

    segments: List[Tuple[str, List[Dict[str, Any]]]] = []
    i = 0
    while i < n:
        if in_table[i]:
            j = i
            while j < n and in_table[j]:
                j += 1
            segments.append(("table", rows[i:j]))
            i = j
        else:
            seg = [rows[i]]
            i += 1
            while i < n and not in_table[i]:
                if rows[i]["cy"] - rows[i - 1]["cy"] > _BLOCK_GAP_RATIO * med_h:
                    break
                seg.append(rows[i])
                i += 1
            segments.append(("text", seg))
    return segments


def _segment_to_region(
    kind: str, seg_rows: List[Dict[str, Any]], med_h: float
) -> Dict[str, Any]:
    """Turn a segment into a typed layout region with a union bbox."""
    cells = [c for r in seg_rows for c in r["cells"]]
    boxes = [c["aabb"] for c in cells]
    union = (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )

    if kind == "table":
        region_type = "table"
        text = _render_markdown_table(seg_rows)
    elif _is_title(seg_rows, med_h):
        region_type = "title"
        text = seg_rows[0]["cells"][0]["text"]
    else:
        region_type = "text"
        text = "\n".join(" ".join(c["text"] for c in r["cells"]) for r in seg_rows)

    return {
        "type": region_type,
        "text": text,
        "bbox": {"x0": union[0], "y0": union[1], "x1": union[2], "y1": union[3]},
        "line_boxes": [list(b) for b in boxes],
    }


def _is_title(block_rows: List[Dict[str, Any]], med_h: float) -> bool:
    """A standalone single short line, notably taller than the page's typical text.

    Conservative on purpose: title vs body is low-stakes (both are valid blocks),
    so we only promote a line that is BOTH short AND visibly larger than the median
    glyph height, never on text length alone.
    """
    if len(block_rows) != 1 or len(block_rows[0]["cells"]) != 1:
        return False
    cell = block_rows[0]["cells"][0]
    if len(cell["text"]) > 40:
        return False
    h = cell["aabb"][3] - cell["aabb"][1]
    return h >= _TITLE_HEIGHT_RATIO * med_h


def _render_markdown_table(block_rows: List[Dict[str, Any]]) -> str:
    """Render clustered rows as a markdown table (header = first row).

    Columns are ragged-tolerant: we pad to the widest row. This reconstructs the
    same kind of markdown table the MiMo path produced, but from real cell boxes.
    """
    grid = [[c["text"] for c in r["cells"]] for r in block_rows]
    ncols = max(len(r) for r in grid)
    lines: List[str] = []
    header = grid[0] + [""] * (ncols - len(grid[0]))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * ncols) + " |")
    for row in grid[1:]:
        padded = row + [""] * (ncols - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)
