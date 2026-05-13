#!/usr/bin/env python3
"""Generate Cat Lord F8 fixtures: market_prices.csv, backtest_result.json, equity_curve.csv."""
import csv
import json
import math
from datetime import date, timedelta

FIXTURE_DIR = "tests/fixtures/kol-backtest-mvp/cat_lord"

# --- Trading days (US market, 50 days: 2026-03-02 to 2026-05-08) ---
def us_trading_days(start: date, count: int) -> list[date]:
    days = []
    d = start
    while len(days) < count:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d += timedelta(days=1)
    return days

TRADING_DAYS = us_trading_days(date(2026, 3, 2), 50)

# --- Price patterns (from fixture contract §5.4) ---
# Phases: (start_price, end_price, num_days)
PHASES = {
    "CSIQ": [(12.00, 18.00, 43), (18.00, 15.00, 10), (15.00, 17.00, 12)],
    "LI":   [(28.00, 22.00, 43), (22.00, 24.00, 10), (24.00, 23.00, 12)],
    "TME":  [(11.50, 12.50, 25), (12.50, 12.00, 13), (12.00, 13.00, 27)],
    "TSLA": [(265.00, 220.00, 20), (220.00, 260.00, 25), (260.00, 275.00, 20)],
    "600989":[(30.00, 30.00, 43), (30.00, 26.50, 10), (26.50, 29.00, 12)],
    "NVDA": [(140.00, 155.00, 17), (155.00, 135.00, 18), (135.00, 148.00, 30)],
}

# Starting prices for intraday range calculation
START_PRICES = {"CSIQ": 12.00, "LI": 28.00, "TME": 11.50, "TSLA": 265.00,
                "600989": 30.00, "NVDA": 140.00}

def generate_close_prices(phases):
    closes = []
    for start_p, end_p, n_days in phases:
        step = (end_p - start_p) / n_days
        for i in range(n_days):
            closes.append(round(start_p + step * i, 2))
    return closes

def generate_market_prices():
    """Generate market_prices.csv and return dict of close prices per ticker."""
    all_closes = {}
    for ticker, phases in PHASES.items():
        all_closes[ticker] = generate_close_prices(phases)

    rows = []
    for i, d in enumerate(TRADING_DAYS):
        for ticker in ["CSIQ", "LI", "TME", "TSLA", "600989", "NVDA"]:
            c = all_closes[ticker][i]
            spread = c * 0.02  # ~2% intraday range
            o = round(c + spread * 0.3, 2)
            h = round(c + spread, 2)
            l = round(c - spread, 2)
            vol = {"CSIQ": 5_000_000, "LI": 8_000_000, "TME": 12_000_000,
                   "TSLA": 32_000_000, "600989": 25_000_000, "NVDA": 45_000_000}[ticker]
            rows.append([d.isoformat(), ticker, f"{o:.2f}", f"{h:.2f}",
                        f"{l:.2f}", f"{c:.2f}", vol, f"{c:.2f}"])

    path = f"{FIXTURE_DIR}/market_prices.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "ticker", "open", "high", "low", "close", "volume", "adj_close"])
        w.writerows(rows)
    print(f"Wrote {path} ({len(rows)} rows)")
    return all_closes

# --- Backtest ---
TRADES = [
    {"content_id": "c_002_buy_li", "ticker": "LI", "action": "close_long",
     "direction": "bearish", "exec_date": "2026-03-16", "published_at": "2026-03-15T10:00:00+08:00"},
    {"content_id": "c_004_hold_tme", "ticker": "TME", "action": "hold",
     "direction": "bullish", "exec_date": "2026-03-23", "published_at": "2026-03-20T14:00:00+08:00"},
    {"content_id": "c_007_mixed", "ticker": "LI", "action": "close_long",
     "direction": "bearish", "exec_date": "2026-04-13", "published_at": "2026-04-10T10:30:00+08:00"},
    {"content_id": "c_007_mixed", "ticker": "CSIQ", "action": "long",
     "direction": "bullish", "exec_date": "2026-04-13", "published_at": "2026-04-10T10:30:00+08:00"},
    {"content_id": "c_008_close_li", "ticker": "LI", "action": "close_long",
     "direction": "bearish", "exec_date": "2026-04-16", "published_at": "2026-04-15T16:00:00+08:00"},
    {"content_id": "c_010_multi_intent", "ticker": "CSIQ", "action": "long",
     "direction": "bullish", "exec_date": "2026-04-28", "published_at": "2026-04-25T20:00:00+08:00"},
    {"content_id": "c_010_multi_intent", "ticker": "TSLA", "action": "long",
     "direction": "bullish", "exec_date": "2026-04-28", "published_at": "2026-04-25T20:00:00+08:00"},
]

