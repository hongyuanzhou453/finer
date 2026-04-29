"""Tests for TopicAssembler — F1.5 deterministic topic grouping.

Tests verify:
- At least 5 TopicBlocks produced from a multi-topic envelope
- Each TopicBlock has non-empty source_block_ids
- raw_text is traceable to source blocks
- unassigned_block_ids exist and are reasonable
- No investment intent fields are produced
- Consecutive block merging works correctly
- Confidence varies by keyword specificity
"""

import pytest
from datetime import datetime

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.quality import QualityCard
from finer.schemas.topic_block import TopicAssemblyResult, TopicBlock, TopicType

from finer.parsing.topic_assembler import TopicAssembler, TopicRule, TOPIC_RULES


# =============================================================================
# Helpers
# =============================================================================

def _make_quality_card() -> QualityCard:
    """Create a default quality card for test blocks."""
    return QualityCard.create_default(overall=0.7)


def _make_block(order: int, text: str, block_id: str | None = None) -> ContentBlock:
    """Create a ContentBlock with given order and text."""
    kwargs: dict = {
        "block_type": "paragraph",
        "text": text,
        "order": order,
        "quality_card": _make_quality_card(),
    }
    if block_id:
        kwargs["block_id"] = block_id
    return ContentBlock(**kwargs)


def _make_envelope(blocks: list[ContentBlock], envelope_id: str = "env_test") -> ContentEnvelope:
    """Create a ContentEnvelope from blocks."""
    return ContentEnvelope(
        envelope_id=envelope_id,
        source_type="chat",
        blocks=blocks,
        quality_card=_make_quality_card(),
    )


# =============================================================================
# Cat Lord Multi-Topic Fixture (inline)
# =============================================================================

def _build_cat_lord_envelope() -> ContentEnvelope:
    """Build a multi-topic envelope simulating 猫大人's investment chat.

    Contains blocks covering:
    - 泡泡玛特 (2 blocks, should merge)
    - 新能源 (3 blocks covering 理想/蔚来/宁德时代, should merge)
    - 巴菲特 (1 block)
    - 老铺黄金 (2 blocks, should merge)
    - 卫星化学 (1 block)
    - Unrelated blocks (2 blocks → unassigned)
    """
    blocks = [
        # 0: 泡泡玛特 block 1
        _make_block(0, "今天聊聊泡泡玛特的Q4表现，营收同比增长超过120%，POP MART海外扩张太猛了。", "blk_ppmt_01"),
        # 1: 泡泡玛特 block 2
        _make_block(1, "泡泡玛特的IP矩阵越来越强，Labubu在东南亚已经成为现象级产品。9992.HK最近走势也不错。", "blk_ppmt_02"),
        # 2: Unrelated — 天气
        _make_block(2, "今天天气真好，适合出去散步。周末打算去爬山。", "blk_weather"),
        # 3: 新能源 block 1 — 理想汽车
        _make_block(3, "理想汽车的四季报出来了，环比增长还可以。新能源赛道竞争越来越激烈。", "blk_nev_01"),
        # 4: 新能源 block 2 — 蔚来
        _make_block(4, "蔚来的换电站布局很激进，小鹏在智驾上投入很大。NEV行业格局在变化。", "blk_nev_02"),
        # 5: 新能源 block 3 — 宁德时代
        _make_block(5, "宁德时代的神行电池量产了，CATL在储能领域也在发力。比亚迪的电池技术也在追赶。", "blk_nev_03"),
        # 6: 巴菲特 block
        _make_block(6, "读了巴菲特最新的股东信，伯克希尔的现金仓位创历史新高。价值投资的理念永不过时。", "blk_buffett"),
        # 7: 老铺黄金 block 1
        _make_block(7, "老铺黄金的门店体验确实不错，古法金工艺有差异化。老铺的定价策略很有意思。", "blk_gold_01"),
        # 8: 老铺黄金 block 2
        _make_block(8, "老铺黄金如果能保持现在的开店节奏，未来几年增长确定性很高。", "blk_gold_02"),
        # 9: Unrelated — 餐饮
        _make_block(9, "中午吃了碗牛肉面，味道不错。推荐给朋友们。", "blk_food"),
        # 10: 卫星化学
        _make_block(10, "卫星化学的C2产业链延伸做得不错，卫星的乙烷裂解项目进展顺利。", "blk_sat_01"),
    ]
    return _make_envelope(blocks, envelope_id="env_cat_lord_test")


