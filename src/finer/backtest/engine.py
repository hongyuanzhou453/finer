"""Backtest Engine — Portfolio simulation and performance metrics.

This module provides:
1. Portfolio simulation from TradeAction history
2. Performance metrics calculation (returns, drawdown, Sharpe)
3. KOL timeline backtesting
4. Trade execution simulation

Key Design Decisions:
- All prices must be provided externally (no live data fetching)
- Slippage and transaction costs are configurable
- Short selling is supported with borrowing costs
- Results are deterministic given same inputs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class PositionSide(str, Enum):
    """Position side for tracking."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class ExitReason(str, Enum):
    """Reason for exiting a position."""
    TARGET_REACHED = "target_reached"
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"
    SIGNAL_REVERSAL = "signal_reversal"
    MANUAL = "manual"
    END_OF_PERIOD = "end_of_period"


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class BacktestConfig:
    """Backtest configuration."""
    # Capital
    initial_capital: float = 100000.0

    # Position sizing
    default_position_pct: float = 0.1  # 10% of portfolio per trade
    max_position_pct: float = 0.25  # Max 25% in single asset
    max_total_exposure: float = 1.0  # Max 100% total exposure

    # Costs
    commission_pct: float = 0.001  # 0.1% commission
    slippage_pct: float = 0.0005  # 0.05% slippage
    borrowing_rate_annual: float = 0.02  # 2% annual borrowing cost for shorts

    # Risk management
    default_stop_loss_pct: float = 0.1  # 10% stop loss
    default_take_profit_pct: float = 0.2  # 20% take profit
    max_holding_days: int = 30  # Force exit after 30 days

    # Simulation
    allow_short_selling: bool = True
    allow_fractional_shares: bool = True
    settlement_delay_days: int = 0  # T+0 settlement


# =============================================================================
# Data Models
# =============================================================================

class Position(BaseModel):
    """A single position in the portfolio."""
    model_config = ConfigDict(strict=True)

    ticker: str = Field(..., description="Ticker symbol")
    side: PositionSide = Field(..., description="Long or short")
    quantity: float = Field(..., gt=0, description="Number of shares")
    entry_price: float = Field(..., gt=0, description="Entry price")
    entry_date: datetime = Field(..., description="Entry date")
    entry_value: float = Field(..., description="Total value at entry")

    # Targets
    stop_loss_price: Optional[float] = Field(None, description="Stop loss price")
    take_profit_price: Optional[float] = Field(None, description="Take profit price")
    target_exit_date: Optional[datetime] = Field(None, description="Target exit date")

    # Metadata
    trade_action_id: Optional[str] = Field(None, description="Source trade action ID")
    kol_id: Optional[str] = Field(None, description="Source KOL ID")

    # Trace fields (R4-A)
    intent_id: Optional[str] = Field(None, description="Source F3 intent ID")
    policy_id: Optional[str] = Field(None, description="Source F4 policy ID")
    evidence_span_ids: List[str] = Field(default_factory=list, description="Source F2 evidence span IDs")

    def current_value(self, current_price: float) -> float:
        """Calculate current position value."""
        if self.side == PositionSide.LONG:
            return self.quantity * current_price
        else:  # SHORT
            # Short: profit when price drops
            return self.entry_value + (self.entry_price - current_price) * self.quantity

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL."""
        if self.side == PositionSide.LONG:
            return (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            return (self.entry_price - current_price) * self.quantity

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized PnL as percentage."""
        if self.entry_value == 0:
            return 0.0
        return self.unrealized_pnl(current_price) / self.entry_value


class Trade(BaseModel):
    """A completed trade."""
    model_config = ConfigDict(strict=True)

    trade_id: str = Field(..., description="Unique trade ID")
    ticker: str = Field(..., description="Ticker symbol")
    side: PositionSide = Field(..., description="Long or short")
    quantity: float = Field(..., gt=0, description="Number of shares")

    entry_date: datetime = Field(..., description="Entry date")
    entry_price: float = Field(..., gt=0, description="Entry price")
    exit_date: datetime = Field(..., description="Exit date")
    exit_price: float = Field(..., gt=0, description="Exit price")

    # PnL
    gross_pnl: float = Field(..., description="Gross PnL before costs")
    commission: float = Field(..., description="Total commission")
    slippage: float = Field(..., description="Total slippage cost")
    borrowing_cost: float = Field(0.0, description="Borrowing cost for shorts")
    net_pnl: float = Field(..., description="Net PnL after all costs")
    return_pct: float = Field(..., description="Return percentage")

    # Exit info
    exit_reason: ExitReason = Field(..., description="Why the position was closed")
    holding_days: int = Field(..., description="Days held")

    # Metadata
    trade_action_id: Optional[str] = Field(None, description="Source trade action ID")
    kol_id: Optional[str] = Field(None, description="Source KOL ID")

    # Trace fields (R4-A)
    intent_id: Optional[str] = Field(None, description="Source F3 intent ID")
    policy_id: Optional[str] = Field(None, description="Source F4 policy ID")
    evidence_span_ids: List[str] = Field(default_factory=list, description="Source F2 evidence span IDs")


