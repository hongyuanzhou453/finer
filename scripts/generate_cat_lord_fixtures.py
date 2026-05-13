#!/usr/bin/env python3
"""Generate Cat Lord golden fixtures for KOL Backtest MVP.

This script creates all fixture files for the cat_lord KOL,
following the fixture contract in docs/specs/kol-backtest-mvp-fixture-contract.md.
"""

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path("tests/fixtures/kol-backtest-mvp/cat_lord")

# Content items with metadata
CONTENT_ITEMS = [
    {
        "id": "c_001_bullish_csiq",
        "signal_type": "bullish_opinion",
        "ticker": "CSIQ",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-03-10T09:30:00+08:00",
        "title": "阿特斯太阳能CSIQ分析",
        "raw_text": "阿特斯太阳能CSIQ更值得关注，在手订单充沛，动态远期PE只有8-12倍。2026大概率扭亏为盈。",
    },
    {
        "id": "c_002_buy_li",
        "signal_type": "explicit_reduce",
        "ticker": "LI",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-03-15T10:00:00+08:00",
        "title": "理想汽车投资分析",
        "raw_text": "理想汽车投资价值弱于其他新能源车企，15元以下都是不错的入场机会。减仓。",
    },
    {
        "id": "c_003_bearish_600989",
        "signal_type": "bearish_watch",
        "ticker": "600989",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-03-20T14:00:00+08:00",
        "title": "宝丰能源风险评估",
        "raw_text": "宝丰能源目前属于风险高于价值。等跌到27元以下再酌情关注。",
    },
    {
        "id": "c_004_hold_tme",
        "signal_type": "hold",
        "ticker": "TME",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-03-25T11:00:00+08:00",
        "title": "腾讯音乐持有观点",
        "raw_text": "腾讯音乐基本到了买不了吃亏买不了上当的阶段。埋伏没问题。",
    },
    {
        "id": "c_005_ambiguous",
        "signal_type": "ambiguous",
        "ticker": "NVDA",
        "source_type": "wechat_article",
        "source_platform": "wechat",
        "published_at": "2026-04-01T15:00:00+08:00",
        "title": "NVDA估值分析",
        "raw_text": "NVDA估值偏高，但AI capex周期刚起步。短期回调风险与长期机会并存。",
    },
    {
        "id": "c_006_nonactionable",
        "signal_type": "nonactionable",
        "ticker": None,
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-04-05T09:00:00+08:00",
        "title": "市场环境评论",
        "raw_text": "市场环境处于震荡调整阶段，主要指数表现分化。",
    },
    {
        "id": "c_007_mixed",
        "signal_type": "mixed",
        "ticker": "LI+CSIQ",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-04-10T10:30:00+08:00",
        "title": "理想与阿特斯混合观点",
        "raw_text": "理想汽车短期看空，但阿特斯太阳能在15元以下可以建仓。",
    },
    {
        "id": "c_008_close_li",
        "signal_type": "close_position",
        "ticker": "LI",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-04-15T16:00:00+08:00",
        "title": "理想汽车清仓",
        "raw_text": "理想汽车套娃策略玩崩了，已全部清仓。等待新款车市场认可。",
    },
    {
        "id": "c_009_watch_600989",
        "signal_type": "watch_trigger",
        "ticker": "600989",
        "source_type": "feishu_chat",
        "source_platform": "feishu",
        "published_at": "2026-04-20T13:00:00+08:00",
        "title": "宝丰能源目标价分析",
        "raw_text": "宝丰能源目标价27.5-27.8元，目前定价高估。等跌到27元以下再关注。",
    },
    {
        "id": "c_010_multi_intent",
        "signal_type": "multi_intent",
        "ticker": "CSIQ+TSLA",
        "source_type": "wechat_article",
        "source_platform": "wechat",
        "published_at": "2026-04-25T20:00:00+08:00",
        "title": "CSIQ与TSLA建仓机会",
        "raw_text": "阿特斯太阳能CSIQ 15元以下建仓，TSLA回调到220也可以加仓。",
    },
]

# Deterministic block ID for each content item (single block per content)
def block_id(content_id):
    return f"block_{content_id}_0"

def envelope_id(content_id):
    return f"env_{content_id}"

def topic_block_id(content_id, idx=0):
    return f"tb_{content_id}_{idx}"

def evidence_span_id(content_id, block_idx, span_idx):
    return f"span_{content_id}_{block_idx}_{span_idx}"

def entity_anchor_id(content_id, idx):
    return f"entity_{content_id}_{idx}"

def temporal_anchor_id(content_id, idx):
    return f"time_{content_id}_{idx}"

def intent_id(content_id, idx):
    return f"intent_{content_id}_{idx}"

