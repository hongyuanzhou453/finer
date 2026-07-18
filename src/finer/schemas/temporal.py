"""Temporal Anchor Schema — Time reference extraction for financial content.

This module defines temporal anchor schemas for capturing time references
in content. Temporal anchors support four types of time references critical
for investment decision-making.

Time Reference Types:
1. published_at: When the content was published
2. mentioned_at: When an event was mentioned/referenced
3. resolved_at: When a vague time reference resolves to a specific date
4. effective_trade_at: When a trade action becomes effective

Schema Version: v0.5
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Temporal Anchor Types
# =============================================================================

TEMPORAL_ANCHOR_TYPE_LITERAL = Literal[
    "published_at",
    "mentioned_at",
    "resolved_at",
    "effective_trade_at",
]

RESOLUTION_STRATEGY_LITERAL = Literal[
    "explicit_date",
    "relative_date",
    "fiscal_period",
    "market_hours",
    "llm_inference",
    "rule_based",
    "unknown",
]


# =============================================================================
# Temporal Anchor Model
# =============================================================================

class TemporalAnchor(BaseModel):
    """Time reference extracted from content.

    TemporalAnchor captures time references found in content, with support
    for resolution strategies and confidence scoring.

    Attributes:
        schema_version: Schema version for backward compatibility.
        anchor_id: Unique identifier for this temporal anchor.
        anchor_type: Type of time reference (published_at, mentioned_at, etc.).
        raw_text: Original text containing the time reference.
        resolved_time: ISO 8601 datetime after resolution.
        confidence: Confidence score for the resolution (0.0-1.0).
        resolution_strategy: Method used to resolve the time reference.
        evidence_span_id: Link to the evidence span for traceability.
        timezone: Timezone of the resolved time (e.g., 'UTC', 'Asia/Shanghai').
        metadata: Additional extensible metadata.

    Example:
        >>> anchor = TemporalAnchor(
        ...     anchor_id="time_abc123",
        ...     anchor_type="effective_trade_at",
        ...     raw_text="下周一开盘",
        ...     resolved_time=datetime(2024, 1, 22, 9, 30),
        ...     confidence=0.85,
        ...     resolution_strategy="rule_based",
        ...     evidence_span_id="span_xyz",
        ...     timezone="Asia/Shanghai",
        ... )
    """
    # datetime fields already serialize to ISO 8601 by default in Pydantic V2;
    # no json_encoders needed (json_encoders is deprecated and removed in V3).
    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Schema Version
    # =========================================================================

    schema_version: str = Field(
        default="v0.5",
        description="Schema version for backward compatibility"
    )

    # =========================================================================
    # Core Fields (Required)
    # =========================================================================

    anchor_id: str = Field(
        default_factory=lambda: f"time_{uuid4().hex[:12]}",
        description="Unique identifier for this temporal anchor"
    )

    anchor_type: TEMPORAL_ANCHOR_TYPE_LITERAL = Field(
        ...,
        description="Type of time reference"
    )

    raw_text: str = Field(
        ...,
        description="Original text containing the time reference"
    )

    resolved_time: Optional[datetime] = Field(
        None,
        description="ISO 8601 datetime after resolution"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for the resolution (0.0-1.0)"
    )

    resolution_strategy: RESOLUTION_STRATEGY_LITERAL = Field(
        ...,
        description="Method used to resolve the time reference"
    )

    # =========================================================================
    # Optional Fields
    # =========================================================================

    evidence_span_id: Optional[str] = Field(
        None,
        description="Link to the evidence span for traceability"
    )

    timezone: Optional[str] = Field(
        None,
        description="Timezone of the resolved time (e.g., 'UTC', 'Asia/Shanghai')"
    )

    # =========================================================================
    # Metadata
    # =========================================================================

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator('timezone', mode='before')
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        """Validate timezone format."""
        if v is None:
            return v

        # Basic timezone validation (allow common formats)
        valid_prefixes = ('UTC', 'GMT', 'Asia/', 'America/', 'Europe/', 'Pacific/')
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            # Allow any non-empty string for flexibility
            pass
        return v

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary with ISO 8601 timestamps.

        Returns:
            Dictionary representation.
        """
        return self.model_dump(mode='json')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TemporalAnchor:
        """
        Create TemporalAnchor from dictionary.

        Args:
            data: Dictionary with temporal anchor data.

        Returns:
            TemporalAnchor instance.
        """
        # Handle datetime string conversion
        if isinstance(data.get("resolved_time"), str):
            data["resolved_time"] = datetime.fromisoformat(data["resolved_time"].replace("Z", "+00:00"))
        return cls.model_validate(data)

    @classmethod
    def create_published_at(
        cls,
        raw_text: str,
        resolved_time: datetime,
        confidence: float = 1.0,
        evidence_span_id: Optional[str] = None,
    ) -> TemporalAnchor:
        """
        Create a published_at temporal anchor.

        Args:
            raw_text: Original text.
            resolved_time: Resolved datetime.
            confidence: Confidence score.
            evidence_span_id: Evidence span link.

        Returns:
            TemporalAnchor with published_at type.
        """
        return cls(
            anchor_type="published_at",
            raw_text=raw_text,
            resolved_time=resolved_time,
            confidence=confidence,
            resolution_strategy="explicit_date",
            evidence_span_id=evidence_span_id,
        )

    @classmethod
    def create_mentioned_at(
        cls,
        raw_text: str,
        resolved_time: Optional[datetime],
        confidence: float,
        resolution_strategy: RESOLUTION_STRATEGY_LITERAL,
        evidence_span_id: Optional[str] = None,
    ) -> TemporalAnchor:
        """
        Create a mentioned_at temporal anchor.

        Args:
            raw_text: Original text.
            resolved_time: Resolved datetime (may be None for vague references).
            confidence: Confidence score.
            resolution_strategy: Method used for resolution.
            evidence_span_id: Evidence span link.

        Returns:
            TemporalAnchor with mentioned_at type.
        """
        return cls(
            anchor_type="mentioned_at",
            raw_text=raw_text,
            resolved_time=resolved_time,
            confidence=confidence,
            resolution_strategy=resolution_strategy,
            evidence_span_id=evidence_span_id,
        )

    @classmethod
    def create_effective_trade_at(
        cls,
        raw_text: str,
        resolved_time: Optional[datetime],
        confidence: float,
        resolution_strategy: RESOLUTION_STRATEGY_LITERAL,
        evidence_span_id: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> TemporalAnchor:
        """
        Create an effective_trade_at temporal anchor.

        Args:
            raw_text: Original text.
            resolved_time: Resolved datetime.
            confidence: Confidence score.
            resolution_strategy: Method used for resolution.
            evidence_span_id: Evidence span link.
            timezone: Timezone for the trade time.

        Returns:
            TemporalAnchor with effective_trade_at type.
        """
        return cls(
            anchor_type="effective_trade_at",
            raw_text=raw_text,
            resolved_time=resolved_time,
            confidence=confidence,
            resolution_strategy=resolution_strategy,
            evidence_span_id=evidence_span_id,
            timezone=timezone,
        )

    def is_resolved(self) -> bool:
        """
        Check if the temporal anchor has been resolved to a specific time.

        Returns:
            True if resolved_time is not None.
        """
        return self.resolved_time is not None

    def get_formatted_time(self, format_str: str = "%Y-%m-%d %H:%M:%S") -> Optional[str]:
        """
        Get formatted time string.

        Args:
            format_str: strftime format string.

        Returns:
            Formatted time string or None if not resolved.
        """
        if self.resolved_time is None:
            return None
        return self.resolved_time.strftime(format_str)
