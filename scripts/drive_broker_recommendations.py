#!/usr/bin/env python
"""Drive broker recommendation intents (bri_*) through F4 → F5 canonical pipeline.

Thin CLI shell (C2) over the canonical executor
``finer.pipeline.broker_runner.run_broker_declarative_f5`` — all business
logic (bri intent loading, anchor bridging, F4 mapping, canonical F5, sidecar
persistence, SQLite index, stage_status upsert) lives in src/. The pipeline
driver routes broker records through the same executor automatically; this
shell remains the manual full-corpus entry point.

Zero LLM calls: strategy is "programmatic" throughout.

Output: data/F5_executed/bri_{content_id}_actions.json  (bri_ prefix keeps
these files out of regen_canonical_f5.py's re-extraction sweep) + SQLite index.

Idempotent: intents whose intent_id already appears in an existing
bri_*_actions.json are skipped.

Usage:
    python scripts/drive_broker_recommendations.py            # dry-run (default)
    python scripts/drive_broker_recommendations.py --execute  # write to disk
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.pipeline.broker_runner import (  # noqa: E402
    BrokerDriveReport,
    run_broker_declarative_f5,
)


def _print_report(report: BrokerDriveReport, execute: bool) -> None:
    print(f"bri intents: {report.intents_seen}")
    print(f"broker envelopes: {report.envelopes_seen}")
    print(f"grounding bridge matched: {report.bridged}")
    if report.skips:
        print(f"skips: {report.skips}")
    for line in report.skip_detail:
        print(f"  skip: {line}")

    if not execute:
        print("\n[dry-run] plan:")
        for eid, count in sorted(report.planned.items()):
            print(f"  {eid}: {count} intent(s)")
        print("\nUse --execute to run F4/F5 and write outputs.")
        return

    print("\n== execute report ==")
    print(f"F4 action_hint distribution: {report.action_hint_dist}")
    print(f"F5 trade_actions produced: {report.actions_written}")
    print(f"F5 canonical_trace_status distribution: {report.trace_status_dist}")
    print(f"F5 rejected: {sum(report.rejected_reasons.values())}")
    for reason, n in sorted(
        report.rejected_reasons.items(), key=lambda kv: kv[1], reverse=True
    ):
        print(f"  rejected[{n}]: {reason}")
    print(f"files written: {len(report.written_files)}")
    for p in report.written_files:
        print(f"  {p}")
    print(f"F4 PolicyMappingResults persisted: {report.f4_written}")
    print(f"indexed actions: {report.indexed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Run F4/F5 and write outputs (default: dry-run plan only)",
    )
    parser.add_argument(
        "--data-root", type=Path, default=None,
        help="Data root to read/write F2/F3/F4/F5 (default: <repo>/data). Point "
             "at the canonical data root when running this script from a git "
             "worktree, whose own data/ is gitignored and absent.",
    )
    args = parser.parse_args()

    data_root = (args.data_root or (REPO_ROOT / "data")).resolve()
    print(f"data root: {data_root}")

    report = asyncio.run(
        run_broker_declarative_f5(data_root, execute=args.execute)
    )
    _print_report(report, execute=args.execute)


if __name__ == "__main__":
    main()
