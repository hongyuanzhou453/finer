"""TushareCalendarProvider tests — trading day queries."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Skip entire module if market-data optional deps are missing
pytest.importorskip("duckdb", reason="market-data extras not installed (pip install 'finer[market-data]')")
pytest.importorskip("pyarrow", reason="market-data extras not installed")

from finer.market_data.providers import TushareCalendarProvider
from finer.market_data.storage import write_trade_cal


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "parquet"
    # May 2026: Mon=4, Tue=5, Wed=6, Thu=7, Fri=8, Sat=9, Sun=10, Mon=11...
    # Mark Mon-Fri as open, Sat-Sun as closed
    cal_rows = []
    for day in range(4, 18):
        dt = date(2026, 5, day)
        is_open = dt.weekday() < 5  # Mon-Fri
        cal_rows.append({
            "exchange": "SSE",
            "cal_date": dt,
            "is_open": is_open,
            "pretrade_date": None,
        })
    write_trade_cal(d, "SSE", pd.DataFrame(cal_rows))
    return d


class TestTushareCalendarProvider:
    def test_is_trading_day_true(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 8 = Friday
        assert cal.is_trading_day(date(2026, 5, 8)) is True

    def test_is_trading_day_false(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 9 = Saturday
        assert cal.is_trading_day(date(2026, 5, 9)) is False

    def test_next_trading_day_from_weekday(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 8 (Fri) -> May 8 (itself)
        assert cal.next_trading_day(date(2026, 5, 8)) == date(2026, 5, 8)

    def test_next_trading_day_from_weekend(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 9 (Sat) -> May 11 (Mon)
        assert cal.next_trading_day(date(2026, 5, 9)) == date(2026, 5, 11)

    def test_prev_trading_day_from_weekday(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 8 (Fri) -> May 8
        assert cal.prev_trading_day(date(2026, 5, 8)) == date(2026, 5, 8)

    def test_prev_trading_day_from_weekend(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 10 (Sun) -> May 8 (Fri)
        assert cal.prev_trading_day(date(2026, 5, 10)) == date(2026, 5, 8)

    def test_trading_days_between(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 6 (Wed) to May 12 (Tue)
        days = cal.trading_days_between(date(2026, 5, 6), date(2026, 5, 12))
        assert len(days) == 5
        assert days[0] == date(2026, 5, 6)
        assert days[-1] == date(2026, 5, 12)
        # May 9 (Sat) and May 10 (Sun) should not be included
        assert date(2026, 5, 9) not in days
        assert date(2026, 5, 10) not in days

    def test_trading_days_between_empty(self, data_dir: Path) -> None:
        cal = TushareCalendarProvider(data_dir)
        # May 9 (Sat) to May 10 (Sun) — no trading days
        days = cal.trading_days_between(date(2026, 5, 9), date(2026, 5, 10))
        assert days == []

    def test_no_data_returns_fallback(self, tmp_path: Path) -> None:
        cal = TushareCalendarProvider(tmp_path / "empty")
        # No data => should return dt itself as fallback
        assert cal.next_trading_day(date(2026, 5, 8)) == date(2026, 5, 8)
        assert cal.prev_trading_day(date(2026, 5, 8)) == date(2026, 5, 8)
        assert cal.is_trading_day(date(2026, 5, 8)) is False
        assert cal.trading_days_between(date(2026, 5, 8), date(2026, 5, 9)) == []
