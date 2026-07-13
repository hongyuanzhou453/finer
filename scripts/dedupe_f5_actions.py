#!/usr/bin/env python
"""Remove duplicate TradeActions from the existing F5 files (F3 dedup backlog).

Before the per-envelope intent dedup landed, the F3 section loop emitted one
intent per section, so the same viewpoint produced several identical actions
(3× 000001.SH, 2× OPTICAL_MODULE, 2× 0700.HK in the live set). This removes
the extras; the pipeline fix prevents new ones.

Duplicate key (strict, within one file): ticker + direction + first action_type
+ executable date + evidence_text. Keeps the FIRST occurrence (its uuid stays
referenced by F8 provenance artifacts; duplicates carry identical backtest
results anyway).

Dry-run by default; --apply backs up data/F5_executed/ then rewrites atomically
and rebuilds the cache index.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/zhouhongyuan/Desktop/finer")
sys.path.insert(0, str(ROOT / "src"))

F5_DIR = ROOT / "data" / "F5_executed"


def dup_key(a: dict) -> tuple:
    timing = a.get("execution_timing") or {}
    return (
        (a.get("target") or {}).get("ticker"),
        a.get("direction"),
        (a.get("action_chain") or [{}])[0].get("action_type"),
        (timing.get("action_executable_at") or "")[:10],
        ((a.get("source") or {}).get("evidence_text") or ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = kept = removed = 0
    changed: dict[Path, dict] = {}

    for fp in sorted(F5_DIR.glob("*_actions.json")):
        doc = json.loads(fp.read_text())
        actions = doc.get("actions") or []
        seen: set[tuple] = set()
        out = []
        for a in actions:
            total += 1
            k = dup_key(a)
            if k in seen:
                removed += 1
                print(
                    f"  remove dup: {fp.name} {k[0]} {k[1]} @{k[3]} "
                    f"id={a.get('trade_action_id', '?')[:8]}"
                )
                continue
            seen.add(k)
            out.append(a)
            kept += 1
        if len(out) != len(actions):
            doc["actions"] = out
            changed[fp] = doc

    print(f"\ntotal={total} kept={kept} removed={removed} files_changed={len(changed)}")

    if not args.apply:
        print("[DRY-RUN] nothing written. Re-run with --apply.")
        return 0

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT / "data" / f"F5_executed.bak-{ts}"
    shutil.copytree(F5_DIR, backup)
    print(f"[APPLY] backup -> {backup}")

    for fp, doc in changed.items():
        tmp = fp.with_suffix(fp.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
        os.replace(tmp, fp)
    print(f"[APPLY] wrote {len(changed)} files")

    from finer.services.repository import TradeActionRepository

    repo = TradeActionRepository()
    print(f"[APPLY] reindex: {repo.rebuild_index()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
