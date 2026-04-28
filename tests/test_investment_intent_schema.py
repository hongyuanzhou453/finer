"""Tests for NormalizedInvestmentIntent Schema.

Covers the pre-TradeAction intent layer:
- Field validation
- Consistency validators
- Helper methods
- Edge cases for actionability/direction consistency
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from finer.schemas.investment_intent import (
    NormalizedInvestmentIntent,
    IntentBatch,
    TARGET_TYPE_LITERAL,
    DIRECTION_LITERAL,
    ACTIONABILITY_LITERAL,
    POSITION_DELTA_HINT_LITERAL,
)


# =============================================================================
# Basic Creation Tests
# =============================================================================

class TestNormalizedInvestmentIntentCreation:
    """Tests for NormalizedInvestmentIntent model creation."""

    def test_intent_creation_minimal(self):
        """Test creating intent with minimal required fields."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="宁德时代",
            target_symbol="300750.SZ",
            market="CN",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="none",
            conviction=0.8,
            confidence=0.9,
        )
        assert intent.envelope_id == "env-001"
        assert intent.target_name == "宁德时代"
        assert intent.direction == "bullish"
        assert intent.actionability == "opinion"
        assert intent.position_delta_hint == "none"
        assert intent.conviction == 0.8
        assert intent.confidence == 0.9
        assert intent.schema_version == "1.0"

    def test_intent_creation_with_all_fields(self):
        """Test creating intent with all optional fields."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-002",
            block_ids=["block-1", "block-2"],
            creator_id="creator-001",
            target_type="stock",
            target_name="Tesla",
            target_symbol="TSLA",
            market="US",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.9,
            sentiment_score=0.75,
            risk_preference_hint="aggressive",
            time_horizon_hint="medium_term",
            temporal_anchor_ids=["anchor-1"],
            evidence_span_ids=["span-1", "span-2"],
            ambiguity_flags=[],
            confidence=0.95,
            metadata={"source": "feishu"},
        )
        assert intent.target_symbol == "TSLA"
        assert intent.creator_id == "creator-001"
        assert intent.sentiment_score == 0.75
        assert intent.risk_preference_hint == "aggressive"
        assert intent.time_horizon_hint == "medium_term"

    def test_intent_auto_generated_id(self):
        """Test that intent_id is auto-generated."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-003",
            target_type="stock",
            target_name="Test",
            direction="neutral",
            actionability="watch",
            position_delta_hint="none",
            conviction=0.5,
            confidence=0.6,
        )
        assert intent.intent_id is not None
        assert len(intent.intent_id) == 36  # UUID format


# =============================================================================
# Key Distinction Tests: Opinion vs Explicit Action
# =============================================================================

