"""Tests for the concurrent batch execution pool (Phase 0 C3 / OPS-3).

Mechanics only — no real LLM. ``process_item`` and the usage/quota readers are
injected, so concurrency, checkpoint resume, the token budget and the quota
circuit breaker are all exercised deterministically.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from finer.pipeline.batch_runner import (
    SKIPPED,
    load_checkpoint,
    run_batch_sync,
)

ZERO_QUOTA = lambda: {"consecutive": 0, "last_status": None}  # noqa: E731
ZERO_USAGE = lambda: {"total_tokens": 0}  # noqa: E731


def _ids(n: int) -> List[str]:
    return [f"c{i}" for i in range(n)]


def test_processes_all_items_and_writes_manifest(tmp_path: Path) -> None:
    seen: List[str] = []
    manifest = run_batch_sync(
        items=_ids(5),
        process_item=lambda cid: seen.append(cid),
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        concurrency=4,
        reset_telemetry=False,
        usage_reader=ZERO_USAGE,
        quota_reader=ZERO_QUOTA,
    )
    assert manifest.status == "completed"
    assert manifest.total == 5 and manifest.done == 5 and manifest.failed == 0
    assert sorted(seen) == sorted(_ids(5))
    assert manifest.finished_at is not None

    # manifest snapshot persisted with the full field set
    on_disk = json.loads((tmp_path / "t.manifest.json").read_text())
    for key in (
        "run_id", "batch_id", "stage", "total", "done", "failed", "skipped",
        "budget_spent_tokens", "checkpoint_cursor", "started_at", "finished_at",
    ):
        assert key in on_disk


def test_failure_isolation(tmp_path: Path) -> None:
    def proc(cid: str) -> None:
        if cid == "c2":
            raise ValueError("boom")

    manifest = run_batch_sync(
        items=_ids(5),
        process_item=proc,
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        concurrency=2,
        reset_telemetry=False,
        usage_reader=ZERO_USAGE,
        quota_reader=ZERO_QUOTA,
    )
    assert manifest.status == "completed"  # one bad item does not fail the batch
    assert manifest.done == 4 and manifest.failed == 1
    assert manifest.failures[0].content_id == "c2"
    assert manifest.failures[0].error_code == "ValueError"
    assert manifest.failures[0].status == "failed"


def test_skipped_sentinel_counted_and_checkpointed(tmp_path: Path) -> None:
    manifest = run_batch_sync(
        items=_ids(4),
        process_item=lambda cid: SKIPPED if cid in ("c0", "c1") else "done",
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        reset_telemetry=False,
        usage_reader=ZERO_USAGE,
        quota_reader=ZERO_QUOTA,
    )
    assert manifest.skipped == 2 and manifest.done == 2
    # skipped items are still recorded so a resume won't revisit them
    assert set(load_checkpoint(tmp_path, "t")) == set(_ids(4))


def test_checkpoint_resume_no_duplicate(tmp_path: Path) -> None:
    seen: List[str] = []

    def proc(cid: str) -> None:
        seen.append(cid)

    # Run 1: cap at 3 → only 3 of 5 settled.
    m1 = run_batch_sync(
        items=_ids(5), process_item=proc, stage="f1", batch_id="t",
        run_state_dir=tmp_path, max_items=3, concurrency=1,
        reset_telemetry=False, usage_reader=ZERO_USAGE, quota_reader=ZERO_QUOTA,
    )
    assert m1.done == 3
    assert len(load_checkpoint(tmp_path, "t")) == 3

    # Run 2: resume → only the remaining 2 processed, none reprocessed.
    m2 = run_batch_sync(
        items=_ids(5), process_item=proc, stage="f1", batch_id="t",
        run_state_dir=tmp_path, concurrency=1,
        reset_telemetry=False, usage_reader=ZERO_USAGE, quota_reader=ZERO_QUOTA,
    )
    assert m2.skipped == 3  # resumed-from-checkpoint
    assert m2.done == 2
    assert sorted(seen) == sorted(_ids(5))  # each id processed exactly once
    assert len(seen) == 5  # no duplicates
    assert len(load_checkpoint(tmp_path, "t")) == 5


def test_budget_hard_cap_trips_and_stops(tmp_path: Path) -> None:
    seen: List[str] = []

    class RisingUsage:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self) -> Dict[str, int]:
            self.n += 1
            return {"total_tokens": self.n * 100}

    manifest = run_batch_sync(
        items=_ids(10),
        process_item=lambda cid: seen.append(cid),
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        concurrency=1,  # deterministic budget accrual
        budget_tokens=250,
        reset_telemetry=False,
        usage_reader=RisingUsage(),
        quota_reader=ZERO_QUOTA,
    )
    assert manifest.status == "budget_exceeded"
    assert manifest.budget_spent_tokens >= 250
    assert manifest.done == 3  # 100, 200, 300 → trips on the 3rd
    assert len(seen) == 3  # scheduling stopped; the other 7 never ran
    assert manifest.resume_command
    assert "budget" in (manifest.stop_reason or "")


def test_quota_circuit_breaker_trips(tmp_path: Path) -> None:
    class RisingQuota:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self) -> Dict[str, Any]:
            self.n += 1
            return {"consecutive": self.n, "last_status": 429}

    manifest = run_batch_sync(
        items=_ids(10),
        process_item=lambda cid: None,
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        concurrency=1,
        quota_strikes=3,
        reset_telemetry=False,
        usage_reader=ZERO_USAGE,
        quota_reader=RisingQuota(),
    )
    assert manifest.status == "quota_tripped"
    assert manifest.resume_command
    assert "quota" in (manifest.stop_reason or "")
    assert manifest.done == 3  # consecutive 1,2,3 → trips on the 3rd


def test_dry_run_processes_nothing(tmp_path: Path) -> None:
    seen: List[str] = []
    manifest = run_batch_sync(
        items=_ids(5),
        process_item=lambda cid: seen.append(cid),
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        dry_run=True,
        reset_telemetry=False,
        usage_reader=ZERO_USAGE,
        quota_reader=ZERO_QUOTA,
    )
    assert manifest.status == "completed"
    assert seen == []  # nothing ran
    assert "dry-run" in (manifest.stop_reason or "")
    assert not (tmp_path / "t.checkpoint.jsonl").exists()


def test_concurrency_is_bounded(tmp_path: Path) -> None:
    lock = threading.Lock()
    state = {"cur": 0, "peak": 0}

    def slow(cid: str) -> None:
        with lock:
            state["cur"] += 1
            state["peak"] = max(state["peak"], state["cur"])
        time.sleep(0.03)
        with lock:
            state["cur"] -= 1

    run_batch_sync(
        items=_ids(9),
        process_item=slow,
        stage="f1",
        batch_id="t",
        run_state_dir=tmp_path,
        concurrency=3,
        reset_telemetry=False,
        usage_reader=ZERO_USAGE,
        quota_reader=ZERO_QUOTA,
    )
    assert state["peak"] <= 3  # never exceeds the semaphore
    assert state["peak"] >= 2  # and genuinely runs in parallel
