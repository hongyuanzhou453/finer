"""C9 Phase 3 — evidence-focused re-anchor + in-place evidence fix (plan A).

Per broker envelope that has bri intents:
  1. re-anchor the F1 envelope with the phase-1 fixes → F2 (entity/temporal
     anchors + evidence spans);
  2. (--execute) overwrite data/F2_anchored/{content_id}.json so the additive
     drive later sees the new anchors;
  3. (--execute) write data/F2_evidence/{span_id}.json sidecars for the
     envelope's spans;
  4. (--execute) for each EXISTING bri action in this envelope, set
     evidence_span_ids to the re-anchored envelope's span ids and rewrite the F5
     file — trade_action_id / policy_id / intent_id UNCHANGED (preserves the
     1,099 settled results).

This closes the C8 evidence gap for existing actions in place. The additive
TW/JP intents are a SEPARATE follow-up (drive_broker_recommendations --execute
after this re-anchor). International unlock is out of scope (needs anchor-
detection work — see the dry-run finding).

DELETION/MUTATION IS A RED LINE. Dry-run by default. --execute backs up
data/F2_anchored and data/F5_executed first (named/protected snapshots).
Concurrent re-anchor (ThreadPool); per-envelope file writes never overlap.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.entity_anchoring import build_f2_deterministic_envelope  # noqa: E402
from finer.schemas.content import ContentRecord  # noqa: E402

DATA = REPO_ROOT / "data"
F1, F2A, F2E, F3, F5 = (
    DATA / "F1_standardized", DATA / "F2_anchored", DATA / "F2_evidence",
    DATA / "F3_intents", DATA / "F5_executed",
)


def _f0_record(cid: str) -> Optional[ContentRecord]:
    p = DATA / "F0_intake" / "broker" / f"{cid}.json"
    if not p.exists():
        return None
    try:
        return ContentRecord.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _reanchor(cid: str) -> dict:
    env = json.loads((F1 / cid / "content_envelope.json").read_text(encoding="utf-8"))
    rec = _f0_record(cid)
    f2 = build_f2_deterministic_envelope(env, f0_record=(rec.model_dump(mode="json") if rec else None))
    return f2.model_dump(mode="json")


def _env_spans(f2_doc: dict) -> List[dict]:
    return [s for b in (f2_doc.get("blocks") or []) for s in (b.get("evidence_spans") or [])]


def _target_terms(action: dict) -> List[str]:
    t = action.get("target") or {}
    terms = [t.get("ticker"), t.get("ticker_normalized"), t.get("company_name")]
    return [str(x).strip().lower() for x in terms if x and str(x).strip()]


def _relevant_span_ids(action: dict, spans: List[dict]) -> List[str]:
    """Spans whose text mentions the action's target (ticker / normalized / name).

    This replaces the original over-broad "all envelope spans" evidence with a
    grounded subset (C8 quality note). Fallbacks keep evidence non-empty:
    entity-type spans, else all spans.
    """
    terms = _target_terms(action)
    if terms:
        hit = [s for s in spans if any(term in (s.get("text") or "").lower() for term in terms)]
        if hit:
            return [s["evidence_span_id"] for s in hit if s.get("evidence_span_id")]
    entity = [s for s in spans if s.get("span_type") == "entity" and s.get("evidence_span_id")]
    if entity:
        return [s["evidence_span_id"] for s in entity]
    return [s["evidence_span_id"] for s in spans if s.get("evidence_span_id")]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="C9 evidence-focused re-anchor + in-place evidence fix (dry-run default).")
    ap.add_argument("--limit", type=int, default=None, help="max envelopes (testing/sampling)")
    ap.add_argument("--workers", type=int, default=8, help="concurrent re-anchor workers")
    ap.add_argument("--execute", action="store_true", help="apply (backs up F2_anchored + F5_executed first)")
    args = ap.parse_args(argv)

    # content_id -> F5 file + existing actions
    cid_actions: Dict[str, List[dict]] = defaultdict(list)
    cid_f5file: Dict[str, str] = {}
    for fp in glob.glob(str(F5 / "bri_*_actions.json")):
        stem = Path(fp).name[len("bri_"):-len("_actions.json")]  # content_id
        doc = json.load(open(fp))
        acts = doc.get("actions", [])
        if acts:
            cid_actions[stem] = acts
            cid_f5file[stem] = fp

    # content_ids with a bri intent (actioned or not) AND an F1 envelope on disk
    eid_by_cid = {}  # not needed; intents carry envelope_id, F5 stem is content_id
    cids_with_intent = set(cid_actions)  # existing-action envelopes (the in-place targets)
    # (additive no_anchor envelopes are handled by the follow-up drive; here we
    #  re-anchor + fix evidence for the existing-action envelopes.)
    cids = sorted(c for c in cids_with_intent if (F1 / c / "content_envelope.json").exists())
    if args.limit is not None:
        cids = cids[: args.limit]

    print(f"[{'execute' if args.execute else 'dry-run'}] C9 evidence re-anchor  existing-action envelopes={len(cids)}  workers={args.workers}")

    backups = {}
    if args.execute:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tag = f"{stamp}-c9-reanchor-{uuid.uuid4().hex[:8]}"
        for name, src in (("F2_anchored", F2A), ("F5_executed", F5)):
            if src.exists():
                dst = DATA / f"{name}.bak-{tag}"
                shutil.copytree(src, dst)
                backups[name] = str(dst)
        F2E.mkdir(parents=True, exist_ok=True)
        for n, p in backups.items():
            print(f"  backup {n} -> {p}")

    lock = Lock()
    stats = {"envelopes": 0, "spans": 0, "actions_updated": 0, "failed": 0, "no_spans": 0, "empty_evidence": 0}

    def process(cid: str) -> None:
        try:
            f2 = _reanchor(cid)
        except Exception as exc:  # noqa: BLE001
            with lock:
                stats["failed"] += 1
            print(f"  skip {cid}: {type(exc).__name__}: {exc}")
            return
        spans = _env_spans(f2)
        span_by_id = {s["evidence_span_id"]: s for s in spans if s.get("evidence_span_id")}
        actions = cid_actions.get(cid, [])

        # per-action grounded evidence subset; sidecars only for referenced spans
        per_action_ids = {a.get("trade_action_id"): _relevant_span_ids(a, spans) for a in actions}
        referenced = sorted({sid for ids in per_action_ids.values() for sid in ids})
        empty = sum(1 for a in actions if not per_action_ids.get(a.get("trade_action_id")))
        with lock:
            stats["envelopes"] += 1
            stats["spans"] += len(referenced)
            stats["empty_evidence"] += empty
            if not spans:
                stats["no_spans"] += 1
        if not args.execute:
            return
        # 2) overwrite F2 envelope
        (F2A / f"{cid}.json").write_text(json.dumps(f2, ensure_ascii=False, indent=2), encoding="utf-8")
        # 3) write sidecars only for referenced spans
        for sid in referenced:
            (F2E / f"{sid}.json").write_text(json.dumps(span_by_id[sid], ensure_ascii=False, indent=2), encoding="utf-8")
        # 4) in-place update existing actions' evidence_span_ids (preserve ids)
        if actions and cid in cid_f5file:
            fp = cid_f5file[cid]
            doc = json.load(open(fp))
            for a in doc.get("actions", []):
                a["evidence_span_ids"] = list(per_action_ids.get(a.get("trade_action_id"), []))
            Path(fp).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            with lock:
                stats["actions_updated"] += len(doc.get("actions", []))

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(process, c) for c in cids]
        done = 0
        for _ in as_completed(futs):
            done += 1
            if done % 200 == 0:
                print(f"  ... {done}/{len(cids)}")

    avg = stats["spans"] / max(stats["envelopes"], 1)
    print("\n=== RESULT ===")
    print(f"envelopes re-anchored: {stats['envelopes']}  failed: {stats['failed']}  no-spans: {stats['no_spans']}")
    print(f"grounded evidence spans referenced (→ sidecars): {stats['spans']}  (avg {avg:.1f}/env)")
    print(f"actions with EMPTY grounded evidence (fallback used / weak): {stats['empty_evidence']}")
    if args.execute:
        print(f"existing actions evidence updated: {stats['actions_updated']}")
        for n, p in backups.items():
            print(f"backup {n}: {p}")
    else:
        print(f"dry-run: nothing written. Would write ~{stats['spans']} sidecars + update {sum(len(v) for v in cid_actions.values())} actions.")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
