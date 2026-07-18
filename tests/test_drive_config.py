"""Tests for DriveRunConfig (Phase 0 C2 / OPS-2)."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from finer.schemas.drive_config import DRIVE_CHANNELS, DRIVE_STAGES, DriveRunConfig
from finer.schemas.import_receipt import SourceChannel


def test_defaults_reproduce_legacy_behaviour() -> None:
    cfg = DriveRunConfig()
    assert cfg.channel == "all"
    assert cfg.stages == list(DRIVE_STAGES)
    assert cfg.concurrency == 1
    assert cfg.max_items is None
    assert cfg.all_channels is True
    for stage in DRIVE_STAGES:
        assert cfg.runs(stage)


def test_runs_reflects_whitelist() -> None:
    cfg = DriveRunConfig(stages=["f1", "f2"])
    assert cfg.runs("f1") and cfg.runs("f2")
    assert not cfg.runs("f5")
    assert not cfg.runs("settle")


def test_broker_channel_is_valid_and_not_all() -> None:
    cfg = DriveRunConfig(channel="broker")
    assert cfg.channel == "broker"
    assert cfg.all_channels is False


def test_unknown_channel_rejected() -> None:
    with pytest.raises(ValidationError):
        DriveRunConfig(channel="brokr")


def test_drive_channels_derived_from_source_channel() -> None:
    """R1 drift guard: the driver's channel set must stay in lock-step with the
    canonical ``SourceChannel`` Literal in both directions.

    ``stage_status.source_channel`` stores ``receipt.source_channel`` verbatim,
    so any drivable channel that is not a real ``SourceChannel`` value (the old
    'local'/'nlm' shorthands) is a dead knob that matches 0 rows, and any intake
    channel missing from ``DRIVE_CHANNELS`` is undrivable. This guard catches the
    pydantic↔pydantic hand-copy that the contracts.ts drift check cannot see.
    """
    canonical = set(get_args(SourceChannel))
    drivable = set(DRIVE_CHANNELS) - {"all"}
    assert drivable == canonical, (
        "DRIVE_CHANNELS drifted from SourceChannel; derive it via "
        "get_args(SourceChannel), do not hand-copy channel names"
    )
    assert "all" in DRIVE_CHANNELS  # sentinel present
    assert "all" not in canonical  # and not itself an intake channel


def test_canonical_local_and_nlm_channels_are_valid() -> None:
    """The two values that used to be mis-spelled must now pass under their
    canonical names and reach the driver filter (R1)."""
    assert DriveRunConfig(channel="local_upload").channel == "local_upload"
    assert DriveRunConfig(channel="notebooklm").channel == "notebooklm"


@pytest.mark.parametrize("shorthand", ["local", "nlm"])
def test_legacy_channel_shorthand_rejected(shorthand: str) -> None:
    """Pre-R1 shorthand must not silently pass — it never matched any row."""
    with pytest.raises(ValidationError):
        DriveRunConfig(channel=shorthand)


def test_unknown_stage_rejected() -> None:
    with pytest.raises(ValidationError):
        DriveRunConfig(stages=["f1", "f9"])


def test_empty_stages_rejected() -> None:
    with pytest.raises(ValidationError):
        DriveRunConfig(stages=[])


def test_max_items_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        DriveRunConfig(max_items=0)
    assert DriveRunConfig(max_items=1).max_items == 1


def test_model_dump_roundtrips() -> None:
    cfg = DriveRunConfig(channel="broker", stages=["f1", "f2"], max_items=5)
    dumped = cfg.model_dump()
    assert dumped["channel"] == "broker"
    assert dumped["stages"] == ["f1", "f2"]
    assert dumped["max_items"] == 5
    assert DriveRunConfig(**dumped) == cfg
