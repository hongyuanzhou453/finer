#!/usr/bin/env python3
"""按 intent 需要定向补 F2 锚定（只读默认，--execute 才写）。

来历：2026-08-06 跑 2026 段时，t9i 板块 intent 因 ``evidence_not_grounded_in_f2``
全数被拒——新 F1 信封还没过 F2。全量 F2 回填要 32 小时（实测中位件 18 块 /
49,478 字符、单条锚定 8.28s，成本是 O(字符 × 注册表别名)），但真正被需要的
只是这些 intent 指向的那几百个信封。

**按需求而不是按存量驱动**：先从 F3 intent 收集 ``envelope_id``，再只锚定
其中缺 F2 的。全量回填是独立课题，不该挡住一次具体交付。

    python scripts/anchor_f2_for_intents.py --prefix t9i_
    python scripts/anchor_f2_for_intents.py --prefix t9i_ --execute
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.ops.env_bootstrap import load_env_file  # noqa: E402

load_env_file()

_ENVELOPE_ID_RE = re.compile(r'"envelope_id"\s*:\s*"([^"]+)"')


def _needed_envelope_ids(data_root: Path, prefix: str) -> Set[str]:
    ids: Set[str] = set()
    for path in glob.glob(str(data_root / "F3_intents" / f"{prefix}*.json")):
        try:
            intent = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        env_id = intent.get("envelope_id")
        if env_id:
            ids.add(env_id)
    return ids


def _existing_f2_envelope_ids(data_root: Path) -> Set[str]:
    """已锚定的 envelope_id（读文件头，避免全量解析上万个 JSON）。"""
    found: Set[str] = set()
    for path in glob.glob(str(data_root / "F2_anchored" / "*.json")):
        try:
            head = Path(path).read_text(encoding="utf-8")[:600]
        except OSError:
            continue
        match = _ENVELOPE_ID_RE.search(head)
        if match:
            found.add(match.group(1))
    return found


def _f1_index(data_root: Path) -> Dict[str, Path]:
    """envelope_id → F1 信封路径。"""
    index: Dict[str, Path] = {}
    for path in glob.glob(
        str(data_root / "F1_standardized" / "*" / "content_envelope.json")
    ):
        try:
            head = Path(path).read_text(encoding="utf-8")[:600]
        except OSError:
            continue
        match = _ENVELOPE_ID_RE.search(head)
        if match:
            index[match.group(1)] = Path(path)
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--prefix", default="t9i_", help="F3 intent 文件前缀")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    data_root = args.data_root.resolve()

    needed = _needed_envelope_ids(data_root, args.prefix)
    have = _existing_f2_envelope_ids(data_root)
    missing = sorted(needed - have)
    print(f"{args.prefix}* intent 指向信封 {len(needed)}；已有 F2 {len(needed & have)}；"
          f"待锚定 {len(missing)}")

    f1 = _f1_index(data_root)
    todo = [(e, f1[e]) for e in missing if e in f1]
    print(f"其中能定位到 F1 信封的: {len(todo)}（缺 F1 {len(missing) - len(todo)}）")
    if args.limit:
        todo = todo[: args.limit]

    if not args.execute:
        print(f"\n[dry-run] 将锚定 {len(todo)} 个信封。加 --execute 执行。")
        return 0

    from finer.enrichment.entity_anchoring import build_f2_deterministic_envelope

    out_dir = data_root / "F2_anchored"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = failed = skipped = 0
    started = time.time()

    for i, (env_id, f1_path) in enumerate(todo, start=1):
        content_id = f1_path.parent.name
        record_path = data_root / "F0_intake" / "broker" / f"{content_id}.json"
        if not record_path.exists():
            skipped += 1
            continue
        try:
            envelope = json.loads(f1_path.read_text(encoding="utf-8"))
            record = json.loads(record_path.read_text(encoding="utf-8"))
            f2_env = build_f2_deterministic_envelope(envelope, f0_record=record)
            out = out_dir / f"{content_id}.json"
            tmp = out.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(
                    f2_env.model_dump(mode="json"),
                    ensure_ascii=False, indent=2, sort_keys=True,
                ),
                encoding="utf-8",
            )
            tmp.replace(out)
            written += 1
        except Exception as exc:  # noqa: BLE001 - 单条失败不该中断整批
            failed += 1
            print(f"  fail {content_id}: {type(exc).__name__}: {exc}")
        if i % 50 == 0:
            rate = i / max(1e-9, time.time() - started)
            print(f"  {i}/{len(todo)}  {rate*60:.1f}/min")

    print(f"\n锚定完成: written={written} failed={failed} skipped={skipped} "
          f"耗时 {(time.time()-started)/60:.1f} 分钟")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
