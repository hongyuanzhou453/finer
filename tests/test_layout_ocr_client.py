"""Tests for layout_ocr_client — Qwen-VL-OCR → layout_regions, and the F1 wiring.

Covers:
- group_cells_into_regions: table-by-column, paragraph split, title, empty
- polygon / rotate_rect → axis-aligned bbox (clamping, malformed)
- _parse_words_info: documented response shape + garbled
- LayoutOCRClient.extract_layout_regions: mocked HTTP (200, 429-retry, error, no-key)
- Integration: ImageOCRLayoutStandardizer routes layout regions → blocks WITH bbox,
  and falls back to chat-vision text (bbox=None) when layout OCR returns nothing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from finer.parsing import layout_ocr_client as loc
from finer.parsing.layout_ocr_client import (
    LayoutOCRClient,
    _parse_words_info,
    _polygon_to_aabb,
    _rotate_rect_to_aabb,
    group_cells_into_regions,
)
from finer.parsing.image_ocr_standardizer import ImageOCRLayoutStandardizer
from finer.schemas.content import ContentRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell(text: str, x0: float, y0: float, x1: float, y1: float) -> dict:
    return {"text": text, "aabb": (x0, y0, x1, y1)}


def _resp(status: int, payload: dict | None = None, text: str = "") -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.text = text
    return m


def _ocr_payload(words_info: list[dict]) -> dict:
    return {
        "output": {"choices": [{"message": {"content": [{"ocr_result": {"words_info": words_info}}]}}]}
    }


def _make_tmp_image(tmp_path: Path, name: str = "t.png") -> Path:
    p = tmp_path / name
    p.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return p


def _f0(content_id: str = "test_layout_001") -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        creator_name="t",
        source_platform="local",
        source_type="unclassified",
        published_at=datetime(2026, 6, 14, 10, 0),
        title="t.png",
        raw_path="/tmp/t.png",
        file_type="image",
        language="zh",
        metadata={},
    )


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

class TestGeometry:
    def test_polygon_to_aabb(self):
        # slightly skewed quad → outer rectangle
        assert _polygon_to_aabb([10, 20, 110, 22, 112, 60, 8, 58]) == (8, 20, 112, 60)

    def test_polygon_clamps_negative(self):
        x0, y0, x1, y1 = _polygon_to_aabb([-5, -3, 100, 0, 100, 40, -5, 40])
        assert x0 == 0 and y0 == 0 and x1 == 100 and y1 == 40

    def test_polygon_malformed_returns_none(self):
        assert _polygon_to_aabb([1, 2, 3, 4]) is None
        assert _polygon_to_aabb(None) is None

    def test_rotate_rect_to_aabb(self):
        assert _rotate_rect_to_aabb([100, 50, 40, 20, 0]) == (80, 40, 120, 60)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestParseWordsInfo:
    def test_documented_shape(self):
        payload = _ocr_payload([
            {"text": "AAPL", "location": [10, 20, 110, 20, 110, 60, 10, 60]},
            {"text": "150", "location": [200, 20, 260, 20, 260, 60, 200, 60]},
        ])
        cells = _parse_words_info(payload)
        assert [c["text"] for c in cells] == ["AAPL", "150"]
        assert cells[0]["aabb"] == (10, 20, 110, 60)

    def test_missing_shape_returns_empty(self):
        assert _parse_words_info({}) == []
        assert _parse_words_info({"output": {}}) == []

    def test_skips_empty_text_and_missing_location(self):
        payload = _ocr_payload([
            {"text": "  ", "location": [0, 0, 1, 0, 1, 1, 0, 1]},  # blank text
            {"text": "real", "location": None},                     # no box
            {"text": "ok", "location": [1, 2, 3, 2, 3, 4, 1, 4]},
        ])
        cells = _parse_words_info(payload)
        assert [c["text"] for c in cells] == ["ok"]


# ---------------------------------------------------------------------------
# Geometric grouping
# ---------------------------------------------------------------------------

class TestGrouping:
    def test_multicell_rows_become_markdown_table(self):
        cells = [
            _cell("股票", 0, 0, 50, 30), _cell("价格", 100, 0, 150, 30), _cell("涨幅", 200, 0, 250, 30),
            _cell("AAPL", 0, 50, 50, 80), _cell("150", 100, 50, 150, 80), _cell("+1%", 200, 50, 250, 80),
        ]
        regions = group_cells_into_regions(cells)
        assert len(regions) == 1
        r = regions[0]
        assert r["type"] == "table"
        assert "| 股票 | 价格 | 涨幅 |" in r["text"]
        assert "| --- | --- | --- |" in r["text"]
        assert "| AAPL | 150 | +1% |" in r["text"]
        # union bbox spans all cells
        assert r["bbox"] == {"x0": 0, "y0": 0, "x1": 250, "y1": 80}
        assert len(r["line_boxes"]) == 6

    def test_close_single_lines_group_into_one_text_region(self):
        cells = [
            _cell("第一行", 0, 0, 200, 30),
            _cell("第二行", 0, 40, 200, 70),
            _cell("第三行", 0, 80, 200, 110),
        ]
        regions = group_cells_into_regions(cells)
        assert len(regions) == 1
        assert regions[0]["type"] == "text"
        assert regions[0]["text"] == "第一行\n第二行\n第三行"

    def test_large_vertical_gap_splits_text_regions(self):
        cells = [
            _cell("段落一内容", 0, 0, 200, 30),
            _cell("段落二内容", 0, 300, 200, 330),  # far below → new block
        ]
        regions = group_cells_into_regions(cells)
        assert len(regions) == 2

    def test_tall_standalone_short_line_is_title(self):
        cells = [
            _cell("大标题", 0, 0, 120, 60),          # tall, short, alone
            _cell("正文第一行内容比较长", 0, 300, 400, 330),
            _cell("正文第二行内容比较长", 0, 340, 400, 370),
        ]
        regions = group_cells_into_regions(cells)
        assert regions[0]["type"] == "title"
        assert regions[0]["text"] == "大标题"

    def test_empty_input(self):
        assert group_cells_into_regions([]) == []
        assert group_cells_into_regions([{"text": "", "aabb": (0, 0, 1, 1)}]) == []


# ---------------------------------------------------------------------------
# HTTP call (mocked)
# ---------------------------------------------------------------------------

class TestExtractLayoutRegions:
    def test_no_key_returns_none(self, monkeypatch):
        # Hermetic: a real DASHSCOPE_API_KEY may be present in the ambient env
        # (or leaked in by another test); "no key" must be tested explicitly.
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        c = LayoutOCRClient(api_key=None)
        assert c.extract_layout_regions(b"x") is None
        assert c.last_error == "no_dashscope_key"

    def test_success(self):
        payload = _ocr_payload([
            {"text": "abc", "location": [0, 0, 10, 0, 10, 10, 0, 10]},
        ])
        c = LayoutOCRClient(api_key="k")
        with patch.object(loc.requests, "post", return_value=_resp(200, payload)) as post:
            regions = c.extract_layout_regions(b"imgbytes", "image/png")
        assert post.call_count == 1
        assert regions and regions[0]["bbox"] == {"x0": 0, "y0": 0, "x1": 10, "y1": 10}

    def test_429_then_success_retries(self):
        payload = _ocr_payload([{"text": "x", "location": [0, 0, 5, 0, 5, 5, 0, 5]}])
        c = LayoutOCRClient(api_key="k")
        with patch.object(loc.time, "sleep") as sleep, \
             patch.object(loc.requests, "post", side_effect=[_resp(429), _resp(200, payload)]) as post:
            regions = c.extract_layout_regions(b"x")
        assert post.call_count == 2
        assert sleep.call_count == 1  # backed off once
        assert regions

    def test_http_error_returns_none(self):
        c = LayoutOCRClient(api_key="k")
        with patch.object(loc.requests, "post", return_value=_resp(500, text="boom")):
            assert c.extract_layout_regions(b"x") is None
        assert c.last_error == "http_500"

    def test_empty_words_info_returns_none(self):
        c = LayoutOCRClient(api_key="k")
        with patch.object(loc.requests, "post", return_value=_resp(200, _ocr_payload([]))):
            assert c.extract_layout_regions(b"x") is None
        assert c.last_error == "empty_words_info"


# ---------------------------------------------------------------------------
# Standardizer integration
# ---------------------------------------------------------------------------

class TestImageStandardizerWiring:
    def test_layout_regions_produce_blocks_with_bbox(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        regions = [
            {"type": "table", "text": "| a | b |\n| --- | --- |\n| 1 | 2 |",
             "bbox": {"x0": 10, "y0": 20, "x1": 300, "y1": 120}, "line_boxes": [[10, 20, 50, 40]]},
            {"type": "text", "text": "一段正文内容。",
             "bbox": {"x0": 10, "y0": 130, "x1": 280, "y1": 160}},
        ]
        stub = MagicMock()
        stub.available = True
        stub.model = "qwen-vl-ocr-latest"
        stub.extract_layout_regions.return_value = regions

        std = ImageOCRLayoutStandardizer()
        std._layout_client = stub
        env = std.standardize(_f0(), img)

        # every OCR block carries a bbox and records the layout engine
        assert all(b.bbox is not None for b in env.blocks)
        assert env.blocks[0].block_type == "table_region"
        assert env.blocks[0].bbox.x0 == 10 and env.blocks[0].bbox.y1 == 120
        assert all(b.provenance.model_name == "qwen-vl-ocr-latest" for b in env.blocks)
        # line-level boxes retained for fine-grained traceability
        assert env.blocks[0].metadata.get("line_boxes") == [[10, 20, 50, 40]]

    def test_falls_back_to_chat_vision_when_layout_returns_none(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        stub = MagicMock()
        stub.available = True
        stub.model = "qwen-vl-ocr-latest"
        stub.extract_layout_regions.return_value = None  # layout OCR unavailable/failed

        llm = MagicMock()
        llm.chat_with_images.return_value = "# 标题\n\n这是回退路径的正文内容，足够长。"
        llm.model = "mimo-v2.5"
        llm.last_error = None

        std = ImageOCRLayoutStandardizer(llm_client=llm)
        std._layout_client = stub
        env = std.standardize(_f0(), img)

        # fell back to MiMo chat-vision text → blocks exist, no bbox
        assert len(env.blocks) >= 1
        assert all(b.bbox is None for b in env.blocks)
        assert any(b.provenance.model_name == "mimo-v2.5" for b in env.blocks)
        stub.extract_layout_regions.assert_called_once()
        llm.chat_with_images.assert_called_once()
