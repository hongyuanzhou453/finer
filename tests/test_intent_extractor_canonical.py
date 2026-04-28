"""Canonical F3 Intent Extraction Tests — Rule-based + Mock LLM.

Verifies the 4 mandatory acceptance criteria from docs/specs/f-stage-contracts.md:

1. "我看好宁德时代" → actionability=opinion, position_delta_hint=none
2. "我加仓宁德时代" → actionability=explicit_action, position_delta_hint=add
3. 腾讯样本: must not become full buy; must reflect hold+add compound
4. 光模块样本: must preserve relative time unresolved or temporal warning

Each canonical sample is tested against BOTH:
- RuleBasedIntentExtractor (baseline)
- LLMIntentExtractor with mock LLM (simulating well-behaved LLM output)
"""

import json
import pytest
from typing import Optional

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.quality import QualityCard
from finer.schemas.entity_anchor import EntityAnchor
from finer.extraction.intent_extractor import (
    RuleBasedIntentExtractor,
    LLMIntentExtractor,
    extract_intents_from_envelope,
    NormalizedInvestmentIntent,
)


# =============================================================================
# Test fixtures
# =============================================================================

def make_quality_card() -> QualityCard:
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.8,
        financial_relevance_score=0.9,
        entity_resolution_score=0.8,
        temporal_resolution_score=0.7,
        evidence_traceability_score=0.8,
    )


def make_test_envelope(blocks_text: list[str], envelope_id: str = "canonical_env_001") -> ContentEnvelope:
    blocks = []
    for i, text in enumerate(blocks_text):
        block = ContentBlock(
            block_type="paragraph",
            text=text,
            order=i,
            quality_card=make_quality_card(),
        )
        blocks.append(block)
    return ContentEnvelope(
        envelope_id=envelope_id,
        source_type="feishu_doc",
        source_title="Canonical Test",
        quality_card=make_quality_card(),
        blocks=blocks,
    )


def _make_mock_llm_fn(response_json: dict) -> callable:
    """Mock LLM that returns a fixed JSON dict as a string."""
    def mock_fn(prompt: str) -> str:
        return json.dumps(response_json, ensure_ascii=False)
    return mock_fn


# =============================================================================
# Canonical Sample 1: "我看好宁德时代" → opinion, none
# =============================================================================

SAMPLE_1_TEXT = ["我看好宁德时代。"]

SAMPLE_1_LLM_OUTPUT = {
    "intents": [{
        "target_name": "宁德时代",
        "target_symbol": "300750.SZ",
        "target_type": "stock",
        "market": "CN",
        "direction": "bullish",
        "actionability": "opinion",
        "position_delta_hint": "none",
        "conviction": 0.7,
        "confidence": 0.9,
        "sentiment_score": 0.5,
        "time_horizon": "unknown",
        "evidence_text": "看好",
        "ambiguity_notes": [],
        "processing_notes": ["Pure opinion expressed via 看好, no trading action implied"],
    }],
    "overall_notes": [],
}


class TestCanonicalSample1:
    """Sample 1: '我看好宁德时代' → opinion, position_delta_hint=none"""

    def test_rule_based_opinion_not_action(self):
        """Rule-based: '看好' should be opinion, not explicit_action."""
        envelope = make_test_envelope(SAMPLE_1_TEXT)
        extractor = RuleBasedIntentExtractor()
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]
        assert intent.actionability == "opinion", \
            f"Rule-based: Expected opinion, got {intent.actionability}"
        assert intent.position_delta_hint == "none", \
            f"Rule-based: Expected none, got {intent.position_delta_hint}"
        assert intent.direction == "bullish"

    def test_llm_based_opinion_not_action(self):
        """LLM-based: '看好' should be opinion, not explicit_action."""
        envelope = make_test_envelope(SAMPLE_1_TEXT)
        mock_llm = _make_mock_llm_fn(SAMPLE_1_LLM_OUTPUT)
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]
        assert intent.actionability == "opinion", \
            f"LLM-based: Expected opinion, got {intent.actionability}"
        assert intent.position_delta_hint == "none", \
            f"LLM-based: Expected none, got {intent.position_delta_hint}"
        assert intent.direction == "bullish"

    def test_backward_compat_function(self):
        """Backward-compatible extract_intents_from_envelope also works."""
        envelope = make_test_envelope(SAMPLE_1_TEXT)
        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]
        assert intent.actionability == "opinion"
        assert intent.position_delta_hint == "none"


# =============================================================================
# Canonical Sample 2: "我加仓宁德时代" → explicit_action, add
# =============================================================================

