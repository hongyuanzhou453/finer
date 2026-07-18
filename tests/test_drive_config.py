"""Tests for DriveRunConfig (Phase 0 C2 / OPS-2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from finer.schemas.drive_config import DRIVE_STAGES, DriveRunConfig


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
