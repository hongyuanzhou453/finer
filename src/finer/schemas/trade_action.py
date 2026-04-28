"""Trade Action Schema — Standardized output template for trading actions.

This module defines the canonical data structure for trade actions extracted
from content analysis. The schema supports the full pipeline from extraction
through enrichment, validation, backtesting, and RLHF feedback.

Key Design Principles:
1. All timestamps are ISO 8601 format for cross-system compatibility
2. Validation status tracks the quality assurance lifecycle
3. Backtest results enable performance tracking
4. RLHF fields support continuous model improvement
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from finer.schemas.lineage import DataLineage, VersionInfo


# =============================================================================
# Enumerations
# =============================================================================

class TradeDirection(str, Enum):
    """Trading direction/sentiment classification."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    WATCHLIST = "watchlist"
    RISK_WARNING = "risk_warning"


class ActionType(str, Enum):
    """Specific trading operation types."""
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    BUY_CALL = "buy_call"
    SELL_CALL = "sell_call"
    BUY_PUT = "buy_put"
    SELL_PUT = "sell_put"
    HOLD = "hold"
    WATCH = "watch"
    BUY_AND_HOLD = "buy_and_hold"


class TriggerType(str, Enum):
    """Trigger condition types."""
    PRICE_THRESHOLD = "price_threshold"
    BREAKOUT = "breakout"
    SUPPORT_RESISTANCE = "support_resistance"
    INDICATOR_SIGNAL = "indicator_signal"
    TIME_BASED = "time_based"
    NEWS_EVENT = "news_event"
    MANUAL = "manual"


class ValidationStatus(str, Enum):
    """Validation lifecycle status."""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    UNDER_REVIEW = "under_review"


class ExitReason(str, Enum):
    """Reasons for exiting a position."""
    TARGET_REACHED = "target_reached"
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"
    SIGNAL_REVERSAL = "signal_reversal"
    MANUAL = "manual"
    UNKNOWN = "unknown"


# =============================================================================
# Nested Models
# =============================================================================

class SourceInfo(BaseModel):
    """Source attribution for the trade action."""
    model_config = ConfigDict(strict=True)

    creator_id: Optional[str] = Field(
        None,
        description="Unique identifier of content creator (Feishu user ID, etc.)"
    )
    content_id: str = Field(
        ...,
        description="Unique identifier of source content (Feishu doc ID, message ID, etc.)"
    )
    evidence_text: str = Field(
        ...,
        description="Original text segment that triggered this action"
    )
    evidence_start_idx: Optional[int] = Field(
        None,
        description="Start character index in source content"
    )
    evidence_end_idx: Optional[int] = Field(
        None,
        description="End character index in source content"
    )
    content_url: Optional[str] = Field(
        None,
        description="URL to source content for reference"
    )


class TargetInfo(BaseModel):
    """Target asset information."""
    model_config = ConfigDict(strict=True)

    ticker: str = Field(
        ...,
        description="Raw ticker symbol as extracted"
    )
    ticker_normalized: Optional[str] = Field(
        None,
        description="Normalized ticker (e.g., 'AAPL' from 'apple', '苹果公司')"
    )
    market: Optional[str] = Field(
        None,
        description="Market identifier (e.g., 'US', 'HK', 'CN', 'CRYPTO')"
    )
    instrument_type: Literal["stock", "option", "etf", "index_future", "crypto", "unspecified"] = Field(
        "unspecified",
        description="Asset class"
    )
    company_name: Optional[str] = Field(
        None,
        description="Full company name for reference"
    )

    @model_validator(mode='after')
    def normalize_ticker_if_none(self) -> TargetInfo:
        """Auto-normalize ticker if not provided."""
        if self.ticker_normalized is None and self.ticker:
            # Basic normalization: uppercase, strip whitespace
            ticker = self.ticker.strip().upper()
            # Remove common prefixes like $ for cashtags
            ticker = ticker.lstrip('$')
            self.ticker_normalized = ticker
        return self


