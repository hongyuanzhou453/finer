"""F1 Feishu Chat Markdown Standardizer.

Converts Feishu chat export markdown into a canonical ContentEnvelope
with ContentBlock records.  This is the F1 adapter for feishu_chat source type.

Parsing rules:
- Header: ``### [YYYY-MM-DD HH:MM:SS] <user_id> (<message_type>)``
- message_type: text, post, merge_forward
- Failed forwards (``[Merged forward: fetch failed: ...]``) → attachment_ref
- HTML wrappers (``<p>...</p>``) are cleaned; metadata records ``html_cleaned``
- Q/A format (``Q:...A:...``) is detected and recorded in metadata
- System metadata header (title, Chat ID, etc.) → system_event block
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.quality import QualityCard

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXTRACTOR_NAME = "feishu_chat_standardizer"
EXTRACTOR_VERSION = "1.0.0"
STANDARDIZATION_PROFILE = "feishu_chat_markdown_v1"

_TZ_BEIJING = timezone(timedelta(hours=8))

# Regex: ### [2026-03-12 14:34:00] ou_xxx (text)
_HEADER_RE = re.compile(
    r"^### \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\S+) \((\w+)\)$"
)

# Patterns for cleaning and detection
_HTML_P_RE = re.compile(r"<p>(.*?)</p>", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_REF_RE = re.compile(r"\[Image:\s*(\S+?)\]")
_QA_FORMAT_RE = re.compile(r"^Q[:：]", re.MULTILINE)
_FAILED_FORWARD_RE = re.compile(r"\[Merged forward:.*fetch failed", re.IGNORECASE)
_MERGED_FORWARD_RE = re.compile(r"^\[Merged forward:", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")

# File metadata header lines (before first ### header)
_METADATA_HEADER_RE = re.compile(
    r"^(# Chat History:|- \*\*Chat ID\*\*:|- \*\*Creator Segment\*\*:|- \*\*Time Range\*\*:|---)$"
)


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def _compute_block_quality(
    text: str,
    block_type: str,
    html_cleaned: bool = False,
    has_failed_forward: bool = False,
) -> BlockQuality:
    """Deterministic quality scoring for a chat block.

    Scores are based on text properties, not subjective LLM judgement.
    All scores in [0.0, 1.0].
    """
    flags: List[str] = []
    text_len = len(text.strip())

    # Readability: based on text length and character quality
    if text_len == 0:
        readability = 0.1
    elif text_len < 10:
        readability = 0.4
    elif text_len < 50:
        readability = 0.6
    else:
        readability = 0.85

    # Extraction confidence: depends on block type and parsing success
    if block_type == "chat_message":
        extraction_confidence = 0.9
    elif block_type == "attachment_ref":
        extraction_confidence = 0.7
        flags.append("attachment_missing" if has_failed_forward else "attachment_ref")
    elif block_type == "system_event":
        extraction_confidence = 0.8
    else:
        extraction_confidence = 0.7

    # Structural confidence: header parsing is deterministic
    structural_confidence = 0.95

    # Completeness: check for empty or truncated content
    if text_len == 0:
        completeness = 0.1
        flags.append("empty_forward" if has_failed_forward else "empty_content")
    elif text_len < 5:
        completeness = 0.3
    else:
        completeness = 0.9

    # Noise score: system noise, failed forwards, metadata headers
    noise_score = 0.0
    if block_type == "system_event":
        noise_score = 0.8
        flags.append("system_noise")
    elif has_failed_forward:
        noise_score = 0.6
    elif block_type == "attachment_ref":
        noise_score = 0.3

    if html_cleaned:
        flags.append("html_cleaned")

    return BlockQuality(
        readability=readability,
        extraction_confidence=extraction_confidence,
        structural_confidence=structural_confidence,
        completeness=completeness,
        noise_score=noise_score,
        quality_flags=flags,
    )


def _make_provenance(
    raw_path: str,
    offset_start: int,
    offset_end: int,
    source_content: str,
) -> BlockProvenance:
    """Build BlockProvenance with raw offsets and content hash."""
    return BlockProvenance(
        raw_path=raw_path,
        raw_offset_start=offset_start,
        raw_offset_end=offset_end,
        extractor=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        source_hash=hashlib.sha256(source_content.encode("utf-8")).hexdigest()[:16],
    )


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> Tuple[str, bool]:
    """Remove mechanical HTML wrappers like <p>...</p>.

    Returns (cleaned_text, html_cleaned_flag).
    """
    if "<p>" not in text and "</p>" not in text:
        return text, False

    # Replace <p>...</p> with content + newline
    cleaned = _HTML_P_RE.sub(r"\1\n", text)
    # Remove any remaining HTML tags
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    # Collapse multiple newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), True


def _extract_image_refs(text: str) -> List[str]:
    """Extract [Image: ...] references from text."""
    return _IMAGE_REF_RE.findall(text)


def _detect_qa_format(text: str) -> bool:
    """Detect Q/A format in message text."""
    return bool(_QA_FORMAT_RE.search(text))


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS' as Beijing time."""
    return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ_BEIJING)


