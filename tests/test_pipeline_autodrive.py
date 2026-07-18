"""Tests for the background pipeline auto-driver (roadmap direction ①).

Covers the scheduler wiring only — the drive_once orchestration itself is
covered by test_pipeline_driver.py. drive_once is faked here so no LLM calls or
data writes happen. The server-lifespan test runs with auto-drive DISABLED
(default), proving start/stop wiring stays inert unless explicitly opted in.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from finer.config import PipelineAutoDriveConfig
from finer.pipeline.autodrive import PipelineAutoDriver


class _FakeReport:
    """Stand-in for driver.DriveReport with the attrs run_pass touches."""

    def __init__(self, f5: int = 0) -> None:
        self.scanned = 1
        self.f1_ran = 0
        self.f2_ran = 0
        self.f5_ran = f5
        self.failures: list = []
        self.reconciled: list = []

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "f1_ran": self.f1_ran,
            "f2_ran": self.f2_ran,
            "f5_ran": self.f5_ran,
            "failures": self.failures,
        }


def _cfg(**kw) -> PipelineAutoDriveConfig:
    base = dict(
        enabled=True,
        interval_seconds=3600,
        limit=0,
        run_settle=False,
        initial_delay_seconds=0.0,
    )
    base.update(kw)
    return PipelineAutoDriveConfig(**base)


async def test_disabled_start_is_noop():
    driver = PipelineAutoDriver(_cfg(enabled=False))
    await driver.start()
    assert driver.running is False
    assert driver._task is None
    await driver.stop()  # must not raise when never started


async def test_run_pass_records_report(monkeypatch):
    driver = PipelineAutoDriver(_cfg())

    def fake_drive_once(*, limit, run_settle, dry_run):
        assert dry_run is False  # auto-drive always applies
        assert limit == 0 and run_settle is False  # config threaded through
        return _FakeReport(f5=3)

    monkeypatch.setattr("finer.pipeline.driver.drive_once", fake_drive_once)

    result = await driver.run_pass()
    assert result == driver.last_report
    assert driver.last_report["f5_ran"] == 3
    assert driver.runs == 1
    assert driver.last_error is None
    assert driver.last_run_at is not None


async def test_run_pass_isolates_failure(monkeypatch):
    driver = PipelineAutoDriver(_cfg())

    def boom(*, limit, run_settle, dry_run):
        raise RuntimeError("f2 exploded")

    monkeypatch.setattr("finer.pipeline.driver.drive_once", boom)

    result = await driver.run_pass()
    assert result is None
    assert driver.runs == 1
    assert "RuntimeError" in driver.last_error
    assert "f2 exploded" in driver.last_error


async def test_loop_runs_then_stops_cleanly(monkeypatch):
    calls: list[int] = []

    def fake_drive_once(*, limit, run_settle, dry_run):
        calls.append(1)
        return _FakeReport()

    monkeypatch.setattr("finer.pipeline.driver.drive_once", fake_drive_once)

    driver = PipelineAutoDriver(_cfg(interval_seconds=0, initial_delay_seconds=0.0))
    await driver.start()
    assert driver.running is True

    for _ in range(200):  # up to ~2s
        if len(calls) >= 2:
            break
        await asyncio.sleep(0.01)

    assert len(calls) >= 2, "loop should have run drive_once repeatedly"

    await driver.stop()
    assert driver.running is False
    assert driver._task is None


async def test_double_start_spawns_one_task(monkeypatch):
    monkeypatch.setattr(
        "finer.pipeline.driver.drive_once",
        lambda **kw: _FakeReport(),
    )
    driver = PipelineAutoDriver(_cfg(interval_seconds=3600, initial_delay_seconds=3600))
    await driver.start()
    first = driver._task
    await driver.start()  # idempotent while running
    assert driver._task is first
    await driver.stop()


async def test_status_shape():
    driver = PipelineAutoDriver(_cfg(enabled=False, interval_seconds=120, limit=5))
    status = driver.status()
    assert status["enabled"] is False
    assert status["running"] is False
    assert status["interval_seconds"] == 120
    assert status["limit"] == 5
    assert status["runs"] == 0
    assert status["last_report"] is None


def test_server_autodrive_endpoint_default_disabled(monkeypatch):
    # Ensure no ambient opt-in leaks in from the environment.
    monkeypatch.delenv("FINER_PIPELINE_AUTODRIVE", raising=False)
    from finer.api.server import create_app

    # `with` triggers the FastAPI lifespan: driver is initialized + started
    # (a no-op because disabled) and stopped cleanly on exit.
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        res = client.get("/api/system/autodrive")
        assert res.status_code == 200
        body = res.json()
        assert body["enabled"] is False
        assert body["running"] is False
