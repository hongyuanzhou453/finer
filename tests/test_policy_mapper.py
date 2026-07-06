"""Tests for F4 PolicyMapper and GlobalBasePolicy.

Covers:
  - Action hint mapping rules (all actionability/direction/position_delta combos)
  - Position sizing from conviction
  - Risk constraint generation
  - Mandatory mapping_rationale and policy_layers_applied
  - Bearish opinion does NOT generate short/explicit actions
  - "我看好宁德时代" → watch_or_no_trade (NOT open_position)
  - "我加仓宁德时代" → add_position
  - "目前依然持有，稍微加仓一点" → conservative sizing
  - PolicyMapper.map_intent() and map_batch()
  - PolicyMappingBatch auto-stats
"""

import pytest
from typing import List

from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import (
    PolicyMappingResult,
    PolicyMappedIntent,
    PolicyMappingBatch,
    PolicyRiskConstraints,
)
from finer.policy.global_base import GlobalBasePolicy
from finer.policy.policy_mapper import PolicyMapper


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def policy() -> GlobalBasePolicy:
    """Default GlobalBasePolicy."""
    return GlobalBasePolicy()


@pytest.fixture
def mapper() -> PolicyMapper:
    """Default PolicyMapper."""
    return PolicyMapper()


def _make_intent(
    intent_id: str = "intent-test-001",
    actionability: str = "explicit_action",
    direction: str = "bullish",
    position_delta_hint: str = "add",
    conviction: float = 0.85,
    confidence: float = 0.9,
    target_name: str = "宁德时代",
    target_symbol: str = "300750.SZ",
    market: str = "CN",
    target_type: str = "stock",
    creator_id: str = "kol-test-001",
    block_ids: List[str] | None = None,
    ambiguity_flags: List[str] | None = None,
) -> NormalizedInvestmentIntent:
    """Create a NormalizedInvestmentIntent with controlled fields."""
    return NormalizedInvestmentIntent(
        intent_id=intent_id,
        envelope_id="env-test-001",
        block_ids=block_ids or ["block-1"],
        creator_id=creator_id,
        target_type=target_type,
        target_name=target_name,
        target_symbol=target_symbol,
        market=market,
        direction=direction,
        actionability=actionability,
        position_delta_hint=position_delta_hint,
        conviction=conviction,
        confidence=confidence,
        evidence_span_ids=["span-001"],
        ambiguity_flags=ambiguity_flags or [],
    )


# =============================================================================
# Action Hint Mapping Rules
# =============================================================================

