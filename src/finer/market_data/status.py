"""Local Tushare storage diagnostics.

This module is intentionally read-only: it inspects local Parquet/DuckDB
artifacts without requiring ``TUSHARE_TOKEN`` or constructing a live Tushare
client.
"""
from __future__ import annotations

import importlib.util
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

from finer.paths import MARKET_DUCKDB_PATH, MARKET_PARQUET_DIR

_TABLE_PATTERNS = {
    "trade_cal": "trade_cal/exchange=*/data.parquet",
    "basic": "basic/data.parquet",
    "daily_kline": "daily_kline/date=*/data.parquet",
    "adj_factor": "adj_factor/date=*/data.parquet",
}


def parquet_files(data_dir: Path, table_name: str) -> list[Path]:
    """Return concrete Parquet files for a supported local market table."""
    pattern = _TABLE_PATTERNS.get(table_name)
    if pattern is None:
        raise ValueError(f"unknown market data table: {table_name}")
    return sorted(Path(data_dir).glob(pattern))


def has_synced_partitions(data_dir: Path, table_name: str) -> bool:
    """True when the table has at least one real Parquet file."""
    return bool(parquet_files(data_dir, table_name))


def inspect_market_data(
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Inspect local Tushare storage without network or token requirements."""
    resolved_data_dir = data_dir or MARKET_PARQUET_DIR
    resolved_db_path = db_path or MARKET_DUCKDB_PATH
    sync_meta = _read_sync_meta(resolved_db_path)

    tables = {}
    for table_name in _TABLE_PATTERNS:
        files = parquet_files(resolved_data_dir, table_name)
        tables[table_name] = {
            "parquet_files": len(files),
            "synced": bool(files),
            "last_date": _date_to_str(sync_meta.get(table_name)),
        }

    daily_ready = tables["daily_kline"]["synced"]
    adj_ready = tables["adj_factor"]["synced"]
    warnings = []
    if daily_ready and not adj_ready:
        warnings.append(
            "daily_kline exists but adj_factor is missing; adjusted prices will fall back to raw OHLCV"
        )
    if not daily_ready:
        warnings.append(
            "daily_kline is empty; CN backtests and annotation market lookup will use no local prices"
        )

    return {
        "data_dir": str(resolved_data_dir),
        "db_path": str(resolved_db_path),
        "token_configured": bool(os.environ.get("TUSHARE_TOKEN", "").strip()),
        "dependencies": {
            "duckdb": duckdb is not None,
            "pyarrow": importlib.util.find_spec("pyarrow") is not None,
            "tushare": importlib.util.find_spec("tushare") is not None,
        },
        "tables": tables,
        "ready": {
            "local_query": daily_ready,
            "adjusted_prices": daily_ready and adj_ready,
            "cn_backtest_provider": daily_ready,
        },
        "warnings": warnings,
    }


def build_sync_plan(
    *,
    table: str | None,
    sync_all: bool,
    start: date | None,
    end: date | None,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    default_start: date = date(2016, 1, 1),
) -> dict[str, Any]:
    """Build a read-only sync plan for CLI dry-runs."""
    status = inspect_market_data(data_dir=data_dir, db_path=db_path)
    tables = list(_TABLE_PATTERNS) if sync_all else ([table] if table else [])
    today = date.today()
    planned = []
    for table_name in tables:
        if table_name not in _TABLE_PATTERNS:
            continue
        last_date_text = status["tables"][table_name]["last_date"]
        inferred_start = (
            _parse_yyyymmdd(last_date_text) + timedelta(days=1)
            if last_date_text and table_name in {"daily_kline", "adj_factor"}
            else default_start
        )
        planned_start = start or inferred_start
        planned_end = end or today
        planned.append(
            {
                "table": table_name,
                "start": _date_to_str(planned_start),
                "end": _date_to_str(planned_end),
                "existing_parquet_files": status["tables"][table_name]["parquet_files"],
                "last_date": last_date_text or "never",
                "will_call_tushare": True,
            }
        )
    return {
        "mode": "dry-run",
        "token_configured": status["token_configured"],
        "requested": {"all": sync_all, "table": table, "start": _date_to_str(start), "end": _date_to_str(end)},
        "tables": planned,
        "local_status": status,
    }


def _read_sync_meta(db_path: Path) -> dict[str, date | None]:
    if duckdb is None or not db_path.exists():
        return {}
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
    except Exception:
        return {}
    try:
        rows = conn.execute("SELECT table_name, last_date FROM sync_meta").fetchall()
    except Exception:
        return {}
    finally:
        conn.close()
    return {str(table_name): last_date for table_name, last_date in rows}


def _date_to_str(value: date | None) -> str | None:
    return value.strftime("%Y%m%d") if value else None


def _parse_yyyymmdd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
