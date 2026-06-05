"""Unified F0 ImportReceipt contract (shared across all six intake channels).

This is the single receipt every F0 channel adapter (feishu / local upload /
NotebookLM / wechat / wechat_channels / bilibili) emits after an import attempt.
It supersedes the ad-hoc per-channel receipt dicts (e.g. wechat_adapter's
``_build_wechat_channels_receipt``) while remaining lossless-projectable into the
frontend ``ImportRun`` row shape consumed by the Import Console.

Design goals
------------
1. One receipt model for all six channels.
2. ``to_import_run()`` projects onto the exact ``import_runs`` table columns the
   Import Console already reads (run_id / source_channel / started_at /
   finished_at / status / records_created / records_skipped / error_code /
   error_message / request_id / retryable / fix_hint) with zero drift.
3. Carries the raw-archive provenance (sha256 + paths) and dedupe identity so a
   channel never has to invent its own receipt shape again.

Security
--------
No field may carry a token, secret, password, cookie, authorization header, or
api_key. The error envelope is the canonical Line F shape and is sanitized at
the error layer, not here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finer.utils.time import ensure_aware_utc, now_utc

# Canonical intake channel set. ``source_channel`` is the coarse routing key the
# Import Console groups by; ``source_kind`` (below) is the finer per-channel kind.
SourceChannel = Literal[
    "feishu",
    "local_upload",
    "notebooklm",
    "wechat",
    "wechat_channels",
    "bilibili",
]

ImportStatus = Literal["pending", "running", "completed", "skipped", "failed"]


class ImportErrorEnvelope(BaseModel):
    """Line F canonical error envelope, embedded in a failed receipt.

    Mirrors the required Line F fields. Must never contain token/secret/cookie/
    authorization/api_key — sanitization happens at the error layer.
    """

    model_config = ConfigDict(strict=False)

    code: str = Field(..., description="Canonical error code, e.g. F0_INDEX_002")
    message: str = Field(..., description="Human-readable, sanitized error message")
    request_id: str = Field(..., description="Correlates the failure with logs/UI")
    stage: str = Field("F0", description="Pipeline stage that raised the error")
    operation: str = Field(..., description="Operation being performed when it failed")
    retryable: bool = Field(..., description="Whether the caller may safely retry")
    fix_hint: Optional[str] = Field(None, description="Actionable remediation hint for the user")
    source_channel: Optional[SourceChannel] = Field(
        None, description="Originating intake channel (required for F0 import errors)"
    )


class ImportReceipt(BaseModel):
    """Unified result of a single F0 import attempt for one content item.

    Emitted by every channel adapter after writing (or failing to write) a
    ``ContentRecord`` + raw archive. One receipt == one content item attempt.
    """

    model_config = ConfigDict(strict=False)

    # --- run identity ---
    run_id: str = Field(..., description="Import run identifier (stable across the receipt + import_runs row)")
    request_id: Optional[str] = Field(None, description="Request correlation id for tracing")

    # --- routing / classification ---
    source_channel: SourceChannel = Field(..., description="Coarse intake channel for Import Console grouping")
    source_kind: str = Field(
        ...,
        description="Fine-grained per-channel kind (e.g. wechat_channels_video, feishu_chat)",
    )
    stage: Literal["F0"] = Field("F0", description="Always F0; receipts are an intake-only artifact")

    # --- outcome ---
    status: ImportStatus = Field(..., description="Outcome of this import attempt")

    # --- content linkage ---
    content_id: Optional[str] = Field(
        None, description="ContentRecord id produced by this import (None on early failure)"
    )
    external_source_id: Optional[str] = Field(
        None, description="Platform-native id (feishu message_id, bilibili BV号, ...)"
    )
    dedupe_fingerprint: Optional[str] = Field(
        None, description="Hash-based dedupe fingerprint for idempotent re-import"
    )

    # --- timestamps (timezone-aware UTC) ---
    collected_at: datetime = Field(
        default_factory=now_utc, description="When the content was collected/ingested (aware UTC)"
    )
    started_at: datetime = Field(
        default_factory=now_utc, description="When this import attempt started (aware UTC)"
    )
    finished_at: Optional[datetime] = Field(
        None, description="When this import attempt finished (aware UTC); None while running"
    )

    # --- raw archive provenance ---
    raw_sha256: dict[str, str] = Field(
        default_factory=dict,
        description="Map of artifact role -> sha256 hex for archived raw payloads (e.g. {'video': '...'})",
    )
    raw_paths: dict[str, str] = Field(
        default_factory=dict,
        description="Map of artifact role -> filesystem path for archived raw payloads",
    )
    record_path: Optional[str] = Field(
        None, description="Path to the persisted ContentRecord JSON under data/F0_intake/"
    )

    # --- counters (default to single-item semantics) ---
    records_created: int = Field(0, description="Number of new ContentRecords created by this attempt")
    records_skipped: int = Field(0, description="Number of records skipped (e.g. dedupe hit)")

    # --- error envelope (only on failure) ---
    error: Optional[ImportErrorEnvelope] = Field(
        None, description="Canonical Line F error envelope; present only when status == 'failed'"
    )

    @field_validator("collected_at", "started_at", "finished_at", mode="after")
    @classmethod
    def _coerce_aware_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        """Force receipt timestamps to aware UTC; naive inputs are tagged, not shifted."""
        return ensure_aware_utc(value)

    # ------------------------------------------------------------------
    # Frontend projection
    # ------------------------------------------------------------------

    def to_import_run(self) -> dict[str, object]:
        """Project onto the ``import_runs`` row shape the Import Console reads.

        Returns a dict whose keys are exactly the import_runs columns:
        run_id, source_channel, started_at, finished_at, status,
        records_created, records_skipped, error_code, error_message,
        request_id, retryable, fix_hint.

        Lossless: every field here is recoverable from the receipt, and the
        Console never has to read receipt-only fields.
        """
        err = self.error
        request_id = self.request_id or (err.request_id if err else None)
        return {
            "run_id": self.run_id,
            "source_channel": self.source_channel,
            "started_at": _iso_or_none(self.started_at),
            "finished_at": _iso_or_none(self.finished_at),
            "status": self.status,
            "records_created": self.records_created,
            "records_skipped": self.records_skipped,
            "error_code": err.code if err else None,
            "error_message": err.message if err else None,
            "request_id": request_id,
            "retryable": bool(err.retryable) if err else False,
            "fix_hint": err.fix_hint if err else None,
        }


def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None