class TestActionHintMapping:
    """Tests for the core action_hint mapping rules."""

    # -- Opinion + Bullish --

    def test_opinion_bullish_maps_to_watch_or_no_trade(self, mapper):
        """'我看好宁德时代' should NOT generate open_position."""
        intent = _make_intent(
            actionability="opinion",
            direction="bullish",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_or_no_trade", (
            f"opinion+bullish should be watch_or_no_trade, got {result.action_hint}"
        )
        assert result.action_hint != "open_position", (
            "opinion MUST NOT become open_position"
        )
        assert result.position_sizing_hint == "none"

    def test_opinion_bullish_chinese_watch_example(self, mapper):
        """'我看好宁德时代' → watch_or_no_trade, no position."""
        intent = _make_intent(
            actionability="opinion",
            direction="bullish",
            position_delta_hint="none",
            target_name="宁德时代",
            target_symbol="300750.SZ",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_or_no_trade"
        assert result.position_sizing_hint == "none"
        # Must NOT be open_position
        assert "open" not in result.action_hint

    # -- Opinion + Bearish --

    def test_opinion_bearish_maps_to_avoid_or_watch_risk(self, mapper):
        """Bearish opinion → avoid_or_watch_risk, NOT a short action."""
        intent = _make_intent(
            actionability="opinion",
            direction="bearish",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "avoid_or_watch_risk", (
            f"opinion+bearish should be avoid_or_watch_risk, got {result.action_hint}"
        )
        # Must NOT generate a trade action hint
        assert result.action_hint not in ("open_position", "add_position",
                                           "close_position", "reduce_position")

    def test_bearish_opinion_no_short_action(self, mapper):
        """Bearish opinion MUST NOT become a short/close action unless explicit_action."""
        intent = _make_intent(
            actionability="opinion",
            direction="bearish",
            position_delta_hint="none",
            conviction=0.9,  # High conviction still doesn't trigger action
        )
        result = mapper.map_intent(intent)
        # Should be avoid_or_watch_risk, NOT close_position or reduce_position
        assert result.action_hint == "avoid_or_watch_risk"
        assert result.action_hint not in (
            "close_position", "reduce_position", "open_position", "add_position"
        )

    # -- Opinion + Neutral --

    def test_opinion_neutral_maps_to_watch_only(self, mapper):
        """Neutral opinion → watch_only."""
        intent = _make_intent(
            actionability="opinion",
            direction="neutral",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_only"

    # -- Watch --

    def test_watch_actionability_maps_to_watch_only(self, mapper):
        """actionability=watch → watch_only regardless of direction."""
        for direction in ("bullish", "bearish", "neutral", "mixed"):
            intent = _make_intent(
                intent_id=f"intent-watch-{direction}",
                actionability="watch",
                direction=direction,
                position_delta_hint="none",
            )
            result = mapper.map_intent(intent)
            assert result.action_hint == "watch_only", (
                f"watch+{direction} should be watch_only, got {result.action_hint}"
            )

    # -- Explicit Action + Open --

    def test_explicit_action_open_bullish(self, mapper):
        """explicit_action + open + bullish → open_position."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="open",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "open_position"

    def test_explicit_action_open_bearish_review_required(self, mapper):
        """explicit_action + open + bearish → review_required (could be short)."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bearish",
            position_delta_hint="open",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required", (
            "bearish+open should escalate to review_required (potential short)"
        )

    # -- Explicit Action + Add --

    def test_explicit_action_add_bullish(self, mapper):
        """explicit_action + add + bullish → add_position."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            target_name="宁德时代",
            target_symbol="300750.SZ",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "add_position", (
            f"'我加仓宁德时代' should be add_position, got {result.action_hint}"
        )

    def test_explicit_action_add_chinese_jiacang_example(self, mapper):
        """'我加仓宁德时代' → add_position with medium/small sizing."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            target_name="宁德时代",
            target_symbol="300750.SZ",
            conviction=0.85,
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "add_position"
        assert result.position_sizing_hint in ("small", "medium")

    # -- Explicit Action + Reduce/Exit --

    def test_explicit_action_reduce(self, mapper):
        """explicit_action + reduce → reduce_position."""
        for direction in ("bullish", "bearish"):
            intent = _make_intent(
                intent_id=f"intent-reduce-{direction}",
                actionability="explicit_action",
                direction=direction,
                position_delta_hint="reduce",
            )
            result = mapper.map_intent(intent)
            assert result.action_hint == "reduce_position"

    def test_explicit_action_exit(self, mapper):
        """explicit_action + exit → close_position."""
        for direction in ("bullish", "bearish"):
            intent = _make_intent(
                intent_id=f"intent-exit-{direction}",
                actionability="explicit_action",
                direction=direction,
                position_delta_hint="exit",
            )
            result = mapper.map_intent(intent)
            assert result.action_hint == "close_position"

    # -- Explicit Action + Hold --

    def test_explicit_action_hold(self, mapper):
        """explicit_action + hold → hold_position."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="hold",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "hold_position"

    # -- Review Required --

    def test_review_required_actionability(self, mapper):
        """actionability=review_required → review_required."""
        intent = _make_intent(
            actionability="review_required",
            direction="bullish",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required"

    # -- Neutral direction mapping --

    def test_neutral_direction_maps_to_watch_only(self, mapper):
        """direction=neutral → watch_only (regardless of position_delta_hint)."""
        intent = _make_intent(
            actionability="opinion",
            direction="neutral",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_only"


# =============================================================================
# Position Sizing & Conservative Handling
# =============================================================================

class TestPositionSizing:
    """Tests for position_sizing_hint logic."""

    def test_low_conviction_sizing_none(self, mapper):
        """Low conviction (<0.35) → sizing 'none'."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.2,
        )
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint == "none"

    def test_medium_conviction_sizing_small(self, mapper):
        """Medium conviction (0.35-0.7) → sizing 'small'."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.5,
        )
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint == "small"

    def test_high_conviction_sizing_medium(self, mapper):
        """High conviction (>0.7) → sizing 'medium'."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.9,
        )
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint == "medium"

    def test_global_base_never_outputs_large(self, mapper):
        """GlobalBasePolicy NEVER outputs 'large' position sizing."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.99,  # Near certainty
        )
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint != "large", (
            "GlobalBase must never output 'large' position_sizing_hint"
        )
        assert result.position_sizing_hint in ("small", "medium", "none", "review_required")

    def test_conservative_sizing_for_cautious_add(self, mapper):
        """'目前依然持有，稍微加仓一点' → conservative: add but sizing=small."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.55,  # Moderate conviction, not strong
            target_name="宁德时代",
        )
        result = mapper.map_intent(intent)
        # Must be add_position, but sizing should be conservative
        assert result.action_hint == "add_position"
        assert result.position_sizing_hint == "small", (
            f"'稍微加仓一点' with moderate conviction should be 'small', "
            f"got {result.position_sizing_hint}"
        )
        # Must NOT be full buy / open_position
        assert result.action_hint != "open_position"

    def test_ambiguous_intent_sizing_review_required(self, mapper):
        """Ambiguous intent (2+ flags) → sizing=review_required."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.7,
            ambiguity_flags=["multiple_targets", "vague_time"],
        )
        result = mapper.map_intent(intent)
        assert result.position_sizing_hint == "review_required"
        assert result.risk_constraints.requires_human_review is True

    def test_watch_actions_have_no_position(self, mapper):
        """Watch/watch_or_no_trade actions always have 'none' sizing."""
        for actionability, direction in [
            ("opinion", "bullish"),
            ("opinion", "bearish"),
            ("opinion", "neutral"),
        ]:
            intent = _make_intent(
                intent_id=f"intent-{actionability}-{direction}",
                actionability=actionability,
                direction=direction,
                position_delta_hint="none",
            )
            result = mapper.map_intent(intent)
            assert result.position_sizing_hint == "none", (
                f"{actionability}+{direction} should have none sizing"
            )


# =============================================================================
# Risk Constraints
# =============================================================================

class TestRiskConstraints:
    """Tests for risk_constraints generation."""

    def test_has_max_position_hint(self, mapper):
        """Every mapping must have max_position_hint."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
        )
        result = mapper.map_intent(intent)
        assert isinstance(result.risk_constraints, PolicyRiskConstraints)
        assert result.risk_constraints.max_position_hint is not None
        assert result.risk_constraints.max_position_hint in (
            "none", "small", "medium", "large"
        )

    def test_has_requires_human_review(self, mapper):
        """Every mapping must have requires_human_review boolean."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        assert isinstance(result.risk_constraints.requires_human_review, bool)

    def test_has_risk_notes(self, mapper):
        """Every mapping must have risk_notes list."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        assert isinstance(result.risk_constraints.risk_notes, list)

    def test_review_required_action_forces_human_review(self, mapper):
        """review_required action_hint → requires_human_review=True."""
        intent = _make_intent(
            actionability="review_required",
            direction="bullish",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required"
        assert result.risk_constraints.requires_human_review is True

    def test_low_conviction_forces_review(self, mapper):
        """conviction < 0.3 on actionable intent → requires_human_review."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.2,
        )
        result = mapper.map_intent(intent)
        assert result.risk_constraints.requires_human_review is True

    def test_high_conviction_no_forced_review(self, mapper):
        """conviction >= 0.7 with clear intent → no forced review."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
            conviction=0.85,
        )
        result = mapper.map_intent(intent)
        assert result.risk_constraints.requires_human_review is False


