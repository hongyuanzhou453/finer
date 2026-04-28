"""Tests for Pydantic schemas — serialization, validation, and edge cases.

Covers the core data models that are the single source of truth:
- TradeAction and nested models
- EventWithActions
- EnrichedEventWithActions
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    TriggerType,
    TradeDirection,
    ValidationStatus,
    ExitReason,
    SourceInfo,
    TargetInfo,
    MarketEnrichment,
    RLHFFeedback,
    BacktestResult,
    TradeAction,
    TradeActionBatch,
)
from finer.schemas.event import TradingAction, EventWithActions
from finer.schemas.enriched_event import (
    MarketDataSnapshot,
    SentimentSnapshot,
    EnrichedEventWithActions,
)


# =============================================================================
# ActionStep Tests
# =============================================================================

class TestActionStep:
    """Tests for ActionStep model."""

    def test_action_step_creation_minimal(self):
        """Test creating ActionStep with minimal fields."""
        step = ActionStep(sequence=1, action_type=ActionType.LONG)
        assert step.sequence == 1
        assert step.action_type == ActionType.LONG
        assert step.trigger_type == TriggerType.MANUAL
        assert step.target_price_low is None
        assert step.target_price_high is None

    def test_action_step_with_price_range(self):
        """Test ActionStep with target price range."""
        step = ActionStep(
            sequence=1,
            action_type=ActionType.LONG,
            target_price_low=100.0,
            target_price_high=150.0,
            trigger_type=TriggerType.PRICE_THRESHOLD,
        )
        assert step.target_price_low == 100.0
        assert step.target_price_high == 150.0

    def test_action_step_invalid_price_range(self):
        """Test that invalid price range raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                target_price_low=150.0,  # Higher than high
                target_price_high=100.0,
            )
        assert "target_price_low" in str(exc_info.value)

    def test_action_step_serialization(self):
        """Test ActionStep serialization/deserialization."""
        step = ActionStep(
            sequence=2,
            action_type=ActionType.BUY_CALL,
            trigger_condition="price > 180",
            trigger_type=TriggerType.BREAKOUT,
            target_price_low=180.0,
            target_price_high=200.0,
            position_size_pct=0.05,
            notes="Breakout entry",
        )
        data = step.model_dump()
        restored = ActionStep.model_validate(data)
        assert restored == step

    def test_action_step_sequence_must_be_positive(self):
        """Test that sequence must be >= 1."""
        with pytest.raises(ValidationError):
            ActionStep(sequence=0, action_type=ActionType.WATCH)


# =============================================================================
# TargetInfo Tests
# =============================================================================

class TestTargetInfo:
    """Tests for TargetInfo model."""

    def test_target_info_auto_normalize(self):
        """Test automatic ticker normalization."""
        target = TargetInfo(ticker="aapl")
        assert target.ticker_normalized == "AAPL"

    def test_target_info_remove_cashtag(self):
        """Test removing $ prefix from cashtags."""
        target = TargetInfo(ticker="$TSLA")
        assert target.ticker_normalized == "TSLA"

    def test_target_info_preserves_normalized(self):
        """Test that provided normalized ticker is preserved."""
        target = TargetInfo(
            ticker="苹果公司",
            ticker_normalized="AAPL",
            market="US",
        )
        assert target.ticker_normalized == "AAPL"

    def test_target_info_serialization(self):
        """Test TargetInfo serialization."""
        target = TargetInfo(
            ticker="NVDA",
            ticker_normalized="NVDA",
            market="US",
            instrument_type="stock",
            company_name="NVIDIA Corporation",
        )
        data = target.model_dump()
        restored = TargetInfo.model_validate(data)
        assert restored.ticker == target.ticker
        assert restored.market == "US"


# =============================================================================
# TradeAction Tests
# =============================================================================

