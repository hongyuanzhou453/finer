#!/usr/bin/env python3
"""Backfill missing F2 evidence sidecars for existing bri_* F5 actions (A4).

Root cause: the additive drive (tag 20260721-033106-c9-additive-drive) called
``run_canonical_from_artifacts`` before it grew the ``persist_dir`` parameter,
so the actions it emitted reference evidence_span_ids that were never written
to ``data/F2_evidence/{span_id}.json``. The span payloads still exist inside
the corresponding ``data/F2_anchored/{stem}.json`` documents, so this is a
pure-additive recovery — no F2 re-run, no F5 mutation.

Behaviour:
  * scan  data/F5_executed/bri_*_actions.json
  * collect evidence_span_ids missing a sidecar under data/F2_evidence/
  * resolve each from data/F2_anchored/{stem}.json (stem = action filename
    minus the ``bri_`` prefix and ``_actions.json`` suffix)
  * dry-run (default): report counts only
  * --execute: write ONLY missing sidecars via the canonical EvidenceSpan
    model (same serialization as canonical_runner._persist_evidence_sidecars);
    never overwrites an existing sidecar, never touches F5/F2 documents.

Usage:
    python scripts/backfill_bri_evidence_sidecars.py            # dry-run
    python scripts/backfill_bri_evidence_sidecars.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.schemas.evidence import EvidenceSpan  # noqa: E402

DATA = REPO_ROOT / "data"
F5_DIR = DATA / "F5_executed"
F2_ANCHORED_DIR = DATA / "F2_anchored"
EVIDENCE_DIR = DATA / "F2_evidence"


def _iter_actions(doc: object) -> Iterable[dict]:
    if isinstance(doc, list):
        return [a for a in doc if isinstance(a, dict)]
    if isinstance(doc, dict):
        for key in ("actions", "trade_actions"):
            val = doc.get(key)
            if isinstance(val, list):
                return [a for a in val if isinstance(a, dict)]
    return []


def _f2_spans_by_id(f2_path: Path) -> Dict[str, dict]:
    doc = json.loads(f2_path.read_text(encoding="utf-8"))
    spans: Dict[str, dict] = {}
    for block in doc.get("blocks") or []:
        for span in block.get("evidence_spans") or []:
            span_id = span.get("evidence_span_id")
            if span_id:
                spans[span_id] = span
    return spans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write missing sidecars (default is a read-only dry-run report).",
    )
    args = parser.parse_args()

    action_files = sorted(F5_DIR.glob("bri_*_actions.json"))
    stats = {
        "action_files_scanned": 0,
        "actions_scanned": 0,
        "actions_with_missing_spans": 0,
        "span_ids_missing": 0,
        "span_ids_recoverable": 0,
        "span_ids_unrecoverable": 0,
        "sidecars_written": 0,
        "f2_docs_absent": 0,
    }
    unrecoverable: List[str] = []

    for fp in action_files:
        stats["action_files_scanned"] += 1
        doc = json.loads(fp.read_text(encoding="utf-8"))
        stem = fp.name[len("bri_") : -len("_actions.json")]
        f2_path = F2_ANCHORED_DIR / f"{stem}.json"
        span_lookup: Dict[str, dict] | None = None

        for action in _iter_actions(doc):
            stats["actions_scanned"] += 1
            span_ids = action.get("evidence_span_ids") or []
            missing = [s for s in span_ids if not (EVIDENCE_DIR / f"{s}.json").exists()]
            if not missing:
                continue
            stats["actions_with_missing_spans"] += 1
            stats["span_ids_missing"] += len(missing)

            if span_lookup is None:
                if not f2_path.exists():
                    stats["f2_docs_absent"] += 1
                    span_lookup = {}
                else:
                    span_lookup = _f2_spans_by_id(f2_path)

            for span_id in missing:
                payload = span_lookup.get(span_id)
                if payload is None:
                    stats["span_ids_unrecoverable"] += 1
                    unrecoverable.append(f"{fp.name}:{span_id}")
                    continue
                stats["span_ids_recoverable"] += 1
                if args.execute:
                    span = EvidenceSpan.model_validate(payload)
                    target = EVIDENCE_DIR / f"{span.evidence_span_id}.json"
                    if target.exists():  # additive-only guarantee
                        continue
                    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                    target.write_text(span.model_dump_json(indent=2), encoding="utf-8")
                    stats["sidecars_written"] += 1

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"[{mode}] bri evidence sidecar backfill")
    for key, val in stats.items():
        print(f"  {key}: {val}")
    if unrecoverable:
        print("  unrecoverable sample (first 10):")
        for item in unrecoverable[:10]:
            print(f"    {item}")

    if stats["span_ids_unrecoverable"]:
        print(
            "NOTE: unrecoverable spans need the F2 doc re-anchored; do NOT lower "
            "the audit EVIDENCE_MIN threshold to compensate."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
