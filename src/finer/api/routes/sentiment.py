"""Sentiment Analysis API — REST endpoints for sentiment analysis.

Provides:
- POST /api/sentiment/analyze — Analyze single text
- POST /api/sentiment/batch — Batch analyze multiple texts
- GET /api/sentiment/config — Get configuration
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from finer.ml.sentiment.analyzer import SentimentAnalyzer
from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError
from finer.ml.sentiment.schemas import (
    BatchSentimentRequest,
    BatchSentimentResult,
    SentimentConfigResponse,
    SentimentRequest,
    SentimentResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Singleton analyzer instances
_analyzers: Dict[str, SentimentAnalyzer] = {}


def get_analyzer(mode: str) -> SentimentAnalyzer:
    """Get or create analyzer for given mode."""
    if mode not in _analyzers:
        _analyzers[mode] = SentimentAnalyzer(mode=mode)
    return _analyzers[mode]


@router.post("/analyze", response_model=SentimentResult)
async def analyze_sentiment(request: SentimentRequest) -> SentimentResult:
    """Analyze sentiment of a single text.

    Args:
        request: SentimentRequest with text, optional context, and mode

    Returns:
        SentimentResult with sentiment type, score, confidence, keywords

    Raises:
        FinerError: If analysis fails
    """
    try:
        analyzer = get_analyzer(request.mode)
        result = analyzer.analyze(request.text, request.context)
        return result
    except ValueError as e:
        raise FinerError(ErrorCode.API_IN_001, str(e), stage="F6", operation="sentiment_analyze", retryable=False, cause=e)
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        raise FinerError(ErrorCode.API_INT_001, "Analysis failed", stage="F6", operation="sentiment_analyze", retryable=False, cause=e)


@router.post("/batch", response_model=BatchSentimentResult)
async def batch_analyze_sentiment(request: BatchSentimentRequest) -> BatchSentimentResult:
    """Batch analyze multiple texts.

    Args:
        request: BatchSentimentRequest with texts list, optional context, and mode

    Returns:
        BatchSentimentResult with all results and statistics

    Raises:
        FinerError: If analysis fails
    """
    if not request.texts:
        return BatchSentimentResult(results=[], summary={}, average_score=0.0)

    try:
        analyzer = get_analyzer(request.mode)
        result = analyzer.batch_analyze(request.texts, request.context)
        return result
    except ValueError as e:
        raise FinerError(ErrorCode.API_IN_001, str(e), stage="F6", operation="sentiment_batch", retryable=False, cause=e)
    except Exception as e:
        logger.error(f"Batch sentiment analysis failed: {e}")
        raise FinerError(ErrorCode.API_INT_001, "Analysis failed", stage="F6", operation="sentiment_batch", retryable=False, cause=e)


@router.get("/config", response_model=SentimentConfigResponse)
async def get_sentiment_config() -> SentimentConfigResponse:
    """Get sentiment analysis configuration.

    Returns:
        SentimentConfigResponse with available modes and settings
    """
    # Check LLM availability
    llm_available = False
    try:
        from finer.llm import LLMClient

        client = LLMClient.auto()
        llm_available = client is not None
    except Exception:
        llm_available = False

    return SentimentConfigResponse(
        available_modes=["rule", "llm", "hybrid"],
        default_mode="rule",
        supported_languages=["zh", "en", "mixed"],
        llm_available=llm_available,
    )
