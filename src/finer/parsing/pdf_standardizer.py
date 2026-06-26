"""PDF Document Standardizer — F1 canonical adapter for PDF content.

Converts multi-page PDF documents into a canonical ContentEnvelope with
ordered ContentBlock[].  Each block carries page_index and, when layout
data is available, a BoundingBox.

Extraction strategy per page:
1. Text extraction via pdfplumber (primary)
2. Table extraction via pdfplumber table detection
3. Chart/image region detection via image/rect density heuristics
4. OCR fallback for scanned/image-heavy pages via vision API

Canonical block types produced:
- section_title: page titles, chapter headings
- paragraph: body text
- table_region: detected tables
- chart_region: chart/graph/image-heavy regions
- image_text: OCR text from image-heavy pages
- ocr_unreadable: pages that failed all extraction paths
- system_event: watermarks, page headers/footers, noise
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    BoundingBox,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.quality import QualityCard

from finer.parsing.layout_ocr_client import LayoutOCRClient

logger = logging.getLogger(__name__)

_EXTRACTOR_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Noise detection patterns (shared with image adapter)
# ---------------------------------------------------------------------------

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
    re.compile(
        r"(?:来自|发送自|via)\s*(?:飞书|微信|钉钉|企业微信|telegram|whatsapp)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:扫码|长按).*(?:识别|关注|查看)", re.IGNORECASE),
]

# Header-like patterns at the top of pages
_HEADER_PATTERNS = [
    re.compile(r"^Flywheel", re.IGNORECASE),
    re.compile(r"^配色应用指引"),
    re.compile(r"^(?:品牌色|边框|功能色)"),
]

# Link/URL pattern
_LINK_RE = re.compile(r"https?://\S+|www\.\S+")

# Thresholds
_MIN_TEXT_FOR_CONTENT = 30  # chars — below this, page is likely scanned/image
# CJK Radicals Supplement + Kangxi Radicals. A broken font CMap maps 汉字 to
# these radical glyphs (⼈ U+2F08 instead of 人 U+4EBA): the page has plenty of
# "text" but it is garbled and must fall back to image OCR.
_RADICAL_RE = re.compile(r"[⺀-⻿⼀-⿟]")
_CJK_RE = re.compile(r"[㐀-鿿⺀-⿟]")
_RADICAL_GARBLE_RATIO = 0.05
_IMAGE_DENSITY_THRESHOLD = 0.4  # fraction of page area covered by images

# Resolution for rendering a page to a raster before OCR. Layout OCR bboxes come
# back in this pixel space; we convert them to PDF points (×72/dpi) so OCR blocks
# share the coordinate system of the pdfplumber text-layer blocks.
_OCR_RENDER_DPI = 150

# Layout region type → canonical PDF block_type.
_LAYOUT_REGION_BLOCK_TYPE = {
    "table": "table_region",
    "title": "section_title",
    "text": "paragraph",
}


class PDFStandardizer:
    """F1 canonical adapter: PDF → ContentEnvelope.

    Processes each page individually, extracting text, tables, and
    chart/image regions.  Scanned pages fall back to OCR via vision API.
    """

    def __init__(self, llm_client=None):
        self._llm = llm_client
        self._layout_client: Optional[LayoutOCRClient] = None

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def standardize(
        self, f0_record: ContentRecord, raw_path: Path
    ) -> ContentEnvelope:
        """Full F1 standardization pipeline for PDF content."""
        import pdfplumber

        try:
            pdf = pdfplumber.open(str(raw_path))
        except Exception as exc:
            logger.warning("Failed to open PDF %s: %s", raw_path.name, type(exc).__name__)
            blocks = [self._build_unreadable_pdf_block(raw_path, f0_record, error_type=type(exc).__name__)]
            blocks[0].order_index = 0
            return self._build_envelope(f0_record, raw_path, blocks)

        try:
            blocks: List[ContentBlock] = []
            num_pages = len(pdf.pages)

            for page_idx, page in enumerate(pdf.pages):
                page_blocks = self._process_page(
                    page, page_idx, num_pages, raw_path
                )
                blocks.extend(page_blocks)

            # Guard: if no blocks extracted, emit failure block
            if not blocks:
                blocks = [self._build_extraction_failure_block(raw_path, f0_record)]

            # Assign sequential order_index
            for i, block in enumerate(blocks):
                block.order_index = i

            return self._build_envelope(f0_record, raw_path, blocks)
        finally:
            pdf.close()

    # -----------------------------------------------------------------------
    # Per-page processing
    # -----------------------------------------------------------------------

    def _process_page(
        self,
        page,
        page_idx: int,
        num_pages: int,
        raw_path: Path,
    ) -> List[ContentBlock]:
        """Extract blocks from a single PDF page."""
        blocks: List[ContentBlock] = []

        # 1. Detect noise/watermark in the full page text
        full_text = page.extract_text() or ""

        # 2. Extract tables first (they consume text regions)
        table_blocks, table_bboxes = self._extract_tables(page, page_idx, raw_path)
        blocks.extend(table_blocks)

        # 3. Extract text blocks (excluding table regions)
        text_blocks = self._extract_text_blocks(
            page, page_idx, raw_path, table_bboxes
        )
        blocks.extend(text_blocks)

        # 4. Detect chart/image regions on pages with heavy visual content
        chart_blocks = self._detect_chart_regions(page, page_idx, raw_path, full_text)
        blocks.extend(chart_blocks)

        # 5. OCR fallback for scanned pages OR CMap-corrupted text layers.
        # Garbled (radical-glyph) pages have a high char count but unusable text,
        # so route them to image OCR even when there is plenty of "text".
        text_garbled = self._is_radical_garbled(full_text)
        if (len(full_text.strip()) < _MIN_TEXT_FOR_CONTENT and not table_blocks) or text_garbled:
            ocr_blocks = self._ocr_fallback_page(page, page_idx, raw_path)
            if ocr_blocks:
                # Replace text blocks with OCR blocks for this page
                blocks = [b for b in blocks if b.page_index != page_idx]
                blocks.extend(ocr_blocks)
            else:
                # OCR attempted but failed — include error reason
                vision_error = self._get_vision_error_reason()
                unreadable = self._build_unreadable_page_block(
                    page_idx, raw_path, error_reason=vision_error
                )
                blocks.append(unreadable)

        # 6. If still no blocks for this page, emit ocr_unreadable
        page_blocks = [b for b in blocks if b.page_index == page_idx]
        if not page_blocks:
            blocks.append(
                self._build_unreadable_page_block(page_idx, raw_path)
            )

        # 7. Mark cover page metadata
        if page_idx == 0:
            for b in blocks:
                if b.page_index == page_idx:
                    b.metadata["cover_page"] = True

        return blocks

    def _is_radical_garbled(self, text: str) -> bool:
        """True if the text layer is CMap-corrupted (汉字 rendered as radicals).

        pdfplumber maps some embedded fonts' glyphs to Kangxi/CJK-radical
        codepoints, producing text like ⼈⼯ instead of 人工. Such a page has a
        high char count but is unusable; it must fall back to image OCR.
        """
        if not text:
            return False
        radicals = _RADICAL_RE.findall(text)
        if len(radicals) < 10:
            return False
        cjk = _CJK_RE.findall(text)
        return bool(cjk) and len(radicals) / len(cjk) > _RADICAL_GARBLE_RATIO

    # -----------------------------------------------------------------------
    # Text extraction
    # -----------------------------------------------------------------------

    def _extract_text_blocks(
        self,
        page,
        page_idx: int,
        raw_path: Path,
        table_bboxes: List[BoundingBox],
    ) -> List[ContentBlock]:
        """Extract text blocks from a page, skipping table regions."""
        full_text = page.extract_text() or ""
        if not full_text.strip():
            return []

        # Split page text into paragraphs
        paragraphs = self._split_paragraphs(full_text)
        blocks: List[ContentBlock] = []

        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue

            # Detect noise first (noise blocks are kept regardless of table overlap)
            noise_type = self._detect_noise_type(para_text)
            if noise_type:
                blocks.append(
                    self._build_noise_block(noise_type, para_text, page_idx, raw_path)
                )
                continue

            # Get bbox from page words — used for both table overlap check and block
            bbox = self._estimate_text_bbox(para_text, page)

            # Check if this paragraph overlaps with a table region
            # (skip if so — tables are handled separately)
            if table_bboxes and bbox and self._bbox_overlaps_table(bbox, table_bboxes):
                continue

            # Classify block type
            block_type = self._classify_text(para_text, page_idx)

            blocks.append(
                self._build_block(
                    block_type=block_type,
                    text=para_text,
                    page_idx=page_idx,
                    raw_path=raw_path,
                    bbox=bbox,
                    source_hash=self._hash_text(para_text),
                )
            )

        return blocks

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split page text into paragraphs by blank lines."""
        # Split on double newlines or more
        chunks = re.split(r"\n\s*\n", text)
        result: List[str] = []
        for chunk in chunks:
            stripped = chunk.strip()
            if stripped:
                result.append(stripped)
        return result if result else [text.strip()]

    def _classify_text(self, text: str, page_idx: int) -> str:
        """Determine block_type for a text paragraph."""
        lines = text.strip().split("\n")
        first_line = lines[0].strip() if lines else ""

        # URL-containing short text is a link reference
        if _LINK_RE.search(text.strip()) and len(text.strip()) < 300:
            return "link_reference"

        # Short single-line text is likely a title
        if len(lines) <= 2 and len(text.strip()) < 80:
            if not text.strip().endswith(("。", ".", "！", "!", "？", "?")):
                return "section_title"

        return "paragraph"

    # -----------------------------------------------------------------------
    # Table extraction
    # -----------------------------------------------------------------------

    def _extract_tables(
        self, page, page_idx: int, raw_path: Path
    ) -> Tuple[List[ContentBlock], List[BoundingBox]]:
        """Extract tables from a page using pdfplumber."""
        tables = page.extract_tables() or []
        blocks: List[ContentBlock] = []
        bboxes: List[BoundingBox] = []

        for table_data in tables:
            if not table_data or len(table_data) < 2:
                continue

            # Convert table to markdown-like text
            table_text = self._table_to_text(table_data)
            if not table_text.strip():
                continue

            # Get table bbox from pdfplumber
            bbox = self._get_table_bbox(page, table_data)
            if bbox:
                bboxes.append(bbox)

            blocks.append(
                self._build_block(
                    block_type="table_region",
                    text=table_text,
                    page_idx=page_idx,
                    raw_path=raw_path,
                    bbox=bbox,
                    source_hash=self._hash_text(table_text),
                    metadata={"row_count": len(table_data)},
                )
            )

        return blocks, bboxes

    def _table_to_text(self, table_data: List[List]) -> str:
        """Convert pdfplumber table data to markdown-like text."""
        rows: List[str] = []
        for row in table_data:
            cells = [str(c).strip() if c else "" for c in row]
            rows.append("| " + " | ".join(cells) + " |")
            # Add separator after first row
            if len(rows) == 1:
                rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
        return "\n".join(rows)

    def _get_table_bbox(self, page, table_data) -> Optional[BoundingBox]:
        """Get bounding box for a table on the page."""
        # pdfplumber's find_tables returns Table objects with bbox
        # But we receive raw data, so we try to find matching table
        try:
            tables_found = page.find_tables()
            for t in tables_found:
                if t.extract() == table_data:
                    x0, y0, x1, y1 = t.bbox
                    return BoundingBox(
                        x0=max(0.0, x0),
                        y0=max(0.0, y0),
                        x1=float(x1),
                        y1=float(y1),
                    )
        except Exception:
            pass
        return None

    def _bbox_overlaps_table(
        self, text_bbox: BoundingBox, table_bboxes: List[BoundingBox]
    ) -> bool:
        """Check if a text bbox overlaps significantly with any table bbox."""
        for tb in table_bboxes:
            # Calculate intersection area
            x_overlap = max(0.0, min(text_bbox.x1, tb.x1) - max(text_bbox.x0, tb.x0))
            y_overlap = max(0.0, min(text_bbox.y1, tb.y1) - max(text_bbox.y0, tb.y0))
            intersection = x_overlap * y_overlap
            if intersection <= 0:
                continue

            # Calculate text bbox area
            text_area = (text_bbox.x1 - text_bbox.x0) * (text_bbox.y1 - text_bbox.y0)
            if text_area <= 0:
                continue

            # If >50% of the text area overlaps with the table, it's a duplicate
            overlap_ratio = intersection / text_area
            if overlap_ratio > 0.5:
                return True
        return False

    # -----------------------------------------------------------------------
    # Chart/image detection
    # -----------------------------------------------------------------------

    def _detect_chart_regions(
        self,
        page,
        page_idx: int,
        raw_path: Path,
        full_text: str,
    ) -> List[ContentBlock]:
        """Detect chart/image-heavy regions on a page."""
        images = page.images or []
        rects = page.rects or []

        # Heuristic: page has many images and relatively little text
        page_area = page.width * page.height
        if page_area <= 0:
            return []

        image_area = sum(
            abs(img.get("x1", 0) - img.get("x0", 0))
            * abs(img.get("y1", 0) - img.get("y0", 0))
            for img in images
        )
        image_density = image_area / page_area if page_area > 0 else 0

        # If images cover a significant portion, this is chart-heavy
        if len(images) >= 3 and image_density > _IMAGE_DENSITY_THRESHOLD:
            # Build a chart_region block summarizing the visual content
            chart_text = self._summarize_visual_page(full_text, images, rects)
            bbox = BoundingBox(x0=0, y0=0, x1=page.width, y1=page.height)

            return [
                self._build_block(
                    block_type="chart_region",
                    text=chart_text,
                    page_idx=page_idx,
                    raw_path=raw_path,
                    bbox=bbox,
                    source_hash=self._hash_text(chart_text),
                    metadata={
                        "image_count": len(images),
                        "rect_count": len(rects),
                        "image_density": round(image_density, 2),
                    },
                )
            ]

        return []

    def _summarize_visual_page(
        self, text: str, images: list, rects: list
    ) -> str:
        """Create a summary for a chart/image-heavy page."""
        parts: List[str] = []
        if text.strip():
            # Take first 200 chars of text as context
            parts.append(text.strip()[:200])
        parts.append(f"[Page contains {len(images)} images and {len(rects)} graphic elements]")
        return " ".join(parts)

    # -----------------------------------------------------------------------
    # OCR fallback for scanned pages
    # -----------------------------------------------------------------------

    def _ocr_fallback_page(
        self, page, page_idx: int, raw_path: Path
    ) -> List[ContentBlock]:
        """OCR fallback for scanned/image-heavy pages."""
        # Primary: layout-aware OCR (Qwen-VL-OCR) — returns text WITH pixel bbox.
        layout_blocks = self._ocr_page_via_layout(page, page_idx, raw_path)
        if layout_blocks:
            return layout_blocks

        # Fallback: MiMo chat-vision text (no bbox).
        ocr_text = self._extract_page_via_vision(page, raw_path)
        if not ocr_text or len(ocr_text.strip()) < 10:
            return []

        # Parse OCR text into blocks
        paragraphs = self._split_paragraphs(ocr_text)
        blocks: List[ContentBlock] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            noise_type = self._detect_noise_type(para)
            if noise_type:
                blocks.append(
                    self._build_noise_block(noise_type, para, page_idx, raw_path)
                )
                continue

            block_type = self._classify_text(para, page_idx)
            blocks.append(
                self._build_block(
                    block_type=block_type,
                    text=para,
                    page_idx=page_idx,
                    raw_path=raw_path,
                    source_hash=self._hash_text(para),
                    quality_flags=["ocr_extracted"],
                    model_name=self._resolve_llm_model_name(),
                )
            )

        return blocks

    def _ocr_page_via_layout(
        self, page, page_idx: int, raw_path: Path
    ) -> List[ContentBlock]:
        """Render the page and OCR it with the layout engine → blocks WITH bbox.

        Qwen-VL-OCR boxes come back in the rendered raster's pixel space; we
        convert them to PDF points (×72/dpi) so OCR blocks share the coordinate
        system of the pdfplumber text-layer blocks. Returns [] to signal fallback.
        """
        if self._layout_client is None:
            self._layout_client = LayoutOCRClient()
        if not self._layout_client.available:
            return []
        try:
            img = page.to_image(resolution=_OCR_RENDER_DPI)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            regions = self._layout_client.extract_layout_regions(buf.getvalue(), "image/png")
        except Exception:
            logger.warning("Layout OCR failed for page in %s", raw_path.name, exc_info=True)
            return []
        if not regions:
            return []

        scale = 72.0 / _OCR_RENDER_DPI  # pixel → PDF point
        model_name = self._layout_client.model
        blocks: List[ContentBlock] = []
        for region in regions:
            text = (region.get("text") or "").strip()
            if not text:
                continue
            noise_type = self._detect_noise_type(text)
            if noise_type:
                blocks.append(self._build_noise_block(noise_type, text, page_idx, raw_path))
                continue
            block_type = _LAYOUT_REGION_BLOCK_TYPE.get(region.get("type", ""), "paragraph")
            bbox = self._region_bbox_to_points(region.get("bbox"), scale)
            metadata: Dict[str, Any] = {"layout_available": True, "render_dpi": _OCR_RENDER_DPI}
            if region.get("line_boxes"):
                metadata["line_boxes"] = [
                    [c * scale for c in lb] for lb in region["line_boxes"]
                ]
            blocks.append(
                self._build_block(
                    block_type=block_type,
                    text=text,
                    page_idx=page_idx,
                    raw_path=raw_path,
                    bbox=bbox,
                    source_hash=self._hash_text(text),
                    quality_flags=["ocr_extracted", "layout_ocr"],
                    model_name=model_name,
                    metadata=metadata,
                )
            )
        return blocks

    @staticmethod
    def _region_bbox_to_points(bb: Optional[Dict[str, float]], scale: float) -> Optional[BoundingBox]:
        """Convert a pixel-space region bbox dict to a PDF-point BoundingBox."""
        if not bb:
            return None
        return BoundingBox(
            x0=bb["x0"] * scale,
            y0=bb["y0"] * scale,
            x1=bb["x1"] * scale,
            y1=bb["y1"] * scale,
        )

    def _get_vision_error_reason(self) -> str:
        """Extract the last vision API error reason for failure metadata."""
        if self._llm is None:
            return "no_llm_client"
        return getattr(self._llm, "last_error", "unknown") or "unknown"

    def _extract_page_via_vision(self, page, raw_path: Path) -> Optional[str]:
        """Render a PDF page to image and send to vision API."""
        try:
            from finer.llm.client import LLMClient
            from finer.model_config import get_vision_registry

            if self._llm is None:
                registry = get_vision_registry()
                self._llm = LLMClient.from_registry(registry)
            if self._llm is None:
                return None

            # Render page to image bytes
            img = page.to_image(resolution=_OCR_RENDER_DPI)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            prompt = (
                "请精准提取这张图片中的所有文字信息，"
                "并按照原图排版结构转化为Markdown格式。"
                "只需返回Markdown本身。"
            )
            from finer.parsing.ocr_quality import gate_vision_output

            raw = self._llm.chat_with_images(
                text=prompt,
                image_base64=image_b64,
                mime_type="image/png",
            )
            return gate_vision_output(raw)
        except Exception:
            logger.warning(
                "Vision OCR failed for page in %s", raw_path.name, exc_info=True
            )
            return None

    # -----------------------------------------------------------------------
    # Noise detection
    # -----------------------------------------------------------------------

    def _detect_noise_type(self, text: str) -> Optional[str]:
        """Classify text as noise type or None."""
        for pat in _WATERMARK_PATTERNS:
            if pat.search(text):
                return "watermark"
        for pat in _FOOTER_PATTERNS:
            if pat.search(text):
                return "page_footer"
        for pat in _PLATFORM_NOISE_PATTERNS:
            if pat.search(text):
                return "platform_noise"
        for pat in _HEADER_PATTERNS:
            if pat.search(text.strip()):
                return "page_header"
        return None

    def _build_noise_block(
        self,
        noise_type: str,
        text: str,
        page_idx: int,
        raw_path: Path,
    ) -> ContentBlock:
        """Build a system_event block for noise content."""
        return ContentBlock(
            block_type="system_event",
            text=text.strip(),
            order_index=0,
            page_index=page_idx,
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
                extractor="pdf_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"noise_type": noise_type},
        )

    # -----------------------------------------------------------------------
    # Block builders
    # -----------------------------------------------------------------------

    def _build_block(
        self,
        block_type: str,
        text: str,
        page_idx: int,
        raw_path: Path,
        bbox: Optional[BoundingBox] = None,
        source_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        quality_flags: Optional[List[str]] = None,
        model_name: Optional[str] = None,
    ) -> ContentBlock:
        """Construct a ContentBlock with quality and provenance."""
        quality = self._score_block_quality(text, block_type, quality_flags)
        provenance = BlockProvenance(
            raw_path=str(raw_path),
            extractor="pdf_standardizer",
            extractor_version=_EXTRACTOR_VERSION,
            source_hash=source_hash or self._hash_text(text),
            model_name=model_name,
        )
        return ContentBlock(
            block_type=block_type,
            text=text,
            order_index=0,
            page_index=page_idx,
            bbox=bbox,
            quality=quality,
            provenance=provenance,
            metadata=metadata or {},
        )

    def _build_unreadable_page_block(
        self, page_idx: int, raw_path: Path, error_reason: Optional[str] = None
    ) -> ContentBlock:
        """Emit for pages where no content could be extracted."""
        metadata: Dict[str, Any] = {}
        flags = ["ocr_unreadable", "empty_page"]
        if error_reason:
            metadata["vision_error"] = error_reason
            flags.append(f"vision_{error_reason.split('(')[0].strip()}")
        return ContentBlock(
            block_type="ocr_unreadable",
            text=f"[Page {page_idx}: no extractable content]",
            order_index=0,
            page_index=page_idx,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.5,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=flags,
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="pdf_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata=metadata,
        )

    def _build_extraction_failure_block(
        self, raw_path: Path, f0_record: ContentRecord
    ) -> ContentBlock:
        """Emit when the entire PDF yielded zero blocks."""
        return ContentBlock(
            block_type="ocr_unreadable",
            text=f"[PDF extraction produced no blocks for {f0_record.content_id}]",
            order_index=0,
            page_index=0,
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
                extractor="pdf_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
        )

    def _build_unreadable_pdf_block(
        self, raw_path: Path, f0_record: ContentRecord, error_type: str = "unknown"
    ) -> ContentBlock:
        """Emit when the PDF itself cannot be opened (corrupt, encrypted, etc.)."""
        return ContentBlock(
            block_type="ocr_unreadable",
            text=f"[PDF unreadable: {raw_path.name}]",
            order_index=0,
            page_index=0,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.5,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["pdf_unreadable", "open_failed"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="pdf_standardizer",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"error_type": error_type},
        )

    # -----------------------------------------------------------------------
    # Quality scoring
    # -----------------------------------------------------------------------

    def _score_block_quality(
        self,
        text: str,
        block_type: str,
        extra_flags: Optional[List[str]] = None,
    ) -> BlockQuality:
        """Deterministic quality scoring for PDF blocks."""
        flags: List[str] = list(extra_flags or [])
        text_len = len(text.strip())

        # Readability
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

        # Structural confidence
        if block_type == "section_title":
            structural = 0.9
        elif block_type in ("table_region", "chart_region"):
            structural = 0.8
        elif block_type == "system_event":
            structural = 0.95
        else:
            structural = 0.7

        # Extraction confidence
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

    # -----------------------------------------------------------------------
    # BBox estimation from page words
    # -----------------------------------------------------------------------

    def _estimate_text_bbox(
        self, text: str, page
    ) -> Optional[BoundingBox]:
        """Estimate bounding box for a text paragraph using page words."""
        try:
            words = page.extract_words() or []
            if not words:
                return None

            # Find words that appear in our text
            text_chars = set(text.strip()[:50])  # first 50 chars
            matching_words = [
                w for w in words
                if any(c in text_chars for c in w.get("text", "")[:10])
            ]

            if not matching_words:
                return None

            x0 = min(w["x0"] for w in matching_words)
            y0 = min(w["top"] for w in matching_words)
            x1 = max(w["x1"] for w in matching_words)
            y1 = max(w["bottom"] for w in matching_words)

            return BoundingBox(
                x0=max(0.0, x0),
                y0=max(0.0, y0),
                x1=float(x1),
                y1=float(y1),
            )
        except Exception:
            return None

    # -----------------------------------------------------------------------
    # Envelope builder
    # -----------------------------------------------------------------------

    def _build_envelope(
        self,
        f0_record: ContentRecord,
        raw_path: Path,
        blocks: List[ContentBlock],
    ) -> ContentEnvelope:
        """Assemble the final ContentEnvelope."""
        quality_card = self._compute_quality_card(blocks)

        noise_tags = sorted({
            b.metadata.get("noise_type", "")
            for b in blocks
            if b.metadata.get("noise_type")
        })

        published_at = f0_record.published_at
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)

        return ContentEnvelope(
            source_record_id=f0_record.content_id,
            schema_version="v1.0",
            source_type="pdf",
            standardization_profile="pdf_layout_v1",
            source_uri=f0_record.raw_path,
            source_title=raw_path.name,
            raw_path=str(raw_path),
            creator_name=f0_record.creator_name,
            published_at=published_at,
            ingested_at=datetime.now(),
            blocks=blocks,
            quality_card=quality_card,
            metadata={
                "file_size_bytes": raw_path.stat().st_size if raw_path.exists() else 0,
                "noise_watermark": noise_tags if noise_tags else [],
            },
        )

    def _compute_quality_card(self, blocks: List[ContentBlock]) -> QualityCard:
        """Aggregate block quality into envelope-level QualityCard."""
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

    # -----------------------------------------------------------------------
    # LLM model name resolution
    # -----------------------------------------------------------------------

    def _resolve_llm_model_name(self) -> Optional[str]:
        """Extract model name from the LLM client, checking public and private attrs."""
        if self._llm is None:
            return None
        return getattr(self._llm, "model", None) or getattr(self._llm, "_model", None)

    # -----------------------------------------------------------------------
    # Hashing
    # -----------------------------------------------------------------------

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