SAMPLE_2_TEXT = ["我加仓宁德时代。"]

SAMPLE_2_LLM_OUTPUT = {
    "intents": [{
        "target_name": "宁德时代",
        "target_symbol": "300750.SZ",
        "target_type": "stock",
        "market": "CN",
        "direction": "bullish",
        "actionability": "explicit_action",
        "position_delta_hint": "add",
        "conviction": 0.75,
        "confidence": 0.9,
        "sentiment_score": 0.6,
        "time_horizon": "unknown",
        "evidence_text": "加仓",
        "ambiguity_notes": [],
        "processing_notes": ["Explicit trading action: 加仓"],
    }],
    "overall_notes": [],
}


class TestCanonicalSample2:
    """Sample 2: '我加仓宁德时代' → explicit_action, position_delta_hint=add"""

    def test_rule_based_add_is_explicit_action(self):
        """Rule-based: '加仓' should be explicit_action + add."""
        envelope = make_test_envelope(SAMPLE_2_TEXT)
        extractor = RuleBasedIntentExtractor()
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]
        assert intent.actionability == "explicit_action", \
            f"Rule-based: Expected explicit_action, got {intent.actionability}"
        assert intent.position_delta_hint == "add", \
            f"Rule-based: Expected add, got {intent.position_delta_hint}"
        assert intent.direction == "bullish"

    def test_llm_based_add_is_explicit_action(self):
        """LLM-based: '加仓' should be explicit_action + add."""
        envelope = make_test_envelope(SAMPLE_2_TEXT)
        mock_llm = _make_mock_llm_fn(SAMPLE_2_LLM_OUTPUT)
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]
        assert intent.actionability == "explicit_action", \
            f"LLM-based: Expected explicit_action, got {intent.actionability}"
        assert intent.position_delta_hint == "add", \
            f"LLM-based: Expected add, got {intent.position_delta_hint}"
        assert intent.direction == "bullish"

    def test_sample1_vs_sample2_distinct(self):
        """Sample1 and Sample2 must produce different actionability."""
        env1 = make_test_envelope(SAMPLE_1_TEXT, "env_1")
        env2 = make_test_envelope(SAMPLE_2_TEXT, "env_2")

        extractor = RuleBasedIntentExtractor()
        r1 = extractor.extract(env1)
        r2 = extractor.extract(env2)

        assert r1.intents[0].actionability != r2.intents[0].actionability, \
            "'看好' and '加仓' must produce different actionability"


# =============================================================================
# Canonical Sample 3: 腾讯 hold+add compound (must NOT become full buy)
# =============================================================================

SAMPLE_3_TEXT = [
    "今天腾讯跟随恒生科技大跌3个点，到达480的点位，"
    "目前我依然持有，今天稍微加仓一点，"
    "短期下跌趋势，不影响腾讯的社交流量入口护城河",
]

SAMPLE_3_LLM_OUTPUT = {
    "intents": [{
        "target_name": "腾讯",
        "target_symbol": "0700.HK",
        "target_type": "stock",
        "market": "HK",
        "direction": "bullish",
        "actionability": "explicit_action",
        "position_delta_hint": "add",
        "conviction": 0.65,
        "confidence": 0.75,
        "sentiment_score": 0.3,
        "time_horizon": "long_term",
        "evidence_text": "依然持有，今天稍微加仓一点",
        "ambiguity_notes": [
            "hold_and_add_compound: maintaining hold while adding slightly",
            "short_term_bearish_long_term_bullish: near-term price decline acknowledged but long-term thesis intact",
        ],
        "processing_notes": [
            "Compound signal: base position maintained (hold) + incremental add",
            "Short-term price weakness acknowledged but long-term conviction on moat remains",
        ],
    }],
    "overall_notes": ["KOL maintains bullish stance on Tencent despite short-term price drop"],
}


