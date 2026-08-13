#!/usr/bin/env python3
"""M1: run the rating-vs-estimate inconsistency audit over live bri intents.

WHAT IT DOES
    Joins T6 deep-equity extractions (``t6-v0.1``) to live broker intents via
    ``intent.metadata.report_id`` (the M2/M3-proven key) and applies the
    conservative rules in ``finer.credibility.rating_estimate_consistency``.

    Output: ``data/audit/rating_estimate_inconsistency.json`` — the event list
    plus the full skip-reason census, so "why wasn't X reported" is answerable.

MERGE ORDER (r2 wins)
    ``burn_t6_r2.jsonl`` re-extracted the reports where r1 failed the gate or
    produced zero estimates, using a larger slice. When both exist for one
    report_id, r2 supersedes r1.

RED LINES BAKED IN (do not relax without re-reading the module docstring)
    - Counts are publishable; **rates are not** — a rate needs SampleSufficiency
      and a display policy, and would invite exactly the cross-source ranking
      the positioning pivot forbids. This script therefore emits counts only.
    - Never sort brokers by inconsistency count into a leaderboard.
    - `signal_class` stays broker_recommendation; never mixed with KOL rows.

USAGE
    python scripts/detect_rating_estimate_inconsistency.py --t6-dir <burn>/products/t6_deep_equity
    python scripts/detect_rating_estimate_inconsistency.py --t6-dir <dir> --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finer.credibility.rating_estimate_consistency import (  # noqa: E402
    detect_inconsistency,
)

#: r1 先读、r2 后读 —— 同 report_id 后者覆盖前者。
T6_FILES_IN_MERGE_ORDER = ("burn_t6.jsonl", "burn_t6_r2.jsonl")


def load_t6(t6_dir: Path) -> Dict[int, dict]:
    merged: Dict[int, dict] = {}
    for name in T6_FILES_IN_MERGE_ORDER:
        path = t6_dir / name
        if not path.is_file():
            continue
        n = 0
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = rec.get("report_id")
                if rid is None:
                    continue
                merged[rid] = rec
                n += 1
        print(f"  [{name}] {n:,} 行")
    return merged


def iter_bri_intents(intents_dir: Path) -> Iterator[dict]:
    for path in sorted(intents_dir.glob("bri_*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if isinstance(raw, dict):
            yield raw


def main() -> int:
    ap = argparse.ArgumentParser(description="M1 评级—预测口径背离检测")
    ap.add_argument("--t6-dir", required=True, type=Path)
    ap.add_argument("--intents-dir", type=Path, default=Path("data/F3_intents"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/audit/rating_estimate_inconsistency.json"))
    ap.add_argument("--sample", type=int, default=10,
                    help="打印前 N 条命中，供人工核对")
    ap.add_argument("--execute", action="store_true", help="写出报告（默认只打印）")
    args = ap.parse_args()

    if not args.t6_dir.is_dir():
        print(f"FATAL: T6 目录不存在: {args.t6_dir}", file=sys.stderr)
        print("       （T6 产物在外置盘 burn_rescue_20260725/products/t6_deep_equity）",
              file=sys.stderr)
        return 2

    print(f"读取 T6: {args.t6_dir}")
    t6 = load_t6(args.t6_dir)
    print(f"  合并后（r2 优先）: {len(t6):,} 份")

    events = []
    skips: Counter[str] = Counter()
    n_intents = n_paired = 0
    for intent in iter_bri_intents(args.intents_dir):
        n_intents += 1
        rid = (intent.get("metadata") or {}).get("report_id")
        rec = t6.get(rid) if rid is not None else None
        if rec is None:
            skips["no_t6_record"] += 1
            continue
        n_paired += 1
        event, reason = detect_inconsistency(intent, rec)
        if event is not None:
            events.append(event)
        elif reason:
            skips[reason] += 1

    print(f"\nbri intent: {n_intents:,} | 与 T6 配对: {n_paired:,}")
    print(f"**命中背离: {len(events):,}**")
    print("\n=== 排除原因普查（回答「为什么没报出来」）===")
    for reason, n in skips.most_common():
        print(f"  {reason:32s} {n:,}")

    if events:
        by_broker = Counter(e.creator_id for e in events)
        print("\n=== 按信源分布（**计数，非比率，不构成排名**）===")
        for broker, n in by_broker.most_common(10):
            print(f"  {broker:16s} {n:,}")
        print(f"\n=== 前 {min(args.sample, len(events))} 条（供人工核对）===")
        for e in sorted(events, key=lambda x: -x.max_change_pct)[: args.sample]:
            ce = e.conflicting_estimates[0]
            print(f"\n  report_id={e.report_id} {e.creator_id} {e.ticker} {e.report_date}")
            print(f"    评级: {e.rating_current} ({e.rating_direction}/{e.rating_action})")
            print(f"    冲突: {ce.metric} {ce.period} {ce.action} {ce.change_pct:+.1f}%")
            print(f"    引文: {e.estimate_evidence_quotes[0][:90]}")

    if not args.execute:
        print("\nDRY-RUN：未写出报告。加 --execute 写入。")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "schema_version": "rating_estimate_inconsistency-v1",
        "n_intents": n_intents,
        "n_paired": n_paired,
        "n_events": len(events),
        "skips": dict(skips),
        "note": (
            "同一份研报内部「评级方向」与「盈利预测调整方向」相悖的记录。"
            "这是文档自洽性审计，不含任何对信源准确性的判断，"
            "不得用于信源排序或评分。"
        ),
        "events": [asdict(e) for e in events],
    }
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\n已写出 {len(events):,} 条 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
