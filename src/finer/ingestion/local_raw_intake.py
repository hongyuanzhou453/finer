"""Local raw-file F0 importer — backfill ContentRecords for historical images/PDFs.

Scans ``data/raw`` for image and PDF files, infers intake metadata from the
directory layout and filename, and writes canonical ``ContentRecord`` JSON under
``data/F0_intake/local/``. This is F0-only: register + provenance, no OCR, no
standardization (that is F1's job, via the standardization router).

Records are keyed by file content SHA-256, so byte-identical duplicates (e.g.
``foo.pdf`` and a re-exported ``foo_1.pdf``) collapse to a single record. The
importer only ever *writes JSON ContentRecords*: it never touches SQLite, never
deletes, and never mutates the raw files it scans.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from finer.schemas.content import ContentRecord

BEIJING_TZ = timezone(timedelta(hours=8))

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PDF_SUFFIXES = {".pdf"}
_SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | PDF_SUFFIXES

# Directory name (anywhere in the relative path) → canonical source_type.
# Only names that map to a real ContentRecord.source_type Literal are listed.
_DIR_SOURCE_TYPE = {
    "daily_post": "daily_post",
    "daily_pre": "daily_pre",
    "weekly_strategy": "weekly_strategy",
    "research_report": "research_report",
    "chat_export": "chat_export",
}
# Substring keywords for nested non-English dirs (e.g. L0_ingest livestream PDFs
# under "3号文件夹：内部直播回放/三月/...内部直播文稿.pdf").
_KEYWORD_SOURCE_TYPE = [
    ("内部直播", "livestream_audio"),
    ("直播", "livestream_audio"),
    ("周度策略", "weekly_strategy"),
    ("课代表", "weekly_strategy"),
    ("研报", "research_report"),
    ("深度分析", "research_report"),
]
# First-segment dirs that name a real origin platform rather than a creator.
_PLATFORM_DIRS = {"feishu", "bilibili", "wechat"}
# First-segment dirs that are not creators (infra/staging buckets).
_NON_CREATOR_DIRS = {"_inbox", "_research", "upload", "local", "feishu", "bilibili", "wechat"}

# Filename date/time patterns, tried most-specific first.
_FNAME_DATETIME_RE = re.compile(r"(?P<date>\d{8})[_-](?P<time>\d{4})(?:\D|$)")
_FNAME_DATE_RE = re.compile(r"(?<!\d)(?P<date>\d{8})(?!\d)")
_FNAME_DOTTED_DATE_RE = re.compile(r"(?<!\d)(?P<y>\d{4})[.\-](?P<m>\d{1,2})[.\-](?P<d>\d{1,2})(?!\d)")


@dataclass
class IntakeItem:
    """One scanned raw file and the record we would write for it."""

    path: Path
    rel_path: str
    segments: list[str]
    content_hash: str
    content_id: str
    creator_id: Optional[str]
    group: str
    source_type: str
    source_platform: str
    file_type: str
    published_at: Optional[datetime]
    published_at_source: str
    record_path: Path
    status: str  # "new" | "duplicate" | "exists"


@dataclass
class IntakeResult:
    """Aggregate outcome of a scan / write pass."""

    scanned: int = 0
    new: int = 0
    duplicates: int = 0
    existing: int = 0
    written: int = 0
    items: list[IntakeItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    by_group: dict[str, int] = field(default_factory=dict)
    by_source_type: dict[str, int] = field(default_factory=dict)
    by_file_type: dict[str, int] = field(default_factory=dict)
    by_published_source: dict[str, int] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    """SHA-256 of a file's bytes, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_raw_files(
    raw_root: Path, suffixes: Iterable[str] = _SUPPORTED_SUFFIXES
) -> list[Path]:
    """Return all image/PDF files under ``raw_root``, sorted for determinism."""
    wanted = {s.lower() for s in suffixes}
    return [
        p
        for p in sorted(raw_root.rglob("*"))
        if p.is_file() and p.suffix.lower() in wanted
    ]


def _segments(path: Path, raw_root: Path) -> list[str]:
    return list(path.relative_to(raw_root).parts)


def infer_creator(segments: list[str]) -> Optional[str]:
    """First path segment is the creator, unless it is an infra/platform bucket."""
    if not segments:
        return None
    first = segments[0]
    return None if first in _NON_CREATOR_DIRS else first


def infer_source_platform(segments: list[str]) -> str:
    """Map first segment to an origin platform; local backfill otherwise."""
    if segments and segments[0] in _PLATFORM_DIRS:
        return segments[0]
    return "local"


def infer_source_type(segments: list[str]) -> str:
    """Pick a canonical source_type from directory signals, else 'unclassified'."""
    for seg in segments:
        if seg in _DIR_SOURCE_TYPE:
            return _DIR_SOURCE_TYPE[seg]
    if "upload" in segments:
        return "manual_upload"
    joined = "/".join(segments)
    for keyword, source_type in _KEYWORD_SOURCE_TYPE:
        if keyword in joined:
            return source_type
    return "unclassified"


def infer_file_type(path: Path) -> str:
    return "pdf" if path.suffix.lower() in PDF_SUFFIXES else "image"


