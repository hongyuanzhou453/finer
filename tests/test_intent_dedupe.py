"""Tests for per-envelope intent deduplication (F3).

Live-data defect: the section loop emitted one intent per section, so a target
discussed in several sections produced N near-identical intents and N duplicate
TradeActions (3× A股, 2× 光模块, 2× 腾讯 from single envelopes).
"""
from __future__ import annotations

from finer.extraction.intent_extractor import (
    RuleBasedIntentExtractor,
    _dedupe_intents,
)
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.quality import QualityCard


def make_quality_card() -> QualityCard:
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.8,
        financial_relevance_score=0.9,
        entity_resolution_score=0.8,
        temporal_resolution_score=0.7,
        evidence_traceability_score=0.8,
    )


def make_envelope(blocks_text: list[str]) -> ContentEnvelope:
    blocks = [
        ContentBlock(
            block_type="paragraph",
            text=text,
            order=i,
            quality_card=make_quality_card(),
        )
        for i, text in enumerate(blocks_text)
    ]
    return ContentEnvelope(
        envelope_id="test_env_dedupe",
        source_type="feishu_doc",
        source_title="Dedupe Test",
        quality_card=make_quality_card(),
        blocks=blocks,
    )


def make_intent(**overrides) -> NormalizedInvestmentIntent:
    base = dict(
        envelope_id="env-1",
        block_ids=["b1"],
        creator_id="k1",
        target_type="stock",
        target_name="贵州茅台",
        target_symbol="600519.SH",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.55,
        confidence=0.85,
        time_horizon_hint="unknown",
        evidence_span_ids=["s1"],
        ambiguity_flags=[],
    )
    base.update(overrides)
    return NormalizedInvestmentIntent(**base)


class TestDedupeHelper:
    def test_merges_same_target_same_stance(self):
        notes: list[str] = []
        a = make_intent(block_ids=["b1"], evidence_span_ids=["s1"], conviction=0.55)
        b = make_intent(block_ids=["b2"], evidence_span_ids=["s2"], conviction=0.75)
        out = _dedupe_intents([a, b], notes)

        assert len(out) == 1
        merged = out[0]
        assert merged.block_ids == ["b1", "b2"]
        assert merged.evidence_span_ids == ["s1", "s2"]
        assert merged.conviction == 0.75  # strongest expression wins
        assert any("deduped 1" in n for n in notes)

    def test_opposite_stances_collapse_to_dominant(self):
        """Within ONE envelope, opposite stances are a contradiction, not a
        flip (flips live across envelopes over time) — keep the dominant
        conviction, flagged for review."""
        notes: list[str] = []
        a = make_intent(direction="bullish", conviction=0.55)
        b = make_intent(
            direction="bearish", position_delta_hint="reduce", conviction=0.75
        )
        out = _dedupe_intents([a, b], notes)
        assert len(out) == 1
        assert out[0].direction == "bearish"  # dominant conviction wins
        assert "conflicting_direction_in_envelope" in out[0].ambiguity_flags
        assert any("collapsed 1 contradictory" in n for n in notes)

    def test_mixed_direction_group_collapses_beyond_strict_opposites(self):
        """§1b is ONE direction per target per envelope — bearish + neutral
        on the same target (live GOOGL case: bearish 0.6 + neutral 0.4×2)
        also collapses to the dominant intent, not only bullish×bearish."""
        notes: list[str] = []
        a = make_intent(direction="bearish", conviction=0.6)
        b = make_intent(direction="neutral", conviction=0.4, position_delta_hint="none")
        c = make_intent(direction="neutral", conviction=0.4, position_delta_hint="hold")
        out = _dedupe_intents([a, b, c], notes)
        assert len(out) == 1
        assert out[0].direction == "bearish"
        assert "conflicting_direction_in_envelope" in out[0].ambiguity_flags

    def test_same_direction_compound_not_collapsed(self):
        """hold+add compound (same direction, different hints) is sanctioned
        dual output — the direction collapse must not touch it."""
        notes: list[str] = []
        a = make_intent(direction="bullish", position_delta_hint="hold")
        b = make_intent(direction="bullish", position_delta_hint="add")
        out = _dedupe_intents([a, b], notes)
        assert len(out) == 2

    def test_narrated_stance_change_keeps_both(self):
        """An explicit '我之前看多，现在转空' narration is a REAL reversal."""
        notes: list[str] = []
        a = make_intent(direction="bullish", conviction=0.55)
        b = make_intent(
            direction="bearish",
            position_delta_hint="reduce",
            conviction=0.75,
            ambiguity_flags=["stance_change"],
        )
        out = _dedupe_intents([a, b], notes)
        assert len(out) == 2

    def test_keeps_different_targets(self):
        notes: list[str] = []
        a = make_intent()
        b = make_intent(target_name="宁德时代", target_symbol="300750.SZ")
        out = _dedupe_intents([a, b], notes)
        assert len(out) == 2

    def test_time_horizon_prefers_known(self):
        notes: list[str] = []
        a = make_intent(time_horizon_hint="unknown")
        b = make_intent(time_horizon_hint="short_term")
        out = _dedupe_intents([a, b], notes)
        assert out[0].time_horizon_hint == "short_term"


class TestExtractorEndToEnd:
    def test_same_entity_across_sections_yields_one_intent(self):
        """Two sections, same entity + same stance → one merged intent."""
        envelope = make_envelope(
            [
                "## 白酒板块",
                "贵州茅台基本面扎实，建议买入，看多后市。",
                "## 收盘总结",
                "还是那句话，贵州茅台可以买入持有，坚定看多。",
            ]
        )
        result = RuleBasedIntentExtractor().extract(envelope)
        maotai = [i for i in result.intents if i.target_symbol == "600519.SH"]
        assert len(maotai) == 1, [
            (i.target_symbol, i.direction) for i in result.intents
        ]
        assert len(maotai[0].block_ids) >= 2  # evidence from both sections kept
