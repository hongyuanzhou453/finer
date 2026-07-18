"""Tests for the F4 recommendation policy branch + horizon-aware exits.

Covers (spec 2026-07-15 broker-research R4/R5):
  - actionability=="recommendation" has its own mapping branch:
      * (recommendation, bullish)  → executable open semantics
      * (recommendation, bearish)  → executable reduce/avoid semantics —
        NEVER the review_required human queue (initiation-at-sell is routine
        broker-research output, not an anomaly)
      * (recommendation, neutral)  → watch_only
  - Exhaustive: no (recommendation, direction, delta) combo yields
    review_required.
  - Sell ratings do not force requires_human_review.
  - Honesty: recommendation-driven constraints carry a "follows institutional
    recommendation" note — the output is never dressed up as the author's own
    position change.
  - Horizon-aware exit tiers via HORIZON_EXIT_TIERS / resolve_horizon_tier
    (single source of truth in schemas/investment_intent.py — no local tier
    tables): short 30d / medium 90d / long 180d with per-tier stop/TP.
  - Legacy regression: horizon-unaware callers and opinion/explicit_action
    paths keep the historical flat -10%/+20%/30d behavior bit-for-bit.
"""

import pytest
from typing import List

from finer.schemas.investment_intent import (
    HORIZON_EXIT_TIERS,
    NormalizedInvestmentIntent,
    resolve_horizon_tier,
)
from finer.policy.global_base import (
    GlobalBasePolicy,
    _HORIZON_EXIT_PARAMS,
    _RECOMMENDATION_RULES,
)
from finer.policy.policy_mapper import PolicyMapper


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def policy() -> GlobalBasePolicy:
    return GlobalBasePolicy()


@pytest.fixture
def mapper() -> PolicyMapper:
    return PolicyMapper()


def _make_intent(
    intent_id: str = "intent-rec-001",
    actionability: str = "recommendation",
    direction: str = "bullish",
    position_delta_hint: str = "none",
    conviction: float = 0.8,
    confidence: float = 0.9,
    time_horizon_hint: str = "unknown",
    target_name: str = "贵州茅台",
    target_symbol: str = "600519.SH",
    ambiguity_flags: List[str] | None = None,
) -> NormalizedInvestmentIntent:
    """Build a broker-research-flavored intent."""
    return NormalizedInvestmentIntent(
        intent_id=intent_id,
        envelope_id="env-rec-001",
        block_ids=["block-1"],
        creator_id="broker-test-001",
        target_type="stock",
        target_name=target_name,
        target_symbol=target_symbol,
        market="CN",
        direction=direction,
        actionability=actionability,
        position_delta_hint=position_delta_hint,
        conviction=conviction,
        confidence=confidence,
        time_horizon_hint=time_horizon_hint,
        evidence_span_ids=["span-001"],
        ambiguity_flags=ambiguity_flags or [],
    )


ALL_DIRECTIONS = ["bullish", "bearish", "neutral", "mixed", "unknown"]
ALL_DELTAS = ["open", "add", "reduce", "hold", "exit", "none", "unknown"]


# =============================================================================
# Recommendation mapping — three directions
# =============================================================================

