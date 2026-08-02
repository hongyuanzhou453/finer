#!/usr/bin/env python3
"""用正文交易所限定符纠正被兜底盖成美股的裸代码（方案 A，**默认只读**）。

问题：``normalize_broker_ticker`` 对**任何**裸代码一律返回 ``market="US"``。
对 RBC 这类覆盖加拿大股的研报，T3 只给了裸代码（``target_name == target_symbol``），
于是 ``AC``（加拿大航空 TSX）被当成 Associated Capital、``CG``（Centerra Gold）
被当成凯雷、``PD``（Precision Drilling）被当成 PagerDuty —— 结算会取**错公司**
的价，产出貌似合理的错误回测。

唯一可靠的身份证据是正文里的交易所限定符（``AC ... CN``、``XRO ... ASX``），
本轮已由 `enrichment/targeted_anchor.py` 记进
``anchor.metadata.occurrences[].exchange_hint``。本脚本据此把
``resolved_symbol`` 升级为带后缀形式，并同步 F5 action 的 target。

安全约束：
  * 默认 dry-run，只出报告；``--execute`` 才写，且先全量备份；
  * 只用**严格** hint 集（剔除 ``IN``/``NA``/``SS`` 等与英文词撞车的两字母码）；
  * 一条记录出现互相矛盾的 hint → 跳过，计入 ``conflicting_hints``；
  * 升级后的符号必须能被 ``normalize_broker_ticker`` 解析回同一市场，否则跳过；
  * 已带后缀的符号一律不碰。

    python scripts/repair_bare_symbol_market.py            # dry-run
    python scripts/repair_bare_symbol_market.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.ticker_normalization import normalize_broker_ticker  # noqa: E402

#: hint → Yahoo 后缀。只列身份明确、且 token 不与英文词撞车的。
#: 注意 Bloomberg 的 ``CN`` 是**加拿大**，不是中国。
HINT_SUFFIX: Dict[str, str] = {
    "TSX": ".TO", "TSXV": ".V", "CN": ".TO",
    "ASX": ".AX",
    "LSE": ".L", "AIM": ".L", "LN": ".L",
    "SEHK": ".HK", "HKEX": ".HK", "HKSE": ".HK", "HK": ".HK",
    "TSE": ".T", "JPX": ".T", "JP": ".T",
    "KRX": ".KS", "KS": ".KS",
    "SGX": ".SI",
    "TWSE": ".TW", "TPEX": ".TWO", "TT": ".TW",
    "NSE": ".NS", "BSE": ".BO",
    "CSE": ".CO", "CPH": ".CO",
    "OMX": ".ST",
    "OSL": ".OL",
    "HEL": ".HE",
    "XETRA": ".DE", "FWB": ".DE", "GR": ".DE",
    "EPA": ".PA", "FP": ".PA",
    "AMS": ".AS",
    "BIT": ".MI", "IM": ".MI",
    "BME": ".MC", "MCE": ".MC",
    "SIX": ".SW",
    "JSE": ".JO",
    "B3": ".SA",
    "BMV": ".MX",
}


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _proposed_symbol(base: str, hints: set) -> Optional[str]:
    """None 表示无 hint / hint 冲突 / 升级后无法回解。"""
    suffixes = {HINT_SUFFIX[h] for h in hints if h in HINT_SUFFIX}
    if len(suffixes) != 1:
        return None
    candidate = base + next(iter(suffixes))
    parsed = normalize_broker_ticker(candidate)
    if parsed is None or not parsed.symbol or parsed.market in (None, "US"):
        return None  # 回解失败或仍被判成美股 → 不动
    return parsed.symbol


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--execute", action="store_true", help="写回（默认 dry-run）")
    args = ap.parse_args()

    data_root = args.data_root.resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # 1) 从定向锚点收集 base -> hints
    hints_by_symbol: Dict[str, set] = {}
    anchor_files: Dict[str, List[Path]] = {}
    for path in (data_root / "F2_anchored").glob("broker_*.json"):
        try:
            env = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for anchor in env.get("entity_anchors") or []:
            md = anchor.get("metadata") or {}
            if md.get("layer") != "targeted_verification":
                continue
            symbol = anchor.get("resolved_symbol") or ""
            if not symbol or "." in symbol:
                continue
            hs = {
                o.get("exchange_hint")
                for o in md.get("occurrences") or []
                if o.get("exchange_hint")
            }
            if hs:
                hints_by_symbol.setdefault(symbol, set()).update(hs)
                anchor_files.setdefault(symbol, []).append(path)

    stats = Counter()
    plan: Dict[str, str] = {}
    for symbol, hs in hints_by_symbol.items():
        proposed = _proposed_symbol(symbol, hs)
        if proposed is None:
            stats["skipped_no_or_conflicting_hint"] += 1
            continue
        plan[symbol] = proposed
        stats["repairable_symbols"] += 1

    print(f"带 hint 的裸码符号: {len(hints_by_symbol)}")
    print(f"可确定性升级: {len(plan)}")
    print(f"跳过（无映射/冲突/回解失败）: {stats['skipped_no_or_conflicting_hint']}")
    print("\n== 升级计划（前 30）==")
    for old, new in sorted(plan.items())[:30]:
        print(f"  {old:<10} → {new}")

    # 2) 统计影响到的 action
    touched_actions = Counter()
    action_files: Dict[str, List[str]] = {}
    for path in (data_root / "F5_executed").glob("bri_*_actions.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for action in doc.get("actions", []):
            target = action.get("target") or {}
            sym = target.get("ticker_normalized") or target.get("ticker") or ""
            if sym in plan:
                touched_actions[sym] += 1
                action_files.setdefault(str(path), []).append(sym)
                if action.get("backtest_result"):
                    stats["already_settled_needs_resettle"] += 1

    print(f"\n受影响 action: {sum(touched_actions.values())} 条，"
          f"分布在 {len(action_files)} 个文件")
    print(f"  其中已结算（需重结算）: {stats['already_settled_needs_resettle']}")
    print("  top:", touched_actions.most_common(12))

    report = {
        "stamp": stamp,
        "symbol_plan": plan,
        "actions_affected": dict(touched_actions),
        "already_settled": stats["already_settled_needs_resettle"],
    }
    out = data_root / "_audit" / f"bare_symbol_repair_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(out, {**report, "status": "planned"})
    print(f"\n计划 → {out}")

    if not args.execute:
        print("\n[dry-run] 未写入任何数据。确认后加 --execute。")
        return 0

    # 3) 写回：F2 锚点 + F5 action target（备份先行）
    backup = data_root / f"symbol_repair.bak-{stamp}"
    (backup / "F2_anchored").mkdir(parents=True, exist_ok=True)
    (backup / "F5_executed").mkdir(parents=True, exist_ok=True)

    f2_written = 0
    for symbol, paths in anchor_files.items():
        if symbol not in plan:
            continue
        for path in set(paths):
            shutil.copy2(path, backup / "F2_anchored" / path.name)
            env = json.loads(path.read_text(encoding="utf-8"))
            changed = False
            for anchor in env.get("entity_anchors") or []:
                md = anchor.get("metadata") or {}
                if md.get("layer") != "targeted_verification":
                    continue
                if anchor.get("resolved_symbol") != symbol:
                    continue
                md["resolved_symbol_before_repair"] = symbol
                md["repair_source"] = "exchange_hint"
                anchor["resolved_symbol"] = plan[symbol]
                changed = True
            if changed:
                _atomic_write(path, env)
                f2_written += 1

    f5_written = 0
    actions_updated = 0
    for key in action_files:
        path = Path(key)
        shutil.copy2(path, backup / "F5_executed" / path.name)
        doc = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for action in doc.get("actions", []):
            target = action.get("target") or {}
            sym = target.get("ticker_normalized") or target.get("ticker") or ""
            if sym not in plan:
                continue
            target["ticker_before_repair"] = sym
            target["ticker"] = plan[sym]
            target["ticker_normalized"] = plan[sym]
            parsed = normalize_broker_ticker(plan[sym])
            if parsed is not None and parsed.market:
                target["market"] = parsed.market
            # 市场变了，旧结算结果按错误公司算的，必须作废重结算
            if action.get("backtest_result"):
                action["backtest_result"] = None
            actions_updated += 1
            changed = True
        if changed:
            _atomic_write(path, doc)
            f5_written += 1

    _atomic_write(out, {
        **report, "status": "applied", "backup": str(backup),
        "f2_files": f2_written, "f5_files": f5_written,
        "actions_updated": actions_updated,
    })
    print(f"\nF2 信封写回 {f2_written}，F5 文件写回 {f5_written}，"
          f"action 更新 {actions_updated}")
    print(f"备份 → {backup}")
    print("\n下一步: python scripts/backfill_f8_backtest.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
