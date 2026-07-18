"""Per-action backtest evaluator (F8).

Evaluates each TradeAction independently as a directional follow-trade and
produces the per-action ``schemas.trade_action.BacktestResult`` that the
opinions API reads. This deliberately bypasses the portfolio ``BacktestEngine``,
which is the wrong tool for per-action attribution: it deduplicates same-ticker
positions (16 actions on one index -> 1 trade), mis-routes bearish+close_long
into fresh shorts, and crashes on the mixed-timezone timestamps present in real
F5 data. Here every action gets its own independent entry/exit.

Semantics (aligned with the dashboard contract "return_pct = 方向校正后跟单
P&L，正=判断对"):
  - direction sign: bullish -> +1; bearish / risk_warning -> -1;
    neutral / watchlist -> not backtestable (None).
  - entry: close of the first trading day ON or AFTER the action's canonical
    execution clock (execution_timing.action_executable_at, falling back to
    intent_effective_at, then timestamp), timezone stripped to a plain date.
  - exit rules: stop / take-profit resolved per action from F4 policy hints
    stored in ``TradeAction.metadata`` (``stop_loss_pct`` /
    ``take_profit_pct``), falling back to the module defaults below
    (stop -10%, take-profit +20%).
  - evaluation window (R5, horizon-tiered): the time-exit window is resolved
    from the action's horizon hint (``TradeAction.time_horizon``, carried
    from F4 ``holding_period_hint``) via the schema single source of truth
    ``schemas.investment_intent.HORIZON_EXIT_TIERS`` /
    ``resolve_horizon_tier`` — short 30d / medium 90d / long 180d. A missing
    or unrecognized hint defaults to **long** (broker-research target prices
    conventionally imply ~12 months; judging them on a 30-day stopwatch is
    the R5 bug). A valid ``metadata["max_holding_days"]`` hint can only
    EXTEND the window (``max(tier, hint)``), never shrink it below the
    claim's horizon — F4 v1 emits a flat 30d placeholder for every
    position-taking action and must not silently re-truncate long calls.
    Callers that need the historical fixed 30-day window pass an explicit
    ``rules=ExitRules(...)``, which wins outright (legacy/compat path).
  - window audit: every result carries ``evaluation_window_days`` and a
    ``window_truncated`` flag (price data ended before the window
    completed — the END_OF_PERIOD case; never silently settled as if the
    window were complete). ``BacktestResult`` has no structured slot for
    these yet (schema gap), so they are encoded into the free-form
    ``backtest_period`` suffix ``[window=<N>d]`` / ``[window=<N>d
    truncated]`` and recoverable via :func:`parse_window_info`.
  - return_pct is a FRACTION (0.123 = +12.3%), net of a fixed round-trip cost
    (commission 0.1% x2 + slippage 0.05% x2 = 0.3%), consistent with existing
    fixtures and the frontend's x100 rendering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from finer.schemas.investment_intent import (
    HORIZON_EXIT_TIERS,
    resolve_horizon_tier,
)
from finer.schemas.trade_action import (
    BacktestResult,
    ExitReason,
    TradeAction,
    TradeDirection,
)

# Round-trip friction: commission 0.1% + slippage 0.05%, both ways.
ROUND_TRIP_COST = 0.003
STOP_LOSS_PCT = -0.10
TAKE_PROFIT_PCT = 0.20
#: Historical fixed window. Kept as the ``ExitRules`` dataclass default so the
#: explicit ``rules=`` path still means "the old 30-day evaluation"; actions
#: resolved via :func:`exit_rules_of` get the horizon-tiered window instead.
MAX_HOLDING_DAYS = 30

#: Machine-readable window suffix appended to ``backtest_period``.
_WINDOW_SUFFIX_RE = re.compile(r"\[window=(\d+)d( truncated)?\]\s*$")

_DIRECTION_SIGN = {
    TradeDirection.BULLISH: 1.0,
    TradeDirection.BEARISH: -1.0,
    TradeDirection.RISK_WARNING: -1.0,
}


@dataclass
class SkipInfo:
    """Why an action could not be evaluated."""

    reason: str  # "non_directional" | "no_price_data" | "no_entry_bar"


@dataclass(frozen=True)
class ExitRules:
    """Exit thresholds for one action's simulated follow-trade."""

    stop_loss_pct: float = STOP_LOSS_PCT
    take_profit_pct: float = TAKE_PROFIT_PCT
    max_holding_days: int = MAX_HOLDING_DAYS


def evaluation_window_days_of(action: TradeAction) -> int:
    """Horizon-tiered evaluation window in calendar days (R5).

    The base window comes from the schema single source of truth:
    ``HORIZON_EXIT_TIERS[resolve_horizon_tier(action.time_horizon)]``
    (short 30 / medium 90 / long 180; missing or unrecognized hint → long).

    A valid ``metadata["max_holding_days"]`` policy hint can only EXTEND the
    window, never shrink it below the claim's horizon: F4 v1 stamps a flat
    30-day placeholder on every position-taking action, and letting it win
    would silently re-truncate 12-month judgments back to 30 days — the exact
    R5 construction bug. Malformed hints are ignored, not raised.
    """
    tier_days = HORIZON_EXIT_TIERS[resolve_horizon_tier(action.time_horizon)]

    meta = action.metadata or {}
    hint = meta.get("max_holding_days")
    if isinstance(hint, int) and not isinstance(hint, bool) and hint > 0:
        return max(tier_days, hint)
    return tier_days


