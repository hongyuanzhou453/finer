#!/usr/bin/env python
"""F2 constrained-LLM entity proposal — precision eval harness.

Mirrors ``scripts/eval_ocr_accuracy.py``'s report style. Two modes:

``propose`` (SPENDS TOKENS — red line):
    Select a small subset of gap blocks (zero-anchor / low-hit items) and run the
    constrained-LLM proposer on them, writing each validated proposal to a JSONL
    with an empty ``verdict`` column for manual review. Gated behind
    ``--confirm-spend`` AND ``--limit`` so it cannot accidentally burn the corpus.

``score`` (offline, no tokens):
    Read a JSONL whose ``verdict`` column has been filled in by a human
    (``correct`` / ``incorrect`` / ``partial``) and report precision overall and
    by cohort / confidence bucket, against the >=0.60 target line.

Workflow::

    # 1. After user authorization, propose on a capped subset:
    python scripts/eval_f2_llm_proposals.py propose \\
        --scope all-local --limit 30 --confirm-spend --out /tmp/f2_llm_eval.jsonl

    # 2. A human fills the `verdict` column in /tmp/f2_llm_eval.jsonl

    # 3. Score:
    python scripts/eval_f2_llm_proposals.py score --scored-in /tmp/f2_llm_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

from finer.enrichment.llm_entity_proposal import (  # noqa: E402
    LLMEntityProposalAdapter,
    LLMEntityProposalError,
)
from finer.llm import DeepSeekClient  # noqa: E402
from scripts.backfill_f2_anchor import (  # noqa: E402
    _FINANCIAL_CONTEXT_TERMS,
    _blocks_without_spans,
    _gap_scan_reason,
    plan_backfill,
)

PRECISION_TARGET = 0.60
VERDICT_VALUES = ("correct", "incorrect", "partial")


def _iter_gap_blocks(
    plan: Any,
    *,
    limit: int,
    per_doc_cap: int = 0,
) -> Iterator[tuple[Any, dict[str, Any], str]]:
    """Yield (item, block, scan_reason) for gap blocks, mirroring build_gap_report.

    ``per_doc_cap`` (0 = unlimited) bounds how many blocks one document may
    contribute, so the subset spreads across documents/entities instead of
    being exhausted inside a single gap-heavy doc.
    """
    count = 0
    for item in plan.items:
        scan_reason = _gap_scan_reason(item)
        if scan_reason is None:
            continue
        doc_count = 0
        for block in _blocks_without_spans(item):
            text = block.get("text") or ""
            if not text.strip():
                continue
            if scan_reason == "low_hit_rate" and not any(
                term in text for term in _FINANCIAL_CONTEXT_TERMS
            ):
                continue
            yield item, block, scan_reason
            count += 1
            doc_count += 1
            if count >= limit:
                return
            if per_doc_cap and doc_count >= per_doc_cap:
                break


def _confidence_bucket(confidence: float) -> str:
    if confidence >= 0.8:
        return ">=0.80"
    if confidence >= 0.6:
        return "0.60-0.79"
    return "<0.60"


def cmd_propose(args: argparse.Namespace) -> int:
    if not args.confirm_spend:
        print("propose mode calls the real LLM and SPENDS TOKENS.")
        print(
            f"Re-run with --confirm-spend to proceed "
            f"(capped at --limit {args.limit} blocks)."
        )
        return 2

    # propose needs real creds; the import chain does not auto-load .env.
    load_dotenv(".env", override=False)
    if args.base_url or args.model:
        # Explicit endpoint/model — bypass the from_env FINER_LLM_BASE_URL
        # fallback (which mis-routes DEEPSEEK_API_KEY to the MiMo endpoint).
        client = DeepSeekClient(
            base_url=args.base_url or None,
            model=args.model or None,
            timeout=args.timeout,
        )
        adapter = LLMEntityProposalAdapter(deepseek_client=client)
    else:
        adapter = LLMEntityProposalAdapter()
    if not adapter.is_configured():
        print(
            "DeepSeek is not configured (set DEEPSEEK_API_KEY). Aborting.",
            file=sys.stderr,
        )
        return 1

    plan = plan_backfill(args.data_root, scope=args.scope, force=False)
    rows: list[dict[str, Any]] = []
    blocks_called = 0

    for item, block, scan_reason in _iter_gap_blocks(
        plan, limit=args.limit, per_doc_cap=args.per_doc_cap
    ):
        blocks_called += 1
        try:
            proposals = adapter.propose_for_block(
                text=block.get("text") or "",
                block_id=str(block.get("block_id") or ""),
                source_record_id=item.content_id,
                raw_path=item.raw_path,
                reason=scan_reason,
            )
        except LLMEntityProposalError as exc:
            print(f"  [skip] {item.content_id} {block.get('block_id')}: {exc}", file=sys.stderr)
            continue
        for cand in proposals:
            rows.append(
                {
                    "alias_candidate": cand["alias_candidate"],
                    "suggested_ticker": cand.get("suggested_ticker", ""),
                    "suggested_market": cand.get("suggested_market", ""),
                    "suggested_entity_type": cand.get("suggested_entity_type", ""),
                    "llm_confidence": cand.get("llm_confidence", cand.get("score")),
                    "evidence_quote": cand.get("evidence_quote", ""),
                    "context_snippet": cand.get("context_snippet", ""),
                    "source_record_id": cand["source_record_id"],
                    "block_id": cand["block_id"],
                    "raw_path": cand.get("raw_path", ""),
                    "f0_source_type": item.f0_source_type,
                    "verdict": "",
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    args.out.write_text((payload + "\n") if payload else "", encoding="utf-8")

    print(f"=== F2 LLM proposal run ===")
    print(f"  scope:          {args.scope}")
    print(f"  blocks queried: {blocks_called} (limit {args.limit})")
    print(f"  proposals:      {len(rows)}")
    print(f"  out:            {args.out}")
    print(f"\nNext: fill the `verdict` column (one of {VERDICT_VALUES}) then run:")
    print(f"  python scripts/eval_f2_llm_proposals.py score --scored-in {args.out}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    rows = [
        json.loads(line)
        for line in args.scored_in.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        print(f"No rows in {args.scored_in}.")
        return 1

    judged = [r for r in rows if str(r.get("verdict") or "").strip() in VERDICT_VALUES]
    unjudged = len(rows) - len(judged)

    def _precision(items: list[dict[str, Any]]) -> float | None:
        if not items:
            return None
        correct = sum(1 for r in items if r["verdict"] == "correct")
        return correct / len(items)

    overall = _precision(judged)

    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_conf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in judged:
        by_cohort[str(r.get("f0_source_type") or "?")].append(r)
        try:
            conf = float(r.get("llm_confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        by_conf[_confidence_bucket(conf)].append(r)

    print(f"=== F2 LLM proposal precision ({len(judged)}/{len(rows)} judged) ===\n")
    if unjudged:
        print(f"  ({unjudged} rows still have an empty/invalid verdict)\n")

    print(f"{'cohort':24s} {'n':>4s} {'correct':>8s} {'precision':>10s}")
    for cohort, items in sorted(by_cohort.items(), key=lambda kv: -len(kv[1])):
        prec = _precision(items)
        correct = sum(1 for r in items if r["verdict"] == "correct")
        pr = f"{prec:.3f}" if prec is not None else "  -  "
        print(f"{cohort[:24]:24s} {len(items):>4d} {correct:>8d} {pr:>10s}")

    print(f"\n{'confidence':24s} {'n':>4s} {'correct':>8s} {'precision':>10s}")
    for bucket in (">=0.80", "0.60-0.79", "<0.60"):
        items = by_conf.get(bucket, [])
        if not items:
            continue
        prec = _precision(items)
        correct = sum(1 for r in items if r["verdict"] == "correct")
        pr = f"{prec:.3f}" if prec is not None else "  -  "
        print(f"{bucket:24s} {len(items):>4d} {correct:>8d} {pr:>10s}")

    print("\n=== verdict counts ===")
    counts = defaultdict(int)
    for r in judged:
        counts[r["verdict"]] += 1
    for v in VERDICT_VALUES:
        print(f"  {v:10s}: {counts.get(v, 0)}")

    print("\n=== aggregate ===")
    if overall is None:
        print("  no judged rows")
        return 1
    verdict = "PASS" if overall >= PRECISION_TARGET else "BELOW TARGET"
    print(f"  precision : {overall:.3f}  (target >= {PRECISION_TARGET:.2f} -> {verdict})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_propose = sub.add_parser("propose", help="Run the LLM proposer on a capped gap subset (spends tokens)")
    p_propose.add_argument("--data-root", type=Path, default=Path("data"))
    p_propose.add_argument("--scope", choices=("curated-pdf", "all-local"), default="all-local")
    p_propose.add_argument("--limit", type=int, default=30, help="Max gap blocks to query")
    p_propose.add_argument("--per-doc-cap", type=int, default=0, help="Max blocks per document (0 = unlimited; use e.g. 3 to spread the subset)")
    p_propose.add_argument("--confirm-spend", action="store_true", help="Required to actually call the LLM")
    p_propose.add_argument("--base-url", default="", help="Override LLM base_url (e.g. https://api.deepseek.com)")
    p_propose.add_argument("--model", default="", help="Override model (e.g. deepseek-chat)")
    p_propose.add_argument("--timeout", type=float, default=120.0)
    p_propose.add_argument("--out", type=Path, default=Path("/tmp/f2_llm_eval.jsonl"))
    p_propose.set_defaults(func=cmd_propose)

    p_score = sub.add_parser("score", help="Score a human-judged proposal JSONL (offline)")
    p_score.add_argument("--scored-in", type=Path, required=True)
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
