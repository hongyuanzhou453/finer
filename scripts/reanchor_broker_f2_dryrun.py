"""C9 Phase 2/3 — broker F2 re-anchor DRY-RUN measurement (read-only).

Re-anchors a sample of broker F1 envelopes with the phase-1 ticker/stoplist
fixes in place and measures the REAL delta (not the intent-side upper bound):

  * additive: of the no_anchor_match intents in the sampled envelopes, how many
    now match a re-anchored envelope anchor (the envelope side must actually
    detect+resolve the ticker, not just the intent-side normalize);
  * evidence: how many evidence_spans the re-anchor produces (→ sidecar volume);
  * existing: whether the re-anchored anchors still cover the existing actions'
    targets (or drop the 7 rating collisions).

READ-ONLY — writes nothing. Serial (re-anchor is ~2.5s/envelope). Sample with
--limit; --seed picks a deterministic slice for reproducibility.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.entity_anchoring import build_f2_deterministic_envelope  # noqa: E402
from finer.enrichment.ticker_normalization import normalize_broker_ticker  # noqa: E402
from finer.schemas.content import ContentRecord  # noqa: E402

DATA = REPO_ROOT / "data"


def _bridge_matches(target_symbol: Optional[str], anchor_symbols: Set[str]) -> bool:
    """Mirror drive_broker_recommendations.bridge_target_symbol (no fabrication)."""
    if not target_symbol:
        return False
    if target_symbol in anchor_symbols:
        return True
    nt = normalize_broker_ticker(target_symbol)
    return bool(nt and nt.symbol in anchor_symbols)


def _load_f0_record(cid: str) -> Optional[ContentRecord]:
    p = DATA / "F0_intake" / "broker" / f"{cid}.json"
    if not p.exists():
        return None
    try:
        return ContentRecord.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _reanchor_symbols(cid: str) -> tuple[Set[str], int]:
    """Re-anchor one broker envelope; return (new resolved_symbols, evidence_span_count)."""
    f1 = DATA / "F1_standardized" / cid / "content_envelope.json"
    env = json.loads(f1.read_text(encoding="utf-8"))
    rec = _load_f0_record(cid)
    f2 = build_f2_deterministic_envelope(env, f0_record=(rec.model_dump(mode="json") if rec else None))
    d = f2.model_dump(mode="json")
    syms = {a.get("resolved_symbol") for a in (d.get("entity_anchors") or []) if a.get("resolved_symbol")}
    spans = sum(len(b.get("evidence_spans") or []) for b in (d.get("blocks") or []))
    return syms, spans


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="C9 broker F2 re-anchor dry-run measurement (read-only).")
    ap.add_argument("--limit", type=int, default=120, help="envelopes to sample (default 120)")
    ap.add_argument("--seed", type=int, default=0, help="deterministic slice offset")
    args = ap.parse_args(argv)

    # existing-actioned intents + their current targets, grouped by envelope
    actioned_targets: Dict[str, str] = {}
    for fp in glob.glob(str(DATA / "F5_executed" / "bri_*_actions.json")):
        for a in json.load(open(fp)).get("actions", []):
            iid = a.get("intent_id")
            if iid:
                actioned_targets[iid] = (a.get("target") or {}).get("ticker_normalized")

    # all bri intents grouped by envelope_id; split actioned vs no_anchor candidates
    env_intents: Dict[str, List[dict]] = defaultdict(list)
    for f3 in glob.glob(str(DATA / "F3_intents" / "bri_*.json")):
        it = json.load(open(f3))
        if it.get("envelope_id"):
            env_intents[it["envelope_id"]].append(it)

    # map envelope_id -> content_id. content_id is the F2 file stem (broker_xxx),
    # which is also the F1 dir name; the internal envelope_id is env_xxx.
    eid2cid: Dict[str, str] = {}
    for p in glob.glob(str(DATA / "F2_anchored" / "broker_*.json")):
        try:
            e = json.load(open(p))
        except Exception:
            continue
        if e.get("envelope_id"):
            eid2cid[e["envelope_id"]] = Path(p).stem

    # envelopes that have at least one no_anchor_match intent (additive candidates)
    candidate_eids = []
    for eid, intents in env_intents.items():
        cid = eid2cid.get(eid)
        if not cid:
            continue
        f1 = DATA / "F1_standardized" / cid / "content_envelope.json"
        if not f1.exists():
            continue
        # any unactioned intent here?
        if any(it["intent_id"] not in actioned_targets for it in intents):
            candidate_eids.append(eid)

    candidate_eids.sort()
    sample = candidate_eids[args.seed : args.seed + args.limit]
    print(f"[dry-run] re-anchor measurement  candidates(env with unactioned intent)={len(candidate_eids)}  sampling={len(sample)}")

    no_anchor_total = 0
    newly_matched = 0
    still_unmatched = 0
    span_counts = []
    existing_covered = 0
    existing_dropped = 0  # existing action whose target no longer anchors (the 7 collisions)
    market_matched = Counter()
    t0 = time.time()

    for i, eid in enumerate(sample, 1):
        cid = eid2cid[eid]
        try:
            new_syms, spans = _reanchor_symbols(cid)
        except Exception as exc:
            print(f"  skip {cid}: {type(exc).__name__}: {exc}")
            continue
        span_counts.append(spans)
        for it in env_intents[eid]:
            iid = it["intent_id"]
            ts = it.get("target_symbol")
            matched = _bridge_matches(ts, new_syms)
            if iid in actioned_targets:
                # existing action: does its target still anchor?
                cur = actioned_targets[iid]
                if matched or (cur and cur in new_syms):
                    existing_covered += 1
                else:
                    existing_dropped += 1
            else:
                no_anchor_total += 1
                if matched:
                    newly_matched += 1
                    nt = normalize_broker_ticker(ts)
                    market_matched[nt.market if nt else "?"] += 1
                else:
                    still_unmatched += 1
        if i % 25 == 0:
            print(f"  ... {i}/{len(sample)} envelopes  ({time.time()-t0:.0f}s)")

    n_env = len(span_counts)
    avg_spans = (sum(span_counts) / n_env) if n_env else 0
    print("\n=== RESULT (sample) ===")
    print(f"envelopes re-anchored: {n_env}   ({time.time()-t0:.0f}s, {(time.time()-t0)/max(n_env,1):.2f}s/env)")
    print(f"ADDITIVE  no_anchor intents in sample: {no_anchor_total}")
    print(f"          newly matched after re-anchor: {newly_matched} ({100*newly_matched/max(no_anchor_total,1):.1f}%)")
    print(f"          still unmatched: {still_unmatched}")
    print(f"          matched by market: {dict(market_matched)}")
    print(f"EXISTING  in-sample existing actions: covered={existing_covered}  dropped(lost anchor)={existing_dropped}")
    print(f"EVIDENCE  avg evidence_spans/envelope: {avg_spans:.1f}  (→ sidecar volume)")
    # extrapolate additive to full candidate set
    if no_anchor_total and n_env:
        rate = newly_matched / no_anchor_total
        # crude: total no_anchor ~1835; extrapolate by match rate
        print(f"\nEXTRAPOLATION (match rate {rate:.1%} × 1835 no_anchor total): ~{int(rate*1835)} new actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
