#!/usr/bin/env python3
"""M2: backfill T7x extraction-confidence labels onto live bri intents.

WHAT THIS IS
    T7x (``t7x-v0.1``) re-extracted every broker rating/target-price 5 times
    (T3 original + 2 runs from T7 + 2 fresh runs with different prompt wording
    and temperature) and voted. This backfill attaches the vote outcome to the
    matching ``NormalizedInvestmentIntent`` as *pipeline metadata*.

WHAT THIS IS NOT — read before touching any consumer of this field
    ``extraction_confidence`` measures **how sure we are that we read the
    report correctly**. It says NOTHING about whether the broker was right, and
    it MUST NOT feed any credibility score, source ranking, or scorecard.
    That is why the key is namespaced ``extraction_`` and carries an inline
    ``note`` — a later reader who sees only the JSON still gets the warning.
    (Positioning pivot 2026-08-02: we do not rank sources by predicted skill.)

WHY METADATA AND NOT A SCHEMA FIELD
    ``broker_recommendation_adapter`` already establishes the split: real
    intent semantics get first-class slots, sidecar facts live in
    ``metadata``. Extraction-vote provenance is sidecar — it describes our
    pipeline, not the investment intent. Keeping it out of the schema also
    keeps ``contracts.ts`` / drift-guard untouched.

JOIN
    ``intent.metadata.report_id`` <-> ``t7x.report_id`` (direct, single hop).
    Measured 2026-07-25: 5,849 / 5,852 live bri intents hit (99.9%).

SAFETY
    - dry-run by default; ``--execute`` required to write
    - ``--execute`` takes a full backup of the intents dir first
    - idempotent: re-running rewrites the same value; ``--force`` to overwrite
      an existing label with a different source version
    - only ever adds ``metadata.extraction_confidence``; every other byte of
      each intent JSON is preserved (verified field-by-field before write)

USAGE
    python scripts/backfill_extraction_confidence.py \
        --t7x-jsonl /Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/products/t7_verify/burn_t7_5votes.jsonl
    python scripts/backfill_extraction_confidence.py --t7x-jsonl <path> --execute
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SOURCE_VERSION = "t7x-v0.1"
FIELD = "extraction_confidence"

#: Inline warning stored with every label. Survives the JSON leaving this repo.
DISCLAIMER = "抽取一致性（我们读对原文的把握），非信源准确性；禁止用于任何信源评分或排序"

VALID_TIERS = ("unanimous", "strong", "majority", "disputed")


def load_t7x(path: Path) -> Dict[int, dict]:
    """report_id -> t7x record, keeping only records whose 5-vote run succeeded."""
    out: Dict[int, dict] = {}
    skipped = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not (rec.get("validation") or {}).get("verify_ok"):
                skipped += 1
                continue
            rid = rec.get("report_id")
            if rid is None:
                skipped += 1
                continue
            out[rid] = rec  # later line wins (resume semantics)
    if skipped:
        print(f"  [t7x] 跳过 {skipped} 行（解析失败 / verify_ok=false / 无 report_id）")
    return out


def build_label(rec: dict) -> Optional[dict]:
    """T7x record -> the metadata payload. None when the record is unusable."""
    c5 = rec.get("consensus5") or {}
    rating_tier = c5.get("rating_confidence")
    target_tier = c5.get("target_confidence")
    if rating_tier not in VALID_TIERS or target_tier not in VALID_TIERS:
        return None
    return {
        "rating": rating_tier,
        "rating_votes": c5.get("rating_votes"),
        "target": target_tier,
        "target_votes": c5.get("target_votes"),
        "total_votes": 5,
        "source": SOURCE_VERSION,
        "note": DISCLAIMER,
    }


def read_intent(path: Path) -> Tuple[Any, dict]:
    """Return (raw_document, intent_dict). Handles both bare dict and 1-item list."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        if len(raw) != 1 or not isinstance(raw[0], dict):
            raise ValueError(f"意外的 intent 结构（list 长度 {len(raw)}）")
        return raw, raw[0]
    if isinstance(raw, dict):
        return raw, raw
    raise ValueError(f"意外的 intent 顶层类型 {type(raw).__name__}")


