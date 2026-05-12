"""F0 Project Memory -- SQLite index schema contract.

This module defines the STRUCTURE of the F0 index only.
Actual table creation requires user confirmation and is not part of A1 first round.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal


class F0IndexSchema:
    """F0 project memory SQLite schema contract."""

    # content_records table
    CONTENT_RECORDS_TABLE: ClassVar[str] = "content_records"
    CONTENT_RECORDS_COLUMNS: ClassVar[dict[str, str]] = {
        "content_id": "TEXT PRIMARY KEY",
        "source_type": "TEXT NOT NULL",
        "source_platform": "TEXT NOT NULL",
        "creator_id": "TEXT",
        "creator_name": "TEXT",
        "title": "TEXT",
        "raw_path": "TEXT NOT NULL",
        "file_type": "TEXT NOT NULL",
        "published_at": "TEXT",
        "collected_at": "TEXT NOT NULL",
        "source_url": "TEXT",
        "external_source_id": "TEXT",
        "dedupe_fingerprint": "TEXT",
        "manifest_path": "TEXT",
        "import_run_id": "TEXT",
        "created_at": "TEXT NOT NULL",
        "updated_at": "TEXT NOT NULL",
    }

    # import_runs table
    IMPORT_RUNS_TABLE: ClassVar[str] = "import_runs"
    IMPORT_RUNS_COLUMNS: ClassVar[dict[str, str]] = {
        "run_id": "TEXT PRIMARY KEY",
        "source_channel": "TEXT NOT NULL",
        "started_at": "TEXT NOT NULL",
        "finished_at": "TEXT",
        "status": "TEXT NOT NULL",
        "records_created": "INTEGER DEFAULT 0",
        "records_skipped": "INTEGER DEFAULT 0",
        "error_code": "TEXT",
        "error_message": "TEXT",
        "request_id": "TEXT",
        "retryable": "INTEGER DEFAULT 0",
        "fix_hint": "TEXT",
    }

    # index_metadata table
    INDEX_METADATA_TABLE: ClassVar[str] = "index_metadata"
    INDEX_METADATA_COLUMNS: ClassVar[dict[str, str]] = {
        "key": "TEXT PRIMARY KEY",
        "value": "TEXT NOT NULL",
    }


@dataclass(frozen=True)
class F0IndexQuery:
    """Canonical query shape for F0 index."""

    source_type: str | None = None
    source_platform: str | None = None
    creator_id: str | None = None
    sort_by: str = "collected_at"
    sort_order: str = "desc"
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class F0IndexResult:
    """Paginated result from F0 index query."""

    records: list[dict]
    total_count: int
    page: int
    page_size: int
    has_more: bool


@dataclass(frozen=True)
class F0IndexHealth:
    """F0 index health status for Import Console display."""

    status: Literal["healthy", "stale", "missing", "rebuilding"]
    record_count: int
    last_rebuild_at: str | None
    last_rebuild_duration_ms: int | None
    manifest_count_on_disk: int
    drift: int
    db_path: str
    db_size_bytes: int

    @property
    def needs_rebuild(self) -> bool:
        return self.status in ("missing", "stale") or self.drift != 0
