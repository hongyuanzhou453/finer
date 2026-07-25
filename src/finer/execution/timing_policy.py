"""Market Calendar Timing Policy — deterministic F5 timing layer.

Implements the first layer of the F5 three-layer timing system:
1. Market Calendar Rules (THIS MODULE) — deterministic, no LLM
2. Policy Timing Rules — F4 policy output timing hints
3. Optional Timing Agent / Quant Bot — constrained by layers 1 & 2

Design principles:
- Pure deterministic rules — zero LLM decisions
- Timezone-aware via zoneinfo (PEP 615)
- Holiday extension point via `is_holiday` hook
- Supported markets: single truth table ``MARKET_SESSIONS`` below (HK/CN/US
  plus every market code derivable from the F2 ticker suffix tables in
  ``enrichment/ticker_normalization.py``)
- All outputs are JSON-serializable via Pydantic V2

Architecture position: F5 Execute stage, called by trade_action_extractor
to compute execution_timing.action_executable_at.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Enums & Data Classes (local models; ExecutionTiming in trade_action.py
# is the canonical downstream consumer — these are the policy's own output)
# ---------------------------------------------------------------------------


class MarketSession(str, Enum):
    """Classification of market state at time of publication."""
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_CLOSE = "after_close"
    NON_TRADING_DAY = "non_trading_day"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TradingSession:
    """A single continuous trading window within a trading day."""
    open: dt_time
    close: dt_time


@dataclass(frozen=True)
class MarketConfig:
    """Configuration for a single market."""
    market: str
    timezone: str
    sessions: List[TradingSession]
    pre_market_start: dt_time
    weekend_days: tuple[int, ...]  # 0=Mon .. 6=Sun


@dataclass
class ExecutionTimingResult:
    """Output of MarketCalendarTimingPolicy.compute_timing().

    Maps 1:1 to ExecutionTiming fields in schemas/trade_action.py.
    """

    # Core output
    action_executable_at: datetime
    market_session_at_publish: str  # MarketSession value
    execution_delay_reason: str
    timing_policy_id: str

    # Echo-back for audit trail
    intent_published_at: datetime
    market: str
    timezone: str

    # Metadata
    min_reaction_delay_minutes: int
    is_holiday: bool = False
    next_trading_day: Optional[str] = None  # ISO date string if jumped

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict with ISO-8601 timestamps."""
        d = asdict(self)
        d["action_executable_at"] = self.action_executable_at.isoformat()
        d["intent_published_at"] = self.intent_published_at.isoformat()
        return d


# ---------------------------------------------------------------------------
# Market session table — SINGLE truth source for market → timezone/sessions.
# ---------------------------------------------------------------------------
# Consumed by both MarketCalendarTimingPolicy (registration) and
# extraction/timing_builder.py (timezone resolution). Do NOT fork a second
# market → timezone map elsewhere.
#
# Coverage = HK/CN/US (byte-identical to the original built-ins — zero
# regression) + the full market-code set derivable from the two suffix tables
# in enrichment/ticker_normalization.py (SUFFIX_NORMALIZATION_TABLE +
# INTERNATIONAL_SUFFIX_TABLE), + a small forward-compat block (NO/DK/PT/NZ/
# TH/ID/BR/MX) for markets the within-envelope loose bridge can surface via
# F2 anchors before their suffixes earn a canonical table row.
#
# Source: official exchange regular trading hours as of 2025/2026 (exchange
# websites; e.g. TSE closes 15:30 since 2024-11). Lunch breaks are modeled as
# a second TradingSession only where the venue actually has one, mirroring
# the existing HK/CN pattern. Precision of pre_market_start matters less than
# a correct IANA timezone; all weeks are Mon–Fri (weekend_days=(5, 6)).

_WEEKEND_SAT_SUN: tuple[int, ...] = (5, 6)


def _mk(
    market: str,
    timezone: str,
    sessions: List[Tuple[dt_time, dt_time]],
    pre_market_start: dt_time,
) -> MarketConfig:
    """Table-row helper: build one Mon–Fri MarketConfig."""
    return MarketConfig(
        market=market,
        timezone=timezone,
        sessions=[TradingSession(open=o, close=c) for o, c in sessions],
        pre_market_start=pre_market_start,
        weekend_days=_WEEKEND_SAT_SUN,
    )


