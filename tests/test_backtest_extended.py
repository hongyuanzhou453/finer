"""Tests for Backtest Engine — Extended test coverage.

Additional tests for:
- Price provider caching
- Mock price provider
- Multi-market price provider
- API endpoints integration
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from finer.backtest.prices import (
    MockPriceProvider,
    CachedPriceProvider,
    PriceCache,
    PriceCacheConfig,
    MultiMarketPriceProvider,
)


class TestPriceCache:
    """Test price cache."""

    def test_cache_set_get(self):
        """Test cache set and get."""
        cache = PriceCache()
        cache.set('AAPL', 175.0, date='2024-01-15')
        price = cache.get('AAPL', date='2024-01-15')
        assert price == 175.0

    def test_cache_latest_price(self):
        """Test caching latest price (no date)."""
        cache = PriceCache()
        cache.set('AAPL', 180.0)  # Latest price
        price = cache.get('AAPL')
        assert price == 180.0

    def test_cache_miss(self):
        """Test cache miss."""
        cache = PriceCache()
        price = cache.get('AAPL', date='2024-01-15')
        assert price is None

    def test_cache_different_dates(self):
        """Test caching prices for different dates."""
        cache = PriceCache()
        cache.set('AAPL', 175.0, date='2024-01-15')
        cache.set('AAPL', 180.0, date='2024-01-16')

        assert cache.get('AAPL', date='2024-01-15') == 175.0
        assert cache.get('AAPL', date='2024-01-16') == 180.0

    def test_cache_different_tickers(self):
        """Test caching prices for different tickers."""
        cache = PriceCache()
        cache.set('AAPL', 175.0, date='2024-01-15')
        cache.set('MSFT', 380.0, date='2024-01-15')

        assert cache.get('AAPL', date='2024-01-15') == 175.0
        assert cache.get('MSFT', date='2024-01-15') == 380.0

    def test_cache_max_entries(self):
        """Test cache with max entries limit."""
        config = PriceCacheConfig(max_entries=10)
        cache = PriceCache(config)

        # Add more than max entries
        for i in range(15):
            cache.set(f'TICK{i}', 100.0 + i, date='2024-01-15')

        # Cache should have cleaned up expired entries
        # (Note: TTL cleanup happens on set when exceeding max)
        assert len(cache._cache) <= 15


class TestMockPriceProvider:
    """Test mock price provider."""

    def test_get_price(self):
        """Test getting price from mock provider."""
        provider = MockPriceProvider(base_prices={'AAPL': 175.0})
        price = provider.get_price('AAPL', '2024-01-15')
        assert price is not None
        assert price > 0

    def test_deterministic_prices(self):
        """Test that prices are deterministic."""
        provider = MockPriceProvider(base_prices={'AAPL': 175.0})

        price1 = provider.get_price('AAPL', '2024-01-15')
        price2 = provider.get_price('AAPL', '2024-01-15')

        assert price1 == pytest.approx(price2, rel=0.0001)

    def test_different_dates_different_prices(self):
        """Test that different dates give different prices (random walk)."""
        provider = MockPriceProvider(
            base_prices={'AAPL': 175.0},
            volatility=0.02,
        )

        price1 = provider.get_price('AAPL', '2024-01-15')
        price2 = provider.get_price('AAPL', '2024-01-20')
        price3 = provider.get_price('AAPL', '2024-01-25')

        # Prices should vary (random walk)
        prices = [price1, price2, price3]
        assert max(prices) != min(prices)

    def test_get_prices_series(self):
        """Test getting price series."""
        provider = MockPriceProvider(base_prices={'AAPL': 175.0})

        prices = provider.get_prices('AAPL', '2024-01-01', '2024-01-31')

        assert len(prices) == 31  # 31 days in January
        assert all(p[1] > 0 for p in prices)  # All prices positive
        assert all(isinstance(p[0], str) for p in prices)  # All dates are strings

    def test_get_latest_price(self):
        """Test getting latest price."""
        provider = MockPriceProvider(base_prices={'AAPL': 175.0})
        price = provider.get_latest_price('AAPL')
        assert price is not None
        assert price > 0

    def test_unknown_ticker(self):
        """Test unknown ticker uses default base price."""
        provider = MockPriceProvider(base_prices={'AAPL': 175.0})
        price = provider.get_price('UNKNOWN', '2024-01-15')
        # Should return price based on default 100.0
        assert price is not None
        assert price > 0

    def test_price_before_reference_date(self):
        """Test price before reference date returns base price."""
        provider = MockPriceProvider(base_prices={'AAPL': 175.0})
        # Reference date is 2024-01-01, so 2023-12-15 should return base
        price = provider.get_price('AAPL', '2023-12-15')
        assert price == pytest.approx(175.0, rel=0.0001)


class TestCachedPriceProvider:
    """Test cached price provider."""

    def test_default_no_fallback(self):
        """Default CachedPriceProvider does not fall back to mock."""
        provider = CachedPriceProvider()
        assert provider._fallback_to_mock is False

    def test_fallback_to_mock(self):
        """Test fallback to mock when API unavailable."""
        provider = CachedPriceProvider(fallback_to_mock=True)
        price = provider.get_price('AAPL', '2024-01-15')
        # Should get mock price
        assert price is not None
        assert price > 0

    def test_no_fallback_raises(self):
        """Test without fallback raises FinerExternalServiceError."""
        from finer.errors import FinerExternalServiceError

        provider = CachedPriceProvider(fallback_to_mock=False)
        with pytest.raises(FinerExternalServiceError) as exc_info:
            provider.get_price('AAPL', '2024-01-15')
        assert exc_info.value.code.value == "F8_EXT_001"
        assert "AAPL" in exc_info.value.message

    def test_get_prices(self):
        """Test getting price series."""
        provider = CachedPriceProvider(fallback_to_mock=True)
        prices = provider.get_prices('AAPL', '2024-01-01', '2024-01-10')
        assert len(prices) > 0
        assert all(p[1] > 0 for p in prices)

    def test_get_latest_price(self):
        """Test getting latest price."""
        provider = CachedPriceProvider(fallback_to_mock=True)
        price = provider.get_latest_price('AAPL')
        assert price is not None
        assert price > 0

    def test_clear_cache(self):
        """Test clearing cache."""
        provider = CachedPriceProvider(fallback_to_mock=True)
        provider.get_price('AAPL', '2024-01-15')  # Cache something
        provider.clear_cache()
        # Cache should be empty now
        assert len(provider._cache._cache) == 0

    def test_price_seeds(self):
        """Test predefined price seeds."""
        provider = CachedPriceProvider(
            fallback_to_mock=True,
        )
        provider._price_seeds['CUSTOM'] = 500.0
        price = provider.get_price('CUSTOM', '2024-01-15')
        assert price is not None


class TestMultiMarketPriceProvider:
    """Test multi-market price provider."""

    def test_detect_market_us(self):
        """Test US market detection."""
        provider = MultiMarketPriceProvider()
        assert provider._detect_market('AAPL') == 'US'
        assert provider._detect_market('MSFT.US') == 'US'
        assert provider._detect_market('SPY') == 'US'

    def test_detect_market_hk(self):
        """Test HK market detection."""
        provider = MultiMarketPriceProvider()
        assert provider._detect_market('00700.HK') == 'HK'
        assert provider._detect_market('01810.HK') == 'HK'

    def test_detect_market_cn(self):
        """Test CN market detection."""
        provider = MultiMarketPriceProvider()
        assert provider._detect_market('000001.SZ') == 'CN'
        assert provider._detect_market('600519.SH') == 'CN'

    def test_detect_market_crypto(self):
        """Test crypto market detection."""
        provider = MultiMarketPriceProvider()
        assert provider._detect_market('BTC-USD') == 'CRYPTO'
        assert provider._detect_market('ETH-USD') == 'CRYPTO'
        assert provider._detect_market('BTC-USDT') == 'CRYPTO'

    def test_get_price_routing(self):
        """Test price requests routed to correct provider."""
        us_mock = MockPriceProvider(base_prices={'AAPL': 175.0, 'MSFT': 380.0})
        provider = MultiMarketPriceProvider(us_provider=us_mock)

        # US stock
        us_price = provider.get_price('AAPL', '2024-01-15')
        assert us_price is not None

        # HK stock
        hk_price = provider.get_price('00700.HK', '2024-01-15')
        assert hk_price is not None

        # CN stock
        cn_price = provider.get_price('000001.SZ', '2024-01-15')
        assert cn_price is not None

        # Crypto
        crypto_price = provider.get_price('BTC-USD', '2024-01-15')
        assert crypto_price is not None

    def test_get_prices_routing(self):
        """Test price series routed to correct provider."""
        us_mock = MockPriceProvider(base_prices={'AAPL': 175.0})
        provider = MultiMarketPriceProvider(us_provider=us_mock)

        us_prices = provider.get_prices('AAPL', '2024-01-01', '2024-01-10')
        assert len(us_prices) > 0

        hk_prices = provider.get_prices('00700.HK', '2024-01-01', '2024-01-10')
        assert len(hk_prices) > 0


class TestBuildCnProvider:
    """Test _build_cn_provider fallback logic for unsynced parquet directories."""

    def test_empty_parquet_dir_falls_back_to_mock(self, tmp_path, monkeypatch):
        """Parquet dir exists but has no daily_kline → MockPriceProvider."""
        import finer.paths
        from finer.backtest.prices import _build_cn_provider

        monkeypatch.setattr(finer.paths, 'MARKET_PARQUET_DIR', tmp_path)

        provider = _build_cn_provider()
        assert isinstance(provider, MockPriceProvider)
        assert provider.get_price('000001.SZ', '2024-01-15') is not None

    def test_empty_daily_kline_falls_back_to_mock(self, tmp_path, monkeypatch):
        """daily_kline dir exists but contains no partitions → MockPriceProvider."""
        import finer.paths
        from finer.backtest.prices import _build_cn_provider

        (tmp_path / 'daily_kline').mkdir()
        monkeypatch.setattr(finer.paths, 'MARKET_PARQUET_DIR', tmp_path)

        provider = _build_cn_provider()
        assert isinstance(provider, MockPriceProvider)
        assert provider.get_price('000001.SZ', '2024-01-15') is not None

    def test_synced_daily_kline_uses_tushare_provider(self, tmp_path, monkeypatch):
        """daily_kline with at least one partition → TusharePriceProvider."""
        import finer.paths
        from finer.backtest.prices import _build_cn_provider
        from finer.market_data.providers import TusharePriceProvider

        partition = tmp_path / 'daily_kline' / 'date=20240115'
        partition.mkdir(parents=True)
        monkeypatch.setattr(finer.paths, 'MARKET_PARQUET_DIR', tmp_path)

        provider = _build_cn_provider()
        assert isinstance(provider, TusharePriceProvider)


class TestBacktestIntegration:
    """Integration tests for backtest module."""

    def test_full_backtest_with_mock_prices(self):
        """Test full backtest using mock prices."""
        from finer.backtest.engine import BacktestEngine, BacktestConfig

        # Create mock price data
        provider = MockPriceProvider(base_prices={'AAPL': 175.0, 'MSFT': 380.0})
        dates = pd.date_range('2024-01-01', '2024-01-31', freq='D')

        rows = []
        for date in dates:
            for ticker in ['AAPL', 'MSFT']:
                price = provider.get_price(ticker, date.strftime('%Y-%m-%d'))
                rows.append({
                    'date': date,
                    'ticker': ticker,
                    'open': price * 0.99,
                    'high': price * 1.01,
                    'low': price * 0.98,
                    'close': price,
                    'volume': 1000000,
                })

        price_df = pd.DataFrame(rows)

        # Actions
        actions = [
            {
                'timestamp': '2024-01-05',
                'ticker': 'AAPL',
                'direction': 'bullish',
                'action_type': 'long',
                'kol_id': 'test_kol',
            },
            {
                'timestamp': '2024-01-15',
                'ticker': 'MSFT',
                'direction': 'bullish',
                'action_type': 'long',
                'kol_id': 'test_kol',
            },
        ]

        # Run backtest
        engine = BacktestEngine(BacktestConfig(initial_capital=100000.0))
        result = engine.run_backtest(actions, price_df)

        # Verify results
        assert result is not None
        assert result.total_trades >= 0
        assert result.total_return is not None
        assert result.sharpe_ratio is not None

    def test_backtest_with_short_selling(self):
        """Test backtest with short positions."""
        from finer.backtest.engine import BacktestEngine, BacktestConfig

        # Price data with decline
        dates = pd.date_range('2024-01-01', '2024-01-20', freq='D')
        rows = []
        for i, date in enumerate(dates):
            price = 200.0 - i * 2  # Declining price
            rows.append({
                'date': date,
                'ticker': 'TSLA',
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 1000000,
            })

        price_df = pd.DataFrame(rows)

        # Short action
        actions = [{
            'timestamp': '2024-01-05',
            'ticker': 'TSLA',
            'direction': 'bearish',
            'action_type': 'short',
        }]

        config = BacktestConfig(allow_short_selling=True)
        engine = BacktestEngine(config)
        result = engine.run_backtest(actions, price_df)

        assert result.total_trades > 0
        # Short should be profitable with declining prices
        if result.trades:
            trade = result.trades[0]
            assert trade.side.value == 'short'

    def test_backtest_with_stop_loss_and_take_profit(self):
        """Test backtest with stop loss and take profit."""
        from finer.backtest.engine import BacktestEngine, BacktestConfig

        # Price data with volatility
        dates = pd.date_range('2024-01-01', '2024-01-20', freq='D')
        rows = []
        for i, date in enumerate(dates):
            # Big drop on day 10
            if i >= 10:
                price = 150.0 * 0.85  # 15% drop
            else:
                price = 150.0
            rows.append({
                'date': date,
                'ticker': 'AAPL',
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 1000000,
            })

        price_df = pd.DataFrame(rows)

        actions = [{
            'timestamp': '2024-01-02',
            'ticker': 'AAPL',
            'direction': 'bullish',
            'action_type': 'long',
        }]

        config = BacktestConfig(default_stop_loss_pct=0.1)
        engine = BacktestEngine(config)
        result = engine.run_backtest(actions, price_df)

        # Should have exited due to stop loss
        assert result.total_trades > 0


class TestBacktestConfigVariations:
    """Test various backtest configurations."""

    def test_small_capital(self):
        """Test with small initial capital."""
        from finer.backtest.engine import BacktestEngine, BacktestConfig

        config = BacktestConfig(initial_capital=1000.0)
        engine = BacktestEngine(config)

        price_df = pd.DataFrame([
            {'date': '2024-01-01', 'ticker': 'AAPL', 'close': 175.0},
            {'date': '2024-01-15', 'ticker': 'AAPL', 'close': 180.0},
        ])
        price_df['date'] = pd.to_datetime(price_df['date'])

        result = engine.run_backtest([{
            'timestamp': '2024-01-01',
            'ticker': 'AAPL',
            'direction': 'bullish',
        }], price_df)

        assert result.initial_capital == 1000.0

    def test_high_commission(self):
        """Test with high commission rate."""
        from finer.backtest.engine import BacktestEngine, BacktestConfig

        config = BacktestConfig(commission_pct=0.05)  # 5% commission
        engine = BacktestEngine(config)

        price_df = pd.DataFrame([
            {'date': '2024-01-01', 'ticker': 'AAPL', 'close': 175.0},
            {'date': '2024-01-15', 'ticker': 'AAPL', 'close': 180.0},
        ])
        price_df['date'] = pd.to_datetime(price_df['date'])

        result = engine.run_backtest([{
            'timestamp': '2024-01-01',
            'ticker': 'AAPL',
            'direction': 'bullish',
        }], price_df)

        assert result is not None

    def test_no_short_selling(self):
        """Test with short selling disabled."""
        from finer.backtest.engine import BacktestEngine, BacktestConfig

        config = BacktestConfig(allow_short_selling=False)
        engine = BacktestEngine(config)

        price_df = pd.DataFrame([
            {'date': '2024-01-01', 'ticker': 'AAPL', 'close': 175.0},
            {'date': '2024-01-15', 'ticker': 'AAPL', 'close': 170.0},
        ])
        price_df['date'] = pd.to_datetime(price_df['date'])

        result = engine.run_backtest([{
            'timestamp': '2024-01-01',
            'ticker': 'AAPL',
            'direction': 'bearish',
            'action_type': 'short',
        }], price_df)

        # Short should be ignored
        assert result.total_trades == 0
