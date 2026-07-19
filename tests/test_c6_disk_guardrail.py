"""Tests for the C6 external-disk guardrail: mount health, backup pruning, intake.

No real external volume is required — the volume path is env-overridable and
os.path.ismount is False for a plain tmp dir, which simulates "unmounted".
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import finer.ops.mount_health as mh
import scripts.prune_backups as pb
from finer.ops.mount_health import (
    broker_mount_alert,
    broker_source_volume,
    broker_volume_available,
    is_volume_mounted,
)


# ---------------------------------------------------------------------------
# mount_health
# ---------------------------------------------------------------------------


def test_broker_source_volume_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINER_BROKER_SOURCE_VOLUME", raising=False)
    assert broker_source_volume() == Path("/Volumes/NAMEZY")
    monkeypatch.setenv("FINER_BROKER_SOURCE_VOLUME", "/tmp/somevol")
    assert broker_source_volume() == Path("/tmp/somevol")


def test_plain_dir_is_not_mounted(tmp_path: Path) -> None:
    assert is_volume_mounted(tmp_path) is False


def test_broker_volume_unavailable_when_unmounted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FINER_BROKER_SOURCE_VOLUME", str(tmp_path / "nope"))
    assert broker_volume_available() is False


def test_broker_mount_alert_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FINER_BROKER_SOURCE_VOLUME", str(tmp_path / "vol"))
    ev = broker_mount_alert(skipped=7, job="pipeline_drive")
    assert ev.alert_type == "volume_unmounted" and ev.severity == "warning"
    assert ev.fix_hint and ev.context["skipped"] == 7 and ev.context["job"] == "pipeline_drive"
    assert str(tmp_path / "vol") in ev.context["volume"]


# ---------------------------------------------------------------------------
# prune_backups
# ---------------------------------------------------------------------------


def _make_backup_dir(parent: Path, name: str, *, age_days: float) -> Path:
    p = parent / name
    p.mkdir(parents=True)
    (p / "data.json").write_text("{}", encoding="utf-8")
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def test_plan_family_keeps_recent_protects_named(tmp_path: Path) -> None:
    # 4 timestamped F5 snapshots (varying age) + 1 named safety snapshot
    _make_backup_dir(tmp_path, "F5_executed.bak-20260101-000000", age_days=40)
    _make_backup_dir(tmp_path, "F5_executed.bak-20260201-000000", age_days=30)
    _make_backup_dir(tmp_path, "F5_executed.bak-20260301-000000", age_days=20)
    _make_backup_dir(tmp_path, "F5_executed.bak-20260401-000000", age_days=1)
    _make_backup_dir(tmp_path, "F5_executed.bak-prebroker", age_days=99)

    plan = pb.plan_family(tmp_path, "F5_executed", keep=2)
    assert {i.path.name for i in plan.protected} == {"F5_executed.bak-prebroker"}
    # newest 2 kept
    assert {i.path.name for i in plan.kept} == {
        "F5_executed.bak-20260401-000000", "F5_executed.bak-20260301-000000",
    }
    # older 2 timestamped marked for deletion
    assert {i.path.name for i in plan.to_delete} == {
        "F5_executed.bak-20260101-000000", "F5_executed.bak-20260201-000000",
    }


def test_delete_backup_removes_dir_and_wal_shm(tmp_path: Path) -> None:
    base = tmp_path / "finer.project.sqlite3.bak-20260101-000000"
    base.write_text("db", encoding="utf-8")
    Path(str(base) + "-wal").write_text("wal", encoding="utf-8")
    Path(str(base) + "-shm").write_text("shm", encoding="utf-8")
    info = pb.scan_family(tmp_path, "finer.project.sqlite3")[0]

    removed = pb.delete_backup(info)
    assert not base.exists()
    assert not Path(str(base) + "-wal").exists() and not Path(str(base) + "-shm").exists()
    assert len(removed) == 3


def test_scan_family_excludes_wal_shm_siblings(tmp_path: Path) -> None:
    base = tmp_path / "finer.project.sqlite3.bak-20260101-000000"
    base.write_text("db", encoding="utf-8")
    Path(str(base) + "-wal").write_text("wal", encoding="utf-8")
    infos = pb.scan_family(tmp_path, "finer.project.sqlite3")
    assert [i.path.name for i in infos] == ["finer.project.sqlite3.bak-20260101-000000"]


def test_prune_main_dry_run_deletes_nothing(tmp_path: Path) -> None:
    (tmp_path / "project_memory").mkdir()
    _make_backup_dir(tmp_path, "F5_executed.bak-20260101-000000", age_days=40)
    _make_backup_dir(tmp_path, "F5_executed.bak-20260401-000000", age_days=1)
    rc = pb.main(["--data-root", str(tmp_path), "--keep", "1"])
    assert rc == 0
    assert (tmp_path / "F5_executed.bak-20260101-000000").exists()  # dry-run: nothing removed


def test_prune_main_execute_deletes_old(tmp_path: Path) -> None:
    (tmp_path / "project_memory").mkdir()
    old = _make_backup_dir(tmp_path, "F5_executed.bak-20260101-000000", age_days=40)
    new = _make_backup_dir(tmp_path, "F5_executed.bak-20260401-000000", age_days=1)
    rc = pb.main(["--data-root", str(tmp_path), "--keep", "1", "--execute"])
    assert rc == 0
    assert not old.exists()  # pruned
    assert new.exists()       # kept


# ---------------------------------------------------------------------------
# broker intake CLI guard
# ---------------------------------------------------------------------------


def test_intake_main_skips_when_volume_unmounted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from finer.ingestion import broker_research_intake as bri

    monkeypatch.setenv("FINER_BROKER_SOURCE_VOLUME", str(tmp_path / "unmounted"))
    monkeypatch.delenv("FINER_ALERT_WEBHOOK", raising=False)  # send_alert is a no-op
    # meta path need not exist — the volume guard runs before the meta-exists check.
    rc = bri.main(["--meta-jsonl", str(tmp_path / "does_not_exist.jsonl")])
    assert rc == 0  # graceful skip, not a parser.error / SystemExit


# ---------------------------------------------------------------------------
# CLI drive → mount alert
# ---------------------------------------------------------------------------


def test_drive_emits_mount_alert_on_skipped_unmounted(monkeypatch: pytest.MonkeyPatch) -> None:
    import finer.cli as cli
    import finer.ops.alerts as alerts_mod

    sent = []
    monkeypatch.setattr(alerts_mod, "send_alert", lambda ev, **k: sent.append(ev) or True)

    report = {"run_id": "d1", "scanned": 3, "skipped_unmounted": 2, "failures": []}
    cli._ledger_and_alert_drive(report, duration_s=0.1, tokens_spent=0)

    mount_alerts = [e for e in sent if e.alert_type == "volume_unmounted"]
    assert len(mount_alerts) == 1
    assert mount_alerts[0].context["skipped"] == 2
