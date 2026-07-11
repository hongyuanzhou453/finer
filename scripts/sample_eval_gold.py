#!/usr/bin/env python3
"""sample_eval_gold.py — 从现役 F5 数据按 creator 分层抽样生成待标注 gold 队列.

eval gold 纪律（docs/specs/2026-07-11-eval-gold-discipline.md）第 1 步：
每个 pipeline-drive run 产出的新 F5 action，按 creator 分层抽样进 gold 队列，
交给既有 annotation workbench 标注；每行携带 pipeline_version 版本章，
管线版本变更后旧 gold 可据此降级为 reference。

输入:
    data/F5_executed/*_actions.json
    （wrapper: {source_file, extracted_at, model, actions[]}）

输出:
    data/dpo/eval_queue/queue_<YYYYMMDD-HHMMSS>.jsonl，每行:

    {
      "id": <trade_action_id>,          # 键名对齐 schemas/annotation.py 标注任务的 id
      "creator_id": ...,
      "evidence_text": ...,             # source.evidence_text
      "ticker": ...,                    # target.ticker
      "direction": ...,
      "action_type": ...,               # action_chain[0].action_type
      "rationale": ...,
      "pipeline_version": {
        "schema_version": ...,          # finer.services.versioning.CURRENT_SCHEMA_VERSION
        "prompt_version": ...,          # finer.services.versioning.CURRENT_PROMPT_VERSION
        "model_version": ...,           # action.model_version
        "f5_model": ...,                # wrapper.model
        "extraction_config_hash": ...,  # action.version_info.extraction_config_hash（可空）
        "source_file": ...              # wrapper.source_file（F5 的上游输入文件）
      },
      "sampled_at": <UTC ISO 时间戳>
    }

行格式与 ``src/finer/schemas/annotation.py`` 的标注任务兼容：``id`` 键名对齐
EvalGoldAnnotation.id（标注行以该 id 回挂队列行），其余字段为标注上下文与
版本章，不要求与 GoldExtraction 严格 1:1。

抽样规则（确定性，不用 random，方便重跑对账）:
    按 creator_id 分组，每组取 max(--per-creator-min, ceil(n * --rate)) 条，
    上限为组内条数；组内按 trade_action_id 字典序排序后取前 N。

用法:
    python scripts/sample_eval_gold.py --dry-run --rate 0.1
    python scripts/sample_eval_gold.py --rate 0.1 --per-creator-min 3 \
        --out-dir data/dpo/eval_queue
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# 版本章真相源：finer.services.versioning（导不到则 fallback，并告警）
try:
    from finer.services.versioning import (  # type: ignore
        CURRENT_PROMPT_VERSION,
        CURRENT_SCHEMA_VERSION,
    )

    _VERSION_SOURCE = "finer.services.versioning"
except Exception:  # pragma: no cover - 仅在脱离 venv 运行时触发
    CURRENT_SCHEMA_VERSION = "1.0"
    CURRENT_PROMPT_VERSION = "2.0"
    _VERSION_SOURCE = "fallback(hardcoded) — 未能 import finer.services.versioning，版本章可能漂移"


def load_actions(f5_dir: Path) -> List[Dict[str, Any]]:
    """读取 F5 wrapper 文件，展平为带 wrapper 上下文的 action 列表。"""
    items: List[Dict[str, Any]] = []
    files = sorted(f5_dir.glob("*_actions.json"))
    for path in files:
        try:
            wrapper = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [warn] 跳过无法解析的文件 {path}: {exc}", file=sys.stderr)
            continue
        actions = wrapper.get("actions")
        if not isinstance(actions, list):
            print(f"  [warn] 跳过缺 actions[] 的文件 {path}", file=sys.stderr)
            continue
        for action in actions:
            if not isinstance(action, dict) or not action.get("trade_action_id"):
                continue
            items.append({
                "action": action,
                "f5_model": wrapper.get("model"),
                "source_file": wrapper.get("source_file"),
            })
    return items


def to_queue_row(item: Dict[str, Any], sampled_at: str) -> Dict[str, Any]:
    """把展平后的 F5 action 转成 gold 队列行（含 pipeline_version 版本章）。"""
    action = item["action"]
    source = action.get("source") or {}
    target = action.get("target") or {}
    chain = action.get("action_chain") or []
    version_info = action.get("version_info") or {}
    return {
        "id": action["trade_action_id"],
        "creator_id": source.get("creator_id"),
        "evidence_text": source.get("evidence_text"),
        "ticker": target.get("ticker"),
        "direction": action.get("direction"),
        "action_type": (chain[0] or {}).get("action_type") if chain else None,
        "rationale": action.get("rationale"),
        "pipeline_version": {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "prompt_version": CURRENT_PROMPT_VERSION,
            "model_version": action.get("model_version"),
            "f5_model": item["f5_model"],
            "extraction_config_hash": version_info.get("extraction_config_hash"),
            "source_file": item["source_file"],
        },
        "sampled_at": sampled_at,
    }


def stratified_sample(
    items: List[Dict[str, Any]], *, rate: float, per_creator_min: int,
) -> Dict[str, Any]:
    """按 creator_id 分层确定性抽样。

    每组 quota = min(n, max(per_creator_min, ceil(n * rate)))；
    组内按 trade_action_id 字典序取前 quota 条。
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        creator = (item["action"].get("source") or {}).get("creator_id") or "unknown"
        groups.setdefault(creator, []).append(item)

    plan: Dict[str, Dict[str, int]] = {}
    sampled: List[Dict[str, Any]] = []
    for creator in sorted(groups):
        group = sorted(groups[creator], key=lambda it: it["action"]["trade_action_id"])
        n = len(group)
        quota = min(n, max(per_creator_min, math.ceil(n * rate)))
        plan[creator] = {"total": n, "sampled": quota}
        sampled.extend(group[:quota])
    return {"plan": plan, "sampled": sampled}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从现役 F5 数据按 creator 分层抽样生成待标注 gold 队列",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--f5-dir", type=str, default="data/F5_executed",
                    help="F5 wrapper (*_actions.json) 目录")
    ap.add_argument("--rate", type=float, default=0.1,
                    help="每 creator 抽样比例")
    ap.add_argument("--per-creator-min", type=int, default=3,
                    help="每 creator 最少抽样条数")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印分层抽样计划，不写文件")
    ap.add_argument("--out-dir", type=str, default="data/dpo/eval_queue",
                    help="队列输出目录")
    args = ap.parse_args()

    if not 0 < args.rate <= 1:
        ap.error(f"--rate 必须在 (0, 1] 内，收到 {args.rate}")
    if args.per_creator_min < 0:
        ap.error(f"--per-creator-min 必须 >= 0，收到 {args.per_creator_min}")

    f5_dir = Path(args.f5_dir)
    if not f5_dir.is_dir():
        print(f"[error] F5 目录不存在: {f5_dir}", file=sys.stderr)
        return 1

    items = load_actions(f5_dir)
    if not items:
        print(f"[error] {f5_dir} 下没有可用的 F5 action", file=sys.stderr)
        return 1

    result = stratified_sample(items, rate=args.rate,
                               per_creator_min=args.per_creator_min)
    plan, sampled = result["plan"], result["sampled"]

    print(f"版本章来源: {_VERSION_SOURCE} "
          f"(schema={CURRENT_SCHEMA_VERSION} prompt={CURRENT_PROMPT_VERSION})")
    print(f"扫描 {f5_dir}: {len(items)} 条现役 F5 action")
    print(f"分层抽样计划 (rate={args.rate}, per-creator-min={args.per_creator_min}):")
    for creator, row in plan.items():
        print(f"  {creator:<12} 现役 {row['total']:>3} 条 → 抽样 {row['sampled']:>3} 条")
    print(f"合计抽样 {len(sampled)} 条")

    if args.dry_run:
        print("\n(--dry-run 模式，仅打印计划，不写文件)")
        return 0

    sampled_at = datetime.now(timezone.utc).isoformat()
    rows = [to_queue_row(item, sampled_at) for item in sampled]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"queue_{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n已写入 {out_path}（{len(rows)} 条待标注 gold 队列）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
