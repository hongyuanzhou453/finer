"""Backfill Project Memory F0-index rows for already-imported broker research.

Broker research was imported into ``data/F0_intake/broker/`` before the intake
channel registered anything into Project Memory, so those ContentRecords never
got a ``stage_status`` / ``asset_index`` row and are invisible to the driver
(``--channel broker`` finds nothing). This script walks the on-disk record files
(the F0 truth) and idempotently registers each one via ``F0IndexWriter``, tagging
its stage_status row with ``source_channel='broker'`` (Phase 0 card C1 / OPS-1).

Idempotent by construction: ``F0IndexWriter.record_imported`` uses
``INSERT OR IGNORE`` / ``ON CONFLICT``, so re-running never duplicates rows and
always re-affirms ``source_channel='broker'`` (COALESCE-overwrite in migration 005).

Dry-run by default: reports how many records WOULD be registered and writes
nothing. Pass ``--execute`` to actually register.

    # preview
    python -m scripts.backfill_broker_stage_status
    # or: .venv/bin/python scripts/backfill_broker_stage_status.py
    # register for real
    .venv/bin/python scripts/backfill_broker_stage_status.py --execute

Requires migration 005 (source_channel column) applied first:
    .venv/bin/python -m finer.scripts.project_memory_migrate upgrade
"""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from finer.paths import DATA_ROOT
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt

BROKER_CHANNEL = "broker"
BROKER_SOURCE_KIND = "broker_research_pdf"


@dataclass
class BackfillResult:
    """Aggregate outcome of one backfill run (dry-run or execute)."""

    dry_run: bool = True
    scanned: int = 0            # broker record files found
    already_registered: int = 0  # had a stage_status F0 row before this run
    registered: int = 0          # newly registered (execute) / would-register (dry-run)
    reaffirmed: int = 0          # already-present rows re-registered (execute only)
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _record_files(broker_dir: Path) -> list[Path]:
    """Record files under the broker F0 dir, excluding ``*.receipt*.json``."""
    return sorted(p for p in broker_dir.glob("*.json") if ".receipt" not in p.name)


def _existing_f0_content_ids(db_path: Path) -> set[str]:
    """content_ids that already have a stage_status F0 row (read-only)."""
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            rows = conn.execute(
                "SELECT content_id FROM stage_status WHERE stage = 'F0'"
            ).fetchall()
        except sqlite3.OperationalError:
            return set()
        return {r[0] for r in rows}
    finally:
        conn.close()


def _synth_receipt(record: ContentRecord, record_file: Path, run_id: str) -> ImportReceipt:
    """Minimal ImportReceipt reconstructed from the on-disk ContentRecord.

    The record file IS the F0 truth; we only need the fields F0IndexWriter reads
    (source_channel/kind, record_path, raw_sha256/raw_paths, external id).
    """
    sha = record.dedupe_fingerprint or (record.metadata or {}).get("content_sha256")
    now = datetime.now(timezone.utc)
    return ImportReceipt(
        run_id=run_id,
        source_channel=BROKER_CHANNEL,
        source_kind=BROKER_SOURCE_KIND,
        status="completed",
        content_id=record.content_id,
        external_source_id=record.external_source_id,
        dedupe_fingerprint=record.dedupe_fingerprint,
        collected_at=record.collected_at,
        started_at=now,
        finished_at=now,
        raw_sha256={"pdf": sha} if sha else {},
        raw_paths={"pdf": record.raw_path},
        record_path=str(record_file),
        records_created=1,
    )


def backfill(
    data_root: Path,
    db_path: Path,
    *,
    execute: bool = False,
    limit: Optional[int] = None,
) -> BackfillResult:
    """Register (or preview) broker F0 records into Project Memory stage_status."""
    result = BackfillResult(dry_run=not execute)
    broker_dir = data_root / "F0_intake" / BROKER_CHANNEL
    if not broker_dir.is_dir():
        return result

    record_files = _record_files(broker_dir)
    if limit is not None:
        record_files = record_files[:limit]

    existing = _existing_f0_content_ids(db_path)

    writer = None
    if execute:
        from finer.ingestion.f0_index_writer import F0IndexWriter

        writer = F0IndexWriter(db_path=db_path)

    run_id = f"backfill_broker_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    for record_file in record_files:
        result.scanned += 1
        try:
            record = ContentRecord.model_validate_json(
                record_file.read_text(encoding="utf-8")
            )
        except Exception as exc:  # noqa: BLE001 - report and continue
            result.failed += 1
            result.errors.append(f"{record_file.name}: parse error: {type(exc).__name__}: {exc}")
            continue

        already = record.content_id in existing
        if already:
            result.already_registered += 1

        if not execute:
            if not already:
                result.registered += 1  # would-register
            continue

        receipt = _synth_receipt(record, record_file, run_id)
        try:
            writer.record_imported(record, receipt)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - report and continue
            result.failed += 1
            result.errors.append(f"{record.content_id}: {type(exc).__name__}: {exc}")
            continue
        if already:
            result.reaffirmed += 1
        else:
            result.registered += 1

    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_broker_stage_status",
        description="Idempotently register already-imported broker F0 records into Project Memory (dry-run by default).",
    )
    parser.add_argument("--data-root", type=Path, default=None, help=f"data root (default: {DATA_ROOT})")
    parser.add_argument("--db-path", type=Path, default=None, help="project DB path (default: <data-root>/project_memory/finer.project.sqlite3)")
    parser.add_argument("--limit", type=int, default=None, help="max record files to process")
    parser.add_argument("--execute", action="store_true", help="actually register (default: dry-run)")
    args = parser.parse_args(argv)

    data_root = args.data_root or DATA_ROOT
    db_path = args.db_path or (data_root / "project_memory" / "finer.project.sqlite3")

    result = backfill(data_root, db_path, execute=args.execute, limit=args.limit)

    header = "[execute]" if args.execute else "[dry-run]"
    print(f"{header} broker F0 backfill  data_root={data_root}  db={db_path}")
    print(
        f"summary: scanned={result.scanned} "
        f"registered={result.registered} reaffirmed={result.reaffirmed} "
        f"already_registered={result.already_registered} failed={result.failed}"
    )
    for err in result.errors[:20]:
        print(f"  ERROR {err}")
    if len(result.errors) > 20:
        print(f"  ... and {len(result.errors) - 20} more errors")
    if not args.execute:
        print(f"dry-run: nothing written. {result.registered} record(s) would be registered. Re-run with --execute.")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
