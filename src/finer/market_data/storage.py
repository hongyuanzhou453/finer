"""Parquet partitioned storage + DuckDB metadata for market data.

Ported from zer0share/storage.py with the following adaptations:
- Standard logging instead of loguru
- Paths passed as parameters, not from config file
- DuckDB connection management follows context manager pattern

Storage layout:
    data/market/tushare/parquet/
    ├── trade_cal/exchange=SSE/data.parquet
    ├── basic/data.parquet
    ├── daily_kline/date=20260101/data.parquet
    └── adj_factor/date=20260101/data.parquet

    data/market/tushare/meta.duckdb
    ├── sync_meta (table_name, last_date, updated_at)
    └── trade_cal (exchange, cal_date, is_open, pretrade_date)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa = None  # type: ignore[assignment]
    pq = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ── DuckDB Metadata Store ──────────────────────────────────────────────


class MetaStore:
    """DuckDB-backed metadata for sync tracking and trade calendar queries."""

    def __init__(self, db_path: Path) -> None:
        if duckdb is None:
            raise ImportError(
                "duckdb is required for market data metadata. "
                "Install with: pip install 'finer[market-data]'"
            )
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_meta (
                table_name  VARCHAR PRIMARY KEY,
                last_date   DATE,
                updated_at  TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_cal (
                exchange      VARCHAR,
                cal_date      DATE,
                is_open       BOOLEAN,
                pretrade_date DATE,
                PRIMARY KEY (exchange, cal_date)
            )
        """)

    def get_last_date(self, table_name: str) -> date | None:
        row = self._conn.execute(
            "SELECT last_date FROM sync_meta WHERE table_name = ?", [table_name]
        ).fetchone()
        return row[0] if row else None

    def update_last_date(self, table_name: str, last_date: date) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_meta (table_name, last_date, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (table_name) DO UPDATE SET
                last_date = excluded.last_date,
                updated_at = excluded.updated_at
            """,
            [table_name, last_date, datetime.now(timezone.utc)],
        )

    def load_trade_cal_from_parquet(self, data_dir: Path) -> None:
        """Load all trade_cal Parquet partitions into DuckDB."""
        trade_cal_dir = data_dir / "trade_cal"
        if not trade_cal_dir.exists():
            return
        self._conn.execute("BEGIN")
        try:
            self._conn.execute("DELETE FROM trade_cal")
            for exchange_dir in sorted(trade_cal_dir.iterdir()):
                if not exchange_dir.is_dir():
                    continue
                parquet_path = exchange_dir / "data.parquet"
                if not parquet_path.exists():
                    continue
                self._conn.execute(
                    "INSERT INTO trade_cal SELECT * FROM read_parquet(?)",
                    [str(parquet_path)],
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def get_trading_days(
        self, exchange: str, start: date, end: date
    ) -> list[date]:
        """Return sorted list of trading days in [start, end] for an exchange."""
        rows = self._conn.execute(
            """
            SELECT cal_date FROM trade_cal
            WHERE exchange = ? AND cal_date >= ? AND cal_date <= ? AND is_open = TRUE
            ORDER BY cal_date
            """,
            [exchange, start, end],
        ).fetchall()
        return [row[0] for row in rows]

    def has_trade_cal_data(self, exchange: str = "SSE") -> bool:
        """Return True when any trade calendar rows exist for an exchange."""
        row = self._conn.execute(
            "SELECT 1 FROM trade_cal WHERE exchange = ? LIMIT 1",
            [exchange],
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MetaStore:
        return self

    def __exit__(self, *args: object) -> bool:
        self.close()
        return False


# ── Parquet Read/Write Functions ───────────────────────────────────────


def _require_pyarrow() -> None:
    if pa is None or pq is None:
        raise ImportError(
            "pyarrow is required for market data storage. "
            "Install with: pip install 'finer[market-data]'"
        )


def write_daily_kline(data_dir: Path, trade_date: date, df: pd.DataFrame) -> None:
    _require_pyarrow()
    partition_dir = data_dir / "daily_kline" / f"date={trade_date.strftime('%Y%m%d')}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, partition_dir / "data.parquet")


def daily_kline_partition_exists(data_dir: Path, trade_date: date) -> bool:
    path = data_dir / "daily_kline" / f"date={trade_date.strftime('%Y%m%d')}" / "data.parquet"
    return path.exists()


def read_daily_kline(data_dir: Path, trade_date: date) -> pd.DataFrame:
    _require_pyarrow()
    path = data_dir / "daily_kline" / f"date={trade_date.strftime('%Y%m%d')}" / "data.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pq.read_table(path).to_pandas()


def write_adj_factor(data_dir: Path, trade_date: date, df: pd.DataFrame) -> None:
    _require_pyarrow()
    partition_dir = data_dir / "adj_factor" / f"date={trade_date.strftime('%Y%m%d')}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, partition_dir / "data.parquet")


def adj_factor_partition_exists(data_dir: Path, trade_date: date) -> bool:
    path = data_dir / "adj_factor" / f"date={trade_date.strftime('%Y%m%d')}" / "data.parquet"
    return path.exists()


def write_basic(data_dir: Path, df: pd.DataFrame) -> None:
    _require_pyarrow()
    basic_dir = data_dir / "basic"
    basic_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, basic_dir / "data.parquet")


def read_basic(data_dir: Path) -> pd.DataFrame:
    _require_pyarrow()
    path = data_dir / "basic" / "data.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pq.read_table(path).to_pandas()


def write_trade_cal(data_dir: Path, exchange: str, df: pd.DataFrame) -> None:
    _require_pyarrow()
    partition_dir = data_dir / "trade_cal" / f"exchange={exchange}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, partition_dir / "data.parquet")


def read_trade_cal(data_dir: Path, exchange: str) -> pd.DataFrame:
    _require_pyarrow()
    path = data_dir / "trade_cal" / f"exchange={exchange}" / "data.parquet"
    if not path.exists():
        return pd.DataFrame()
    schema = pq.read_schema(path)
    return pq.read_table(path, schema=schema).to_pandas()
