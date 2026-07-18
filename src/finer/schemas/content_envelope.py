"""Content Envelope Schema — F1 canonical content standardization layer.

This module defines the canonical data structure for content normalization
across all data sources (image, chat, feishu_doc, pdf, audio/video transcripts).

Key Design Principles:
1. ContentEnvelope is the top-level container for all content types
2. ContentBlock represents granular content units (paragraphs, tables, etc.)
3. BlockQuality measures standardization reliability (F1), not investment relevance (F2)
4. BlockProvenance traces each block back to the F0 source
5. BoundingBox captures spatial layout for image/PDF blocks

Schema Version: v1.0 (F1 canonical)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from finer.schemas.quality import QualityCard
from finer.schemas.temporal import TemporalAnchor
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan


# =============================================================================
# F1 Canonical Supporting Models
# =============================================================================


class BoundingBox(BaseModel):
    """Spatial bounding box for image/PDF content regions.

    Coordinates are in pixel units: (x0, y0) is top-left, (x1, y1) is bottom-right.
    """

    model_config = ConfigDict(strict=True)

    x0: float = Field(..., ge=0, description="Left edge (pixels)")
    y0: float = Field(..., ge=0, description="Top edge (pixels)")
    x1: float = Field(..., ge=0, description="Right edge (pixels)")
    y1: float = Field(..., ge=0, description="Bottom edge (pixels)")

    @model_validator(mode="after")
    def validate_geometry(self) -> "BoundingBox":
        if self.x1 < self.x0:
            raise ValueError(f"x1 ({self.x1}) must be >= x0 ({self.x0})")
        if self.y1 < self.y0:
            raise ValueError(f"y1 ({self.y1}) must be >= y0 ({self.y0})")
        return self


class BlockQuality(BaseModel):
    """F1 standardization quality for a single ContentBlock.

    Measures standardization reliability, NOT investment relevance.
    Investment relevance scoring belongs to F2 QualityCard.
    """

    model_config = ConfigDict(strict=True)

    readability: float = Field(
        ..., ge=0.0, le=1.0,
        description="Text readability: length, garbage ratio, repeated chars, residual HTML",
    )
    extraction_confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Parser/OCR/ASR confidence or fallback estimate",
    )
    structural_confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence that block boundary and block_type are correct",
    )
    completeness: float = Field(
        ..., ge=0.0, le=1.0,
        description="Whether content is missing, empty, truncated, or attachment-only",
    )
    noise_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Likelihood that block is platform/system/meta noise",
    )
    quality_flags: List[str] = Field(
        default_factory=list,
        description="Flag strings: html_cleaned, timestamp_parsed, speaker_missing, etc.",
    )


class BlockProvenance(BaseModel):
    """Audit trail tracing a ContentBlock back to its F0 source."""

    model_config = ConfigDict(strict=True)

    raw_path: Optional[str] = Field(
        None, description="Path to the F0 raw source file"
    )
    raw_offset_start: Optional[int] = Field(
        None, ge=0, description="Character offset start in raw source"
    )
    raw_offset_end: Optional[int] = Field(
        None, ge=0, description="Character offset end in raw source"
    )
    extractor: str = Field(
        ..., description="Extractor module name (e.g. feishu_chat_standardizer)"
    )
    extractor_version: str = Field(
        ..., description="Version string of the extractor"
    )
    model_name: Optional[str] = Field(
        None, description="LLM model name if LLM-assisted"
    )
    source_hash: Optional[str] = Field(
        None, description="Hash of raw source content for dedup"
    )


# =============================================================================
# F1 Canonical Type Literals
# =============================================================================

BLOCK_TYPE_LITERAL = Literal[
    # F1 canonical block types
    "chat_message",
    "paragraph",
    "section_title",
    "image_text",
    "table_region",
    "chart_region",
    "audio_segment",
    "video_segment",
    "quote",
    "link_reference",
    "attachment_ref",
    "ocr_unreadable",
    "system_event",
    # Deprecated V0 types (kept for backward compatibility)
    # "heading"      -> "section_title"
    # "list"         -> "paragraph" or "quote"
    # "table"        -> "table_region"
    # "chart"        -> "chart_region"
    # "image_region" -> "image_text" / "table_region" / "chart_region" / "ocr_unreadable"
    # "transcript_segment" -> "audio_segment" or "video_segment"
    # "unknown"      -> "system_event" or "paragraph"
    "heading",
    "list",
    "table",
    "chart",
    "image_region",
    "transcript_segment",
    "unknown",
]

SOURCE_TYPE_LITERAL = Literal[
    # F1 canonical source types
    "feishu_chat",
    "feishu_doc",
    "wechat_article",
    "image",
    "pdf",
    "audio_transcript",
    "video_transcript",
    "manual_text",
    # Deprecated source types (kept for backward compatibility)
    # "chat" -> "feishu_chat"
    # "text" -> "manual_text"
    "chat",
    "text",
]


# =============================================================================
# Backward Compatibility Helpers
# =============================================================================


def _get_overall_score(quality: Any) -> float:
    """Extract overall score from QualityCard or BlockQuality."""
    if hasattr(quality, "overall_score"):
        return quality.overall_score
    # BlockQuality: compute mean of dimension scores
    dims = [
        quality.readability,
        quality.extraction_confidence,
        quality.structural_confidence,
        quality.completeness,
        1.0 - quality.noise_score,  # invert noise for quality contribution
    ]
    return sum(dims) / len(dims)


def _quality_card_to_block_quality(qc: Any) -> BlockQuality:
    """Convert a legacy QualityCard to F1 BlockQuality for backward compatibility.

    Maps QualityCard dimension scores to BlockQuality fields:
    - readability_score -> readability
    - semantic_completeness_score -> completeness
    - financial_relevance_score -> (not mapped, set to extraction_confidence default)
    - evidence_traceability_score -> structural_confidence
    - noise_score defaults to 0.0 (QualityCard has no noise dimension)
    """
    return BlockQuality(
        readability=getattr(qc, "readability_score", 0.5),
        extraction_confidence=getattr(qc, "financial_relevance_score", 0.5),
        structural_confidence=getattr(qc, "evidence_traceability_score", 0.5),
        completeness=getattr(qc, "semantic_completeness_score", 0.5),
        noise_score=0.0,
        quality_flags=[],
    )


# =============================================================================
# Content Block Model
# =============================================================================

class ContentBlock(BaseModel):
    """Granular content unit within a ContentEnvelope.

    ContentBlock represents a semantically meaningful unit of content,
    such as a paragraph, table, or chat message. Each block has its own
    quality assessment (BlockQuality), provenance trace, and evidence spans.
    """

    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Core Fields (Required per F1 Contract)
    # =========================================================================

    block_id: str = Field(
        default_factory=lambda: f"block_{uuid4().hex[:12]}",
        description="Unique identifier for this content block",
    )

    envelope_id: Optional[str] = Field(
        None,
        description="Parent envelope ID. Populated by ContentEnvelope on construction.",
    )

    block_type: BLOCK_TYPE_LITERAL = Field(
        ...,
        description="F1 canonical block type (chat_message, paragraph, section_title, etc.)",
    )

    text: str = Field(
        ...,
        description="Textual content of the block",
    )

    order_index: int = Field(
        ...,
        ge=0,
        description="Position in the content sequence (0-indexed). Canonical field.",
    )

    # =========================================================================
    # Optional Structural Fields
    # =========================================================================

    speaker: Optional[str] = Field(
        None,
        description="Speaker identifier for chat/transcript content",
    )

    timestamp: Optional[datetime] = Field(
        None,
        description="Block-level timestamp (e.g. chat message time)",
    )

    page_index: Optional[int] = Field(
        None,
        ge=0,
        description="Page number for paginated sources (PDFs)",
    )

    bbox: Optional[BoundingBox] = Field(
        None,
        description="Bounding box for spatial content (image/PDF layout)",
    )

    start_time_sec: Optional[float] = Field(
        None,
        ge=0,
        description="Start time in seconds for audio/video transcripts",
    )

    end_time_sec: Optional[float] = Field(
        None,
        ge=0,
        description="End time in seconds for audio/video transcripts",
    )

    parent_block_id: Optional[str] = Field(
        None,
        description="Parent block ID for nested structures (tables, lists)",
    )

    thread_id: Optional[str] = Field(
        None,
        description="Thread/conversation ID for chat messages",
    )

    # =========================================================================
    # F1 Quality and Provenance (Required per F1 Contract)
    # =========================================================================

    quality: Union[BlockQuality, QualityCard] = Field(
        ...,
        description="F1 standardization quality (BlockQuality) or legacy QualityCard",
    )

    provenance: Optional[BlockProvenance] = Field(
        None,
        description="Audit trail tracing this block to its F0 source",
    )

    evidence_spans: List[Any] = Field(
        default_factory=list,
        description="Traceable text spans within this block (EvidenceSpan from F2)",
    )

    # =========================================================================
    # Metadata
    # =========================================================================

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata",
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @model_validator(mode="before")
    @classmethod
    def _backward_compat_aliases(cls, data: Any) -> Any:
        """Map legacy field names to canonical fields."""
        if isinstance(data, dict):
            # order -> order_index
            if "order" in data and "order_index" not in data:
                data["order_index"] = data.pop("order")
            elif "order" in data and "order_index" in data:
                data.pop("order")

            # quality_card -> quality (only if quality not already set)
            if "quality_card" in data and "quality" not in data:
                data["quality"] = data.pop("quality_card")
            elif "quality_card" in data and "quality" in data:
                data.pop("quality_card")

            # bbox list -> BoundingBox
            if "bbox" in data and isinstance(data["bbox"], (list, tuple)):
                coords = data["bbox"]
                if len(coords) == 4:
                    data["bbox"] = BoundingBox(
                        x0=coords[0], y0=coords[1], x1=coords[2], y1=coords[3]
                    )
        return data

    @property
    def order(self) -> int:
        """Backward-compatible accessor: block.order returns order_index."""
        return self.order_index

    @order.setter
    def order(self, value: int) -> None:
        """Backward-compatible setter: block.order = x sets order_index."""
        self.order_index = value

    @property
    def quality_card(self) -> Any:
        """Backward-compatible accessor: block.quality_card returns quality."""
        return self.quality

    @model_validator(mode="after")
    def validate_time_range(self) -> "ContentBlock":
        """Ensure time range is valid for transcript blocks."""
        if self.start_time_sec is not None and self.end_time_sec is not None:
            if self.start_time_sec > self.end_time_sec:
                raise ValueError(
                    f"start_time_sec ({self.start_time_sec}) cannot exceed "
                    f"end_time_sec ({self.end_time_sec})"
                )
        return self


# =============================================================================
# Content Envelope Model
# =============================================================================

class ContentEnvelope(BaseModel):
    """Top-level container for F1-standardized content.

    ContentEnvelope is the unified data structure for all content types
    in the Finer pipeline. It normalizes diverse sources (images, PDFs,
    chat logs, transcripts) into a consistent, queryable format.
    """

    # datetime already serializes to ISO 8601 by default in Pydantic V2;
    # json_encoders is deprecated (removed in V3), so it is omitted here.
    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Core Fields (Required per F1 Contract)
    # =========================================================================

    envelope_id: str = Field(
        default_factory=lambda: f"env_{uuid4().hex[:12]}",
        description="Unique identifier for this content envelope",
    )

    source_record_id: Optional[str] = Field(
        None,
        description="F0 ContentRecord.content_id that produced this envelope",
    )

    schema_version: str = Field(
        default="v0.5",
        description="Schema version for compatibility tracking",
    )

    source_type: SOURCE_TYPE_LITERAL = Field(
        ...,
        description="F1 canonical source type (feishu_chat, image, pdf, etc.)",
    )

    standardization_profile: Optional[str] = Field(
        None,
        description="Standardizer profile used (e.g. feishu_chat_v1, image_ocr_v1)",
    )

    # =========================================================================
    # Source Metadata
    # =========================================================================

    source_uri: Optional[str] = Field(
        None,
        description="URI to original source content",
    )

    source_title: Optional[str] = Field(
        None,
        description="Title or filename of source content",
    )

    title: Optional[str] = Field(
        None,
        description="Alias for source_title",
    )

    raw_path: Optional[str] = Field(
        None,
        description="Path to the F0 raw file",
    )

    # =========================================================================
    # Creator Fields
    # =========================================================================

    creator_id: Optional[str] = Field(
        None,
        description="Unique identifier of content creator",
    )

    creator_name: Optional[str] = Field(
        None,
        description="Display name of content creator",
    )

    # =========================================================================
    # Temporal Fields
    # =========================================================================

    published_at: Optional[datetime] = Field(
        None,
        description="Original publication timestamp",
    )

    collected_at: Optional[datetime] = Field(
        None,
        description="Timestamp when content was collected/ingested at F0",
    )

    ingested_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when content was ingested",
    )

    # =========================================================================
    # Content Blocks
    # =========================================================================

    blocks: List[ContentBlock] = Field(
        default_factory=list,
        description="Ordered list of content blocks",
    )

    # =========================================================================
    # Quality
    # =========================================================================

    quality_card: QualityCard = Field(
        ...,
        description="Overall quality assessment for this envelope (F2-level QualityCard)",
    )

    # =========================================================================
    # Extraction Hooks (Backward Compatibility)
    # These are populated by downstream stages (F2), not F1.
    # Kept on the envelope for backward compatibility with existing code.
    # =========================================================================

    temporal_anchors: List[Any] = Field(
        default_factory=list,
        description="Extracted time references (populated by F2)",
    )

    entity_anchors: List[Any] = Field(
        default_factory=list,
        description="Extracted entity references (populated by F2)",
    )

    # =========================================================================
    # Metadata
    # =========================================================================

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata",
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @model_validator(mode="before")
    @classmethod
    def _resolve_title_alias(cls, data: Any) -> Any:
        """Map 'title' to 'source_title' and parse datetime strings."""
        if isinstance(data, dict):
            if "title" in data and "source_title" not in data:
                data["source_title"] = data.pop("title")
            elif "title" in data and "source_title" in data:
                data.pop("title")

            # Parse datetime strings for strict mode compatibility
            for dt_field in ("published_at", "collected_at", "ingested_at"):
                val = data.get(dt_field)
                if isinstance(val, str):
                    try:
                        data[dt_field] = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except ValueError:
                        pass
        return data

    @model_validator(mode="after")
    def _populate_block_envelope_ids(self) -> "ContentEnvelope":
        """Set envelope_id on all child blocks."""
        for block in self.blocks:
            if block.envelope_id is None:
                object.__setattr__(block, "envelope_id", self.envelope_id)
        return self

    @model_validator(mode="after")
    def validate_block_order(self) -> "ContentEnvelope":
        """Ensure block order_index values are sequential starting from 0."""
        if not self.blocks:
            return self

        orders = [block.order_index for block in self.blocks]
        expected = list(range(len(self.blocks)))

        if sorted(orders) != expected:
            raise ValueError(
                f"Block order_index values must be sequential from 0, got: {orders}"
            )
        return self

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ISO 8601 timestamps."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentEnvelope":
        """Create ContentEnvelope from dictionary."""
        # Handle datetime string conversion
        if isinstance(data.get("published_at"), str):
            data["published_at"] = datetime.fromisoformat(data["published_at"].replace("Z", "+00:00"))
        if isinstance(data.get("ingested_at"), str):
            data["ingested_at"] = datetime.fromisoformat(data["ingested_at"].replace("Z", "+00:00"))
        if isinstance(data.get("collected_at"), str):
            data["collected_at"] = datetime.fromisoformat(data["collected_at"].replace("Z", "+00:00"))

        # Handle temporal_anchors datetime conversion
        for anchor in data.get("temporal_anchors", []):
            if isinstance(anchor, dict) and isinstance(anchor.get("resolved_time"), str):
                anchor["resolved_time"] = datetime.fromisoformat(anchor["resolved_time"].replace("Z", "+00:00"))

        return cls.model_validate(data)

    def get_block_by_id(self, block_id: str) -> Optional[ContentBlock]:
        """Retrieve a block by its ID."""
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        return None

    def get_blocks_by_type(self, block_type: BLOCK_TYPE_LITERAL) -> List[ContentBlock]:
        """Filter blocks by type."""
        return [b for b in self.blocks if b.block_type == block_type]

    def get_text_content(self) -> str:
        """Get concatenated text from all blocks."""
        return "\n\n".join(block.text for block in self.blocks if block.text)

    def get_entity_by_symbol(self, symbol: str) -> Optional[Any]:
        """Find an entity anchor by its resolved symbol."""
        for anchor in self.entity_anchors:
            if hasattr(anchor, "resolved_symbol") and anchor.resolved_symbol and anchor.resolved_symbol.upper() == symbol.upper():
                return anchor
        return None

    def get_temporal_anchors_by_type(
        self,
        anchor_type: Literal["published_at", "mentioned_at", "resolved_at", "effective_trade_at"],
    ) -> List[Any]:
        """Filter temporal anchors by type."""
        return [a for a in self.temporal_anchors if hasattr(a, "anchor_type") and a.anchor_type == anchor_type]

    def compute_overall_quality(self) -> float:
        """Compute overall quality score from block quality.

        Works with both QualityCard (has overall_score) and BlockQuality
        (computes mean of dimension scores).
        """
        if not self.blocks:
            return _get_overall_score(self.quality_card)

        block_scores = [_get_overall_score(b.quality_card) for b in self.blocks]
        return sum(block_scores) / len(block_scores)

    def get_blocks_requiring_review(self) -> List[ContentBlock]:
        """Get blocks with gate_status 'review' or 'reject'.

        Works with both QualityCard (has gate_status) and BlockQuality (no gate_status).
        Blocks with BlockQuality that lack gate_status are excluded.
        """
        result = []
        for b in self.blocks:
            q = b.quality_card
            if hasattr(q, "gate_status") and q.gate_status in ("review", "reject"):
                result.append(b)
        return result

    # =========================================================================
    # F1 Canonical Validation
    # =========================================================================

    _LEGACY_SOURCE_TYPES: set[str] = {"chat", "text"}
    _LEGACY_BLOCK_TYPES: set[str] = {
        "heading", "list", "table", "chart",
        "image_region", "transcript_segment", "unknown",
    }

    def validate_canonical_f1(self) -> List[str]:
        """Strict canonical validation for F1 output.

        Returns a list of violation strings. Empty list means canonical PASS.
        Does NOT raise — callers inspect the list and decide how to handle.

        Checks:
        1. source_type must not be a legacy value (chat, text)
        2. block_type must not be a legacy value (heading, list, table, chart, etc.)
        3. Each block.quality must be BlockQuality, not QualityCard
        4. Each block.provenance must exist
        5. order_index must be sequential from 0
        6. Each block.envelope_id must equal self.envelope_id
        7. temporal_anchors and entity_anchors must be empty
        8. standardization_profile must be set
        9. source_record_id must be set (F0 -> F1 audit chain)
        10. blocks must not be empty
        11. schema_version must be "v1.0"
        9. source_record_id must be set (F0 -> F1 audit chain)
        10. blocks must not be empty (adapter failure must not pass silently)
        11. schema_version must be "v1.0" (canonical schema version)
        """
        violations: List[str] = []

        # 11. schema_version must be canonical
        if self.schema_version != "v1.0":
            violations.append(
                f"schema_version is '{self.schema_version}'; "
                f"canonical F1 output requires 'v1.0'"
            )

        # 1. Legacy source_type
        if self.source_type in self._LEGACY_SOURCE_TYPES:
            violations.append(
                f"source_type is legacy '{self.source_type}'; "
                f"canonical requires 'feishu_chat' or 'manual_text'"
            )

        # 9. source_record_id required (F0 -> F1 audit chain)
        if not self.source_record_id:
            violations.append(
                "source_record_id is required for canonical F1 output "
                "(F0 -> F1 audit chain)"
            )

        # 7. Extraction hooks must be empty at F1
        if self.temporal_anchors:
            violations.append(
                f"temporal_anchors must be empty at F1 output "
                f"(got {len(self.temporal_anchors)}); populated by F2"
            )
        if self.entity_anchors:
            violations.append(
                f"entity_anchors must be empty at F1 output "
                f"(got {len(self.entity_anchors)}); populated by F2"
            )

        # 8. standardization_profile required
        if not self.standardization_profile:
            violations.append("standardization_profile is required for canonical F1 output")

        # 10. blocks must not be empty
        if not self.blocks:
            violations.append(
                "blocks must not be empty; "
                "adapter failure or unreadable input must emit at least one "
                "system_event or ocr_unreadable block with provenance"
            )

        # Block-level checks
        orders: List[int] = []
        for i, block in enumerate(self.blocks):
            prefix = f"block[{i}] (block_id={block.block_id!r})"

            # 2. Legacy block_type
            if block.block_type in self._LEGACY_BLOCK_TYPES:
                violations.append(
                    f"{prefix}.block_type is legacy '{block.block_type}'"
                )

            # 3. quality must be BlockQuality
            if not isinstance(block.quality, BlockQuality):
                violations.append(
                    f"{prefix}.quality is {type(block.quality).__name__}, "
                    f"canonical requires BlockQuality"
                )

            # 4. provenance required
            if block.provenance is None:
                violations.append(f"{prefix}.provenance is required")

            # 6. envelope_id must match
            if block.envelope_id != self.envelope_id:
                violations.append(
                    f"{prefix}.envelope_id={block.envelope_id!r} "
                    f"!= envelope.envelope_id={self.envelope_id!r}"
                )

            orders.append(block.order_index)

        # 5. order_index sequential from 0
        if self.blocks:
            expected = list(range(len(self.blocks)))
            if sorted(orders) != expected:
                violations.append(
                    f"order_index must be sequential from 0; "
                    f"got {orders}, expected {expected}"
                )

        return violations
