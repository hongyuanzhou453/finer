"""Cat Lord (猫大人FIRE) MVP Golden Fixture Smoke Test.

Tests the full F0 -> F1 -> F1.5 -> F2 -> F3 -> F4 -> F5 -> F8 pipeline
using pre-computed golden fixtures for the Cat Lord KOL.

Coverage:
- 10 content items (c_001-c_010)
- 5 actionable content items -> 7 canonical TradeActions
- 5 rejected content items -> 5 rejections
- 4 US tickers (LI, TME, CSIQ, TSLA)
- Value investor archetype (fundamentals-driven, CN/US equities)
- Time-sensitive signals: "明天", "下周", "财报后"

Run: pytest tests/test_cat_lord_mvp_smoke.py -v
"""

import csv
import json
import os
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "kol-backtest-mvp" / "cat_lord"

# Content IDs
CONTENT_IDS = [
    "c_001_bullish_csiq",
    "c_002_buy_li",
    "c_003_bearish_600989",
    "c_004_hold_tme",
    "c_005_ambiguous",
    "c_006_nonactionable",
    "c_007_mixed",
    "c_008_close_li",
    "c_009_watch_600989",
    "c_010_multi_intent",
]

# Actionable content IDs (produce canonical TradeActions)
ACTIONABLE_IDS = [
    "c_002_buy_li",
    "c_004_hold_tme",
    "c_007_mixed",
    "c_008_close_li",
    "c_010_multi_intent",
]

# Non-actionable content IDs (rejected at F4 gate)
REJECTED_IDS = [
    "c_001_bullish_csiq",
    "c_003_bearish_600989",
    "c_005_ambiguous",
    "c_006_nonactionable",
    "c_009_watch_600989",
]

# Expected tickers in market data
REQUIRED_TICKERS = {"LI", "TME", "CSIQ", "TSLA"}


# =========================================================================
# Helpers
# =========================================================================

def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_fixture(stage: str, content_id: str, suffix: str) -> dict:
    path = FIXTURE_ROOT / stage / f"expected_{content_id}.{suffix}.json"
    return load_json(path)


