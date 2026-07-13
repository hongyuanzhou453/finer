#!/usr/bin/env python
"""F8 per-action backtest backfill for the real F5 actions.

Pipeline: load data/F5_executed actions -> fetch daily closes from the Yahoo
chart API (no key; symbol mapping .SH->.SS, DXY->DX-Y.NYB) -> evaluate each
directional action independently (backtest/per_action.py) -> write the
per-action BacktestResult back into the authoritative F5 JSON via
TradeActionRepository.update_backtest_result (atomic), plus a batch provenance
artifact under data/F8_metrics/.

SAFE by construction:
  - dry-run by default: fetches prices + evaluates + prints the full plan,
    writes NOTHING under data/ (price cache goes to --cache-dir, default /tmp).
  - --apply backs up data/F5_executed/ first; only sets the backtest_result
    key (atomic replace, siblings preserved); never touches other fields.

Usage:
  python scripts/backfill_f8_backtest.py                # dry-run
  python scripts/backfill_f8_backtest.py --apply        # write back (after confirm)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/zhouhongyuan/Desktop/finer")
sys.path.insert(0, str(ROOT / "src"))

from finer.backtest.per_action import evaluate_action  # noqa: E402
from finer.backtest.yahoo_prices import fetch_daily_closes  # noqa: E402
from finer.schemas.trade_action import TradeAction  # noqa: E402
from finer.services.repository import TradeActionRepository  # noqa: E402

F5_DIR = ROOT / "data" / "F5_executed"
F8_DIR = ROOT / "data" / "F8_metrics"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write back (default: dry-run)")
    ap.add_argument(
        "--cache-dir",
        default="/private/tmp/claude-501/-Users-zhouhongyuan-Desktop-finer/a1dd1110-953f-467c-821b-6fe4cea47c77/scratchpad/yahoo_cache",
        help="price cache dir (kept out of data/ in dry-run)",
    )
    args = ap.parse_args()
    cache_dir = Path(args.cache_dir)

    repo = TradeActionRepository()
    actions: list[tuple[TradeAction, Path]] = []
    for fp in sorted(F5_DIR.glob("*_actions.json")):
        for a in repo.load_actions_from_file(fp):
            actions.append((a, fp))
    print(f"loaded actions: {len(actions)}")

    tickers = sorted({a.target.ticker_normalized or a.target.ticker for a, _ in actions})
    prices: dict[str, list] = {}
    for t in tickers:
        prices[t] = fetch_daily_closes(t, cache_dir)
    covered = {t: len(p) for t, p in prices.items()}
    print(f"price coverage ({len(tickers)} tickers): "
          + json.dumps({t: n for t, n in covered.items()}, ensure_ascii=False))

    plan = []  # (action, result|None, skip_reason|None)
    for a, _fp in actions:
        ticker = a.target.ticker_normalized or a.target.ticker
        result, skip = evaluate_action(a, prices.get(ticker, []))
        plan.append((a, result, skip.reason if skip else None))

    evaluated = [(a, r) for a, r, s in plan if r is not None]
    skipped = Counter(s for _, r, s in plan if s is not None)

    print(f"\nevaluated: {len(evaluated)} | skipped: {dict(skipped)}\n")
    print(f"{'ticker':<14}{'dir':<14}{'entry':<12}{'exit':<12}{'reason':<16}{'net_ret':>8}")
    for a, r in sorted(evaluated, key=lambda x: x[1].return_pct or 0, reverse=True):
        ticker = a.target.ticker_normalized or a.target.ticker
        period = (r.backtest_period or " — ").split(" — ")
        print(
            f"{ticker:<14}{a.direction.value:<14}{period[0]:<12}{period[-1]:<12}"
            f"{r.exit_reason.value:<16}{(r.return_pct or 0) * 100:>7.1f}%"
        )

    wins = sum(1 for _, r in evaluated if (r.return_pct or 0) > 0)
    print(f"\nhit rate: {wins}/{len(evaluated)}"
          f" = {wins / len(evaluated) * 100:.0f}%" if evaluated else "no results")
    by_kol = Counter()
    by_kol_wins = Counter()
    for a, r in evaluated:
        k = a.source.creator_id or "unknown"
        by_kol[k] += 1
        if (r.return_pct or 0) > 0:
            by_kol_wins[k] += 1
    for k in by_kol:
        print(f"  {k}: {by_kol_wins[k]}/{by_kol[k]} settled-wins")

    if not args.apply:
        print("\n[DRY-RUN] nothing written under data/. Re-run with --apply.")
        return 0

    # ---- APPLY ----
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT / "data" / f"F5_executed.bak-{ts}"
    shutil.copytree(F5_DIR, backup)
    print(f"\n[APPLY] backup -> {backup}")

    ok = fail = 0
    for a, r in evaluated:
        if repo.update_backtest_result(a.trade_action_id, r):
            ok += 1
        else:
            fail += 1
    print(f"[APPLY] written back: {ok} | failed: {fail}")

    # provenance artifact
    F8_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "kind": "per_action_backfill",
        "run_at": datetime.now().isoformat(),
        "price_source": "yahoo_chart_api_1y_daily_close",
        "evaluated": len(evaluated),
        "skipped": dict(skipped),
        "results": [
            {
                "trade_action_id": a.trade_action_id,
                "ticker": a.target.ticker_normalized or a.target.ticker,
                "direction": a.direction.value,
                "creator_id": a.source.creator_id,
                **r.model_dump(mode="json"),
            }
            for a, r in evaluated
        ],
    }
    artifact_path = F8_DIR / f"per_action_backfill_{ts}.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    print(f"[APPLY] provenance -> {artifact_path}")

    # persist the price snapshots used, for reproducibility
    snap_dir = ROOT / "data" / "market" / "yahoo_snapshots" / ts
    shutil.copytree(cache_dir, snap_dir)
    print(f"[APPLY] price snapshots -> {snap_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
