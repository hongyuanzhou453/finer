"""Tests for the F8 per-action backtest evaluator."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from finer.backtest.per_action import (
    MAX_HOLDING_DAYS,
    ROUND_TRIP_COST,
    ExitRules,
    evaluate_action,
    evaluation_window_days_of,
    parse_window_info,
)
from finer.schemas.investment_intent import HORIZON_EXIT_TIERS
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    ExitReason,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)


def make_action(
    direction: TradeDirection,
    ts: datetime,
    time_horizon: str | None = None,
) -> TradeAction:
    return TradeAction(
        trade_action_id=f"ta-test-{direction.value}",
        timestamp=ts,
        source=SourceInfo(content_id="c-1", evidence_text="test", creator_id="k1"),
        target=TargetInfo(ticker="TEST", market="CN"),
        direction=direction,
        time_horizon=time_horizon,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG
                if direction == TradeDirection.BULLISH
                else ActionType.SHORT,
                trigger_type=TriggerType.MANUAL,
                trigger_condition="test",
            )
        ],
    )


def series(start: date, closes: list[float]) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), c) for i, c in enumerate(closes)]


ENTRY = datetime(2026, 3, 2, 9, 30)
D0 = date(2026, 3, 2)


def test_bullish_take_profit():
    action = make_action(TradeDirection.BULLISH, ENTRY)
    closes = series(D0, [100, 105, 112, 121, 130])
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED
    assert result.return_pct == round(0.21 - ROUND_TRIP_COST, 4)
    assert result.holding_days == 3


def test_bullish_stop_loss():
    action = make_action(TradeDirection.BULLISH, ENTRY)
    closes = series(D0, [100, 96, 89, 95])
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.STOP_LOSS
    assert result.return_pct == round(-0.11 - ROUND_TRIP_COST, 4)


def test_bearish_direction_adjusted_win():
    """A bearish call profits when the price falls (direction-adjusted P&L)."""
    action = make_action(TradeDirection.BEARISH, ENTRY)
    closes = series(D0, [100, 92, 79])  # falls 21% -> short-view take profit
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED
    assert result.return_pct == round(0.21 - ROUND_TRIP_COST, 4)


def test_time_exit_after_max_holding():
    """Short-horizon actions keep the historical 30-day time exit."""
    action = make_action(TradeDirection.BULLISH, ENTRY, time_horizon="short_term")
    closes = series(D0, [100.0] + [101.0] * (MAX_HOLDING_DAYS + 5))
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TIME_EXIT
    assert result.holding_days == MAX_HOLDING_DAYS


def test_entry_uses_first_bar_on_or_after_clock():
    """Entry snaps forward to the first trading day >= the execution clock."""
    action = make_action(TradeDirection.BULLISH, ENTRY)
    closes = series(D0 + timedelta(days=3), [100, 125])  # series starts after clock
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED


def test_neutral_not_backtestable():
    action = make_action(TradeDirection.NEUTRAL, ENTRY)
    result, skip = evaluate_action(action, series(D0, [100, 101]))
    assert result is None and skip is not None
    assert skip.reason == "non_directional"


def test_no_price_data():
    action = make_action(TradeDirection.BULLISH, ENTRY)
    result, skip = evaluate_action(action, [])
    assert result is None and skip is not None
    assert skip.reason == "no_price_data"


def test_no_entry_bar_when_series_ends_before_clock():
    action = make_action(TradeDirection.BULLISH, ENTRY)
    closes = series(D0 - timedelta(days=10), [100, 101, 102])
    result, skip = evaluate_action(action, closes)
    assert result is None and skip is not None
    assert skip.reason == "no_entry_bar"


def test_insufficient_bars_after_entry_is_skipped():
    """A single bar at/after entry would only measure friction — skip it."""
    action = make_action(TradeDirection.BULLISH, ENTRY)
    closes = series(D0 - timedelta(days=5), [100, 101, 102, 103, 104, 105])
    # only the last bar (D0) is >= entry date
    result, skip = evaluate_action(action, closes[: 6])
    assert closes[5][0] == D0
    assert result is None and skip is not None
    assert skip.reason == "insufficient_bars"


def test_end_of_data_falls_back_to_end_of_period():
    action = make_action(TradeDirection.BULLISH, ENTRY)
    closes = series(D0, [100, 103, 105])  # no threshold hit, data ends
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.END_OF_PERIOD
    assert result.return_pct == round(0.05 - ROUND_TRIP_COST, 4)


def test_metadata_exit_rules_override_defaults():
    """F4 policy hints in metadata drive stop/target/holding thresholds."""
    action = make_action(TradeDirection.BULLISH, ENTRY)
    action.metadata["stop_loss_pct"] = -0.05
    action.metadata["take_profit_pct"] = 0.08
    action.metadata["max_holding_days"] = 10
    closes = series(D0, [100, 103, 109, 120])  # +9% on day 2 -> custom target hit
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED
    assert result.holding_days == 2

    tighter_stop = make_action(TradeDirection.BULLISH, ENTRY)
    tighter_stop.metadata["stop_loss_pct"] = -0.05
    closes = series(D0, [100, 94, 99])  # -6% breaches -5% custom stop, not -10%
    result, skip = evaluate_action(tighter_stop, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.STOP_LOSS


def test_malformed_metadata_exit_rules_fall_back():
    """Wrong-typed or wrong-signed metadata hints are ignored, not raised."""
    action = make_action(TradeDirection.BULLISH, ENTRY)
    action.metadata["stop_loss_pct"] = "tight"
    action.metadata["take_profit_pct"] = -0.2
    action.metadata["max_holding_days"] = True
    closes = series(D0, [100, 105, 112, 121, 130])
    result, skip = evaluate_action(action, closes)
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED  # default +20%
    assert result.holding_days == 3


def test_explicit_rules_argument_wins():
    action = make_action(TradeDirection.BULLISH, ENTRY)
    action.metadata["take_profit_pct"] = 0.50
    closes = series(D0, [100, 106])
    result, skip = evaluate_action(action, closes, rules=ExitRules(take_profit_pct=0.05))
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED


# ---------------------------------------------------------------------------
# R5: horizon-tiered evaluation windows (short 30 / medium 90 / long 180)
# ---------------------------------------------------------------------------


def flat_series(days: int) -> list[tuple[date, float]]:
    """Entry bar + `days` flat bars: never hits stop/target thresholds."""
    return series(D0, [100.0] + [101.0] * days)


def test_horizon_tier_windows_drive_time_exit():
    """Each horizon tier settles on its own window, not a flat 30 days."""
    for hint, tier in (
        ("intraday", "short"),
        ("short_term", "short"),
        ("medium_term", "medium"),
        ("long_term", "long"),
    ):
        expected = HORIZON_EXIT_TIERS[tier]
        action = make_action(TradeDirection.BULLISH, ENTRY, time_horizon=hint)
        assert evaluation_window_days_of(action) == expected
        result, skip = evaluate_action(action, flat_series(expected + 5))
        assert skip is None and result is not None, hint
        assert result.exit_reason == ExitReason.TIME_EXIT, hint
        assert result.holding_days == expected, hint
        assert parse_window_info(result.backtest_period) == (expected, False)


def test_missing_hint_defaults_to_long_window():
    """No horizon hint -> long/180d (broker-research semantics), not 30d."""
    action = make_action(TradeDirection.BULLISH, ENTRY)  # time_horizon=None
    long_days = HORIZON_EXIT_TIERS["long"]
    assert evaluation_window_days_of(action) == long_days

    result, skip = evaluate_action(action, flat_series(long_days + 5))
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TIME_EXIT
    assert result.holding_days == long_days  # NOT the historical 30

    # A 30-day-shaped series no longer time-exits: it is a truncated window.
    result, skip = evaluate_action(action, flat_series(MAX_HOLDING_DAYS + 5))
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.END_OF_PERIOD


def test_unrecognized_hint_defaults_to_long_window():
    for hint in ("review_required", "1 week", "unknown"):
        action = make_action(TradeDirection.BULLISH, ENTRY, time_horizon=hint)
        assert evaluation_window_days_of(action) == HORIZON_EXIT_TIERS["long"]


def test_window_truncated_flag_when_data_ends_early():
    """Data ending before the window is marked, never settled as complete."""
    action = make_action(TradeDirection.BULLISH, ENTRY, time_horizon="long_term")
    result, skip = evaluate_action(action, flat_series(40))  # << 180d window
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.END_OF_PERIOD
    window_days, truncated = parse_window_info(result.backtest_period)
    assert window_days == HORIZON_EXIT_TIERS["long"]
    assert truncated is True


def test_threshold_exit_before_data_end_is_not_truncated():
    """A take-profit inside a short series is a complete evaluation."""
    action = make_action(TradeDirection.BULLISH, ENTRY, time_horizon="long_term")
    result, skip = evaluate_action(action, series(D0, [100, 112, 121]))
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED
    assert parse_window_info(result.backtest_period) == (
        HORIZON_EXIT_TIERS["long"],
        False,
    )


def test_metadata_days_extend_but_never_shrink_window():
    """F4 v1 flat 30d hint must not re-truncate long-horizon judgments."""
    # The R5 core case: canonical actions all carry max_holding_days=30.
    flat_hint = make_action(TradeDirection.BULLISH, ENTRY, time_horizon="long_term")
    flat_hint.metadata["max_holding_days"] = 30
    assert evaluation_window_days_of(flat_hint) == HORIZON_EXIT_TIERS["long"]

    # An explicitly longer policy hint (more patience) is honored.
    patient = make_action(TradeDirection.BULLISH, ENTRY, time_horizon="short_term")
    patient.metadata["max_holding_days"] = 200
    assert evaluation_window_days_of(patient) == 200

    # Malformed hints are ignored, not raised.
    broken = make_action(TradeDirection.BULLISH, ENTRY, time_horizon="medium_term")
    broken.metadata["max_holding_days"] = True
    assert evaluation_window_days_of(broken) == HORIZON_EXIT_TIERS["medium"]


def test_explicit_rules_pin_legacy_30d_window():
    """Old-data path: callers can still request the historical fixed window."""
    action = make_action(TradeDirection.BULLISH, ENTRY)  # no hint -> long tier
    closes = flat_series(MAX_HOLDING_DAYS + 5)
    result, skip = evaluate_action(action, closes, rules=ExitRules())
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TIME_EXIT
    assert result.holding_days == MAX_HOLDING_DAYS
    assert parse_window_info(result.backtest_period) == (MAX_HOLDING_DAYS, False)


def test_parse_window_info_handles_legacy_periods():
    assert parse_window_info(None) == (None, None)
    assert parse_window_info("") == (None, None)
    # Pre-R5 results carry no suffix: unknown, not "not truncated".
    assert parse_window_info("2026-03-02 — 2026-03-05") == (None, None)
    assert parse_window_info("2026-03-02 — 2026-03-05 [window=90d]") == (90, False)
    assert parse_window_info(
        "2026-03-02 — 2026-09-01 [window=180d truncated]"
    ) == (180, True)
