"""导出宣传站 /records 页的冻结数据快照。

把真实语料的记录卡 + 每信源的研报结果行导出为静态 JSON，供
`src/finer_site`（纯静态站，无后端）按需 fetch。快照是**冻结档案**：
带 as_of 日期，站点必须展示该日期而非暗示实时。

版权与隐私约束（导出即对外发布的前提）：
- 不导出 evidence_text / rationale / summary 等含研报原文片段的字段——
  结构化事实（评级、目标价、方向、日期、结算结果）可导出，原文不可。
- 不导出分析师个人姓名；信源展示到机构层级。
- 比率纪律由卡片自带的 sufficiency 保证（schema 必填），行级只导出实值。

用法（在主仓根目录）：
    .venv/bin/python scripts/export_site_records_snapshot.py \
        --out src/finer_site/public/records-data --as-of 2026-08-10
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from finer.backtest.scorecard import is_scoreable
from finer.credibility.record_card import build_record_cards
from finer.schemas.trade_action import TradeAction
from finer.services.repository import TradeActionRepository

SIGNAL_CLASSES = ["broker_recommendation", "broker_sector_view"]


def _load_intent_index(intents_dir: Path, intent_ids: set) -> Dict[str, dict]:
    """按 intent_id 读取 F3 文件；一个 id 一个文件，缺失容忍。"""
    index: Dict[str, dict] = {}
    for iid in intent_ids:
        f = intents_dir / f"{iid}.json"
        if not f.exists():
            continue
        try:
            index[iid] = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
    return index


def _row_of(action: TradeAction, intent: Optional[dict]) -> dict:
    """action + intent → 站点行。只含结构化事实，不含原文片段。"""
    meta = intent.get("metadata", {}) if intent else {}
    tp = (intent or {}).get("target_price") or {}
    br = action.backtest_result
    settle: dict
    if br is not None and br.return_pct is not None and not (
        (action.metadata or {}).get("superseded_by")
    ):
        settle = {
            "status": "settled",
            "win": br.return_pct > 0,
            "return_pct": round(br.return_pct, 4),
            "holding_days": br.holding_days,
            "exit_reason": str(br.exit_reason.value if hasattr(br.exit_reason, "value") else br.exit_reason),
        }
    else:
        settle = {"status": "pending"}
    timing = action.execution_timing
    published = (
        timing.intent_published_at.isoformat()
        if timing is not None and timing.intent_published_at is not None
        else None
    )
    return {
        "id": action.trade_action_id,
        "intent_id": action.intent_id,
        "signal_class": action.signal_class,
        "report_date": meta.get("report_date") or (published[:10] if published else None),
        "published_at": published,
        "executable_at": (
            timing.action_executable_at.isoformat()
            if timing is not None and timing.action_executable_at is not None
            else None
        ),
        "ticker": action.target.ticker if action.target else None,
        "name": action.target.company_name if action.target else None,
        "market": action.target.market if action.target else None,
        "direction": str(action.direction.value if hasattr(action.direction, "value") else action.direction),
        "rating": meta.get("rating_current"),
        "rating_prior": meta.get("rating_prior"),
        "target_price": tp.get("value"),
        "target_price_currency": tp.get("currency"),
        "action_type": (
            str(action.action_chain[0].action_type.value
                if hasattr(action.action_chain[0].action_type, "value")
                else action.action_chain[0].action_type)
            if action.action_chain else None
        ),
        "time_horizon": str(action.time_horizon.value if hasattr(action.time_horizon, "value") else action.time_horizon)
        if action.time_horizon is not None else None,
        "evidence_span_count": len(action.evidence_span_ids or []),
        "canonical": action.canonical_trace_status == "canonical",
        "settle": settle,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--as-of", required=True, help="快照冻结日期 YYYY-MM-DD")
    args = parser.parse_args()

    repo = TradeActionRepository(
        db_path=args.data_root / "cache" / "trade_actions.db",
        action_dir=args.data_root / "F5_executed",
    )
    all_actions = repo.load_all_actions()

    broker_actions: List[TradeAction] = [
        a
        for a in all_actions
        if a.signal_class in SIGNAL_CLASSES
        and not (a.metadata or {}).get("superseded_by")
    ]
    intent_ids = {a.intent_id for a in broker_actions if a.intent_id}
    intent_index = _load_intent_index(args.data_root / "F3_intents", intent_ids)

    by_creator: Dict[str, List[TradeAction]] = defaultdict(list)
    for a in broker_actions:
        creator = (a.source.creator_id if a.source is not None else None) or "unknown"
        by_creator[creator].append(a)

    # 记录卡：与产品同一构造器（sufficiency 必填、稳定输出序）。
    cards_by_class: Dict[str, list] = {}
    for sc in SIGNAL_CLASSES:
        cards = build_record_cards(all_actions, signal_class=sc)
        cards_by_class[sc] = [c.model_dump(mode="json") for c in cards]

    # 文件名不用中文 creator 名：cards 顺序即 creator-<i>.json 的 i。
    creator_order: List[str] = []
    for sc in SIGNAL_CLASSES:
        for c in cards_by_class[sc]:
            if c["creator_id"] not in creator_order:
                creator_order.append(c["creator_id"])
    for creator in sorted(by_creator):
        if creator not in creator_order:
            creator_order.append(creator)
    file_of = {creator: f"creator-{i}.json" for i, creator in enumerate(creator_order)}

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    settled_total = sum(1 for a in broker_actions if is_scoreable(a))
    manifest = {
        "as_of": args.as_of,
        "note": "冻结快照：真实语料的历史记录，不构成对未来的预测。",
        "total_actions": len(broker_actions),
        "settled_actions": settled_total,
        "signal_classes": SIGNAL_CLASSES,
        "cards": {
            sc: [
                {**card, "rows_file": file_of[card["creator_id"]]}
                for card in cards_by_class[sc]
            ]
            for sc in SIGNAL_CLASSES
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    for creator, actions in by_creator.items():
        rows = [_row_of(a, intent_index.get(a.intent_id or "")) for a in actions]
        rows.sort(key=lambda r: (r["report_date"] or "", r["id"]), reverse=True)
        payload = {
            "as_of": args.as_of,
            "creator_id": creator,
            "n_rows": len(rows),
            "rows": rows,
        }
        (out / file_of[creator]).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    sizes = sum(f.stat().st_size for f in out.glob("*.json"))
    print(
        f"exported {len(by_creator)} creators, {len(broker_actions)} rows "
        f"({settled_total} settled) → {out} ({sizes/1e6:.1f} MB)"
    )


if __name__ == "__main__":
    main()
