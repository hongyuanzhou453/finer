"""Tests for the F4 per-style exit-rule overlay (PolicyMapper + tuning.by_style).

The overlay is inert unless the active policy's tuning declares by_style
overrides; the shipped config ships none, so default behavior is unchanged.
"""
from __future__ import annotations

from finer.policy.global_base import GlobalBasePolicy
from finer.policy.policy_config import ExitRuleHints, PolicyTuning
from finer.policy.policy_mapper import PolicyMapper
from finer.schemas.investment_intent import NormalizedInvestmentIntent


def _intent(creator_id="trader_ji", actionability="explicit_action",
            direction="bullish", position_delta_hint="add", conviction=0.85):
    return NormalizedInvestmentIntent(
        intent_id="intent-ovl-001",
        envelope_id="env-ovl-001",
        block_ids=["block-1"],
        creator_id=creator_id,
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction=direction,
        actionability=actionability,
        position_delta_hint=position_delta_hint,
        conviction=conviction,
        confidence=0.9,
        evidence_span_ids=["span-001"],
        ambiguity_flags=[],
    )


def _policy_with_style_override():
    """GlobalBase whose tuning tunes right_side exit rules."""
    tuning = PolicyTuning(
        base_exit=ExitRuleHints(-0.10, 0.20, 30),
        by_style={"right_side": ExitRuleHints(stop_loss_pct=-0.10,
                                              take_profit_pct=0.30,
                                              max_holding_days=20)},
    )
    return GlobalBasePolicy(tuning=tuning)


# --- inert by default --------------------------------------------------------

def test_no_overlay_when_by_style_empty():
    calls: list[str] = []
    mapper = PolicyMapper(style_resolver=lambda cid: calls.append(cid) or "right_side")
    result = mapper.map_intent(_intent())
    rc = result.risk_constraints
    # base exit hints unchanged
    assert rc.stop_loss_pct_hint == -0.10
    assert rc.take_profit_pct_hint == 0.20
    assert rc.max_holding_days_hint == 30
    assert result.policy_layers_applied == ["GlobalBase"]
    # Empty by_style → resolver never consulted (no wasted registry lookup).
    assert calls == []


# --- overlay applies ---------------------------------------------------------

def test_overlay_applies_for_matching_style():
    mapper = PolicyMapper(
        policy=_policy_with_style_override(),
        style_resolver=lambda cid: "right_side",
    )
    result = mapper.map_intent(_intent())
    rc = result.risk_constraints
    assert rc.take_profit_pct_hint == 0.30        # overridden
    assert rc.max_holding_days_hint == 20          # overridden
    assert rc.stop_loss_pct_hint == -0.10          # base
    assert "StyleExitOverlay" in result.policy_layers_applied
    assert any("right_side" in n for n in rc.risk_notes)
    assert any(t.layer_name == "StyleExitOverlay" for t in result.layer_traces)


def test_overlay_skipped_when_style_not_tuned():
    mapper = PolicyMapper(
        policy=_policy_with_style_override(),
        style_resolver=lambda cid: "left_side",  # no by_style entry
    )
    rc = mapper.map_intent(_intent()).risk_constraints
    assert rc.take_profit_pct_hint == 0.20  # base
    assert rc.max_holding_days_hint == 30


def test_overlay_skipped_for_non_position_intent():
    # opinion+bullish → watch_or_no_trade → no exit hints to tune.
    mapper = PolicyMapper(
        policy=_policy_with_style_override(),
        style_resolver=lambda cid: "right_side",
    )
    result = mapper.map_intent(
        _intent(actionability="opinion", position_delta_hint="none")
    )
    rc = result.risk_constraints
    assert rc.stop_loss_pct_hint is None
    assert rc.take_profit_pct_hint is None
    assert "StyleExitOverlay" not in result.policy_layers_applied


def test_resolver_exception_falls_back_to_base():
    def boom(_cid):
        raise RuntimeError("registry down")

    mapper = PolicyMapper(policy=_policy_with_style_override(), style_resolver=boom)
    rc = mapper.map_intent(_intent()).risk_constraints
    assert rc.take_profit_pct_hint == 0.20  # base, no crash


def test_missing_creator_id_falls_back_to_base():
    mapper = PolicyMapper(
        policy=_policy_with_style_override(),
        style_resolver=lambda cid: "right_side",
    )
    rc = mapper.map_intent(_intent(creator_id="")).risk_constraints
    assert rc.take_profit_pct_hint == 0.20  # base
