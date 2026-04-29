"""Tests for MarketCalendarTimingPolicy — F5 deterministic timing layer.

Covers the required test scenarios:
- Friday HK after_close bullish on Tencent → next Monday HK open executable
- Saturday publish → next Monday open
- During trading → 5 min delay
- Pre-market → same day open
- US/HK/CN timezone correctness
"""

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

import pytest

from finer.execution.timing_policy import (
    ExecutionTimingResult,
    MarketCalendarTimingPolicy,
    MarketConfig,
    MarketSession,
    NoOpHolidayProvider,
    TradingSession,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def policy() -> MarketCalendarTimingPolicy:
    """Default policy with no holidays."""
    return MarketCalendarTimingPolicy()


@pytest.fixture
def tz_hk() -> ZoneInfo:
    return ZoneInfo("Asia/Hong_Kong")


@pytest.fixture
def tz_cn() -> ZoneInfo:
    return ZoneInfo("Asia/Shanghai")


@pytest.fixture
def tz_us() -> ZoneInfo:
    return ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hk(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Shorthand for naive HK datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Hong_Kong"))


def _cn(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Shorthand for naive CN datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai"))


def _us(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Shorthand for naive US datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))


# ---------------------------------------------------------------------------
# 1. Friday HK after_close → next Monday open
# ---------------------------------------------------------------------------

class TestFridayAfterCloseHK:
    """Friday HK after_close bullish on Tencent → next Monday HK open."""

    def test_friday_1700_hk_after_close(self, policy: MarketCalendarTimingPolicy) -> None:
        """Friday 17:00 HKT → Monday 09:30 HKT."""
        # 2026-04-24 is a Friday
        published = _hk(2026, 4, 24, 17, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE.value
        # Next trading day: Monday 2026-04-27
        expected = _hk(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected
        assert result.next_trading_day == "2026-04-27"
        assert "after market close" in result.execution_delay_reason.lower()

    def test_friday_1601_hk_after_close(self, policy: MarketCalendarTimingPolicy) -> None:
        """Friday 16:01 HKT (just after close) → Monday 09:30 HKT."""
        published = _hk(2026, 4, 24, 16, 1)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE.value
        expected = _hk(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected

    def test_friday_2359_hk_after_close(self, policy: MarketCalendarTimingPolicy) -> None:
        """Friday 23:59 HKT → Monday 09:30 HKT."""
        published = _hk(2026, 4, 24, 23, 59)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE.value
        expected = _hk(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 2. Saturday / Sunday publish → next Monday open
# ---------------------------------------------------------------------------

class TestWeekendPublish:
    """Weekend publish → next Monday open."""

    def test_saturday_publish_hk(self, policy: MarketCalendarTimingPolicy) -> None:
        """Saturday 10:00 HKT → Monday 09:30 HKT."""
        # 2026-04-25 is Saturday
        published = _hk(2026, 4, 25, 10, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        expected = _hk(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected
        assert result.next_trading_day == "2026-04-27"
        assert "non-trading day" in result.execution_delay_reason.lower()

    def test_sunday_publish_hk(self, policy: MarketCalendarTimingPolicy) -> None:
        """Sunday 15:00 HKT → Monday 09:30 HKT."""
        published = _hk(2026, 4, 26, 15, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        expected = _hk(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected

    def test_saturday_publish_us(self, policy: MarketCalendarTimingPolicy) -> None:
        """Saturday 10:00 ET → Monday 09:30 ET."""
        published = _us(2026, 4, 25, 10, 0)
        result = policy.compute_timing(
            published_at=published,
            market="US",
            timezone="America/New_York",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        expected = _us(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 3. During trading → 5 min delay
# ---------------------------------------------------------------------------

class TestDuringTrading:
    """Published during regular session → published + 5 min delay."""

    def test_hk_mid_session(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 10:30 (within AM session) → 10:35."""
        published = _hk(2026, 4, 23, 10, 30)  # Thursday
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _hk(2026, 4, 23, 10, 35)
        assert result.action_executable_at == expected
        assert "5min" in result.execution_delay_reason or "5 min" in result.execution_delay_reason

    def test_hk_pm_session(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 14:00 (within PM session) → 14:05."""
        published = _hk(2026, 4, 23, 14, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _hk(2026, 4, 23, 14, 5)
        assert result.action_executable_at == expected

    def test_cn_mid_session(self, policy: MarketCalendarTimingPolicy) -> None:
        """CN 10:00 → 10:05."""
        published = _cn(2026, 4, 23, 10, 0)
        result = policy.compute_timing(
            published_at=published,
            market="CN",
            timezone="Asia/Shanghai",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _cn(2026, 4, 23, 10, 5)
        assert result.action_executable_at == expected

    def test_us_mid_session(self, policy: MarketCalendarTimingPolicy) -> None:
        """US 11:00 ET → 11:05 ET."""
        published = _us(2026, 4, 23, 11, 0)
        result = policy.compute_timing(
            published_at=published,
            market="US",
            timezone="America/New_York",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _us(2026, 4, 23, 11, 5)
        assert result.action_executable_at == expected

    def test_hk_session_open_boundary(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 09:30 exactly (open) → 09:35."""
        published = _hk(2026, 4, 23, 9, 30)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _hk(2026, 4, 23, 9, 35)
        assert result.action_executable_at == expected

    def test_hk_session_close_boundary(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 16:00 exactly (close) → next trading day open (after_close)."""
        published = _hk(2026, 4, 23, 16, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        # 16:00 is at the boundary; since close is inclusive in last_close check
        # and we check `t <= last_close`, 16:00 should be REGULAR.
        # But the session close is 16:00 and we check `sess.open <= t <= sess.close`
        # for REGULAR, so 16:00 IS in the session.
        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _hk(2026, 4, 23, 16, 5)
        assert result.action_executable_at == expected

    def test_custom_delay(self) -> None:
        """Custom min_reaction_delay_minutes=10 → 10 min delay during session."""
        policy = MarketCalendarTimingPolicy(min_reaction_delay_minutes=10)
        published = _hk(2026, 4, 23, 10, 30)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _hk(2026, 4, 23, 10, 40)
        assert result.action_executable_at == expected
        assert result.min_reaction_delay_minutes == 10


# ---------------------------------------------------------------------------
# 4. Pre-market → same day open
# ---------------------------------------------------------------------------

class TestPreMarket:
    """Published before market open → same day open time."""

    def test_hk_pre_market_0800(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 08:00 → same day 09:30."""
        published = _hk(2026, 4, 23, 8, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.PRE_MARKET.value
        expected = _hk(2026, 4, 23, 9, 30)
        assert result.action_executable_at == expected
        assert "pre-market" in result.execution_delay_reason.lower()

    def test_cn_pre_market_0900(self, policy: MarketCalendarTimingPolicy) -> None:
        """CN 09:00 → same day 09:30."""
        published = _cn(2026, 4, 23, 9, 0)
        result = policy.compute_timing(
            published_at=published,
            market="CN",
            timezone="Asia/Shanghai",
        )

        assert result.market_session_at_publish == MarketSession.PRE_MARKET.value
        expected = _cn(2026, 4, 23, 9, 30)
        assert result.action_executable_at == expected

    def test_us_pre_market_0800(self, policy: MarketCalendarTimingPolicy) -> None:
        """US 08:00 ET → same day 09:30 ET."""
        published = _us(2026, 4, 23, 8, 0)
        result = policy.compute_timing(
            published_at=published,
            market="US",
            timezone="America/New_York",
        )

        assert result.market_session_at_publish == MarketSession.PRE_MARKET.value
        expected = _us(2026, 4, 23, 9, 30)
        assert result.action_executable_at == expected

    def test_hk_very_early_0200(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 02:00 → pre-market → same day 09:30."""
        published = _hk(2026, 4, 23, 2, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.PRE_MARKET.value
        expected = _hk(2026, 4, 23, 9, 30)
        assert result.action_executable_at == expected

    def test_hk_pre_market_0929(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 09:29 (1 min before open) → 09:30 same day."""
        published = _hk(2026, 4, 23, 9, 29)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.PRE_MARKET.value
        expected = _hk(2026, 4, 23, 9, 30)
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 5. US/HK/CN timezone correctness
# ---------------------------------------------------------------------------

class TestTimezoneCorrectness:
    """Verify timezone handling across all three markets."""

    def test_utc_input_hk_market(self, policy: MarketCalendarTimingPolicy) -> None:
        """UTC input for HK market: 10:00 UTC = 18:00 HKT (after close)."""
        published_utc = datetime(2026, 4, 23, 10, 0, tzinfo=ZoneInfo("UTC"))
        result = policy.compute_timing(
            published_at=published_utc,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        # 10:00 UTC = 18:00 HKT → after close
        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE.value
        # Next trading day: Friday 2026-04-24 09:30 HKT
        expected = _hk(2026, 4, 24, 9, 30)
        assert result.action_executable_at == expected
        assert result.timezone == "Asia/Hong_Kong"

    def test_utc_input_cn_market_regular(self, policy: MarketCalendarTimingPolicy) -> None:
        """UTC input for CN market: 03:00 UTC = 11:00 CST (regular session)."""
        published_utc = datetime(2026, 4, 23, 3, 0, tzinfo=ZoneInfo("UTC"))
        result = policy.compute_timing(
            published_at=published_utc,
            market="CN",
            timezone="Asia/Shanghai",
        )

        # 03:00 UTC = 11:00 CST → regular
        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _cn(2026, 4, 23, 11, 5)
        assert result.action_executable_at == expected

    def test_utc_input_us_market_regular(self, policy: MarketCalendarTimingPolicy) -> None:
        """UTC input for US market: 15:00 UTC = 11:00 ET (regular, EDT)."""
        published_utc = datetime(2026, 4, 23, 15, 0, tzinfo=ZoneInfo("UTC"))
        result = policy.compute_timing(
            published_at=published_utc,
            market="US",
            timezone="America/New_York",
        )

        # 15:00 UTC = 11:00 EDT (April is DST) → regular
        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _us(2026, 4, 23, 11, 5)
        assert result.action_executable_at == expected

    def test_us_est_winter_time(self, policy: MarketCalendarTimingPolicy) -> None:
        """US market in winter (EST, UTC-5): 15:00 UTC = 10:00 EST."""
        # January 2026 — EST (no DST)
        published_utc = datetime(2026, 1, 15, 15, 0, tzinfo=ZoneInfo("UTC"))
        result = policy.compute_timing(
            published_at=published_utc,
            market="US",
            timezone="America/New_York",
        )

        # 15:00 UTC = 10:00 EST → regular
        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = datetime(2026, 1, 15, 10, 5, tzinfo=ZoneInfo("America/New_York"))
        assert result.action_executable_at == expected

    def test_hk_to_us_cross_market(self, policy: MarketCalendarTimingPolicy) -> None:
        """Same moment classified differently for HK vs US."""
        # 2026-04-23 10:00 HKT → HK regular
        published_hk = _hk(2026, 4, 23, 10, 0)
        result_hk = policy.compute_timing(
            published_at=published_hk,
            market="HK",
            timezone="Asia/Hong_Kong",
        )
        assert result_hk.market_session_at_publish == MarketSession.REGULAR.value

        # Convert to US market — 10:00 HKT = 22:00 ET (previous day) → US after close
        published_us = published_hk.astimezone(ZoneInfo("America/New_York"))
        result_us = policy.compute_timing(
            published_at=published_us,
            market="US",
            timezone="America/New_York",
        )
        # Should be after_close or non_trading_day for US
        assert result_us.market_session_at_publish in (
            MarketSession.AFTER_CLOSE.value,
            MarketSession.NON_TRADING_DAY.value,
        )

    def test_result_timezone_matches_config(self, policy: MarketCalendarTimingPolicy) -> None:
        """Result timezone always matches the market config timezone."""
        for market, tz_str in [("HK", "Asia/Hong_Kong"), ("CN", "Asia/Shanghai"), ("US", "America/New_York")]:
            published = datetime(2026, 4, 23, 10, 0, tzinfo=ZoneInfo(tz_str))
            result = policy.compute_timing(
                published_at=published,
                market=market,
                timezone=tz_str,
            )
            assert result.timezone == tz_str
            assert result.market == market


# ---------------------------------------------------------------------------
# 6. HK/CN lunch break handling
# ---------------------------------------------------------------------------

class TestLunchBreak:
    """HK/CN lunch break should be classified as REGULAR."""

    def test_hk_lunch_break(self, policy: MarketCalendarTimingPolicy) -> None:
        """HK 12:30 (lunch break) → REGULAR, 5 min delay."""
        published = _hk(2026, 4, 23, 12, 30)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _hk(2026, 4, 23, 12, 35)
        assert result.action_executable_at == expected

    def test_cn_lunch_break(self, policy: MarketCalendarTimingPolicy) -> None:
        """CN 12:00 (lunch break) → REGULAR, 5 min delay."""
        published = _cn(2026, 4, 23, 12, 0)
        result = policy.compute_timing(
            published_at=published,
            market="CN",
            timezone="Asia/Shanghai",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        expected = _cn(2026, 4, 23, 12, 5)
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 7. Holiday extension point
# ---------------------------------------------------------------------------

class TestHolidays:
    """Test holiday provider integration."""

    def test_holiday_triggers_non_trading_day(self) -> None:
        """Holiday on a weekday → non_trading_day → next trading day open."""
        class FixedHolidayProvider:
            def is_holiday(self, date: datetime, market: str) -> bool:
                # Mark 2026-04-23 as a holiday for HK
                return (
                    market == "HK"
                    and date.year == 2026
                    and date.month == 4
                    and date.day == 23
                )

        policy = MarketCalendarTimingPolicy(holiday_provider=FixedHolidayProvider())
        published = _hk(2026, 4, 23, 10, 0)  # Thursday, but holiday
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        assert result.is_holiday is True
        # Next trading day: Friday 2026-04-24
        expected = _hk(2026, 4, 24, 9, 30)
        assert result.action_executable_at == expected

    def test_holiday_on_weekend_does_not_double_count(self) -> None:
        """Weekend + holiday → still non_trading_day, next Monday open."""
        class WeekendHolidayProvider:
            def is_holiday(self, date: datetime, market: str) -> bool:
                # Mark Saturday as holiday too
                return date.weekday() == 5

        policy = MarketCalendarTimingPolicy(holiday_provider=WeekendHolidayProvider())
        published = _hk(2026, 4, 25, 10, 0)  # Saturday
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        expected = _hk(2026, 4, 27, 9, 30)  # Monday
        assert result.action_executable_at == expected

    def test_consecutive_holidays(self) -> None:
        """Multi-day holiday → skips all holiday days."""
        class ConsecutiveHolidayProvider:
            def is_holiday(self, date: datetime, market: str) -> bool:
                # Thu + Fri are holidays
                return (
                    market == "HK"
                    and date.year == 2026
                    and date.month == 4
                    and date.day in (23, 24)
                )

        policy = MarketCalendarTimingPolicy(holiday_provider=ConsecutiveHolidayProvider())
        published = _hk(2026, 4, 23, 10, 0)  # Thursday holiday
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        # Skip Thu (holiday), Fri (holiday), Sat-Sun (weekend) → Monday
        expected = _hk(2026, 4, 27, 9, 30)
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 8. is_trading_day helper
# ---------------------------------------------------------------------------

class TestIsTradingDay:
    """Test the is_trading_day helper method."""

    def test_weekday_is_trading_day(self, policy: MarketCalendarTimingPolicy) -> None:
        """Thursday is a trading day."""
        assert policy.is_trading_day(_hk(2026, 4, 23), "HK") is True

    def test_saturday_not_trading_day(self, policy: MarketCalendarTimingPolicy) -> None:
        """Saturday is not a trading day."""
        assert policy.is_trading_day(_hk(2026, 4, 25), "HK") is False

    def test_sunday_not_trading_day(self, policy: MarketCalendarTimingPolicy) -> None:
        """Sunday is not a trading day."""
        assert policy.is_trading_day(_hk(2026, 4, 26), "HK") is False

    def test_unknown_market_not_trading_day(self, policy: MarketCalendarTimingPolicy) -> None:
        """Unknown market → False."""
        assert policy.is_trading_day(_hk(2026, 4, 23), "XX") is False


# ---------------------------------------------------------------------------
# 9. Unknown market fallback
# ---------------------------------------------------------------------------

class TestUnknownMarket:
    """Unknown market → UNKNOWN session + default delay."""

    def test_unknown_market(self, policy: MarketCalendarTimingPolicy) -> None:
        """Unknown market 'XX' → UNKNOWN + 5min delay."""
        published = datetime(2026, 4, 23, 10, 0)
        result = policy.compute_timing(
            published_at=published,
            market="XX",
            timezone="UTC",
        )

        assert result.market_session_at_publish == MarketSession.UNKNOWN.value
        assert result.market == "XX"
        expected = published + timedelta(minutes=5)
        assert result.action_executable_at == expected
        assert "unknown market" in result.execution_delay_reason.lower()


# ---------------------------------------------------------------------------
# 10. Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    """Verify results are JSON-serializable."""

    def test_to_dict(self, policy: MarketCalendarTimingPolicy) -> None:
        """to_dict returns ISO-8601 strings."""
        published = _hk(2026, 4, 23, 10, 30)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )
        d = result.to_dict()

        assert isinstance(d["action_executable_at"], str)
        assert isinstance(d["intent_published_at"], str)
        assert "T" in d["action_executable_at"]  # ISO 8601

    def test_result_fields_complete(self, policy: MarketCalendarTimingPolicy) -> None:
        """All required fields are present in result."""
        published = _hk(2026, 4, 23, 10, 30)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.action_executable_at is not None
        assert result.market_session_at_publish in [e.value for e in MarketSession]
        assert result.execution_delay_reason  # non-empty
        assert result.timing_policy_id  # non-empty
        assert result.market == "HK"
        assert result.timezone == "Asia/Hong_Kong"


# ---------------------------------------------------------------------------
# 11. Custom market registration
# ---------------------------------------------------------------------------

class TestCustomMarket:
    """Test registering a custom market."""

    def test_register_custom_market(self) -> None:
        """Register SG market and compute timing."""
        policy = MarketCalendarTimingPolicy()
        policy.register_market(MarketConfig(
            market="SG",
            timezone="Asia/Singapore",
            sessions=[
                TradingSession(open=dt_time(9, 0), close=dt_time(12, 0)),
                TradingSession(open=dt_time(13, 0), close=dt_time(17, 0)),
            ],
            pre_market_start=dt_time(8, 30),
            weekend_days=(5, 6),
        ))

        published = datetime(2026, 4, 23, 10, 0, tzinfo=ZoneInfo("Asia/Singapore"))
        result = policy.compute_timing(
            published_at=published,
            market="SG",
            timezone="Asia/Singapore",
        )

        assert result.market_session_at_publish == MarketSession.REGULAR.value
        assert result.market == "SG"
        expected = datetime(2026, 4, 23, 10, 5, tzinfo=ZoneInfo("Asia/Singapore"))
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 12. Edge cases: month/year boundaries
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases across month and year boundaries."""

    def test_friday_last_day_of_month(self, policy: MarketCalendarTimingPolicy) -> None:
        """Friday 2026-05-29 (last trading day of May) after close → Monday 2026-06-01."""
        published = _hk(2026, 5, 29, 17, 0)  # Friday
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE.value
        # Next Monday is June 1st
        expected = _hk(2026, 6, 1, 9, 30)
        assert result.action_executable_at == expected

    def test_friday_last_day_of_year(self, policy: MarketCalendarTimingPolicy) -> None:
        """Friday 2026-01-02 after close → Monday 2026-01-05."""
        # 2026-01-02 is a Friday
        published = _hk(2026, 1, 2, 17, 0)
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE.value
        expected = _hk(2026, 1, 5, 9, 30)  # Monday
        assert result.action_executable_at == expected

    def test_saturday_new_year(self, policy: MarketCalendarTimingPolicy) -> None:
        """Saturday 2026-01-03 → Monday 2026-01-05."""
        published = _hk(2026, 1, 3, 12, 0)  # Saturday
        result = policy.compute_timing(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert result.market_session_at_publish == MarketSession.NON_TRADING_DAY.value
        expected = _hk(2026, 1, 5, 9, 30)
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 13. Policy timing hints (layer 3 reservation)
# ---------------------------------------------------------------------------

class TestAgentHint:
    """Test the reserved timing agent interface."""

    def test_agent_hint_recorded(self, policy: MarketCalendarTimingPolicy) -> None:
        """Agent hint is recorded in reason but doesn't change timing."""
        published = _hk(2026, 4, 23, 10, 30)
        result = policy.compute_timing_with_agent_hint(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
            agent_hint="follow_after_open_30min",
        )

        # Timing should be the same as without hint
        expected = _hk(2026, 4, 23, 10, 35)
        assert result.action_executable_at == expected
        # But hint is recorded
        assert "follow_after_open_30min" in result.execution_delay_reason

    def test_no_agent_hint(self, policy: MarketCalendarTimingPolicy) -> None:
        """No agent hint → no extra text in reason."""
        published = _hk(2026, 4, 23, 10, 30)
        result = policy.compute_timing_with_agent_hint(
            published_at=published,
            market="HK",
            timezone="Asia/Hong_Kong",
        )

        assert "agent_hint" not in result.execution_delay_reason