# =============================================================================
# Mandatory Fields: mapping_rationale & policy_layers_applied
# =============================================================================

class TestMandatoryFields:
    """Tests that every mapping has required audit fields."""

    def test_every_mapping_has_rationale(self, mapper):
        """Each PolicyMappingResult must include mapping_rationale."""
        for actionability, direction, pos_hint in [
            ("opinion", "bullish", "none"),
            ("opinion", "bearish", "none"),
            ("explicit_action", "bullish", "add"),
            ("explicit_action", "bullish", "open"),
            ("explicit_action", "bearish", "exit"),
            ("watch", "neutral", "none"),
        ]:
            intent = _make_intent(
                intent_id=f"intent-rationale-{actionability}-{direction}",
                actionability=actionability,
                direction=direction,
                position_delta_hint=pos_hint,
            )
            result = mapper.map_intent(intent)
            assert result.mapping_rationale, (
                f"Mapping {actionability}+{direction}+{pos_hint} is missing rationale"
            )
            assert len(result.mapping_rationale) > 20, (
                f"Rationale too short for {actionability}+{direction}+{pos_hint}: "
                f"'{result.mapping_rationale}'"
            )

    def test_every_mapping_has_policy_layers_applied(self, mapper):
        """Each mapping must include policy_layers_applied with at least GlobalBase."""
        for actionability, direction, pos_hint in [
            ("opinion", "bullish", "none"),
            ("explicit_action", "bullish", "add"),
            ("explicit_action", "bearish", "exit"),
        ]:
            intent = _make_intent(
                intent_id=f"intent-layers-{actionability}-{direction}",
                actionability=actionability,
                direction=direction,
                position_delta_hint=pos_hint,
            )
            result = mapper.map_intent(intent)
            assert "GlobalBase" in result.policy_layers_applied, (
                f"policy_layers_applied missing 'GlobalBase' "
                f"for {actionability}+{direction}+{pos_hint}: "
                f"got {result.policy_layers_applied}"
            )
            assert len(result.policy_layers_applied) >= 1

    def test_policy_version_is_global_base_v1(self, mapper):
        """Default policy_version is 'global-base-v1'."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        assert result.policy_version == "global-base-v1"

    def test_intent_id_is_preserved(self, mapper):
        """PolicyMappingResult.intent_id must match the input intent's ID."""
        intent = _make_intent(intent_id="my-custom-intent-id")
        result = mapper.map_intent(intent)
        assert result.intent_id == "my-custom-intent-id"


