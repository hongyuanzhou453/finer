"""Regenerate the canonical F5 dataset from data/F2_anchored.

Re-runs the production canonical path (``_run_extraction_pipeline_async`` →
``canonical_runner.run_canonical_from_envelope``) over every F2-anchored
envelope, refreshing the derived sidecars:

    data/F5_executed/{stem}_actions.json   (wrapper: model + actions[])
    data/F3_intents/{intent_id}.json
    data/F4_policy_mapped/{policy_id}.json
    data/F2_evidence/{evidence_span_id}.json

Because every id is a fresh uuid4, a re-run must START FROM A CLEAN SLATE or the
previous run's sidecars linger as orphans. This script therefore:

  1. backs up the four derived dirs to BACKUP_ROOT,
  2. clears them,
  3. regenerates via the canonical pipeline,
  4. verifies every emitted action is F2-grounded (evidence_span_ids resolve to
     freshly-written data/F2_evidence sidecars) and reports canonical/partial
     counts.

The F2-grounding hard gate (batch B) means some intents that previously produced
actions may now be rejected (``evidence_not_grounded_in_f2``); a lower action
count than a pre-gate run is expected, not a regression.

Usage:
    cd /Users/zhouhongyuan/Desktop/finer
    python scripts/regen_canonical_f5.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("regen_canonical_f5")

from finer.paths import DATA_ROOT  # noqa: E402

F2_ANCHORED = DATA_ROOT / "F2_anchored"
F5_EXECUTED = DATA_ROOT / "F5_executed"
DERIVED_DIRS = [
    F5_EXECUTED,
    DATA_ROOT / "F3_intents",
    DATA_ROOT / "F4_policy_mapped",
    DATA_ROOT / "F2_evidence",
]
BACKUP_ROOT = Path("/tmp/finer_f5_backup_pre_f2gate")


def _count(path: Path) -> int:
    return len(list(path.glob("*.json"))) if path.is_dir() else 0


def backup_and_clear() -> None:
    if BACKUP_ROOT.exists():
        shutil.rmtree(BACKUP_ROOT)
    BACKUP_ROOT.mkdir(parents=True)
    for d in DERIVED_DIRS:
        if d.is_dir():
            shutil.copytree(d, BACKUP_ROOT / d.name)
            logger.info("backed up %s (%d files) → %s", d.name, _count(d), BACKUP_ROOT / d.name)
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)


def verify() -> int:
    """Verify every emitted action is F2-grounded. Returns process exit code."""
    evidence_dir = DATA_ROOT / "F2_evidence"
    evidence_ids = {p.stem for p in evidence_dir.glob("*.json")}

    total_actions = canonical = partial = other = ungrounded = 0
    for wrapper in sorted(F5_EXECUTED.glob("*_actions.json")):
        data = json.loads(wrapper.read_text(encoding="utf-8"))
        for action in data.get("actions", []):
            total_actions += 1
            status = action.get("canonical_trace_status")
            canonical += status == "canonical"
            partial += status == "partial"
            other += status not in ("canonical", "partial")
            span_ids = action.get("evidence_span_ids") or []
            missing = [s for s in span_ids if s not in evidence_ids]
            if missing:
                ungrounded += 1
                logger.warning(
                    "action %s references %d evidence span(s) not on disk: %s",
                    action.get("trade_action_id"), len(missing), missing[:3],
                )

    logger.info("── regeneration result ──")
    logger.info("F5 wrappers:     %d", _count(F5_EXECUTED))
    logger.info("F3 intents:      %d", _count(DATA_ROOT / "F3_intents"))
    logger.info("F4 policy:       %d", _count(DATA_ROOT / "F4_policy_mapped"))
    logger.info("F2 evidence:     %d", _count(evidence_dir))
    logger.info("actions total:   %d  (canonical=%d partial=%d other=%d)",
                total_actions, canonical, partial, other)
    logger.info("ungrounded refs: %d", ungrounded)

    if ungrounded:
        logger.error("FAIL: %d action(s) reference evidence spans absent from F2_evidence", ungrounded)
        return 1
    if other:
        logger.error("FAIL: %d action(s) are neither canonical nor partial", other)
        return 1
    logger.info("OK: every action's evidence_span_ids resolve to F2 evidence on disk")
    return 0


def main() -> int:
    if not F2_ANCHORED.is_dir() or _count(F2_ANCHORED) == 0:
        logger.error("No F2-anchored envelopes at %s — nothing to regenerate.", F2_ANCHORED)
        return 1
    logger.info("F2_anchored inputs: %d", _count(F2_ANCHORED))

    backup_and_clear()

    from finer.api.routes.extraction import _run_extraction_pipeline_async

    asyncio.run(_run_extraction_pipeline_async(F2_ANCHORED, F5_EXECUTED, limit=10_000))

    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
