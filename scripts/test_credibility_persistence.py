#!/usr/bin/env python3
"""可信度持续性检验（P2）—— 判据**预先声明**，只读。

检验的产品前提：**信源的历史准确度能否预测其未来准确度。**
做法：在某个时间切分点把每家券商的 action 分成前后两段，用前段的超额胜率排名，
看后段是否延续（前段高于中位数的一组 vs 低于中位数的一组，比较后段超额胜率）。

**判据在看到结果之前就固定**（`docs/specs/2026-07-30-next-actions-plan.md` P2）：

    遍历全部可行切分点：
      * z 稳定同号 且 中位 |z| > 1.5   → 报「初步支持」
      * 否则                            → 报「前提未获支持」

这条纪律来自 07-30 的教训：单一切分点（2025-12）曾给出 +3.6pp / z=1.40 的正面
信号，遍历后符号随机（4 正 3 负）、|z| 全部 <1.4。**单一切口的正面信号不算数。**

口径：
  * 超额胜率 = 实际胜率 − 该组市场构成的期望胜率（剥离市场暴露，非选股能力）
  * 只用 `signal_class == "broker_recommendation"` 且方向非 neutral 的已结算 action
  * 每段每家券商样本数 < `--min-n` 的直接排除，并**报告被排除掉多少**
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# 预声明判据 —— 不得在看到结果后修改
CRITERION_SAME_SIGN = True
CRITERION_MEDIAN_ABS_Z = 1.5


def _market_of(ticker: str) -> str:
    """从代码本身推市场，不信存储的市场戳（它可能是兜底盖的）。"""
    if "." not in ticker:
        return "US"
    suffix = ticker.rsplit(".", 1)[1].upper()
    return {
        "TO": "CA", "V": "CA", "AX": "AU", "L": "UK", "HK": "HK",
        "T": "JP", "KS": "KR", "SI": "SG", "TW": "TW", "TWO": "TW",
        "NS": "IN", "BO": "IN", "CO": "DK", "ST": "SE", "OL": "NO",
        "HE": "FI", "DE": "DE", "PA": "FR", "AS": "NL", "MI": "IT",
        "MC": "ES", "SW": "CH", "JO": "ZA", "SA": "BR", "MX": "MX",
        "SS": "CN", "SZ": "CN", "SH": "CN",
    }.get(suffix, suffix)


def _load(data_root: Path) -> List[dict]:
    rows: List[dict] = []
    for path in glob.glob(str(data_root / "F5_executed" / "bri_*_actions.json")):
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for action in doc.get("actions", []):
            if action.get("signal_class") != "broker_recommendation":
                continue
            result = action.get("backtest_result")
            if not result:
                continue
            direction = action.get("direction")
            if direction not in ("bullish", "bearish"):
                continue
            ret = result.get("return_pct")
            if ret is None:
                continue
            target = action.get("target") or {}
            ticker = target.get("ticker_normalized") or target.get("ticker") or ""
            timing = action.get("execution_timing") or {}
            when = (
                timing.get("intent_published_at")
                or timing.get("action_decision_at")
                or action.get("timestamp")
            )
            if not when or not ticker:
                continue
            try:
                at = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
            except ValueError:
                continue
            rows.append({
                "broker": (action.get("source") or {}).get("creator_id") or "unknown",
                "at": at.replace(tzinfo=None),
                "market": _market_of(ticker),
                "win": (ret > 0) if direction == "bullish" else (ret < 0),
            })
    return rows


def _excess(rows: List[dict], baseline: Dict[str, float]) -> Optional[float]:
    """实际胜率 − 该组市场构成的期望胜率。"""
    if not rows:
        return None
    actual = sum(1 for r in rows if r["win"]) / len(rows)
    expected = sum(baseline.get(r["market"], 0.5) for r in rows) / len(rows)
    return actual - expected


def _two_group_z(a: List[dict], b: List[dict], baseline: Dict[str, float]) -> Optional[float]:
    """两组后段超额胜率之差的 z（正态近似，比例差标准误）。"""
    if len(a) < 2 or len(b) < 2:
        return None
    ea, eb = _excess(a, baseline), _excess(b, baseline)
    if ea is None or eb is None:
        return None
    pa = sum(1 for r in a if r["win"]) / len(a)
    pb = sum(1 for r in b if r["win"]) / len(b)
    se = math.sqrt(pa * (1 - pa) / len(a) + pb * (1 - pb) / len(b))
    if se == 0:
        return None
    return (ea - eb) / se


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--min-n", type=int, default=30,
                    help="每段每家券商的最小样本数")
    args = ap.parse_args()

    rows = _load(args.data_root.resolve())
    print(f"可用已结算 action: {len(rows)}")
    if not rows:
        print("没有可用样本 —— 先跑 settle。")
        return 1

    by_market: Dict[str, List[bool]] = defaultdict(list)
    for r in rows:
        by_market[r["market"]].append(r["win"])
    baseline = {m: sum(w) / len(w) for m, w in by_market.items()}
    print("市场基线胜率:", {k: f"{v:.1%}" for k, v in
                       sorted(baseline.items(), key=lambda x: -len(by_market[x[0]]))[:8]})

    months = sorted({(r["at"].year, r["at"].month) for r in rows})
    print(f"覆盖月份: {months[0]} → {months[-1]}（{len(months)} 个月）")

    results: List[Tuple[str, float, int, int]] = []
    excluded_total = Counter()

    for split in months[1:-1]:                      # 首尾月不能做切分点
        cut = datetime(split[0], split[1], 1)
        early: Dict[str, List[dict]] = defaultdict(list)
        late: Dict[str, List[dict]] = defaultdict(list)
        for r in rows:
            (early if r["at"] < cut else late)[r["broker"]].append(r)

        eligible = [
            b for b in early
            if len(early[b]) >= args.min_n and len(late.get(b, [])) >= args.min_n
        ]
        excluded_total[str(split)] = len(set(early) | set(late)) - len(eligible)
        if len(eligible) < 4:                        # 至少要能分出两组各 2 家
            continue

        scored = sorted(
            eligible, key=lambda b: _excess(early[b], baseline) or 0.0, reverse=True
        )
        half = len(scored) // 2
        top = [r for b in scored[:half] for r in late[b]]
        bottom = [r for b in scored[len(scored) - half:] for r in late[b]]
        z = _two_group_z(top, bottom, baseline)
        if z is None:
            continue
        results.append((f"{split[0]}-{split[1]:02d}", z, len(scored), len(top) + len(bottom)))

    if not results:
        print("\n没有任何切分点满足最小样本要求 —— 前提**当前不可检验**。")
        return 0

    print(f"\n== 全切分点结果（min-n={args.min_n}）==")
    print(f"{'切分点':<10} {'z':>8}  {'合格券商':>8}  {'后段样本':>8}")
    for name, z, n_brokers, n_late in results:
        print(f"{name:<10} {z:>8.2f}  {n_brokers:>8}  {n_late:>8}")

    zs = [z for _, z, _, _ in results]
    positives = sum(1 for z in zs if z > 0)
    median_abs = statistics.median(abs(z) for z in zs)
    same_sign = positives == len(zs) or positives == 0

    print(f"\n切分点数: {len(zs)}   符号: {positives} 正 / {len(zs) - positives} 负")
    print(f"中位 |z|: {median_abs:.2f}")
    print("\n== 判据（**结果揭晓前已声明**）==")
    print(f"  [{'✓' if same_sign else '✗'}] z 稳定同号")
    print(f"  [{'✓' if median_abs > CRITERION_MEDIAN_ABS_Z else '✗'}] "
          f"中位 |z| > {CRITERION_MEDIAN_ABS_Z}")

    if same_sign and median_abs > CRITERION_MEDIAN_ABS_Z:
        print("\n结论：**初步支持** —— 历史超额对未来有预测性。")
    else:
        print("\n结论：**前提未获支持**。这不等于被证伪；按规划，此时应把产品定位"
              "讨论正式提上桌面（从「预测谁更准」转向「审计谁说过什么」）。")

    print("\n被样本量门槛排除的券商数（各切分点）:",
          dict(list(excluded_total.items())[:6]), "…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
