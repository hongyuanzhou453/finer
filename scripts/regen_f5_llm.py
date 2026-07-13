#!/usr/bin/env python
"""Phase-2 full re-extraction: rerun F3(LLM)→F4→F5 over the 12 real F2 envelopes.

Chain position: this is step 1 of the authorized regen sequence
  regen (this) → creator_id backfill → F8 backtest backfill → index/snapshot refresh.

Safety:
  - Backs up F5_executed + F3_intents + F4_policy_mapped + F2_evidence first.
  - Old F3/F4/F2-evidence sidecars are cleared (they reference the old uuids);
    stale F5 wrappers whose envelope yields nothing are removed (backup holds them).
  - FINER_F3_EXTRACTOR=llm with the runner's built-in rule-based fallback, so a
    dead LLM chain degrades per-envelope instead of aborting the run. Since
    2026-07-05 llm mode defaults to 3-run majority-vote consensus
    (ConsensusIntentExtractor); FINER_F3_CONSENSUS_RUNS overrides.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/zhouhongyuan/Desktop/finer")
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)

import os  # noqa: E402

os.environ["FINER_F3_EXTRACTOR"] = "llm"
os.environ.setdefault("FINER_LLM_TIMEOUT", "180")

from finer.paths import DATA_ROOT  # noqa: E402
from finer.pipeline.canonical_runner import (  # noqa: E402
    _coerce_envelope_anchors,
    run_canonical_from_envelope,
)
from finer.schemas.content_envelope import ContentEnvelope  # noqa: E402
from finer.services.repository import TradeActionRepository  # noqa: E402

F2_DIR = DATA_ROOT / "F2_anchored"
F5_DIR = DATA_ROOT / "F5_executed"
SIDECAR_DIRS = [
    DATA_ROOT / "F3_intents",
    DATA_ROOT / "F4_policy_mapped",
    DATA_ROOT / "F2_evidence",
]


async def main() -> int:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = DATA_ROOT / f"regen-backup-{ts}"
    backup_root.mkdir(parents=True)
    for d in [F5_DIR, *SIDECAR_DIRS]:
        if d.exists():
            shutil.copytree(d, backup_root / d.name)
    print(f"[backup] -> {backup_root}")

    # old sidecars reference old uuids — clear so the tiers hold only the new run
    for d in SIDECAR_DIRS:
        if d.exists():
            for fp in d.glob("*.json"):
                fp.unlink()
    print("[clear] old F3/F4/F2-evidence sidecars removed (backed up)")

    f2_files = sorted(F2_DIR.glob("*.json"))
    print(f"[regen] {len(f2_files)} F2 envelopes, extractor=llm (rule fallback)\n")

    written: set[str] = set()
    total_actions = 0
    for f2_path in f2_files:
        stem = f2_path.stem
        try:
            env = ContentEnvelope.from_dict(json.loads(f2_path.read_text()))
            _coerce_envelope_anchors(env)
            context = {"kol_id": env.creator_id} if env.creator_id else {}
            actions = await run_canonical_from_envelope(
                env, context, persist_dir=DATA_ROOT
            )
        except Exception as e:
            print(f"  {stem}: FAILED ({e})")
            continue

        if not actions:
            print(f"  {stem}: 0 actions")
            continue

        out = F5_DIR / f"{stem}_actions.json"
        out.write_text(
            json.dumps(
                {
                    "source_file": str(f2_path),
                    "extracted_at": datetime.now().isoformat(),
                    "model": "canonical-f2-envelope+f3_llm_consensus",
                    "actions": [a.model_dump(mode="json") for a in actions],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        written.add(out.name)
        total_actions += len(actions)
        print(f"  {stem}: {len(actions)} actions")

    # remove stale wrappers from envelopes that now yield nothing
    stale = [p for p in F5_DIR.glob("*_actions.json") if p.name not in written]
    for p in stale:
        p.unlink()
        print(f"[stale removed] {p.name}")

    repo = TradeActionRepository()
    print(f"\n[reindex] {repo.rebuild_index()}")
    print(f"[done] envelopes={len(f2_files)} wrappers={len(written)} actions={total_actions}")
    print(f"[next] scripts/backfill_creator_id.py --apply → scripts/backfill_f8_backtest.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
