#!/usr/bin/env python3
"""全语料执行时钟回写 + 入场 bar 变动者重置待结算。

**根因**（`docs/specs/2026-07-27-corpus-wide-entry-lookahead.md`）：上游只有研报
**日期**没有发布时刻，``published_at`` 被填成当地零点。北京时 D 日零点 ≡ 纽约时
D−1 日 11:00（盘中），时钟策略把占位符当真实时刻，于是把可执行时间放到 D−1 ——
比研报发布早一整天。实测 **1,669 条（50.4%）** 入场早于其研报日期，绝大多数是美股。

本脚本按修好的前向规则重算全语料时钟：

  * 市场取 ticker 归一化出的**真实市场**（存量有 870 条被旧 ``infer_market``
    误标成 US；仅改市场标记并不能解决前视，见 spec §3）；
  * date-only 的 ``published_at`` 经 ``resolve_publication_instant`` 按目标市场
    时区重锚（与 ``timing_builder`` 用同一个函数，前向与回写不会漂移）。

Phase 1 — 时钟有变化的全部 action：改写 ``execution_timing``（market / timezone /
          action_executable_at / market_session_at_publish / timing_policy_id /
          execution_delay_reason）与 ``target.market``。
Phase 2 — 入场 bar 必然变动者：清空 ``backtest_result``、状态回 ``pending``，
          交 ``finer settle`` 用正确时钟重算。旧值全量入审计。

安全（含对抗审查提出的四项修正）：
  * 审计文件在**写入循环之前**先落盘（中断也留有可回溯记录），完成后追加 marker；
  * ``--execute`` 前检查是否有其他进程在写 F5，并要求 ``--i-know-no-writers`` 确认；
  * 打印的 rebuild-index 命令使用实际 ``--data-root``；
  * 审计捕获全部被覆盖字段（含 market_session_at_publish / timing_policy_id /
    target.market），可脱离备份重建原状；
  * 入场 bar **前移**（理论上可能，实测 0 例）单独计数并拒绝自动处理。

    python scripts/backfill_execution_timing.py                       # dry-run
    python scripts/backfill_execution_timing.py --execute --i-know-no-writers
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.ticker_normalization import normalize_broker_ticker  # noqa: E402
from finer.execution.timing_policy import (  # noqa: E402
    MarketCalendarTimingPolicy,
    get_market_config,
)
from finer.extraction.timing_builder import resolve_publication_instant  # noqa: E402

POLICY = MarketCalendarTimingPolicy()

#: 上游（研报聚合源）产出研报日期时所用的时区 —— 日期被填成该时区的零点。
#: F5 已把同一瞬间重新渲染成市场本地时区（如 ``2025-12-16T11:00:00-05:00``
#: 其实就是 ``2025-12-17T00:00:00+08:00``），零点标记在存量里不可见，
#: 因此回写必须显式按源时区判定，否则 97.5% 的 date-only 记录会被漏掉。
SOURCE_TIMEZONE = "Asia/Shanghai"

#: execution_timing 中会被本脚本覆盖的字段（审计必须逐个留旧值）
_TIMING_FIELDS = (
    "market",
    "timezone",
    "action_executable_at",
    "market_session_at_publish",
    "timing_policy_id",
    "execution_delay_reason",
)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _entry_bar(period: Optional[str]) -> Optional[date]:
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


def _plan(action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """返回改动计划；无变化或无法计算时返回 None / skip。"""
    timing = action.get("execution_timing") or {}
    target = action.get("target") or {}
    published_at = _parse_dt(timing.get("intent_published_at"))
    if published_at is None:
        return {"skip_reason": "no_published_at"}

    symbol = target.get("ticker_normalized") or target.get("ticker") or ""
    normalized = normalize_broker_ticker(symbol)
    market = (
        normalized.market
        if normalized is not None and normalized.market
        else (timing.get("market") or target.get("market"))
    )
    if not market:
        return {"skip_reason": "no_market"}

    config = get_market_config(market)
    timezone = config.timezone if config is not None else "UTC"
    anchored = resolve_publication_instant(
        published_at, timezone, source_timezone=SOURCE_TIMEZONE
    )
    computed = POLICY.compute_timing(
        published_at=anchored,
        market=market,
        timezone=timezone,
        intent_effective_at=_parse_dt(timing.get("intent_effective_at")),
    )

    new_values = {
        "market": computed.market,
        "timezone": computed.timezone,
        "action_executable_at": computed.action_executable_at.isoformat()
        if computed.action_executable_at else None,
        "market_session_at_publish": computed.market_session_at_publish,
        "timing_policy_id": computed.timing_policy_id,
        "execution_delay_reason": getattr(computed, "execution_delay_reason", None),
    }
    old_values = {field: timing.get(field) for field in _TIMING_FIELDS}
    timing_changed = any(old_values[f] != new_values[f] for f in _TIMING_FIELDS)
    market_changed = target.get("market") != computed.market
    if not timing_changed and not market_changed:
        return None

    old_executable = _parse_dt(timing.get("action_executable_at"))
    new_executable = computed.action_executable_at
    old_entry = old_executable.date() if old_executable else None
    new_entry = new_executable.date() if new_executable else None

    backtest = action.get("backtest_result") or {}
    settled = backtest.get("return_pct") is not None
    bar = _entry_bar(backtest.get("backtest_period"))

    # new > B_old ⟹ 必然换到更晚的 bar；new ∈ [old, B_old] ⟹ 同一根 bar
    # （该区间内按 B_old 的定义不存在 bar）。new < old ⟹ 可能前移，见下。
    moves_later = bool(settled and bar and new_entry and new_entry > bar)
    moves_earlier = bool(
        settled and old_entry and new_entry and new_entry < old_entry
    )

    return {
        "trade_action_id": action.get("trade_action_id"),
        "ticker": symbol,
        "settled": settled,
        "old_target_market": target.get("market"),
        "old_timing": old_values,
        "new_timing": new_values,
        "old_entry_date": old_entry.isoformat() if old_entry else None,
        "new_entry_date": new_entry.isoformat() if new_entry else None,
        "old_entry_bar": bar.isoformat() if bar else None,
        "entry_bar_moves_later": moves_later,
        "entry_bar_may_move_earlier": moves_earlier,
        "old_backtest_result": backtest if moves_later else None,
        "old_validation_status": action.get("validation_status") if moves_later else None,
    }


def _apply(action: Dict[str, Any], plan: Dict[str, Any]) -> None:
    timing = action.setdefault("execution_timing", {})
    for field, value in plan["new_timing"].items():
        timing[field] = value
    action.setdefault("target", {})["market"] = plan["new_timing"]["market"]
    if plan["entry_bar_moves_later"]:
        action["backtest_result"] = None
        action["validation_status"] = "pending"


def _other_writers() -> List[str]:
    """粗查是否有别的进程可能在写 F5（审查 Defect 3）。"""
    try:
        out = subprocess.run(
            ["ps", "-Ao", "pid,command"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:  # noqa: BLE001
        return []
    mine = str(os.getpid())
    hits = []
    for line in out.splitlines():
        if line.split(maxsplit=1)[:1] == [mine]:
            continue
        if any(k in line for k in ("finer.cli settle", "uvicorn finer", "drive_broker",
                                   "broker_runner", "pipeline-drive")):
            hits.append(line.strip()[:140])
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--i-know-no-writers", action="store_true",
        help="确认没有其他进程在写 data/F5_executed（本脚本做 read-modify-write，"
             "与并发写方互相覆盖）",
    )
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    f5_dir = data_root / "F5_executed"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    plans: Dict[str, List[Dict[str, Any]]] = {}
    stats: Counter = Counter()
    remap: Counter = Counter()
    shift: Counter = Counter()

    for path in sorted(f5_dir.glob("*_actions.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stats["file_unreadable"] += 1
            continue
        for action in _iter_actions(doc):
            stats["scanned"] += 1
            plan = _plan(action)
            if plan is None:
                stats["unchanged"] += 1
                continue
            if plan.get("skip_reason"):
                stats[f"skipped/{plan['skip_reason']}"] += 1
                continue
            stats["to_rewrite"] += 1
            old_market = plan["old_timing"]["market"]
            if old_market != plan["new_timing"]["market"]:
                remap[f"{old_market}->{plan['new_timing']['market']}"] += 1
            if plan["old_entry_date"] and plan["new_entry_date"]:
                delta = (
                    date.fromisoformat(plan["new_entry_date"])
                    - date.fromisoformat(plan["old_entry_date"])
                ).days
                shift[delta] += 1
            if plan["settled"]:
                stats["settled"] += 1
            if plan["entry_bar_moves_later"]:
                stats["entry_bar_moves_later(re-settle)"] += 1
            if plan["entry_bar_may_move_earlier"]:
                stats["entry_bar_MAY_MOVE_EARLIER(manual)"] += 1
            plans.setdefault(str(path), []).append(plan)

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"[{mode}] corpus-wide execution-timing backfill — {f5_dir}")
    print(f"  files with changes: {len(plans)}")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    print("  entry-date shift (new − old):")
    for delta, count in sorted(shift.items()):
        print(f"    {delta:>+4}d : {count}")
    if remap:
        print("  market remap (top 12):")
        for pair, count in remap.most_common(12):
            print(f"    {count:>5}  {pair}")

    if stats["entry_bar_MAY_MOVE_EARLIER(manual)"]:
        print("\n⚠️ 存在入场 bar 可能前移的条目 —— 本脚本不自动处理，先人工核查。")

    if not args.execute:
        print("\n加 --execute --i-know-no-writers 执行（会先备份 F5_executed）。")
        return 0

    writers = _other_writers()
    if writers:
        print("\n⛔ 检测到可能正在写 F5 的进程，中止：")
        for line in writers:
            print(f"    {line}")
        return 3
    if not args.i_know_no_writers:
        print("\n⛔ 需要 --i-know-no-writers 显式确认无并发写入者。")
        return 4

    if not plans:
        print("\n无待回写项。")
        return 0

    backup = f5_dir.parent / f"F5_executed.bak-{stamp}-timing"
    print(f"\n备份 → {backup}")
    shutil.copytree(f5_dir, backup)

    # 审计**先于**写入落盘：中途中断也留有完整可回溯记录。
    audit_path = data_root / "_audit" / f"execution_timing_backfill_{stamp}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(audit_path, {
        "generated_at": datetime.now().isoformat(),
        "status": "planned",
        "backup": str(backup),
        "counts": dict(stats),
        "changes": {k: v for k, v in plans.items()},
    })
    print(f"审计（planned）→ {audit_path}")

    written = 0
    for path_str, file_plans in plans.items():
        path = Path(path_str)
        doc = json.loads(path.read_text(encoding="utf-8"))
        by_id = {a.get("trade_action_id"): a for a in _iter_actions(doc)}
        touched = False
        for plan in file_plans:
            action = by_id.get(plan["trade_action_id"])
            if action is None:
                stats["apply/action_vanished"] += 1
                continue
            _apply(action, plan)
            touched = True
        if touched:
            _atomic_write(path, doc)
            written += 1

    _atomic_write(audit_path, {
        "generated_at": datetime.now().isoformat(),
        "status": "applied",
        "backup": str(backup),
        "counts": dict(stats),
        "files_written": written,
        "changes": {k: v for k, v in plans.items()},
    })

    print(f"files written: {written}")
    print(f"审计（applied）→ {audit_path}")
    resettle = stats["entry_bar_moves_later(re-settle)"]
    print(f"\n{resettle} 条已回到 pending。接下来：")
    print(f"  1) 重建索引（同步 validation_status）：")
    print(f"     python -c \"import sys;sys.path.insert(0,'{REPO_ROOT / 'src'}');"
          f"from finer.services.repository import TradeActionRepository;"
          f"from pathlib import Path;"
          f"print(TradeActionRepository("
          f"db_path=Path('{data_root}')/'cache'/'trade_actions.db',"
          f"action_dir=Path('{data_root}')/'F5_executed').rebuild_index())\"")
    print("     注：重建会顺带清掉索引里的陈旧孤儿行（文件是真值），"
          "计数下降属正常，非本次回写导致。")
    print("  2) 结算：python -m finer.cli settle --apply")
    print("  3) 出记分卡：python scripts/broker_scorecard.py "
          "--signal-class broker_recommendation --out docs/specs/<date>-scorecard-v6.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