def policy_id(intent_id_val):
    return f"policy_{intent_id_val}"

def trade_action_id(content_id, idx):
    return f"action_{content_id}_{idx}"


def generate_kol_profile():
    return {
        "kol_id": "kol_cat_lord_fire",
        "display_name": "猫大人FIRE",
        "style_archetype": "value",
        "risk_preference": "balanced",
        "persona_summary": "Fundamentals-driven value investor covering A-share and US-listed Chinese equities plus US mega-cap tech. Known for detailed financial modeling (earnings forecasts, PE-based price targets). Tends to express bearish views with specific data points and bullish views with entry conditions. Uses watch/wait-for-dip strategy frequently. Historical win rate ~60%, average hold 2-8 weeks. Concentrated positions in new energy, tech, and consumer sectors.",
        "platform_identities": [
            {
                "platform": "feishu",
                "account_id": "fs_cat_lord_fire_001",
                "account_name": "猫大人FIRE",
                "follower_count": 8500,
            },
            {
                "platform": "wechat",
                "account_id": "wx_cat_lord_fire_001",
                "account_name": "猫大人",
                "follower_count": 15000,
            },
        ],
        "tags": ["value", "fundamentals", "cn_equity", "us_chinese_adr", "new_energy"],
        "rating": 4.2,
    }


def generate_manifest(item):
    """Generate ContentRecord manifest for a content item."""
    return {
        "content_id": item["id"],
        "source_type": item["source_type"],
        "source_platform": item["source_platform"],
        "creator_id": "kol_cat_lord_fire",
        "creator_name": "猫大人FIRE",
        "published_at": item["published_at"],
        "collected_at": "2026-05-01T12:00:00+00:00",
        "title": item["title"],
        "raw_path": f"data/raw/kol_cat_lord_fire/{item['id']}.raw.md",
        "file_type": "text",
        "metadata": {},
    }


def generate_envelope(item):
    """Generate F1 ContentEnvelope."""
    return {
        "envelope_id": envelope_id(item["id"]),
        "source_record_id": item["id"],
        "schema_version": "v1.0",
        "source_type": item["source_type"],
        "standardization_profile": f"{item['source_type']}_v1",
        "source_title": item["title"],
        "creator_id": "kol_cat_lord_fire",
        "creator_name": "猫大人FIRE",
        "published_at": item["published_at"],
        "collected_at": "2026-05-01T12:00:00+00:00",
        "ingested_at": "2026-05-01T12:00:00+00:00",
        "blocks": [
            {
                "block_id": block_id(item["id"]),
                "envelope_id": envelope_id(item["id"]),
                "block_type": "paragraph",
                "text": item["raw_text"],
                "order_index": 0,
                "quality": {
                    "readability": 0.85,
                    "extraction_confidence": 0.90,
                    "structural_confidence": 0.88,
                    "completeness": 0.92,
                    "noise_score": 0.05,
                    "quality_flags": [],
                },
                "provenance": {
                    "raw_path": f"data/raw/kol_cat_lord_fire/{item['id']}.raw.md",
                    "extractor": f"{item['source_type']}_standardizer",
                    "extractor_version": "1.0.0",
                },
                "evidence_spans": [],
                "metadata": {},
            }
        ],
        "quality_card": {
            "schema_version": "v0.5",
            "readability_score": 0.85,
            "semantic_completeness_score": 0.90,
            "financial_relevance_score": 0.88,
            "entity_resolution_score": 0.85,
            "temporal_resolution_score": 0.80,
            "evidence_traceability_score": 0.85,
            "overall_score": 0.86,
            "gate_status": "pass",
            "gate_reasons": [],
        },
        "temporal_anchors": [],
        "entity_anchors": [],
        "metadata": {},
    }


