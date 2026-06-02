"""Tests for F5 Execute — TradeAction extraction pipeline.

Covers:
- TradeActionExtractor: GLM-5.1 + Finance-Skills hybrid extraction
- Confidence-based routing
- LLM response parsing
- Batch extraction
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from finer.extraction.trade_action_extractor import (
    TradeActionExtractor,
    ExtractionResult,
    ConfidenceThreshold,
)
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    TriggerType,
    TradeAction,
    TradeDirection,
    ValidationStatus,
    TargetInfo,
    SourceInfo,
)
from finer.services.finance_skills_client import FinanceSkillsClient


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLMClient for testing."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat_prompt = MagicMock()
    return client


@pytest.fixture
def mock_finance_client():
    """Mock FinanceSkillsClient."""
    client = AsyncMock()
    client.get_market_data = AsyncMock()
    client.get_fundamentals = AsyncMock()
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_extraction_response():
    """Sample LLM JSON response for extraction."""
    return """
    [
        {
            "ticker": "AAPL",
            "ticker_normalized": "AAPL",
            "market": "US",
            "instrument_type": "stock",
            "direction": "bullish",
            "confidence": 0.85,
            "action_chain": [
                {
                    "action_type": "watch",
                    "trigger_condition": "price < 180",
                    "trigger_type": "price_threshold"
                },
                {
                    "action_type": "long",
                    "trigger_condition": "breaks above 180",
                    "trigger_type": "breakout",
                    "target_price_low": 180,
                    "target_price_high": 200
                }
            ],
            "time_horizon": "2 weeks",
            "rationale": "Technical support at 180"
        }
    ]
    """


@pytest.fixture
def sample_market_data():
    """Sample market data from finance-skills."""
    return {
        "currentPrice": 175.0,
        "averageVolume": 50000000,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 120.0,
        "trailingPE": 28.5,
        "marketCap": 2800000000000,
    }


# =============================================================================
# ExtractionResult Tests
# =============================================================================

class TestExtractionResult:
    """Tests for ExtractionResult container."""

    def test_result_creation_success(self):
        """Test successful result creation."""
        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            confidence=0.8,
        )
        result = ExtractionResult(
            success=True,
            actions=[action],
            raw_response='[{"ticker": "AAPL"}]',
        )
        assert result.success is True
        assert result.action_count == 1
        assert result.avg_confidence == 0.8

    def test_result_empty_actions(self):
        """Test result with no actions."""
        result = ExtractionResult(success=True, actions=[])
        assert result.action_count == 0
        assert result.avg_confidence == 0.0

    def test_result_with_error(self):
        """Test result with error."""
        result = ExtractionResult(
            success=False,
            actions=[],
            error="LLM connection failed",
        )
        assert result.success is False
        assert result.error == "LLM connection failed"


# =============================================================================
# ConfidenceThreshold Tests
# =============================================================================

class TestConfidenceThreshold:
    """Tests for confidence thresholds."""

    def test_threshold_values(self):
        """Test threshold constants."""
        assert ConfidenceThreshold.HIGH == 0.8
        assert ConfidenceThreshold.MEDIUM == 0.5
        assert ConfidenceThreshold.LOW == 0.3


# =============================================================================
# TradeActionExtractor Tests
# =============================================================================

class TestTradeActionExtractor:
    """Tests for TradeActionExtractor."""

    def test_extractor_initialization(self, mock_llm_client, mock_finance_client):
        """Test extractor initialization."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )
        assert extractor.model_version == "glm-5.1"
        assert extractor.enable_enrichment is True

    def test_build_extraction_prompt(self, mock_llm_client, mock_finance_client):
        """Test prompt building."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        system_prompt, user_prompt = extractor._build_extraction_prompt(
            "AAPL at 180 is a good entry",
            context={"source_id": "test-001", "author": "analyst"},
        )

        assert "交易操作" in system_prompt
        assert "AAPL at 180" in user_prompt
        assert "test-001" in user_prompt

    def test_parse_llm_response_valid(
        self, mock_llm_client, mock_finance_client, sample_extraction_response
    ):
        """Test parsing valid LLM response."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        actions = extractor._parse_llm_response(
            sample_extraction_response,
            source_id="test-001",
            evidence_text="AAPL at 180 is a good entry",
        )

        assert len(actions) == 1
        assert actions[0].target.ticker == "AAPL"
        assert actions[0].direction == TradeDirection.BULLISH
        assert len(actions[0].action_chain) == 2

    def test_parse_llm_response_with_markdown(
        self, mock_llm_client, mock_finance_client, sample_extraction_response
    ):
        """Test parsing LLM response wrapped in markdown."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        markdown_response = f"```json\n{sample_extraction_response}\n```"

        actions = extractor._parse_llm_response(
            markdown_response,
            source_id="test-001",
            evidence_text="Test",
        )

        assert len(actions) == 1

    def test_parse_llm_response_invalid_json(self, mock_llm_client, mock_finance_client):
        """Test handling invalid JSON response."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        actions = extractor._parse_llm_response(
            "This is not valid JSON",
            source_id="test-001",
            evidence_text="Test",
        )

        assert actions == []

    def test_parse_llm_response_single_object(self, mock_llm_client, mock_finance_client):
        """Test parsing single object (not array) response."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        single_object = '{"ticker": "AAPL", "direction": "bullish", "confidence": 0.8}'

        actions = extractor._parse_llm_response(
            single_object,
            source_id="test-001",
            evidence_text="Test",
        )

        assert len(actions) == 1

    def test_dict_to_trade_action(self, mock_llm_client, mock_finance_client):
        """Test converting dictionary to TradeAction."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        data = {
            "ticker": "TSLA",
            "ticker_normalized": "TSLA",
            "market": "US",
            "direction": "bearish",
            "confidence": 0.75,
            "action_chain": [
                {
                    "action_type": "short",
                    "trigger_condition": "price > 250",
                    "trigger_type": "price_threshold",
                }
            ],
            "time_horizon": "1 week",
        }

        action = extractor._dict_to_trade_action(
            data,
            source_id="test-001",
            evidence_text="TSLA looks overvalued",
        )

        assert action.target.ticker == "TSLA"
        assert action.direction == TradeDirection.BEARISH
        assert action.confidence == 0.75
        assert len(action.action_chain) == 1

    @pytest.mark.asyncio
    async def test_extract_from_text_success(
        self, mock_llm_client, mock_finance_client, sample_extraction_response
    ):
        """Test successful text extraction."""
        mock_llm_client.chat.return_value = sample_extraction_response

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        result = await extractor.extract_from_text(
            "AAPL at 180 is a good entry point",
            context={"source_id": "test-001"},
        )

        assert result.success is True
        assert result.action_count == 1
        assert result.needs_validation is False  # confidence 0.85 >= 0.8

    @pytest.mark.asyncio
    async def test_extract_from_text_no_client(self, mock_finance_client):
        """Test extraction with no LLM client."""
        extractor = TradeActionExtractor(
            llm_client=None,
            finance_client=mock_finance_client,
        )
        # Mock get_text_registry to prevent auto-creating a client
        with patch("finer.model_config.get_text_registry", side_effect=RuntimeError("no registry in test")):
            result = await extractor.extract_from_text("Test text")

        assert result.success is False
        assert "No LLM client" in result.error

    @pytest.mark.asyncio
    async def test_extract_from_text_empty_response(
        self, mock_llm_client, mock_finance_client
    ):
        """Test handling empty LLM response."""
        mock_llm_client.chat.return_value = None

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        result = await extractor.extract_from_text("Test text")

        assert result.success is False
        assert "Empty" in result.error

    @pytest.mark.asyncio
    async def test_extract_from_file(
        self, mock_llm_client, mock_finance_client, sample_extraction_response, tmp_path
    ):
        """Test extraction from file."""
        mock_llm_client.chat.return_value = sample_extraction_response

        # Create test file
        test_file = tmp_path / "2026-04-24-test.txt"
        test_file.write_text("AAPL at 180 is a good entry")

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        result = await extractor.extract_from_file(str(test_file))

        assert result.success is True

    @pytest.mark.asyncio
    async def test_extract_from_file_not_found(
        self, mock_llm_client, mock_finance_client
    ):
        """Test handling file not found."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        result = await extractor.extract_from_file("/nonexistent/file.txt")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_batch_extract_sequential(
        self, mock_llm_client, mock_finance_client, sample_extraction_response
    ):
        """Test sequential batch extraction."""
        mock_llm_client.chat.return_value = sample_extraction_response

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        items = [
            {"text": "AAPL bullish", "context": {"source_id": "t1"}},
            {"text": "TSLA bearish", "context": {"source_id": "t2"}},
        ]

        results = await extractor.batch_extract(items, parallel=False)

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_batch_extract_parallel(
        self, mock_llm_client, mock_finance_client, sample_extraction_response
    ):
        """Test parallel batch extraction."""
        mock_llm_client.chat.return_value = sample_extraction_response

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        items = [
            {"text": f"Stock {i} analysis", "context": {"source_id": f"t{i}"}}
            for i in range(5)
        ]

        results = await extractor.batch_extract(
            items,
            parallel=True,
            max_concurrency=3,
        )

        assert len(results) == 5


# =============================================================================
# Enrichment Integration Tests
# =============================================================================

class TestExtractionEnrichment:
    """Tests for extraction with enrichment."""

    @pytest.mark.asyncio
    async def test_validate_and_enrich_success(
        self, mock_llm_client, mock_finance_client, sample_market_data
    ):
        """Test successful validation and enrichment."""
        mock_finance_client.get_market_data.return_value = sample_market_data
        mock_finance_client.get_fundamentals.return_value = {"pe_ratio": 28.5}

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
            enable_enrichment=True,
        )

        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            confidence=0.6,  # Below HIGH threshold
        )

        enriched = await extractor.validate_and_enrich(action)

        assert enriched.enrichment is not None
        assert enriched.enrichment.market_price_at_time == 175.0

    @pytest.mark.asyncio
    async def test_validate_and_enrich_disabled(self, mock_llm_client, mock_finance_client):
        """Test that enrichment can be disabled."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
            enable_enrichment=False,
        )

        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )

        enriched = await extractor.validate_and_enrich(action)

        assert enriched.enrichment is None

    @pytest.mark.asyncio
    async def test_validate_price_targets(
        self, mock_llm_client, mock_finance_client, sample_market_data
    ):
        """Test price target validation."""
        mock_finance_client.get_market_data.return_value = sample_market_data

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        action = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
            action_chain=[
                ActionStep(
                    sequence=1,
                    action_type=ActionType.LONG,
                    target_price_low=130.0,  # Below 175 * 0.8 = 140 threshold
                    target_price_high=200.0,
                ),
            ],
        )

        validated = await extractor.validate_and_enrich(action)

        # Should have warnings for bullish with low target
        assert len(validated.validation_warnings) > 0

    @pytest.mark.asyncio
    async def test_extract_with_enrichment_pipeline(
        self, mock_llm_client, mock_finance_client,
        sample_extraction_response, sample_market_data
    ):
        """Test full extraction + enrichment pipeline."""
        mock_llm_client.chat.return_value = sample_extraction_response
        mock_finance_client.get_market_data.return_value = sample_market_data

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
            enable_enrichment=True,
        )

        batch = await extractor.extract_with_enrichment(
            "AAPL at 180 is a good entry",
            context={"source_id": "test-001"},
            enrich_all=True,
        )

        assert batch.total_actions == 1
        assert batch.bullish_count == 1


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_with_missing_fields(self, mock_llm_client, mock_finance_client):
        """Test parsing with missing optional fields."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        # Minimal valid response
        response = '[{"ticker": "AAPL"}]'

        actions = extractor._parse_llm_response(
            response,
            source_id="test",
            evidence_text="Test",
        )

        # Should create action with defaults
        assert len(actions) == 1
        assert actions[0].direction == TradeDirection.NEUTRAL  # Default

    def test_parse_with_invalid_action_type(self, mock_llm_client, mock_finance_client):
        """Test handling invalid action type."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        response = '''
        [{
            "ticker": "AAPL",
            "direction": "bullish",
            "action_chain": [
                {"action_type": "invalid_type"}
            ]
        }]
        '''

        actions = extractor._parse_llm_response(
            response,
            source_id="test",
            evidence_text="Test",
        )

        # Should default to WATCH
        assert len(actions) == 1
        assert actions[0].action_chain[0].action_type == ActionType.WATCH

    def test_parse_with_confidence_out_of_range(self, mock_llm_client, mock_finance_client):
        """Test clamping confidence to valid range."""
        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        response = '''
        [{
            "ticker": "AAPL",
            "direction": "bullish",
            "confidence": 1.5
        }]
        '''

        actions = extractor._parse_llm_response(
            response,
            source_id="test",
            evidence_text="Test",
        )

        assert actions[0].confidence == 1.0  # Clamped

    @pytest.mark.asyncio
    async def test_concurrent_extraction_limit(
        self, mock_llm_client, mock_finance_client, sample_extraction_response
    ):
        """Test that concurrent extraction respects semaphore."""
        call_count = 0

        def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return sample_extraction_response

        mock_llm_client.chat.side_effect = count_calls

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        items = [
            {"text": f"Stock {i}", "context": {"source_id": f"t{i}"}}
            for i in range(10)
        ]

        results = await extractor.batch_extract(
            items,
            parallel=True,
            max_concurrency=3,
        )

        assert len(results) == 10
        assert all(r.success for r in results)


# =============================================================================
# Confidence Routing Tests
# =============================================================================

class TestConfidenceRouting:
    """Tests for confidence-based routing."""

    @pytest.mark.asyncio
    async def test_high_confidence_direct_output(
        self, mock_llm_client, mock_finance_client
    ):
        """Test that high confidence actions bypass enrichment."""
        high_conf_response = '''
        [{
            "ticker": "AAPL",
            "direction": "bullish",
            "confidence": 0.95
        }]
        '''
        mock_llm_client.chat.return_value = high_conf_response

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
            enable_enrichment=True,
        )

        result = await extractor.extract_from_text("Test")

        assert result.success is True
        assert not result.needs_validation  # High confidence

    @pytest.mark.asyncio
    async def test_low_confidence_needs_validation(
        self, mock_llm_client, mock_finance_client
    ):
        """Test that low confidence actions need validation."""
        low_conf_response = '''
        [{
            "ticker": "AAPL",
            "direction": "bullish",
            "confidence": 0.4
        }]
        '''
        mock_llm_client.chat.return_value = low_conf_response

        extractor = TradeActionExtractor(
            llm_client=mock_llm_client,
            finance_client=mock_finance_client,
        )

        result = await extractor.extract_from_text("Test")

        assert result.success is True
        assert result.needs_validation is True
