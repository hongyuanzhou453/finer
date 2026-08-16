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
- **语料是静态档案，不是活水**。视图只存 ``latest_report_date`` 这个不变事实；
  「距今多少天 / 陈旧到什么程度」由 :func:`with_staleness` 在**读取时**算——
  物化时算好存起来，第二天就是错的。
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import date
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

#: 币种**子单位** → 独立 canonical 桶。ISO 4217 没有子单位代码，沿用市场惯用的
#: GBX（便士）；南非分照此办理。
#:
#: **绝不与主单位合并。** 此前分桶键是 ``(currency or "?").upper()``，
#: ``GBp``（便士）被抹成 ``GBP``（镑）——差 100 倍，正是 ``.L`` 排除规则要防的那个错。
#: 现役数据里 GBp 36 / p 6 / pence 1 条，且有 43 只**非 .L** 英股带这些标签
#: （不受后缀门保护）；目前每只只有一家信源覆盖才没炸，是潜伏而非不存在。
#: 匹配大小写敏感——``GBp`` 与 ``GBP`` 的区别**只在大小写上**。
_SUBUNIT_EXACT = {"GBp": "GBX", "p": "GBX", "ZAc": "ZAX"}
_SUBUNIT_WORDS = {"pence": "GBX", "penny": "GBX"}

#: 子单位 → 其主单位。两者同时出现在一只票上 = 单位不明，整只票不聚合。
_SUBUNIT_OF = {"GBX": "GBP", "ZAX": "ZAR"}

#: 自由文本币种写法 → ISO 代码（键为大写）。**逐条有实证**：每个写法都在
#: 现役 F3 数据里出现过，且已用标的的市场后缀交叉确认（如 ``M$``/``P$`` 出现在
#: ``.MX`` 上是墨西哥比索，不是马来西亚林吉特——只看符号会弄反）。
#:
#: 刻意**不**收录的：``¥``（JPY 与 CNY 都用）、``$``（多国）、``KWF``
#: （1 条，疑似 KWD 笔误——映射笔误等于编造）。宁可让它们各成一桶被排除。
_CURRENCY_ALIASES = {
    "W": "KRW", "WON": "KRW",          # .KS / .KQ
    "NT$": "TWD", "NTD": "TWD", "NT": "TWD",  # .TW
    "SFR": "CHF",                       # .S
    "NKR": "NOK", "SKR": "SEK", "DKR": "DKK",
    "RS": "INR",                        # .BO / .NS / .IN
    "RM": "MYR",                        # .KL
    "M$": "MXN", "P$": "MXN",           # .MX（比索，不是林吉特）
    "RP": "IDR",                        # .JK
    "BT": "THB",                        # .BK
    "ZL": "PLN",                        # .WA
    "R$": "BRL",
    "A$": "AUD", "AU$": "AUD",
    "C$": "CAD", "CA$": "CAD",
    "US$": "USD", "HK$": "HKD", "S$": "SGD",
    "RMB": "CNY",
}


def normalize_currency(label: Optional[str]) -> Optional[str]:
    """自由文本币种标签 → canonical 桶键。

    子单位先判且**大小写敏感**（``GBp`` 与 ``GBP`` 只差大小写），其余大写后查别名表；
    表里没有的原样大写返回——未知写法自成一桶，会被当作币种不符排除，
    这比猜错单位安全。
    """
    if not label:
        return None
    raw = label.strip()
    if not raw:
        return None
    if raw in _SUBUNIT_EXACT:
        return _SUBUNIT_EXACT[raw]
    if raw.lower() in _SUBUNIT_WORDS:
        return _SUBUNIT_WORDS[raw.lower()]
    upper = raw.upper()
    return _CURRENCY_ALIASES.get(upper, upper)

#: 陈旧度阈值（天）。取自研报的实际节奏：券商对同一标的通常按季度更新。
_STALENESS_BANDS = ((90, "current"), (180, "aging"), (365, "stale"))

_METHOD_NOTES = [
    "共识为等权聚合，每个信源只计其最新一篇报告的立场；不按 conviction 加权。",
    "本视图描述已发生的声明记录，不构成对未来的预测；"
    "共识方向的预测力尚未检验（见 configs/significance.yaml）。",
]


def _canonical(symbol: str) -> Optional[str]:
    parsed = normalize_broker_ticker(symbol or "")
    return parsed.symbol if parsed is not None and parsed.symbol else None


