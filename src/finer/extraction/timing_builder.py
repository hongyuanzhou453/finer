"""ExecutionTiming builder — extracted from canonical_runner.

Deterministic timing computation for F5 TradeActions.
Delegates to MarketCalendarTimingPolicy for market-calendar-based logic.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.trade_action import ExecutionTiming, MarketSession

__all__ = ["build_execution_timing", "is_date_only", "resolve_publication_instant"]


def is_date_only(
    published_at: datetime, source_timezone: Optional[str] = None
) -> bool:
    """发布时间戳是否只携带日期（时刻为源时区的零点）。

    F0/F1 从研报 PDF 只能拿到**日期**，拿不到发布时刻，于是 ``published_at``
    被填成「当地零点」。实测语料 3,229/3,313（97.5%）如此。

    Args:
        published_at: 待判定的时间戳。
        source_timezone: 上游产出该时间戳时所用的时区。**下游若把同一瞬间
            重新渲染成别的时区，零点标记就看不见了**——例如 F5 存的
            ``2025-12-16T11:00:00-05:00`` 其实就是 ``2025-12-17T00:00:00+08:00``。
            回写这类已渲染数据时必须显式传入源时区；``None`` 表示按时间戳
            自身的时区判定（F1/F2 envelope 走这条）。
    """
    moment = (
        published_at.astimezone(ZoneInfo(source_timezone))
        if source_timezone
        else published_at
    )
    return (
        moment.hour == 0
        and moment.minute == 0
        and moment.second == 0
        and moment.microsecond == 0
    )


def resolve_publication_instant(
    published_at: datetime,
    timezone: str,
    source_timezone: Optional[str] = None,
) -> datetime:
    """把 date-only 的发布时间戳重新锚定到**目标市场**的时区。

    为什么必须重锚（2026-07-27 全语料前视偏差根因）：``published_at`` 的零点是
    占位符，不是真实时刻。把它当真实时刻解释时，**北京时 D 日零点 ≡ 纽约时
    D−1 日 11:00**——正处美股盘中，于是可执行时间被放在 D−1，比研报日期早
    一整天。实测该机制让语料里 **1,669 条（50.4%）** 的入场早于其研报日期，
    对任何位于北京以西的市场（美洲、欧洲）都成立。

    正确语义：研报日期是一个**日历日**，不是一个瞬间。把该日历日按目标市场
    的时区重新锚定为当地零点，则它落在当地盘前，可执行时间自然是研报日当天
    的开盘——既不提前于发布，也不无谓地推迟一天。

    亚太市场（当地零点与北京零点同日）行为逐位不变；改变的只有北京以西的市场。

    带真实时刻的 ``published_at``（如飞书/KOL 内容）原样返回，不受影响。

    ``source_timezone`` 的用途见 :func:`is_date_only`：F5 存量已被重新渲染成
    市场本地时区，零点标记不可见，回写时必须显式告知源时区才能取回研报日期。

    详见 ``docs/specs/2026-07-27-corpus-wide-entry-lookahead.md``。
    """
    if not is_date_only(published_at, source_timezone):
        return published_at
    try:
        target_tz = ZoneInfo(timezone)
    except Exception:  # noqa: BLE001 — 未知时区退回原值，不猜
        return published_at
    source_moment = (
        published_at.astimezone(ZoneInfo(source_timezone))
        if source_timezone
        else published_at
    )
    # 研报日期是一个日历日；把它按目标市场时区锚成当地零点（落在盘前）。
    return datetime.combine(source_moment.date(), time(0, 0), tzinfo=target_tz)


def build_execution_timing(
    envelope: ContentEnvelope,
    temporal_anchors: Optional[List[Any]] = None,
    market: str = "CN",
    intent_id: Optional[str] = None,
) -> ExecutionTiming:
    """Build ExecutionTiming using MarketCalendarTimingPolicy.

    Uses the deterministic market calendar timing policy to compute
    action_executable_at, instead of ad-hoc datetime arithmetic.

    Args:
        envelope: Content envelope with published_at.
        temporal_anchors: Temporal anchors from F2. Only ``effective_trade_at``
            populates ``intent_effective_at``; ``mentioned_at`` dates are
            contextual references and are ignored for timing.
        market: Market code from the shared session table
            (``execution/timing_policy.py:MARKET_SESSIONS`` — HK/CN/US plus
            the international set derivable from the F2 ticker suffix
            tables). An unknown code does NOT silently fall back to a default
            exchange calendar: it flows through the policy's explicit
            unknown-market path (``market_session_at_publish == UNKNOWN``,
            default reaction delay, timezone ``UTC``).
        intent_id: Associated intent ID (for logging; unused in timing logic).

    Returns:
        ExecutionTiming with all fields populated.
    """
    from finer.execution.timing_policy import (
        MarketCalendarTimingPolicy,
        get_market_config,
    )

    if envelope.published_at is None:
        raise ValueError(
            "ContentEnvelope.published_at is required to build canonical "
            "ExecutionTiming without falling back to runtime now()."
        )
    published_at = envelope.published_at

    # Determine intent_effective_at from temporal anchors
    intent_effective_at = _resolve_intent_effective_at(temporal_anchors)

    # Timezone from the single shared market table (no fork, no duplicate map).
    # Unknown market → explicit degradation, mirroring the policy's
    # _unknown_market_result pattern: a neutral UTC clock plus the UNKNOWN
    # session marker downstream — NEVER a silent Asia/Shanghai assumption.
    config = get_market_config(market)
    tz = config.timezone if config is not None else "UTC"

    # date-only 的发布时间戳必须先按目标市场时区重锚，否则「北京零点」会被解释成
    # 纽约前一日盘中，把入场放到研报发布之前（全语料 50.4% 中招）。见
    # resolve_publication_instant 的说明。
    anchored_at = resolve_publication_instant(published_at, tz)

    # Use MarketCalendarTimingPolicy for deterministic timing
    policy = MarketCalendarTimingPolicy()
    result = policy.compute_timing(
        published_at=anchored_at,
        market=market,
        timezone=tz,
        intent_effective_at=intent_effective_at,
    )

    return ExecutionTiming(
        intent_published_at=result.intent_published_at,
        intent_effective_at=intent_effective_at,
        action_decision_at=result.intent_published_at,
        action_executable_at=result.action_executable_at,
        market=result.market,
        timezone=result.timezone,
        market_session_at_publish=MarketSession(result.market_session_at_publish),
        timing_policy_id=result.timing_policy_id,
    )


def _resolve_intent_effective_at(
    temporal_anchors: Optional[List[Any]],
) -> Optional[datetime]:
    """Resolve intent_effective_at from temporal anchors.

    Only an explicit ``effective_trade_at`` anchor — the time the KOL says the
    trade should take effect — populates this clock. ``mentioned_at`` anchors are
    historical/contextual dates merely *referenced* in the text; they are NOT the
    effective time. Conflating the two (the previous fallback) set
    ``intent_effective_at`` to a date *before* publication on every action —
    look-ahead that corrupts F8 backtest entry timing. When no effective_trade_at
    anchor exists, the effective time is left unresolved (None) rather than
    guessed from a referenced date.
    """
    if not temporal_anchors:
        return None

    for anchor in temporal_anchors:
        if getattr(anchor, "anchor_type", None) == "effective_trade_at":
            resolved = getattr(anchor, "resolved_time", None)
            if resolved:
                return resolved

    return None
