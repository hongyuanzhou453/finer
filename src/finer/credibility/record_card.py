"""CRD-1 信源历史记录卡 —— scorecard 聚合的对外序列化边界。

不重算任何统计：聚合复用 ``backtest/scorecard.py``（含它已接入的 CRD-2
效力门），本模块只负责把 ``GroupStats`` 转成可进 API / 投影表的 pydantic
模型，并补上活动窗口（``first/last_action_at``——诚实暴露语料只有 ~10 个月，
不伪造长历史）。

口径约束（定位转向后）：
- 记录卡**不排序**。返回顺序 = 已结算样本量降序（UI-1 拍板的默认序），
  但这只是稳定输出序，不是排名——排名语义被 CRD-2 的预测性主张门否定。
- 每张卡必带 ``sufficiency``；缺门的卡不允许构造（schema 层强制）。
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from finer.backtest.scorecard import build_scorecard
from finer.credibility.significance import get_significance_gate
from finer.schemas.credibility import CreatorRecordCard
from finer.schemas.trade_action import TradeAction
from finer.timeline.stance_snapshot import signal_clock_of


def build_record_cards(
    actions: Iterable[TradeAction],
    *,
    signal_class: Optional[str] = None,
) -> List[CreatorRecordCard]:
    """把 F5 action 汇总成每信源一张历史记录卡。

    Args:
        actions: 全部候选 action（含未结算——覆盖率需要分母）。
        signal_class: 记录口径。R6：券商与 KOL 不得混在同一批卡里比较。
    """
    all_actions = list(actions)
    card = build_scorecard(all_actions, signal_class=signal_class)

    # 活动窗口 + 全量计数（口径与 build_scorecard 一致：排除 superseded）
    window: dict = {}
    totals: dict = {}
    for action in all_actions:
        if signal_class is not None and action.signal_class != signal_class:
            continue
        if (action.metadata or {}).get("superseded_by"):
            continue
        creator = (action.source.creator_id or "").strip()
        if not creator:
            continue
        totals[creator] = totals.get(creator, 0) + 1
        try:
            stamp = signal_clock_of(action)
        except Exception:  # noqa: BLE001 - 时钟缺失不应挡住记录卡
            continue
        lo, hi = window.get(creator, (stamp, stamp))
        window[creator] = (min(lo, stamp), max(hi, stamp))

    cards: List[CreatorRecordCard] = []
    for stats in card.by_creator:
        if stats.sufficiency is None:
            # build_scorecard 恒定挂门；这里防御性拒绝而非补造
            raise ValueError(f"GroupStats({stats.key}) 缺 sufficiency——效力门未生效")
        lo, hi = window.get(stats.key, (None, None))
        cards.append(CreatorRecordCard(
            creator_id=stats.key,
            signal_class=signal_class,
            n_total=stats.total_n if stats.total_n is not None else stats.n,
            n_settled=stats.n,
            wins=stats.wins,
            mean_return=stats.mean_return if stats.n else None,
            median_return=stats.median_return if stats.n else None,
            expected_win_rate=stats.expected_win_rate,
            market_mix=dict(stats.market_mix),
            first_action_at=lo,
            last_action_at=hi,
            sufficiency=stats.sufficiency,
        ))

    # 全未结算的信源不产生 GroupStats，但记录卡必须让它以「只显计数」出现——
    # 消失就是幸存者偏差（只展示能结算的，恰是 CRD-2 覆盖率门要防的事）。
    covered = {c.creator_id for c in cards}
    gate = get_significance_gate()
    metric = (
        "broker_excess_win_rate"
        if signal_class == "broker_recommendation"
        else None
    )
    for creator, total in totals.items():
        if creator in covered:
            continue
        lo, hi = window.get(creator, (None, None))
        cards.append(CreatorRecordCard(
            creator_id=creator,
            signal_class=signal_class,
            n_total=total,
            n_settled=0,
            wins=0,
            market_mix={},
            first_action_at=lo,
            last_action_at=hi,
            sufficiency=gate.assess(
                successes=0, settled_n=0, total_n=total, metric=metric
            ),
        ))

    cards.sort(key=lambda c: -c.n_settled)   # 稳定输出序（UI-1 默认序），非排名
    return cards
