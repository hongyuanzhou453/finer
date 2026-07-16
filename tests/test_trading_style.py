"""Tests for the KOL trading-style profile service (services/trading_style.py)."""
from __future__ import annotations

import itertools
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)
from finer.services.trading_style import (
    build_style_profile,
    compute_observed_style,
    load_declared_style,
)


# =============================================================================
# Helpers
# =============================================================================

_TICKER_SEQ = itertools.count()


def _action(
    action_type: ActionType = ActionType.LONG,
    creator_id: str = "kol-style-test",
    metadata: dict | None = None,
    ticker: str | None = None,
) -> TradeAction:
    """One observed action. Defaults to a UNIQUE ticker so each call is a
    distinct stance slot — i.e. one independent voter. Style votes are cast per
    stance episode, so passing the SAME ticker models a restated standing view
    (which deliberately collapses to a single vote)."""
    return TradeAction(
        timestamp=datetime(2026, 6, 1, 10, 0),
        source=SourceInfo(
            content_id="c-1", evidence_text="test", creator_id=creator_id
        ),
        target=TargetInfo(ticker=ticker or f"T{next(_TICKER_SEQ)}", market="CN"),
        direction=TradeDirection.BULLISH,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=action_type,
                trigger_type=TriggerType.MANUAL,
            )
        ],
        metadata=metadata or {},
    )