class TestRecommendationMapping:

    def test_bullish_recommendation_maps_to_open(self, mapper):
        """Initiate/maintain buy rating → executable open semantics."""
        intent = _make_intent(direction="bullish", position_delta_hint="none")
        result = mapper.map_intent(intent)
        assert result.action_hint == "open_position"

    def test_bullish_recommendation_open_delta(self, mapper):
        intent = _make_intent(direction="bullish", position_delta_hint="open")
        result = mapper.map_intent(intent)
        assert result.action_hint == "open_position"

    def test_bullish_recommendation_add_delta(self, mapper):
        intent = _make_intent(direction="bullish", position_delta_hint="add")
        result = mapper.map_intent(intent)
        assert result.action_hint == "add_position"

    def test_bearish_recommendation_maps_to_reduce(self, mapper):
        """Initiation-at-sell (delta=none) → executable reduce, NOT human queue.

        This is the R4 blackhole fix: broker research routinely initiates
        coverage at a sell rating.
        """
        intent = _make_intent(direction="bearish", position_delta_hint="none")
        result = mapper.map_intent(intent)
        assert result.action_hint == "reduce_position"

    def test_bearish_recommendation_exit_delta(self, mapper):
        intent = _make_intent(direction="bearish", position_delta_hint="exit")
        result = mapper.map_intent(intent)
        assert result.action_hint == "close_position"

    def test_bearish_recommendation_never_opens_short(self, mapper):
        """Bearish rating + open/add delta → reduce long exposure, no shorts."""
        for delta in ("open", "add"):
            intent = _make_intent(direction="bearish", position_delta_hint=delta)
            result = mapper.map_intent(intent)
            assert result.action_hint == "reduce_position"

    def test_neutral_recommendation_maps_to_watch(self, mapper):
        """Hold / market-perform rating → watch_only."""
        intent = _make_intent(direction="neutral", position_delta_hint="none")
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_only"
        assert result.position_sizing_hint == "none"

    def test_mixed_and_unknown_direction_fall_back_to_watch(self, policy):
        for direction in ("mixed", "unknown"):
            hint = policy.lookup_action_hint("recommendation", direction, "none")
            assert hint == "watch_only"


# =============================================================================
# R4: sell ratings never enter the human queue
# =============================================================================

