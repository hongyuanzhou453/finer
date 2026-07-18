"""DriveRunConfig — parameters for one incremental pipeline-drive pass.

Backend-only (no contracts.ts mirror): the driver is not a frontend surface.
The config is recorded in each DriveReport (and thus pipeline_runs.summary_json)
so a pass is replayable from its own logged parameters. Phase 0 card C2 / OPS-2.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# Stages the driver can run, in canonical order. 'settle' is the F8 batch step
# (settle_actions); the F1/F2/F5 stages are the per-content fill-only steps.
DRIVE_STAGES: tuple[str, ...] = ("f1", "f2", "f5", "settle")

# Known import channels. 'all' is the sentinel for "every channel" (no filter).
# Specific values match stage_status.source_channel (written by F0IndexWriter).
DRIVE_CHANNELS: tuple[str, ...] = (
    "all",
    "broker",
    "feishu",
    "local",
    "wechat",
    "wechat_channels",
    "bilibili",
    "nlm",
)


class DriveRunConfig(BaseModel):
    """Scope + throughput knobs for one ``drive_once`` pass.

    Defaults reproduce the legacy behaviour exactly: every channel, all stages,
    serial, unlimited — so an un-parameterised drive is unchanged.
    """

    channel: str = Field(
        "all",
        description="import-channel filter; 'all' drives every channel (matches stage_status.source_channel)",
    )
    stages: List[str] = Field(
        default_factory=lambda: list(DRIVE_STAGES),
        description="ordered stage whitelist; a stage runs only if listed (e.g. ['f1','f2'] stops before F5/settle)",
    )
    concurrency: int = Field(
        1,
        ge=1,
        description="parallel workers; the batch_runner (C3) honors this, the v1 driver is serial",
    )
    max_items: Optional[int] = Field(
        None,
        ge=1,
        description="cap on content items discovered per pass (None = unlimited)",
    )

    @field_validator("channel")
    @classmethod
    def _known_channel(cls, v: str) -> str:
        if v not in DRIVE_CHANNELS:
            raise ValueError(f"unknown channel {v!r}; expected one of {DRIVE_CHANNELS}")
        return v

    @field_validator("stages")
    @classmethod
    def _known_stages(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("stages must not be empty")
        unknown = [s for s in v if s not in DRIVE_STAGES]
        if unknown:
            raise ValueError(f"unknown stage(s) {unknown}; expected subset of {list(DRIVE_STAGES)}")
        return v

    def runs(self, stage: str) -> bool:
        """True if ``stage`` (one of DRIVE_STAGES) is in this pass's whitelist."""
        return stage in self.stages

    @property
    def all_channels(self) -> bool:
        return self.channel == "all"
