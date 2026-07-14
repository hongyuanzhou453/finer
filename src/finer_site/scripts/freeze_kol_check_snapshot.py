#!/usr/bin/env python3
"""Freeze + anonymize real F5 canonical TradeActions into a static snapshot for the
finer_site retail demo. Reads data/F5_executed/*.json (non-bak), keeps real
tickers/timing/evidence/backtest, and relabels the KOL identity.

Output: src/finer_site/src/demo/kol-check/data.json  (shape: KOLRadarData + sidecars)
"""
import json
import os
import glob
from collections import Counter

# repo root = this file's dir (src/finer_site/scripts) up three levels
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC_DIR = os.path.join(REPO, "data", "F5_executed")
OUT = os.path.join(REPO, "src", "finer_site", "src", "demo", "kol-check", "data.json")

REAL_CREATOR = "trader_ji"

# ---- anonymized identity (single constant block; easy to rename) -------------
ANON = {
    "kolId": "kol-anon-tech",
    "name": "科技成长派 · 匿名KOL",
    "handle": "anon-J",
    "style": "个股短线 · 科技成长",
    "platform": "社媒（视频/直播转写）",
    "specialties": ["美股科技", "港股互联网", "A股半导体"],
}

DIR_LABEL = {
    "bullish": "看多", "bearish": "看空", "neutral": "中性",
    "watchlist": "观察", "risk_warning": "风险",
}
HINT_ZH = {
    "watch_or_no_trade": "观望·不交易",
    "avoid_or_watch_risk": "规避·提示风险",
    "watch_only": "仅观察",
    "accumulate": "逢低吸纳", "add_position": "加仓", "add": "加仓",
    "reduce_position": "减仓", "reduce": "减仓",
    "close_position": "平仓", "close_long": "平多", "close_short": "平空",
    "open_long": "做多", "go_long": "做多", "buy": "买入",
    "open_short": "做空", "go_short": "做空", "sell": "卖出",
    "hold": "持有", "hold_position": "持有", "buy_and_hold": "买入持有",
}
HORIZON_ZH = {
    "short_term": "短线", "medium_term": "中线", "long_term": "长线",
    "review_required": "待定", None: "待定",
}


def display_market(ticker: str, market: str) -> str:
    t = (ticker or "").upper()
    if t.endswith(".HK"):
        return "HK"
    if t.endswith(".SH") or t.endswith(".SS"):
        return "SH"
    if t.endswith(".SZ"):
        return "SZ"
    # US tickers have no dotted suffix
    if "." not in t and t:
        return "US"
    return market or "—"


def load_actions():
    acts = []
    for f in sorted(glob.glob(os.path.join(SRC_DIR, "*.json"))):
        d = json.load(open(f))
        for a in d.get("actions", []):
            if (a.get("source") or {}).get("creator_id") == REAL_CREATOR:
                acts.append(a)
    # dedupe by trade_action_id
    seen, uniq = set(), []
    for a in acts:
        i = a.get("trade_action_id")
        if i in seen:
            continue
        seen.add(i)
        uniq.append(a)
    return uniq


def build_summary(a) -> str:
    d = a.get("direction")
    meta = a.get("metadata") or {}
    hint = meta.get("action_hint_original")
    hint_zh = HINT_ZH.get(hint, hint or "观点")
    hz = HORIZON_ZH.get(meta.get("holding_period_hint")) or HORIZON_ZH.get(a.get("time_horizon"), "待定")
    return f"{DIR_LABEL.get(d, d)} · {hint_zh}（{hz}）"


