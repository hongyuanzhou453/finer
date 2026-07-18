"""Tests for A2-1 investment intent semantic additions (broker research).

Covers the F3 schema extensions that make institutional recommendations
representable (spec: docs/specs/2026-07-15-broker-research-source-integration.md
§3 A2, §7 R2/R3/R6, R5 for horizon tiers):

- actionability "recommendation"（三分语义第三档：零仓位承诺的机构建议）
- IntentTargetPrice slot（声明式目标价，R3）+ 序列化往返
- prior_direction / rating_action（研报自带前态，不再事后反推）
- conviction_source（derived_lookup 不得进 credibility，R6）
- HORIZON_EXIT_TIERS / resolve_horizon_tier（F4/F8 单一真相源，R5）
- 存量 F3 JSON（无任何新字段）反序列化零破坏
"""

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from finer.schemas.investment_intent import (
    ACTIONABILITY_LITERAL,
    CONVICTION_SOURCE_LITERAL,
    HORIZON_EXIT_TIERS,
    PRIOR_DIRECTION_LITERAL,
    RATING_ACTION_LITERAL,
    TIME_HORIZON_LITERAL,
    IntentTargetPrice,
    NormalizedInvestmentIntent,
    resolve_horizon_tier,
)


def make_intent(**overrides) -> NormalizedInvestmentIntent:
    """Minimal valid intent; overrides patch individual fields."""
    kwargs = dict(
        envelope_id="env-broker-001",
        target_type="stock",
        target_name="哔哩哔哩",
        target_symbol="BILI.US",
        market="US",
        direction="bullish",
        actionability="recommendation",
        position_delta_hint="none",
        conviction=0.7,
        confidence=0.9,
    )
    kwargs.update(overrides)
    return NormalizedInvestmentIntent(**kwargs)


# =============================================================================
# actionability "recommendation"
# =============================================================================

class TestRecommendationActionability:
    def test_recommendation_in_literal(self):
        assert "recommendation" in get_args(ACTIONABILITY_LITERAL)

    def test_recommendation_intent_creation(self):
        intent = make_intent()
        assert intent.actionability == "recommendation"

    def test_recommendation_does_not_trip_consistency_validators(self):
        """recommendation 是零仓位承诺——none 的 position_delta_hint 不应被
        opinion/explicit_action 的一致性规则误伤。"""
        intent = make_intent(position_delta_hint="none")
        assert intent.ambiguity_flags == []

    def test_existing_values_still_valid(self):
        for a in ["opinion", "watch", "explicit_action", "review_required"]:
            assert make_intent(actionability=a).actionability == a

    def test_invalid_actionability_rejected(self):
        with pytest.raises(ValidationError):
            make_intent(actionability="buy_recommendation")


# =============================================================================
# IntentTargetPrice
# =============================================================================

class TestIntentTargetPrice:
    def test_default_is_none(self):
        assert make_intent().target_price is None

    def test_prior_value_optional(self):
        tp = IntentTargetPrice(value=31.0, currency="USD")
        assert tp.prior_value is None

    def test_full_round_trip_through_json(self):
        """to_dict → json 字符串 → from_dict 必须无损（R3 槽位可持久化）。"""
        intent = make_intent(
            target_price=IntentTargetPrice(
                value=6.60, currency="USD", prior_value=7.50
            ),
            prior_direction="neutral",
            rating_action="downgrade",
            conviction_source="derived_lookup",
        )
        payload = json.loads(json.dumps(intent.to_dict()))
        restored = NormalizedInvestmentIntent.from_dict(payload)

        assert restored.target_price is not None
        assert restored.target_price.value == 6.60
        assert restored.target_price.currency == "USD"
        assert restored.target_price.prior_value == 7.50
        assert restored.prior_direction == "neutral"
        assert restored.rating_action == "downgrade"
        assert restored.conviction_source == "derived_lookup"

    def test_round_trip_preserves_absent_target_price(self):
        payload = json.loads(json.dumps(make_intent().to_dict()))
        restored = NormalizedInvestmentIntent.from_dict(payload)
        assert restored.target_price is None

    def test_missing_required_fields_rejected(self):
        with pytest.raises(ValidationError):
            IntentTargetPrice(value=31.0)  # currency required
        with pytest.raises(ValidationError):
            IntentTargetPrice(currency="USD")  # value required


# =============================================================================
# prior_direction / rating_action
# =============================================================================

