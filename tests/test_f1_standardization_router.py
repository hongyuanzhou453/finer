"""Tests for StandardizationRouter — F1 unified entry point.

Covers:
- Adapter selection logic (suffix, content_type, source_platform)
- End-to-end routing for each adapter type
- StandardizationReport fields
- Failure handling (corrupt files, missing files, unsupported types)
- ManualTextStandardizer canonical output
- Canonical validation on all routed envelopes
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict

import pytest

from finer.parsing.manual_text_standardizer import ManualTextStandardizer
from finer.parsing.standardization_router import (
    StandardizationError,
    StandardizationReport,
    StandardizationRouter,
)
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import ContentEnvelope

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "f1_standardization"


def _make_f0(
    content_id: str = "test_001",
    content_type: str = "unclassified",
    source_platform: str = "manual",
    source_path: str = "/tmp/test.txt",
    metadata: dict | None = None,
) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        creator_name="test_creator",
        source_platform=source_platform,
        content_type=content_type,
        published_at=datetime(2026, 4, 30, 12, 0, 0),
        title="test",
        source_path=source_path,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------

class TestSelectAdapter:
    def test_pdf_suffix_selects_pdf(self):
        router = StandardizationRouter()
        f0 = _make_f0(source_path="/tmp/report.pdf")
        assert router._select_adapter(f0, Path("/tmp/report.pdf")) == "pdf"

    def test_png_suffix_selects_image(self):
        router = StandardizationRouter()
        f0 = _make_f0(source_path="/tmp/slide.png")
        assert router._select_adapter(f0, Path("/tmp/slide.png")) == "image"

    def test_jpg_suffix_selects_image(self):
        router = StandardizationRouter()
        f0 = _make_f0(source_path="/tmp/photo.jpg")
        assert router._select_adapter(f0, Path("/tmp/photo.jpg")) == "image"

    def test_md_chat_transcript_selects_feishu_chat(self):
        router = StandardizationRouter()
        f0 = _make_f0(
            content_type="chat_transcript",
            source_path="/tmp/chat.md",
        )
        assert router._select_adapter(f0, Path("/tmp/chat.md")) == "feishu_chat"

    def test_md_feishu_platform_alone_selects_manual_text(self):
        """P1: feishu platform without chat content_type should NOT route to chat adapter."""
        router = StandardizationRouter()
        f0 = _make_f0(
            source_platform="feishu",
            content_type="unclassified",
            source_path="/tmp/note.md",
        )
        assert router._select_adapter(f0, Path("/tmp/note.md")) == "manual_text"

    def test_md_feishu_platform_with_chat_transcript_selects_feishu_chat(self):
        router = StandardizationRouter()
        f0 = _make_f0(
            source_platform="feishu",
            content_type="chat_transcript",
            source_path="/tmp/chat.md",
        )
        assert router._select_adapter(f0, Path("/tmp/chat.md")) == "feishu_chat"

    def test_md_unclassified_selects_manual_text(self):
        router = StandardizationRouter()
        f0 = _make_f0(
            content_type="unclassified",
            source_path="/tmp/article.md",
        )
        assert router._select_adapter(f0, Path("/tmp/article.md")) == "manual_text"

    def test_txt_selects_manual_text(self):
        router = StandardizationRouter()
        f0 = _make_f0(source_path="/tmp/notes.txt")
        assert router._select_adapter(f0, Path("/tmp/notes.txt")) == "manual_text"

    def test_livestream_audio_raises(self):
        router = StandardizationRouter()
        f0 = _make_f0(
            content_type="livestream_audio",
            source_path="/tmp/audio.mp3",
        )
        with pytest.raises(StandardizationError, match="Audio standardization"):
            router._select_adapter(f0, Path("/tmp/audio.mp3"))

    def test_unknown_suffix_returns_unsupported(self):
        router = StandardizationRouter()
        f0 = _make_f0(source_path="/tmp/data.csv")
        assert router._select_adapter(f0, Path("/tmp/data.csv")) == "unsupported"

    def test_chat_export_selects_feishu_chat(self):
        router = StandardizationRouter()
        f0 = _make_f0(
            content_type="chat_export",
            source_path="/tmp/export.md",
        )
        assert router._select_adapter(f0, Path("/tmp/export.md")) == "feishu_chat"


# ---------------------------------------------------------------------------
# ManualTextStandardizer
# ---------------------------------------------------------------------------

class TestManualText:
    def test_produces_canonical_envelope(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nSome body text here.\n\nMore content.")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        assert isinstance(envelope, ContentEnvelope)
        assert envelope.schema_version == "v1.0"
        assert envelope.source_type == "manual_text"
        assert envelope.standardization_profile == "manual_text_v1"
        assert len(envelope.blocks) >= 2

    def test_heading_becomes_section_title(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# My Heading\n\nBody text.")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        types = {b.block_type for b in envelope.blocks}
        assert "section_title" in types

    def test_url_becomes_link_reference(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Check https://example.com for details")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        types = {b.block_type for b in envelope.blocks}
        assert "link_reference" in types

    def test_empty_file_returns_unreadable(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "ocr_unreadable"

    def test_canonical_validation_passes(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nBody paragraph with enough text to pass quality checks.")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Violations: {violations}"

    def test_all_blocks_have_provenance(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Para one.\n\nPara two.\n\nPara three.")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        for block in envelope.blocks:
            assert block.provenance is not None
            assert block.provenance.extractor == "manual_text_standardizer"
            assert block.provenance.source_hash is not None

    def test_order_index_sequential(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("First.\n\nSecond.\n\nThird.")

        std = ManualTextStandardizer()
        f0 = _make_f0(source_path=str(f))
        envelope = std.standardize(f0, f)

        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i


# ---------------------------------------------------------------------------
# End-to-end routing
# ---------------------------------------------------------------------------

class TestRouteEndToEnd:
    def _load_manifest(self, name: str) -> Dict:
        path = FIXTURE_DIR / f"{name}.json"
        return json.loads(path.read_text())

    _SOURCE_TYPE_TO_CONTENT_TYPE = {
        "feishu_chat": "chat_transcript",
        "image": "unclassified",
        "pdf": "unclassified",
        "manual_text": "unclassified",
    }

    def _f0_from_manifest(self, manifest: Dict) -> ContentRecord:
        source_type = manifest.get("source_type", "manual_text")
        content_type = self._SOURCE_TYPE_TO_CONTENT_TYPE.get(source_type, "unclassified")
        source_platform = "feishu" if source_type == "feishu_chat" else "manual"
        return ContentRecord(
            content_id=manifest["source_record_id"],
            creator_name=manifest.get("creator_name", ""),
            source_platform=source_platform,
            content_type=content_type,
            published_at=datetime.fromisoformat(manifest["published_at"]),
            title=Path(manifest["raw_path"]).name,
            source_path=manifest["raw_path"],
            metadata=manifest.get("metadata", {}),
        )

    def test_pdf_fixture_routes_correctly(self):
        manifest = self._load_manifest("pdf_maodaren_0415")
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip("Raw file not found")

        router = StandardizationRouter()
        f0 = self._f0_from_manifest(manifest)
        envelope, report = router.route(f0, raw_path)

        assert report["adapter"] == "pdf"
        assert report["canonical_validation_passed"] is True
        assert report["block_count"] > 0
        assert envelope.source_type == "pdf"

    def test_image_fixture_routes_correctly(self):
        manifest = self._load_manifest("img_9you_0416")
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip("Raw file not found")

        router = StandardizationRouter()
        f0 = self._f0_from_manifest(manifest)
        envelope, report = router.route(f0, raw_path)

        assert report["adapter"] == "image"
        assert report["block_count"] > 0

    def test_chat_fixture_routes_correctly(self):
        manifest = self._load_manifest("chat_maodaren_0312")
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        if not raw_path.exists():
            pytest.skip("Raw file not found")

        router = StandardizationRouter()
        f0 = self._f0_from_manifest(manifest)
        envelope, report = router.route(f0, raw_path)

        assert report["adapter"] == "feishu_chat"
        assert report["block_count"] > 0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_fields_populated(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Heading\n\nBody text with enough content for quality.")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, report = router.route(f0, f)

        assert report["envelope_id"] == envelope.envelope_id
        assert report["adapter"] == "manual_text"
        assert report["block_count"] == len(envelope.blocks)
        assert isinstance(report["low_quality_block_count"], int)
        assert isinstance(report["warnings"], list)
        assert isinstance(report["canonical_validation_passed"], bool)

    def test_report_canonical_validation_true(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nParagraph with enough text for quality scoring.")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        _, report = router.route(f0, f)

        assert report["canonical_validation_passed"] is True
        assert report["warnings"] == []


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    def test_corrupt_pdf_returns_failure_envelope(self, tmp_path):
        f = tmp_path / "bad.pdf"
        f.write_bytes(b"not a pdf")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, report = router.route(f0, f)

        assert isinstance(envelope, ContentEnvelope)
        assert envelope.blocks[0].block_type == "ocr_unreadable"
        assert report["canonical_validation_passed"] is True
        assert report["adapter"] == "pdf"

    def test_missing_file_returns_failure_envelope(self, tmp_path):
        missing = tmp_path / "nope.pdf"

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(missing))
        envelope, report = router.route(f0, missing)

        assert isinstance(envelope, ContentEnvelope)
        assert envelope.blocks[0].block_type == "ocr_unreadable"

    def test_unsupported_type_returns_failure_envelope(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"a,b,c\n1,2,3")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, report = router.route(f0, f)

        assert isinstance(envelope, ContentEnvelope)
        assert envelope.blocks[0].block_type == "ocr_unreadable"
        assert "unsupported" in report["adapter"] or report["adapter"] == "unsupported"

    def test_audio_type_raises_standardization_error(self):
        router = StandardizationRouter()
        f0 = _make_f0(
            content_type="livestream_audio",
            source_path="/tmp/audio.mp3",
        )
        with pytest.raises(StandardizationError):
            router.route(f0, Path("/tmp/audio.mp3"))

    def test_failure_envelope_passes_canonical_validator(self, tmp_path):
        f = tmp_path / "bad.pdf"
        f.write_bytes(b"garbage")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, _ = router.route(f0, f)

        violations = envelope.validate_canonical_f1()
        assert violations == [], f"Violations: {violations}"

    def test_failure_envelope_source_type_matches_input(self, tmp_path):
        """P2: failure source_type should reflect the intended input, not always 'manual_text'."""
        router = StandardizationRouter()

        # PDF → source_type should be "pdf"
        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"not a pdf")
        f0 = _make_f0(source_path=str(pdf))
        envelope, _ = router.route(f0, pdf)
        assert envelope.source_type == "pdf"

        # Image → source_type should be "image"
        img = tmp_path / "bad.png"
        img.write_bytes(b"not an image")
        f0 = _make_f0(source_path=str(img))
        envelope, _ = router.route(f0, img)
        assert envelope.source_type == "image"

    def test_failure_envelope_has_intended_source_type_metadata(self, tmp_path):
        """P2: failure block metadata should record intended_source_type."""
        f = tmp_path / "data.csv"
        f.write_bytes(b"a,b,c")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, _ = router.route(f0, f)

        assert envelope.blocks[0].metadata.get("intended_source_type") is not None


# ---------------------------------------------------------------------------
# Canonical validation — all routed envelopes
# ---------------------------------------------------------------------------

class TestCanonicalValidation:
    def test_manual_text_passes_validator(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Report\n\nMarket analysis shows strong momentum in Q2.")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, _ = router.route(f0, f)

        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_empty_text_passes_validator(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, _ = router.route(f0, f)

        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_unsupported_passes_validator(self, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_bytes(b"random bytes")

        router = StandardizationRouter()
        f0 = _make_f0(source_path=str(f))
        envelope, _ = router.route(f0, f)

        violations = envelope.validate_canonical_f1()
        assert violations == []
