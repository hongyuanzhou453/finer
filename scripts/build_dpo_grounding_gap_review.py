#!/usr/bin/env python3
"""从 DPO HQ cleaned pairs 的 grounding 失败中，构建 registry 补录待核验清单.

背景：``validate_dpo_hq`` 的 registry-aware grounding（见 ``finer.ml.rewards``）把
committal 且 ticker 不可溯的 chosen 判为 error。其中一部分是 ``ENTITY_REGISTRY``
覆盖缺口（公司真实、可交易，但 registry 没有该 alias→code）。本脚本把这类候选
连证据抽出，供**逐条人工核验**（复用 F2 gap-review 纪律：禁批量盲插）。

它只产出候选清单，**不改 registry**。核验通过的条目由人工/后续 apply 步落库。

用法:
    python scripts/build_dpo_grounding_gap_review.py \
        --pairs data/dpo/hq_v1/pairs_cleaned.jsonl \
        --out data/skills/f2-entity-anchoring/dpo_grounding_gaps.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from finer.ml.rewards import is_committal, parse_output, ticker_grounded  # noqa: E402
from finer.services.annotation_store import evidence_from_prompt  # noqa: E402

# 明确非 registry 候选的占位/畸形 ticker（category A：改判 abstention 或剔除，不进 registry）
JUNK_TICKERS = {
    "NONE", "", "UNRESOLVED", "UNSPECIFIED", "UNSP", "UNSPECIFIED.",
    "未明确", "未指定", "N/A", "NA", "XAU", "XAUUSD",
}


def _infer_market(ticker: str) -> str:
    up = ticker.strip().upper()
    if up.endswith((".SZ", ".SH", ".SS", ".BJ")):
        return "CN"
    if up.endswith(".HK"):
        return "HK"
    if up.replace(".", "").isascii() and any(c.isalpha() for c in up) and "." not in up and up.isalpha():
        return "US?"
    if not up.isascii():
        return "?"  # 中文名当 ticker（如 速腾聚创）——需查代码
    return "?"


def _is_junk(ticker: str) -> bool:
    up = ticker.strip().upper()
    if up in JUNK_TICKERS:
        return True
    # 多代码塞一字段 / 带括号说明 = 畸形
    return any(ch in ticker for ch in ("(", "（", ",", "，", "和")) and (any(c.isdigit() for c in ticker) or "指数" in ticker)


def build(pairs_path: Path) -> List[Dict[str, Any]]:
    by_ticker: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"occurrences": 0, "passage_ids": [], "evidence": [], "rationales": []}
    )
    for line in pairs_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        chosen = parse_output(row.get("chosen"))
        if not chosen or not is_committal(chosen):
            continue
        ticker = str(chosen.get("ticker", "")).strip()
        evidence = evidence_from_prompt(row.get("prompt", ""))
        if ticker_grounded(ticker, evidence):
            continue
        if _is_junk(ticker):
            continue  # category A：非 registry 候选
        meta = row.get("meta") or {}
        agg = by_ticker[ticker]
        agg["occurrences"] += 1
        pid = meta.get("passage_id")
        if pid:
            agg["passage_ids"].append(pid)
        agg["evidence"].append(evidence[:180].replace("\n", " "))
        rat = (chosen.get("rationale") or "")[:110].replace("\n", " ")
        agg["rationales"].append(rat)

    out: List[Dict[str, Any]] = []
    for ticker, agg in sorted(by_ticker.items(), key=lambda kv: -kv[1]["occurrences"]):
        out.append(
            {
                "ticker_claimed": ticker,
                "market_inferred": _infer_market(ticker),
                "occurrences": agg["occurrences"],
                "passage_ids": agg["passage_ids"],
                "evidence_snippet": agg["evidence"][0] if agg["evidence"] else "",
                "rationale_snippet": agg["rationales"][0] if agg["rationales"] else "",
                # 人工核验后填写：
                "verified_alias": None,      # 证据中出现、要加入 registry 的公司名
                "verified_ticker": None,     # 核验后的真实代码（.市场后缀）
                "verdict": "pending",        # insert | reject | relabel
                "reject_reason": None,
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = build(Path(args.pairs))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    print(f"registry 补录候选: {len(rows)} 个唯一 ticker（committal+未grounded，已排除 junk/畸形）")
    print(f"wrote {out_path}\n")
    print(f"{'ticker':<16}{'mkt':<6}{'n':<4}{'rationale/evidence 片段'}")
    print("-" * 100)
    for r in rows:
        hint = (r["rationale_snippet"] or r["evidence_snippet"])[:70]
        print(f"{r['ticker_claimed']:<16}{r['market_inferred']:<6}{r['occurrences']:<4}{hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
