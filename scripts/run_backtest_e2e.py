"""E2E Backtest Script — Load canonical F5 actions from data/review/ + market prices.

Reads TradeActions from:  data/review/{kol_id}/F5_actions/*.actions.json
Uses market prices from:  tests/fixtures/kol-backtest-mvp/{kol_id}/market_prices.csv
Produces:
    data/review/{kol_id}/F8_backtest/backtest_result.json
    data/review/{kol_id}/F8_backtest/equity_curve.csv
    data/review/{kol_id}/F8_backtest/trades.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from finer.backtest.engine import BacktestEngine, BacktestConfig
from finer.backtest.validators import validate_canonical_action

FIXTURES = ROOT / "tests" / "fixtures" / "kol-backtest-mvp"
DATA_REVIEW = ROOT / "data" / "review"

_DIRECTION_MAP = {"bullish": "bullish", "bearish": "bearish"}
_ACTION_TYPE_MAP = {
    "long": "long", "short": "short",
    "close_long": "close_long", "close_short": "close_short",
    "buy_call": "buy_call", "buy_put": "buy_put",
    "buy_and_hold": "long",
}


def _raw_action_to_record(action_dict: dict, kol_id: str) -> dict | None:
    """Convert raw canonical TradeAction JSON to backtest engine record."""
    direction = action_dict.get("direction", "")
    if direction not in _DIRECTION_MAP:
        return None

    action_chain = action_dict.get("action_chain", [])
    if not action_chain:
        return None

    primary = action_chain[0]
    action_type = _ACTION_TYPE_MAP.get(primary.get("action_type", ""))
    if action_type is None:
        return None

    # Timing: prefer execution_timing.action_executable_at (canonical path)
    exec_timing = action_dict.get("execution_timing") or {}
    ts = exec_timing.get("action_executable_at") or action_dict.get("timestamp", "")
    ts = re.sub(r'[+-]\d{2}:\d{2}$', '', ts)
    if ts.endswith("Z"):
        ts = ts[:-1]

    target = action_dict.get("target") or {}
    ticker = target.get("ticker_normalized") or target.get("ticker", "")

    source = action_dict.get("source") or {}
    action_kol_id = source.get("creator_id") or kol_id

    return {
        "timestamp": ts,
        "ticker": ticker,
        "direction": _DIRECTION_MAP[direction],
        "action_type": action_type,
        "trade_action_id": action_dict.get("trade_action_id", ""),
        "kol_id": action_kol_id,
        # --- trace fields (R4-A) ---
        "intent_id": action_dict.get("intent_id"),
        "policy_id": action_dict.get("policy_id"),
        "evidence_span_ids": action_dict.get("evidence_span_ids") or [],
    }


def load_canonical_f5_actions(kol_id: str) -> list[dict]:
    """Load canonical TradeActions from data/review/{kol_id}/F5_actions/.

    Filters to canonical_trace_status == "canonical" and backtestable directions.
    """
    f5_dir = DATA_REVIEW / kol_id / "F5_actions"
    if not f5_dir.exists():
        print(f"  [BLOCKER] F5_actions directory not found: {f5_dir}")
        return []

    all_records = []
    total_canonical = 0
    total_skipped = 0

    for f in sorted(f5_dir.glob("*.actions.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            continue

        for action_idx, action_dict in enumerate(raw):
            if not action_dict:
                continue
            # Gate: only process canonical actions
            if action_dict.get("canonical_trace_status") != "canonical":
                continue
            total_canonical += 1

            # Validate canonical fields using shared validator
            try:
                validate_canonical_action(action_dict, action_idx)
            except Exception as exc:
                total_skipped += 1
                print(f"  [SKIP] Canonical validation failed: {exc}")
                continue

            record = _raw_action_to_record(action_dict, kol_id)
            if record is not None:
                all_records.append(record)
            else:
                total_skipped += 1
                direction = action_dict.get("direction", "?")
                atype = (action_dict.get("action_chain") or [{}])[0].get("action_type", "?")
                print(f"  [SKIP] Non-backtestable canonical: {direction}/{atype}")

    print(f"  Found {total_canonical} canonical actions, "
          f"{len(all_records)} backtestable, {total_skipped} skipped")
    return all_records


def run_kol_backtest(kol_id: str) -> bool:
    """Run backtest for a single KOL. Returns True on success."""
    print(f"\n{'='*60}")
    print(f"Running backtest for: {kol_id}")
    print(f"{'='*60}")

    # Step 1: Load canonical F5 actions from data/review/
    actions = load_canonical_f5_actions(kol_id)
    if not actions:
        print(f"  [BLOCKER] No backtestable canonical actions for {kol_id}")
        return False

    # Print action timeline
    actions.sort(key=lambda a: a["timestamp"])
    print(f"\n  Action timeline:")
    for a in actions:
        print(f"    {a['timestamp'][:10]} | {a['ticker']:>10} | "
              f"{a['direction']:>8} | {a['action_type']}")

    # Step 2: Load market prices from fixtures
    _KOL_TO_FIXTURE = {
        "kol_cat_lord_fire": "cat_lord",
        "trader_ji": "trader_ji",
    }
    fixture_name = _KOL_TO_FIXTURE.get(kol_id, kol_id)
    price_csv = FIXTURES / fixture_name / "market_prices.csv"
    if not price_csv.exists():
        print(f"  [ERROR] No market_prices.csv found at {price_csv}")
        return False

    price_data = pd.read_csv(price_csv, dtype={"ticker": str})
    price_data["date"] = pd.to_datetime(price_data["date"])
    print(f"\n  Market prices: {len(price_data)} rows, "
          f"tickers: {sorted(price_data['ticker'].unique())}")
    print(f"  Date range: {price_data['date'].min().date()} → {price_data['date'].max().date()}")

    # Step 3: Run backtest
    config = BacktestConfig(initial_capital=100000.0)
    engine = BacktestEngine(config)
    result = engine.run_backtest(actions, price_data)

    print(f"\n  === Backtest Results ===")
    print(f"  Backtest ID:      {result.backtest_id}")
    print(f"  Period:           {result.start_date.date()} → {result.end_date.date()}")
    print(f"  Total return:     {result.total_return*100:.2f}%")
    print(f"  Annualized:       {result.annualized_return*100:.2f}%")
    print(f"  Sharpe ratio:     {result.sharpe_ratio:.3f}")
    print(f"  Max drawdown:     {result.max_drawdown*100:.2f}%")
    print(f"  Total trades:     {result.total_trades}")
    print(f"  Win rate:         {result.win_rate*100:.1f}%")
    print(f"  Avg holding days: {result.avg_holding_days:.1f}")

    # Step 4: Save outputs
    out_dir = DATA_REVIEW / kol_id / "F8_backtest"
    out_dir.mkdir(parents=True, exist_ok=True)

    # backtest_result.json
    result_dict = result.model_dump(mode="json")
    result_dict.pop("portfolio_snapshots", None)
    result_path = out_dir / "backtest_result.json"
    result_path.write_text(
        json.dumps(result_dict, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  Saved: {result_path}")

    # equity_curve.csv
    equity_rows = []
    for snap in result.portfolio_snapshots:
        equity_rows.append({
            "date": snap.date.isoformat(),
            "total_value": snap.total_value,
            "cash": snap.cash,
            "positions_value": snap.positions_value,
            "cumulative_return": snap.cumulative_return,
            "drawdown": snap.current_drawdown,
            "num_positions": snap.num_positions,
        })
    equity_df = pd.DataFrame(equity_rows)
    equity_path = out_dir / "equity_curve.csv"
    equity_df.to_csv(equity_path, index=False)
    print(f"  Saved: {equity_path}  ({len(equity_df)} rows)")

    # trades.json
    trades_rows = []
    for t in result.trades:
        trades_rows.append({
            "trade_id": t.trade_id,
            "ticker": t.ticker,
            "side": t.side.value,
            "entry_date": t.entry_date.isoformat(),
            "entry_price": round(t.entry_price, 4),
            "exit_date": t.exit_date.isoformat(),
            "exit_price": round(t.exit_price, 4),
            "net_pnl": round(t.net_pnl, 2),
            "return_pct": round(t.return_pct * 100, 2),
            "exit_reason": t.exit_reason.value,
            "holding_days": t.holding_days,
            "trade_action_id": t.trade_action_id,
            "kol_id": t.kol_id,
            "intent_id": t.intent_id,
            "policy_id": t.policy_id,
            "evidence_span_ids": t.evidence_span_ids,
        })
    trades_path = out_dir / "trades.json"
    trades_path.write_text(
        json.dumps(trades_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Saved: {trades_path}  ({len(trades_rows)} trades)")

    return True


def main():
    DATA_REVIEW.mkdir(parents=True, exist_ok=True)

    kols = ["kol_cat_lord_fire", "trader_ji"]
    results = {}

    for kol_id in kols:
        f5_dir = DATA_REVIEW / kol_id / "F5_actions"
        if not f5_dir.exists():
            print(f"\n[BLOCKER] {kol_id}: F5_actions directory missing at {f5_dir}")
            results[kol_id] = "BLOCKER"
            continue
        results[kol_id] = "OK" if run_kol_backtest(kol_id) else "FAILED"

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for kol_id, status in results.items():
        print(f"  {kol_id}: {status}")

    has_blocker = any(v == "BLOCKER" for v in results.values())
    all_ok = all(v == "OK" for v in results.values())

    if has_blocker:
        print("\n[RESULT] BLOCKED — some KOLs missing F5_actions")
        return 2
    elif all_ok:
        print("\n[RESULT] ALL PASSED")
        return 0
    else:
        print("\n[RESULT] SOME FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