def exit_rules_of(action: TradeAction) -> ExitRules:
    """Resolve exit rules from F4 policy hints in metadata, else defaults.

    Stop / take-profit come from metadata hints or module defaults; the
    time-exit window is horizon-tiered via :func:`evaluation_window_days_of`.
    Malformed metadata values (wrong type, wrong sign) are ignored rather
    than raised — legacy actions must stay backtestable.
    """
    meta = action.metadata or {}

    stop = meta.get("stop_loss_pct")
    if not isinstance(stop, (int, float)) or isinstance(stop, bool) or stop >= 0:
        stop = STOP_LOSS_PCT

    target = meta.get("take_profit_pct")
    if not isinstance(target, (int, float)) or isinstance(target, bool) or target <= 0:
        target = TAKE_PROFIT_PCT

    return ExitRules(
        stop_loss_pct=float(stop),
        take_profit_pct=float(target),
        max_holding_days=evaluation_window_days_of(action),
    )


def parse_window_info(
    backtest_period: Optional[str],
) -> Tuple[Optional[int], Optional[bool]]:
    """Recover (evaluation_window_days, window_truncated) from a result.

    ``BacktestResult`` has no structured slot for the window audit fields
    (schema gap), so :func:`evaluate_action` encodes them as a
    ``[window=<N>d]`` / ``[window=<N>d truncated]`` suffix on
    ``backtest_period``. Legacy results without the suffix (and ``None``)
    return ``(None, None)`` — unknown, not "not truncated".
    """
    if not backtest_period:
        return None, None
    match = _WINDOW_SUFFIX_RE.search(backtest_period)
    if match is None:
        return None, None
    return int(match.group(1)), match.group(2) is not None


def direction_sign(action: TradeAction) -> Optional[float]:
    """+1 for long views, -1 for short/risk views, None if non-directional."""
    return _DIRECTION_SIGN.get(action.direction)


def entry_date_of(action: TradeAction) -> date:
    """Canonical execution clock, normalized to a plain (tz-stripped) date."""
    timing = action.execution_timing
    dt: Optional[datetime] = None
    if timing is not None:
        dt = timing.action_executable_at or timing.intent_effective_at
    if dt is None:
        dt = action.timestamp
    return dt.date()


def evaluate_action(
    action: TradeAction,
    closes: Sequence[Tuple[date, float]],
    rules: Optional[ExitRules] = None,
) -> Tuple[Optional[BacktestResult], Optional[SkipInfo]]:
    """Evaluate one action against a daily close series (ascending by date).

    Exit thresholds come from ``rules`` when given, otherwise from the
    action's F4 policy hints via :func:`exit_rules_of`.

    Returns (result, None) on success or (None, SkipInfo) when the action is
    non-directional or the series cannot support an entry.
    """
    sign = direction_sign(action)
    if sign is None:
        return None, SkipInfo("non_directional")
    if not closes:
        return None, SkipInfo("no_price_data")

    entry_date = entry_date_of(action)
    series: List[Tuple[date, float]] = [
        (d, c) for d, c in closes if c is not None and c > 0
    ]
    entry_idx = next((i for i, (d, _) in enumerate(series) if d >= entry_date), None)
    if entry_idx is None:
        return None, SkipInfo("no_entry_bar")
    if entry_idx == len(series) - 1:
        # No bars after entry — a same-day "round trip" would only measure
        # friction, not the call. Skip instead of emitting a noise result.
        return None, SkipInfo("insufficient_bars")

    resolved_rules = rules if rules is not None else exit_rules_of(action)

    entry_day, entry_price = series[entry_idx]
    deadline = entry_day + timedelta(days=resolved_rules.max_holding_days)

    exit_day, exit_price = entry_day, entry_price
    exit_reason = ExitReason.END_OF_PERIOD  # end-of-data fallback
    worst_pnl = 0.0

    for d, c in series[entry_idx + 1 :]:
        gross = sign * (c / entry_price - 1.0)
        worst_pnl = min(worst_pnl, gross)
        exit_day, exit_price = d, c
        if gross <= resolved_rules.stop_loss_pct:
            exit_reason = ExitReason.STOP_LOSS
            break
        if gross >= resolved_rules.take_profit_pct:
            exit_reason = ExitReason.TARGET_REACHED
            break
        if d >= deadline:
            exit_reason = ExitReason.TIME_EXIT
            break

    gross_return = sign * (exit_price / entry_price - 1.0)
    net_return = gross_return - ROUND_TRIP_COST

    # Window audit (R5): END_OF_PERIOD means the price series ran out before
    # the evaluation window completed (a bar at/after the deadline would have
    # produced TIME_EXIT, a threshold hit STOP_LOSS/TARGET_REACHED). Mark it
    # instead of silently settling a partial window as if it were complete.
    window_days = resolved_rules.max_holding_days
    window_truncated = exit_reason is ExitReason.END_OF_PERIOD
    window_note = (
        f"[window={window_days}d truncated]"
        if window_truncated
        else f"[window={window_days}d]"
    )

    return (
        BacktestResult(
            return_pct=round(net_return, 4),
            holding_days=(exit_day - entry_day).days,
            exit_reason=exit_reason,
            exit_price=round(float(exit_price), 4),
            max_drawdown_pct=round(worst_pnl, 4),
            backtest_timestamp=datetime.now(),
            backtest_period=(
                f"{entry_day.isoformat()} — {exit_day.isoformat()} {window_note}"
            ),
        ),
        None,
    )
