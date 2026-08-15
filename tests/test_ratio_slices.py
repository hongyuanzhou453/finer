"""胜率切片（CorpusRatioSlices）测试。

钉住四条：
  1. 每片强制携带 SampleSufficiency——schema 层缺门即构造失败；
  2. 小样本片 display_policy == count_only（切片不因为「想画图」而放宽门）；
  3. 市场维度用 ticker 推导的真实市场，不信存量误标（870 条国际股标成 US
     的伪影不得再现）；
  4. predictive_claim.permitted 恒为 False——切片指标从未做过持续性检验。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest
from pydantic import ValidationError

from finer.credibility.ratio_slices import build_ratio_slices
from finer.schemas.credibility import RatioSlice
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
    stamped_market: str = "US",
    ts: datetime = datetime(2026, 3, 2, 9, 30),
    return_pct: Optional[float] = 0.10,
    superseded: bool = False,
    signal_class: Optional[str] = "broker_recommendation",
) -> TradeAction:
    br = None
    if return_pct is not None:
        br = BacktestResult(
            return_pct=return_pct,
            exit_reason=ExitReason.TARGET_REACHED,
            max_drawdown_pct=-0.05,
            backtest_period="2026-03-02 — 2026-04-01",
        )
    meta = {"superseded_by": "other-id"} if superseded else {}
    return TradeAction(
        trade_action_id=action_id,
        timestamp=ts,
        source=SourceInfo(content_id="c-1", evidence_text="t", creator_id=creator),
        target=TargetInfo(ticker=ticker, market=stamped_market),
        direction=TradeDirection.BULLISH,
        signal_class=signal_class,
        execution_timing=_timing(stamped_market, ts),
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


def test_every_slice_carries_sufficiency_and_is_gated() -> None:
    actions = [
        _action(f"a{i}", return_pct=0.05 if i % 2 == 0 else -0.05)
        for i in range(6)
    ] + [_action("p1", return_pct=None)]
    result = build_ratio_slices(actions, signal_class="broker_recommendation")

    assert result.dimension == "market"
    assert result.overall.sufficiency is not None
    # n_settled=6 < count_only 阈值 → 比率不得放行
    assert result.overall.sufficiency.display_policy == "count_only"
    for s in result.slices:
        assert s.sufficiency is not None
        assert s.sufficiency.display_policy == "count_only"
    # 计数照常在场
    us = next(s for s in result.slices if s.key == "US")
    assert us.n_total == 7
    assert us.n_settled == 6
    assert us.wins == 3


def test_sufficient_slice_passes_gate() -> None:
    actions = [
        _action(f"a{i}", return_pct=0.05 if i % 2 == 0 else -0.05)
        for i in range(40)
    ]
    result = build_ratio_slices(actions, signal_class="broker_recommendation")
    us = next(s for s in result.slices if s.key == "US")
    assert us.sufficiency.display_policy in ("show", "show_with_warning")
    assert us.sufficiency.point_estimate == pytest.approx(0.5)
    assert us.sufficiency.wilson_low is not None
    assert us.sufficiency.wilson_high is not None
    # 切片指标未做持续性检验：预测性主张必须关死
    claim = us.sufficiency.predictive_claim
    assert claim is None or claim.permitted is False


def test_market_derived_from_ticker_not_stamp() -> None:
    """0700.HK 被误标 US 的行必须归到 HK——伪影解毒剂在切片同样生效。"""
    actions = [
        _action("hk1", ticker="0700.HK", stamped_market="US"),
        _action("us1", ticker="AAPL", stamped_market="US"),
    ]
    result = build_ratio_slices(actions, signal_class="broker_recommendation")
    keys = {s.key for s in result.slices}
    assert "HK" in keys
    hk = next(s for s in result.slices if s.key == "HK")
    assert hk.n_total == 1


def test_month_dimension_ascending() -> None:
    actions = [
        _action("m1", ts=datetime(2026, 3, 2, 9, 30)),
        _action("m2", ts=datetime(2025, 12, 5, 9, 30)),
        _action("m3", ts=datetime(2025, 12, 9, 9, 30), return_pct=None),
    ]
    result = build_ratio_slices(
        actions, signal_class="broker_recommendation", dimension="month"
    )
    assert [s.key for s in result.slices] == ["2025-12", "2026-03"]
    dec = result.slices[0]
    assert dec.n_total == 2 and dec.n_settled == 1


def test_exclusions_and_scope_isolation() -> None:
    actions = [
        _action("keep"),
        _action("dup", superseded=True),
        _action("orphan", creator=""),
        _action("sector", signal_class="broker_sector_view"),
    ]
    result = build_ratio_slices(actions, signal_class="broker_recommendation")
    assert result.overall.n_total == 1


def test_slice_without_sufficiency_cannot_exist() -> None:
    """schema 层强制：缺门的切片构造直接失败。"""
    with pytest.raises(ValidationError):
        RatioSlice(key="US", n_total=1, n_settled=1, wins=1)  # type: ignore[call-arg]


def test_unknown_dimension_rejected() -> None:
    with pytest.raises(ValueError):
        build_ratio_slices([], signal_class=None, dimension="creator")
