"""Price Data Provider — Market data fetching with caching.

This module provides:
1. PriceProvider protocol for abstract price data access
2. CachedPriceProvider using Finance-Skills API
3. MockPriceProvider for explicit opt-in fallback

Key Design:
- Thread-safe caching with TTL
- No silent mock fallback in production (fallback_to_mock=False by default)
- Support for multi-market (US/HK/CN/Crypto)
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Protocol, Tuple

import numpy as np
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# Price Provider Protocol
# =============================================================================

class PriceProvider(Protocol):
    """Protocol for price data providers."""

    def get_price(self, ticker: str, date: str) -> Optional[float]:
        """Get price for a ticker on a specific date.

        Args:
            ticker: Ticker symbol (e.g., 'AAPL', 'BTC-USD')
            date: ISO date string (e.g., '2024-01-15')

        Returns:
            Price as float, or None if unavailable
        """
        ...

    def get_prices(
        self,
        ticker: str,
        start: str,
        end: str
    ) -> List[Tuple[str, float]]:
        """Get price series for a ticker over a date range.

        Args:
            ticker: Ticker symbol
            start: Start date (ISO format)
            end: End date (ISO format)

        Returns:
            List of (date, price) tuples
        """
        ...

    def get_latest_price(self, ticker: str) -> Optional[float]:
        """Get latest available price for a ticker.

        Args:
            ticker: Ticker symbol

        Returns:
            Latest price, or None if unavailable
        """
        ...


# =============================================================================
# Cache Implementation
# =============================================================================

@dataclass
class PriceCacheEntry:
    """Cache entry for price data."""
    price: float
    timestamp: float
    ttl: int  # seconds

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.timestamp > self.ttl


@dataclass
class PriceCacheConfig:
    """Configuration for price caching."""
    default_ttl: int = 3600  # 1 hour
    historical_ttl: int = 86400  # 24 hours (historical data rarely changes)
    realtime_ttl: int = 60  # 1 minute
    max_entries: int = 1000  # Prevent unbounded growth


class PriceCache:
    """Thread-safe price cache with TTL."""

    def __init__(self, config: Optional[PriceCacheConfig] = None):
        self.config = config or PriceCacheConfig()
        self._cache: Dict[str, PriceCacheEntry] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, ticker: str, date: Optional[str] = None) -> str:
        """Generate cache key."""
        if date:
            return f"{ticker}:{date}"
        return f"{ticker}:latest"

    def get(self, ticker: str, date: Optional[str] = None) -> Optional[float]:
        """Get cached price if available and not expired."""
        key = self._make_key(ticker, date)
        entry = self._cache.get(key)
        if entry and not entry.is_expired():
            return entry.price
        return None

    def set(
        self,
        ticker: str,
        price: float,
        date: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """Set cached price."""
        # Cleanup if exceeding max entries
        if len(self._cache) >= self.config.max_entries:
            self._cleanup_expired()

        key = self._make_key(ticker, date)
        ttl = ttl or (self.config.historical_ttl if date else self.config.default_ttl)
        self._cache[key] = PriceCacheEntry(
            price=price,
            timestamp=time.time(),
            ttl=ttl,
        )

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        expired_keys = [
            k for k, v in self._cache.items()
            if v.is_expired()
        ]
        for k in expired_keys:
            del self._cache[k]

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()


# =============================================================================
# Cached Price Provider (Finance-Skills API)
# =============================================================================

class CachedPriceProvider:
    """Price provider with Finance-Skills API caching.

    By default, raises FinerExternalServiceError when real data is unavailable.
    Set fallback_to_mock=True only for tests or explicit mock scenarios.
    """

    def __init__(
        self,
        cache_ttl: int = 3600,
        fallback_to_mock: bool = False,
    ):
        self._cache = PriceCache(PriceCacheConfig(default_ttl=cache_ttl))
        self._fallback_to_mock = fallback_to_mock
        self._mock_provider: Optional[MockPriceProvider] = None

        # Price seed for mock fallback (ticker -> base_price)
        self._price_seeds: Dict[str, float] = {
            # US stocks
            'AAPL': 175.0,
            'MSFT': 380.0,
            'GOOGL': 140.0,
            'AMZN': 155.0,
            'NVDA': 450.0,
            'META': 350.0,
            'TSLA': 250.0,
            'SPY': 450.0,
            'QQQ': 380.0,
            # HK stocks
            '00700.HK': 350.0,  # Tencent
            '00941.HK': 80.0,   # Ping An
            '01810.HK': 35.0,   # Xiaomi
            # CN stocks
            '000001.SZ': 12.0,  # Ping An Bank
            '600519.SH': 1800.0,  # Moutai
            # Crypto
            'BTC-USD': 40000.0,
            'ETH-USD': 2500.0,
        }

    async def _fetch_from_api(
        self,
        ticker: str,
        date: Optional[str] = None
    ) -> Optional[float]:
        """Fetch price from Finance-Skills API."""
        try:
            from finer.services.finance_skills_client import get_finance_skills_client

            client = get_finance_skills_client()
            data = await client.get_market_data(ticker)

            if data:
                # Extract price from response
                # Finance-Skills returns dict with 'close', 'price', etc.
                price = None

                # Try different price fields
                if date:
                    # Historical price request
                    # API might return historical data under 'history' key
                    history = data.get('history', [])
                    for entry in history:
                        if isinstance(entry, dict) and entry.get('date') == date:
                            price = entry.get('close') or entry.get('price')
                            break

                # Latest price
                if price is None:
                    price = data.get('close') or data.get('price') or data.get('last_price')

                if price and isinstance(price, (int, float)):
                    return float(price)

        except Exception as e:
            logger.warning(f"Failed to fetch price for {ticker}: {e}")

        return None

    def get_price(self, ticker: str, date: str) -> Optional[float]:
        """Get price for ticker on specific date (sync wrapper).

        Raises:
            FinerExternalServiceError: If real data unavailable and fallback_to_mock=False.
        """
        # Check cache first
        cached = self._cache.get(ticker, date)
        if cached:
            return cached

        # Try async fetch (for sync compatibility, we run in thread)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, need to schedule
                if self._fallback_to_mock:
                    return self._get_mock_price(ticker, date)
                self._raise_price_unavailable(ticker, date)
            else:
                # Can run async
                price = loop.run_until_complete(self._fetch_from_api(ticker, date))
                if price:
                    self._cache.set(ticker, price, date)
                    return price
        except RuntimeError:
            # No event loop
            pass

        # Fallback to mock
        if self._fallback_to_mock:
            return self._get_mock_price(ticker, date)

        self._raise_price_unavailable(ticker, date)

    async def get_price_async(
        self,
        ticker: str,
        date: str
    ) -> Optional[float]:
        """Async version of get_price.

        Raises:
            FinerExternalServiceError: If real data unavailable and fallback_to_mock=False.
        """
        # Check cache
        cached = self._cache.get(ticker, date)
        if cached:
            return cached

        # Fetch from API
        price = await self._fetch_from_api(ticker, date)

        if price:
            self._cache.set(ticker, price, date)
            return price

        # Fallback to mock
        if self._fallback_to_mock:
            return self._get_mock_price(ticker, date)

        self._raise_price_unavailable(ticker, date)

    def get_prices(
        self,
        ticker: str,
        start: str,
        end: str
    ) -> List[Tuple[str, float]]:
        """Get price series for date range.

        Raises:
            FinerExternalServiceError: If any date has no data and fallback_to_mock=False.
        """
        prices = []

        # Parse dates
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        current = start_dt
        while current <= end_dt:
            date_str = current.strftime('%Y-%m-%d')
            price = self.get_price(ticker, date_str)
            if price:
                prices.append((date_str, price))
            current += timedelta(days=1)

        return prices

    async def get_prices_async(
        self,
        ticker: str,
        start: str,
        end: str
    ) -> List[Tuple[str, float]]:
        """Async version of get_prices."""
        prices = []

        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        # Batch fetch if possible
        try:
            from finer.services.finance_skills_client import get_finance_skills_client

            client = get_finance_skills_client()
            data = await client.get_market_data(ticker)

            if data and 'history' in data:
                # Use historical data from API
                history = data.get('history', [])
                for entry in history:
                    if isinstance(entry, dict):
                        date = entry.get('date')
                        price = entry.get('close') or entry.get('price')
                        if date and price:
                            date_dt = datetime.fromisoformat(date)
                            if start_dt <= date_dt <= end_dt:
                                self._cache.set(ticker, float(price), date)
                                prices.append((date, float(price)))

                if prices:
                    return sorted(prices, key=lambda x: x[0])

        except Exception as e:
            logger.warning(f"Failed to batch fetch prices for {ticker}: {e}")

        # Fallback to individual fetches
        current = start_dt
        while current <= end_dt:
            date_str = current.strftime('%Y-%m-%d')
            price = await self.get_price_async(ticker, date_str)
            if price:
                prices.append((date_str, price))
            current += timedelta(days=1)

        return prices

    def get_latest_price(self, ticker: str) -> Optional[float]:
        """Get latest price for ticker.

        Raises:
            FinerExternalServiceError: If real data unavailable and fallback_to_mock=False.
        """
        # Check cache
        cached = self._cache.get(ticker)
        if cached:
            return cached

        # Try API
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                price = loop.run_until_complete(self._fetch_from_api(ticker))
                if price:
                    self._cache.set(ticker, price)
                    return price
        except RuntimeError:
            pass

        # Fallback
        if self._fallback_to_mock:
            return self._get_mock_price(ticker, datetime.now().strftime('%Y-%m-%d'))

        self._raise_price_unavailable(ticker, None)

    def _get_mock_price(self, ticker: str, date: str) -> float:
        """Generate mock price for fallback."""
        if self._mock_provider is None:
            self._mock_provider = MockPriceProvider(self._price_seeds)
        return self._mock_provider.get_price(ticker, date) or 100.0

    @staticmethod
    def _raise_price_unavailable(ticker: str, date: Optional[str] = None) -> None:
        """Raise canonical error when real price data is unavailable."""
        from finer.errors import FinerExternalServiceError

        date_info = f" on {date}" if date else ""
        raise FinerExternalServiceError(
            code="F8_EXT_001",
            message=f"Price data unavailable for {ticker}{date_info}",
            stage="F8",
            operation="price_fetch",
            retryable=True,
            details={"ticker": ticker, "date": date},
        )

    def clear_cache(self) -> None:
        """Clear price cache."""
        self._cache.clear()


# =============================================================================
# Mock Price Provider (Random Walk)
# =============================================================================

class MockPriceProvider:
    """Mock price provider using geometric random walk.

    Used when Finance-Skills API is unavailable.
    Prices are deterministic given same seed.
    """

    def __init__(
        self,
        base_prices: Optional[Dict[str, float]] = None,
        volatility: float = 0.02,  # Daily volatility
        drift: float = 0.0001,  # Daily drift (slight upward bias)
    ):
        self.base_prices = base_prices or {
            'AAPL': 175.0,
            'MSFT': 380.0,
            'GOOGL': 140.0,
            'SPY': 450.0,
        }
        self.volatility = volatility
        self.drift = drift

        # Seed prices for reproducibility
        self._price_state: Dict[str, float] = {}
        self._price_history: Dict[str, Dict[str, float]] = {}  # ticker -> {date: price}

    def get_price(self, ticker: str, date: str) -> Optional[float]:
        """Get mock price for ticker on date."""
        # Get base price
        base_price = self.base_prices.get(ticker, 100.0)

        # Calculate days from reference date
        ref_date = datetime(2024, 1, 1)
        target_date = datetime.fromisoformat(date)
        days = (target_date - ref_date).days

        if days < 0:
            # Before reference date, use base price
            return base_price

        # Check if already calculated
        if ticker not in self._price_history:
            self._price_history[ticker] = {}

        if date in self._price_history[ticker]:
            return self._price_history[ticker][date]

        # Calculate price using random walk
        # Use ticker hash as seed for reproducibility
        seed = hash(f"{ticker}:{date}") % 2147483647
        rng = random.Random(seed)

        # Geometric random walk
        price = base_price
        for _ in range(days):
            # Daily return: drift + volatility * random shock
            daily_return = self.drift + self.volatility * (rng.gauss(0, 1))
            price *= (1 + daily_return)

        # Round to 2 decimal places
        price = round(price, 2)

        # Cache result
        self._price_history[ticker][date] = price

        return price

    def get_prices(
        self,
        ticker: str,
        start: str,
        end: str
    ) -> List[Tuple[str, float]]:
        """Get mock price series."""
        prices = []

        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        current = start_dt
        while current <= end_dt:
            date_str = current.strftime('%Y-%m-%d')
            price = self.get_price(ticker, date_str)
            if price:
                prices.append((date_str, price))
            current += timedelta(days=1)

        return prices

    def get_latest_price(self, ticker: str) -> Optional[float]:
        """Get latest mock price."""
        return self.get_price(ticker, datetime.now().strftime('%Y-%m-%d'))


# =============================================================================
# CN Market Provider Builder
# =============================================================================


def _build_cn_provider() -> PriceProvider:
    """Build CN price provider — try TusharePriceProvider, fallback to MockPriceProvider."""
    try:
        from finer.market_data.providers import TusharePriceProvider
        from finer.paths import MARKET_PARQUET_DIR

        # 仅当 daily_kline 下已有 synced 分区时才启用真实 provider；
        # 空 parquet 目录（建了目录但从未跑 market-data sync）必须回落 mock，
        # 否则 get_price 对任何 ticker 都返回 None。
        daily_kline_dir = MARKET_PARQUET_DIR / "daily_kline"
        if daily_kline_dir.is_dir() and any(daily_kline_dir.iterdir()):
            return TusharePriceProvider(MARKET_PARQUET_DIR)
    except Exception as e:
        logger.debug("TusharePriceProvider unavailable, using MockPriceProvider: %s", e)

    return MockPriceProvider({
        '000001.SZ': 12.0,
        '600519.SH': 1800.0,
    })


# =============================================================================
# Multi-Market Price Provider
# =============================================================================

class MultiMarketPriceProvider:
    """Price provider supporting multiple markets.

    Routes requests to appropriate providers based on ticker format:
    - US stocks: No suffix or .US
    - HK stocks: .HK suffix
    - CN stocks: .SZ or .SH suffix
    - Crypto: -USD suffix
    """

    def __init__(
        self,
        us_provider: Optional[PriceProvider] = None,
        hk_provider: Optional[PriceProvider] = None,
        cn_provider: Optional[PriceProvider] = None,
        crypto_provider: Optional[PriceProvider] = None,
    ):
        self.us_provider = us_provider or CachedPriceProvider(fallback_to_mock=False)
        self.hk_provider = hk_provider or MockPriceProvider({
            '00700.HK': 350.0,
            '00941.HK': 80.0,
            '01810.HK': 35.0,
        })
        self.cn_provider = cn_provider or _build_cn_provider()
        self.crypto_provider = crypto_provider or MockPriceProvider({
            'BTC-USD': 40000.0,
            'ETH-USD': 2500.0,
        })

    def _detect_market(self, ticker: str) -> str:
        """Detect market from ticker suffix."""
        if ticker.endswith('.HK'):
            return 'HK'
        elif ticker.endswith('.SZ') or ticker.endswith('.SH'):
            return 'CN'
        elif ticker.endswith('-USD') or ticker.endswith('-USDT'):
            return 'CRYPTO'
        else:
            return 'US'

    def _get_provider(self, ticker: str) -> PriceProvider:
        """Get appropriate provider for ticker."""
        market = self._detect_market(ticker)

        if market == 'HK':
            return self.hk_provider
        elif market == 'CN':
            return self.cn_provider
        elif market == 'CRYPTO':
            return self.crypto_provider
        else:
            return self.us_provider

    def get_price(self, ticker: str, date: str) -> Optional[float]:
        """Get price from appropriate provider."""
        provider = self._get_provider(ticker)
        return provider.get_price(ticker, date)

    def get_prices(
        self,
        ticker: str,
        start: str,
        end: str
    ) -> List[Tuple[str, float]]:
        """Get price series from appropriate provider."""
        provider = self._get_provider(ticker)
        return provider.get_prices(ticker, start, end)

    def get_latest_price(self, ticker: str) -> Optional[float]:
        """Get latest price from appropriate provider."""
        provider = self._get_provider(ticker)
        return provider.get_latest_price(ticker)


# =============================================================================
# Price Snapshot Materializer
# =============================================================================


class PriceSnapshotMaterializer:
    """Materializes price snapshots from Tushare Parquet for BacktestEngine.

    Reads OHLCV data via LocalPro and produces a DataFrame matching
    the format expected by BacktestEngine.run_backtest().

    Output DataFrame columns:
        date (datetime64), ticker (str), open, high, low, close (float), volume (float)
    """

    def __init__(self, data_dir: Optional[Path] = None, adj: str = "qfq") -> None:
        from finer.paths import MARKET_PARQUET_DIR
        self._data_dir = data_dir or MARKET_PARQUET_DIR
        self._adj = adj

    def materialize(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Build price DataFrame for given tickers and date range.

        Args:
            tickers: List of ticker symbols (e.g., ['000001.SZ', '600519.SH']).
            start_date: ISO date string (e.g., '2024-01-01').
            end_date: ISO date string (e.g., '2024-12-31').

        Returns:
            DataFrame with columns: date, ticker, open, high, low, close, volume.
            Empty DataFrame if tickers list is empty.

        Raises:
            FinerExternalServiceError: If tickers non-empty but no data found.
        """
        empty_df = pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])

        if not tickers:
            return empty_df

        from finer.market_data.local_api import LocalPro

        api = LocalPro(self._data_dir)
        frames: list[pd.DataFrame] = []

        for ticker in tickers:
            try:
                df = api.pro_bar(
                    ts_code=ticker,
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    adj=self._adj,
                )
                if df.empty:
                    logger.warning("No price data for %s in [%s, %s]", ticker, start_date, end_date)
                    continue

                # Normalize columns to BacktestEngine format
                out = pd.DataFrame({
                    "date": pd.to_datetime(df["trade_date"], format="%Y%m%d"),
                    "ticker": ticker,
                    "open": df["open"].astype(float),
                    "high": df["high"].astype(float),
                    "low": df["low"].astype(float),
                    "close": df["close"].astype(float),
                    "volume": df["vol"].astype(float) if "vol" in df.columns else 0.0,
                })
                frames.append(out)
            except Exception as e:
                logger.warning("Failed to fetch OHLCV for %s: %s", ticker, e)

        if not frames:
            from finer.errors import FinerExternalServiceError

            raise FinerExternalServiceError(
                code="F8_EXT_001",
                message=f"No price data found for tickers {tickers} in [{start_date}, {end_date}]",
                stage="F8",
                operation="price_materialize",
                retryable=True,
                details={"tickers": tickers, "start_date": start_date, "end_date": end_date},
            )


        result = pd.concat(frames, ignore_index=True)
        result = result.sort_values(["date", "ticker"]).reset_index(drop=True)
        return result

    def materialize_from_actions(
        self,
        actions: List[Dict[str, Any]],
        lookback_days: int = 0,
        lookahead_days: int = 0,
    ) -> pd.DataFrame:
        """Build price DataFrame auto-derived from trade action timestamps.

        Expands the date range by lookback/lookahead days to cover
        stop-loss, take-profit, and holding period scenarios.

        Args:
            actions: List of action dicts with 'timestamp' and 'ticker' keys.
            lookback_days: Extra days before earliest action.
            lookahead_days: Extra days after latest action.

        Returns:
            Price DataFrame covering all tickers and the expanded date range.
        """
        if not actions:
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])

        tickers = sorted({a["ticker"] for a in actions if a.get("ticker")})
        timestamps = [pd.Timestamp(a["timestamp"]) for a in actions if a.get("timestamp")]

        if not timestamps or not tickers:
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])

        start = (min(timestamps) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = (max(timestamps) + timedelta(days=lookahead_days)).strftime("%Y-%m-%d")

        return self.materialize(tickers, start, end)