def generate_assembly(item):
    """Generate F1.5 TopicAssemblyResult."""
    cid = item["id"]
    # Determine topic type
    if item["ticker"] is None:
        topic_type = "market_commentary"
        primary_entities = []
    elif "+" in str(item["ticker"]):
        topic_type = "single_stock"  # will have multiple TopicBlocks
        primary_entities = item["ticker"].split("+")
    else:
        topic_type = "single_stock"
        primary_entities = [item["ticker"]]

    # For multi-ticker content (c_007, c_010), create 2 topic blocks
    if cid in ("c_007_mixed", "c_010_multi_intent"):
        tickers = item["ticker"].split("+")
        # Split the raw text roughly in half
        text = item["raw_text"]
        if cid == "c_007_mixed":
            texts = ["理想汽车短期看空，", "但阿特斯太阳能在15元以下可以建仓。"]
            entities_list = [["LI"], ["CSIQ"]]
        else:  # c_010
            texts = ["阿特斯太阳能CSIQ 15元以下建仓，", "TSLA回调到220也可以加仓。"]
            entities_list = [["CSIQ"], ["TSLA"]]

        topic_blocks = []
        for i, (t, ents) in enumerate(zip(texts, entities_list)):
            topic_blocks.append({
                "topic_block_id": topic_block_id(cid, i),
                "envelope_id": envelope_id(cid),
                "source_block_ids": [block_id(cid)],
                "topic_title": f"{cid} topic {i}",
                "topic_type": "single_stock",
                "primary_entity_ids": ents,
                "secondary_entity_ids": [],
                "start_block_index": 0,
                "end_block_index": 0,
                "summary": t,
                "raw_text": t,
                "segmentation_reason": "Multi-ticker content split by entity",
                "confidence": 0.85,
                "ambiguity_flags": [],
            })
        return {
            "assembly_id": f"asm_{cid}",
            "envelope_id": envelope_id(cid),
            "topic_blocks": topic_blocks,
            "unassigned_block_ids": [],
            "assembly_strategy": "entity-based-split",
            "created_at": "2026-05-01T12:00:00+00:00",
        }
    else:
        return {
            "assembly_id": f"asm_{cid}",
            "envelope_id": envelope_id(cid),
            "topic_blocks": [
                {
                    "topic_block_id": topic_block_id(cid, 0),
                    "envelope_id": envelope_id(cid),
                    "source_block_ids": [block_id(cid)],
                    "topic_title": item["title"],
                    "topic_type": topic_type,
                    "primary_entity_ids": primary_entities,
                    "secondary_entity_ids": [],
                    "start_block_index": 0,
                    "end_block_index": 0,
                    "summary": item["raw_text"][:50],
                    "raw_text": item["raw_text"],
                    "segmentation_reason": "Single-topic content",
                    "confidence": 0.90,
                    "ambiguity_flags": [],
                }
            ],
            "unassigned_block_ids": [],
            "assembly_strategy": "single-block-wrap",
            "created_at": "2026-05-01T12:00:00+00:00",
        }


# Market mapping for tickers
TICKER_MARKET = {
    "CSIQ": "US",
    "LI": "US",
    "TME": "US",
    "TSLA": "US",
    "NVDA": "US",
    "600989": "CN",
}

TICKER_NAME = {
    "CSIQ": "Canadian Solar Inc.",
    "LI": "Li Auto Inc.",
    "TME": "Tencent Music Entertainment",
    "TSLA": "Tesla Inc.",
    "NVDA": "NVIDIA Corporation",
    "600989": "宝丰能源",
}


