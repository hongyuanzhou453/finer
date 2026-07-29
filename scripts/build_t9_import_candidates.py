#!/usr/bin/env python3
"""生成 T9 池的 F0 导入候选清单（只读）。

C10 金丝雀的选批必须**显式按 T9 池取**，不能用「目录序下一批」的隐式口径——
否则 1,000 份的构成不可控，吞吐/成本外推失真。依据（2026-07-25 实测）：

  T3 池 6,631 份中 6,441 已在 F0（97.1%）
  T9 池 18,747 份中 仅 13 在 F0（0.07%）
  T3 ∩ T9 = 0  ← 两个烧录产物覆盖的研报集合完全不相交

即现有 F0 语料实质就是 T3 池，行业/宏观研报一份都没进过流水线。所以「下一批
未建档研报」实际就是从 T9 池取，金丝雀天然是 T9 池的金丝雀，产出 t9i_ sector
intent（走 sector_transmission_adapter）而非 bri_。

输出一份 JSONL 清单（filepath + 元数据 + 是否存在于磁盘），供导入器按清单取批，
使批次可复现、可审计。**不导入任何东西**。

    python scripts/build_t9_import_candidates.py --limit 1000 --out data/_candidates/t9_canary.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.ops.mount_health import broker_volume_available  # noqa: E402

DEFAULT_T9_DIR = Path(
    "/Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/products/t9_sector_deep"
)


def _iter_t9_rows(t9_dir: Path) -> Iterator[dict]:
    for name in ("burn_t9.jsonl", "burn_t9_r2.jsonl"):
        path = t9_dir / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("validation") or {}).get("json_ok"):
                    yield row


def _imported_source_paths(data_root: Path) -> Set[str]:
    """已建档的 source_filepath 集合（F0 真值）。"""
    seen: Set[str] = set()
    broker_dir = data_root / "F0_intake" / "broker"
    if not broker_dir.is_dir():
        return seen
    for path in broker_dir.glob("*.json"):
        if ".receipt" in path.name:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = (record.get("metadata") or {}).get("source_filepath")
        if source:
            seen.add(source)
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t9-dir", type=Path, default=DEFAULT_T9_DIR)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--limit", type=int, default=None,
                        help="取 N 份（金丝雀批量；省略则输出全部候选）")
    parser.add_argument(
        "--year", action="append", default=None,
        help="只取该年份目录下的研报（可重复，如 --year 2025）。"
             "分段放量用：2025 段图片型 PDF 仅约 1.9%（几乎零 OCR 成本），"
             "2026 段约 35.5%（需先决策是否配 OCR）。",
    )
    parser.add_argument(
        "--sample", choices=["even", "head"], default="even",
        help="选批方式。even（默认）= 按 filepath 排序后等距抽样，保持券商/期间构成"
             "与候选池一致，金丝雀才能外推全量；head = 取前 N 份（构成会偏向排序靠前的"
             "目录，仅用于快速冒烟）。两者都确定性可复现。",
    )
    parser.add_argument("--out", type=Path, default=None,
                        help="清单落盘路径（省略则只打印统计）")
    args = parser.parse_args()

    if not broker_volume_available():
        print("ERROR: broker source volume (NAMEZY) 未挂载 — 中止。")
        return 2

    imported = _imported_source_paths(args.data_root.resolve())
    print(f"F0 已建档 source_filepath: {len(imported)}")

    seen: Dict[str, dict] = {}
    stats: Counter = Counter()
    for row in _iter_t9_rows(args.t9_dir):
        filepath = row.get("filepath")
        stats["t9_rows"] += 1
        if not filepath:
            stats["no_filepath"] += 1
            continue
        if filepath in imported:
            stats["already_imported"] += 1
            continue
        if filepath in seen:
            stats["duplicate_row"] += 1
            continue
        if args.year and not any(f"/{y}年/" in filepath for y in args.year):
            stats["year_filtered_out"] += 1
            continue
        seen[filepath] = row

    candidates = []
    for filepath, row in sorted(seen.items()):
        exists = Path(filepath).exists()
        stats["on_disk" if exists else "MISSING_ON_DISK"] += 1
        if not exists:
            continue
        extraction = row.get("extraction") or {}
        # 字段集必须满足 finer.ingestion.broker_research_intake 的 meta 契约：
        # filepath 必填，其余走 _META_PASSTHROUGH（filename/broker/date/
        # company_name/stock_code/... ），否则 F0 记录会缺元数据。
        candidates.append({
            "filepath": filepath,
            "filename": row.get("filename") or Path(filepath).name,
            "broker": row.get("broker"),
            "date": row.get("date"),
            "company_name": row.get("company_name") or None,
            "stock_code": row.get("stock_code") or None,
            "topic": extraction.get("industry_or_theme"),
            "is_industry_report": True,  # T9 池按定义是行业/宏观研报
            # 以下非 intake 契约字段，仅供 D1 适配器与批次审计使用
            "t9_industry_or_theme": extraction.get("industry_or_theme"),
            "t9_cycle_view": extraction.get("cycle_view"),
            "t9_n_chains": (row.get("validation") or {}).get("n_chains"),
        })

    print("\n候选池统计:")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    print(f"  candidates(on disk, deduped): {len(candidates)}")

    brokers = Counter(c["broker"] for c in candidates)
    print("\n候选池券商构成 (top 12):")
    for broker, count in brokers.most_common(12):
        print(f"  {count:>5}  {broker}")

    if args.limit and args.limit < len(candidates):
        if args.sample == "even":
            # 等距抽样：stride 取整后按下标取，保持券商/期间构成与池一致。
            stride = len(candidates) / args.limit
            batch = [candidates[int(i * stride)] for i in range(args.limit)]
        else:
            batch = candidates[: args.limit]
    else:
        batch = candidates

    if args.limit:
        print(f"\n本批 {len(batch)} 份（--sample {args.sample}，确定性可复现）")
        batch_mix = Counter(c["broker"] for c in batch)
        print(f"  {'券商':<16}{'本批':>7}{'本批占比':>9}{'池占比':>9}{'偏离':>8}")
        for broker, count in batch_mix.most_common(10):
            share = count / len(batch) * 100
            pool_share = brokers[broker] / len(candidates) * 100
            print(f"  {str(broker):<16}{count:>7}{share:>8.1f}%{pool_share:>8.1f}%"
                  f"{share - pool_share:>+7.1f}pp")
        # 构成保真度：总变差距离（越小越像总体）
        tvd = sum(
            abs(batch_mix.get(b, 0) / len(batch) - brokers[b] / len(candidates))
            for b in brokers
        ) / 2
        print(f"  券商构成总变差距离 vs 候选池: {tvd * 100:.2f}%（越小越有代表性）")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for item in batch:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"\nwrote {args.out}  ({len(batch)} 份)")
    else:
        print("\n加 --out 落盘清单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
