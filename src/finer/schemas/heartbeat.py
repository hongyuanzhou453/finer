"""HeartbeatState — liveness record for a long-running driver/watch loop (C4 / OPS-4).

Backend-only (no contracts.ts mirror). Written to ``data/run_state/heartbeat.json``
at the end of every watch pass so an external supervisor (launchd KeepAlive, an
alerting job in C5) can tell whether the driver is alive and when it last made a
pass. ``lock_holder`` records whether this pass actually held the single-flight
drive lock (False = the pass was ``skipped_locked`` because another instance held
it), so a second instance is observably distinguishable from a stalled one.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from finer.utils.time import now_utc


class HeartbeatState(BaseModel):
    """One liveness snapshot for a resident driver/watch process."""

    pid: int = Field(..., description="OS process id of the watch loop")
    job_type: str = Field(..., description="Which loop: 'pipeline_drive' | 'feishu_watch'")
    started_at: str = Field(..., description="When this process's loop started (aware UTC ISO)")
    last_pass_at: str = Field(
        default_factory=lambda: now_utc().isoformat(),
        description="End time of the most recent pass (aware UTC ISO)",
    )
    cycles: int = Field(0, ge=0, description="Passes completed since start (monotonic)")
    interval_seconds: Optional[int] = Field(
        None, description="Configured poll interval; a supervisor flags stale if age > 2×interval"
    )
    lock_holder: bool = Field(
        True,
        description="True if this pass held the single-flight drive lock; False = skipped_locked (another instance had it)",
    )
    last_pass_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Compact summary of the last pass (stage counts + failure count)",
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