class TestOpinionVsActionDistinction:
    """Tests for the core distinction between opinion and explicit action."""

    def test_opinion_watch_case(self):
        """
        "我看好宁德时代" = bullish + opinion/watch + none
        This is a pure opinion, no action commitment.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-opinion-1",
            target_type="stock",
            target_name="宁德时代",
            target_symbol="300750.SZ",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="none",
            conviction=0.8,
            confidence=0.85,
        )
        assert intent.actionability == "opinion"
        assert intent.position_delta_hint == "none"
        assert intent.is_actionable() is False  # Opinion is not directly actionable

    def test_explicit_action_add_case(self):
        """
        "我加仓宁德时代" = bullish + explicit_action + add
        This is an explicit trading action.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-action-1",
            target_type="stock",
            target_name="宁德时代",
            target_symbol="300750.SZ",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.9,
            confidence=0.92,
        )
        assert intent.actionability == "explicit_action"
        assert intent.position_delta_hint == "add"
        assert intent.is_actionable() is True

    def test_hold_case_bullish(self):
        """
        "继续持有腾讯" = bullish/neutral + explicit_action + hold
        Context determines direction confidence.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-hold-1",
            target_type="stock",
            target_name="腾讯",
            target_symbol="0700.HK",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="hold",
            conviction=0.7,
            confidence=0.75,
        )
        assert intent.actionability == "explicit_action"
        assert intent.position_delta_hint == "hold"
        assert intent.is_actionable() is True

    def test_hold_case_neutral(self):
        """
        "继续持有腾讯" - when context suggests neutral stance.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-hold-2",
            target_type="stock",
            target_name="腾讯",
            target_symbol="0700.HK",
            direction="neutral",
            actionability="explicit_action",
            position_delta_hint="hold",
            conviction=0.5,
            confidence=0.6,
        )
        assert intent.direction == "neutral"
        assert intent.position_delta_hint == "hold"

    def test_watch_signal(self):
        """
        "关注一下新能源板块" = bullish/neutral + watch + none
        Watch list entry, not immediate action.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-watch-1",
            target_type="sector",
            target_name="新能源板块",
            direction="bullish",
            actionability="watch",
            position_delta_hint="none",
            conviction=0.6,
            confidence=0.7,
        )
        assert intent.actionability == "watch"
        # Watch needs higher confidence (0.7) to be actionable
        assert intent.is_actionable() is True


# =============================================================================
# Consistency Validator Tests
# =============================================================================

class TestConsistencyValidators:
    """Tests for automatic consistency validation."""

    def test_opinion_with_position_hint_flagged(self):
        """
        Opinion + position_delta_hint (open/add/reduce/exit) is suspicious.
        Should add ambiguity flag.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-inconsistent-1",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="add",  # Suspicious: opinion shouldn't have action
            conviction=0.7,
            confidence=0.8,
        )
        assert "opinion_with_position_hint" in intent.ambiguity_flags
        assert intent.needs_review() is True

    def test_explicit_action_without_position_flagged(self):
        """
        Explicit action + position_delta_hint=none is suspicious.
        Should add ambiguity flag.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-inconsistent-2",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="none",  # Suspicious: action should have hint
            conviction=0.7,
            confidence=0.8,
        )
        assert "action_without_position_hint" in intent.ambiguity_flags

    def test_bearish_with_open_flagged(self):
        """
        Bearish + open/add is unusual (usually means short).
        Should add ambiguity flag.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-inconsistent-3",
            target_type="stock",
            target_name="Test",
            direction="bearish",
            actionability="explicit_action",
            position_delta_hint="open",  # Bearish + open = short signal?
            conviction=0.8,
            confidence=0.85,
        )
        assert "bearish_position_mismatch" in intent.ambiguity_flags

    def test_bullish_with_exit_flagged(self):
        """
        Bullish + exit is unusual.
        Should add ambiguity flag.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-inconsistent-4",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="exit",  # Bullish + exit is unusual
            conviction=0.6,
            confidence=0.7,
        )
        assert "bullish_exit_mismatch" in intent.ambiguity_flags

    def test_consistent_intent_no_flags(self):
        """
        Consistent intent should not add ambiguity flags.
        """
        intent = NormalizedInvestmentIntent(
            envelope_id="env-consistent-1",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.9,
        )
        assert len(intent.ambiguity_flags) == 0
        assert intent.needs_review() is False


# =============================================================================
# Helper Method Tests
# =============================================================================

class TestHelperMethods:
    """Tests for helper methods."""

    def test_is_actionable_explicit_action(self):
        """Test is_actionable for explicit_action with sufficient confidence."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.7,
        )
        assert intent.is_actionable() is True

    def test_is_actionable_explicit_action_low_confidence(self):
        """Test is_actionable for explicit_action with low confidence."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.4,  # Below 0.5 threshold
        )
        assert intent.is_actionable() is False

    def test_is_actionable_watch_high_confidence(self):
        """Test is_actionable for watch with high confidence."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="watch",
            position_delta_hint="none",
            conviction=0.6,
            confidence=0.75,  # Above 0.7 threshold for watch
        )
        assert intent.is_actionable() is True

    def test_is_actionable_watch_low_confidence(self):
        """Test is_actionable for watch with low confidence."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="watch",
            position_delta_hint="none",
            conviction=0.6,
            confidence=0.65,  # Below 0.7 threshold for watch
        )
        assert intent.is_actionable() is False

    def test_is_actionable_opinion(self):
        """Test that opinion is never directly actionable."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="none",
            conviction=0.9,
            confidence=0.95,
        )
        assert intent.is_actionable() is False

    def test_needs_review_review_required(self):
        """Test needs_review for review_required actionability."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="unknown",
            actionability="review_required",
            position_delta_hint="unknown",
            conviction=0.3,
            confidence=0.9,
        )
        assert intent.needs_review() is True

    def test_needs_review_with_ambiguity_flags(self):
        """Test needs_review with ambiguity flags."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="add",  # Triggers flag
            conviction=0.7,
            confidence=0.8,
        )
        assert intent.needs_review() is True

    def test_needs_review_low_confidence(self):
        """Test needs_review with low confidence."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.4,  # Below 0.5 threshold
        )
        assert intent.needs_review() is True

    def test_summarize(self):
        """Test summarize method."""
        intent = NormalizedInvestmentIntent(
            intent_id="12345678-1234-1234-1234-123456789012",
            envelope_id="env-001",
            target_type="stock",
            target_name="宁德时代",
            target_symbol="300750.SZ",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.85,
            confidence=0.92,
        )
        summary = intent.summarize()
        assert "bullish" in summary
        assert "300750.SZ" in summary
        assert "explicit_action" in summary
        assert "add" in summary

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            target_symbol="TEST",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            sentiment_score=0.7,
            confidence=0.9,
        )
        data = intent.to_dict()
        restored = NormalizedInvestmentIntent.from_dict(data)
        assert restored.envelope_id == intent.envelope_id
        assert restored.target_name == intent.target_name
        assert restored.direction == intent.direction
        assert restored.conviction == intent.conviction


# =============================================================================
# Field Validation Tests
# =============================================================================

class TestFieldValidation:
    """Tests for field validation and constraints."""

    def test_conviction_bounds(self):
        """Test conviction must be between 0 and 1."""
        # Valid
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="none",
            conviction=0.5,
            confidence=0.5,
        )
        assert intent.conviction == 0.5

        # Invalid: > 1
        with pytest.raises(ValidationError):
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test",
                direction="bullish",
                actionability="opinion",
                position_delta_hint="none",
                conviction=1.5,
                confidence=0.5,
            )

    def test_confidence_bounds(self):
        """Test confidence must be between 0 and 1."""
        # Invalid: < 0
        with pytest.raises(ValidationError):
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test",
                direction="bullish",
                actionability="opinion",
                position_delta_hint="none",
                conviction=0.5,
                confidence=-0.1,
            )

    def test_sentiment_score_bounds(self):
        """Test sentiment_score must be between -1 and 1."""
        # Valid
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="none",
            conviction=0.5,
            sentiment_score=-0.8,
            confidence=0.5,
        )
        assert intent.sentiment_score == -0.8

        # Invalid: > 1
        with pytest.raises(ValidationError):
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test",
                direction="bullish",
                actionability="opinion",
                position_delta_hint="none",
                conviction=0.5,
                sentiment_score=1.5,
                confidence=0.5,
            )

    def test_target_type_literal(self):
        """Test target_type must be valid literal."""
        # Valid
        for tt in ["stock", "sector", "index", "macro", "commodity", "crypto", "unknown"]:
            intent = NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type=tt,
                target_name="Test",
                direction="bullish",
                actionability="opinion",
                position_delta_hint="none",
                conviction=0.5,
                confidence=0.5,
            )
            assert intent.target_type == tt

        # Invalid
        with pytest.raises(ValidationError):
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="invalid_type",
                target_name="Test",
                direction="bullish",
                actionability="opinion",
                position_delta_hint="none",
                conviction=0.5,
                confidence=0.5,
            )

    def test_direction_literal(self):
        """Test direction must be valid literal."""
        # Valid
        for d in ["bullish", "bearish", "neutral", "mixed", "unknown"]:
            intent = NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test",
                direction=d,
                actionability="opinion",
                position_delta_hint="none",
                conviction=0.5,
                confidence=0.5,
            )
            assert intent.direction == d

    def test_actionability_literal(self):
        """Test actionability must be valid literal."""
        # Valid
        for a in ["opinion", "watch", "explicit_action", "review_required"]:
            intent = NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test",
                direction="bullish",
                actionability=a,
                position_delta_hint="none",
                conviction=0.5,
                confidence=0.5,
            )
            assert intent.actionability == a


# =============================================================================
# IntentBatch Tests
# =============================================================================

class TestIntentBatch:
    """Tests for IntentBatch container."""

    def test_batch_auto_compute_stats(self):
        """Test that batch auto-computes statistics."""
        intents = [
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test1",
                direction="bullish",
                actionability="explicit_action",
                position_delta_hint="add",
                conviction=0.8,
                confidence=0.8,
            ),
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test2",
                direction="bearish",
                actionability="watch",
                position_delta_hint="none",
                conviction=0.6,
                confidence=0.75,
            ),
            NormalizedInvestmentIntent(
                envelope_id="env-001",
                target_type="stock",
                target_name="Test3",
                direction="neutral",
                actionability="review_required",
                position_delta_hint="unknown",
                conviction=0.3,
                confidence=0.4,
            ),
        ]
        batch = IntentBatch(intents=intents, envelope_id="env-001")

        assert batch.total_intents == 3
        assert batch.actionable_count == 2  # explicit_action + watch (high confidence)
        assert batch.review_required_count == 1  # only review_required

    def test_batch_empty(self):
        """Test empty batch."""
        batch = IntentBatch()
        assert batch.total_intents == 0
        assert batch.actionable_count == 0
        assert batch.review_required_count == 0


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_unknown_target_type(self):
        """Test unknown target_type is valid."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="unknown",
            target_name="Unknown Target",
            direction="unknown",
            actionability="review_required",
            position_delta_hint="unknown",
            conviction=0.1,
            confidence=0.2,
        )
        assert intent.target_type == "unknown"
        assert intent.needs_review() is True

    def test_mixed_direction(self):
        """Test mixed direction for complex statements."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="mixed",
            actionability="review_required",
            position_delta_hint="unknown",
            conviction=0.3,
            confidence=0.4,
        )
        assert intent.direction == "mixed"

    def test_crypto_target(self):
        """Test crypto target type."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="crypto",
            target_name="Bitcoin",
            target_symbol="BTC",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="open",
            conviction=0.7,
            confidence=0.8,
        )
        assert intent.target_type == "crypto"
        assert intent.target_symbol == "BTC"

    def test_sector_target(self):
        """Test sector target type."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="sector",
            target_name="半导体",
            direction="bullish",
            actionability="watch",
            position_delta_hint="none",
            conviction=0.6,
            confidence=0.75,
        )
        assert intent.target_type == "sector"
        assert intent.target_symbol is None  # Sectors don't have symbols


# =============================================================================
# F3/F4 Boundary Tests
# =============================================================================

class TestF3F4Boundary:
    """Tests verifying the F3 Intent does not contain F4 or F5 fields."""

    def test_f3_intent_no_position_size_pct(self):
        """F3 Intent MUST NOT contain position_size_pct — that is F5 territory."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.9,
        )
        data = intent.model_dump()
        assert "position_size_pct" not in data

    def test_f3_intent_no_target_price(self):
        """F3 Intent MUST NOT contain target price fields — F5 territory."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="opinion",
            position_delta_hint="none",
            conviction=0.7,
            confidence=0.8,
        )
        data = intent.model_dump()
        assert "target_price_low" not in data
        assert "target_price_high" not in data

    def test_f3_intent_no_stop_loss(self):
        """F3 Intent MUST NOT contain stop_loss or take_profit — F4/F5 territory."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="hold",
            conviction=0.6,
            confidence=0.7,
        )
        data = intent.model_dump()
        assert "stop_loss_pct" not in data
        assert "take_profit_pct" not in data

    def test_f3_intent_no_trigger_condition(self):
        """F3 Intent MUST NOT contain trigger_condition — F5 territory."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.9,
        )
        data = intent.model_dump()
        assert "trigger_condition" not in data
        assert "entry_condition" not in data
        assert "exit_condition" not in data

    def test_f3_intent_has_evidence_not_execution(self):
        """F3 Intent has evidence_span_ids but NOT action_chain."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.9,
            evidence_span_ids=["span-001", "span-002"],
        )
        data = intent.model_dump()
        # F3 has evidence traceability
        assert "evidence_span_ids" in data
        assert data["evidence_span_ids"] == ["span-001", "span-002"]
        # F3 does NOT have action_chain
        assert "action_chain" not in data

    def test_f3_position_delta_hint_is_hint_not_pct(self):
        """position_delta_hint is a semantic hint (open/add/reduce), not a percentage."""
        intent = NormalizedInvestmentIntent(
            envelope_id="env-001",
            target_type="stock",
            target_name="Test",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.9,
        )
        # position_delta_hint is a string enum, not a float
        assert isinstance(intent.position_delta_hint, str)
        assert intent.position_delta_hint in ("open", "add", "reduce", "hold", "exit", "none", "unknown")
