"""Concurrent batch execution pool (Phase 0 C3 / OPS-3).

A generic, F-stage-agnostic runner that drives a work-list of content ids through
an injected ``process_item`` callable concurrently, with:

  * an asyncio ``Semaphore`` pool (F1 default 8, matching measured throughput);
  * per-item failure isolation — one broken item never kills the batch;
  * an append-only checkpoint so an interrupted run resumes without reprocessing;
  * a hard **token budget** (read from the in-process usage accumulator in
    ``llm.client``) that stops scheduling once exceeded;
  * a **quota-strike circuit breaker** (consecutive 401/402/403/429 → trip),
    porting the semantics — not the code — of the NAS
    ``rag_system/structured_extract.py`` sweep runner.

The runner is deliberately decoupled from ``pipeline/driver.py``: callers inject a
``process_item`` closure (e.g. wrapping ``driver._default_f1_executor``), so this
module never imports driver internals and driver's main loop stays untouched.

State lives under ``run_state_dir`` keyed by a stable ``batch_id``:
  * ``<batch_id>.checkpoint.jsonl`` — one line per settled item (authority on done);
  * ``<batch_id>.manifest.json``   — a ``BatchRunManifest`` snapshot, rewritten
    after every item so a hard kill leaves a replayable record.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from finer.llm.client import (
    get_quota_state,
    get_usage_counter,
    reset_quota_state,
    reset_usage_counter,
)
from finer.schemas.batch_run import BatchItemOutcome, BatchRunManifest
from finer.utils.time import now_utc

logger = logging.getLogger(__name__)

#: process_item may return this sentinel to mark an item already-complete
#: (counted as skipped, still checkpointed so a resume won't revisit it).
SKIPPED = "skipped"


class BudgetExceeded(Exception):
    """Raised/flagged when cumulative tokens reach the hard budget cap."""


class QuotaTripped(Exception):
    """Raised/flagged when consecutive quota/auth errors trip the breaker."""


# =============================================================================
# Checkpoint + manifest IO (plain files under run_state_dir)
# =============================================================================


def _checkpoint_path(run_state_dir: Path, batch_id: str) -> Path:
    return run_state_dir / f"{batch_id}.checkpoint.jsonl"


def _manifest_path(run_state_dir: Path, batch_id: str) -> Path:
    return run_state_dir / f"{batch_id}.manifest.json"


def load_checkpoint(run_state_dir: Path, batch_id: str) -> Dict[str, str]:
    """Return ``{content_id: status}`` for every already-settled item.

    Tolerant of a partially-written trailing line (a hard kill mid-append):
    unparseable lines are skipped rather than aborting the resume.
    """
    path = _checkpoint_path(run_state_dir, batch_id)
    done: Dict[str, str] = {}
    if not path.exists():
        return done
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn trailing write — ignore
            cid = rec.get("content_id")
            if cid:
                done[cid] = rec.get("status", "done")
    return done


def _append_checkpoint(path: Path, outcome: BatchItemOutcome) -> None:
    """Append one settled item; flush so a kill can't lose an acknowledged item."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "content_id": outcome.content_id,
                    "status": outcome.status,
                    "error_code": outcome.error_code,
                    "ts": now_utc().isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        fh.flush()


def _write_manifest(path: Path, manifest: BatchRunManifest) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic swap so readers never see a half-written manifest


# =============================================================================
# Core pool
# =============================================================================


