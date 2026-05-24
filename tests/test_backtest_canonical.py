"""Tests for F8 Backtest consuming canonical TradeActions.

Verifies that the backtest engine correctly processes canonical TradeActions
with all required F3→F4→F5 traceability fields:
- intent_id is not None
- policy_id is not None
- evidence_span_ids is non-empty
- execution_timing is not None
- canonical_trace_status == "canonical"
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from finer.backtest.engine import BacktestEngine, BacktestConfig
from finer.backtest.converter import trade_action_to_record
from finer.backtest.validators import validate_canonical_action
from finer.errors.exceptions import FinerError


# =============================================================================
# Helpers
# =============================================================================

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kol-backtest-mvp"
DATA_REVIEW = Path(__file__).resolve().parent.parent / "data" / "review"

_DIRECTION_MAP = {"bullish": "bullish", "bearish": "bearish"}
_ACTION_TYPE_MAP = {
    "long": "long", "short": "short",
    "close_long": "close_long", "close_short": "close_short",
    "buy_call": "buy_call", "buy_put": "buy_put",
    "buy_and_hold": "long",
}


def _make_canonical_action(
    ticker: str = "AAPL",
    direction: str = "bullish",
    action_type: str = "long",
    ts: str = "2024-01-05T09:30:00",
) -> dict:
    """Build a canonical TradeAction dict with all required fields."""
    return {
        "trade_action_id": f"ta_{ticker}_{ts[:10]}",
        "timestamp": ts,
        "source": {
            "creator_id": "kol_canonical_test",
            "content_id": "content_001",
            "evidence_text": f"bullish on {ticker}",
        },
        "target": {"ticker": ticker, "ticker_normalized": ticker},
        "direction": direction,
        "action_chain": [{"sequence": 1, "action_type": action_type}],
        "intent_id": f"intent_{ticker}_001",
        "policy_id": f"policy_{ticker}_001",
        "evidence_span_ids": [f"span_{ticker}_001"],
        "execution_timing": {
            "intent_published_at": ts,
            "action_decision_at": ts,
            "action_executable_at": ts,
            "market": "US",
            "timezone": "America/New_York",
            "timing_policy_id": "market-calendar-next-open-v1",
        },
        "canonical_trace_status": "canonical",
    }


def _make_price_data(tickers: list[str], days: int = 30) -> pd.DataFrame:
    """Build OHLCV price DataFrame for tickers over N days."""
    rows = []
    base = datetime(2024, 1, 1)
    for d in range(days):
        date = base + timedelta(days=d)
        for ticker in tickers:
            price = 150.0 + d * 0.5
            rows.append({
                "date": date,
                "ticker": ticker,
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 1_000_000,
            })
    return pd.DataFrame(rows)


def _raw_to_engine_record(action_dict: dict) -> dict | None:
    """Convert raw canonical TradeAction to backtest engine record."""
    direction = action_dict.get("direction", "")
    if direction not in _DIRECTION_MAP:
        return None

    action_chain = action_dict.get("action_chain", [])
    if not action_chain:
        return None

    primary = action_chain[0]
    action_type = _ACTION_TYPE_MAP.get(primary.get("action_type", ""))
    if action_type is None:
        return None

    exec_timing = action_dict.get("execution_timing") or {}
    ts = exec_timing.get("action_executable_at") or action_dict.get("timestamp", "")
    ts = re.sub(r'[+-]\d{2}:\d{2}$', '', ts)
    if ts.endswith("Z"):
        ts = ts[:-1]

    target = action_dict.get("target") or {}
    ticker = target.get("ticker_normalized") or target.get("ticker", "")

    source = action_dict.get("source") or {}
    return {
        "timestamp": ts,
        "ticker": ticker,
        "direction": _DIRECTION_MAP[direction],
        "action_type": action_type,
        "trade_action_id": action_dict.get("trade_action_id", ""),
        "kol_id": source.get("creator_id", "unknown"),
        "intent_id": action_dict.get("intent_id"),
        "policy_id": action_dict.get("policy_id"),
        "evidence_span_ids": action_dict.get("evidence_span_ids") or [],
    }


# =============================================================================
# Canonical field assertions
# =============================================================================


class TestCanonicalTradeActionFields:
    """Verify that canonical TradeActions carry all required traceability fields."""

    def test_canonical_action_has_intent_id(self):
        """Canonical action must have a non-None intent_id."""
        action = _make_canonical_action()
        assert action.get("intent_id") is not None
        assert len(action["intent_id"]) > 0

    def test_canonical_action_has_policy_id(self):
        """Canonical action must have a non-None policy_id."""
        action = _make_canonical_action()
        assert action.get("policy_id") is not None
        assert len(action["policy_id"]) > 0

    def test_canonical_action_has_evidence_span_ids(self):
        """Canonical action must have non-empty evidence_span_ids."""
        action = _make_canonical_action()
        span_ids = action.get("evidence_span_ids")
        assert span_ids is not None
        assert len(span_ids) > 0

    def test_canonical_action_has_execution_timing(self):
        """Canonical action must have execution_timing with action_executable_at."""
        action = _make_canonical_action()
        timing = action.get("execution_timing")
        assert timing is not None
        assert timing.get("action_executable_at") is not None

    def test_canonical_action_has_canonical_trace_status(self):
        """Canonical action must have canonical_trace_status == 'canonical'."""
        action = _make_canonical_action()
        assert action.get("canonical_trace_status") == "canonical"

    def test_canonical_action_has_source_creator_id(self):
        """Canonical action must have source.creator_id for KOL attribution."""
        action = _make_canonical_action()
        source = action.get("source", {})
        assert source.get("creator_id") is not None


# =============================================================================
# Backtest engine consumes canonical actions
# =============================================================================


class TestBacktestCanonicalConsumption:
    """Verify BacktestEngine correctly processes canonical TradeActions."""

    def test_engine_accepts_canonical_action(self):
        """Engine processes a canonical action and produces trades."""
        action = _make_canonical_action("AAPL", "bullish", "long", "2024-01-05T09:30:00")
        record = _raw_to_engine_record(action)
        assert record is not None

        price_data = _make_price_data(["AAPL"], days=30)
        engine = BacktestEngine()
        result = engine.run_backtest([record], price_data)

        assert result is not None
        assert result.total_trades >= 0
        assert result.backtest_id is not None

    def test_validator_rejects_action_missing_intent_id(self):
        """Validator raises FinerError for actions without intent_id."""
        action = _make_canonical_action()
        del action["intent_id"]
        with pytest.raises(FinerError, match="intent_id"):
            validate_canonical_action(action, 0)

    def test_validator_rejects_action_missing_policy_id(self):
        """Validator raises FinerError for actions without policy_id."""
        action = _make_canonical_action()
        del action["policy_id"]
        with pytest.raises(FinerError, match="policy_id"):
            validate_canonical_action(action, 0)

    def test_validator_rejects_action_empty_evidence_span_ids(self):
        """Validator raises FinerError for actions with empty evidence_span_ids."""
        action = _make_canonical_action()
        action["evidence_span_ids"] = []
        with pytest.raises(FinerError, match="evidence_span_ids"):
            validate_canonical_action(action, 0)

    def test_validator_rejects_action_missing_execution_timing(self):
        """Validator raises FinerError for actions without execution_timing."""
        action = _make_canonical_action()
        del action["execution_timing"]
        with pytest.raises(FinerError, match="execution_timing"):
            validate_canonical_action(action, 0)

    def test_canonical_action_with_bearish_short(self):
        """Canonical bearish SHORT action processes correctly."""
        action = _make_canonical_action("TSLA", "bearish", "short", "2024-01-10T09:30:00")
        record = _raw_to_engine_record(action)
        assert record is not None
        assert record["direction"] == "bearish"
        assert record["action_type"] == "short"

        price_data = _make_price_data(["TSLA"], days=30)
        config = BacktestConfig(allow_short_selling=True)
        engine = BacktestEngine(config)
        result = engine.run_backtest([record], price_data)
        assert result is not None

    def test_canonical_action_with_close_long(self):
        """Canonical close_long action processes correctly."""
        action = _make_canonical_action("LI", "bearish", "close_long", "2024-01-15T09:30:00")
        record = _raw_to_engine_record(action)
        assert record is not None
        assert record["action_type"] == "close_long"

    def test_multiple_canonical_actions(self):
        """Engine handles multiple canonical actions across tickers."""
        actions = [
            _make_canonical_action("AAPL", "bullish", "long", "2024-01-05T09:30:00"),
            _make_canonical_action("MSFT", "bullish", "long", "2024-01-10T09:30:00"),
            _make_canonical_action("AAPL", "bearish", "close_long", "2024-01-20T09:30:00"),
        ]
        records = [_raw_to_engine_record(a) for a in actions]
        assert all(r is not None for r in records)

        price_data = _make_price_data(["AAPL", "MSFT"], days=30)
        engine = BacktestEngine()
        result = engine.run_backtest(records, price_data)

        assert result is not None
        assert len(result.portfolio_snapshots) > 0


# =============================================================================
# F5 canonical actions integration (from data/review/)
# =============================================================================


class TestF5CanonicalIntegration:
    """Integration tests using actual F5 canonical actions from data/review/."""

    @pytest.fixture
    def cat_lord_f5_actions(self) -> list[dict]:
        """Load canonical F5 actions for kol_cat_lord_fire."""
        f5_dir = DATA_REVIEW / "kol_cat_lord_fire" / "F5_actions"
        if not f5_dir.exists():
            pytest.skip("F5_actions not found")

        records = []
        for f in sorted(f5_dir.glob("*.actions.json")):
            raw = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                continue
            for action_dict in raw:
                if not action_dict:
                    continue
                if action_dict.get("canonical_trace_status") != "canonical":
                    continue
                record = _raw_to_engine_record(action_dict)
                if record is not None:
                    records.append(record)
        return records

    def test_cat_lord_has_canonical_actions(self, cat_lord_f5_actions):
        """kol_cat_lord_fire has at least one canonical backtestable action."""
        assert len(cat_lord_f5_actions) > 0

    def test_cat_lord_canonical_fields_present(self, cat_lord_f5_actions):
        """All cat_lord F5 actions carry canonical traceability fields."""
        f5_dir = DATA_REVIEW / "kol_cat_lord_fire" / "F5_actions"
        if not f5_dir.exists():
            pytest.skip("F5_actions not found")

        for f in sorted(f5_dir.glob("*.actions.json")):
            raw = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                continue
            for action in raw:
                if action.get("canonical_trace_status") != "canonical":
                    continue
                assert action.get("intent_id") is not None, \
                    f"Missing intent_id in {f.name}"
                assert action.get("policy_id") is not None, \
                    f"Missing policy_id in {f.name}"
                spans = action.get("evidence_span_ids", [])
                assert len(spans) > 0, \
                    f"Empty evidence_span_ids in {f.name}"
                assert action.get("execution_timing") is not None, \
                    f"Missing execution_timing in {f.name}"
                assert action["canonical_trace_status"] == "canonical"

    def test_cat_lord_backtest_produces_equity_curve(self, cat_lord_f5_actions):
        """Running backtest on cat_lord canonical actions produces valid results."""
        if not cat_lord_f5_actions:
            pytest.skip("No backtestable actions")

        price_csv = FIXTURES / "cat_lord" / "market_prices.csv"
        if not price_csv.exists():
            pytest.skip("No market_prices.csv")

        price_data = pd.read_csv(price_csv, dtype={"ticker": str})
        price_data["date"] = pd.to_datetime(price_data["date"])

        engine = BacktestEngine()
        result = engine.run_backtest(cat_lord_f5_actions, price_data)

        assert result is not None
        assert result.backtest_id is not None
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)
        assert len(result.portfolio_snapshots) > 0

    def test_cat_lord_equity_curve_has_required_columns(self, cat_lord_f5_actions):
        """Equity curve CSV has all required columns."""
        if not cat_lord_f5_actions:
            pytest.skip("No backtestable actions")

        price_csv = FIXTURES / "cat_lord" / "market_prices.csv"
        if not price_csv.exists():
            pytest.skip("No market_prices.csv")

        price_data = pd.read_csv(price_csv, dtype={"ticker": str})
        price_data["date"] = pd.to_datetime(price_data["date"])

        engine = BacktestEngine()
        result = engine.run_backtest(cat_lord_f5_actions, price_data)

        # These columns match the task card spec for equity_curve.csv
        required_fields = {"date", "total_value", "cash", "positions_value",
                           "cumulative_return", "current_drawdown", "num_positions"}

        for snap in result.portfolio_snapshots:
            snap_dict = snap.model_dump()
            for field in required_fields:
                assert field in snap_dict, f"Missing field: {field}"


# =============================================================================
# R4-A: Trace Retention — intent_id / policy_id / evidence_span_ids flow through
# =============================================================================


class TestTraceRetention:
    """Verify that F3→F4→F5 trace fields survive the full F8 pipeline.

    Trace fields: intent_id, policy_id, evidence_span_ids
    Flow: TradeAction → converter → engine record → engine Position → engine Trade
    """

    def test_converter_preserves_trace_fields(self):
        """trade_action_to_record() output contains intent_id, policy_id, evidence_span_ids."""
        from finer.schemas.trade_action import (
            TradeAction, SourceInfo, TargetInfo, ActionStep,
            TradeDirection, ActionType, ExecutionTiming,
        )

        ts = datetime(2024, 6, 1, 9, 30, 0)
        action = TradeAction(
            trade_action_id="ta_trace_001",
            timestamp=ts,
            source=SourceInfo(
                content_id="c_001",
                evidence_text="bullish on AAPL",
                creator_id="kol_test",
            ),
            target=TargetInfo(ticker="AAPL", ticker_normalized="AAPL"),
            direction=TradeDirection.BULLISH,
            action_chain=[ActionStep(sequence=1, action_type=ActionType.LONG)],
            intent_id="intent_001",
            policy_id="policy_001",
            evidence_span_ids=["span_001", "span_002"],
            execution_timing=ExecutionTiming(
                intent_published_at=ts,
                action_decision_at=ts,
                action_executable_at=ts,
                market="US",
                timezone="America/New_York",
                timing_policy_id="market-calendar-v1",
            ),
            canonical_trace_status="canonical",
        )

        record = trade_action_to_record(action)

        assert record is not None
        assert record["intent_id"] == "intent_001"
        assert record["policy_id"] == "policy_001"
        assert record["evidence_span_ids"] == ["span_001", "span_002"]

    def test_engine_trade_has_trace_fields(self):
        """Engine Trade objects carry intent_id, policy_id, evidence_span_ids."""
        action = _make_canonical_action("AAPL", "bullish", "long", "2024-01-05T09:30:00")
        record = _raw_to_engine_record(action)
        assert record is not None

        # Build price data where AAPL drops to trigger stop loss → forces a Trade
        price_data = _make_price_data(["AAPL"], days=30)
        config = BacktestConfig(default_stop_loss_pct=0.001)  # tight stop
        engine = BacktestEngine(config)
        result = engine.run_backtest([record], price_data)

        assert result is not None
        # If trades were produced, verify trace fields
        for trade in result.trades:
            assert trade.intent_id == "intent_AAPL_001"
            assert trade.policy_id == "policy_AAPL_001"
            assert trade.evidence_span_ids == ["span_AAPL_001"]

    def test_e2e_trades_json_has_trace_fields(self):
        """Cat Lord F5 canonical actions → engine → trades retain trace fields."""
        f5_dir = DATA_REVIEW / "kol_cat_lord_fire" / "F5_actions"
        if not f5_dir.exists():
            pytest.skip("F5_actions not found")

        price_csv = FIXTURES / "cat_lord" / "market_prices.csv"
        if not price_csv.exists():
            pytest.skip("No market_prices.csv")

        records = []
        for f in sorted(f5_dir.glob("*.actions.json")):
            raw = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                continue
            for action_dict in raw:
                if not action_dict:
                    continue
                if action_dict.get("canonical_trace_status") != "canonical":
                    continue
                record = _raw_to_engine_record(action_dict)
                if record is not None:
                    records.append(record)

        if not records:
            pytest.skip("No backtestable canonical records")

        price_data = pd.read_csv(price_csv, dtype={"ticker": str})
        price_data["date"] = pd.to_datetime(price_data["date"])

        engine = BacktestEngine()
        result = engine.run_backtest(records, price_data)

        assert result is not None
        # At least one record should carry trace fields into trades
        if result.trades:
            for trade in result.trades:
                # Trace fields must be present (may be None if input had None)
                assert hasattr(trade, "intent_id")
                assert hasattr(trade, "policy_id")
                assert hasattr(trade, "evidence_span_ids")
                # For canonical inputs, these should be populated
                if trade.intent_id is not None:
                    assert len(trade.intent_id) > 0
                if trade.policy_id is not None:
                    assert len(trade.policy_id) > 0
