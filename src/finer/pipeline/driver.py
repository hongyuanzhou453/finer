"""Incremental F0→F8 pipeline driver.

Closes the automation gap named in docs/specs/2026-07-11-architecture-priorities.md
P0-2: F0 intake deliberately stops at the ``F1_HANDOFF_SEAM`` (see
ingestion/orchestrator.py) and, until now, every downstream stage was a
manually-run script. ``drive_once`` walks that seam: it discovers imported
content (``stage_status`` rows written by f0_index_writer), fills in whichever
stage outputs are missing, and records per-stage outcomes back into the
existing ``stage_status`` / ``pipeline_runs`` tables (no schema changes — the
tables shipped in migration 003 and were write-only-from-F0 until now).

Idempotency contract (file truth first):

===== ============================================================ =========
Stage "already done" predicate                                     action
===== ============================================================ =========
F0    stage_status(content_id,'F0') == 'ready'                     input set
F1    F1_standardized/{content_id}/content_envelope.json exists    route()
F2    F2_anchored/{content_id}.json exists                         anchor()
F5    F5_executed/{content_id}_actions.json exists, OR             extract()
      stage_status(content_id,'F5') == 'ready' (0-action envelope)
F8    settle_actions() once per run (naturally incremental)        settle
===== ============================================================ =========

F1 is NEVER re-run for an existing envelope: envelope/block/span/intent ids
are uuids, so a re-run churns every downstream sidecar (the regen scripts
exist precisely to do that intentionally, with backups). The driver only
fills gaps.

v1 is CLI-driven (``python -m finer.cli pipeline-drive [--watch N]``) and
synchronous; it must not be called from a running event loop (the F5 step
uses ``asyncio.run``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from finer.errors.exceptions import FinerError, FinerStateError
from finer.errors import ErrorCode
from finer.paths import DATA_ROOT
from finer.schemas.content import ContentRecord
from finer.services.project_memory.connection import get_connection

logger = logging.getLogger(__name__)


# =============================================================================
# Report
# =============================================================================


@dataclass
class DriveReport:
    """Outcome of one drive_once() run."""

    run_id: str
    scanned: int = 0
    skipped_complete: int = 0
    skipped_excluded: int = 0
    skipped_legacy_identity: int = 0
    f1_ran: int = 0
    f2_ran: int = 0
    f5_ran: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)
    reconciled: List[Dict[str, Any]] = field(default_factory=list)
    settle: Optional[Dict[str, Any]] = None
    dry_run: bool = False
    skipped_locked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scanned": self.scanned,
            "skipped_complete": self.skipped_complete,
            "skipped_excluded": self.skipped_excluded,
            "skipped_legacy_identity": self.skipped_legacy_identity,
            "f1_ran": self.f1_ran,
            "f2_ran": self.f2_ran,
            "f5_ran": self.f5_ran,
            "failures": self.failures,
            "reconciled": self.reconciled,
            "settle": self.settle,
            "dry_run": self.dry_run,
            "skipped_locked": self.skipped_locked,
        }


# =============================================================================
# F5 per-envelope core (shared with api/routes/extraction.py)
# =============================================================================


async def execute_f5_for_envelope(
    file_path: Path,
    output_path: Path,
    *,
    persist_root: Optional[Path] = None,
) -> Tuple[int, str]:
    """Run canonical F3→F4→F5 (+F8 auto-backtest) for one F2 file.

    Extracted from the /api/extraction/pipeline route so the driver and the
    route share one per-envelope implementation. Returns
    ``(action_count, model_label)``; raises on hard failure. A zero count is
    a legitimate outcome (all intents rejected) and writes no output file.
    """
    from finer.pipeline.canonical_runner import (
        run_canonical_extraction,
        run_canonical_from_envelope,
    )

    output_path.mkdir(parents=True, exist_ok=True)
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    context: Dict[str, Any] = {
        "source_id": str(file_path),
        "source_file": file_path.name,
    }

    # Prefer the canonical F2-envelope path so F3/F5 consume the entity and
    # temporal anchors. Fall back to the raw-text path only when the file is
    # not a serialized ContentEnvelope.
    envelope = None
    if isinstance(data, dict) and "blocks" in data:
        try:
            from finer.schemas.content_envelope import ContentEnvelope

            envelope = ContentEnvelope.model_validate(data)
        except Exception as exc:
            logger.warning(
                "F2 envelope validation failed for %s (%s); using raw-text fallback",
                file_path.name,
                exc,
            )
            envelope = None

    if envelope is not None:
        context["kol_id"] = getattr(envelope, "creator_id", None)
        # persist_dir = data root so F3/F4 sidecars land where the audit
        # assembler reads them.
        actions = await run_canonical_from_envelope(
            envelope, context, persist_dir=persist_root or output_path.parent
        )
        model = "canonical-f2-envelope"
    else:
        text = data.get("text") or data.get("content") or data.get("clean_text", "")
        if not text:
            logger.warning("No text content in %s", file_path)
            return 0, "no-text"
        actions = await run_canonical_extraction(text, context)
        model = "canonical-programmatic"

    if not actions:
        return 0, model

    # F8 auto-backtest: fail-open — any price/eval error leaves
    # backtest_result as None (opinions shows 待回测).
    if os.environ.get("FINER_F8_AUTO_BACKTEST", "1") != "0":
        try:
            from finer.backtest.per_action import evaluate_action
            from finer.backtest.yahoo_prices import fetch_daily_closes

            closes_by_ticker: Dict[str, list] = {}
            for a in actions:
                ticker = a.target.ticker_normalized or a.target.ticker
                if ticker not in closes_by_ticker:
                    closes_by_ticker[ticker] = fetch_daily_closes(ticker)
                result, _skip = evaluate_action(a, closes_by_ticker[ticker])
                if result is not None:
                    a.backtest_result = result
        except Exception as bt_exc:
            logger.warning("F8 auto-backtest skipped for %s: %s", file_path.name, bt_exc)

    output_file = output_path / f"{file_path.stem}_actions.json"
    output_data = {
        "source_file": str(file_path),
        "extracted_at": datetime.now().isoformat(),
        "model": model,
        "actions": [a.model_dump(mode="json") for a in actions],
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Keep the SQLite cache index fresh; files stay authoritative.
    try:
        from finer.services.repository import TradeActionRepository

        repo = TradeActionRepository()
        for a in actions:
            repo.index_trade_action(a, str(output_file))
    except Exception as index_exc:
        logger.warning("Failed to index extracted actions from %s: %s", output_file, index_exc)

    return len(actions), model


# =============================================================================
# Default stage executors (injectable for tests)
# =============================================================================

_ROUTER = None


def _default_f1_executor(rec: ContentRecord, data_root: Path) -> Path:
    """Standardize one ContentRecord via StandardizationRouter."""
    global _ROUTER
    if _ROUTER is None:
        from finer.llm.client import LLMClient
        from finer.model_config import get_vision_registry
        from finer.parsing.standardization_router import StandardizationRouter

        vision_llm = None
        try:
            vision_llm = LLMClient(registry=get_vision_registry())
        except Exception as exc:  # vision optional: text records still route
            logger.warning("Vision LLM unavailable for F1 (%s); text-only routing", exc)
        _ROUTER = StandardizationRouter(llm_client=vision_llm)

    raw_path = Path(rec.raw_path)
    if not raw_path.exists():
        raise FinerStateError(
            ErrorCode.API_NTF_001,
            f"raw file missing for {rec.content_id}: {rec.raw_path}",
            stage="F1",
            operation="standardize",
            retryable=False,
        )
    env, _report = _ROUTER.route(rec, raw_path)
    out = data_root / "F1_standardized" / rec.content_id / "content_envelope.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(env.model_dump_json(indent=2), encoding="utf-8")
    return out


def _default_f2_executor(f1_envelope_path: Path, rec: ContentRecord, data_root: Path) -> Path:
    """Attach deterministic F2 anchors/spans to one F1 envelope."""
    from finer.enrichment.entity_anchoring import build_f2_deterministic_envelope

    envelope = json.loads(f1_envelope_path.read_text(encoding="utf-8"))
    f2_env = build_f2_deterministic_envelope(envelope, f0_record=rec.model_dump(mode="json"))
    out = data_root / "F2_anchored" / f"{rec.content_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(f2_env.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return out


def _default_f5_executor(f2_path: Path, data_root: Path) -> int:
    """Run the shared per-envelope F5 core synchronously."""
    count, _model = asyncio.run(
        execute_f5_for_envelope(
            f2_path,
            data_root / "F5_executed",
            persist_root=data_root,
        )
    )
    return count


def _is_excluded(rec: ContentRecord) -> bool:
    """Content the pipeline intentionally does not standardize.

    Mirrors scripts/backfill_f1_standardize.py: bilibili video covers carry
    no text, and the local tutorial PDF is non-investment content.
    """
    rp = (rec.raw_path or "").replace("\\", "/")
    if "/bilibili/" in rp:
        return True
    if rec.file_type == "pdf" and "/raw/local/" in rp:
        return True
    if "教程" in (rec.title or ""):
        return True
    return False


# =============================================================================
# Ledger writes (existing tables only — no DDL)
# =============================================================================


def _upsert_stage_status(
    conn: sqlite3.Connection,
    content_id: str,
    stage: str,
    status: str,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO stage_status (content_id, stage, status, error_code, error_message, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_id, stage) DO UPDATE SET
            status = excluded.status,
            error_code = excluded.error_code,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (content_id, stage, status, error_code, error_message, datetime.now().isoformat()),
    )
    conn.commit()


def _record_failure(
    conn: sqlite3.Connection,
    report: DriveReport,
    content_id: str,
    stage: str,
    exc: Exception,
) -> None:
    error_code = exc.error_code_str if isinstance(exc, FinerError) else type(exc).__name__
    error_message = str(exc)[:500]
    report.failures.append(
        {
            "content_id": content_id,
            "stage": stage,
            "error_code": error_code,
            "error_message": error_message,
        }
    )
    if not report.dry_run:
        _upsert_stage_status(conn, content_id, stage, "failed", error_code, error_message)


def _reconcile_orphan(
    conn: sqlite3.Connection,
    report: DriveReport,
    content_id: str,
    dry_run: bool,
) -> None:
    """Handle a stage_status F0='ready' row whose ContentRecord is not on disk.

    The SQLite ledger is only a hot index; the ContentRecord file is the F0
    truth (F0 Project Memory contract). A 'ready' row with no record on disk is
    an inconsistent index entry — e.g. an old smoke-test import, or a record
    deleted/moved after registration (this is the write-atomicity gap: the PM
    row outlived its durable record). Rather than surfacing it as a fresh
    failure on *every* drive, flip the F0 row to 'failed' so it leaves the ready
    set. Self-healing: a genuine re-import rewrites the record and F0IndexWriter
    flips the row back to 'ready'.
    """
    report.reconciled.append(
        {
            "content_id": content_id,
            "stage": "F0",
            "reason": "ContentRecordMissing",
            "action": "would_mark_failed" if dry_run else "marked_failed",
        }
    )
    if not dry_run:
        _upsert_stage_status(
            conn,
            content_id,
            "F0",
            "failed",
            "ContentRecordMissing",
            "stage_status F0=ready but no ContentRecord on disk; reconciled by "
            "driver (a genuine re-import restores 'ready')",
        )


# =============================================================================
# Driver
# =============================================================================


def _discover_ready_content(conn: sqlite3.Connection) -> List[str]:
    try:
        rows = conn.execute(
            "SELECT content_id FROM stage_status "
            "WHERE stage = 'F0' AND status = 'ready' ORDER BY updated_at"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise FinerStateError(
            ErrorCode.API_INT_001,
            "project memory tables missing (stage_status) — initialize the "
            "project memory database before running the driver",
            stage="F0",
            operation="pipeline_drive",
            retryable=False,
            cause=exc,
        ) from exc
    return [r["content_id"] for r in rows]


def _find_content_record(data_root: Path, content_id: str) -> Optional[ContentRecord]:
    # rglob: local intake nests records under creator subdirectories
    # (data/F0_intake/local/{creator}/{content_id}.json).
    for path in (data_root / "F0_intake").rglob(f"{content_id}.json"):
        if path.name.endswith(".receipt.json"):
            continue
        try:
            return ContentRecord.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            logger.warning("Unparsable ContentRecord %s: %s", path, exc)
            return None
    return None


def _stage_ready(conn: sqlite3.Connection, content_id: str, stage: str) -> bool:
    row = conn.execute(
        "SELECT status FROM stage_status WHERE content_id = ? AND stage = ?",
        (content_id, stage),
    ).fetchone()
    return bool(row and row["status"] == "ready")


_LOCK_UNAVAILABLE = object()


def _acquire_drive_lock(lock_dir: Path):
    """Best-effort non-blocking exclusive lock for a drive pass.

    Returns an open locked file handle on success, ``None`` if another drive
    already holds it, or ``_LOCK_UNAVAILABLE`` when locking can't be used
    (non-POSIX / unwritable dir) — in which case the caller proceeds unguarded.
    """
    try:
        import fcntl
    except ImportError:  # pragma: no cover — POSIX only
        return _LOCK_UNAVAILABLE
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
        handle = open(lock_dir / ".pipeline_drive.lock", "w")
    except OSError:
        return _LOCK_UNAVAILABLE
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _release_drive_lock(handle) -> None:
    if handle is None or handle is _LOCK_UNAVAILABLE:
        return
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:  # noqa: BLE001 — release is best-effort
        pass
    finally:
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass


def drive_once(
    *,
    data_root: Path = DATA_ROOT,
    db_path: Optional[Path] = None,
    limit: Optional[int] = None,
    run_settle: bool = True,
    dry_run: bool = False,
    f1_executor: Optional[Callable[[ContentRecord, Path], Path]] = None,
    f2_executor: Optional[Callable[[Path, ContentRecord, Path], Path]] = None,
    f5_executor: Optional[Callable[[Path, Path], int]] = None,
) -> DriveReport:
    """One incremental pass, guarded by a single-flight lock.

    A non-blocking file lock (keyed on the DB / data dir) ensures a server-hosted
    auto-driver and a CLI ``pipeline-drive --watch`` loop can't drive
    concurrently — two overlapping passes would race on the same envelope (F1
    uuid churn). If another drive holds the lock, this pass is skipped
    (``skipped_locked=True``) and retried next cycle. See ``_drive_once_unlocked``
    for the actual work.
    """
    lock_dir = Path(db_path).parent if db_path is not None else data_root
    handle = _acquire_drive_lock(lock_dir)
    if handle is None:
        run_id = f"drive_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}"
        logger.info("pipeline drive %s: skipped — another drive holds the lock", run_id)
        return DriveReport(run_id=run_id, dry_run=dry_run, skipped_locked=True)
    try:
        return _drive_once_unlocked(
            data_root=data_root,
            db_path=db_path,
            limit=limit,
            run_settle=run_settle,
            dry_run=dry_run,
            f1_executor=f1_executor,
            f2_executor=f2_executor,
            f5_executor=f5_executor,
        )
    finally:
        _release_drive_lock(handle)


def _drive_once_unlocked(
    *,
    data_root: Path = DATA_ROOT,
    db_path: Optional[Path] = None,
    limit: Optional[int] = None,
    run_settle: bool = True,
    dry_run: bool = False,
    f1_executor: Optional[Callable[[ContentRecord, Path], Path]] = None,
    f2_executor: Optional[Callable[[Path, ContentRecord, Path], Path]] = None,
    f5_executor: Optional[Callable[[Path, Path], int]] = None,
) -> DriveReport:
    """One incremental pass: fill missing F1/F2/F5 outputs, then settle.

    Per-content failures are isolated (recorded in the report and in
    stage_status.error_code/error_message); one broken item never blocks the
    batch. Skips (output already present) do NOT touch stage_status so manual
    backfill history keeps its own timestamps.
    """
    f1_run = f1_executor or _default_f1_executor
    f2_run = f2_executor or _default_f2_executor
    f5_run = f5_executor or _default_f5_executor

    conn = get_connection(db_path)
    run_id = f"drive_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}"
    report = DriveReport(run_id=run_id, dry_run=dry_run)

    if not dry_run:
        try:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, run_type, status, started_at) "
                "VALUES (?, 'pipeline_drive', 'running', ?)",
                (run_id, datetime.now().isoformat()),
            )
            conn.commit()
        except sqlite3.OperationalError:
            logger.warning("pipeline_runs table missing; run bookkeeping skipped")

    content_ids = _discover_ready_content(conn)
    if limit is not None:
        content_ids = content_ids[:limit]

    for content_id in content_ids:
        report.scanned += 1

        # `cnt_*` rows are project-memory identity projections written by the
        # 2026-06-04 manifest backfill — they never had a ContentRecord under
        # F0_intake and are not driver input. Skip quietly (counted) instead
        # of flagging 368 legacy rows as failures on every run.
        if content_id.startswith("cnt_"):
            report.skipped_legacy_identity += 1
            continue

        rec = _find_content_record(data_root, content_id)
        if rec is None:
            _reconcile_orphan(conn, report, content_id, dry_run)
            continue
        if _is_excluded(rec):
            report.skipped_excluded += 1
            continue

        f1_path = data_root / "F1_standardized" / content_id / "content_envelope.json"
        f2_path = data_root / "F2_anchored" / f"{content_id}.json"
        f5_path = data_root / "F5_executed" / f"{content_id}_actions.json"

        try:
            # F1 — fill only; an existing envelope is NEVER re-run (uuid churn).
            if not f1_path.exists():
                if dry_run:
                    report.f1_ran += 1
                    continue  # downstream stages need the real envelope
                f1_path = f1_run(rec, data_root)
                report.f1_ran += 1
                _upsert_stage_status(conn, content_id, "F1", "ready")

            # F2
            if not f2_path.exists():
                if dry_run:
                    report.f2_ran += 1
                    continue
                f2_path = f2_run(f1_path, rec, data_root)
                report.f2_ran += 1
                _upsert_stage_status(conn, content_id, "F2", "ready")

            # F5 (+ embedded F8 auto-backtest). A prior legitimate 0-action
            # run is remembered in stage_status so empties aren't re-extracted
            # every drive.
            if f5_path.exists() or _stage_ready(conn, content_id, "F5"):
                report.skipped_complete += 1
                continue
            if dry_run:
                report.f5_ran += 1
                continue
            count = f5_run(f2_path, data_root)
            report.f5_ran += 1
            _upsert_stage_status(
                conn,
                content_id,
                "F5",
                "ready",
                error_message=None if count else "0 actions (all intents rejected)",
            )
        except FinerError as exc:
            _record_failure(conn, report, content_id, exc.stage or "F5", exc)
        except Exception as exc:  # noqa: BLE001 — per-content isolation
            stage = (
                "F1" if not f1_path.exists()
                else "F2" if not f2_path.exists()
                else "F5"
            )
            _record_failure(conn, report, content_id, stage, exc)

    if run_settle:
        from finer.backtest.settle import settle_actions

        try:
            report.settle = settle_actions(dry_run=dry_run).to_dict()
        except Exception as exc:  # noqa: BLE001 — settle failure isolated too
            report.failures.append(
                {
                    "content_id": None,
                    "stage": "F8",
                    "error_code": type(exc).__name__,
                    "error_message": str(exc)[:500],
                }
            )

    if not dry_run:
        try:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at = ?, summary_json = ? "
                "WHERE run_id = ?",
                (
                    "failed" if report.failures else "completed",
                    datetime.now().isoformat(),
                    json.dumps(report.to_dict(), ensure_ascii=False),
                    run_id,
                ),
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass

    logger.info(
        "pipeline drive %s: scanned=%d f1=%d f2=%d f5=%d skipped=%d excluded=%d "
        "reconciled=%d failures=%d",
        run_id,
        report.scanned,
        report.f1_ran,
        report.f2_ran,
        report.f5_ran,
        report.skipped_complete,
        report.skipped_excluded,
        len(report.reconciled),
        len(report.failures),
    )
    return report
