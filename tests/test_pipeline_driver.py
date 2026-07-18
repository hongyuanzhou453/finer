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


def _register_content(
    db_path: Path,
    data_root: Path,
    content_id: str,
    *,
    source_channel: str | None = None,
    **record_overrides,
):
    """Write the FK parents + stage_status F0 ready row + ContentRecord file.

    Mirrors f0_index_writer: content_identities → contents → stage_status
    (stage_status has a FOREIGN KEY on contents.content_id). ``source_channel``
    tags the F0 stage_status row (NULL by default = pre-C1 legacy row).
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
        "INSERT INTO stage_status (content_id, stage, status, source_channel, updated_at) "
        "VALUES (?, 'F0', 'ready', ?, ?) "
        "ON CONFLICT(content_id, stage) DO UPDATE SET status='ready', source_channel=excluded.source_channel",
        (content_id, source_channel, now),
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
    # Declarative exclusion keys on source_platform (bilibili covers = no text).
    _register_content(
        pm_db, data_root, "c-cover",
        source_platform="bilibili",
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


def test_f1_executor_resolves_relative_raw_path_against_data_root(
    data_root, monkeypatch
):
    """Regression: ``rec.raw_path`` is persisted relative to data_root (files.py
    writes ``raw_path.relative_to(DATA_ROOT)``). The F1 executor must resolve it
    against data_root, not the process CWD — otherwise every real upload fails
    F1 with ``API_NTF_001 raw file missing`` and the driver never produces
    throughput (the activation bug found on the first real run)."""
    import finer.pipeline.driver as drv
    from finer.schemas.content import ContentRecord

    # A real raw file under data_root, referenced by a RELATIVE raw_path.
    raw_file = data_root / "raw" / "local" / "sample.txt"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text("看好半导体板块。", encoding="utf-8")

    rec = ContentRecord(
        content_id="c-rel-path",
        source_type="manual_upload",
        source_platform="local",
        creator_id="trader_ji",
        collected_at=datetime(2026, 5, 31),
        title="sample",
        raw_path="raw/local/sample.txt",  # relative, exactly as production persists
        file_type="text",
    )

    captured = {}

    class _StubEnvelope:
        def model_dump_json(self, indent=2):
            return "{}"

    class _StubRouter:
        def route(self, r, raw_path):
            # The executor must hand us an EXISTING, data_root-resolved path.
            captured["raw_path"] = raw_path
            assert raw_path.exists(), f"unresolved path: {raw_path}"
            return _StubEnvelope(), None

    monkeypatch.setattr(drv, "_ROUTER", _StubRouter())

    out = drv._default_f1_executor(rec, data_root)

    assert out == data_root / "F1_standardized" / "c-rel-path" / "content_envelope.json"
    assert out.exists()
    assert captured["raw_path"] == data_root / "raw" / "local" / "sample.txt"


def test_f1_executor_still_accepts_absolute_raw_path(data_root, monkeypatch):
    """Absolute raw_paths (legacy records / receipts) must keep working."""
    import finer.pipeline.driver as drv
    from finer.schemas.content import ContentRecord

    raw_file = data_root / "raw" / "abs.txt"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text("绝对路径样本。", encoding="utf-8")

    rec = ContentRecord(
        content_id="c-abs-path",
        source_type="manual_upload",
        source_platform="local",
        collected_at=datetime(2026, 5, 31),
        title="abs",
        raw_path=str(raw_file),  # absolute
        file_type="text",
    )

    class _StubEnvelope:
        def model_dump_json(self, indent=2):
            return "{}"

    class _StubRouter:
        def route(self, r, raw_path):
            assert raw_path == raw_file
            return _StubEnvelope(), None

    monkeypatch.setattr(drv, "_ROUTER", _StubRouter())
    out = drv._default_f1_executor(rec, data_root)
    assert out.exists()


def test_f1_executor_resolves_repo_root_relative_raw_path(data_root, monkeypatch):
    """Regression: 215/242 real F0 records (feishu backlog) store raw_path
    prefixed 'data/...' (repo-root-relative); joining that onto data_root gave
    <data_root>/data/... and every backlog record failed F1."""
    import finer.pipeline.driver as drv
    from finer.schemas.content import ContentRecord

    raw_file = data_root / "raw" / "feishu" / "doc.md"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text("看好储能板块。", encoding="utf-8")

    rec = ContentRecord(
        content_id="c-data-prefix",
        source_type="feishu_chat",
        source_platform="feishu",
        collected_at=datetime(2026, 6, 1),
        title="doc",
        raw_path="data/raw/feishu/doc.md",  # repo-root-relative, as persisted
        file_type="text",
    )

    class _StubEnvelope:
        def model_dump_json(self, indent=2):
            return "{}"

    class _StubRouter:
        def route(self, r, raw_path):
            assert raw_path == raw_file, raw_path
            return _StubEnvelope(), None

    monkeypatch.setattr(drv, "_ROUTER", _StubRouter())
    out = drv._default_f1_executor(rec, data_root)
    assert out.exists()


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


# =============================================================================
# C2: channel filter + stage whitelist (DriveRunConfig)
# =============================================================================


def _broker(pm_db, data_root, content_id):
    """Register a broker PDF F0 row (source_channel + source_platform = broker)."""
    return _register_content(
        pm_db, data_root, content_id,
        source_channel="broker",
        source_platform="broker",
        source_type="research_report",
        file_type="pdf",
        raw_path=str(data_root / "raw" / "broker" / f"{content_id}.pdf"),
    )


def test_channel_filter_scopes_discovery_to_broker(data_root, pm_db):
    _broker(pm_db, data_root, "broker_a")
    _register_content(pm_db, data_root, "feishu_b", source_channel="feishu", source_platform="feishu")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, channel="broker")

    assert report.scanned == 1
    assert rec.f1_calls == ["broker_a"]


def test_feishu_channel_excludes_broker_rows(data_root, pm_db):
    _broker(pm_db, data_root, "broker_a")
    _register_content(pm_db, data_root, "feishu_b", source_channel="feishu", source_platform="feishu")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, channel="feishu")

    assert "broker_a" not in rec.f1_calls
    assert rec.f1_calls == ["feishu_b"]


def test_all_channel_default_drives_everything(data_root, pm_db):
    _broker(pm_db, data_root, "broker_a")
    _register_content(pm_db, data_root, "legacy_null")  # NULL source_channel (pre-C1)
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec)  # channel defaults to 'all'

    assert report.scanned == 2
    assert set(rec.f1_calls) == {"broker_a", "legacy_null"}


def test_broker_pdf_is_not_excluded(data_root, pm_db):
    """R1 guard: broker research PDFs must drive (not silently evaporate)."""
    _broker(pm_db, data_root, "broker_pdf")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, channel="broker")

    assert report.skipped_excluded == 0
    assert rec.f1_calls == ["broker_pdf"]


def test_stages_whitelist_stops_before_f5(data_root, pm_db):
    _broker(pm_db, data_root, "c-x")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, channel="broker", stages=["f1", "f2"])

    assert rec.f1_calls == ["c-x"]
    assert rec.f2_calls == ["c-x"]
    assert rec.f5_calls == []           # F5 not requested
    assert report.f5_ran == 0
    assert _stage_rows(pm_db, "c-x").get("F5") is None


def test_config_recorded_in_report(data_root, pm_db):
    _broker(pm_db, data_root, "c-cfg")
    rec = StageRecorder(data_root)

    report = _drive(data_root, pm_db, rec, channel="broker", stages=["f1", "f2"], limit=5)

    assert report.config is not None
    assert report.config["channel"] == "broker"
    assert report.config["stages"] == ["f1", "f2"]
    assert report.config["max_items"] == 5
    assert report.to_dict()["config"]["channel"] == "broker"


def test_settle_gated_by_stage_whitelist(data_root, pm_db, monkeypatch):
    import finer.backtest.settle as settle_mod

    calls: list = []

    class _FakeSettle:
        def to_dict(self):
            return {"settled": 0}

    def _fake_settle(**kwargs):
        calls.append(kwargs)
        return _FakeSettle()

    monkeypatch.setattr(settle_mod, "settle_actions", _fake_settle)
    _broker(pm_db, data_root, "c-s")
    rec = StageRecorder(data_root)

    # settle in the default stage set + run_settle=True -> called once
    drive_once(
        data_root=data_root, db_path=pm_db, run_settle=True, channel="broker",
        f1_executor=rec.f1, f2_executor=rec.f2, f5_executor=rec.f5,
    )
    assert len(calls) == 1

    # stages excludes settle -> settle_actions NOT called even with run_settle=True
    calls.clear()
    drive_once(
        data_root=data_root, db_path=pm_db, run_settle=True, channel="broker",
        stages=["f1", "f2", "f5"],
        f1_executor=rec.f1, f2_executor=rec.f2, f5_executor=rec.f5,
    )
    assert calls == []
