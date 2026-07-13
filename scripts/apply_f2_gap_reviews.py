#!/usr/bin/env python
"""Apply human-reviewed F2 gap candidates to annotation registry gaps.

Reads JSONL rows produced by ``backfill_f2_anchor.py --gap-candidates-out`` after
human review. Dry-run is the default. Only rows with ``review_status=approved``
are eligible, and writes go through ``AnnotationStore.append_registry_gap()``
rather than touching the entity registry directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from finer.services.annotation_store import AnnotationStore  # noqa: E402


APPROVED_STATUS = "approved"
SKIP_STATUSES = {"", "pending", "needs_review", "rejected", "ignore", "ignored"}


@dataclass
class PlannedRegistryGap:
    alias: str
    item_id: str
    suggested_ticker: str
    market: str
    source_line: int


@dataclass
class RegistryGapApplyPlan:
    review_path: Path
    dpo_dir: Path
    scanned: int = 0
    approved: int = 0
    skipped: int = 0
    duplicates: int = 0
    written: int = 0
    items: list[PlannedRegistryGap] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def to_write(self) -> int:
        return len(self.items)


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        rows.append((line_no, payload))
    return rows


def _existing_registry_gap_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    for _, row in _read_jsonl(path):
        alias = str(row.get("alias") or "").strip().casefold()
        item_id = str(row.get("item_id") or "").strip()
        if alias:
            keys.add((alias, item_id))
    return keys


def _review_status(row: dict[str, Any]) -> str:
    return str(row.get("review_status") or "").strip().casefold()


def _planned_gap_from_row(line_no: int, row: dict[str, Any]) -> PlannedRegistryGap | str:
    alias = str(row.get("alias_candidate") or row.get("alias") or "").strip()
    if not alias:
        return f"line {line_no}: alias_candidate is required for approved rows"
    return PlannedRegistryGap(
        alias=alias,
        item_id=str(row.get("source_record_id") or row.get("item_id") or "").strip(),
        suggested_ticker=str(row.get("suggested_ticker") or "").strip(),
        market=str(row.get("market") or "").strip(),
        source_line=line_no,
    )


def plan_registry_gap_apply(review_path: Path, *, dpo_dir: Path) -> RegistryGapApplyPlan:
    plan = RegistryGapApplyPlan(review_path=review_path, dpo_dir=dpo_dir)
    existing_keys = _existing_registry_gap_keys(AnnotationStore(dpo_dir=dpo_dir).registry_gaps)
    planned_keys: set[tuple[str, str]] = set()

    for line_no, row in _read_jsonl(review_path):
        plan.scanned += 1
        status = _review_status(row)
        if status != APPROVED_STATUS:
            if status in SKIP_STATUSES:
                plan.skipped += 1
                continue
            plan.errors.append(f"line {line_no}: unsupported review_status={status!r}")
            continue

        planned = _planned_gap_from_row(line_no, row)
        if isinstance(planned, str):
            plan.errors.append(planned)
            continue

        plan.approved += 1
        key = (planned.alias.casefold(), planned.item_id)
        if key in existing_keys or key in planned_keys:
            plan.duplicates += 1
            continue
        planned_keys.add(key)
        plan.items.append(planned)

    return plan


def write_registry_gap_plan(plan: RegistryGapApplyPlan, *, reviewer_id: str) -> None:
    reviewer_id = reviewer_id.strip()
    if not reviewer_id:
        raise ValueError("reviewer_id is required for --write")

    store = AnnotationStore(dpo_dir=plan.dpo_dir)
    for item in plan.items:
        store.append_registry_gap(
            alias=item.alias,
            suggested_ticker=item.suggested_ticker,
            market=item.market,
            item_id=item.item_id,
            reviewer_id=reviewer_id,
        )
        plan.written += 1


def _print_plan(plan: RegistryGapApplyPlan, *, mode: str) -> None:
    print(f"mode:       {mode}")
    print(f"review:     {plan.review_path}")
    print(f"dpo_dir:    {plan.dpo_dir}")
    print(f"scanned:    {plan.scanned}")
    print(f"approved:   {plan.approved}")
    print(f"skipped:    {plan.skipped}")
    print(f"duplicates: {plan.duplicates}")
    print(f"to_write:   {plan.to_write}")
    if mode == "write":
        print(f"written:    {plan.written}")
    if plan.items:
        print("\nApproved registry-gap rows:")
        for item in plan.items[:20]:
            print(
                f"  line={item.source_line}  "
                f"alias={item.alias}  "
                f"item_id={item.item_id}  "
                f"ticker={item.suggested_ticker or '-'}  "
                f"market={item.market or '-'}"
            )
        remaining = len(plan.items) - 20
        if remaining > 0:
            print(f"  ... {remaining} more")
    if plan.errors:
        print(f"\nERRORS ({len(plan.errors)}):")
        for err in plan.errors[:20]:
            print(f"  {err}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-in", type=Path, required=True)
    parser.add_argument("--dpo-dir", type=Path, default=Path("data/dpo"))
    parser.add_argument("--reviewer-id", default="")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; default mode")
    parser.add_argument("--write", action="store_true", help="Append approved rows")
    args = parser.parse_args()

    if args.dry_run and args.write:
        print("--dry-run and --write are mutually exclusive", file=sys.stderr)
        raise SystemExit(2)
    if args.write and not args.reviewer_id.strip():
        print("--reviewer-id is required with --write", file=sys.stderr)
        raise SystemExit(2)

    mode = "write" if args.write else "dry-run"
    try:
        plan = plan_registry_gap_apply(args.review_in, dpo_dir=args.dpo_dir)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"failed to read review input: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.write and not plan.errors:
        write_registry_gap_plan(plan, reviewer_id=args.reviewer_id)
    _print_plan(plan, mode=mode)

    if plan.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