class TestNoReviewBlackhole:

    def test_no_recommendation_combo_yields_review_required(self, policy):
        """Exhaustive: the recommendation branch never outputs review_required."""
        for direction in ALL_DIRECTIONS:
            for delta in ALL_DELTAS:
                hint = policy.lookup_action_hint("recommendation", direction, delta)
                assert hint != "review_required", (
                    f"(recommendation, {direction}, {delta}) fell into the "
                    f"review_required blackhole"
                )

    def test_bearish_recommendation_no_forced_human_review(self, mapper):
        """Sell rating with sane conviction → requires_human_review is False."""
        intent = _make_intent(
            direction="bearish", position_delta_hint="none", conviction=0.7
        )
        result = mapper.map_intent(intent)
        assert result.risk_constraints.requires_human_review is False

    def test_bullish_recommendation_no_forced_human_review(self, mapper):
        intent = _make_intent(
            direction="bullish", position_delta_hint="none", conviction=0.7
        )
        result = mapper.map_intent(intent)
        assert result.risk_constraints.requires_human_review is False

    def test_low_conviction_recommendation_still_escalates(self, mapper):
        """The orthogonal low-conviction guard is NOT relaxed by this branch."""
        intent = _make_intent(
            direction="bearish", position_delta_hint="none", conviction=0.2
        )
        result = mapper.map_intent(intent)
        assert result.risk_constraints.requires_human_review is True

    def test_explicit_action_bearish_open_still_escalates(self, mapper):
        """Regression: a PERSON opening a bearish position (possible short)
        keeps the escalation — only declarative ratings are exempt."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bearish",
            position_delta_hint="open",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required"


# =============================================================================
# Sizing flows through the normal conviction pipeline
# =============================================================================

class TestRecommendationSizing:

    def test_medium_conviction_small_sizing(self, mapper):
        intent = _make_intent(direction="bullish", conviction=0.5)
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint == "small"

    def test_high_conviction_medium_sizing(self, mapper):
        intent = _make_intent(direction="bullish", conviction=0.85)
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint == "medium"

    def test_recommendation_never_large(self, mapper):
        intent = _make_intent(direction="bullish", conviction=0.99)
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint != "large"


# =============================================================================
# Honesty: follow-the-recommendation, not the author's own position
# =============================================================================

class TestHonestSemantics:

    def test_recommendation_constraints_carry_honesty_note(self, policy):
        rc = policy.compute_risk_constraints(
            "reduce_position", 0.7, actionability="recommendation"
        )
        assert any("institutional recommendation" in note for note in rc.risk_notes)

    def test_explicit_action_constraints_have_no_recommendation_note(self, policy):
        rc = policy.compute_risk_constraints(
            "add_position", 0.7, actionability="explicit_action"
        )
        assert not any("institutional recommendation" in note for note in rc.risk_notes)


# =============================================================================
# R5: horizon-aware exit parameters
# =============================================================================

class TestHorizonAwareExits:

    def test_short_tier_matches_legacy_constants(self, policy):
        """short tier is byte-identical to the historical flat constants."""
        rc = policy.compute_risk_constraints(
            "open_position", 0.7, time_horizon_hint="short_term"
        )
        assert rc.stop_loss_pct_hint == -0.10
        assert rc.take_profit_pct_hint == 0.20
        assert rc.max_holding_days_hint == HORIZON_EXIT_TIERS["short"] == 30

    def test_medium_tier(self, policy):
        rc = policy.compute_risk_constraints(
            "open_position", 0.7, time_horizon_hint="medium_term"
        )
        assert rc.stop_loss_pct_hint == -0.15
        assert rc.take_profit_pct_hint == 0.30
        assert rc.max_holding_days_hint == HORIZON_EXIT_TIERS["medium"] == 90

    def test_long_tier(self, policy):
        rc = policy.compute_risk_constraints(
            "open_position", 0.7, time_horizon_hint="long_term"
        )
        assert rc.stop_loss_pct_hint == -0.20
        assert rc.take_profit_pct_hint == 0.40
        assert rc.max_holding_days_hint == HORIZON_EXIT_TIERS["long"] == 180

    def test_unknown_horizon_defaults_to_long_window(self, policy):
        """R5 core: absence of an explicit horizon must NOT shrink the window
        back to the 30-day stopwatch — broker target prices imply ~12 months."""
        rc = policy.compute_risk_constraints(
            "open_position", 0.7, time_horizon_hint="unknown"
        )
        assert rc.max_holding_days_hint == HORIZON_EXIT_TIERS["long"]

    def test_intraday_resolves_to_short_tier(self, policy):
        rc = policy.compute_risk_constraints(
            "open_position", 0.7, time_horizon_hint="intraday"
        )
        assert rc.max_holding_days_hint == HORIZON_EXIT_TIERS["short"]

    def test_horizon_note_in_risk_notes(self, policy):
        rc = policy.compute_risk_constraints(
            "open_position", 0.7, time_horizon_hint="long_term"
        )
        assert any("Exit window" in note for note in rc.risk_notes)

    def test_non_position_hints_get_no_exit_rules_even_with_horizon(self, policy):
        rc = policy.compute_risk_constraints(
            "watch_only", 0.7, time_horizon_hint="long_term"
        )
        assert rc.stop_loss_pct_hint is None
        assert rc.take_profit_pct_hint is None
        assert rc.max_holding_days_hint is None

    def test_exit_params_table_covers_exactly_the_schema_tiers(self):
        """_HORIZON_EXIT_PARAMS must key off the schema's tier set — no local
        tier invention, no missing tier (would KeyError at runtime)."""
        assert set(_HORIZON_EXIT_PARAMS.keys()) == set(HORIZON_EXIT_TIERS.keys())

    def test_take_profit_is_double_the_stop_in_every_tier(self):
        """Documented invariant: 2:1 reward-to-risk preserved across tiers."""
        for tier, (stop, tp) in _HORIZON_EXIT_PARAMS.items():
            assert stop < 0 < tp
            assert tp == pytest.approx(-2 * stop), tier

    def test_stops_widen_monotonically_with_horizon(self):
        s = _HORIZON_EXIT_PARAMS
        assert s["short"][0] > s["medium"][0] > s["long"][0]

    def test_resolve_horizon_tier_is_the_router(self, policy):
        """Exit days must always agree with resolve_horizon_tier's verdict."""
        for hint in ("intraday", "short_term", "medium_term", "long_term", "unknown"):
            rc = policy.compute_risk_constraints(
                "add_position", 0.7, time_horizon_hint=hint
            )
            assert rc.max_holding_days_hint == HORIZON_EXIT_TIERS[resolve_horizon_tier(hint)]


# =============================================================================
# Legacy regression — horizon-unaware callers and non-recommendation paths
# =============================================================================