class ActionStep(BaseModel):
    """Single step in the action chain."""
    model_config = ConfigDict(strict=True)

    sequence: int = Field(
        1,
        ge=1,
        description="Order in execution chain (1 = first step)"
    )
    action_type: ActionType = Field(
        ...,
        description="Type of trading operation"
    )
    trigger_condition: Optional[str] = Field(
        None,
        description="Natural language or numeric condition (e.g., 'price < 480')"
    )
    trigger_type: TriggerType = Field(
        TriggerType.MANUAL,
        description="Category of trigger"
    )
    target_price_low: Optional[float] = Field(
        None,
        ge=0,
        description="Lower bound of target price range"
    )
    target_price_high: Optional[float] = Field(
        None,
        ge=0,
        description="Upper bound of target price range"
    )
    position_size_pct: Optional[float] = Field(
        None,
        gt=0,
        le=1,
        description="Suggested position size as fraction of portfolio (must be > 0)"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes for this step"
    )

    @model_validator(mode='after')
    def validate_price_range(self) -> ActionStep:
        """Ensure price range is valid."""
        if self.target_price_low is not None and self.target_price_high is not None:
            if self.target_price_low > self.target_price_high:
                raise ValueError(
                    f"target_price_low ({self.target_price_low}) cannot exceed "
                    f"target_price_high ({self.target_price_high})"
                )
        return self


class MarketEnrichment(BaseModel):
    """Market data enrichment fields."""
    model_config = ConfigDict(strict=True)

    market_price_at_time: Optional[float] = Field(
        None,
        ge=0,
        description="Price when action was generated"
    )
    volume_avg_20d: Optional[float] = Field(
        None,
        ge=0,
        description="20-day average volume"
    )
    volume_at_time: Optional[float] = Field(
        None,
        ge=0,
        description="Volume when action was generated"
    )
    relative_volume: Optional[float] = Field(
        None,
        ge=0,
        description="Volume relative to 20-day average"
    )
    high_52wk: Optional[float] = Field(
        None,
        ge=0,
        description="52-week high"
    )
    low_52wk: Optional[float] = Field(
        None,
        ge=0,
        description="52-week low"
    )
    pct_from_52wk_high: Optional[float] = Field(
        None,
        description="Percentage distance from 52-week high"
    )
    pct_from_52wk_low: Optional[float] = Field(
        None,
        description="Percentage distance from 52-week low"
    )
    implied_volatility: Optional[float] = Field(
        None,
        ge=0,
        description="Implied volatility (for options)"
    )
    pe_ratio: Optional[float] = Field(
        None,
        description="Price-to-earnings ratio"
    )
    market_cap: Optional[float] = Field(
        None,
        ge=0,
        description="Market capitalization"
    )

    # Data quality
    data_source: str = Field(
        "finance-skills",
        description="Service that provided market data"
    )
    data_timestamp: Optional[datetime] = Field(
        None,
        description="When market data was fetched"
    )
    is_stale: bool = Field(
        False,
        description="Whether data may be stale (>1 hour old)"
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Fields that could not be fetched"
    )


class RLHFFeedback(BaseModel):
    """Reinforcement Learning from Human Feedback fields."""
    model_config = ConfigDict(strict=True)

    rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Human rating (1-5 stars)"
    )
    is_correct: Optional[bool] = Field(
        None,
        description="Whether the action was correct/useful"
    )
    corrections: List[str] = Field(
        default_factory=list,
        description="List of corrections from reviewer"
    )
    corrected_direction: Optional[TradeDirection] = Field(
        None,
        description="Corrected direction if original was wrong"
    )
    corrected_ticker: Optional[str] = Field(
        None,
        description="Corrected ticker if original was wrong"
    )
    reviewer_id: Optional[str] = Field(
        None,
        description="ID of the human reviewer"
    )
    reviewed_at: Optional[datetime] = Field(
        None,
        description="Timestamp of review"
    )
    review_notes: Optional[str] = Field(
        None,
        description="Additional notes from reviewer"
    )

    @field_validator('reviewed_at', mode='before')
    @classmethod
    def set_reviewed_at_if_rated(cls, v: Optional[datetime], info: Any) -> Optional[datetime]:
        """Auto-set review timestamp if rating provided."""
        if v is None and info.data.get('rating') is not None:
            return datetime.now()
        return v


