#!/usr/bin/env python
"""生成券商/KOL 记分卡（只读）。

薄壳：聚合逻辑在 ``finer.backtest.scorecard``。默认打印到 stdout，
``--out`` 落盘。全程只读 data/，不写任何流水线产物。

    # 券商榜（R6：与 KOL 分开算）
    python scripts/broker_scorecard.py --signal-class broker_recommendation
    # KOL 榜
    python scripts/broker_scorecard.py --signal-class kol_statement
    # 落盘
    python scripts/broker_scorecard.py --signal-class broker_recommendation \\
        --out docs/specs/2026-07-XX-broker-scorecard.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.backtest.scorecard import build_scorecard, render_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signal-class",
        choices=["broker_recommendation", "kol_statement"],
        default=None,
        help="只统计该类信号（R6：券商建议与 KOL 自述仓位不得混榜）。"
             "省略则不过滤，仅作全局体检，不可直接当排名用。",
    )
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--out", type=Path, default=None, help="落盘路径（默认打印）")
    args = parser.parse_args()

    from finer.services.repository import TradeActionRepository

    repo = TradeActionRepository(
        db_path=args.data_root / "cache" / "trade_actions.db",
        action_dir=args.data_root / "F5_executed",
    )
    card = build_scorecard(
        repo.load_all_actions(), signal_class=args.signal_class
    )
    md = render_markdown(card)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
        print(f"wrote {args.out}  "
              f"({card.settled_actions} scored / {card.total_actions} actions)")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
