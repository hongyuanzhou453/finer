"""Concurrent F1 scale-up over broker research (Phase 0 C3 / OPS-3).

In-repo, reproducible replacement for the ad-hoc scratchpad ``broker_scaleup_runner``:
discovers broker F0-ready content that still needs F1, drives it through the
concurrent :mod:`finer.pipeline.batch_runner` pool (asyncio semaphore + per-item
failure isolation + checkpoint resume + token budget + quota circuit breaker), and
writes ``stage_status`` F1='ready' as each envelope lands — so the driver and the
Import Console see standardized broker content.

Unlike the scratchpad runner, this entry:
  * lives in the repo and is version-controlled;
  * writes stage_status (the scratchpad one did not);
  * has a hard token budget and a quota breaker with a printed resume command.

Discovery + the F1 executor are reused read-only from ``pipeline.driver`` (the
card forbids modifying the driver's main loop; collaboration is by executor
injection only).

Dry-run by default. Examples::

    # preview what would run
    .venv/bin/python scripts/drive_broker_scaleup.py

    # process up to 200 items, 8 workers, stop after 2M tokens
    .venv/bin/python scripts/drive_broker_scaleup.py --execute \
        --max-items 200 --concurrency 8 --budget 2000000

    # resume after a budget/quota stop (same batch-id reuses the checkpoint)
    .venv/bin/python scripts/drive_broker_scaleup.py --execute --max-items 200

WARNING: this makes real MiMo vision calls. Do NOT run it while another broker
F1 scale-up process is active (``ps aux | grep scaleup``) — the two would
double-burn OCR quota and race on ``data/F1_standardized``.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from finer.paths import DATA_ROOT

_STAGE_STATUS_UPSERT = """
    INSERT INTO stage_status (content_id, stage, status, updated_at)
    VALUES (?, ?, 'ready', ?)
    ON CONFLICT(content_id, stage) DO UPDATE SET
        status = 'ready',
        updated_at = excluded.updated_at
