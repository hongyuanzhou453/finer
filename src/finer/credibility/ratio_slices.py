"""语料胜率切片（RatioSlice / CorpusRatioSlices 的唯一构造点）。

与 ``aggregates.py``（纯计数）相对：本模块产出**比率**，因此每一片都
强制过 CRD-2 效力门——这是两个模块分开的原因，不是代码洁癖：
aggregates 刻意不 import significance，本模块刻意不允许任何比率绕过它。

口径复用 ``backtest/scorecard.py`` 的原语（record_card 同款纪律
「不重算任何统计」）：

- 结算判定 = ``is_scoreable``（return_pct 非空 + 非 superseded）；
- 市场维度 = ``real_market_of``（ticker 推导的真实市场——存量有 870 条
  国际股误标 US，直接信存量标记会把美股胜率从 43.1% 抬到 47.8%）;
- 分组统计 = ``stats_for_group``（win = return_pct > 0）；
- 月度归置 = ``signal_clock_of``（与记录窗口/月度计数同时钟）。

预测性主张：切片一律 ``metric=None``——市场/月度切片从未做过跨期持续性
检验，``predictive_claim.permitted`` 必须为 False（未检验 ≠ 可预测）。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from finer.backtest.scorecard import is_scoreable, real_market_of, stats_for_group
from finer.credibility.significance import get_significance_gate
from finer.schemas.credibility import CorpusRatioSlices, RatioSlice
from finer.schemas.trade_action import TradeAction
from finer.timeline.stance_snapshot import signal_clock_of


def _month_of(action: TradeAction) -> Optional[str]:
    try:
        return signal_clock_of(action)[:7]
    except Exception:  # noqa: BLE001 - 时钟缺失的行不进月度切片
        return None


def _key_of(action: TradeAction, dimension: str) -> Optional[str]:
    if dimension == "market":
        return real_market_of(action) or "unknown"
    return _month_of(action)


def _slice_of(
    key: str,
    settled: List[TradeAction],
    n_total: int,
) -> RatioSlice:
    stats = stats_for_group(key, settled)
    sufficiency = get_significance_gate().assess(
        successes=stats.wins,
        settled_n=stats.n,
        total_n=n_total,
        metric=None,  # 切片指标未做持续性检验：permitted 必须为 False
    )
    return RatioSlice(
        key=key,
        n_total=n_total,
        n_settled=stats.n,
        wins=stats.wins,
        mean_return=stats.mean_return if stats.n else None,
        median_return=stats.median_return if stats.n else None,
        sufficiency=sufficiency,
    )


def build_ratio_slices(
    actions: Iterable[TradeAction],
    *,
    signal_class: Optional[str] = None,
    dimension: str = "market",
) -> CorpusRatioSlices:
    """把 F5 action 切成单一维度的胜率切片集。

    Args:
        actions: 全部候选 action（含未结算——每片的覆盖率需要全量分母）。
        signal_class: 记录口径。R6：不同口径的切片不可并排比较。
        dimension: "market" 或 "month"。
    """
    if dimension not in ("market", "month"):
        raise ValueError(f"unknown slice dimension: {dimension!r}")

    kept: List[TradeAction] = []
    for action in actions:
        if signal_class is not None and action.signal_class != signal_class:
            continue
        if (action.metadata or {}).get("superseded_by"):
            continue
        creator = (action.source.creator_id or "").strip()
        if not creator:
            # 与 record_card/aggregates 同口径：孤儿行不进任何统计
            continue
        kept.append(action)

    totals: Dict[str, int] = defaultdict(int)
    settled_by_key: Dict[str, List[TradeAction]] = defaultdict(list)
    settled_all: List[TradeAction] = []
    for action in kept:
        key = _key_of(action, dimension)
        if key is None:
            continue
        totals[key] += 1
        if is_scoreable(action):
            settled_by_key[key].append(action)
            settled_all.append(action)

    slices = [
        _slice_of(key, settled_by_key.get(key, []), totals[key])
        for key in totals
    ]
    if dimension == "month":
        slices.sort(key=lambda s: s.key)  # 时间轴升序
    else:
        # 已结算样本量降序 = 稳定输出序，不是排名（UI-1 拍板的同一条纪律）
        slices.sort(key=lambda s: (-s.n_settled, s.key))

    overall = _slice_of("__overall__", settled_all, sum(totals.values()))

    return CorpusRatioSlices(
        signal_class=signal_class,
        dimension=dimension,  # type: ignore[arg-type]
        overall=overall,
        slices=slices,
        notes=[
            "每片比率都附 95% 区间与效力门判定；样本不足的片只报计数，不渲染比率。",
            "切片描述已发生的结算事实，切片间差异不构成对未来的预测（跨期持续性未获支持）。",
            "市场归属按 ticker 推导的真实市场（存量的市场标记有误标，不可直接采信）。",
            "月度切片大多样本不足是预期行为——单月样本本来就少，这正是效力门存在的意义。",
        ],
    )
