"""Tests for PriceSnapshotMaterializer, TradeAction converter, and backtest storage."""

from __future__ import annotations

import json
import pytest
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from finer.backtest.prices import PriceSnapshotMaterializer
from finer.backtest.converter import (
    trade_action_to_record,
    trade_actions_to_records,
    extract_tickers_from_actions,
)
from finer.backtest.storage import (
    save_backtest_result,
    load_backtest_result,
    list_backtest_results,
)
from finer.schemas.trade_action import (
    TradeAction,
    TradeDirection,
    ActionType,
    SourceInfo,
    TargetInfo,
    ActionStep,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_trade_action(
    ticker: str = "000001.SZ",
    direction: TradeDirection = TradeDirection.BULLISH,
    action_type: ActionType = ActionType.LONG,
    creator_id: str = "kol_001",
    content_id: str = "content_001",
    timestamp: datetime | None = None,
) -> TradeAction:
    return TradeAction(
        timestamp=timestamp or datetime(2024, 6, 15, 9, 30),
        source=SourceInfo(creator_id=creator_id, content_id=content_id, evidence_text="buy now"),
        target=TargetInfo(ticker=ticker),
        direction=direction,
        action_chain=[ActionStep(sequence=1, action_type=action_type)],
    )


# =============================================================================
# PriceSnapshotMaterializer
# =============================================================================


class TestPriceSnapshotMaterializer:
    """Test PriceSnapshotMaterializer."""

    def test_materialize_empty_tickers(self):
        """Empty ticker list returns empty DataFrame."""
        mat = PriceSnapshotMaterializer()
        df = mat.materialize([], "2024-01-01", "2024-01-31")
        assert df.empty
        assert list(df.columns) == ["date", "ticker", "open", "high", "low", "close", "volume"]

    def test_materialize_from_actions_empty(self):
        """Empty actions list returns empty DataFrame."""
        mat = PriceSnapshotMaterializer()
        df = mat.materialize_from_actions([])
        assert df.empty

    @patch("finer.backtest.prices.PriceSnapshotMaterializer.materialize")
    def test_materialize_from_actions_expands_range(self, mock_mat):
        """materialize_from_actions expands date range by lookback/lookahead."""
        mock_mat.return_value = pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])

        mat = PriceSnapshotMaterializer()
        actions = [
            {"timestamp": "2024-06-15", "ticker": "000001.SZ"},
            {"timestamp": "2024-06-20", "ticker": "600519.SH"},
        ]
        mat.materialize_from_actions(actions, lookback_days=10, lookahead_days=30)

        mock_mat.assert_called_once()
        call_args = mock_mat.call_args
        assert sorted(call_args[0][0]) == ["000001.SZ", "600519.SH"]
        # start = 2024-06-15 - 10 days = 2024-06-05
        assert call_args[0][1] == "2024-06-05"
        # end = 2024-06-20 + 30 days = 2024-07-20
        assert call_args[0][2] == "2024-07-20"


# =============================================================================
# TradeAction Converter
# =============================================================================


class TestTradeActionConverter:
    """Test TradeAction → backtest record conversion."""

    def test_bullish_long(self):
        """Bullish LONG action converts correctly."""
        action = _make_trade_action(direction=TradeDirection.BULLISH, action_type=ActionType.LONG)
        record = trade_action_to_record(action)

        assert record is not None
        assert record["ticker"] == "000001.SZ"
        assert record["direction"] == "bullish"
        assert record["action_type"] == "long"
        assert record["kol_id"] == "kol_001"

    def test_bearish_short(self):
        """Bearish SHORT action converts correctly."""
        action = _make_trade_action(direction=TradeDirection.BEARISH, action_type=ActionType.SHORT)
        record = trade_action_to_record(action)

        assert record is not None
        assert record["direction"] == "bearish"
        assert record["action_type"] == "short"

    def test_neutral_skipped(self):
        """Neutral direction returns None."""
        action = _make_trade_action(direction=TradeDirection.NEUTRAL)
        record = trade_action_to_record(action)
        assert record is None

    def test_watch_skipped(self):
        """Watch direction returns None."""
        action = _make_trade_action(direction=TradeDirection.WATCHLIST)
        record = trade_action_to_record(action)
        assert record is None

    def test_close_long(self):
        """Close long converts correctly."""
        action = _make_trade_action(
            direction=TradeDirection.BEARISH,
            action_type=ActionType.CLOSE_LONG,
        )
        record = trade_action_to_record(action)
        assert record is not None
        assert record["action_type"] == "close_long"

    def test_buy_and_hold(self):
        """Buy and hold maps to 'long'."""
        action = _make_trade_action(
            direction=TradeDirection.BULLISH,
            action_type=ActionType.BUY_AND_HOLD,
        )
        record = trade_action_to_record(action)
        assert record is not None
        assert record["action_type"] == "long"

    def test_effective_trade_at_used(self):
        """effective_trade_at takes precedence over timestamp."""
        effective = datetime(2024, 7, 1, 10, 0)
        action = _make_trade_action(timestamp=datetime(2024, 6, 15, 9, 30))
        action.effective_trade_at = effective

        record = trade_action_to_record(action)
        assert record is not None
        assert record["timestamp"] == effective.isoformat()

    def test_batch_conversion(self):
        """Batch conversion filters and converts correctly."""
        actions = [
            _make_trade_action(direction=TradeDirection.BULLISH, action_type=ActionType.LONG),
            _make_trade_action(direction=TradeDirection.NEUTRAL),  # skipped
            _make_trade_action(direction=TradeDirection.BEARISH, action_type=ActionType.SHORT),
        ]
        records = trade_actions_to_records(actions)
        assert len(records) == 2

    def test_extract_tickers(self):
        """Extract unique tickers from actions."""
        a1 = _make_trade_action(ticker="000001.SZ")
        a2 = _make_trade_action(ticker="600519.SH")
        a3 = _make_trade_action(ticker="000001.SZ")  # duplicate

        tickers = extract_tickers_from_actions([a1, a2, a3])
        assert tickers == ["000001.SZ", "600519.SH"]


