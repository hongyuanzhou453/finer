"""CRD-3 个股共识 —— 「这只票，谁说过什么」的等权聚合。

输入是 F3 bri intent（dict），因为立场语义（direction / rating / target_price /
report_date）在 F3 最完整；F5 action 是它的执行投影。

口径（每条都写进 ``notes``，UI 逐条展示）：
- **每源只计最新一篇**。同券商对同标的的多篇报告是立场的时间序列，
  把每篇都算一票会让高频覆盖的券商霸占共识（重述膨胀，同 stance_episodes
  教训）。历史篇数记在 ``n_reports``。
- **等权、仅方向**。conviction 是编造值，不用它加权（红线 §8-8）。
- **目标价只聚合同币种**，且 ``.L`` 标的显式排除：2026-08-03 数据质量审计
  实测 .L 的 target_price 镑/便士混存（BP 5.25=镑、TATE 399=便士，币种
  一律标 GBP），聚合会产生 100 倍错——排除并计数，比错误的中位数诚实。
- 共识描述**谁说了什么**，不判断谁说得对——共识方向是否有预测力是
  EXT-2 前置门待检验的假设（configs/significance.yaml: consensus_direction）。
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Dict, Iterable, List, Optional

from finer.enrichment.ticker_normalization import normalize_broker_ticker
from finer.schemas.credibility import (
    ConsensusSourceRow,
    TargetPriceSummary,
    TickerConsensusView,
)

_DIRECTIONAL = ("bullish", "bearish")

#: 单位可疑的市场后缀（镑/便士混存已实测；先只收录有实证的）。
_UNIT_AMBIGUOUS_SUFFIXES = (".L",)

_METHOD_NOTES = [
    "共识为等权聚合，每个信源只计其最新一篇报告的立场；不按 conviction 加权。",
    "本视图描述已发生的声明记录，不构成对未来的预测；"
    "共识方向的预测力尚未检验（见 configs/significance.yaml）。",
]


def _canonical(symbol: str) -> Optional[str]:
    parsed = normalize_broker_ticker(symbol or "")
    return parsed.symbol if parsed is not None and parsed.symbol else None


def build_ticker_consensus(
    intents: Iterable[dict],
    ticker: str,
) -> Optional[TickerConsensusView]:
    """聚合一只标的的共识记录；该标的无任何立场时返回 None。

    Args:
        intents: F3 bri intent dict 序列。
        ticker: 目标符号（任意方言写法，内部归一化后匹配）。
    """
    canonical = _canonical(ticker)
    if canonical is None:
        return None

    by_source: Dict[str, List[dict]] = {}
    names: List[str] = []
    for intent in intents:
        if _canonical(intent.get("target_symbol") or "") != canonical:
            continue
        creator = (intent.get("creator_id") or "").strip()
        if not creator:
            continue
        by_source.setdefault(creator, []).append(intent)
        name = (intent.get("target_name") or "").strip()
        if name and name != intent.get("target_symbol") and name not in names:
            names.append(name)

    if not by_source:
        return None

    rows: List[ConsensusSourceRow] = []
    tp_by_currency: Dict[str, List[float]] = {}
    excluded_unit = 0
    excluded_currency = 0
    unit_ambiguous = canonical.endswith(_UNIT_AMBIGUOUS_SUFFIXES)

    for creator, items in by_source.items():
        # 最新一篇为准；report_date 缺失的排最早（不让无日期的抢最新位）
        items.sort(key=lambda i: (i.get("metadata") or {}).get("report_date") or "")
        latest = items[-1]
        md = latest.get("metadata") or {}
        tp = latest.get("target_price") or {}
        rows.append(ConsensusSourceRow(
            creator_id=creator,
            direction=latest.get("direction") or "mixed",
            rating=md.get("rating_current"),
            target_price_value=tp.get("value"),
            target_price_currency=tp.get("currency"),
            report_date=md.get("report_date"),
            intent_id=latest.get("intent_id") or "",
            n_reports=len(items),
        ))
        value = tp.get("value")
        if value:
            if unit_ambiguous:
                excluded_unit += 1
            else:
                tp_by_currency.setdefault(
                    (tp.get("currency") or "?").upper(), []
                ).append(value)

    direction_counts = Counter(r.direction for r in rows)
    directional = [r for r in rows if r.direction in _DIRECTIONAL]
    agreement = (
        max(
            sum(1 for r in directional if r.direction == d)
            for d in _DIRECTIONAL
        ) / len(directional)
        if directional
        else None
    )

    notes = list(_METHOD_NOTES)
    summary: Optional[TargetPriceSummary] = None
    if tp_by_currency:
        # 只聚合占多数的那个币种；其余计入 mismatch
        major = max(tp_by_currency, key=lambda c: len(tp_by_currency[c]))
        values = tp_by_currency[major]
        excluded_currency = sum(
            len(v) for c, v in tp_by_currency.items() if c != major
        )
        summary = TargetPriceSummary(
            currency=major,
            n=len(values),
            min_value=min(values),
            median_value=statistics.median(values),
            max_value=max(values),
            excluded_unit_ambiguous=excluded_unit,
            excluded_currency_mismatch=excluded_currency,
        )
    elif excluded_unit:
        notes.append(
            f"目标价 {excluded_unit} 条因单位可疑（{canonical} 镑/便士混存风险）"
            "未聚合——排除比错误的中位数诚实。"
        )

    rows.sort(key=lambda r: r.report_date or "", reverse=True)
    return TickerConsensusView(
        ticker=canonical,
        target_names=names,
        n_sources=len(rows),
        direction_counts=dict(direction_counts),
        directional_agreement=agreement,
        latest_by_source=rows,
        target_prices=summary,
        notes=notes,
    )
