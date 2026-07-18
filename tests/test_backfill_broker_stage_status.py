"""Tests for scripts/backfill_broker_stage_status.py (Phase 0 C1 / OPS-1).

Broker records are produced by driving the REAL intake (run_intake, no index
writer) so the on-disk record format is authentic; the backfill then registers
them into a freshly-migrated temp Project Memory DB.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from finer.ingestion.broker_research_intake import run_intake
from finer.scripts.project_memory_migrate import apply_migrations

# Load the repo-root script module by path (mirrors tests/test_contract_drift.py).
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_broker_stage_status.py"
_spec = importlib.util.spec_from_file_location("backfill_broker_stage_status", _SCRIPT)
assert _spec and _spec.loader
_bf = importlib.util.module_from_spec(_spec)
sys.modules["backfill_broker_stage_status"] = _bf
_spec.loader.exec_module(_bf)
backfill = _bf.backfill

FAKE_PDF = b"%PDF-1.4 fake broker research bytes\n%%EOF\n"


def _make_broker_records(tmp_path: Path, n: int) -> Path:
    """Drive the real intake to write ``n`` distinct broker ContentRecords.

    Returns the data_root under which F0_intake/broker/*.json now exist. No PM
    registration happens here (run_intake without index_writer)."""
    data_root = tmp_path / "data"
    source = tmp_path / "src"
    source.mkdir(parents=True, exist_ok=True)
    metas: list[dict[str, Any]] = []
    for i in range(n):
        pdf = source / f"r{i}.pdf"
        pdf.write_bytes(FAKE_PDF + bytes([i]))  # unique bytes -> unique content_id
        metas.append(
            {
                "filepath": str(pdf),
                "filename": pdf.name,
                "broker": "高盛",
                "date": "2026-05-31",
                "topic": "风险回报更新",
                "company_name": "测试公司",
                "stock_code": "X.US",
            }
        )
    meta_jsonl = tmp_path / "meta.jsonl"
    meta_jsonl.write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in metas) + "\n",
        encoding="utf-8",
    )
    result = run_intake(meta_jsonl, data_root, limit=n, execute=True)
    assert result.written_records == n
    assert result.registered == 0  # no index_writer -> nothing registered yet
    return data_root


def _migrated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "pm.sqlite3"
    apply_migrations(db_path)
    return db_path


def _query(db_path: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(str(db_path))
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


# ---------------------------------------------------------------------------


def test_migration_005_adds_source_channel_column(tmp_path: Path) -> None:
    db_path = _migrated_db(tmp_path)
    cols = [r[1] for r in _query(db_path, "PRAGMA table_info(stage_status)")]
    assert "source_channel" in cols


def test_backfill_registers_broker_records_with_source_channel(tmp_path: Path) -> None:
    data_root = _make_broker_records(tmp_path, 3)
    db_path = _migrated_db(tmp_path)

    result = backfill(data_root, db_path, execute=True)

    assert result.scanned == 3
    assert result.registered == 3
    assert result.reaffirmed == 0
    assert result.failed == 0

    rows = _query(
        db_path,
        "SELECT content_id, source_channel, status FROM stage_status WHERE stage='F0'",
    )
    assert len(rows) == 3
    assert all(r[1] == "broker" for r in rows)
    assert all(r[2] == "ready" for r in rows)
    assert all(r[0].startswith("broker_") for r in rows)


def test_backfill_dry_run_writes_nothing(tmp_path: Path) -> None:
    data_root = _make_broker_records(tmp_path, 2)
    db_path = _migrated_db(tmp_path)

    result = backfill(data_root, db_path, execute=False)

    assert result.dry_run is True
    assert result.scanned == 2
    assert result.registered == 2  # would-register
    # nothing actually written
    assert _query(db_path, "SELECT COUNT(*) FROM stage_status WHERE stage='F0'")[0][0] == 0


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    data_root = _make_broker_records(tmp_path, 2)
    db_path = _migrated_db(tmp_path)

    first = backfill(data_root, db_path, execute=True)
    assert first.registered == 2

    second = backfill(data_root, db_path, execute=True)
    assert second.scanned == 2
    assert second.registered == 0
    assert second.reaffirmed == 2
    assert second.failed == 0

    # still exactly two F0 rows (no duplicates)
    assert _query(db_path, "SELECT COUNT(*) FROM stage_status WHERE stage='F0'")[0][0] == 2


def test_backfill_ignores_receipt_files(tmp_path: Path) -> None:
    data_root = _make_broker_records(tmp_path, 1)
    broker_dir = data_root / "F0_intake" / "broker"
    receipts = [p for p in broker_dir.glob("*.json") if ".receipt" in p.name]
    assert receipts, "intake fixture should have written a receipt file"

    db_path = _migrated_db(tmp_path)
    result = backfill(data_root, db_path, execute=True)

    assert result.scanned == 1  # only the record, receipts skipped
    assert result.registered == 1


def test_backfill_missing_broker_dir_is_noop(tmp_path: Path) -> None:
    db_path = _migrated_db(tmp_path)
    result = backfill(tmp_path / "empty_data", db_path, execute=True)
    assert result.scanned == 0
    assert result.registered == 0
