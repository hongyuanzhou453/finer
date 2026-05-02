"""Tests for F1 canonical ContentEnvelope and ContentBlock schemas.

Tests cover:
- F1 canonical models: BoundingBox, BlockQuality, BlockProvenance
- ContentEnvelope creation and validation (canonical field names)
- ContentBlock creation and validation (canonical field names)
- Backward compatibility: order, quality_card, bbox list, source_type aliases
- Block ordering validation
- Helper methods
- Serialization/deserialization
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from finer.schemas.content_envelope import (
    BoundingBox,
    BlockQuality,
    BlockProvenance,
    ContentEnvelope,
    ContentBlock,
    BLOCK_TYPE_LITERAL,
    SOURCE_TYPE_LITERAL,
)
from finer.schemas.quality import QualityCard


# =============================================================================
# F1 Canonical Fixtures
# =============================================================================

@pytest.fixture
def block_quality() -> BlockQuality:
    """Create a standard F1 BlockQuality."""
    return BlockQuality(
        readability=0.9,
        extraction_confidence=0.85,
        structural_confidence=0.88,
        completeness=0.95,
        noise_score=0.05,
        quality_flags=["timestamp_parsed", "speaker_parsed"],
    )


@pytest.fixture
def low_block_quality() -> BlockQuality:
    """Create a low-quality F1 BlockQuality."""
    return BlockQuality(
        readability=0.4,
        extraction_confidence=0.3,
        structural_confidence=0.35,
        completeness=0.5,
        noise_score=0.7,
        quality_flags=["ocr_low_confidence", "system_noise"],
    )


@pytest.fixture
def provenance() -> BlockProvenance:
    """Create a standard BlockProvenance."""
    return BlockProvenance(
        raw_path="/data/raw/test.json",
        raw_offset_start=0,
        raw_offset_end=100,
        extractor="feishu_chat_standardizer",
        extractor_version="1.0.0",
        source_hash="abc123",
    )


@pytest.fixture
def quality_card() -> QualityCard:
    """Create a QualityCard for backward compat tests."""
    return QualityCard.create_default(overall=0.8)


# =============================================================================
# BoundingBox Tests
# =============================================================================

class TestBoundingBox:
    def test_creation(self):
        bb = BoundingBox(x0=10.0, y0=20.0, x1=100.0, y1=50.0)
        assert bb.x0 == 10.0
        assert bb.y0 == 20.0
        assert bb.x1 == 100.0
        assert bb.y1 == 50.0

    def test_invalid_negative_coordinates(self):
        with pytest.raises(ValidationError):
            BoundingBox(x0=-1, y0=0, x1=100, y1=50)

    def test_zero_coordinates_valid(self):
        bb = BoundingBox(x0=0, y0=0, x1=0, y1=0)
        assert bb.x0 == 0

    def test_geometry_x1_less_than_x0(self):
        with pytest.raises(ValidationError, match="x1.*>=.*x0"):
            BoundingBox(x0=100, y0=0, x1=50, y1=100)

    def test_geometry_y1_less_than_y0(self):
        with pytest.raises(ValidationError, match="y1.*>=.*y0"):
            BoundingBox(x0=0, y0=100, x1=100, y1=50)

    def test_geometry_x1_equals_x0_valid(self):
        bb = BoundingBox(x0=50, y0=0, x1=50, y1=100)
        assert bb.x0 == bb.x1

    def test_geometry_y1_equals_y0_valid(self):
        bb = BoundingBox(x0=0, y0=50, x1=100, y1=50)
        assert bb.y0 == bb.y1


# =============================================================================
# BlockQuality Tests
# =============================================================================

class TestBlockQuality:
    def test_creation(self, block_quality: BlockQuality):
        assert block_quality.readability == 0.9
        assert block_quality.extraction_confidence == 0.85
        assert block_quality.structural_confidence == 0.88
        assert block_quality.completeness == 0.95
        assert block_quality.noise_score == 0.05
        assert "timestamp_parsed" in block_quality.quality_flags

    def test_default_quality_flags(self):
        bq = BlockQuality(
            readability=0.5, extraction_confidence=0.5,
            structural_confidence=0.5, completeness=0.5, noise_score=0.5,
        )
        assert bq.quality_flags == []

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            BlockQuality(
                readability=1.5, extraction_confidence=0.5,
                structural_confidence=0.5, completeness=0.5, noise_score=0.5,
            )

    def test_score_lower_bound(self):
        with pytest.raises(ValidationError):
            BlockQuality(
                readability=-0.1, extraction_confidence=0.5,
                structural_confidence=0.5, completeness=0.5, noise_score=0.5,
            )


# =============================================================================
# BlockProvenance Tests
# =============================================================================

class TestBlockProvenance:
    def test_creation(self, provenance: BlockProvenance):
        assert provenance.raw_path == "/data/raw/test.json"
        assert provenance.raw_offset_start == 0
        assert provenance.raw_offset_end == 100
        assert provenance.extractor == "feishu_chat_standardizer"
        assert provenance.extractor_version == "1.0.0"
        assert provenance.source_hash == "abc123"

    def test_minimal(self):
        bp = BlockProvenance(extractor="test", extractor_version="0.1")
        assert bp.raw_path is None
        assert bp.model_name is None

    def test_model_name(self):
        bp = BlockProvenance(
            extractor="image_ocr_standardizer",
            extractor_version="1.0",
            model_name="qwen-vl-plus",
        )
        assert bp.model_name == "qwen-vl-plus"


# =============================================================================
# ContentBlock Canonical Tests
# =============================================================================

class TestContentBlockCanonical:
    """Tests using F1 canonical field names."""

    def test_minimal_canonical(self, block_quality: BlockQuality):
        block = ContentBlock(
            block_type="paragraph",
            text="This is a test paragraph.",
            order_index=0,
            quality=block_quality,
        )
        assert block.block_type == "paragraph"
        assert block.text == "This is a test paragraph."
        assert block.order_index == 0
        assert block.envelope_id is None
        assert block.speaker is None
        assert block.timestamp is None
        assert block.thread_id is None
        assert block.bbox is None
        assert block.provenance is None

    def test_all_canonical_fields(self, block_quality: BlockQuality, provenance: BlockProvenance):
        bb = BoundingBox(x0=10, y0=20, x1=100, y1=50)
        ts = datetime(2026, 4, 30, 10, 30)

        block = ContentBlock(
            block_id="block_123",
            envelope_id="env_abc",
            block_type="chat_message",
            text="Hello, welcome to the show.",
            order_index=5,
            speaker="Host",
            timestamp=ts,
            page_index=2,
            bbox=bb,
            start_time_sec=12.5,
            end_time_sec=15.3,
            parent_block_id="block_100",
            thread_id="thread_1",
            quality=block_quality,
            provenance=provenance,
            metadata={"custom": "value"},
        )

        assert block.block_id == "block_123"
        assert block.envelope_id == "env_abc"
        assert block.block_type == "chat_message"
        assert block.order_index == 5
        assert block.speaker == "Host"
        assert block.timestamp == ts
        assert block.bbox == bb
        assert block.thread_id == "thread_1"
        assert block.provenance.extractor == "feishu_chat_standardizer"
        assert block.metadata == {"custom": "value"}

    def test_invalid_time_range(self, block_quality: BlockQuality):
        with pytest.raises(ValidationError) as exc_info:
            ContentBlock(
                block_type="audio_segment",
                text="Invalid time range.",
                order_index=0,
                quality=block_quality,
                start_time_sec=20.0,
                end_time_sec=10.0,
            )
        assert "start_time_sec" in str(exc_info.value).lower()

    def test_auto_id_generation(self, block_quality: BlockQuality):
        b1 = ContentBlock(block_type="paragraph", text="First.", order_index=0, quality=block_quality)
        b2 = ContentBlock(block_type="paragraph", text="Second.", order_index=1, quality=block_quality)
        assert b1.block_id != b2.block_id
        assert b1.block_id.startswith("block_")


# =============================================================================
# ContentBlock Backward Compatibility Tests
# =============================================================================

class TestContentBlockBackwardCompat:
    """Tests for legacy field names (order, quality_card, bbox list)."""

    def test_order_alias(self, quality_card: QualityCard):
        """Legacy order= maps to order_index."""
        block = ContentBlock(
            block_type="paragraph",
            text="Legacy order.",
            order=0,
            quality_card=quality_card,
        )
        assert block.order_index == 0
        assert block.order == 0

    def test_quality_card_alias(self, quality_card: QualityCard):
        """Legacy quality_card=QualityCard maps to quality field, preserved as QualityCard."""
        block = ContentBlock(
            block_type="paragraph",
            text="Legacy quality.",
            order=0,
            quality_card=quality_card,
        )
        assert isinstance(block.quality, QualityCard)
        assert block.quality_card is block.quality

    def test_bbox_list_to_bounding_box(self, block_quality: BlockQuality):
        """Legacy bbox=[x0,y0,x1,y1] maps to BoundingBox."""
        block = ContentBlock(
            block_type="image_text",
            text="OCR text.",
            order_index=0,
            quality=block_quality,
            bbox=[10.0, 20.0, 100.0, 50.0],
        )
        assert isinstance(block.bbox, BoundingBox)
        assert block.bbox.x0 == 10.0
        assert block.bbox.x1 == 100.0

    def test_order_and_order_index_both_set(self, block_quality: BlockQuality):
        """When both order and order_index are set, order_index wins."""
        block = ContentBlock(
            block_type="paragraph",
            text="Both set.",
            order_index=3,
            order=99,
            quality=block_quality,
        )
        assert block.order_index == 3
        assert block.order == 3

    def test_quality_and_quality_card_both_set(self, block_quality: BlockQuality, quality_card: QualityCard):
        """When both quality and quality_card are set, quality wins."""
        block = ContentBlock(
            block_type="paragraph",
            text="Both set.",
            order_index=0,
            quality=block_quality,
            quality_card=quality_card,
        )
        assert isinstance(block.quality, BlockQuality)
        assert block.quality.readability == 0.9


# =============================================================================
# ContentEnvelope Canonical Tests
# =============================================================================

class TestContentEnvelopeCanonical:
    def test_minimal_canonical(self, quality_card: QualityCard):
        envelope = ContentEnvelope(
            source_type="feishu_chat",
            quality_card=quality_card,
        )
        assert envelope.source_type == "feishu_chat"
        assert envelope.schema_version == "v0.5"
        assert envelope.blocks == []
        assert envelope.metadata == {}
        assert envelope.envelope_id.startswith("env_")

    def test_all_canonical_fields(self, block_quality: BlockQuality, provenance: BlockProvenance):
        block = ContentBlock(
            block_type="chat_message",
            text="Hello.",
            order_index=0,
            quality=block_quality,
            provenance=provenance,
        )
        envelope = ContentEnvelope(
            envelope_id="env_test123",
            source_record_id="rec_456",
            source_type="feishu_chat",
            standardization_profile="feishu_chat_v1",
            source_uri="feishu://docs/abc123",
            source_title="Test Chat",
            raw_path="/data/raw/chat.json",
            creator_id="user_789",
            creator_name="Test User",
            published_at=datetime(2026, 4, 30, 10, 0),
            collected_at=datetime(2026, 4, 30, 9, 0),
            blocks=[block],
            quality_card=QualityCard.create_default(overall=0.8),
            metadata={"source": "test"},
        )

        assert envelope.envelope_id == "env_test123"
        assert envelope.source_record_id == "rec_456"
        assert envelope.source_type == "feishu_chat"
        assert envelope.standardization_profile == "feishu_chat_v1"
        assert envelope.raw_path == "/data/raw/chat.json"
        assert envelope.collected_at == datetime(2026, 4, 30, 9, 0)
        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].envelope_id == "env_test123"

    def test_title_alias(self, quality_card: QualityCard):
        """title= maps to source_title."""
        envelope = ContentEnvelope(
            source_type="image",
            title="My Image",
            quality_card=quality_card,
        )
        assert envelope.source_title == "My Image"

    def test_block_order_validation(self, block_quality: BlockQuality):
        b1 = ContentBlock(block_type="paragraph", text="First.", order_index=0, quality=block_quality)
        b2 = ContentBlock(block_type="paragraph", text="Third.", order_index=2, quality=block_quality)

        with pytest.raises(ValidationError) as exc_info:
            ContentEnvelope(
                source_type="feishu_chat",
                blocks=[b1, b2],
                quality_card=QualityCard.create_default(overall=0.8),
            )
        assert "sequential" in str(exc_info.value).lower()

    def test_envelope_id_populated_on_blocks(self, block_quality: BlockQuality):
        b = ContentBlock(block_type="paragraph", text="Test.", order_index=0, quality=block_quality)
        envelope = ContentEnvelope(
            envelope_id="env_xyz",
            source_type="feishu_chat",
            blocks=[b],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        assert envelope.blocks[0].envelope_id == "env_xyz"


# =============================================================================
# ContentEnvelope Helper Method Tests
# =============================================================================

class TestContentEnvelopeHelpers:
    def test_get_block_by_id(self, block_quality: BlockQuality):
        b1 = ContentBlock(block_id="a", block_type="paragraph", text="A.", order_index=0, quality=block_quality)
        b2 = ContentBlock(block_id="b", block_type="paragraph", text="B.", order_index=1, quality=block_quality)
        envelope = ContentEnvelope(
            source_type="feishu_chat",
            blocks=[b1, b2],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        assert envelope.get_block_by_id("b").text == "B."
        assert envelope.get_block_by_id("c") is None

    def test_get_blocks_by_type(self, block_quality: BlockQuality):
        b1 = ContentBlock(block_type="paragraph", text="P1.", order_index=0, quality=block_quality)
        b2 = ContentBlock(block_type="section_title", text="Title.", order_index=1, quality=block_quality)
        b3 = ContentBlock(block_type="paragraph", text="P2.", order_index=2, quality=block_quality)
        envelope = ContentEnvelope(
            source_type="feishu_chat",
            blocks=[b1, b2, b3],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        assert len(envelope.get_blocks_by_type("paragraph")) == 2
        assert len(envelope.get_blocks_by_type("section_title")) == 1
        assert len(envelope.get_blocks_by_type("table_region")) == 0

    def test_get_text_content(self, block_quality: BlockQuality):
        b1 = ContentBlock(block_type="paragraph", text="First.", order_index=0, quality=block_quality)
        b2 = ContentBlock(block_type="paragraph", text="Second.", order_index=1, quality=block_quality)
        envelope = ContentEnvelope(
            source_type="feishu_chat",
            blocks=[b1, b2],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        assert envelope.get_text_content() == "First.\n\nSecond."

    def test_serialization_roundtrip(self, block_quality: BlockQuality):
        b = ContentBlock(block_type="paragraph", text="Test.", order_index=0, quality=block_quality)
        envelope = ContentEnvelope(
            source_type="feishu_chat",
            source_title="Test Doc",
            blocks=[b],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        data = envelope.to_dict()
        assert data["source_type"] == "feishu_chat"
        assert len(data["blocks"]) == 1

        restored = ContentEnvelope.from_dict(data)
        assert restored.source_type == "feishu_chat"
        assert restored.source_title == "Test Doc"
        assert len(restored.blocks) == 1

    def test_compute_overall_quality(self, block_quality: BlockQuality, low_block_quality: BlockQuality):
        b1 = ContentBlock(block_type="paragraph", text="Good.", order_index=0, quality=block_quality)
        b2 = ContentBlock(block_type="paragraph", text="Bad.", order_index=1, quality=low_block_quality)
        envelope = ContentEnvelope(
            source_type="feishu_chat",
            blocks=[b1, b2],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        score = envelope.compute_overall_quality()
        assert 0.0 <= score <= 1.0

    def test_get_blocks_requiring_review_with_quality_card(self, block_quality: BlockQuality):
        """get_blocks_requiring_review works when blocks have QualityCard (backward compat)."""
        pass_card = QualityCard(
            readability_score=0.9, semantic_completeness_score=0.85,
            financial_relevance_score=0.9, entity_resolution_score=0.8,
            temporal_resolution_score=0.85, evidence_traceability_score=0.8,
        )
        review_card = QualityCard(
            readability_score=0.6, semantic_completeness_score=0.5,
            financial_relevance_score=0.55, entity_resolution_score=0.4,
            temporal_resolution_score=0.5, evidence_traceability_score=0.45,
        )

        # quality_card= preserves QualityCard, so gate_status is available
        b_pass = ContentBlock(block_type="paragraph", text="Good.", order_index=0, quality_card=pass_card)
        b_review = ContentBlock(block_type="paragraph", text="Bad.", order_index=1, quality_card=review_card)

        envelope = ContentEnvelope(
            source_type="feishu_chat",
            blocks=[b_pass, b_review],
            quality_card=pass_card,
        )
        review_blocks = envelope.get_blocks_requiring_review()
        assert len(review_blocks) == 1
        assert review_blocks[0].text == "Bad."


# =============================================================================
# Source Type Tests (Canonical F1)
# =============================================================================

class TestSourceTypes:
    def test_canonical_source_types(self, quality_card: QualityCard):
        """All F1 canonical source types are valid."""
        canonical_types: list[SOURCE_TYPE_LITERAL] = [
            "feishu_chat", "feishu_doc", "wechat_article", "image",
            "pdf", "audio_transcript", "video_transcript", "manual_text",
        ]
        for st in canonical_types:
            envelope = ContentEnvelope(source_type=st, quality_card=quality_card)
            assert envelope.source_type == st

    def test_deprecated_source_types(self, quality_card: QualityCard):
        """Deprecated source types still work for backward compatibility."""
        for st in ["chat", "text"]:
            envelope = ContentEnvelope(source_type=st, quality_card=quality_card)
            assert envelope.source_type == st

    def test_invalid_source_type(self, quality_card: QualityCard):
        with pytest.raises(ValidationError):
            ContentEnvelope(source_type="invalid_type", quality_card=quality_card)


# =============================================================================
# Block Type Tests (Canonical F1)
# =============================================================================

class TestBlockTypes:
    def test_canonical_block_types(self, block_quality: BlockQuality):
        """All F1 canonical block types are valid."""
        canonical_types: list[BLOCK_TYPE_LITERAL] = [
            "chat_message", "paragraph", "section_title", "image_text",
            "table_region", "chart_region", "audio_segment", "video_segment",
            "quote", "link_reference", "attachment_ref", "ocr_unreadable",
            "system_event",
        ]
        for bt in canonical_types:
            block = ContentBlock(block_type=bt, text=f"Block {bt}", order_index=0, quality=block_quality)
            assert block.block_type == bt

    def test_deprecated_block_types(self, block_quality: BlockQuality):
        """Deprecated block types still work for backward compatibility."""
        deprecated = ["heading", "table", "chart", "image_region", "transcript_segment", "list", "unknown"]
        for bt in deprecated:
            block = ContentBlock(block_type=bt, text=f"Deprecated {bt}", order_index=0, quality=block_quality)
            assert block.block_type == bt

    def test_invalid_block_type(self, block_quality: BlockQuality):
        with pytest.raises(ValidationError):
            ContentBlock(block_type="invalid_type", text="Bad.", order_index=0, quality=block_quality)


# =============================================================================
# Backward Compatibility: Source Envelope with QualityCard
# =============================================================================

class TestEnvelopeBackwardCompat:
    def test_envelope_with_quality_card(self, quality_card: QualityCard):
        """ContentEnvelope still accepts quality_card=QualityCard."""
        envelope = ContentEnvelope(
            source_type="chat",
            quality_card=quality_card,
        )
        assert envelope.quality_card.overall_score > 0
        assert envelope.source_type == "chat"

    def test_envelope_blocks_with_quality_card(self, quality_card: QualityCard):
        """ContentEnvelope blocks can use quality_card=QualityCard."""
        b = ContentBlock(
            block_type="paragraph",
            text="Legacy.",
            order=0,
            quality_card=quality_card,
        )
        envelope = ContentEnvelope(
            source_type="chat",
            blocks=[b],
            quality_card=quality_card,
        )
        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].order == 0


# =============================================================================
# F1 Canonical Validation Tests
# =============================================================================

def _canonical_envelope(
    block_quality: BlockQuality,
    provenance: BlockProvenance,
    **overrides,
) -> ContentEnvelope:
    """Build a fully canonical F1 envelope for testing."""
    defaults = dict(
        envelope_id="env_canonical_test",
        source_record_id="rec_001",
        schema_version="v1.0",
        source_type="feishu_chat",
        standardization_profile="feishu_chat_v1",
        raw_path="/data/raw/chat.json",
        blocks=[
            ContentBlock(
                block_type="chat_message",
                text="Hello.",
                order_index=0,
                quality=block_quality,
                provenance=provenance,
            ),
        ],
        quality_card=QualityCard.create_default(overall=0.8),
        temporal_anchors=[],
        entity_anchors=[],
    )
    defaults.update(overrides)

    # Fix envelope_id on blocks if overridden
    env_id = defaults.get("envelope_id", "env_canonical_test")
    for b in defaults.get("blocks", []):
        if b.envelope_id is None:
            object.__setattr__(b, "envelope_id", env_id)

    return ContentEnvelope(**defaults)


class TestValidateCanonicalF1:
    """Tests for ContentEnvelope.validate_canonical_f1()."""

    def test_canonical_pass(self, block_quality, provenance):
        """A fully canonical envelope returns empty violations."""
        env = _canonical_envelope(block_quality, provenance)
        assert env.validate_canonical_f1() == []

    # -- Check 1: legacy source_type --

    def test_legacy_source_type_chat(self, block_quality, provenance):
        env = _canonical_envelope(block_quality, provenance, source_type="chat")
        violations = env.validate_canonical_f1()
        assert any("source_type" in v and "chat" in v for v in violations)

    def test_legacy_source_type_text(self, block_quality, provenance):
        env = _canonical_envelope(block_quality, provenance, source_type="text")
        violations = env.validate_canonical_f1()
        assert any("source_type" in v and "text" in v for v in violations)

    # -- Check 2: legacy block_type --

    def test_legacy_block_type_heading(self, block_quality, provenance):
        b = ContentBlock(
            block_type="heading", text="Title.", order_index=0,
            quality=block_quality, provenance=provenance,
        )
        env = _canonical_envelope(block_quality, provenance, blocks=[b])
        violations = env.validate_canonical_f1()
        assert any("block_type" in v and "heading" in v for v in violations)

    def test_legacy_block_type_table(self, block_quality, provenance):
        b = ContentBlock(
            block_type="table", text="Data.", order_index=0,
            quality=block_quality, provenance=provenance,
        )
        env = _canonical_envelope(block_quality, provenance, blocks=[b])
        violations = env.validate_canonical_f1()
        assert any("block_type" in v and "table" in v for v in violations)

    def test_all_legacy_block_types_rejected(self, block_quality, provenance):
        """Every legacy block type produces a violation."""
        for bt in ["heading", "list", "table", "chart", "image_region", "transcript_segment", "unknown"]:
            b = ContentBlock(
                block_type=bt, text="x.", order_index=0,
                quality=block_quality, provenance=provenance,
            )
            env = _canonical_envelope(block_quality, provenance, blocks=[b])
            violations = env.validate_canonical_f1()
            assert any("block_type" in v and bt in v for v in violations), f"Expected violation for {bt}"

    # -- Check 3: quality must be BlockQuality --

    def test_quality_card_rejected(self, provenance, quality_card):
        """Block with QualityCard instead of BlockQuality is flagged."""
        b = ContentBlock(
            block_type="paragraph", text="Legacy quality.", order_index=0,
            quality_card=quality_card, provenance=provenance,
        )
        env = _canonical_envelope(
            QualityCard.create_default(overall=0.8), provenance, blocks=[b],
        )
        violations = env.validate_canonical_f1()
        assert any("quality" in v and "QualityCard" in v for v in violations)

    # -- Check 4: provenance required --

    def test_missing_provenance(self, block_quality):
        """Block without provenance is flagged."""
        b = ContentBlock(
            block_type="paragraph", text="No provenance.", order_index=0,
            quality=block_quality,
        )
        env = ContentEnvelope(
            envelope_id="env_test",
            source_type="feishu_chat",
            standardization_profile="feishu_chat_v1",
            blocks=[b],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        violations = env.validate_canonical_f1()
        assert any("provenance" in v for v in violations)

    # -- Check 5: order_index sequential --

    def test_non_sequential_order(self, block_quality, provenance):
        """Non-sequential order_index is flagged by canonical validator."""
        b1 = ContentBlock(
            block_type="paragraph", text="A.", order_index=0,
            quality=block_quality, provenance=provenance,
        )
        b2 = ContentBlock(
            block_type="paragraph", text="B.", order_index=1,
            quality=block_quality, provenance=provenance,
        )
        env = _canonical_envelope(block_quality, provenance, blocks=[b1, b2])
        # Mutate order_index after construction to bypass built-in validator
        object.__setattr__(b2, "order_index", 5)
        violations = env.validate_canonical_f1()
        assert any("order_index" in v and "sequential" in v for v in violations)

    # -- Check 6: envelope_id mismatch --

    def test_envelope_id_mismatch(self, block_quality, provenance):
        """Block with wrong envelope_id is flagged."""
        b = ContentBlock(
            block_type="paragraph", text="Wrong env.", order_index=0,
            quality=block_quality, provenance=provenance,
        )
        env = ContentEnvelope(
            envelope_id="env_correct",
            source_type="feishu_chat",
            standardization_profile="feishu_chat_v1",
            blocks=[b],
            quality_card=QualityCard.create_default(overall=0.8),
        )
        # Override the block's envelope_id after construction
        object.__setattr__(b, "envelope_id", "env_wrong")
        violations = env.validate_canonical_f1()
        assert any("envelope_id" in v and "env_wrong" in v for v in violations)

    # -- Check 7: temporal_anchors / entity_anchors must be empty --

    def test_temporal_anchors_not_empty(self, block_quality, provenance):
        from finer.schemas.temporal import TemporalAnchor
        anchor = TemporalAnchor(
            anchor_type="published_at", raw_text="2026-04-30",
            confidence=1.0, resolution_strategy="explicit_date",
        )
        env = _canonical_envelope(
            block_quality, provenance, temporal_anchors=[anchor],
        )
        violations = env.validate_canonical_f1()
        assert any("temporal_anchors" in v for v in violations)

    def test_entity_anchors_not_empty(self, block_quality, provenance):
        from finer.schemas.entity_anchor import EntityAnchor
        anchor = EntityAnchor(
            entity_type="stock", raw_text="AAPL", confidence=0.9,
        )
        env = _canonical_envelope(
            block_quality, provenance, entity_anchors=[anchor],
        )
        violations = env.validate_canonical_f1()
        assert any("entity_anchors" in v for v in violations)

    # -- Check 8: standardization_profile required --

    def test_missing_standardization_profile(self, block_quality, provenance):
        env = _canonical_envelope(
            block_quality, provenance, standardization_profile=None,
        )
        violations = env.validate_canonical_f1()
        assert any("standardization_profile" in v for v in violations)

    # -- Check 9: source_record_id required --

    def test_missing_source_record_id(self, block_quality, provenance):
        """Envelope with source_record_id=None is rejected."""
        env = _canonical_envelope(
            block_quality, provenance, source_record_id=None,
        )
        violations = env.validate_canonical_f1()
        assert any("source_record_id" in v for v in violations)

    def test_empty_string_source_record_id(self, block_quality, provenance):
        """Envelope with source_record_id='' is rejected."""
        env = _canonical_envelope(
            block_quality, provenance, source_record_id="",
        )
        violations = env.validate_canonical_f1()
        assert any("source_record_id" in v for v in violations)

    # -- Check 10: blocks must not be empty --

    def test_empty_blocks_rejected(self, block_quality):
        """Empty blocks=[] is rejected — adapter failure must not pass silently."""
        env = ContentEnvelope(
            envelope_id="env_test",
            source_record_id="rec_001",
            schema_version="v1.0",
            source_type="feishu_chat",
            standardization_profile="feishu_chat_v1",
            blocks=[],
            quality_card=QualityCard.create_default(overall=0.8),
            temporal_anchors=[],
            entity_anchors=[],
        )
        violations = env.validate_canonical_f1()
        assert any("blocks must not be empty" in v for v in violations)

    # -- Check 11: schema_version must be v1.0 --

    def test_schema_version_v0_5_rejected(self, block_quality, provenance):
        """Default v0.5 schema_version is rejected by canonical gate."""
        env = _canonical_envelope(
            block_quality, provenance, schema_version="v0.5",
        )
        violations = env.validate_canonical_f1()
        assert any("schema_version" in v and "v0.5" in v for v in violations)

    def test_schema_version_v1_0_passes(self, block_quality, provenance):
        env = _canonical_envelope(block_quality, provenance)
        # Already uses schema_version="v1.0" from helper
        violations = env.validate_canonical_f1()
        assert not any("schema_version" in v for v in violations)

    # -- Multiple violations --

    def test_multiple_violations(self, quality_card, provenance):
        """An envelope with multiple issues produces multiple violations."""
        b = ContentBlock(
            block_type="heading", text="Legacy.", order_index=0,
            quality_card=quality_card, provenance=provenance,
        )
        env = ContentEnvelope(
            source_type="chat",
            blocks=[b],
            quality_card=quality_card,
            temporal_anchors=["fake_anchor"],
        )
        object.__setattr__(b, "envelope_id", env.envelope_id)
        violations = env.validate_canonical_f1()
        # At least: schema_version, source_type, source_record_id, block_type, quality, temporal_anchors, standardization_profile
        assert len(violations) >= 6
