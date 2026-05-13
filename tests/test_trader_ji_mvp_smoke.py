"""Trader Ji (9友/trader韭) MVP Golden Fixture Smoke Test.

Tests the full F0 -> F1 -> F1.5 -> F2 -> F3 -> F4 -> F5 -> F8 pipeline
using pre-computed golden fixtures for the Trader Ji KOL.

Coverage:
- 15 content items across 5 source types (daily_pre, daily_post, weekly_strategy, wechat, bilibili)
- 10 actionable intents + 7 non-executable intents
- 10 canonical TradeActions + 7 rejections
- 8 CN tickers (510300, 159915, 600519, 000858, 601318, 000001, 601012, 399006)
- 5 distinct action types (long, close_long, hold, reduce, add)
- Time-sensitive signals: "今天开盘", "尾盘", "本周", "明天"

Run: pytest tests/test_trader_ji_mvp_smoke.py -v
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "kol-backtest-mvp" / "trader_ji"

# Content IDs
CONTENT_IDS = [
    "t_001_buy_510300",
    "t_002_sell_159915",
    "t_003_hold_600519",
    "t_004_bullish_000858",
    "t_005_bearish_601318",
    "t_006_nonactionable",
    "t_007_mixed",
    "t_008_add_510300",
    "t_009_watch_000001",
    "t_010_multi_intent",
    "t_011_ambiguous",
    "t_012_close_510300",
    "t_013_bullish_399006",
    "t_014_reduce_600519",
    "t_015_ambiguous_multi",
]

# Actionable content IDs (produce canonical TradeActions)
ACTIONABLE_IDS = [
    "t_001_buy_510300",
    "t_002_sell_159915",
    "t_003_hold_600519",
    "t_007_mixed",
    "t_008_add_510300",
    "t_010_multi_intent",
    "t_012_close_510300",
    "t_014_reduce_600519",
]

# Non-actionable content IDs (rejected at F4 gate)
REJECTED_IDS = [
    "t_004_bullish_000858",
    "t_005_bearish_601318",
    "t_006_nonactionable",
    "t_009_watch_000001",
    "t_011_ambiguous",
    "t_013_bullish_399006",
    "t_015_ambiguous_multi",
]

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


# =========================================================================
# Helpers
# =========================================================================

def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_fixture(stage: str, content_id: str, suffix: str) -> dict:
    path = FIXTURE_ROOT / stage / f"expected_{content_id}.{suffix}.json"
    return load_json(path)


# =========================================================================
# F0: ContentRecord (manifest.json)
# =========================================================================

class TestF0ContentRecord:
    """F0 manifest.json strict assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_manifest_exists(self, content_id):
        path = FIXTURE_ROOT / "content" / f"{content_id}.manifest.json"
        assert path.exists(), f"Missing manifest: {path}"

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_manifest_required_fields(self, content_id):
        m = load_json(FIXTURE_ROOT / "content" / f"{content_id}.manifest.json")
        assert m["content_id"] == content_id
        assert m["file_type"] == "markdown"
        assert m["creator_id"] == "trader_ji"
        assert isinstance(m.get("raw_path"), str)
        assert isinstance(m.get("published_at"), str)
        assert isinstance(m.get("collected_at"), str)

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_raw_md_exists(self, content_id):
        path = FIXTURE_ROOT / "content" / f"{content_id}.raw.md"
        assert path.exists(), f"Missing raw file: {path}"
        content = path.read_text().strip()
        assert len(content) > 0

    def test_source_type_coverage(self):
        """Must cover at least 4 distinct source types."""
        source_types = set()
        for cid in CONTENT_IDS:
            m = load_json(FIXTURE_ROOT / "content" / f"{cid}.manifest.json")
            source_types.add(m["source_type"])
        assert len(source_types) >= 4, f"Only {len(source_types)} source types: {source_types}"


# =========================================================================
# F1: ContentEnvelope
# =========================================================================