def load_flat_list(stage: str, content_id: str, suffix: str) -> list:
    """Load a fixture that is a flat JSON array (Cat Lord F3/F4/F5 format)."""
    return load_fixture(stage, content_id, suffix)


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
        assert m["creator_id"] == "kol_cat_lord_fire"
        assert isinstance(m.get("raw_path"), str)
        assert isinstance(m.get("published_at"), str)

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_raw_md_exists(self, content_id):
        path = FIXTURE_ROOT / "content" / f"{content_id}.raw.md"
        assert path.exists(), f"Missing raw file: {path}"
        content = path.read_text().strip()
        assert len(content) > 0

    def test_kol_profile_exists(self):
        path = FIXTURE_ROOT / "kol_profile.json"
        assert path.exists()
        profile = load_json(path)
        assert profile["kol_id"] == "kol_cat_lord_fire"
        assert profile["style_archetype"] == "value"
        assert profile["risk_preference"] == "balanced"


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
    def test_envelope_creator(self, content_id):
        env = load_fixture("F1", content_id, "envelope")
        assert env["creator_id"] == "kol_cat_lord_fire"

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

    def test_mixed_content_multiple_topics(self):
        """c_007 (mixed: LI bearish + CSIQ bullish) should have >= 2 topic blocks."""
        asm = load_fixture("F1.5", "c_007_mixed", "assembly")
        assert len(asm["topic_blocks"]) >= 2


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
    def test_evidence_spans_exist(self, content_id):
        anchors = load_fixture("F2", content_id, "anchors")
        assert len(anchors["evidence_spans"]) >= 1
        for span in anchors["evidence_spans"]:
            assert span["evidence_span_id"]
            assert span["char_start"] < span["char_end"]

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_entity_anchors_resolved(self, content_id):
        anchors = load_fixture("F2", content_id, "anchors")
        for ea in anchors["entity_anchors"]:
            assert ea["entity_type"] in (
                "stock", "etf", "index", "crypto", "sector", "company"
            )
            if ea.get("resolved_symbol"):
                assert ea["market"] is not None

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_published_at_anchor(self, content_id):
        anchors = load_fixture("F2", content_id, "anchors")
        pub_anchors = [a for a in anchors["temporal_anchors"] if a["anchor_type"] == "published_at"]
        assert len(pub_anchors) >= 1
        assert pub_anchors[0]["confidence"] == 1.0

    def test_multi_entity_mixed(self):
        """c_007 (LI+CSIQ) must have entity_anchors for both tickers."""
        anchors = load_fixture("F2", "c_007_mixed", "anchors")
        symbols = {ea["resolved_symbol"] for ea in anchors["entity_anchors"]}
        assert "LI" in symbols
        assert "CSIQ" in symbols

    def test_multi_entity_c010(self):
        """c_010 (CSIQ+TSLA) must have entity_anchors for both tickers."""
        anchors = load_fixture("F2", "c_010_multi_intent", "anchors")
        symbols = {ea["resolved_symbol"] for ea in anchors["entity_anchors"]}
        assert "CSIQ" in symbols
        assert "TSLA" in symbols


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
        intents = load_flat_list("F3", content_id, "intents")
        for intent in intents:
            assert intent["schema_version"] == "1.0"
            assert intent["intent_id"]
            assert intent["envelope_id"] == f"env_{content_id}"

    def test_total_actionable_intents(self):
        """7 actionable intents across 5 actionable content items."""
        total = 0
        for cid in ACTIONABLE_IDS:
            intents = load_flat_list("F3", cid, "intents")
            total += sum(1 for i in intents if i["actionability"] == "explicit_action")
        assert total == 7, f"Expected 7 actionable intents, got {total}"

    def test_total_non_executable_intents(self):
        """5 non-executable intents across 5 rejected content items."""
        total = 0
        for cid in REJECTED_IDS:
            intents = load_flat_list("F3", cid, "intents")
            total += len(intents)
        assert total == 5, f"Expected 5 non-executable intents, got {total}"

    # Per-content strict assertions
    def test_c002_buy_li(self):
        intents = load_flat_list("F3", "c_002_buy_li", "intents")
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bearish"  # "减仓" = reduce/close
        assert i["actionability"] == "explicit_action"
        assert i["target_symbol"] == "LI"
        assert i["market"] == "US"

    def test_c004_hold_tme(self):
        intents = load_flat_list("F3", "c_004_hold_tme", "intents")
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bullish"
        assert i["actionability"] == "explicit_action"
        assert i["target_symbol"] == "TME"

    def test_c007_mixed_two_intents(self):
        intents = load_flat_list("F3", "c_007_mixed", "intents")
        assert len(intents) == 2
        symbols = {i["target_symbol"] for i in intents}
        assert "LI" in symbols
        assert "CSIQ" in symbols

    def test_c008_close_li(self):
        intents = load_flat_list("F3", "c_008_close_li", "intents")
        assert len(intents) == 1
        i = intents[0]
        assert i["direction"] == "bearish"
        assert i["actionability"] == "explicit_action"
        assert i["target_symbol"] == "LI"

    def test_c010_multi_intent(self):
        intents = load_flat_list("F3", "c_010_multi_intent", "intents")
        assert len(intents) == 2
        symbols = {i["target_symbol"] for i in intents}
        assert "CSIQ" in symbols
        assert "TSLA" in symbols

    def test_c001_rejected(self):
        intents = load_flat_list("F3", "c_001_bullish_csiq", "intents")
        assert len(intents) == 1
        # CSIQ bullish but rejected at F4

    def test_c006_nonactionable(self):
        intents = load_flat_list("F3", "c_006_nonactionable", "intents")
        assert len(intents) >= 1

    # Evidence traceability
    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_intents_have_evidence(self, content_id):
        intents = load_flat_list("F3", content_id, "intents")
        for intent in intents:
            assert len(intent["evidence_span_ids"]) >= 1, (
                f"Intent {intent['intent_id']} has no evidence spans"
            )

    # Conviction and confidence ranges
    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_conviction_confidence_ranges(self, content_id):
        intents = load_flat_list("F3", content_id, "intents")
        for intent in intents:
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
        mappings = load_flat_list("F4", content_id, "policy")
        for m in mappings:
            assert m["policy_version"] == "global-base-v1"
            assert m["policy_id"]
            assert m["intent_id"]

    def test_actionable_policies_have_executable_hints(self):
        """Actionable intents should map to executable action hints."""
        executable_hints = {
            "open_position", "add_position", "reduce_position",
            "close_position", "hold_position"
        }
        for cid in ACTIONABLE_IDS:
            mappings = load_flat_list("F4", cid, "policy")
            for m in mappings:
                assert m["action_hint"] in executable_hints, (
                    f"{cid}: expected executable hint, got {m['action_hint']}"
                )

    def test_rejected_policies_have_non_executable_hints(self):
        """Non-actionable intents should map to non-executable hints."""
        non_exec_hints = {
            "watch_only", "watch_or_no_trade", "avoid_or_watch_risk",
            "review_required"
        }
        for cid in REJECTED_IDS:
            mappings = load_flat_list("F4", cid, "policy")
            for m in mappings:
                assert m["action_hint"] in non_exec_hints, (
                    f"{cid}: expected non-executable hint, got {m['action_hint']}"
                )

    # Specific policy expectations
    def test_c002_policy(self):
        mappings = load_flat_list("F4", "c_002_buy_li", "policy")
        assert len(mappings) == 1
        m = mappings[0]
        assert m["action_hint"] == "reduce_position"

    def test_c004_policy(self):
        mappings = load_flat_list("F4", "c_004_hold_tme", "policy")
        assert len(mappings) == 1
        m = mappings[0]
        assert m["action_hint"] == "hold_position"

    def test_c007_two_policies(self):
        mappings = load_flat_list("F4", "c_007_mixed", "policy")
        assert len(mappings) == 2
        hints = {m["action_hint"] for m in mappings}
        assert "close_position" in hints
        assert "open_position" in hints

    def test_c008_policy(self):
        mappings = load_flat_list("F4", "c_008_close_li", "policy")
        assert len(mappings) == 1
        m = mappings[0]
        assert m["action_hint"] == "close_position"


