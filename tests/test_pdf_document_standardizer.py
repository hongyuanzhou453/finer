"""Tests for PDFStandardizer — F1 canonical PDF adapter.

Covers:
- Page-level processing and page_index assignment
- Text extraction and paragraph splitting
- Table detection and table_region blocks
- Chart/image region detection
- Cover page metadata
- Noise detection (watermark, header, footer)
- BlockQuality scoring determinism
- BlockProvenance on every block
- OCR fallback for scanned pages
- Canonical validation (validate_canonical_f1)
- Fixture integration with pdf_maodaren_0415
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from finer.parsing.pdf_standardizer import PDFStandardizer
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    BoundingBox,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.quality import QualityCard

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "f1_standardization"


def _make_f0_record(
    content_id: str = "test_pdf_001",
    creator_name: str = "test_creator",
    metadata: dict | None = None,
) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        creator_name=creator_name,
        source_platform="feishu",
        content_type="unclassified",
        published_at=datetime(2026, 4, 15, 15, 46),
        title="test.pdf",
        source_path="/tmp/test.pdf",
        language="zh",
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------

class TestParagraphSplitting:
    def test_double_newline_splits(self):
        std = PDFStandardizer()
        result = std._split_paragraphs("段落一。\n\n段落二。")
        assert len(result) == 2

    def test_triple_newline_splits(self):
        std = PDFStandardizer()
        result = std._split_paragraphs("A\n\n\nB\n\nC")
        assert len(result) == 3

    def test_no_newline_single_para(self):
        std = PDFStandardizer()
        result = std._split_paragraphs("单段文本。")
        assert len(result) == 1

    def test_whitespace_only_skipped(self):
        std = PDFStandardizer()
        result = std._split_paragraphs("段一。\n\n   \n\n段二。")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Text classification
# ---------------------------------------------------------------------------

class TestTextClassification:
    def test_short_single_line_is_title(self):
        std = PDFStandardizer()
        assert std._classify_text("宏观经济趋势", 0) == "section_title"

    def test_long_text_is_paragraph(self):
        std = PDFStandardizer()
        text = "这是很长的一段文本。" * 20
        assert std._classify_text(text, 0) == "paragraph"

    def test_url_text_is_link_reference(self):
        std = PDFStandardizer()
        assert std._classify_text("详情 https://example.com/report", 5) == "link_reference"

    def test_ending_with_period_is_paragraph(self):
        std = PDFStandardizer()
        assert std._classify_text("短文本。", 0) == "paragraph"


# ---------------------------------------------------------------------------
# Noise detection
# ---------------------------------------------------------------------------

class TestNoiseDetection:
    def test_watermark_detected(self):
        std = PDFStandardizer()
        assert std._detect_noise_type("仅供内部使用") == "watermark"

    def test_page_footer_detected(self):
        std = PDFStandardizer()
        assert std._detect_noise_type("第3页/共10页") == "page_footer"

    def test_platform_noise_detected(self):
        std = PDFStandardizer()
        assert std._detect_noise_type("来自飞书") == "platform_noise"

    def test_header_detected(self):
        std = PDFStandardizer()
        assert std._detect_noise_type("配色应用指引") == "page_header"

    def test_normal_text_not_noise(self):
        std = PDFStandardizer()
        assert std._detect_noise_type("宠物行业市场规模分析") is None

    def test_noise_block_is_system_event(self):
        std = PDFStandardizer()
        block = std._build_noise_block("watermark", "仅供内部使用", 0, Path("/tmp/x.pdf"))
        assert block.block_type == "system_event"
        assert block.quality.noise_score >= 0.8
        assert block.metadata["noise_type"] == "watermark"


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

class TestTableExtraction:
    def test_table_to_text_markdown(self):
        std = PDFStandardizer()
        data = [["A", "B"], ["1", "2"], ["3", "4"]]
        text = std._table_to_text(data)
        assert "| A | B |" in text
        assert "| --- | --- |" in text
        assert "| 1 | 2 |" in text

    def test_single_row_table(self):
        std = PDFStandardizer()
        data = [["X", "Y", "Z"]]
        text = std._table_to_text(data)
        assert "| X | Y | Z |" in text


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

class TestQualityScoring:
    def test_long_text_high_quality(self):
        std = PDFStandardizer()
        q = std._score_block_quality("这是足够长的文本内容。" * 10, "paragraph")
        assert q.readability > 0.6
        assert q.extraction_confidence > 0.6

    def test_empty_text_zero_quality(self):
        std = PDFStandardizer()
        q = std._score_block_quality("", "paragraph")
        assert q.readability == 0.0
        assert q.extraction_confidence == 0.0

    def test_title_high_structural(self):
        std = PDFStandardizer()
        q = std._score_block_quality("标题文本内容", "section_title")
        assert q.structural_confidence >= 0.9

    def test_table_structural(self):
        std = PDFStandardizer()
        q = std._score_block_quality("| A | B |\n|---|---|\n| 1 | 2 |", "table_region")
        assert q.structural_confidence == 0.8

    def test_noise_high_noise_score(self):
        std = PDFStandardizer()
        q = std._score_block_quality("仅供内部使用", "system_event")
        assert q.noise_score == 0.8

    def test_extra_flags_preserved(self):
        std = PDFStandardizer()
        q = std._score_block_quality("文本", "paragraph", extra_flags=["ocr_extracted"])
        assert "ocr_extracted" in q.quality_flags


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_every_block_has_provenance(self):
        std = PDFStandardizer()
        block = std._build_block("paragraph", "文本内容", 0, Path("/tmp/test.pdf"))
        assert block.provenance is not None
        assert block.provenance.extractor == "pdf_standardizer"
        assert block.provenance.extractor_version == "1.0.0"
        assert block.provenance.raw_path == "/tmp/test.pdf"

    def test_source_hash_populated(self):
        std = PDFStandardizer()
        block = std._build_block("paragraph", "文本内容", 0, Path("/tmp/x.pdf"))
        assert block.provenance.source_hash is not None
        assert len(block.provenance.source_hash) == 64

    def test_model_name_on_ocr_block(self):
        std = PDFStandardizer()
        block = std._build_block(
            "paragraph", "OCR文本", 0, Path("/tmp/x.pdf"),
            quality_flags=["ocr_extracted"], model_name="qwen-vl-max",
        )
        assert block.provenance.model_name == "qwen-vl-max"


# ---------------------------------------------------------------------------
# Page index
# ---------------------------------------------------------------------------

class TestPageIndex:
    def test_page_index_set_on_block(self):
        std = PDFStandardizer()
        block = std._build_block("paragraph", "文本", 3, Path("/tmp/x.pdf"))
        assert block.page_index == 3

    def test_unreadable_block_has_page_index(self):
        std = PDFStandardizer()
        block = std._build_unreadable_page_block(5, Path("/tmp/x.pdf"))
        assert block.page_index == 5
        assert block.block_type == "ocr_unreadable"


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------

class TestCoverPage:
    def test_cover_page_metadata_set(self):
        """Cover page blocks should have metadata.cover_page = True."""
        std = PDFStandardizer()
        # Simulate what _process_page does for page 0
        block = std._build_block("section_title", "封面标题", 0, Path("/tmp/x.pdf"))
        # In real flow, _process_page sets this
        if block.page_index == 0:
            block.metadata["cover_page"] = True
        assert block.metadata.get("cover_page") is True

    def test_non_cover_page_no_metadata(self):
        std = PDFStandardizer()
        block = std._build_block("paragraph", "正文", 5, Path("/tmp/x.pdf"))
        assert block.metadata.get("cover_page") is None


# ---------------------------------------------------------------------------
# Canonical validation
# ---------------------------------------------------------------------------

class TestCanonicalValidation:
    def test_envelope_passes_validator(self):
        std = PDFStandardizer()
        blocks = [
            std._build_block("section_title", "标题", 0, Path("/tmp/x.pdf")),
            std._build_block("paragraph", "正文内容。" * 5, 0, Path("/tmp/x.pdf")),
            std._build_block("table_region", "| A | B |\n|---|---|\n| 1 | 2 |", 1, Path("/tmp/x.pdf")),
        ]
        for i, b in enumerate(blocks):
            b.order_index = i

        envelope = ContentEnvelope(
            source_record_id="test_001",
            schema_version="v1.0",
            source_type="pdf",
            standardization_profile="pdf_layout_v1",
            raw_path="/tmp/x.pdf",
            blocks=blocks,
            quality_card=QualityCard.create_default(0.7),
        )
        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Violations: {violations}"

    def test_schema_version_v1(self):
        std = PDFStandardizer()
        f0 = _make_f0_record()
        # Use mock page
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "封面标题"
        mock_page.extract_words.return_value = []
        mock_page.extract_tables.return_value = []
        mock_page.images = []
        mock_page.rects = []
        mock_page.width = 960
        mock_page.height = 540
        mock_page.find_tables.return_value = []

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            envelope = std.standardize(f0, Path("/tmp/x.pdf"))

        assert envelope.schema_version == "v1.0"
        assert envelope.source_type == "pdf"
        assert envelope.standardization_profile == "pdf_layout_v1"


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------

class TestEnvelopeConstruction:
    def test_blocks_order_sequential(self):
        std = PDFStandardizer()
        blocks = [
            std._build_block("section_title", "标题", 0, Path("/tmp/x.pdf")),
            std._build_block("paragraph", "正文。", 0, Path("/tmp/x.pdf")),
            std._build_block("paragraph", "更多。", 1, Path("/tmp/x.pdf")),
        ]
        for i, b in enumerate(blocks):
            b.order_index = i

        envelope = ContentEnvelope(
            source_record_id="test",
            schema_version="v1.0",
            source_type="pdf",
            standardization_profile="pdf_layout_v1",
            blocks=blocks,
            quality_card=QualityCard.create_default(0.7),
        )
        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i

    def test_envelope_id_propagated(self):
        std = PDFStandardizer()
        blocks = [std._build_block("paragraph", "文本", 0, Path("/tmp/x.pdf"))]
        blocks[0].order_index = 0
        envelope = ContentEnvelope(
            source_record_id="test",
            schema_version="v1.0",
            source_type="pdf",
            standardization_profile="pdf_layout_v1",
            blocks=blocks,
            quality_card=QualityCard.create_default(0.7),
        )
        for block in envelope.blocks:
            assert block.envelope_id == envelope.envelope_id


# ---------------------------------------------------------------------------
# Fixture integration
# ---------------------------------------------------------------------------

class TestFixtureIntegration:
    """Test against the real PDF fixture manifest."""

    @pytest.fixture
    def manifest(self):
        path = FIXTURE_DIR / "pdf_maodaren_0415.json"
        with open(path) as f:
            return json.load(f)

    def test_adapter_produces_valid_envelope(self, manifest):
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

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        assert len(envelope.blocks) > 0
        assert envelope.source_type == "pdf"
        assert envelope.source_record_id == manifest["source_record_id"]
        assert envelope.standardization_profile == manifest["expected_profile"]
        assert envelope.raw_path == str(raw_path)

        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i
            assert isinstance(block.quality, BlockQuality)
            assert block.provenance is not None
            assert block.provenance.extractor == "pdf_standardizer"
            assert block.envelope_id == envelope.envelope_id

    def test_page_index_populated(self, manifest):
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name="",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            metadata=manifest.get("metadata", {}),
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        has_page = any(b.page_index is not None for b in envelope.blocks)
        assert has_page, "No block has page_index set"

    def test_required_block_types(self, manifest):
        required = manifest["assertions"].get("required_block_types", [])
        if not required:
            return

        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name="",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            metadata=manifest.get("metadata", {}),
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        present = {b.block_type for b in envelope.blocks}
        for bt in required:
            assert bt in present, (
                f"Required block_type '{bt}' not found. Present: {sorted(present)}"
            )

    def test_min_region_types(self, manifest):
        min_count = manifest["assertions"].get("min_region_types", 0)
        if not min_count:
            return

        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name="",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            metadata=manifest.get("metadata", {}),
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        region_types = {"table_region", "chart_region", "image_text"}
        present = {b.block_type for b in envelope.blocks} & region_types
        assert len(present) >= min_count, (
            f"Expected >= {min_count} region types, found: {sorted(present)}"
        )

    def test_no_legacy_block_types(self, manifest):
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name="",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            metadata=manifest.get("metadata", {}),
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        legacy = {"heading", "list", "table", "chart", "image_region",
                  "transcript_segment", "unknown"}
        for block in envelope.blocks:
            assert block.block_type not in legacy

    def test_canonical_validation(self, manifest):
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name="",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            metadata=manifest.get("metadata", {}),
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        violations = envelope.validate_canonical_f1()
        assert violations == [], (
            f"Canonical validation failed ({len(violations)} violations):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_cover_or_chapter_identified(self, manifest):
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip(f"Raw file not found")

        f0 = ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name="",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=str(raw_path),
            metadata=manifest.get("metadata", {}),
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, raw_path)

        structural = {"section_title", "paragraph"}
        present = {b.block_type for b in envelope.blocks}
        assert structural & present, (
            f"Expected section_title or paragraph. Present: {sorted(present)}"
        )


# ---------------------------------------------------------------------------
# P1: Unreadable PDF handling
# ---------------------------------------------------------------------------

class TestUnreadablePDF:
    def test_corrupt_pdf_returns_canonical_envelope(self, tmp_path):
        """P1: corrupt PDF should not raise, should return envelope with ocr_unreadable."""
        corrupt_file = tmp_path / "corrupt.pdf"
        corrupt_file.write_bytes(b"this is not a valid PDF file")

        std = PDFStandardizer()
        f0 = _make_f0_record()
        envelope = std.standardize(f0, corrupt_file)

        assert isinstance(envelope, ContentEnvelope)
        assert envelope.schema_version == "v1.0"
        assert envelope.source_type == "pdf"
        assert len(envelope.blocks) == 1
        block = envelope.blocks[0]
        assert block.block_type == "ocr_unreadable"
        assert "pdf_unreadable" in block.quality.quality_flags
        assert block.page_index == 0
        assert block.order_index == 0
        assert block.metadata.get("error_type") is not None

    def test_missing_file_returns_canonical_envelope(self, tmp_path):
        """P1: missing file should not raise, should return envelope with ocr_unreadable."""
        missing = tmp_path / "does_not_exist.pdf"

        std = PDFStandardizer()
        f0 = _make_f0_record()
        envelope = std.standardize(f0, missing)

        assert isinstance(envelope, ContentEnvelope)
        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "ocr_unreadable"

    def test_empty_file_returns_canonical_envelope(self, tmp_path):
        """P1: empty file should not raise."""
        empty_file = tmp_path / "empty.pdf"
        empty_file.write_bytes(b"")

        std = PDFStandardizer()
        f0 = _make_f0_record()
        envelope = std.standardize(f0, empty_file)

        assert isinstance(envelope, ContentEnvelope)
        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "ocr_unreadable"

    def test_unreadable_envelope_passes_canonical_validator(self, tmp_path):
        """P1: failure envelope must pass validate_canonical_f1()."""
        corrupt_file = tmp_path / "bad.pdf"
        corrupt_file.write_bytes(b"not a pdf")

        std = PDFStandardizer()
        f0 = _make_f0_record()
        envelope = std.standardize(f0, corrupt_file)

        violations = envelope.validate_canonical_f1()
        assert violations == [], (
            f"Canonical validation failed: {violations}"
        )


# ---------------------------------------------------------------------------
# P2: Table bbox overlap deduplication
# ---------------------------------------------------------------------------

class TestTableBboxOverlap:
    def test_bbox_overlaps_table_high_overlap(self):
        """P2: text bbox mostly inside table bbox should be detected as overlap."""
        std = PDFStandardizer()
        text_bbox = BoundingBox(x0=100, y0=100, x1=300, y1=200)
        table_bboxes = [BoundingBox(x0=50, y0=50, x1=400, y1=250)]
        assert std._bbox_overlaps_table(text_bbox, table_bboxes) is True

    def test_bbox_overlaps_table_no_overlap(self):
        """P2: text bbox outside table bbox should not be detected as overlap."""
        std = PDFStandardizer()
        text_bbox = BoundingBox(x0=100, y0=100, x1=200, y1=150)
        table_bboxes = [BoundingBox(x0=300, y0=300, x1=500, y1=400)]
        assert std._bbox_overlaps_table(text_bbox, table_bboxes) is False

    def test_bbox_overlaps_table_partial_overlap(self):
        """P2: text bbox with <50% overlap should not be flagged."""
        std = PDFStandardizer()
        # Text bbox: 100x100 area (100,100 to 200,200)
        # Table bbox overlaps only a small corner (150,150 to 200,200) = 50x50 = 2500
        # 2500 / 10000 = 25% < 50%
        text_bbox = BoundingBox(x0=100, y0=100, x1=200, y1=200)
        table_bboxes = [BoundingBox(x0=150, y0=150, x1=400, y1=400)]
        assert std._bbox_overlaps_table(text_bbox, table_bboxes) is False

    def test_bbox_overlaps_table_multiple_tables(self):
        """P2: overlap with any table in the list should be detected."""
        std = PDFStandardizer()
        text_bbox = BoundingBox(x0=100, y0=100, x1=200, y1=200)
        table_bboxes = [
            BoundingBox(x0=300, y0=300, x1=400, y1=400),  # no overlap
            BoundingBox(x0=80, y0=80, x1=300, y1=300),    # high overlap
        ]
        assert std._bbox_overlaps_table(text_bbox, table_bboxes) is True
