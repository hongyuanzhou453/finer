"""F1 Standardization Fixture Tests.

Manifest-driven structural assertion tests for 5 F0 samples.  Every assertion
is read from the fixture manifest's ``assertions`` dict — the manifest is the
single source of truth for what each sample must satisfy.

Design:
- Manifest structure tests: always pass (validate fixture JSON schema)
- Raw file tests: pass if file exists, skip in CI without data/
- F0 record tests: validate ContentRecord built from manifest before adapter
- Adapter output tests: xfail until F1 adapters are implemented
- All adapter assertions are driven by manifest['assertions'] keys
- F0 metadata propagation: adapter receives real ContentRecord, output must
  match manifest source_record_id / expected_profile / raw_path exactly
- Unknown assertion keys in manifest FAIL validation (no silent skip)

No golden text comparison. Assertions are structural.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Set

import pytest

from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    BoundingBox,
    ContentBlock,
    ContentEnvelope,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "f1_standardization"

# ---------------------------------------------------------------------------
# F1 source_type → F0 content_type mapping
# ---------------------------------------------------------------------------

# F0 ContentRecord uses a different content_type taxonomy than F1 source_type.
# This mapping translates manifest source_type to valid F0 content_type values.
_F1_SOURCE_TYPE_TO_F0_CONTENT_TYPE: Dict[str, str] = {
    "feishu_chat": "chat_transcript",
    "feishu_doc": "unclassified",
    "wechat_article": "wechat_article",
    "image": "unclassified",
    "pdf": "unclassified",
    "audio_transcript": "unclassified",
    "video_transcript": "unclassified",
    "manual_text": "unclassified",
}

# ---------------------------------------------------------------------------
# Fixture manifest loader
# ---------------------------------------------------------------------------

MANIFEST_FILES = [
    "chat_maodaren_0312.json",
    "img_9you_0416.json",
    "pdf_maodaren_0415.json",
    "img_9you_0409.json",
    "img_maodaren_0319.json",
]

REQUIRED_MANIFEST_KEYS = {
    "fixture_id",
    "source_type",
    "file_type",
    "raw_path",
    "source_record_id",
    "expected_adapter",
    "expected_profile",
    "assertions",
    "engineering_risks",
}

REQUIRED_ASSERTION_KEYS = {
    "blocks_non_empty",
    "order_index_sequential",
    "every_block_has_quality",
    "every_block_has_provenance",
    "passes_canonical_validator",
}


def _load_manifests() -> List[Dict[str, Any]]:
    manifests = []
    for fname in MANIFEST_FILES:
        path = FIXTURE_DIR / fname
        with open(path) as f:
            manifests.append(json.load(f))
    return manifests


def _resolve_raw_path(manifest: Dict[str, Any]) -> Path:
    return PROJECT_ROOT / manifest["raw_path"]


def _build_f0_record(manifest: Dict[str, Any]) -> ContentRecord:
    """Build a validated F0 ContentRecord from a fixture manifest.

    Maps F1 source_type to F0 content_type using the canonical mapping.
    Validates the result against ContentRecord schema before returning.
    """
    raw_path = _resolve_raw_path(manifest)
    published_at = manifest.get("published_at")
    if isinstance(published_at, str):
        published_at = datetime.fromisoformat(published_at)

    source_type = manifest["source_type"]
    f0_content_type = _F1_SOURCE_TYPE_TO_F0_CONTENT_TYPE.get(source_type)
    if f0_content_type is None:
        raise ValueError(
            f"No F0 content_type mapping for source_type '{source_type}'. "
            f"Update _F1_SOURCE_TYPE_TO_F0_CONTENT_TYPE."
        )

    record = ContentRecord(
        content_id=manifest["source_record_id"],
        creator_name=manifest.get("creator_name", ""),
        source_platform="feishu",
        content_type=f0_content_type,
        published_at=published_at,
        title=raw_path.name,
        source_path=str(raw_path),
        language="zh",
        metadata=manifest.get("metadata", {}),
    )
    return record


# ---------------------------------------------------------------------------
# Assertion registry
# ---------------------------------------------------------------------------
#
# Every key that can appear in manifest['assertions'] MUST be registered here.
# Unknown keys cause a validation failure — no silent skip.
#
# Handler signature: (envelope: ContentEnvelope, manifest: Dict) -> None
# Handlers raise AssertionError on failure.

def _assert_blocks_non_empty(envelope: ContentEnvelope, _m: Dict) -> None:
    assert len(envelope.blocks) > 0, "Envelope has no blocks."


def _assert_order_index_sequential(envelope: ContentEnvelope, _m: Dict) -> None:
    for i, block in enumerate(envelope.blocks):
        assert block.order_index == i, (
            f"Block {i} has order_index={block.order_index}, expected {i}"
        )


def _assert_every_block_has_quality(envelope: ContentEnvelope, _m: Dict) -> None:
    for i, block in enumerate(envelope.blocks):
        assert block.quality is not None, f"Block {i} has no quality"
        assert isinstance(block.quality, BlockQuality), (
            f"Block {i} quality is {type(block.quality).__name__}, expected BlockQuality"
        )


def _assert_every_block_has_provenance(envelope: ContentEnvelope, _m: Dict) -> None:
    for i, block in enumerate(envelope.blocks):
        assert block.provenance is not None, f"Block {i} has no provenance"
        assert isinstance(block.provenance, BlockProvenance)
        assert block.provenance.extractor, f"Block {i} extractor is empty"
        assert block.provenance.extractor_version, f"Block {i} extractor_version is empty"


def _assert_passes_canonical_validator(envelope: ContentEnvelope, _m: Dict) -> None:
    violations = envelope.validate_canonical_f1()
    assert violations == [], (
        f"Canonical validation failed ({len(violations)} violations):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def _assert_source_type_match(envelope: ContentEnvelope, manifest: Dict) -> None:
    expected = manifest["assertions"].get("source_type_must_be") or manifest["source_type"]
    assert envelope.source_type == expected, (
        f"source_type '{envelope.source_type}' != expected '{expected}'"
    )


def _assert_no_legacy_block_types(envelope: ContentEnvelope, _m: Dict) -> None:
    legacy = {"heading", "list", "table", "chart", "image_region",
              "transcript_segment", "unknown"}
    for i, block in enumerate(envelope.blocks):
        assert block.block_type not in legacy, (
            f"Block {i} uses legacy block_type '{block.block_type}'"
        )


def _assert_quality_is_block_quality(envelope: ContentEnvelope, _m: Dict) -> None:
    for i, block in enumerate(envelope.blocks):
        assert isinstance(block.quality, BlockQuality), (
            f"Block {i} quality is {type(block.quality).__name__}, expected BlockQuality"
        )


def _assert_envelope_id_propagated(envelope: ContentEnvelope, _m: Dict) -> None:
    for i, block in enumerate(envelope.blocks):
        assert block.envelope_id == envelope.envelope_id, (
            f"Block {i} envelope_id mismatch"
        )


def _assert_source_record_id_match(envelope: ContentEnvelope, manifest: Dict) -> None:
    expected = manifest["source_record_id"]
    assert envelope.source_record_id == expected, (
        f"source_record_id '{envelope.source_record_id}' != manifest '{expected}'"
    )


def _assert_standardization_profile_match(envelope: ContentEnvelope, manifest: Dict) -> None:
    expected = manifest["expected_profile"]
    assert envelope.standardization_profile == expected, (
        f"standardization_profile '{envelope.standardization_profile}' "
        f"!= manifest '{expected}'"
    )


def _assert_raw_path_match(envelope: ContentEnvelope, manifest: Dict) -> None:
    expected = str(_resolve_raw_path(manifest))
    assert envelope.raw_path == expected, (
        f"raw_path '{envelope.raw_path}' != manifest '{expected}'"
    )


def _assert_required_block_types(envelope: ContentEnvelope, manifest: Dict) -> None:
    required = manifest["assertions"].get("required_block_types", [])
    if not required:
        return
    present = {b.block_type for b in envelope.blocks}
    for bt in required:
        assert bt in present, (
            f"Required block_type '{bt}' not found. Present: {sorted(present)}"
        )


def _assert_page_index_populated(envelope: ContentEnvelope, _m: Dict) -> None:
    has_page = any(b.page_index is not None for b in envelope.blocks)
    assert has_page, "No block has page_index."


def _assert_min_region_types(envelope: ContentEnvelope, manifest: Dict) -> None:
    min_count = manifest["assertions"].get("min_region_types", 1)
    region_types = {"table_region", "chart_region", "image_text"}
    present = {b.block_type for b in envelope.blocks} & region_types
    assert len(present) >= min_count, (
        f"Expected >= {min_count} region types, found: {sorted(present)}"
    )


def _assert_must_identify_cover_or_chapter(envelope: ContentEnvelope, _m: Dict) -> None:
    structural = {"section_title", "paragraph"}
    present = {b.block_type for b in envelope.blocks}
    assert structural & present, (
        f"Expected section_title or paragraph, found: {sorted(present)}"
    )


def _assert_speaker_parsed(envelope: ContentEnvelope, _m: Dict) -> None:
    chat_blocks = [b for b in envelope.blocks if b.block_type == "chat_message"]
    assert chat_blocks, "No chat_message blocks found"
    with_speaker = [b for b in chat_blocks if b.speaker]
    assert with_speaker, "No chat_message block has speaker parsed."


def _assert_timestamp_parsed(envelope: ContentEnvelope, _m: Dict) -> None:
    chat_blocks = [b for b in envelope.blocks if b.block_type == "chat_message"]
    assert chat_blocks, "No chat_message blocks found"
    with_ts = [b for b in chat_blocks if b.timestamp is not None]
    assert with_ts, "No chat_message block has timestamp parsed."


def _assert_bbox_populated_when_layout(envelope: ContentEnvelope, _m: Dict) -> None:
    """Check bbox is populated when layout metadata indicates availability.

    If no block declares layout_available=True, this assertion is a no-op
    (layout data absent, bbox not expected).
    """
    layout_available = any(
        b.metadata.get("layout_available", False) for b in envelope.blocks
    )
    if not layout_available:
        return  # no layout data, bbox not expected
    has_bbox = any(b.bbox is not None for b in envelope.blocks)
    assert has_bbox, "Layout available but no block has bbox."


def _assert_optional_block_types_noop(envelope: ContentEnvelope, _m: Dict) -> None:
    """optional_block_types is documentation-only — no enforcement."""
    pass


# Complete registry — every key that can appear in manifest['assertions']
_ASSERTION_REGISTRY: Dict[str, Callable] = {
    # Boolean assertions (value must be True to trigger)
    "blocks_non_empty": _assert_blocks_non_empty,
    "order_index_sequential": _assert_order_index_sequential,
    "every_block_has_quality": _assert_every_block_has_quality,
    "every_block_has_provenance": _assert_every_block_has_provenance,
    "passes_canonical_validator": _assert_passes_canonical_validator,
    "block_type_must_not_be_legacy": _assert_no_legacy_block_types,
    "quality_must_be_block_quality": _assert_quality_is_block_quality,
    "page_index_populated": _assert_page_index_populated,
    "must_identify_cover_or_chapter": _assert_must_identify_cover_or_chapter,
    "speaker_parsed": _assert_speaker_parsed,
    "timestamp_parsed": _assert_timestamp_parsed,
    "bbox_populated_when_layout_available": _assert_bbox_populated_when_layout,
    # Manifest-value assertions
    "source_type_must_be": _assert_source_type_match,
    "required_block_types": _assert_required_block_types,
    "optional_block_types": _assert_optional_block_types_noop,  # doc-only
    "min_region_types": _assert_min_region_types,
    # F0 metadata propagation
    "source_record_id_match": _assert_source_record_id_match,
    "standardization_profile_match": _assert_standardization_profile_match,
    "raw_path_match": _assert_raw_path_match,
    # Always-on (not in manifest, always checked)
    "_envelope_id_propagated": _assert_envelope_id_propagated,
}

_ALWAYS_CHECK = {"_envelope_id_propagated"}


def get_unknown_assertion_keys(manifest: Dict[str, Any]) -> Set[str]:
    """Return assertion keys in manifest that are not in the registry."""
    assertions = manifest.get("assertions", {})
    return set(assertions.keys()) - set(_ASSERTION_REGISTRY.keys()) - _ALWAYS_CHECK


def run_manifest_assertions(
    envelope: ContentEnvelope, manifest: Dict[str, Any]
) -> List[str]:
    """Run all assertions declared in manifest['assertions'].

    Unknown keys cause a FAILURE, not a skip.  This prevents manifest/test
    drift — every assertion the manifest declares must have a handler.

    Returns list of failure descriptions (empty = all passed).
    """
    assertions = manifest.get("assertions", {})
    failures: List[str] = []

    # Fail on unknown keys — manifest must not declare unhandled assertions
    unknown = get_unknown_assertion_keys(manifest)
    if unknown:
        failures.append(
            f"[manifest] Unknown assertion keys (no handler): {sorted(unknown)}. "
            f"Register them in _ASSERTION_REGISTRY or remove from manifest."
        )

    # Run registered assertions
    for key, expected in assertions.items():
        handler = _ASSERTION_REGISTRY.get(key)
        if handler is None:
            continue  # already reported as unknown
        # Boolean: only run if True
        if isinstance(expected, bool) and not expected:
            continue
        try:
            handler(envelope, manifest)
        except AssertionError as e:
            failures.append(f"[{key}] {e}")
        except Exception as e:
            failures.append(f"[{key}] unexpected error: {e}")

    # Always-run checks
    for key in _ALWAYS_CHECK:
        handler = _ASSERTION_REGISTRY[key]
        try:
            handler(envelope, manifest)
        except AssertionError as e:
            failures.append(f"[{key}] {e}")

    return failures


# ---------------------------------------------------------------------------
# Adapter availability flags
# ---------------------------------------------------------------------------

_FEISHU_CHAT_ADAPTER_AVAILABLE = False
_IMAGE_OCR_ADAPTER_AVAILABLE = False
_PDF_ADAPTER_AVAILABLE = False

try:
    from finer.parsing.feishu_chat_standardizer import FeishuChatMarkdownStandardizer  # noqa: F401
    _FEISHU_CHAT_ADAPTER_AVAILABLE = True
except ImportError:
    pass

try:
    from finer.parsing.image_ocr_standardizer import ImageOCRLayoutStandardizer  # noqa: F401
    _IMAGE_OCR_ADAPTER_AVAILABLE = True
except ImportError:
    pass

try:
    from finer.parsing.pdf_standardizer import PDFStandardizer  # noqa: F401
    _PDF_ADAPTER_AVAILABLE = True
except ImportError:
    pass

ADAPTER_FLAGS = {
    "FeishuChatMarkdownStandardizer": _FEISHU_CHAT_ADAPTER_AVAILABLE,
    "ImageOCRLayoutStandardizer": _IMAGE_OCR_ADAPTER_AVAILABLE,
    "PDFStandardizer": _PDF_ADAPTER_AVAILABLE,
}

ADAPTER_IMPORT_ERROR = {
    "FeishuChatMarkdownStandardizer": "finer.parsing.feishu_chat_standardizer.FeishuChatMarkdownStandardizer",
    "ImageOCRLayoutStandardizer": "finer.parsing.image_ocr_standardizer.ImageOCRLayoutStandardizer",
    "PDFStandardizer": "finer.parsing.pdf_standardizer.PDFStandardizer",
}


def _adapter_available(adapter_name: str) -> bool:
    return ADAPTER_FLAGS.get(adapter_name, False)


def _xfail_reason(adapter_name: str) -> str:
    module = ADAPTER_IMPORT_ERROR.get(adapter_name, adapter_name)
    return f"F1 adapter {adapter_name} not implemented (import {module} failed)"


def _run_adapter(manifest: Dict[str, Any]) -> ContentEnvelope:
    """Run the F1 adapter with a validated F0 ContentRecord.

    Builds and validates a ContentRecord from the manifest, then passes it
    to the adapter together with the raw file path.

    Raises:
        pytest.xfail if adapter not available
        pytest.skip if raw file missing
    """
    adapter_name = manifest["expected_adapter"]
    if not _adapter_available(adapter_name):
        pytest.xfail(_xfail_reason(adapter_name))

    raw_path = _resolve_raw_path(manifest)
    if not raw_path.exists():
        pytest.skip(f"Raw file not found: {manifest['raw_path']}")

    f0_record = _build_f0_record(manifest)

    if adapter_name == "FeishuChatMarkdownStandardizer":
        from finer.parsing.feishu_chat_standardizer import FeishuChatMarkdownStandardizer
        std = FeishuChatMarkdownStandardizer()
        return std.standardize(f0_record, raw_path)

    if adapter_name == "ImageOCRLayoutStandardizer":
        from finer.parsing.image_ocr_standardizer import ImageOCRLayoutStandardizer
        std = ImageOCRLayoutStandardizer()
        return std.standardize(f0_record, raw_path)

    if adapter_name == "PDFStandardizer":
        from finer.parsing.pdf_standardizer import PDFStandardizer
        std = PDFStandardizer()
        return std.standardize(f0_record, raw_path)

    pytest.xfail(f"Unknown adapter: {adapter_name}")


# ===========================================================================
# Test Classes
# ===========================================================================


class TestFixtureManifest:
    """Validate fixture manifest JSON structure."""

    @pytest.fixture(params=MANIFEST_FILES, ids=[f.replace(".json", "") for f in MANIFEST_FILES])
    def manifest(self, request):
        path = FIXTURE_DIR / request.param
        with open(path) as f:
            return json.load(f)

    def test_manifest_has_required_keys(self, manifest: Dict):
        missing = REQUIRED_MANIFEST_KEYS - set(manifest.keys())
        assert not missing, f"Missing manifest keys: {missing}"

    def test_assertions_has_required_keys(self, manifest: Dict):
        assertions = manifest.get("assertions", {})
        missing = REQUIRED_ASSERTION_KEYS - set(assertions.keys())
        assert not missing, f"Missing assertion keys: {missing}"

    def test_assertions_has_no_unknown_keys(self, manifest: Dict):
        """Every assertion key must have a registered handler."""
        unknown = get_unknown_assertion_keys(manifest)
        assert not unknown, (
            f"Unknown assertion keys (no handler): {sorted(unknown)}. "
            f"Register in _ASSERTION_REGISTRY or remove from manifest."
        )

    def test_source_type_is_canonical(self, manifest: Dict):
        canonical = set(_F1_SOURCE_TYPE_TO_F0_CONTENT_TYPE.keys())
        assert manifest["source_type"] in canonical, (
            f"source_type '{manifest['source_type']}' not in mapping"
        )

    def test_engineering_risks_is_non_empty_list(self, manifest: Dict):
        risks = manifest.get("engineering_risks", [])
        assert isinstance(risks, list) and len(risks) > 0

    def test_expected_adapter_is_set(self, manifest: Dict):
        assert manifest["expected_adapter"]

    def test_expected_profile_is_set(self, manifest: Dict):
        assert manifest["expected_profile"]

    def test_source_record_id_is_set(self, manifest: Dict):
        assert manifest["source_record_id"]

    def test_raw_path_is_relative(self, manifest: Dict):
        assert not manifest["raw_path"].startswith("/")


class TestFixtureF0Record:
    """Validate that manifests produce valid F0 ContentRecord objects."""

    @pytest.fixture(params=MANIFEST_FILES, ids=[f.replace(".json", "") for f in MANIFEST_FILES])
    def manifest(self, request):
        path = FIXTURE_DIR / request.param
        with open(path) as f:
            return json.load(f)

    def test_f0_record_validates(self, manifest: Dict):
        """ContentRecord.model_validate must succeed for the built record."""
        record = _build_f0_record(manifest)
        # _build_f0_record already calls ContentRecord(...), which validates.
        # Double-check via model_validate for belt-and-suspenders.
        ContentRecord.model_validate(record.model_dump())

    def test_f0_record_content_id_matches(self, manifest: Dict):
        record = _build_f0_record(manifest)
        assert record.content_id == manifest["source_record_id"]

    def test_f0_record_source_path_matches(self, manifest: Dict):
        record = _build_f0_record(manifest)
        expected = str(_resolve_raw_path(manifest))
        assert record.source_path == expected


class TestFixtureRawFiles:
    """Validate raw files exist at manifest paths."""

    @pytest.fixture(params=MANIFEST_FILES, ids=[f.replace(".json", "") for f in MANIFEST_FILES])
    def manifest(self, request):
        path = FIXTURE_DIR / request.param
        with open(path) as f:
            return json.load(f)

    def test_raw_file_exists(self, manifest: Dict):
        raw_path = _resolve_raw_path(manifest)
        if not raw_path.exists():
            pytest.skip(
                f"Raw file not found: {manifest['raw_path']} "
                "(expected in CI with full data/ checkout)"
            )

    def test_raw_path_matches_extension(self, manifest: Dict):
        raw_path = _resolve_raw_path(manifest)
        if not raw_path.exists():
            pytest.skip("Raw file not found")
        assert raw_path.suffix == f".{manifest['file_type']}", (
            f"Extension {raw_path.suffix} != .{manifest['file_type']}"
        )


class TestF1ManifestDrivenAssertions:
    """Manifest-driven adapter acceptance tests.

    Every assertion is read from manifest['assertions'].  The manifest is the
    single source of truth — no hardcoded per-sample checks.

    All tests are xfail until F1 adapters are implemented.
    """

    @pytest.fixture(params=MANIFEST_FILES, ids=[f.replace(".json", "") for f in MANIFEST_FILES])
    def manifest(self, request):
        path = FIXTURE_DIR / request.param
        with open(path) as f:
            return json.load(f)

    def test_manifest_driven_assertions(self, manifest: Dict):
        """Run all assertions declared in the manifest."""
        envelope = _run_adapter(manifest)
        failures = run_manifest_assertions(envelope, manifest)
        assert failures == [], (
            f"{len(failures)} assertion(s) failed:\n"
            + "\n".join(f"  {f}" for f in failures)
        )

    def test_f0_metadata_propagation(self, manifest: Dict):
        """F0→F1 metadata must match manifest values exactly."""
        envelope = _run_adapter(manifest)
        errors = []
        if envelope.source_record_id != manifest["source_record_id"]:
            errors.append(
                f"source_record_id '{envelope.source_record_id}' "
                f"!= manifest '{manifest['source_record_id']}'"
            )
        if envelope.standardization_profile != manifest["expected_profile"]:
            errors.append(
                f"standardization_profile '{envelope.standardization_profile}' "
                f"!= manifest '{manifest['expected_profile']}'"
            )
        expected_raw = str(_resolve_raw_path(manifest))
        if envelope.raw_path != expected_raw:
            errors.append(
                f"raw_path '{envelope.raw_path}' != manifest '{expected_raw}'"
            )
        assert errors == [], (
            f"F0 metadata propagation failed:\n"
            + "\n".join(f"  {e}" for e in errors)
        )
