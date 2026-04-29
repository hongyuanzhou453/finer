"""Tests for F1.5 TopicBlock and TopicAssemblyResult schemas."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from finer.schemas.topic_block import TopicAssemblyResult, TopicBlock, TopicType


# =============================================================================
# Helpers
# =============================================================================

def _make_block(**overrides) -> dict:
    """Return a valid TopicBlock dict, with optional field overrides."""
    base = {
        "envelope_id": "env_test123",
        "source_block_ids": ["block_001", "block_002"],
        "topic_title": "泡泡玛特业绩分析",
        "topic_type": TopicType.SINGLE_STOCK,
        "start_block_index": 0,
        "end_block_index": 1,
        "raw_text": "泡泡玛特上半年业绩超预期，收入同比增长40%。",
    }
    base.update(overrides)
    return base


def _make_assembly(**overrides) -> dict:
    """Return a valid TopicAssemblyResult dict, with optional field overrides."""
    block = TopicBlock(**_make_block())
    base = {
        "envelope_id": "env_test123",
        "topic_blocks": [block],
    }
    base.update(overrides)
    return base


# =============================================================================
# TopicType Enum Tests
# =============================================================================

class TestTopicType:
    """Tests for TopicType enum values."""

    def test_all_expected_values_exist(self):
        expected = {
            "single_stock", "industry", "macro_policy",
            "market_commentary", "investment_philosophy",
            "portfolio_update", "news_forward", "other",
        }
        actual = {e.value for e in TopicType}
        assert actual == expected

    def test_enum_member_count(self):
        assert len(TopicType) == 8

    def test_string_comparison(self):
        assert TopicType.SINGLE_STOCK == "single_stock"
        assert TopicType.OTHER == "other"


# =============================================================================
# TopicBlock Serialization / Deserialization
# =============================================================================

class TestTopicBlockSerialization:
    """Tests for TopicBlock serialization and deserialization."""

    def test_create_minimal(self):
        block = TopicBlock(**_make_block())
        assert block.envelope_id == "env_test123"
        assert block.topic_type == TopicType.SINGLE_STOCK
        assert block.confidence == 1.0
        assert block.primary_entity_ids == []
        assert block.secondary_entity_ids == []
        assert block.ambiguity_flags == []
        assert block.summary == ""
        assert block.segmentation_reason == ""

    def test_create_full(self):
        now = datetime.now()
        block = TopicBlock(**_make_block(
            primary_entity_ids=["entity_001"],
            secondary_entity_ids=["entity_002"],
            start_time=now,
            end_time=now + timedelta(hours=1),
            summary="泡泡玛特业绩分析摘要",
            segmentation_reason="话题切换",
            confidence=0.85,
            ambiguity_flags=["low_entity_density"],
        ))
        assert block.primary_entity_ids == ["entity_001"]
        assert block.confidence == 0.85
        assert block.end_time > block.start_time

    def test_model_dump_roundtrip(self):
        """Serialize to dict and reconstruct — should be lossless."""
        original = TopicBlock(**_make_block(
            confidence=0.9,
            summary="Test summary",
        ))
        dumped = original.model_dump()
        restored = TopicBlock.model_validate(dumped)
        assert restored == original

    def test_model_dump_json_roundtrip(self):
        """Serialize to JSON string and reconstruct."""
        original = TopicBlock(**_make_block())
        json_str = original.model_dump_json()
        restored = TopicBlock.model_validate_json(json_str)
        assert restored == original

    def test_default_ids_are_unique(self):
        b1 = TopicBlock(**_make_block())
        b2 = TopicBlock(**_make_block())
        assert b1.topic_block_id != b2.topic_block_id

    def test_topic_type_from_string(self):
        """topic_type field should accept plain strings during deserialization."""
        data = _make_block(topic_type="industry")
        block = TopicBlock(**data)
        assert block.topic_type == "industry"
        assert block.topic_type in [e.value for e in TopicType]


# =============================================================================
# TopicBlock Validator Tests
# =============================================================================

class TestTopicBlockValidators:
    """Tests for TopicBlock field validators."""

    def test_invalid_confidence_below_zero(self):
        with pytest.raises(ValidationError, match="greater than or equal"):
            TopicBlock(**_make_block(confidence=-0.1))

    def test_invalid_confidence_above_one(self):
        with pytest.raises(ValidationError, match="less than or equal"):
            TopicBlock(**_make_block(confidence=1.1))

    def test_valid_confidence_boundaries(self):
        low = TopicBlock(**_make_block(confidence=0.0))
        assert low.confidence == 0.0
        high = TopicBlock(**_make_block(confidence=1.0))
        assert high.confidence == 1.0

    def test_invalid_block_index_end_before_start(self):
        with pytest.raises(ValidationError, match="end_block_index"):
            TopicBlock(**_make_block(start_block_index=5, end_block_index=2))

    def test_valid_block_index_equal(self):
        block = TopicBlock(**_make_block(
            start_block_index=3,
            end_block_index=3,
            source_block_ids=["block_003"],
        ))
        assert block.start_block_index == block.end_block_index

    def test_empty_source_block_ids(self):
        with pytest.raises(ValidationError, match="source_block_ids must not be empty"):
            TopicBlock(**_make_block(source_block_ids=[]))

    def test_end_time_before_start_time(self):
        now = datetime.now()
        with pytest.raises(ValidationError, match="end_time"):
            TopicBlock(**_make_block(
                start_time=now,
                end_time=now - timedelta(hours=1),
            ))

    def test_valid_time_range(self):
        now = datetime.now()
        block = TopicBlock(**_make_block(
            start_time=now,
            end_time=now + timedelta(hours=2),
        ))
        assert block.end_time > block.start_time

    def test_only_start_time_is_valid(self):
        block = TopicBlock(**_make_block(start_time=datetime.now()))
        assert block.start_time is not None
        assert block.end_time is None

    def test_only_end_time_is_valid(self):
        block = TopicBlock(**_make_block(end_time=datetime.now()))
        assert block.start_time is None
        assert block.end_time is not None

    def test_empty_raw_text(self):
        with pytest.raises(ValidationError, match="raw_text must not be empty"):
            TopicBlock(**_make_block(raw_text=""))

    def test_negative_start_block_index(self):
        with pytest.raises(ValidationError, match="greater than or equal"):
            TopicBlock(**_make_block(start_block_index=-1, end_block_index=0))


# =============================================================================
# TopicAssemblyResult Tests
# =============================================================================

class TestTopicAssemblyResult:
    """Tests for TopicAssemblyResult serialization and behavior."""

    def test_create_minimal(self):
        result = TopicAssemblyResult(**_make_assembly())
        assert result.envelope_id == "env_test123"
        assert len(result.topic_blocks) == 1
        assert result.unassigned_block_ids == []
        assert result.assembly_strategy == ""

    def test_create_with_unassigned(self):
        result = TopicAssemblyResult(**_make_assembly(
            unassigned_block_ids=["block_999"],
        ))
        assert result.unassigned_block_ids == ["block_999"]

    def test_model_dump_roundtrip(self):
        original = TopicAssemblyResult(**_make_assembly(
            assembly_strategy="llm_topic_split",
        ))
        dumped = original.model_dump()
        restored = TopicAssemblyResult.model_validate(dumped)
        assert restored == original

    def test_model_dump_json_roundtrip(self):
        original = TopicAssemblyResult(**_make_assembly())
        json_str = original.model_dump_json()
        restored = TopicAssemblyResult.model_validate_json(json_str)
        assert restored == original

    def test_default_ids_are_unique(self):
        a1 = TopicAssemblyResult(**_make_assembly())
        a2 = TopicAssemblyResult(**_make_assembly())
        assert a1.assembly_id != a2.assembly_id

    def test_created_at_default_is_recent(self):
        before = datetime.now()
        result = TopicAssemblyResult(**_make_assembly())
        after = datetime.now()
        assert before <= result.created_at <= after

    def test_empty_topic_blocks_is_valid(self):
        """An assembly with zero topic blocks is valid (all blocks unassigned)."""
        result = TopicAssemblyResult(
            envelope_id="env_test123",
            topic_blocks=[],
            unassigned_block_ids=["block_001", "block_002"],
        )
        assert len(result.topic_blocks) == 0
        assert len(result.unassigned_block_ids) == 2
