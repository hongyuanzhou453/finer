#!/usr/bin/env python
"""Drive broker recommendation intents (bri_*) through F4 → F5 canonical pipeline.

Reads data/F3_intents/bri_*.json (produced by broker_recommendation_adapter),
joins each intent to its F2-anchored envelope (data/F2_anchored/broker_*.json),
bridges the grounding gap (intent.target_symbol → anchor.resolved_symbol via
enrichment.ticker_normalization), maps F4 policy per intent, and runs the
canonical F5 entry point `run_canonical_from_artifacts`.

Zero LLM calls: strategy is "programmatic" throughout.

Output: data/F5_executed/bri_{env_stem}_actions.json  (bri_ prefix keeps these
files out of regen_canonical_f5.py's re-extraction sweep) + SQLite index via
TradeActionRepository.index_trade_action.

Idempotent: intents whose intent_id already appears in an existing
bri_*_actions.json are skipped.

Usage:
    python scripts/drive_broker_recommendations.py            # dry-run (default)
    python scripts/drive_broker_recommendations.py --execute  # write to disk
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.ticker_normalization import normalize_broker_ticker  # noqa: E402
from finer.pipeline.canonical_runner import (  # noqa: E402
    _coerce_envelope_anchors,
    run_canonical_from_artifacts,
)
from finer.policy.policy_mapper import PolicyMapper  # noqa: E402
from finer.schemas.content_envelope import ContentEnvelope  # noqa: E402
from finer.schemas.evidence import EvidenceSpan  # noqa: E402
from finer.schemas.investment_intent import NormalizedInvestmentIntent  # noqa: E402
from finer.schemas.policy import PolicyContext  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"
F3_DIR = DATA_ROOT / "F3_intents"
F2_DIR = DATA_ROOT / "F2_anchored"
F5_DIR = DATA_ROOT / "F5_executed"


# ── Loading ──────────────────────────────────────────────────────────────────


def load_bri_intents() -> List[NormalizedInvestmentIntent]:
    intents: List[NormalizedInvestmentIntent] = []
    for path in sorted(F3_DIR.glob("bri_*.json")):
        # JSON mode: strict models still accept ISO datetime strings here
        intents.append(
            NormalizedInvestmentIntent.model_validate_json(path.read_text(encoding="utf-8"))
        )
    return intents


def load_envelopes() -> Dict[str, Tuple[Path, ContentEnvelope]]:
    """envelope_id → (file path, coerced ContentEnvelope)."""
    envs: Dict[str, Tuple[Path, ContentEnvelope]] = {}
    for path in sorted(F2_DIR.glob("broker_*.json")):
        env = ContentEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
        _coerce_envelope_anchors(env)
        envs[env.envelope_id] = (path, env)
    return envs


def existing_actioned_intent_ids() -> set[str]:
    """intent_ids already present in bri_*_actions.json files (idempotency)."""
    seen: set[str] = set()
    for path in F5_DIR.glob("bri_*_actions.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for action in data.get("actions", []):
                iid = action.get("intent_id")
                if iid:
                    seen.add(iid)
        except (OSError, json.JSONDecodeError):
            continue
    return seen


# ── Grounding bridge ─────────────────────────────────────────────────────────


def bridge_target_symbol(
    intent: NormalizedInvestmentIntent, env: ContentEnvelope
) -> Optional[str]:
    """Normalize intent.target_symbol to match one of the envelope's F2
    anchor resolved_symbols. Returns the matched symbol or None (no fabrication).

    Only mutates the in-memory intent; pipeline code untouched.
    """
    anchor_symbols = {
        getattr(a, "resolved_symbol", None)
        for a in (env.entity_anchors or [])
    }
    anchor_symbols.discard(None)

    raw = intent.target_symbol
    if raw in anchor_symbols:
        return raw

    normalized = normalize_broker_ticker(raw) if raw else None
    if normalized and normalized.symbol in anchor_symbols:
        intent.target_symbol = normalized.symbol
        return normalized.symbol
    return None


def collect_env_spans(env: ContentEnvelope) -> List[EvidenceSpan]:
    spans: List[EvidenceSpan] = []
    for block in env.blocks or []:
        raw_spans = (
            block.get("evidence_spans") if isinstance(block, dict)
            else getattr(block, "evidence_spans", None)
        ) or []
        for raw in raw_spans:
            try:
                spans.append(
                    raw if isinstance(raw, EvidenceSpan) else EvidenceSpan.model_validate(raw)
                )
            except Exception:  # noqa: BLE001 — malformed F2 span, skip
                continue
    return spans


# ── Main drive ───────────────────────────────────────────────────────────────


async def drive(execute: bool) -> None:
    intents = load_bri_intents()
    envs = load_envelopes()
    already = existing_actioned_intent_ids()

    print(f"bri intents: {len(intents)}")
    print(f"broker envelopes: {len(envs)}")
    print(f"already-actioned intent_ids (skip): {len(already & {i.intent_id for i in intents})}")

    # Group runnable intents per envelope
    per_env: Dict[str, List[NormalizedInvestmentIntent]] = defaultdict(list)
    skips: Counter = Counter()
    skip_detail: List[str] = []
    bridged = 0

    for intent in intents:
        if intent.intent_id in already:
            skips["already_actioned"] += 1
            continue
        pair = envs.get(intent.envelope_id)
        if pair is None:
            skips["no_envelope"] += 1
            skip_detail.append(f"{intent.intent_id}: envelope {intent.envelope_id} not found")
            continue
        _, env = pair
        matched = bridge_target_symbol(intent, env)
        if matched is None:
            skips["no_anchor_match"] += 1
            skip_detail.append(
                f"{intent.intent_id}: target_symbol={intent.target_symbol!r} "
                f"has no matching resolved_symbol in {intent.envelope_id}"
            )
            continue
        bridged += 1
        per_env[intent.envelope_id].append(intent)

    print(f"grounding bridge matched: {bridged}")
    if skips:
        print(f"skips: {dict(skips)}")
    for line in skip_detail:
        print(f"  skip: {line}")

    if not execute:
        print("\n[dry-run] plan:")
        for eid, group in sorted(per_env.items()):
            path, env = envs[eid]
            out = F5_DIR / f"bri_{path.stem}_actions.json"
            print(f"  {eid} ({env.creator_id}): {len(group)} intent(s) -> {out.name}")
        print("\nUse --execute to run F4/F5 and write outputs.")
        return

    # Lazy import so dry-run never touches SQLite
    from finer.services.repository import TradeActionRepository

    repo = TradeActionRepository()
    action_hint_dist: Counter = Counter()
    trace_status_dist: Counter = Counter()
    rejected_reasons: Counter = Counter()
    written_files: List[str] = []
    indexed = 0
    total_actions = 0

    F5_DIR.mkdir(parents=True, exist_ok=True)

    for eid, group in sorted(per_env.items()):
        env_path, env = envs[eid]

        # F4 — per-envelope batch (composer consumes batch.mapped_intents)
        mapper = PolicyMapper(context=PolicyContext(kol_id=env.creator_id))
        batch = mapper.map_batch(group)
        for m in batch.mappings:
            action_hint_dist[m.action_hint] += 1

        # F5 — canonical entry
        result = await run_canonical_from_artifacts(
            intents=group,
            policy_batch=batch,
            evidence_spans=collect_env_spans(env),
            envelope=env,
            temporal_anchors=env.temporal_anchors,
            strategy="programmatic",
        )

        for r in result.rejected_intents:
            rejected_reasons[r.reason] += 1
        for a in result.trade_actions:
            trace_status_dist[a.canonical_trace_status] += 1

        if not result.trade_actions:
            continue

        out_path = F5_DIR / f"bri_{env_path.stem}_actions.json"
        # Merge with any prior actions in the same file (idempotent reruns)
        prior_actions: List[Dict[str, Any]] = []
        if out_path.exists():
            try:
                with open(out_path, encoding="utf-8") as f:
                    prior_actions = json.load(f).get("actions", [])
            except (OSError, json.JSONDecodeError):
                prior_actions = []

        output_data = {
            "source_file": str(env_path),
            "extracted_at": datetime.now().isoformat(),
            "model": "canonical-programmatic-bri",
            "actions": prior_actions
            + [a.model_dump(mode="json") for a in result.trade_actions],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        written_files.append(str(out_path))
        total_actions += len(result.trade_actions)

        for a in result.trade_actions:
            repo.index_trade_action(a, str(out_path))
            indexed += 1

    print("\n== execute report ==")
    print(f"F4 action_hint distribution: {dict(action_hint_dist)}")
    print(f"F5 trade_actions produced: {total_actions}")
    print(f"F5 canonical_trace_status distribution: {dict(trace_status_dist)}")
    print(f"F5 rejected: {sum(rejected_reasons.values())}")
    for reason, n in rejected_reasons.most_common():
        print(f"  rejected[{n}]: {reason}")
    print(f"files written: {len(written_files)}")
    for p in written_files:
        print(f"  {p}")
    print(f"indexed actions: {indexed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Run F4/F5 and write outputs (default: dry-run plan only)",
    )
    args = parser.parse_args()
    asyncio.run(drive(execute=args.execute))


if __name__ == "__main__":
    main()
