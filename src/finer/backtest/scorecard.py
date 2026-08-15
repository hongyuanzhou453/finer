"""F8 记分卡聚合 — 把已结算 TradeAction 汇总成 creator / market 维度的可审计报表.

为什么在 backtest/ 而不是新建模块：记分卡消费的是 F8 结算产物
（``BacktestResult``），与 ``per_action`` / ``settle`` 同层同源。路线图里的
``credibility/``（CRD-1，信誉打分）与投影表（PROJ-1）是更上层的产品化概念，
本模块不预占其命名，只提供它们将来要用的确定性聚合底座。

**度量口径的核心告诫（2026-07-25 归因拆解结论）**：

胜率**不能**跨波动率不同的市场直接比较。退出规则是非对称的
（−20% 止损 / +40% 止盈），止损距离只有止盈的一半，所以低波动标的
触发止损的次数天然更少 → 在**均值收益完全相同**的情况下也会得到更高胜率。
实证：非亚洲国际股均值 +0.22% vs 美股 +0.27%（几乎相同），胜率却高 8.8pp。

因此本模块**始终并列输出 win_rate 与 mean_return**，并额外给出
``expected_win_rate``（按该 creator 的市场构成、用各市场语料基准胜率算出的
纯暴露预期）与 ``excess_win_rate``（实际 − 预期，即剥离市场暴露后的超额）。
消费方不得只取 win_rate 排名。

详见 ``docs/specs/2026-07-25-intl-winrate-decomposition.md``。
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from finer.credibility.significance import get_significance_gate
from finer.enrichment.ticker_normalization import normalize_broker_ticker
from finer.schemas.significance import SampleSufficiency
from finer.schemas.trade_action import TradeAction

__all__ = [
    "GroupStats",
    "Scorecard",
    "build_scorecard",
    "is_scoreable",
    "render_markdown",
]

#: 参与记分的最小样本量 —— 低于此值的分组只统计不排名（噪声压倒信号）。
#: 与 ``configs/significance.yaml`` 的 ``tiers.sufficient.min_settled`` 保持一致；
#: 该 YAML 是真相源，本常量只在门加载失败时兜底。
MIN_RANKED_N = 30

#: 计算 within-market 分项时，单个 (creator, market) 单元的最小样本量。
MIN_STRATUM_N = 5


# =============================================================================
# 统计单元
# =============================================================================


@dataclass
class GroupStats:
    """一个分组（creator 或 market）的记分卡指标。"""

    key: str
    n: int = 0
    wins: int = 0
    mean_return: float = 0.0
    median_return: float = 0.0
    stop_rate: float = 0.0
    target_rate: float = 0.0
    median_drawdown: Optional[float] = None
    #: 按本组市场构成 + 各市场语料基准胜率推出的纯暴露预期胜率
    expected_win_rate: Optional[float] = None
    #: 市场构成（market -> n），用于审计「这个分数里有多少是市场暴露」
    market_mix: Dict[str, int] = field(default_factory=dict)
    #: 该组内的全部 action 数（含未结算），供 CRD-2 算结算覆盖率
    total_n: Optional[int] = None
    #: CRD-2 统计效力门的判定。阈值真相源 = configs/significance.yaml
    sufficiency: Optional[SampleSufficiency] = None

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def excess_win_rate(self) -> Optional[float]:
        """实际胜率 − 市场暴露预期胜率（剥离市场构成后的超额）。"""
        if self.expected_win_rate is None:
            return None
        return self.win_rate - self.expected_win_rate

    @property
    def ranked(self) -> bool:
        """是否够格进排名。

        真相源是 CRD-2 效力门（``configs/significance.yaml``）——``MIN_RANKED_N``
        只在门不可用时兜底，两者的 ``sufficient`` 门槛保持一致。
        走门的额外收益：结算覆盖率过低时即使 n 够大也会被降档，
        避免「只有能结算的那部分」被当成全貌。
        """
        if self.sufficiency is not None:
            return self.sufficiency.tier == "sufficient"
        return self.n >= MIN_RANKED_N


@dataclass
class Scorecard:
    """一次记分卡快照。"""

    total_actions: int = 0
    settled_actions: int = 0
    excluded_superseded: int = 0
    by_creator: List[GroupStats] = field(default_factory=list)
    by_market: List[GroupStats] = field(default_factory=list)
    signal_class_filter: Optional[str] = None


# =============================================================================
# 取数
# =============================================================================


def is_scoreable(action: TradeAction) -> bool:
    """该 action 是否进入记分聚合。

    排除两类：尚未结算的（无 ``return_pct``），以及被去重标记为
    ``metadata.superseded_by`` 的重复件（同一份研报被重复导入时，
    计分两次会双记同一个判断）。
    """
    br = action.backtest_result
    if br is None or br.return_pct is None:
        return False
    if (action.metadata or {}).get("superseded_by"):
        return False
    return True


def _market_of(action: TradeAction) -> Optional[str]:
    """标的的**真实**市场，优先从 ticker 归一化推导。

    不能直接信 ``execution_timing.market`` / ``target.market``：存量里有 870 条
    国际股被 F3 早期的 ``infer_market`` 误标成 ``US``（该 bug 已于 2026-07-25 修复
    前向，但存量未回写）。若照搬存量标记，记分卡的市场维度会把日/台/韩股全部
    算进美股桶 —— 实测会把美股胜率从真实的 43.1% 抬到 47.8%，
    正好复现本模块 docstring 警告的那类伪影。

    ticker 无法归一化时（sector 代理、异常代码）才回落到存量标记。
    详见 ``docs/specs/2026-07-25-intl-calendar-impact-assessment.md``。
    """
    target = action.target
    if target is not None:
        symbol = target.ticker_normalized or target.ticker
        if symbol:
            normalized = normalize_broker_ticker(symbol)
            if normalized is not None and normalized.market:
                return normalized.market
    timing = action.execution_timing
    if timing is not None and timing.market:
        return timing.market
    return target.market if target is not None else None


#: 公开别名：CRD 消费层（credibility/aggregates、ratio_slices）复用同一套
#: 市场推导与分组统计，保证图表/切片与记分卡逐位对账。真相源仍是本模块。
def real_market_of(action: TradeAction) -> Optional[str]:
    """见 ``_market_of``——ticker 推导的真实市场（存量误标 US 的解毒剂）。"""
    return _market_of(action)


def stats_for_group(key: str, actions: "Sequence[TradeAction]") -> "GroupStats":
    """见 ``_stats_for``——一组已结算 action 的分组统计。"""
    return _stats_for(key, actions)


def _creator_of(action: TradeAction) -> str:
    src = action.source
    return (src.creator_id if src is not None else None) or "unknown"


def _stats_for(key: str, actions: Sequence[TradeAction]) -> GroupStats:
    returns = [a.backtest_result.return_pct for a in actions]  # type: ignore[union-attr]
    drawdowns = [
        a.backtest_result.max_drawdown_pct  # type: ignore[union-attr]
        for a in actions
        if a.backtest_result is not None and a.backtest_result.max_drawdown_pct is not None
    ]
    exits = Counter(
        a.backtest_result.exit_reason.value  # type: ignore[union-attr]
        for a in actions
        if a.backtest_result is not None
    )
    n = len(actions)
    return GroupStats(
        key=key,
        n=n,
        wins=sum(1 for r in returns if r > 0),
        mean_return=statistics.fmean(returns) if returns else 0.0,
        median_return=statistics.median(returns) if returns else 0.0,
        stop_rate=exits.get("stop_loss", 0) / n if n else 0.0,
        target_rate=exits.get("target_reached", 0) / n if n else 0.0,
        median_drawdown=statistics.median(drawdowns) if drawdowns else None,
        market_mix=dict(Counter(_market_of(a) or "unknown" for a in actions)),
    )


# =============================================================================
# 聚合
# =============================================================================


def build_scorecard(
    actions: Iterable[TradeAction],
    *,
    signal_class: Optional[str] = None,
) -> Scorecard:
    """把 TradeAction 汇总成记分卡。

    Args:
        actions: 待聚合的 action（通常来自 ``TradeActionRepository.load_all_actions()``）。
        signal_class: 只统计该 ``signal_class`` 的 action。R6 规定券商声明式建议
            （``broker_recommendation``）不得与 KOL 自述仓位（``kol_statement``）
            混在同一张榜里 —— 二者的 conviction 来源与语义不同。None 表示不过滤
            （仅用于全局体检，不可直接当排名用）。

    Returns:
        Scorecard，creator 与 market 两个维度均按 n 降序。
    """
    all_actions = list(actions)
    scoreable: List[TradeAction] = []
    superseded = 0
    for a in all_actions:
        if (a.metadata or {}).get("superseded_by"):
            br = a.backtest_result
            if br is not None and br.return_pct is not None:
                superseded += 1
            continue
        if not is_scoreable(a):
            continue
        if signal_class is not None and a.signal_class != signal_class:
            continue
        scoreable.append(a)

    # per-creator 全量计数（含未结算），CRD-2 用它算结算覆盖率。
    # 口径与 scoreable 一致地先过 signal_class 过滤，否则覆盖率会被别的
    # 信号类别稀释。
    creator_totals: Dict[str, int] = defaultdict(int)
    for a in all_actions:
        if (a.metadata or {}).get("superseded_by"):
            continue
        if signal_class is not None and a.signal_class != signal_class:
            continue
        creator_totals[_creator_of(a)] += 1

    by_market_actions: Dict[str, List[TradeAction]] = defaultdict(list)
    by_creator_actions: Dict[str, List[TradeAction]] = defaultdict(list)
    for a in scoreable:
        by_market_actions[_market_of(a) or "unknown"].append(a)
        by_creator_actions[_creator_of(a)].append(a)

    market_stats = [_stats_for(m, rs) for m, rs in by_market_actions.items()]
    market_baseline = {s.key: s.win_rate for s in market_stats}

    gate = get_significance_gate()
    creator_stats: List[GroupStats] = []
    for creator, rs in by_creator_actions.items():
        stats = _stats_for(creator, rs)
        stats.total_n = creator_totals.get(creator, stats.n)
        stats.sufficiency = gate.assess(
            successes=stats.wins,
            settled_n=stats.n,
            total_n=stats.total_n,
            metric="broker_excess_win_rate"
            if signal_class == "broker_recommendation"
            else None,
        )
        # 纯暴露预期：把本 creator 的每条 action 换成「该市场的语料平均水平」
        if stats.n:
            stats.expected_win_rate = sum(
                market_baseline.get(m, 0.0) * count
                for m, count in stats.market_mix.items()
            ) / stats.n
        creator_stats.append(stats)

    return Scorecard(
        total_actions=len(all_actions),
        settled_actions=len(scoreable),
        excluded_superseded=superseded,
        by_creator=sorted(creator_stats, key=lambda s: -s.n),
        by_market=sorted(market_stats, key=lambda s: -s.n),
        signal_class_filter=signal_class,
    )


# =============================================================================
# 渲染
# =============================================================================


def _pct(v: Optional[float], digits: int = 1, signed: bool = False) -> str:
    if v is None:
        return "—"
    fmt = f"{{:+.{digits}f}}%" if signed else f"{{:.{digits}f}}%"
    return fmt.format(v * 100)


def render_markdown(card: Scorecard) -> str:
    """渲染成可直接落盘审阅的 markdown。"""
    lines: List[str] = []
    scope = card.signal_class_filter or "全部（未按 signal_class 过滤）"
    lines.append("# 券商/KOL 记分卡")
    lines.append("")
    lines.append(f"- 口径：`{scope}`")
    lines.append(f"- action 总数 {card.total_actions}，参与记分 {card.settled_actions}"
                 f"，因 `superseded_by` 排除 {card.excluded_superseded}")
    lines.append(f"- 排名门槛：n ≥ {MIN_RANKED_N}")
    lines.append("")
    lines.append("> ⚠️ **胜率不可跨市场比较。** 退出规则非对称（−20% 止损 / +40% 止盈），")
    lines.append("> 低波动标的触发止损更少，在均值收益相同时也会得到更高胜率。")
    lines.append("> 请并列阅读 `均值收益` 与 `超额胜率`（已剥离市场暴露）。")
    lines.append("")
    verdict = next(
        (x.sufficiency.predictive_claim for x in card.by_creator
         if x.sufficiency is not None and x.sufficiency.predictive_claim is not None),
        None,
    )
    if verdict is not None and not verdict.permitted:
        lines.append("> 🚫 **本表描述已发生的事实，不构成对未来的预测。**")
        if verdict.summary:
            lines.append(f"> 跨期持续性检验结论：{verdict.summary}")
        if verdict.scope_note:
            lines.append(f"> 适用边界：{verdict.scope_note}")
        if verdict.evidence:
            lines.append(f"> 依据：`{verdict.evidence}`")
        lines.append("> 因此**不要据此排序选择信源**——见下表的 95% 区间，")
        lines.append("> 绝大多数信源之间的差距在统计上不可分辨。")
        lines.append("")

    lines.append("## 按信源")
    lines.append("")
    lines.append("| 信源 | n | 胜率 | 95% 区间 | 均值收益 | 中位收益 | 市场预期胜率 | 超额 | 主要市场 |")
    lines.append("|---|---:|---:|:---:|---:|---:|---:|---:|---|")
    for s in [x for x in card.by_creator if x.ranked]:
        mix = ", ".join(
            f"{m}:{c}" for m, c in sorted(s.market_mix.items(), key=lambda kv: -kv[1])[:3]
        )
        suf = s.sufficiency
        ci = (
            f"{_pct(suf.wilson_low)}–{_pct(suf.wilson_high)}"
            if suf is not None and suf.wilson_low is not None
            else "—"
        )
        lines.append(
            f"| {s.key} | {s.n} | {_pct(s.win_rate)} | {ci} | "
            f"{_pct(s.mean_return, 2, True)} | "
            f"{_pct(s.median_return, 2, True)} | {_pct(s.expected_win_rate)} | "
            f"{_pct(s.excess_win_rate, 1, True)} | {mix} |"
        )

    # CRD-2 的中间档：样本够看但不够排，单列而非与「样本不足」混为一谈
    provisional = [
        x for x in card.by_creator
        if not x.ranked and x.sufficiency is not None
        and x.sufficiency.display_policy == "show_with_warning"
    ]
    if provisional:
        lines.append("")
        lines.append("*样本偏少，数字仅供参考（未进排名）：*"
                     + "、".join(
                         f"{s.key}({s.n}，{_pct(s.win_rate)}"
                         f"，区间 {_pct(s.sufficiency.wilson_low)}"
                         f"–{_pct(s.sufficiency.wilson_high)})"
                         for s in provisional
                     ))

    unranked = [
        x for x in card.by_creator
        if not x.ranked and x not in provisional
    ]
    if unranked:
        lines.append("")
        lines.append(f"*样本不足未排名（n < {MIN_RANKED_N}）：*"
                     + "、".join(f"{s.key}({s.n})" for s in unranked))

    lines.append("")
    lines.append("## 按市场")
    lines.append("")
    lines.append("| 市场 | n | 胜率 | 均值收益 | 中位收益 | 止损率 | 止盈率 | 中位回撤 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    thin = False
    for s in card.by_market:
        mark = "" if s.ranked else " \\*"
        thin = thin or not s.ranked
        lines.append(
            f"| {s.key}{mark} | {s.n} | {_pct(s.win_rate)} | {_pct(s.mean_return, 2, True)} | "
            f"{_pct(s.median_return, 2, True)} | {_pct(s.stop_rate)} | "
            f"{_pct(s.target_rate)} | {_pct(s.median_drawdown, 2, True)} |"
        )
    if thin:
        lines.append("")
        lines.append(f"\\* n < {MIN_RANKED_N}，仅供参考，不构成市场结论"
                     f"（单条记录的胜率必然是 0% 或 100%）。")
    lines.append("")
    return "\n".join(lines)
