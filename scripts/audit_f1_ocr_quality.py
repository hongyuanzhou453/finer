#!/usr/bin/env python
"""F1 OCR quality audit — surface SILENT failures in standardized envelopes.

The standardization pipeline marks an envelope "ok / canonical=True" as long as
some text comes back. But MiMo can return a content-safety refusal message, or
fabricate placeholder image URLs for charts — both pass as "successful OCR" and
mix into the corpus undetected. This audit classifies every envelope:

    refusal        — API content-safety / error message captured as OCR text
                     (whole image lost if it dominates a short envelope)
    hallucination  — fabricated placeholder URLs (via.placeholder.com etc.)
    fallback       — vision-failure placeholder block (429 / unreachable)
    thin           — clean but suspiciously little text (possible partial OCR)
    clean          — passes all machine-checkable gates

It does NOT measure character/number accuracy on "clean" envelopes — that needs
a human-checked gold set (silent transcription errors can't be regex-detected).

    python scripts/audit_f1_ocr_quality.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Single source of truth for the gate patterns lives in the adapter-side module,
# so the audit and the inline adapter gate can never drift apart.
from finer.parsing.ocr_quality import (  # noqa: E402
    HALLUCINATION_PATTERNS,
    REFUSAL_DOMINATES,
    REFUSAL_PATTERNS,
    THIN_CHARS,
)

_REFUSAL_RE = [re.compile(p, re.I) for p in REFUSAL_PATTERNS]
_HALLU_RE = [re.compile(p, re.I) for p in HALLUCINATION_PATTERNS]


def envelope_text(env: dict) -> str:
    return "\n".join((b.get("text") or "") for b in env.get("blocks", []))


def has_fallback_flag(env: dict) -> bool:
    for b in env.get("blocks", []):
        qf = ((b.get("quality") or {}).get("quality_flags")) or []
        if "no_vision_transcript" in qf or "fallback_generated" in qf:
            return True
    return False


def classify(env: dict) -> list[str]:
    txt = envelope_text(env)
    tags: list[str] = []

    if has_fallback_flag(env):
        tags.append("fallback")

    refusal_hit = any(r.search(txt) for r in _REFUSAL_RE)
    if refusal_hit:
        tags.append("refusal" if len(txt) < REFUSAL_DOMINATES else "refusal_partial")

    if any(r.search(txt) for r in _HALLU_RE):
        tags.append("hallucination")

    if not tags and len(txt.strip()) < THIN_CHARS:
        tags.append("thin")

    return tags or ["clean"]


def main() -> None:
    data_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    d = data_root / "F1_standardized"
    files = sorted(d.glob("local_*/content_envelope.json"))
    if not files:
        print(f"no envelopes under {d}", file=sys.stderr)
        raise SystemExit(2)

    counts: dict[str, int] = {}
    worklist: list[dict] = []
    for f in files:
        try:
            env = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            counts["unreadable_json"] = counts.get("unreadable_json", 0) + 1
            continue
        tags = classify(env)
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
        if any(t in ("refusal", "refusal_partial", "hallucination", "fallback") for t in tags):
            worklist.append(
                {
                    "content_id": f.parent.name,
                    "raw_path": env.get("raw_path"),
                    "tags": tags,
                    "chars": len(envelope_text(env)),
                }
            )

    total = len(files)
    hard_fail = {c["content_id"] for c in worklist}
    clean = counts.get("clean", 0)
    usable_rate = 100.0 * (total - len(hard_fail)) / total

    print("=== F1 OCR Quality Audit ===")
    print(f"total envelopes: {total}")
    print(f"machine-clean:   {clean} ({100.0*clean/total:.1f}%)")
    print(f"usable (excl. hard failures): {total - len(hard_fail)}/{total} ({usable_rate:.1f}%)")
    print()
    print("by tag:")
    for tag in ("refusal", "refusal_partial", "hallucination", "fallback", "thin", "clean", "unreadable_json"):
        if tag in counts:
            print(f"  {tag:16s} {counts[tag]}")
    print()
    print(f"=== reprocess worklist ({len(worklist)}) ===")
    for c in sorted(worklist, key=lambda x: x["tags"]):
        print(f"  {','.join(c['tags']):22s} {c['chars']:5d}字  {c['content_id']}  {c['raw_path']}")

    out = data_root / "F1_standardized" / "_backfill_runs" / "ocr_quality_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"counts": counts, "worklist": worklist, "usable_rate": usable_rate},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nreport → {out}")
    print(
        "\nNOTE: this audits machine-detectable failures only. Character/number "
        "accuracy on 'clean' envelopes is NOT measured here — that needs a "
        "human-checked gold set."
    )


if __name__ == "__main__":
    main()
