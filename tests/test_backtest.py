"""Tests for Backtest Engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from finer.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    PortfolioSimulator,
    Position,
    PositionSide,
    ExitReason,
    run_simple_backtest,
)


class TestBacktestConfig:
    """Test BacktestConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BacktestConfig()
        assert config.initial_capital == 100000.0
        assert config.default_position_pct == 0.1
        assert config.commission_pct == 0.001
        assert config.slippage_pct == 0.0005
        assert config.allow_short_selling is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = BacktestConfig(
            initial_capital=50000.0,
            default_position_pct=0.05,
            commission_pct=0.002,
        )
        assert config.initial_capital == 50000.0
        assert config.default_position_pct == 0.05
        assert config.commission_pct == 0.002


class TestPortfolioSimulator:
    """Test PortfolioSimulator."""

    def test_initialization(self):
        """Test simulator initialization."""
        simulator = PortfolioSimulator()
        assert simulator.cash == 100000.0
        assert len(simulator.positions) == 0
        assert len(simulator.trades) == 0

    def test_open_long_position(self):
        """Test opening a long position."""
        simulator = PortfolioSimulator()
        position = simulator.open_position(
            ticker="AAPL",
            side=PositionSide.LONG,
            price=150.0,
            date=datetime.now(),
        )

        assert position is not None
        assert position.ticker == "AAPL"
        assert position.side == PositionSide.LONG
        assert position.entry_price > 150.0  # Includes slippage
        assert "AAPL" in simulator.positions

    def test_open_short_position(self):
        """Test opening a short position."""
        config = BacktestConfig(allow_short_selling=True)
        simulator = PortfolioSimulator(config)
        position = simulator.open_position(
            ticker="TSLA",
            side=PositionSide.SHORT,
            price=200.0,
            date=datetime.now(),
        )

        assert position is not None
        assert position.side == PositionSide.SHORT

    def test_close_position(self):
        """Test closing a position."""
        simulator = PortfolioSimulator()
        simulator.open_position(
            ticker="AAPL",
            side=PositionSide.LONG,
            price=150.0,
            date=datetime.now(),
        )

        trade = simulator.close_position(
            ticker="AAPL",
            price=160.0,
            date=datetime.now(),
            exit_reason=ExitReason.MANUAL,
        )

        assert trade is not None
        assert trade.ticker == "AAPL"
        assert trade.return_pct > 0  # Profitable trade
        assert "AAPL" not in simulator.positions

    def test_stop_loss_exit(self):
        """Test stop loss triggered exit."""
        config = BacktestConfig(default_stop_loss_pct=0.1)
        simulator = PortfolioSimulator(config)
        position = simulator.open_position(
            ticker="AAPL",
            side=PositionSide.LONG,
            price=150.0,
            date=datetime.now(),
        )

        # Price drops below stop loss
        current_price = position.entry_price * 0.85  # 15% drop
        assert position.stop_loss_price is not None
        assert current_price < position.stop_loss_price

    def test_position_sizing(self):
        """Test position sizing constraints."""
        config = BacktestConfig(
            initial_capital=100000.0,
            default_position_pct=0.1,
            max_position_pct=0.25,
        )
        simulator = PortfolioSimulator(config)

        # Open position
        position = simulator.open_position(
            ticker="AAPL",
            side=PositionSide.LONG,
            price=150.0,
            date=datetime.now(),
        )

        # Position should be approximately 10% of capital
        expected_value = 100000.0 * 0.1
        assert position.entry_value < expected_value * 1.1  # Allow for costs

    def test_snapshot(self):
        """Test portfolio snapshot."""
        simulator = PortfolioSimulator()
        simulator.open_position(
            ticker="AAPL",
            side=PositionSide.LONG,
            price=150.0,
            date=datetime.now(),
        )

        snapshot = simulator.take_snapshot(
            date=datetime.now(),
            prices={"AAPL": 155.0},
        )

        assert snapshot.num_positions == 1
        assert snapshot.total_value > 0
        assert snapshot.date is not None


