"""Generate all Trader Ji golden fixtures deterministically.

Run: python tests/fixtures/kol-backtest-mvp/trader_ji/_generate_fixtures.py
"""
import json
import csv
import os
from datetime import datetime, date, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))

# =========================================================================
# Content items definition
# =========================================================================
ITEMS = [
    {
        "id": "t_001_buy_510300",
        "signal_type": "explicit buy",
        "ticker": "510300",
        "source_type": "daily_pre",
        "published_at": "2026-03-02T08:00:00+08:00",
        "raw_text": "今天开盘买入沪深300ETF，目标前高。止损设在昨日低点。",
    },
    {
        "id": "t_002_sell_159915",
        "signal_type": "explicit sell",
        "ticker": "159915",
        "source_type": "daily_post",
        "published_at": "2026-03-03T16:30:00+08:00",
        "raw_text": "创业板ETF尾盘已全部清仓，明天观望。",
    },
    {
        "id": "t_003_hold_600519",
        "signal_type": "hold",
        "ticker": "600519",
        "source_type": "weekly_strategy",
        "published_at": "2026-03-01T20:00:00+08:00",
        "raw_text": "茅台本周继续持有，不加不减。等待周五消费数据。",
    },
    {
        "id": "t_004_bullish_000858",
        "signal_type": "bullish+watch",
        "ticker": "000858",
        "source_type": "daily_pre",
        "published_at": "2026-03-04T08:00:00+08:00",
        "raw_text": "五粮液估值合理，但短期无催化剂。观察。",
    },
    {
        "id": "t_005_bearish_601318",
        "signal_type": "bearish+avoid",
        "ticker": "601318",
        "source_type": "wechat",
        "published_at": "2026-03-05T09:00:00+08:00",
        "raw_text": "中国平安短期承压，地产风险未出清。暂时回避。",
    },
    {
        "id": "t_006_nonactionable",
        "signal_type": "non-actionable",
        "ticker": None,
        "source_type": "daily_post",
        "published_at": "2026-03-05T16:30:00+08:00",
        "raw_text": "今日大盘缩量震荡，市场情绪偏谨慎。",
    },
    {
        "id": "t_007_mixed",
        "signal_type": "mixed",
        "ticker": "510300+159915",
        "source_type": "weekly_strategy",
        "published_at": "2026-03-06T20:00:00+08:00",
        "raw_text": "沪深300看多，但创业板短期需减仓。",
    },
    {
        "id": "t_008_add_510300",
        "signal_type": "explicit add",
        "ticker": "510300",
        "source_type": "daily_pre",
        "published_at": "2026-03-09T08:00:00+08:00",
        "raw_text": "沪深300ETF今天回调到位，加仓10%。",
    },
    {
        "id": "t_009_watch_000001",
        "signal_type": "watch+trigger",
        "ticker": "000001",
        "source_type": "daily_post",
        "published_at": "2026-03-09T16:30:00+08:00",
        "raw_text": "平安银行接近支撑位，明天如果放量可以进场。",
    },
    {
        "id": "t_010_multi_intent",
        "signal_type": "multi-intent",
        "ticker": "510300+600519",
        "source_type": "weekly_strategy",
        "published_at": "2026-03-10T20:00:00+08:00",
        "raw_text": "本周策略：沪深300继续加仓，茅台择机减仓锁定利润。",
    },
    {
        "id": "t_011_ambiguous",
        "signal_type": "ambiguous",
        "ticker": "601012",
        "source_type": "wechat",
        "published_at": "2026-03-11T09:00:00+08:00",
        "raw_text": "隆基绿能消息面复杂，多空分歧大。暂时不动。",
    },
    {
        "id": "t_012_close_510300",
        "signal_type": "close position",
        "ticker": "510300",
        "source_type": "daily_post",
        "published_at": "2026-03-12T16:30:00+08:00",
        "raw_text": "沪深300ETF已全部止盈，落袋为安。",
    },
    {
        "id": "t_013_bullish_399006",
        "signal_type": "bullish opinion",
        "ticker": "399006",
        "source_type": "daily_pre",
        "published_at": "2026-03-13T08:00:00+08:00",
        "raw_text": "创业板指今天大概率反弹，但不确定幅度。",
    },
    {
        "id": "t_014_reduce_600519",
        "signal_type": "explicit reduce",
        "ticker": "600519",
        "source_type": "daily_post",
        "published_at": "2026-03-14T16:30:00+08:00",
        "raw_text": "茅台减仓一半，锁定部分利润。",
    },
    {
        "id": "t_015_ambiguous_multi",
        "signal_type": "ambiguous multi",
        "ticker": "000858+601318",
        "source_type": "wechat",
        "published_at": "2026-03-16T09:00:00+08:00",
        "raw_text": "白酒和保险都不确定，再观察一周。",
    },
]

# Source type mapping for F1 envelope
SOURCE_TYPE_MAP = {
    "daily_pre": "feishu_doc",
    "daily_post": "feishu_doc",
    "weekly_strategy": "feishu_doc",
    "wechat": "wechat_article",
    "bilibili": "video_transcript",
}

# Dates for F3 intents and downstream
ACTION_DECISION_AT = "2026-05-10T12:00:00+00:00"

TICKER_NAMES = {
    "510300": "沪深300ETF",
    "159915": "创业板ETF",
    "600519": "贵州茅台",
    "000858": "五粮液",
    "601318": "中国平安",
    "000001": "平安银行",
    "601012": "隆基绿能",
    "399006": "创业板指",
}

