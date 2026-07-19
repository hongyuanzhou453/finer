#!/usr/bin/env python3
"""Contract drift guard — pydantic Literal/Enum ↔ frontend contracts.ts enums.

The frontend `contracts.ts` string-literal union types must stay in lockstep
with their backend pydantic sources (CLAUDE.md §2: schema is the single source
of truth; contracts.ts must mirror it). Enum *values* are exact string matches
that break silently — a renamed direction or a new validation status ships a
frontend that quietly drops rows. This script diffs the value sets and fails
CI on any drift.

Scope: string-literal ENUM values only (not field names — those cross the
snake_case↔camelCase convention and are covered by typed API tests). Each TS
enum backed by a pydantic Literal/Enum is registered in ``REGISTRY``; the
Python side is imported live so the pydantic definition is the sole source of
truth (no hardcoded value lists here).

Usage:
    python scripts/check_contract_drift.py            # report + exit code
    python scripts/check_contract_drift.py --json     # machine-readable

Exit codes: 0 = in sync, 1 = drift detected, 2 = registry/parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Set, Tuple, get_args

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_TS = REPO_ROOT / "src" / "finer_dashboard" / "src" / "lib" / "contracts.ts"

# TS enum type name → (python module, attribute, kind). The Python side is the
# single source of truth; add a row when a new mirrored enum lands on either
# side. ``kind``: "literal" = typing.Literal alias, "enum" = str-Enum class.
REGISTRY: Dict[str, Tuple[str, str, str]] = {
    "SourceType": ("finer.schemas.contract", "SourceType", "literal"),
    "WorkflowStage": ("finer.schemas.contract", "WorkflowStage", "literal"),
    "ReviewDirection": ("finer.schemas.contract", "ReviewDirection", "literal"),
    "EntryStyle": ("finer.schemas.kol_profile", "ENTRY_STYLE_LITERAL", "literal"),
    "IntentDirection": ("finer.schemas.investment_intent", "DIRECTION_LITERAL", "literal"),
    "AnnotationTaskId": ("finer.schemas.annotation", "AnnotationTaskId", "literal"),
    "AnnotationExportMode": ("finer.schemas.annotation", "AnnotationExportMode", "literal"),
    "AnnotationItemStatus": ("finer.schemas.annotation", "AnnotationItemStatus", "literal"),
    "EvalSampleVerdict": ("finer.schemas.annotation", "EvalSampleVerdict", "literal"),
    "TradeValidationStatus": ("finer.schemas.trade_action", "ValidationStatus", "enum"),
    "CanonicalTraceStatus": ("finer.schemas.trade_action", "CANONICAL_TRACE_STATUS_LITERAL", "literal"),
    # F5 TradeAction core enums (trade_action.py)
    "TradeDirection": ("finer.schemas.trade_action", "TradeDirection", "enum"),
    "ActionType": ("finer.schemas.trade_action", "ActionType", "enum"),
    "TriggerType": ("finer.schemas.trade_action", "TriggerType", "enum"),
    "ExitReason": ("finer.schemas.trade_action", "ExitReason", "enum"),
    "MarketSession": ("finer.schemas.trade_action", "MarketSession", "enum"),
    "InstrumentType": ("finer.schemas.trade_action", "INSTRUMENT_TYPE_LITERAL", "literal"),
    "SignalClass": ("finer.schemas.trade_action", "SIGNAL_CLASS_LITERAL", "literal"),
    # F3 NormalizedInvestmentIntent literals (investment_intent.py)
    "IntentTargetType": ("finer.schemas.investment_intent", "TARGET_TYPE_LITERAL", "literal"),
    "IntentTimeHorizon": ("finer.schemas.investment_intent", "TIME_HORIZON_LITERAL", "literal"),
    "IntentRiskPreference": ("finer.schemas.investment_intent", "RISK_PREFERENCE_LITERAL", "literal"),
    "PositionDeltaHint": ("finer.schemas.investment_intent", "POSITION_DELTA_HINT_LITERAL", "literal"),
    "IntentActionability": ("finer.schemas.investment_intent", "ACTIONABILITY_LITERAL", "literal"),
    "IntentPriorDirection": ("finer.schemas.investment_intent", "PRIOR_DIRECTION_LITERAL", "literal"),
    "IntentRatingAction": ("finer.schemas.investment_intent", "RATING_ACTION_LITERAL", "literal"),
    "IntentConvictionSource": ("finer.schemas.investment_intent", "CONVICTION_SOURCE_LITERAL", "literal"),
}

# TS enums that intentionally have no pydantic mirror (UI-only vocabularies).
# Listing them here keeps the "unmapped TS enum" report honest — a NEW unmapped
# enum shows up and prompts a decision (register it, or add it here).
UI_ONLY_TS_ENUMS: Set[str] = {
    "WeChatLoginStatus",  # frontend polling state, not a persisted contract
}


class DriftError(Exception):
    """Registry misconfiguration or unreadable contracts.ts."""


# ── TS parsing ────────────────────────────────────────────────────────────────

# Matches `export type X = "a" | "b" | ...;` across one or many lines, capturing
# the RHS up to the terminating semicolon.
_TS_TYPE_RE = re.compile(
    r"export\s+type\s+(?P<name>\w+)\s*=\s*(?P<body>[^;]+);",
    re.DOTALL,
)
_TS_STRING_RE = re.compile(r'"([^"]*)"')


def parse_ts_enums(text: str) -> Dict[str, Set[str]]:
    """Extract every pure string-literal union type from contracts.ts.

    Only types whose RHS is entirely `"literal" | "literal" | ...` are returned
    (object types, intersections, and references are skipped).
    """
    enums: Dict[str, Set[str]] = {}
    for m in _TS_TYPE_RE.finditer(text):
        body = m.group("body").strip()
        # Strip leading union pipe and whitespace/newlines for the purity check.
        compact = re.sub(r"\s+", "", body)
        # Pure union of double-quoted strings separated by pipes, optional
        # leading pipe: "a"|"b" or |"a"|"b".
        if not re.fullmatch(r'\|?("[^"]*")(\|"[^"]*")*', compact):
            continue
        values = set(_TS_STRING_RE.findall(body))
        if values:
            enums[m.group("name")] = values
    return enums


# ── Python side ───────────────────────────────────────────────────────────────

def _import_attr(module: str, attr: str):
    import importlib

    mod = importlib.import_module(module)
    try:
        return getattr(mod, attr)
    except AttributeError as exc:
        raise DriftError(f"{module}.{attr} not found (registry stale?)") from exc


def python_enum_values(module: str, attr: str, kind: str) -> Set[str]:
    obj = _import_attr(module, attr)
    if kind == "literal":
        args = get_args(obj)
        if not args:
            raise DriftError(f"{module}.{attr} is not a Literal with args")
        return {str(a) for a in args}
    if kind == "enum":
        if not (isinstance(obj, type) and issubclass(obj, Enum)):
            raise DriftError(f"{module}.{attr} is not an Enum class")
        return {str(e.value) for e in obj}
    raise DriftError(f"unknown kind {kind!r} for {module}.{attr}")


# ── Diff ──────────────────────────────────────────────────────────────────────

def check() -> Tuple[List[dict], List[str]]:
    """Return (drifts, unmapped_ts_enums). Raises DriftError on config issues."""
    if not CONTRACTS_TS.exists():
        raise DriftError(f"contracts.ts not found at {CONTRACTS_TS}")
    ts_enums = parse_ts_enums(CONTRACTS_TS.read_text(encoding="utf-8"))

    drifts: List[dict] = []
    for ts_name, (module, attr, kind) in sorted(REGISTRY.items()):
        py_values = python_enum_values(module, attr, kind)
        if ts_name not in ts_enums:
            drifts.append({
                "ts_type": ts_name,
                "issue": "ts_type_missing",
                "detail": f"{module}.{attr} exists but contracts.ts has no "
                          f"`export type {ts_name} = ...` string union",
                "python": sorted(py_values),
                "ts": None,
            })
            continue
        ts_values = ts_enums[ts_name]
        missing_in_ts = py_values - ts_values
        extra_in_ts = ts_values - py_values
        if missing_in_ts or extra_in_ts:
            drifts.append({
                "ts_type": ts_name,
                "issue": "value_drift",
                "python_source": f"{module}.{attr}",
                "missing_in_ts": sorted(missing_in_ts),
                "extra_in_ts": sorted(extra_in_ts),
            })

    unmapped = sorted(
        name for name in ts_enums
        if name not in REGISTRY and name not in UI_ONLY_TS_ENUMS
    )
    return drifts, unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        drifts, unmapped = check()
    except DriftError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"✗ contract-drift check misconfigured: {exc}")
        return 2

    if args.json:
        print(json.dumps({"drifts": drifts, "unmapped_ts_enums": unmapped}, ensure_ascii=False))
    else:
        if not drifts:
            print(f"✓ contract enums in sync ({len(REGISTRY)} mapped enums)")
        for d in drifts:
            if d["issue"] == "ts_type_missing":
                print(f"✗ {d['ts_type']}: {d['detail']}")
                print(f"    python values: {d['python']}")
            else:
                print(f"✗ {d['ts_type']} ({d['python_source']}) drift:")
                if d["missing_in_ts"]:
                    print(f"    missing in contracts.ts: {d['missing_in_ts']}")
                if d["extra_in_ts"]:
                    print(f"    extra in contracts.ts (not in pydantic): {d['extra_in_ts']}")
        if unmapped:
            print(f"⚠ {len(unmapped)} TS string-enum(s) not mapped to a pydantic "
                  f"source (register in REGISTRY or UI_ONLY_TS_ENUMS): {unmapped}")

    return 1 if drifts else 0


if __name__ == "__main__":
    sys.exit(main())
