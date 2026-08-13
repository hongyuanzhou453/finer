"""M1 评级—预测口径背离检测 —— 同一份研报内部「说」与「说」互相拉扯。

**这不是 CRD-4 言行不一。** `credibility/divergence.py` 比的是「说 vs 做」
（声明 vs 本人仓位变动），并明确写着券商结构上不可能触发它——券商只产零仓位
承诺的 `recommendation`。本模块比的是**同一份文档内两个声明是否自洽**：
券商维持/上调评级，同时下调盈利预测（或反之）。

**为什么这个事实在当前定位下成立**（定位转向 2026-08-02）：
它不需要任何预测性假设。不问「谁更准」，只问「这份研报自不自洽」——
研报白纸黑字写着「维持买入」+「下调 2026E EPS 8%」，两侧都能下钻原文。
这正是「让你查得清谁说过什么」的高阶形态。

**本模块的假阳性等于对券商的不实指控**，因此沿用 divergence.py 的保守纪律：

1. **只比明确方向。** intent `direction` 非 bullish/bearish 一律不参与——
   从「中性」推不出任何矛盾。
2. **只比核心盈利指标。** eps / net_profit / revenue。毛利率、EBITDA 等
   派生或分项指标下调不构成对整体判断的矛盾（例：毛利率降但营收放量）。
3. **只比明确调整。** estimate `action` 非 raised/cut 一律不参与
   （unchanged / new / unknown 都不是「调整」）。
4. **微调不算。** |change_pct| < MIN_CHANGE_PCT 视为噪声区间。
5. **无证据不报。** T6 抽取必须 `json_ok` 且 `evidence_ok`，且至少有一条
   命中的原文引文——不能下钻的指控不应存在。

**明确不判定**（写死并附理由，防止后续 agent「补全」成 bug）：

- **目标价上调 + 盈利预测下调 ≠ 背离**。估值倍数扩张是正当逻辑
  （盈利下修但给更高 P/E），不是自相矛盾。本模块根本不读 target_price。
- **跨报告不比**。十个月里先看多后看空是正常的改变主意；只看单份文档内部。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: 参与判定的核心盈利指标。刻意不含 gross_margin / ebitda / other——见模块纪律 2。
CORE_METRICS: frozenset[str] = frozenset({"eps", "net_profit", "revenue"})

#: 参与判定的调整方向。unchanged / new / unknown 都不是「调整」。
DIRECTED_ACTIONS: frozenset[str] = frozenset({"raised", "cut"})

#: 低于此幅度的调整视为噪声，不构成背离。单位：百分比绝对值。
MIN_CHANGE_PCT: float = 5.0

#: intent.direction 中参与判定的取值。
DIRECTED_STANCES: frozenset[str] = frozenset({"bullish", "bearish"})

#: 冲突矩阵：看多却下调 / 看空却上调。
_CONFLICT: Dict[str, str] = {"bullish": "cut", "bearish": "raised"}


@dataclass(frozen=True)
class ConflictingEstimate:
    """一条与评级方向相悖的盈利预测调整。"""

    metric: str
    metric_name_raw: Optional[str]
    period: Optional[str]
    action: str
    change_pct: Optional[float]
    value: Optional[float]
    unit: Optional[str]


@dataclass(frozen=True)
class RatingEstimateInconsistency:
    """一份研报内部的评级—预测口径背离。两侧均可下钻。"""

    report_id: int
    intent_id: str
    creator_id: str
    ticker: Optional[str]
    report_date: Optional[str]

    #: 「说」的一侧：评级方向
    rating_direction: str
    rating_current: Optional[str]
    rating_action: Optional[str]
    #: intent 的证据（F2 span），供 /audit 下钻
    intent_evidence_span_ids: Tuple[str, ...]

    #: 「也说」的一侧：与评级相悖的盈利预测调整
    conflicting_estimates: Tuple[ConflictingEstimate, ...]
    #: T6 抽取的原文引文（报告级证据，非逐条 estimate 级——T6 schema 如此）
    estimate_evidence_quotes: Tuple[str, ...]

    @property
    def has_both_sides(self) -> bool:
        """两侧都能下钻才允许对外展示（同 divergence.py 的纪律）。"""
        return bool(self.conflicting_estimates) and bool(self.estimate_evidence_quotes)

    @property
    def max_change_pct(self) -> float:
        """冲突中最大的调整幅度，供排序展示（非评分）。"""
        return max(
            (abs(e.change_pct) for e in self.conflicting_estimates
             if e.change_pct is not None),
            default=0.0,
        )


@dataclass
class InconsistencyReport:
    """检测结果 + 各道排除条件的命中计数（用于回答「为什么没报出来」）。"""

    events: List[RatingEstimateInconsistency] = field(default_factory=list)
    skips: Dict[str, int] = field(default_factory=dict)

    def bump(self, reason: str) -> None:
        self.skips[reason] = self.skips.get(reason, 0) + 1


def _as_float(value: Any) -> Optional[float]:
    """宽松取数：T6 的 change_pct 可能是 int / float / 数字字符串 / None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _collect_conflicts(
    estimates: Sequence[Any],
    want_action: str,
) -> Tuple[List[ConflictingEstimate], Dict[str, int]]:
    """挑出与评级方向相悖、且通过全部纪律门的 estimate。"""
    hits: List[ConflictingEstimate] = []
    skips: Dict[str, int] = {}

    def bump(k: str) -> None:
        skips[k] = skips.get(k, 0) + 1

    for est in estimates:
        if not isinstance(est, dict):
            bump("estimate_not_object")
            continue
        metric = est.get("metric")
        if metric not in CORE_METRICS:
            bump("metric_not_core")
            continue
        action = est.get("action")
        if action not in DIRECTED_ACTIONS:
            bump("action_not_directed")
            continue
        if action != want_action:
            bump("action_agrees_with_rating")
            continue
        change = _as_float(est.get("change_pct"))
        # change_pct 缺失时不放行：无法证明幅度超过噪声区间，宁可漏报。
        if change is None:
            bump("change_pct_missing")
            continue
        if abs(change) < MIN_CHANGE_PCT:
            bump("change_below_threshold")
            continue
        hits.append(
            ConflictingEstimate(
                metric=str(metric),
                metric_name_raw=est.get("metric_name_raw"),
                period=est.get("period"),
                action=str(action),
                change_pct=change,
                value=_as_float(est.get("value")),
                unit=est.get("unit"),
            )
        )
    return hits, skips


