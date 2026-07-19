"""Log retention (Phase 0 C5 / OPS-5).

The wrapper scripts already roll logs by day (``logs/<name>-YYYYMMDD.log``); this
prunes files older than a retention window. Best-effort and idempotent.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_KEEP_DAYS = 14


def prune_old_logs(
    logs_dir: Path,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    pattern: str = "*.log",
    now: Optional[float] = None,
) -> List[Path]:
    """Delete log files older than ``keep_days`` (by mtime); return what was removed.

    Missing directory → no-op. Individual unlink failures are logged and skipped
    so one locked file never aborts the sweep.
    """
    if keep_days < 0:
        raise ValueError("keep_days must be >= 0")
    if not logs_dir.is_dir():
        return []
    now = now if now is not None else time.time()
    cutoff = now - keep_days * 86400
    removed: List[Path] = []
    for path in sorted(logs_dir.glob(pattern)):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path)
        except OSError as exc:
            logger.warning("could not prune %s: %s", path.name, exc)
    return removed
