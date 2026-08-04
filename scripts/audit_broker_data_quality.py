#!/usr/bin/env python3
"""券商数据质量审计器（D1 反向使用，只读）。

来历：CRD-4 可行性判定（`2026-08-02-crd4-feasibility.md` §3.1）中，
「看多但目标价低于股价」作为**指控**检测器无效（6 条核验 0 条券商自相矛盾），
但它在同一批样本里找出了 **2 个我们自己的数据缺陷**：

  * 高盛 MSFT 目标价 $55（收盘 $457）—— T3 把别的数字抽成了目标价
  * 摩根大通 ``LI`` 挂了 NIO 的报告 —— ticker 归属错误

因此反向落地为**对内**审计器：零指控风险，产出的是「我们的抽取哪里错了」，
直接服务审计优先的定位。两类检查：

  Q1 目标价量级不合理
     bullish 且 target/close < 0.5，或 bearish 且 target/close > 2.0。
     阈值实测校准：0.5 恰好分开真缺陷（MSFT 0.12 / LI 0.43）与正常的
     「股价涨过目标价」（Murata 0.69、AVAV 0.97 等全部 > 0.6）。

  Q3 report_date 时间戳合理性
     未来日期（> 今天 + 3 天宽限）或早于语料起点（< 2020-01-01）。
     来历：/discover 页如实显示了摩根士丹利一条 2026-12-16 的记录窗口
     （T3 从报告排版抽出的未来日期，沿 F0→F5 一路传播）。

  Q2 thesis 与 target 归属存疑
     thesis 里出现**已知另一家公司**的名字、且 target 自己的名字/代码在
     thesis 里完全缺席。第二个条件是关键——2026-08-03 实测：只查「提到了
     别家」会把港股双重上市（9866.HK 就是蔚来）全部误报，10 条里 9 条是
     误报；加上「自己缺席」后误报清零。名字表只收录高辨识度公司，宁缺勿滥。

只读、只报告，不改任何流水线数据。发现项落 ``data/_audit/``。

    python scripts/audit_broker_data_quality.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

BULL_MAX_RATIO = 0.5   # bullish：目标价低于现价一半 → 量级可疑
BEAR_MIN_RATIO = 2.0   # bearish：目标价高于现价两倍 → 量级可疑

#: Q2 的公司名 → 该公司的合法代码 base 集（含各交易所上市形式）。
#: 只收录辨识度极高、不会作为普通词出现的名字；表小是特性不是缺陷。
KNOWN_COMPANIES: Dict[str, frozenset] = {
    "NIO": frozenset({"NIO", "9866"}),
    "Li Auto": frozenset({"LI", "2015"}),
    "XPeng": frozenset({"XPEV", "9868"}),
    "BYD": frozenset({"1211", "002594", "BYDDY", "BYDDF"}),
    "Tesla": frozenset({"TSLA"}),
    "Microsoft": frozenset({"MSFT"}),
    "Nvidia": frozenset({"NVDA"}),
    "Alibaba": frozenset({"BABA", "9988"}),
    "Tencent": frozenset({"0700", "700", "TCEHY"}),
    "Meituan": frozenset({"3690", "MPNGY"}),
}
_NAME_PATTERNS = {
    name: re.compile(r"\b" + re.escape(name) + r"(?:'s)?\b")
    for name in KNOWN_COMPANIES
}


def _latest_snapshot_dir(data_root: Path) -> Optional[Path]:
    dirs = sorted(glob.glob(str(data_root / "market" / "yahoo_snapshots" / "*")))
    return Path(dirs[-1]) if dirs else None


def _price_series_index(snap_dir: Path) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = {}
    for p in snap_dir.glob("*.json"):
        base = p.name
        ticker = base.rsplit("-", 3)[0] if base.count("-") >= 3 else base.split("-")[0]
        index.setdefault(ticker, []).append(p)
    return index


def _close_series(paths: List[Path]) -> Tuple[Optional[str], Dict[date, float]]:
    for p in sorted(paths, reverse=True):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = (doc.get("chart") or {}).get("result") or []
        if not results:
            continue
        meta = results[0].get("meta") or {}
        stamps = results[0].get("timestamp") or []
        closes = ((results[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        series = {
            datetime.fromtimestamp(t, timezone.utc).date(): c
            for t, c in zip(stamps, closes)
            if c is not None
        }
        if series:
            return meta.get("currency"), series
    return None, {}


def _close_on_or_before(series: Dict[date, float], day: date, lookback: int = 5) -> Optional[float]:
    for off in range(lookback + 1):
        close = series.get(day - timedelta(days=off))
        if close is not None:
            return close
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    args = ap.parse_args()
    data_root = args.data_root.resolve()

    snap_dir = _latest_snapshot_dir(data_root)
    price_index = _price_series_index(snap_dir) if snap_dir else {}
    print(f"价格快照: {snap_dir.name if snap_dir else '无'}（{len(price_index)} ticker）")

    stats = Counter()
    q1_findings: List[dict] = []
    q2_findings: List[dict] = []
    q3_findings: List[dict] = []
    today = date.today()
    q3_future_limit = today + timedelta(days=3)
    q3_past_limit = date(2020, 1, 1)
    series_cache: Dict[str, Tuple[Optional[str], Dict[date, float]]] = {}

    for path in glob.glob(str(data_root / "F3_intents" / "bri_*.json")):
        try:
            intent = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stats["scanned"] += 1
        md = intent.get("metadata") or {}
        ticker = (intent.get("target_symbol") or "").strip()
        base = ticker.split(".")[0].upper()
        direction = intent.get("direction")

        # ── Q1 目标价量级 ────────────────────────────────────────────
        tp = intent.get("target_price") or {}
        value = tp.get("value")
        report_date = md.get("report_date")
        if value and report_date and direction in ("bullish", "bearish") and ticker:
            if ticker not in series_cache:
                series_cache[ticker] = _close_series(price_index.get(ticker, []))
            currency, series = series_cache[ticker]
            tp_cur = (tp.get("currency") or "").upper()
            # GBp（便士）与 GBP（英镑）差 100 倍，大小写折叠会吞掉这个区别；
            # 南非 ZAc/ZAR、以色列 ILA/ILS 同理。显式换算，不认等价。
            scale = 1.0
            if currency in ("GBp", "ZAc", "ILA") and tp_cur in ("GBP", "ZAR", "ILS"):
                scale = 0.01
                currency_ok = True
            else:
                currency_ok = not currency or not tp_cur or currency.upper() == tp_cur
            if series and currency_ok:
                try:
                    close = _close_on_or_before(series, date.fromisoformat(report_date))
                except ValueError:
                    close = None
                if close:
                    close *= scale
                    stats["q1_comparable"] += 1
                    ratio = value / close
                    suspicious = (
                        (direction == "bullish" and ratio < BULL_MAX_RATIO)
                        or (direction == "bearish" and ratio > BEAR_MIN_RATIO)
                    )
                    if suspicious:
                        stats["q1_flagged"] += 1
                        q1_findings.append({
                            "intent_id": intent.get("intent_id"),
                            "broker": intent.get("creator_id"),
                            "ticker": ticker,
                            "direction": direction,
                            "target_price": value,
                            "close_on_report_date": round(close, 2),
                            "ratio": round(ratio, 3),
                            "report_date": report_date,
                            "thesis_head": (md.get("key_thesis") or "")[:140],
                        })

        # ── Q3 report_date 合理性 ────────────────────────────────────
        if report_date:
            stats["q3_comparable"] += 1
            try:
                rd = date.fromisoformat(report_date)
            except ValueError:
                rd = None
            if rd is None or rd > q3_future_limit or rd < q3_past_limit:
                stats["q3_flagged"] += 1
                q3_findings.append({
                    "intent_id": intent.get("intent_id"),
                    "broker": intent.get("creator_id"),
                    "ticker": ticker,
                    "report_date": report_date,
                    "reason": "unparseable" if rd is None else (
                        "future" if rd > q3_future_limit else "too_old"
                    ),
                })

        # ── Q2 thesis 归属 ───────────────────────────────────────────
        thesis = md.get("key_thesis") or ""
        target_name = (intent.get("target_name") or "").strip()
        if thesis and ticker:
            # 只在 target 与被提及公司**双双**在名录内时判定——第一版只查
            # 「提到了别家」，被跨语言（中文 target_name vs 英文 thesis）打出
            # 9/11 误报。名录内才有英文名可查「自己是否缺席」。
            target_known = next(
                (n for n, bases in KNOWN_COMPANIES.items() if base in bases), None
            )
            if target_known is not None:
                stats["q2_comparable"] += 1
                self_mentioned = bool(_NAME_PATTERNS[target_known].search(thesis))
                if not self_mentioned:
                    for name, legit_bases in KNOWN_COMPANIES.items():
                        if name == target_known or base in legit_bases:
                            continue
                        if _NAME_PATTERNS[name].search(thesis):
                            stats["q2_flagged"] += 1
                            q2_findings.append({
                                "intent_id": intent.get("intent_id"),
                                "broker": intent.get("creator_id"),
                                "ticker": ticker,
                                "target_name": target_name,
                                "thesis_names": name,
                                "thesis_head": thesis[:140],
                            })
                            break

    print(f"\n扫描 bri intent: {stats['scanned']}")
    print(f"Q1 目标价量级  可比对 {stats['q1_comparable']}  可疑 {stats['q1_flagged']}")
    print(f"Q2 thesis 归属  可比对 {stats['q2_comparable']}  可疑 {stats['q2_flagged']}")
    print(f"Q3 时间戳合理  可比对 {stats['q3_comparable']}  可疑 {stats['q3_flagged']}")

    for tag, findings in (("Q1", q1_findings), ("Q2", q2_findings), ("Q3", q3_findings)):
        print(f"\n== {tag} 发现 ==")
        for f in findings[:15]:
            if tag == "Q1":
                print(f"  {f['broker']} {f['ticker']} {f['direction']}  "
                      f"目标价 {f['target_price']} vs 收盘 {f['close_on_report_date']} "
                      f"(ratio {f['ratio']})")
            elif tag == "Q2":
                print(f"  {f['broker']} target={f['ticker']}({f['target_name']}) "
                      f"但 thesis 讲 {f['thesis_names']}: {f['thesis_head'][:70]}…")
            else:
                print(f"  {f['broker']} {f['ticker']}  report_date={f['report_date']} "
                      f"({f['reason']})  {f['intent_id']}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = data_root / "_audit" / f"broker_data_quality_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "stats": dict(stats),
        "q1_implausible_target": q1_findings,
        "q2_thesis_ticker_mismatch": q2_findings,
        "q3_implausible_report_date": q3_findings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)
    print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
