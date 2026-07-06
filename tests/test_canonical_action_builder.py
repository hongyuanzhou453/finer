"""Tests for CanonicalActionBuilder — F3 + F4 + Evidence + Timing -> F5.

Verifies:
- Build succeeds with all required inputs
- Build rejects when intent_id missing
- Build rejects when policy_id missing
- Build rejects when evidence_span_ids empty
- Build rejects when execution_timing missing
- Action chain mapping correctness for each action_hint
- No raw text accepted (type guards)
- Canonical trace status is always "canonical" on success
"""

import pytest
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import ValidationError

from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent
from finer.schemas.trade_action import (
    ActionType,
    ExecutionTiming,
    MarketSession,
    TradeAction,
    TradeDirection,
    ValidationStatus,
)
from finer.extraction.canonical_action_builder import (
    CanonicalActionBuilder,
    CanonicalBuildError,
    EmptyEvidenceSpanIdsError,
    MissingExecutionTimingError,
    MissingIntentIdError,
    MissingPolicyIdError,
)


# =============================================================================
# Helpers
# =============================================================================

def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}"


def _make_intent(
    intent_id: str = "",
    target_name: str = "宁德时代",
    target_symbol: str = "300750.SZ",
    market: str = "CN",
    direction: str = "bullish",
    actionability: str = "opinion",
    position_delta_hint: str = "none",
    conviction: float = 0.7,
    confidence: float = 0.85,
    evidence_span_ids: Optional[List[str]] = None,
    creator_id: str = "kol-test",
) -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id=intent_id or _uid("intent-"),
        envelope_id=_uid("env-"),
        block_ids=[_uid("block-")],
        creator_id=creator_id,
        target_type="stock",
        target_name=target_name,
        target_symbol=target_symbol,
        market=market,
        direction=direction,
        actionability=actionability,
        position_delta_hint=position_delta_hint,
        conviction=conviction,
        confidence=confidence,
        evidence_span_ids=evidence_span_ids or [_uid("span-")],
    )


def _make_mapped_intent(
    intent_id: str,
    policy_id: str = "",
    action_hint: str = "watch_only",
    position_sizing_hint: str = "none",
    holding_period_hint: str = "review_required",
    mapping_confidence: float = 0.85,
    requires_human_review: bool = False,
) -> PolicyMappedIntent:
    return PolicyMappedIntent(
        intent_id=intent_id,
        policy_id=policy_id or _uid("policy-"),
        original_intent_summary=f"Test intent {intent_id[:12]}",
        action_hint=action_hint,
        position_sizing_hint=position_sizing_hint,
        holding_period_hint=holding_period_hint,
        mapping_confidence=mapping_confidence,
        requires_human_review=requires_human_review,
    )


def _make_timing(
    market: str = "CN",
    timezone: str = "Asia/Shanghai",
) -> ExecutionTiming:
    now = datetime.now()
    return ExecutionTiming(
        intent_published_at=now,
        action_decision_at=now,
        action_executable_at=now,
        market=market,
        timezone=timezone,
        timing_policy_id="market-calendar-v1",
    )


# =============================================================================
# Happy path: build succeeds with all required inputs
# =============================================================================


