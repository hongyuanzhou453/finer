"""Market data configuration — Tushare token and storage paths.

Token is read from environment variable TUSHARE_TOKEN.
Storage paths derive from finer.paths.DATA_ROOT.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from finer.paths import DATA_ROOT, MARKET_DUCKDB_PATH, MARKET_PARQUET_DIR


@dataclass(frozen=True)
class MarketDataConfig:
    """Configuration for the Tushare market data layer."""

    tushare_token: str
    data_dir: Path
    db_path: Path
    sync_start_date: date = date(2016, 1, 1)
    request_interval: float = 0.2  # seconds between Tushare API calls


def load_market_data_config(*, require_token: bool = True) -> MarketDataConfig:
    """Load market data config from environment.

    Raises ValueError if TUSHARE_TOKEN is not set and require_token=True.
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if require_token and not token:
        raise ValueError(
            "TUSHARE_TOKEN environment variable is required for market data operations. "
            "Get your token at https://tushare.pro and set: export TUSHARE_TOKEN=your_token"
        )
    return MarketDataConfig(
        tushare_token=token,
        data_dir=MARKET_PARQUET_DIR,
        db_path=MARKET_DUCKDB_PATH,
    )
