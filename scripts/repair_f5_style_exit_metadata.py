#!/usr/bin/env python
"""In-place F5 repair: backfill style/exit metadata + fine-grained ActionType.

Root cause (2026-07-10): pipeline/canonical_runner.py built TradeActions with a
hand-rolled metadata dict (action_hint_original + tier only) and its own stale
ACTION_HINT_TO_ACTION_TYPE table, bypassing CanonicalActionBuilder. The 07-05
consensus regen therefore produced F5 actions that
  - dropped the F3 trading-style signals (margin_flag / leverage_flag /
    entry_timing_style) even though the F3 sidecars carry them,
  - dropped the F4 numeric exit-rule hints even though the F4 sidecars'
    risk_constraints carry them,
  - collapsed add_position/reduce_position back to LONG/CLOSE_LONG.

The runner is fixed (shared build_action_metadata + table pinned by
tests/test_canonical_runner_mapping.py). This script repairs the EXISTING 42
actions in place from F3/F4 sidecar truth instead of re-running the LLM chain:
trade_action_id, direction, timing, and backtest_result stay untouched, so F7
snapshots, F8 results and audit traces remain valid. Exit-hint values equal the
historical F8 constants, so re-running the backtest would be a no-op.

Safety: full backup of data/F5_executed to data/repair-backup-{ts}/ first.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/zhouhongyuan/Desktop/finer")
sys.path.insert(0, str(ROOT / "src"))

from finer.paths import DATA_ROOT  # noqa: E402
from finer.schemas.trade_action import TradeAction  # noqa: E402

F5_DIR = DATA_ROOT / "F5_executed"
F3_DIR = DATA_ROOT / "F3_intents"
F4_DIR = DATA_ROOT / "F4_policy_mapped"

POSITION_TAKING_HINTS = {
    "open_position", "add_position", "reduce_position",
    "close_position", "hold_position",
}
HINT_TO_FINE_ACTION_TYPE = {
    "add_position": "add",
    "reduce_position": "reduce",
}
# Only these coarse values may be upgraded — anything else means the action
# was built by a different path and must be left alone.
UPGRADEABLE_COARSE = {"add_position": "long", "reduce_position": "close_long"}


def load_index(directory: Path, key: str) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"  ! skipping unreadable {path.name}: {e}")
            continue
        if isinstance(obj, dict) and obj.get(key):
            index[obj[key]] = obj
    return index


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_ROOT / f"repair-backup-{ts}"
    backup.mkdir(parents=True)
    shutil.copytree(F5_DIR, backup / "F5_executed")
    print(f"backup -> {backup}")

    intents = load_index(F3_DIR, "intent_id")
    mapped = load_index(F4_DIR, "policy_id")
    print(f"loaded {len(intents)} F3 intents, {len(mapped)} F4 mappings")

    stats = {
        "actions": 0, "style_filled": 0, "exit_filled": 0,
        "action_type_upgraded": 0, "missing_intent": 0, "missing_policy": 0,
    }

    for path in sorted(F5_DIR.glob("*_actions.json")):
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        actions = wrapper["actions"] if isinstance(wrapper, dict) else wrapper
        changed = False

        for action in actions:
            stats["actions"] += 1
            meta = action.setdefault("metadata", {})
            hint = meta.get("action_hint_original")

            # -- F3 style signals --------------------------------------------
            intent = intents.get(action.get("intent_id"))
            if intent is None:
                stats["missing_intent"] += 1
            else:
                touched = False
                if intent.get("margin_flag") is not None and "margin_flag" not in meta:
                    meta["margin_flag"] = intent["margin_flag"]
                    touched = True
                if intent.get("leverage_flag") is not None and "leverage_flag" not in meta:
                    meta["leverage_flag"] = intent["leverage_flag"]
                    touched = True
                ets = intent.get("entry_timing_style")
                if ets and ets != "unknown" and "entry_timing_style" not in meta:
                    meta["entry_timing_style"] = ets
                    touched = True
                if touched:
                    stats["style_filled"] += 1
                    changed = True

            # -- F4 hints (sizing/holding always; exit only for position hints)
            pmr = mapped.get(action.get("policy_id"))
            if pmr is None:
                stats["missing_policy"] += 1
            else:
                if "position_sizing_hint" not in meta and pmr.get("position_sizing_hint"):
                    meta["position_sizing_hint"] = pmr["position_sizing_hint"]
                    changed = True
                if "holding_period_hint" not in meta and pmr.get("holding_period_hint"):
                    meta["holding_period_hint"] = pmr["holding_period_hint"]
                    changed = True
                rc = pmr.get("risk_constraints") or {}
                if hint in POSITION_TAKING_HINTS:
                    filled = False
                    for src, dst in (
                        ("stop_loss_pct_hint", "stop_loss_pct"),
                        ("take_profit_pct_hint", "take_profit_pct"),
                        ("max_holding_days_hint", "max_holding_days"),
                    ):
                        if rc.get(src) is not None and dst not in meta:
                            meta[dst] = rc[src]
                            filled = True
                    if filled:
                        stats["exit_filled"] += 1
                        changed = True

            # -- fine-grained ActionType -------------------------------------
            fine = HINT_TO_FINE_ACTION_TYPE.get(hint)
            if fine and action.get("action_chain"):
                step = action["action_chain"][0]
                if step.get("action_type") == UPGRADEABLE_COARSE[hint]:
                    step["action_type"] = fine
                    stats["action_type_upgraded"] += 1
                    changed = True

        if changed:
            # Round-trip through the schema so an invalid patch can never land.
            for action in actions:
                TradeAction.from_dict(action)
            path.write_text(
                json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"  patched {path.name}")

    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
