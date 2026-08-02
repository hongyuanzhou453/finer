#!/usr/bin/env python3
"""对搁浅 bri intent 做定向实体验证，把核实过的锚点写回 F2 信封（P1）。

流程契约（`docs/specs/2026-07-30-next-actions-plan.md` P1，用户已确认）：

  1. dry-run（默认）：漏斗报告，零写入
  2. ``--audit-sample N``：随机抽 N 条命中，连同 ±80 字符上下文窗口落盘，
     供人工/独立 agent 精度核对 —— **精度 ≥95% 才允许 --execute**
  3. ``--execute``：只把新 anchor/spans **增量并入** F2 信封（按 span id 去重，
     幂等）；改动文件先备份；审计 JSON 在写入前落盘（planned → applied）
  4. 后续由 ``drive_broker_recommendations.py`` 正常桥接产 action

安全：绝不修改既有锚点/span；新增内容全部带 ``layer=targeted_verification``
标记，可按标记整体审计或回滚；原子写（tmp+fsync+replace）。

    python scripts/backfill_targeted_anchors.py                    # dry-run
    python scripts/backfill_targeted_anchors.py --audit-sample 50
    python scripts/backfill_targeted_anchors.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.targeted_anchor import verify_declared_target  # noqa: E402

CONTEXT_CHARS = 80


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _load_stranded(data_root: Path) -> List[Dict[str, Any]]:
    actioned = set()
    for f in (data_root / "F5_executed").glob("bri_*_actions.json"):
        try:
            for a in json.loads(f.read_text(encoding="utf-8")).get("actions", []):
                if a.get("intent_id"):
                    actioned.add(a["intent_id"])
        except (OSError, json.JSONDecodeError):
            continue
    stranded = []
    for f in (data_root / "F3_intents").glob("bri_*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("intent_id") not in actioned:
            stranded.append(d)
    return stranded


def _envelope_index(data_root: Path) -> Dict[str, Path]:
    """envelope_id → F2 文件路径（头部正则，避免全量解析 9,800 个文件）。"""
    index: Dict[str, Path] = {}
    pattern = re.compile(r'"envelope_id"\s*:\s*"([^"]+)"')
    for path in (data_root / "F2_anchored").glob("broker_*.json"):
        try:
            head = path.read_text(encoding="utf-8")[:600]
        except OSError:
            continue
        m = pattern.search(head)
        if m:
            index[m.group(1)] = path
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--audit-sample", type=int, default=None,
                        help="随机抽 N 条命中落盘供精度核对（隐含 dry-run）")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-kind", choices=("all", "bare"), default="all",
                        help="bare: 只抽裸代码命中（交易所限定门的专项审计）")
    parser.add_argument("--execute", action="store_true",
                        help="把核实过的锚点并入 F2 信封（需先过精度审计门）")
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    stranded = _load_stranded(data_root)
    env_index = _envelope_index(data_root)
    print(f"搁浅 bri intent: {len(stranded)}")
    print(f"F2 信封索引: {len(env_index)}")

    funnel: Counter = Counter()
    gate_rejects: Counter = Counter()
    verified: List[Dict[str, Any]] = []  # {intent, path, result}
    env_cache: Dict[str, Dict[str, Any]] = {}

    for intent in stranded:
        path = env_index.get(intent.get("envelope_id"))
        if path is None:
            funnel["no_envelope"] += 1
            continue
        key = str(path)
        if key not in env_cache:
            try:
                env_cache[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                env_cache[key] = {}
        env = env_cache[key]
        if not env:
            funnel["envelope_unreadable"] += 1
            continue

        existing = {
            a.get("resolved_symbol")
            for a in (env.get("entity_anchors") or [])
        }
        result = verify_declared_target(
            env, intent.get("target_symbol") or "", intent.get("target_name")
        )
        for gate, n in result.rejected.items():
            gate_rejects[gate] += n
        funnel[result.status] += 1
        if result.status != "verified":
            continue
        if result.anchor.resolved_symbol in existing:
            funnel["already_anchored"] += 1  # 状态漂移：本应已可桥接
            continue
        verified.append({"intent": intent, "path": path, "result": result})

    print("\n== 验证漏斗 ==")
    for k, v in funnel.most_common():
        print(f"  {k}: {v}")
    print(f"  → 可写回: {len(verified)}")
    print("\n== 上下文门拒绝分布 ==")
    for k, v in gate_rejects.most_common():
        print(f"  {k}: {v}")

    # ── 审计抽样 ─────────────────────────────────────────────────────────
    if args.audit_sample:
        random.seed(args.seed)
        pool = verified
        if args.sample_kind == "bare":
            # 裸代码命中 = alias 不含点且不是声明的公司名（交易所限定门的产物）
            pool = [
                e for e in verified
                if any(
                    "." not in o["alias"]
                    and o["alias"] != (e["intent"].get("target_name") or "")
                    for o in e["result"].anchor.metadata["occurrences"]
                )
            ]
            print(f"\n裸代码命中池: {len(pool)}")
        sample = random.sample(pool, min(args.audit_sample, len(pool)))
        items = []
        for entry in sample:
            env = env_cache[str(entry["path"])]
            blocks = {b.get("block_id"): b.get("text") or "" for b in env.get("blocks") or []}
            occs = entry["result"].anchor.metadata["occurrences"]
            if args.sample_kind == "bare":
                occs = [
                    o for o in occs
                    if "." not in o["alias"]
                    and o["alias"] != (entry["intent"].get("target_name") or "")
                ] or occs
            occ = occs[0]
            text = blocks.get(occ["block_id"], "")
            lo = max(0, occ["char_start"] - CONTEXT_CHARS)
            hi = min(len(text), occ["char_end"] + CONTEXT_CHARS)
            items.append({
                "intent_id": entry["intent"].get("intent_id"),
                "target_symbol": entry["intent"].get("target_symbol"),
                "target_name": entry["intent"].get("target_name"),
                "matched_alias": occ["alias"],
                "resolved_symbol": entry["result"].anchor.resolved_symbol,
                "occurrences": entry["result"].occurrences,
                "context": text[lo:hi].replace("\n", " "),
                "file": entry["path"].name,
            })
        out = data_root / "_audit" / f"targeted_anchor_sample_{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(out, {"seed": args.seed, "n": len(items), "items": items})
        print(f"\n审计样本 → {out}  ({len(items)} 条)")
        return 0

    if not args.execute:
        print("\n加 --audit-sample 50 出精度核对样本；过门后再 --execute。")
        return 0

    # ── 执行：备份 → 审计先行 → 增量并入 ────────────────────────────────
    touched: Dict[str, List[Dict[str, Any]]] = {}
    for entry in verified:
        touched.setdefault(str(entry["path"]), []).append(entry)

    backup_dir = data_root / f"F2_anchored.bak-{stamp}-targeted-anchor"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for key in touched:
        shutil.copy2(key, backup_dir / Path(key).name)
    print(f"\n备份 {len(touched)} 个将改动的信封 → {backup_dir}")

    audit_path = data_root / "_audit" / f"targeted_anchor_backfill_{stamp}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_changes = [
        {
            "file": Path(k).name,
            "intent_ids": [e["intent"].get("intent_id") for e in v],
            "symbols": [e["result"].anchor.resolved_symbol for e in v],
            "span_ids": [
                s.evidence_span_id
                for e in v
                for spans in e["result"].spans_by_block.values()
                for s in spans
            ],
        }
        for k, v in touched.items()
    ]
    _atomic_write(audit_path, {
        "status": "planned", "backup": str(backup_dir), "changes": audit_changes,
    })

    written = 0
    added_anchors = 0
    for key, entries in touched.items():
        env = env_cache[key]
        anchors = env.setdefault("entity_anchors", [])
        existing_symbols = {a.get("resolved_symbol") for a in anchors}
        block_by_id = {b.get("block_id"): b for b in env.get("blocks") or []}
        changed = False
        for entry in entries:
            result = entry["result"]
            if result.anchor.resolved_symbol in existing_symbols:
                continue
            anchors.append(result.anchor.model_dump(mode="json"))
            existing_symbols.add(result.anchor.resolved_symbol)
            added_anchors += 1
            changed = True
            for block_id, spans in result.spans_by_block.items():
                block = block_by_id.get(block_id)
                if block is None:
                    continue
                existing_ids = {
                    s.get("evidence_span_id")
                    for s in (block.get("evidence_spans") or [])
                }
                for span in spans:
                    if span.evidence_span_id in existing_ids:
                        continue  # 幂等：稳定 id 重跑不重复
                    block.setdefault("evidence_spans", []).append(
                        span.model_dump(mode="json")
                    )
        if changed:
            _atomic_write(Path(key), env)
            written += 1

    _atomic_write(audit_path, {
        "status": "applied", "backup": str(backup_dir),
        "files_written": written, "anchors_added": added_anchors,
        "changes": audit_changes,
    })
    print(f"信封写回: {written}  新增锚点: {added_anchors}")
    print(f"审计 → {audit_path}")
    print("\n下一步: python scripts/drive_broker_recommendations.py --execute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
