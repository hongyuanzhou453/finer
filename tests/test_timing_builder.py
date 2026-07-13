"""Tests for extraction.timing_builder — ExecutionTiming builder.

Covers CN/HK/US timezone handling and temporal anchor resolution.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from zoneinfo import ZoneInfo

import pytest

from finer.extraction.timing_builder import build_execution_timing
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.quality import QualityCard
from finer.schemas.trade_action import ExecutionTiming, MarketSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quality_card() -> QualityCard:
    """Create a default quality card for testing."""
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.8,
        financial_relevance_score=0.9,
        entity_resolution_score=0.8,
        temporal_resolution_score=0.7,
        evidence_traceability_score=0.8,
    )


def _make_envelope(published_at: Optional[datetime] = None) -> ContentEnvelope:
    """Build a minimal ContentEnvelope with a published_at."""
    return ContentEnvelope(
        envelope_id="test_env_001",
        source_type="text",
        quality_card=_make_quality_card(),
        published_at=published_at,
    )


def _make_anchor(anchor_type: str, resolved_time: Optional[datetime] = None) -> SimpleNamespace:
    """Build a mock temporal anchor."""
    return SimpleNamespace(anchor_type=anchor_type, resolved_time=resolved_time)


# ---------------------------------------------------------------------------
# 1. CN timezone handling
# ---------------------------------------------------------------------------

class TestCNTiming:
    """CN market → Asia/Shanghai timezone."""

    def test_cn_regular_session(self) -> None:
        """CN 10:30 CST during regular session → 5 min delay."""
        published = datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="CN")

        assert isinstance(result, ExecutionTiming)
        assert result.market == "CN"
        assert result.timezone == "Asia/Shanghai"
        assert result.market_session_at_publish == MarketSession.REGULAR
        assert result.intent_published_at == published
        assert result.action_decision_at == published
        expected = datetime(2026, 4, 23, 10, 35, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result.action_executable_at == expected

    def test_cn_pre_market(self) -> None:
        """CN 09:00 pre-market → same day 09:30 open."""
        published = datetime(2026, 4, 23, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="CN")

        assert result.market_session_at_publish == MarketSession.PRE_MARKET
        expected = datetime(2026, 4, 23, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result.action_executable_at == expected

    def test_cn_after_close(self) -> None:
        """CN 15:30 after close → next trading day 09:30."""
        published = datetime(2026, 4, 23, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="CN")

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE
        # Next trading day: Friday 2026-04-24
        expected = datetime(2026, 4, 24, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 2. HK timezone handling
# ---------------------------------------------------------------------------

class TestHKTiming:
    """HK market → Asia/Hong_Kong timezone."""

    def test_hk_regular_session(self) -> None:
        """HK 11:00 during regular session → 5 min delay."""
        published = datetime(2026, 4, 23, 11, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="HK")

        assert result.market == "HK"
        assert result.timezone == "Asia/Hong_Kong"
        assert result.market_session_at_publish == MarketSession.REGULAR
        expected = datetime(2026, 4, 23, 11, 5, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        assert result.action_executable_at == expected

    def test_hk_friday_after_close(self) -> None:
        """HK Friday 17:00 after close → Monday 09:30."""
        # 2026-04-24 is a Friday
        published = datetime(2026, 4, 24, 17, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="HK")

        assert result.market_session_at_publish == MarketSession.AFTER_CLOSE
        expected = datetime(2026, 4, 27, 9, 30, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 3. US timezone handling
# ---------------------------------------------------------------------------

class TestUSTiming:
    """US market → America/New_York timezone."""

    def test_us_regular_session(self) -> None:
        """US 11:00 ET during regular session → 5 min delay."""
        published = datetime(2026, 4, 23, 11, 0, tzinfo=ZoneInfo("America/New_York"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="US")

        assert result.market == "US"
        assert result.timezone == "America/New_York"
        assert result.market_session_at_publish == MarketSession.REGULAR
        expected = datetime(2026, 4, 23, 11, 5, tzinfo=ZoneInfo("America/New_York"))
        assert result.action_executable_at == expected

    def test_us_pre_market(self) -> None:
        """US 08:00 ET pre-market → same day 09:30."""
        published = datetime(2026, 4, 23, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="US")

        assert result.market_session_at_publish == MarketSession.PRE_MARKET
        expected = datetime(2026, 4, 23, 9, 30, tzinfo=ZoneInfo("America/New_York"))
        assert result.action_executable_at == expected

    def test_us_est_winter_time(self) -> None:
        """US market in winter (EST): 15:00 UTC = 10:00 EST → regular."""
        published = datetime(2026, 1, 15, 15, 0, tzinfo=ZoneInfo("UTC"))
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="US")

        assert result.market_session_at_publish == MarketSession.REGULAR
        expected = datetime(2026, 1, 15, 10, 5, tzinfo=ZoneInfo("America/New_York"))
        assert result.action_executable_at == expected


# ---------------------------------------------------------------------------
# 4. Temporal anchor resolution
# ---------------------------------------------------------------------------

class TestTemporalAnchorResolution:
    """Test intent_effective_at extraction from temporal anchors."""

    def test_effective_trade_at_used(self) -> None:
        """An explicit effective_trade_at anchor (>= published) populates the clock."""
        effective = datetime(2026, 4, 23, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        mentioned = datetime(2026, 4, 22, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        anchors = [
            _make_anchor("mentioned_at", mentioned),
            _make_anchor("effective_trade_at", effective),
        ]
        envelope = _make_envelope(datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

        result = build_execution_timing(
            envelope=envelope, market="CN", temporal_anchors=anchors,
        )

        assert result.intent_effective_at == effective

    def test_mentioned_at_is_not_used_as_effective(self) -> None:
        """mentioned_at is a contextual reference, NOT the effective time.

        Previously this fell back to mentioned_at; that conflation is the bug
        that produced intent_effective_at < intent_published_at on every action.
        """
        mentioned = datetime(2026, 4, 22, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        anchors = [_make_anchor("mentioned_at", mentioned)]
        envelope = _make_envelope(datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

        result = build_execution_timing(
            envelope=envelope, market="CN", temporal_anchors=anchors,
        )

        assert result.intent_effective_at is None

    def test_past_mentioned_at_does_not_invert_clocks(self) -> None:
        """Regression for the real F2 data: published_at + many past mentioned_at.

        Mirrors data/F2_anchored, where envelopes carry a published_at anchor plus
        dozens of mentioned_at anchors resolving to an earlier date. The effective
        clock must stay unresolved (None), never the past date, and the chain must
        be forward-only.
        """
        published = datetime(2026, 3, 22, tzinfo=ZoneInfo("Asia/Shanghai"))
        past = datetime(2026, 3, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
        anchors = [_make_anchor("published_at", published)] + [
            _make_anchor("mentioned_at", past) for _ in range(5)
        ]
        envelope = _make_envelope(published)

        result = build_execution_timing(
            envelope=envelope, market="CN", temporal_anchors=anchors,
        )

        assert result.intent_effective_at is None
        assert result.action_decision_at >= result.intent_published_at
        assert result.action_executable_at >= result.action_decision_at

    def test_no_anchors(self) -> None:
        """No temporal anchors → intent_effective_at is None."""
        envelope = _make_envelope(datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

        result = build_execution_timing(envelope=envelope, market="CN")

        assert result.intent_effective_at is None

    def test_empty_anchors(self) -> None:
        """Empty anchor list → intent_effective_at is None."""
        envelope = _make_envelope(datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

        result = build_execution_timing(
            envelope=envelope, market="CN", temporal_anchors=[],
        )

        assert result.intent_effective_at is None

    def test_anchor_without_resolved_time(self) -> None:
        """Anchor with None resolved_time is skipped."""
        anchors = [_make_anchor("effective_trade_at", None)]
        envelope = _make_envelope(datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

        result = build_execution_timing(
            envelope=envelope, market="CN", temporal_anchors=anchors,
        )

        assert result.intent_effective_at is None


# ---------------------------------------------------------------------------
# 5. Fallback and edge cases
# ---------------------------------------------------------------------------

class TestFallback:
    """Unknown market and missing published_at handling."""

    def test_unknown_market_defaults_to_shanghai(self) -> None:
        """Unknown market → fallback to Asia/Shanghai."""
        published = datetime(2026, 4, 23, 10, 0)
        envelope = _make_envelope(published)

        result = build_execution_timing(envelope=envelope, market="XX")

        assert result.timezone == "Asia/Shanghai"

    def test_missing_published_at_raises(self) -> None:
        """Envelope without published_at must not fall back to runtime now."""
        envelope = _make_envelope(published_at=None)

        with pytest.raises(ValueError, match="published_at is required"):
            build_execution_timing(envelope=envelope, market="CN")

    def test_intent_id_recorded(self) -> None:
        """intent_id parameter is accepted (no crash)."""
        envelope = _make_envelope(datetime(2026, 4, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

        result = build_execution_timing(
            envelope=envelope, market="CN", intent_id="intent-123",
        )

        assert isinstance(result, ExecutionTiming)
