#!/usr/bin/env python
"""Check F2 backfill coverage against current dry-run baselines."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backfill_f2_anchor import build_gap_report, plan_backfill  # noqa: E402


EXPECTED_CANDIDATE_KEYS = {
    "alias_candidate",
    "source_record_id",
    "block_id",
    "raw_path",
    "context_snippet",
    "reason",
    "candidate_type",
    "score",
}
FORBIDDEN_CANDIDATE_KEYS = {"ticker", "market", "entity_id"}
REQUIRED_TEMPORAL_RULES = {
    "published_at",
    "relative_day_from_published_at",
    "relative_week_from_published_at",
}


@dataclass(frozen=True)
class CoverageBaseline:
    min_scanned: int
    min_selected: int
    min_blocks: int
    min_hit_blocks: int
    min_hit_rate: float
    min_anchors: int
    min_temporal_anchors: int
    min_temporal_spans: int
    min_spans: int
    max_zero_anchor: int


@dataclass
class CoverageCheckResult:
    scope: str
    summary: dict[str, Any]
    candidate_count: int
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


BASELINES = {
    "curated-pdf": CoverageBaseline(
        min_scanned=401,
        min_selected=14,
        min_blocks=357,
        min_hit_blocks=190,
        min_hit_rate=0.532,
        min_anchors=210,
        min_temporal_anchors=501,
        min_temporal_spans=487,
        min_spans=1592,
        max_zero_anchor=1,
    ),
    "all-local": CoverageBaseline(
        min_scanned=401,
        min_selected=205,
        min_blocks=3051,
        min_hit_blocks=507,
        min_hit_rate=0.165,
        min_anchors=564,
        min_temporal_anchors=1246,
        min_temporal_spans=1041,
        min_spans=2813,
        max_zero_anchor=71,
    ),
}


def _check_min(
    failures: list[str],
    *,
    name: str,
    actual: int | float,
    expected: int | float,
) -> None:
    if actual < expected:
        failures.append(f"{name} regressed: {actual} < {expected}")


def _check_max(
    failures: list[str],
    *,
    name: str,
    actual: int | float,
    expected: int | float,
) -> None:
    if actual > expected:
        failures.append(f"{name} regressed: {actual} > {expected}")


def check_scope(
    data_root: Path,
    *,
    scope: str,
    baseline: CoverageBaseline,
) -> CoverageCheckResult:
    plan = plan_backfill(data_root, scope=scope)
    report = build_gap_report(plan)
    summary = report["summary"]
    totals = summary["totals"]
    failures: list[str] = []

    _check_min(failures, name="scanned", actual=int(totals["scanned"]), expected=baseline.min_scanned)
    _check_min(failures, name="selected", actual=int(totals["selected"]), expected=baseline.min_selected)
    _check_min(failures, name="blocks", actual=int(totals["blocks"]), expected=baseline.min_blocks)
    _check_min(
        failures,
        name="hit_blocks",
        actual=int(totals["hit_blocks"]),
        expected=baseline.min_hit_blocks,
    )
    _check_min(
        failures,
        name="hit_rate",
        actual=float(totals["hit_rate"]),
        expected=baseline.min_hit_rate,
    )
    _check_min(failures, name="anchors", actual=int(totals["anchors"]), expected=baseline.min_anchors)
    _check_min(
        failures,
        name="temporal_anchors",
        actual=int(totals["temporal_anchors"]),
        expected=baseline.min_temporal_anchors,
    )
    _check_min(
        failures,
        name="temporal_spans",
        actual=int(totals["temporal_spans"]),
        expected=baseline.min_temporal_spans,
    )
    _check_min(failures, name="spans", actual=int(totals["spans"]), expected=baseline.min_spans)
    _check_max(
        failures,
        name="zero_anchor",
        actual=int(totals["zero_anchor"]),
        expected=baseline.max_zero_anchor,
    )
    _check_max(failures, name="errors", actual=int(totals["errors"]), expected=0)

    for key in (
        "by_f0_source_type",
        "by_f1_source_type",
        "worst_f0_source_types",
        "worst_f1_source_types",
        "by_status",
        "temporal_rules",
        "temporal_strategies",
        "temporal_granularity",
    ):
        if key not in summary:
            failures.append(f"summary missing key: {key}")

    for key in (
        "low_hit_diagnostics",
        "low_hit_reason_summary",
        "low_hit_reason_by_f0_source_type",
        "low_hit_reason_by_f1_source_type",
    ):
        if key not in report:
            failures.append(f"report missing key: {key}")

    for index, diagnostic in enumerate(report.get("low_hit_diagnostics") or []):
        if "missed_block_reasons" not in diagnostic:
            failures.append(f"low_hit_diagnostics[{index}] missing missed_block_reasons")
        if "missed_block_samples" not in diagnostic:
            failures.append(f"low_hit_diagnostics[{index}] missing missed_block_samples")

    temporal_rules = summary.get("temporal_rules") or {}
    for rule in REQUIRED_TEMPORAL_RULES:
        if int(temporal_rules.get(rule) or 0) <= 0:
            failures.append(f"temporal rule missing or empty: {rule}")

    for index, candidate in enumerate(report["gap_candidates"]):
        keys = set(candidate)
        forbidden = keys & FORBIDDEN_CANDIDATE_KEYS
        if forbidden:
            failures.append(
                f"gap_candidates[{index}] has forbidden keys: {sorted(forbidden)}"
            )
        if keys != EXPECTED_CANDIDATE_KEYS:
            failures.append(
                f"gap_candidates[{index}] schema drift: {sorted(keys)}"
            )

    return CoverageCheckResult(
        scope=scope,
        summary=summary,
        candidate_count=len(report["gap_candidates"]),
        failures=failures,
    )


def check_scopes(data_root: Path, scopes: list[str]) -> list[CoverageCheckResult]:
    return [
        check_scope(data_root, scope=scope, baseline=BASELINES[scope])
        for scope in scopes
    ]


def _print_result(result: CoverageCheckResult) -> None:
    totals = result.summary["totals"]
    status = "PASS" if result.passed else "FAIL"
    print(
        f"{status} {result.scope}: "
        f"selected={int(totals['selected'])} "
        f"blocks={int(totals['blocks'])} "
        f"hit_blocks={int(totals['hit_blocks'])} "
        f"hit_rate={float(totals['hit_rate']):.1%} "
        f"anchors={int(totals['anchors'])} "
        f"temporal={int(totals['temporal_anchors'])} "
        f"temporal_spans={int(totals['temporal_spans'])} "
        f"spans={int(totals['spans'])} "
        f"zero={int(totals['zero_anchor'])} "
        f"candidates={result.candidate_count}"
    )
    for failure in result.failures:
        print(f"  - {failure}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--scope",
        choices=("all", "curated-pdf", "all-local"),
        default="all",
    )
    args = parser.parse_args()

    scopes = list(BASELINES) if args.scope == "all" else [args.scope]
    results = check_scopes(args.data_root, scopes)
    for result in results:
        _print_result(result)

    if any(not result.passed for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