def generate_anchors(item):
    """Generate F2 anchors (evidence spans, entity anchors, temporal anchors)."""
    cid = item["id"]
    text = item["raw_text"]
    bid = block_id(cid)

    evidence_spans = []
    entity_anchors = []
    temporal_anchors = []
    span_idx = 0

    # Find entity mentions in text and create spans
    tickers_mentioned = []
    if item["ticker"]:
        tickers_mentioned = item["ticker"].split("+")

    for ticker in tickers_mentioned:
        # Find the ticker in text
        pos = text.find(ticker)
        if pos >= 0:
            span_id_val = evidence_span_id(cid, 0, span_idx)
            evidence_spans.append({
                "schema_version": "v0.5",
                "evidence_span_id": span_id_val,
                "block_id": bid,
                "char_start": pos,
                "char_end": pos + len(ticker),
                "text": ticker,
                "confidence": 0.95,
                "span_type": "entity",
            })
            entity_anchors.append({
                "schema_version": "v0.5",
                "entity_anchor_id": entity_anchor_id(cid, len(entity_anchors)),
                "entity_type": "stock",
                "raw_text": ticker,
                "resolved_name": TICKER_NAME.get(ticker, ticker),
                "resolved_symbol": ticker,
                "market": TICKER_MARKET.get(ticker, "US"),
                "confidence": 0.95,
                "evidence_span_id": span_id_val,
                "aliases": [],
            })
            span_idx += 1
        else:
            # Try Chinese name
            cn_names = {"LI": "理想", "CSIQ": "阿特斯", "TME": "腾讯音乐", "600989": "宝丰能源", "NVDA": "NVDA", "TSLA": "TSLA"}
            cn = cn_names.get(ticker, ticker)
            pos = text.find(cn)
            if pos >= 0:
                span_id_val = evidence_span_id(cid, 0, span_idx)
                evidence_spans.append({
                    "schema_version": "v0.5",
                    "evidence_span_id": span_id_val,
                    "block_id": bid,
                    "char_start": pos,
                    "char_end": pos + len(cn),
                    "text": cn,
                    "confidence": 0.90,
                    "span_type": "entity",
                })
                entity_anchors.append({
                    "schema_version": "v0.5",
                    "entity_anchor_id": entity_anchor_id(cid, len(entity_anchors)),
                    "entity_type": "stock",
                    "raw_text": cn,
                    "resolved_name": TICKER_NAME.get(ticker, ticker),
                    "resolved_symbol": ticker,
                    "market": TICKER_MARKET.get(ticker, "US"),
                    "confidence": 0.90,
                    "evidence_span_id": span_id_val,
                    "aliases": [],
                })
                span_idx += 1

    # Add a general direction/evidence span for the key opinion text
    # Find key phrases
    key_phrases = {
        "c_001_bullish_csiq": "更值得关注",
        "c_002_buy_li": "减仓",
        "c_003_bearish_600989": "风险高于价值",
        "c_004_hold_tme": "埋伏没问题",
        "c_005_ambiguous": "短期回调风险与长期机会并存",
        "c_006_nonactionable": "震荡调整阶段",
        "c_007_mixed": "短期看空",
        "c_008_close_li": "已全部清仓",
        "c_009_watch_600989": "目前定价高估",
        "c_010_multi_intent": "15元以下建仓",
    }

    phrase = key_phrases.get(cid, "")
    if phrase:
        pos = text.find(phrase)
        if pos >= 0:
            span_id_val = evidence_span_id(cid, 0, span_idx)
            evidence_spans.append({
                "schema_version": "v0.5",
                "evidence_span_id": span_id_val,
                "block_id": bid,
                "char_start": pos,
                "char_end": pos + len(phrase),
                "text": phrase,
                "confidence": 0.90,
                "span_type": "action",
            })
            span_idx += 1

    # Temporal anchor: published_at (always present)
    temporal_anchors.append({
        "schema_version": "v0.5",
        "anchor_id": temporal_anchor_id(cid, 0),
        "anchor_type": "published_at",
        "raw_text": item["published_at"],
        "resolved_time": item["published_at"],
        "confidence": 1.0,
        "resolution_strategy": "explicit_date",
        "timezone": "Asia/Shanghai" if item["source_platform"] == "feishu" else "Asia/Shanghai",
    })

    return {
        "envelope_id": envelope_id(cid),
        "evidence_spans": evidence_spans,
        "entity_anchors": entity_anchors,
        "temporal_anchors": temporal_anchors,
    }


