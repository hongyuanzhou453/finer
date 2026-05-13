"""Backtest Module — Portfolio simulation and performance analysis.

This module provides backtesting capabilities for KOL trade signals:
- Portfolio simulation with realistic costs
- Performance metrics calculation
- KOL attribution analysis
- Price data providers with caching
"""

from finer.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    PortfolioSimulator,
    PortfolioSnapshot,
    Position,
    Trade,
    PositionSide,
    ExitReason,
    run_simple_backtest,
)
from finer.backtest.prices import (
    PriceProvider,
    CachedPriceProvider,
    MockPriceProvider,
    MultiMarketPriceProvider,
    PriceCache,
    PriceCacheConfig,
    PriceSnapshotMaterializer,
)
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

__all__ = [
    # Engine
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "PortfolioSimulator",
    "PortfolioSnapshot",
    "Position",
    "Trade",
    "PositionSide",
    "ExitReason",
    "run_simple_backtest",
    # Price providers
    "PriceProvider",
    "CachedPriceProvider",
    "MockPriceProvider",
    "MultiMarketPriceProvider",
    "PriceCache",
    "PriceCacheConfig",
    "PriceSnapshotMaterializer",
    # Converter
    "trade_action_to_record",
    "trade_actions_to_records",
    "extract_tickers_from_actions",
    # Storage
    "save_backtest_result",
    "load_backtest_result",
    "list_backtest_results",
]
