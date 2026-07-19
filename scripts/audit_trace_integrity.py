"""Three-way trace-integrity audit for F5 actions (Phase 0 C8 / AUD-3).

Walks every F5 TradeAction and verifies its canonical trace resolves three ways —
the same path conventions the /audit assembler uses:

  * ``intent_id``          -> data/F3_intents/{intent_id}.json
  * ``policy_id``          -> data/F4_policy_mapped/{policy_id}.json
  * ``evidence_span_ids``  -> data/F2_evidence/{span_id}.json  (ALL must resolve)

Emits a completeness report (human-readable + JSON) listing every action_id whose
trace is broken and the break type. READ-ONLY: never writes into the F-stage data
dirs (only an optional JSON report file).

    .venv/bin/python scripts/audit_trace_integrity.py                 # summary
    .venv/bin/python scripts/audit_trace_integrity.py --json out.json # + JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.paths import DATA_ROOT  # noqa: E402

# Break-type slugs (stable — the CI test and the report both key on these).
BREAK_MISSING_INTENT_ID = "missing_intent_id"
BREAK_F3_MISSING = "f3_intent_missing"
BREAK_MISSING_POLICY_ID = "missing_policy_id"
BREAK_F4_MISSING = "f4_policy_missing"
BREAK_MISSING_EVIDENCE_IDS = "missing_evidence_ids"
BREAK_F2_EVIDENCE_MISSING = "f2_evidence_missing"


@dataclass
class BrokenAction:
    action_id: str
    source_file: str
    breaks: List[str]
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    total_actions: int = 0
    intent_resolved: int = 0          # actions whose intent_id -> F3 file exists
    policy_resolved: int = 0          # actions whose policy_id -> F4 file exists
    evidence_all_resolved: int = 0    # actions where ALL evidence spans -> F2 file
    evidence_spans_total: int = 0
    evidence_spans_resolved: int = 0
    break_counts: Counter = field(default_factory=Counter)
    broken: List[BrokenAction] = field(default_factory=list)

    def _rate(self, n: int) -> float:
        return (n / self.total_actions) if self.total_actions else 0.0

    @property
    def intent_rate(self) -> float:
        return self._rate(self.intent_resolved)

    @property
    def policy_rate(self) -> float:
        return self._rate(self.policy_resolved)

    @property
    def evidence_rate(self) -> float:
        return self._rate(self.evidence_all_resolved)

    @property
    def evidence_span_rate(self) -> float:
        return (self.evidence_spans_resolved / self.evidence_spans_total) if self.evidence_spans_total else 0.0

    @property
    def fully_intact(self) -> int:
        return self.total_actions - len(self.broken)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "fully_intact": self.fully_intact,
            "rates": {
                "intent_resolve": round(self.intent_rate, 4),
                "policy_resolve": round(self.policy_rate, 4),
                "evidence_all_resolve": round(self.evidence_rate, 4),
                "evidence_span_resolve": round(self.evidence_span_rate, 4),
            },
            "counts": {
                "intent_resolved": self.intent_resolved,
                "policy_resolved": self.policy_resolved,
                "evidence_all_resolved": self.evidence_all_resolved,
                "evidence_spans_total": self.evidence_spans_total,
                "evidence_spans_resolved": self.evidence_spans_resolved,
            },
            "break_counts": dict(self.break_counts),
            "broken": [
                {"action_id": b.action_id, "source_file": b.source_file, "breaks": b.breaks, "detail": b.detail}
                for b in self.broken
            ],
        }


def _iter_actions(f5_dir: Path):
    """Yield (action_dict, source_file_name) for every F5 action."""
    for path in sorted(f5_dir.glob("*_actions.json")):
        if ".bak-" in path.name:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for action in doc.get("actions", []):
            yield action, path.name


def audit_trace_integrity(data_root: Path) -> AuditReport:
    """Read-only three-way resolvability audit over all F5 actions."""
    f5_dir = data_root / "F5_executed"
    f3_dir = data_root / "F3_intents"
    f4_dir = data_root / "F4_policy_mapped"
    f2_evidence_dir = data_root / "F2_evidence"

    report = AuditReport()
    if not f5_dir.is_dir():
        return report

    for action, source_file in _iter_actions(f5_dir):
        report.total_actions += 1
        action_id = action.get("trade_action_id") or "<no-id>"
        breaks: List[str] = []
        detail: Dict[str, Any] = {}

        # 1. intent_id -> F3
        intent_id = action.get("intent_id")
        if not intent_id:
            breaks.append(BREAK_MISSING_INTENT_ID)
        elif (f3_dir / f"{intent_id}.json").exists():
            report.intent_resolved += 1
        else:
            breaks.append(BREAK_F3_MISSING)
            detail["intent_id"] = intent_id

        # 2. policy_id -> F4
        policy_id = action.get("policy_id")
        if not policy_id:
            breaks.append(BREAK_MISSING_POLICY_ID)
        elif (f4_dir / f"{policy_id}.json").exists():
            report.policy_resolved += 1
        else:
            breaks.append(BREAK_F4_MISSING)
            detail["policy_id"] = policy_id

        # 3. evidence_span_ids -> F2 (ALL must resolve)
        span_ids = action.get("evidence_span_ids") or []
        if not span_ids:
            breaks.append(BREAK_MISSING_EVIDENCE_IDS)
        else:
            resolved = sum((f2_evidence_dir / f"{s}.json").exists() for s in span_ids)
            report.evidence_spans_total += len(span_ids)
            report.evidence_spans_resolved += resolved
            if resolved == len(span_ids):
                report.evidence_all_resolved += 1
            else:
                breaks.append(BREAK_F2_EVIDENCE_MISSING)
                detail["evidence_missing"] = len(span_ids) - resolved
                detail["evidence_total"] = len(span_ids)

        if breaks:
            for b in breaks:
                report.break_counts[b] += 1
            report.broken.append(BrokenAction(action_id=action_id, source_file=source_file, breaks=breaks, detail=detail))

    return report


def _print_summary(report: AuditReport, *, list_limit: int) -> None:
    print("=== F5 three-way trace-integrity audit (C8) ===")
    print(f"total F5 actions: {report.total_actions}   fully intact: {report.fully_intact}")
    print(f"  intent_id -> F3          : {report.intent_resolved}/{report.total_actions}  ({report.intent_rate:.1%})")
    print(f"  policy_id -> F4          : {report.policy_resolved}/{report.total_actions}  ({report.policy_rate:.1%})")
    print(
        f"  evidence -> F2 (all spans): {report.evidence_all_resolved}/{report.total_actions}  "
        f"({report.evidence_rate:.1%})   span-level {report.evidence_spans_resolved}/{report.evidence_spans_total} ({report.evidence_span_rate:.1%})"
    )
    if report.break_counts:
        print(f"break counts: {dict(report.break_counts)}")
    if report.broken:
        print(f"\nbroken actions ({len(report.broken)}; showing up to {list_limit}):")
        for b in report.broken[:list_limit]:
            print(f"  {b.action_id}  [{','.join(b.breaks)}]  ({b.source_file})  {b.detail or ''}")
        if len(report.broken) > list_limit:
            print(f"  ... and {len(report.broken) - list_limit} more (see --json for the full list)")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_trace_integrity",
        description="Read-only three-way trace-integrity audit over all F5 actions (C8).",
    )
    parser.add_argument("--data-root", type=Path, default=None, help=f"data root (default: {DATA_ROOT})")
    parser.add_argument("--json", type=Path, default=None, help="also write the full JSON report to this path")
    parser.add_argument("--list-limit", type=int, default=30, help="max broken actions to print (full set in --json)")
    args = parser.parse_args(argv)

    data_root = args.data_root or DATA_ROOT
    report = audit_trace_integrity(data_root)
    _print_summary(report, list_limit=args.list_limit)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON report -> {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
