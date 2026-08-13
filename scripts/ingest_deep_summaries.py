#!/usr/bin/env python3
"""M3: ingest T8 deep summaries into the repo as per-report sidecars.

WHAT
    T8 (``t8-v0.1``) generated 1,500-2,500 character structured deep summaries
    of broker research reports (核心观点 / 投资逻辑链 / 关键数据明细 / 与共识差异 /
    时间线与催化剂 / 风险提示 / 结论倾向). This script copies the ones that pass
    validation into ``data/deep_summaries/{report_id}.json`` so the audit
    assembler can attach them to a trace without reading the external volume.

WHY report_id AND NOT content_id
    ``intent.metadata.report_id`` is the join key already proven by M2
    (99.9% hit on live bri intents). Keying the sidecar by the same id keeps
    one join for both features. The external corpus id is stable; content_id
    would add a hop with nothing gained.

WHAT THIS IS NOT
    A deep summary is **LLM-generated from the report**, not the broker's own
    text, and not a recommendation. Every consumer must label it as such and
    date it. It carries the model name and burn date for exactly that reason.

COVERAGE HONESTY
    Coverage is partial and unevenly distributed by year (the burn processed
    the 2026 pool ahead of 2025). Consumers MUST show "未生成深摘要" for a miss
    rather than silently falling back to the short T5 summary, and MUST NOT
    sort or filter records by whether a summary exists — that would let a
    coverage artifact masquerade as a quality signal.

USAGE
    python scripts/ingest_deep_summaries.py --t8-dir <burn_rescue>/products/t8_deep_summary
    python scripts/ingest_deep_summaries.py --t8-dir <dir> --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable

SCHEMA_VERSION = "deep_summary-v1"
SOURCE_SCHEMA = "t8-v0.1"

#: The eight sections the T8 prompt asks for. A summary missing any of the four
#: load-bearing ones is treated as malformed and skipped (same gate the burn used).
REQUIRED_SECTIONS = ("## 核心观点", "## 投资逻辑链", "## 关键数据明细", "## 风险提示")

DISCLAIMER = (
    "本摘要由 LLM 从研报原文生成，非券商原文，亦非投资建议；"
    "数字以研报原文为准（图表类数据为已知弱项）"
)


def iter_t8_records(t8_dir: Path) -> Iterable[dict]:
    for path in sorted(t8_dir.glob("burn_t8*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def build_sidecar(rec: dict) -> Dict[str, Any] | None:
    """T8 record -> sidecar payload, or None when it fails the quality gate."""
    if not (rec.get("validation") or {}).get("summary_ok"):
        return None
    summary = (rec.get("summary") or "").strip()
    if not summary:
        return None
    missing = [s for s in REQUIRED_SECTIONS if s not in summary]
    if missing:
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": rec.get("report_id"),
        "summary": summary,
        "n_chars": len(summary),
        "broker": rec.get("broker"),
        "report_date": rec.get("date"),
        "stock_code": rec.get("stock_code"),
        "company_name": rec.get("company_name"),
        "filename": rec.get("filename"),
        "source_schema": rec.get("schema_version") or SOURCE_SCHEMA,
        "generated_by": rec.get("model") or "mimo-v2.5",
        "slice_chars": rec.get("slice_chars"),
        "text_length": rec.get("text_length"),
        "disclaimer": DISCLAIMER,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="M3 深摘要落地为 per-report sidecar")
    ap.add_argument("--t8-dir", required=True, type=Path,
                    help="T8 产物目录（含 burn_t8*.jsonl）")
    ap.add_argument("--out-dir", type=Path, default=Path("data/deep_summaries"))
    ap.add_argument("--execute", action="store_true", help="真正写入（默认 dry-run）")
    args = ap.parse_args()

    if not args.t8_dir.is_dir():
        print(f"FATAL: T8 目录不存在: {args.t8_dir}", file=sys.stderr)
        return 2

    stats = Counter()
    payloads: Dict[int, Dict[str, Any]] = {}
    for rec in iter_t8_records(args.t8_dir):
        rid = rec.get("report_id")
        if rid is None:
            stats["no_report_id"] += 1
            continue
        payload = build_sidecar(rec)
        if payload is None:
            stats["failed_gate"] += 1
            continue
        # later line wins: resume semantics mean a re-burn supersedes the old one
        if rid in payloads:
            stats["superseded"] += 1
        payloads[rid] = payload
        stats["accepted"] += 1

    chars = sum(p["n_chars"] for p in payloads.values())
    print("=== 计划 ===")
    for k, v in sorted(stats.items()):
        print(f"  {k:16s} {v:,}")
    print(f"  {'去重后篇数':16s} {len(payloads):,}")
    print(f"  {'总字符':16s} {chars:,}（≈ {chars * 3 / 1024 / 1024:.1f} MB）")
    by_year = Counter(str(p.get("report_date") or "")[:4] for p in payloads.values())
    print(f"  按年分布: {dict(sorted(by_year.items()))}")

    if not args.execute:
        print("\nDRY-RUN：未写入。加 --execute 执行。")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for rid, payload in payloads.items():
        (args.out_dir / f"{rid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        written += 1
    index = {
        "schema_version": SCHEMA_VERSION,
        "n_summaries": written,
        "report_ids": sorted(payloads.keys()),
        "note": DISCLAIMER,
    }
    (args.out_dir / "_index.json").write_text(
        json.dumps(index, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\n写入 {written:,} 个 sidecar + _index.json → {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
