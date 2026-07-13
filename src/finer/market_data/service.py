"""Market data sync service — incremental Tushare data synchronization.

Adapted from zer0share/pipeline.py with the following changes:
- Standard logging instead of loguru
- No Notifier dependency (errors logged, optionally reported via Finer error system)
- MarketDataConfig instead of TOML-based Config
- Added sync_status() for non-destructive state inspection
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from finer.market_data.config import MarketDataConfig
from finer.market_data.fetcher import TushareFetcher
from finer.market_data.storage import (
    MetaStore,
    adj_factor_partition_exists,
    daily_kline_partition_exists,
    write_adj_factor,
    write_basic,
    write_daily_kline,
    write_trade_cal,
)

logger = logging.getLogger(__name__)

FIRST_DATE = date(2016, 1, 1)
EXCHANGES = ["SSE", "SZSE", "CFFEX", "SHFE", "CZCE", "DCE", "INE"]


class MarketDataSyncService:
    """Orchestrates incremental sync of Tushare data to local Parquet storage.

    Usage:
        config = load_market_data_config()
        service = MarketDataSyncService(config)
        service.sync_all()
    """

    def __init__(
        self,
        config: MarketDataConfig,
        *,
        fetcher: TushareFetcher | None = None,
        meta: MetaStore | None = None,
    ) -> None:
        self._cfg = config
        self._fetcher = fetcher or TushareFetcher(config.tushare_token)
        self._meta = meta or MetaStore(config.db_path)

    def sync_trade_cal(self) -> None:
        """Sync trade calendars for all exchanges."""
        try:
            for exchange in EXCHANGES:
                df = self._fetcher.fetch_trade_cal(exchange)
                write_trade_cal(self._cfg.data_dir, exchange, df)
                logger.info("trade_cal %s written: %d rows", exchange, len(df))
            self._meta.load_trade_cal_from_parquet(self._cfg.data_dir)
            self._meta.update_last_date("trade_cal", date.today())
            logger.info("trade_cal sync complete")
        except Exception as e:
            logger.error("trade_cal sync failed: %s", e)
            raise

    def sync_basic(self) -> None:
        """Sync stock basic info."""
        today = date.today()
        try:
            df = self._fetcher.fetch_basic()
            write_basic(self._cfg.data_dir, df)
            self._meta.update_last_date("basic", today)
            logger.info("basic sync complete: %d rows", len(df))
        except Exception as e:
            logger.error("basic sync failed: %s", e)
            raise

    def sync_daily_kline(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> None:
        """Sync daily OHLCV data incrementally."""
        today = date.today()
        last = self._meta.get_last_date("daily_kline")

        if start_date is None:
            start = (last + timedelta(days=1)) if last else self._cfg.sync_start_date
            end = today
        else:
            start = start_date
            end = end_date or today

        if start_date is None and start > end:
            logger.info("daily_kline already up to date")
            return

        if start > end:
            raise ValueError("start_date must be on or before end_date")

        self._ensure_trade_cal_loaded()
        trading_days = self._meta.get_trading_days("SSE", start, end)
        if not trading_days and not self._meta.has_trade_cal_data("SSE"):
            raise RuntimeError(
                "No trade_cal data in DuckDB. Run sync_trade_cal() first."
            )

        if not trading_days:
            logger.info("No trading days in range, nothing to sync")
            return

        success = 0
        skipped = 0
        frontier = last

        for trade_date in trading_days:
            if daily_kline_partition_exists(self._cfg.data_dir, trade_date):
                skipped += 1
                if frontier is None or trade_date > frontier:
                    self._meta.update_last_date("daily_kline", trade_date)
                    frontier = trade_date
                continue
            try:
                df = self._fetcher.fetch_daily_kline(trade_date)
                time.sleep(self._cfg.request_interval)
                if not df.empty:
                    write_daily_kline(self._cfg.data_dir, trade_date, df)
                    if frontier is None or trade_date > frontier:
                        self._meta.update_last_date("daily_kline", trade_date)
                        frontier = trade_date
                    success += 1
            except Exception as e:
                logger.error("daily_kline %s failed: %s", trade_date, e)
                raise

        logger.info(
            "daily_kline sync: %d succeeded, %d skipped, %d total trading days",
            success, skipped, len(trading_days),
        )

    def sync_adj_factor(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> None:
        """Sync adjustment factors incrementally."""
        today = date.today()
        last = self._meta.get_last_date("adj_factor")

        if start_date is None:
            start = (last + timedelta(days=1)) if last else self._cfg.sync_start_date
            end = today
        else:
            start = start_date
            end = end_date or today

        if start_date is None and start > end:
            logger.info("adj_factor already up to date")
            return

        if start > end:
            raise ValueError("start_date must be on or before end_date")

        self._ensure_trade_cal_loaded()
        trading_days = self._meta.get_trading_days("SSE", start, end)
        if not trading_days and not self._meta.has_trade_cal_data("SSE"):
            raise RuntimeError(
                "No trade_cal data in DuckDB. Run sync_trade_cal() first."
            )

        if not trading_days:
            logger.info("No trading days in range, nothing to sync")
            return

        success = 0
        skipped = 0
        frontier = last

        for trade_date in trading_days:
            if adj_factor_partition_exists(self._cfg.data_dir, trade_date):
                skipped += 1
                if frontier is None or trade_date > frontier:
                    self._meta.update_last_date("adj_factor", trade_date)
                    frontier = trade_date
                continue
            try:
                df = self._fetcher.fetch_adj_factor(trade_date)
                time.sleep(self._cfg.request_interval)
                if not df.empty:
                    write_adj_factor(self._cfg.data_dir, trade_date, df)
                    if frontier is None or trade_date > frontier:
                        self._meta.update_last_date("adj_factor", trade_date)
                        frontier = trade_date
                    success += 1
            except Exception as e:
                logger.error("adj_factor %s failed: %s", trade_date, e)
                raise

        logger.info(
            "adj_factor sync: %d succeeded, %d skipped, %d total trading days",
            success, skipped, len(trading_days),
        )

    def sync_all(self) -> dict[str, str]:
        """Sync all tables in dependency order. Returns status per table."""
        results: dict[str, str] = {}
        for name, method in [
            ("trade_cal", self.sync_trade_cal),
            ("basic", self.sync_basic),
            ("daily_kline", self.sync_daily_kline),
            ("adj_factor", self.sync_adj_factor),
        ]:
            try:
                method()
                results[name] = "ok"
            except Exception as e:
                results[name] = f"error: {e}"
                logger.error("sync_all: %s failed, aborting remaining", name)
                break
        return results

    def sync_status(self) -> dict[str, date | None]:
        """Return last sync date for each table (read-only, no network calls)."""
        return {
            "trade_cal": self._meta.get_last_date("trade_cal"),
            "basic": self._meta.get_last_date("basic"),
            "daily_kline": self._meta.get_last_date("daily_kline"),
            "adj_factor": self._meta.get_last_date("adj_factor"),
        }

    def _ensure_trade_cal_loaded(self) -> None:
        """Hydrate DuckDB calendar metadata from existing Parquet if needed."""
        if self._meta.get_last_date("trade_cal") is not None:
            return
        self._meta.load_trade_cal_from_parquet(self._cfg.data_dir)

    def close(self) -> None:
        self._meta.close()

    def __enter__(self) -> MarketDataSyncService:
        return self

    def __exit__(self, *args: object) -> bool:
        self.close()
        return False
