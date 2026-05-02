"""Standardization Router — unified F1 entry point.

Routes F0 ContentRecord to the correct F1 canonical adapter based on
file type (suffix), content_type, and source_platform.

Routing priority:
1. .pdf → PDFStandardizer
2. .png/.jpg/.jpeg/.webp/.bmp → ImageOCRLayoutStandardizer
3. .md + content_type in (chat_transcript, chat_export) → FeishuChatMarkdownStandardizer
4. .md/.txt (fallback) → ManualTextStandardizer
5. livestream_audio → StandardizationError (reserved, not implemented)
6. No match → ocr_unreadable failure envelope
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, TypedDict

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

_PDF_SUFFIXES = {".pdf"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEXT_SUFFIXES = {".md", ".txt"}
_CHAT_CONTENT_TYPES = {"chat_transcript", "chat_export"}
_AUDIO_CONTENT_TYPES = {"livestream_audio"}


class StandardizationError(Exception):
    """Raised when standardization cannot proceed (reserved types, unsupported)."""


class StandardizationReport(TypedDict):
    envelope_id: str
    adapter: str
    block_count: int
    low_quality_block_count: int
    warnings: list[str]
    canonical_validation_passed: bool


class StandardizationRouter:
    """Unified F1 entry point: routes F0 → correct adapter → canonical envelope."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def route(
        self, f0_record: ContentRecord, raw_path: Path
    ) -> tuple[ContentEnvelope, StandardizationReport]:
        """Route a F0 record to the appropriate adapter and return envelope + report."""
        adapter_name = self._select_adapter(f0_record, raw_path)
        envelope = self._run_adapter(adapter_name, f0_record, raw_path)
        report = self._build_report(envelope, adapter_name)
        return envelope, report

    # -----------------------------------------------------------------------
    # Adapter selection
    # -----------------------------------------------------------------------

    def _select_adapter(self, f0_record: ContentRecord, raw_path: Path) -> str:
        """Determine which adapter handles this record.

        Returns: "pdf", "image", "feishu_chat", "manual_text"
        Raises: StandardizationError for reserved/unsupported types.
        """
        suffix = raw_path.suffix.lower()

        # 1. PDF
        if suffix in _PDF_SUFFIXES:
            return "pdf"

        # 2. Image
        if suffix in _IMAGE_SUFFIXES:
            return "image"

        # 3. Feishu chat markdown (content_type must be chat — platform alone is insufficient)
        if suffix in _TEXT_SUFFIXES:
            if f0_record.content_type in _CHAT_CONTENT_TYPES:
                return "feishu_chat"
            # 4. Manual text fallback
            return "manual_text"

        # 5. Reserved: audio
        if f0_record.content_type in _AUDIO_CONTENT_TYPES:
            raise StandardizationError(
                f"Audio standardization not implemented "
                f"(content_type={f0_record.content_type})"
            )

        # 6. No match — caller will build failure envelope
        return "unsupported"

    # -----------------------------------------------------------------------
    # Adapter dispatch
    # -----------------------------------------------------------------------

    def _run_adapter(
        self, adapter_name: str, f0_record: ContentRecord, raw_path: Path
    ) -> ContentEnvelope:
        """Dispatch to the correct adapter. Never raises — returns failure envelope on error."""
        try:
            if adapter_name == "pdf":
                return self._run_pdf(f0_record, raw_path)
            if adapter_name == "image":
                return self._run_image(f0_record, raw_path)
            if adapter_name == "feishu_chat":
                return self._run_feishu_chat(f0_record, raw_path)
            if adapter_name == "manual_text":
                return self._run_manual_text(f0_record, raw_path)
            # unsupported
            return self._build_failure_envelope(
                f0_record, raw_path,
                reason=f"No adapter for suffix={raw_path.suffix}, "
                       f"content_type={f0_record.content_type}",
            )
        except StandardizationError:
            raise
        except Exception as exc:
            logger.warning(
                "Adapter %s failed for %s: %s",
                adapter_name, raw_path.name, type(exc).__name__,
            )
            return self._build_failure_envelope(
                f0_record, raw_path,
                reason=f"Adapter {adapter_name} failed: {type(exc).__name__}",
            )

    def _run_pdf(self, f0_record: ContentRecord, raw_path: Path) -> ContentEnvelope:
        from finer.parsing.pdf_standardizer import PDFStandardizer
        std = PDFStandardizer(llm_client=self._llm)
        return std.standardize(f0_record, raw_path)

    def _run_image(self, f0_record: ContentRecord, raw_path: Path) -> ContentEnvelope:
        from finer.parsing.image_ocr_standardizer import ImageOCRLayoutStandardizer
        std = ImageOCRLayoutStandardizer(llm_client=self._llm)
        return std.standardize(f0_record, raw_path)

    def _run_feishu_chat(self, f0_record: ContentRecord, raw_path: Path) -> ContentEnvelope:
        from finer.parsing.feishu_chat_standardizer import FeishuChatMarkdownStandardizer
        std = FeishuChatMarkdownStandardizer()
        return std.standardize(f0_record, raw_path)

    def _run_manual_text(self, f0_record: ContentRecord, raw_path: Path) -> ContentEnvelope:
        from finer.parsing.manual_text_standardizer import ManualTextStandardizer
        std = ManualTextStandardizer()
        return std.standardize(f0_record, raw_path)

    # -----------------------------------------------------------------------
    # Failure envelope
    # -----------------------------------------------------------------------

    @staticmethod
    def _infer_source_type(f0_record: ContentRecord, raw_path: Path) -> str:
        """Map suffix/content_type to a meaningful source_type for failure envelopes."""
        suffix = raw_path.suffix.lower()
        if suffix in _PDF_SUFFIXES:
            return "pdf"
        if suffix in _IMAGE_SUFFIXES:
            return "image"
        if f0_record.content_type in _CHAT_CONTENT_TYPES:
            return "feishu_chat"
        return "manual_text"

    def _build_failure_envelope(
        self, f0_record: ContentRecord, raw_path: Path, reason: str
    ) -> ContentEnvelope:
        """Build a canonical envelope with a single ocr_unreadable failure block."""
        source_type = self._infer_source_type(f0_record, raw_path)

        block = ContentBlock(
            block_type="ocr_unreadable",
            text=f"[Standardization failed: {reason}]",
            order_index=0,
            page_index=0,
            quality=BlockQuality(
                readability=0.0,
                extraction_confidence=0.0,
                structural_confidence=0.5,
                completeness=0.0,
                noise_score=0.0,
                quality_flags=["standardization_failed"],
            ),
            provenance=BlockProvenance(
                raw_path=str(raw_path),
                extractor="standardization_router",
                extractor_version=_EXTRACTOR_VERSION,
            ),
            metadata={"failure_reason": reason, "intended_source_type": source_type},
        )

        published_at = f0_record.published_at
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)

        return ContentEnvelope(
            source_record_id=f0_record.content_id,
            schema_version="v1.0",
            source_type=source_type,
            standardization_profile="failure",
            source_uri=f0_record.source_path,
            source_title=raw_path.name,
            raw_path=str(raw_path),
            creator_name=f0_record.creator_name,
            published_at=published_at,
            ingested_at=datetime.now(),
            blocks=[block],
            quality_card=QualityCard.create_default(overall=0.0),
        )

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------

    def _build_report(
        self, envelope: ContentEnvelope, adapter_name: str
    ) -> StandardizationReport:
        """Build a standardization report from the envelope."""
        violations = envelope.validate_canonical_f1()
        low_quality = sum(
            1 for b in envelope.blocks
            if b.quality.extraction_confidence < 0.5
        )

        warnings: List[str] = []
        if violations:
            warnings.append(
                f"Canonical validation failed ({len(violations)} violations)"
            )
        if low_quality > 0:
            warnings.append(f"{low_quality} low-quality blocks (confidence < 0.5)")

        return StandardizationReport(
            envelope_id=envelope.envelope_id,
            adapter=adapter_name,
            block_count=len(envelope.blocks),
            low_quality_block_count=low_quality,
            warnings=warnings,
            canonical_validation_passed=len(violations) == 0,
        )
