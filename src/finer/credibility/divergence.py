"""CRD-4 言行不一检测 —— 同期「说的」与「做的」方向冲突。

**本模块的假阳性等于对信源的不实指控**，因此判定条件比其他模块更保守：

1. **只比同期。** 十个月里先看空后看多是正常的改变主意，不是言行不一。
   冲突必须发生在一个已声明立场的**有效窗口内**。窗口长度由声明自带的
   ``time_horizon_hint`` 推出，不猜。
2. **只比同一立场槽位。** 复用 ``stance_snapshot.stance_key_of``——它已经
   编码了「两个代理到同一 ETF 的板块必须保持不同视角」这条非显然规则。
3. **只比明确方向。** ``neutral`` / ``mixed`` 一律不参与——从「中性」推不出
   任何矛盾。
4. **「说」与「做」必须是不同性质的声明。** 「说」= ``opinion`` / ``watch``
   （零仓位承诺）；「做」= ``explicit_action``（本人仓位变动）。

**券商在结构上不可能触发本检测**：R2 保证券商只产 ``recommendation``，
那是零仓位承诺的声明式评级——一家券商给了买入评级却没有买入，不是言行
不一，它本来就不交易。误把评级当「做」会把每一家券商都误告一遍。

规模诚实：现有语料中 ``explicit_action`` 仅 100 条，可归属信源**只有一个**
（trader_ji）。本模块因此是**为将来准备的能力**，当前不足以作为产品功能
对外呈现——见 `docs/specs/2026-08-02-crd4-feasibility.md`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_BEIJING = timezone(timedelta(hours=8))

#: 只有明确方向才可能构成矛盾。
_DIRECTIONAL = ("bullish", "bearish")

#: 「说」的层级——零仓位承诺的表态。``recommendation`` 不在其中：
#: 那是机构评级，其发出者本来就不持仓，谈不上言行。
SAY_ACTIONABILITY = ("opinion", "watch")

#: 「做」的层级——本人仓位真的动了。
DO_ACTIONABILITY = ("explicit_action",)

#: 立场有效窗口（天）。声明没给 horizon 时用 ``default``——取值偏**短**，
#: 因为窗口越长越容易把「后来改主意」误判成「当时就言行不一」。
HORIZON_WINDOW_DAYS: Dict[str, int] = {
    "intraday": 3,
    "short_term": 14,
    "medium_term": 45,
    "long_term": 90,
}
DEFAULT_WINDOW_DAYS = 14

#: 无法归属的标的占位符，一律排除（``unknown`` 是数据缺口不是标的）。
_UNUSABLE_TICKERS = frozenset({"", "unknown", "none", "n/a"})


@dataclass(frozen=True)
class DivergenceEvent:
    """一次同期言行冲突。双方都挂证据，供下钻核验。"""

    creator_id: str
    stance_key: str
    ticker: str

    said_direction: str
    said_at: str
    said_intent_id: str
    said_evidence_span_ids: Tuple[str, ...]

    did_direction: str
    did_at: str
    did_intent_id: str
    did_evidence_span_ids: Tuple[str, ...]

    #: 「做」发生在「说」之后第几天（负数表示先做后说）
    gap_days: int
    #: 该次声明的有效窗口长度，用于审计判定为何成立
    window_days: int

    @property
    def both_sides_have_evidence(self) -> bool:
        """双方都能下钻到原文。缺任一侧的事件不应对外展示。"""
        return bool(self.said_evidence_span_ids) and bool(self.did_evidence_span_ids)


@dataclass
class DivergenceReport:
    events: List[DivergenceEvent] = field(default_factory=list)
    #: 各道排除条件命中多少条，用于审计「为什么没报出来」
    skips: Dict[str, int] = field(default_factory=dict)
    creators_with_both_tiers: List[str] = field(default_factory=list)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=_BEIJING) if dt.tzinfo is None else dt


def _window_days(horizon: Optional[str]) -> int:
    return HORIZON_WINDOW_DAYS.get(horizon or "", DEFAULT_WINDOW_DAYS)


def _slot(intent: dict) -> Optional[Tuple[str, str]]:
    """(stance_key, ticker)。无法归属的返回 None。"""
    ticker = (intent.get("target_symbol") or intent.get("target_name") or "").strip()
    if ticker.lower() in _UNUSABLE_TICKERS:
        return None
    target_type = intent.get("target_type") or "stock"
    # 与 stance_snapshot.stance_key_of 同构：类型进 key，避免两个代理到同一
    # ETF 的板块被折叠成一个视角
    return f"{target_type}:{ticker}", ticker


def publication_clock_from_actions(actions: Iterable[dict]) -> Dict[str, str]:
    """intent_id → 真实发布时刻，取自 F5 ``execution_timing``。

    这是本模块唯一可信的时钟来源。F3 的 ``created_at`` 是批处理时间戳，
    实测全语料只落在 3 个日期上——用它判定「同期」会把一整批处理过的声明
    判成并发。
    """
    clock: Dict[str, str] = {}
    for action in actions:
        intent_id = action.get("intent_id")
        if not intent_id:
            continue
        timing = action.get("execution_timing") or {}
        stamp = timing.get("intent_published_at") or timing.get("action_decision_at")
        if stamp:
            clock.setdefault(intent_id, stamp)
    return clock


def detect_divergences(
    intents: Iterable[dict],
    *,
    published_at_of=None,
) -> DivergenceReport:
    """在同一信源的声明流里找同期言行冲突。

    Args:
        intents: F3 intent 的 dict 序列（同一或多个 creator 均可）。
        published_at_of: 从 intent 取**发布时刻**的函数。**必须传**——
            F3 的 ``created_at`` 是批处理时间戳（实测全语料只有 3 个不同
            日期），拿它比同期会把同一批处理的所有声明判成并发，造出成片
            的不实指控。调用方应传入 F5 ``execution_timing.intent_published_at``
            的查表函数，见 ``publication_clock_from_actions``。

    Returns:
        DivergenceReport。``skips`` 记录每道排除条件的命中数——没报出来
        和报出来同样需要可审计。
    """
    if published_at_of is None:
        raise ValueError(
            "published_at_of 必须显式提供：F3 的 created_at 是批处理时间戳，"
            "用它判定同期会产生成片的假阳性（2026-08-02 实测：37 条冲突全部"
            "是处理时间戳造成的假象）。请用 publication_clock_from_actions。"
        )
    report = DivergenceReport()
    when = published_at_of

    says: Dict[Tuple[str, str], List[dict]] = {}
    dos: Dict[Tuple[str, str], List[dict]] = {}
    tiers: Dict[str, set] = {}

    for intent in intents:
        creator = (intent.get("creator_id") or "").strip()
        if not creator or creator.lower() in _UNUSABLE_TICKERS:
            report.skips["no_creator"] = report.skips.get("no_creator", 0) + 1
            continue
        actionability = intent.get("actionability")
        if actionability in SAY_ACTIONABILITY:
            bucket, tier = says, "say"
        elif actionability in DO_ACTIONABILITY:
            bucket, tier = dos, "do"
        else:
            # recommendation / review_required：机构评级与待审，皆非言行
            report.skips["not_say_or_do"] = report.skips.get("not_say_or_do", 0) + 1
            continue
        if intent.get("direction") not in _DIRECTIONAL:
            report.skips["non_directional"] = report.skips.get("non_directional", 0) + 1
            continue
        slot = _slot(intent)
        if slot is None:
            report.skips["unusable_ticker"] = report.skips.get("unusable_ticker", 0) + 1
            continue
        if _parse(when(intent)) is None:
            report.skips["no_timestamp"] = report.skips.get("no_timestamp", 0) + 1
            continue
        tiers.setdefault(creator, set()).add(tier)
        bucket.setdefault((creator, slot[0]), []).append(intent)

    report.creators_with_both_tiers = sorted(
        c for c, t in tiers.items() if t == {"say", "do"}
    )

    for key, said_list in says.items():
        did_list = dos.get(key)
        if not did_list:
            continue
        said_list = sorted(said_list, key=lambda i: _parse(when(i)))
        did_list = sorted(did_list, key=lambda i: _parse(when(i)))

        # 贪心不重叠扫描：一次冲突 = 一个事件。同日多条「说」× 多条「做」
        # 是同一件事的重述，不是 M×N 次言行不一——重述膨胀正是
        # stance_episodes docstring 警告过的那个坑。
        consumed_until = None
        for said in said_list:
            said_at = _parse(when(said))
            if consumed_until is not None and said_at <= consumed_until:
                report.skips["same_episode"] = report.skips.get("same_episode", 0) + 1
                continue
            window = _window_days(said.get("time_horizon_hint"))
            deadline = said_at + timedelta(days=window)
            did = next(
                (
                    d for d in did_list
                    if d.get("direction") != said.get("direction")
                    and said_at <= _parse(when(d)) <= deadline
                ),
                None,
            )
            if did is None:
                report.skips["no_concurrent_conflict"] = (
                    report.skips.get("no_concurrent_conflict", 0) + 1
                )
                continue
            did_at = _parse(when(did))
            consumed_until = deadline
            if True:
                _, ticker = _slot(said)  # type: ignore[misc]
                report.events.append(DivergenceEvent(
                    creator_id=key[0],
                    stance_key=key[1],
                    ticker=ticker,
                    said_direction=said["direction"],
                    said_at=said_at.isoformat(),
                    said_intent_id=said.get("intent_id") or "",
                    said_evidence_span_ids=tuple(said.get("evidence_span_ids") or ()),
                    did_direction=did["direction"],
                    did_at=did_at.isoformat(),
                    did_intent_id=did.get("intent_id") or "",
                    did_evidence_span_ids=tuple(did.get("evidence_span_ids") or ()),
                    gap_days=(did_at - said_at).days,
                    window_days=window,
                ))

    report.events.sort(key=lambda e: (e.creator_id, e.said_at))
    return report