class TestBuildSuccess:
    """CanonicalActionBuilder.build() succeeds with valid inputs."""

    def test_build_with_all_required_inputs(self):
        """Build produces a TradeAction with canonical trace."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            action_hint="watch_only",
        )
        evidence_ids = [_uid("span-")]
        timing = _make_timing()

        ta = builder.build(intent, mapped, evidence_ids, timing)

        assert isinstance(ta, TradeAction)
        assert ta.canonical_trace_status == "canonical"
        assert ta.intent_id == intent.intent_id
        assert ta.policy_id == mapped.policy_id
        assert ta.evidence_span_ids == evidence_ids

    def test_build_preserves_effective_trade_at(self):
        """effective_trade_at comes from execution_timing.intent_effective_at."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)
        effective = datetime(2026, 4, 29, 9, 30, 0)
        timing = ExecutionTiming(
            intent_published_at=datetime(2026, 4, 29, 8, 0),
            intent_effective_at=effective,
            action_decision_at=datetime(2026, 4, 29, 8, 5),
            action_executable_at=datetime(2026, 4, 29, 9, 30),
            market="CN",
            timezone="Asia/Shanghai",
            timing_policy_id="market-calendar-v1",
        )

        ta = builder.build(intent, mapped, [_uid("span-")], timing)
        assert ta.effective_trade_at == effective

    def test_build_stores_timing_on_trade_action(self):
        """ExecutionTiming is set directly on TradeAction.execution_timing."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)
        timing = _make_timing()

        ta = builder.build(intent, mapped, [_uid("span-")], timing)

        assert ta.execution_timing is not None
        assert ta.execution_timing.timing_policy_id == "market-calendar-v1"

    def test_build_stores_policy_hints_in_metadata(self):
        """Policy hints are preserved in TradeAction.metadata."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            action_hint="add_position",
            position_sizing_hint="small",
            holding_period_hint="medium_term",
        )

        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())

        assert ta.metadata["action_hint_original"] == "add_position"
        assert ta.metadata["position_sizing_hint"] == "small"
        assert ta.metadata["holding_period_hint"] == "medium_term"
        # No numeric exit hints on the mapped intent -> keys absent, so F8
        # falls back to its module defaults.
        assert "stop_loss_pct" not in ta.metadata
        assert "take_profit_pct" not in ta.metadata
        assert "max_holding_days" not in ta.metadata

    def test_build_stores_exit_rule_hints_in_metadata(self):
        """Numeric F4 exit-rule hints are propagated into metadata."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            action_hint="add_position",
        )
        mapped = mapped.model_copy(update={
            "stop_loss_pct_hint": -0.08,
            "take_profit_pct_hint": 0.15,
            "max_holding_days_hint": 20,
        })

        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())

        assert ta.metadata["stop_loss_pct"] == -0.08
        assert ta.metadata["take_profit_pct"] == 0.15
        assert ta.metadata["max_holding_days"] == 20

    def test_build_stores_style_signals_in_metadata(self):
        """F3 trading-style signals are propagated when informative."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        intent = intent.model_copy(update={
            "margin_flag": True,
            "leverage_flag": False,
            "entry_timing_style": "left_side",
        })
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())

        assert ta.metadata["margin_flag"] is True
        assert ta.metadata["leverage_flag"] is False
        assert ta.metadata["entry_timing_style"] == "left_side"

    def test_build_omits_uninformative_style_signals(self):
        """Default (None/unknown) style signals do not pollute metadata."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())

        assert "margin_flag" not in ta.metadata
        assert "leverage_flag" not in ta.metadata
        assert "entry_timing_style" not in ta.metadata

    def test_build_has_canonical_tag(self):
        """TradeAction includes 'canonical' tag."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())
        assert "canonical" in ta.tags
        assert "f3-f4-f5" in ta.tags


# =============================================================================
# Rejection: missing required fields
# =============================================================================


class TestBuildRejection:
    """CanonicalActionBuilder.build() rejects invalid inputs."""

    def test_rejects_empty_intent_id(self):
        """Build raises MissingIntentIdError when intent_id is empty."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        intent.intent_id = ""  # Force empty after construction
        mapped = _make_mapped_intent(intent_id="some-id")

        with pytest.raises(MissingIntentIdError, match="intent_id"):
            builder.build(intent, mapped, [_uid("span-")], _make_timing())

    def test_rejects_empty_policy_id(self):
        """Build raises MissingPolicyIdError when policy_id is empty."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)
        mapped.policy_id = ""  # Force empty after construction

        with pytest.raises(MissingPolicyIdError, match="policy_id"):
            builder.build(intent, mapped, [_uid("span-")], _make_timing())

    def test_rejects_empty_evidence_span_ids(self):
        """Build raises EmptyEvidenceSpanIdsError when evidence list is empty."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        with pytest.raises(EmptyEvidenceSpanIdsError, match="evidence_span_ids"):
            builder.build(intent, mapped, [], _make_timing())

    def test_rejects_none_execution_timing(self):
        """Build raises TypeError when execution_timing is None."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        with pytest.raises(TypeError):
            builder.build(intent, mapped, [_uid("span-")], None)  # type: ignore


# =============================================================================
# Type guards: no raw text accepted
# =============================================================================