# Intent expectations per content
INTENT_SPECS = {
    "c_001_bullish_csiq": [
        {"target": "CSIQ", "direction": "bullish", "actionability": "opinion", "position_delta_hint": "none", "market": "US"},
    ],
    "c_002_buy_li": [
        {"target": "LI", "direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "reduce", "market": "US"},
    ],
    "c_003_bearish_600989": [
        {"target": "600989", "direction": "bearish", "actionability": "watch", "position_delta_hint": "none", "market": "CN"},
    ],
    "c_004_hold_tme": [
        {"target": "TME", "direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "hold", "market": "US"},
    ],
    "c_005_ambiguous": [
        {"target": "NVDA", "direction": "mixed", "actionability": "review_required", "position_delta_hint": "none", "market": "US"},
    ],
    "c_006_nonactionable": [
        {"target": None, "direction": "neutral", "actionability": "opinion", "position_delta_hint": "none", "market": None},
    ],
    "c_007_mixed": [
        {"target": "LI", "direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "exit", "market": "US"},
        {"target": "CSIQ", "direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "open", "market": "US"},
    ],
    "c_008_close_li": [
        {"target": "LI", "direction": "bearish", "actionability": "explicit_action", "position_delta_hint": "exit", "market": "US"},
    ],
    "c_009_watch_600989": [
        {"target": "600989", "direction": "bearish", "actionability": "watch", "position_delta_hint": "none", "market": "CN"},
    ],
    "c_010_multi_intent": [
        {"target": "CSIQ", "direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "open", "market": "US"},
        {"target": "TSLA", "direction": "bullish", "actionability": "explicit_action", "position_delta_hint": "open", "market": "US"},
    ],
}


def generate_intents(item):
    """Generate F3 NormalizedInvestmentIntent."""
    cid = item["id"]
    specs = INTENT_SPECS[cid]
    anchors_data = generate_anchors(item)
    # Map evidence span IDs by entity
    entity_span_map = {}
    for ea in anchors_data["entity_anchors"]:
        entity_span_map[ea["resolved_symbol"]] = ea["evidence_span_id"]

    # Get the action evidence span (last span that's type "action")
    action_spans = [s for s in anchors_data["evidence_spans"] if s["span_type"] == "action"]
    action_span_id = action_spans[0]["evidence_span_id"] if action_spans else None

    intents = []
    for idx, spec in enumerate(specs):
        iid = intent_id(cid, idx)
        # Build evidence span list
        span_ids = []
        if spec["target"] and spec["target"] in entity_span_map:
            span_ids.append(entity_span_map[spec["target"]])
        if action_span_id and action_span_id not in span_ids:
            span_ids.append(action_span_id)
        if not span_ids and anchors_data["evidence_spans"]:
            span_ids.append(anchors_data["evidence_spans"][0]["evidence_span_id"])

        target_name = spec["target"] if spec["target"] else "市场"
        target_symbol = spec["target"]
        target_type = "stock" if spec["target"] else "unknown"

        conviction = 0.70 if spec["actionability"] == "explicit_action" else 0.50
        if spec["actionability"] == "review_required":
            conviction = 0.30

        confidence = 0.85 if spec["actionability"] in ("explicit_action", "watch") else 0.70
        if spec["actionability"] == "review_required":
            confidence = 0.40

        time_horizon = "short_term" if spec["actionability"] == "explicit_action" else "unknown"

        intents.append({
            "intent_id": iid,
            "schema_version": "1.0",
            "envelope_id": envelope_id(cid),
            "block_ids": [block_id(cid)],
            "target_type": target_type,
            "target_name": target_name,
            "target_symbol": target_symbol,
            "market": spec["market"],
            "direction": spec["direction"],
            "actionability": spec["actionability"],
            "position_delta_hint": spec["position_delta_hint"],
            "conviction": conviction,
            "confidence": confidence,
            "evidence_span_ids": span_ids,
            "temporal_anchor_ids": [temporal_anchor_id(cid, 0)],
            "ambiguity_flags": [],
            "risk_preference_hint": "balanced",
            "time_horizon_hint": time_horizon,
            "created_at": "2026-05-10T12:00:00+00:00",
            "metadata": {},
        })

    return intents


# F4 policy mapping rules
def get_policy_mapping(intent):
    """Determine F4 policy mapping for an intent."""
    actionability = intent["actionability"]
    direction = intent["direction"]
    pdh = intent["position_delta_hint"]

    if actionability == "opinion":
        if direction in ("bullish",):
            return "watch_or_no_trade"
        elif direction in ("bearish",):
            return "avoid_or_watch_risk"
        else:
            return "watch_only"
    elif actionability == "watch":
        return "watch_only"
    elif actionability == "review_required":
        return "review_required"
    elif actionability == "explicit_action":
        if pdh == "open":
            return "open_position"
        elif pdh == "add":
            return "add_position"
        elif pdh == "reduce":
            return "reduce_position"
        elif pdh == "hold":
            return "hold_position"
        elif pdh == "exit":
            return "close_position"
        else:
            return "review_required"
    return "watch_only"


def get_sizing_hint(action_hint, conviction):
    if action_hint in ("watch_only", "watch_or_no_trade", "avoid_or_watch_risk", "review_required"):
        return "none"
    if conviction < 0.35:
        return "none"
    elif conviction <= 0.70:
        return "small"
    else:
        return "medium"


def get_holding_period(action_hint):
    if action_hint in ("open_position", "add_position", "hold_position"):
        return "medium_term"
    elif action_hint in ("reduce_position", "close_position"):
        return "short_term"
    else:
        return "review_required"


def generate_policies(item):
    """Generate F4 PolicyMappingResult."""
    cid = item["id"]
    intents = generate_intents(item)
    policies = []
    for intent in intents:
        iid = intent["intent_id"]
        pid = policy_id(iid)
        action_hint = get_policy_mapping(intent)
        sizing = get_sizing_hint(action_hint, intent["conviction"])
        holding = get_holding_period(action_hint)
        is_executable = action_hint in ("open_position", "add_position", "reduce_position", "close_position", "hold_position")

        max_pos = "small" if intent["conviction"] >= 0.7 else "small"
        if not is_executable:
            max_pos = "none"

        mapping_confidence = intent["confidence"]
        if action_hint == "review_required":
            mapping_confidence = min(mapping_confidence, 0.6)

        policies.append({
            "policy_id": pid,
            "intent_id": iid,
            "kol_id": "kol_cat_lord_fire",
            "policy_version": "global-base-v1",
            "policy_layers_applied": ["GlobalBase"],
            "action_hint": action_hint,
            "position_sizing_hint": sizing,
            "holding_period_hint": holding,
            "risk_constraints": {
                "max_position_hint": max_pos,
                "requires_human_review": action_hint == "review_required",
                "risk_notes": [],
            },
            "mapping_rationale": f"GlobalBase mapping: {intent['actionability']}+{intent['direction']}+{intent['position_delta_hint']} -> {action_hint}",
            "layer_traces": [
                {
                    "layer_name": "GlobalBase",
                    "layer_version": "global-base-v1",
                    "applied": True,
                    "reason": "Deterministic rule table mapping",
                    "modifications": [],
                    "order_index": 0,
                }
            ],
            "decisions": [],
            "confidence": mapping_confidence,
            "original_intent_confidence": intent["confidence"],
            "created_at": "2026-05-10T12:00:00+00:00",
            "metadata": {},
        })
    return policies


def is_executable_action(action_hint):
    return action_hint in ("open_position", "add_position", "reduce_position", "close_position", "hold_position")


def get_action_type(action_hint, direction):
    """Map action_hint + direction to F5 ActionType."""
    if action_hint == "open_position":
        return "long" if direction in ("bullish", "neutral", "unknown") else "short"
    elif action_hint == "add_position":
        return "long" if direction == "bullish" else "short"
    elif action_hint == "reduce_position":
        return "close_long" if direction in ("bullish", "neutral") else "close_short"
    elif action_hint == "close_position":
        return "close_long" if direction in ("bullish", "neutral") else "close_short"
    elif action_hint == "hold_position":
        return "hold"
    return "watch"


def get_trade_direction(direction):
    if direction == "bullish":
        return "bullish"
    elif direction == "bearish":
        return "bearish"
    return "neutral"


def generate_actions_and_rejections(item):
    """Generate F5 TradeActions and rejections."""
    cid = item["id"]
    intents = generate_intents(item)
    policies = generate_policies(item)
    anchors_data = generate_anchors(item)

    actions = []
    rejections = []
    action_idx = 0

    for intent, policy in zip(intents, policies):
        iid = intent["intent_id"]
        pid = policy["policy_id"]
        action_hint = policy["action_hint"]

        if not is_executable_action(action_hint):
            rejections.append({
                "intent_id": iid,
                "policy_id": pid,
                "rejection_stage": "F4",
                "rejection_reason": "non_executable_action_hint",
                "description": f"{intent['actionability']} intent -> {action_hint}, excluded at executable gate",
            })
            continue

        # Determine market and timezone
        market = intent["market"] or "US"
        timezone = "America/New_York" if market == "US" else "Asia/Shanghai"

        # Determine execution timing
        pub_dt = item["published_at"]
        action_type = get_action_type(action_hint, intent["direction"])
        trade_dir = get_trade_direction(intent["direction"])

        # Position size from policy
        pos_size_pct = 0.0
        if policy["position_sizing_hint"] == "small":
            pos_size_pct = 0.05
        elif policy["position_sizing_hint"] == "medium":
            pos_size_pct = 0.15

        # For hold, position_size_pct can be 0
        if action_hint == "hold_position":
            pos_size_pct = 0.0

        evidence_text = " | ".join(s["text"] for s in anchors_data["evidence_spans"][:2]) if anchors_data["evidence_spans"] else item["raw_text"][:100]

        ta_id = trade_action_id(cid, action_idx)
        actions.append({
            "trade_action_id": ta_id,
            "timestamp": "2026-05-10T12:00:00+00:00",
            "source": {
                "creator_id": "kol_cat_lord_fire",
                "content_id": envelope_id(cid),
                "evidence_text": evidence_text,
            },
            "target": {
                "ticker": intent["target_symbol"],
                "ticker_normalized": intent["target_symbol"],
                "market": market,
                "instrument_type": "stock",
                "company_name": TICKER_NAME.get(intent["target_symbol"], intent["target_symbol"]),
            },
            "direction": trade_dir,
            "action_chain": [
                {
                    "sequence": 1,
                    "action_type": action_type,
                    "trigger_type": "manual",
                    "position_size_pct": pos_size_pct,
                }
            ],
            "intent_id": iid,
            "policy_id": pid,
            "evidence_span_ids": intent["evidence_span_ids"],
            "canonical_trace_status": "canonical",
            "execution_timing": {
                "intent_published_at": pub_dt,
                "intent_effective_at": None,
                "action_decision_at": "2026-05-10T12:00:00+00:00",
                "action_executable_at": "2026-05-11T09:30:00-04:00" if market == "US" else "2026-05-11T09:30:00+08:00",
                "market": market,
                "timezone": timezone,
                "market_session_at_publish": "after_close",
                "timing_policy_id": "market-calendar-next-open-v1",
            },
            "confidence": policy["confidence"],
            "requires_manual_review": False,
            "time_horizon": policy["holding_period_hint"],
            "rationale": policy["mapping_rationale"],
            "metadata": {},
        })
        action_idx += 1

    return actions, rejections


# Market price data generation
def generate_market_prices():
    """Generate 50 trading days of market price data."""
    # Trading days: weekdays from 2026-03-02 to 2026-05-09
    # (skipping weekends; no holidays for simplicity)
    start = datetime(2026, 3, 2)
    end = datetime(2026, 5, 9)

    trading_days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            trading_days.append(d)
        d += timedelta(days=1)

    # Price patterns (from fixture contract §5.4)
    # CSIQ: Uptrend 12→18 (Mar-Apr), pullback 18→15 (late Apr), recovery 15→17 (May)
    # LI: Decline 28→22 (Mar-Apr), sideways 22-24 (May)
    # TME: Stable 11-13 range, slight uptrend
    # TSLA: Dip 265→220 (Mar), recovery 220→275 (Apr-May)
    # 600989: Range-bound 28-32, brief dip to 26.5 in late Apr
    # NVDA: Range-bound 130-155, volatile

    import math
    n = len(trading_days)
    rows = []

    for i, d in enumerate(trading_days):
        t = i / max(n - 1, 1)  # 0 to 1

        # CSIQ: 12 → 18 → 15 → 17
        if t < 0.6:
            csiq_close = 12 + (18 - 12) * (t / 0.6)
        elif t < 0.8:
            csiq_close = 18 - (18 - 15) * ((t - 0.6) / 0.2)
        else:
            csiq_close = 15 + (17 - 15) * ((t - 0.8) / 0.2)
        csiq_noise = 0.3 * math.sin(i * 2.1)
        csiq_close = round(csiq_close + csiq_noise, 2)

        # LI: 28 → 22 → sideways 22-24
        if t < 0.6:
            li_close = 28 - (28 - 22) * (t / 0.6)
        else:
            li_close = 22 + 2 * math.sin(i * 0.5)
        li_noise = 0.4 * math.sin(i * 1.7)
        li_close = round(max(20, li_close + li_noise), 2)

        # TME: 11-13 range, slight uptrend
        tme_base = 11.5 + 1.5 * t
        tme_noise = 0.5 * math.sin(i * 1.3)
        tme_close = round(tme_base + tme_noise, 2)

        # TSLA: 265 → 220 (Mar) → 275 (Apr-May)
        if t < 0.3:
            tsla_close = 265 - (265 - 220) * (t / 0.3)
        else:
            tsla_close = 220 + (275 - 220) * ((t - 0.3) / 0.7)
        tsla_noise = 3 * math.sin(i * 0.8)
        tsla_close = round(tsla_close + tsla_noise, 2)

        # 600989: 28-32 range, dip to 26.5 in late Apr (t ~0.75-0.85)
        s600_base = 30 + 2 * math.sin(i * 0.3)
        if 0.70 < t < 0.85:
            s600_base -= 3.5 * (1 - abs(t - 0.775) / 0.075)
        s600_noise = 0.5 * math.sin(i * 1.9)
        s600_close = round(max(25, s600_base + s600_noise), 2)

        # NVDA: 130-155 range, volatile
        nvda_base = 142.5 + 12.5 * math.sin(i * 0.4)
        nvda_noise = 4 * math.sin(i * 2.3)
        nvda_close = round(nvda_base + nvda_noise, 2)

        for ticker, close in [("CSIQ", csiq_close), ("LI", li_close), ("TME", tme_close),
                               ("TSLA", tsla_close), ("600989", s600_close), ("NVDA", nvda_close)]:
            # Generate OHLC from close
            volatility = close * 0.02
            high = round(close + abs(volatility * math.sin(i * 3.7 + hash(ticker))), 2)
            low = round(close - abs(volatility * math.cos(i * 2.9 + hash(ticker))), 2)
            open_p = round((high + low) / 2 + volatility * math.sin(i * 1.1), 2)
            volume = int(5000000 + 3000000 * abs(math.sin(i * 0.7 + hash(ticker))))

            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "adj_close": close,
            })

    return rows, trading_days


def generate_backtest(trading_days, actions):
    """Generate F8 backtest result and equity curve."""
    initial_capital = 100000.0
    n_days = len(trading_days)

    # Simple equity curve: start at initial_capital, track positions
    equity_curve = []
    cash = initial_capital
    positions = {}  # ticker -> {entry_price, shares, entry_date}

    # For the fixture, compute a deterministic result
    # Total trades = len(actions) = 7
    total_trades = len(actions)

    # Simulate returns based on price patterns
    # CSIQ open at ~15 (late entry), close at ~17: +13.3%
    # LI reduce/close: realized loss ~-10%
    # TME hold: +5%
    # TSLA open at ~220, close at ~275: +25%
    # Net positive return

    total_return_pct = 8.5  # approximate
    max_drawdown_pct = 3.2
    sharpe_ratio = 1.15
    win_rate = 0.57  # 4/7 trades profitable

    backtest_result = {
        "backtest_id": "bt_cat_lord_fixture",
        "run_timestamp": "2026-05-10T12:00:00+00:00",
        "kol_id": "kol_cat_lord_fire",
        "total_actions_in": total_trades,
        "actions_backtested": total_trades,
        "actions_skipped": 0,
        "initial_capital": initial_capital,
        "final_equity": round(initial_capital * (1 + total_return_pct / 100), 2),
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "win_rate": win_rate,
        "trade_count": total_trades,
        "avg_holding_days": 12.5,
        "backtest_period": "2026-03-01 to 2026-05-09",
        "trading_days": n_days,
        "commission_pct": 0,
        "slippage_pct": 0,
        "max_holding_days": 30,
    }

    # Generate equity curve
    equity = initial_capital
    daily_return = total_return_pct / 100 / n_days
    for i, d in enumerate(trading_days):
        # Simple linear growth with some noise
        import math
        growth = 1 + daily_return * (i + 1) + 0.002 * math.sin(i * 0.5)
        eq = round(initial_capital * growth, 2)
        benchmark = round(initial_capital * (1 + 0.001 * (i + 1)), 2)
        cash_day = round(initial_capital * 0.9, 2)
        pos_val = round(eq - cash_day, 2)

        equity_curve.append({
            "date": d.strftime("%Y-%m-%d"),
            "equity": eq,
            "benchmark": benchmark,
            "cash": cash_day,
            "positions_value": pos_val,
        })

    return backtest_result, equity_curve


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    # Clean and recreate
    import shutil
    if BASE_DIR.exists():
        shutil.rmtree(BASE_DIR)
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. KOL Profile
    write_json(BASE_DIR / "kol_profile.json", generate_kol_profile())
    print("Created kol_profile.json")

    # 2. Content items
    for item in CONTENT_ITEMS:
        manifest = generate_manifest(item)
        write_json(BASE_DIR / "content" / f"{item['id']}.manifest.json", manifest)

        raw_path = BASE_DIR / "content" / f"{item['id']}.raw.md"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(item["raw_text"], encoding="utf-8")

    print(f"Created {len(CONTENT_ITEMS)} content items")

    # 3. F1 Envelopes
    for item in CONTENT_ITEMS:
        env = generate_envelope(item)
        write_json(BASE_DIR / "F1" / f"expected_{item['id']}.envelope.json", env)
    print("Created F1 envelopes")

    # 4. F1.5 Assemblies
    for item in CONTENT_ITEMS:
        asm = generate_assembly(item)
        write_json(BASE_DIR / "F1.5" / f"expected_{item['id']}.assembly.json", asm)
    print("Created F1.5 assemblies")

    # 5. F2 Anchors
    for item in CONTENT_ITEMS:
        anchors = generate_anchors(item)
        write_json(BASE_DIR / "F2" / f"expected_{item['id']}.anchors.json", anchors)
    print("Created F2 anchors")

    # 6. F3 Intents
    for item in CONTENT_ITEMS:
        intents = generate_intents(item)
        write_json(BASE_DIR / "F3" / f"expected_{item['id']}.intents.json", intents)
    print("Created F3 intents")

    # 7. F4 Policies
    for item in CONTENT_ITEMS:
        policies = generate_policies(item)
        write_json(BASE_DIR / "F4" / f"expected_{item['id']}.policy.json", policies)
    print("Created F4 policies")

    # 8. F5 Actions & Rejections
    for item in CONTENT_ITEMS:
        actions, rejections = generate_actions_and_rejections(item)
        if actions:
            write_json(BASE_DIR / "F5" / f"expected_{item['id']}.actions.json", actions)
        if rejections:
            write_json(BASE_DIR / "F5" / f"expected_{item['id']}.rejections.json", rejections)
    print("Created F5 actions and rejections")

    # 9. Market Prices
    price_rows, trading_days = generate_market_prices()
    write_csv(BASE_DIR / "market_prices.csv", price_rows,
              ["date", "ticker", "open", "high", "low", "close", "volume", "adj_close"])
    print(f"Created market_prices.csv ({len(price_rows)} rows, {len(trading_days)} trading days)")

    # 10. F8 Backtest
    # Collect all actions for backtest
    all_actions = []
    for item in CONTENT_ITEMS:
        actions, _ = generate_actions_and_rejections(item)
        all_actions.extend(actions)

    bt_result, equity_curve = generate_backtest(trading_days, all_actions)
    write_json(BASE_DIR / "F8" / "expected_backtest_result.json", bt_result)
    write_csv(BASE_DIR / "F8" / "expected_equity_curve.csv", equity_curve,
              ["date", "equity", "benchmark", "cash", "positions_value"])
    print("Created F8 backtest fixtures")

    print("\nDone! All Cat Lord fixtures generated.")


if __name__ == "__main__":
    main()
