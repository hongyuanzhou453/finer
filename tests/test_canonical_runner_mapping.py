"""Pin canonical_runner's F4→F5 mapping to the CanonicalActionBuilder truth.

The runner keeps its own ACTION_HINT_TO_ACTION_TYPE table (it adds the
opinion-tier WATCH hints), which silently drifted from the builder once
already: add_position/reduce_position kept collapsing to LONG/CLOSE_LONG
after the builder moved to ADD/REDUCE (live regen 2026-07-05 output had
zero ADD/REDUCE actions despite 6 matching F4 hints). These tests fail
loudly on the next drift.
"""
from __future__ import annotations

from datetime import datetime

from finer.extraction.canonical_action_builder import (
    _ACTION_HINT_MAP,
    build_action_metadata,
)
from finer.pipeline.canonical_runner import ACTION_HINT_TO_ACTION_TYPE
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent
from finer.schemas.trade_action import ActionType


def test_runner_hint_mapping_matches_builder():
    """Every hint the runner maps must agree with the builder's ActionType."""
    drift = {}
    for hint, runner_type in ACTION_HINT_TO_ACTION_TYPE.items():
        builder_entry = _ACTION_HINT_MAP.get(hint)
        if builder_entry is not None and builder_entry[0] != runner_type:
            drift[hint] = (runner_type, builder_entry[0])
    assert drift == {}, f"runner vs builder ActionType drift: {drift}"


def test_runner_maps_add_reduce_fine_grained():
    assert ACTION_HINT_TO_ACTION_TYPE["add_position"] == ActionType.ADD
    assert ACTION_HINT_TO_ACTION_TYPE["reduce_position"] == ActionType.REDUCE


def test_build_action_metadata_carries_style_and_exit_hints():
    intent = NormalizedInvestmentIntent(
        envelope_id="env-1",
        block_ids=["b-1"],
        creator_id="k1",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.8,
        confidence=0.9,
        margin_flag=True,
        entry_timing_style="left_side",
    )
    mapped = PolicyMappedIntent(
        intent_id=intent.intent_id,
        policy_id="pol-1",
        original_intent_summary="test",
        action_hint="add_position",
        position_sizing_hint="small",
        holding_period_hint="medium_term",
        stop_loss_pct_hint=-0.10,
        take_profit_pct_hint=0.20,
        max_holding_days_hint=30,
        mapping_confidence=0.9,
        created_at=datetime(2026, 7, 1),
    )
    meta = build_action_metadata(intent, mapped)
    assert meta["entry_timing_style"] == "left_side"
    assert meta["margin_flag"] is True
    assert "leverage_flag" not in meta  # None = not mentioned, stays absent
    assert meta["stop_loss_pct"] == -0.10
    assert meta["take_profit_pct"] == 0.20
    assert meta["max_holding_days"] == 30
