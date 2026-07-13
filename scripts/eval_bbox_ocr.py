#!/usr/bin/env python
"""Phase 1 bbox validation — Qwen-VL-OCR advanced_recognition vs MiMo.

Before wiring a layout engine into F1, this answers the two questions the plan
gates on (docs/specs/2026-06-13-self-improving-annotation-loop.md §10 task D):

1. **bbox 准不准** — draw the line boxes Qwen-VL-OCR returns onto the original
   image (overlay PNG) so a human can confirm each box lands on its text. A box
   that drifts off its text is worse than no box (the plan's red line against
   LLM-estimated coords); this surfaces that visually.
2. **文本会不会回退** — concat Qwen-OCR text and score number recall/precision
   against the SAME gold set MiMo scored 97.3% recall on
   (data/F1_gold_sets/ocr_accuracy/). If Qwen-OCR text regresses MiMo, the wiring
   step keeps MiMo for text and uses Qwen only for geometry (plan Design 2).

Engine: Qwen-VL-OCR advanced_recognition via DashScope **raw HTTP** (reuses the
existing DASHSCOPE_API_KEY; mirrors ingestion/bilibili_adapter.py's DashScope
direct-HTTP pattern). Zero new pip dependency — the installed dashscope SDK is too
old to expose ocr_options, so we POST the documented contract ourselves.

    python scripts/eval_bbox_ocr.py                  # gold set (7 imgs)
    python scripts/eval_bbox_ocr.py --limit 3        # quick smoke
    python scripts/eval_bbox_ocr.py --img a.png b.png  # extra ad-hoc images

Outputs to data/F1_bbox_eval/:
  {content_id}.overlay.png   — original image with numbered boxes
  {content_id}.regions.txt   — index → bbox → text (cross-check the overlay)
  _summary.json              — per-image + aggregate metrics, go/no-go inputs
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw

# Reuse the exact number-canonicalization the MiMo eval uses, so the recall
# comparison is apples-to-apples (accounting parens → negative, commas stripped).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_ocr_accuracy import canonical_numbers, envelope_text  # noqa: E402

# Beijing endpoint — matches the DASHSCOPE_API_KEY account the repo already uses
# (ingestion/bilibili_adapter.py hits dashscope.aliyuncs.com directly too).
_OCR_ENDPOINT = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)
_DEFAULT_MODEL = os.getenv("QWEN_OCR_MODEL", "qwen-vl-ocr-latest")
# advanced_recognition with generous max_pixels — financial screenshots have small
# axis labels / footnote numbers that get lost at low resolution.
_MIN_PIXELS = 3072
_MAX_PIXELS = 8_388_608

_GOLD_DIR = Path("data/F1_gold_sets/ocr_accuracy")
_STD_DIR = Path("data/F1_standardized")
_OUT_DIR = Path("data/F1_bbox_eval")


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _load_api_key() -> str:
    """Load DASHSCOPE_API_KEY, hard-failing rather than silently degrading.

    The mimo-intake postmortem (docs/specs/2026-06-13-mimo-image-pdf-f1-intake.md
    §4) records a real bug where a missing load_dotenv() let images fall through to
    fallback blocks while still reporting success. We refuse to run keyless.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        print(
            "ERROR: DASHSCOPE_API_KEY not set (checked env + .env). "
            "This script calls the DashScope OCR API and must not run keyless.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return key


# ---------------------------------------------------------------------------
# Qwen-VL-OCR call (raw HTTP)
# ---------------------------------------------------------------------------

def call_qwen_ocr(
    image_path: Path, api_key: str, model: str = _DEFAULT_MODEL, timeout: int = 90
) -> Dict[str, Any]:
    """Call Qwen-VL-OCR advanced_recognition. Returns {words_info, text, error}.

    Retries on 429 with exponential backoff (2/4/8/16s), mirroring the adapter's
    rate-limit handling so a throttle doesn't read as an engine failure.
    """
    img_bytes = image_path.read_bytes()
    b64 = base64.b64encode(img_bytes).decode("ascii")
    suffix = image_path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    data_uri = f"data:image/{mime};base64,{b64}"

    body = {
        "model": model,
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
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            resp = requests.post(_OCR_ENDPOINT, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            return {"words_info": [], "text": "", "error": f"request_exception: {e}"}

        if resp.status_code == 429 and attempt < max_attempts - 1:
            backoff = 2.0 * (2 ** attempt)
            print(f"    429 rate-limited, retry {attempt+1}/{max_attempts-1} after {backoff:.0f}s")
            time.sleep(backoff)
            continue
        if resp.status_code != 200:
            return {
                "words_info": [],
                "text": "",
                "error": f"http_{resp.status_code}: {resp.text[:200]}",
            }
        try:
            data = resp.json()
        except ValueError as e:
            return {"words_info": [], "text": "", "error": f"bad_json: {e}"}
        return _parse_ocr_response(data)

    return {"words_info": [], "text": "", "error": "rate_limited_exhausted"}


def _parse_ocr_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Pull words_info + plain text out of the documented response nesting."""
    try:
        content = data["output"]["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"words_info": [], "text": "", "error": f"unexpected_shape: {json.dumps(data)[:200]}"}

    words_info: List[Dict[str, Any]] = []
    plain_text = ""
    # content is a list of parts; ocr_result lives in one part, plain text in another.
    parts = content if isinstance(content, list) else [content]
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "ocr_result" in part and isinstance(part["ocr_result"], dict):
            words_info = part["ocr_result"].get("words_info") or []
        if isinstance(part.get("text"), str) and part["text"].strip():
            plain_text = part["text"]

    # Prefer the structured per-line text (what carries bbox) for the eval; fall
    # back to the plain-text part when words_info is empty.
    struct_text = "\n".join(
        (w.get("text") or "").strip() for w in words_info if (w.get("text") or "").strip()
    )
    return {
        "words_info": words_info,
        "text": struct_text or plain_text,
        "plain_text": plain_text,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def polygon_to_aabb(location: List[float]) -> Optional[Tuple[float, float, float, float]]:
    """8-coord polygon [x1,y1,...,x4,y4] → axis-aligned (x0,y0,x1,y1) via min/max.

    This is exactly the reduction the F1 consumer needs: BoundingBox is axis-aligned
    (schemas/content_envelope.py), so we take the outer rectangle of the (possibly
    rotated) text quad. Returns None if the location is malformed.
    """
    if not location or len(location) < 8:
        return None
    xs = [float(location[i]) for i in range(0, 8, 2)]
    ys = [float(location[i]) for i in range(1, 8, 2)]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Overlay rendering
# ---------------------------------------------------------------------------

def draw_overlay(image_path: Path, words_info: List[Dict[str, Any]], out_path: Path) -> int:
    """Draw numbered boxes on the image for human bbox verification. Returns #boxes."""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    n = 0
    for idx, w in enumerate(words_info):
        loc = w.get("location")
        drawn = False
        # Faithful: draw the actual (rotated) quad if we have all 4 points.
        if loc and len(loc) >= 8:
            pts = [(float(loc[i]), float(loc[i + 1])) for i in range(0, 8, 2)]
            draw.line(pts + [pts[0]], fill=(220, 30, 30), width=2)
            label_xy = (pts[0][0] + 2, pts[0][1] + 2)
            drawn = True
        else:
            aabb = None
            rr = w.get("rotate_rect")
            if rr and len(rr) >= 4:  # [cx,cy,w,h,angle] → ignore angle for the box
                cx, cy, bw, bh = float(rr[0]), float(rr[1]), float(rr[2]), float(rr[3])
                aabb = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
            if aabb:
                draw.rectangle(aabb, outline=(220, 30, 30), width=2)
                label_xy = (aabb[0] + 2, aabb[1] + 2)
                drawn = True
        if drawn:
            draw.text(label_xy, str(idx), fill=(0, 90, 220))
            n += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return n


def write_regions_txt(words_info: List[Dict[str, Any]], out_path: Path) -> None:
    """Sidecar mapping index → aabb → text, so the user can cross-check the overlay."""
    lines = []
    for idx, w in enumerate(words_info):
        aabb = polygon_to_aabb(w.get("location") or [])
        box = (
            f"({aabb[0]:.0f},{aabb[1]:.0f},{aabb[2]:.0f},{aabb[3]:.0f})" if aabb else "(no-bbox)"
        )
        text = (w.get("text") or "").replace("\n", " ")
        lines.append(f"[{idx:>3}] {box}  {text}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# MiMo baseline
# ---------------------------------------------------------------------------

def load_mimo_text(content_id: str) -> Optional[str]:
    """Concat the existing MiMo envelope text for the same image (the baseline)."""
    p = _STD_DIR / content_id / "content_envelope.json"
    if not p.exists():
        return None
    try:
        return envelope_text(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_numbers(text: str, gold_numbers: List[str]) -> Dict[str, Any]:
    gold = set(gold_numbers)
    pred = canonical_numbers(text)
    inter = gold & pred
    return {
        "n_gold": len(gold),
        "recall": (len(inter) / len(gold)) if gold else None,
        "precision": (len(inter) / len(pred)) if pred else None,
        "missed": sorted(gold - pred),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _gather_targets(args) -> List[Dict[str, Any]]:
    """Build the work list: gold files (with content_id + gold_numbers) and/or ad-hoc images."""
    targets: List[Dict[str, Any]] = []
    if args.img:
        for raw in args.img:
            p = Path(raw)
            targets.append(
                {"content_id": p.stem, "note": "ad-hoc", "raw_path": str(p), "gold_numbers": []}
            )
        return targets
    gold_files = sorted(_GOLD_DIR.glob("*.json"))
    if args.limit:
        gold_files = gold_files[: args.limit]
    for gf in gold_files:
        g = json.loads(gf.read_text(encoding="utf-8"))
        targets.append(g)
    return targets


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 Qwen-VL-OCR bbox validation")
    ap.add_argument("--limit", type=int, default=0, help="only first N gold images")
    ap.add_argument("--img", nargs="*", help="ad-hoc image paths (skip gold set)")
    ap.add_argument("--model", default=_DEFAULT_MODEL, help="qwen-vl-ocr model id")
    args = ap.parse_args()

    api_key = _load_api_key()
    targets = _gather_targets(args)
    if not targets:
        print(f"No targets. Gold dir empty? {_GOLD_DIR}")
        raise SystemExit(1)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []

    print(f"=== Qwen-VL-OCR bbox eval — {len(targets)} image(s), model={args.model} ===\n")
    for t in targets:
        cid = t["content_id"]
        note = t.get("note", "")
        raw_path = Path(t["raw_path"])
        if not raw_path.exists():
            print(f"  [skip] {note} — raw not found: {raw_path}")
            rows.append({"content_id": cid, "note": note, "status": "no_raw"})
            continue

        print(f"  [{note}] {cid}  ({raw_path.name})")
        res = call_qwen_ocr(raw_path, api_key, model=args.model)
        if res.get("error"):
            print(f"      ERROR: {res['error']}")
            rows.append({"content_id": cid, "note": note, "status": "ocr_error", "error": res["error"]})
            continue

        words_info = res["words_info"]
        n_boxed = sum(1 for w in words_info if polygon_to_aabb(w.get("location") or []))
        overlay = _OUT_DIR / f"{cid}.overlay.png"
        n_drawn = draw_overlay(raw_path, words_info, overlay)
        write_regions_txt(words_info, _OUT_DIR / f"{cid}.regions.txt")

        qwen_score = score_numbers(res["text"], t.get("gold_numbers", []))
        mimo_text = load_mimo_text(cid)
        mimo_score = score_numbers(mimo_text, t.get("gold_numbers", [])) if mimo_text else None

        bbox_rate = (n_boxed / len(words_info)) if words_info else 0.0
        print(
            f"      regions={len(words_info)} boxed={n_boxed} ({bbox_rate:.0%})  "
            f"qwen_recall={_fmt(qwen_score['recall'])}  "
            f"mimo_recall={_fmt(mimo_score['recall']) if mimo_score else '  -  '}  "
            f"-> {overlay}"
        )
        rows.append(
            {
                "content_id": cid,
                "note": note,
                "status": "ok",
                "n_regions": len(words_info),
                "n_boxed": n_boxed,
                "bbox_rate": bbox_rate,
                "qwen": qwen_score,
                "mimo": mimo_score,
                "overlay": str(overlay),
            }
        )

    _print_aggregate(rows)
    summary = _OUT_DIR / "_summary.json"
    summary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary written: {summary}")
    print(f"Overlays in: {_OUT_DIR}/  — open them to verify boxes land on text.")


def _fmt(v: Optional[float]) -> str:
    return f"{v:.3f}" if v is not None else "  -  "


def _print_aggregate(rows: List[Dict[str, Any]]) -> None:
    ok = [r for r in rows if r["status"] == "ok"]
    print("\n=== aggregate ===")
    if not ok:
        print("  no successful rows")
        return

    def avg(getter):
        vals = [v for r in ok if (v := getter(r)) is not None]
        return sum(vals) / len(vals) if vals else None

    qwen_recall = avg(lambda r: r["qwen"]["recall"])
    mimo_recall = avg(lambda r: r["mimo"]["recall"] if r["mimo"] else None)
    qwen_prec = avg(lambda r: r["qwen"]["precision"])
    bbox_rate = avg(lambda r: r["bbox_rate"])
    print(f"  images scored      : {len(ok)}")
    print(f"  mean bbox coverage : {_fmt(bbox_rate)}  (regions with a usable box)")
    print(f"  Qwen number recall : {_fmt(qwen_recall)}")
    print(f"  MiMo number recall : {_fmt(mimo_recall)}  (baseline)")
    print(f"  Qwen precision     : {_fmt(qwen_prec)}")
    if qwen_recall is not None and mimo_recall is not None:
        delta = qwen_recall - mimo_recall
        verdict = "Qwen ≥ MiMo → Design 1 (full replace) viable" if delta >= -0.01 else (
            "Qwen < MiMo → Design 2 (MiMo text + Qwen bbox)"
        )
        print(f"  recall delta       : {delta:+.3f}  → {verdict}")


if __name__ == "__main__":
    main()
