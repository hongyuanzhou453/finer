"""Topic Block Schema — F1.5 Topic Assembly sub-stage.

This module defines the canonical data structures for assembling multi-topic
content (long chats, documents, audio transcripts) into semantically coherent
TopicBlocks between F1 (Standardize) and F2 (Anchor).

Key Design Principles:
1. TopicBlock groups contiguous ContentBlocks around a single topic
2. TopicAssemblyResult captures the full assembly output for one envelope
3. Strict validation ensures data integrity across the pipeline
4. No investment intent or trade action generation (F3/F5 responsibility)

Schema Version: v1.0
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


# =============================================================================
# Topic Type Enum
# =============================================================================

class TopicType(str, Enum):
    """Classification of topic content within a TopicBlock."""

    SINGLE_STOCK = "single_stock"
    INDUSTRY = "industry"
    MACRO_POLICY = "macro_policy"
    MARKET_COMMENTARY = "market_commentary"
    INVESTMENT_PHILOSOPHY = "investment_philosophy"
    PORTFOLIO_UPDATE = "portfolio_update"
    NEWS_FORWARD = "news_forward"
    OTHER = "other"


# For backward compatibility with Literal-style type hints
TOPIC_TYPE_LITERAL = Literal[
    "single_stock",
    "industry",
    "macro_policy",
    "market_commentary",
    "investment_philosophy",
    "portfolio_update",
    "news_forward",
    "other",
]


# =============================================================================
# Topic Block Model
# =============================================================================

class TopicBlock(BaseModel):
    """A semantically coherent grouping of ContentBlocks around a single topic.

    TopicBlock is the output of F1.5 topic assembly. It references source
    ContentBlocks via block IDs and provides topic-level metadata including
    classification, entity associations, and a summary.

    Attributes:
        topic_block_id: Unique identifier for this topic block.
        envelope_id: ID of the parent ContentEnvelope.
        source_block_ids: Ordered list of ContentBlock IDs in this topic.
        topic_title: Human-readable title for the topic.
        topic_type: Classification of the topic.
        primary_entity_ids: IDs of directly discussed entities.
        secondary_entity_ids: IDs of tangentially mentioned entities.
        start_block_index: Index of the first source block in envelope order.
        end_block_index: Index of the last source block in envelope order.
        start_time: Earliest temporal reference in this topic.
        end_time: Latest temporal reference in this topic.
        summary: Concise summary of the topic content.
        raw_text: Concatenated text from all source blocks.
        segmentation_reason: Explanation of why this grouping was formed.
        confidence: Model confidence in this segmentation (0.0-1.0).
        ambiguity_flags: Flags indicating ambiguous or uncertain aspects.
    """

    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Core Identification
    # =========================================================================

    topic_block_id: str = Field(
        default_factory=lambda: f"tb_{uuid4().hex[:12]}",
        description="Unique identifier for this topic block"
    )

    envelope_id: str = Field(
        ...,
        description="ID of the parent ContentEnvelope this block belongs to"
    )

    source_block_ids: List[str] = Field(
        ...,
        description="Ordered list of ContentBlock.block_id references in this topic"
    )

    # =========================================================================
    # Topic Classification
    # =========================================================================

    topic_title: str = Field(
        ...,
        description="Human-readable title summarizing the topic"
    )

    topic_type: TOPIC_TYPE_LITERAL = Field(
        ...,
        description="Classification of the topic (single_stock, industry, etc.)"
    )

    # =========================================================================
    # Entity Associations
    # =========================================================================

    primary_entity_ids: List[str] = Field(
        default_factory=list,
        description="IDs of entities directly discussed in this topic"
    )

    secondary_entity_ids: List[str] = Field(
        default_factory=list,
        description="IDs of entities tangentially mentioned in this topic"
    )

    # =========================================================================
    # Positional / Temporal Span
    # =========================================================================

    start_block_index: int = Field(
        ...,
        ge=0,
        description="Index of the first source block in envelope block order"
    )

    end_block_index: int = Field(
        ...,
        ge=0,
        description="Index of the last source block in envelope block order"
    )

    start_time: Optional[datetime] = Field(
        None,
        description="Earliest temporal reference within this topic"
    )

    end_time: Optional[datetime] = Field(
        None,
        description="Latest temporal reference within this topic"
    )

    # =========================================================================
    # Content & Provenance
    # =========================================================================

    summary: str = Field(
        default="",
        description="Concise summary of the topic content"
    )

    raw_text: str = Field(
        ...,
        description="Concatenated text from all source blocks (not fabricated)"
    )

    segmentation_reason: str = Field(
        default="",
        description="Explanation of why this topic grouping was formed"
    )

    # =========================================================================
    # Quality Signals
    # =========================================================================

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in this topic segmentation (0.0-1.0)"
    )

    ambiguity_flags: List[str] = Field(
        default_factory=list,
        description="Flags indicating ambiguous or uncertain aspects of this topic"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @model_validator(mode="after")
    def validate_source_block_ids_not_empty(self) -> TopicBlock:
        """Ensure at least one source block is referenced."""
        if not self.source_block_ids:
            raise ValueError("source_block_ids must not be empty")
        return self

    @model_validator(mode="after")
    def validate_block_index_range(self) -> TopicBlock:
        """Ensure end_block_index >= start_block_index."""
        if self.end_block_index < self.start_block_index:
            raise ValueError(
                f"end_block_index ({self.end_block_index}) must be >= "
                f"start_block_index ({self.start_block_index})"
            )
        return self

    @model_validator(mode="after")
    def validate_time_range(self) -> TopicBlock:
        """Ensure end_time is not before start_time when both are present."""
        if self.start_time is not None and self.end_time is not None:
            if self.end_time < self.start_time:
                raise ValueError(
                    f"end_time ({self.end_time}) must not be before "
                    f"start_time ({self.start_time})"
                )
        return self

    @model_validator(mode="after")
    def validate_raw_text_not_empty(self) -> TopicBlock:
        """Ensure raw_text is not empty — text must come from source blocks."""
        if not self.raw_text:
            raise ValueError("raw_text must not be empty")
        return self


# =============================================================================
# Topic Assembly Result Model
# =============================================================================

class TopicAssemblyResult(BaseModel):
    """Complete output of F1.5 topic assembly for one ContentEnvelope.

    TopicAssemblyResult captures all TopicBlocks produced from a single
    envelope, along with blocks that could not be assigned and metadata
    about the assembly process.

    Attributes:
        assembly_id: Unique identifier for this assembly run.
        envelope_id: ID of the ContentEnvelope being assembled.
        topic_blocks: Ordered list of TopicBlocks produced.
        unassigned_block_ids: Block IDs that could not be assigned to any topic.
        assembly_strategy: Description of the assembly algorithm used.
        created_at: Timestamp when this assembly was produced.
    """

    model_config = ConfigDict(strict=True)

    assembly_id: str = Field(
        default_factory=lambda: f"asm_{uuid4().hex[:12]}",
        description="Unique identifier for this assembly run"
    )

    envelope_id: str = Field(
        ...,
        description="ID of the ContentEnvelope this assembly operates on"
    )

    topic_blocks: List[TopicBlock] = Field(
        default_factory=list,
        description="Ordered list of TopicBlocks produced by assembly"
    )

    unassigned_block_ids: List[str] = Field(
        default_factory=list,
        description="Block IDs that could not be assigned to any topic"
    )

    assembly_strategy: str = Field(
        default="",
        description="Description of the assembly algorithm or strategy used"
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when this assembly result was produced"
    )
