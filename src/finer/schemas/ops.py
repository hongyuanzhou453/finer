"""Observability schemas — run ledger + alerts (Phase 0 C5 / OPS-5).

Backend-only (no contracts.ts mirror). ``RunLedgerEntry`` is one appended line
per drive/settle pass under ``data/run_state/ledger/``; ``AlertEvent`` is the
payload sent to the ops webhook. Error entries reuse the Line F canonical error
envelope field set (code/message/stage/operation/retryable/request_id/fix_hint)
rather than inventing a new error shape.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from finer.utils.time import now_utc

AlertType = Literal["heartbeat_timeout", "failure_rate", "budget_exceeded", "test"]
AlertSeverity = Literal["info", "warning", "critical"]


class LedgerErrorEntry(BaseModel):
    """One error in a ledger row — the Line F canonical envelope fields, reused."""

    code: str = Field(..., description="Canonical error code or exception type")
    message: str = Field(..., description="Sanitized, human-readable error message")
    stage: Optional[str] = Field(None, description="Pipeline stage that raised it")
    operation: Optional[str] = Field(None, description="Operation in flight when it failed")
    retryable: bool = Field(True, description="Whether the caller may safely retry")
    request_id: Optional[str] = Field(None, description="Correlation id, if any")
    fix_hint: Optional[str] = Field(None, description="Actionable remediation hint")
    content_id: Optional[str] = Field(None, description="Affected content id, if item-scoped")


class RunLedgerEntry(BaseModel):
    """One drive/settle pass, appended to the daily ledger JSONL."""

    run_id: str = Field(..., description="Run identifier (from the drive/settle report)")
    job_type: str = Field(..., description="'pipeline_drive' | 'settle'")
    ts: str = Field(default_factory=lambda: now_utc().isoformat(), description="Row write time (aware UTC ISO)")
    status: str = Field(..., description="'completed' | 'failed' | 'skipped_locked'")
    duration_s: float = Field(0.0, ge=0, description="Wall-clock seconds for the pass")
    tokens_spent: int = Field(0, ge=0, description="LLM tokens consumed this pass (usage accumulator delta)")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Compact report summary")
    errors: List[LedgerErrorEntry] = Field(default_factory=list, description="Per-item failures, canonical shape")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class AlertEvent(BaseModel):
    """An operational alert delivered to the ops webhook."""

    alert_type: AlertType = Field(..., description="Which condition tripped")
    severity: AlertSeverity = Field(..., description="info | warning | critical")
    title: str = Field(..., description="Short one-line headline")
    message: str = Field(..., description="What happened (numbers, no secrets)")
    fix_hint: str = Field(..., description="What the operator should do next")
    context: Dict[str, Any] = Field(default_factory=dict, description="Structured detail (ids, counts)")
    ts: str = Field(default_factory=lambda: now_utc().isoformat(), description="Alert time (aware UTC ISO)")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