def infer_published_at(path: Path) -> tuple[Optional[datetime], str]:
    """Parse a publish time from the filename; fall back to file mtime.

    Returns (datetime | None, source_label) where source_label is one of
    filename_datetime / filename_date / filename_dotted_date / file_mtime /
    unknown. All filename-derived times are tagged Beijing (UTC+8), matching the
    Feishu importer convention.
    """
    name = path.name

    m = _FNAME_DATETIME_RE.search(name)
    if m:
        try:
            dt = datetime.strptime(m.group("date") + m.group("time"), "%Y%m%d%H%M")
            return dt.replace(tzinfo=BEIJING_TZ), "filename_datetime"
        except ValueError:
            pass

    m = _FNAME_DATE_RE.search(name)
    if m:
        try:
            dt = datetime.strptime(m.group("date"), "%Y%m%d")
            return dt.replace(tzinfo=BEIJING_TZ), "filename_date"
        except ValueError:
            pass

    m = _FNAME_DOTTED_DATE_RE.search(name)
    if m:
        try:
            dt = datetime(
                int(m.group("y")), int(m.group("m")), int(m.group("d")), tzinfo=BEIJING_TZ
            )
            return dt, "filename_dotted_date"
        except ValueError:
            pass

    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=BEIJING_TZ), "file_mtime"
    except OSError:
        return None, "unknown"


def plan_intake(
    raw_root: Path, data_root: Path, suffixes: Iterable[str] = _SUPPORTED_SUFFIXES
) -> IntakeResult:
    """Scan raw_root and compute the record we'd write for each file (no writes)."""
    result = IntakeResult()
    seen_hashes: set[str] = set()

    for path in iter_raw_files(raw_root, suffixes):
        result.scanned += 1
        segments = _segments(path, raw_root)
        content_hash = sha256_file(path)
        content_id = f"local_{content_hash[:24]}"
        creator_id = infer_creator(segments)
        group = creator_id or (segments[0] if segments else "misc")
        source_type = infer_source_type(segments)
        source_platform = infer_source_platform(segments)
        file_type = infer_file_type(path)
        published_at, published_at_source = infer_published_at(path)
        record_path = data_root / "F0_intake" / "local" / group / f"{content_id}.json"

        if content_hash in seen_hashes:
            status = "duplicate"
            result.duplicates += 1
        elif record_path.exists():
            status = "exists"
            result.existing += 1
            seen_hashes.add(content_hash)
        else:
            status = "new"
            result.new += 1
            seen_hashes.add(content_hash)
            result.by_group[group] = result.by_group.get(group, 0) + 1
            result.by_source_type[source_type] = result.by_source_type.get(source_type, 0) + 1
            result.by_file_type[file_type] = result.by_file_type.get(file_type, 0) + 1
            result.by_published_source[published_at_source] = (
                result.by_published_source.get(published_at_source, 0) + 1
            )

        result.items.append(
            IntakeItem(
                path=path,
                rel_path=str(path),
                segments=segments,
                content_hash=content_hash,
                content_id=content_id,
                creator_id=creator_id,
                group=group,
                source_type=source_type,
                source_platform=source_platform,
                file_type=file_type,
                published_at=published_at,
                published_at_source=published_at_source,
                record_path=record_path,
                status=status,
            )
        )

    return result


def build_record(item: IntakeItem, collected_at: datetime) -> ContentRecord:
    """Construct the canonical ContentRecord for one intake item."""
    origin_hint = "feishu_export" if "img_v3" in item.path.name else "local_file"
    return ContentRecord(
        content_id=item.content_id,
        source_type=item.source_type,
        source_platform=item.source_platform,
        creator_id=item.creator_id,
        creator_name=item.creator_id,
        published_at=item.published_at,
        collected_at=collected_at,
        title=item.path.name,
        raw_path=item.rel_path,
        file_type=item.file_type,
        metadata={
            "registered_via": "local_raw_intake",
            "content_sha256": item.content_hash,
            "published_at_source": item.published_at_source,
            "origin_hint": origin_hint,
            "rel_segments": item.segments,
        },
        external_source_id=f"local_raw:{item.content_hash}",
        dedupe_fingerprint=item.content_hash,
        language="zh",
    )


def run_intake(
    raw_root: Path,
    data_root: Path,
    *,
    dry_run: bool = True,
    collected_at: Optional[datetime] = None,
    suffixes: Iterable[str] = _SUPPORTED_SUFFIXES,
) -> IntakeResult:
    """Plan the intake, validate every new record, and optionally write them.

    Records are validated (constructed) even in dry-run mode so schema problems
    surface before any disk write. Only ``status == "new"`` items are written.
    """
    collected_at = collected_at or datetime.now(timezone.utc)
    result = plan_intake(raw_root, data_root, suffixes)

    for item in result.items:
        if item.status != "new":
            continue
        try:
            record = build_record(item, collected_at)
        except Exception as exc:  # pydantic ValidationError et al.
            result.errors.append(f"{item.path}: {type(exc).__name__}: {exc}")
            continue
        if not dry_run:
            item.record_path.parent.mkdir(parents=True, exist_ok=True)
            item.record_path.write_text(
                record.model_dump_json(indent=2), encoding="utf-8"
            )
            result.written += 1

    return result