POSITION_SIZE = 5000  # 5% of 100,000

def run_backtest(all_closes: dict):
    """Run backtest and generate F8 fixtures."""
    date_idx = {d.isoformat(): i for i, d in enumerate(TRADING_DAYS)}
    n_days = len(TRADING_DAYS)

    # Parse trade execution dates
    for t in TRADES:
        t["exec_idx"] = date_idx[t["exec_date"]]
        t["entry_price"] = all_closes[t["ticker"]][t["exec_idx"]]

    # Determine close index for each trade
    for i, t in enumerate(TRADES):
        if t["action"] == "hold":
            t["close_idx"] = n_days - 1  # held to end
        elif t["action"] == "close_long":
            # Close at next trade's exec date for same ticker, or end
            t["close_idx"] = n_days - 1
            for j in range(i + 1, len(TRADES)):
                if TRADES[j]["ticker"] == t["ticker"] and TRADES[j]["action"] == "close_long":
                    t["close_idx"] = TRADES[j]["exec_idx"]
                    break
        else:  # long (open)
            t["close_idx"] = n_days - 1  # still open at end

    # Build active positions per day
    equity_curve = []
    cash = 100_000.0
    total_pnl = 0.0
    wins = 0
    losses = 0
    max_equity = 100_000.0
    max_drawdown = 0.0

    for day_i in range(n_days):
        d_str = TRADING_DAYS[day_i].isoformat()

        # Process trades that execute today
        for t in TRADES:
            if t["exec_idx"] == day_i:
                cash -= POSITION_SIZE

        # Calculate positions value
        positions_value = 0.0
        for t in TRADES:
            if t["exec_idx"] <= day_i <= t["close_idx"]:
                current_price = all_closes[t["ticker"]][day_i]
                if t["action"] in ("long", "hold"):
                    # Long position: value = shares * current_price
                    shares = POSITION_SIZE / t["entry_price"]
                    positions_value += shares * current_price
                elif t["action"] == "close_long":
                    # Short position simulation: gain = entry - current
                    gain = POSITION_SIZE * (1 - current_price / t["entry_price"])
                    positions_value += POSITION_SIZE + gain

            # Process close: return cash
            if t["close_idx"] == day_i and t["action"] == "close_long":
                entry_p = t["entry_price"]
                exit_p = all_closes[t["ticker"]][day_i]
                pnl = POSITION_SIZE * (exit_p - entry_p) / entry_p
                cash += POSITION_SIZE + pnl
                total_pnl += pnl
                if pnl >= 0:
                    wins += 1
                else:
                    losses += 1

        equity = cash + positions_value
        equity_curve.append({
            "date": d_str,
            "equity": round(equity, 2),
            "benchmark": round(100_000.0 * (1 + 0.001 * day_i), 2),  # simple benchmark
            "cash": round(cash, 2),
            "positions_value": round(positions_value, 2),
        })

        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity
        max_drawdown = max(max_drawdown, dd)

    # Compute final P&L for open trades at end
    final_equity = equity_curve[-1]["equity"]
    return_pct = (final_equity - 100_000) / 100_000 * 100
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0

    # Sharpe ratio (simplified: daily returns)
    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i-1]["equity"]
        curr = equity_curve[i]["equity"]
        daily_returns.append((curr - prev) / prev)
    mean_ret = sum(daily_returns) / len(daily_returns) if daily_returns else 0
    std_ret = (sum((r - mean_ret)**2 for r in daily_returns) / len(daily_returns))**0.5 if daily_returns else 1
    sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0

    # Write backtest result
    result = {
        "total_trades": 7,
        "return_pct": round(return_pct, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "sharpe_ratio": round(sharpe, 4),
        "win_rate": round(win_rate, 4),
        "backtest_period": "2026-03-02 to 2026-05-08",
        "initial_capital": 100000,
        "trading_days": 50,
        "commission_pct": 0,
        "slippage_pct": 0,
        "max_holding_days": 30,
    }
    result_path = f"{FIXTURE_DIR}/F8/expected_backtest_result.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {result_path}")

    # Write equity curve
    curve_path = f"{FIXTURE_DIR}/F8/expected_equity_curve.csv"
    with open(curve_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "equity", "benchmark", "cash", "positions_value"])
        w.writeheader()
        w.writerows(equity_curve)
    print(f"Wrote {curve_path} ({len(equity_curve)} rows)")

    return result

if __name__ == "__main__":
    all_closes = generate_market_prices()
    result = run_backtest(all_closes)
    print(f"\nBacktest result: {json.dumps(result, indent=2)}")