def _split_messages(raw_text: str) -> List[Tuple[int, int, Optional[str], Optional[str], Optional[str], str]]:
    """Split raw text into messages by ### headers.

    Returns list of (body_start_offset, body_end_offset, timestamp_str, speaker, message_type, body_text).
    The first entry may have None for header fields if it's a metadata prefix.

    Offsets are **character** offsets into raw_text (not UTF-8 byte offsets),
    so ``raw_text[start:end]`` reliably recovers the source span.

    Uses ``splitlines(keepends=True)`` so that each raw line retains its
    original line ending (``\\n`` or ``\\r\\n``).  The character advance for
    each line is simply ``len(raw_line)`` — no +1 heuristic needed.
    """
    raw_lines = raw_text.splitlines(keepends=True)
    messages: List[Tuple[int, int, Optional[str], Optional[str], Optional[str], str]] = []

    current_header: Optional[Tuple[str, str, str]] = None  # (ts, speaker, msg_type)
    body_lines: List[str] = []
    body_start_offset = 0
    current_offset = 0

    for raw_line in raw_lines:
        line = raw_line.rstrip("\n\r")  # strip line ending for matching/content
        line_char_len = len(raw_line)   # exact character advance in raw_text
        match = _HEADER_RE.match(line)

        if match:
            # Save previous message
            if current_header is not None:
                body_text = "\n".join(body_lines)
                messages.append((
                    body_start_offset,
                    current_offset,
                    current_header[0],
                    current_header[1],
                    current_header[2],
                    body_text,
                ))
            elif body_lines:
                # Metadata prefix before first header — end offset is the
                # character position just before the header line begins.
                body_text = "\n".join(body_lines)
                messages.append((
                    0,
                    current_offset,
                    None,
                    None,
                    None,
                    body_text,
                ))

            # Start new message: body begins after this raw line
            current_header = (match.group(1), match.group(2), match.group(3))
            body_lines = []
            body_start_offset = current_offset + line_char_len
        else:
            body_lines.append(line)

        current_offset += line_char_len

    # Save last message
    if current_header is not None:
        body_text = "\n".join(body_lines)
        messages.append((
            body_start_offset,
            current_offset,
            current_header[0],
            current_header[1],
            current_header[2],
            body_text,
        ))

    return messages


# ---------------------------------------------------------------------------
# Standardizer
# ---------------------------------------------------------------------------