class PortfolioSnapshot(BaseModel):
    """Portfolio state at a point in time."""
    model_config = ConfigDict(strict=True)

    date: datetime = Field(..., description="Snapshot date")
    cash: float = Field(..., description="Cash balance")
    positions_value: float = Field(..., description="Total positions market value")
    total_value: float = Field(..., description="Total portfolio value")

    # PnL
    daily_pnl: float = Field(0.0, description="PnL for this day")
    cumulative_pnl: float = Field(0.0, description="Cumulative PnL")
    cumulative_return: float = Field(0.0, description="Cumulative return %")

    # Drawdown
    peak_value: float = Field(..., description="Peak portfolio value")
    current_drawdown: float = Field(0.0, description="Current drawdown %")

    # Position counts
    num_positions: int = Field(0, description="Number of open positions")
    long_exposure: float = Field(0.0, description="Total long exposure")
    short_exposure: float = Field(0.0, description="Total short exposure")


class BacktestResult(BaseModel):
    """Complete backtest result."""
    model_config = ConfigDict(strict=True)

    # Metadata
    backtest_id: str = Field(..., description="Unique backtest ID")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    run_timestamp: datetime = Field(default_factory=datetime.now)

    # Configuration
    initial_capital: float = Field(..., description="Starting capital")
    config: Dict[str, Any] = Field(default_factory=dict, description="Config used")

    # Performance metrics
    total_return: float = Field(..., description="Total return %")
    annualized_return: float = Field(..., description="Annualized return %")
    volatility: float = Field(..., description="Annualized volatility %")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    sortino_ratio: float = Field(..., description="Sortino ratio")
    calmar_ratio: float = Field(..., description="Calmar ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown %")
    max_drawdown_duration: int = Field(..., description="Max drawdown duration in days")

    # Trade statistics
    total_trades: int = Field(0, description="Total number of trades")
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = Field(0.0, description="Win rate %")
    avg_win: float = Field(0.0, description="Average winning trade %")
    avg_loss: float = Field(0.0, description="Average losing trade %")
    profit_factor: float = Field(0.0, description="Profit factor (gross win / gross loss)")
    avg_holding_days: float = Field(0.0, description="Average holding period")

    # Risk metrics
    value_at_risk_95: float = Field(0.0, description="95% VaR")
    expected_shortfall: float = Field(0.0, description="Expected shortfall (CVaR)")
    max_consecutive_losses: int = Field(0, description="Max consecutive losing trades")

    # Time series data
    portfolio_snapshots: List[PortfolioSnapshot] = Field(
        default_factory=list, description="Daily portfolio snapshots"
    )
    trades: List[Trade] = Field(default_factory=list, description="All completed trades")

    # KOL attribution (if applicable)
    kol_metrics: Dict[str, Dict[str, float]] = Field(
        default_factory=dict, description="Per-KOL performance metrics"
    )


# =============================================================================
# Portfolio Simulator
# =============================================================================