MARKET_SESSIONS: Dict[str, MarketConfig] = {
    cfg.market: cfg
    for cfg in [
        # ── Original built-ins (behavior frozen — do not touch) ────────────
        _mk("HK", "Asia/Hong_Kong",
            [(dt_time(9, 30), dt_time(12, 0)), (dt_time(13, 0), dt_time(16, 0))],
            dt_time(9, 0)),
        _mk("CN", "Asia/Shanghai",
            [(dt_time(9, 30), dt_time(11, 30)), (dt_time(13, 0), dt_time(15, 0))],
            dt_time(9, 15)),
        _mk("US", "America/New_York",
            [(dt_time(9, 30), dt_time(16, 0))],
            dt_time(4, 0)),
        # ── Asia-Pacific ────────────────────────────────────────────────────
        _mk("JP", "Asia/Tokyo",  # TSE
            [(dt_time(9, 0), dt_time(11, 30)), (dt_time(12, 30), dt_time(15, 30))],
            dt_time(8, 0)),
        _mk("TW", "Asia/Taipei",  # TWSE
            [(dt_time(9, 0), dt_time(13, 30))],
            dt_time(8, 30)),
        _mk("KR", "Asia/Seoul",  # KRX
            [(dt_time(9, 0), dt_time(15, 30))],
            dt_time(8, 30)),
        _mk("SG", "Asia/Singapore",  # SGX
            [(dt_time(9, 0), dt_time(12, 0)), (dt_time(13, 0), dt_time(17, 0))],
            dt_time(8, 30)),
        _mk("MY", "Asia/Kuala_Lumpur",  # Bursa Malaysia
            [(dt_time(9, 0), dt_time(12, 30)), (dt_time(14, 30), dt_time(17, 0))],
            dt_time(8, 30)),
        _mk("IN", "Asia/Kolkata",  # NSE / BSE
            [(dt_time(9, 15), dt_time(15, 30))],
            dt_time(9, 0)),
        _mk("TH", "Asia/Bangkok",  # SET
            [(dt_time(10, 0), dt_time(12, 30)), (dt_time(14, 30), dt_time(16, 30))],
            dt_time(9, 30)),
        _mk("ID", "Asia/Jakarta",  # IDX
            [(dt_time(9, 0), dt_time(12, 0)), (dt_time(13, 30), dt_time(15, 50))],
            dt_time(8, 45)),
        _mk("AU", "Australia/Sydney",  # ASX
            [(dt_time(10, 0), dt_time(16, 0))],
            dt_time(7, 0)),
        _mk("NZ", "Pacific/Auckland",  # NZX
            [(dt_time(10, 0), dt_time(16, 45))],
            dt_time(9, 0)),
        # ── Europe ──────────────────────────────────────────────────────────
        _mk("UK", "Europe/London",  # LSE
            [(dt_time(8, 0), dt_time(16, 30))],
            dt_time(7, 50)),
        _mk("FR", "Europe/Paris",  # Euronext Paris
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(7, 15)),
        _mk("NL", "Europe/Amsterdam",  # Euronext Amsterdam
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(7, 15)),
        _mk("DE", "Europe/Berlin",  # XETRA
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(8, 0)),
        _mk("CH", "Europe/Zurich",  # SIX Swiss
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(8, 0)),
        _mk("IT", "Europe/Rome",  # Borsa Italiana
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(8, 0)),
        _mk("ES", "Europe/Madrid",  # BME
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(8, 30)),
        _mk("PT", "Europe/Lisbon",  # Euronext Lisbon (WET)
            [(dt_time(8, 0), dt_time(16, 30))],
            dt_time(7, 15)),
        _mk("SE", "Europe/Stockholm",  # Nasdaq Stockholm
            [(dt_time(9, 0), dt_time(17, 30))],
            dt_time(8, 45)),
        _mk("FI", "Europe/Helsinki",  # Nasdaq Helsinki (EET)
            [(dt_time(10, 0), dt_time(18, 30))],
            dt_time(9, 45)),
        _mk("DK", "Europe/Copenhagen",  # Nasdaq Copenhagen
            [(dt_time(9, 0), dt_time(17, 0))],
            dt_time(8, 45)),
        _mk("NO", "Europe/Oslo",  # Oslo Børs
            [(dt_time(9, 0), dt_time(16, 20))],
            dt_time(8, 15)),
        # ── Americas ────────────────────────────────────────────────────────
        _mk("CA", "America/Toronto",  # TSX
            [(dt_time(9, 30), dt_time(16, 0))],
            dt_time(7, 0)),
        _mk("BR", "America/Sao_Paulo",  # B3
            [(dt_time(10, 0), dt_time(17, 0))],
            dt_time(9, 45)),
        _mk("MX", "America/Mexico_City",  # BMV
            [(dt_time(8, 30), dt_time(15, 0))],
            dt_time(8, 0)),
    ]
}