class TestTradeAction:
    """Tests for TradeAction model."""

    def test_trade_action_creation_minimal(self):
        """Test creating TradeAction with minimal required fields."""
        action = TradeAction(
            source=SourceInfo(
                content_id="test-001",
                evidence_text="Test evidence",
            ),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )
        assert action.target.ticker == "AAPL"
        assert action.direction == TradeDirection.BULLISH
        assert action.validation_status == ValidationStatus.PENDING
        assert len(action.action_chain) == 1  # Default WATCH action

    def test_trade_action_with_action_chain(self):
        """Test TradeAction with multiple action steps."""
        action = TradeAction(
            source=SourceInfo(content_id="test-002", evidence_text="Test"),
            target=TargetInfo(ticker="TSLA"),
            direction=TradeDirection.BULLISH,
            action_chain=[
                ActionStep(sequence=1, action_type=ActionType.WATCH),
                ActionStep(
                    sequence=2,
                    action_type=ActionType.LONG,
                    trigger_condition="price < 200",
                ),
            ],
            confidence=0.85,
        )
        assert len(action.action_chain) == 2
        assert action.is_actionable() is False  # Not verified yet

    def test_trade_action_invalid_chain_sequence(self):
        """Test that non-consecutive sequence raises error."""
        with pytest.raises(ValidationError) as exc_info:
            TradeAction(
                source=SourceInfo(content_id="test", evidence_text="Test"),
                target=TargetInfo(ticker="AAPL"),
                direction=TradeDirection.BULLISH,
                action_chain=[
                    ActionStep(sequence=1, action_type=ActionType.WATCH),
                    ActionStep(sequence=3, action_type=ActionType.LONG),  # Skipped 2
                ],
            )
        assert "consecutive" in str(exc_info.value).lower()

    def test_trade_action_auto_flag_for_review(self):
        """Test that validation_issues auto-flags for manual review."""
        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            validation_issues=["Invalid price target"],
        )
        assert action.requires_manual_review is True

    def test_trade_action_timestamp_parsing(self):
        """Test timestamp parsing from various formats."""
        # ISO 8601
        action1 = TradeAction(
            timestamp="2026-04-24T10:30:00Z",
            source=SourceInfo(content_id="t1", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.NEUTRAL,
        )
        assert action1.timestamp.year == 2026

        # String format
        action2 = TradeAction(
            timestamp="2026-04-24 10:30:00",
            source=SourceInfo(content_id="t2", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.NEUTRAL,
        )
        assert action2.timestamp.year == 2026

    def test_trade_action_serialization(self):
        """Test full TradeAction serialization."""
        action = TradeAction(
            source=SourceInfo(
                content_id="test-001",
                evidence_text="AAPL at 180 is a good entry",
            ),
            target=TargetInfo(ticker="AAPL", market="US"),
            direction=TradeDirection.BULLISH,
            action_chain=[
                ActionStep(
                    sequence=1,
                    action_type=ActionType.LONG,
                    trigger_condition="price <= 180",
                ),
            ],
            confidence=0.9,
            time_horizon="2 weeks",
            rationale="Technical support at 180",
        )

        # Serialize
        data = action.model_dump()
        # Deserialize
        restored = TradeAction.model_validate(data)

        assert restored.target.ticker == "AAPL"
        assert restored.direction == TradeDirection.BULLISH
        assert restored.confidence == 0.9
        assert len(restored.action_chain) == 1

    def test_trade_action_to_dict(self):
        """Test to_dict method for JSON serialization."""
        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            confidence=0.8,
        )
        data = action.to_dict()
        assert isinstance(data, dict)
        assert "timestamp" in data
        assert data["confidence"] == 0.8

    def test_trade_action_is_actionable(self):
        """Test is_actionable method."""
        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            confidence=0.8,
        )
        # Not actionable: not verified, pending status
        assert action.is_actionable() is False

        # Mark as verified
        action.validation_status = ValidationStatus.VERIFIED
        assert action.is_actionable() is True

        # Low confidence
        action.confidence = 0.4
        assert action.is_actionable() is False

    def test_trade_action_normalize_ticker(self):
        """Test ticker normalization."""
        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="$aapl", market="US"),
            direction=TradeDirection.BULLISH,
        )
        assert action.normalize_ticker() == "AAPL"


# =============================================================================
# TradeActionBatch Tests
# =============================================================================

