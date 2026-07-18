"""End-to-end horizon plumbing: F3 hint → F4 → F5 → F8 window (A2-fixup).

Proves the 180d tier is REACHABLE on the canonical path, closing the two
rework items from the A2 acceptance round:

  1. PolicyMapper._map_single now passes time_horizon_hint / actionability
     into GlobalBasePolicy.compute_risk_constraints — the horizon-tiered
     exit params and the honesty note are live on the canonical path, not
     only via direct test calls.
  2. holding_period_hint is horizon-aware: an F3 time_horizon_hint
     dominates the per-action_hint coarse default via resolve_horizon_tier
     (schemas single source of truth), so a broker 12-month view carries
     "long_term" into TradeAction.time_horizon and gets a 180d F8 window
     instead of the 90d "medium_term" open-position default.

Flow under test (each hop asserted):

    F3  intent.time_horizon_hint = "long_term"
    F4  holding_period_hint      = "long_term"   (tier "long")
        risk_constraints         = -20% / +40% / 180d + honesty note
    F5  TradeAction.time_horizon = "long_term"   (runner passes
        mapped.holding_period_hint — mirrored here via compose_trade_action)
        metadata.max_holding_days = 180
    F8  evaluation_window_days_of(action) == 180 (read-only backtest call)

Also pins that opinion / explicit_action intents with the "unknown" F3
default keep the pre-change outputs bit-for-bit (legacy flat exits, coarse
holding-period defaults, no recommendation honesty note) — the wiring must
not drag old semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pytest

from finer.backtest.per_action import evaluation_window_days_of
from finer.extraction.action_composer import compose_trade_action
from finer.policy.policy_mapper import PolicyMapper
from finer.schemas.investment_intent import (
    HORIZON_EXIT_TIERS,
    NormalizedInvestmentIntent,
)
from finer.schemas.policy import PolicyMappedIntent
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    ExecutionTiming,
    SourceInfo,
    TargetInfo,
    TradeDirection,
    TriggerType,
)


# =============================================================================
# Fixtures / helpers
# =============================================================================

@pytest.fixture
def mapper() -> PolicyMapper:
    return PolicyMapper()


def _make_intent(
    intent_id: str = "intent-hz-001",
    actionability: str = "recommendation",
    direction: str = "bullish",
    position_delta_hint: str = "none",
    conviction: float = 0.8,
    confidence: float = 0.9,
    time_horizon_hint: str = "unknown",
    ambiguity_flags: Optional[List[str]] = None,
) -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id=intent_id,
        envelope_id="env-hz-001",
        block_ids=["block-1"],
        creator_id="broker-hz-001",
        target_type="stock",
        target_name="贵州茅台",
        target_symbol="600519.SH",
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


def _compose_from_mapping(
    intent: NormalizedInvestmentIntent,
    pmi: PolicyMappedIntent,
):
    """Mirror the canonical runner's F5 construction: the composer receives
    time_horizon=mapped.holding_period_hint (canonical_runner.py:950) and
    stamps the F4 exit hints into metadata via build_action_metadata."""
    now = datetime(2026, 7, 1, 10, 0)
    timing = ExecutionTiming(
        intent_published_at=now,
        action_decision_at=now,
        action_executable_at=now,
        market="CN",
        timezone="Asia/Shanghai",
        timing_policy_id="test-policy",
    )
    return compose_trade_action(
        intent=intent,
        policy_mapped_intent=pmi,
        evidence_span_ids=["span-001"],
        execution_timing=timing,
        source=SourceInfo(
            content_id="env-hz-001",
            evidence_text="维持买入评级，12个月目标价2100元",
            creator_id="broker-hz-001",
        ),
        target=TargetInfo(ticker="600519.SH", market="CN"),
        direction=TradeDirection.BULLISH,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                trigger_type=TriggerType.MANUAL,
            )
        ],
        rationale="看多 600519.SH · open_position",
        time_horizon=pmi.holding_period_hint,
    )


def _map(mapper: PolicyMapper, intent: NormalizedInvestmentIntent) -> PolicyMappedIntent:
    return mapper.map_batch([intent]).mapped_intents[0]


# =============================================================================
# End-to-end: 180d tier is reachable on the canonical path
# =============================================================================

class TestLongHorizonEndToEnd:
    """recommendation + long_term walks F3 → F4 → F5 → F8 and gets 180d."""

    @pytest.fixture
    def intent(self) -> NormalizedInvestmentIntent:
        return _make_intent(
            actionability="recommendation",
            direction="bullish",
            position_delta_hint="none",
            time_horizon_hint="long_term",
        )

    def test_f4_constraints_are_long_tier(self, mapper, intent):
        """F4 hop: constraint window == 180d with long-tier stop/TP."""
        pmi = _map(mapper, intent)
        assert pmi.action_hint == "open_position"
        assert pmi.max_holding_days_hint == HORIZON_EXIT_TIERS["long"] == 180
        assert pmi.stop_loss_pct_hint == -0.20
        assert pmi.take_profit_pct_hint == 0.40

    def test_f4_risk_notes_carry_honesty_note(self, mapper, intent):
        """Honesty note is live on the canonical path."""
        pmi = _map(mapper, intent)
        assert any("institutional recommendation" in n for n in pmi.risk_notes)
        assert any("Exit window" in n for n in pmi.risk_notes)

    def test_f4_holding_period_is_long_term(self, mapper, intent):
        """F3 hint dominates the open_position → medium_term coarse default."""
        pmi = _map(mapper, intent)
        assert pmi.holding_period_hint == "long_term"

    def test_f5_action_carries_long_horizon(self, mapper, intent):
        """F5 hop: TradeAction.time_horizon == 'long_term',
        metadata.max_holding_days == 180."""
        pmi = _map(mapper, intent)
        action = _compose_from_mapping(intent, pmi)
        assert action.time_horizon == "long_term"
        assert action.metadata["max_holding_days"] == 180
        assert action.metadata["stop_loss_pct"] == -0.20
        assert action.metadata["take_profit_pct"] == 0.40

    def test_f8_window_resolves_to_180(self, mapper, intent):
        """F8 hop (read-only): the backtest evaluation window is 180 days."""
        pmi = _map(mapper, intent)
        action = _compose_from_mapping(intent, pmi)
        assert evaluation_window_days_of(action) == 180


class TestMediumAndShortTiersThroughMapper:

    def test_medium_term_gets_90d(self, mapper):
        intent = _make_intent(time_horizon_hint="medium_term")
        pmi = _map(mapper, intent)
        assert pmi.max_holding_days_hint == HORIZON_EXIT_TIERS["medium"] == 90
        assert pmi.holding_period_hint == "medium_term"

    def test_short_term_matches_legacy_constants(self, mapper):
        """Short tier is byte-identical to the historical flat constants, so
        a stated short horizon cannot drift the backtest."""
        intent = _make_intent(time_horizon_hint="short_term")
        pmi = _map(mapper, intent)
        assert pmi.stop_loss_pct_hint == -0.10
        assert pmi.take_profit_pct_hint == 0.20
        assert pmi.max_holding_days_hint == 30
        assert pmi.holding_period_hint == "short_term"

    def test_intraday_collapses_to_short_tier(self, mapper):
        intent = _make_intent(time_horizon_hint="intraday")
        pmi = _map(mapper, intent)
        assert pmi.max_holding_days_hint == HORIZON_EXIT_TIERS["short"] == 30
        assert pmi.holding_period_hint == "short_term"


# =============================================================================
# Legacy-path pinning: opinion / explicit_action stay bit-for-bit unchanged
# =============================================================================

class TestLegacyPathsUnchanged:
    """The wiring must not drag pre-change semantics for existing intents
    (F3 default time_horizon_hint == 'unknown')."""

    def test_explicit_action_unknown_horizon_identical_to_pre_change(self, mapper):
        """Pre-change canonical output for (explicit_action, bullish, add):
        add_position / medium_term / -10% / +20% / 30d, no honesty note."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            time_horizon_hint="unknown",
        )
        pmi = _map(mapper, intent)
        assert pmi.action_hint == "add_position"
        assert pmi.holding_period_hint == "medium_term"
        assert pmi.stop_loss_pct_hint == -0.10
        assert pmi.take_profit_pct_hint == 0.20
        assert pmi.max_holding_days_hint == 30
        assert pmi.requires_human_review is False
        assert not any("institutional recommendation" in n for n in pmi.risk_notes)
        assert not any("Exit window" in n for n in pmi.risk_notes)

    def test_explicit_action_exit_unknown_horizon_identical(self, mapper):
        intent = _make_intent(
            actionability="explicit_action",
            direction="bearish",
            position_delta_hint="exit",
            time_horizon_hint="unknown",
        )
        pmi = _map(mapper, intent)
        assert pmi.action_hint == "close_position"
        assert pmi.holding_period_hint == "short_term"
        assert pmi.stop_loss_pct_hint == -0.10
        assert pmi.take_profit_pct_hint == 0.20
        assert pmi.max_holding_days_hint == 30
        assert not any("institutional recommendation" in n for n in pmi.risk_notes)

    def test_opinion_unknown_horizon_identical_to_pre_change(self, mapper):
        """Opinion → watch hint, review_required holding period, NO exit
        hints — with or without the new wiring."""
        intent = _make_intent(
            actionability="opinion",
            direction="bullish",
            position_delta_hint="none",
            time_horizon_hint="unknown",
        )
        pmi = _map(mapper, intent)
        assert pmi.action_hint == "watch_or_no_trade"
        assert pmi.holding_period_hint == "review_required"
        assert pmi.stop_loss_pct_hint is None
        assert pmi.take_profit_pct_hint is None
        assert pmi.max_holding_days_hint is None
        assert not any("institutional recommendation" in n for n in pmi.risk_notes)

    def test_opinion_with_horizon_still_no_exit_rules(self, mapper):
        """A stated horizon on a non-position intent must not conjure exit
        rules or a holding period out of a watch hint."""
        intent = _make_intent(
            actionability="opinion",
            direction="bullish",
            position_delta_hint="none",
            time_horizon_hint="long_term",
        )
        pmi = _map(mapper, intent)
        assert pmi.action_hint == "watch_or_no_trade"
        assert pmi.holding_period_hint == "review_required"
        assert pmi.max_holding_days_hint is None

    def test_explicit_action_no_honesty_note_even_with_horizon(self, mapper):
        """The honesty note is recommendation-only: an author's own explicit
        action with a long horizon gets tiered exits but no such note."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            time_horizon_hint="long_term",
        )
        pmi = _map(mapper, intent)
        assert pmi.max_holding_days_hint == 180
        assert not any("institutional recommendation" in n for n in pmi.risk_notes)