class BacktestResult(BaseModel):
    """Backtest performance results."""
    model_config = ConfigDict(strict=True)

    return_pct: Optional[float] = Field(
        None,
        description="Return percentage (positive = profit)"
    )
    holding_days: Optional[int] = Field(
        None,
        ge=0,
        description="Days the position was held"
    )
    exit_reason: ExitReason = Field(
        ExitReason.UNKNOWN,
        description="Why the position was exited"
    )
    exit_price: Optional[float] = Field(
        None,
        ge=0,
        description="Price at exit"
    )
    max_drawdown_pct: Optional[float] = Field(
        None,
        description="Maximum drawdown during hold period"
    )
    sharpe_ratio: Optional[float] = Field(
        None,
        description="Sharpe ratio for this trade"
    )
    win_rate_context: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Win rate for similar trades in historical data"
    )
    backtest_timestamp: Optional[datetime] = Field(
        None,
        description="When backtest was performed"
    )
    backtest_period: Optional[str] = Field(
        None,
        description="Backtest period (e.g., '2023-01-01 to 2023-12-31')"
    )


# =============================================================================
# Main TradeAction Model
# =============================================================================

class TradeAction(BaseModel):
    """
    Standardized trade action output for Finer pipeline.

    This schema captures the complete lifecycle of a trade action from
    extraction through validation, enrichment, backtesting, and human feedback.

    Core Fields:
        - trade_action_id: Unique identifier for this action
        - timestamp: ISO 8601 timestamp (critical for backtesting)
        - source: Attribution to original content
        - target: Asset information with normalized ticker
        - direction: Overall sentiment/direction
        - action_chain: Ordered sequence of operations

    Enrichment Fields:
        - enrichment: Market data at time of action
        - confidence: Model confidence score

    Validation Fields:
        - validation_status: Lifecycle status
        - backtest_result: Historical performance

    Learning Fields:
        - rlhf_feedback: Human feedback for model improvement
    """
    model_config = ConfigDict(
        strict=True,
        # Enable serialization of datetime as ISO 8601
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )

    # =========================================================================
    # Core Fields (Required)
    # =========================================================================

    trade_action_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this trade action"
    )

    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="ISO 8601 timestamp when action was generated (critical for backtest)"
    )

    source: SourceInfo = Field(
        ...,
        description="Source attribution information"
    )

    target: TargetInfo = Field(
        ...,
        description="Target asset information"
    )

    direction: TradeDirection = Field(
        ...,
        description="Overall trading direction/sentiment"
    )

    action_chain: List[ActionStep] = Field(
        default_factory=lambda: [ActionStep(sequence=1, action_type=ActionType.WATCH)],
        description="Ordered sequence of trading operations"
    )

    # =========================================================================
    # Upstream Trace (F3 → F4 → F5 canonical chain)
    # =========================================================================

    intent_id: Optional[str] = Field(
        None,
        description="Reference to F3 NormalizedInvestmentIntent.intent_id. "
                    "Canonical TradeActions MUST have this set. "
                    "Null indicates legacy/direct-extraction actions that bypassed F3."
    )

    policy_id: Optional[str] = Field(
        None,
        description="Reference to F4 PolicyMappingResult.policy_id. "
                    "Canonical TradeActions MUST have this set. "
                    "Null indicates legacy actions that bypassed F4."
    )

    evidence_span_ids: List[str] = Field(
        default_factory=list,
        description="Reference to F2 EvidenceSpan.evidence_span_id entries. "
                    "Canonical TradeActions SHOULD have at least one evidence span. "
                    "Empty list indicates no evidence traceability."
    )

    effective_trade_at: Optional[datetime] = Field(
        None,
        description="When the trade should take effect for backtesting purposes. "
                    "Distinct from timestamp (when the action was generated). "
                    "Set from F2 TemporalAnchor (anchor_type='effective_trade'). "
                    "Required for F8 backtesting."
    )

    canonical_trace_status: str = Field(
        "non_canonical",
        description="Indicates whether the F3→F4→F5 trace chain is complete. "
                    "'canonical': intent_id + policy_id both present and non-empty. "
                    "'partial': at least one upstream ID present but not both. "
                    "'non_canonical': no upstream IDs (legacy direct-extraction path)."
    )

    # =========================================================================
    # Confidence & Model Metadata
    # =========================================================================

    confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in this extraction (0-1)"
    )

    model_version: str = Field(
        "v1.0",
        description="Version of the model that generated this action"
    )

    extraction_method: str = Field(
        "llm",
        description="Method used for extraction (llm, rule_based, hybrid)"
    )

    # =========================================================================
    # Enrichment Fields
    # =========================================================================

    enrichment: Optional[MarketEnrichment] = Field(
        None,
        description="Market data enrichment at time of action"
    )

    # =========================================================================
    # Validation & Quality Assurance
    # =========================================================================

    validation_status: ValidationStatus = Field(
        ValidationStatus.PENDING,
        description="Current validation lifecycle status"
    )

    validation_issues: List[str] = Field(
        default_factory=list,
        description="Critical validation issues found"
    )

    validation_warnings: List[str] = Field(
        default_factory=list,
        description="Non-critical warnings"
    )

    requires_manual_review: bool = Field(
        False,
        description="Flag for manual review queue"
    )

    # =========================================================================
    # Backtest Results
    # =========================================================================

    backtest_result: Optional[BacktestResult] = Field(
        None,
        description="Backtest performance results"
    )

    # =========================================================================
    # RLHF Feedback
    # =========================================================================

    rlhf_feedback: Optional[RLHFFeedback] = Field(
        None,
        description="Human feedback for model improvement"
    )

    # =========================================================================
    # Additional Context
    # =========================================================================

    time_horizon: Optional[str] = Field(
        None,
        description="Expected holding period (e.g., '1 week', 'long term')"
    )

    rationale: Optional[str] = Field(
        None,
        description="Model's reasoning for this action"
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Free-form tags for categorization"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (extensible)"
    )

    # =========================================================================
    # Lineage & Version Control
    # =========================================================================

    lineage: Optional[DataLineage] = Field(
        None,
        description="Data lineage tracking from source to output"
    )

    version_info: Optional[VersionInfo] = Field(
        None,
        description="Version control information for reproducibility"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator('timestamp', mode='before')
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        """Parse timestamp from various formats."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # ISO 8601 parsing
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                # Try other common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(v, fmt)
                    except ValueError:
                        continue
        raise ValueError(f"Cannot parse timestamp: {v}")

    @model_validator(mode='after')
    def validate_canonical_trace(self) -> TradeAction:
        """Auto-set canonical_trace_status based on upstream ID presence."""
        has_intent = bool(self.intent_id)
        has_policy = bool(self.policy_id)

        if has_intent and has_policy:
            self.canonical_trace_status = "canonical"
        elif has_intent or has_policy:
            self.canonical_trace_status = "partial"
        else:
            self.canonical_trace_status = "non_canonical"
        return self

    @model_validator(mode='after')
    def validate_action_chain_sequence(self) -> TradeAction:
        """Ensure action chain sequences are consecutive starting from 1."""
        if not self.action_chain:
            return self

        sequences = [step.sequence for step in self.action_chain]
        expected = list(range(1, len(self.action_chain) + 1))

        if sorted(sequences) != expected:
            raise ValueError(
                f"Action chain sequences must be consecutive from 1, got: {sequences}"
            )
        return self

    @model_validator(mode='after')
    def auto_flag_for_review(self) -> TradeAction:
        """Auto-flag for manual review if issues exist."""
        if self.validation_issues and not self.requires_manual_review:
            self.requires_manual_review = True
        return self

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary with ISO 8601 timestamps.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return self.model_dump(mode='json')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TradeAction:
        """
        Create TradeAction from dictionary.

        Args:
            data: Dictionary with trade action data.

        Returns:
            TradeAction instance.
        """
        return cls.model_validate(data)

    def normalize_ticker(self) -> str:
        """
        Get normalized ticker symbol.

        Returns:
            Normalized ticker (uppercase, stripped).
        """
        if self.target.ticker_normalized:
            return self.target.ticker_normalized

        # Apply normalization rules
        ticker = self.target.ticker.strip().upper()
        ticker = ticker.lstrip('$')  # Remove cashtag prefix

        # Use unified entity registry
        from finer.entity_registry import normalize_ticker
        return normalize_ticker(ticker)

    def get_primary_action(self) -> Optional[ActionStep]:
        """
        Get the primary (first) action in the chain.

        Returns:
            First ActionStep or None if chain is empty.
        """
        return self.action_chain[0] if self.action_chain else None

    def is_actionable(self) -> bool:
        """
        Check if this action is ready for execution.

        Returns:
            True if validated and not requiring review.
        """
        return (
            self.validation_status == ValidationStatus.VERIFIED
            and not self.requires_manual_review
            and self.confidence >= 0.5
        )

    def get_market_context(self) -> Optional[str]:
        """
        Get human-readable market context summary.

        Returns:
            Summary string or None if no enrichment data.
        """
        if not self.enrichment:
            return None

        parts = []
        if self.enrichment.market_price_at_time:
            parts.append(f"Price: ${self.enrichment.market_price_at_time:.2f}")
        if self.enrichment.relative_volume:
            parts.append(f"Rel. Volume: {self.enrichment.relative_volume:.2f}x")
        if self.enrichment.pct_from_52wk_high:
            parts.append(f"{self.enrichment.pct_from_52wk_high:.1f}% from 52wk high")

        return " | ".join(parts) if parts else None

    def get_source_content_id(self) -> Optional[str]:
        """
        Get the original source content ID from lineage.

        Returns:
            Original content ID if lineage exists, None otherwise.
        """
        if self.lineage:
            return self.lineage.original_content_id
        return None

    def get_extraction_config_hash(self) -> Optional[str]:
        """
        Get the extraction config hash from version info.

        Returns:
            Config hash if version info exists, None otherwise.
        """
        if self.version_info:
            return self.version_info.extraction_config_hash
        return None

    def needs_reprocessing(self, current_prompt_version: str = "2.0") -> bool:
        """
        Check if this action needs re-processing due to version changes.

        Args:
            current_prompt_version: Current prompt version to compare against.

        Returns:
            True if re-processing is recommended.
        """
        if not self.version_info:
            return True  # No version info, assume needs reprocessing

        # Prompt version changed
        if self.version_info.prompt_version and self.version_info.prompt_version != current_prompt_version:
            return True

        # Schema version incompatibility (major version mismatch)
        if self.version_info.schema_version:
            try:
                existing_major = int(self.version_info.schema_version.split('.')[0])
                current_major = 1  # Current schema version is 1.0
                if existing_major != current_major:
                    return True
            except (ValueError, AttributeError):
                pass

        return False

    def to_backtest_record(self) -> Dict[str, Any]:
        """
        Export minimal record for backtest engine.

        Returns:
            Dictionary with only backtest-relevant fields.
        """
        return {
            'trade_action_id': self.trade_action_id,
            'timestamp': self.timestamp.isoformat(),
            'ticker': self.normalize_ticker(),
            'direction': self.direction.value,
            'action_chain': [
                {
                    'sequence': step.sequence,
                    'action_type': step.action_type.value,
                    'trigger_condition': step.trigger_condition,
                }
                for step in self.action_chain
            ],
            'confidence': self.confidence,
            'time_horizon': self.time_horizon,
        }


# =============================================================================
# Container Models
# =============================================================================

class TradeActionBatch(BaseModel):
    """Container for multiple trade actions from a single extraction."""
    model_config = ConfigDict(strict=True)

    actions: List[TradeAction] = Field(
        default_factory=list,
        description="List of extracted trade actions"
    )

    content_id: Optional[str] = Field(
        None,
        description="Source content ID for all actions"
    )

    extraction_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When extraction was performed"
    )

    model_version: str = Field(
        "v1.0",
        description="Model version used for extraction"
    )

    # Statistics
    total_actions: int = Field(
        0,
        description="Total number of actions"
    )
    bullish_count: int = Field(0)
    bearish_count: int = Field(0)
    neutral_count: int = Field(0)

    @model_validator(mode='after')
    def compute_stats(self) -> TradeActionBatch:
        """Auto-compute statistics."""
        self.total_actions = len(self.actions)
        self.bullish_count = sum(
            1 for a in self.actions if a.direction == TradeDirection.BULLISH
        )
        self.bearish_count = sum(
            1 for a in self.actions if a.direction == TradeDirection.BEARISH
        )
        self.neutral_count = sum(
            1 for a in self.actions if a.direction == TradeDirection.NEUTRAL
        )
        return self
