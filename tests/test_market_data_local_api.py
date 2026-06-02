"""LocalPro query tests — stock_basic, daily, adj_factor, pro_bar."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Skip entire module if market-data optional deps are missing
pytest.importorskip("duckdb", reason="market-data extras not installed (pip install 'finer[market-data]')")
pytest.importorskip("pyarrow", reason="market-data extras not installed")

from finer.market_data.local_api import LocalPro
from finer.market_data.storage import (
    write_adj_factor,
    write_basic,
    write_daily_kline,
    write_trade_cal,
)

BASIC_DF = pd.DataFrame({
    "ts_code": ["000001.SZ", "600000.SH", "000002.SZ"],
    "symbol": ["000001", "600000", "000002"],
    "name": ["平安银行", "浦发银行", "万科A"],
    "area": ["深圳", "上海", "深圳"],
    "industry": ["银行", "银行", "房地产"],
    "fullname": ["平安银行股份有限公司", "上海浦东发展银行股份有限公司", "万科企业股份有限公司"],
    "enname": ["Ping An Bank", "Shanghai Pudong Development Bank", "China Vanke"],
    "cnspell": ["pay", "pfyh", "wka"],
    "market": ["主板", "主板", "主板"],
    "exchange": ["SZSE", "SSE", "SZSE"],
    "curr_type": ["CNY", "CNY", "CNY"],
    "list_status": ["L", "L", "L"],
    "list_date": ["19910403", "19991110", "19910129"],
    "delist_date": [None, None, None],
    "is_hs": ["H", "H", "H"],
    "act_name": ["平安银行", "浦发银行", "万科"],
    "act_ent_type": ["民营企业", "地方国企", "公众企业"],
})


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "parquet"
    write_basic(d, BASIC_DF)
    # Write 3 days of daily data for 000001.SZ
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
    # Write adj_factor
    for day in [7, 8, 9]:
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [f"2026050{day}"],
            "adj_factor": [1.0],
        })
        write_adj_factor(d, date(2026, 5, day), df)
    return d


# ── stock_basic ─────────────────────────────────────────────────────────


class TestStockBasic:
    def test_list_all(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.stock_basic()
        assert len(df) == 3

    def test_filter_ts_code(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.stock_basic(ts_code="000001.SZ")
        assert len(df) == 1
        assert df.iloc[0]["ts_code"] == "000001.SZ"

    def test_filter_market(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.stock_basic(market="主板")
        assert len(df) == 3

    def test_fields_selection(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.stock_basic(fields="ts_code,name")
        assert list(df.columns) == ["ts_code", "name"]

    def test_date_columns_formatted(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.stock_basic(ts_code="000001.SZ")
        assert df.iloc[0]["list_date"] == "19910403"

    def test_file_not_found(self, tmp_path: Path) -> None:
        api = LocalPro(tmp_path / "empty")
        with pytest.raises(FileNotFoundError, match="basic data not found"):
            api.stock_basic()


# ── daily ───────────────────────────────────────────────────────────────


class TestDaily:
    def test_query_by_ts_code(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(ts_code="000001.SZ")
        assert len(df) == 3

    def test_query_by_trade_date(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(trade_date="20260508")
        assert len(df) == 1

    def test_query_date_range(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(ts_code="000001.SZ", start_date="20260508", end_date="20260509")
        assert len(df) == 2

    def test_query_multi_ts_code(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(ts_code="000001.SZ,600000.SH")
        assert len(df) == 3  # only 000001.SZ has daily data

    def test_fields_selection(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(ts_code="000001.SZ", fields="ts_code,close")
        assert list(df.columns) == ["ts_code", "close"]

    def test_trade_date_and_range_conflict(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        with pytest.raises(ValueError, match="trade_date cannot be combined"):
            api.daily(trade_date="20260508", start_date="20260507")

    def test_end_before_start(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        with pytest.raises(ValueError, match="end_date must be on or after"):
            api.daily(start_date="20260509", end_date="20260507")

    def test_date_columns_formatted(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(trade_date="20260508")
        assert df.iloc[0]["trade_date"] == "20260508"

    def test_iso_date_input(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.daily(trade_date="2026-05-08")
        assert len(df) == 1


# ── adj_factor ──────────────────────────────────────────────────────────


class TestAdjFactor:
    def test_query(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.adj_factor(ts_code="000001.SZ")
        assert len(df) == 3
        assert "adj_factor" in df.columns


# ── pro_bar ─────────────────────────────────────────────────────────────


class TestProBar:
    def test_raw(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.pro_bar(ts_code="000001.SZ", adj=None)
        assert len(df) == 3
        assert df.iloc[0]["close"] == 12.5

    def test_qfq(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.pro_bar(ts_code="000001.SZ", adj="qfq")
        assert len(df) == 3
        # qfq with adj_factor=1.0 everywhere => prices unchanged
        assert df.iloc[0]["close"] == 12.5

    def test_hfq(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.pro_bar(ts_code="000001.SZ", adj="hfq")
        assert len(df) == 3
        # hfq with adj_factor=1.0 => prices unchanged
        assert df.iloc[0]["close"] == 12.5

    def test_invalid_adj(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        with pytest.raises(ValueError, match="adj must be one of"):
            api.pro_bar(ts_code="000001.SZ", adj="invalid")

    def test_empty_result(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.pro_bar(ts_code="999999.SZ")
        assert df.empty

    def test_date_range(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        df = api.pro_bar(ts_code="000001.SZ", start_date="20260508", end_date="20260509")
        assert len(df) == 2


# ── helpers ─────────────────────────────────────────────────────────────


class TestHelpers:
    def test_unknown_field_raises(self, data_dir: Path) -> None:
        api = LocalPro(data_dir)
        with pytest.raises(ValueError, match="unknown fields"):
            api.daily(fields="ts_code,nonexistent_col")