# =============================================================================
# Test Suite
# =============================================================================


class TestTopicAssemblerBasic:
    """Basic functionality tests."""

    def test_produces_at_least_five_topic_blocks(self):
        """Cat Lord fixture should produce >= 5 TopicBlocks."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        assert len(result.topic_blocks) >= 5, (
            f"Expected >= 5 topic blocks, got {len(result.topic_blocks)}: "
            f"{[tb.topic_title for tb in result.topic_blocks]}"
        )

    def test_each_topic_block_has_non_empty_source_block_ids(self):
        """Every TopicBlock must reference at least one source block."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        for tb in result.topic_blocks:
            assert len(tb.source_block_ids) > 0, (
                f"TopicBlock '{tb.topic_title}' has empty source_block_ids"
            )

    def test_raw_text_is_traceable_to_source_blocks(self):
        """TopicBlock.raw_text must be the concatenation of source block texts."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        block_map = {b.block_id: b.text for b in envelope.blocks}

        for tb in result.topic_blocks:
            expected_text = "\n\n".join(
                block_map[bid] for bid in tb.source_block_ids
            )
            assert tb.raw_text == expected_text, (
                f"TopicBlock '{tb.topic_title}': raw_text does not match "
                f"concatenation of source block texts"
            )

    def test_unassigned_block_ids_exist(self):
        """Some blocks should be unassigned (weather, food)."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        assert len(result.unassigned_block_ids) > 0, (
            "Expected some unassigned blocks (weather, food)"
        )

    def test_unassigned_blocks_are_reasonable(self):
        """Unassigned blocks should be the non-financial ones."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        # The weather and food blocks should be unassigned
        assert "blk_weather" in result.unassigned_block_ids
        assert "blk_food" in result.unassigned_block_ids

    def test_no_investment_intent_fields(self):
        """TopicBlock must NOT contain direction/actionability/position fields.

        These are F3/F4 responsibilities, not F1.5.
        """
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        forbidden_fields = [
            "direction", "actionability", "position_delta_hint",
            "trade_action", "target_price", "stop_loss",
        ]

        dumped = result.model_dump()
        for tb_data in dumped["topic_blocks"]:
            for f in forbidden_fields:
                assert f not in tb_data, (
                    f"Forbidden field '{f}' found in TopicBlock"
                )

    def test_envelope_id_preserved(self):
        """Result envelope_id must match input."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        assert result.envelope_id == envelope.envelope_id

    def test_all_blocks_accounted_for(self):
        """Total blocks = sum of assigned + unassigned."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        assigned_ids = set()
        for tb in result.topic_blocks:
            assigned_ids.update(tb.source_block_ids)

        all_block_ids = {b.block_id for b in envelope.blocks}

        assert assigned_ids | set(result.unassigned_block_ids) == all_block_ids, (
            "Some blocks are neither assigned nor unassigned"
        )

    def test_no_block_lost(self):
        """Original block count must equal assigned + unassigned count."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        assigned_count = sum(len(tb.source_block_ids) for tb in result.topic_blocks)
        total = assigned_count + len(result.unassigned_block_ids)

        assert total == len(envelope.blocks), (
            f"Block count mismatch: {assigned_count} assigned + "
            f"{len(result.unassigned_block_ids)} unassigned != {len(envelope.blocks)} total"
        )