def get_market_config(market: str) -> Optional[MarketConfig]:
    """Look up the shared session table; ``None`` for unknown market codes.

    Callers (e.g. ``extraction/timing_builder.py``) MUST treat ``None`` as an
    explicit degradation signal — never substitute a default timezone
    silently.
    """
    if not market:
        return None
    return MARKET_SESSIONS.get(market.upper())


# ---------------------------------------------------------------------------
# Holiday Provider Protocol (extension point)
# ---------------------------------------------------------------------------


class HolidayProvider(Protocol):
    """Interface for pluggable holiday calendars.

    Implementations should return True for dates that are market holidays.
    The default (NoOpHolidayProvider) treats no days as holidays.
    """

    def is_holiday(self, date: datetime, market: str) -> bool:
        """Return True if `date` is a holiday for `market`."""
        ...


@dataclass
class NoOpHolidayProvider:
    """Default: no holidays recognized. Replace with real calendar."""

    def is_holiday(self, date: datetime, market: str) -> bool:
        return False


# ---------------------------------------------------------------------------
# Market Calendar Timing Policy
# ---------------------------------------------------------------------------

# Minimum delay (minutes) applied when a publish falls within a regular
# trading session.  Represents the minimum reaction/execution latency.
_DEFAULT_MIN_REACTION_DELAY_MINUTES = 5

# Maximum look-ahead (trading days) when searching for the next open.
# Safety guard to avoid infinite loops in degenerate configurations.
_MAX_LOOKAHEAD_TRADING_DAYS = 30