class TestPriorDirectionAndRatingAction:
    def test_defaults_are_none(self):
        intent = make_intent()
        assert intent.prior_direction is None
        assert intent.rating_action is None

    def test_valid_values(self):
        for d in get_args(PRIOR_DIRECTION_LITERAL):
            assert make_intent(prior_direction=d).prior_direction == d
        for r in get_args(RATING_ACTION_LITERAL):
            assert make_intent(rating_action=r).rating_action == r

    def test_rating_action_vocabulary_matches_t3(self):
        """T3 JSONL (t3-v0.2) rating_action 词表逐值对齐。"""
        assert set(get_args(RATING_ACTION_LITERAL)) == {
            "upgrade", "downgrade", "maintain", "initiate", "unknown",
        }

    def test_invalid_values_rejected(self):
        with pytest.raises(ValidationError):
            make_intent(prior_direction="mixed")  # 前态不允许 mixed/unknown
        with pytest.raises(ValidationError):
            make_intent(rating_action="reiterate")


# =============================================================================
# conviction_source
# =============================================================================

class TestConvictionSource:
    def test_default_is_model_inferred(self):
        assert make_intent().conviction_source == "model_inferred"

    def test_valid_values(self):
        for src in get_args(CONVICTION_SOURCE_LITERAL):
            assert make_intent(conviction_source=src).conviction_source == src

    def test_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            make_intent(conviction_source="derived")

    def test_conviction_type_unchanged(self):
        """conviction 本身仍是 0-1 float，不受来源标注影响。"""
        intent = make_intent(conviction=0.7, conviction_source="derived_lookup")
        assert intent.conviction == 0.7
        with pytest.raises(ValidationError):
            make_intent(conviction=1.5)


# =============================================================================
# HORIZON_EXIT_TIERS / resolve_horizon_tier
# =============================================================================

class TestHorizonExitTiers:
    def test_tier_values(self):
        assert HORIZON_EXIT_TIERS == {"short": 30, "medium": 90, "long": 180}

    def test_resolve_known_hints(self):
        assert resolve_horizon_tier("intraday") == "short"
        assert resolve_horizon_tier("short_term") == "short"
        assert resolve_horizon_tier("medium_term") == "medium"
        assert resolve_horizon_tier("long_term") == "long"

    def test_resolve_unknown_and_missing_default_to_long(self):
        """R5：缺省不得把 12 个月的判断塞回 30 天窗口——默认 long。"""
        assert resolve_horizon_tier("unknown") == "long"
        assert resolve_horizon_tier(None) == "long"
        assert resolve_horizon_tier("") == "long"
        assert resolve_horizon_tier("next_quarter") == "long"

    def test_every_time_horizon_hint_resolves_to_a_registered_tier(self):
        """全部 TIME_HORIZON_LITERAL 取值都必须落进 HORIZON_EXIT_TIERS 的键。"""
        for hint in get_args(TIME_HORIZON_LITERAL):
            assert resolve_horizon_tier(hint) in HORIZON_EXIT_TIERS


# =============================================================================
# 存量 F3 数据零破坏
# =============================================================================

class TestLegacyDataCompatibility:
    LEGACY_F3_JSON = {
        # 一条 pre-A2-1 的存量 F3 intent（无任何新字段），字段集与
        # tests/test_investment_intent_schema.py 的既有产出对齐。
        "intent_id": "legacy-intent-0001",
        "schema_version": "1.0",
        "envelope_id": "env-legacy-001",
        "block_ids": ["block-1"],
        "creator_id": "laoji",
        "target_type": "stock",
        "target_name": "宁德时代",
        "target_symbol": "300750.SZ",
        "market": "CN",
        "direction": "bullish",
        "actionability": "explicit_action",
        "position_delta_hint": "add",
        "conviction": 0.8,
        "sentiment_score": 0.6,
        "risk_preference_hint": "balanced",
        "time_horizon_hint": "medium_term",
        "temporal_anchor_ids": [],
        "evidence_span_ids": ["span-1"],
        "ambiguity_flags": [],
        "confidence": 0.9,
        "metadata": {"source": "feishu"},
        "created_at": "2026-07-10T12:00:00Z",
    }

    def test_legacy_json_loads_without_new_fields(self):
        intent = NormalizedInvestmentIntent.from_dict(dict(self.LEGACY_F3_JSON))
        assert intent.intent_id == "legacy-intent-0001"
        assert intent.actionability == "explicit_action"

    def test_legacy_json_gets_new_field_defaults(self):
        intent = NormalizedInvestmentIntent.from_dict(dict(self.LEGACY_F3_JSON))
        assert intent.target_price is None
        assert intent.prior_direction is None
        assert intent.rating_action is None
        assert intent.conviction_source == "model_inferred"

    def test_legacy_json_round_trips_with_defaults_materialized(self):
        """老数据 load 后再 dump，新字段以默认值显式出现且可再次 load。"""
        intent = NormalizedInvestmentIntent.from_dict(dict(self.LEGACY_F3_JSON))
        payload = json.loads(json.dumps(intent.to_dict()))
        assert payload["target_price"] is None
        assert payload["conviction_source"] == "model_inferred"
        restored = NormalizedInvestmentIntent.from_dict(payload)
        assert restored.conviction_source == "model_inferred"