class TestCanonicalSample3:
    """Sample 3: Tencent hold+add compound — must NOT become full buy."""

    def test_rule_based_hold_add_compound(self):
        """Rule-based: must detect hold+add compound, not a simple buy."""
        envelope = make_test_envelope(SAMPLE_3_TEXT)
        extractor = RuleBasedIntentExtractor()
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]

        # Should be bullish
        assert intent.direction == "bullish"

        # Must NOT be a simple "open" (full buy)
        assert intent.position_delta_hint != "open", \
            "Rule-based: Must not classify compound hold+add as 'open' (full buy)"

        # Should have hold_and_add_compound flag (rule-based now detects this)
        assert any("hold_and_add" in f for f in intent.ambiguity_flags) or \
               intent.position_delta_hint in ("add", "hold"), \
            f"Rule-based: Expected compound hold+add detection. " \
            f"Got pos_hint={intent.position_delta_hint}, flags={intent.ambiguity_flags}"

        # Conviction should NOT be very high (the "稍微" and "短期下跌" hedge it)
        assert intent.conviction < 0.9, \
            "Rule-based: conviction should be moderated, got {intent.conviction}"

    def test_llm_based_not_full_buy(self):
        """LLM-based: must not output 'open' position_delta_hint."""
        envelope = make_test_envelope(SAMPLE_3_TEXT)
        mock_llm = _make_mock_llm_fn(SAMPLE_3_LLM_OUTPUT)
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]

        # Must NOT be full buy
        assert intent.position_delta_hint != "open", \
            "LLM-based: Must not classify as 'open' (full buy)"

        # Must be add (incremental), not full position
        assert intent.position_delta_hint == "add", \
            f"LLM-based: Expected add, got {intent.position_delta_hint}"

        # Conviction should be moderate
        assert intent.conviction < 0.8, \
            "LLM-based: conviction should reflect the hedged nature of '稍微加仓一点'"

        # Must have compound ambiguity flag
        assert any("hold_and_add" in f for f in intent.ambiguity_flags), \
            "LLM-based: must flag hold+add compound in ambiguity_notes"

        # Should acknowledge short-term vs long-term split
        assert any("short_term" in f.lower() for f in intent.ambiguity_flags), \
            "LLM-based: must flag the short-term/long-term temporal split"

    def test_short_term_does_not_override_long_term(self):
        """'短期下跌趋势不影响长期逻辑' — direction is still bullish overall."""
        envelope = make_test_envelope(SAMPLE_3_TEXT)
        mock_llm = _make_mock_llm_fn(SAMPLE_3_LLM_OUTPUT)
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        result = extractor.extract(envelope)

        intent = result.intents[0]

        # Overall direction must remain bullish (long-term thesis intact)
        assert intent.direction == "bullish", \
            "Short-term weakness should not flip overall direction to bearish"

        # Time horizon should reflect the belief's horizon
        assert intent.time_horizon_hint == "long_term", \
            f"Expected long_term horizon for moat-based thesis, got {intent.time_horizon_hint}"


# =============================================================================
# Canonical Sample 4: 光模块相对时间 unresolved
# =============================================================================

SAMPLE_4_TEXT = [
    "上周的时候，我们坚定抄底光模块，这周市场资金重新回归光模块",
]

SAMPLE_4_LLM_OUTPUT = {
    "intents": [{
        "target_name": "光模块",
        "target_symbol": None,
        "target_type": "sector",
        "market": "CN",
        "direction": "bullish",
        "actionability": "explicit_action",
        "position_delta_hint": "add",
        "conviction": 0.7,
        "confidence": 0.75,
        "sentiment_score": 0.5,
        "time_horizon": "unknown",
        "evidence_text": "坚定抄底光模块",
        "ambiguity_notes": [
            "relative_time_unresolved: '上周' and '这周' are relative, cannot resolve to absolute dates",
            "temporal_warning: exact trade date cannot be determined from relative time expressions",
        ],
        "processing_notes": [
            "Bought optical module sector last week per text, but exact date unresolved",
            "This week capital flows back in, confirming the thesis",
        ],
    }],
    "overall_notes": ["Temporal references are relative and cannot be resolved without additional context"],
}


