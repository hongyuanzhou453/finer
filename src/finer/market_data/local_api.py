"""Local Pro API — Tushare-compatible query interface over local Parquet files.

Ported from zer0share/api.py with the following adaptations:
- No pro_api() factory (config passed explicitly)
- Standard logging instead of loguru
- DuckDB connections are per-query (no persistent connection pool)

All queries read from local Parquet via DuckDB — no network calls, no Tushare credits.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

from finer.market_data.fetcher import ADJ_FACTOR_COLS, BASIC_COLS, DAILY_COLS, TRADE_CAL_COLS

logger = logging.getLogger(__name__)


class LocalPro:
    """Tushare-compatible local query API backed by Parquet + DuckDB.

    Args:
        data_dir: Root directory of Parquet partitions (e.g. data/market/tushare/parquet).
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    # ── stock_basic ─────────────────────────────────────────────────────

    def stock_basic(
        self,
        ts_code: str | None = None,
        name: str | None = None,
        market: str | None = None,
        list_status: str | None = "L",
        exchange: str | None = None,
        is_hs: str | None = None,
        fields: str | list[str] | None = None,
    ) -> pd.DataFrame:
        _require_duckdb()
        path = self._data_dir / "basic" / "data.parquet"
        if not path.exists():
            raise FileNotFoundError(
                "basic data not found. Run: finer market-data sync --table basic"
            )
        columns = _parse_fields(fields, BASIC_COLS)
        where, params = [], []
        if ts_code is not None:
            where.append("ts_code = ?"); params.append(ts_code)
        if name is not None:
            where.append("name = ?"); params.append(name)
        if market is not None:
            where.append("market = ?"); params.append(market)
        if list_status is not None:
            where.append("list_status = ?"); params.append(list_status)
        if exchange is not None:
            where.append("exchange = ?"); params.append(exchange)
        if is_hs is not None:
            where.append("is_hs = ?"); params.append(is_hs)

        sql = f"SELECT {', '.join(columns)} FROM read_parquet(?)"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts_code"

        df = duckdb.connect().execute(sql, [str(path), *params]).fetchdf()
        return _format_date_columns(df, ["list_date", "delist_date"])

    # ── trade_cal ───────────────────────────────────────────────────────

    def trade_cal(
        self,
        exchange: str = "SSE",
        start_date: str | None = None,
        end_date: str | None = None,
        is_open: str | int | bool | None = None,
        fields: str | list[str] | None = None,
    ) -> pd.DataFrame:
        _require_duckdb()
        trade_cal_dir = self._data_dir / "trade_cal"
        if not _trade_cal_files_exist(trade_cal_dir):
            raise FileNotFoundError(
                "trade_cal data not found. Run: finer market-data sync --table trade_cal"
            )
        columns = _parse_fields(fields, TRADE_CAL_COLS)
        where, params = ["exchange = ?"], [exchange]
        parsed_start = _parse_date(start_date) if start_date else None
        parsed_end = _parse_date(end_date) if end_date else None
        if parsed_start and parsed_end and parsed_end < parsed_start:
            raise ValueError("end_date must be on or after start_date")
        if parsed_start:
            where.append("cal_date >= ?"); params.append(parsed_start)
        if parsed_end:
            where.append("cal_date <= ?"); params.append(parsed_end)
        if is_open is not None:
            where.append("is_open = ?"); params.append(_parse_is_open(is_open))

        pattern = trade_cal_dir / "exchange=*" / "data.parquet"
        sql = (
            f"SELECT {', '.join(columns)} FROM read_parquet(?, hive_partitioning=true) "
            f"WHERE {' AND '.join(where)} ORDER BY exchange, cal_date"
        )
        df = duckdb.connect().execute(sql, [str(pattern), *params]).fetchdf()
        return _format_date_columns(df, ["cal_date", "pretrade_date"])

    # ── daily ───────────────────────────────────────────────────────────

    def daily(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        fields: str | list[str] | None = None,
    ) -> pd.DataFrame:
        return self._query_daily_partitioned(
            "daily_kline", DAILY_COLS, ts_code, trade_date, start_date, end_date, fields,
        )

    # ── adj_factor ──────────────────────────────────────────────────────

    def adj_factor(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        fields: str | list[str] | None = None,
    ) -> pd.DataFrame:
        return self._query_daily_partitioned(
            "adj_factor", ADJ_FACTOR_COLS, ts_code, trade_date, start_date, end_date, fields,
        )

    # ── pro_bar (adjusted OHLCV) ────────────────────────────────────────

    def pro_bar(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        adj: str | None = "qfq",
    ) -> pd.DataFrame:
        """Return daily OHLCV with optional adjustment (qfq/hfq/None).

        Args:
            ts_code: Stock code (e.g. "000001.SZ").
            start_date: Start date (YYYYMMDD or YYYY-MM-DD).
            end_date: End date.
            adj: Adjustment mode — None (raw), "qfq" (forward), "hfq" (backward).
        """
        if adj not in (None, "qfq", "hfq"):
            raise ValueError("adj must be one of None, 'qfq', or 'hfq'")

        daily = self.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if adj is None or daily.empty:
            return daily

        try:
            factors = self.adj_factor(
                ts_code=ts_code, start_date=start_date, end_date=end_date,
            )
        except FileNotFoundError:
            logger.debug("adj_factor data missing; returning raw daily prices for %s", ts_code)
            return daily
        if factors.empty:
            logger.debug("adj_factor rows missing; returning raw daily prices for %s", ts_code)
            return daily

        result = daily.merge(
            factors[["ts_code", "trade_date", "adj_factor"]],
            on=["ts_code", "trade_date"],
            how="left",
        ).sort_values(["ts_code", "trade_date"])
        result["adj_factor"] = result.groupby("ts_code")["adj_factor"].bfill()
        result = result.dropna(subset=["adj_factor"])
        if result.empty:
            return daily.iloc[0:0].copy()

        price_cols = ["open", "high", "low", "close", "pre_close"]
        if adj == "qfq":
            base_factor = result.sort_values("trade_date").iloc[-1]["adj_factor"]
            multiplier = result["adj_factor"] / base_factor
        else:
            multiplier = result["adj_factor"]

        for col in price_cols:
            result[col] = (result[col] * multiplier).round(2)

        result["change"] = (result["close"] - result["pre_close"]).round(2)
        result["pct_chg"] = (result["change"] / result["pre_close"] * 100).round(2)
        return result.drop(columns=["adj_factor"])

    # ── internal ────────────────────────────────────────────────────────

    def _query_daily_partitioned(
        self,
        table_name: str,
        columns: list[str],
        ts_code: str | None,
        trade_date: str | None,
        start_date: str | None,
        end_date: str | None,
        fields: str | list[str] | None,
    ) -> pd.DataFrame:
        _require_duckdb()
        if trade_date and (start_date or end_date):
            raise ValueError("trade_date cannot be combined with start_date or end_date")
        parsed_start = _parse_date(start_date) if start_date else None
        parsed_end = _parse_date(end_date) if end_date else None
        if parsed_start and parsed_end and parsed_end < parsed_start:
            raise ValueError("end_date must be on or after start_date")

        table_dir = self._data_dir / table_name
        if not _partition_files_exist(table_dir):
            raise FileNotFoundError(
                f"{table_name} data not found. Run: finer market-data sync --table {table_name}"
            )

        selected = _parse_fields(fields, columns)
        where, params = [], []
        if ts_code:
            codes = [c.strip() for c in ts_code.split(",") if c.strip()]
            placeholders = ", ".join("?" for _ in codes)
            where.append(f"ts_code IN ({placeholders})")
            params.extend(codes)
        if trade_date:
            where.append("trade_date = ?"); params.append(_parse_date(trade_date).strftime("%Y%m%d"))
        if parsed_start:
            where.append("trade_date >= ?"); params.append(parsed_start.strftime("%Y%m%d"))
        if parsed_end:
            where.append("trade_date <= ?"); params.append(parsed_end.strftime("%Y%m%d"))

        pattern = table_dir / "date=*" / "data.parquet"
        sql = f"SELECT {', '.join(selected)} FROM read_parquet(?, hive_partitioning=true)"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts_code, trade_date"

        df = duckdb.connect().execute(sql, [str(pattern), *params]).fetchdf()
        return _format_date_columns(df, ["trade_date"])


