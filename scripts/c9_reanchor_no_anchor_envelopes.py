#!/usr/bin/env python
"""C9 follow-up — additive re-anchor of no-anchor broker envelopes.

Re-anchors the broker envelopes that C9 step A (``c9_evidence_reanchor.py``) did
NOT touch: those referenced by a bri intent but with **no F5 action file**. Step A
only re-anchored existing-action envelopes, so these ~2,000 never received the
phase-1 ticker/stoplist fixes and their intents stayed ``no_anchor_match``.
Re-anchoring them lets ``drive_broker_recommendations.py --execute`` bridge the
newly-matchable ones.

Each processed envelope is re-bridged (build new F2 → does its bri intent's
target resolve to a NEW anchor?) so the run reports the additive yield directly.
Measured ~13% → ~238, all TW/JP; the international ``.PA``/``.L`` upside needs
envelope-side anchor DETECTION (the phase-1 fix only bridges the intent side),
which is a separate, bigger follow-up.

Pairs with the driver:
  1. this script --execute                       (refresh F2 anchors, no-action envelopes)
  2. drive_broker_recommendations.py --execute   (produce new actions + evidence
     sidecars via persist_dir)

``build_f2_deterministic_envelope`` is ~4s/envelope and CPU-bound, so this fans
out over processes (real parallelism; the GIL makes threads useless here). It
does no network I/O and is deterministic (verified: stable span ids), so a run
is reproducible and a re-run idempotent.

DELETION/MUTATION IS A RED LINE. Dry-run by default; ``--execute`` backs up
``data/F2_anchored`` **and** ``data/F5_executed`` first (named snapshot — the
second covers the driver step that follows). Only no-action envelopes are
rewritten, so no settled result is disturbed.

Usage:
    python scripts/c9_reanchor_no_anchor_envelopes.py --limit 300        # fast sample dry-run
    python scripts/c9_reanchor_no_anchor_envelopes.py --execute          # back up + rewrite all
    # ... from a git worktree (data/ is gitignored / absent there):
    python scripts/c9_reanchor_no_anchor_envelopes.py --data-root /path/to/repo/data --execute
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.entity_anchoring import build_f2_deterministic_envelope  # noqa: E402
from finer.enrichment.ticker_normalization import normalize_broker_ticker  # noqa: E402
from finer.schemas.content import ContentRecord  # noqa: E402


def _bridged_symbol(target_symbol: Optional[str], anchor_symbols: set) -> Optional[str]:
    """Same bridge as ``drive_broker_recommendations.bridge_target_symbol`` but
    pure (no intent mutation): does the intent target resolve to a NEW anchor?"""
    if not target_symbol:
        return None
    if target_symbol in anchor_symbols:
        return target_symbol
    normalized = normalize_broker_ticker(target_symbol)
    if normalized and normalized.symbol in anchor_symbols:
        return normalized.symbol
    return None


def _reanchor_worker(task: Tuple[str, Optional[str], str, str, str, bool]) -> Tuple[str, bool, bool, Optional[str]]:
    """Process-pool worker (module-level → picklable under spawn).

    Returns ``(cid, matched, wrote, error)``. On --execute the worker writes the
    re-anchored F2 itself so 130 KB envelopes are not shipped back to the parent.
    """
    cid, target_symbol, f1_dir, f0b_dir, f2a_dir, execute = task
    try:
        env_json = json.loads(
            (Path(f1_dir) / cid / "content_envelope.json").read_text(encoding="utf-8")
        )
        f0p = Path(f0b_dir) / f"{cid}.json"
        rec = None
        if f0p.exists():
            try:
                rec = ContentRecord.model_validate_json(f0p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — best-effort F0 enrichment
                rec = None
        f2 = build_f2_deterministic_envelope(
            env_json, f0_record=(rec.model_dump(mode="json") if rec else None)
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return (cid, False, False, f"{type(exc).__name__}: {exc}")

    anchor_symbols = {
        a.get("resolved_symbol")
        for a in (f2.get("entity_anchors") or [])
        if a.get("resolved_symbol")
    }
    matched = _bridged_symbol(target_symbol, anchor_symbols) is not None

    wrote = False
    if execute:
        (Path(f2a_dir) / f"{cid}.json").write_text(
            json.dumps(f2, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        wrote = True
    return (cid, matched, wrote, None)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="C9 follow-up: additive re-anchor of no-anchor broker envelopes (dry-run default)."
    )
    ap.add_argument("--data-root", type=Path, default=None,
                    help="Data root (default: <repo>/data). Point at the canonical "
                         "data root when running from a git worktree.")
    ap.add_argument("--limit", type=int, default=None, help="max candidate envelopes (testing/sampling)")
    ap.add_argument("--workers", type=int, default=8, help="parallel re-anchor processes")
    ap.add_argument("--execute", action="store_true",
                    help="apply (backs up F2_anchored + F5_executed first)")
    args = ap.parse_args(argv)

    data = (args.data_root.resolve() if args.data_root else REPO_ROOT / "data")
    F1, F2A, F3, F5, F0B = (
        data / "F1_standardized", data / "F2_anchored", data / "F3_intents",
        data / "F5_executed", data / "F0_intake" / "broker",
    )
    print(f"[{'execute' if args.execute else 'dry-run'}] C9 additive re-anchor  data_root={data}")

    # envelope_id -> cid (F2 file stem = broker_<hash>)
    eid2cid: Dict[str, str] = {}
    for fp in glob.glob(str(F2A / "broker_*.json")):
        try:
            eid = json.loads(Path(fp).read_text(encoding="utf-8")).get("envelope_id")
        except (OSError, json.JSONDecodeError):
            continue
        if eid:
            eid2cid[eid] = Path(fp).stem

    # bri intents -> target_symbol keyed by envelope_id
    intent_by_eid: Dict[str, dict] = {}
    for fp in glob.glob(str(F3 / "bri_*.json")):
        try:
            d = json.loads(Path(fp).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        eid = d.get("envelope_id")
        if eid:
            intent_by_eid[eid] = d

    # cids that already have a bri action file (step A re-anchored these already)
    action_cids: set = set()
    for fp in glob.glob(str(F5 / "bri_*_actions.json")):
        stem = Path(fp).name[len("bri_"):-len("_actions.json")]
        try:
            if json.loads(Path(fp).read_text(encoding="utf-8")).get("actions"):
                action_cids.add(stem)
        except (OSError, json.JSONDecodeError):
            continue

    # Candidates: referenced by a bri intent, no action file, F1 envelope present.
    candidates: List[str] = []
    cid_target: Dict[str, Optional[str]] = {}
    missing_f1 = 0
    for eid, intent in intent_by_eid.items():
        cid = eid2cid.get(eid)
        if not cid or cid in action_cids:
            continue
        if not (F1 / cid / "content_envelope.json").exists():
            missing_f1 += 1
            continue
        candidates.append(cid)
        cid_target[cid] = intent.get("target_symbol")
    candidates.sort()
    if args.limit is not None:
        candidates = candidates[: args.limit]

    print(f"bri intents: {len(intent_by_eid)}  existing-action cids: {len(action_cids)}")
    print(f"CANDIDATE no-anchor envelopes: {len(candidates)}  (missing F1: {missing_f1})")
    if not candidates:
        print("nothing to do.")
        return 0

    backups: Dict[str, str] = {}
    if args.execute:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tag = f"{stamp}-c9-additive-{uuid.uuid4().hex[:8]}"
        for name, src in (("F2_anchored", F2A), ("F5_executed", F5)):
            if src.exists():
                dst = data / f"{name}.bak-{tag}"
                shutil.copytree(src, dst)
                backups[name] = str(dst)
                print(f"  backup {name} -> {dst}")

    tasks = [
        (cid, cid_target.get(cid), str(F1), str(F0B), str(F2A), args.execute)
        for cid in candidates
    ]
    reanchored = failed = would_match = 0
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(_reanchor_worker, t) for t in tasks]
        done = 0
        for fut in as_completed(futs):
            cid, matched, wrote, err = fut.result()
            done += 1
            if err is not None:
                failed += 1
                print(f"  skip {cid}: {err}")
            else:
                if matched:
                    would_match += 1
                if wrote:
                    reanchored += 1
            if done % 200 == 0:
                print(f"  ... {done}/{len(tasks)}  (newly-match so far: {would_match})")

    print("\n=== RESULT ===")
    print(f"candidates processed: {len(candidates)}  failed: {failed}")
    print(f"would newly bridge (→ new actions after driver): {would_match}  "
          f"still no match: {len(candidates) - failed - would_match}")
    if args.execute:
        print(f"F2 envelopes re-anchored (overwritten): {reanchored}")
        for n, p in backups.items():
            print(f"backup {n}: {p}")
        print("\nNext: python scripts/drive_broker_recommendations.py --execute "
              f"--data-root {data}")
    else:
        print("dry-run: nothing written. --execute backs up F2_anchored + F5_executed "
              "then rewrites the candidate F2 envelopes.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