# =============================================================================
# Layer Trace Tests
# =============================================================================

class TestLayerTraces:
    """Tests for per-layer audit trail."""

    def test_has_layer_traces(self, mapper):
        """Each mapping must produce layer_traces."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        assert len(result.layer_traces) >= 1, (
            "Every mapping must have at least one layer trace"
        )

    def test_global_base_trace_applied(self, mapper):
        """GlobalBase trace must show applied=True."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        gb_trace = [t for t in result.layer_traces if t.layer_name == "GlobalBase"]
        assert len(gb_trace) == 1
        assert gb_trace[0].applied is True
        assert gb_trace[0].layer_version == "global-base-v1"
        assert len(gb_trace[0].modifications) >= 3  # action_hint, sizing, holding

    def test_has_decisions(self, mapper):
        """Each mapping must produce at least one PolicyDecision."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        assert len(result.decisions) >= 1


# =============================================================================
# PolicyMapper.map_batch() Tests
# =============================================================================

class TestMapBatch:
    """Tests for batch mapping."""

    def test_map_batch_returns_policy_mapping_batch(self, mapper):
        """map_batch returns PolicyMappingBatch."""
        intents = [
            _make_intent(intent_id="intent-1", actionability="opinion",
                         direction="bullish", position_delta_hint="none"),
            _make_intent(intent_id="intent-2", actionability="explicit_action",
                         direction="bullish", position_delta_hint="add"),
            _make_intent(intent_id="intent-3", actionability="watch",
                         direction="neutral", position_delta_hint="none"),
        ]
        batch = mapper.map_batch(intents)
        assert isinstance(batch, PolicyMappingBatch)
        assert batch.total_mappings == 3
        assert batch.total_mapped_intents == 3

    def test_map_batch_each_intent_mapped(self, mapper):
        """Each intent in batch gets a mapping."""
        intents = [
            _make_intent(intent_id=f"batch-{i}") for i in range(5)
        ]
        batch = mapper.map_batch(intents)
        assert len(batch.mappings) == 5
        assert len(batch.mapped_intents) == 5
        for mapping, intent in zip(batch.mappings, intents):
            assert mapping.intent_id == intent.intent_id

    def test_map_batch_review_count(self, mapper):
        """Batch correctly counts review_required."""
        intents = [
            _make_intent(intent_id="ok-1", actionability="explicit_action",
                         direction="bullish", position_delta_hint="add",
                         conviction=0.85),
            _make_intent(intent_id="review-1", actionability="review_required",
                         direction="bullish", position_delta_hint="none"),
            _make_intent(intent_id="review-2", actionability="explicit_action",
                         direction="bearish", position_delta_hint="open"),
        ]
        batch = mapper.map_batch(intents)
        assert batch.review_required_count >= 2  # review_required + bearish+open

    def test_map_batch_empty_raises(self, mapper):
        """Empty batch raises ValueError."""
        with pytest.raises(ValueError):
            mapper.map_batch([])

    def test_map_batch_invalid_type_raises(self, mapper):
        """Non-Intent items in batch raise TypeError."""
        with pytest.raises(TypeError):
            mapper.map_batch(["not an intent"])  # type: ignore[list-item]

    def test_map_batch_mapped_intents_have_policy_id(self, mapper):
        """Each mapped intent references its policy result."""
        intents = [
            _make_intent(intent_id="linked-1"),
            _make_intent(intent_id="linked-2"),
        ]
        batch = mapper.map_batch(intents)
        for pmi, pmr in zip(batch.mapped_intents, batch.mappings):
            assert pmi.policy_id == pmr.policy_id
            assert pmi.intent_id == pmr.intent_id

    def test_map_intent_raises_on_invalid_input(self, mapper):
        """map_intent rejects non-NormalizedInvestmentIntent."""
        with pytest.raises(TypeError):
            mapper.map_intent("not an intent")  # type: ignore[arg-type]


# =============================================================================
# GlobalBasePolicy Direct Tests
# =============================================================================

class TestGlobalBasePolicyDirect:
    """Tests for GlobalBasePolicy methods directly."""

    def test_lookup_action_hint_returns_valid_literal(self, policy):
        """All returned action hints must be valid action_hint literals."""
        valid = {"watch_only", "watch_or_no_trade", "avoid_or_watch_risk",
                 "open_position", "add_position", "reduce_position",
                 "hold_position", "close_position", "review_required"}
        # Test all known combos
        combos = [
            ("opinion", "bullish", "none"),
            ("opinion", "bearish", "none"),
            ("opinion", "neutral", "none"),
            ("explicit_action", "bullish", "open"),
            ("explicit_action", "bullish", "add"),
            ("explicit_action", "bullish", "reduce"),
            ("explicit_action", "bullish", "exit"),
            ("explicit_action", "bullish", "hold"),
            ("explicit_action", "bearish", "exit"),
            ("explicit_action", "bearish", "reduce"),
            ("explicit_action", "bearish", "hold"),
            ("watch", "bullish", "none"),
            ("review_required", "bullish", "none"),
        ]
        for act, dir_, pos in combos:
            hint = policy.lookup_action_hint(act, dir_, pos)
            assert hint in valid, f"Invalid hint '{hint}' for ({act}, {dir_}, {pos})"

    def test_compute_position_sizing_respects_ceiling(self, policy):
        """Position sizing never exceeds global-base ceiling (medium)."""
        sizing = policy.compute_position_sizing_hint("add_position", 0.99)
        assert sizing != "large"
        assert sizing in ("none", "small", "medium", "review_required")

    def test_compute_risk_constraints_minimal(self, policy):
        """Risk constraints are always created with required fields."""
        rc = policy.compute_risk_constraints("add_position", 0.7)
        assert rc.max_position_hint is not None
        assert isinstance(rc.requires_human_review, bool)
        assert isinstance(rc.risk_notes, list)

    def test_position_taking_hints_get_default_exit_rules(self, policy):
        """Position-taking hints carry the v1 numeric exit-rule defaults,
        which must stay equal to the historical F8 constants (zero drift)."""
        rc = policy.compute_risk_constraints("add_position", 0.7)
        assert rc.stop_loss_pct_hint == -0.10
        assert rc.take_profit_pct_hint == 0.20
        assert rc.max_holding_days_hint == 30

    def test_watch_hints_get_no_exit_rules(self, policy):
        """Non-position hints have no exit-rule hints."""
        rc = policy.compute_risk_constraints("watch_only", 0.7)
        assert rc.stop_loss_pct_hint is None
        assert rc.take_profit_pct_hint is None
        assert rc.max_holding_days_hint is None


# =============================================================================
# PolicyMappedIntent Tests
# =============================================================================

class TestPolicyMappedIntentOutput:
    """Tests for PolicyMappedIntent as output of map_batch."""

    def test_mapped_intent_has_original_summary(self, mapper):
        """Mapped intent preserves F3 intent summary."""
        intent = _make_intent(
            target_name="腾讯控股",
            target_symbol="0700.HK",
            market="HK",
        )
        batch = mapper.map_batch([intent])
        pmi = batch.mapped_intents[0]
        # summarize() uses target_symbol over target_name when available
        assert len(pmi.original_intent_summary) > 0
        assert "0700.HK" in pmi.original_intent_summary or \
               "腾讯控股" in pmi.original_intent_summary

    def test_mapped_intent_carries_action_hint(self, mapper):
        """Mapped intent carries the policy-determined action hint."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
        )
        batch = mapper.map_batch([intent])
        pmi = batch.mapped_intents[0]
        assert pmi.action_hint == "add_position"

    def test_mapped_intent_carries_exit_rule_hints(self, mapper):
        """Mapped intent carries the numeric exit-rule hints from risk constraints."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="add",
        )
        batch = mapper.map_batch([intent])
        pmi = batch.mapped_intents[0]
        assert pmi.stop_loss_pct_hint == -0.10
        assert pmi.take_profit_pct_hint == 0.20
        assert pmi.max_holding_days_hint == 30

    def test_mapped_intent_carries_position_sizing_hint(self, mapper):
        """Mapped intent carries position sizing hint."""
        intent = _make_intent(conviction=0.9)
        batch = mapper.map_batch([intent])
        pmi = batch.mapped_intents[0]
        assert pmi.position_sizing_hint in ("none", "small", "medium", "large", "review_required")

    def test_mapped_intent_review_consistency(self, mapper):
        """When action_hint is review_required, requires_human_review is True."""
        intent = _make_intent(
            actionability="review_required",
            direction="bullish",
            position_delta_hint="none",
        )
        batch = mapper.map_batch([intent])
        pmi = batch.mapped_intents[0]
        assert pmi.action_hint == "review_required"
        assert pmi.requires_human_review is True

    def test_mapped_intent_json_serializable(self, mapper):
        """Mapped intent output is JSON-serializable."""
        intent = _make_intent()
        batch = mapper.map_batch([intent])
        pmi = batch.mapped_intents[0]
        data = pmi.model_dump(mode='json')
        assert isinstance(data["mapped_id"], str)
        assert isinstance(data["action_hint"], str)
        assert isinstance(data["created_at"], str)

    def test_batch_json_serializable(self, mapper):
        """Batch output is JSON-serializable."""
        intents = [
            _make_intent(intent_id="json-1"),
            _make_intent(intent_id="json-2"),
        ]
        batch = mapper.map_batch(intents)
        data = batch.model_dump(mode='json')
        assert isinstance(data["batch_id"], str)
        assert isinstance(data["created_at"], str)
        assert len(data["mappings"]) == 2
        assert len(data["mapped_intents"]) == 2


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_unknown_direction_with_opinion(self, mapper):
        """direction=unknown + opinion → watch_only."""
        intent = _make_intent(
            actionability="opinion",
            direction="unknown",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "watch_only"

    def test_mixed_direction_with_explicit_action(self, mapper):
        """mixed direction + explicit_action → review_required."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="mixed",
            position_delta_hint="add",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required"

    def test_explicit_action_without_position_hint(self, mapper):
        """explicit_action + position_delta_hint=none → review_required."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="none",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required"

    def test_explicit_action_unknown_position_hint(self, mapper):
        """explicit_action + position_delta_hint=unknown → review_required."""
        intent = _make_intent(
            actionability="explicit_action",
            direction="bullish",
            position_delta_hint="unknown",
        )
        result = mapper.map_intent(intent)
        assert result.action_hint == "review_required"

    def test_no_llm_no_trade_action(self, mapper):
        """Verify PolicyMapper does not produce TradeAction objects."""
        intent = _make_intent()
        result = mapper.map_intent(intent)
        # Check that result is PolicyMappingResult, not TradeAction
        assert isinstance(result, PolicyMappingResult)
        # There is no 'trade_action' field on PolicyMappingResult
        data = result.model_dump()
        assert "trade_action" not in data
        assert "action_chain" not in data
        assert "position_size_pct" not in data

    def test_result_json_roundtrip(self, mapper):
        """PolicyMappingResult survives JSON serialization round-trip."""
        import json
        from datetime import datetime
        intent = _make_intent()
        result = mapper.map_intent(intent)
        json_str = result.model_dump_json()
        restored = PolicyMappingResult.model_validate_json(json_str)
        assert restored.intent_id == result.intent_id
        assert restored.action_hint == result.action_hint
        assert restored.position_sizing_hint == result.position_sizing_hint
