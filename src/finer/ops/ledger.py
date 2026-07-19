"""Run ledger — one appended JSONL line per drive/settle pass (C5 / OPS-5).

Files live under ``data/run_state/ledger/<YYYY-MM-DD>.jsonl`` (one file per day,
append-only). Each line is a :class:`~finer.schemas.ops.RunLedgerEntry`. Writes
are best-effort: a ledger failure must never break the pass it records.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from finer.paths import DATA_ROOT
from finer.schemas.ops import LedgerErrorEntry, RunLedgerEntry
from finer.utils.time import now_utc

logger = logging.getLogger(__name__)


def ledger_dir(run_state_dir: Optional[Path] = None) -> Path:
    base = run_state_dir if run_state_dir is not None else (DATA_ROOT / "run_state")
    return base / "ledger"


def ledger_path_for_day(day: Optional[str] = None, run_state_dir: Optional[Path] = None) -> Path:
    day = day or now_utc().strftime("%Y-%m-%d")
    return ledger_dir(run_state_dir) / f"{day}.jsonl"


def write_ledger_entry(entry: RunLedgerEntry, run_state_dir: Optional[Path] = None) -> Optional[Path]:
    """Append one ledger row to today's file; returns the path (None on failure)."""
    path = ledger_path_for_day(run_state_dir=run_state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            fh.flush()
        return path
    except Exception as exc:  # noqa: BLE001 — ledger must never break the pass
        logger.warning("ledger write failed: %s", exc)
        return None


def _drive_errors_to_canonical(failures: List[Dict[str, Any]]) -> List[LedgerErrorEntry]:
    """Map DriveReport.failures ({content_id,stage,error_code,error_message}) to
    the canonical Line F error-envelope shape."""
    out: List[LedgerErrorEntry] = []
    for f in failures or []:
        out.append(
            LedgerErrorEntry(
                code=f.get("error_code") or "UNKNOWN",
                message=(f.get("error_message") or "")[:500],
                stage=f.get("stage"),
                operation="pipeline_drive",
                retryable=False,
                content_id=f.get("content_id"),
                fix_hint="inspect stage_status.error_code/error_message for this content_id",
            )
        )
    return out


def build_drive_ledger_entry(
    report: Dict[str, Any], *, tokens_spent: int, duration_s: float
) -> RunLedgerEntry:
    """Build a ledger row from a DriveReport dict."""
    failures = report.get("failures") or []
    status = (
        "skipped_locked" if report.get("skipped_locked")
        else "failed" if failures
        else "completed"
    )
    return RunLedgerEntry(
        run_id=report.get("run_id", "unknown"),
        job_type="pipeline_drive",
        status=status,
        duration_s=round(duration_s, 3),
        tokens_spent=max(0, tokens_spent),
        stats={
            "scanned": report.get("scanned"),
            "f1_ran": report.get("f1_ran"),
            "f2_ran": report.get("f2_ran"),
            "f5_ran": report.get("f5_ran"),
            "skipped_complete": report.get("skipped_complete"),
            "skipped_excluded": report.get("skipped_excluded"),
            "failure_count": len(failures),
            "dry_run": report.get("dry_run", False),
            "settle": report.get("settle"),
        },
        errors=_drive_errors_to_canonical(failures),
    )


def build_settle_ledger_entry(
    report: Dict[str, Any], *, run_id: str, duration_s: float
) -> RunLedgerEntry:
    """Build a ledger row from a SettleReport dict."""
    return RunLedgerEntry(
        run_id=run_id,
        job_type="settle",
        status="completed",
        duration_s=round(duration_s, 3),
        tokens_spent=0,
        stats={k: v for k, v in report.items() if k != "backup"},
        errors=[],
    )
