#!/usr/bin/env python3
"""回写国际股的市场与执行时钟，并把入场 bar 会变的动作放回待结算队列。

**背景**：F3 早期的 ``infer_market`` 把所有非 US/CN/HK 后缀一律判成 ``US``
（且漏掉 ``.SH``），导致 870 条 action 的 ``execution_timing`` 挂在纽约日历上。
后果不是口径争议而是物理不可能：纽约时间上午发的日股研报，东京当天早已收盘，
却被允许当日入场——真实的 look-ahead。前向已于 2026-07-25 修复，存量未回写。

只读评估见 ``docs/specs/2026-07-25-intl-calendar-impact-assessment.md``：
870 条错标 / 514 已结算，其中 **237 条**的入场 bar 必然后移（其余 277 条同 bar，
重结算会得到逐位相同的结果，因此不动它们的 backtest_result）。

**两个阶段**：

  Phase 1 — 全部 870 条：按 ticker 归一化出的真实市场重算
            ``execution_timing``（market / timezone / action_executable_at /
            market_session_at_publish）并同步 ``target.market``。
  Phase 2 — 仅入场 bar 后移的子集：清空 ``backtest_result`` 且状态回 ``pending``，
            交给 ``finer settle`` 用正确日历重算。旧结果全量记入审计文件，可回溯。

安全：默认 dry-run；``--execute`` 前自动备份 ``data/F5_executed``；写文件用与
``TradeActionRepository`` 相同的 tmp+fsync+os.replace 原子模式；每条改动都进审计
JSON。只改 execution_timing / target.market / backtest_result / validation_status，
其余字段（含 trade_action_id、intent_id、policy_id、evidence_span_ids）逐位不动。

    python scripts/backfill_intl_market_timing.py            # dry-run 报告
    python scripts/backfill_intl_market_timing.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.ticker_normalization import normalize_broker_ticker  # noqa: E402
from finer.execution.timing_policy import (  # noqa: E402
    MarketCalendarTimingPolicy,
    get_market_config,
)

POLICY = MarketCalendarTimingPolicy()


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _entry_bar(period: Optional[str]) -> Optional[date]:
    """旧回测实际选中的入场 bar（backtest_period 的首段）。"""
    if not period:
        return None
    try:
        return date.fromisoformat(period.split(" — ")[0].strip()[:10])
    except ValueError:
        return None


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _iter_actions(doc: Any) -> List[Dict[str, Any]]:
    if isinstance(doc, list):
        return [a for a in doc if isinstance(a, dict)]
    if isinstance(doc, dict):
        for key in ("actions", "trade_actions"):
            value = doc.get(key)
            if isinstance(value, list):
                return [a for a in value if isinstance(a, dict)]
        if doc.get("trade_action_id"):
            return [doc]
    return []


def _plan_action(action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """判断一条 action 是否需要回写；返回改动计划或 None。"""
    target = action.get("target") or {}
    symbol = target.get("ticker_normalized") or target.get("ticker") or ""
    normalized = normalize_broker_ticker(symbol)
    if normalized is None or not normalized.market:
        return None

    timing = action.get("execution_timing") or {}
    stamped = timing.get("market") or target.get("market")
    if not stamped or normalized.market == stamped:
        return None

    published_at = _parse_dt(timing.get("intent_published_at"))
    if published_at is None:
        return {"skip_reason": "no_published_at"}

    config = get_market_config(normalized.market)
    timezone = config.timezone if config is not None else "UTC"
    effective_at = _parse_dt(timing.get("intent_effective_at"))
    computed = POLICY.compute_timing(
        published_at=published_at,
        market=normalized.market,
        timezone=timezone,
        intent_effective_at=effective_at,
    )

    old_executable = _parse_dt(timing.get("action_executable_at")) or effective_at
    new_executable = computed.action_executable_at
    old_entry = old_executable.date() if old_executable else None
    new_entry = new_executable.date() if new_executable else None

    backtest = action.get("backtest_result") or {}
    settled = bool(backtest) and backtest.get("return_pct") is not None
    bar = _entry_bar(backtest.get("backtest_period"))

    # 入场 bar 只在新时钟晚于旧的实际入场 bar 时必然改变；
    # new_entry ∈ [old_entry, bar] 区间内取到的仍是同一根 bar（该区间内按定义无 bar）。
    entry_bar_moves = bool(settled and bar and new_entry and new_entry > bar)

    return {
        "trade_action_id": action.get("trade_action_id"),
        "ticker": symbol,
        "old_market": stamped,
        "new_market": normalized.market,
        "old_timezone": timing.get("timezone"),
        "new_timezone": computed.timezone,
        "old_executable_at": timing.get("action_executable_at"),
        "new_executable_at": new_executable.isoformat() if new_executable else None,
        "old_entry_date": old_entry.isoformat() if old_entry else None,
        "new_entry_date": new_entry.isoformat() if new_entry else None,
        "old_entry_bar": bar.isoformat() if bar else None,
        "settled": settled,
        "entry_bar_moves": entry_bar_moves,
        "old_backtest_result": backtest if entry_bar_moves else None,
        "old_validation_status": action.get("validation_status"),
        "new_market_session": computed.market_session_at_publish,
        "new_timing_policy_id": computed.timing_policy_id,
    }


def _apply(action: Dict[str, Any], plan: Dict[str, Any]) -> None:
    """就地改写 action（只动市场/时钟，以及需重结算者的结果字段）。"""
    timing = action.setdefault("execution_timing", {})
    timing["market"] = plan["new_market"]
    timing["timezone"] = plan["new_timezone"]
    timing["action_executable_at"] = plan["new_executable_at"]
    timing["market_session_at_publish"] = plan["new_market_session"]
    timing["timing_policy_id"] = plan["new_timing_policy_id"]

    target = action.setdefault("target", {})
    target["market"] = plan["new_market"]

    if plan["entry_bar_moves"]:
        # 旧结果建立在物理上不可能的入场点上，清空交给 settle 重算。
        action["backtest_result"] = None
        action["validation_status"] = "pending"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument(
        "--execute", action="store_true",
        help="写入改动（默认只出报告）",
    )
    parser.add_argument(
        "--audit-out", type=Path, default=None,
        help="审计 JSON 落盘路径（默认 <data-root>/_audit/intl_market_backfill_<ts>.json）",
    )
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    f5_dir = data_root / "F5_executed"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    plans_by_file: Dict[Path, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = {}
    stats: Counter = Counter()
    remap: Counter = Counter()

    for path in sorted(f5_dir.glob("*_actions.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stats["file_unreadable"] += 1
            continue
        for action in _iter_actions(doc):
            plan = _plan_action(action)
            if plan is None:
                continue
            if plan.get("skip_reason"):
                stats[f"skipped/{plan['skip_reason']}"] += 1
                continue
            stats["to_rewrite"] += 1
            remap[f"{plan['old_market']}->{plan['new_market']}"] += 1
            if plan["settled"]:
                stats["settled"] += 1
            if plan["entry_bar_moves"]:
                stats["entry_bar_moves(will re-settle)"] += 1
            plans_by_file.setdefault(path, []).append((action, plan))

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"[{mode}] international market/timing backfill — {f5_dir}")
    print(f"  files touched: {len(plans_by_file)}")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    print("  market remap (top 15):")
    for pair, count in remap.most_common(15):
        print(f"    {count:>4}  {pair}")

    if not args.execute:
        print("\n加 --execute 执行（会先备份 F5_executed）。")
        return 0

    if not plans_by_file:
        print("\n无待回写项。")
        return 0

    backup = f5_dir.parent / f"F5_executed.bak-{stamp}-intl-market"
    print(f"\n备份 → {backup}")
    shutil.copytree(f5_dir, backup)

    audit: List[Dict[str, Any]] = []
    written = 0
    for path, pairs in plans_by_file.items():
        doc = json.loads(path.read_text(encoding="utf-8"))
        # 重新按 id 定位（_plan_action 阶段持有的 dict 属于另一次解析）
        by_id = {a.get("trade_action_id"): a for a in _iter_actions(doc)}
        for _stale, plan in pairs:
            action = by_id.get(plan["trade_action_id"])
            if action is None:
                stats["apply/action_vanished"] += 1
                continue
            _apply(action, plan)
            audit.append({**plan, "file": path.name})
        _atomic_write(path, doc)
        written += 1

    audit_path = args.audit_out or (
        data_root / "_audit" / f"intl_market_backfill_{stamp}.json"
    )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(audit_path, {
        "generated_at": datetime.now().isoformat(),
        "backup": str(backup),
        "counts": dict(stats),
        "changes": audit,
    })

    print(f"files written: {written}")
    print(f"audit → {audit_path}  ({len(audit)} changes)")
    resettle = stats["entry_bar_moves(will re-settle)"]
    print(f"\n{resettle} 条已回到 pending；索引里的 validation_status 需要同步：")
    print("  python -c \"import sys;sys.path.insert(0,'src');"
          "from finer.services.repository import TradeActionRepository;"
          "print(TradeActionRepository().rebuild_index())\"")
    print("随后运行结算：finer settle --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
