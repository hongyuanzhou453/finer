#!/usr/bin/env python3
"""Reconcile stage_status with on-disk truth: bri F5 rows + NULL channels (C3).

Two gaps left by the pre-C2 split-brain (driver vs. standalone broker script):

1. **bri F5 rows missing** — the standalone broker drive wrote
   ``data/F5_executed/bri_{content_id}_actions.json`` files but never
   registered a stage_status F5 row, so the driver's idempotency only held
   via the file-existence probe. Upsert ``F5='ready', source_channel='broker'``
   for every existing bri actions file.

2. **NULL source_channel rows** — rows written before migration 005 (legacy
   feishu/local F0 rows) and rows written by the pre-C3 driver/scaleup
   upserts carry ``source_channel=NULL``. Fill them from the F0 truth:
   the ContentRecord's ``source_platform`` (fallback: the content's F0 row
   channel). Rows whose content record cannot be found are left untouched
   and reported.

Dry-run by default; ``--execute`` writes. Never overwrites a non-NULL channel,
never downgrades a status. Idempotent.

Usage:
    python scripts/reconcile_stage_status_channels.py            # dry-run
    python scripts/reconcile_stage_status_channels.py --execute
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.paths import DATA_ROOT, F0_INDEX_DB_PATH  # noqa: E402


def _content_platform(data_root: Path, content_id: str) -> Optional[str]:
    """source_platform from the F0 ContentRecord file (any channel subdir)."""
    f0_root = data_root / "F0_intake"
    candidates = [f0_root / "broker" / f"{content_id}.json"]
    candidates += sorted(f0_root.glob(f"*/{content_id}.json"))
    candidates += [f0_root / f"{content_id}.json"]
    for path in candidates:
        if not path.exists() or ".receipt" in path.name:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        platform = doc.get("source_platform") or (doc.get("metadata") or {}).get(
            "source_platform"
        )
        if platform:
            return str(platform)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--execute", action="store_true",
                        help="write changes (default: dry-run report)")
    args = parser.parse_args()

    data_root = (args.data_root or DATA_ROOT).resolve()
    db_path = (args.db_path or F0_INDEX_DB_PATH).resolve()
    now = datetime.now(timezone.utc).isoformat()
    mode = "EXECUTE" if args.execute else "DRY-RUN"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats: Counter = Counter()
    unresolved: list[str] = []

    try:
        # ── 1. bri F5 rows ──────────────────────────────────────────────────
        f5_dir = data_root / "F5_executed"
        bri_files = sorted(f5_dir.glob("bri_*_actions.json"))
        existing_f5 = {
            r["content_id"]
            for r in conn.execute("SELECT content_id FROM stage_status WHERE stage='F5'")
        }
        for path in bri_files:
            content_id = path.name[len("bri_"):-len("_actions.json")]
            stats["bri_files_scanned"] += 1
            if content_id in existing_f5:
                stats["f5_rows_already_present"] += 1
                continue
            stats["f5_rows_to_insert"] += 1
            if args.execute:
                conn.execute(
                    """
                    INSERT INTO stage_status
                        (content_id, stage, status, updated_at, source_channel)
                    VALUES (?, 'F5', 'ready', ?, 'broker')
                    ON CONFLICT(content_id, stage) DO UPDATE SET
                        source_channel = COALESCE(stage_status.source_channel, 'broker'),
                        updated_at = excluded.updated_at
                    """,
                    (content_id, now),
                )
                stats["f5_rows_inserted"] += 1

        # ── 2. NULL source_channel rows ─────────────────────────────────────
        null_rows = conn.execute(
            "SELECT content_id, stage FROM stage_status WHERE source_channel IS NULL"
        ).fetchall()
        stats["null_channel_rows"] = len(null_rows)

        # F0-row channel as fallback per content (one query, then dict lookup)
        f0_channels: Dict[str, str] = {
            r["content_id"]: r["source_channel"]
            for r in conn.execute(
                "SELECT content_id, source_channel FROM stage_status "
                "WHERE stage='F0' AND source_channel IS NOT NULL"
            )
        }

        resolved_cache: Dict[str, Optional[str]] = {}
        for row in null_rows:
            cid = row["content_id"]
            if cid not in resolved_cache:
                resolved_cache[cid] = _content_platform(data_root, cid) or f0_channels.get(cid)
            channel = resolved_cache[cid]
            if channel is None:
                stats["null_rows_unresolved"] += 1
                if len(unresolved) < 20:
                    unresolved.append(f"{cid} [{row['stage']}]")
                continue
            stats[f"null_rows_resolvable_to_{channel}"] += 1
            if args.execute:
                conn.execute(
                    "UPDATE stage_status SET source_channel=?, updated_at=? "
                    "WHERE content_id=? AND stage=? AND source_channel IS NULL",
                    (channel, now, cid, row["stage"]),
                )
                stats["null_rows_updated"] += 1

        if args.execute:
            conn.commit()
    finally:
        conn.close()

    print(f"[{mode}] stage_status channel reconcile — db: {db_path}")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    if unresolved:
        print("  unresolved sample (no ContentRecord / F0 channel found):")
        for item in unresolved:
            print(f"    {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
