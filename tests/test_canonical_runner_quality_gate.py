"""Tests for Quality Gate wiring in canonical pipeline runners.

Verifies that:
1. golden_path.run_golden_path applies quality gate before F3
2. canonical_runner.run_canonical_extraction applies quality gate before F3
3. Envelopes with "reject" gate_status are skipped (no intent extraction)
4. Envelopes with "pass" or "review" gate_status proceed to F3
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from finer.schemas.quality import QualityCard
from finer.schemas.content_envelope import ContentEnvelope, ContentBlock


# =============================================================================
# Helpers
# =============================================================================


def _make_envelope(quality_card: QualityCard) -> ContentEnvelope:
    """Create a minimal ContentEnvelope with the given quality card."""
    return ContentEnvelope(
        envelope_id="env-test-001",
        source_type="text",
        creator_id="test-kol",
        published_at=datetime.now(),
        ingested_at=datetime.now(),
        blocks=[],
        quality_card=quality_card,
        temporal_anchors=[],
        entity_anchors=[],
        metadata={},
    )


def _pass_card() -> QualityCard:
    """QualityCard that evaluates to gate_status='pass'."""
    return QualityCard(
        readability_score=0.95,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.95,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.85,
        evidence_traceability_score=0.9,
    )


def _reject_card() -> QualityCard:
    """QualityCard that evaluates to gate_status='reject'."""
    return QualityCard(
        readability_score=0.2,
        semantic_completeness_score=0.2,
        financial_relevance_score=0.1,
        entity_resolution_score=0.2,
        temporal_resolution_score=0.15,
        evidence_traceability_score=0.1,
    )


def _review_card() -> QualityCard:
    """QualityCard that evaluates to gate_status='review'."""
    return QualityCard(
        readability_score=0.7,
        semantic_completeness_score=0.65,
        financial_relevance_score=0.6,
        entity_resolution_score=0.5,
        temporal_resolution_score=0.55,
        evidence_traceability_score=0.55,
    )


# Verify helper cards have expected gate_status values
class TestHelperCards:
    """Sanity-check that helper QualityCards produce expected gate_status."""

    def test_pass_card_gate_status(self):
        assert _pass_card().gate_status == "pass"

    def test_reject_card_gate_status(self):
        assert _reject_card().gate_status == "reject"

    def test_review_card_gate_status(self):
        assert _review_card().gate_status == "review"


# =============================================================================
# Golden Path Quality Gate Tests
# =============================================================================


class TestGoldenPathQualityGate:
    """Tests that golden_path.run_golden_path enforces quality gate."""

    def test_pass_envelope_proceeds_to_f3(self):
        """Envelope with 'pass' quality should reach F3 intent extraction."""
        from finer.pipeline.golden_path import run_golden_path

        envelope = _make_envelope(_pass_card())

        mock_intent = MagicMock()
        mock_intent.intent_id = "intent-001"
        mock_intent.evidence_span_ids = ["span-001"]
        mock_intent.target_symbol = "300750.SZ"
        mock_intent.target_name = "宁德时代"
        mock_intent.market = "CN"
        mock_intent.direction = "bullish"
        mock_intent.confidence = 0.85

        mock_result = MagicMock()
        mock_result.intents = [mock_intent]
        mock_result.processing_notes = []

        mock_mapped = MagicMock()
        mock_mapped.intent_id = "intent-001"
        mock_mapped.policy_id = "policy-001"
        mock_mapped.action_hint = "open_position"
        mock_mapped.position_sizing_hint = "small"
        mock_mapped.holding_period_hint = "medium_term"
        mock_mapped.requires_human_review = False

        mock_batch = MagicMock()
        mock_batch.mapped_intents = [mock_mapped]
        mock_batch.mappings = [mock_mapped]

        with (
            patch("finer.pipeline.golden_path.LLMIntentExtractor") as MockExtractor,
            patch("finer.pipeline.golden_path.PolicyMapper") as MockMapper,
        ):
            MockExtractor.return_value.extract.return_value = mock_result
            MockMapper.return_value.map_batch.return_value = mock_batch

            # Should not raise — proceeds to F3
            result = run_golden_path(envelope, data_root="/tmp/test_golden")
            assert result is not None
            MockExtractor.return_value.extract.assert_called_once_with(envelope)

    def test_reject_envelope_raises_value_error(self):
        """Envelope with 'reject' quality should raise ValueError before F3."""
        from finer.pipeline.golden_path import run_golden_path

        envelope = _make_envelope(_reject_card())

        with patch("finer.pipeline.golden_path.LLMIntentExtractor") as MockExtractor:
            with pytest.raises(ValueError, match="rejected by quality gate"):
                run_golden_path(envelope, data_root="/tmp/test_golden")

            # Extractor should NOT have been called
            MockExtractor.return_value.extract.assert_not_called()

    def test_review_envelope_proceeds_to_f3(self):
        """Envelope with 'review' quality should proceed to F3 (review is not reject)."""
        from finer.pipeline.golden_path import run_golden_path

        envelope = _make_envelope(_review_card())

        mock_intent = MagicMock()
        mock_intent.intent_id = "intent-002"
        mock_intent.evidence_span_ids = ["span-002"]
        mock_intent.target_symbol = "0700.HK"
        mock_intent.target_name = "腾讯"
        mock_intent.market = "HK"
        mock_intent.direction = "bullish"
        mock_intent.confidence = 0.75

        mock_result = MagicMock()
        mock_result.intents = [mock_intent]
        mock_result.processing_notes = []

        mock_mapped = MagicMock()
        mock_mapped.intent_id = "intent-002"
        mock_mapped.policy_id = "policy-002"
        mock_mapped.action_hint = "open_position"
        mock_mapped.position_sizing_hint = "medium"
        mock_mapped.holding_period_hint = "long_term"
        mock_mapped.requires_human_review = False

        mock_batch = MagicMock()
        mock_batch.mapped_intents = [mock_mapped]
        mock_batch.mappings = [mock_mapped]

        with (
            patch("finer.pipeline.golden_path.LLMIntentExtractor") as MockExtractor,
            patch("finer.pipeline.golden_path.PolicyMapper") as MockMapper,
        ):
            MockExtractor.return_value.extract.return_value = mock_result
            MockMapper.return_value.map_batch.return_value = mock_batch

            # Should not raise — proceeds to F3
            result = run_golden_path(envelope, data_root="/tmp/test_golden_review")
            assert result is not None
            MockExtractor.return_value.extract.assert_called_once_with(envelope)


# =============================================================================
# Canonical Runner Quality Gate Tests (deprecated path)
# =============================================================================


class TestCanonicalRunnerQualityGate:
    """Tests that canonical_runner.run_canonical_extraction enforces quality gate."""

    @pytest.mark.asyncio
    async def test_pass_envelope_proceeds_to_f3(self):
        """Envelope with 'pass' quality should reach F3 intent extraction."""
        from finer.pipeline.canonical_runner import run_canonical_extraction

        mock_intent = MagicMock()
        mock_intent.intent_id = "intent-001"
        mock_intent.evidence_span_ids = ["span-001"]
        mock_intent.target_symbol = "300750.SZ"
        mock_intent.target_name = "宁德时代"
        mock_intent.market = "CN"
        mock_intent.direction = "bullish"
        mock_intent.confidence = 0.85

        mock_result = MagicMock()
        mock_result.intents = [mock_intent]
        mock_result.evidence_spans = []

        mock_mapped = MagicMock()
        mock_mapped.intent_id = "intent-001"
        mock_mapped.policy_id = "policy-001"
        mock_mapped.action_hint = "open_position"
        mock_mapped.position_sizing_hint = "small"
        mock_mapped.holding_period_hint = "medium_term"
        mock_mapped.requires_human_review = False

        mock_batch = MagicMock()
        mock_batch.mapped_intents = [mock_mapped]
        mock_batch.mappings = [mock_mapped]

        with (
            patch("finer.extraction.intent_extractor.RuleBasedIntentExtractor") as MockExtractor,
            patch("finer.policy.policy_mapper.PolicyMapper") as MockMapper,
        ):
            MockExtractor.return_value.extract.return_value = mock_result
            MockMapper.return_value.map_batch.return_value = mock_batch

            result = await run_canonical_extraction(
                text="看好宁德时代，目标价500",
                context={"source_id": "test-001", "author": "test-kol"},
            )

            # Extractor should have been called (pass gate allows F3)
            MockExtractor.return_value.extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_envelope_returns_empty_list(self):
        """Envelope with 'reject' quality should return empty list before F3."""
        from finer.pipeline.canonical_runner import run_canonical_extraction

        with patch("finer.extraction.intent_extractor.RuleBasedIntentExtractor") as MockExtractor:
            # The default envelope built by _build_envelope has pass quality (0.8).
            # We need to patch _build_envelope to return a reject-quality envelope.
            reject_envelope = _make_envelope(_reject_card())

            with patch(
                "finer.pipeline.canonical_runner._build_envelope",
                return_value=reject_envelope,
            ):
                result = await run_canonical_extraction(
                    text="some text",
                    context={"source_id": "test-002"},
                )

                assert result == []
                # Extractor should NOT have been called
                MockExtractor.return_value.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_review_envelope_proceeds_to_f3(self):
        """Envelope with 'review' quality should proceed to F3."""
        from finer.pipeline.canonical_runner import run_canonical_extraction

        mock_intent = MagicMock()
        mock_intent.intent_id = "intent-003"
        mock_intent.evidence_span_ids = ["span-003"]
        mock_intent.target_symbol = "0700.HK"
        mock_intent.target_name = "腾讯"
        mock_intent.market = "HK"
        mock_intent.direction = "bullish"
        mock_intent.confidence = 0.7

        mock_result = MagicMock()
        mock_result.intents = [mock_intent]
        mock_result.evidence_spans = []

        mock_mapped = MagicMock()
        mock_mapped.intent_id = "intent-003"
        mock_mapped.policy_id = "policy-003"
        mock_mapped.action_hint = "open_position"
        mock_mapped.position_sizing_hint = "medium"
        mock_mapped.holding_period_hint = "long_term"
        mock_mapped.requires_human_review = False

        mock_batch = MagicMock()
        mock_batch.mapped_intents = [mock_mapped]
        mock_batch.mappings = [mock_mapped]

        # Patch _build_envelope to return review-quality envelope
        review_envelope = _make_envelope(_review_card())

        with (
            patch(
                "finer.pipeline.canonical_runner._build_envelope",
                return_value=review_envelope,
            ),
            patch("finer.extraction.intent_extractor.RuleBasedIntentExtractor") as MockExtractor,
            patch("finer.policy.policy_mapper.PolicyMapper") as MockMapper,
        ):
            MockExtractor.return_value.extract.return_value = mock_result
            MockMapper.return_value.map_batch.return_value = mock_batch

            result = await run_canonical_extraction(
                text="some text",
                context={"source_id": "test-003"},
            )

            # Extractor should have been called (review gate allows F3)
            MockExtractor.return_value.extract.assert_called_once()
