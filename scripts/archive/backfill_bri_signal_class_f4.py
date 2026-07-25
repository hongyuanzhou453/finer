"""Backfill signal_class + F4 artifacts onto existing bri_* actions (C7, plan A).

The forward code (schemas/action_composer/drive_broker_recommendations) makes NEW
broker drives emit signal_class + persisted F4 PolicyMappingResults. But the
driver skips already-actioned intents, so the ~1,773 bri actions already on disk
(the scorecard scale-up) still lack both. This script backfills them IN PLACE,
preserving every existing id (trade_action_id / policy_id / intent_id) so the
scorecard's settled backtest results stay valid.

For each action in data/F5_executed/bri_*_actions.json:
  1. signal_class ← derive_signal_class(its F3 intent) — set on the action.
  2. F4 artifact ← re-run PolicyMapper on the intent (deterministic, no LLM),
     force the result's policy_id to the action's stored policy_id, write to
     data/F4_policy_mapped/{policy_id}.json (the path audit_assembler reads).

Fidelity note: PolicyMapper is deterministic, so re-derivation reproduces the
mapping that originally produced the action AS LONG AS the policy code is
unchanged since it was composed. The bri corpus was produced on 2026-07-19, after
C0's global_base merge, so the code matches.

DELETION/MUTATION IS A RED LINE. Dry-run by default (writes nothing, prints a
plan). --execute backs up data/F5_executed first, then rewrites F5 files
(adding signal_class) and writes F4 artifacts. Idempotent: re-running writes
identical content.

    .venv/bin/python scripts/backfill_bri_signal_class_f4.py            # dry-run
    .venv/bin/python scripts/backfill_bri_signal_class_f4.py --execute  # apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.extraction.action_composer import derive_signal_class  # noqa: E402
from finer.policy.policy_mapper import PolicyMapper  # noqa: E402
from finer.schemas.investment_intent import NormalizedInvestmentIntent  # noqa: E402
from finer.schemas.policy import PolicyContext  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"
F3_DIR = DATA_ROOT / "F3_intents"
F4_DIR = DATA_ROOT / "F4_policy_mapped"
F5_DIR = DATA_ROOT / "F5_executed"


@dataclass
class BackfillResult:
    dry_run: bool = True
    files_scanned: int = 0
    actions_scanned: int = 0
    signal_class_set: int = 0          # actions that got (or would get) signal_class
    signal_class_already: int = 0      # actions that already had it
    f4_written: int = 0                # F4 artifacts written (or would write)
    intent_missing: int = 0            # action's F3 intent not on disk (skipped)
    failed: int = 0
    signal_class_dist: Counter = field(default_factory=Counter)
    errors: List[str] = field(default_factory=list)
    backup_path: Optional[str] = None


def _load_intent(intent_id: str) -> Optional[NormalizedInvestmentIntent]:
    path = F3_DIR / f"{intent_id}.json"
    if not path.exists():
        return None
    return NormalizedInvestmentIntent.model_validate_json(path.read_text(encoding="utf-8"))


def _reconstruct_f4(intent: NormalizedInvestmentIntent, policy_id: str) -> dict:
    """Deterministically re-map the intent and stamp the action's stored policy_id."""
    mapper = PolicyMapper(context=PolicyContext(kol_id=intent.creator_id))
    batch = mapper.map_batch([intent])
    pmr = batch.mappings[0]
    payload = pmr.model_dump(mode="json")
    payload["policy_id"] = policy_id  # preserve the id the action already references
    return payload


def backfill(*, execute: bool, limit: Optional[int] = None) -> BackfillResult:
    result = BackfillResult(dry_run=not execute)
    files = sorted(F5_DIR.glob("bri_*_actions.json"))

    if execute:
        # A deliberate pre-mutation snapshot. The uuid suffix makes it a *named*
        # backup (not a bare timestamp), so prune_backups protects it AND two
        # runs never collide on the same-second directory name.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = DATA_ROOT / f"F5_executed.bak-{stamp}-bri-backfill-{uuid.uuid4().hex[:8]}"
        shutil.copytree(F5_DIR, backup)
        result.backup_path = str(backup)
        F4_DIR.mkdir(parents=True, exist_ok=True)

    for f5_path in files:
        if limit is not None and result.actions_scanned >= limit:
            break
        result.files_scanned += 1
        try:
            doc = json.loads(f5_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.failed += 1
            result.errors.append(f"{f5_path.name}: read error: {exc}")
            continue

        actions = doc.get("actions", [])
        file_dirty = False
        for action in actions:
            if limit is not None and result.actions_scanned >= limit:
                break
            result.actions_scanned += 1
            intent_id = action.get("intent_id")
            policy_id = action.get("policy_id")
            intent = _load_intent(intent_id) if intent_id else None
            if intent is None:
                result.intent_missing += 1
                continue

            sc = derive_signal_class(intent)
            result.signal_class_dist[sc] += 1
            if action.get("signal_class") == sc:
                result.signal_class_already += 1
            else:
                result.signal_class_set += 1
                if execute:
                    action["signal_class"] = sc
                    file_dirty = True

            if policy_id:
                if execute:
                    try:
                        f4_payload = _reconstruct_f4(intent, policy_id)
                        (F4_DIR / f"{policy_id}.json").write_text(
                            json.dumps(f4_payload, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        result.f4_written += 1
                    except Exception as exc:  # noqa: BLE001 - report and continue
                        result.failed += 1
                        result.errors.append(f"{intent_id}: F4 reconstruct failed: {type(exc).__name__}: {exc}")
                else:
                    result.f4_written += 1  # would write

        if execute and file_dirty:
            f5_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_bri_signal_class_f4",
        description="Backfill signal_class + F4 artifacts onto existing bri actions (dry-run by default).",
    )
    parser.add_argument("--limit", type=int, default=None, help="max actions to process (testing)")
    parser.add_argument("--execute", action="store_true", help="apply changes (default: dry-run). Backs up F5_executed first.")
    args = parser.parse_args(argv)

    result = backfill(execute=args.execute, limit=args.limit)

    header = "[execute]" if args.execute else "[dry-run]"
    print(f"{header} bri signal_class + F4 backfill")
    if result.backup_path:
        print(f"backup -> {result.backup_path}")
    print(
        f"files={result.files_scanned} actions={result.actions_scanned} "
        f"signal_class_set={result.signal_class_set} already={result.signal_class_already} "
        f"f4_{'written' if args.execute else 'would_write'}={result.f4_written} "
        f"intent_missing={result.intent_missing} failed={result.failed}"
    )
    print(f"signal_class distribution: {dict(result.signal_class_dist)}")
    for err in result.errors[:20]:
        print(f"  ERROR {err}")
    if len(result.errors) > 20:
        print(f"  ... and {len(result.errors) - 20} more errors")
    if not args.execute:
        print("dry-run: nothing written. Review above, then re-run with --execute.")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