class TestBacktestEngine:
    """Test BacktestEngine."""

    @pytest.fixture
    def sample_price_data(self):
        """Create sample price data."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        data = []
        for date in dates:
            for ticker in ["AAPL", "MSFT"]:
                price = 150.0 + np.random.randn() * 5
                data.append({
                    "date": date,
                    "ticker": ticker,
                    "open": price,
                    "high": price * 1.02,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 1000000,
                })
        return pd.DataFrame(data)

    @pytest.fixture
    def sample_actions(self):
        """Create sample trade actions."""
        return [
            {
                "timestamp": "2024-01-05",
                "ticker": "AAPL",
                "direction": "bullish",
                "action_type": "long",
                "trade_action_id": "ta_001",
                "kol_id": "kol_001",
            },
            {
                "timestamp": "2024-01-15",
                "ticker": "MSFT",
                "direction": "bearish",
                "action_type": "short",
                "trade_action_id": "ta_002",
                "kol_id": "kol_001",
            },
        ]

    def test_run_backtest(self, sample_price_data, sample_actions):
        """Test running a full backtest."""
        engine = BacktestEngine()
        result = engine.run_backtest(
            actions=sample_actions,
            price_data=sample_price_data,
        )

        assert result is not None
        assert result.backtest_id is not None
        assert result.initial_capital == 100000.0
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)

    def test_backtest_with_config(self, sample_price_data, sample_actions):
        """Test backtest with custom config."""
        config = BacktestConfig(
            initial_capital=50000.0,
            commission_pct=0.002,
        )
        engine = BacktestEngine(config)
        result = engine.run_backtest(
            actions=sample_actions,
            price_data=sample_price_data,
        )

        assert result.initial_capital == 50000.0
        assert "commission_pct" in result.config

    def test_backtest_metrics(self, sample_price_data, sample_actions):
        """Test backtest metrics calculation."""
        engine = BacktestEngine()
        result = engine.run_backtest(
            actions=sample_actions,
            price_data=sample_price_data,
        )

        # Check all metrics are calculated
        assert hasattr(result, "total_return")
        assert hasattr(result, "annualized_return")
        assert hasattr(result, "volatility")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "max_drawdown")
        assert hasattr(result, "win_rate")

    def test_kol_attribution(self, sample_price_data, sample_actions):
        """Test KOL attribution in backtest."""
        engine = BacktestEngine()
        result = engine.run_backtest(
            actions=sample_actions,
            price_data=sample_price_data,
        )

        # Check KOL metrics if trades occurred
        if result.total_trades > 0:
            assert isinstance(result.kol_metrics, dict)

    def test_empty_actions(self, sample_price_data):
        """Test backtest with no actions."""
        engine = BacktestEngine()
        result = engine.run_backtest(
            actions=[],
            price_data=sample_price_data,
        )

        assert result.total_trades == 0


class TestRunSimpleBacktest:
    """Test convenience function."""

    def test_simple_backtest(self):
        """Test simple backtest wrapper."""
        price_data = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "ticker": ["AAPL"] * 10,
            "open": [150.0] * 10,
            "high": [152.0] * 10,
            "low": [148.0] * 10,
            "close": [150.0 + i for i in range(10)],
            "volume": [1000000] * 10,
        })

        actions = [{
            "timestamp": "2024-01-03",
            "ticker": "AAPL",
            "direction": "bullish",
            "action_type": "long",
        }]

        result = run_simple_backtest(actions, price_data)
        assert result is not None


# =============================================================================
# E2E Integration Tests — API Route
# =============================================================================


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
            "creator_id": "kol_e2e",
            "content_id": "content_e2e_001",
            "evidence_text": f"bullish on {ticker}",
        },
        "target": {"ticker": ticker},
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


def _make_price_rows(tickers: list[str], days: int = 30) -> list[dict]:
    """Build OHLCV price rows for tickers over N days."""
    rows = []
    base = datetime(2024, 1, 1)
    for d in range(days):
        date = base + timedelta(days=d)
        for ticker in tickers:
            price = 150.0 + d * 0.5
            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 1_000_000,
            })
    return rows


class TestBacktestE2E:
    """E2E integration tests for the backtest API route."""

    @pytest.fixture(autouse=True)
    def _setup_app(self, tmp_path):
        """Create a test app with isolated storage."""
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from finer.api.server import create_app

        app = create_app()
        self.client = TestClient(app)
        self.tmp_path = tmp_path

        # Patch F8_METRICS_DIR to use temp directory
        with patch("finer.api.routes.backtest.F8_METRICS_DIR", tmp_path):
            yield

    def test_run_canonical_backtest_returns_result_with_snapshots(self):
        """POST /run with canonical TradeActions + price_data → BacktestResult."""
        actions = [
            _make_canonical_action("AAPL", "bullish", "long", "2024-01-05T09:30:00"),
            _make_canonical_action("MSFT", "bullish", "long", "2024-01-10T09:30:00"),
        ]
        price_data = _make_price_rows(["AAPL", "MSFT"], days=30)

        resp = self.client.post("/api/backtest/run", json={
            "actions": actions,
            "price_data": price_data,
            "initial_capital": 100000.0,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

        data = body["data"]
        assert data["backtest_id"] is not None
        assert data["total_trades"] >= 0
        assert "portfolio_snapshots" in data
        assert "trades" in data
        assert "saved_to" in body

    def test_run_rejects_non_canonical_action_missing_intent_id(self):
        """POST /run rejects actions missing intent_id."""
        bad_action = _make_canonical_action()
        del bad_action["intent_id"]

        resp = self.client.post("/api/backtest/run", json={
            "actions": [bad_action],
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "F8_IN_001"
        assert "intent_id" in body["error"]["message"]

    def test_run_rejects_non_canonical_action_missing_policy_id(self):
        """POST /run rejects actions missing policy_id."""
        bad_action = _make_canonical_action()
        del bad_action["policy_id"]

        resp = self.client.post("/api/backtest/run", json={
            "actions": [bad_action],
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert "policy_id" in body["error"]["message"]

    def test_run_rejects_non_canonical_action_missing_evidence_span_ids(self):
        """POST /run rejects actions with empty evidence_span_ids."""
        bad_action = _make_canonical_action()
        bad_action["evidence_span_ids"] = []

        resp = self.client.post("/api/backtest/run", json={
            "actions": [bad_action],
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert "evidence_span_ids" in body["error"]["message"]

    def test_run_rejects_non_canonical_action_missing_execution_timing(self):
        """POST /run/actions missing execution_timing.action_executable_at."""
        bad_action = _make_canonical_action()
        del bad_action["execution_timing"]

        resp = self.client.post("/api/backtest/run", json={
            "actions": [bad_action],
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert "execution_timing" in body["error"]["message"]

    def test_run_rejects_missing_price_data(self):
        """POST /run without price_data raises F8_IN_001."""
        actions = [_make_canonical_action()]

        resp = self.client.post("/api/backtest/run", json={
            "actions": actions,
        })

        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "F8_IN_001"
        assert "price_data" in body["error"]["message"]

    def test_trade_actions_alias_accepted(self):
        """POST /run accepts 'trade_actions' as alias for 'actions'."""
        actions = [_make_canonical_action()]
        price_data = _make_price_rows(["AAPL"], 10)

        resp = self.client.post("/api/backtest/run", json={
            "trade_actions": actions,
            "price_data": price_data,
        })

        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestCompareEndpointReject:
    """POST /compare rejects non-canonical TradeActions."""

    @pytest.fixture(autouse=True)
    def _setup_app(self, tmp_path):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from finer.api.server import create_app

        app = create_app()
        self.client = TestClient(app)

        with patch("finer.api.routes.backtest.F8_METRICS_DIR", tmp_path):
            yield

    def test_compare_rejects_missing_intent_id(self):
        """POST /compare rejects actions missing intent_id."""
        bad_action = _make_canonical_action()
        del bad_action["intent_id"]

        resp = self.client.post("/api/backtest/compare", json={
            "kol_actions": {"kol_1": [bad_action]},
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "F8_IN_001"
        assert "intent_id" in body["error"]["message"]

    def test_compare_rejects_missing_policy_id(self):
        """POST /compare rejects actions missing policy_id."""
        bad_action = _make_canonical_action()
        del bad_action["policy_id"]

        resp = self.client.post("/api/backtest/compare", json={
            "kol_actions": {"kol_1": [bad_action]},
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert "policy_id" in body["error"]["message"]

    def test_compare_rejects_empty_evidence_span_ids(self):
        """POST /compare rejects actions with empty evidence_span_ids."""
        bad_action = _make_canonical_action()
        bad_action["evidence_span_ids"] = []

        resp = self.client.post("/api/backtest/compare", json={
            "kol_actions": {"kol_1": [bad_action]},
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert "evidence_span_ids" in body["error"]["message"]

    def test_compare_rejects_missing_execution_timing(self):
        """POST /compare rejects actions missing execution_timing."""
        bad_action = _make_canonical_action()
        del bad_action["execution_timing"]

        resp = self.client.post("/api/backtest/compare", json={
            "kol_actions": {"kol_1": [bad_action]},
            "price_data": _make_price_rows(["AAPL"], 10),
        })

        assert resp.status_code == 400
        body = resp.json()
        assert "execution_timing" in body["error"]["message"]
