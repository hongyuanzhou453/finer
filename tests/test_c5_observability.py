"""Tests for C5 observability: run ledger, alerts, log rotation, ops CLI.

No real webhook is called — httpx is mocked. No real driver runs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

import pytest

import finer.ops.alerts as alerts_mod
from finer.ops.alerts import (
    check_budget,
    check_failure_rate,
    check_heartbeat_stale,
    format_alert,
    self_test_event,
    send_alert,
)
from finer.ops.ledger import (
    build_drive_ledger_entry,
    build_settle_ledger_entry,
    ledger_path_for_day,
    write_ledger_entry,
)
from finer.ops.log_rotation import prune_old_logs
from finer.schemas.heartbeat import HeartbeatState
from finer.schemas.ops import AlertEvent, RunLedgerEntry

SECRET_WEBHOOK = "https://open.feishu.cn/hook/SECRET-TOKEN-abc123"


# ---------------------------------------------------------------------------
# Run ledger
# ---------------------------------------------------------------------------


def test_run_ledger_entry_serializes() -> None:
    entry = RunLedgerEntry(run_id="r1", job_type="pipeline_drive", status="completed")
    d = entry.to_dict()
    for key in ("run_id", "job_type", "ts", "status", "duration_s", "tokens_spent", "stats", "errors"):
        assert key in d


def test_write_ledger_appends_jsonl(tmp_path: Path) -> None:
    e1 = RunLedgerEntry(run_id="r1", job_type="pipeline_drive", status="completed")
    e2 = RunLedgerEntry(run_id="r2", job_type="settle", status="completed")
    write_ledger_entry(e1, run_state_dir=tmp_path)
    path = write_ledger_entry(e2, run_state_dir=tmp_path)
    assert path is not None and path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_id"] == "r1"
    assert json.loads(lines[1])["job_type"] == "settle"
    # lands in the day-partitioned ledger dir
    assert path == ledger_path_for_day(run_state_dir=tmp_path)


def test_build_drive_ledger_maps_failures_to_canonical() -> None:
    report = {
        "run_id": "drive_x",
        "scanned": 5, "f1_ran": 1, "f2_ran": 1, "f5_ran": 0, "skipped_complete": 2,
        "failures": [{"content_id": "c1", "stage": "F5", "error_code": "F5_ERR", "error_message": "boom"}],
        "dry_run": False,
    }
    entry = build_drive_ledger_entry(report, tokens_spent=1234, duration_s=2.5)
    assert entry.job_type == "pipeline_drive"
    assert entry.status == "failed"  # has failures
    assert entry.tokens_spent == 1234
    assert entry.stats["scanned"] == 5 and entry.stats["failure_count"] == 1
    # error entry reuses the canonical Line F envelope fields
    err = entry.errors[0]
    assert err.code == "F5_ERR" and err.stage == "F5" and err.content_id == "c1"
    assert err.fix_hint  # present


def test_build_drive_ledger_status_variants() -> None:
    assert build_drive_ledger_entry({"run_id": "a", "scanned": 1, "failures": []}, tokens_spent=0, duration_s=0).status == "completed"
    assert build_drive_ledger_entry({"run_id": "b", "skipped_locked": True}, tokens_spent=0, duration_s=0).status == "skipped_locked"


def test_build_settle_ledger_entry() -> None:
    report = {"verified": 3, "failed": 1, "pending": 10, "backup": "/tmp/x"}
    entry = build_settle_ledger_entry(report, run_id="settle_1", duration_s=1.0)
    assert entry.job_type == "settle"
    assert entry.stats["verified"] == 3
    assert "backup" not in entry.stats  # backup path is not a stat


# ---------------------------------------------------------------------------
# Alert checks
# ---------------------------------------------------------------------------


def test_failure_rate_trips_above_threshold() -> None:
    ev = check_failure_rate({"scanned": 10, "failure_count": 3})
    assert ev is not None and ev.alert_type == "failure_rate" and ev.severity == "warning"
    assert ev.fix_hint and ev.context["rate"] == 0.3


def test_failure_rate_quiet_below_threshold_and_edges() -> None:
    assert check_failure_rate({"scanned": 100, "failure_count": 1}) is None  # 1%
    assert check_failure_rate({"scanned": 0, "failure_count": 0}) is None
    assert check_failure_rate({"scanned": 10, "failure_count": 0}) is None


def test_budget_alert() -> None:
    assert check_budget("completed") is None
    ev = check_budget("budget_exceeded", context={"batch_id": "f1_broker"})
    assert ev is not None and ev.alert_type == "budget_exceeded" and ev.fix_hint


def test_heartbeat_stale_and_fresh() -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    fresh = HeartbeatState(
        pid=1, job_type="pipeline_drive", started_at=now.isoformat(),
        last_pass_at=(now - timedelta(seconds=5)).isoformat(), interval_seconds=10,
    )
    assert check_heartbeat_stale(fresh, now=now) is None  # 5s < 2×10

    stale = HeartbeatState(
        pid=1, job_type="pipeline_drive", started_at=now.isoformat(),
        last_pass_at=(now - timedelta(seconds=100)).isoformat(), interval_seconds=10,
    )
    ev = check_heartbeat_stale(stale, now=now)
    assert ev is not None and ev.severity == "critical" and ev.fix_hint
    assert ev.context["age_s"] == 100


def test_heartbeat_missing_is_critical() -> None:
    ev = check_heartbeat_stale(None)
    assert ev is not None and ev.alert_type == "heartbeat_timeout" and ev.severity == "critical"


# ---------------------------------------------------------------------------
# Webhook delivery (mocked)
# ---------------------------------------------------------------------------


def _install_fake_httpx(monkeypatch: pytest.MonkeyPatch, status_code: int = 200) -> Dict[str, Any]:
    captured: Dict[str, Any] = {}

    class FakeResp:
        def __init__(self) -> None:
            self.status_code = status_code

    class FakeClient:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def post(self, url: str, json: Dict[str, Any]) -> FakeResp:
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    monkeypatch.setattr(alerts_mod.httpx, "Client", FakeClient)
    return captured


def test_send_alert_unset_webhook_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINER_ALERT_WEBHOOK", raising=False)
    assert send_alert(self_test_event()) is False  # no crash, just False


def test_send_alert_posts_feishu_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_httpx(monkeypatch)
    ev = check_failure_rate({"scanned": 10, "failure_count": 5})
    assert send_alert(ev, url=SECRET_WEBHOOK) is True
    assert captured["url"] == SECRET_WEBHOOK
    body = captured["json"]
    assert body["msg_type"] == "text"
    text = body["content"]["text"]
    assert "failure rate" in text.lower()
    assert ev.fix_hint in text  # remediation reaches the operator


def test_send_alert_never_leaks_url_into_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_httpx(monkeypatch)
    send_alert(self_test_event(), url=SECRET_WEBHOOK)
    assert "SECRET-TOKEN" not in captured["json"]["content"]["text"]


def test_send_alert_non_200_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_httpx(monkeypatch, status_code=500)
    assert send_alert(self_test_event(), url=SECRET_WEBHOOK) is False


def test_format_alert_contains_fix_hint() -> None:
    ev = AlertEvent(
        alert_type="test", severity="warning", title="T", message="M", fix_hint="do X", context={"a": 1}
    )
    out = format_alert(ev)
    assert "do X" in out and "T" in out and "a=1" in out


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------


def test_prune_old_logs_removes_only_stale(tmp_path: Path) -> None:
    old = tmp_path / "pipeline-drive-20260101.log"
    new = tmp_path / "pipeline-drive-today.log"
    old.write_text("old")
    new.write_text("new")
    twenty_days = time.time() - 20 * 86400
    os.utime(old, (twenty_days, twenty_days))

    removed = prune_old_logs(tmp_path, keep_days=14)
    assert old in removed and not old.exists()
    assert new.exists()


def test_prune_old_logs_missing_dir_is_noop(tmp_path: Path) -> None:
    assert prune_old_logs(tmp_path / "nope") == []


def test_prune_old_logs_rejects_negative_keep_days(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        prune_old_logs(tmp_path, keep_days=-1)


# ---------------------------------------------------------------------------
# Ops CLI
# ---------------------------------------------------------------------------


def test_cli_alert_test_without_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    import finer.cli as cli

    monkeypatch.delenv("FINER_ALERT_WEBHOOK", raising=False)
    args = cli.build_parser().parse_args(["alert-test"])
    result = cli._cmd_alert_test(args)
    assert result["ok"] is False and "FINER_ALERT_WEBHOOK" in result["error"]


def test_cli_alert_test_with_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    import finer.cli as cli

    _install_fake_httpx(monkeypatch)
    args = cli.build_parser().parse_args(["alert-test", "--webhook", SECRET_WEBHOOK])
    result = cli._cmd_alert_test(args)
    assert result["ok"] is True and result["sent"] is True


def test_cli_alert_check_fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import finer.cli as cli
    from finer.ops.heartbeat import write_heartbeat

    write_heartbeat(
        HeartbeatState(pid=1, job_type="pipeline_drive", started_at="2026-07-18T00:00:00+00:00", interval_seconds=999999),
        run_state_dir=tmp_path,
    )
    args = cli.build_parser().parse_args(["alert-check", "--run-state-dir", str(tmp_path)])
    result = cli._cmd_alert_check(args)
    assert result["ok"] is True and result["stale"] is False


def test_cli_prune_logs(tmp_path: Path) -> None:
    import finer.cli as cli

    old = tmp_path / "x-old.log"
    old.write_text("x")
    twenty_days = time.time() - 20 * 86400
    os.utime(old, (twenty_days, twenty_days))
    args = cli.build_parser().parse_args(["prune-logs", "--logs-dir", str(tmp_path), "--keep-days", "14"])
    result = cli._cmd_prune_logs(args)
    assert result["ok"] is True and result["removed_count"] == 1