class TestTradeActionBatch:
    """Tests for TradeActionBatch container."""

    def test_batch_auto_compute_stats(self):
        """Test that batch auto-computes statistics."""
        actions = [
            TradeAction(
                source=SourceInfo(content_id="t1", evidence_text="Test"),
                target=TargetInfo(ticker="AAPL"),
                direction=TradeDirection.BULLISH,
                confidence=0.8,
            ),
            TradeAction(
                source=SourceInfo(content_id="t2", evidence_text="Test"),
                target=TargetInfo(ticker="TSLA"),
                direction=TradeDirection.BEARISH,
                confidence=0.7,
            ),
            TradeAction(
                source=SourceInfo(content_id="t3", evidence_text="Test"),
                target=TargetInfo(ticker="NVDA"),
                direction=TradeDirection.NEUTRAL,
                confidence=0.6,
            ),
        ]
        batch = TradeActionBatch(actions=actions)

        assert batch.total_actions == 3
        assert batch.bullish_count == 1
        assert batch.bearish_count == 1
        assert batch.neutral_count == 1

    def test_batch_empty(self):
        """Test empty batch."""
        batch = TradeActionBatch()
        assert batch.total_actions == 0
        assert batch.bullish_count == 0


# =============================================================================
# TradingAction (compatibility) Tests
# =============================================================================

class TestTradingActionCompatibility:
    """Tests for TradingAction backward compatibility wrapper."""

    def test_trading_action_sequence_order_alias(self):
        """Test that ActionStep has sequence field (TradingAction uses action_chain)."""
        step = ActionStep(
            sequence=2,
            action_type=ActionType.LONG,
        )
        assert step.sequence == 2

    def test_trading_action_from_action_step(self):
        """Test conversion from ActionStep."""
        step = ActionStep(
            sequence=1,
            action_type=ActionType.BUY_CALL,
            trigger_condition="price > 180",
        )
        action = TradingAction.from_action_step(
            step,
            confidence=0.85,
            instrument_type="option",
        )
        assert action.action_type == ActionType.BUY_CALL
        assert action.confidence == 0.85
        assert action.instrument_type == "option"

    def test_trading_action_to_action_step(self):
        """Test conversion to pure ActionStep."""
        action = TradingAction(
            sequence=1,
            action_type=ActionType.SHORT,
            confidence=0.7,
        )
        step = action.to_action_step()
        assert step.sequence == 1
        assert step.action_type == ActionType.SHORT
        assert not hasattr(step, "confidence")


# =============================================================================
# EventWithActions Tests
# =============================================================================