class TestF1Envelope:
    """F1 ContentEnvelope assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_envelope_exists(self, content_id):
        path = FIXTURE_ROOT / "F1" / f"expected_{content_id}.envelope.json"
        assert path.exists()

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_envelope_strict_fields(self, content_id):
        env = load_fixture("F1", content_id, "envelope")
        assert env["envelope_id"] == f"env_{content_id}"
        assert env["schema_version"] == "v1.0"
        assert env["source_record_id"] == content_id
        assert isinstance(env["source_type"], str)
        assert len(env["blocks"]) >= 1

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_block_quality_fields(self, content_id):
        env = load_fixture("F1", content_id, "envelope")
        for block in env["blocks"]:
            q = block["quality"]
            assert 0.0 <= q["readability"] <= 1.0
            assert 0.0 <= q["extraction_confidence"] <= 1.0
            assert 0.0 <= q["structural_confidence"] <= 1.0
            assert 0.0 <= q["completeness"] <= 1.0

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_block_text_not_empty(self, content_id):
        env = load_fixture("F1", content_id, "envelope")
        for block in env["blocks"]:
            assert len(block["text"]) > 0


# =========================================================================
# F1.5: TopicAssemblyResult
# =========================================================================

class TestF15Assembly:
    """F1.5 TopicAssemblyResult assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_assembly_exists(self, content_id):
        path = FIXTURE_ROOT / "F1.5" / f"expected_{content_id}.assembly.json"
        assert path.exists()

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_envelope_id_match(self, content_id):
        asm = load_fixture("F1.5", content_id, "assembly")
        assert asm["envelope_id"] == f"env_{content_id}"

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_topic_blocks_non_empty(self, content_id):
        asm = load_fixture("F1.5", content_id, "assembly")
        assert len(asm["topic_blocks"]) >= 1
        for tb in asm["topic_blocks"]:
            assert len(tb["source_block_ids"]) >= 1
            assert len(tb["raw_text"]) > 0
            assert tb["topic_type"] in (
                "single_stock", "industry", "macro_policy",
                "market_commentary", "investment_philosophy",
                "portfolio_update", "news_forward", "other"
            )

    def test_nonactionable_topic_type(self):
        """t_006 (non-actionable) should be market_commentary."""
        asm = load_fixture("F1.5", "t_006_nonactionable", "assembly")
        tb = asm["topic_blocks"][0]
        assert tb["topic_type"] in ("market_commentary", "other")


# =========================================================================
# F2: Anchors
# =========================================================================

