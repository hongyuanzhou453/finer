"""Tests for the incremental pipeline driver (pipeline/driver.py)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from finer.pipeline.driver import DriveReport, drive_once

MIGRATIONS_DIR = (
    Path(__file__).parent.parent
    / "src" / "finer" / "services" / "project_memory" / "migrations"
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def pm_db(tmp_path):
    """Project-memory SQLite with the real migrations applied."""
    db_path = tmp_path / "finer.project.sqlite3"
    conn = sqlite3.connect(db_path)
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(sql_file.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def data_root(tmp_path):
    root = tmp_path / "data"
    (root / "F0_intake" / "local").mkdir(parents=True)
    (root / "F1_standardized").mkdir()
    (root / "F2_anchored").mkdir()
    (root / "F5_executed").mkdir()
    return root


def _register_content(db_path: Path, data_root: Path, content_id: str, **record_overrides):
    """Write the FK parents + stage_status F0 ready row + ContentRecord file.

    Mirrors f0_index_writer: content_identities → contents → stage_status
    (stage_status has a FOREIGN KEY on contents.content_id).
    """
    now = datetime(2026, 7, 1).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO content_identities "
        "(content_id, identity_scheme, stable_key, created_at) VALUES (?, 'test', ?, ?)",
        (content_id, content_id, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO contents "
        "(content_id, current_stage, created_at, updated_at, status) "
        "VALUES (?, 'F0', ?, ?, 'active')",
        (content_id, now, now),
    )
    conn.execute(
        "INSERT INTO stage_status (content_id, stage, status, updated_at) "
        "VALUES (?, 'F0', 'ready', ?) "
        "ON CONFLICT(content_id, stage) DO UPDATE SET status='ready'",
        (content_id, now),
    )
    conn.commit()
    conn.close()

    record = {
        "content_id": content_id,
        "creator_id": "kol-test",
        "source_platform": "local",
        "source_type": "manual_upload",
        "file_type": "image",
        "title": f"测试内容 {content_id}",
        "raw_path": str(data_root / "raw" / f"{content_id}.png"),
        "collected_at": "2026-07-01T10:00:00",
    }
    record.update(record_overrides)
    path = data_root / "F0_intake" / "local" / f"{content_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return record


def _touch_f1(data_root: Path, content_id: str):
    p = data_root / "F1_standardized" / content_id / "content_envelope.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return p


def _touch_f2(data_root: Path, content_id: str):
    p = data_root / "F2_anchored" / f"{content_id}.json"
    p.write_text("{}", encoding="utf-8")
    return p


def _touch_f5(data_root: Path, content_id: str):
    p = data_root / "F5_executed" / f"{content_id}_actions.json"
    p.write_text('{"actions": []}', encoding="utf-8")
    return p


class StageRecorder:
    """Injectable stage executors that record invocations."""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.f1_calls: list[str] = []
        self.f2_calls: list[str] = []
        self.f5_calls: list[str] = []
        self.f5_count = 1

    def f1(self, rec, data_root):
        self.f1_calls.append(rec.content_id)
        return _touch_f1(data_root, rec.content_id)

    def f2(self, f1_path, rec, data_root):
        self.f2_calls.append(rec.content_id)
        return _touch_f2(data_root, rec.content_id)

    def f5(self, f2_path, data_root):
        cid = f2_path.stem
        self.f5_calls.append(cid)
        if self.f5_count:
            _touch_f5(data_root, cid)
        return self.f5_count


def _drive(data_root, pm_db, recorder, **kwargs):
    return drive_once(
        data_root=data_root,
        db_path=pm_db,
        run_settle=False,  # settle has its own suite (test_settle.py)
        f1_executor=recorder.f1,
        f2_executor=recorder.f2,
        f5_executor=recorder.f5,
        **kwargs,
    )


def _stage_rows(db_path: Path, content_id: str) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT stage, status FROM stage_status WHERE content_id = ?", (content_id,)
    ).fetchall()
    conn.close()
    return {r["stage"]: r["status"] for r in rows}


# =============================================================================
# Tests
# =============================================================================


def test_fills_all_missing_stages(data_root, pm_db):
    _register_content(pm_db, data_root, "c-new")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    assert rec.f1_calls == ["c-new"]
    assert rec.f2_calls == ["c-new"]
    assert rec.f5_calls == ["c-new"]
    assert report.f1_ran == report.f2_ran == report.f5_ran == 1
    assert report.failures == []
    rows = _stage_rows(pm_db, "c-new")
    assert rows["F1"] == rows["F2"] == rows["F5"] == "ready"


def test_idempotent_skip_when_all_outputs_exist(data_root, pm_db):
    _register_content(pm_db, data_root, "c-done")
    _touch_f1(data_root, "c-done")
    _touch_f2(data_root, "c-done")
    _touch_f5(data_root, "c-done")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    assert rec.f1_calls == rec.f2_calls == rec.f5_calls == []
    assert report.skipped_complete == 1
    # Skips must not stamp stage_status (manual backfill history preserved).
    assert _stage_rows(pm_db, "c-done") == {"F0": "ready"}


def test_f1_never_rerun_when_envelope_exists(data_root, pm_db):
    """Pin: an existing F1 envelope is sacred (uuid churn on re-run)."""
    _register_content(pm_db, data_root, "c-half")
    _touch_f1(data_root, "c-half")  # F1 done, F2/F5 missing
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    assert rec.f1_calls == []  # never re-run
    assert rec.f2_calls == ["c-half"]
    assert rec.f5_calls == ["c-half"]
    assert report.f1_ran == 0 and report.f2_ran == 1 and report.f5_ran == 1


def test_failure_writes_stage_status_and_isolates(data_root, pm_db):
    _register_content(pm_db, data_root, "c-boom")
    _register_content(pm_db, data_root, "c-ok")
    rec = StageRecorder(data_root)
    original_f2 = rec.f2

    def exploding_f2(f1_path, r, root):
        if r.content_id == "c-boom":
            raise RuntimeError("anchor exploded")
        return original_f2(f1_path, r, root)

    report = drive_once(
        data_root=data_root,
        db_path=pm_db,
        run_settle=False,
        f1_executor=rec.f1,
        f2_executor=exploding_f2,
        f5_executor=rec.f5,
    )

    assert len(report.failures) == 1
    failure = report.failures[0]
    assert failure["content_id"] == "c-boom"
    assert failure["stage"] == "F2"
    assert failure["error_code"] == "RuntimeError"
    assert _stage_rows(pm_db, "c-boom")["F2"] == "failed"
    # The healthy sibling still completed.
    assert _stage_rows(pm_db, "c-ok")["F5"] == "ready"


def test_zero_action_envelope_not_rerun_next_drive(data_root, pm_db):
    _register_content(pm_db, data_root, "c-empty")
    rec = StageRecorder(data_root)
    rec.f5_count = 0  # legitimate zero-action outcome: no output file

    first = _drive(data_root, pm_db, rec)
    assert first.f5_ran == 1
    assert _stage_rows(pm_db, "c-empty")["F5"] == "ready"

    second = _drive(data_root, pm_db, rec)
    assert rec.f5_calls == ["c-empty"]  # not re-extracted
    assert second.skipped_complete == 1


def test_excluded_content_skipped(data_root, pm_db):
    _register_content(
        pm_db, data_root, "c-cover",
        raw_path=str(data_root / "raw" / "bilibili" / "cover.png"),
    )
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    assert report.skipped_excluded == 1
    assert rec.f1_calls == []
    assert _stage_rows(pm_db, "c-cover") == {"F0": "ready"}


def test_limit_caps_scanned(data_root, pm_db):
    for i in range(5):
        _register_content(pm_db, data_root, f"c-{i}")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, limit=2)

    assert report.scanned == 2
    assert len(rec.f1_calls) == 2


def test_dry_run_writes_nothing(data_root, pm_db):
    _register_content(pm_db, data_root, "c-plan")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, dry_run=True)

    assert report.dry_run is True
    assert report.f1_ran == 1  # counted as would-run
    assert rec.f1_calls == []  # but nothing executed
    assert _stage_rows(pm_db, "c-plan") == {"F0": "ready"}
    conn = sqlite3.connect(pm_db)
    runs = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
    conn.close()
    assert runs == 0


def test_pipeline_runs_row_written(data_root, pm_db):
    _register_content(pm_db, data_root, "c-run")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    conn = sqlite3.connect(pm_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM pipeline_runs WHERE run_id = ?", (report.run_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["run_type"] == "pipeline_drive"
    assert row["status"] == "completed"
    summary = json.loads(row["summary_json"])
    assert summary["f5_ran"] == 1


def test_missing_content_record_is_reconciled_not_failed(data_root, pm_db):
    # Registered in the ledger but the ContentRecord file vanished (the F0
    # write-atomicity gap: PM row outlived its durable record).
    _register_content(pm_db, data_root, "c-ghost")
    (data_root / "F0_intake" / "local" / "c-ghost.json").unlink()
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    # Handled as a reconciliation, NOT a failure — a run with only orphans is clean.
    assert report.failures == []
    assert len(report.reconciled) == 1
    assert report.reconciled[0]["content_id"] == "c-ghost"
    assert report.reconciled[0]["action"] == "marked_failed"
    assert rec.f1_calls == []
    # The F0 row is flipped to 'failed' so it leaves the ready set.
    assert _stage_rows(pm_db, "c-ghost")["F0"] == "failed"


def test_reconciled_orphan_not_rediscovered_next_run(data_root, pm_db):
    _register_content(pm_db, data_root, "c-ghost")
    (data_root / "F0_intake" / "local" / "c-ghost.json").unlink()
    rec = StageRecorder(data_root)

    first = _drive(data_root, pm_db, rec)
    assert len(first.reconciled) == 1

    # Second pass: the orphan is no longer F0='ready', so it isn't scanned.
    second = _drive(data_root, pm_db, rec)
    assert second.reconciled == []
    assert second.failures == []
    assert second.scanned == 0


def test_reimport_restores_reconciled_orphan(data_root, pm_db):
    _register_content(pm_db, data_root, "c-ghost")
    (data_root / "F0_intake" / "local" / "c-ghost.json").unlink()
    rec = StageRecorder(data_root)
    _drive(data_root, pm_db, rec)  # reconcile → F0 failed
    assert _stage_rows(pm_db, "c-ghost")["F0"] == "failed"

    # A genuine re-import rewrites the record + flips F0 back to 'ready'.
    _register_content(pm_db, data_root, "c-ghost")
    assert _stage_rows(pm_db, "c-ghost")["F0"] == "ready"
    report = _drive(data_root, pm_db, rec)
    assert report.reconciled == []
    assert rec.f1_calls == ["c-ghost"]  # now processed normally


def test_dry_run_reports_orphan_without_writing(data_root, pm_db):
    _register_content(pm_db, data_root, "c-ghost")
    (data_root / "F0_intake" / "local" / "c-ghost.json").unlink()
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, dry_run=True)

    assert len(report.reconciled) == 1
    assert report.reconciled[0]["action"] == "would_mark_failed"
    # dry-run must NOT mutate the ledger — row stays 'ready'.
    assert _stage_rows(pm_db, "c-ghost")["F0"] == "ready"


def test_legacy_identity_rows_skipped_quietly(data_root, pm_db):
    """cnt_* rows (2026-06-04 manifest backfill projections) are not driver
    input — counted, never flagged as failures."""
    _register_content(pm_db, data_root, "cnt_deadbeef00000001")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    assert report.skipped_legacy_identity == 1
    assert report.failures == []
    assert rec.f1_calls == []


def test_finds_record_nested_under_creator_dir(data_root, pm_db):
    _register_content(pm_db, data_root, "c-nested")
    src = data_root / "F0_intake" / "local" / "c-nested.json"
    nested = data_root / "F0_intake" / "local" / "9you" / "c-nested.json"
    nested.parent.mkdir(parents=True)
    nested.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    src.unlink()
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)

    assert report.failures == []
    assert rec.f1_calls == ["c-nested"]


def test_report_to_dict_roundtrip(data_root, pm_db):
    report = DriveReport(run_id="drive_test")
    d = report.to_dict()
    assert d["run_id"] == "drive_test"
    assert d["skipped_locked"] is False
    assert json.dumps(d)  # JSON-serializable


def test_concurrent_drive_is_skipped(data_root, pm_db):
    """A drive holding the single-flight lock makes a concurrent pass a no-op."""
    from finer.pipeline.driver import _acquire_drive_lock, _release_drive_lock

    _register_content(pm_db, data_root, "c-lock")
    rec = StageRecorder(data_root)

    held = _acquire_drive_lock(pm_db.parent)  # simulate another drive in flight
    try:
        report = _drive(data_root, pm_db, rec)  # db_path=pm_db → same lock dir
        assert report.skipped_locked is True
        assert report.scanned == 0
        assert rec.f1_calls == []  # nothing processed
    finally:
        _release_drive_lock(held)

    # Lock released → a subsequent drive proceeds normally.
    report2 = _drive(data_root, pm_db, rec)
    assert report2.skipped_locked is False
    assert rec.f1_calls == ["c-lock"]
