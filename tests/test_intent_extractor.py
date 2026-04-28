"""Tests for F3 Intent Extractor — Rule-based + LLM-based.

Tests verify both the rule-based baseline extractor and the LLM-based
extractor (using mock LLM calls) for architecture validation.
"""

import json
import pytest
from datetime import datetime
from typing import Optional

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.quality import QualityCard
from finer.schemas.entity_anchor import EntityAnchor
from finer.extraction.intent_extractor import (
    IntentExtractionResult,
    RuleBasedIntentExtractor,
    LLMIntentExtractor,
    extract_intents_from_envelope,
)


def make_quality_card() -> QualityCard:
    """Create a default quality card for testing."""
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.8,
        financial_relevance_score=0.9,
        entity_resolution_score=0.8,
        temporal_resolution_score=0.7,
        evidence_traceability_score=0.8,
    )


def make_test_envelope(blocks_text: list[str]) -> ContentEnvelope:
    """Create a test ContentEnvelope from block texts.

    Args:
        blocks_text: List of text for each block.

    Returns:
        ContentEnvelope with test blocks.
    """
    blocks = []
    for i, text in enumerate(blocks_text):
        block = ContentBlock(
            block_type="paragraph",
            text=text,
            order=i,
            quality_card=make_quality_card(),
        )
        blocks.append(block)

    return ContentEnvelope(
        envelope_id="test_env_001",
        source_type="feishu_doc",
        source_title="Test Document",
        quality_card=make_quality_card(),
        blocks=blocks,
    )