# =========================================================================
# F5: TradeAction
# =========================================================================

class TestF5Actions:
    """F5 TradeAction assertions."""

    @pytest.mark.parametrize("content_id", CONTENT_IDS)
    def test_actions_or_rejections_exist(self, content_id):
        actions_path = FIXTURE_ROOT / "F5" / f"expected_{content_id}.actions.json"
        rejections_path = FIXTURE_ROOT / "F5" / f"expected_{content_id}.rejections.json"
        assert actions_path.exists() or rejections_path.exists(), (
            f"Neither actions nor rejections found for {content_id}"
        )

    def test_total_canonical_actions(self):
        """7 canonical TradeActions across 5 actionable content items."""
        total = 0
        for cid in ACTIONABLE_IDS:
            actions = load_flat_list("F5", cid, "actions")
            total += len(actions)
        assert total == 7, f"Expected 7 canonical actions, got {total}"

    def test_total_rejections(self):
        """5 rejections across 5 non-actionable content items."""
        total = 0
        for cid in REJECTED_IDS:
            rejections = load_flat_list("F5", cid, "rejections")
            total += len(rejections)
        assert total == 5, f"Expected 5 rejections, got {total}"

    @pytest.mark.parametrize("content_id", ACTIONABLE_IDS)
    def test_canonical_trace_status(self, content_id):
        actions = load_flat_list("F5", content_id, "actions")
        for action in actions:
            assert action["canonical_trace_status"] == "canonical"
            assert action["intent_id"]
            assert action["policy_id"]
            assert len(action["evidence_span_ids"]) >= 1
            assert action["execution_timing"] is not None

    @pytest.mark.parametrize("content_id", ACTIONABLE_IDS)
    def test_execution_timing_fields(self, content_id):
        actions = load_flat_list("F5", content_id, "actions")
        for action in actions:
            et = action["execution_timing"]
            assert et["intent_published_at"]
            assert et["action_decision_at"]
            assert et["action_executable_at"]
            assert et["market"] == "US"
            assert et["timezone"] == "America/New_York"
            assert et["timing_policy_id"] == "market-calendar-next-open-v1"

    @pytest.mark.parametrize("content_id", ACTIONABLE_IDS)
    def test_target_info(self, content_id):
        actions = load_flat_list("F5", content_id, "actions")
        for action in actions:
            target = action["target"]
            assert target["market"] == "US"
            assert target["ticker_normalized"]
            assert target["ticker"]

    # Specific action type assertions
    def test_c002_action_type(self):
        actions = load_flat_list("F5", "c_002_buy_li", "actions")
        assert len(actions) == 1
        a = actions[0]
        assert a["direction"] == "bearish"
        assert a["action_chain"][0]["action_type"] == "close_long"
        assert a["target"]["ticker_normalized"] == "LI"

    def test_c004_action_type(self):
        actions = load_flat_list("F5", "c_004_hold_tme", "actions")
        assert len(actions) == 1
        a = actions[0]
        assert a["action_chain"][0]["action_type"] == "hold"
        assert a["target"]["ticker_normalized"] == "TME"

    def test_c007_two_actions(self):
        actions = load_flat_list("F5", "c_007_mixed", "actions")
        assert len(actions) == 2
        tickers = {a["target"]["ticker_normalized"] for a in actions}
        assert "LI" in tickers
        assert "CSIQ" in tickers

    def test_c008_close_action(self):
        actions = load_flat_list("F5", "c_008_close_li", "actions")
        assert len(actions) == 1
        a = actions[0]
        assert a["action_chain"][0]["action_type"] == "close_long"
        assert a["target"]["ticker_normalized"] == "LI"

    def test_c010_two_actions(self):
        actions = load_flat_list("F5", "c_010_multi_intent", "actions")
        assert len(actions) == 2
        tickers = {a["target"]["ticker_normalized"] for a in actions}
        assert "CSIQ" in tickers
        assert "TSLA" in tickers

    # Rejection assertions
    def test_c001_rejection(self):
        rejections = load_flat_list("F5", "c_001_bullish_csiq", "rejections")
        assert len(rejections) == 1
        r = rejections[0]
        assert r["rejection_stage"] == "F4"
        assert r["rejection_reason"] == "non_executable_action_hint"

    def test_c005_rejection(self):
        rejections = load_flat_list("F5", "c_005_ambiguous", "rejections")
        assert len(rejections) == 1

    def test_c009_rejection(self):
        rejections = load_flat_list("F5", "c_009_watch_600989", "rejections")
        assert len(rejections) == 1

    # Distinct action types coverage
    def test_distinct_action_types(self):
        """Must cover at least 3 distinct action types: long, close_long, hold."""
        action_types = set()
        for cid in ACTIONABLE_IDS:
            actions = load_flat_list("F5", cid, "actions")
            for a in actions:
                action_types.add(a["action_chain"][0]["action_type"])
        assert "long" in action_types
        assert "close_long" in action_types
        assert "hold" in action_types


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
        assert result["total_trades"] == 2
        assert result["initial_capital"] == 100000
        assert result["commission_pct"] == 0
        assert result["slippage_pct"] == 0
        assert result["max_holding_days"] == 30

    def test_backtest_approximate_fields(self):
        result = load_json(FIXTURE_ROOT / "F8" / "expected_backtest_result.json")
        assert isinstance(result["return_pct"], (int, float))
        assert isinstance(result["win_rate"], (int, float))
        assert 0.0 <= result["win_rate"] <= 1.0

    def test_trade_details_structure(self):
        result = load_json(FIXTURE_ROOT / "F8" / "expected_backtest_result.json")
        assert len(result["trade_details"]) == 2
        for td in result["trade_details"]:
            assert td["trade_action_id"]
            assert td["ticker"] in ("CSIQ", "TSLA")
            assert td["direction"] == "long"
            assert td["entry_date"]
            assert td["entry_price"] > 0
            assert td["exit_date"]
            assert td["exit_price"] > 0
            assert td["exit_reason"] in ("signal_reversal", "max_holding_days", "end_of_period")

    def test_equity_curve_structure(self):
        with open(FIXTURE_ROOT / "F8" / "expected_equity_curve.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 40  # ~49 trading days
        assert float(rows[0]["equity"]) == 100000.0
        assert float(rows[0]["cash"]) == 100000.0
        assert float(rows[0]["positions_value"]) == 0.0

    def test_equity_curve_dates_monotonic(self):
        with open(FIXTURE_ROOT / "F8" / "expected_equity_curve.csv") as f:
            reader = csv.DictReader(f)
            dates = [row["date"] for row in reader]
        assert dates == sorted(dates)

    def test_equity_curve_no_negative(self):
        """Portfolio value must never go negative."""
        with open(FIXTURE_ROOT / "F8" / "expected_equity_curve.csv") as f:
            reader = csv.DictReader(f)
            for row in reader:
                assert float(row["equity"]) >= 0, f"Negative equity on {row['date']}"

    def test_max_drawdown_sane(self):
        """Max drawdown must be <= 100%."""
        result = load_json(FIXTURE_ROOT / "F8" / "expected_backtest_result.json")
        assert result["max_drawdown_pct"] <= 100.0


# =========================================================================
# Market Prices
# =========================================================================

class TestMarketPrices:
    """Market price data assertions."""

    def test_csv_exists(self):
        assert (FIXTURE_ROOT / "market_prices.csv").exists()

    def test_required_tickers(self):
        with open(FIXTURE_ROOT / "market_prices.csv") as f:
            reader = csv.DictReader(f)
            tickers = {row["ticker"] for row in reader}
        assert REQUIRED_TICKERS.issubset(tickers), f"Missing tickers: {REQUIRED_TICKERS - tickers}"

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

    def test_price_data_sane(self):
        """All prices must be positive."""
        with open(FIXTURE_ROOT / "market_prices.csv") as f:
            reader = csv.DictReader(f)
            for row in reader:
                assert float(row["open"]) > 0
                assert float(row["close"]) > 0
                assert float(row["high"]) >= float(row["low"])


# =========================================================================
# Cross-Reference Integrity
# =========================================================================

class TestCrossReference:
    """Cross-stage reference integrity checks."""

    def test_f3_references_f1_envelope(self):
        """Every F3 intent's envelope_id must match a F1 envelope."""
        for cid in CONTENT_IDS:
            env = load_fixture("F1", cid, "envelope")
            intents = load_flat_list("F3", cid, "intents")
            for intent in intents:
                assert intent["envelope_id"] == env["envelope_id"]

    def test_f4_references_f3_intents(self):
        """Every F4 policy's intent_id must resolve to a F3 intent."""
        for cid in CONTENT_IDS:
            f3_intents = load_flat_list("F3", cid, "intents")
            f4_mappings = load_flat_list("F4", cid, "policy")
            f3_ids = {i["intent_id"] for i in f3_intents}
            for m in f4_mappings:
                assert m["intent_id"] in f3_ids

    def test_f5_references_f3_f4(self):
        """Every F5 action's intent_id and policy_id must resolve."""
        for cid in ACTIONABLE_IDS:
            f3_intents = load_flat_list("F3", cid, "intents")
            f4_mappings = load_flat_list("F4", cid, "policy")
            f5_actions = load_flat_list("F5", cid, "actions")
            f3_ids = {i["intent_id"] for i in f3_intents}
            f4_ids = {m["policy_id"] for m in f4_mappings}
            for a in f5_actions:
                assert a["intent_id"] in f3_ids
                assert a["policy_id"] in f4_ids

    def test_f5_evidence_spans_resolve_to_f2(self):
        """Every F5 evidence_span_id must exist in F2 output."""
        for cid in ACTIONABLE_IDS:
            f2 = load_fixture("F2", cid, "anchors")
            f5_actions = load_flat_list("F5", cid, "actions")
            f2_span_ids = {s["evidence_span_id"] for s in f2["evidence_spans"]}
            for a in f5_actions:
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
