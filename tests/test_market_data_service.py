"""MarketDataSyncService incremental sync edge cases."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("duckdb", reason="market-data extras not installed")
pytest.importorskip("pyarrow", reason="market-data extras not installed")

from finer.market_data.config import MarketDataConfig
from finer.market_data.service import MarketDataSyncService
from finer.market_data.storage import MetaStore, write_daily_kline, write_trade_cal


class _NoCallFetcher:
    def fetch_daily_kline(self, trade_date: date) -> pd.DataFrame:  # pragma: no cover
        raise AssertionError(f"unexpected fetch_daily_kline call: {trade_date}")


def test_sync_daily_kline_loads_trade_cal_and_advances_skipped_frontier(tmp_path: Path) -> None:
    data_dir = tmp_path / "parquet"
    db_path = tmp_path / "meta.duckdb"
    trade_day = date(2026, 5, 8)
    write_trade_cal(
        data_dir,
        "SSE",
        pd.DataFrame({
            "exchange": ["SSE"],
            "cal_date": [trade_day],
            "is_open": [True],
            "pretrade_date": [date(2026, 5, 7)],
        }),
    )
    write_daily_kline(
        data_dir,
        trade_day,
        pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20260508"],
            "open": [12.4],
            "high": [12.8],
            "low": [12.3],
            "close": [12.7],
            "pre_close": [12.4],
            "change": [0.3],
            "pct_chg": [2.42],
            "vol": [1000000.0],
            "amount": [12500000.0],
        }),
    )
    config = MarketDataConfig(
        tushare_token="dummy",
        data_dir=data_dir,
        db_path=db_path,
        sync_start_date=trade_day,
        request_interval=0,
    )

    with MarketDataSyncService(config, fetcher=_NoCallFetcher()) as service:
        service.sync_daily_kline(start_date=trade_day, end_date=trade_day)

    with MetaStore(db_path) as meta:
        assert meta.get_last_date("trade_cal") is None
        assert meta.get_trading_days("SSE", trade_day, trade_day) == [trade_day]
        assert meta.get_last_date("daily_kline") == trade_day


def test_sync_daily_kline_with_calendar_but_no_trading_days_is_noop(tmp_path: Path) -> None:
    data_dir = tmp_path / "parquet"
    db_path = tmp_path / "meta.duckdb"
    closed_day = date(2026, 5, 9)
    write_trade_cal(
        data_dir,
        "SSE",
        pd.DataFrame({
            "exchange": ["SSE"],
            "cal_date": [closed_day],
            "is_open": [False],
            "pretrade_date": [date(2026, 5, 8)],
        }),
    )
    config = MarketDataConfig(
        tushare_token="dummy",
        data_dir=data_dir,
        db_path=db_path,
        sync_start_date=closed_day,
        request_interval=0,
    )

    with MarketDataSyncService(config, fetcher=_NoCallFetcher()) as service:
        service.sync_daily_kline(start_date=closed_day, end_date=closed_day)

    with MetaStore(db_path) as meta:
        assert meta.has_trade_cal_data("SSE") is True
        assert meta.get_last_date("daily_kline") is None
