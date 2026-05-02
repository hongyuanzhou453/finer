"""Image OCR/Layout Standardizer — F1 canonical adapter for image content.

Converts image OCR markdown or layout region data into a canonical
ContentEnvelope with ordered ContentBlock[].

Input paths:
1. OCR markdown: pre-extracted text from vision API (in f0_record metadata)
2. Layout regions: structured regions with bounding boxes (in f0_record metadata)
3. Vision API fallback: calls vision model when no pre-extracted data exists

Canonical block types produced:
- section_title: markdown headers, slide titles
- image_text: body text paragraphs
- table_region: table structures (markdown tables, layout table regions)
- chart_region: chart/graph references
- quote: quoted text blocks
- link_reference: URLs and link patterns
- ocr_unreadable: unreadable or low-confidence regions
- system_event: watermarks, page headers/footers, platform noise
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from finer.llm.client import LLMClient
from finer.model_config import get_vision_registry
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    BoundingBox,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.quality import QualityCard

logger = logging.getLogger(__name__)

# Version string for BlockProvenance.extractor_version
_EXTRACTOR_VERSION = "1.0.0"

# Markdown header pattern
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# Markdown table detection
_TABLE_SEPARATOR_RE = re.compile(r"^\|?[\s\-:|]+\|[\s\-:|]+\|?\s*$")
_TABLE_ROW_RE = re.compile(r"^\|.+\|\s*$")

# Link/URL pattern
_LINK_RE = re.compile(r"https?://\S+|www\.\S+")

# Noise / watermark patterns (Chinese + English)
_WATERMARK_PATTERNS = [
    re.compile(r"仅供.*内部.*(?:使用|交流|学习)", re.IGNORECASE),
    re.compile(r"(?:严禁|禁止).*(?:转载|传播|外传)", re.IGNORECASE),
    re.compile(r"(?:confidential|internal\s+use\s+only)", re.IGNORECASE),
    re.compile(r"(?:转发|截图).*(?:必究|追责|法律责任)", re.IGNORECASE),
]
_FOOTER_PATTERNS = [
    re.compile(r"第\s*\d+\s*页\s*/\s*共\s*\d+\s*页"),
    re.compile(r"page\s+\d+\s+(?:of|/)\s+\d+", re.IGNORECASE),
    re.compile(r"(?:免责声明|disclaimer)\s*[:：]", re.IGNORECASE),
]
_PLATFORM_NOISE_PATTERNS = [
    re.compile(r"(?:来自|发送自|via)\s*(?:飞书|微信|钉钉|企业微信|telegram|whatsapp)", re.IGNORECASE),
    re.compile(r"(?:扫码|长按).*(?:识别|关注|查看)", re.IGNORECASE),
]


class ImageOCRLayoutStandardizer:
    """F1 canonical adapter: image OCR/layout → ContentEnvelope.

    Supports three input paths in priority order:
    1. OCR markdown in f0_record.metadata['ocr_markdown']
    2. Layout regions in f0_record.metadata['layout_regions']
    3. Vision API fallback (calls LLM with image)
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client

    def standardize(self, f0_record: ContentRecord, raw_path: Path) -> ContentEnvelope:
        """Full F1 standardization pipeline for image content."""
        metadata = f0_record.metadata or {}
        ocr_markdown = metadata.get("ocr_markdown")
        layout_regions = metadata.get("layout_regions")

        # Step 1: Extract content via appropriate path.
        # Priority: layout regions (bbox-rich) > OCR markdown > vision API > fallback.
        # When both layout and OCR exist, prefer layout — it preserves spatial
        # evidence (bbox, region_role) that pure OCR chunking discards.
        if layout_regions:
            blocks = self._build_blocks_from_regions(layout_regions, raw_path)
            source_hash = self._hash_file(raw_path)
        elif ocr_markdown:
            blocks = self._chunk_ocr_markdown(ocr_markdown, raw_path)
            source_hash = self._hash_text(ocr_markdown)
        else:
            vision_text = self._extract_via_vision_api(raw_path)
            if vision_text:
                model_name = self._resolve_llm_model_name()
                blocks = self._chunk_ocr_markdown(vision_text, raw_path, model_name=model_name)
                source_hash = self._hash_text(vision_text)
            else:
                llm_error = getattr(self._llm, "last_error", None) if self._llm else "no_llm_client"
                blocks = self._build_fallback_blocks(f0_record, raw_path, llm_error=llm_error)
                source_hash = self._hash_file(raw_path)

        # Step 1b: Guard — if extraction produced no usable blocks, emit a
        # failure block so the envelope never passes silently as empty.
        if not blocks:
            blocks = [self._build_extraction_failure_block(f0_record, raw_path)]
            source_hash = self._hash_file(raw_path)

        # Step 2: Assign order_index
        for i, block in enumerate(blocks):
            block.order_index = i

        # Step 3: Build envelope
        envelope = self._build_envelope(f0_record, raw_path, blocks, source_hash)
        return envelope

    # -------------------------------------------------------------------------
    # Path 1: OCR markdown chunking
    # -------------------------------------------------------------------------

    def _chunk_ocr_markdown(
        self,
        ocr_text: str,
        raw_path: Path,
        model_name: Optional[str] = None,
    ) -> List[ContentBlock]:
        """Parse OCR markdown into structured ContentBlocks.

        Splits on markdown headers and blank lines, classifies each chunk,
        detects watermarks/noise, and handles table regions.
        """
        blocks: List[ContentBlock] = []
        chunks = self._split_into_chunks(ocr_text)

        for chunk_text, chunk_type_hint in chunks:
            if not chunk_text.strip():
                continue

            # Check for noise/watermark first
            noise_type = self._detect_noise_type(chunk_text)
            if noise_type:
                blocks.append(self._build_noise_block(noise_type, chunk_text, raw_path))
                continue

            # Classify block type
            block_type = self._classify_chunk(chunk_text, chunk_type_hint)

            # Check for table region
            if block_type == "image_text" and self._is_table_region(chunk_text):
                block_type = "table_region"

            blocks.append(
                self._build_block(
                    block_type=block_type,
                    text=chunk_text.strip(),
                    raw_path=raw_path,
                    source_hash=self._hash_text(chunk_text),
                    model_name=model_name,
                )
            )

        return blocks

    def _split_into_chunks(self, text: str) -> List[Tuple[str, str]]:
        """Split OCR text into (chunk_text, type_hint) tuples.

        Type hints: 'header', 'blank', 'body'.
        """
        lines = text.split("\n")
        chunks: List[Tuple[str, str]] = []
        current_lines: List[str] = []
        current_hint = "body"

        def flush():
            if current_lines:
                chunks.append(("\n".join(current_lines), current_hint))

        for line in lines:
            is_header = bool(_HEADER_RE.match(line.strip()))
            is_blank = not line.strip()

            if is_header:
                flush()
                current_lines = [line]
                current_hint = "header"
            elif is_blank:
                flush()
                current_lines = []
                current_hint = "body"
            else:
                if current_hint == "header" and current_lines:
                    # Header already collected, start new body chunk
                    flush()
                    current_hint = "body"
                current_lines.append(line)

        flush()
        return chunks

    def _classify_chunk(self, text: str, hint: str) -> str:
        """Determine canonical block_type for a text chunk."""
        if hint == "header":
            return "section_title"

        stripped = text.strip()

        if _LINK_RE.search(stripped) and len(stripped) < 300:
            return "link_reference"

        if stripped.startswith(">") or stripped.startswith('"') or stripped.startswith("“"):
            return "quote"

        return "image_text"

    def _is_table_region(self, text: str) -> bool:
        """Detect markdown table structure."""
        lines = text.strip().split("\n")
        table_rows = sum(1 for l in lines if _TABLE_ROW_RE.match(l.strip()))
        has_separator = any(_TABLE_SEPARATOR_RE.match(l.strip()) for l in lines)
        return table_rows >= 2 and has_separator

    # -------------------------------------------------------------------------
    # Path 2: Layout regions
    # -------------------------------------------------------------------------

    def _build_blocks_from_regions(
        self, regions: List[Dict[str, Any]], raw_path: Path
    ) -> List[ContentBlock]:
        """Build ContentBlocks from structured layout regions."""
        blocks: List[ContentBlock] = []

        for region in regions:
            text = region.get("text", "").strip()
            if not text:
                blocks.append(self._build_unreadable_region_block(region, raw_path))
                continue

            noise_type = self._detect_noise_type(text)
            if noise_type:
                blocks.append(self._build_noise_block(noise_type, text, raw_path))
                continue

            block_type = self._map_region_type(region.get("type", ""), text)
            bbox = self._extract_bbox(region)

            blocks.append(
                self._build_block(
                    block_type=block_type,
                    text=text,
                    raw_path=raw_path,
                    bbox=bbox,
                    source_hash=self._hash_text(text),
                    metadata={
                        "layout_available": True,
                        "region_role": region.get("role", ""),
                        "nested_source_type": region.get("nested_source_type", ""),
                    },
                )
            )

        return blocks

    _REGION_TYPE_MAP: Dict[str, str] = {
        "text": "image_text",
        "paragraph": "image_text",
        "title": "section_title",
        "heading": "section_title",
        "header": "section_title",
        "table": "table_region",
        "chart": "chart_region",
        "figure": "chart_region",
        "quote": "quote",
        "caption": "image_text",
        "footer": "system_event",
        "watermark": "system_event",
        "page_number": "system_event",
        "link": "link_reference",
        "url": "link_reference",
    }

    def _map_region_type(self, region_type: str, text: str) -> str:
        """Map layout region type to canonical block_type."""
        mapped = self._REGION_TYPE_MAP.get(region_type.lower())
        if mapped:
            return mapped

        if self._is_table_region(text):
            return "table_region"
        if _LINK_RE.search(text) and len(text) < 300:
            return "link_reference"
        return "image_text"

    def _extract_bbox(self, region: Dict[str, Any]) -> Optional[BoundingBox]:
        """Extract BoundingBox from layout region data."""
        bbox_data = region.get("bbox") or region.get("bounding_box") or region.get("coordinates")
        if not bbox_data:
            return None

        if isinstance(bbox_data, dict):
            return BoundingBox(
                x0=float(bbox_data.get("x0", bbox_data.get("left", 0))),
                y0=float(bbox_data.get("y0", bbox_data.get("top", 0))),
                x1=float(bbox_data.get("x1", bbox_data.get("right", 0))),
                y1=float(bbox_data.get("y1", bbox_data.get("bottom", 0))),
            )
        if isinstance(bbox_data, (list, tuple)) and len(bbox_data) == 4:
            return BoundingBox(
                x0=float(bbox_data[0]),
                y0=float(bbox_data[1]),
                x1=float(bbox_data[2]),
                y1=float(bbox_data[3]),
            )
        return None

    def _build_unreadable_region_block(
        self, region: Dict[str, Any], raw_path: Path
    ) -> ContentBlock:
        """Build ocr_unreadable block for regions with no text."""
        bbox = self._extract_bbox(region)
        return ContentBlock(
            block_type="ocr_unreadable",
            text="[unreadable region]",
            order_index=0,
            bbox=bbox,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.8,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["ocr_unreadable", "empty_region"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="image_ocr_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={
                "layout_available": True,
                "original_region_type": region.get("type", ""),
            },
        )

    # -------------------------------------------------------------------------
    # Path 3: Vision API fallback
    # -------------------------------------------------------------------------

    def _extract_via_vision_api(self, raw_path: Path) -> Optional[str]:
        """Call vision LLM to extract text from image."""
        if not raw_path.exists():
            logger.warning("Image file not found: %s", raw_path)
            return None

        try:
            if self._llm is None:
                registry = get_vision_registry()
                self._llm = LLMClient.from_registry(registry)

            # Read image and encode to base64
            image_bytes = raw_path.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            mime_type = mimetypes.guess_type(str(raw_path))[0] or "image/png"

            prompt = (
                "请精准提取这张图片中的所有文字信息，"
                "并严格按照原图的视觉排版结构，将其转化为逻辑连贯的Markdown格式返回。"
                "遇到图表，请尽可能提取表头结构和主要数据。"
                "只需返回Markdown本身，不要附加额外问候语。"
            )

            result = self._llm.chat_with_images(
                text=prompt,
                image_base64=image_b64,
                mime_type=mime_type,
            )

            if result and len(result.strip()) > 10:
                logger.info("Vision API extracted %d chars from %s", len(result), raw_path.name)
                return result

            logger.warning("Vision API returned insufficient text for %s", raw_path.name)
            return None

        except Exception:
            logger.warning("Vision API failed for %s", raw_path.name, exc_info=True)
            return None

    # -------------------------------------------------------------------------
    # Fallback: no OCR, no layout, no vision API
    # -------------------------------------------------------------------------

    def _build_fallback_blocks(
        self, f0_record: ContentRecord, raw_path: Path, llm_error: Optional[str] = None
    ) -> List[ContentBlock]:
        """Produce minimal blocks when no text extraction is possible.

        Does NOT fabricate content blocks (image_text, paragraph, etc.) for
        unreadable images — that would mask extraction failure.  Emits:
        - section_title: generated metadata title (low extraction_confidence)
        - ocr_unreadable: the actual failure signal
        """
        filename = raw_path.stem
        source_record_id = f0_record.content_id or "unknown"
        error_msg = llm_error or (
            f0_record.metadata.get("vision_transcript_error", "unknown") if f0_record.metadata else "unknown"
        )

        title_block = ContentBlock(
            block_type="section_title",
            text=f"Image: {filename}",
            order_index=0,
            quality=BlockQuality(
                readability=0.9,
                extraction_confidence=0.1,
                structural_confidence=0.7,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["fallback_generated"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="image_ocr_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"source": "fallback"},
        )

        error_block = ContentBlock(
            block_type="ocr_unreadable",
            text=f"[OCR extraction failed: no vision transcript available for {source_record_id}]",
            order_index=0,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.5,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["ocr_failed", "no_vision_transcript", "fallback_generated"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="image_ocr_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={
                "source": "fallback",
                "error": error_msg,
            },
        )

        return [title_block, error_block]

    def _build_extraction_failure_block(
        self, f0_record: ContentRecord, raw_path: Path
    ) -> ContentBlock:
        """Emit when extraction produced zero usable blocks (e.g. whitespace-only OCR).

        Ensures the envelope never passes canonical validation as empty — that
        would be a silent success for an extraction failure.
        """
        source_record_id = f0_record.content_id or "unknown"
        return ContentBlock(
            block_type="ocr_unreadable",
            text=f"[Extraction produced no usable blocks for {source_record_id}]",
            order_index=0,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.5,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["extraction_empty", "ocr_failed"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="image_ocr_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"source": "extraction_failure_guard"},
        )

    # -------------------------------------------------------------------------
    # Noise / watermark detection
    # -------------------------------------------------------------------------

    def _detect_noise_type(self, text: str) -> Optional[str]:
        """Classify text as noise type or None if content."""
        for pat in _WATERMARK_PATTERNS:
            if pat.search(text):
                return "watermark"
        for pat in _FOOTER_PATTERNS:
            if pat.search(text):
                return "page_footer"
        for pat in _PLATFORM_NOISE_PATTERNS:
            if pat.search(text):
                return "platform_noise"
        return None

    def _build_noise_block(
        self, noise_type: str, text: str, raw_path: Path
    ) -> ContentBlock:
        """Build a system_event block for noise/watermark content."""
        return ContentBlock(
            block_type="system_event",
            text=text.strip(),
            order_index=0,
            quality=BlockQuality(
                readability=0.6,
                extraction_confidence=0.8,
                structural_confidence=0.9,
                completeness=1.0,
                noise_score=0.9,
                quality_flags=["noise_detected", f"noise_{noise_type}"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="image_ocr_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"noise_type": noise_type},
        )

    # -------------------------------------------------------------------------
    # Block builder
    # -------------------------------------------------------------------------

    def _build_block(
        self,
        block_type: str,
        text: str,
        raw_path: Path,
        bbox: Optional[BoundingBox] = None,
        source_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
    ) -> ContentBlock:
        """Construct a ContentBlock with quality and provenance."""
        quality = self._score_block_quality(text, block_type)
        provenance = BlockProvenance(
            raw_path=str(raw_path),
            extractor="image_ocr_standardizer",
            extractor_version=_EXTRACTOR_VERSION,
            source_hash=source_hash,
            model_name=model_name,
        )

        return ContentBlock(
            block_type=block_type,
            text=text,
            order_index=0,
            bbox=bbox,
            quality=quality,
            provenance=provenance,
            metadata=metadata or {},
        )

    # -------------------------------------------------------------------------
    # Quality scoring
    # -------------------------------------------------------------------------

    def _score_block_quality(self, text: str, block_type: str) -> BlockQuality:
        """Deterministic quality scoring for image OCR blocks."""
        flags: List[str] = []

        # Readability: text length, garbage ratio
        text_len = len(text.strip())
        if text_len == 0:
            readability = 0.0
        elif text_len < 20:
            readability = 0.4
        else:
            readability = min(1.0, 0.6 + text_len / 500.0)

        garbage_chars = sum(
            1 for c in text if not c.isprintable() and c not in "\n\r\t"
        )
        garbage_ratio = garbage_chars / max(text_len, 1)
        if garbage_ratio > 0.1:
            readability *= 0.5
            flags.append("garbage_chars_detected")
        if garbage_ratio > 0.3:
            flags.append("high_garbage_ratio")

        # Structural confidence: header blocks are well-identified
        if block_type == "section_title":
            structural = 0.9
        elif block_type in ("table_region", "chart_region"):
            structural = 0.8
        elif block_type == "system_event":
            structural = 0.95
        else:
            structural = 0.7

        # Extraction confidence: heuristic based on text quality
        if text_len > 50 and garbage_ratio < 0.05:
            extraction = 0.85
        elif text_len > 20:
            extraction = 0.7
        elif text_len > 0:
            extraction = 0.5
            flags.append("short_text")
        else:
            extraction = 0.0
            flags.append("empty_text")

        # Completeness
        completeness = 1.0 if text_len > 10 else text_len / 10.0

        # Noise score
        noise = 0.1 if block_type != "system_event" else 0.8

        return BlockQuality(
            readability=readability,
            extraction_confidence=extraction,
            structural_confidence=structural,
            completeness=completeness,
            noise_score=noise,
            quality_flags=flags,
        )

    # -------------------------------------------------------------------------
    # Envelope builder
    # -------------------------------------------------------------------------

    def _build_envelope(
        self,
        f0_record: ContentRecord,
        raw_path: Path,
        blocks: List[ContentBlock],
        source_hash: Optional[str],
    ) -> ContentEnvelope:
        """Assemble the final ContentEnvelope."""
        # Compute quality card from block aggregates
        quality_card = self._compute_quality_card(blocks)

        # Collect noise/watermark metadata
        noise_tags = sorted({
            b.metadata.get("noise_type", "")
            for b in blocks
            if b.metadata.get("noise_type")
        })

        published_at = f0_record.published_at
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)

        envelope = ContentEnvelope(
            source_record_id=f0_record.content_id,
            schema_version="v1.0",
            source_type="image",
            standardization_profile="image_ocr_layout_v1",
            source_uri=f0_record.source_path,
            source_title=raw_path.name,
            raw_path=str(raw_path),
            creator_id=f0_record.metadata.get("creator_id") if f0_record.metadata else None,
            creator_name=f0_record.creator_name,
            published_at=published_at,
            ingested_at=datetime.now(),
            blocks=blocks,
            quality_card=quality_card,
            metadata={
                "source_hash": source_hash,
                "file_size_bytes": raw_path.stat().st_size if raw_path.exists() else 0,
                "noise_watermark": noise_tags if noise_tags else [],
            },
        )

        return envelope

    def _compute_quality_card(self, blocks: List[ContentBlock]) -> QualityCard:
        """Aggregate block quality into envelope-level QualityCard."""
        if not blocks:
            return QualityCard.create_default(overall=0.0)

        n = len(blocks)
        avg_extraction = sum(b.quality.extraction_confidence for b in blocks) / n
        avg_readability = sum(b.quality.readability for b in blocks) / n
        avg_completeness = sum(b.quality.completeness for b in blocks) / n
        avg_noise = sum(b.quality.noise_score for b in blocks) / n

        return QualityCard(
            readability_score=avg_readability,
            semantic_completeness_score=avg_completeness,
            financial_relevance_score=avg_extraction * 0.8,
            entity_resolution_score=0.0,
            temporal_resolution_score=0.0,
            evidence_traceability_score=avg_extraction,
        )

    # -------------------------------------------------------------------------
    # LLM model name resolution
    # -------------------------------------------------------------------------

    def _resolve_llm_model_name(self) -> Optional[str]:
        """Extract model name from the LLM client, checking public and private attrs."""
        if self._llm is None:
            return None
        # LLMClient stores model as _model; check public attr first for compat
        return getattr(self._llm, "model", None) or getattr(self._llm, "_model", None)

    # -------------------------------------------------------------------------
    # File hashing
    # -------------------------------------------------------------------------

    @staticmethod
    def _hash_file(path: Path) -> str:
        """SHA-256 hash of file contents."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _hash_text(text: str) -> str:
        """SHA-256 hash of text content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