# =============================================================================
# Backtest Storage
# =============================================================================


class TestBacktestStorage:
    """Test BacktestResult persistence."""

    def test_save_and_load(self, tmp_path):
        """Save and load a backtest result."""
        with patch("finer.backtest.storage.BACKTESTS_DIR", tmp_path):
            result_dict = {
                "backtest_id": "test-001",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T00:00:00",
                "run_timestamp": "2024-07-01T12:00:00",
                "total_return": 0.15,
                "sharpe_ratio": 1.2,
                "max_drawdown": 0.08,
                "total_trades": 10,
                "portfolio_snapshots": [{"date": "2024-01-01", "total_value": 100000}],
            }

            saved = save_backtest_result(result_dict, include_snapshots=True)
            assert saved.exists()

            loaded = load_backtest_result("test-001")
            assert loaded is not None
            assert loaded["backtest_id"] == "test-001"
            assert loaded["total_return"] == 0.15

    def test_save_without_snapshots(self, tmp_path):
        """Save without snapshots omits portfolio_snapshots."""
        with patch("finer.backtest.storage.BACKTESTS_DIR", tmp_path):
            result_dict = {
                "backtest_id": "test-002",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T00:00:00",
                "total_return": 0.10,
                "sharpe_ratio": 0.8,
                "max_drawdown": 0.05,
                "total_trades": 5,
                "portfolio_snapshots": [{"date": "2024-01-01", "total_value": 100000}],
            }

            save_backtest_result(result_dict, include_snapshots=False)
            loaded = load_backtest_result("test-002")
            assert loaded is not None
            assert "portfolio_snapshots" not in loaded

    def test_index_updated(self, tmp_path):
        """Index is updated after save."""
        with patch("finer.backtest.storage.BACKTESTS_DIR", tmp_path):
            result_dict = {
                "backtest_id": "test-003",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T00:00:00",
                "total_return": 0.20,
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.06,
                "total_trades": 8,
            }

            save_backtest_result(result_dict)
            results = list_backtest_results()
            assert len(results) == 1
            assert results[0]["backtest_id"] == "test-003"

    def test_deduplicate_on_save(self, tmp_path):
        """Saving same backtest_id updates existing entry."""
        with patch("finer.backtest.storage.BACKTESTS_DIR", tmp_path):
            result_dict = {
                "backtest_id": "test-004",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T00:00:00",
                "total_return": 0.10,
                "sharpe_ratio": 0.8,
                "max_drawdown": 0.05,
                "total_trades": 5,
            }

            save_backtest_result(result_dict)
            result_dict["total_return"] = 0.25
            save_backtest_result(result_dict)

            results = list_backtest_results()
            assert len(results) == 1
            assert results[0]["total_return"] == 0.25

    def test_load_nonexistent(self, tmp_path):
        """Load nonexistent backtest returns None."""
        with patch("finer.backtest.storage.BACKTESTS_DIR", tmp_path):
            result = load_backtest_result("nonexistent")
            assert result is None

    def test_list_empty(self, tmp_path):
        """List on empty dir returns empty list."""
        with patch("finer.backtest.storage.BACKTESTS_DIR", tmp_path):
            results = list_backtest_results()
            assert results == []
