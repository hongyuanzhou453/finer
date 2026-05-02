"""Manual Text Standardizer — F1 canonical adapter for plain text / markdown files.

Converts .txt and .md files into a canonical ContentEnvelope with
ordered ContentBlock[].  This is the fallback adapter for content types
that don't have a specialized F1 adapter (e.g., wechat articles, manual
uploads, generic markdown).

Canonical block types produced:
- section_title: markdown headings (# ... ######)
- paragraph: body text
- link_reference: text containing URLs
- system_event: noise (platform markers, etc.)
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.quality import QualityCard

logger = logging.getLogger(__name__)

_EXTRACTOR_VERSION = "1.0.0"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)")
_LINK_RE = re.compile(r"https?://\S+|www\.\S+")
_PLATFORM_NOISE_RE = re.compile(
    r"(?:来自|发送自|via)\s*(?:飞书|微信|钉钉|企业微信|telegram|whatsapp)",
    re.IGNORECASE,
)


class ManualTextStandardizer:
    """F1 canonical adapter: plain text / markdown → ContentEnvelope."""

    def standardize(
        self, f0_record: ContentRecord, raw_path: Path
    ) -> ContentEnvelope:
        """Full F1 standardization pipeline for text content."""
        try:
            text = raw_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = raw_path.read_text(encoding="utf-8", errors="replace")
            logger.warning("Encoding issues in %s, using replacement", raw_path.name)

        if not text.strip():
            blocks = [self._build_empty_block(raw_path)]
        else:
            blocks = self._extract_blocks(text, raw_path)
            if not blocks:
                blocks = [self._build_empty_block(raw_path)]

        # Assign sequential order_index
        for i, block in enumerate(blocks):
            block.order_index = i

        return self._build_envelope(f0_record, raw_path, blocks)

    # -----------------------------------------------------------------------
    # Block extraction
    # -----------------------------------------------------------------------

    def _extract_blocks(self, text: str, raw_path: Path) -> List[ContentBlock]:
        """Split text into blocks and classify each."""
        paragraphs = self._split_paragraphs(text)
        blocks: List[ContentBlock] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Noise check
            if _PLATFORM_NOISE_RE.search(para):
                blocks.append(self._build_noise_block(para, raw_path))
                continue

            block_type = self._classify(para)
            blocks.append(
                self._build_block(block_type, para, raw_path)
            )

        return blocks

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split on blank lines."""
        chunks = re.split(r"\n\s*\n", text)
        return [c.strip() for c in chunks if c.strip()]

    def _classify(self, text: str) -> str:
        """Determine block_type for a paragraph."""
        # Markdown heading
        if _HEADING_RE.match(text.split("\n")[0].strip()):
            return "section_title"

        # URL-containing short text
        if _LINK_RE.search(text) and len(text) < 300:
            return "link_reference"

        return "paragraph"

    # -----------------------------------------------------------------------
    # Block builders
    # -----------------------------------------------------------------------

    def _build_block(
        self, block_type: str, text: str, raw_path: Path
    ) -> ContentBlock:
        quality = self._score_quality(text, block_type)
        return ContentBlock(
            block_type=block_type,
            text=text,
            order_index=0,
            page_index=0,
            quality=quality,
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="manual_text_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
                source_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            ),
        )

    def _build_noise_block(self, text: str, raw_path: Path) -> ContentBlock:
        return ContentBlock(
            block_type="system_event",
            text=text,
            order_index=0,
            page_index=0,
            quality=BlockQuality(
                readability=0.6,
                extraction_confidence=0.8,
                structural_confidence=0.9,
                completeness=1.0,
                noise_score=0.9,
                quality_flags=["noise_detected"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="manual_text_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"noise_type": "platform_noise"},
        )

    def _build_empty_block(self, raw_path: Path) -> ContentBlock:
        return ContentBlock(
            block_type="ocr_unreadable",
            text="[No extractable text content]",
            order_index=0,
            page_index=0,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.5,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["empty_text"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="manual_text_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
        )

    # -----------------------------------------------------------------------
    # Quality scoring
    # -----------------------------------------------------------------------

    def _score_quality(self, text: str, block_type: str) -> BlockQuality:
        flags: List[str] = []
        text_len = len(text.strip())

        if text_len == 0:
            readability = 0.0
        elif text_len < 20:
            readability = 0.4
            flags.append("short_text")
        else:
            readability = min(1.0, 0.6 + text_len / 500.0)

        structural = {
            "section_title": 0.9,
            "system_event": 0.95,
            "link_reference": 0.8,
        }.get(block_type, 0.7)

        if text_len > 50:
            extraction = 0.85
        elif text_len > 20:
            extraction = 0.7
        elif text_len > 0:
            extraction = 0.5
        else:
            extraction = 0.0

        completeness = 1.0 if text_len > 10 else text_len / 10.0

        return BlockQuality(
            readability=readability,
            extraction_confidence=extraction,
            structural_confidence=structural,
            completeness=completeness,
            noise_score=0.1,
            quality_flags=flags,
        )

    # -----------------------------------------------------------------------
    # Envelope builder
    # -----------------------------------------------------------------------

    def _build_envelope(
        self,
        f0_record: ContentRecord,
        raw_path: Path,
        blocks: List[ContentBlock],
    ) -> ContentEnvelope:
        quality_card = self._compute_quality_card(blocks)

        published_at = f0_record.published_at
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)

        return ContentEnvelope(
            source_record_id=f0_record.content_id,
            schema_version="v1.0",
            source_type="manual_text",
            standardization_profile="manual_text_v1",
            source_uri=f0_record.source_path,
            source_title=raw_path.name,
            raw_path=str(raw_path),
            creator_name=f0_record.creator_name,
            published_at=published_at,
            ingested_at=datetime.now(),
            blocks=blocks,
            quality_card=quality_card,
        )

    def _compute_quality_card(self, blocks: List[ContentBlock]) -> QualityCard:
        if not blocks:
            return QualityCard.create_default(overall=0.0)

        n = len(blocks)
        avg_extraction = sum(b.quality.extraction_confidence for b in blocks) / n
        avg_readability = sum(b.quality.readability for b in blocks) / n
        avg_completeness = sum(b.quality.completeness for b in blocks) / n

        return QualityCard(
            readability_score=avg_readability,
            semantic_completeness_score=avg_completeness,
            financial_relevance_score=avg_extraction * 0.8,
            entity_resolution_score=0.0,
            temporal_resolution_score=0.0,
            evidence_traceability_score=avg_extraction,
        )