async def run_batch(
    *,
    items: List[str],
    process_item: Callable[[str], Any],
    stage: str,
    batch_id: str,
    run_state_dir: Path,
    concurrency: int = 8,
    budget_tokens: Optional[int] = None,
    quota_strikes: int = 5,
    max_items: Optional[int] = None,
    resume: bool = True,
    dry_run: bool = False,
    reset_telemetry: bool = True,
    resume_command: Optional[str] = None,
    usage_reader: Callable[[], Dict[str, int]] = get_usage_counter,
    quota_reader: Callable[[], Dict[str, Any]] = get_quota_state,
    run_id: Optional[str] = None,
) -> BatchRunManifest:
    """Drive ``items`` through ``process_item`` concurrently; return the manifest.

    ``process_item`` runs in a worker thread (it is expected to be blocking —
    LLM calls, file IO). It returns :data:`SKIPPED` for an already-complete item,
    anything else for a processed item, and raises to signal an isolated failure.
    Token accounting comes from the ``usage_reader`` (the in-process accumulator);
    the breaker reads consecutive strikes from ``quota_reader``. Both are
    injectable so tests need no real LLM.
    """
    run_state_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = _checkpoint_path(run_state_dir, batch_id)
    manifest_path = _manifest_path(run_state_dir, batch_id)
    run_id = run_id or f"batch_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}"

    already_done = load_checkpoint(run_state_dir, batch_id) if resume else {}
    worklist = [cid for cid in items if cid not in already_done]
    if max_items is not None:
        worklist = worklist[:max_items]

    manifest = BatchRunManifest(
        run_id=run_id,
        batch_id=batch_id,
        stage=stage,
        total=len(items),
        skipped=len(already_done),
        budget_tokens=budget_tokens,
        concurrency=max(1, concurrency),
        quota_strikes=max(1, quota_strikes),
        checkpoint_cursor=len(already_done),
        status="running",
    )

    if dry_run:
        manifest.status = "completed"
        manifest.stop_reason = f"dry-run: {len(worklist)} item(s) would be processed"
        manifest.finished_at = now_utc().isoformat()
        _write_manifest(manifest_path, manifest)
        logger.info(
            "batch %s dry-run: %d discovered, %d already done, %d would process",
            batch_id, len(items), len(already_done), len(worklist),
        )
        return manifest

    if reset_telemetry:
        reset_usage_counter()
        reset_quota_state()

    _write_manifest(manifest_path, manifest)

    semaphore = asyncio.Semaphore(max(1, concurrency))
    stop_event = asyncio.Event()

    def _settle(outcome: BatchItemOutcome) -> None:
        """Persist one settled item and refresh the manifest snapshot.

        Runs only on the event-loop thread (never inside ``to_thread``), so the
        shared manifest/checkpoint mutations need no lock.
        """
        _append_checkpoint(checkpoint_path, outcome)
        if outcome.status == "done":
            manifest.done += 1
        elif outcome.status == "skipped":
            manifest.skipped += 1
        else:
            manifest.failed += 1
            manifest.failures.append(outcome)
        manifest.checkpoint_cursor += 1
        manifest.budget_spent_tokens = int(usage_reader().get("total_tokens") or 0)

        # Circuit breakers — evaluated after every settled item.
        if budget_tokens is not None and manifest.budget_spent_tokens >= budget_tokens:
            if not stop_event.is_set():
                manifest.status = "budget_exceeded"
                manifest.stop_reason = (
                    f"token budget reached: {manifest.budget_spent_tokens} >= {budget_tokens}"
                )
                stop_event.set()
        consecutive = int(quota_reader().get("consecutive") or 0)
        if consecutive >= manifest.quota_strikes:
            if not stop_event.is_set():
                manifest.status = "quota_tripped"
                manifest.stop_reason = (
                    f"quota circuit breaker: {consecutive} consecutive "
                    f"401/402/403/429 (last={quota_reader().get('last_status')})"
                )
                stop_event.set()
        _write_manifest(manifest_path, manifest)

    async def worker(content_id: str) -> None:
        if stop_event.is_set():
            return
        async with semaphore:
            if stop_event.is_set():
                return  # a breaker tripped while we waited for a slot
            try:
                result = await asyncio.to_thread(process_item, content_id)
                status = "skipped" if result == SKIPPED else "done"
                _settle(BatchItemOutcome(content_id=content_id, status=status))
            except Exception as exc:  # noqa: BLE001 — per-item isolation
                logger.warning("batch %s item %s failed: %s", batch_id, content_id, exc)
                _settle(
                    BatchItemOutcome(
                        content_id=content_id,
                        status="failed",
                        error_code=type(exc).__name__,
                        error_message=str(exc)[:500],
                    )
                )

    await asyncio.gather(*(worker(cid) for cid in worklist))

    if manifest.status == "running":
        manifest.status = "completed"
    else:
        # a breaker tripped: attach the copy-paste continuation command
        manifest.resume_command = resume_command or (
            f"# resume batch '{batch_id}' from its checkpoint "
            f"({manifest.checkpoint_cursor}/{manifest.total} settled)"
        )
    manifest.finished_at = now_utc().isoformat()
    _write_manifest(manifest_path, manifest)
    logger.info(
        "batch %s %s: done=%d failed=%d skipped=%d tokens=%d",
        batch_id, manifest.status, manifest.done, manifest.failed,
        manifest.skipped, manifest.budget_spent_tokens,
    )
    return manifest


def run_batch_sync(**kwargs: Any) -> BatchRunManifest:
    """Blocking wrapper around :func:`run_batch` for CLI / script entry points."""
    return asyncio.run(run_batch(**kwargs))