class MarketCalendarTimingPolicy:
    """Deterministic market-calendar timing for F5 TradeActions.

    Computes `action_executable_at` based solely on:
    - Publication timestamp
    - Market trading hours
    - Timezone rules
    - Optional holiday calendar

    No LLM decisions.  Fully deterministic and reproducible.

    Usage::

        policy = MarketCalendarTimingPolicy()
        result = policy.compute_timing(
            published_at=datetime(2026, 4, 24, 17, 0),  # Friday 5pm HKT
            market="HK",
            timezone="Asia/Hong_Kong",
        )
        # result.action_executable_at = Monday 09:30 HKT
    """

    POLICY_ID = "market-calendar-v1"

    def __init__(
        self,
        min_reaction_delay_minutes: int = _DEFAULT_MIN_REACTION_DELAY_MINUTES,
        holiday_provider: Optional[HolidayProvider] = None,
    ) -> None:
        self.min_reaction_delay_minutes = min_reaction_delay_minutes
        self.holiday_provider = holiday_provider or NoOpHolidayProvider()
        self._markets: Dict[str, MarketConfig] = {}
        self._register_default_markets()

    # ------------------------------------------------------------------
    # Market Registration
    # ------------------------------------------------------------------

    def _register_default_markets(self) -> None:
        """Register every market from the shared ``MARKET_SESSIONS`` table."""
        for config in MARKET_SESSIONS.values():
            self.register_market(config)

    def register_market(self, config: MarketConfig) -> None:
        """Register a market configuration.  Overwrites if already exists."""
        self._markets[config.market.upper()] = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_timing(
        self,
        published_at: datetime,
        market: str,
        timezone: str,
        intent_effective_at: Optional[datetime] = None,
        action_decision_at: Optional[datetime] = None,
    ) -> ExecutionTimingResult:
        """Compute deterministic execution timing for a published intent.

        Parameters
        ----------
        published_at:
            When the KOL content was published.  May be naive or aware.
        market:
            Market identifier (``"HK"``, ``"CN"``, ``"US"``).
        timezone:
            IANA timezone string (e.g. ``"Asia/Hong_Kong"``).
            Used as the canonical market timezone; `published_at` is
            converted to this zone for session classification.
        intent_effective_at:
            If the KOL text references a future time (e.g. "next Monday"),
            pass the resolved datetime here.  Currently stored but not
            used in calendar computation (reserved for layer 2/3).
        action_decision_at:
            When the system generated the TradeAction.  Defaults to now.

        Returns
        -------
        ExecutionTimingResult
            Deterministic timing result with action_executable_at.
        """
        market_key = market.upper()
        config = self._markets.get(market_key)
        if config is None:
            return self._unknown_market_result(published_at, market, timezone)

        tz = ZoneInfo(config.timezone)
        pub_local = self._to_local(published_at, tz)
        is_weekend = pub_local.weekday() in config.weekend_days
        is_holiday = self.holiday_provider.is_holiday(pub_local, market_key)
        is_trading_day = not is_weekend and not is_holiday

        # Classify the market session
        if not is_trading_day:
            session = MarketSession.NON_TRADING_DAY
        else:
            session = self._classify_session(pub_local, config)

        # Compute executable time
        executable_local = self._compute_executable(
            pub_local, session, config, tz
        )

        # Build human-readable reason
        reason = self._build_reason(
            pub_local, session, executable_local, config, is_weekend, is_holiday
        )

        next_td = None
        if session in (MarketSession.AFTER_CLOSE, MarketSession.NON_TRADING_DAY):
            next_td = executable_local.date().isoformat()

        return ExecutionTimingResult(
            action_executable_at=executable_local,
            market_session_at_publish=session.value,
            execution_delay_reason=reason,
            timing_policy_id=self.POLICY_ID,
            intent_published_at=pub_local,
            market=market_key,
            timezone=config.timezone,
            min_reaction_delay_minutes=self.min_reaction_delay_minutes,
            is_holiday=is_holiday,
            next_trading_day=next_td,
        )

    # ------------------------------------------------------------------
    # Helper: can a trade execute on a given date?
    # ------------------------------------------------------------------

    def is_trading_day(self, date: datetime, market: str) -> bool:
        """Check whether `date` falls on a trading day for `market`.

        Useful for downstream consumers (backtest, orchestrator).
        """
        config = self._markets.get(market.upper())
        if config is None:
            return False
        tz = ZoneInfo(config.timezone)
        local = self._to_local(date, tz)
        if local.weekday() in config.weekend_days:
            return False
        if self.holiday_provider.is_holiday(local, market.upper()):
            return False
        return True

    # ------------------------------------------------------------------
    # Layer 3 reservation: Timing Agent / Quant Bot interface
    # ------------------------------------------------------------------

    def compute_timing_with_agent_hint(
        self,
        published_at: datetime,
        market: str,
        timezone: str,
        agent_hint: Optional[str] = None,
        **kwargs: Any,
    ) -> ExecutionTimingResult:
        """Reserved interface for optional Timing Agent / Quant Bot.

        Layer 3 of the three-layer timing system.  The agent may provide
        a hint (e.g. ``"follow_after_open_30min"``) but the final
        ``action_executable_at`` must still be a legal candidate computed
        by this deterministic calendar policy.

        Parameters
        ----------
        agent_hint:
            Optional timing hint from an LLM or quant bot.  Must be one
            of the F4 timing hint values.  Currently logged but not acted
            upon — the calendar result is returned unchanged.

        Returns
        -------
        ExecutionTimingResult
            Same as compute_timing(); agent_hint is stored in
            execution_delay_reason for audit trail.
        """
        result = self.compute_timing(published_at, market, timezone, **kwargs)
        if agent_hint:
            result.execution_delay_reason = (
                f"{result.execution_delay_reason} | agent_hint={agent_hint}"
            )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _to_local(dt: datetime, tz: ZoneInfo) -> datetime:
        """Convert a datetime to the target timezone.

        - If naive: assume it's already in the target tz (return as-is with tz attached).
        - If aware: convert to the target tz.
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)

    @staticmethod
    def _classify_session(dt: datetime, config: MarketConfig) -> MarketSession:
        """Classify a local datetime into a market session.

        Assumes the date is already confirmed as a trading day.
        """
        t = dt.time()

        # Before pre-market start: technically pre_market
        if t < config.pre_market_start:
            return MarketSession.PRE_MARKET

        # Pre-market window: between pre_market_start and first session open
        first_open = min(s.open for s in config.sessions)
        if t < first_open:
            return MarketSession.PRE_MARKET

        # Within any trading session? (inclusive of lunch gaps for HK/CN)
        # "Regular" means: after first open AND before last close.
        last_close = max(s.close for s in config.sessions)
        if first_open <= t <= last_close:
            # Check if we're in the actual trading sessions (not lunch gap)
            for sess in config.sessions:
                if sess.open <= t <= sess.close:
                    return MarketSession.REGULAR
            # In a gap between sessions (e.g., HK/CN lunch break).
            # Treat as REGULAR — a new position can still be placed and
            # will queue for the afternoon session.
            return MarketSession.REGULAR

        # After last session close
        return MarketSession.AFTER_CLOSE

    def _compute_executable(
        self,
        pub_local: datetime,
        session: MarketSession,
        config: MarketConfig,
        tz: ZoneInfo,
    ) -> datetime:
        """Compute the action_executable_at based on session classification."""

        if session == MarketSession.REGULAR:
            # Same-day: published_at + min_reaction_delay
            return pub_local + timedelta(minutes=self.min_reaction_delay_minutes)

        if session == MarketSession.PRE_MARKET:
            # Same day: open at first session open time
            first_open = min(s.open for s in config.sessions)
            open_dt = pub_local.replace(
                hour=first_open.hour,
                minute=first_open.minute,
                second=0,
                microsecond=0,
            )
            # If the computed open is somehow in the past (edge case with
            # timezone weirdness), add delay
            if open_dt <= pub_local:
                return pub_local + timedelta(minutes=self.min_reaction_delay_minutes)
            return open_dt

        if session in (MarketSession.AFTER_CLOSE, MarketSession.NON_TRADING_DAY):
            # Next trading day open
            next_td = self._find_next_trading_day(pub_local, config)
            first_open = min(s.open for s in config.sessions)
            return next_td.replace(
                hour=first_open.hour,
                minute=first_open.minute,
                second=0,
                microsecond=0,
            )

        # UNKNOWN — fallback: delay
        return pub_local + timedelta(minutes=self.min_reaction_delay_minutes)

    def _find_next_trading_day(
        self,
        from_date: datetime,
        config: MarketConfig,
    ) -> datetime:
        """Find the next trading day after `from_date`.

        Starts from the *next* calendar day (if after_close) or the same
        day (if non_trading_day) and advances until a trading day is found.

        For after_close, we always advance to the next day because the
        current day's trading is over.
        """
        # Start searching from the next calendar day
        candidate = (from_date + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        for _ in range(_MAX_LOOKAHEAD_TRADING_DAYS):
            if candidate.weekday() not in config.weekend_days:
                if not self.holiday_provider.is_holiday(candidate, config.market):
                    return candidate
            candidate += timedelta(days=1)

        # Fallback — should never happen with reasonable configs
        return candidate

    def _unknown_market_result(
        self,
        published_at: datetime,
        market: str,
        timezone: str,
    ) -> ExecutionTimingResult:
        """Fallback result when market is not registered."""
        delay = timedelta(minutes=self.min_reaction_delay_minutes)
        return ExecutionTimingResult(
            action_executable_at=published_at + delay,
            market_session_at_publish=MarketSession.UNKNOWN.value,
            execution_delay_reason=f"Unknown market '{market}'; applied default {self.min_reaction_delay_minutes}min delay",
            timing_policy_id=self.POLICY_ID,
            intent_published_at=published_at,
            market=market.upper(),
            timezone=timezone,
            min_reaction_delay_minutes=self.min_reaction_delay_minutes,
        )

    def _build_reason(
        self,
        pub_local: datetime,
        session: MarketSession,
        executable_local: datetime,
        config: MarketConfig,
        is_weekend: bool,
        is_holiday: bool,
    ) -> str:
        """Build a human-readable reason string for the timing decision."""

        day_label = ""
        if is_holiday:
            day_label = " (holiday)"
        elif is_weekend:
            day_label = " (weekend)"

        if session == MarketSession.REGULAR:
            return (
                f"Published during regular trading session{day_label}; "
                f"applied {self.min_reaction_delay_minutes}min min reaction delay"
            )

        if session == MarketSession.PRE_MARKET:
            first_open = min(s.open for s in config.sessions)
            return (
                f"Published during pre-market{day_label}; "
                f"executable at same-day open {first_open.strftime('%H:%M')} {config.timezone}"
            )

        if session == MarketSession.AFTER_CLOSE:
            return (
                f"Published after market close{day_label}; "
                f"deferred to next trading day open ({executable_local.strftime('%Y-%m-%d %H:%M')} {config.timezone})"
            )

        if session == MarketSession.NON_TRADING_DAY:
            return (
                f"Published on non-trading day{day_label}; "
                f"deferred to next trading day open ({executable_local.strftime('%Y-%m-%d %H:%M')} {config.timezone})"
            )

        return (
            f"Market session unknown; "
            f"applied default {self.min_reaction_delay_minutes}min delay"
        )
