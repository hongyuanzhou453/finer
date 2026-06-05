"""Minimal F0-only importer for exported Feishu chat markdown.

This module consumes an already-exported chat transcript and writes canonical
``ContentRecord`` objects. It intentionally stops at F0: raw archive, message
slice, provenance, and timestamp preservation.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from finer.schemas.content import ContentRecord

BEIJING_TZ = timezone(timedelta(hours=8))
FEISHU_CHAT_SOURCE_TYPE = "feishu_chat"

_HEADER_RE = re.compile(
    r"^### \[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
    r"(?P<sender_id>\S+) \((?P<message_type>\w+)\)\r?$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class FeishuMessageSelection:
    """Selector for one exported chat message.

    ``occurrence`` is 1-based among messages matching timestamp, sender, and
    message_type. It disambiguates repeated Feishu exports with identical
    timestamps.
    """

    timestamp: datetime | str
    sender_id: str | None = None
    message_type: str | None = None
    occurrence: int = 1


@dataclass(frozen=True)
class FeishuExportMessage:
    """One parsed Feishu export message."""

    timestamp: datetime
    sender_id: str
    message_type: str
    occurrence: int
    raw_slice: str
    body_text: str
    char_start: int
    char_end: int
    byte_start: int
    byte_end: int


@dataclass(frozen=True)
class FeishuF0ImportItem:
    """A written F0 item and its audit paths."""

    message: FeishuExportMessage
    content_record: ContentRecord
    record_path: Path
    raw_slice_path: Path
    raw_slice_sha256: str


@dataclass(frozen=True)
class FeishuF0ImportResult:
    """Result of importing selected Feishu messages."""

    chat_id: str
    source_export_path: Path
    archived_export_path: Path
    source_export_sha256: str
    items: list[FeishuF0ImportItem]


def parse_feishu_export(source_path: Path | str) -> list[FeishuExportMessage]:
    """Parse an exported Feishu markdown transcript into message records."""
    path = Path(source_path)
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    matches = list(_HEADER_RE.finditer(raw_text))
    messages: list[FeishuExportMessage] = []
    occurrence_counts: dict[tuple[str, str, str], int] = {}

    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        raw_slice = raw_text[match.start():next_start]
        body_start = raw_text.find("\n", match.start(), next_start)
        if body_start == -1:
            body_text = ""
        else:
            body_text = raw_text[body_start + 1:next_start]

        ts_str = match.group("timestamp")
        sender_id = match.group("sender_id")
        message_type = match.group("message_type")
        key = (ts_str, sender_id, message_type)
        occurrence_counts[key] = occurrence_counts.get(key, 0) + 1

        byte_start = len(raw_text[:match.start()].encode("utf-8"))
        byte_end = len(raw_text[:next_start].encode("utf-8"))
        messages.append(
            FeishuExportMessage(
                timestamp=_parse_export_timestamp(ts_str),
                sender_id=sender_id,
                message_type=message_type,
                occurrence=occurrence_counts[key],
                raw_slice=raw_slice,
                body_text=body_text,
                char_start=match.start(),
                char_end=next_start,
                byte_start=byte_start,
                byte_end=byte_end,
            )
        )

    return messages


def import_feishu_transcript(
    *,
    source_path: Path | str,
    selections: list[FeishuMessageSelection],
    chat_id: str,
    chat_name: str,
    creator_id: str = "maodaren",
    creator_name: str = "猫大人FIRE",
    canonical_creator_id: str = "kol_cat_lord_fire",
    data_root: Path | str = Path("data"),
    collected_at: datetime | None = None,
) -> FeishuF0ImportResult:
    """Import selected messages from a Feishu transcript into F0 records."""
    if not selections:
        raise ValueError("At least one FeishuMessageSelection is required")

    source = Path(source_path)
    data_root_path = Path(data_root)
    collected = collected_at or datetime.now(timezone.utc)
    source_bytes = source.read_bytes()
    source_hash = _sha256_bytes(source_bytes)

    archived_export_path = _archive_export(
        source=source,
        source_hash=source_hash,
        data_root=data_root_path,
        chat_id=chat_id,
    )

    messages = parse_feishu_export(source)
    selected_messages = _select_messages(messages, selections)

    raw_dir = data_root_path / "raw" / "feishu" / chat_id / "messages"
    record_dir = data_root_path / "F0_intake" / "feishu" / chat_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)

    items: list[FeishuF0ImportItem] = []
    for message in selected_messages:
        raw_slice_bytes = message.raw_slice.encode("utf-8")
        raw_slice_sha256 = _sha256_bytes(raw_slice_bytes)
        external_source_id = _derive_external_source_id(
            chat_id=chat_id,
            message=message,
            raw_slice_sha256=raw_slice_sha256,
        )
        content_id = f"feishu_{_short_sha256(external_source_id, 24)}"
        raw_slice_path = raw_dir / f"{content_id}.md"
        record_path = record_dir / f"{content_id}.json"

        raw_slice_path.write_bytes(raw_slice_bytes)
        record = _build_content_record(
            content_id=content_id,
            source_type=FEISHU_CHAT_SOURCE_TYPE,
            source_platform="feishu",
            creator_id=creator_id,
            creator_name=creator_name,
            published_at=message.timestamp,
            collected_at=collected,
            title=f"{chat_name} {message.timestamp.isoformat()}",
            raw_path=str(raw_slice_path),
            external_source_id=external_source_id,
            dedupe_fingerprint=_sha256_bytes(
                external_source_id.encode("utf-8") + b"\0" + raw_slice_bytes
            ),
            metadata={
                "chat_id": chat_id,
                "chat_name": chat_name,
                "message_type": message.message_type,
                "sender_id": message.sender_id,
                "feishu_sender_id": message.sender_id,
                "message_occurrence": message.occurrence,
                "timestamp_source": "feishu_create_time",
                "source_export_path": str(archived_export_path),
                "original_export_path": str(source),
                "source_export_sha256": source_hash,
                "raw_slice_sha256": raw_slice_sha256,
                "source_export_char_start": message.char_start,
                "source_export_char_end": message.char_end,
                "source_export_byte_start": message.byte_start,
                "source_export_byte_end": message.byte_end,
                "external_source_id_kind": "derived_from_export",
                "creator_mapping": {
                    "source_creator_id": creator_id,
                    "canonical_creator_id": canonical_creator_id,
                },
            },
        )
        record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        items.append(
            FeishuF0ImportItem(
                message=message,
                content_record=record,
                record_path=record_path,
                raw_slice_path=raw_slice_path,
                raw_slice_sha256=raw_slice_sha256,
            )
        )

    return FeishuF0ImportResult(
        chat_id=chat_id,
        source_export_path=source,
        archived_export_path=archived_export_path,
        source_export_sha256=source_hash,
        items=items,
    )


def import_feishu_export_all(
    *,
    source_path: Path | str,
    chat_id: str,
    chat_name: str,
    creator_id: str = "maodaren",
    creator_name: str = "猫大人FIRE",
    canonical_creator_id: str = "kol_cat_lord_fire",
    data_root: Path | str = Path("data"),
    collected_at: datetime | None = None,
) -> FeishuF0ImportResult:
    """Import *every* parsed message from a Feishu export into F0 records.

    Convenience wrapper over :func:`import_feishu_transcript` that auto-builds a
    selection for each parsed message (so the live sync path does not have to
    enumerate selections by hand). Returns an empty-items result if the export
    contains no parseable messages.
    """
    messages = parse_feishu_export(source_path)
    selections = [
        FeishuMessageSelection(
            timestamp=message.timestamp,
            sender_id=message.sender_id,
            message_type=message.message_type,
            occurrence=message.occurrence,
        )
        for message in messages
    ]
    if not selections:
        source = Path(source_path)
        source_bytes = source.read_bytes()
        source_hash = _sha256_bytes(source_bytes)
        archived_export_path = _archive_export(
            source=source,
            source_hash=source_hash,
            data_root=Path(data_root),
            chat_id=chat_id,
        )
        return FeishuF0ImportResult(
            chat_id=chat_id,
            source_export_path=source,
            archived_export_path=archived_export_path,
            source_export_sha256=source_hash,
            items=[],
        )

    return import_feishu_transcript(
        source_path=source_path,
        selections=selections,
        chat_id=chat_id,
        chat_name=chat_name,
        creator_id=creator_id,
        creator_name=creator_name,
        canonical_creator_id=canonical_creator_id,
        data_root=data_root,
        collected_at=collected_at,
    )


def freeze_feishu_f0_pack(
    *,
    result: FeishuF0ImportResult,
    pack_dir: Path | str,
) -> Path:
    """Write a small raw pack manifest for an F0-only Feishu import result."""
    pack_path = Path(pack_dir)
    pack_path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "pack_id": pack_path.name,
        "source_platform": "feishu",
        "source_type": FEISHU_CHAT_SOURCE_TYPE,
        "chat_id": result.chat_id,
        "source_export_path": str(result.archived_export_path),
        "source_export_sha256": result.source_export_sha256,
        "item_count": len(result.items),
        "items": [
            {
                "content_id": item.content_record.content_id,
                "record_path": str(item.record_path),
                "record_sha256": _sha256_file(item.record_path),
                "raw_slice_path": str(item.raw_slice_path),
                "raw_slice_sha256": item.raw_slice_sha256,
                "published_at": item.content_record.published_at.isoformat()
                if item.content_record.published_at
                else None,
                "timestamp_source": item.content_record.metadata.get("timestamp_source"),
                "external_source_id": item.content_record.external_source_id,
            }
            for item in result.items
        ],
    }
    manifest_path = pack_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


def _archive_export(
    *,
    source: Path,
    source_hash: str,
    data_root: Path,
    chat_id: str,
) -> Path:
    export_dir = data_root / "raw" / "feishu" / chat_id / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    archived = export_dir / source.name
    if archived.exists():
        archived_hash = _sha256_file(archived)
        if archived_hash != source_hash:
            raise ValueError(
                f"Archived export hash mismatch for {archived}: "
                f"{archived_hash} != {source_hash}"
            )
    else:
        shutil.copyfile(source, archived)
    return archived


def _select_messages(
    messages: list[FeishuExportMessage],
    selections: list[FeishuMessageSelection],
) -> list[FeishuExportMessage]:
    selected: list[FeishuExportMessage] = []
    for selection in selections:
        ts = _normalize_selection_timestamp(selection.timestamp)
        matches = [
            message
            for message in messages
            if message.timestamp == ts
            and (selection.sender_id is None or message.sender_id == selection.sender_id)
            and (selection.message_type is None or message.message_type == selection.message_type)
        ]
        if selection.occurrence < 1:
            raise ValueError("selection.occurrence must be >= 1")
        if len(matches) < selection.occurrence:
            raise ValueError(
                "No Feishu message matched selection "
                f"timestamp={ts.isoformat()} sender_id={selection.sender_id!r} "
                f"message_type={selection.message_type!r} occurrence={selection.occurrence}"
            )
        selected.append(matches[selection.occurrence - 1])
    return selected


def _build_content_record(
    *,
    content_id: str,
    source_type: str,
    source_platform: str,
    creator_id: str,
    creator_name: str,
    published_at: datetime,
    collected_at: datetime,
    title: str,
    raw_path: str,
    external_source_id: str,
    dedupe_fingerprint: str,
    metadata: dict[str, Any],
) -> ContentRecord:
    if source_type != FEISHU_CHAT_SOURCE_TYPE:
        raise ValueError(f"Feishu F0 importer only emits {FEISHU_CHAT_SOURCE_TYPE}")

    return ContentRecord(
        content_id=content_id,
        source_type=FEISHU_CHAT_SOURCE_TYPE,
        source_platform=source_platform,
        creator_id=creator_id,
        creator_name=creator_name,
        published_at=published_at,
        collected_at=collected_at,
        title=title,
        raw_path=raw_path,
        file_type="chat_log",
        metadata=metadata,
        external_source_id=external_source_id,
        dedupe_fingerprint=dedupe_fingerprint,
        language="zh",
    )


def _derive_external_source_id(
    *,
    chat_id: str,
    message: FeishuExportMessage,
    raw_slice_sha256: str,
) -> str:
    ts = message.timestamp.isoformat()
    return (
        f"feishu_export:{chat_id}:{ts}:{message.sender_id}:"
        f"{message.message_type}:{message.occurrence}:{raw_slice_sha256[:16]}"
    )


def _parse_export_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING_TZ)


def _normalize_selection_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=BEIJING_TZ)
        return value.astimezone(BEIJING_TZ)
    return _parse_export_timestamp(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _short_sha256(value: str, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
