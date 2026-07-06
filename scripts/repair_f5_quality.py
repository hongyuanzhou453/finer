#!/usr/bin/env python
"""In-place quality repair for the existing F5 actions (照妖镜清单存量修复).

Repairs exactly three per-action fields, preserving everything else (uuids,
backtest_result, timing, RLHF...):
  1. source.evidence_text — rebuilt from the F2 evidence spans with the fixed
     sentence-window builder (kills the degenerate "亚马逊 | 亚马逊 | …" strings)
  2. rationale — its 依据 tail replaced with the first context snippet
  3. conviction — backfilled from data/F3_intents/ via the intent_id join
     (F3's rule-based conviction: real 3-band belief signal never carried before)

SAFE by construction: dry-run by default (prints per-action before/after +
degenerate metric); --apply backs up data/F5_executed/ first, then writes
atomically per file and rebuilds the cache index.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/zhouhongyuan/Desktop/finer")
sys.path.insert(0, str(ROOT / "src"))

from finer.pipeline.canonical_runner import (  # noqa: E402
    _block_texts,
    _build_evidence_text,
    _index_f2_evidence,
)

F5_DIR = ROOT / "data" / "F5_executed"
F3_DIR = ROOT / "data" / "F3_intents"


class _EnvShim:
    """Duck-typed envelope: _index_f2_evidence/_block_texts only need these."""

    def __init__(self, d: dict):
        self.blocks = d.get("blocks") or []
        self.entity_anchors = d.get("entity_anchors") or []


def is_degenerate(text: str) -> bool:
    """Mention-join detector: short repeated tokens split by '|'."""
    parts = [p.strip() for p in (text or "").split("|") if p.strip()]
    if len(parts) < 2:
        return False
    return len(set(parts)) < len(parts) or all(len(p) <= 8 for p in parts)


def load_conviction_map() -> dict[str, float]:
    out: dict[str, float] = {}
    for fp in F3_DIR.glob("*.json"):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        iid, conv = d.get("intent_id"), d.get("conviction")
        if iid and conv is not None:
            out[iid] = conv
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conviction_by_intent = load_conviction_map()
    print(f"F3 conviction map: {len(conviction_by_intent)} intents")

    stats = {
        "actions": 0,
        "degenerate_before": 0,
        "degenerate_after": 0,
        "evidence_repaired": 0,
        "conviction_filled": 0,
        "no_f2": 0,
    }
    changed_files: dict[Path, dict] = {}
    samples: list[tuple[str, str, str]] = []

    for fp in sorted(F5_DIR.glob("*_actions.json")):
        doc = json.loads(fp.read_text())
        src = Path(doc.get("source_file", ""))
        span_map, block_texts = {}, {}
        if src.exists():
            env = _EnvShim(json.loads(src.read_text()))
            span_map, _sym, _blk = _index_f2_evidence(env)
            block_texts = _block_texts(env)
        file_changed = False

        for a in doc.get("actions") or []:
            stats["actions"] += 1
            source = a.get("source") or {}
            old_ev = source.get("evidence_text") or ""
            if is_degenerate(old_ev):
                stats["degenerate_before"] += 1

            # 1+2: evidence + rationale repair (needs F2 spans)
            ids = a.get("evidence_span_ids") or []
            if span_map and ids:
                new_ev = _build_evidence_text(ids, span_map, block_texts=block_texts)
                if new_ev and new_ev != old_ev:
                    source["evidence_text"] = new_ev[:500]
                    a["source"] = source
                    rationale = a.get("rationale") or ""
                    prefix = rationale.split("｜依据：")[0]
                    first = new_ev.split(" | ")[0][:160]
                    a["rationale"] = f"{prefix}｜依据：{first}" if first else prefix
                    stats["evidence_repaired"] += 1
                    file_changed = True
                    if len(samples) < 5 and is_degenerate(old_ev):
                        samples.append((a.get("trade_action_id", "?")[:8], old_ev[:60], new_ev[:90]))
            elif not span_map:
                stats["no_f2"] += 1

            # 3: conviction backfill
            if a.get("conviction") is None:
                conv = conviction_by_intent.get(a.get("intent_id") or "")
                if conv is not None:
                    a["conviction"] = conv
                    stats["conviction_filled"] += 1
                    file_changed = True

            if is_degenerate((a.get("source") or {}).get("evidence_text") or ""):
                stats["degenerate_after"] += 1

        if file_changed:
            changed_files[fp] = doc

    print(f"\nstats: {json.dumps(stats, ensure_ascii=False)}")
    print(f"files to write: {len(changed_files)}")
    print("\nsample repairs (id | before | after):")
    for tid, before, after in samples:
        print(f"  {tid} | {before!r}\n           -> {after!r}")

    if not args.apply:
        print("\n[DRY-RUN] nothing written. Re-run with --apply.")
        return 0

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT / "data" / f"F5_executed.bak-{ts}"
    shutil.copytree(F5_DIR, backup)
    print(f"\n[APPLY] backup -> {backup}")

    import os

    for fp, doc in changed_files.items():
        tmp = fp.with_suffix(fp.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
        os.replace(tmp, fp)
    print(f"[APPLY] wrote {len(changed_files)} files")

    from finer.services.repository import TradeActionRepository

    repo = TradeActionRepository()
    print(f"[APPLY] reindex: {repo.rebuild_index()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
