#!/usr/bin/env python3
"""市场戳修正后重算 ExecutionTiming（默认只读）。

`repair_bare_symbol_market.py` 把裸代码升级成了带后缀形式并改正了 `market`，
但 `execution_timing` 是 F5 组装时用**旧的（兜底 US）市场**算出来的——时区仍是
`America/New_York`。而结算取的正是 `execution_timing.action_executable_at`
（`backtest/per_action.py:170`），所以伦敦/悉尼/米兰的标的会按纽约日历入场，
入场日可能整体差一天。这与本项目上周做过全语料修复的是**同一类错**。

本脚本对「被修过市场戳、且新市场非北美」的 action 用正确市场重算时机：

  * 北美（US/CA）跳过 —— 多伦多与纽约同时区、日历基本一致，重算无实益；
  * 重算后若 `action_executable_at` 的**日期**发生变化，则该 action 的既有
    `backtest_result` 是按错误入场日算的，一并作废等待重结算；
  * 全量备份，记录 `execution_timing_before_repair`。

    python scripts/repair_execution_timing_after_market_fix.py            # dry-run
    python scripts/repair_execution_timing_after_market_fix.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.execution.timing_policy import (  # noqa: E402
    MarketCalendarTimingPolicy,
    get_market_config,
)

NORTH_AMERICA = {"US", "CA"}


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


_POLICY = MarketCalendarTimingPolicy()


def _recompute(published_at: datetime, market: str) -> Optional[Dict[str, Any]]:
    """用正确市场重算 executable 时刻；该市场不在会话表里则返回 None（不猜）。"""
    config = get_market_config(market)
    if config is None:
        return None
    result = _POLICY.compute_timing(
        published_at=published_at, market=market, timezone=config.timezone
    )
    return {
        "action_executable_at": result.action_executable_at,
        "market_session_at_publish": result.market_session_at_publish,
        "timezone": config.timezone,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    data_root = args.data_root.resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    stats = Counter()
    planned: Dict[str, list] = {}

    for path in sorted((data_root / "F5_executed").glob("bri_*_actions.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        changes = []
        for idx, action in enumerate(doc.get("actions", [])):
            target = action.get("target") or {}
            if not target.get("ticker_before_repair"):
                continue
            market = target.get("market") or ""
            stats["repaired_actions"] += 1
            if market in NORTH_AMERICA:
                stats["skipped_north_america"] += 1
                continue
            timing = action.get("execution_timing") or {}
            published = _parse(timing.get("intent_published_at"))
            if published is None:
                stats["skipped_no_published_at"] += 1
                continue
            fresh = _recompute(published, market)
            if fresh is None:
                stats["skipped_unknown_market"] += 1
                continue
            old_exec = _parse(timing.get("action_executable_at"))
            new_exec = fresh["action_executable_at"]
            date_moved = (
                old_exec is None or old_exec.date() != new_exec.date()
            )
            stats["recomputed"] += 1
            if date_moved:
                stats["entry_date_moved"] += 1
                if action.get("backtest_result"):
                    stats["settled_needs_resettle"] += 1
            changes.append({
                "idx": idx,
                "market": market,
                "old_tz": timing.get("timezone"),
                "new_tz": fresh["timezone"],
                "old_exec": old_exec.isoformat() if old_exec else None,
                "new_exec": new_exec.isoformat(),
                "date_moved": date_moved,
            })
        if changes:
            planned[str(path)] = changes

    print(f"被修过市场戳的 action: {stats['repaired_actions']}")
    print(f"  北美跳过（纽约≈多伦多）: {stats['skipped_north_america']}")
    print(f"  重算: {stats['recomputed']}")
    print(f"    其中入场**日期**改变: {stats['entry_date_moved']}")
    print(f"    其中已结算需作废重结算: {stats['settled_needs_resettle']}")
    print(f"  跳过（无 published_at / 未知市场）: "
          f"{stats['skipped_no_published_at']} / {stats['skipped_unknown_market']}")

    sample = [c for cs in planned.values() for c in cs if c["date_moved"]][:10]
    if sample:
        print("\n== 入场日改变样例 ==")
        for c in sample:
            print(f"  {c['market']:<4} {c['old_tz']} → {c['new_tz']}   "
                  f"{c['old_exec']} → {c['new_exec']}")

    out = data_root / "_audit" / f"timing_repair_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(out, {"status": "planned", "stats": dict(stats),
                        "files": len(planned)})
    print(f"\n计划 → {out}")

    if not args.execute:
        print("\n[dry-run] 未写入。确认后加 --execute。")
        return 0

    backup = data_root / f"timing_repair.bak-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    written = 0
    for key, changes in planned.items():
        path = Path(key)
        shutil.copy2(path, backup / path.name)
        doc = json.loads(path.read_text(encoding="utf-8"))
        for change in changes:
            action = doc["actions"][change["idx"]]
            timing = action.get("execution_timing") or {}
            action.setdefault("metadata", {})["execution_timing_before_repair"] = {
                "action_executable_at": change["old_exec"],
                "timezone": change["old_tz"],
            }
            timing["action_executable_at"] = change["new_exec"]
            timing["timezone"] = change["new_tz"]
            timing["market"] = change["market"]
            action["execution_timing"] = timing
            if change["date_moved"] and action.get("backtest_result"):
                action["backtest_result"] = None  # 按错误入场日算的，作废
        _atomic_write(path, doc)
        written += 1

    _atomic_write(out, {"status": "applied", "stats": dict(stats),
                        "files": written, "backup": str(backup)})
    print(f"\n写回 {written} 个文件；备份 → {backup}")
    print("\n下一步: python scripts/backfill_f8_backtest.py --apply（重结算被作废的）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
