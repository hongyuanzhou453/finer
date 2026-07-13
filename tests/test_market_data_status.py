"""Read-only market data diagnostics and CLI dry-run tests."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("pyarrow", reason="market-data extras not installed")

from finer.cli import _cmd_market_data_status, _cmd_market_data_sync
from finer.market_data.status import has_synced_partitions, inspect_market_data
from finer.market_data.storage import write_daily_kline


def _write_daily(data_dir: Path) -> None:
    write_daily_kline(
        data_dir,
        date(2026, 5, 8),
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


def test_inspect_market_data_reports_empty_store_without_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    result = inspect_market_data(data_dir=tmp_path / "parquet", db_path=tmp_path / "meta.duckdb")

    assert result["token_configured"] is False
    assert result["tables"]["daily_kline"]["synced"] is False
    assert result["ready"]["cn_backtest_provider"] is False
    assert "daily_kline is empty" in result["warnings"][0]


def test_has_synced_partitions_requires_real_parquet_file(tmp_path: Path) -> None:
    table_dir = tmp_path / "daily_kline"
    (table_dir / "date=20260508").mkdir(parents=True)
    (table_dir / ".DS_Store").write_text("", encoding="utf-8")
    assert has_synced_partitions(tmp_path, "daily_kline") is False

    _write_daily(tmp_path)
    assert has_synced_partitions(tmp_path, "daily_kline") is True


def test_cli_status_does_not_require_tushare_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from finer.market_data import status as status_mod

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(status_mod, "MARKET_PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(status_mod, "MARKET_DUCKDB_PATH", tmp_path / "meta.duckdb")

    result = _cmd_market_data_status(argparse.Namespace())

    assert result["token_configured"] is False
    assert result["tables"]["daily_kline"]["synced"] is False


def test_cli_sync_dry_run_does_not_require_tushare_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from finer.market_data import status as status_mod

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(status_mod, "MARKET_PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(status_mod, "MARKET_DUCKDB_PATH", tmp_path / "meta.duckdb")

    result = _cmd_market_data_sync(
        argparse.Namespace(
            all=False,
            table="daily_kline",
            start="20260501",
            end="20260508",
            dry_run=True,
        )
    )

    assert result["mode"] == "dry-run"
    assert result["token_configured"] is False
    assert result["tables"] == [
        {
            "table": "daily_kline",
            "start": "20260501",
            "end": "20260508",
            "existing_parquet_files": 0,
            "last_date": "never",
            "will_call_tushare": True,
        }
    ]


def test_cli_real_sync_missing_token_returns_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    result = _cmd_market_data_sync(
        argparse.Namespace(
            all=False,
            table="basic",
            start=None,
            end=None,
            dry_run=False,
        )
    )

    assert result["status"] == "error"
    assert result["token_configured"] is False
    assert "TUSHARE_TOKEN" in result["error"]
