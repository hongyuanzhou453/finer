"""TusharePriceProvider tests — PriceProvider protocol conformance."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Skip entire module if market-data optional deps are missing
pytest.importorskip("duckdb", reason="market-data extras not installed (pip install 'finer[market-data]')")
pytest.importorskip("pyarrow", reason="market-data extras not installed")

from finer.market_data.providers import TusharePriceProvider
from finer.market_data.storage import write_adj_factor, write_basic, write_daily_kline


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "parquet"
    write_basic(d, pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "symbol": ["000001"],
        "name": ["平安银行"],
        "area": ["深圳"],
        "industry": ["银行"],
        "fullname": ["平安银行股份有限公司"],
        "enname": ["Ping An Bank"],
        "cnspell": ["pay"],
        "market": ["主板"],
        "exchange": ["SZSE"],
        "curr_type": ["CNY"],
        "list_status": ["L"],
        "list_date": ["19910403"],
        "delist_date": [None],
        "is_hs": ["H"],
        "act_name": ["平安银行"],
        "act_ent_type": ["民营企业"],
    }))
    for day, close in [(7, 12.5), (8, 12.7), (9, 12.8)]:
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [f"2026050{day}"],
            "open": [close - 0.2],
            "high": [close + 0.1],
            "low": [close - 0.3],
            "close": [close],
            "pre_close": [close - 0.1],
            "change": [0.1],
            "pct_chg": [0.8],
            "vol": [1000000.0],
            "amount": [12500000.0],
        })
        write_daily_kline(d, date(2026, 5, day), df)
    for day in [7, 8, 9]:
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [f"2026050{day}"],
            "adj_factor": [1.0],
        })
        write_adj_factor(d, date(2026, 5, day), df)
    return d


class TestTusharePriceProvider:
    def test_get_price(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        price = provider.get_price("000001.SZ", "2026-05-09")
        assert price == 12.8

    def test_get_price_missing(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        price = provider.get_price("000001.SZ", "2026-01-01")
        assert price is None

    def test_get_price_unknown_ticker(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        price = provider.get_price("999999.SZ", "2026-05-09")
        assert price is None

    def test_get_prices(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        prices = provider.get_prices("000001.SZ", "2026-05-07", "2026-05-09")
        assert len(prices) == 3
        assert prices[0] == ("2026-05-07", 12.5)
        assert prices[1] == ("2026-05-08", 12.7)
        assert prices[2] == ("2026-05-09", 12.8)

    def test_get_prices_empty_range(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        prices = provider.get_prices("000001.SZ", "2026-01-01", "2026-01-10")
        assert prices == []

    def test_get_latest_price(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        latest = provider.get_latest_price("000001.SZ")
        assert latest == 12.8

    def test_get_latest_price_no_data(self, data_dir: Path) -> None:
        provider = TusharePriceProvider(data_dir)
        latest = provider.get_latest_price("999999.SZ")
        assert latest is None

    def test_protocol_conformance(self, data_dir: Path) -> None:
        """Verify TusharePriceProvider satisfies PriceProvider protocol."""
        from finer.backtest.prices import PriceProvider

        provider = TusharePriceProvider(data_dir)
        # Structural conformance — these calls should not raise
        assert hasattr(provider, "get_price")
        assert hasattr(provider, "get_prices")
        assert hasattr(provider, "get_latest_price")
        # Actually satisfies the protocol (runtime_checkable if needed)
        _provider: PriceProvider = provider  # noqa: F841