class TestTopicMatching:
    """Tests for keyword matching accuracy."""

    def test_popmart_topic_detected(self):
        """泡泡玛特/POP MART/9992.HK blocks should be grouped."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        popmart_blocks = [
            tb for tb in result.topic_blocks if tb.topic_title == "泡泡玛特"
        ]
        assert len(popmart_blocks) >= 1, "泡泡玛特 topic not found"

        # Should include both popmart blocks
        ppmt = popmart_blocks[0]
        assert "blk_ppmt_01" in ppmt.source_block_ids
        assert "blk_ppmt_02" in ppmt.source_block_ids

    def test_nev_topic_detected(self):
        """新能源/NEV/蔚来/理想/宁德时代 blocks should be grouped."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        nev_blocks = [
            tb for tb in result.topic_blocks if tb.topic_title == "新能源"
        ]
        assert len(nev_blocks) >= 1, "新能源 topic not found"

        nev = nev_blocks[0]
        assert "blk_nev_01" in nev.source_block_ids
        assert "blk_nev_02" in nev.source_block_ids
        assert "blk_nev_03" in nev.source_block_ids

    def test_buffett_topic_detected(self):
        """巴菲特/伯克希尔/股东信/价值投资 block should be grouped."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        buffett_blocks = [
            tb for tb in result.topic_blocks if tb.topic_title == "巴菲特/价值投资"
        ]
        assert len(buffett_blocks) >= 1, "巴菲特 topic not found"
        assert "blk_buffett" in buffett_blocks[0].source_block_ids

    def test_gold_topic_detected(self):
        """老铺黄金/老铺 blocks should be grouped."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        gold_blocks = [
            tb for tb in result.topic_blocks if tb.topic_title == "老铺黄金"
        ]
        assert len(gold_blocks) >= 1, "老铺黄金 topic not found"

        gold = gold_blocks[0]
        assert "blk_gold_01" in gold.source_block_ids
        assert "blk_gold_02" in gold.source_block_ids

    def test_satellite_chem_topic_detected(self):
        """卫星化学/卫星 block should be grouped."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        sat_blocks = [
            tb for tb in result.topic_blocks if tb.topic_title == "卫星化学"
        ]
        assert len(sat_blocks) >= 1, "卫星化学 topic not found"
        assert "blk_sat_01" in sat_blocks[0].source_block_ids


class TestConfidence:
    """Tests for confidence scoring."""

    def test_confidence_varies_by_specificity(self):
        """Different topics should have different confidence levels."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        confidences = {tb.topic_title: tb.confidence for tb in result.topic_blocks}

        # 泡泡玛特 (has stock code 9992.HK) should be high confidence
        assert confidences.get("泡泡玛特", 0) >= 0.9

        # 巴菲特 (person name) should be moderate
        assert confidences.get("巴菲特/价值投资", 0) >= 0.8

        # 老铺黄金 / 卫星化学 (short keyword) should be lower
        assert confidences.get("老铺黄金", 0) <= 0.8
        assert confidences.get("卫星化学", 0) <= 0.8

    def test_not_all_confidence_is_one(self):
        """Confidence should NOT all be 1.0 — rule-determined means varied."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        confidences = [tb.confidence for tb in result.topic_blocks]
        assert not all(c == 1.0 for c in confidences), (
            "All confidence is 1.0 — should vary by keyword specificity"
        )


class TestConsecutiveMerge:
    """Tests for consecutive block merging."""

    def test_consecutive_same_topic_merged(self):
        """Consecutive blocks with same topic should be one TopicBlock."""
        blocks = [
            _make_block(0, "泡泡玛特业绩很好。", "b1"),
            _make_block(1, "POP MART的海外收入增长。", "b2"),
            _make_block(2, "9992.HK股价走势不错。", "b3"),
        ]
        envelope = _make_envelope(blocks)
        assembler = TopicAssembler()
        result = assembler.assemble(envelope)

        popmart = [tb for tb in result.topic_blocks if tb.topic_title == "泡泡玛特"]
        assert len(popmart) == 1, "Three consecutive popmart blocks should merge into 1"
        assert len(popmart[0].source_block_ids) == 3

    def test_non_consecutive_same_topic_separate(self):
        """Non-consecutive blocks with same topic produce separate TopicBlocks."""
        blocks = [
            _make_block(0, "泡泡玛特业绩很好。", "b1"),
            _make_block(1, "今天天气不错。", "b2"),  # unrelated
            _make_block(2, "POP MART的海外收入增长。", "b3"),
        ]
        envelope = _make_envelope(blocks)
        assembler = TopicAssembler()
        result = assembler.assemble(envelope)

        popmart = [tb for tb in result.topic_blocks if tb.topic_title == "泡泡玛特"]
        assert len(popmart) == 2, "Separated blocks should produce 2 TopicBlocks"


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_envelope(self):
        """Empty envelope produces no topic blocks."""
        envelope = _make_envelope([])
        assembler = TopicAssembler()
        result = assembler.assemble(envelope)

        assert len(result.topic_blocks) == 0
        assert len(result.unassigned_block_ids) == 0

    def test_no_matching_blocks(self):
        """All-unrelated blocks produce no topic blocks, all unassigned."""
        blocks = [
            _make_block(0, "今天天气不错。", "b1"),
            _make_block(1, "中午吃了碗面。", "b2"),
        ]
        envelope = _make_envelope(blocks)
        assembler = TopicAssembler()
        result = assembler.assemble(envelope)

        assert len(result.topic_blocks) == 0
        assert len(result.unassigned_block_ids) == 2

    def test_single_matching_block(self):
        """A single block matching a topic produces one TopicBlock."""
        blocks = [
            _make_block(0, "巴菲特说价值投资最重要。", "b1"),
        ]
        envelope = _make_envelope(blocks)
        assembler = TopicAssembler()
        result = assembler.assemble(envelope)

        assert len(result.topic_blocks) == 1
        assert result.topic_blocks[0].source_block_ids == ["b1"]

    def test_block_index_range_correct(self):
        """start_block_index and end_block_index match source block orders."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        block_order_map = {b.block_id: b.order for b in envelope.blocks}

        for tb in result.topic_blocks:
            orders = [block_order_map[bid] for bid in tb.source_block_ids]
            assert tb.start_block_index == min(orders)
            assert tb.end_block_index == max(orders)