def main():
    acts = load_actions()
    # sort time-descending by real signal clock (intent_published_at)
    def pub(a):
        return ((a.get("execution_timing") or {}).get("intent_published_at")) or a.get("timestamp") or ""
    acts.sort(key=pub, reverse=True)

    viewpoints = []
    audit_by_id = {}
    entry_styles = Counter()
    short_side = 0
    directional = 0
    margin_mentions = 0
    leverage_mentions = 0

    for a in acts:
        tid = a["trade_action_id"]
        tgt = a.get("target") or {}
        src = a.get("source") or {}
        bt = a.get("backtest_result") or {}
        et = a.get("execution_timing") or {}
        meta = a.get("metadata") or {}
        ac0 = (a.get("action_chain") or [{}])[0]
        ticker = tgt.get("ticker_normalized") or tgt.get("ticker") or "—"
        mkt = display_market(ticker, tgt.get("market"))

        ret = bt.get("return_pct")
        hold = bt.get("holding_days")

        viewpoints.append({
            "id": tid,
            "timestamp": pub(a),
            "ticker": ticker,
            "companyName": tgt.get("company_name") or ticker,
            "market": mkt,
            "direction": a.get("direction"),
            "confidence": a.get("confidence"),
            "validationStatus": a.get("validation_status"),
            "summary": build_summary(a),
            "evidenceText": src.get("evidence_text") or "",
            "returnPct": ret,
            "holdingDays": hold,
            "traceStatus": a.get("canonical_trace_status"),
            "actionType": ac0.get("action_type"),
        })

        audit_by_id[tid] = {
            "intentId": a.get("intent_id"),
            "policyId": a.get("policy_id"),
            "evidenceSpanIds": a.get("evidence_span_ids") or [],
            "traceStatus": a.get("canonical_trace_status"),
            "conviction": a.get("conviction"),
            "confidence": a.get("confidence"),
            "extractionMethod": a.get("extraction_method"),
            "modelVersion": a.get("model_version"),
            "actionHint": meta.get("action_hint_original"),
            "tier": meta.get("tier"),
            "rationale": a.get("rationale"),
            "executionTiming": {
                "intentPublishedAt": et.get("intent_published_at"),
                "intentEffectiveAt": et.get("intent_effective_at"),
                "actionDecisionAt": et.get("action_decision_at"),
                "actionExecutableAt": et.get("action_executable_at"),
                "market": et.get("market"),
                "timezone": et.get("timezone"),
                "session": et.get("market_session_at_publish"),
                "timingPolicyId": et.get("timing_policy_id"),
            },
            "backtest": {
                "returnPct": ret,
                "holdingDays": hold,
                "exitReason": bt.get("exit_reason"),
                "exitPrice": bt.get("exit_price"),
                "maxDrawdownPct": bt.get("max_drawdown_pct"),
                "period": bt.get("backtest_period"),
            } if bt else None,
        }

        # observed style accumulation
        est = meta.get("entry_timing_style")
        if est in ("left_side", "right_side"):
            entry_styles[est] += 1
        d = a.get("direction")
        at = ac0.get("action_type")
        if d in ("bullish", "bearish"):
            directional += 1
        if at in ("short", "close_long", "sell_call", "buy_put") or d == "bearish":
            # count explicit short-side signals conservatively via action_type only
            pass
        if at in ("short", "sell_call", "buy_put"):
            short_side += 1
        if meta.get("margin_flag"):
            margin_mentions += 1
        if meta.get("leverage_flag"):
            leverage_mentions += 1

    left = entry_styles.get("left_side", 0)
    right = entry_styles.get("right_side", 0)
    est_sample = left + right
    if est_sample >= 5 and left / est_sample >= 0.6:
        entry_observed = "left_side"
    elif est_sample >= 5 and right / est_sample >= 0.6:
        entry_observed = "right_side"
    else:
        entry_observed = "unknown" if est_sample else "unknown"

    trading_style = {
        "creator_id": ANON["kolId"],
        "display_name": ANON["name"],
        "declared": {
            "uses_margin": False,
            "uses_leverage": None,
            "does_short": False,
            "entry_style": "right_side",
            "evidence_notes": [
                "自述“突破确认后再上车”，自我定位右侧交易",
                "自述“不用融资，仓位只用自有资金”",
            ],
        },
        "observed": {
            "sample_size": len(viewpoints),
            "directional_sample_size": directional,
            "short_side_count": short_side,
            "short_ratio": (short_side / directional) if directional else 0.0,
            "margin_mention_count": margin_mentions,
            "leverage_mention_count": leverage_mentions,
            "left_side_count": left,
            "right_side_count": right,
            "entry_style_observed": entry_observed,
            "entry_style_sample_size": est_sample,
            "low_sample": est_sample < 5,
            "computed_at": "2026-07-14T12:00:00+08:00",
            "window_label": "ALL",
        },
    }

    times = sorted(v["timestamp"][:10] for v in viewpoints if v["timestamp"])
    period_label = f"观点区间 {times[0]} — {times[-1]}" if times else ""

    radar = {
        "generatedAt": "2026-07-14T12:00:00+08:00",
        "periodLabel": period_label,
        "kols": [{**ANON, "viewpoints": viewpoints}],
        "changes": [],
    }

    out = {"radar": radar, "tradingStyle": trading_style, "auditById": audit_by_id}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    # ---- sanity log ----
    settled = [v for v in viewpoints if v["returnPct"] is not None and (v["holdingDays"] or 0) > 0]
    wins = [v for v in settled if v["returnPct"] > 0]
    PRIOR_K = 4
    adj = (len(wins) + PRIOR_K * 0.5) / (len(settled) + PRIOR_K) if settled else 0.5
    cred = max(0, min(99, round(40 + 55 * adj)))
    print(f"actions(trader_ji): {len(viewpoints)}")
    print(f"settled: {len(settled)}  wins: {len(wins)}  hitRate: {len(wins)/len(settled)*100:.1f}%")
    print(f"avg return: {sum(v['returnPct'] for v in settled)/len(settled)*100:.2f}%")
    print(f"best: {max(settled, key=lambda v: v['returnPct'])['companyName']} {max(v['returnPct'] for v in settled)*100:.1f}%")
    print(f"worst: {min(settled, key=lambda v: v['returnPct'])['companyName']} {min(v['returnPct'] for v in settled)*100:.1f}%")
    print(f"credibility: {cred}/99")
    print(f"entry style observed: {entry_observed}  left={left} right={right}")
    print(f"pending(no backtest): {len(viewpoints)-len(settled)}")
    print(f"direction mix: {Counter(v['direction'] for v in viewpoints)}")
    print(f"markets: {Counter(v['market'] for v in viewpoints)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
