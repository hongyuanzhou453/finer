"""Market data storage tests — Parquet read/write + DuckDB meta."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Skip entire module if market-data optional deps are missing
pytest.importorskip("duckdb", reason="market-data extras not installed (pip install 'finer[market-data]')")
pytest.importorskip("pyarrow", reason="market-data extras not installed")

from finer.market_data.storage import (
    MetaStore,
    adj_factor_partition_exists,
    daily_kline_partition_exists,
    read_basic,
    read_daily_kline,
    read_trade_cal,
    write_adj_factor,
    write_basic,
    write_daily_kline,
    write_trade_cal,
)


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "meta.duckdb"


@pytest.fixture()
def sample_daily_df() -> pd.DataFrame:
    return pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ"],
        "trade_date": ["20260508", "20260509"],
        "open": [12.5, 12.6],
        "high": [12.8, 12.9],
        "low": [12.3, 12.4],
        "close": [12.7, 12.8],
        "pre_close": [12.4, 12.7],
        "change": [0.3, 0.1],
        "pct_chg": [2.42, 0.79],
        "vol": [1000000.0, 1100000.0],
        "amount": [12500000.0, 14080000.0],
    })


# ── MetaStore ───────────────────────────────────────────────────────────


class TestMetaStore:
    def test_init_creates_tables(self, db_path: Path) -> None:
        store = MetaStore(db_path)
        assert store.get_last_date("daily_kline") is None
        store.close()

    def test_update_and_get_last_date(self, db_path: Path) -> None:
        store = MetaStore(db_path)
        store.update_last_date("daily_kline", date(2026, 5, 9))
        assert store.get_last_date("daily_kline") == date(2026, 5, 9)
        store.update_last_date("daily_kline", date(2026, 5, 10))
        assert store.get_last_date("daily_kline") == date(2026, 5, 10)
        store.close()

    def test_get_trading_days_empty(self, db_path: Path) -> None:
        store = MetaStore(db_path)
        days = store.get_trading_days("SSE", date(2026, 1, 1), date(2026, 12, 31))
        assert days == []
        store.close()

    def test_load_trade_cal_from_parquet(self, db_path: Path, data_dir: Path) -> None:
        cal_df = pd.DataFrame({
            "exchange": ["SSE", "SSE", "SSE"],
            "cal_date": [date(2026, 5, 7), date(2026, 5, 8), date(2026, 5, 9)],
            "is_open": [True, True, False],
            "pretrade_date": [date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 8)],
        })
        write_trade_cal(data_dir, "SSE", cal_df)

        store = MetaStore(db_path)
        store.load_trade_cal_from_parquet(data_dir)
        days = store.get_trading_days("SSE", date(2026, 5, 7), date(2026, 5, 9))
        assert len(days) == 2
        assert days == [date(2026, 5, 7), date(2026, 5, 8)]
        store.close()

    def test_context_manager(self, db_path: Path) -> None:
        with MetaStore(db_path) as store:
            store.update_last_date("basic", date(2026, 5, 1))
            assert store.get_last_date("basic") == date(2026, 5, 1)


# ── Parquet Read/Write ─────────────────────────────────────────────────


class TestDailyKlineStorage:
    def test_write_and_read(self, data_dir: Path, sample_daily_df: pd.DataFrame) -> None:
        write_daily_kline(data_dir, date(2026, 5, 9), sample_daily_df)
        assert daily_kline_partition_exists(data_dir, date(2026, 5, 9))
        assert not daily_kline_partition_exists(data_dir, date(2026, 5, 10))

        read_df = read_daily_kline(data_dir, date(2026, 5, 9))
        assert len(read_df) == 2
        # Original columns must be present (hive partition may add extra 'date' column)
        for col in sample_daily_df.columns:
            assert col in read_df.columns

    def test_read_nonexistent_returns_empty(self, data_dir: Path) -> None:
        read_df = read_daily_kline(data_dir, date(2026, 1, 1))
        assert read_df.empty


class TestAdjFactorStorage:
    def test_write_and_exists(self, data_dir: Path) -> None:
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20260509"],
            "adj_factor": [1.0],
        })
        write_adj_factor(data_dir, date(2026, 5, 9), df)
        assert adj_factor_partition_exists(data_dir, date(2026, 5, 9))


class TestBasicStorage:
    def test_write_and_read(self, data_dir: Path) -> None:
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", "600000.SH"],
            "name": ["平安银行", "浦发银行"],
        })
        write_basic(data_dir, df)
        read_df = read_basic(data_dir)
        assert len(read_df) == 2

    def test_read_nonexistent_returns_empty(self, data_dir: Path) -> None:
        read_df = read_basic(data_dir)
        assert read_df.empty


class TestTradeCalStorage:
    def test_write_and_read(self, data_dir: Path) -> None:
        df = pd.DataFrame({
            "exchange": ["SSE", "SSE"],
            "cal_date": [date(2026, 5, 8), date(2026, 5, 9)],
            "is_open": [True, False],
            "pretrade_date": [date(2026, 5, 7), date(2026, 5, 8)],
        })
        write_trade_cal(data_dir, "SSE", df)
        read_df = read_trade_cal(data_dir, "SSE")
        assert len(read_df) == 2

    def test_read_nonexistent_returns_empty(self, data_dir: Path) -> None:
        read_df = read_trade_cal(data_dir, "SSE")
        assert read_df.empty
