"""语料构成聚合（RecordCorpusAggregates）测试。

钉住四条口径，全部是「图表合计必须与卡墙对账」的前提：
  1. 只有计数，没有比率字段（schema 层面防「夹带比率绕过效力门」）；
  2. superseded / 空 creator / 跨口径行不进任何计数；
  3. 已结算判定与 scorecard.is_scoreable 同口径（return_pct 非空）；
  4. 月度桶按 canonical signal clock 归月，升序输出。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from finer.credibility.aggregates import build_corpus_aggregates
from finer.schemas.credibility import RecordCorpusAggregates
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


def _timing(market: str, ts: datetime) -> ExecutionTiming:
    return ExecutionTiming(
        intent_published_at=ts,
        action_decision_at=ts,
        action_executable_at=ts,
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
    market: str = "US",
    ts: datetime = datetime(2026, 3, 2, 9, 30),
    return_pct: Optional[float] = 0.10,
    exit_reason: ExitReason = ExitReason.TARGET_REACHED,
    direction: TradeDirection = TradeDirection.BULLISH,
    superseded: bool = False,
    signal_class: Optional[str] = "broker_recommendation",
    time_horizon: Optional[str] = "long_term",
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
        timestamp=ts,
        source=SourceInfo(content_id="c-1", evidence_text="t", creator_id=creator),
        target=TargetInfo(ticker=ticker, market=market),
        direction=direction,
        signal_class=signal_class,
        time_horizon=time_horizon,
        execution_timing=_timing(market, ts),
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


def test_counts_and_monthly_buckets() -> None:
    actions = [
        _action("a1", ts=datetime(2025, 12, 5, 9, 30)),                      # settled, 2025-12
        _action("a2", ts=datetime(2025, 12, 9, 9, 30), return_pct=None),     # pending, 2025-12
        _action("a3", ts=datetime(2026, 3, 2, 9, 30), creator="花旗",
                ticker="0700.HK", market="HK", direction=TradeDirection.BEARISH,
                exit_reason=ExitReason.STOP_LOSS, return_pct=-0.08),         # settled, 2026-03
    ]
    agg = build_corpus_aggregates(actions, signal_class="broker_recommendation")

    assert agg.n_total == 3
    assert agg.n_settled == 2
    assert agg.n_creators == 2
    assert [b.month for b in agg.monthly] == ["2025-12", "2026-03"]
    assert agg.monthly[0].n_total == 2 and agg.monthly[0].n_settled == 1
    assert agg.monthly[1].n_total == 1 and agg.monthly[1].n_settled == 1
    assert agg.directions == {"bullish": 2, "bearish": 1}
    # 市场按 ticker 推导（AAPL→US，0700.HK→HK），不信存量标记
    assert agg.markets == {"US": 2, "HK": 1}
    assert agg.exit_reasons == {"target_reached": 1, "stop_loss": 1}
    assert agg.time_horizons == {"long_term": 3}
    assert agg.first_action_at is not None and agg.first_action_at.startswith("2025-12")
    assert agg.last_action_at is not None and agg.last_action_at.startswith("2026-03")
    assert agg.notes  # 口径声明必须随响应走


def test_exclusions_match_record_card() -> None:
    """superseded / 空 creator / 跨口径行不进计数——否则图表与卡墙对不上账。"""
    actions = [
        _action("keep"),
        _action("dup", superseded=True),
        _action("orphan", creator=""),
        _action("sector", signal_class="broker_sector_view"),
    ]
    agg = build_corpus_aggregates(actions, signal_class="broker_recommendation")
    assert agg.n_total == 1
    assert agg.n_settled == 1
    assert agg.n_creators == 1

    sector = build_corpus_aggregates(actions, signal_class="broker_sector_view")
    assert sector.n_total == 1  # 口径隔离：各算各的，不相加


def test_schema_has_no_ratio_fields() -> None:
    """红线防护：本模型任何字段都不得是比率。

    新增比率字段必须改走 SampleSufficiency 通道；此测试挡住「顺手在
    aggregates 里加个 win_rate」这类最容易发生的绕门改动。
    """
    forbidden = {"rate", "ratio", "pct", "return", "win", "excess", "sharpe"}
    for name in RecordCorpusAggregates.model_fields:
        lowered = name.lower()
        assert not any(tok in lowered for tok in forbidden), (
            f"RecordCorpusAggregates.{name} 疑似比率字段——计数聚合不得携带比率，"
            "请改走 SampleSufficiency 通道"
        )


def test_empty_input() -> None:
    agg = build_corpus_aggregates([], signal_class="broker_recommendation")
    assert agg.n_total == 0
    assert agg.monthly == []
    assert agg.first_action_at is None
