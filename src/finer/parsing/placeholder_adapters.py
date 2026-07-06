"""Placeholder adapters for unsupported source types.

These adapters return failure envelopes with clear error messages.
They are NOT production implementations -- just stubs for type coverage.

Source types without a canonical F1 adapter:
- livestream_audio (audio/video transcription)
- wechat_article (WeChat public account articles)
- weibo_post (Weibo social media)
- twitter_post (Twitter/X)
- rss_feed (RSS/Atom feeds)
- podcast_episode (podcast transcripts)
- research_report (third-party research PDFs)
- news_article (web news scraping)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.quality import QualityCard

logger = logging.getLogger(__name__)

_PLACEHOLDER_VERSION = "0.0.1"


def create_unsupported_envelope(
    f0_record: ContentRecord,
    raw_path: Path,
    source_type: str,
    reason: str,
) -> ContentEnvelope:
    """Create a failure envelope for unsupported source types.

    Args:
        f0_record: The F0 ContentRecord that triggered this call.
        raw_path: Path to the raw file.
        source_type: The unsupported source type identifier.
        reason: Human-readable explanation of why standardization is not supported.

    Returns:
        A ContentEnvelope with a single ocr_unreadable failure block,
        quality scores at 0.0, and standardization_profile="placeholder".
    """
    block = ContentBlock(
        block_type="ocr_unreadable",
        text=f"[Unsupported: {reason}]",
        order_index=0,
        quality=BlockQuality(
            readability=0.0,
            extraction_confidence=0.0,
            structural_confidence=0.0,
            completeness=0.0,
            noise_score=0.0,
            quality_flags=["unsupported_source_type"],
        ),
        provenance=BlockProvenance(
            raw_path=str(raw_path),
            extractor="placeholder_adapter",
            extractor_version=_PLACEHOLDER_VERSION,
        ),
    )

    published_at = f0_record.published_at
    if isinstance(published_at, str):
        published_at = datetime.fromisoformat(published_at)

    return ContentEnvelope(
        source_record_id=f0_record.content_id,
        schema_version="v1.0",
        source_type=source_type,
        standardization_profile="placeholder",
        source_title=raw_path.name,
        raw_path=str(raw_path),
        creator_id=f0_record.creator_id,
        creator_name=f0_record.creator_name,
        published_at=published_at,
        ingested_at=datetime.now(),
        blocks=[block],
        quality_card=QualityCard.create_default(overall=0.0),
    )