def _write_creator_yaml(root: Path, creator_id: str, config: dict) -> None:
    creators_dir = root / "configs" / "creators"
    creators_dir.mkdir(parents=True, exist_ok=True)
    (creators_dir / f"{creator_id}.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )


# =============================================================================
# Declared layer
# =============================================================================

class TestLoadDeclaredStyle:
    def test_loads_trading_style_block(self, tmp_path):
        _write_creator_yaml(tmp_path, "k1", {
            "creator_id": "k1",
            "display_name": "K1",
            "trading_style": {
                "uses_margin": False,
                "uses_leverage": None,
                "does_short": True,
                "entry_style": "left_side",
                "evidence_notes": ["直播自述从不融资"],
            },
        })
        declared = load_declared_style("k1", root=tmp_path)
        assert declared is not None
        assert declared.uses_margin is False
        assert declared.uses_leverage is None
        assert declared.does_short is True
        assert declared.entry_style == "left_side"
        assert declared.evidence_notes == ["直播自述从不融资"]

    def test_missing_config_returns_none(self, tmp_path):
        assert load_declared_style("nobody", root=tmp_path) is None

    def test_missing_block_returns_none(self, tmp_path):
        _write_creator_yaml(tmp_path, "k2", {"creator_id": "k2"})
        assert load_declared_style("k2", root=tmp_path) is None

    def test_invalid_block_returns_none(self, tmp_path):
        _write_creator_yaml(tmp_path, "k3", {
            "creator_id": "k3",
            "trading_style": {"entry_style": "not_a_valid_style"},
        })
        assert load_declared_style("k3", root=tmp_path) is None

    def test_real_trader_ji_config_parses(self):
        """The checked-in trader_ji annotation must stay schema-valid."""
        declared = load_declared_style("trader_ji")
        assert declared is not None
        assert declared.does_short is False
        assert declared.entry_style == "right_side"

    def test_invalid_block_keeps_display_name(self, tmp_path):
        """块隔离钉子：trading_style 无效不得拖垮档案其余字段（display_name）。"""
        _write_creator_yaml(tmp_path, "k4", {
            "creator_id": "k4",
            "display_name": "老四",
            "trading_style": {"entry_style": "not_a_valid_style"},
        })
        assert load_declared_style("k4", root=tmp_path) is None
        profile = build_style_profile(
            "k4", repository=_EmptyRepo(), root=tmp_path
        )
        assert profile.display_name == "老四"
        assert profile.declared is None


class _EmptyRepo:
    def load_all_actions(self):
        return []


# =============================================================================
# Observed layer
# =============================================================================

class TestComputeObservedStyle:
    def test_empty_actions_returns_none(self):
        assert compute_observed_style([]) is None

    def test_short_ratio(self):
        actions = [
            _action(ActionType.LONG),
            _action(ActionType.LONG),
            _action(ActionType.SHORT),
            _action(ActionType.BUY_PUT),
            _action(ActionType.WATCH),  # non-directional, excluded
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.sample_size == 5
        assert observed.directional_sample_size == 4
        assert observed.short_side_count == 2
        assert observed.short_ratio == 0.5

    def test_no_directional_sample_gives_none_ratio(self):
        observed = compute_observed_style([_action(ActionType.WATCH)])
        assert observed is not None
        assert observed.directional_sample_size == 0
        assert observed.short_ratio is None
        assert observed.low_sample is True

    def test_style_flag_counting(self):
        actions = [
            _action(metadata={"margin_flag": True}),
            _action(metadata={"margin_flag": True, "leverage_flag": True}),
            _action(metadata={"entry_timing_style": "left_side"}),
            _action(metadata={}),
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.margin_mention_count == 2
        assert observed.leverage_mention_count == 1
        assert observed.left_side_count == 1
        assert observed.right_side_count == 0

    def test_entry_style_majority_vote(self):
        # 5 left, 1 right -> 83% left >= 60% with n=6 >= 5
        actions = (
            [_action(metadata={"entry_timing_style": "left_side"}) for _ in range(5)]
            + [_action(metadata={"entry_timing_style": "right_side"})]
        )
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.entry_style_sample_size == 6
        assert observed.entry_style_observed == "left_side"

    def test_restated_standing_view_votes_once_and_cannot_stuff_the_ballot(self):
        """A weekly template restating ONE view must not outvote real calls.

        Regression for the 2026-07-14 finding: trader_ji's template restated a
        single AAPL view ~19x, and per-action voting let it dominate a ~24-vote
        denominator — manufacturing a 自述右侧 vs 实测左侧 contradiction that was
        an artifact of his template, not his trading. Per-episode voting makes the
        restated view worth exactly one vote, so the real calls decide the verdict.
        """
        restated_one_view = [
            _action(metadata={"entry_timing_style": "left_side"}, ticker="AAPL")
            for _ in range(19)
        ]
        genuine_calls = [
            _action(metadata={"entry_timing_style": "right_side"}, ticker=t)
            for t in ("NVDA", "0700.HK", "600519.SH", "9992.HK", "GOOGL")
        ]
        observed = compute_observed_style(restated_one_view + genuine_calls)
        assert observed is not None
        # 19 restatements collapse to 1 vote; 5 distinct calls keep 5
        assert observed.left_side_count == 1
        assert observed.right_side_count == 5
        assert observed.entry_style_sample_size == 6
        # verdict follows the real calls, not the template
        assert observed.entry_style_observed == "right_side"

    def test_watch_tier_mentions_are_not_entry_evidence(self):
        """A view he never entered has no entry to time."""
        actions = [
            _action(
                ActionType.WATCH,
                metadata={"entry_timing_style": "left_side", "tier": "opinion"},
            )
            for _ in range(6)
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.left_side_count == 0
        assert observed.entry_style_sample_size == 0
        assert observed.entry_style_observed == "unknown"

    def test_reduce_is_an_exit_not_an_entry(self):
        observed = compute_observed_style(
            [_action(ActionType.REDUCE, metadata={"entry_timing_style": "right_side"})]
        )
        assert observed is not None
        assert observed.right_side_count == 0

    def test_real_entries_still_count(self):
        actions = [
            _action(ActionType.LONG, metadata={"entry_timing_style": "right_side"}),
            _action(ActionType.ADD, metadata={"entry_timing_style": "right_side"}),
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.right_side_count == 2

    def test_trader_ji_shape_refuses_to_judge_instead_of_faking_a_conflict(self):
        """Regression for the 2026-07-15 false 言行不一 verdict.

        trader_ji's live evidence was 6 watch-tier "left_side" mentions plus one
        reduce tagged "right_side" — zero real entries. The old per-action count
        read that as entry_style_observed="left_side" and the UI rendered a red
        ⚠冲突 against his declared right_side. With no entry evidence the honest
        answer is "unknown", which the card renders as 数据不足.
        """
        actions = [
            _action(
                ActionType.WATCH,
                metadata={"entry_timing_style": "left_side", "tier": "opinion"},
            )
            for _ in range(6)
        ] + [
            _action(ActionType.REDUCE, metadata={"entry_timing_style": "right_side"})
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.entry_style_observed == "unknown"
        assert (observed.left_side_count, observed.right_side_count) == (0, 0)

    def test_entry_style_mixed_when_no_majority(self):
        # 3 left, 3 right -> 50%/50%, both below 60% -> mixed
        actions = (
            [_action(metadata={"entry_timing_style": "left_side"}) for _ in range(3)]
            + [_action(metadata={"entry_timing_style": "right_side"}) for _ in range(3)]
        )
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.entry_style_observed == "mixed"

    def test_entry_style_unknown_below_min_sample(self):
        actions = [_action(metadata={"entry_timing_style": "left_side"}) for _ in range(4)]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.entry_style_observed == "unknown"
        assert observed.entry_style_sample_size == 4

    def test_low_sample_threshold(self):
        below = compute_observed_style([_action() for _ in range(4)])
        at = compute_observed_style([_action() for _ in range(5)])
        assert below is not None and below.low_sample is True
        assert at is not None and at.low_sample is False


# =============================================================================
# Full profile
# =============================================================================

class TestBuildStyleProfile:
    def test_double_none_profile_for_unknown_creator(self, tmp_path):
        class EmptyRepo:
            def load_all_actions(self):
                return []

        profile = build_style_profile(
            "ghost", repository=EmptyRepo(), root=tmp_path
        )
        assert profile.creator_id == "ghost"
        assert profile.declared is None
        assert profile.observed is None

    def test_profile_filters_actions_by_creator(self, tmp_path):
        _write_creator_yaml(tmp_path, "k1", {
            "creator_id": "k1",
            "display_name": "老K",
            "trading_style": {"does_short": False},
        })

        class MixedRepo:
            def load_all_actions(self):
                return [
                    _action(ActionType.LONG, creator_id="k1"),
                    _action(ActionType.SHORT, creator_id="k1"),
                    _action(ActionType.SHORT, creator_id="someone-else"),
                ]

        profile = build_style_profile("k1", repository=MixedRepo(), root=tmp_path)
        assert profile.display_name == "老K"
        assert profile.declared is not None
        assert profile.declared.does_short is False
        assert profile.observed is not None
        assert profile.observed.sample_size == 2
        assert profile.observed.short_side_count == 1

    def test_profile_serializes_to_json(self, tmp_path):
        class EmptyRepo:
            def load_all_actions(self):
                return []

        profile = build_style_profile("ghost", repository=EmptyRepo(), root=tmp_path)
        payload = profile.model_dump(mode="json")
        assert payload["creator_id"] == "ghost"
        assert payload["declared"] is None
        assert payload["observed"] is None


class TestReviewHardening:
    """2026-07-16 adversarial-review fixes: mention stats are per-action
    (existence evidence must not be masked by anchor-only counting), entry
    votes are per-episode via the episode's first REAL entry."""

    def test_margin_flag_on_a_restatement_still_counts(self):
        # same ticker = one episode; the flag rides on the 3rd restatement.
        actions = [
            _action(ticker="AAPL"),
            _action(ticker="AAPL"),
            _action(ticker="AAPL", metadata={"margin_flag": True}),
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.margin_mention_count == 1  # anchor-only counting gave 0

    def test_short_on_a_later_action_in_episode_still_counts(self):
        actions = [
            _action(ActionType.WATCH, ticker="AAPL"),
            _action(ActionType.SHORT, ticker="AAPL"),
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.short_side_count == 1

    def test_episode_entered_later_still_casts_its_entry_vote(self):
        # anchor is a watch (no entry to time); the REAL entry comes later in
        # the same episode and must cast the episode's one vote.
        actions = [
            _action(
                ActionType.WATCH, ticker="AAPL",
                metadata={"tier": "opinion", "entry_timing_style": "left_side"},
            ),
            _action(
                ActionType.LONG, ticker="AAPL",
                metadata={"entry_timing_style": "right_side"},
            ),
        ]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert (observed.left_side_count, observed.right_side_count) == (0, 1)

    def test_sample_size_is_attributed_action_count_per_schema(self):
        actions = [_action(ticker="AAPL") for _ in range(3)]
        observed = compute_observed_style(actions)
        assert observed is not None
        assert observed.sample_size == 3  # schema: 参与统计的 action 总数