class TestIntentExtractorBasics:
    """Basic tests for intent extractor."""

    def test_empty_envelope(self):
        """Test extraction from empty envelope returns empty result."""
        envelope = ContentEnvelope(
            envelope_id="empty_env",
            source_type="text",
            quality_card=make_quality_card(),
        )

        result = extract_intents_from_envelope(envelope)

        assert result.envelope_id == "empty_env"
        assert len(result.intents) == 0
        assert len(result.evidence_spans) == 0

    def test_no_intent_text(self):
        """Test extraction from text without investment intent."""
        envelope = make_test_envelope([
            "今天天气不错，适合出门散步。",
            "明天计划去看电影。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 0

    def test_result_structure(self):
        """Test that result has correct structure."""
        envelope = make_test_envelope([
            "我看好宁德时代，准备加仓。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert isinstance(result, IntentExtractionResult)
        assert result.extractor_version == "rule_based_v1"
        assert isinstance(result.extraction_timestamp, datetime)


class TestDirectionDetection:
    """Tests for direction (bullish/bearish) detection."""

    def test_bullish_keyword_detection(self):
        """Test detection of bullish keywords."""
        envelope = make_test_envelope([
            "我看好宁德时代的发展前景。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        assert result.intents[0].direction == "bullish"

    def test_bearish_keyword_detection(self):
        """Test detection of bearish keywords."""
        envelope = make_test_envelope([
            "风险比较大，建议回避这只股票。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        assert result.intents[0].direction == "bearish"

    def test_explicit_buy_action(self):
        """Test detection of explicit buy action."""
        envelope = make_test_envelope([
            "今天加仓了宁德时代。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.direction == "bullish"
        assert intent.actionability == "explicit_action"
        assert intent.position_delta_hint == "add"

    def test_hold_action(self):
        """Test detection of hold action."""
        envelope = make_test_envelope([
            "继续持有腾讯，看好长期价值。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.actionability == "explicit_action"
        assert intent.position_delta_hint == "hold"

    def test_opinion_watch(self):
        """Test detection of opinion/watch signals."""
        envelope = make_test_envelope([
            "关注新能源板块的机会。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.actionability == "watch"
        assert intent.position_delta_hint == "none"


class TestEntityExtraction:
    """Tests for target entity extraction."""

    def test_unknown_entity(self):
        """Test handling of unknown entity."""
        envelope = make_test_envelope([
            "看好这个方向，准备加仓。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.target_name == "unknown"
        assert "unknown_target" in intent.ambiguity_flags

    def test_entity_from_anchors(self):
        """Test entity extraction from entity anchors."""
        envelope = make_test_envelope([
            "看好这只股票，准备加仓。",
        ])

        # Add entity anchor
        anchor = EntityAnchor(
            raw_text="宁德时代",
            resolved_name="宁德时代",
            resolved_symbol="300750.SZ",
            entity_type="stock",
            confidence=0.95,
        )
        envelope.entity_anchors = [anchor]

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.target_name == "宁德时代"
        assert intent.target_symbol == "300750.SZ"
        assert intent.target_type == "stock"


class TestEvidenceSpans:
    """Tests for evidence span creation."""

    def test_evidence_span_required(self):
        """Test that each intent has at least one evidence span."""
        envelope = make_test_envelope([
            "看好新能源板块，准备加仓。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert len(intent.evidence_span_ids) >= 1

        # Verify evidence spans exist
        assert len(result.evidence_spans) >= 1
        span = result.evidence_spans[0]
        assert span.block_id is not None
        assert span.text is not None
        assert span.confidence > 0

    def test_evidence_span_traceability(self):
        """Test that evidence spans point to correct blocks."""
        envelope = make_test_envelope([
            "第一段没有意图。",
            "第二段：看好宁德时代。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]

        # Intent should reference block 1 (second block)
        assert envelope.blocks[1].block_id in intent.block_ids


class TestConstraints:
    """Tests for extractor constraints."""

    def test_no_position_ratio(self):
        """Test that position ratio is not generated."""
        envelope = make_test_envelope([
            "加仓宁德时代 10%。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]

        # Should not have position ratio in metadata
        assert "position_ratio" not in intent.metadata

    def test_sentiment_score_auxiliary(self):
        """Test that sentiment score is auxiliary."""
        envelope = make_test_envelope([
            "我加仓宁德时代。",
        ])

        result = extract_intents_from_envelope(envelope)

        intent = result.intents[0]
        # Actionability should be explicit_action regardless of sentiment_score
        assert intent.actionability == "explicit_action"
        # sentiment_score should be None in minimal implementation
        assert intent.sentiment_score is None


class TestMultipleIntents:
    """Tests for multiple intents in one envelope."""

    def test_multiple_blocks_multiple_intents(self):
        """Test extraction from multiple blocks."""
        envelope = make_test_envelope([
            "看好新能源板块，关注一下。",
            "减仓了高估的科技股。",
        ])

        result = extract_intents_from_envelope(envelope)

        assert len(result.intents) == 2

        # First intent: bullish, opinion (看好 returns opinion, not watch)
        assert result.intents[0].direction == "bullish"
        assert result.intents[0].actionability == "opinion"

        # Second intent: bearish, explicit_action
        assert result.intents[1].direction == "bearish"
        assert result.intents[1].actionability == "explicit_action"


# =============================================================================
# Mock LLM helpers
# =============================================================================

def _make_mock_llm_fn(response_json: dict) -> callable:
    """Create a mock LLM callable that returns a fixed JSON response."""
    def mock_fn(prompt: str) -> str:
        return json.dumps(response_json, ensure_ascii=False)
    return mock_fn


# =============================================================================
# LLM Extractor Tests (with mock LLM)
# =============================================================================

class TestLLMExtractorBasics:
    """Basic tests for LLMIntentExtractor with mock LLM."""

    def test_llm_empty_result(self):
        """LLM returns no intents."""
        mock_llm = _make_mock_llm_fn({
            "intents": [],
            "overall_notes": ["No investment content detected"],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["今天天气不错。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 0
        assert result.extractor_version == "llm_v1"

    def test_llm_null_response(self):
        """LLM returns None (API failure)."""
        mock_llm = lambda prompt: None
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["我看好宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 0

    def test_llm_invalid_json(self):
        """LLM returns invalid JSON."""
        mock_llm = lambda prompt: "not valid json at all"
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["我看好宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 0
        assert any("Failed to parse" in n for n in result.processing_notes)

    def test_llm_basic_opinion(self):
        """LLM correctly extracts opinion vs action."""
        mock_llm = _make_mock_llm_fn({
            "intents": [{
                "target_name": "宁德时代",
                "target_symbol": "300750.SZ",
                "target_type": "stock",
                "market": "CN",
                "direction": "bullish",
                "actionability": "opinion",
                "position_delta_hint": "none",
                "conviction": 0.7,
                "confidence": 0.9,
                "evidence_text": "看好",
                "ambiguity_notes": [],
                "processing_notes": [],
            }],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["我看好宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.direction == "bullish"
        assert intent.actionability == "opinion"
        assert intent.position_delta_hint == "none"

    def test_llm_explicit_action(self):
        """LLM correctly identifies explicit action."""
        mock_llm = _make_mock_llm_fn({
            "intents": [{
                "target_name": "宁德时代",
                "target_symbol": "300750.SZ",
                "target_type": "stock",
                "market": "CN",
                "direction": "bullish",
                "actionability": "explicit_action",
                "position_delta_hint": "add",
                "conviction": 0.75,
                "confidence": 0.9,
                "evidence_text": "加仓",
                "ambiguity_notes": [],
                "processing_notes": [],
            }],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["我加仓宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.actionability == "explicit_action"
        assert intent.position_delta_hint == "add"

    def test_llm_rejects_forbidden_fields(self):
        """LLM output containing position_size is rejected."""
        mock_llm = _make_mock_llm_fn({
            "intents": [{
                "target_name": "宁德时代",
                "direction": "bullish",
                "actionability": "explicit_action",
                "position_delta_hint": "add",
                "conviction": 0.8,
                "confidence": 0.9,
                "position_size_pct": 0.1,
                "target_price": 500.0,
            }],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["加仓宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 0
        assert any("forbidden" in n for n in result.processing_notes)

    def test_llm_sentiment_auxiliary(self):
        """LLM includes sentiment_score as auxiliary, not primary."""
        mock_llm = _make_mock_llm_fn({
            "intents": [{
                "target_name": "宁德时代",
                "target_type": "stock",
                "direction": "bullish",
                "actionability": "explicit_action",
                "position_delta_hint": "add",
                "conviction": 0.75,
                "confidence": 0.85,
                "sentiment_score": 0.8,
                "evidence_text": "加仓",
                "ambiguity_notes": [],
                "processing_notes": [],
            }],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["加仓宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.actionability == "explicit_action"
        assert intent.sentiment_score is not None
        assert -1.0 <= intent.sentiment_score <= 1.0


class TestLLMExtractorAmbiguity:
    """Tests for ambiguity handling in LLM extractor."""

    def test_hold_and_add_compound(self):
        """Hold + add compound signal."""
        mock_llm = _make_mock_llm_fn({
            "intents": [{
                "target_name": "腾讯",
                "target_symbol": "0700.HK",
                "target_type": "stock",
                "market": "HK",
                "direction": "bullish",
                "actionability": "explicit_action",
                "position_delta_hint": "add",
                "conviction": 0.65,
                "confidence": 0.75,
                "evidence_text": "依然持有，今天稍微加仓一点",
                "ambiguity_notes": ["hold_and_add_compound: maintaining hold while adding slightly"],
                "processing_notes": [],
            }],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope([
            "今天腾讯跟随恒生科技大跌3个点，到达480的点位，"
            "目前我依然持有，今天稍微加仓一点，"
            "短期下跌趋势，不影响腾讯的社交流量入口护城河",
        ])

        result = extractor.extract(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.position_delta_hint == "add"
        assert intent.conviction < 0.8
        # Must have compound ambiguity flag
        assert any("hold_and_add" in f for f in intent.ambiguity_flags) or \
               any("compound" in f.lower() for f in intent.ambiguity_flags)

    def test_relative_time_unresolved(self):
        """Relative time is flagged, not fabricated."""
        mock_llm = _make_mock_llm_fn({
            "intents": [{
                "target_name": "光模块",
                "target_type": "sector",
                "target_symbol": None,
                "direction": "bullish",
                "actionability": "explicit_action",
                "position_delta_hint": "add",
                "conviction": 0.7,
                "confidence": 0.75,
                "evidence_text": "上周坚定抄底光模块",
                "ambiguity_notes": ["relative_time_unresolved: '上周'"],
                "processing_notes": [],
            }],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope([
            "上周的时候，我们坚定抄底光模块，这周市场资金重新回归光模块",
        ])

        result = extractor.extract(envelope)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert any("relative_time" in f for f in intent.ambiguity_flags) or \
               any("temporal" in f.lower() for f in intent.ambiguity_flags)


class TestLLMExtractorEdgeCases:
    """Edge case tests for LLM extractor."""

    def test_llm_with_code_fences(self):
        """LLM wraps JSON in markdown code fences."""
        raw_json = json.dumps({
            "intents": [{
                "target_name": "宁德时代",
                "target_type": "stock",
                "direction": "bullish",
                "actionability": "opinion",
                "position_delta_hint": "none",
                "conviction": 0.6,
                "confidence": 0.8,
                "ambiguity_notes": [],
                "processing_notes": [],
            }],
        }, ensure_ascii=False)
        mock_llm = lambda prompt: f"```json\n{raw_json}\n```"

        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["我看好宁德时代。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 1
        assert result.intents[0].actionability == "opinion"

    def test_llm_multiple_intents(self):
        """LLM extracts multiple intents from one envelope."""
        mock_llm = _make_mock_llm_fn({
            "intents": [
                {
                    "target_name": "宁德时代",
                    "target_type": "stock",
                    "direction": "bullish",
                    "actionability": "opinion",
                    "position_delta_hint": "none",
                    "conviction": 0.7,
                    "confidence": 0.85,
                    "ambiguity_notes": [],
                    "processing_notes": [],
                },
                {
                    "target_name": "腾讯",
                    "target_type": "stock",
                    "direction": "bullish",
                    "actionability": "explicit_action",
                    "position_delta_hint": "hold",
                    "conviction": 0.65,
                    "confidence": 0.8,
                    "ambiguity_notes": [],
                    "processing_notes": [],
                },
            ],
        })
        extractor = LLMIntentExtractor(llm_fn=mock_llm)
        envelope = make_test_envelope(["看好宁德时代，继续持有腾讯。"])

        result = extractor.extract(envelope)

        assert len(result.intents) == 2
