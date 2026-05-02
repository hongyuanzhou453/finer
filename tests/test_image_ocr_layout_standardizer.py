"""Tests for ImageOCRLayoutStandardizer — F1 canonical image adapter.

Covers:
- OCR markdown chunking (headers, blank lines, tables, links, quotes)
- Layout region mapping with bounding boxes
- Watermark / page footer / platform noise detection
- BlockQuality scoring determinism
- BlockProvenance on every block
- Missing OCR fallback (vision API failure)
- Canonical validation (validate_canonical_f1)
- Three fixture scenarios: long OCR, long concatenated slide, two-column slide
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from finer.parsing.image_ocr_standardizer import ImageOCRLayoutStandardizer
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    BoundingBox,
    ContentBlock,
    ContentEnvelope,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "f1_standardization"


def _make_f0_record(
    content_id: str = "test_img_001",
    creator_name: str = "test_creator",
    published_at: datetime | None = None,
    metadata: dict | None = None,
) -> ContentRecord:
    """Build a minimal F0 ContentRecord for testing."""
    return ContentRecord(
        content_id=content_id,
        creator_name=creator_name,
        source_platform="feishu",
        content_type="unclassified",
        published_at=published_at or datetime(2026, 4, 16, 13, 27),
        title="test_image.png",
        source_path="/tmp/test_image.png",
        language="zh",
        metadata=metadata or {},
    )


def _make_tmp_image(tmp_path: Path, name: str = "test.png") -> Path:
    """Create a minimal PNG file for testing."""
    img_path = tmp_path / name
    # Minimal valid PNG (1x1 transparent pixel)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"  # signature
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    img_path.write_bytes(png_bytes)
    return img_path


# ---------------------------------------------------------------------------
# OCR markdown chunking
# ---------------------------------------------------------------------------

class TestOCRMarkdownChunking:
    """Test deterministic OCR markdown parsing."""

    def test_header_splits_into_section_title(self):
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record()
        blocks = std._chunk_ocr_markdown("# 第一部分\n\n正文内容。", Path("/tmp/x.png"))
        types = [b.block_type for b in blocks]
        assert "section_title" in types
        assert "image_text" in types

    def test_blank_line_separates_blocks(self):
        std = ImageOCRLayoutStandardizer()
        text = "段落一。\n\n段落二。\n\n段落三。"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        assert len(blocks) == 3

    def test_markdown_table_detected(self):
        std = ImageOCRLayoutStandardizer()
        text = (
            "| 股票 | 价格 |\n"
            "| --- | --- |\n"
            "| AAPL | 150 |\n"
            "| GOOG | 2800 |"
        )
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        assert len(blocks) == 1
        assert blocks[0].block_type == "table_region"

    def test_link_text_classified(self):
        std = ImageOCRLayoutStandardizer()
        text = "更多信息请访问 https://example.com/report"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        assert blocks[0].block_type == "link_reference"

    def test_quote_detection(self):
        std = ImageOCRLayoutStandardizer()
        text = "> 这是一段引用文本。"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        assert blocks[0].block_type == "quote"

    def test_multiple_headers(self):
        std = ImageOCRLayoutStandardizer()
        text = "# 标题一\n\n内容一。\n\n## 标题二\n\n内容二。"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        types = [b.block_type for b in blocks]
        assert types.count("section_title") == 2
        assert types.count("image_text") == 2


# ---------------------------------------------------------------------------
# Layout region mapping
# ---------------------------------------------------------------------------

class TestLayoutRegionMapping:
    """Test layout region → ContentBlock mapping."""

    def test_text_region_maps_to_image_text(self):
        std = ImageOCRLayoutStandardizer()
        regions = [{"type": "text", "text": "正文内容。", "bbox": [10, 20, 300, 100]}]
        blocks = std._build_blocks_from_regions(regions, Path("/tmp/x.png"))
        assert blocks[0].block_type == "image_text"
        assert blocks[0].bbox is not None
        assert blocks[0].bbox.x0 == 10.0
        assert blocks[0].bbox.y0 == 20.0

    def test_title_region_maps_to_section_title(self):
        std = ImageOCRLayoutStandardizer()
        regions = [{"type": "title", "text": "标题"}]
        blocks = std._build_blocks_from_regions(regions, Path("/tmp/x.png"))
        assert blocks[0].block_type == "section_title"

    def test_table_region_maps_to_table_region(self):
        std = ImageOCRLayoutStandardizer()
        regions = [{"type": "table", "text": "| A | B |\n|---|---|\n| 1 | 2 |"}]
        blocks = std._build_blocks_from_regions(regions, Path("/tmp/x.png"))
        assert blocks[0].block_type == "table_region"

    def test_empty_region_becomes_unreadable(self):
        std = ImageOCRLayoutStandardizer()
        regions = [{"type": "text", "text": "", "bbox": [0, 0, 100, 100]}]
        blocks = std._build_blocks_from_regions(regions, Path("/tmp/x.png"))
        assert blocks[0].block_type == "ocr_unreadable"

    def test_bbox_from_dict(self):
        std = ImageOCRLayoutStandardizer()
        region = {"type": "text", "text": "内容", "bbox": {"x0": 5, "y0": 10, "x1": 200, "y1": 50}}
        bbox = std._extract_bbox(region)
        assert bbox is not None
        assert bbox.x0 == 5.0
        assert bbox.x1 == 200.0

    def test_no_bbox_returns_none(self):
        std = ImageOCRLayoutStandardizer()
        region = {"type": "text", "text": "内容"}
        assert std._extract_bbox(region) is None

    def test_nested_source_type_in_metadata(self):
        std = ImageOCRLayoutStandardizer()
        regions = [{
            "type": "text",
            "text": "嵌入的推文内容",
            "role": "embedded_tweet",
            "nested_source_type": "twitter",
        }]
        blocks = std._build_blocks_from_regions(regions, Path("/tmp/x.png"))
        assert blocks[0].metadata["region_role"] == "embedded_tweet"
        assert blocks[0].metadata["nested_source_type"] == "twitter"
        assert blocks[0].metadata["layout_available"] is True


# ---------------------------------------------------------------------------
# Noise / watermark detection
# ---------------------------------------------------------------------------

class TestNoiseDetection:
    """Test watermark, footer, and platform noise detection."""

    def test_watermark_detected(self):
        std = ImageOCRLayoutStandardizer()
        assert std._detect_noise_type("仅供内部使用，请勿外传") == "watermark"

    def test_confidential_watermark(self):
        std = ImageOCRLayoutStandardizer()
        assert std._detect_noise_type("CONFIDENTIAL - Internal Use Only") == "watermark"

    def test_page_footer_detected(self):
        std = ImageOCRLayoutStandardizer()
        assert std._detect_noise_type("第3页/共10页") == "page_footer"

    def test_platform_noise_detected(self):
        std = ImageOCRLayoutStandardizer()
        assert std._detect_noise_type("来自飞书") == "platform_noise"

    def test_normal_text_not_noise(self):
        std = ImageOCRLayoutStandardizer()
        assert std._detect_noise_type("吉利汽车2025年Q1财报分析") is None

    def test_noise_becomes_system_event(self):
        std = ImageOCRLayoutStandardizer()
        text = "仅供内部交流使用，严禁转载传播"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        assert len(blocks) == 1
        assert blocks[0].block_type == "system_event"
        assert blocks[0].quality.noise_score >= 0.8

    def test_noise_not_mixed_into_content(self):
        std = ImageOCRLayoutStandardizer()
        text = "正文内容。\n\n仅供内部使用，请勿外传\n\n更多正文。"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/x.png"))
        content_blocks = [b for b in blocks if b.block_type != "system_event"]
        noise_blocks = [b for b in blocks if b.block_type == "system_event"]
        assert len(noise_blocks) == 1
        for cb in content_blocks:
            assert "仅供内部" not in cb.text


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

class TestQualityScoring:
    """Test deterministic BlockQuality scoring."""

    def test_long_text_high_quality(self):
        std = ImageOCRLayoutStandardizer()
        text = "这是一段长度足够的文本内容，用于测试质量评分。" * 5
        q = std._score_block_quality(text, "image_text")
        assert q.readability > 0.6
        assert q.extraction_confidence > 0.6
        assert q.completeness == 1.0

    def test_empty_text_zero_quality(self):
        std = ImageOCRLayoutStandardizer()
        q = std._score_block_quality("", "image_text")
        assert q.readability == 0.0
        assert q.extraction_confidence == 0.0

    def test_short_text_low_confidence(self):
        std = ImageOCRLayoutStandardizer()
        q = std._score_block_quality("短", "image_text")
        assert q.extraction_confidence < 0.6
        assert "short_text" in q.quality_flags

    def test_header_high_structural_confidence(self):
        std = ImageOCRLayoutStandardizer()
        q = std._score_block_quality("这是一个标题文本内容", "section_title")
        assert q.structural_confidence >= 0.9

    def test_garbage_chars_detected(self):
        std = ImageOCRLayoutStandardizer()
        text = "正常文本" + "\x00\x01\x02" * 20
        q = std._score_block_quality(text, "image_text")
        assert "garbage_chars_detected" in q.quality_flags

    def test_noise_block_high_noise_score(self):
        std = ImageOCRLayoutStandardizer()
        blocks = std._chunk_ocr_markdown("仅供内部使用", Path("/tmp/x.png"))
        assert blocks[0].quality.noise_score >= 0.8


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    """Test BlockProvenance on every block."""

    def test_every_block_has_provenance(self):
        std = ImageOCRLayoutStandardizer()
        text = "# 标题\n\n正文内容。"
        blocks = std._chunk_ocr_markdown(text, Path("/tmp/test.png"))
        for block in blocks:
            assert block.provenance is not None
            assert isinstance(block.provenance, BlockProvenance)
            assert block.provenance.extractor == "image_ocr_standardizer"
            assert block.provenance.extractor_version == "1.0.0"
            assert block.provenance.raw_path == "/tmp/test.png"

    def test_source_hash_populated(self):
        std = ImageOCRLayoutStandardizer()
        blocks = std._chunk_ocr_markdown("正文内容。", Path("/tmp/x.png"))
        assert blocks[0].provenance.source_hash is not None
        assert len(blocks[0].provenance.source_hash) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Missing OCR fallback
# ---------------------------------------------------------------------------

class TestMissingOCRFallback:
    """Test behavior when OCR data is unavailable."""

    def test_fallback_produces_ocr_unreadable(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"vision_transcript_error": "API key missing"})

        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, img)

        assert len(envelope.blocks) >= 1
        types = {b.block_type for b in envelope.blocks}
        assert "ocr_unreadable" in types

    def test_fallback_does_not_fabricate_image_text(self, tmp_path):
        """P1-1: Fallback must NOT emit image_text for unreadable images."""
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record()

        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, img)

        content_types = {b.block_type for b in envelope.blocks} - {"section_title", "ocr_unreadable"}
        assert content_types == set(), (
            f"Fallback fabricated content block types: {content_types}. "
            f"Only section_title (metadata) and ocr_unreadable (failure) are allowed."
        )

    def test_fallback_preserves_error_info(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(
            content_id="test_fallback",
            metadata={"vision_transcript_error": "DASHSCOPE_API_KEY not configured"},
        )

        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, img)

        error_blocks = [b for b in envelope.blocks if b.block_type == "ocr_unreadable"]
        assert len(error_blocks) >= 1
        assert "test_fallback" in error_blocks[0].text

    def test_fallback_quality_flags(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record()

        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, img)

        for block in envelope.blocks:
            assert isinstance(block.quality, BlockQuality)
            assert block.provenance is not None

    def test_whitespace_only_ocr_produces_failure_block(self, tmp_path):
        """P1-3: Whitespace-only OCR must not produce empty blocks list."""
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"ocr_markdown": "   \n\n  \n  "})

        envelope = std.standardize(f0, img)

        assert len(envelope.blocks) >= 1
        types = {b.block_type for b in envelope.blocks}
        assert "ocr_unreadable" in types

        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Canonical violations: {violations}"

    def test_empty_string_ocr_produces_failure_block(self, tmp_path):
        """P1-3: Empty string OCR must not produce empty blocks list."""
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"ocr_markdown": ""})

        # Empty string is falsy, so it falls through to vision API fallback
        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, img)

        assert len(envelope.blocks) >= 1
        violations = envelope.validate_canonical_f1()
        assert violations == []


# ---------------------------------------------------------------------------
# Canonical validation
# ---------------------------------------------------------------------------

class TestCanonicalValidation:
    """Test validate_canonical_f1 compliance."""

    def test_ocr_input_passes_validator(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        ocr_text = "# 标题\n\n正文内容。这是足够长的文本用于测试。"
        f0 = _make_f0_record(metadata={"ocr_markdown": ocr_text})

        envelope = std.standardize(f0, img)
        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Canonical violations: {violations}"

    def test_fallback_passes_validator(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record()

        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, img)

        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Canonical violations: {violations}"

    def test_schema_version_is_v1(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"ocr_markdown": "# 标题\n\n内容。"})

        envelope = std.standardize(f0, img)
        assert envelope.schema_version == "v1.0"

    def test_source_type_is_image(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"ocr_markdown": "# 标题\n\n内容。"})

        envelope = std.standardize(f0, img)
        assert envelope.source_type == "image"

    def test_standardization_profile_set(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"ocr_markdown": "# 标题\n\n内容。"})

        envelope = std.standardize(f0, img)
        assert envelope.standardization_profile == "image_ocr_layout_v1"

    def test_no_legacy_block_types(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        text = "# 标题\n\n正文。\n\n| A | B |\n|---|---|\n| 1 | 2 |"
        f0 = _make_f0_record(metadata={"ocr_markdown": text})

        envelope = std.standardize(f0, img)
        legacy = {"heading", "list", "table", "chart", "image_region", "transcript_segment", "unknown"}
        for block in envelope.blocks:
            assert block.block_type not in legacy

    def test_order_index_sequential(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        text = "# 标题\n\n段落一。\n\n段落二。"
        f0 = _make_f0_record(metadata={"ocr_markdown": text})

        envelope = std.standardize(f0, img)
        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i

    def test_envelope_id_propagated(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        f0 = _make_f0_record(metadata={"ocr_markdown": "# 标题\n\n内容。"})

        envelope = std.standardize(f0, img)
        for block in envelope.blocks:
            assert block.envelope_id == envelope.envelope_id


# ---------------------------------------------------------------------------
# Layout path with bbox
# ---------------------------------------------------------------------------

class TestLayoutPath:
    """Test layout region input path end-to-end."""

    def test_layout_regions_produce_bbox(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        regions = [
            {"type": "title", "text": "吉利汽车财报", "bbox": [10, 10, 400, 60]},
            {"type": "text", "text": "2025年Q1营收增长15%。", "bbox": [10, 70, 400, 150]},
            {"type": "table", "text": "| 指标 | 数值 |\n|---|---|\n| 营收 | 500亿 |", "bbox": [10, 160, 400, 300]},
        ]
        f0 = _make_f0_record(metadata={"layout_regions": regions})

        envelope = std.standardize(f0, img)

        assert envelope.source_type == "image"
        types = {b.block_type for b in envelope.blocks}
        assert "section_title" in types
        assert "image_text" in types
        assert "table_region" in types

        # All blocks from layout should have bbox
        for block in envelope.blocks:
            if block.block_type != "ocr_unreadable":
                assert block.bbox is not None
                assert block.metadata.get("layout_available") is True

    def test_layout_passes_canonical_validator(self, tmp_path):
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        regions = [
            {"type": "title", "text": "标题", "bbox": [0, 0, 100, 30]},
            {"type": "text", "text": "正文内容。", "bbox": [0, 40, 100, 80]},
        ]
        f0 = _make_f0_record(metadata={"layout_regions": regions})

        envelope = std.standardize(f0, img)
        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Canonical violations: {violations}"

    def test_layout_preferred_over_ocr_when_both_exist(self, tmp_path):
        """P1-2: When both layout_regions and ocr_markdown exist, prefer layout
        because it preserves bbox and spatial evidence."""
        img = _make_tmp_image(tmp_path)
        std = ImageOCRLayoutStandardizer()
        regions = [
            {"type": "title", "text": "布局标题", "bbox": [10, 10, 400, 60]},
            {"type": "text", "text": "布局正文。", "bbox": [10, 70, 400, 150]},
        ]
        ocr_text = "# OCR标题\n\nOCR正文。"
        f0 = _make_f0_record(metadata={
            "layout_regions": regions,
            "ocr_markdown": ocr_text,
        })

        envelope = std.standardize(f0, img)

        # Should use layout text, not OCR text
        texts = [b.text for b in envelope.blocks]
        assert any("布局" in t for t in texts), (
            f"Expected layout text, got: {texts}"
        )
        assert not any("OCR标题" in t for t in texts), (
            "Layout should take precedence over OCR markdown"
        )

        # Layout blocks should have bbox
        for block in envelope.blocks:
            if block.block_type != "ocr_unreadable":
                assert block.bbox is not None
                assert block.metadata.get("layout_available") is True


# ---------------------------------------------------------------------------
# Integration with fixture manifests
# ---------------------------------------------------------------------------

class TestFixtureIntegration:
    """Test adapter against real fixture manifests (deterministic, no API calls)."""

    @pytest.fixture(params=["img_9you_0416.json", "img_9you_0409.json", "img_maodaren_0319.json"])
    def manifest(self, request):
        path = FIXTURE_DIR / request.param
        with open(path) as f:
            return json.load(f)

    def test_adapter_produces_valid_envelope(self, manifest, tmp_path):
        """Adapter must produce a valid ContentEnvelope even without OCR data."""
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found: {manifest['raw_path']}")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name=manifest.get("creator_name", ""),
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            language="zh",
            metadata=manifest.get("metadata", {}),
        )

        std = ImageOCRLayoutStandardizer()

        # Mock vision API to simulate failure (no API key in test env)
        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, raw_path)

        # Basic structural assertions
        assert len(envelope.blocks) > 0
        assert envelope.source_type == "image"
        assert envelope.source_record_id == manifest["source_record_id"]
        assert envelope.standardization_profile == manifest["expected_profile"]
        assert envelope.raw_path == str(raw_path)

        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i
            assert isinstance(block.quality, BlockQuality)
            assert block.provenance is not None
            assert block.provenance.extractor == "image_ocr_standardizer"
            assert block.envelope_id == envelope.envelope_id

    def test_fixture_canonical_validation(self, manifest):
        """Canonical validation must pass for all fixtures."""
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found: {manifest['raw_path']}")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name=manifest.get("creator_name", ""),
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            language="zh",
            metadata=manifest.get("metadata", {}),
        )

        std = ImageOCRLayoutStandardizer()
        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, raw_path)

        violations = envelope.validate_canonical_f1()
        assert violations == [], (
            f"Canonical validation failed for {manifest['fixture_id']} "
            f"({len(violations)} violations):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_fixture_required_block_types(self, manifest):
        """Required block types from manifest must be present."""
        required = manifest["assertions"].get("required_block_types", [])
        if not required:
            return

        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found: {manifest['raw_path']}")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name=manifest.get("creator_name", ""),
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            language="zh",
            metadata=manifest.get("metadata", {}),
        )

        std = ImageOCRLayoutStandardizer()
        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, raw_path)

        present = {b.block_type for b in envelope.blocks}
        for bt in required:
            assert bt in present, (
                f"Required block_type '{bt}' not found in {manifest['fixture_id']}. "
                f"Present: {sorted(present)}"
            )

    def test_fixture_no_legacy_types(self, manifest):
        """No legacy block types in output."""
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found: {manifest['raw_path']}")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name=manifest.get("creator_name", ""),
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            language="zh",
            metadata=manifest.get("metadata", {}),
        )

        std = ImageOCRLayoutStandardizer()
        with patch.object(std, "_extract_via_vision_api", return_value=None):
            envelope = std.standardize(f0, raw_path)

        legacy = {"heading", "list", "table", "chart", "image_region",
                  "transcript_segment", "unknown"}
        for block in envelope.blocks:
            assert block.block_type not in legacy, (
                f"Legacy block_type '{block.block_type}' in {manifest['fixture_id']}"
            )


# ---------------------------------------------------------------------------
# Real OCR text scenarios
# ---------------------------------------------------------------------------

class TestRealOCRScenarios:
    """Test with realistic OCR text matching the three fixture types."""

    def test_long_ocr_with_watermark(self, tmp_path):
        """Scenario: 04-16 image — long OCR text + watermark."""
        img = _make_tmp_image(tmp_path)
        ocr_text = (
            "# 9you 沟通纪要\n\n"
            "会议时间：2026-04-16 13:27\n\n"
            "参会人：张三、李四、王五\n\n"
            "## 议题一：Q1 业绩回顾\n\n"
            "2025年Q1营收同比增长15%，净利润率提升至12%。\n\n"
            "## 议题二：Q2 展望\n\n"
            "预计Q2营收环比增长8-10%。\n\n"
            "| 指标 | Q1实际 | Q2预期 |\n"
            "| --- | --- | --- |\n"
            "| 营收 | 500亿 | 545亿 |\n"
            "| 净利 | 60亿 | 68亿 |\n\n"
            "仅供内部交流使用，严禁转载传播\n\n"
            "第1页/共3页"
        )

        f0 = _make_f0_record(metadata={"ocr_markdown": ocr_text})
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, img)

        types = {b.block_type for b in envelope.blocks}
        assert "section_title" in types
        assert "image_text" in types
        assert "table_region" in types
        assert "system_event" in types

        # Watermark and footer should be system_event, not mixed into content
        system_blocks = [b for b in envelope.blocks if b.block_type == "system_event"]
        assert len(system_blocks) == 2
        noise_types = {b.metadata.get("noise_type") for b in system_blocks}
        assert "watermark" in noise_types
        assert "page_footer" in noise_types

        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_long_concatenated_slide(self, tmp_path):
        """Scenario: 04-09 image — long concatenated multi-source slide."""
        img = _make_tmp_image(tmp_path)
        ocr_text = (
            "# 市场周报 2026-04-09\n\n"
            "## A股市场\n\n"
            "沪指收涨0.5%，深成指涨0.8%。新能源板块领涨。\n\n"
            "## 港股市场\n\n"
            "恒指收跌0.3%，科技股表现疲软。\n\n"
            "## 美股市场\n\n"
            "道指涨0.2%，纳指跌0.1%。美联储维持利率不变。\n\n"
            "## 热门个股\n\n"
            "| 股票 | 涨跌幅 | 评论 |\n"
            "| --- | --- | --- |\n"
            "| 宁德时代 | +3.5% | 电池出货量超预期 |\n"
            "| 贵州茅台 | -1.2% | 消费疲软 |\n\n"
            "来源：Wind、Bloomberg\n\n"
            "来自飞书"
        )

        f0 = _make_f0_record(metadata={"ocr_markdown": ocr_text})
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, img)

        types = {b.block_type for b in envelope.blocks}
        assert "section_title" in types
        assert "image_text" in types
        assert "table_region" in types
        assert "system_event" in types

        # Multiple section titles (one per market)
        title_blocks = [b for b in envelope.blocks if b.block_type == "section_title"]
        assert len(title_blocks) >= 4

        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_two_column_slide(self, tmp_path):
        """Scenario: 03-19 image — two-column investment research slide."""
        img = _make_tmp_image(tmp_path)
        ocr_text = (
            "# 吉利汽车 2025 年报分析\n\n"
            "## 核心数据\n\n"
            "全年营收 2,402 亿元（同比+21%）\n"
            "净利润 166 亿元（同比+8%）\n"
            "毛利率 16.2%（+0.5pp）\n\n"
            "## 关键风险\n\n"
            "1. 价格战持续：吉利品牌向新能源转型，短期牺牲单车利润\n"
            "2. 研发投入增加：全年研发费用 176.2 亿元（同比+29%）\n"
            "3. 品牌整合成本：私有化极氪的一次性费用\n\n"
            "更多详情请访问 https://example.com/geely-2025"
        )

        f0 = _make_f0_record(metadata={"ocr_markdown": ocr_text})
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, img)

        types = {b.block_type for b in envelope.blocks}
        assert "section_title" in types
        assert "image_text" in types
        assert "link_reference" in types

        violations = envelope.validate_canonical_f1()
        assert violations == []