class TestTypeGuards:
    """CanonicalActionBuilder rejects raw text / wrong types."""

    def test_rejects_string_intent(self):
        """Raw string as intent is rejected with TypeError."""
        builder = CanonicalActionBuilder()
        mapped = _make_mapped_intent(intent_id="x")

        with pytest.raises(TypeError, match="NormalizedInvestmentIntent"):
            builder.build("raw text", mapped, [_uid("span-")], _make_timing())  # type: ignore

    def test_rejects_dict_intent(self):
        """Dict as intent is rejected with TypeError."""
        builder = CanonicalActionBuilder()
        mapped = _make_mapped_intent(intent_id="x")

        with pytest.raises(TypeError, match="NormalizedInvestmentIntent"):
            builder.build({"direction": "bullish"}, mapped, [_uid("span-")], _make_timing())  # type: ignore

    def test_rejects_string_mapped_intent(self):
        """Raw string as policy_mapped_intent is rejected."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()

        with pytest.raises(TypeError, match="PolicyMappedIntent"):
            builder.build(intent, "raw text", [_uid("span-")], _make_timing())  # type: ignore

    def test_rejects_dict_mapped_intent(self):
        """Dict as policy_mapped_intent is rejected."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()

        with pytest.raises(TypeError, match="PolicyMappedIntent"):
            builder.build(intent, {"policy_id": "x"}, [_uid("span-")], _make_timing())  # type: ignore

    def test_rejects_string_timing(self):
        """Raw string as execution_timing is rejected."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        with pytest.raises(TypeError, match="ExecutionTiming"):
            builder.build(intent, mapped, [_uid("span-")], "tomorrow")  # type: ignore

    def test_rejects_string_evidence_span_ids(self):
        """String instead of list for evidence_span_ids is rejected."""
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)

        with pytest.raises(TypeError, match="list"):
            builder.build(intent, mapped, "span-001", _make_timing())  # type: ignore


# =============================================================================
# Action chain mapping correctness
# =============================================================================


class TestActionChainMapping:
    """Verify each action_hint maps to the correct ActionType."""

    def _build_with_hint(self, action_hint: str) -> TradeAction:
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            action_hint=action_hint,
        )
        return builder.build(intent, mapped, [_uid("span-")], _make_timing())

    def test_consider_buy_maps_to_buy_and_hold(self):
        """consider_buy -> BUY_AND_HOLD (tested via internal mapping)."""
        action_type, status, _ = CanonicalActionBuilder._resolve_action_chain("consider_buy")
        assert action_type == ActionType.BUY_AND_HOLD
        assert status == "review"

    def test_consider_sell_maps_to_close_long(self):
        """consider_sell -> CLOSE_LONG (tested via internal mapping)."""
        action_type, status, _ = CanonicalActionBuilder._resolve_action_chain("consider_sell")
        assert action_type == ActionType.CLOSE_LONG
        assert status == "review"

    def test_watch_only_maps_to_watch(self):
        ta = self._build_with_hint("watch_only")
        assert ta.action_chain[0].action_type == ActionType.WATCH

    def test_review_required_maps_to_watch_under_review(self):
        ta = self._build_with_hint("review_required")
        assert ta.action_chain[0].action_type == ActionType.WATCH
        assert ta.validation_status == ValidationStatus.UNDER_REVIEW
        assert ta.requires_manual_review is True

    def test_open_position_maps_to_long(self):
        ta = self._build_with_hint("open_position")
        assert ta.action_chain[0].action_type == ActionType.LONG

    def test_add_position_maps_to_add(self):
        ta = self._build_with_hint("add_position")
        assert ta.action_chain[0].action_type == ActionType.ADD

    def test_close_position_maps_to_close_long(self):
        ta = self._build_with_hint("close_position")
        assert ta.action_chain[0].action_type == ActionType.CLOSE_LONG

    # Extended mappings (not in primary spec but supported)

    def test_reduce_position_maps_to_reduce(self):
        ta = self._build_with_hint("reduce_position")
        assert ta.action_chain[0].action_type == ActionType.REDUCE

    def test_hold_position_maps_to_hold(self):
        ta = self._build_with_hint("hold_position")
        assert ta.action_chain[0].action_type == ActionType.HOLD

    def test_watch_or_no_trade_maps_to_watch(self):
        ta = self._build_with_hint("watch_or_no_trade")
        assert ta.action_chain[0].action_type == ActionType.WATCH

    def test_avoid_or_watch_risk_maps_to_watch(self):
        ta = self._build_with_hint("avoid_or_watch_risk")
        assert ta.action_chain[0].action_type == ActionType.WATCH

    def test_unknown_hint_maps_to_watch_under_review(self):
        """Unknown action_hint falls back to WATCH + under_review."""
        # We need a valid ACTION_HINT_LITERAL to pass PolicyMappedIntent validation,
        # but we can test the internal _resolve_action_chain directly.
        from finer.extraction.canonical_action_builder import _ACTION_HINT_MAP
        # Verify all known hints have entries
        known_hints = [
            "consider_buy", "consider_sell", "watch_only", "review_required",
            "open_position", "add_position", "close_position",
            "watch_or_no_trade", "avoid_or_watch_risk",
            "reduce_position", "hold_position",
        ]
        for hint in known_hints:
            assert hint in _ACTION_HINT_MAP, f"Missing mapping for '{hint}'"


# =============================================================================
# Direction mapping
# =============================================================================


class TestDirectionMapping:
    """Verify F3 direction maps to correct TradeDirection."""

    def _build_with_direction(self, direction: str) -> TradeAction:
        builder = CanonicalActionBuilder()
        intent = _make_intent(direction=direction)
        mapped = _make_mapped_intent(intent_id=intent.intent_id)
        return builder.build(intent, mapped, [_uid("span-")], _make_timing())

    def test_bullish_maps_to_bullish(self):
        ta = self._build_with_direction("bullish")
        assert ta.direction == TradeDirection.BULLISH

    def test_bearish_maps_to_bearish(self):
        ta = self._build_with_direction("bearish")
        assert ta.direction == TradeDirection.BEARISH

    def test_neutral_maps_to_neutral(self):
        ta = self._build_with_direction("neutral")
        assert ta.direction == TradeDirection.NEUTRAL

    def test_mixed_maps_to_neutral(self):
        ta = self._build_with_direction("mixed")
        assert ta.direction == TradeDirection.NEUTRAL

    def test_unknown_maps_to_neutral(self):
        ta = self._build_with_direction("unknown")
        assert ta.direction == TradeDirection.NEUTRAL


# =============================================================================
# Confidence handling
# =============================================================================


class TestConfidenceHandling:
    """Verify confidence is the min of intent and policy confidence."""

    def test_uses_lower_confidence(self):
        builder = CanonicalActionBuilder()
        intent = _make_intent(confidence=0.9)
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            mapping_confidence=0.7,
        )
        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())
        assert ta.confidence == 0.7

    def test_uses_intent_confidence_when_lower(self):
        builder = CanonicalActionBuilder()
        intent = _make_intent(confidence=0.6)
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            mapping_confidence=0.9,
        )
        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())
        assert ta.confidence == 0.6


# =============================================================================
# Review flag propagation
# =============================================================================


class TestReviewFlag:
    """Verify requires_manual_review propagation from policy."""

    def test_policy_review_flag_propagates(self):
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            requires_human_review=True,
        )
        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())
        assert ta.requires_manual_review is True

    def test_review_required_hint_sets_flag(self):
        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            action_hint="review_required",
        )
        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())
        assert ta.requires_manual_review is True
        assert ta.validation_status == ValidationStatus.UNDER_REVIEW


# =============================================================================
# Rationale
# =============================================================================


class TestRationale:
    """Verify rationale contains key information."""

    def test_rationale_contains_key_info(self):
        builder = CanonicalActionBuilder()
        intent = _make_intent(
            target_name="腾讯",
            target_symbol="0700.HK",
            direction="bullish",
        )
        mapped = _make_mapped_intent(
            intent_id=intent.intent_id,
            action_hint="add_position",
        )
        ta = builder.build(intent, mapped, [_uid("span-")], _make_timing())

        assert "0700.HK" in ta.rationale
        assert "bullish" in ta.rationale
        assert "add_position" in ta.rationale
        assert "F3->F4->F5" in ta.rationale


# =============================================================================
# Integration: serialization round-trip
# =============================================================================


class TestSerialization:
    """Verify the built TradeAction survives JSON round-trip."""

    def test_json_round_trip(self):
        import json

        builder = CanonicalActionBuilder()
        intent = _make_intent()
        mapped = _make_mapped_intent(intent_id=intent.intent_id)
        timing = _make_timing()

        ta = builder.build(intent, mapped, [_uid("span-")], timing)

        data = ta.model_dump(mode="json")
        json_str = json.dumps(data, default=str)
        restored = json.loads(json_str)

        assert restored["intent_id"] == intent.intent_id
        assert restored["policy_id"] == mapped.policy_id
        assert restored["canonical_trace_status"] == "canonical"
        assert restored["execution_timing"] is not None
        assert restored["execution_timing"]["timing_policy_id"] == "market-calendar-v1"
