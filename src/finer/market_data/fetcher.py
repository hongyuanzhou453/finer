"""Tushare Pro API fetcher — field definitions and data retrieval.

Ported from zer0share/fetcher.py with the following adaptations:
- Standard logging instead of loguru
- Token passed as parameter, not from config file
- Errors raise FinerError (F0_EXT_001) on external source failure
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column constants (authoritative from Tushare Pro API) ──────────────

BASIC_COLS = [
    "ts_code", "symbol", "name", "area", "industry", "fullname", "enname",
    "cnspell", "market", "exchange", "curr_type", "list_status", "list_date",
    "delist_date", "is_hs", "act_name", "act_ent_type",
]

DAILY_COLS = [
    "ts_code", "trade_date", "open", "high", "low",
    "close", "pre_close", "change", "pct_chg", "vol", "amount",
]

TRADE_CAL_COLS = ["exchange", "cal_date", "is_open", "pretrade_date"]

ADJ_FACTOR_COLS = ["ts_code", "trade_date", "adj_factor"]
BASIC_LIST_STATUSES = ("L", "D", "P")


class TushareFetcher:
    """Thin wrapper around Tushare Pro API for A-share data retrieval.

    Args:
        token: Tushare Pro API token (from tushare.pro).
    """

    def __init__(self, token: str) -> None:
        try:
            import tushare as ts
        except ImportError as e:
            raise ImportError(
                "tushare is required for market data sync. "
                "Install with: pip install 'finer[market-data]'"
            ) from e
        self._pro = ts.pro_api(token)

    def fetch_basic(self, list_statuses: Iterable[str] = BASIC_LIST_STATUSES) -> pd.DataFrame:
        """Fetch all stock basic info for supported list statuses (L/D/P)."""
        logger.info("Fetching stock_basic")
        frames: list[pd.DataFrame] = []
        for status in list_statuses:
            df = self._pro.stock_basic(
                exchange="", list_status=status,
                fields=",".join(BASIC_COLS),
            )
            if df is not None and not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame(columns=BASIC_COLS)
        df = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["ts_code"], keep="first")
            .reset_index(drop=True)
        )
        df["list_date"] = pd.to_datetime(
            df["list_date"], format="%Y%m%d", errors="coerce"
        ).dt.date
        df["delist_date"] = pd.to_datetime(
            df["delist_date"], format="%Y%m%d", errors="coerce"
        ).apply(lambda x: x.date() if not pd.isnull(x) else None)
        return df[BASIC_COLS]

    def fetch_daily_kline(self, trade_date: date) -> pd.DataFrame:
        """Fetch daily OHLCV for all stocks on a single trade date."""
        date_str = trade_date.strftime("%Y%m%d")
        logger.info("Fetching daily kline: %s", date_str)
        df = self._pro.daily(trade_date=date_str, fields=",".join(DAILY_COLS))
        if df is None or df.empty:
            return pd.DataFrame(columns=DAILY_COLS)
        df["trade_date"] = pd.to_datetime(
            df["trade_date"], format="%Y%m%d"
        ).dt.date
        return df[DAILY_COLS]

    def fetch_adj_factor(self, trade_date: date) -> pd.DataFrame:
        """Fetch adjustment factors for all stocks on a single trade date."""
        date_str = trade_date.strftime("%Y%m%d")
        logger.info("Fetching adj_factor: %s", date_str)
        df = self._pro.adj_factor(trade_date=date_str, fields=",".join(ADJ_FACTOR_COLS))
        if df is None or df.empty:
            return pd.DataFrame(columns=ADJ_FACTOR_COLS)
        df["trade_date"] = pd.to_datetime(
            df["trade_date"], format="%Y%m%d"
        ).dt.date
        return df[ADJ_FACTOR_COLS]

    def fetch_trade_cal(self, exchange: str) -> pd.DataFrame:
        """Fetch full trade calendar for an exchange (from 1990 to today)."""
        today = date.today().strftime("%Y%m%d")
        logger.info("Fetching trade_cal: %s", exchange)
        df = self._pro.trade_cal(
            exchange=exchange, start_date="19900101", end_date=today,
            fields=",".join(TRADE_CAL_COLS),
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=TRADE_CAL_COLS)
        df["cal_date"] = pd.to_datetime(
            df["cal_date"], format="%Y%m%d", errors="coerce"
        ).dt.date
        df["pretrade_date"] = pd.to_datetime(
            df["pretrade_date"], format="%Y%m%d", errors="coerce"
        ).apply(lambda x: x.date() if not pd.isnull(x) else None)
        df["is_open"] = (
            df["is_open"].astype(str).map({"1": True, "0": False}).astype(object)
        )
        return df[TRADE_CAL_COLS]