TICKER_TYPES = {
    "510300": "etf",
    "159915": "etf",
    "600519": "stock",
    "000858": "stock",
    "601318": "stock",
    "000001": "stock",
    "601012": "stock",
    "399006": "index",
}


def find_span(text: str, substr: str, start_from: int = 0) -> tuple:
    """Find character offsets of substr in text."""
    idx = text.find(substr, start_from)
    if idx == -1:
        raise ValueError(f"'{substr}' not found in text starting from {start_from}")
    return idx, idx + len(substr)


# =========================================================================
# F0: content/ directory
# =========================================================================
def write_content_files():
    os.makedirs(os.path.join(BASE, "content"), exist_ok=True)
    for item in ITEMS:
        cid = item["id"]
        # manifest.json
        manifest = {
            "content_id": cid,
            "source_type": item["source_type"],
            "file_type": "markdown",
            "creator_id": "trader_ji",
            "creator_name": "9友",
            "raw_path": f"data/raw/trader_ji/{cid}.raw.md",
            "published_at": item["published_at"],
            "collected_at": "2026-03-15T00:00:00+08:00",
            "title": f"trader_ji/{cid}",
        }
        with open(os.path.join(BASE, "content", f"{cid}.manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # raw.md
        with open(os.path.join(BASE, "content", f"{cid}.raw.md"), "w") as f:
            f.write(item["raw_text"])


# =========================================================================
# F1: expected_*.envelope.json
# =========================================================================
def write_f1_envelopes():
    f1_dir = os.path.join(BASE, "F1")
    os.makedirs(f1_dir, exist_ok=True)
    for item in ITEMS:
        cid = item["id"]
        block_id = f"block_{cid}_0"
        envelope = {
            "envelope_id": f"env_{cid}",
            "schema_version": "v1.0",
            "source_record_id": cid,
            "source_type": SOURCE_TYPE_MAP[item["source_type"]],
            "standardization_profile": f"{item['source_type']}_v1",
            "source_title": f"trader_ji/{cid}",
            "raw_path": f"data/raw/trader_ji/{cid}.raw.md",
            "creator_id": "trader_ji",
            "creator_name": "9友",
            "published_at": item["published_at"],
            "collected_at": "2026-03-15T00:00:00+08:00",
            "ingested_at": "2026-03-15T00:00:00+08:00",
            "blocks": [
                {
                    "block_id": block_id,
                    "envelope_id": f"env_{cid}",
                    "block_type": "paragraph",
                    "text": item["raw_text"],
                    "order_index": 0,
                    "quality": {
                        "readability": 0.90,
                        "extraction_confidence": 0.95,
                        "structural_confidence": 0.90,
                        "completeness": 0.95,
                        "noise_score": 0.05,
                        "quality_flags": [],
                    },
                    "provenance": {
                        "raw_path": f"data/raw/trader_ji/{cid}.raw.md",
                        "extractor": f"{item['source_type']}_standardizer",
                        "extractor_version": "1.0.0",
                    },
                    "evidence_spans": [],
                }
            ],
            "quality_card": {
                "schema_version": "v0.5",
                "readability_score": 0.90,
                "semantic_completeness_score": 0.90,
                "financial_relevance_score": 0.85,
                "entity_resolution_score": 0.80,
                "temporal_resolution_score": 0.80,
                "evidence_traceability_score": 0.85,
                "overall_score": 0.85,
                "gate_status": "pass",
                "gate_reasons": [],
            },
            "temporal_anchors": [],
            "entity_anchors": [],
            "metadata": {},
        }
        with open(os.path.join(f1_dir, f"expected_{cid}.envelope.json"), "w") as f:
            json.dump(envelope, f, indent=2, ensure_ascii=False)


# =========================================================================
# F1.5: expected_*.assembly.json
# =========================================================================
def write_f15_assemblies():
    f15_dir = os.path.join(BASE, "F1.5")
    os.makedirs(f15_dir, exist_ok=True)
    for item in ITEMS:
        cid = item["id"]
        block_id = f"block_{cid}_0"
        tickers = item["ticker"].split("+") if item["ticker"] else []

        # Determine topic_type
        if not tickers:
            topic_type = "market_commentary"
        elif len(tickers) > 1:
            topic_type = "portfolio_update"
        else:
            topic_type = "single_stock"

        assembly = {
            "assembly_id": f"asm_{cid}",
            "envelope_id": f"env_{cid}",
            "topic_blocks": [
                {
                    "topic_block_id": f"tb_{cid}_0",
                    "envelope_id": f"env_{cid}",
                    "source_block_ids": [block_id],
                    "topic_title": f"trader_ji signal: {cid}",
                    "topic_type": topic_type,
                    "primary_entity_ids": tickers,
                    "secondary_entity_ids": [],
                    "start_block_index": 0,
                    "end_block_index": 0,
                    "summary": item["raw_text"][:50],
                    "raw_text": item["raw_text"],
                    "segmentation_reason": "single-block content, wrapping as single topic",
                    "confidence": 0.95,
                    "ambiguity_flags": [],
                }
            ],
            "unassigned_block_ids": [],
            "assembly_strategy": "single_block_wrap",
            "created_at": "2026-03-15T00:00:00+08:00",
        }
        with open(os.path.join(f15_dir, f"expected_{cid}.assembly.json"), "w") as f:
            json.dump(assembly, f, indent=2, ensure_ascii=False)


# =========================================================================
# F2: expected_*.anchors.json
# =========================================================================
def write_f2_anchors():
    f2_dir = os.path.join(BASE, "F2")
    os.makedirs(f2_dir, exist_ok=True)

    for item in ITEMS:
        cid = item["id"]
        text = item["raw_text"]
        block_id = f"block_{cid}_0"
        published_at = item["published_at"]
        tickers = item["ticker"].split("+") if item["ticker"] else []

        evidence_spans = []
        entity_anchors = []
        temporal_anchors = []

        # --- Entity spans ---
        for i, ticker in enumerate(tickers):
            ticker_name = TICKER_NAMES.get(ticker, ticker)
            entity_type = TICKER_TYPES.get(ticker, "stock")
            # Find the ticker name in text
            try:
                s, e = find_span(text, ticker_name)
            except ValueError:
                # For index ticker like 399006, the name might be "创业板指"
                s, e = 0, len(text)

            span_id = f"span_{cid}_0_{i}"
            evidence_spans.append({
                "schema_version": "v0.5",
                "evidence_span_id": span_id,
                "block_id": block_id,
                "char_start": s,
                "char_end": e,
                "text": text[s:e],
                "confidence": 0.90,
                "span_type": "entity",
            })

            entity_anchors.append({
                "schema_version": "v0.5",
                "entity_anchor_id": f"entity_{cid}_{i}",
                "entity_type": entity_type,
                "raw_text": text[s:e],
                "resolved_name": ticker_name,
                "resolved_symbol": ticker,
                "market": "CN",
                "confidence": 0.90,
                "evidence_span_id": span_id,
                "aliases": [],
            })

        # --- Temporal anchors ---
        # published_at anchor
        temporal_anchors.append({
            "schema_version": "v0.5",
            "anchor_id": f"temp_{cid}_pub",
            "anchor_type": "published_at",
            "raw_text": "published_at",
            "resolved_time": published_at,
            "confidence": 1.0,
            "resolution_strategy": "explicit_date",
            "timezone": "Asia/Shanghai",
        })

        # mentioned_at anchors for time-sensitive content
        time_keywords = {
            "今天": "market_hours",
            "今日": "market_hours",
            "明天": "relative_date",
            "本周": "relative_date",
            "尾盘": "market_hours",
            "开盘": "market_hours",
        }
        temp_idx = 1
        for keyword, strategy in time_keywords.items():
            if keyword in text:
                try:
                    s, e = find_span(text, keyword)
                    span_id = f"span_{cid}_0_t{temp_idx}"
                    evidence_spans.append({
                        "schema_version": "v0.5",
                        "evidence_span_id": span_id,
                        "block_id": block_id,
                        "char_start": s,
                        "char_end": e,
                        "text": text[s:e],
                        "confidence": 0.85,
                        "span_type": "temporal",
                    })

                    # Resolve time
                    pub_dt = datetime.fromisoformat(published_at)
                    if keyword == "今天" or keyword == "今日":
                        resolved = pub_dt.replace(hour=9, minute=30, second=0).isoformat()
                    elif keyword == "明天":
                        resolved = (pub_dt + timedelta(days=1)).replace(hour=9, minute=30, second=0).isoformat()
                    elif keyword == "本周":
                        resolved = pub_dt.isoformat()
                    elif keyword == "尾盘":
                        resolved = pub_dt.replace(hour=14, minute=30, second=0).isoformat()
                    elif keyword == "开盘":
                        resolved = pub_dt.replace(hour=9, minute=30, second=0).isoformat()
                    else:
                        resolved = pub_dt.isoformat()

                    temporal_anchors.append({
                        "schema_version": "v0.5",
                        "anchor_id": f"temp_{cid}_m{temp_idx}",
                        "anchor_type": "mentioned_at",
                        "raw_text": keyword,
                        "resolved_time": resolved,
                        "confidence": 0.85,
                        "resolution_strategy": strategy,
                        "evidence_span_id": span_id,
                        "timezone": "Asia/Shanghai",
                    })
                    temp_idx += 1
                except ValueError:
                    pass

        # effective_trade_at for actionable items
        actionable_signals = ["explicit buy", "explicit sell", "hold", "mixed",
                              "explicit add", "multi-intent", "close position",
                              "explicit reduce"]
        if item["signal_type"] in actionable_signals:
            pub_dt = datetime.fromisoformat(published_at)
            if item["source_type"] == "daily_pre":
                eff = pub_dt.replace(hour=9, minute=30, second=0)
            elif item["source_type"] == "daily_post":
                eff = (pub_dt + timedelta(days=1)).replace(hour=9, minute=30, second=0)
            elif item["source_type"] == "weekly_strategy":
                # Next Monday open
                days_ahead = 7 - pub_dt.weekday()
                eff = (pub_dt + timedelta(days=days_ahead)).replace(hour=9, minute=30, second=0)
            else:
                eff = (pub_dt + timedelta(days=1)).replace(hour=9, minute=30, second=0)

            temporal_anchors.append({
                "schema_version": "v0.5",
                "anchor_id": f"temp_{cid}_eff",
                "anchor_type": "effective_trade_at",
                "raw_text": item["raw_text"][:20],
                "resolved_time": eff.isoformat(),
                "confidence": 0.80,
                "resolution_strategy": "market_hours",
                "timezone": "Asia/Shanghai",
            })

        anchors = {
            "envelope_id": f"env_{cid}",
            "evidence_spans": evidence_spans,
            "entity_anchors": entity_anchors,
            "temporal_anchors": temporal_anchors,
        }
        with open(os.path.join(f2_dir, f"expected_{cid}.anchors.json"), "w") as f:
            json.dump(anchors, f, indent=2, ensure_ascii=False)


# =========================================================================
# F3: expected_*.intents.json
# =========================================================================
def write_f3_intents():
    f3_dir = os.path.join(BASE, "F3")
    os.makedirs(f3_dir, exist_ok=True)

    # Per-content intent definitions
    INTENT_DEFS = {
        "t_001_buy_510300": [
            {"direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "open",
             "target_symbol": "510300", "target_type": "etf", "market": "CN", "conviction": 0.85, "confidence": 0.90,
             "time_horizon": "intraday"},
        ],
        "t_002_sell_159915": [
            {"direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "exit",
             "target_symbol": "159915", "target_type": "etf", "market": "CN", "conviction": 0.90, "confidence": 0.95,
             "time_horizon": "intraday"},
        ],
        "t_003_hold_600519": [
            {"direction": "neutral", "actionability": "explicit_action", "position_delta_hint": "hold",
             "target_symbol": "600519", "target_type": "stock", "market": "CN", "conviction": 0.70, "confidence": 0.90,
             "time_horizon": "short_term"},
        ],
        "t_004_bullish_000858": [
            {"direction": "bullish", "actionability": "watch", "position_delta_hint": "none",
             "target_symbol": "000858", "target_type": "stock", "market": "CN", "conviction": 0.50, "confidence": 0.80,
             "time_horizon": "unknown"},
        ],
        "t_005_bearish_601318": [
            {"direction": "bearish", "actionability": "watch", "position_delta_hint": "none",
             "target_symbol": "601318", "target_type": "stock", "market": "CN", "conviction": 0.60, "confidence": 0.85,
             "time_horizon": "unknown"},
        ],
        "t_006_nonactionable": [
            {"direction": "neutral", "actionability": "opinion", "position_delta_hint": "none",
             "target_symbol": None, "target_type": "unknown", "market": None, "conviction": 0.30, "confidence": 0.70,
             "time_horizon": "unknown"},
        ],
        "t_007_mixed": [
            {"direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "open",
             "target_symbol": "510300", "target_type": "etf", "market": "CN", "conviction": 0.75, "confidence": 0.85,
             "time_horizon": "short_term"},
            {"direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "reduce",
             "target_symbol": "159915", "target_type": "etf", "market": "CN", "conviction": 0.70, "confidence": 0.85,
             "time_horizon": "short_term"},
        ],
        "t_008_add_510300": [
            {"direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "add",
             "target_symbol": "510300", "target_type": "etf", "market": "CN", "conviction": 0.80, "confidence": 0.90,
             "time_horizon": "intraday"},
        ],
        "t_009_watch_000001": [
            {"direction": "bullish", "actionability": "watch", "position_delta_hint": "none",
             "target_symbol": "000001", "target_type": "stock", "market": "CN", "conviction": 0.55, "confidence": 0.75,
             "time_horizon": "unknown"},
        ],
        "t_010_multi_intent": [
            {"direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "add",
             "target_symbol": "510300", "target_type": "etf", "market": "CN", "conviction": 0.80, "confidence": 0.85,
             "time_horizon": "short_term"},
            {"direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "reduce",
             "target_symbol": "600519", "target_type": "stock", "market": "CN", "conviction": 0.75, "confidence": 0.85,
             "time_horizon": "short_term"},
        ],
        "t_011_ambiguous": [
            {"direction": "unknown", "actionability": "review_required", "position_delta_hint": "unknown",
             "target_symbol": "601012", "target_type": "stock", "market": "CN", "conviction": 0.30, "confidence": 0.50,
             "time_horizon": "unknown"},
        ],
        "t_012_close_510300": [
            {"direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "exit",
             "target_symbol": "510300", "target_type": "etf", "market": "CN", "conviction": 0.90, "confidence": 0.95,
             "time_horizon": "intraday"},
        ],
        "t_013_bullish_399006": [
            {"direction": "bullish", "actionability": "opinion", "position_delta_hint": "none",
             "target_symbol": "399006", "target_type": "index", "market": "CN", "conviction": 0.55, "confidence": 0.70,
             "time_horizon": "intraday"},
        ],
        "t_014_reduce_600519": [
            {"direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "reduce",
             "target_symbol": "600519", "target_type": "stock", "market": "CN", "conviction": 0.80, "confidence": 0.90,
             "time_horizon": "intraday"},
        ],
        "t_015_ambiguous_multi": [
            {"direction": "unknown", "actionability": "review_required", "position_delta_hint": "unknown",
             "target_symbol": "000858", "target_type": "stock", "market": "CN", "conviction": 0.25, "confidence": 0.45,
             "time_horizon": "unknown"},
        ],
    }

    for item in ITEMS:
        cid = item["id"]
        defs = INTENT_DEFS[cid]
        block_id = f"block_{cid}_0"
        text = item["raw_text"]
        tickers = item["ticker"].split("+") if item["ticker"] else []

        intents = []
        for i, idef in enumerate(defs):
            intent_id = f"intent_{cid}_{i}"
            symbol = idef["target_symbol"]

            # Find evidence spans for this intent
            evidence_span_ids = []
            if symbol:
                name = TICKER_NAMES.get(symbol, symbol)
                try:
                    s, e = find_span(text, name)
                    evidence_span_ids.append(f"span_{cid}_0_{tickers.index(symbol) if symbol in tickers else 0}")
                except ValueError:
                    evidence_span_ids.append(f"span_{cid}_0_0")

            # Add temporal evidence if time-sensitive keywords present
            time_keywords_in_text = [kw for kw in ["今天", "今日", "明天", "本周", "尾盘", "开盘"] if kw in text]
            for kw in time_keywords_in_text:
                evidence_span_ids.append(f"span_{cid}_0_t{time_keywords_in_text.index(kw) + 1}")

            if not evidence_span_ids:
                evidence_span_ids.append(f"span_{cid}_0_0")

            intent = {
                "intent_id": intent_id,
                "schema_version": "1.0",
                "envelope_id": f"env_{cid}",
                "block_ids": [block_id],
                "target_type": idef["target_type"],
                "target_name": TICKER_NAMES.get(symbol, symbol) if symbol else "market",
                "target_symbol": symbol,
                "market": idef["market"],
                "direction": idef["direction"],
                "actionability": idef["actionability"],
                "position_delta_hint": idef["position_delta_hint"],
                "conviction": idef["conviction"],
                "confidence": idef["confidence"],
                "evidence_span_ids": evidence_span_ids,
                "temporal_anchor_ids": [],
                "ambiguity_flags": [],
                "time_horizon_hint": idef["time_horizon"],
                "created_at": "2026-05-10T12:00:00+00:00",
                "metadata": {},
            }
            intents.append(intent)

        result = {
            "envelope_id": f"env_{cid}",
            "intents": intents,
            "extraction_timestamp": "2026-05-10T12:00:00+00:00",
            "model_version": "v1.0",
            "total_intents": len(intents),
            "actionable_count": sum(1 for i in intents if i["actionability"] == "explicit_action"),
        }
        with open(os.path.join(f3_dir, f"expected_{cid}.intents.json"), "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)


# =========================================================================
# F4: expected_*.policy.json
# =========================================================================
def write_f4_policies():
    f4_dir = os.path.join(BASE, "F4")
    os.makedirs(f4_dir, exist_ok=True)

    # Mapping rules from stage contracts
    def map_policy(actionability, direction, position_delta_hint, conviction, confidence, ambiguity_flags):
        # Action hint mapping
        if actionability == "explicit_action":
            if direction in ("bullish",) and position_delta_hint == "open":
                action_hint = "open_position"
            elif direction in ("bullish",) and position_delta_hint == "add":
                action_hint = "add_position"
            elif position_delta_hint == "reduce":
                action_hint = "reduce_position"
            elif position_delta_hint == "hold":
                action_hint = "hold_position"
            elif position_delta_hint == "exit":
                action_hint = "close_position"
            elif direction == "bearish" and position_delta_hint == "open":
                action_hint = "review_required"
            elif position_delta_hint in ("none", "unknown"):
                action_hint = "review_required"
            else:
                action_hint = "review_required"
        elif actionability == "watch":
            action_hint = "watch_only"
        elif actionability == "opinion":
            if direction == "bullish":
                action_hint = "watch_or_no_trade"
            elif direction == "bearish":
                action_hint = "avoid_or_watch_risk"
            else:
                action_hint = "watch_only"
        else:  # review_required
            action_hint = "review_required"

        # Position sizing
        if action_hint in ("watch_only", "watch_or_no_trade", "avoid_or_watch_risk", "review_required"):
            position_sizing = "none"
        elif len(ambiguity_flags) >= 2:
            position_sizing = "review_required"
        elif conviction < 0.35:
            position_sizing = "none"
        elif conviction <= 0.70:
            position_sizing = "small"
        else:
            position_sizing = "medium"

        # Holding period
        if action_hint in ("open_position", "add_position", "hold_position"):
            holding_period = "medium_term"
        elif action_hint in ("reduce_position", "close_position"):
            holding_period = "short_term"
        else:
            holding_period = "review_required"

        # Max position hint
        if action_hint in ("watch_only", "watch_or_no_trade", "avoid_or_watch_risk", "review_required"):
            max_pos = "none"
        elif conviction >= 0.70:
            max_pos = "medium"
        else:
            max_pos = "small"

        # Requires human review
        requires_review = action_hint == "review_required" or len(ambiguity_flags) >= 2

        # Mapping confidence
        mapping_conf = confidence
        if action_hint == "review_required":
            mapping_conf = min(mapping_conf, 0.6)
        if ambiguity_flags:
            mapping_conf -= min(0.15, 0.05 * len(ambiguity_flags))
        mapping_conf = max(0.2, mapping_conf)

        return {
            "action_hint": action_hint,
            "position_sizing_hint": position_sizing,
            "holding_period_hint": holding_period,
            "max_position_hint": max_pos,
            "requires_human_review": requires_review,
            "mapping_confidence": round(mapping_conf, 2),
        }

    for item in ITEMS:
        cid = item["id"]
        # Read F3 intents
        with open(os.path.join(BASE, "F3", f"expected_{cid}.intents.json")) as f:
            f3 = json.load(f)

        mappings = []
        mapped_intents = []

        for intent in f3["intents"]:
            intent_id = intent["intent_id"]
            policy_id = f"policy_{intent_id}"

            p = map_policy(
                intent["actionability"],
                intent["direction"],
                intent["position_delta_hint"],
                intent["conviction"],
                intent["confidence"],
                intent.get("ambiguity_flags", []),
            )

            # Build rationale
            rationale = (
                f"GlobalBase: {intent['actionability']}+{intent['direction']}+"
                f"{intent['position_delta_hint']} -> {p['action_hint']}"
            )

            mapping = {
                "policy_id": policy_id,
                "intent_id": intent_id,
                "policy_version": "global-base-v1",
                "policy_layers_applied": ["GlobalBase"],
                "action_hint": p["action_hint"],
                "position_sizing_hint": p["position_sizing_hint"],
                "holding_period_hint": p["holding_period_hint"],
                "risk_constraints": {
                    "max_position_hint": p["max_position_hint"],
                    "requires_human_review": p["requires_human_review"],
                    "risk_notes": [],
                },
                "mapping_rationale": rationale,
                "layer_traces": [
                    {
                        "layer_name": "GlobalBase",
                        "layer_version": "global-base-v1",
                        "applied": True,
                        "reason": rationale,
                        "modifications": [],
                        "order_index": 0,
                    }
                ],
                "decisions": [],
                "confidence": p["mapping_confidence"],
                "original_intent_confidence": intent["confidence"],
                "created_at": "2026-05-10T12:00:00+00:00",
                "metadata": {},
            }
            mappings.append(mapping)

            target_name = intent.get("target_name", "unknown")
            mi = {
                "mapped_id": f"mapped_{intent_id}",
                "intent_id": intent_id,
                "policy_id": policy_id,
                "original_intent_summary": f"{intent['direction']} {target_name} ({intent['position_delta_hint']})",
                "action_hint": p["action_hint"],
                "position_sizing_hint": p["position_sizing_hint"],
                "holding_period_hint": p["holding_period_hint"],
                "risk_notes": [],
                "mapping_confidence": p["mapping_confidence"],
                "requires_human_review": p["requires_human_review"],
                "created_at": "2026-05-10T12:00:00+00:00",
                "metadata": {},
            }
            mapped_intents.append(mi)

        result = {
            "envelope_id": f"env_{cid}",
            "mappings": mappings,
            "mapped_intents": mapped_intents,
            "created_at": "2026-05-10T12:00:00+00:00",
        }
        with open(os.path.join(f4_dir, f"expected_{cid}.policy.json"), "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)


# =========================================================================
# F5: expected_*.actions.json + expected_*.rejections.json
# =========================================================================
def write_f5_actions():
    f5_dir = os.path.join(BASE, "F5")
    os.makedirs(f5_dir, exist_ok=True)

    def compute_executable_at(published_at_str, source_type):
        pub = datetime.fromisoformat(published_at_str)
        if source_type == "daily_pre":
            # Same day open
            return pub.replace(hour=9, minute=30, second=0).isoformat()
        elif source_type == "daily_post":
            # Next trading day open
            next_day = pub + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day.replace(hour=9, minute=30, second=0).isoformat()
        elif source_type == "weekly_strategy":
            # Next Monday open
            days_ahead = 7 - pub.weekday()
            if days_ahead == 0:
                days_ahead = 7
            next_mon = pub + timedelta(days=days_ahead)
            return next_mon.replace(hour=9, minute=30, second=0).isoformat()
        else:
            next_day = pub + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day.replace(hour=9, minute=30, second=0).isoformat()

    def compute_market_session(source_type):
        if source_type == "daily_pre":
            return "pre_market"
        elif source_type == "daily_post":
            return "after_close"
        elif source_type == "weekly_strategy":
            return "after_close"
        else:
            return "after_close"

    ACTION_TYPE_MAP = {
        "open_position": "long",
        "add_position": "long",
        "reduce_position": "close_long",
        "close_position": "close_long",
        "hold_position": "hold",
    }

    POSITION_SIZE_MAP = {
        "none": 0.0,
        "small": 0.05,
        "medium": 0.15,
    }

    # Actions: only explicit_action intents that pass F4 executable gate
    ACTIONABLE_CONTENT = [
        "t_001_buy_510300", "t_002_sell_159915", "t_003_hold_600519",
        "t_007_mixed", "t_008_add_510300", "t_010_multi_intent",
        "t_012_close_510300", "t_014_reduce_600519",
    ]

    # Non-actionable: rejected at F4 gate
    REJECTED_CONTENT = [
        "t_004_bullish_000858", "t_005_bearish_601318", "t_006_nonactionable",
        "t_009_watch_000001", "t_011_ambiguous", "t_013_bullish_399006",
        "t_015_ambiguous_multi",
    ]

    for item in ITEMS:
        cid = item["id"]
        with open(os.path.join(BASE, "F4", f"expected_{cid}.policy.json")) as f:
            f4 = json.load(f)
        with open(os.path.join(BASE, "F3", f"expected_{cid}.intents.json")) as f:
            f3 = json.load(f)

        actions = []
        rejections = []

        for mi in f4["mapped_intents"]:
            intent_id = mi["intent_id"]
            policy_id = mi["policy_id"]
            action_hint = mi["action_hint"]

            # Find the matching F3 intent
            f3_intent = None
            for intent in f3["intents"]:
                if intent["intent_id"] == intent_id:
                    f3_intent = intent
                    break

            if f3_intent is None:
                continue

            # Check if executable
            if action_hint not in ("open_position", "add_position", "reduce_position",
                                    "close_position", "hold_position"):
                rejections.append({
                    "intent_id": intent_id,
                    "policy_id": policy_id,
                    "rejection_stage": "F4",
                    "rejection_reason": "non_executable_action_hint",
                    "description": f"{f3_intent['actionability']} intent -> {action_hint}, excluded at executable gate",
                })
                continue

            symbol = f3_intent.get("target_symbol", "")
            direction = f3_intent["direction"]
            action_type = ACTION_TYPE_MAP.get(action_hint, "watch")
            position_size = POSITION_SIZE_MAP.get(mi["position_sizing_hint"], 0.10)

            # Map direction to TradeDirection
            if direction == "bullish":
                trade_dir = "bullish"
            elif direction == "bearish":
                trade_dir = "bearish"
            else:
                trade_dir = "neutral"

            exec_at = compute_executable_at(item["published_at"], item["source_type"])
            market_session = compute_market_session(item["source_type"])

            # For hold actions, position_size is 0 (no-op)
            if action_type == "hold":
                position_size = 0.0

            action = {
                "trade_action_id": f"action_{cid}_{len(actions)}",
                "timestamp": "2026-05-10T12:00:00+00:00",
                "source": {
                    "content_id": f"env_{cid}",
                    "evidence_text": item["raw_text"],
                },
                "target": {
                    "ticker": TICKER_NAMES.get(symbol, symbol) if symbol else symbol,
                    "ticker_normalized": symbol,
                    "market": "CN",
                    "instrument_type": TICKER_TYPES.get(symbol, "stock"),
                    "company_name": TICKER_NAMES.get(symbol, symbol),
                },
                "direction": trade_dir,
                "action_chain": [
                    {
                        "sequence": 1,
                        "action_type": action_type,
                        "trigger_condition": None,
                        "trigger_type": "manual",
                        "position_size_pct": position_size,
                    }
                ],
                "intent_id": intent_id,
                "policy_id": policy_id,
                "evidence_span_ids": f3_intent.get("evidence_span_ids", []),
                "canonical_trace_status": "canonical",
                "execution_timing": {
                    "intent_published_at": item["published_at"],
                    "intent_effective_at": exec_at,
                    "action_decision_at": ACTION_DECISION_AT,
                    "action_executable_at": exec_at,
                    "market": "CN",
                    "timezone": "Asia/Shanghai",
                    "market_session_at_publish": market_session,
                    "execution_delay_reason": None,
                    "timing_policy_id": "market-calendar-next-open-v1",
                },
                "confidence": mi["mapping_confidence"],
                "requires_manual_review": mi["requires_human_review"],
                "time_horizon": mi["holding_period_hint"],
                "rationale": f4["mappings"][f4["mapped_intents"].index(mi)]["mapping_rationale"],
                "metadata": {},
            }
            actions.append(action)

        # Write actions
        with open(os.path.join(f5_dir, f"expected_{cid}.actions.json"), "w") as f:
            json.dump({"actions": actions}, f, indent=2, ensure_ascii=False)

        # Write rejections
        with open(os.path.join(f5_dir, f"expected_{cid}.rejections.json"), "w") as f:
            json.dump({"rejections": rejections}, f, indent=2, ensure_ascii=False)


# =========================================================================
# Market prices CSV
# =========================================================================
def write_market_prices():
    tickers = ["510300", "159915", "600519", "000858", "601318", "000001", "601012", "399006"]

    # Base prices and trends
    base_prices = {
        "510300": 4.00,   # CSI 300 ETF
        "159915": 2.20,   # ChiNext ETF
        "600519": 1680.0, # Kweichow Moutai
        "000858": 135.0,  # Wuliangye
        "601318": 48.0,   # Ping An
        "000001": 12.50,  # Ping An Bank
        "601012": 22.0,   # LONGi Green Energy
        "399006": 2200.0, # ChiNext Index
    }

    # Simple deterministic price generator
    # Each ticker gets a seeded random walk
    def generate_prices(ticker, base, start_date, end_date):
        prices = []
        current = base
        d = start_date
        day_idx = 0
        while d <= end_date:
            if d.weekday() < 5:  # Trading days only
                # Deterministic pseudo-random based on ticker+day
                seed_val = hash(f"{ticker}_{day_idx}") % 1000 / 1000.0
                change_pct = (seed_val - 0.5) * 0.04  # +/- 2%
                current = round(current * (1 + change_pct), 2)

                # Ensure prices stay reasonable
                current = max(current * 0.5, min(current, base * 3))

                o = round(current * (1 + (seed_val - 0.5) * 0.01), 2)
                h = round(max(o, current) * (1 + seed_val * 0.005), 2)
                l = round(min(o, current) * (1 - (1 - seed_val) * 0.005), 2)
                c = current
                vol = int(5000000 + seed_val * 10000000)

                prices.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": vol,
                    "adj_close": c,
                })
                day_idx += 1
            d += timedelta(days=1)
        return prices

    start = date(2026, 3, 1)
    end = date(2026, 5, 9)

    all_rows = []
    for ticker in tickers:
        rows = generate_prices(ticker, base_prices[ticker], start, end)
        all_rows.extend(rows)

    # Sort by date then ticker
    all_rows.sort(key=lambda r: (r["date"], r["ticker"]))

    csv_path = os.path.join(BASE, "market_prices.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "ticker", "open", "high", "low", "close", "volume", "adj_close"])
        writer.writeheader()
        writer.writerows(all_rows)


# =========================================================================
# F8: expected_backtest_result.json + expected_equity_curve.csv
# =========================================================================
def write_f8_backtest():
    f8_dir = os.path.join(BASE, "F8")
    os.makedirs(f8_dir, exist_ok=True)

    # Read market prices
    prices = {}
    with open(os.path.join(BASE, "market_prices.csv")) as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["date"], row["ticker"])
            prices[key] = row

    # Collect all actions across all content
    all_actions = []
    for item in ITEMS:
        cid = item["id"]
        with open(os.path.join(BASE, "F5", f"expected_{cid}.actions.json")) as f:
            data = json.load(f)
        for a in data["actions"]:
            all_actions.append(a)

    # Sort by executable_at
    all_actions.sort(key=lambda a: a["execution_timing"]["action_executable_at"])

    # Simple backtest simulation
    initial_capital = 100000.0
    cash = initial_capital
    positions = {}  # ticker -> {entry_date, entry_price, size_pct, direction}
    trades = []
    equity_curve = []

    # Get all trading dates
    all_dates = sorted(set(p[0] for p in prices.keys()))

    for d in all_dates:
        # Record equity at START of day (before processing trades)
        pos_value = 0
        for ticker, pos in positions.items():
            price_key = (d, ticker)
            if price_key in prices:
                pos_value += float(prices[price_key]["close"]) * pos["shares"]

        equity = cash + pos_value
        equity_curve.append({
            "date": d,
            "equity": round(equity, 2),
            "benchmark": round(initial_capital * 1.0, 2),
            "cash": round(cash, 2),
            "positions_value": round(pos_value, 2),
        })

        # Process actions executable on this date
        for action in all_actions:
            exec_date = action["execution_timing"]["action_executable_at"][:10]
            if exec_date != d:
                continue

            ticker = action["target"]["ticker_normalized"]
            action_type = action["action_chain"][0]["action_type"]
            size_pct = action["action_chain"][0].get("position_size_pct", 0.10)

            price_key = (d, ticker)
            if price_key not in prices:
                continue

            price = float(prices[price_key]["open"])

            if action_type == "long" and ticker not in positions:
                alloc = cash * size_pct
                shares = alloc / price
                cash -= alloc
                positions[ticker] = {
                    "entry_date": d,
                    "entry_price": price,
                    "shares": shares,
                    "direction": "long",
                    "action_id": action["trade_action_id"],
                }
            elif action_type in ("close_long",) and ticker in positions:
                pos = positions.pop(ticker)
                pnl = (price - pos["entry_price"]) * pos["shares"]
                cash += pos["entry_price"] * pos["shares"] + pnl
                holding_days = (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(pos["entry_date"], "%Y-%m-%d")).days
                ret_pct = (price - pos["entry_price"]) / pos["entry_price"] * 100
                trades.append({
                    "trade_action_id": pos["action_id"],
                    "ticker": ticker,
                    "direction": "long",
                    "entry_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "exit_date": d,
                    "exit_price": price,
                    "exit_reason": "signal_reversal",
                    "return_pct": round(ret_pct, 2),
                    "holding_days": holding_days,
                    "max_drawdown_pct": 0.0,
                    "position_size_pct": size_pct,
                    "pnl_absolute": round(pnl, 2),
                })


    # Close remaining positions at end
    for ticker, pos in list(positions.items()):
        last_key = (all_dates[-1], ticker)
        if last_key in prices:
            price = float(prices[last_key]["close"])
            pnl = (price - pos["entry_price"]) * pos["shares"]
            cash += pos["entry_price"] * pos["shares"] + pnl
            holding_days = (datetime.strptime(all_dates[-1], "%Y-%m-%d") - datetime.strptime(pos["entry_date"], "%Y-%m-%d")).days
            ret_pct = (price - pos["entry_price"]) / pos["entry_price"] * 100
            trades.append({
                "trade_action_id": pos["action_id"],
                "ticker": ticker,
                "direction": "long",
                "entry_date": pos["entry_date"],
                "exit_date": all_dates[-1],
                "exit_price": price,
                "exit_reason": "end_of_period",
                "return_pct": round(ret_pct, 2),
                "holding_days": holding_days,
                "max_drawdown_pct": 0.0,
                "position_size_pct": 0.10,
                "pnl_absolute": round(pnl, 2),
            })

    final_equity = cash
    total_return = (final_equity - initial_capital) / initial_capital * 100
    win_count = sum(1 for t in trades if t["return_pct"] > 0)

    backtest_result = {
        "total_trades": len(all_actions),
        "return_pct": round(total_return, 2),
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "win_rate": round(win_count / max(len(trades), 1), 2),
        "backtest_period": "2026-03-01 to 2026-05-09",
        "initial_capital": 100000,
        "trading_days": len(all_dates),
        "commission_pct": 0,
        "slippage_pct": 0,
        "max_holding_days": 30,
        "trade_details": trades,
    }

    with open(os.path.join(f8_dir, "expected_backtest_result.json"), "w") as f:
        json.dump(backtest_result, f, indent=2, ensure_ascii=False)

    # Equity curve CSV
    with open(os.path.join(f8_dir, "expected_equity_curve.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "equity", "benchmark", "cash", "positions_value"])
        writer.writeheader()
        writer.writerows(equity_curve)


# =========================================================================
# Main
# =========================================================================
if __name__ == "__main__":
    print("Generating Trader Ji fixtures...")
    write_content_files()
    print("  content/ done")
    write_f1_envelopes()
    print("  F1/ done")
    write_f15_assemblies()
    print("  F1.5/ done")
    write_f2_anchors()
    print("  F2/ done")
    write_f3_intents()
    print("  F3/ done")
    write_f4_policies()
    print("  F4/ done")
    write_f5_actions()
    print("  F5/ done")
    write_market_prices()
    print("  market_prices.csv done")
    write_f8_backtest()
    print("  F8/ done")
    print("All fixtures generated.")