"""


def _mark_stage_ready(db_path: Path, content_id: str, stage: str) -> None:
    """Upsert one stage_status row on a short-lived, own-thread connection.

    A fresh connection per call (rather than the shared pool connection) keeps
    concurrent worker-thread writes safe; a long busy_timeout rides out WAL
    write contention from the other workers.
    """
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            _STAGE_STATUS_UPSERT,
            (content_id, stage, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _discover_needs_f1(data_root: Path, db_path: Path, channel: str) -> List[str]:
    """F0-ready content ids for ``channel`` whose F1 envelope is still missing."""
    from finer.pipeline.driver import (  # read-only reuse; driver loop untouched
        _discover_ready_content,
        _find_content_record,
        _is_excluded,
    )
    from finer.services.project_memory.connection import get_connection

    conn = get_connection(db_path)
    ready = _discover_ready_content(conn, channel)

    worklist: List[str] = []
    for content_id in ready:
        if content_id.startswith("cnt_"):
            continue  # legacy identity projection — not driver input
        f1_path = data_root / "F1_standardized" / content_id / "content_envelope.json"
        if f1_path.exists():
            continue  # F1 is fill-only; an existing envelope is never re-run
        rec = _find_content_record(data_root, content_id)
        if rec is None or _is_excluded(rec):
            continue
        worklist.append(content_id)
    return worklist


def _make_f1_process_item(data_root: Path, db_path: Path):
    """Build the per-item F1 worker (runs in a batch_runner thread)."""
    from finer.pipeline.batch_runner import SKIPPED
    from finer.pipeline.driver import _default_f1_executor, _find_content_record, _is_excluded

    def process_item(content_id: str) -> str:
        f1_path = data_root / "F1_standardized" / content_id / "content_envelope.json"
        if f1_path.exists():
            return SKIPPED
        rec = _find_content_record(data_root, content_id)
        if rec is None:
            raise FileNotFoundError(f"no ContentRecord on disk for {content_id}")
        if _is_excluded(rec):
            return SKIPPED
        _default_f1_executor(rec, data_root)  # real MiMo vision OCR
        _mark_stage_ready(db_path, content_id, "F1")
        return "done"

    return process_item


def _build_resume_command(args: argparse.Namespace, batch_id: str) -> str:
    parts = [".venv/bin/python", "scripts/drive_broker_scaleup.py", "--execute"]
    if args.channel != "broker":
        parts += ["--channel", args.channel]
    if args.max_items is not None:
        parts += ["--max-items", str(args.max_items)]
    parts += ["--concurrency", str(args.concurrency), "--quota-strikes", str(args.quota_strikes)]
    if args.budget:
        parts += ["--budget", str(args.budget)]
    parts += ["--batch-id", batch_id]
    return " ".join(parts)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="drive_broker_scaleup",
        description="Concurrent F1 scale-up over broker research via the batch_runner pool (dry-run by default).",
    )
    parser.add_argument("--data-root", type=Path, default=None, help=f"data root (default: {DATA_ROOT})")
    parser.add_argument("--db-path", type=Path, default=None, help="project DB path (default: <data-root>/project_memory/finer.project.sqlite3)")
    parser.add_argument("--channel", default="broker", help="import channel to scale up (default: broker)")
    parser.add_argument("--concurrency", type=int, default=8, help="max in-flight F1 workers (default: 8)")
    parser.add_argument("--budget", type=int, default=0, help="hard token budget for this pass (0 = unlimited)")
    parser.add_argument("--quota-strikes", type=int, default=5, help="consecutive 401/402/403/429 that trip the breaker (default: 5)")
    parser.add_argument("--max-items", type=int, default=None, help="cap on items processed this pass (recommended — see R2 guardrail)")
    parser.add_argument("--batch-id", default=None, help="stable resume key (default: f1_<channel>)")
    parser.add_argument("--run-state-dir", type=Path, default=None, help="manifest/checkpoint dir (default: <data-root>/run_state)")
    parser.add_argument("--no-resume", action="store_true", help="ignore any existing checkpoint and start fresh")
    parser.add_argument("--execute", action="store_true", help="actually run F1 (default: dry-run)")
    args = parser.parse_args(argv)

    data_root: Path = args.data_root or DATA_ROOT
    db_path: Path = args.db_path or (data_root / "project_memory" / "finer.project.sqlite3")
    run_state_dir: Path = args.run_state_dir or (data_root / "run_state")
    batch_id: str = args.batch_id or f"f1_{args.channel}"

    from finer.pipeline.batch_runner import run_batch_sync

    worklist = _discover_needs_f1(data_root, db_path, args.channel)

    header = "[execute]" if args.execute else "[dry-run]"
    print(f"{header} broker F1 scale-up  channel={args.channel}  data_root={data_root}")
    print(f"discovered {len(worklist)} F0-ready item(s) needing F1  batch_id={batch_id}")

    manifest = run_batch_sync(
        items=worklist,
        process_item=_make_f1_process_item(data_root, db_path),
        stage="f1",
        batch_id=batch_id,
        run_state_dir=run_state_dir,
        concurrency=args.concurrency,
        budget_tokens=args.budget or None,
        quota_strikes=args.quota_strikes,
        max_items=args.max_items,
        resume=not args.no_resume,
        dry_run=not args.execute,
        resume_command=_build_resume_command(args, batch_id),
    )

    print(
        f"summary: status={manifest.status} total={manifest.total} done={manifest.done} "
        f"failed={manifest.failed} skipped={manifest.skipped} tokens={manifest.budget_spent_tokens}"
    )
    if manifest.stop_reason:
        print(f"stop_reason: {manifest.stop_reason}")
    if manifest.resume_command:
        print(f"resume: {manifest.resume_command}")
    if not args.execute:
        print(f"dry-run: nothing written. Re-run with --execute (recommend --max-items to cap the pass).")

    # Non-zero exit on a circuit-breaker stop so a scheduler/launchd surfaces it.
    return 0 if manifest.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