def detect_inconsistency(
    intent: Dict[str, Any],
    t6_record: Dict[str, Any],
) -> Tuple[Optional[RatingEstimateInconsistency], Optional[str]]:
    """判定单份研报。返回 (事件, None) 或 (None, 排除原因)。

    ``intent``    —— canonical bri ``NormalizedInvestmentIntent`` 的 dict 形式
    ``t6_record`` —— 一条 t6-v0.1 JSONL 记录
    """
    direction = intent.get("direction")
    if direction not in DIRECTED_STANCES:
        return None, "intent_direction_not_directed"

    validation = t6_record.get("validation") or {}
    if not validation.get("json_ok"):
        return None, "t6_json_failed"
    if not validation.get("evidence_ok"):
        # 证据未全部命中原文 → 不能下钻 → 不报（纪律 5）
        return None, "t6_evidence_not_grounded"

    extraction = t6_record.get("extraction") or {}
    estimates = extraction.get("estimates")
    if not isinstance(estimates, list) or not estimates:
        return None, "no_estimates"

    quotes = extraction.get("evidence_quotes")
    quotes = tuple(q for q in quotes if isinstance(q, str) and q.strip()) \
        if isinstance(quotes, list) else ()
    if not quotes:
        return None, "no_evidence_quotes"

    want = _CONFLICT[direction]
    conflicts, _ = _collect_conflicts(estimates, want)
    if not conflicts:
        return None, "no_conflicting_estimate"

    meta = intent.get("metadata") or {}
    event = RatingEstimateInconsistency(
        report_id=int(meta.get("report_id")) if meta.get("report_id") is not None else -1,
        intent_id=str(intent.get("intent_id") or ""),
        creator_id=str(intent.get("creator_id") or ""),
        ticker=intent.get("target_symbol"),
        report_date=meta.get("report_date") or t6_record.get("date"),
        rating_direction=str(direction),
        rating_current=meta.get("rating_current"),
        rating_action=intent.get("rating_action"),
        intent_evidence_span_ids=tuple(intent.get("evidence_span_ids") or ()),
        conflicting_estimates=tuple(conflicts),
        estimate_evidence_quotes=quotes,
    )
    if not event.has_both_sides:
        return None, "missing_side_evidence"
    return event, None


def detect_inconsistencies(
    pairs: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]],
) -> InconsistencyReport:
    """批量判定。``pairs`` 为 (intent_dict, t6_record) 序列。"""
    report = InconsistencyReport()
    for intent, t6 in pairs:
        event, reason = detect_inconsistency(intent, t6)
        if event is not None:
            report.events.append(event)
        elif reason:
            report.bump(reason)
    return report