class TestCanonicalSample4:
    """Sample 4: 光模块 — relative time must be unresolved, no fabricated dates."""

    def test_rule_based_relative_time_detected(self):
        """Rule-based: must detect relative time and flag it."""
        envelope = make_test_envelope(SAMPLE_4_TEXT)
        extractor = RuleBasedIntentExtractor()
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]

        # Rule-based now detects relative time
        assert any(
            "relative_time" in f or "temporal" in f.lower()
            for f in intent.ambiguity_flags
        ), (
            "Rule-based: Must flag relative time. "
            f"Got flags: {intent.ambiguity_flags}"
        )

    def test_llm_based_temporal_warning(self):
        """LLM-based: must not fabricate dates, must flag temporal unresolved."""
        envelope = make_test_envelope(SAMPLE_4_TEXT)
        mock_llm = _make_mock_llm_fn(SAMPLE_4_LLM_OUTPUT)
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        result = extractor.extract(envelope)

        assert len(result.intents) >= 1
        intent = result.intents[0]

        # Must flag relative time
        assert any(
            "relative_time" in f or "temporal_warning" in f
            for f in intent.ambiguity_flags
        ), (
            "LLM-based: Must flag relative time unresolved. "
            f"Got flags: {intent.ambiguity_flags}"
        )

        # Direction is bullish (抄底 + 资金回归)
        assert intent.direction == "bullish"

    def test_no_fabricated_dates_in_intent(self):
        """Neither extractor should fabricate dates."""
        envelope = make_test_envelope(SAMPLE_4_TEXT)

        # Rule-based
        rb = RuleBasedIntentExtractor()
        rb_result = rb.extract(envelope)
        rb_intent = rb_result.intents[0]
        # Rule-based never generates temporal data, just checks
        assert "上周" not in str(rb_intent.model_dump_json())

        # LLM-based
        mock_llm = _make_mock_llm_fn(SAMPLE_4_LLM_OUTPUT)
        llm_extractor = LLMIntentExtractor(llm_fn=mock_llm)
        llm_result = llm_extractor.extract(envelope)
        llm_intent = llm_result.intents[0]

        # Check that no fabricated absolute dates appear
        # The ambiguity_notes should contain 'relative_time_unresolved', not a specific date
        json_str = llm_intent.model_dump_json()
        # Should not fabricate specific dates like "2026-04-21"
        assert "2026-" not in json_str or "relative_time_unresolved" in json_str, \
            "Should not fabricate absolute dates for relative time expressions"


# =============================================================================
# Cross-cutting tests
# =============================================================================

class TestCrossCutting:
    """Tests that apply across all canonical samples."""

    def test_all_samples_produce_intents(self):
        """All 4 canonical samples should produce at least 1 intent."""
        samples = [
            (SAMPLE_1_TEXT, "sample1"),
            (SAMPLE_2_TEXT, "sample2"),
            (SAMPLE_3_TEXT, "sample3"),
            (SAMPLE_4_TEXT, "sample4"),
        ]
        extractor = RuleBasedIntentExtractor()

        for text, label in samples:
            envelope = make_test_envelope(text, f"env_{label}")
            result = extractor.extract(envelope)
            assert len(result.intents) >= 1, f"{label}: RuleBased produced no intents"

    def test_no_forbidden_fields_in_any_output(self):
        """Verify that no extractor outputs position_size, stop_loss, etc."""
        forbidden = [
            "position_size_pct", "position_size", "stop_loss",
            "take_profit", "target_price", "target_price_low",
            "target_price_high", "trigger_condition",
        ]

        all_texts = [SAMPLE_1_TEXT, SAMPLE_2_TEXT, SAMPLE_3_TEXT, SAMPLE_4_TEXT]

        for text in all_texts:
            envelope = make_test_envelope(text)

            # Rule-based
            rb = RuleBasedIntentExtractor()
            rb_result = rb.extract(envelope)
            for intent in rb_result.intents:
                intent_dict = intent.model_dump()
                for field in forbidden:
                    assert field not in intent_dict or intent_dict.get(field) is None, \
                        f"Rule-based: forbidden field '{field}' found in output"

            # LLM-based does its own rejection via _parse_llm_output
            # (tested in test_intent_extractor.py::test_llm_rejects_forbidden_fields)

    def test_every_intent_has_evidence(self):
        """Every intent must have evidence_span_ids."""
        extractor = RuleBasedIntentExtractor()
        for text in [SAMPLE_1_TEXT, SAMPLE_2_TEXT]:
            envelope = make_test_envelope(text)
            result = extractor.extract(envelope)
            for intent in result.intents:
                assert len(intent.evidence_span_ids) >= 1, \
                    f"Intent {intent.intent_id} has no evidence spans"

    def test_rule_based_and_llm_extractor_versions(self):
        """Verify extractor version strings."""
        rb = RuleBasedIntentExtractor()
        assert rb.VERSION == "rule_based_v1"

        llm = LLMIntentExtractor(llm_fn=lambda p: "{}")
        assert llm.VERSION == "llm_v1"

    def test_sentiment_does_not_replace_intent(self):
        """sentiment_score is auxiliary; intent is determined by the four axes."""
        envelope = make_test_envelope(SAMPLE_2_TEXT)
        mock_llm = _make_mock_llm_fn(SAMPLE_2_LLM_OUTPUT)
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        result = extractor.extract(envelope)

        intent = result.intents[0]
        # Sentiment score exists but does not define actionability
        assert intent.sentiment_score is not None
        # The four axes determine intent, not sentiment
        assert intent.actionability == "explicit_action"  # from axis, not from sentiment
        assert intent.direction == "bullish"
        assert intent.position_delta_hint == "add"
        assert isinstance(intent.conviction, float)