# ── Helpers ─────────────────────────────────────────────────────────────


def _require_duckdb() -> None:
    if duckdb is None:
        raise ImportError(
            "duckdb is required for LocalPro queries. "
            "Install with: pip install 'finer[market-data]'"
        )


def _parse_fields(fields: str | list[str] | None, default_columns: list[str]) -> list[str]:
    if fields is None:
        return list(default_columns)
    if isinstance(fields, str):
        parsed = [f.strip() for f in fields.split(",") if f.strip()]
    else:
        parsed = list(fields)
    unknown = [f for f in parsed if f not in default_columns]
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(unknown)}")
    return parsed


def _parse_date(value: str) -> __import__("datetime").date:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date format: {value}")


def _parse_is_open(value: str | int | bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1"):
        return True
    if value in (0, "0"):
        return False
    raise ValueError("is_open must be one of True, False, 1, 0, '1', '0'")


def _partition_files_exist(table_dir: Path) -> bool:
    return table_dir.exists() and any(table_dir.glob("date=*/data.parquet"))


def _trade_cal_files_exist(table_dir: Path) -> bool:
    return table_dir.exists() and any(table_dir.glob("exchange=*/data.parquet"))


def _format_date_columns(df: pd.DataFrame, date_columns: list[str]) -> pd.DataFrame:
    for col in date_columns:
        if col not in df.columns:
            continue
        formatted = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y%m%d")
        df[col] = formatted.astype(object)
        df.loc[formatted.isna(), col] = None
    return df
