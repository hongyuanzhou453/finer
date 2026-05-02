"""Live MiMo Multimodal Pipeline Tests.

Two categories:
  1. Live tests (TestLiveImageOCR, TestLiveScannedPDFProbe): skipped unless
     FINER_ENABLE_LIVE_MIMO=1 and MIMO_API_KEY are set.
  2. Deterministic failure tests (TestFailureReporting): always run in CI,
     using temp files and mocks — no API key required.

Run live tests:
  FINER_ENABLE_LIVE_MIMO=1 MIMO_API_KEY=... python -m pytest tests/test_live_mimo_multimodal.py -v
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest

from finer.parsing.image_ocr_standardizer import ImageOCRLayoutStandardizer
from finer.parsing.pdf_standardizer import PDFStandardizer
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    ContentBlock,
    ContentEnvelope,
)

# ---------------------------------------------------------------------------
# Skip condition for live-only tests
# ---------------------------------------------------------------------------

_LIVE_ENABLED = os.getenv("FINER_ENABLE_LIVE_MIMO") == "1"
_MIMO_KEY_SET = bool(os.getenv("MIMO_API_KEY"))
_LIVE_READY = _LIVE_ENABLED and _MIMO_KEY_SET

_live_skip = pytest.mark.skipif(
    not _LIVE_READY,
    reason="Live MiMo tests require FINER_ENABLE_LIVE_MIMO=1 and MIMO_API_KEY",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "f1_standardization"

# One representative image fixture per creator
_IMAGE_FIXTURES = [
    "img_9you_0416.json",
    "img_maodaren_0319.json",
]

_PDF_FIXTURE = "pdf_maodaren_0415.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_manifest(name: str) -> Dict:
    import json

    with open(FIXTURE_DIR / name) as f:
        return json.load(f)


def _build_f0(manifest: Dict) -> ContentRecord:
    raw_path = PROJECT_ROOT / manifest["raw_path"]
    published_at = manifest.get("published_at")
    if isinstance(published_at, str):
        published_at = datetime.fromisoformat(published_at)

    return ContentRecord(
        content_id=manifest["source_record_id"],
        creator_name=manifest.get("creator_name", ""),
        source_platform="feishu",
        content_type="unclassified",
        published_at=published_at,
        title=raw_path.name,
        source_path=str(raw_path),
        language="zh",
        metadata=manifest.get("metadata", {}),
    )


def _assert_canonical(envelope: ContentEnvelope, label: str) -> None:
    violations = envelope.validate_canonical_f1()
    assert violations == [], (
        f"[{label}] Canonical validation failed ({len(violations)} violations):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def _assert_no_secrets_in_envelope(envelope: ContentEnvelope) -> None:
    """Ensure no API key appears in block text, metadata, or provenance."""
    import json

    blob = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
    mimo_key = os.getenv("MIMO_API_KEY", "")
    if mimo_key and len(mimo_key) > 8:
        assert mimo_key not in blob, "MIMO_API_KEY leaked into envelope"


def _collect_block_types(envelope: ContentEnvelope) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for b in envelope.blocks:
        counts[b.block_type] = counts.get(b.block_type, 0) + 1
    return counts


def _ocr_blocks(envelope: ContentEnvelope) -> List[ContentBlock]:
    """Blocks that were derived from OCR/VL extraction."""
    return [
        b
        for b in envelope.blocks
        if b.block_type in ("image_text", "paragraph", "section_title", "table_region", "chart_region")
        and b.provenance
        and b.provenance.model_name is not None
    ]


# ---------------------------------------------------------------------------
# Image tests
# ---------------------------------------------------------------------------


@_live_skip
class TestLiveImageOCR:
    """Validate image fixtures with real MiMo OCR."""

    @pytest.fixture(params=_IMAGE_FIXTURES, ids=[f.replace(".json", "") for f in _IMAGE_FIXTURES])
    def manifest(self, request):
        m = _load_manifest(request.param)
        raw = PROJECT_ROOT / m["raw_path"]
        if not raw.exists():
            pytest.skip(f"Raw file missing: {m['raw_path']}")
        return m

    def test_image_ocr_produces_content_blocks(self, manifest):
        """MiMo OCR must produce real content blocks, not only ocr_unreadable."""
        f0 = _build_f0(manifest)
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, raw_path)

        types = _collect_block_types(envelope)
        assert len(envelope.blocks) > 0
        # At least one non-failure block when MiMo succeeds
        content_types = set(types.keys()) - {"ocr_unreadable", "system_event"}
        assert content_types, (
            f"MiMo OCR returned only failure/noise blocks: {types}. "
            f"Expected at least one content block."
        )

    def test_image_canonical_validation(self, manifest):
        f0 = _build_f0(manifest)
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, raw_path)
        _assert_canonical(envelope, manifest["fixture_id"])

    def test_image_ocr_blocks_carry_model_name(self, manifest):
        """OCR/VL-derived blocks must have BlockProvenance.model_name."""
        f0 = _build_f0(manifest)
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, raw_path)

        ocr = _ocr_blocks(envelope)
        assert ocr, (
            "No blocks with model_name found — OCR/VL blocks must carry provenance.model_name"
        )
        for b in ocr:
            assert b.provenance.model_name, (
                f"Block {b.block_id} ({b.block_type}) has empty model_name"
            )

    def test_image_no_secret_leak(self, manifest):
        f0 = _build_f0(manifest)
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, raw_path)
        _assert_no_secrets_in_envelope(envelope)

    def test_image_metadata_propagation(self, manifest):
        f0 = _build_f0(manifest)
        raw_path = PROJECT_ROOT / manifest["raw_path"]
        std = ImageOCRLayoutStandardizer()
        envelope = std.standardize(f0, raw_path)

        assert envelope.source_record_id == manifest["source_record_id"]
        assert envelope.standardization_profile == manifest["expected_profile"]
        assert envelope.source_type == "image"


# ---------------------------------------------------------------------------
# Scanned PDF probe
# ---------------------------------------------------------------------------


@_live_skip
class TestLiveScannedPDFProbe:
    """Generate a scanned PDF from an image and validate MiMo OCR path."""

    def test_scanned_pdf_ocr_probe(self, tmp_path):
        """Create a single-page PDF from an image, run PDFStandardizer with MiMo."""
        # Use one of the real image fixtures as the source
        img_manifest = _load_manifest("img_9you_0416.json")
        img_path = PROJECT_ROOT / img_manifest["raw_path"]
        if not img_path.exists():
            pytest.skip(f"Image fixture missing: {img_manifest['raw_path']}")

        # Convert image to single-page PDF
        pdf_path = tmp_path / "scanned_probe.pdf"
        self._image_to_pdf(img_path, pdf_path)

        # Build a minimal F0 record
        f0 = ContentRecord(
            content_id="probe_scanned_pdf",
            creator_name="probe",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime(2026, 5, 2),
            title="scanned_probe.pdf",
            source_path=str(pdf_path),
            language="zh",
            metadata={},
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, pdf_path)

        # Must produce blocks
        assert len(envelope.blocks) > 0

        # Canonical validation
        _assert_canonical(envelope, "scanned_pdf_probe")

        # The scanned PDF path MUST produce real OCR content blocks.
        # If the only blocks are ocr_unreadable/system_event, the live
        # MiMo OCR path was not actually exercised.
        content_types = {
            b.block_type for b in envelope.blocks
        } - {"ocr_unreadable", "system_event"}
        assert content_types, (
            f"Scanned PDF probe produced only failure/noise blocks: "
            f"{_collect_block_types(envelope)}. "
            f"MiMo vision OCR did not produce real content."
        )

        # OCR-derived content blocks must carry model_name
        ocr = _ocr_blocks(envelope)
        assert ocr, (
            "No blocks with model_name — OCR/VL path was not exercised. "
            "Expected at least one content block with provenance.model_name."
        )
        for b in ocr:
            assert b.provenance.model_name, (
                f"Block {b.block_id} ({b.block_type}) has empty model_name"
            )

        # page_index must be set
        for b in envelope.blocks:
            assert b.page_index is not None, (
                f"Block {b.block_id} missing page_index"
            )

        # No secrets
        _assert_no_secrets_in_envelope(envelope)

    @staticmethod
    def _image_to_pdf(img_path: Path, pdf_path: Path) -> None:
        """Convert an image to a single-page PDF using Pillow."""
        from PIL import Image

        img = Image.open(img_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(pdf_path, "PDF")


# ---------------------------------------------------------------------------
# Failure reporting
# ---------------------------------------------------------------------------


class TestFailureReporting:
    """Validate that provider failures produce canonical envelopes."""

    def test_missing_key_produces_canonical_envelope(self, tmp_path):
        """When LLM client is None, adapter must emit ocr_unreadable."""
        img_path = tmp_path / "test.png"
        img_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        f0 = ContentRecord(
            content_id="fail_test",
            creator_name="test",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime(2026, 5, 2),
            title="test.png",
            source_path=str(img_path),
            language="zh",
            metadata={},
        )

        std = ImageOCRLayoutStandardizer(llm_client=None)
        envelope = std.standardize(f0, img_path)

        # Must have blocks
        assert len(envelope.blocks) > 0
        # Must have ocr_unreadable
        types = {b.block_type for b in envelope.blocks}
        assert "ocr_unreadable" in types
        # Canonical validation must pass
        _assert_canonical(envelope, "missing_key_failure")

    def test_empty_response_produces_canonical_envelope(self, tmp_path):
        """Empty vision response must produce ocr_unreadable, not empty blocks."""
        img_path = tmp_path / "test.png"
        img_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        f0 = ContentRecord(
            content_id="empty_resp_test",
            creator_name="test",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime(2026, 5, 2),
            title="test.png",
            source_path=str(img_path),
            language="zh",
            metadata={},
        )

        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.chat_with_images.return_value = ""

        std = ImageOCRLayoutStandardizer(llm_client=mock_client)
        envelope = std.standardize(f0, img_path)

        assert len(envelope.blocks) > 0
        # Empty response should trigger fallback
        types = {b.block_type for b in envelope.blocks}
        assert "ocr_unreadable" in types
        _assert_canonical(envelope, "empty_response_failure")

    def test_corrupt_pdf_produces_canonical_envelope(self, tmp_path):
        """Corrupt PDF must produce ocr_unreadable with pdf_unreadable flag."""
        corrupt_path = tmp_path / "corrupt.pdf"
        corrupt_path.write_bytes(b"not a real pdf")

        f0 = ContentRecord(
            content_id="corrupt_pdf",
            creator_name="test",
            source_platform="feishu",
            content_type="unclassified",
            published_at=datetime(2026, 5, 2),
            title="corrupt.pdf",
            source_path=str(corrupt_path),
            language="zh",
            metadata={},
        )

        std = PDFStandardizer()
        envelope = std.standardize(f0, corrupt_path)

        assert len(envelope.blocks) > 0
        types = {b.block_type for b in envelope.blocks}
        assert "ocr_unreadable" in types
        _assert_canonical(envelope, "corrupt_pdf_failure")