class TestLegacyRegression:

    def test_no_horizon_arg_keeps_flat_defaults(self, policy):
        """Callers that do not pass time_horizon_hint (and PolicyMapper for
        intents whose time_horizon_hint is the "unknown" schema default)
        get the historical flat constants — zero backtest drift."""
        rc = policy.compute_risk_constraints("add_position", 0.7)
        assert rc.stop_loss_pct_hint == -0.10
        assert rc.take_profit_pct_hint == 0.20
        assert rc.max_holding_days_hint == 30

    def test_opinion_bullish_unchanged(self, mapper):
        intent = _make_intent(
            actionability="opinion", direction="bullish", position_delta_hint="none"
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_or_no_trade"

    def test_opinion_bearish_unchanged(self, mapper):
        intent = _make_intent(
            actionability="opinion", direction="bearish", position_delta_hint="none"
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "avoid_or_watch_risk"

    def test_explicit_action_add_unchanged(self, mapper):
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "add_position"

    def test_explicit_action_exit_unchanged(self, mapper):
        intent = _make_intent(
            actionability="explicit_action",
            direction="bearish",
            position_delta_hint="exit",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "close_position"

    def test_recommendation_rules_only_emit_valid_hints(self):
        valid = {"watch_only", "watch_or_no_trade", "avoid_or_watch_risk",
                 "open_position", "add_position", "reduce_position",
                 "hold_position", "close_position"}
        assert set(_RECOMMENDATION_RULES.values()) <= valid


# =============================================================================
# Canonical mapper horizon wiring (A2-fixup) — the mapper itself must pass
# time_horizon_hint / actionability through to compute_risk_constraints,
# otherwise the tiered params above are dead code on the canonical path.
# =============================================================================

class TestMapperHorizonWiring:

    def test_mapper_reaches_long_tier(self, mapper):
        """recommendation + long_term through the CANONICAL mapper (not a
        direct policy call) must land in the 180d long tier."""
        intent = _make_intent(
            direction="bullish",
            position_delta_hint="none",
            time_horizon_hint="long_term",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "open_position"
        assert result.risk_constraints.max_holding_days_hint == HORIZON_EXIT_TIERS["long"] == 180
        assert result.risk_constraints.stop_loss_pct_hint == -0.20
        assert result.risk_constraints.take_profit_pct_hint == 0.40

    def test_mapper_reaches_medium_tier(self, mapper):
        intent = _make_intent(time_horizon_hint="medium_term")
        result = mapper.map_intent(intent)
        assert result.risk_constraints.max_holding_days_hint == HORIZON_EXIT_TIERS["medium"] == 90

    def test_mapper_emits_honesty_note_for_recommendation(self, mapper):
        """The 'follows institutional recommendation' note must survive the
        canonical mapper path, not just direct compute_risk_constraints calls."""
        intent = _make_intent(direction="bullish", position_delta_hint="none")
        result = mapper.map_intent(intent)
        assert any(
            "institutional recommendation" in note
            for note in result.risk_constraints.risk_notes
        )

    def test_mapper_horizon_overrides_holding_period(self, mapper):
        """F3 long_term hint dominates the action_hint coarse default
        (open_position would otherwise yield medium_term)."""
        intent = _make_intent(
            direction="bullish",
            position_delta_hint="none",
            time_horizon_hint="long_term",
        )
        result = mapper.map_intent(intent)
        assert result.holding_period_hint == "long_term"

    def test_mapper_unknown_horizon_keeps_legacy_flat(self, mapper):
        """time_horizon_hint='unknown' (F3 default) through the mapper keeps
        the legacy flat -10%/+20%/30d and per-action holding period."""
        intent = _make_intent(
            direction="bullish",
            position_delta_hint="none",
            time_horizon_hint="unknown",
        )
        result = mapper.map_intent(intent)
        assert result.risk_constraints.stop_loss_pct_hint == -0.10
        assert result.risk_constraints.take_profit_pct_hint == 0.20
        assert result.risk_constraints.max_holding_days_hint == 30
        assert result.holding_period_hint == "medium_term"
