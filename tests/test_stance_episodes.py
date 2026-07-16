"""Tests for the F7 stance-episode projection (persistent-viewpoint identity).

Pins the behaviour that makes KOL accountability scoring stable:
  - a standing view restated across weeks is ONE call, scored from its FIRST
    statement (trader_ji's weekly template restated one AAPL view 8x, which
    inflated his settled record 8x before this projection existed);
  - a genuine flip opens a NEW call;
  - two sectors proxying to the SAME ETF stay distinct viewpoints (identity is
    reused from stance_key_of — never re-derived from (kol, ticker)).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    BacktestResult,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)
from finer.timeline.stance_episodes import build_stance_episodes, episodes_by_creator


def make_action(
    kol: str,
    ticker: str,
    direction: TradeDirection,
    ts: datetime,
    action_id: str,
    sector_symbol: str | None = None,
    return_pct: float | None = None,
) -> TradeAction:
    a = TradeAction(
        trade_action_id=action_id,
        timestamp=ts,
        source=SourceInfo(content_id=f"c-{action_id}", evidence_text="e", creator_id=kol),
        target=TargetInfo(ticker=ticker, market="CN", company_name=ticker),
        direction=direction,
        action_chain=[
            ActionStep(sequence=1, action_type=ActionType.LONG, trigger_type=TriggerType.MANUAL)
        ],
        backtest_result=BacktestResult(return_pct=return_pct) if return_pct is not None else None,
    )
    if sector_symbol:
        a.metadata = {
            "sector_proxy": {
                "sector_symbol": sector_symbol,
                "sector_name": sector_symbol,
                "proxy_symbol": ticker,
                "proxy_name": ticker,
                "rule": "test",
                "config_version": 1,
            }
        }
    return a


def _wk(n: int) -> datetime:
    """Weekly cadence: 2026-01-04 + n weeks."""
    return datetime(2026, 1, 4, 20, 0) + timedelta(weeks=n)


class TestStandingView:
    def test_restated_view_collapses_to_one_episode_scored_from_first(self):
        # the real shape: one AAPL bearish view restated 8 weeks running
        actions = [
            make_action("trader_ji", "AAPL", TradeDirection.BEARISH, _wk(i), f"a{i}",
                        return_pct=0.05)
            for i in range(8)
        ]
        eps = build_stance_episodes(actions)
        assert len(eps) == 1
        ep = eps[0]
        assert ep.restatement_count == 8
        assert ep.is_standing_view is True
        assert ep.direction == "bearish"
        # scored from the FIRST statement — a follower's real entry point
        assert ep.anchor.trade_action_id == "a0"
        assert ep.first_stated_at < ep.last_stated_at

    def test_single_statement_is_not_a_standing_view(self):
        eps = build_stance_episodes(
            [make_action("k", "AAPL", TradeDirection.BEARISH, _wk(0), "a0")]
        )
        assert len(eps) == 1
        assert eps[0].restatement_count == 1
        assert eps[0].is_standing_view is False


class TestFlipOpensNewCall:
    def test_direction_change_starts_a_new_episode(self):
        actions = [
            make_action("k", "AAPL", TradeDirection.BEARISH, _wk(0), "a0"),
            make_action("k", "AAPL", TradeDirection.BEARISH, _wk(1), "a1"),
            make_action("k", "AAPL", TradeDirection.BULLISH, _wk(2), "a2"),
            make_action("k", "AAPL", TradeDirection.BULLISH, _wk(3), "a3"),
        ]
        eps = sorted(build_stance_episodes(actions), key=lambda e: e.first_stated_at)
        assert len(eps) == 2
        assert eps[0].direction == "bearish" and eps[0].anchor.trade_action_id == "a0"
        assert eps[1].direction == "bullish" and eps[1].anchor.trade_action_id == "a2"

    def test_flip_back_is_a_third_call(self):
        actions = [
            make_action("k", "AAPL", TradeDirection.BEARISH, _wk(0), "a0"),
            make_action("k", "AAPL", TradeDirection.BULLISH, _wk(1), "a1"),
            make_action("k", "AAPL", TradeDirection.BEARISH, _wk(2), "a2"),
        ]
        assert len(build_stance_episodes(actions)) == 3


class TestIdentityReusesStanceKey:
    def test_two_sectors_sharing_one_proxy_etf_stay_distinct(self):
        # the collapse bug stance_key_of exists to prevent — must survive here
        actions = [
            make_action("k", "159819", TradeDirection.BEARISH, _wk(0), "a0",
                        sector_symbol="COMPUTE_POWER"),
            make_action("k", "159819", TradeDirection.BULLISH, _wk(1), "a1",
                        sector_symbol="AI_COMPUTING"),
        ]
        eps = build_stance_episodes(actions)
        assert len(eps) == 2, "two sectors on one proxy ETF must not merge"
        assert {e.stance_key for e in eps} == {
            "sector:COMPUTE_POWER", "sector:AI_COMPUTING",
        }
        # and neither is a flip of the other
        assert {e.direction for e in eps} == {"bearish", "bullish"}

    def test_different_kols_never_share_an_episode(self):
        actions = [
            make_action("k1", "AAPL", TradeDirection.BEARISH, _wk(0), "a0"),
            make_action("k2", "AAPL", TradeDirection.BEARISH, _wk(1), "a1"),
        ]
        eps = build_stance_episodes(actions)
        assert len(eps) == 2
        assert {e.creator_id for e in eps} == {"k1", "k2"}


class TestAttribution:
    def test_unattributed_and_tickerless_actions_are_skipped(self):
        actions = [
            make_action("unknown", "AAPL", TradeDirection.BEARISH, _wk(0), "a0"),
            make_action("", "AAPL", TradeDirection.BEARISH, _wk(1), "a1"),
        ]
        assert build_stance_episodes(actions) == []

    def test_episodes_by_creator_groups(self):
        actions = [
            make_action("k1", "AAPL", TradeDirection.BEARISH, _wk(0), "a0"),
            make_action("k1", "0700.HK", TradeDirection.BULLISH, _wk(0), "a1"),
            make_action("k2", "AAPL", TradeDirection.BEARISH, _wk(0), "a2"),
        ]
        by = episodes_by_creator(build_stance_episodes(actions))
        assert set(by) == {"k1", "k2"}
        assert len(by["k1"]) == 2 and len(by["k2"]) == 1


class TestChronology:
    def test_mixed_utc_offsets_sort_chronologically_not_lexically(self):
        """Real F5 slots mix +08:00 and -04:00/-05:00 clocks; raw ISO-string
        comparison is not chronological across offsets and can misorder a flip."""
        from datetime import timezone as _tz

        cn = _tz(timedelta(hours=8))
        us = _tz(timedelta(hours=-4))
        # CN evening post = 14:00 UTC; US morning post same day = 14:30 UTC.
        # Lexically "T10:30" < "T22:00" would misorder them; chronologically the
        # CN bearish comes FIRST and the US bullish flip is the newer episode.
        first = make_action(
            "k", "GOOGL", TradeDirection.BEARISH,
            datetime(2026, 3, 16, 22, 0, tzinfo=cn), "a-cn",
        )
        second = make_action(
            "k", "GOOGL", TradeDirection.BULLISH,
            datetime(2026, 3, 16, 10, 30, tzinfo=us), "a-us",
        )
        eps = build_stance_episodes([second, first])
        assert len(eps) == 2
        ordered = sorted(eps, key=lambda e: e.first_stated_at)
        # anchor of the FIRST episode must be the CN action (earlier in UTC)
        first_ep = [e for e in eps if e.anchor.trade_action_id == "a-cn"]
        assert first_ep and first_ep[0].direction == "bearish"
        latest_ep = [e for e in eps if e.anchor.trade_action_id == "a-us"]
        assert latest_ep and latest_ep[0].direction == "bullish"


class TestWindowedUniverse:
    def test_windowed_scope_does_not_reanchor_a_standing_view(self):
        """opinions._kol_settled_record(actions, universe): a windowed subset
        must not re-anchor a standing view to its first in-window restatement —
        episodes come from the full history and only anchors decide window
        membership."""
        from finer.api.routes.opinions import _kol_settled_record

        anchor = make_action(
            "k", "AAPL", TradeDirection.BEARISH, _wk(0), "a0", return_pct=-0.05
        )
        anchor.backtest_result.holding_days = 10
        restatements = []
        for i in range(1, 4):
            a = make_action(
                "k", "AAPL", TradeDirection.BEARISH, _wk(i), f"a{i}", return_pct=0.03
            )
            a.backtest_result.holding_days = 10
            restatements.append(a)
        universe = [anchor, *restatements]

        # full history: one call, scored from the anchor (a loss)
        full = _kol_settled_record(universe)
        assert full["k"] == (1, 0)

        # window containing only restatements: the standing view was NOT
        # initiated in this window — it must not resurface as a fresh win.
        windowed = _kol_settled_record(restatements, universe=universe)
        assert windowed["k"] == (0, 0)

        # window containing the anchor: counted once, from the true anchor.
        windowed_with_anchor = _kol_settled_record(
            [anchor, restatements[0]], universe=universe
        )
        assert windowed_with_anchor["k"] == (1, 0)