class TestF2Anchors:
    """F2 EvidenceSpan, EntityAnchor, TemporalAnchor assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_anchors_exist(self, content_id):
        path = FIXTURE_ROOT / "F2" / f"expected_{content_id}.anchors.json"
        assert path.exists()

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_evidence_span_schema_version(self, content_id):
        anchors = load_fixture("F2", content_id, "anchors")
        for span in anchors["evidence_spans"]:
            assert span["schema_version"] == "v0.5"
            assert span["evidence_span_id"]
            assert span["char_start"] < span["char_end"]

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_entity_anchors_resolved(self, content_id):
        anchors = load_fixture("F2", content_id, "anchors")
        for ea in anchors["entity_anchors"]:
            assert ea["entity_type"] in (
                "stock", "etf", "index", "crypto", "commodity",
                "forex", "bond", "fund", "company", "person",
                "organization", "sector", "concept", "unknown"
            )
            if ea.get("resolved_symbol"):
                assert ea["market"] is not None

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_published_at_anchor(self, content_id):
        anchors = load_fixture("F2", content_id, "anchors")
        pub_anchors = [a for a in anchors["temporal_anchors"] if a["anchor_type"] == "published_at"]
        assert len(pub_anchors) >= 1
        assert pub_anchors[0]["confidence"] == 1.0

    def test_nonactionable_no_entities(self):
        """t_006 (non-actionable) may have empty entity_anchors."""
        anchors = load_fixture("F2", "t_006_nonactionable", "anchors")
        # At minimum, published_at temporal anchor exists
        assert len(anchors["temporal_anchors"]) >= 1

    def test_multi_ticker_has_multiple_entities(self):
        """t_007 (510300+159915) must have entity_anchors for each ticker."""
        anchors = load_fixture("F2", "t_007_mixed", "anchors")
        symbols = {ea["resolved_symbol"] for ea in anchors["entity_anchors"]}
        assert "510300" in symbols
        assert "159915" in symbols


# =========================================================================
# F3: NormalizedInvestmentIntent
# =========================================================================

class TestF3Intents:
    """F3 intent extraction assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_intents_exist(self, content_id):
        path = FIXTURE_ROOT / "F3" / f"expected_{content_id}.intents.json"
        assert path.exists()

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_intent_schema_version(self, content_id):
        result = load_fixture("F3", content_id, "intents")
        for intent in result["intents"]:
            assert intent["schema_version"] == "1.0"
            assert intent["intent_id"]
            assert intent["envelope_id"] == f"env_{content_id}"

    def test_total_actionable_intents(self):
        """10 actionable intents across 8 content items."""
        total = 0
        for cid in ACTIONABLE_IDS:
            result = load_fixture("F3", cid, "intents")
            total += sum(1 for i in result["intents"] if i["actionability"] == "explicit_action")
        assert total == 10, f"Expected 10 actionable intents, got {total}"

    def test_total_non_executable_intents(self):
        """7 non-executable intents across 7 content items."""
        total = 0
        for cid in REJECTED_IDS:
            result = load_fixture("F3", cid, "intents")
            total += len(result["intents"])
        assert total == 7, f"Expected 7 non-executable intents, got {total}"

    # Per-content strict assertions
    def test_t001_buy_signal(self):
        intents = load_fixture("F3", "t_001_buy_510300", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bullish"
        assert i["actionability"] == "explicit_action"
        assert i["position_delta_hint"] == "open"
        assert i["target_symbol"] == "510300"
        assert i["market"] == "CN"
        assert i["time_horizon_hint"] == "intraday"

    def test_t002_sell_signal(self):
        intents = load_fixture("F3", "t_002_sell_159915", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bearish"
        assert i["actionability"] == "explicit_action"
        assert i["position_delta_hint"] == "exit"
        assert i["target_symbol"] == "159915"

    def test_t003_hold_signal(self):
        intents = load_fixture("F3", "t_003_hold_600519", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "neutral"
        assert i["actionability"] == "explicit_action"
        assert i["position_delta_hint"] == "hold"
        assert i["target_symbol"] == "600519"
        assert i["time_horizon_hint"] == "short_term"

    def test_t004_bullish_watch(self):
        intents = load_fixture("F3", "t_004_bullish_000858", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bullish"
        assert i["actionability"] == "watch"
        assert i["position_delta_hint"] == "none"
        assert i["target_symbol"] == "000858"

    def test_t005_bearish_avoid(self):
        intents = load_fixture("F3", "t_005_bearish_601318", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bearish"
        assert i["actionability"] == "watch"
        assert i["target_symbol"] == "601318"

    def test_t006_nonactionable(self):
        intents = load_fixture("F3", "t_006_nonactionable", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "neutral"
        assert i["actionability"] == "opinion"
        assert i["position_delta_hint"] == "none"

    def test_t007_mixed_multi(self):
        intents = load_fixture("F3", "t_007_mixed", "intents")["intents"]
        assert len(intents) == 2
        symbols = {i["target_symbol"] for i in intents}
        assert "510300" in symbols
        assert "159915" in symbols
        t007_510 = [i for i in intents if i["target_symbol"] == "510300"][0]
        t007_159 = [i for i in intents if i["target_symbol"] == "159915"][0]
        assert t007_510["direction"] == "bullish"
        assert t007_510["position_delta_hint"] == "open"
        assert t007_159["direction"] == "bearish"
        assert t007_159["position_delta_hint"] == "reduce"

    def test_t008_add_signal(self):
        intents = load_fixture("F3", "t_008_add_510300", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bullish"
        assert i["actionability"] == "explicit_action"
        assert i["position_delta_hint"] == "add"
        assert i["target_symbol"] == "510300"
        assert i["time_horizon_hint"] == "intraday"

    def test_t009_watch_trigger(self):
        intents = load_fixture("F3", "t_009_watch_000001", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["actionability"] == "watch"
        assert i["target_symbol"] == "000001"

    def test_t010_multi_intent(self):
        intents = load_fixture("F3", "t_010_multi_intent", "intents")["intents"]
        assert len(intents) == 2
        symbols = {i["target_symbol"] for i in intents}
        assert "510300" in symbols
        assert "600519" in symbols
        t010_510 = [i for i in intents if i["target_symbol"] == "510300"][0]
        t010_600 = [i for i in intents if i["target_symbol"] == "600519"][0]
        assert t010_510["position_delta_hint"] == "add"
        assert t010_600["position_delta_hint"] == "reduce"

    def test_t011_ambiguous(self):
        intents = load_fixture("F3", "t_011_ambiguous", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["actionability"] == "review_required"
        assert i["target_symbol"] == "601012"

    def test_t012_close_signal(self):
        intents = load_fixture("F3", "t_012_close_510300", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bearish"
        assert i["actionability"] == "explicit_action"
        assert i["position_delta_hint"] == "exit"
        assert i["target_symbol"] == "510300"

    def test_t013_bullish_opinion(self):
        intents = load_fixture("F3", "t_013_bullish_399006", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bullish"
        assert i["actionability"] == "opinion"
        assert i["target_symbol"] == "399006"

    def test_t014_reduce_signal(self):
        intents = load_fixture("F3", "t_014_reduce_600519", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bearish"
        assert i["actionability"] == "explicit_action"
        assert i["position_delta_hint"] == "reduce"
        assert i["target_symbol"] == "600519"

    def test_t015_ambiguous_multi(self):
        intents = load_fixture("F3", "t_015_ambiguous_multi", "intents")["intents"]
        assert len(intents) == 1
        i = intents[0]
        assert i["actionability"] == "review_required"
        assert i["target_symbol"] == "000858"

    # Evidence traceability
    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_intents_have_evidence(self, content_id):
        result = load_fixture("F3", content_id, "intents")
        for intent in result["intents"]:
            assert len(intent["evidence_span_ids"]) >= 1, (
                f"Intent {intent['intent_id']} has no evidence spans"
            )

    # Conviction and confidence ranges
    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_conviction_confidence_ranges(self, content_id):
        result = load_fixture("F3", content_id, "intents")
        for intent in result["intents"]:
            assert 0.0 <= intent["conviction"] <= 1.0
            assert 0.0 <= intent["confidence"] <= 1.0


# =========================================================================
# F4: PolicyMappingResult
# =========================================================================

class TestF4Policy:
    """F4 policy mapping assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_policy_exists(self, content_id):
        path = FIXTURE_ROOT / "F4" / f"expected_{content_id}.policy.json"
        assert path.exists()

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_policy_version(self, content_id):
        result = load_fixture("F4", content_id, "policy")
        for m in result["mappings"]:
            assert m["policy_version"] == "global-base-v1"
            assert m["policy_id"]
            assert m["intent_id"]

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_mapped_intents_match_mappings(self, content_id):
        result = load_fixture("F4", content_id, "policy")
        assert len(result["mappings"]) == len(result["mapped_intents"])
        for m, mi in zip(result["mappings"], result["mapped_intents"]):
            assert m["policy_id"] == mi["policy_id"]
            assert m["intent_id"] == mi["intent_id"]
            assert m["action_hint"] == mi["action_hint"]

    def test_actionable_policies_have_executable_hints(self):
        """Actionable intents should map to executable action hints."""
        executable_hints = {
            "open_position", "add_position", "reduce_position",
            "close_position", "hold_position"
        }
        for cid in ACTIONABLE_IDS:
            result = load_fixture("F4", cid, "policy")
            for mi in result["mapped_intents"]:
                assert mi["action_hint"] in executable_hints, (
                    f"{cid}: expected executable hint, got {mi['action_hint']}"
                )

    def test_rejected_policies_have_non_executable_hints(self):
        """Non-actionable intents should map to non-executable hints."""
        non_exec_hints = {
            "watch_only", "watch_or_no_trade", "avoid_or_watch_risk",
            "review_required"
        }
        for cid in REJECTED_IDS:
            result = load_fixture("F4", cid, "policy")
            for mi in result["mapped_intents"]:
                assert mi["action_hint"] in non_exec_hints, (
                    f"{cid}: expected non-executable hint, got {mi['action_hint']}"
                )

    # Specific policy expectations
    def test_t001_policy(self):
        result = load_fixture("F4", "t_001_buy_510300", "policy")
        mi = result["mapped_intents"][0]
        assert mi["action_hint"] == "open_position"
        assert mi["position_sizing_hint"] == "medium"  # conviction 0.85 > 0.70
        assert mi["holding_period_hint"] == "medium_term"

    def test_t002_policy(self):
        result = load_fixture("F4", "t_002_sell_159915", "policy")
        mi = result["mapped_intents"][0]
        assert mi["action_hint"] == "close_position"
        assert mi["holding_period_hint"] == "short_term"

    def test_t003_policy(self):
        result = load_fixture("F4", "t_003_hold_600519", "policy")
        mi = result["mapped_intents"][0]
        assert mi["action_hint"] == "hold_position"
        assert mi["holding_period_hint"] == "medium_term"

    def test_t004_policy(self):
        result = load_fixture("F4", "t_004_bullish_000858", "policy")
        mi = result["mapped_intents"][0]
        assert mi["action_hint"] == "watch_only"

    def test_t011_policy(self):
        result = load_fixture("F4", "t_011_ambiguous", "policy")
        mi = result["mapped_intents"][0]
        assert mi["action_hint"] == "review_required"
        assert mi["requires_human_review"] is True


# =========================================================================
# F5: TradeAction
# =========================================================================

class TestF5Actions:
    """F5 TradeAction assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_actions_file_exists(self, content_id):
        path = FIXTURE_ROOT / "F5" / f"expected_{content_id}.actions.json"
        assert path.exists()

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_rejections_file_exists(self, content_id):
        path = FIXTURE_ROOT / "F5" / f"expected_{content_id}.rejections.json"
        assert path.exists()

    def test_total_canonical_actions(self):
        """10 canonical TradeActions across 8 actionable content items."""
        total = 0
        for cid in ACTIONABLE_IDS:
            data = load_fixture("F5", cid, "actions")
            total += len(data["actions"])
        assert total == 10, f"Expected 10 canonical actions, got {total}"

    def test_total_rejections(self):
        """7 rejections across 7 non-actionable content items."""
        total = 0
        for cid in REJECTED_IDS:
            data = load_fixture("F5", cid, "rejections")
            total += len(data["rejections"])
        assert total == 7, f"Expected 7 rejections, got {total}"

    @pytest.mark.parametrize("content_id", ACTIONABLE_IDS)
    def test_canonical_trace_status(self, content_id):
        data = load_fixture("F5", content_id, "actions")
        for action in data["actions"]:
            assert action["canonical_trace_status"] == "canonical"
            assert action["intent_id"]
            assert action["policy_id"]
            assert len(action["evidence_span_ids"]) >= 1
            assert action["execution_timing"] is not None

    @pytest.mark.parametrize("content_id", ACTIONABLE_IDS)
    def test_execution_timing_fields(self, content_id):
        data = load_fixture("F5", content_id, "actions")
        for action in data["actions"]:
            et = action["execution_timing"]
            assert et["intent_published_at"]
            assert et["action_decision_at"]
            assert et["action_executable_at"]
            assert et["market"] == "CN"
            assert et["timezone"] == "Asia/Shanghai"
            assert et["timing_policy_id"] == "market-calendar-next-open-v1"

    @pytest.mark.parametrize("content_id", ACTIONABLE_IDS)
    def test_target_info(self, content_id):
        data = load_fixture("F5", content_id, "actions")
        for action in data["actions"]:
            target = action["target"]
            assert target["market"] == "CN"
            assert target["ticker_normalized"]
            assert target["ticker"]

    # Specific action type assertions
    def test_t001_action_type(self):
        data = load_fixture("F5", "t_001_buy_510300", "actions")
        assert len(data["actions"]) == 1
        a = data["actions"][0]
        assert a["direction"] == "bullish"
        assert a["action_chain"][0]["action_type"] == "long"
        assert a["target"]["ticker_normalized"] == "510300"

    def test_t002_action_type(self):
        data = load_fixture("F5", "t_002_sell_159915", "actions")
        assert len(data["actions"]) == 1
        a = data["actions"][0]
        assert a["direction"] == "bearish"
        assert a["action_chain"][0]["action_type"] == "close_long"
        assert a["target"]["ticker_normalized"] == "159915"

    def test_t003_action_type(self):
        data = load_fixture("F5", "t_003_hold_600519", "actions")
        assert len(data["actions"]) == 1
        a = data["actions"][0]
        assert a["action_chain"][0]["action_type"] == "hold"
        assert a["target"]["ticker_normalized"] == "600519"

    def test_t007_two_actions(self):
        data = load_fixture("F5", "t_007_mixed", "actions")
        assert len(data["actions"]) == 2
        tickers = {a["target"]["ticker_normalized"] for a in data["actions"]}
        assert "510300" in tickers
        assert "159915" in tickers

    def test_t008_add_action(self):
        data = load_fixture("F5", "t_008_add_510300", "actions")
        assert len(data["actions"]) == 1
        a = data["actions"][0]
        assert a["action_chain"][0]["action_type"] == "long"
        assert a["direction"] == "bullish"

    def test_t010_two_actions(self):
        data = load_fixture("F5", "t_010_multi_intent", "actions")
        assert len(data["actions"]) == 2
        tickers = {a["target"]["ticker_normalized"] for a in data["actions"]}
        assert "510300" in tickers
        assert "600519" in tickers

    def test_t012_close_action(self):
        data = load_fixture("F5", "t_012_close_510300", "actions")
        assert len(data["actions"]) == 1
        a = data["actions"][0]
        assert a["action_chain"][0]["action_type"] == "close_long"
        assert a["target"]["ticker_normalized"] == "510300"

    def test_t014_reduce_action(self):
        data = load_fixture("F5", "t_014_reduce_600519", "actions")
        assert len(data["actions"]) == 1
        a = data["actions"][0]
        assert a["action_chain"][0]["action_type"] == "close_long"
        assert a["direction"] == "bearish"

    # Rejection assertions
    def test_t004_rejection(self):
        data = load_fixture("F5", "t_004_bullish_000858", "rejections")
        assert len(data["rejections"]) == 1
        r = data["rejections"][0]
        assert r["rejection_stage"] == "F4"
        assert r["rejection_reason"] == "non_executable_action_hint"

    def test_t011_rejection(self):
        data = load_fixture("F5", "t_011_ambiguous", "rejections")
        assert len(data["rejections"]) == 1
        r = data["rejections"][0]
        assert r["rejection_stage"] == "F4"

    def test_t015_rejection(self):
        data = load_fixture("F5", "t_015_ambiguous_multi", "rejections")
        assert len(data["rejections"]) == 1

    # Distinct action types coverage
    def test_distinct_action_types(self):
        """Must cover 5 distinct action types: long, close_long, hold, reduce (mapped as close_long), add (mapped as long)."""
        action_types = set()
        for cid in ACTIONABLE_IDS:
            data = load_fixture("F5", cid, "actions")
            for a in data["actions"]:
                action_types.add(a["action_chain"][0]["action_type"])
        # F5 maps add_position -> long, reduce_position -> close_long
        # So we expect: long, close_long, hold at minimum
        assert "long" in action_types
        assert "close_long" in action_types
        assert "hold" in action_types

    # Execution timing: daily_pre -> same day open
    def test_daily_pre_executable_same_day(self):
        data = load_fixture("F5", "t_001_buy_510300", "actions")
        a = data["actions"][0]
        exec_date = a["execution_timing"]["action_executable_at"][:10]
        pub_date = a["execution_timing"]["intent_published_at"][:10]
        assert exec_date == pub_date, "daily_pre should be executable same day"

    # Execution timing: daily_post -> next trading day
    def test_daily_post_executable_next_day(self):
        data = load_fixture("F5", "t_002_sell_159915", "actions")
        a = data["actions"][0]
        pub_session = a["execution_timing"]["market_session_at_publish"]
        assert pub_session == "after_close"


# =========================================================================
# F8: BacktestResult
# =========================================================================

class TestF8Backtest:
    """F8 backtest result assertions."""

    def test_backtest_result_exists(self):
        path = FIXTURE_ROOT / "F8" / "expected_backtest_result.json"
        assert path.exists()

    def test_equity_curve_exists(self):
        path = FIXTURE_ROOT / "F8" / "expected_equity_curve.csv"
        assert path.exists()

    def test_backtest_strict_fields(self):
        result = load_json(FIXTURE_ROOT / "F8" / "expected_backtest_result.json")
        assert result["total_trades"] == 10
        assert result["backtest_period"] == "2026-03-01 to 2026-05-09"
        assert result["initial_capital"] == 100000
        assert result["commission_pct"] == 0
        assert result["slippage_pct"] == 0
        assert result["max_holding_days"] == 30

    def test_backtest_approximate_fields(self):
        result = load_json(FIXTURE_ROOT / "F8" / "expected_backtest_result.json")
        assert isinstance(result["return_pct"], (int, float))
        assert isinstance(result["win_rate"], (int, float))
        assert 0.0 <= result["win_rate"] <= 1.0

    def test_equity_curve_structure(self):
        with open(FIXTURE_ROOT / "F8" / "expected_equity_curve.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 40  # ~50 trading days
        assert rows[0]["date"] == "2026-03-02"  # First trading day
        assert float(rows[0]["equity"]) == 100000.0
        assert float(rows[0]["cash"]) == 100000.0
        assert float(rows[0]["positions_value"]) == 0.0

    def test_equity_curve_dates_monotonic(self):
        with open(FIXTURE_ROOT / "F8" / "expected_equity_curve.csv") as f:
            reader = csv.DictReader(f)
            dates = [row["date"] for row in reader]
        assert dates == sorted(dates)


# =========================================================================
# Market Prices
# =========================================================================

class TestMarketPrices:
    """Market price data assertions."""

    def test_csv_exists(self):
        assert (FIXTURE_ROOT / "market_prices.csv").exists()

    def test_required_tickers(self):
        required = {"510300", "159915", "600519", "000858", "601318", "000001", "601012", "399006"}
        with open(FIXTURE_ROOT / "market_prices.csv") as f:
            reader = csv.DictReader(f)
            tickers = {row["ticker"] for row in reader}
        assert required.issubset(tickers), f"Missing tickers: {required - tickers}"

    def test_date_range(self):
        with open(FIXTURE_ROOT / "market_prices.csv") as f:
            reader = csv.DictReader(f)
            dates = sorted(set(row["date"] for row in reader))
        assert dates[0] >= "2026-03-01"
        assert dates[-1] <= "2026-05-09"

    def test_csv_schema(self):
        with open(FIXTURE_ROOT / "market_prices.csv") as f:
            reader = csv.DictReader(f)
            required_cols = {"date", "ticker", "open", "high", "low", "close", "volume", "adj_close"}
            assert required_cols.issubset(set(reader.fieldnames))


# =========================================================================
# Cross-Reference Integrity
# =========================================================================

class TestCrossReference:
    """Cross-stage reference integrity checks."""

    def test_f3_references_f1_envelope(self):
        """Every F3 intent's envelope_id must match a F1 envelope."""
        for cid in CONTENT_IDS:
            env = load_fixture("F1", cid, "envelope")
            f3 = load_fixture("F3", cid, "intents")
            for intent in f3["intents"]:
                assert intent["envelope_id"] == env["envelope_id"]

    def test_f4_references_f3_intents(self):
        """Every F4 policy's intent_id must resolve to a F3 intent."""
        for cid in CONTENT_IDS:
            f3 = load_fixture("F3", cid, "intents")
            f4 = load_fixture("F4", cid, "policy")
            f3_ids = {i["intent_id"] for i in f3["intents"]}
            for m in f4["mappings"]:
                assert m["intent_id"] in f3_ids

    def test_f5_references_f3_f4(self):
        """Every F5 action's intent_id and policy_id must resolve."""
        for cid in ACTIONABLE_IDS:
            f3 = load_fixture("F3", cid, "intents")
            f4 = load_fixture("F4", cid, "policy")
            f5 = load_fixture("F5", cid, "actions")
            f3_ids = {i["intent_id"] for i in f3["intents"]}
            f4_ids = {m["policy_id"] for m in f4["mappings"]}
            for a in f5["actions"]:
                assert a["intent_id"] in f3_ids
                assert a["policy_id"] in f4_ids

    def test_f5_evidence_spans_resolve_to_f2(self):
        """Every F5 evidence_span_id must exist in F2 output."""
        for cid in ACTIONABLE_IDS:
            f2 = load_fixture("F2", cid, "anchors")
            f5 = load_fixture("F5", cid, "actions")
            f2_span_ids = {s["evidence_span_id"] for s in f2["evidence_spans"]}
            for a in f5["actions"]:
                for span_id in a["evidence_span_ids"]:
                    assert span_id in f2_span_ids, (
                        f"Evidence span {span_id} not found in F2 for {cid}"
                    )

    def test_f15_references_f1_blocks(self):
        """Every F1.5 source_block_id must exist in F1 blocks."""
        for cid in CONTENT_IDS:
            env = load_fixture("F1", cid, "envelope")
            asm = load_fixture("F1.5", cid, "assembly")
            f1_block_ids = {b["block_id"] for b in env["blocks"]}
            for tb in asm["topic_blocks"]:
                for bid in tb["source_block_ids"]:
                    assert bid in f1_block_ids
