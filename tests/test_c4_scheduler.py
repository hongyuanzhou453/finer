"""Tests for the C4 scheduler shell: R4 --stages guard, heartbeat, launchd plists.

No real driver or launchd is invoked — the loop's report→heartbeat mapping is
tested via the extracted helper, and the plists are validated as files.
"""

from __future__ import annotations

import argparse
import plistlib
import stat
from pathlib import Path

import pytest

import finer.cli as cli
from finer.ops.heartbeat import read_heartbeat, write_heartbeat
from finer.schemas.heartbeat import HeartbeatState

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# R4 — illegal --stages is rejected at parse time (not a bare traceback)
# ---------------------------------------------------------------------------


def test_stages_arg_accepts_valid() -> None:
    assert cli._stages_arg("f1,f2") == ["f1", "f2"]
    assert cli._stages_arg(" f1 , settle ") == ["f1", "settle"]


@pytest.mark.parametrize("bad", ["f1,f9", "nope", "", " , "])
def test_stages_arg_rejects_invalid(bad: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli._stages_arg(bad)


def test_cli_parses_valid_stages_to_list() -> None:
    args = cli.build_parser().parse_args(["pipeline-drive", "--stages", "f1,f2"])
    assert args.stages == ["f1", "f2"]


@pytest.mark.parametrize("bad", ["f1,f9", "bogus", ""])
def test_cli_rejects_bad_stages_with_exit_2(bad: str) -> None:
    """A launchd/--watch job must fail fast, not dump a pydantic traceback."""
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["pipeline-drive", "--stages", bad])
    assert exc.value.code == 2


def test_cmd_pipeline_drive_normalizes_string_stages() -> None:
    """Programmatic Namespace with a raw string is still validated (no traceback)."""
    ns = argparse.Namespace(
        stages="f1,f9", limit=None, no_settle=False, dry_run=True, channel="all", watch=None
    )
    result = cli._cmd_pipeline_drive(ns)
    assert "error" in result and "stages" in result["error"]


# ---------------------------------------------------------------------------
# Heartbeat — schema, report→state mapping, IO round-trip
# ---------------------------------------------------------------------------


def test_heartbeat_state_serializes() -> None:
    hb = HeartbeatState(
        pid=1, job_type="pipeline_drive", started_at="2026-07-18T00:00:00Z", cycles=2
    )
    d = hb.to_dict()
    for key in ("pid", "job_type", "started_at", "last_pass_at", "cycles", "lock_holder", "last_pass_stats"):
        assert key in d


def test_drive_heartbeat_state_maps_report() -> None:
    hb = cli._drive_heartbeat_state(
        pid=42,
        started_at="2026-07-18T00:00:00Z",
        cycle=5,
        interval=900,
        report={
            "scanned": 10, "f1_ran": 2, "f2_ran": 1, "f5_ran": 0,
            "skipped_complete": 7, "failures": [{"x": 1}, {"y": 2}], "skipped_locked": False,
        },
    )
    assert hb.pid == 42 and hb.cycles == 5 and hb.interval_seconds == 900
    assert hb.lock_holder is True
    assert hb.last_pass_stats["failures"] == 2  # count, not the list
    assert hb.last_pass_stats["scanned"] == 10


def test_drive_heartbeat_lock_holder_false_when_skipped_locked() -> None:
    hb = cli._drive_heartbeat_state(
        pid=1, started_at="t", cycle=1, interval=1, report={"skipped_locked": True}
    )
    assert hb.lock_holder is False


def test_heartbeat_write_read_roundtrip(tmp_path: Path) -> None:
    hb = HeartbeatState(pid=99, job_type="pipeline_drive", started_at="2026-07-18T00:00:00Z", cycles=3)
    path = write_heartbeat(hb, run_state_dir=tmp_path)
    assert path is not None and path.exists()
    back = read_heartbeat(run_state_dir=tmp_path)
    assert back is not None and back.pid == 99 and back.cycles == 3


def test_read_heartbeat_absent_is_none(tmp_path: Path) -> None:
    assert read_heartbeat(run_state_dir=tmp_path) is None


def test_write_heartbeat_never_raises_on_bad_dir(tmp_path: Path) -> None:
    # Point at a path whose parent is a file so mkdir fails; must return None,
    # not raise (heartbeat is best-effort and must never break the loop).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    hb = HeartbeatState(pid=1, job_type="pipeline_drive", started_at="t")
    assert write_heartbeat(hb, run_state_dir=blocker / "sub") is None


# ---------------------------------------------------------------------------
# launchd plists + wrapper scripts (repo files)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,label",
    [
        ("com.finer.pipeline-drive.plist", "com.finer.pipeline-drive"),
        ("com.finer.feishu-watch.plist", "com.finer.feishu-watch"),
    ],
)
def test_launchd_plist_is_wellformed(name: str, label: str) -> None:
    path = REPO_ROOT / "configs" / "launchd" / name
    with open(path, "rb") as fh:
        d = plistlib.load(fh)  # strict XML: rejects '--' in comments etc.
    assert d["Label"] == label
    assert d["RunAtLoad"] is True
    assert d["KeepAlive"] is True
    assert d["ProgramArguments"][0].endswith(".sh")


@pytest.mark.parametrize("script", ["run_pipeline_drive.sh", "run_feishu_watch.sh"])
def test_wrapper_scripts_executable(script: str) -> None:
    path = REPO_ROOT / "scripts" / "ops" / script
    assert path.exists()
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR  # owner-executable
    body = path.read_text()
    assert ".venv/bin/python" in body  # runs from the project venv
    assert "finer.cli" in body