class TestAssemblyStrategy:
    """Tests for assembly metadata."""

    def test_assembly_strategy_set(self):
        """Assembly strategy should be documented."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        assert result.assembly_strategy, "assembly_strategy should not be empty"
        assert "keyword" in result.assembly_strategy.lower()

    def test_segmentation_reason_populated(self):
        """Each TopicBlock should have a segmentation_reason."""
        assembler = TopicAssembler()
        envelope = _build_cat_lord_envelope()
        result = assembler.assemble(envelope)

        for tb in result.topic_blocks:
            assert tb.segmentation_reason, (
                f"TopicBlock '{tb.topic_title}' missing segmentation_reason"
            )


class TestExtraRules:
    """Tests for custom rule injection."""

    def test_extra_rule_added(self):
        """Custom TopicRule can be injected at init time."""
        custom_rule = TopicRule(
            topic_key="custom",
            topic_title="自定义话题",
            topic_type=TopicType.OTHER,
            keywords=["自定义关键词", "CUSTOM_KEYWORD"],
            primary_entity_ids=["custom_entity"],
            confidence=0.8,
        )
        assembler = TopicAssembler(extra_rules=[custom_rule])
        blocks = [
            _make_block(0, "这段话包含自定义关键词，应该被匹配到。", "b1"),
        ]
        envelope = _make_envelope(blocks)
        result = assembler.assemble(envelope)

        custom = [tb for tb in result.topic_blocks if tb.topic_title == "自定义话题"]
        assert len(custom) == 1
        assert custom[0].confidence == 0.8