class FeishuChatMarkdownStandardizer:
    """F1 standardizer for Feishu chat markdown exports."""

    def standardize(
        self,
        f0_record: ContentRecord,
        raw_path: Path,
    ) -> ContentEnvelope:
        """Convert a Feishu chat markdown file into a canonical ContentEnvelope.

        Args:
            f0_record: F0 ContentRecord with source metadata.
            raw_path: Path to the raw markdown file.

        Returns:
            ContentEnvelope with canonical F1 output.
        """
        raw_text = raw_path.read_text(encoding="utf-8")
        raw_path_str = str(raw_path)

        messages = _split_messages(raw_text)
        blocks: List[ContentBlock] = []
        order = 0

        for body_start, body_end, ts_str, speaker, msg_type, body_text in messages:
            # Skip metadata prefix (no header)
            if ts_str is None:
                # Emit as system_event if it has meaningful content
                stripped = body_text.strip()
                if stripped and not all(_METADATA_HEADER_RE.match(l) or not l.strip() for l in stripped.split("\n")):
                    cleaned, html_cleaned = _clean_html(stripped)
                    if cleaned:
                        blocks.append(self._make_block(
                            block_type="system_event",
                            text=cleaned,
                            order_index=order,
                            speaker=None,
                            timestamp=None,
                            raw_path=raw_path_str,
                            offset_start=body_start,
                            offset_end=body_end,
                            source_content=cleaned,
                            metadata={"source": "file_header", "html_cleaned": html_cleaned},
                            is_noise=True,
                        ))
                        order += 1
                continue

            # Parse timestamp
            timestamp = _parse_timestamp(ts_str)

            # Clean HTML
            cleaned, html_cleaned = _clean_html(body_text)
            cleaned = cleaned.strip()

            # Detect failed forward
            is_failed_forward = bool(_FAILED_FORWARD_RE.search(body_text))

            # Detect merge_forward type
            is_merge_forward = msg_type == "merge_forward" or bool(_MERGED_FORWARD_RE.match(body_text.strip()))

            # Build metadata
            metadata: Dict[str, Any] = {"message_type": msg_type}
            if html_cleaned:
                metadata["html_cleaned"] = True

            # Extract image references
            image_refs = _extract_image_refs(body_text)
            if image_refs:
                metadata["image_refs"] = image_refs

            # Detect Q/A format
            if _detect_qa_format(cleaned):
                metadata["qa_format"] = True

            # Determine block type
            if is_failed_forward or (is_merge_forward and "fetch failed" in body_text.lower()):
                # Failed forward → attachment_ref
                block_type = "attachment_ref"
                metadata["failure_reason"] = "fetch_failed"
                text = cleaned if cleaned else "[Merged forward: fetch failed: empty data]"
                blocks.append(self._make_block(
                    block_type=block_type,
                    text=text,
                    order_index=order,
                    speaker=speaker,
                    timestamp=timestamp,
                    raw_path=raw_path_str,
                    offset_start=body_start,
                    offset_end=body_end,
                    source_content=body_text,
                    metadata=metadata,
                    has_failed_forward=True,
                ))
                order += 1

            elif is_merge_forward:
                # Successful merge_forward → chat_message
                block_type = "chat_message"
                metadata["message_type"] = "merge_forward"
                if cleaned:
                    blocks.append(self._make_block(
                        block_type=block_type,
                        text=cleaned,
                        order_index=order,
                        speaker=speaker,
                        timestamp=timestamp,
                        raw_path=raw_path_str,
                        offset_start=body_start,
                        offset_end=body_end,
                        source_content=body_text,
                        metadata=metadata,
                    ))
                    order += 1

            elif msg_type in ("text", "post"):
                # Normal text or post message → chat_message
                block_type = "chat_message"
                if cleaned:
                    blocks.append(self._make_block(
                        block_type=block_type,
                        text=cleaned,
                        order_index=order,
                        speaker=speaker,
                        timestamp=timestamp,
                        raw_path=raw_path_str,
                        offset_start=body_start,
                        offset_end=body_end,
                        source_content=body_text,
                        metadata=metadata,
                    ))
                    order += 1
            else:
                # Unknown type → system_event
                if cleaned:
                    metadata["original_type"] = msg_type
                    blocks.append(self._make_block(
                        block_type="system_event",
                        text=cleaned,
                        order_index=order,
                        speaker=speaker,
                        timestamp=timestamp,
                        raw_path=raw_path_str,
                        offset_start=body_start,
                        offset_end=body_end,
                        source_content=body_text,
                        metadata=metadata,
                        is_noise=True,
                    ))
                    order += 1

        # Canonical guard: never return an empty block list.  If parsing
        # produced zero blocks (empty file, header-only, no parseable headers),
        # emit a single system_event explaining the situation.
        if not blocks:
            reason = "empty_export" if not raw_text.strip() else "no_parseable_messages"
            blocks.append(self._make_block(
                block_type="system_event",
                text=f"[Standardization fallback: {reason}]",
                order_index=0,
                speaker=None,
                timestamp=None,
                raw_path=raw_path_str,
                offset_start=0,
                offset_end=len(raw_text),
                source_content=raw_text[:200] if raw_text else "",
                metadata={"source": "standardization_fallback", "reason": reason},
                is_noise=True,
            ))

        # Build envelope-level quality card (required by ContentEnvelope)
        envelope_quality = QualityCard(
            readability_score=0.8,
            semantic_completeness_score=0.7,
            financial_relevance_score=0.6,
            entity_resolution_score=0.0,
            temporal_resolution_score=0.0,
            evidence_traceability_score=0.8,
        )

        # Extract chat_id from f0_record metadata if available
        f0_metadata = f0_record.metadata or {}
        chat_id = f0_metadata.get("chat_id", "")

        envelope = ContentEnvelope(
            source_type="feishu_chat",
            schema_version="v1.0",
            source_record_id=f0_record.content_id,
            standardization_profile=STANDARDIZATION_PROFILE,
            raw_path=raw_path_str,
            creator_id=f0_metadata.get("feishu_sender_id"),
            creator_name=f0_record.creator_name,
            title=f0_record.title or raw_path.name,
            published_at=f0_record.published_at,
            blocks=blocks,
            quality_card=envelope_quality,
            temporal_anchors=[],
            entity_anchors=[],
            metadata={
                "chat_id": chat_id,
                "chat_name": f0_metadata.get("chat_name", ""),
                "total_messages_parsed": order,
                "feishu_chat_id": chat_id,
            },
        )

        return envelope

    def _make_block(
        self,
        block_type: str,
        text: str,
        order_index: int,
        speaker: Optional[str],
        timestamp: Optional[datetime],
        raw_path: str,
        offset_start: int,
        offset_end: int,
        source_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        is_noise: bool = False,
        has_failed_forward: bool = False,
        html_cleaned: bool = False,
    ) -> ContentBlock:
        """Build a single ContentBlock with quality and provenance."""
        quality = _compute_block_quality(
            text=text,
            block_type=block_type,
            html_cleaned=html_cleaned,
            has_failed_forward=has_failed_forward,
        )
        provenance = _make_provenance(
            raw_path=raw_path,
            offset_start=offset_start,
            offset_end=offset_end,
            source_content=source_content,
        )

        return ContentBlock(
            block_id=f"block_{uuid4().hex[:12]}",
            block_type=block_type,
            text=text,
            order_index=order_index,
            speaker=speaker,
            timestamp=timestamp,
            quality=quality,
            provenance=provenance,
            metadata=metadata or {},
        )
