"""Content Standardizer — Minimal V0 Processor.

This module provides text standardization functions for converting
markdown sources and plain text into ContentEnvelope format.

Design Principles:
1. No LLM calls — pure rule-based parsing
2. Preserve block order for traceability
3. Generate evidence spans for each block
4. Create default quality cards
5. Preserve creator_id, creator_name, published_at, source_type

Supported Block Types:
- heading: Lines starting with # (H1-H6)
- list: Lines starting with -, *, +, or numbered (1., 2., etc.)
- paragraph: Regular text blocks
- table: Placeholder for table detection (future)
- chart: Placeholder for chart detection (future)

Schema Version: v0.5
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Literal, Optional
from uuid import uuid4

from finer.schemas.content_envelope import (
    ContentEnvelope,
    ContentBlock,
    BLOCK_TYPE_LITERAL,
    SOURCE_TYPE_LITERAL,
)
from finer.schemas.quality import QualityCard
from finer.schemas.evidence import EvidenceSpan


# =============================================================================
# Block Detection Patterns
# =============================================================================

# Heading pattern: # ## ### etc.
HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$')

# List item patterns: -, *, +, 1., 2., etc.
UNORDERED_LIST_PATTERN = re.compile(r'^[\-\*\+]\s+(.+)$')
ORDERED_LIST_PATTERN = re.compile(r'^\d+\.\s+(.+)$')

# Table placeholder: lines containing | as column separators, or +--/+= style table borders
# Excludes standalone --- (markdown horizontal rule) and --- with spaces
TABLE_PATTERN = re.compile(r'^\s*\|.+\|\s*$')
TABLE_BORDER_PATTERN = re.compile(r'^[\s\|+\-=]*(?:\||\+)[\s\|+\-=]*$')
# Markdown horizontal rule or section separator (---, ***, ___)
SECTION_SEPARATOR_PATTERN = re.compile(r'^[\-\*\_]{3,}\s*$')

# Chart/image placeholder: [图表], [chart], (图), etc.
CHART_PLACEHOLDER_PATTERN = re.compile(
    r'\[(?:图表|chart|图|图片|image)\]|\（(?:图|图表)\）',
    re.IGNORECASE
)

# =============================================================================
# Placeholder Patterns for Image Strategy
# =============================================================================

PLACEHOLDER_PATTERNS = {
    "table_region": re.compile(r'\[TABLE_REGION\]|\[表格区域\]'),
    "chart_region": re.compile(r'\[CHART_REGION\]|\[图表区域\]'),
    "image_region": re.compile(r'\[IMAGE_REGION\]|\[图片区域\]'),
    "ocr_unreadable": re.compile(r'\[OCR_UNREADABLE\]|\[无法识别\]'),
}


# =============================================================================
# Helper Functions
# =============================================================================

def _detect_block_type(text: str) -> BLOCK_TYPE_LITERAL:
    """Detect block type from text content.

    Args:
        text: Text content to analyze.

    Returns:
        Detected block type.
    """
    text = text.strip()

    if not text:
        return "unknown"

    # Check for placeholder types first (highest priority)
    for placeholder_type, pattern in PLACEHOLDER_PATTERNS.items():
        if pattern.search(text):
            return placeholder_type  # type: ignore

    # Check for heading (must be at start of text)
    first_line = text.split('\n')[0].strip()
    if HEADING_PATTERN.match(first_line):
        return "heading"

    # Check for list item (check first line or any line for multi-line blocks)
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if UNORDERED_LIST_PATTERN.match(line) or ORDERED_LIST_PATTERN.match(line):
            return "list"

    # Check for section separator first (skip these)
    for line in lines:
        line_stripped = line.strip()
        if SECTION_SEPARATOR_PATTERN.match(line_stripped) and len(line_stripped) >= 3:
            if not TABLE_BORDER_PATTERN.match(line_stripped):
                # This is a markdown hr like --- or ***, not a table border
                return "section_separator"

    # Check for table (must have | in content)
    for line in lines:
        if TABLE_PATTERN.match(line) or TABLE_BORDER_PATTERN.match(line):
            return "table"

    # Check for chart placeholder
    if CHART_PLACEHOLDER_PATTERN.search(text):
        return "chart"

    # Default to paragraph
    return "paragraph"


def _create_default_quality_card(block_type: BLOCK_TYPE_LITERAL) -> QualityCard:
    """Create default quality card based on block type.

    Args:
        block_type: Type of content block.

    Returns:
        QualityCard with default scores.
    """
    # Base scores for all block types
    base_scores = {
        "readability": 0.7,
        "semantic_completeness": 0.6,
        "financial_relevance": 0.5,
        "entity_resolution": 0.4,
        "temporal_resolution": 0.4,
        "evidence_traceability": 0.8,  # High because we preserve original text
    }

    # Adjust scores based on block type
    if block_type == "heading":
        base_scores["semantic_completeness"] = 0.7
        base_scores["financial_relevance"] = 0.6
    elif block_type == "list":
        base_scores["readability"] = 0.8
        base_scores["semantic_completeness"] = 0.7
    elif block_type == "table":
        base_scores["readability"] = 0.6
        base_scores["semantic_completeness"] = 0.8
        base_scores["financial_relevance"] = 0.7
    elif block_type == "chart":
        base_scores["readability"] = 0.5
        base_scores["financial_relevance"] = 0.8
    # Placeholder types for image strategy
    elif block_type == "table_region":
        base_scores["readability"] = 0.5
        base_scores["financial_relevance"] = 0.7
    elif block_type == "chart_region":
        base_scores["readability"] = 0.4
        base_scores["financial_relevance"] = 0.8
    elif block_type == "image_region":
        base_scores["readability"] = 0.3
        base_scores["financial_relevance"] = 0.5
    elif block_type == "ocr_unreadable":
        base_scores["readability"] = 0.1
        base_scores["financial_relevance"] = 0.3
    elif block_type == "unknown":
        # Lower scores for unknown content
        for key in base_scores:
            base_scores[key] = 0.3

    return QualityCard(
        readability_score=base_scores["readability"],
        semantic_completeness_score=base_scores["semantic_completeness"],
        financial_relevance_score=base_scores["financial_relevance"],
        entity_resolution_score=base_scores["entity_resolution"],
        temporal_resolution_score=base_scores["temporal_resolution"],
        evidence_traceability_score=base_scores["evidence_traceability"],
    )


def _create_evidence_span(
    block_id: str,
    text: str,
    confidence: float = 0.9,
    span_type: Optional[str] = None,
) -> EvidenceSpan:
    """Create evidence span for entire block text.

    Args:
        block_id: ID of the content block.
        text: Full text of the block.
        confidence: Confidence score.
        span_type: Type of evidence.

    Returns:
        EvidenceSpan covering entire block text.
    """
    # For empty text, create span with placeholder (char_end > char_start required)
    if not text:
        return EvidenceSpan(
            block_id=block_id,
            char_start=0,
            char_end=1,
            text="",
            confidence=confidence,
            span_type=span_type,
        )

    return EvidenceSpan(
        block_id=block_id,
        char_start=0,
        char_end=len(text),
        text=text,
        confidence=confidence,
        span_type=span_type,
    )


def _split_into_blocks(text: str) -> List[str]:
    """Split text into blocks (paragraphs and individual lines).

    Args:
        text: Full text content.

    Returns:
        List of text blocks.
    """
    # Split by double newlines first (paragraph boundaries)
    paragraphs = re.split(r'\n\s*\n', text.strip())

    blocks = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Skip section separators (---, *** markdown hr)
        if SECTION_SEPARATOR_PATTERN.match(para) and len(para) >= 3:
            if not TABLE_BORDER_PATTERN.match(para):
                continue

        # Split paragraph into lines
        lines = para.split('\n')

        # Group consecutive list items together
        current_group = []
        in_list = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip section separator lines
            if SECTION_SEPARATOR_PATTERN.match(line) and len(line) >= 3:
                if not TABLE_BORDER_PATTERN.match(line):
                    continue

            is_list = (
                UNORDERED_LIST_PATTERN.match(line) is not None or
                ORDERED_LIST_PATTERN.match(line) is not None
            )
            is_heading = HEADING_PATTERN.match(line) is not None

            # Headings are always separate blocks
            if is_heading:
                if current_group:
                    blocks.append('\n'.join(current_group))
                    current_group = []
                blocks.append(line)
                in_list = False
            # List items
            elif is_list:
                current_group.append(line)
                in_list = True
            # Regular text
            else:
                # If we were in a list, this ends the list block
                if in_list:
                    if current_group:
                        blocks.append('\n'.join(current_group))
                        current_group = []
                    in_list = False
                current_group.append(line)

        # Flush remaining group
        if current_group:
            blocks.append('\n'.join(current_group))

    return blocks


# =============================================================================
# Main Standardization Functions
# =============================================================================

def standardize_text_source(
    text: str,
    source_type: SOURCE_TYPE_LITERAL = "text",
    source_uri: Optional[str] = None,
    source_title: Optional[str] = None,
    creator_id: Optional[str] = None,
    creator_name: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> ContentEnvelope:
    """Standardize plain text into ContentEnvelope.

    Args:
        text: Plain text content to standardize.
        source_type: Type of source content.
        source_uri: URI to original source.
        source_title: Title of source content.
        creator_id: Unique identifier of content creator.
        creator_name: Display name of content creator.
        published_at: Original publication timestamp.

    Returns:
        ContentEnvelope with extracted blocks.

    Example:
        >>> envelope = standardize_text_source(
        ...     text="# 市场分析\\n\\n今日市场表现强劲...",
        ...     source_type="text",
        ...     creator_name="分析师A",
        ... )
        >>> len(envelope.blocks)
        2
    """
    # Split text into blocks
    text_blocks = _split_into_blocks(text)

    # Create ContentBlock for each text block
    content_blocks: List[ContentBlock] = []
    block_order = 0
    for block_text in text_blocks:
        block_type = _detect_block_type(block_text)

        # Skip section separators (markdown hr)
        if block_type == "section_separator":
            continue

        block_id = f"block_{uuid4().hex[:12]}"

        # Create quality card
        quality_card = _create_default_quality_card(block_type)

        # Create evidence span
        evidence_span = _create_evidence_span(
            block_id=block_id,
            text=block_text,
            confidence=0.9,
            span_type=block_type,
        )

        # Create ContentBlock
        content_block = ContentBlock(
            block_id=block_id,
            block_type=block_type,
            text=block_text,
            order=block_order,
            quality_card=quality_card,
            evidence_spans=[evidence_span],
        )
        content_blocks.append(content_block)
        block_order += 1

    # Create overall quality card
    overall_quality = QualityCard.create_default(overall=0.6)

    # Create ContentEnvelope
    envelope = ContentEnvelope(
        source_type=source_type,
        source_uri=source_uri,
        source_title=source_title,
        creator_id=creator_id,
        creator_name=creator_name,
        published_at=published_at,
        blocks=content_blocks,
        quality_card=overall_quality,
    )

    return envelope


def standardize_markdown_source(
    markdown: str,
    source_type: SOURCE_TYPE_LITERAL = "text",
    source_uri: Optional[str] = None,
    source_title: Optional[str] = None,
    creator_id: Optional[str] = None,
    creator_name: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> ContentEnvelope:
    """Standardize markdown text into ContentEnvelope.

    This function is similar to standardize_text_source but is intended
    for markdown-formatted content. It handles:
    - Headings (H1-H6)
    - Lists (ordered and unordered)
    - Tables (placeholder)
    - Code blocks (treated as paragraphs)
    - Images/charts (placeholder)

    Args:
        markdown: Markdown text content to standardize.
        source_type: Type of source content.
        source_uri: URI to original source.
        source_title: Title of source content.
        creator_id: Unique identifier of content creator.
        creator_name: Display name of content creator.
        published_at: Original publication timestamp.

    Returns:
        ContentEnvelope with extracted blocks.

    Example:
        >>> envelope = standardize_markdown_source(
        ...     markdown="## 策略分析\\n\\n- 看多\\n- 看空",
        ...     source_type="text",
        ... )
        >>> envelope.blocks[0].block_type
        'heading'
    """
    # Markdown is essentially text, so we reuse the text standardizer
    # The block type detection will identify markdown-specific structures
    return standardize_text_source(
        text=markdown,
        source_type=source_type,
        source_uri=source_uri,
        source_title=source_title,
        creator_id=creator_id,
        creator_name=creator_name,
        published_at=published_at,
    )


# =============================================================================
# Convenience Functions
# =============================================================================

def standardize_chat_transcript(
    transcript: str,
    creator_id: Optional[str] = None,
    creator_name: Optional[str] = None,
    published_at: Optional[datetime] = None,
    source_uri: Optional[str] = None,
) -> ContentEnvelope:
    """Standardize chat transcript into ContentEnvelope.

    Args:
        transcript: Chat transcript text.
        creator_id: Creator identifier.
        creator_name: Creator display name.
        published_at: Publication timestamp.
        source_uri: URI to source.

    Returns:
        ContentEnvelope with chat messages as blocks.
    """
    return standardize_text_source(
        text=transcript,
        source_type="chat",
        source_uri=source_uri,
        creator_id=creator_id,
        creator_name=creator_name,
        published_at=published_at,
    )


def standardize_audio_transcript(
    transcript: str,
    creator_id: Optional[str] = None,
    creator_name: Optional[str] = None,
    published_at: Optional[datetime] = None,
    source_uri: Optional[str] = None,
) -> ContentEnvelope:
    """Standardize audio transcript into ContentEnvelope.

    Args:
        transcript: Audio transcript text.
        creator_id: Creator identifier.
        creator_name: Creator display name.
        published_at: Publication timestamp.
        source_uri: URI to source.

    Returns:
        ContentEnvelope with transcript segments as blocks.
    """
    return standardize_text_source(
        text=transcript,
        source_type="audio_transcript",
        source_uri=source_uri,
        creator_id=creator_id,
        creator_name=creator_name,
        published_at=published_at,
    )


def standardize_image_strategy(
    text_content: str,
    creator_id: Optional[str] = None,
    creator_name: Optional[str] = None,
    published_at: Optional[datetime] = None,
    source_uri: Optional[str] = None,
) -> ContentEnvelope:
    """Standardize textified image strategy content into ContentEnvelope.

    Args:
        text_content: Text extracted from image (OCR).
        creator_id: Creator identifier.
        creator_name: Creator display name.
        published_at: Publication timestamp.
        source_uri: URI to source image.

    Returns:
        ContentEnvelope with image content as blocks.
    """
    return standardize_text_source(
        text=text_content,
        source_type="image",
        source_uri=source_uri,
        creator_id=creator_id,
        creator_name=creator_name,
        published_at=published_at,
    )
