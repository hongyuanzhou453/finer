"""BatchRunManifest — durable state of one concurrent batch pass (Phase 0 C3 / OPS-3).

Backend-only (no contracts.ts mirror): the batch runner is a throughput tool, not
a frontend surface. One manifest is written per ``batch_id`` under
``data/run_state/`` and rewritten (snapshot) after every item so an interrupted
run is replayable/resumable from its own logged state; the append-only checkpoint
sidecar (``<batch_id>.checkpoint.jsonl``) is the authority on which items are done.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from finer.utils.time import now_utc

# Terminal + in-flight states for one batch pass. 'budget_exceeded' and
# 'quota_tripped' are the two circuit-breaker stops (non-zero exit); 'interrupted'
# is a manifest left 'running' by a hard kill and picked up on resume.
BatchRunStatus = Literal[
    "running",
    "completed",
    "budget_exceeded",
    "quota_tripped",
    "interrupted",
    "failed",
]


class BatchItemOutcome(BaseModel):
    """One item's terminal record, mirrored into the checkpoint jsonl."""

    content_id: str = Field(..., description="Item identifier (F0 content_id)")
    status: Literal["done", "failed", "skipped"] = Field(
        ..., description="done = processed this run; skipped = already complete; failed = isolated error"
    )
    error_code: Optional[str] = Field(None, description="Exception type on failure")
    error_message: Optional[str] = Field(None, description="Sanitized failure message (truncated)")


class BatchRunManifest(BaseModel):
    """Durable summary of one concurrent batch pass.

    Field set matches the C3 card contract (run_id/total/done/failed/skipped/
    budget_spent_tokens/checkpoint_cursor/started_at/finished_at) plus the scope
    knobs and circuit-breaker outcome needed to make a stop self-describing.
    """

    run_id: str = Field(..., description="Unique id for this concrete pass (one per invocation)")
    batch_id: str = Field(
        ...,
        description="Stable work-set id (e.g. 'f1_broker'); the resume key — same batch_id reuses the checkpoint",
    )
    stage: str = Field(..., description="Pipeline stage this batch fills (e.g. 'f1')")

    total: int = Field(0, description="Items in the discovered work set (before resume filtering)")
    done: int = Field(0, description="Items processed to completion this run")
    failed: int = Field(0, description="Items whose processing raised (isolated, not fatal)")
    skipped: int = Field(0, description="Items skipped (already complete or resumed from checkpoint)")

    budget_tokens: Optional[int] = Field(
        None, description="Hard token budget for this pass (None = unbounded)"
    )
    budget_spent_tokens: int = Field(
        0, description="Cumulative LLM tokens consumed this run (from the in-process usage accumulator)"
    )
    concurrency: int = Field(1, ge=1, description="Max in-flight workers for this pass")
    quota_strikes: int = Field(
        5, ge=1, description="Consecutive 401/402/429 count that trips the circuit breaker"
    )

    checkpoint_cursor: int = Field(
        0, description="Count of items recorded in the checkpoint (done+failed+skipped persisted)"
    )
    status: BatchRunStatus = Field("running", description="In-flight or terminal state of this pass")
    stop_reason: Optional[str] = Field(
        None, description="Human-readable reason for a circuit-breaker / early stop"
    )
    resume_command: Optional[str] = Field(
        None, description="Copy-paste command to continue from the checkpoint after a stop"
    )

    started_at: str = Field(default_factory=lambda: now_utc().isoformat(), description="Run start (aware UTC ISO)")
    finished_at: Optional[str] = Field(None, description="Run end (aware UTC ISO); None while running")

    failures: List[BatchItemOutcome] = Field(
        default_factory=list, description="Per-item failures for this run (isolated)"
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
