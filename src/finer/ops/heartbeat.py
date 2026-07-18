"""Heartbeat read/write for resident driver loops (Phase 0 C4 / OPS-4).

A single JSON file (``data/run_state/heartbeat.json``) holding the latest
:class:`~finer.schemas.heartbeat.HeartbeatState`. Written atomically (tmp+replace)
at the end of every watch pass; read by a supervisor / alerting job to detect a
stalled loop (age > 2× interval). All writes are best-effort — a heartbeat
failure must never break the drive itself.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from finer.paths import DATA_ROOT
from finer.schemas.heartbeat import HeartbeatState

logger = logging.getLogger(__name__)

_HEARTBEAT_FILENAME = "heartbeat.json"


def heartbeat_path(run_state_dir: Optional[Path] = None) -> Path:
    base = run_state_dir if run_state_dir is not None else (DATA_ROOT / "run_state")
    return base / _HEARTBEAT_FILENAME


def write_heartbeat(state: HeartbeatState, run_state_dir: Optional[Path] = None) -> Optional[Path]:
    """Atomically persist the heartbeat; returns the path (or None on failure).

    Best-effort: any IO error is logged and swallowed so a heartbeat problem
    never interrupts the drive loop.
    """
    path = heartbeat_path(run_state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
    except Exception as exc:  # noqa: BLE001 — heartbeat must never break the loop
        logger.warning("heartbeat write failed: %s", exc)
        return None


def read_heartbeat(run_state_dir: Optional[Path] = None) -> Optional[HeartbeatState]:
    """Load the current heartbeat, or None if absent/unreadable."""
    path = heartbeat_path(run_state_dir)
    if not path.exists():
        return None
    try:
        return HeartbeatState.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat read failed: %s", exc)
        return None
