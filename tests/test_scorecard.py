"""F8 记分卡聚合测试。

重点钉住三条容易回归的口径：
  1. 市场维度必须用 ticker 推导的真实市场，不能信存量里被误标成 US 的
     execution_timing.market（否则日/台/韩股会被算进美股桶）；
  2. superseded_by 的重复件不进记分（同一判断不得双记）；
  3. expected/excess 胜率的定义 —— 纯市场暴露预期与剥离暴露后的超额。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest

from finer.backtest.scorecard import (
    MIN_RANKED_N,
    build_scorecard,
    is_scoreable,
    render_markdown,
)
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    BacktestResult,
    ExecutionTiming,
    ExitReason,
    MarketSession,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)

TS = datetime(2026, 3, 2, 9, 30)


def _timing(market: str) -> ExecutionTiming:
    return ExecutionTiming(
        intent_published_at=TS,
        action_decision_at=TS,
        action_executable_at=TS,
        market=market,
        timezone="America/New_York",
        market_session_at_publish=MarketSession.REGULAR,
        timing_policy_id="test",
    )


def _action(
    action_id: str,
    *,
    ticker: str = "AAPL",
    creator: str = "高盛",
    stamped_market: str = "US",
    return_pct: Optional[float] = 0.10,
    exit_reason: ExitReason = ExitReason.TARGET_REACHED,
    superseded: bool = False,
    signal_class: Optional[str] = "broker_recommendation",
) -> TradeAction:
    br = None
    if return_pct is not None:
        br = BacktestResult(
            return_pct=return_pct,
            exit_reason=exit_reason,
            max_drawdown_pct=-0.05,
            backtest_period="2026-03-02 — 2026-04-01",
        )
    meta = {"superseded_by": "other-id"} if superseded else {}
    return TradeAction(
        trade_action_id=action_id,
        timestamp=TS,
        source=SourceInfo(content_id="c-1", evidence_text="t", creator_id=creator),
        target=TargetInfo(ticker=ticker, market=stamped_market),
        direction=TradeDirection.BULLISH,
        signal_class=signal_class,
        execution_timing=_timing(stamped_market),
        backtest_result=br,
        metadata=meta,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                trigger_type=TriggerType.MANUAL,
                trigger_condition="t",
            )
        ],
    )


# ---------------------------------------------------------------------------
# 真实市场推导（本模块最重要的口径）
# ---------------------------------------------------------------------------


def test_market_derived_from_ticker_not_stale_stamp():
    """存量把 8309.T 标成 US；记分卡必须归到 JP。

    这正是 2026-07-25 评估里的 870 条错标：照搬存量标记会把国际股算进美股桶，
    实测把美股胜率从 43.7% 虚抬到 47.8%。
    """
    card = build_scorecard([
        _action("a1", ticker="8309.T", stamped_market="US", return_pct=0.30),
        _action("a2", ticker="AAPL", stamped_market="US", return_pct=-0.30),
    ])
    markets = {s.key: s for s in card.by_market}
    assert set(markets) == {"JP", "US"}
    assert markets["JP"].n == 1 and markets["JP"].wins == 1
    assert markets["US"].n == 1 and markets["US"].wins == 0


def test_unnormalizable_ticker_falls_back_to_stamp():
    """sector 代理等无法归一化的符号，回落到存量标记而不是丢弃。"""
    card = build_scorecard([
        _action("a1", ticker="ENERGY_STORAGE", stamped_market="CN"),
    ])
    assert [s.key for s in card.by_market] == ["CN"]


# ---------------------------------------------------------------------------
# 参与记分的过滤
# ---------------------------------------------------------------------------


def test_unsettled_actions_excluded():
    assert not is_scoreable(_action("a1", return_pct=None))
    card = build_scorecard([_action("a1", return_pct=None)])
    assert card.settled_actions == 0


def test_superseded_duplicates_excluded_and_counted():
    """去重标记的重复件不进记分，但要报出被排除的条数（可审计）。"""
    card = build_scorecard([
        _action("a1", return_pct=0.10),
        _action("a2", return_pct=0.10, superseded=True),
    ])
    assert card.settled_actions == 1
    assert card.excluded_superseded == 1


def test_signal_class_filter_separates_broker_from_kol():
    """R6：券商声明式建议与 KOL 自述仓位不得混榜。"""
    actions = [
        _action("a1", signal_class="broker_recommendation", creator="高盛"),
        _action("a2", signal_class="kol_statement", creator="trader_ji"),
    ]
    broker = build_scorecard(actions, signal_class="broker_recommendation")
    kol = build_scorecard(actions, signal_class="kol_statement")
    assert [s.key for s in broker.by_creator] == ["高盛"]
    assert [s.key for s in kol.by_creator] == ["trader_ji"]


# ---------------------------------------------------------------------------
# 指标语义
# ---------------------------------------------------------------------------


def test_expected_win_rate_is_pure_market_exposure():
    """预期胜率 = 按本 creator 市场构成加权的语料各市场基准胜率。

    构造：HK 语料基准 0%（1 负），JP 语料基准 100%（1 正）。
    某 creator 一条 HK 一条 JP，则其预期胜率应为 50%。
    """
    card = build_scorecard([
        _action("h1", ticker="0700.HK", stamped_market="HK", creator="A", return_pct=-0.3),
        _action("j1", ticker="8309.T", stamped_market="US", creator="B", return_pct=+0.3),
        _action("h2", ticker="0005.HK", stamped_market="HK", creator="C", return_pct=-0.3),
        _action("j2", ticker="6981.T", stamped_market="US", creator="C", return_pct=+0.3),
    ])
    by = {s.key: s for s in card.by_creator}
    # 语料基准：HK 0/2 = 0%，JP 2/2 = 100%
    assert by["C"].expected_win_rate == pytest.approx(0.5)
    assert by["C"].win_rate == pytest.approx(0.5)
    # 实际与暴露预期一致 → 无超额
    assert by["C"].excess_win_rate == pytest.approx(0.0)


def test_excess_win_rate_isolates_skill_from_exposure():
    """两个 creator 同样只做 HK：一个跑赢基准，超额为正。"""
    card = build_scorecard([
        _action("x1", ticker="0700.HK", stamped_market="HK", creator="loser", return_pct=-0.3),
        _action("x2", ticker="0005.HK", stamped_market="HK", creator="loser", return_pct=-0.3),
        _action("y1", ticker="0388.HK", stamped_market="HK", creator="winner", return_pct=+0.3),
        _action("y2", ticker="1810.HK", stamped_market="HK", creator="winner", return_pct=+0.3),
    ])
    by = {s.key: s for s in card.by_creator}
    assert by["winner"].expected_win_rate == pytest.approx(0.5)  # 语料 HK 基准 2/4
    assert by["winner"].excess_win_rate == pytest.approx(0.5)
    assert by["loser"].excess_win_rate == pytest.approx(-0.5)


def test_ranked_threshold():
    few = build_scorecard([_action(f"a{i}") for i in range(MIN_RANKED_N - 1)])
    assert not few.by_creator[0].ranked
    many = build_scorecard([_action(f"a{i}") for i in range(MIN_RANKED_N)])
    assert many.by_creator[0].ranked


def test_exit_rate_and_drawdown_stats():
    card = build_scorecard([
        _action("s1", return_pct=-0.21, exit_reason=ExitReason.STOP_LOSS),
        _action("t1", return_pct=+0.41, exit_reason=ExitReason.TARGET_REACHED),
    ])
    us = card.by_market[0]
    assert us.stop_rate == pytest.approx(0.5)
    assert us.target_rate == pytest.approx(0.5)
    assert us.median_drawdown == pytest.approx(-0.05)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def test_markdown_carries_the_volatility_caveat():
    """胜率不可跨市场比较的告诫必须随报表一起走，否则消费方会误读。"""
    md = render_markdown(build_scorecard([_action("a1")]))
    assert "胜率不可跨市场比较" in md
    assert "均值收益" in md


def test_markdown_marks_thin_markets():
    md = render_markdown(build_scorecard([_action("a1")]))
    assert "\\*" in md and f"n < {MIN_RANKED_N}" in md


def test_sector_views_are_isolated_from_stock_recommendations():
    """券商对板块的看法不得混进个股评级的记分卡。

    两者基准率不同——混算等于把「选股」和「押赛道」平均掉。
    2026-08-06 驱动 2026 段 T9 前发现：不隔离的话板块观点会占到
    券商记分卡的约 14%。
    """
    stock = [
        _action(f"s{i}", signal_class="broker_recommendation") for i in range(30)
    ]
    sector = [
        _action(f"v{i}", signal_class="broker_sector_view") for i in range(30)
    ]
    card = build_scorecard(stock + sector, signal_class="broker_recommendation")
    assert sum(s.n for s in card.by_creator) == 30