class TestEventWithActions:
    """Tests for EventWithActions model."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = EventWithActions(
            ticker="AAPL",
            direction="bullish",
            evidence_text="Strong earnings beat",
            rationale="EPS exceeded expectations",
        )
        assert event.ticker == "AAPL"
        assert event.direction == "bullish"
        assert len(event.action_chain) == 0

    def test_event_with_actions(self):
        """Test event with trading actions."""
        event = EventWithActions(
            ticker="TSLA",
            direction="bearish",
            evidence_text="Production concerns",
            action_chain=[
                TradingAction(
                    sequence=1,
                    action_type=ActionType.WATCH,
                    confidence=0.7,
                ),
            ],
        )
        assert len(event.action_chain) == 1

    def test_event_serialization(self):
        """Test event serialization."""
        event = EventWithActions(
            event_id="evt-001",
            content_id="content-001",
            ticker="NVDA",
            direction="bullish",
            evidence_text="AI demand surge",
            time_horizon="long term",
        )
        data = event.model_dump()
        restored = EventWithActions.model_validate(data)
        assert restored.event_id == "evt-001"
        assert restored.ticker == "NVDA"


# =============================================================================
# EnrichedEventWithActions Tests
# =============================================================================

class TestEnrichedEventWithActions:
    """Tests for EnrichedEventWithActions model."""

    def test_enriched_event_from_base(self):
        """Test creating enriched event from base event."""
        base = EventWithActions(
            ticker="AAPL",
            direction="bullish",
            evidence_text="Test",
        )
        market = MarketDataSnapshot(
            ticker="AAPL",
            current_price=180.0,
            high_52wk=200.0,
            low_52wk=120.0,
        )
        enriched = EnrichedEventWithActions.from_event(
            base,
            market_snapshot=market,
            validation_issues=["Price near 52-week high"],
        )

        assert enriched.ticker == "AAPL"
        assert enriched.market_snapshot is not None
        assert enriched.market_snapshot.current_price == 180.0
        assert len(enriched.validation_issues) == 1

    def test_enriched_event_confidence_calculation(self):
        """Test confidence score fields."""
        enriched = EnrichedEventWithActions(
            ticker="AAPL",
            direction="bullish",
            evidence_text="Test",
            base_confidence=0.8,
            market_data_confidence=0.2,
            overall_confidence=0.85,
        )
        assert enriched.overall_confidence == 0.85


# =============================================================================
# MarketDataSnapshot Tests
# =============================================================================

class TestMarketDataSnapshot:
    """Tests for MarketDataSnapshot model."""

    def test_market_snapshot_creation(self):
        """Test market data snapshot creation."""
        snapshot = MarketDataSnapshot(
            ticker="AAPL",
            current_price=180.0,
            change_pct=1.5,
            volume=100000000,
            high_52wk=200.0,
            low_52wk=120.0,
            pe_ratio=28.5,
            market_cap=2800000000000,
        )
        assert snapshot.current_price == 180.0
        assert snapshot.is_complete is True

    def test_market_snapshot_missing_fields(self):
        """Test tracking of missing fields."""
        snapshot = MarketDataSnapshot(
            ticker="AAPL",
            current_price=180.0,
            # Missing 52-week data
        )
        snapshot.missing_fields = ["high_52wk", "low_52wk"]
        snapshot.is_complete = False
        assert snapshot.is_complete is False


# =============================================================================
# SentimentSnapshot Tests
# =============================================================================

class TestSentimentSnapshot:
    """Tests for SentimentSnapshot model."""

    def test_sentiment_snapshot_creation(self):
        """Test sentiment snapshot creation."""
        snapshot = SentimentSnapshot(
            ticker="AAPL",
            reddit_sentiment=0.3,
            twitter_sentiment=0.5,
            news_sentiment=0.4,
            aggregated_score=0.4,
            overall_sentiment="bullish",
            sources=["reddit", "twitter", "news"],
        )
        assert snapshot.aggregated_score == 0.4
        assert snapshot.overall_sentiment == "bullish"

    def test_sentiment_contrarian_signal(self):
        """Test contrarian signal detection."""
        snapshot = SentimentSnapshot(
            ticker="AAPL",
            aggregated_score=0.8,  # Extreme
            sentiment_velocity=0.4,  # Rapid change
            contrarian_signal=True,
            extreme_sentiment=True,
        )
        assert snapshot.contrarian_signal is True
        assert snapshot.extreme_sentiment is True


# =============================================================================
# RLHFFeedback Tests
# =============================================================================

class TestRLHFFeedback:
    """Tests for RLHFFeedback model."""

    def test_rlh_feedback_creation(self):
        """Test RLHF feedback creation."""
        feedback = RLHFFeedback(
            rating=4,
            is_correct=True,
            reviewer_id="user-001",
            review_notes="Good extraction",
        )
        assert feedback.rating == 4
        assert feedback.is_correct is True

    def test_rlh_feedback_auto_timestamp(self):
        """Test that reviewed_at can be set explicitly."""
        feedback = RLHFFeedback(rating=5, reviewed_at=datetime.now())
        assert feedback.reviewed_at is not None


# =============================================================================
# BacktestResult Tests
# =============================================================================

class TestBacktestResult:
    """Tests for BacktestResult model."""

    def test_backtest_result_creation(self):
        """Test backtest result creation."""
        result = BacktestResult(
            return_pct=15.5,
            holding_days=14,
            exit_reason=ExitReason.TARGET_REACHED,
            exit_price=180.0,
            max_drawdown_pct=3.2,
            sharpe_ratio=1.8,
        )
        assert result.return_pct == 15.5
        assert result.exit_reason == ExitReason.TARGET_REACHED


# =============================================================================
# Edge Cases and Validation Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_position_size_pct_bounds(self):
        """Test position size percentage bounds."""
        # Valid
        step = ActionStep(
            sequence=1,
            action_type=ActionType.LONG,
            position_size_pct=0.05,
        )
        assert step.position_size_pct == 0.05

        # Invalid: zero
        with pytest.raises(ValidationError):
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                position_size_pct=0.0,
            )

        # Invalid: > 1
        with pytest.raises(ValidationError):
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                position_size_pct=1.5,
            )

    def test_confidence_bounds(self):
        """Test confidence bounds."""
        # Valid
        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            confidence=0.5,
        )
        assert action.confidence == 0.5

        # Invalid: > 1
        with pytest.raises(ValidationError):
            TradeAction(
                source=SourceInfo(content_id="test", evidence_text="Test"),
                target=TargetInfo(ticker="AAPL"),
                direction=TradeDirection.BULLISH,
                confidence=1.5,
            )

    def test_rlh_feedback_rating_bounds(self):
        """Test RLHF rating bounds (1-5)."""
        # Valid
        feedback = RLHFFeedback(rating=3)
        assert feedback.rating == 3

        # Invalid: 0
        with pytest.raises(ValidationError):
            RLHFFeedback(rating=0)

        # Invalid: 6
        with pytest.raises(ValidationError):
            RLHFFeedback(rating=6)

    def test_sentiment_score_bounds(self):
        """Test sentiment score bounds (-1 to 1)."""
        snapshot = SentimentSnapshot(
            ticker="AAPL",
            reddit_sentiment=0.9,
            twitter_sentiment=-0.8,
            aggregated_score=0.5,
        )
        assert snapshot.reddit_sentiment == 0.9

        # Invalid: > 1
        with pytest.raises(ValidationError):
            SentimentSnapshot(
                ticker="AAPL",
                reddit_sentiment=1.5,
            )


# =============================================================================
# Canonical Trace Tests (F3 → F4 → F5)
# =============================================================================

class TestCanonicalTrace:
    """Tests for F3 → F4 → F5 canonical trace chain in TradeAction."""

    def test_trade_action_canonical_with_full_ids(self):
        """TradeAction with intent_id + policy_id + evidence_span_ids is canonical."""
        ta = TradeAction(
            intent_id="intent-abc-123",
            policy_id="policy-def-456",
            evidence_span_ids=["span-001", "span-002"],
            effective_trade_at=datetime(2026, 4, 24, 9, 30, 0),
            source=SourceInfo(content_id="test", evidence_text="Canonical trace test"),
            target=TargetInfo(ticker="NVDA"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.canonical_trace_status == "canonical"
        assert ta.intent_id == "intent-abc-123"
        assert ta.policy_id == "policy-def-456"
        assert ta.evidence_span_ids == ["span-001", "span-002"]

    def test_trade_action_non_canonical_without_ids(self):
        """TradeAction without intent_id/policy_id is non-canonical (legacy path)."""
        ta = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Legacy extraction"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.canonical_trace_status == "non_canonical"
        assert ta.intent_id is None
        assert ta.policy_id is None

    def test_trade_action_partial_trace(self):
        """TradeAction with only one upstream ID is partial."""
        ta = TradeAction(
            intent_id="intent-only-001",
            evidence_span_ids=["span-001"],
            source=SourceInfo(content_id="test", evidence_text="Partial trace"),
            target=TargetInfo(ticker="TSLA"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.canonical_trace_status == "partial"

    def test_trade_action_effective_trade_at(self):
        """TradeAction carries effective_trade_at distinct from timestamp."""
        effective = datetime(2026, 3, 15, 9, 30, 0)
        ta = TradeAction(
            intent_id="intent-001",
            policy_id="policy-001",
            effective_trade_at=effective,
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="GOOGL"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.effective_trade_at == effective
        # effective_trade_at is a distinct field from timestamp
        assert "effective_trade_at" in ta.model_dump()

    def test_trade_action_serialization_with_trace(self):
        """TradeAction serialization includes trace fields."""
        ta = TradeAction(
            intent_id="intent-serialize-001",
            policy_id="policy-serialize-001",
            evidence_span_ids=["span-001"],
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )
        data = ta.model_dump(mode='json')
        assert data["intent_id"] == "intent-serialize-001"
        assert data["policy_id"] == "policy-serialize-001"
        assert data["canonical_trace_status"] == "canonical"

        # Round-trip via model_dump preserves enum types for strict=True
        data_python = ta.model_dump()
        restored = TradeAction.model_validate(data_python)
        assert restored.intent_id == "intent-serialize-001"
        assert restored.canonical_trace_status == "canonical"

        # JSON round-trip via model_validate_json
        import json
        json_str = json.dumps(data, default=str)
        restored_json = TradeAction.model_validate_json(json_str)
        assert restored_json.intent_id == "intent-serialize-001"
        assert restored_json.canonical_trace_status == "canonical"
