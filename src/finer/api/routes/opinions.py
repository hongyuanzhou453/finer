"""Opinion Timeline API — 观点时间线数据查询.

Reads real TradeAction data from F5/F6 layers via TradeActionRepository.
Returns FinerError canonical envelope when data is unavailable.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, get_args

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from finer.credibility.significance import get_significance_gate
from finer.paths import DATA_ROOT
from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError
from finer.schemas.trade_action import (
    SIGNAL_CLASS_LITERAL,
    ActionStep as TradeActionStep,
    TradeAction,
    ValidationStatus,
)
from finer.services.repository import TradeActionRepository
from finer.timeline.stance_snapshot import (
    build_snapshot,
    diff_snapshots,
    load_latest_snapshot_before,
    persist_snapshot,
    signal_clock_of,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# 类型定义
# ============================================

class ActionStep(BaseModel):
    id: str
    actionType: Literal[
        "watch", "long", "short", "add", "reduce", "close_long", "close_short"
    ]
    triggerCondition: Optional[str] = None
    targetPriceLow: Optional[str] = None
    targetPriceHigh: Optional[str] = None
    # Signed portfolio-fraction delta (+ = increase exposure); only set on
    # add/reduce steps that carry a numeric delta.
    positionDeltaPct: Optional[float] = None


class TimelineOpinion(BaseModel):
    id: str
    timestamp: str
    ticker: str
    tickerName: Optional[str] = None
    # Full 5-way TradeDirection — risk_warning/watchlist are no longer
    # collapsed into bearish/neutral (they carry distinct retail semantics).
    direction: Literal["bullish", "bearish", "neutral", "watchlist", "risk_warning"]
    confidence: float = Field(..., ge=0, le=1)
    # KOL belief strength from F3 (distinct from pipeline confidence) — the
    # honest ranking signal for "此刻可跟"; None on legacy actions.
    conviction: Optional[float] = Field(None, ge=0, le=1)
    verificationStatus: Literal["success", "failed", "pending"]

    # 验证结果
    priceChange: Optional[float] = None
    holdingDays: Optional[int] = None
    exitReason: Optional[str] = None  # backtest exit_reason (stop_loss/target_reached/…)

    # 来源信息
    sourceText: str
    author: Optional[str] = None
    platform: Optional[str] = None
    market: Optional[str] = None  # target market, e.g. "CN"
    traceStatus: Optional[str] = None  # canonical_trace_status of the F5 action
    instrumentType: Optional[str] = None  # stock/etf/index_future/…/unspecified — lets the UI downgrade non-tradable concepts
    # kol_statement vs broker_recommendation (schemas SIGNAL_CLASS_LITERAL;
    # mirrored by contracts.ts SignalClass). Passed through so the frontend can
    # badge declarative broker ratings; None = legacy/unclassified action.
    signalClass: Optional[SIGNAL_CLASS_LITERAL] = None
    # Canonical execution clock (execution_timing.action_executable_at) — the
    # real signal time. `timestamp` is the pipeline extraction moment, which
    # collapses a whole batch onto one instant; consumers that need the true
    # timeline (tide charts, latest-stance, freshness) should prefer this.
    executableAt: Optional[str] = None

    # Action Chain
    actionChain: Optional[List[ActionStep]] = None

    # RLHF 状态
    rlhfStatus: Optional[Literal["pending", "reviewed", "skipped"]] = None
    rlhfRating: Optional[int] = None


class TimelineData(BaseModel):
    opinions: List[TimelineOpinion]
    total: int
    hasMore: bool
    nextCursor: Optional[str] = None


class TimelineMeta(BaseModel):
    tickers: List[str]
    kols: List[str]
    totalOpinions: int
    timeRange: Dict[str, str]


# ============================================
# Repository 单例
# ============================================

_repository: Optional[TradeActionRepository] = None


def _get_repository() -> TradeActionRepository:
    """Get or create the TradeActionRepository singleton."""
    global _repository
    if _repository is None:
        _repository = TradeActionRepository()
    return _repository


# ============================================
# TradeAction -> TimelineOpinion 转换
# ============================================

# ActionType 枚举值到前端展示值的映射
_ACTION_TYPE_MAP = {
    "long": "long",
    "short": "short",
    "add": "add",
    "reduce": "reduce",
    "close_long": "close_long",
    "close_short": "close_short",
    "buy_call": "long",
    "sell_call": "close_long",
    "buy_put": "short",
    "sell_put": "close_short",
    "hold": "watch",
    "watch": "watch",
    "buy_and_hold": "long",
}

# TradeDirection 枚举值到前端方向值的映射（1:1 透传 5 向；
# 仅对未知值兜底到 neutral）
_DIRECTION_MAP = {
    "bullish": "bullish",
    "bearish": "bearish",
    "neutral": "neutral",
    "watchlist": "watchlist",
    "risk_warning": "risk_warning",
}

# ValidationStatus 枚举值到前端验证状态值的映射
_VALIDATION_STATUS_MAP = {
    "pending": "pending",
    "verified": "success",
    "failed": "failed",
    "under_review": "pending",
}


def _convert_action_step(step: TradeActionStep) -> ActionStep:
    """Convert a schema ActionStep to the API ActionStep model."""
    action_type_value = step.action_type.value
    mapped_type = _ACTION_TYPE_MAP.get(action_type_value, "watch")

    return ActionStep(
        id=f"step-{step.sequence}",
        actionType=mapped_type,  # type: ignore[arg-type]
        triggerCondition=step.trigger_condition,
        targetPriceLow=str(step.target_price_low) if step.target_price_low is not None else None,
        targetPriceHigh=str(step.target_price_high) if step.target_price_high is not None else None,
        positionDeltaPct=step.position_delta_pct,
    )


def trade_action_to_opinion(action: TradeAction) -> TimelineOpinion:
    """Convert a TradeAction to a TimelineOpinion for the API response."""
    direction_value = action.direction.value
    mapped_direction = _DIRECTION_MAP.get(direction_value, "neutral")

    status_value = action.validation_status.value
    mapped_status = _VALIDATION_STATUS_MAP.get(status_value, "pending")

    # Extract price change from backtest result
    price_change = None
    holding_days = None
    exit_reason = None
    if action.backtest_result:
        price_change = action.backtest_result.return_pct
        holding_days = action.backtest_result.holding_days
        er = action.backtest_result.exit_reason
        exit_reason = er.value if hasattr(er, "value") else er

    # Canonical execution clock (real signal time vs extraction moment)
    executable_at = None
    if action.execution_timing:
        clock = (
            action.execution_timing.action_executable_at
            or action.execution_timing.intent_effective_at
        )
        if clock is not None:
            executable_at = clock.isoformat()

    # Map RLHF feedback
    rlhf_status: Optional[str] = None
    rlhf_rating: Optional[int] = None
    if action.rlhf_feedback:
        if action.rlhf_feedback.rating is not None:
            rlhf_status = "reviewed"
            rlhf_rating = action.rlhf_feedback.rating
        elif action.rlhf_feedback.is_correct is not None:
            rlhf_status = "reviewed"
        else:
            rlhf_status = "pending"

    # Convert action chain
    action_chain: Optional[List[ActionStep]] = None
    if action.action_chain:
        action_chain = [_convert_action_step(s) for s in action.action_chain]

    # Extract author from source info
    author = action.source.creator_id
    # Platform is not directly available in TradeAction; use content_url domain or leave empty
    platform = None

    # Ticker name from target info
    ticker_name = action.target.company_name

    trace_status = action.canonical_trace_status
    trace_status_value = (
        trace_status.value if hasattr(trace_status, "value") else trace_status
    )

    # Signal-class passthrough (top-level field with metadata fallback); only
    # contract values survive — junk metadata degrades to None (= KOL).
    # 白名单取自 SIGNAL_CLASS_LITERAL 而非手写字面量：这里曾漏掉
    # broker_sector_view，使板块观点在时间线上被抹成 None，即「显示为 KOL」。
    signal_class = _signal_class_of(action)
    if signal_class not in _VALID_SIGNAL_CLASSES:
        signal_class = None

    return TimelineOpinion(
        id=action.trade_action_id,
        timestamp=action.timestamp.isoformat(),
        ticker=action.target.ticker_normalized or action.target.ticker,
        tickerName=ticker_name,
        direction=mapped_direction,  # type: ignore[arg-type]
        confidence=round(action.confidence, 2),
        conviction=getattr(action, "conviction", None),
        verificationStatus=mapped_status,  # type: ignore[arg-type]
        priceChange=round(price_change, 4) if price_change is not None else None,
        holdingDays=holding_days,
        exitReason=exit_reason,
        sourceText=action.source.evidence_text,
        author=author,
        platform=platform,
        market=action.target.market,
        traceStatus=trace_status_value,
        instrumentType=action.target.instrument_type,
        signalClass=signal_class,  # type: ignore[arg-type]
        executableAt=executable_at,
        actionChain=action_chain,
        rlhfStatus=rlhf_status,  # type: ignore[arg-type]
        rlhfRating=rlhf_rating,
    )


# ============================================
# 信号分类（R6 隔离门）
# ============================================

# data/F5_executed mixes KOL statements ({content_id}_actions.json) with broker
# declarative recommendations (bri_*_actions.json). Rule R6: derived_lookup-
# conviction broker recommendations must NOT feed KOL credibility scoring, the
# settled record, or the leaderboard. Timeline/detail keep them (badged via
# signalClass). These helpers are the single classification point — O(1) per
# action, no extra pass over pure-KOL directories.

#: 券商口径。**两个都算券商**——``broker_recommendation`` 是对个股的评级，
#: ``broker_sector_view`` 是对板块的看法（经 ETF 代理成交）。两者基准率不同、
#: 不得互相混算（见 SIGNAL_CLASS_LITERAL 的注释），但对 KOL 记分卡而言同样是
#: 「不是 KOL 说的」，两个都必须被 R6 门挡住。
#:
#: 此前这里是单个字符串 ``"broker_recommendation"``，用 ``==`` 比较，于是 400 条
#: ``broker_sector_view`` 全部落进「未知 = KOL」的默认分支，进了 KOL 记分卡与榜单。
_BROKER_SIGNAL_CLASSES: frozenset[str] = frozenset(
    {"broker_recommendation", "broker_sector_view"}
)

#: KOL 自述口径。与 ``_BROKER_SIGNAL_CLASSES`` 合并后必须覆盖契约的全部取值。
_KOL_SIGNAL_CLASSES: frozenset[str] = frozenset({"kol_statement"})

#: 契约认可的全部取值，直接取自 schema 真相源——用于对外透传时的白名单，
#: 避免手写字面量与契约漂移（``check_contract_drift.py`` 守的是 TS 侧镜像，
#: 守不住 Python 内部重新手写的这类白名单）。
_VALID_SIGNAL_CLASSES: frozenset[str] = frozenset(get_args(SIGNAL_CLASS_LITERAL))

# 新增 signal_class 却忘了在此归类时，**import 期就炸**，而不是静默落进
# 「未知 = KOL」——后者正是 broker_sector_view 漏了 400 条的机制。
_UNCLASSIFIED_SIGNAL_CLASSES = (
    set(get_args(SIGNAL_CLASS_LITERAL))
    - _BROKER_SIGNAL_CLASSES
    - _KOL_SIGNAL_CLASSES
)
if _UNCLASSIFIED_SIGNAL_CLASSES:  # pragma: no cover - 契约扩张时的启动期护栏
    raise RuntimeError(
        "SIGNAL_CLASS_LITERAL 新增了未归类的取值 "
        f"{sorted(_UNCLASSIFIED_SIGNAL_CLASSES)}；请在 opinions.py 的 R6 隔离门里"
        "明确归入券商侧或 KOL 侧，不要依赖默认分支。"
    )


def _signal_class_of(action: TradeAction) -> Optional[str]:
    """Signal class of an action: top-level field, metadata fallback.

    None on legacy KOL actions written before the field existed — None means
    KOL, never broker.
    """
    sc = getattr(action, "signal_class", None)
    if sc is None:
        metadata = action.metadata or {}
        sc = metadata.get("signal_class")
    return sc


def _is_broker_signal(action: TradeAction) -> bool:
    """True when the action carries any broker signal class (stock or sector)."""
    return _signal_class_of(action) in _BROKER_SIGNAL_CLASSES


def _is_superseded(action: TradeAction) -> bool:
    """True when a dedup pass marked this action as a duplicate.

    Superseded duplicates stay visible in timeline/detail, but must never be
    double-counted in stats/credibility/leaderboard aggregation.
    """
    return bool((action.metadata or {}).get("superseded_by"))


def _is_credibility_scoreable(action: TradeAction) -> bool:
    """R6 gate: may this action feed KOL stats/credibility/leaderboard?"""
    return not _is_broker_signal(action) and not _is_superseded(action)


# ============================================
# 真实数据查询
# ============================================

def _load_actions_from_dir(action_dir: Path) -> List[TradeAction]:
    """Load all TradeActions from a directory (recursive).

    Covers both persisted layouts: single ``*.action.json`` files and batch
    ``*_actions.json`` wrappers (current F5 extractor output).
    """
    actions: List[TradeAction] = []
    if not action_dir.exists():
        return actions
    repo = _get_repository()
    seen_files: set[Path] = set()
    for pattern in ("**/*.action.json", "**/*_actions.json"):
        for file_path in action_dir.glob(pattern):
            if file_path in seen_files:
                continue
            seen_files.add(file_path)
            try:
                actions.extend(repo.load_actions_from_file(file_path))
            except Exception as e:
                logger.warning(
                    "Failed to load TradeAction from %s: %s", file_path, e
                )
    return actions


def _query_real_timeline(
    ticker_list: List[str],
    direction_list: List[str],
    kol_list: List[str],
    start_time: datetime,
    end_time: datetime,
    offset: int,
    limit: int,
) -> tuple[List[TimelineOpinion], int]:
    """Query real TradeAction data and convert to TimelineOpinion list.

    Reads F5 and F6 via direct file scans — the same single track as
    _load_all_actions (/meta, /stats). The SQLite index is a cache that the F5
    write path does not refresh, so it must not gate the main timeline
    (otherwise /timeline silently misses actions that /meta counts).
    Deduplicates by trade_action_id.

    Returns:
        Tuple of (opinions, total_count).
    """
    repo = _get_repository()

    # Collect all actions, deduplicated by trade_action_id
    seen_ids: set[str] = set()
    all_actions: List[TradeAction] = []

    # --- F5 data: direct file scan of the canonical tier dir ---
    for action in _load_actions_from_dir(repo.action_dir):
        if action.trade_action_id not in seen_ids:
            seen_ids.add(action.trade_action_id)
            all_actions.append(action)

    # --- F6 data: direct file scan (reviewed actions) ---
    l6_dir = DATA_ROOT / "F6_reviewed"
    for action in _load_actions_from_dir(l6_dir):
        if action.trade_action_id not in seen_ids:
            seen_ids.add(action.trade_action_id)
            all_actions.append(action)

    # --- Unified in-memory filters (applied to F5 and F6 alike) ---
    all_actions = [
        a for a in all_actions if start_time <= a.timestamp <= end_time
    ]
    if kol_list:
        all_actions = [a for a in all_actions if a.source.creator_id in kol_list]
    if direction_list:
        all_actions = [a for a in all_actions if a.direction.value in direction_list]
    if ticker_list:
        normalized_tickers = {t.upper() for t in ticker_list}
        all_actions = [
            a for a in all_actions
            if (a.target.ticker_normalized or a.target.ticker).upper() in normalized_tickers
        ]

    # Sort by timestamp descending
    all_actions.sort(key=lambda a: a.timestamp, reverse=True)

    total = len(all_actions)

    # Apply pagination
    paginated = all_actions[offset: offset + limit]

    # Convert to TimelineOpinion
    opinions = [trade_action_to_opinion(a) for a in paginated]

    return opinions, total


def _load_all_actions() -> List[TradeAction]:
    """Load all TradeAction data from F5 and F6 (direct file scans).

    Scans files as the authoritative source (both persisted layouts), so a
    stale or empty SQLite index cannot hide F5 data. Deduplicates by
    trade_action_id.
    """
    repo = _get_repository()
    seen_ids: set[str] = set()
    all_actions: List[TradeAction] = []

    # F5 data via direct file scan of the canonical tier dir
    for action in _load_actions_from_dir(repo.action_dir):
        if action.trade_action_id not in seen_ids:
            seen_ids.add(action.trade_action_id)
            all_actions.append(action)

    # F6 data via direct file scan
    l6_dir = DATA_ROOT / "F6_reviewed"
    for action in _load_actions_from_dir(l6_dir):
        if action.trade_action_id not in seen_ids:
            seen_ids.add(action.trade_action_id)
            all_actions.append(action)

    return all_actions


def _get_real_meta() -> TimelineMeta:
    """Get meta information from real data (F5 + F6)."""
    all_actions = _load_all_actions()

    tickers_set: set[str] = set()
    kols_set: set[str] = set()
    timestamps: List[str] = []

    for action in all_actions:
        tickers_set.add(action.target.ticker_normalized or action.target.ticker)
        if action.source.creator_id:
            kols_set.add(action.source.creator_id)
        timestamps.append(action.timestamp.isoformat())

    now = datetime.now()
    time_range = {
        "min": min(timestamps) if timestamps else (now - timedelta(days=365)).isoformat(),
        "max": max(timestamps) if timestamps else now.isoformat(),
    }

    return TimelineMeta(
        tickers=sorted(tickers_set),
        kols=sorted(kols_set),
        totalOpinions=len(all_actions),
        timeRange=time_range,
    )


# 曾有一个收缩式「信誉分」：adjRate = (wins + K/2)/(settled + K) → 0-99，
# 私有阈值 n<5 判低样本。2026-08-17 **整条链路删除**（API 字段、快照存储、
# score_change 事件、前端 4 个组件）。两个无法接受的性质：
#   1. canonical 效力门是 30/15（configs/significance.yaml），私有门宽了
#      3-6 倍——同一件事两道门，松的那道还是用户看到的那道；
#   2. 0-99 分 + 降序排名正是 2026-08-02 定位转向禁止的形态。
# 任何比率型指标一律走 `get_significance_gate().assess()`。

_DIRECTION_CN = {
    "bullish": "看多",
    "bearish": "看空",
    "neutral": "中性",
    "watchlist": "观察",
    "risk_warning": "风险提示",
}


def _attributed_actions() -> List[TradeAction]:
    """All credibility-scoreable actions with a real KOL attribution.

    This is the universe for /changes (snapshots, flip/stop-loss events) and
    the credibility map — broker recommendations and superseded duplicates are
    excluded here (R6): a broker rating must not open a KOL stance, flip one,
    or move a credibility score.
    """
    return [
        a
        for a in _load_all_actions()
        if a.source.creator_id
        and a.source.creator_id.strip().lower() not in ("unknown", "none", "")
        and _is_credibility_scoreable(a)
    ]


def _kol_settled_record(
    actions: List[TradeAction],
    universe: Optional[List[TradeAction]] = None,
) -> Dict[str, tuple[int, int]]:
    """(settled, wins) per KOL over stance EPISODES, not raw actions.

    Single source of truth for every KOL record on this route — both the
    credibility map and the /stats/summary topKols tally read it, so the two
    cannot drift apart.

    A standing view restated week after week is ONE call, scored from its first
    statement (a follower's real entry point); a flip opens a new call. Counting
    each restatement as an independent bet inflated records badly — 8 of
    trader_ji's 12 settled "calls" were a single AAPL view repeated by his
    weekly-strategy template. See timeline/stance_episodes.py.

    ``universe`` is the FULL action history used to build episodes; ``actions``
    is the (possibly time/ticker-filtered) scope being scored. Episodes must be
    built from the universe or a windowed query re-anchors a standing view to
    its first in-window restatement and scores that restatement's backtest —
    the exact restatement-scoring this function exists to eliminate. An episode
    is tallied only when its anchor (true first statement) is inside ``actions``:
    windowed stats mean "calls initiated in this window, scored from initiation".
    """
    from finer.timeline.stance_episodes import build_stance_episodes

    # R6 gate at the single settled-record source: broker recommendations and
    # superseded duplicates never enter the record — not as scored episodes,
    # not as zero-record leaderboard entries, and not as episode anchors in
    # the universe (a superseded duplicate must not steal an anchor from the
    # surviving copy).
    actions = [a for a in actions if _is_credibility_scoreable(a)]
    universe_actions = (
        [a for a in universe if _is_credibility_scoreable(a)]
        if universe is not None
        else actions
    )

    record: Dict[str, list[int]] = {}
    for a in actions:  # every attributed KOL appears, even with nothing settled
        k = (a.source.creator_id or "").strip()
        if k and k.lower() not in ("unknown", "none"):
            record.setdefault(k, [0, 0])
    in_scope = {a.trade_action_id for a in actions}
    for ep in build_stance_episodes(universe_actions):
        if ep.anchor.trade_action_id not in in_scope:
            continue
        bt = ep.backtest_result  # the FIRST statement's outcome
        if bt and bt.return_pct is not None and (bt.holding_days or 0) > 0:
            rec = record.setdefault(ep.creator_id, [0, 0])
            rec[0] += 1
            if bt.return_pct > 0:
                rec[1] += 1
    return {k: (v[0], v[1]) for k, v in record.items()}


def _kol_settled_count_map(actions: List[TradeAction]) -> Dict[str, int]:
    """每个 KOL 的已结算样本量——快照存的事实计数（取代已下线的信誉分）。"""
    return {
        k: settled for k, (settled, _wins) in _kol_settled_record(actions).items()
    }


def _history_change_events(actions: List[TradeAction]) -> List[dict]:
    """Change events observable in the opinion history itself.

    Flips = consecutive direction changes per (KOL, ticker) ordered by the
    canonical signal clock; stop-loss exits come from real backtest results.
    (Same semantics the dashboard adapter derived client-side before this
    endpoint existed.)
    """
    events: List[dict] = []

    groups: Dict[tuple, List[TradeAction]] = {}
    for a in actions:
        ticker = a.target.ticker_normalized or a.target.ticker
        groups.setdefault((a.source.creator_id, ticker), []).append(a)

    for (kol, ticker), lst in groups.items():
        lst.sort(key=lambda a: (signal_clock_of(a), a.trade_action_id))
        for prev_a, cur_a in zip(lst, lst[1:]):
            if prev_a.direction != cur_a.direction:
                events.append(
                    {
                        "id": f"flip-{cur_a.trade_action_id}",
                        "type": "flip",
                        "kolId": kol,
                        "kolName": kol,
                        "ticker": ticker,
                        "companyName": cur_a.target.company_name or ticker,
                        "fromDirection": prev_a.direction.value,
                        "toDirection": cur_a.direction.value,
                        "detail": (
                            f"从{_DIRECTION_CN.get(prev_a.direction.value, prev_a.direction.value)}"
                            f"转为{_DIRECTION_CN.get(cur_a.direction.value, cur_a.direction.value)}"
                        ),
                        "timestamp": signal_clock_of(cur_a),
                    }
                )

    for a in actions:
        bt = a.backtest_result
        exit_reason = getattr(bt, "exit_reason", None) if bt else None
        exit_value = getattr(exit_reason, "value", exit_reason)
        if exit_value == "stop_loss":
            ticker = a.target.ticker_normalized or a.target.ticker
            events.append(
                {
                    "id": f"sl-{a.trade_action_id}",
                    "type": "stop_loss",
                    "kolId": a.source.creator_id,
                    "kolName": a.source.creator_id,
                    "ticker": ticker,
                    "companyName": a.target.company_name or ticker,
                    "detail": "跟单回测触发止损离场",
                    "timestamp": signal_clock_of(a),
                    "value": bt.return_pct,
                }
            )

    return events


def _get_real_stats(time_range: str, ticker: Optional[str]) -> Dict[str, Any]:
    """Get statistics summary from real data (F5 + F6)."""
    all_actions = _load_all_actions()

    now = datetime.now()
    time_range_map = {
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "1Y": timedelta(days=365),
        "ALL": timedelta(days=365 * 2),
    }
    start_time = now - time_range_map.get(time_range, timedelta(days=30))

    # Filter by time range and ticker. Superseded duplicates (dedup markers in
    # metadata.superseded_by) are dropped from ALL stats aggregation here —
    # they'd double-count the surviving copy. They stay visible in
    # timeline/detail only.
    filtered: List[TradeAction] = []
    for action in all_actions:
        if action.timestamp < start_time:
            continue
        if ticker and (action.target.ticker_normalized or action.target.ticker).upper() != ticker.upper():
            continue
        if _is_superseded(action):
            continue
        filtered.append(action)

    if not filtered:
        return {
            "total": 0,
            "byDirection": {
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "watchlist": 0,
                "risk_warning": 0,
            },
            "byStatus": {"success": 0, "failed": 0, "pending": 0},
            "avgConfidence": 0.0,
            "avgPriceChange": 0.0,
            "topTickers": [],
            "topKols": [],
        }

    # Aggregate — full 5-way direction buckets (no collapse)
    by_direction: Dict[str, int] = {
        "bullish": 0,
        "bearish": 0,
        "neutral": 0,
        "watchlist": 0,
        "risk_warning": 0,
    }
    by_status: Dict[str, int] = {"success": 0, "failed": 0, "pending": 0}
    confidences: List[float] = []
    price_changes: List[float] = []
    ticker_counts: Dict[str, int] = {}
    ticker_success: Dict[str, List[bool]] = {}
    kol_counts: Dict[str, int] = {}

    for action in filtered:
        # Direction (5-way buckets cover every TradeDirection value)
        d = action.direction.value
        if d in by_direction:
            by_direction[d] += 1

        # Validation status
        s = action.validation_status.value
        mapped_s = _VALIDATION_STATUS_MAP.get(s, "pending")
        if mapped_s in by_status:
            by_status[mapped_s] += 1

        confidences.append(action.confidence)

        # Backtest price change
        if action.backtest_result and action.backtest_result.return_pct is not None:
            price_changes.append(action.backtest_result.return_pct)

        # Ticker counts
        t = action.target.ticker_normalized or action.target.ticker
        ticker_counts[t] = ticker_counts.get(t, 0) + 1
        if action.validation_status == ValidationStatus.VERIFIED:
            ticker_success.setdefault(t, []).append(True)
        elif action.validation_status == ValidationStatus.FAILED:
            ticker_success.setdefault(t, []).append(False)

        # KOL volume count (the topKols ranking metric — how often they spoke).
        # The settled follow-P&L RECORD is computed once below over stance
        # episodes, so restatements of one standing view count as one call.
        # Key exactly like _kol_settled_record (stripped, unknown/none dropped)
        # or a padded/pseudo creator occupies a topKols slot with a zeroed
        # record and a fabricated neutral-prior credibility. Broker
        # recommendations are excluded (R6): a broker must never occupy a KOL
        # leaderboard slot.
        kol = (action.source.creator_id or "").strip()
        if (
            kol
            and kol.lower() not in ("unknown", "none")
            and not _is_broker_signal(action)
        ):
            kol_counts[kol] = kol_counts.get(kol, 0) + 1

    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    avg_price_change = round(sum(price_changes) / len(price_changes), 2) if price_changes else 0.0

    # Top tickers
    top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_ticker_list = [
        {
            "ticker": t,
            "count": cnt,
            "successRate": round(
                sum(1 for v in ticker_success.get(t, []) if v) / len(ticker_success[t]), 2
            ) if t in ticker_success and ticker_success[t] else 0.0,
        }
        for t, cnt in top_tickers
    ]

    # Top KOLs — with server-side credibility (single source of truth; the
    # dashboard previously derived this client-side in kol-radar.ts).
    from finer.services.kol_registry import get_registry

    registry = get_registry()
    # One shared, episode-based record — same function the credibility map uses,
    # so topKols and /changes can never drift apart. Episodes are built from the
    # FULL history (universe) so the window can't re-anchor a standing view to
    # an in-window restatement; the window only decides which anchors count.
    kol_record = _kol_settled_record(filtered, universe=all_actions)
    # 默认序 = 已结算样本量降序（UI-1 拍板的稳定输出序，**不是排名**）。
    # 此前按观点数排序、再由前端配上 0-99 信誉分与名次，合起来就是一张
    # 「谁更准」的榜——定位转向明令禁止的形态。
    gate = get_significance_gate()
    ranked = sorted(
        kol_counts.items(),
        key=lambda kv: (-kol_record.get(kv[0], (0, 0))[0], -kv[1], kv[0]),
    )[:5]
    top_kol_list = []
    for k, cnt in ranked:
        settled, wins = kol_record.get(k, (0, 0))
        # `author` stays the raw creator_id — it is the join key the frontend
        # uses; registry adds display fields only.
        profile = registry.get(k)
        sufficiency = gate.assess(successes=wins, settled_n=settled, total_n=cnt)
        permitted = sufficiency.display_policy != "count_only"
        top_kol_list.append({
            "author": k,
            "displayName": profile.display_name if profile and profile.display_name else k,
            "styleLabel": profile.style_label if profile else None,
            "count": cnt,
            "settledCount": settled,
            "wins": wins,
            # 比率过门才发；不过门发 None——0 会被当真，见 CLAUDE.md 定位前提 §1
            "hitRate": round(wins / settled, 4) if (permitted and settled) else None,
            "sufficiency": sufficiency.model_dump(mode="json"),
        })

    return {
        "total": len(filtered),
        "byDirection": by_direction,
        "byStatus": by_status,
        "avgConfidence": avg_confidence,
        "avgPriceChange": avg_price_change,
        "topTickers": top_ticker_list,
        "topKols": top_kol_list,
    }



# ============================================
# API 端点
# ============================================

@router.get("/timeline", response_model=TimelineData)
async def get_timeline(
    timeRange: str = Query("1M", description="时间范围: 1W, 1M, 3M, 1Y, ALL"),
    tickers: Optional[str] = Query(None, description="标的列表，逗号分隔"),
    directions: Optional[str] = Query(None, description="方向列表，逗号分隔"),
    kols: Optional[str] = Query(None, description="KOL列表，逗号分隔"),
    cursor: Optional[str] = Query(None, description="分页游标"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取观点时间线数据."""
    ticker_list = tickers.split(",") if tickers else []
    direction_list = directions.split(",") if directions else []
    kol_list = kols.split(",") if kols else []

    now = datetime.now()
    time_range_map = {
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "1Y": timedelta(days=365),
        "ALL": timedelta(days=365 * 2),
    }
    start_time = now - time_range_map.get(timeRange, timedelta(days=30))
    offset = int(cursor) if cursor else 0

    try:
        opinions, total = _query_real_timeline(
            ticker_list=ticker_list,
            direction_list=direction_list,
            kol_list=kol_list,
            start_time=start_time,
            end_time=now,
            offset=offset,
            limit=limit,
        )
    except Exception as e:
        logger.error("Failed to query timeline data: %s", e, exc_info=True)
        raise FinerError(
            ErrorCode.F7_INT_001,
            f"时间线数据查询失败: {e}",
            stage="F7",
            operation="get_timeline",
            retryable=True,
            fix_hint="检查 F5/F6 数据目录是否存在有效的 TradeAction 文件",
        )

    has_more = offset + limit < total
    next_cursor = str(offset + limit) if has_more else None

    return TimelineData(
        opinions=opinions,
        total=total,
        hasMore=has_more,
        nextCursor=next_cursor,
    )


@router.get("/meta", response_model=TimelineMeta)
async def get_timeline_meta():
    """获取时间线元数据（可选的标的、KOL等）."""
    try:
        return _get_real_meta()
    except Exception as e:
        logger.error("Failed to query timeline meta: %s", e, exc_info=True)
        raise FinerError(
            ErrorCode.F7_INT_001,
            f"时间线元数据查询失败: {e}",
            stage="F7",
            operation="get_timeline_meta",
            retryable=True,
            fix_hint="检查 F5/F6 数据目录是否存在有效的 TradeAction 文件",
        )


@router.get("/stats/summary")
async def get_stats_summary(
    timeRange: str = Query("1M", description="时间范围"),
    ticker: Optional[str] = Query(None, description="标的筛选"),
):
    """获取统计摘要."""
    try:
        return {"ok": True, "data": _get_real_stats(timeRange, ticker)}
    except Exception as e:
        logger.error("Failed to query stats summary: %s", e, exc_info=True)
        raise FinerError(
            ErrorCode.F7_INT_001,
            f"统计摘要查询失败: {e}",
            stage="F7",
            operation="get_stats_summary",
            retryable=True,
            fix_hint="检查 F5/F6 数据目录是否存在有效的 TradeAction 文件",
        )


def _compute_changes(limit: int) -> dict:
    """Synchronous body of GET /changes (run in a threadpool, see handler)."""
    actions = _attributed_actions()
    settled_counts = _kol_settled_count_map(actions)

    today = date.today()
    current = build_snapshot(actions, settled_counts, snapshot_date=today)
    previous = load_latest_snapshot_before(today)
    snapshot_events = diff_snapshots(previous[1], current) if previous else []
    persist_snapshot(current)

    # merge, dedupe by id (a same-day flip can appear in both sources)
    merged: Dict[str, dict] = {}
    for ev in _history_change_events(actions) + snapshot_events:
        merged.setdefault(ev["id"], ev)
    events = sorted(
        merged.values(), key=lambda e: e.get("timestamp") or "", reverse=True
    )[:limit]

    # Presentation decoration at the API boundary: both event sources carry raw
    # creator_ids; the registry supplies display names in one place (kolId stays
    # the raw join key).
    from finer.services.kol_registry import get_registry

    registry = get_registry()
    for ev in events:
        if ev.get("kolId"):
            ev["kolName"] = registry.display_name(ev["kolId"])

    return {
        "events": events,
        "snapshotDate": current["snapshot_date"],
        "prevSnapshotDate": previous[0].isoformat() if previous else None,
    }


@router.get("/changes")
async def get_changes(limit: int = Query(20, ge=1, le=100, description="事件数量上限")):
    """近期异动：历史派生（翻向/止损）+ 每日立场快照对比（新增覆盖/隔日翻向/信誉变动）。

    每次调用会把当日立场快照落盘到 data/F7_timeline/stance_snapshots/（当日内
    幂等覆盖），与最近一份更早的快照做 diff。冷启动（无历史快照）时只返回
    历史派生事件，快照 diff 随历史积累自然出现。
    """
    try:
        # The body scans F5, builds + persists an F7 snapshot, and diffs — all
        # synchronous and heavy. Offload to the threadpool so /changes never
        # blocks the event loop (which stalls every other request, e.g. /radar).
        data = await run_in_threadpool(_compute_changes, limit)
        return {"ok": True, "data": data}
    except Exception as e:
        logger.error("Failed to compute changes: %s", e, exc_info=True)
        raise FinerError(
            ErrorCode.F7_INT_001,
            f"异动计算失败: {e}",
            stage="F7",
            operation="get_changes",
            retryable=True,
            fix_hint="检查 F5 数据与 data/F7_timeline/stance_snapshots/ 目录可写",
        )


@router.get("/{opinion_id}", response_model=TimelineOpinion)
async def get_opinion_detail(opinion_id: str):
    """获取单个观点详情."""
    try:
        # F5 via repository
        repo = _get_repository()
        action = repo.load(opinion_id)
        if action:
            return trade_action_to_opinion(action)

        # F6 via direct file scan (both persisted layouts)
        l6_dir = DATA_ROOT / "F6_reviewed"
        for candidate in _load_actions_from_dir(l6_dir):
            if candidate.trade_action_id == opinion_id:
                return trade_action_to_opinion(candidate)
    except FinerError:
        raise
    except Exception as e:
        logger.error("Failed to load opinion %s: %s", opinion_id, e, exc_info=True)
        raise FinerError(
            ErrorCode.F7_INT_001,
            f"观点详情查询失败: {e}",
            stage="F7",
            operation="get_opinion_detail",
            retryable=True,
            fix_hint="检查 F5/F6 数据目录是否存在有效的 TradeAction 文件",
        )

    raise FinerError(
        ErrorCode.F7_NTF_001,
        f"观点 {opinion_id} 未找到",
        stage="F7",
        operation="get_opinion_detail",
        retryable=False,
        fix_hint="检查 opinion_id 是否正确，或确认 F5/F6 数据已导入",
    )