class PortfolioSimulator:
    """Simulates portfolio with positions and cash management."""

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}  # ticker -> Position
        self.trades: List[Trade] = []
        self.snapshots: List[PortfolioSnapshot] = []
        self.peak_value = self.config.initial_capital
        self._trade_counter = 0

    def get_position(self, ticker: str) -> Optional[Position]:
        """Get current position for a ticker."""
        return self.positions.get(ticker)

    def get_total_value(self, prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        positions_value = sum(
            pos.current_value(prices.get(ticker, pos.entry_price))
            for ticker, pos in self.positions.items()
        )
        return self.cash + positions_value

    def get_exposure(self, total_value: float) -> Tuple[float, float]:
        """Calculate long and short exposure as % of portfolio."""
        if total_value <= 0:
            return 0.0, 0.0

        long_exposure = 0.0
        short_exposure = 0.0

        for pos in self.positions.values():
            pct = pos.entry_value / total_value
            if pos.side == PositionSide.LONG:
                long_exposure += pct
            else:
                short_exposure += pct

        return long_exposure, short_exposure

    def open_position(
        self,
        ticker: str,
        side: PositionSide,
        price: float,
        date: datetime,
        position_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        trade_action_id: Optional[str] = None,
        kol_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        evidence_span_ids: Optional[List[str]] = None,
    ) -> Optional[Position]:
        """Open a new position."""
        # Check if position already exists
        if ticker in self.positions:
            logger.warning(f"Position already exists for {ticker}, skipping")
            return None

        # Determine position size
        total_value = self.get_total_value({ticker: price})
        position_pct = position_pct or self.config.default_position_pct
        position_pct = min(position_pct, self.config.max_position_pct)

        # Check total exposure
        long_exp, short_exp = self.get_exposure(total_value)
        new_exposure = long_exp + short_exp + position_pct
        if new_exposure > self.config.max_total_exposure:
            logger.debug(f"Would exceed max exposure, reducing position size")
            position_pct = max(0.01, self.config.max_total_exposure - long_exp - short_exp)

        # Calculate quantity
        position_value = total_value * position_pct
        quantity = position_value / price

        # Apply slippage
        actual_price = price * (1 + self.config.slippage_pct) if side == PositionSide.LONG \
                       else price * (1 - self.config.slippage_pct)

        # Calculate commission
        commission = position_value * self.config.commission_pct

        # Check cash availability
        required_cash = position_value + commission
        if side == PositionSide.LONG and self.cash < required_cash:
            # Reduce position to available cash
            position_value = (self.cash - commission) / (1 + self.config.commission_pct)
            quantity = position_value / actual_price

        # Execute trade
        if side == PositionSide.LONG:
            self.cash -= (quantity * actual_price + commission)
        else:  # SHORT
            self.cash -= commission  # Only commission from cash
            # Proceeds from short sale are tracked separately

        # Create position
        position = Position(
            ticker=ticker,
            side=side,
            quantity=quantity,
            entry_price=actual_price,
            entry_date=date,
            entry_value=quantity * actual_price,
            stop_loss_price=actual_price * (1 - (stop_loss_pct or self.config.default_stop_loss_pct))
                          if side == PositionSide.LONG else
                          actual_price * (1 + (stop_loss_pct or self.config.default_stop_loss_pct)),
            take_profit_price=actual_price * (1 + (take_profit_pct or self.config.default_take_profit_pct))
                             if side == PositionSide.LONG else
                             actual_price * (1 - (take_profit_pct or self.config.default_take_profit_pct)),
            target_exit_date=date + timedelta(days=self.config.max_holding_days),
            trade_action_id=trade_action_id,
            kol_id=kol_id,
            intent_id=intent_id,
            policy_id=policy_id,
            evidence_span_ids=evidence_span_ids or [],
        )

        self.positions[ticker] = position
        logger.debug(f"Opened {side.value} position in {ticker}: {quantity:.2f} shares @ ${actual_price:.2f}")

        return position

    def close_position(
        self,
        ticker: str,
        price: float,
        date: datetime,
        exit_reason: ExitReason,
    ) -> Optional[Trade]:
        """Close an existing position."""
        position = self.positions.get(ticker)
        if not position:
            return None

        # Apply slippage
        actual_price = price * (1 - self.config.slippage_pct) if position.side == PositionSide.LONG \
                       else price * (1 + self.config.slippage_pct)

        # Calculate PnL
        if position.side == PositionSide.LONG:
            gross_pnl = (actual_price - position.entry_price) * position.quantity
            proceeds = position.quantity * actual_price
        else:  # SHORT
            gross_pnl = (position.entry_price - actual_price) * position.quantity
            proceeds = position.entry_value + gross_pnl  # Return collateral + profit

        # Calculate costs
        commission = position.quantity * actual_price * self.config.commission_pct
        slippage_cost = abs(actual_price - price) * position.quantity

        # Borrowing cost for shorts
        borrowing_cost = 0.0
        if position.side == PositionSide.SHORT:
            days_held = (date - position.entry_date).days
            borrowing_cost = position.entry_value * (self.config.borrowing_rate_annual / 365) * days_held

        # Net PnL
        net_pnl = gross_pnl - commission - slippage_cost - borrowing_cost

        # Update cash
        if position.side == PositionSide.LONG:
            self.cash += proceeds - commission
        else:
            self.cash += proceeds - commission - borrowing_cost

        # Create trade record
        self._trade_counter += 1
        trade = Trade(
            trade_id=f"trade_{self._trade_counter:04d}",
            ticker=ticker,
            side=position.side,
            quantity=position.quantity,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=date,
            exit_price=actual_price,
            gross_pnl=gross_pnl,
            commission=commission,
            slippage=slippage_cost,
            borrowing_cost=borrowing_cost,
            net_pnl=net_pnl,
            return_pct=net_pnl / position.entry_value if position.entry_value > 0 else 0.0,
            exit_reason=exit_reason,
            holding_days=(date - position.entry_date).days,
            trade_action_id=position.trade_action_id,
            kol_id=position.kol_id,
            intent_id=position.intent_id,
            policy_id=position.policy_id,
            evidence_span_ids=position.evidence_span_ids,
        )

        # Remove position
        del self.positions[ticker]
        self.trades.append(trade)

        logger.debug(f"Closed {position.side.value} position in {ticker}: "
                    f"PnL=${net_pnl:.2f} ({trade.return_pct*100:.1f}%)")

        return trade

    def take_snapshot(self, date: datetime, prices: Dict[str, float]) -> PortfolioSnapshot:
        """Take a portfolio snapshot for the given date."""
        positions_value = sum(
            pos.current_value(prices.get(ticker, pos.entry_price))
            for ticker, pos in self.positions.items()
        )
        total_value = self.cash + positions_value

        # Update peak
        if total_value > self.peak_value:
            self.peak_value = total_value

        # Calculate drawdown
        drawdown = (self.peak_value - total_value) / self.peak_value if self.peak_value > 0 else 0.0

        # Previous snapshot for daily PnL
        daily_pnl = 0.0
        if self.snapshots:
            prev = self.snapshots[-1]
            daily_pnl = total_value - prev.total_value

        snapshot = PortfolioSnapshot(
            date=date,
            cash=self.cash,
            positions_value=positions_value,
            total_value=total_value,
            daily_pnl=daily_pnl,
            cumulative_pnl=total_value - self.config.initial_capital,
            cumulative_return=(total_value / self.config.initial_capital - 1),
            peak_value=self.peak_value,
            current_drawdown=drawdown,
            num_positions=len(self.positions),
            long_exposure=self.get_exposure(total_value)[0],
            short_exposure=self.get_exposure(total_value)[1],
        )

        self.snapshots.append(snapshot)
        return snapshot


# =============================================================================
# Backtest Engine
# =============================================================================

class BacktestEngine:
    """Main backtest engine for KOL timeline simulation."""

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    def run_backtest(
        self,
        actions: List[Dict[str, Any]],
        price_data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Run backtest on a list of trade actions.

        Args:
            actions: List of trade action dicts with keys:
                - timestamp: ISO datetime string
                - ticker: Ticker symbol
                - direction: 'bullish', 'bearish', etc.
                - action_type: 'long', 'short', 'close_long', etc.
                - trade_action_id: Optional ID for tracking
                - kol_id: Optional KOL ID for attribution
            price_data: DataFrame with columns:
                - date: datetime
                - ticker: str
                - open, high, low, close: float
                - volume: int (optional)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            BacktestResult with all metrics and history
        """
        import uuid

        # Initialize
        simulator = PortfolioSimulator(self.config)

        # Prepare price data
        price_data = price_data.copy()
        if 'date' in price_data.columns:
            price_data['date'] = pd.to_datetime(price_data['date'])
        price_data = price_data.set_index(['date', 'ticker'])

        # Determine date range
        if start_date is None:
            start_date = price_data.index.get_level_values('date').min()
        if end_date is None:
            end_date = price_data.index.get_level_values('date').max()

        # Convert actions to DataFrame and sort
        actions_df = pd.DataFrame(actions)
        if not actions_df.empty:
            actions_df['timestamp'] = pd.to_datetime(actions_df['timestamp'])
            actions_df = actions_df.sort_values('timestamp')

        # Daily simulation
        current_date = pd.Timestamp(start_date).normalize()
        end_date = pd.Timestamp(end_date).normalize()

        while current_date <= end_date:
            # Get today's prices
            try:
                today_prices = price_data.loc[current_date]
                price_map = today_prices['close'].to_dict()
            except KeyError:
                # No data for this date, skip
                current_date += timedelta(days=1)
                continue

            # Check existing positions for exits
            positions_to_close = []
            for ticker, pos in simulator.positions.items():
                current_price = price_map.get(ticker)
                if current_price is None:
                    continue

                # Check stop loss
                if pos.side == PositionSide.LONG:
                    if pos.stop_loss_price and current_price <= pos.stop_loss_price:
                        positions_to_close.append((ticker, ExitReason.STOP_LOSS))
                        continue
                else:  # SHORT
                    if pos.stop_loss_price and current_price >= pos.stop_loss_price:
                        positions_to_close.append((ticker, ExitReason.STOP_LOSS))
                        continue

                # Check take profit
                if pos.side == PositionSide.LONG:
                    if pos.take_profit_price and current_price >= pos.take_profit_price:
                        positions_to_close.append((ticker, ExitReason.TARGET_REACHED))
                        continue
                else:  # SHORT
                    if pos.take_profit_price and current_price <= pos.take_profit_price:
                        positions_to_close.append((ticker, ExitReason.TARGET_REACHED))
                        continue

                # Check time exit
                if pos.target_exit_date and current_date >= pd.Timestamp(pos.target_exit_date):
                    positions_to_close.append((ticker, ExitReason.TIME_EXIT))

            # Execute exits
            for ticker, reason in positions_to_close:
                simulator.close_position(ticker, price_map[ticker], current_date, reason)

            # Process actions for this date
            if not actions_df.empty:
                today_actions = actions_df[
                    (actions_df['timestamp'] >= current_date) &
                    (actions_df['timestamp'] < current_date + timedelta(days=1))
                ]

                for _, action in today_actions.iterrows():
                    ticker = action.get('ticker', '')
                    if ticker not in price_map:
                        continue

                    direction = action.get('direction', '')
                    action_type = action.get('action_type', '')

                    # Handle action
                    if direction == 'bullish' or action_type in ['long', 'buy_call']:
                        simulator.open_position(
                            ticker=ticker,
                            side=PositionSide.LONG,
                            price=price_map[ticker],
                            date=current_date,
                            trade_action_id=action.get('trade_action_id'),
                            kol_id=action.get('kol_id'),
                            intent_id=action.get('intent_id'),
                            policy_id=action.get('policy_id'),
                            evidence_span_ids=action.get('evidence_span_ids'),
                        )
                    elif direction == 'bearish' or action_type in ['short', 'buy_put']:
                        if self.config.allow_short_selling:
                            simulator.open_position(
                                ticker=ticker,
                                side=PositionSide.SHORT,
                                price=price_map[ticker],
                                date=current_date,
                                trade_action_id=action.get('trade_action_id'),
                                kol_id=action.get('kol_id'),
                                intent_id=action.get('intent_id'),
                                policy_id=action.get('policy_id'),
                                evidence_span_ids=action.get('evidence_span_ids'),
                            )
                    elif action_type in ['close_long', 'close_short']:
                        if ticker in simulator.positions:
                            simulator.close_position(
                                ticker=ticker,
                                price=price_map[ticker],
                                date=current_date,
                                exit_reason=ExitReason.SIGNAL_REVERSAL,
                            )

            # Take snapshot
            simulator.take_snapshot(current_date, price_map)

            current_date += timedelta(days=1)

        # Close remaining positions at end
        final_prices = {}
        try:
            final_data = price_data.loc[end_date]
            final_prices = final_data['close'].to_dict()
        except KeyError:
            pass

        for ticker, pos in list(simulator.positions.items()):
            if ticker in final_prices:
                simulator.close_position(
                    ticker=ticker,
                    price=final_prices[ticker],
                    date=end_date,
                    exit_reason=ExitReason.END_OF_PERIOD,
                )

        # Calculate metrics
        result = self._compute_metrics(
            simulator=simulator,
            start_date=start_date,
            end_date=end_date,
            backtest_id=str(uuid.uuid4()),
        )

        return result

    def _compute_metrics(
        self,
        simulator: PortfolioSimulator,
        start_date: datetime,
        end_date: datetime,
        backtest_id: str,
    ) -> BacktestResult:
        """Compute all performance metrics from simulation results."""
        snapshots = simulator.snapshots
        trades = simulator.trades

        if not snapshots:
            # No data, return empty result
            return BacktestResult(
                backtest_id=backtest_id,
                start_date=start_date,
                end_date=end_date,
                initial_capital=self.config.initial_capital,
                total_return=0.0,
                annualized_return=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_duration=0,
            )

        # Returns series
        returns = pd.Series([s.daily_pnl / s.total_value for s in snapshots[1:]])
        cumulative_return = snapshots[-1].cumulative_return

        # Annualization factor
        days = (end_date - start_date).days
        years = max(days / 365.25, 1/365.25)
        annualized_return = (1 + cumulative_return) ** (1 / years) - 1

        # Volatility
        volatility = returns.std() * np.sqrt(252) if len(returns) > 1 else 0.0

        # Sharpe ratio (assuming 0% risk-free rate for simplicity)
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0.0

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_dev = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 1 else volatility
        sortino_ratio = annualized_return / downside_dev if downside_dev > 0 else 0.0

        # Max drawdown
        max_drawdown = max(s.current_drawdown for s in snapshots)

        # Max drawdown duration
        max_dd_duration = 0
        current_dd_duration = 0
        for s in snapshots:
            if s.current_drawdown > 0:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0

        # Calmar ratio
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0

        # Trade statistics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl < 0]

        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        avg_win = np.mean([t.return_pct for t in winning_trades]) if winning_trades else 0.0
        avg_loss = np.mean([t.return_pct for t in losing_trades]) if losing_trades else 0.0

        gross_wins = sum(t.net_pnl for t in winning_trades)
        gross_losses = abs(sum(t.net_pnl for t in losing_trades))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf') if gross_wins > 0 else 0.0

        avg_holding_days = np.mean([t.holding_days for t in trades]) if trades else 0.0

        # Risk metrics
        var_95 = np.percentile(returns, 5) if len(returns) > 0 else 0.0
        es_returns = returns[returns <= var_95] if len(returns) > 0 else pd.Series()
        expected_shortfall = es_returns.mean() if len(es_returns) > 0 else var_95

        # Max consecutive losses
        max_consec_losses = 0
        current_consec = 0
        for t in trades:
            if t.net_pnl < 0:
                current_consec += 1
                max_consec_losses = max(max_consec_losses, current_consec)
            else:
                current_consec = 0

        # KOL attribution
        kol_metrics = {}
        kol_trades: Dict[str, List[Trade]] = {}
        for t in trades:
            if t.kol_id:
                if t.kol_id not in kol_trades:
                    kol_trades[t.kol_id] = []
                kol_trades[t.kol_id].append(t)

        for kol_id, kol_trade_list in kol_trades.items():
            kol_total_pnl = sum(t.net_pnl for t in kol_trade_list)
            kol_win_rate = len([t for t in kol_trade_list if t.net_pnl > 0]) / len(kol_trade_list)
            kol_avg_return = np.mean([t.return_pct for t in kol_trade_list])
            kol_metrics[kol_id] = {
                'total_trades': len(kol_trade_list),
                'total_pnl': kol_total_pnl,
                'win_rate': kol_win_rate,
                'avg_return': kol_avg_return,
            }

        return BacktestResult(
            backtest_id=backtest_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.config.initial_capital,
            config={
                'commission_pct': self.config.commission_pct,
                'slippage_pct': self.config.slippage_pct,
                'default_position_pct': self.config.default_position_pct,
                'max_position_pct': self.config.max_position_pct,
            },
            total_return=cumulative_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            avg_holding_days=avg_holding_days,
            value_at_risk_95=var_95,
            expected_shortfall=expected_shortfall,
            max_consecutive_losses=max_consec_losses,
            portfolio_snapshots=snapshots,
            trades=trades,
            kol_metrics=kol_metrics,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def run_simple_backtest(
    actions: List[Dict[str, Any]],
    price_data: pd.DataFrame,
    initial_capital: float = 100000.0,
) -> BacktestResult:
    """Run a simple backtest with default configuration.

    Args:
        actions: List of trade action dicts
        price_data: DataFrame with OHLCV data
        initial_capital: Starting capital

    Returns:
        BacktestResult
    """
    config = BacktestConfig(initial_capital=initial_capital)
    engine = BacktestEngine(config)
    return engine.run_backtest(actions, price_data)
