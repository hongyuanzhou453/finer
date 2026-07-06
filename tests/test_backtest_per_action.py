"""Tests for the F8 per-action backtest evaluator."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from finer.backtest.per_action import (
    MAX_HOLDING_DAYS,
    ROUND_TRIP_COST,
    evaluate_action,
)
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


def make_action(direction: TradeDirection, ts: datetime) -> TradeAction:
    return TradeAction(
        trade_action_id=f"ta-test-{direction.value}",
        timestamp=ts,
        source=SourceInfo(content_id="c-1", evidence_text="test", creator_id="k1"),
        target=TargetInfo(ticker="TEST", market="CN"),
        direction=direction,
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
    action = make_action(TradeDirection.BULLISH, ENTRY)
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
    from finer.backtest.per_action import ExitRules

    action = make_action(TradeDirection.BULLISH, ENTRY)
    action.metadata["take_profit_pct"] = 0.50
    closes = series(D0, [100, 106])
    result, skip = evaluate_action(action, closes, rules=ExitRules(take_profit_pct=0.05))
    assert skip is None and result is not None
    assert result.exit_reason == ExitReason.TARGET_REACHED
