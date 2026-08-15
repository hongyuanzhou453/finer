"""语料构成聚合（RecordCorpusAggregates 的唯一构造点）。

为 UI 图表提供**纯计数**聚合：月度活动、方向、市场、离场原因、期限档。
计数不是比率，不受 CRD-2 效力门约束；本模块因此刻意不 import
significance——如果未来要在这里算任何比率，必须改走 ``SampleSufficiency``
通道并让 schema 强制携带，不得在 dict 里夹带。

口径与 ``credibility/record_card.py`` 逐条对齐（superseded 排除、空
creator 排除、signal_class 隔离、signal_clock_of 时钟），保证图表合计
能与 /discover 卡墙逐位对账。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from finer.backtest.scorecard import real_market_of
from finer.schemas.credibility import MonthlyActivityBucket, RecordCorpusAggregates
from finer.schemas.trade_action import TradeAction
from finer.timeline.stance_snapshot import signal_clock_of


def _is_settled(action: TradeAction) -> bool:
    """结算判定，与 scorecard.is_scoreable 的结算半边同口径。"""
    br = action.backtest_result
    return br is not None and br.return_pct is not None


def build_corpus_aggregates(
    actions: Iterable[TradeAction],
    *,
    signal_class: Optional[str] = None,
) -> RecordCorpusAggregates:
    """把 F5 action 汇总成单一口径的语料构成计数。

    Args:
        actions: 全部候选 action（含未结算——月度/方向等分布需要全量分母）。
        signal_class: 记录口径。R6：不同口径的计数不得相加。
    """
    n_total = 0
    n_settled = 0
    creators: set = set()
    monthly_total: Dict[str, int] = defaultdict(int)
    monthly_settled: Dict[str, int] = defaultdict(int)
    directions: Dict[str, int] = defaultdict(int)
    markets: Dict[str, int] = defaultdict(int)
    exit_reasons: Dict[str, int] = defaultdict(int)
    time_horizons: Dict[str, int] = defaultdict(int)
    first_at: Optional[str] = None
    last_at: Optional[str] = None

    for action in actions:
        if signal_class is not None and action.signal_class != signal_class:
            continue
        if (action.metadata or {}).get("superseded_by"):
            continue
        creator = (action.source.creator_id or "").strip()
        if not creator:
            # 与 record_card 同口径：孤儿行不进卡墙，也不进图表，
            # 否则图表合计 > 卡墙合计，对账即失败。
            continue

        n_total += 1
        creators.add(creator)
        settled = _is_settled(action)
        if settled:
            n_settled += 1

        # 时钟：canonical signal clock（与记录窗口同源）
        try:
            stamp = signal_clock_of(action)
        except Exception:  # noqa: BLE001 - 时钟缺失不挡计数，只缺月度归属
            stamp = None
        if stamp is not None:
            month = stamp[:7]
            monthly_total[month] += 1
            if settled:
                monthly_settled[month] += 1
            if first_at is None or stamp < first_at:
                first_at = stamp
            if last_at is None or stamp > last_at:
                last_at = stamp

        direction = getattr(action.direction, "value", action.direction)
        if direction:
            directions[str(direction)] += 1

        # 真实市场按 ticker 推导（存量有 870 条国际股误标 US——scorecard
        # 的 _market_of 文档记载的伪影；构成计数与胜率切片必须同口径）
        market = real_market_of(action)
        if market:
            markets[market] += 1

        horizon = action.time_horizon
        if horizon:
            time_horizons[str(horizon)] += 1

        if settled and action.backtest_result is not None:
            reason = action.backtest_result.exit_reason
            reason_v = getattr(reason, "value", reason)
            if reason_v:
                exit_reasons[str(reason_v)] += 1

    monthly: List[MonthlyActivityBucket] = [
        MonthlyActivityBucket(
            month=m, n_total=monthly_total[m], n_settled=monthly_settled.get(m, 0)
        )
        for m in sorted(monthly_total)
    ]

    return RecordCorpusAggregates(
        signal_class=signal_class,
        n_total=n_total,
        n_settled=n_settled,
        n_creators=len(creators),
        monthly=monthly,
        directions=dict(sorted(directions.items(), key=lambda kv: -kv[1])),
        markets=dict(sorted(markets.items(), key=lambda kv: -kv[1])),
        exit_reasons=dict(sorted(exit_reasons.items(), key=lambda kv: -kv[1])),
        time_horizons=dict(sorted(time_horizons.items(), key=lambda kv: -kv[1])),
        first_action_at=first_at,
        last_action_at=last_at,
        notes=[
            "本视图只有计数，没有任何比率；计数不构成对信源的评价或预测。",
            "月度形状主要反映语料入库节奏（单月批量导入会形成峰值），不反映信源行为节奏。",
            "口径与记录卡一致：排除重复件与无信源归属的行；不同口径的计数不可相加。",
        ],
    )