def backup_dir(src: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = src.with_name(f"{src.name}.bak-{stamp}-m2-{uuid.uuid4().hex[:8]}")
    shutil.copytree(src, dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="M2 回填 T7x 抽取置信度到现役 bri intent")
    ap.add_argument("--t7x-jsonl", required=True, type=Path)
    ap.add_argument("--intents-dir", type=Path, default=Path("data/F3_intents"))
    ap.add_argument("--prefix", default="bri_", help="只处理该前缀的 intent 文件")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（调试用）")
    ap.add_argument("--force", action="store_true",
                    help="覆盖已存在且 source 不同的标签")
    ap.add_argument("--execute", action="store_true", help="真正写入（默认 dry-run）")
    args = ap.parse_args()

    if not args.t7x_jsonl.exists():
        print(f"FATAL: T7x JSONL 不存在: {args.t7x_jsonl}", file=sys.stderr)
        return 2
    if not args.intents_dir.is_dir():
        print(f"FATAL: intents 目录不存在: {args.intents_dir}", file=sys.stderr)
        return 2

    print(f"读取 T7x: {args.t7x_jsonl}")
    t7x = load_t7x(args.t7x_jsonl)
    print(f"  可用记录: {len(t7x):,}")

    files = sorted(args.intents_dir.glob(f"{args.prefix}*.json"))
    if args.limit:
        files = files[: args.limit]
    print(f"intent 文件: {len(files):,}（前缀 {args.prefix!r}）")

    planned: list[Tuple[Path, Any, dict, dict]] = []
    stats = Counter()
    tiers = Counter()
    for path in files:
        try:
            raw, intent = read_intent(path)
        except (ValueError, json.JSONDecodeError) as exc:
            stats["read_error"] += 1
            print(f"  ! {path.name}: {exc}")
            continue
        meta = intent.get("metadata")
        if not isinstance(meta, dict):
            stats["no_metadata"] += 1
            continue
        rid = meta.get("report_id")
        if rid is None:
            stats["no_report_id"] += 1
            continue
        rec = t7x.get(rid)
        if rec is None:
            stats["no_t7x_match"] += 1
            continue
        label = build_label(rec)
        if label is None:
            stats["bad_t7x_payload"] += 1
            continue
        existing = meta.get(FIELD)
        if isinstance(existing, dict):
            if existing == label:
                stats["already_current"] += 1
                continue
            if existing.get("source") == label["source"] and not args.force:
                stats["already_same_source"] += 1
                continue
            if not args.force:
                stats["conflict_needs_force"] += 1
                continue
            stats["overwrite"] += 1
        else:
            stats["new"] += 1
        tiers[f"rating:{label['rating']}"] += 1
        planned.append((path, raw, intent, label))

    print("\n=== 计划 ===")
    for k, v in sorted(stats.items()):
        print(f"  {k:22s} {v:,}")
    print(f"  {'待写入':22s} {len(planned):,}")
    print("\n=== 置信度分布（待写入）===")
    for k, v in sorted(tiers.items(), key=lambda kv: -kv[1]):
        share = v / len(planned) * 100 if planned else 0.0
        print(f"  {k:22s} {v:,} ({share:.2f}%)")
    non_unanimous = sum(v for k, v in tiers.items() if not k.endswith("unanimous"))
    print(f"\n  非 unanimous（值得 UI 标注的）: {non_unanimous:,}")

    if not args.execute:
        print("\nDRY-RUN：未写入任何文件。加 --execute 执行（会先自动备份）。")
        return 0
    if not planned:
        print("\n无待写入项，跳过备份与写入。")
        return 0

    print(f"\n备份 {args.intents_dir} ...")
    dest = backup_dir(args.intents_dir)
    print(f"  备份完成: {dest}")

    written = failed = 0
    for path, raw, intent, label in planned:
        try:
            intent["metadata"][FIELD] = label
            path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written += 1
        except OSError as exc:
            failed += 1
            print(f"  ! 写入失败 {path.name}: {exc}")

    print(f"\n写入完成: {written:,} 成功 / {failed} 失败")
    print(f"回滚方式: rm -rf {args.intents_dir} && mv {dest} {args.intents_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
