#!/usr/bin/env python3
"""Validate DPO HQ v1 cleaned preference pairs.

The HQ dataset is intentionally stricter than the generic DPO export path:
every kept pair must be manually reviewed, every chosen answer must conform to
the compact target schema, and train/eval id overlap is a hard failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from finer.ml.rewards import (  # noqa: E402
    extract_cited_numbers,
    is_committal,
    number_in_text,
    parse_output,
    ticker_grounded,
    validate_structure,
)
from finer.services.annotation_store import evidence_from_prompt  # noqa: E402


REQUIRED_CHOSEN_KEYS = {
    "ticker",
    "direction",
    "conviction",
    "action_chain",
    "time_horizon",
    "rationale",
}
ALLOWED_REVIEW_VERDICTS = {"accept", "edit"}
TARGET_PRICE_KEYS = ("target_price_low", "target_price_high")


def load_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    bad: List[Dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                bad.append({"line": line_no, "error": str(exc)})
                continue
            if not isinstance(obj, dict):
                bad.append({"line": line_no, "error": "row must be a JSON object"})
                continue
            rows.append(obj)
    return rows, bad


def normalized_prompt_hash(prompt: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", "", prompt).encode("utf-8")).hexdigest()[:16]


def eval_ids(rows: Iterable[Dict[str, Any]]) -> Set[str]:
    ids: Set[str] = set()
    for row in rows:
        row_id = row.get("id") or (row.get("meta") or {}).get("passage_id")
        if isinstance(row_id, str) and row_id:
            ids.add(row_id)
    return ids


def target_prices(obj: Dict[str, Any]) -> List[float]:
    prices: List[float] = []
    for step in obj.get("action_chain", []) or []:
        if not isinstance(step, dict):
            continue
        for key in TARGET_PRICE_KEYS:
            value = step.get(key)
            if isinstance(value, (int, float)):
                prices.append(float(value))
    return prices


def parse_json_object(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, str):
        return None
    return parse_output(raw)


def validate_chosen_schema(chosen: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(chosen.keys())
    missing = sorted(REQUIRED_CHOSEN_KEYS - keys)
    extra = sorted(keys - REQUIRED_CHOSEN_KEYS)
    if missing:
        errors.append(f"chosen missing keys: {missing}")
    if extra:
        errors.append(f"chosen has extra keys: {extra}")
    conviction = chosen.get("conviction")
    if not isinstance(conviction, (int, float)) or not 0 <= float(conviction) <= 1:
        errors.append(f"conviction invalid: {conviction!r}")
    rationale = chosen.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append("rationale must be a non-empty string")
    chain = chosen.get("action_chain")
    if not isinstance(chain, list):
        errors.append("action_chain must be a list")
    ok, reason = validate_structure(chosen)
    if not ok:
        errors.append(f"chosen structure invalid: {reason}")
    return errors


def validate_row(row: Dict[str, Any], row_no: int, eval_id_set: Set[str]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    errors: List[str] = []
    warnings: List[str] = []
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    passage_id = meta.get("passage_id")
    reviewer_id = meta.get("reviewer_id")
    review_verdict = meta.get("review_verdict")

    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        errors.append("missing meta.reviewer_id")
    if review_verdict not in ALLOWED_REVIEW_VERDICTS:
        errors.append(f"meta.review_verdict must be accept/edit, got {review_verdict!r}")
    if isinstance(passage_id, str) and passage_id in eval_id_set:
        errors.append(f"train/eval overlap id: {passage_id}")

    prompt = row.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append("prompt missing or empty")
        evidence = ""
    else:
        evidence = evidence_from_prompt(prompt)

    chosen = parse_json_object(row.get("chosen"))
    rejected = parse_json_object(row.get("rejected"))
    if chosen is None:
        errors.append("chosen is not a JSON object")
    if rejected is None:
        errors.append("rejected is not a JSON object")
    if chosen is not None and rejected is not None and chosen == rejected:
        errors.append("chosen equals rejected")

    if chosen is not None:
        errors.extend(validate_chosen_schema(chosen))
        if is_committal(chosen) and not ticker_grounded(str(chosen.get("ticker", "")), evidence):
            errors.append(f"ticker not grounded in evidence: {chosen.get('ticker')!r}")
        missing_prices = [n for n in target_prices(chosen) if not number_in_text(n, evidence)]
        if missing_prices:
            errors.append(f"target prices not found in evidence: {missing_prices}")
        trigger_numbers = [n for n in extract_cited_numbers(chosen) if n not in target_prices(chosen)]
        missing_trigger_numbers = [n for n in trigger_numbers if not number_in_text(n, evidence)]
        if missing_trigger_numbers:
            warnings.append(f"trigger numbers not found in evidence: {missing_trigger_numbers}")

    if rejected is not None:
        ok, reason = validate_structure(rejected)
        if not ok:
            warnings.append(f"rejected structure invalid: {reason}")

    summary = {
        "row_no": row_no,
        "passage_id": passage_id,
        "review_verdict": review_verdict,
        "reviewer_id": reviewer_id,
        "direction": chosen.get("direction") if chosen else None,
        "hq_category": meta.get("hq_category"),
        "prompt_hash": normalized_prompt_hash(prompt or ""),
    }
    return errors, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate DPO HQ v1 cleaned preference pairs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--pairs", required=True, help="Cleaned HQ pairs JSONL")
    parser.add_argument("--eval", required=True, help="Held-out eval_set/passages JSONL for leakage check")
    parser.add_argument("--report", required=True, help="Output quality report JSON")
    parser.add_argument("--min-size", type=int, default=120)
    parser.add_argument("--max-size", type=int, default=150)
    args = parser.parse_args()

    pairs_path = Path(args.pairs)
    eval_path = Path(args.eval)
    report_path = Path(args.report)

    pair_rows, pair_bad = load_jsonl(pairs_path)
    eval_rows, eval_bad = load_jsonl(eval_path)
    eval_id_set = eval_ids(eval_rows)

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    row_summaries: List[Dict[str, Any]] = []
    prompt_hashes: Counter[str] = Counter()

    if pair_bad:
        errors.extend({"scope": "pairs_jsonl", **item} for item in pair_bad)
    if eval_bad:
        errors.extend({"scope": "eval_jsonl", **item} for item in eval_bad)
    if not args.min_size <= len(pair_rows) <= args.max_size:
        errors.append(
            {
                "scope": "dataset_size",
                "error": f"expected {args.min_size}-{args.max_size} rows, got {len(pair_rows)}",
            }
        )

    for idx, row in enumerate(pair_rows, 1):
        row_errors, row_warnings, summary = validate_row(row, idx, eval_id_set)
        row_summaries.append(summary)
        prompt_hashes[summary["prompt_hash"]] += 1
        errors.extend({"scope": "row", **summary, "error": err} for err in row_errors)
        warnings.extend({"scope": "row", **summary, "warning": warn} for warn in row_warnings)

    duplicate_hashes = sorted(h for h, count in prompt_hashes.items() if h and count > 1)
    for dup in duplicate_hashes:
        errors.append({"scope": "duplicate_prompt", "prompt_hash": dup, "error": "duplicate prompt"})

    direction_counts = Counter(str(row.get("direction")) for row in row_summaries)
    category_counts = Counter(str(row.get("hq_category")) for row in row_summaries)
    review_counts = Counter(str(row.get("review_verdict")) for row in row_summaries)
    reviewer_counts = Counter(str(row.get("reviewer_id")) for row in row_summaries)
    overlap_ids = sorted(
        {
            str(row.get("passage_id"))
            for row in row_summaries
            if isinstance(row.get("passage_id"), str) and row.get("passage_id") in eval_id_set
        }
    )

    report = {
        "ok": not errors,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pairs_path": str(pairs_path),
        "eval_path": str(eval_path),
        "row_count": len(pair_rows),
        "min_size": args.min_size,
        "max_size": args.max_size,
        "eval_ids": len(eval_id_set),
        "train_eval_overlap_ids": overlap_ids,
        "direction_counts": dict(direction_counts),
        "hq_category_counts": dict(category_counts),
        "review_counts": dict(review_counts),
        "reviewer_counts": dict(reviewer_counts),
        "duplicate_prompt_hashes": duplicate_hashes,
        "errors": errors,
        "warnings": warnings,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ok={report['ok']} rows={len(pair_rows)} errors={len(errors)} warnings={len(warnings)}")
    print(f"direction_counts={dict(direction_counts)}")
    print(f"review_counts={dict(review_counts)}")
    print(f"wrote {report_path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
