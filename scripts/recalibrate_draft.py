#!/usr/bin/env python3
"""一次性离线重算 pairs_draft.jsonl 的 chosen（用修复后的 calibrate，零 API 成本）。

根因1 修复后，ungrounded committal 的 chosen.ticker 不再透传基座幻觉值（如把泡泡玛特
填成 002857.SZ），而是置 UNRESOLVED 并把基座原始猜测留到 meta.ticker_guess。本脚本对
当前已生成的 draft 离线重算——draft 已存 rejected 原文，source_candidates 提供 evidence_text，
不需要重新调用 DashScope。

**不覆盖原文件**：写 pairs_draft.recalibrated.jsonl + 控制台 diff 摘要，供人工对比确认后替换。

用法:
    python scripts/recalibrate_draft.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_rejected import UNRESOLVED_TICKER, calibrate  # noqa: E402
from eval_compare import parse_output  # noqa: E402

DRAFT = Path("data/dpo/hq_v1/pairs_draft.jsonl")
SOURCE = Path("data/dpo/hq_v1/source_candidates.jsonl")
OUT = Path("data/dpo/hq_v1/pairs_draft.recalibrated.jsonl")


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    if not DRAFT.exists():
        print(f"[error] 缺 {DRAFT}", file=sys.stderr)
        return 1
    draft = load_jsonl(DRAFT)
    evidence_by_id = {r["id"]: r.get("evidence_text", "") for r in load_jsonl(SOURCE)}

    out_rows: List[Dict[str, Any]] = []
    changed_ticker = 0      # chosen.ticker 由具体值 → UNRESOLVED
    guess_kept = 0          # 留存 meta.ticker_guess
    missing_evidence = 0
    examples: List[str] = []

    for p in draft:
        meta = dict(p.get("meta") or {})
        pid = meta.get("passage_id")
        evidence = evidence_by_id.get(pid)
        if evidence is None:
            missing_evidence += 1
            out_rows.append(p)  # 无 evidence 原样保留，不臆改
            continue

        old_ticker = str((parse_output(p.get("chosen")) or {}).get("ticker", ""))
        new_chosen = calibrate(p.get("rejected", ""), evidence)
        new_ticker = str(new_chosen.get("ticker", ""))

        if new_ticker == UNRESOLVED_TICKER and old_ticker != UNRESOLVED_TICKER:
            changed_ticker += 1
            guess = str((parse_output(p.get("rejected")) or {}).get("ticker", "")).strip()
            if guess:
                meta["ticker_guess"] = guess
                guess_kept += 1
            if len(examples) < 8:
                examples.append(f"  {pid}: {old_ticker!r} → UNRESOLVED (meta.ticker_guess={guess!r})")

        out_rows.append({
            "prompt": p.get("prompt"),
            "chosen": json.dumps(new_chosen, ensure_ascii=False),
            "rejected": p.get("rejected"),
            "meta": meta,
        })

    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
        encoding="utf-8",
    )
    print(f"读入 draft {len(draft)} 条；evidence 缺失 {missing_evidence} 条")
    print(f"chosen.ticker 由具体代码 → UNRESOLVED: {changed_ticker} 条（含 {guess_kept} 条留存 meta.ticker_guess）")
    if examples:
        print("样例：")
        print("\n".join(examples))
    print(f"\n已写 {OUT}")
    print("⚠ 未覆盖原 pairs_draft.jsonl。对比确认后由你手动替换（批量重写数据需你拍板）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