def group_by_canonical_ticker(intents: Iterable[dict]) -> Dict[str, List[dict]]:
    """按 canonical 符号分组（方言归一只做一遍——批量物化的性能前提）。"""
    groups: Dict[str, List[dict]] = {}
    for intent in intents:
        canonical = _canonical(intent.get("target_symbol") or "")
        if canonical is None:
            continue
        groups.setdefault(canonical, []).append(intent)
    return groups


def build_all_ticker_consensus(
    intents: Iterable[dict],
) -> Dict[str, TickerConsensusView]:
    """全部标的的共识视图（PROJ-1 物化入口）。"""
    views: Dict[str, TickerConsensusView] = {}
    for canonical, group in group_by_canonical_ticker(intents).items():
        view = _view_from_group(canonical, group)
        if view is not None:
            views[canonical] = view
    return views


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
    group = [
        i for i in intents
        if _canonical(i.get("target_symbol") or "") == canonical
    ]
    return _view_from_group(canonical, group)


def _view_from_group(
    canonical: str, group: List[dict]
) -> Optional[TickerConsensusView]:
    by_source: Dict[str, List[dict]] = {}
    names: List[str] = []
    for intent in group:
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
                    normalize_currency(tp.get("currency")) or "?", []
                ).append(value)

    # 主单位与其子单位同时出现（镑 + 便士）= 这只票的单位不明，整只不聚合。
    # 后缀门（.L）只认伦敦后缀，抓不到裸码英股与 .AS 上的英股 ADR——
    # 而标签本身已经把矛盾写出来了，比后缀更直接的证据。
    if not unit_ambiguous:
        for sub, major in _SUBUNIT_OF.items():
            if sub in tp_by_currency and major in tp_by_currency:
                excluded_unit = sum(len(v) for v in tp_by_currency.values())
                tp_by_currency = {}
                unit_ambiguous = True
                break

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
        # 只聚合占多数的那个币种；其余计入 mismatch。
        # **平局不选。** 原实现用 `max()`，取的是 dict 插入序——同样的数据换个
        # 读取顺序就换一个中位数。改成按字母序只是把随机换成确定性，掷硬币还是
        # 掷硬币：一个取决于字母序的「共识」不是共识。19 只票是这种情形，
        # 多为双重上市（A/H、ADR/本地）。逐源报价行照常展示，信息不丢，
        # 只是不给一个假的聚合值——同 `.L` 的处理原则。
        top = max(len(v) for v in tp_by_currency.values())
        winners = sorted(c for c, v in tp_by_currency.items() if len(v) == top)
        if len(winners) > 1:
            notes.append(
                "目标价按币种分组后无多数派（"
                + "、".join(f"{c} {len(tp_by_currency[c])} 条" for c in winners)
                + "），不聚合——逐源报价见下表。"
            )
        else:
            major = winners[0]
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
    dates = [r.report_date for r in rows if r.report_date]
    return TickerConsensusView(
        ticker=canonical,
        latest_report_date=max(dates) if dates else None,
        target_names=names,
        n_sources=len(rows),
        direction_counts=dict(direction_counts),
        directional_agreement=agreement,
        latest_by_source=rows,
        target_prices=summary,
        notes=notes,
    )


def with_staleness(
    view: TickerConsensusView, *, today: Optional[date] = None
) -> TickerConsensusView:
    """按当天补上 ``as_of_days`` / ``staleness`` 并追加一条声明。

    **必须在读取时调用，不能在物化时固化**：距今天数每天都在变，存进投影
    第二天就是错的。``latest_report_date`` 才是可以物化的不变事实。

    这个标注不是装饰：实测中位标的的最新报告是 8 个月前、70% 的标的三个月
    以上无更新（2026-08-05）。不标截止日期，用户会把陈旧记录读成「当前共识」。
    """
    if not view.latest_report_date:
        return view
    try:
        latest = date.fromisoformat(view.latest_report_date)
    except ValueError:
        return view

    days = ((today or date.today()) - latest).days
    band = next((name for limit, name in _STALENESS_BANDS if days <= limit), "archival")
    label = {
        "current": "近期记录",
        "aging": "已有一段时间未更新",
        "stale": "记录较旧",
        "archival": "档案级记录",
    }[band]

    updated = view.model_copy(deep=True)
    updated.as_of_days = days
    updated.staleness = band
    updated.notes = list(view.notes) + [
        f"本页记录截至 {view.latest_report_date}（距今 {days} 天，{label}）；"
        "语料为静态档案，不代表此刻的市场共识。"
    ]
    return updated
