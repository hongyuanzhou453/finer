"""Tests for the F3 declarative broker recommendation adapter.

Pure-function tests over hand-built T3/F0/F1/F2 dicts — no disk, no LLM.
NormalizedInvestmentIntent is instantiated for real (not mocked).
"""

import json

import pytest

from finer.extraction.broker_recommendation_adapter import (
    CONVICTION_SOURCE,
    CONVICTION_TABLE,
    RATING_DIRECTION_TABLE,
    AdaptResult,
    IntentTargetPrice,
    adapt_t3_line,
    derive_intent_id,
    infer_currency,
    infer_market,
    map_horizon_months,
    map_rating_to_direction,
    normalize_rating_token,
    run,
    select_target_symbol,
    ticker_segments,
)
from finer.schemas.investment_intent import NormalizedInvestmentIntent


# =============================================================================
# Fixtures (hand-built dicts, mirroring real on-disk shapes)
# =============================================================================

def make_t3(**overrides):
    extraction_overrides = overrides.pop("extraction", {})
    t3 = {
        "report_id": "rpt_001",
        "filename": "20250901-MS-微博.pdf",
        "filepath": "/Volumes/NAMEZY/外资研报/2025/20250901-MS-微博.pdf",
        "broker": "摩根士丹利",
        "date": "2025-09-01",
        "stock_code": "WB.US",
        "company_name": "微博",
        "extraction": {
            "ticker": "WB.US",
            "rating_current": "Overweight",
            "rating_prior": "Equal-weight",
            "rating_action": "upgrade",
            "target_price": {"value": 7.5, "currency": "USD", "prior_value": 6.6},
            "bull_target": 11.1,
            "bear_target": 6.1,
            "horizon_months": 12,
            "analysts": ["Gary Yu"],
            "key_thesis": "广告复苏",
            "evidence_quotes": ["Price Target US$7.50"],
        },
        "validation": {"json_ok": True, "evidence_ok": True, "ticker_match": True},
        "schema_version": "t3-v0.2",
    }
    t3["extraction"].update(extraction_overrides)
    t3.update(overrides)
    return t3


def make_f0(**overrides):
    f0 = {
        "content_id": "broker_abc123",
        "source_type": "research_report",
        "source_platform": "broker",
        "creator_id": "摩根士丹利",
        "creator_name": "摩根士丹利",
        "metadata": {
            "source_filepath": "/Volumes/NAMEZY/外资研报/2025/20250901-MS-微博.pdf",
        },
    }
    f0.update(overrides)
    return f0


def make_envelope(**overrides):
    env = {"envelope_id": "env_deadbeef0001", "source_record_id": "broker_abc123"}
    env.update(overrides)
    return env


def make_f2(resolved_symbol="WB.US", **anchor_overrides):
    anchor = {
        "entity_anchor_id": "entity_001",
        "entity_type": "stock",
        "resolved_symbol": resolved_symbol,
        "evidence_span_id": "span_top",
        "metadata": {
            "evidence_span_ids": ["span_a", "span_b"],
            "occurrences": [
                {"block_id": "block_1", "evidence_span_id": "span_a"},
                {"block_id": "block_2", "evidence_span_id": "span_b"},
                {"block_id": "block_1", "evidence_span_id": "span_a"},
            ],
        },
    }
    anchor.update(anchor_overrides)
    return {"envelope_id": "env_deadbeef0001", "entity_anchors": [anchor]}


def adapt(t3=None, f0=None, envelope=None, f2=None) -> AdaptResult:
    return adapt_t3_line(
        t3 or make_t3(), f0 or make_f0(), envelope or make_envelope(), f2
    )


# =============================================================================
# Direction keyword table
# =============================================================================

@pytest.mark.parametrize("rating", [
    "Buy", "BUY", "buy", "Overweight", "OW", "Outperform", "Add",
    "Positive", "Accumulate", "买入", "增持", "Surperformance",
])
def test_bullish_ratings(rating):
    assert map_rating_to_direction(rating) == "bullish"


@pytest.mark.parametrize("rating", [
    "Neutral", "Hold", "HOLD", "Equal-weight", "Equal Weight", "EW",
    "Market-Perform", "Market Perform", "Sector Perform", "In-line",
    "持有", "中性",
])
def test_neutral_ratings(rating):
    assert map_rating_to_direction(rating) == "neutral"


@pytest.mark.parametrize("rating", [
    "Sell", "SELL", "Underweight", "Underperform", "Reduce", "卖出", "减持",
])
def test_bearish_ratings(rating):
    assert map_rating_to_direction(rating) == "bearish"


def test_normalize_handles_hyphen_case_whitespace():
    assert normalize_rating_token("  Equal-Weight ") == "equal weight"
    assert normalize_rating_token("MARKET_PERFORM") == "market perform"
    assert normalize_rating_token(None) is None
    assert normalize_rating_token("   ") is None


def test_direction_table_covers_conviction_table():
    # Every rated token has a conviction entry and vice versa.
    assert set(RATING_DIRECTION_TABLE) == set(CONVICTION_TABLE)


# =============================================================================
# Skips
# =============================================================================

def test_not_rated_skips():
    result = adapt(make_t3(extraction={"rating_current": "Not Rated"}))
    assert result.skipped
    assert result.skip_reason == "not_rated"


def test_missing_rating_skips():
    for empty in (None, "", "   "):
        result = adapt(make_t3(extraction={"rating_current": empty}))
        assert result.skipped
        assert result.skip_reason == "no_rating"


def test_unmapped_rating_skips_and_records_raw_word():
    result = adapt(make_t3(extraction={"rating_current": "Conviction List"}))
    assert result.skipped
    assert result.skip_reason == "unmapped_rating"
    assert result.raw_rating == "Conviction List"


def test_no_ticker_skips():
    result = adapt(make_t3(stock_code="", extraction={"ticker": ""}))
    assert result.skipped
    assert result.skip_reason == "no_ticker"


# =============================================================================
# Target selection / ticker "/" split / market inference
# =============================================================================

def test_stock_code_takes_priority_over_extraction_ticker():
    t3 = make_t3(stock_code="9868.HK", extraction={"ticker": "XPEV"})
    assert select_target_symbol(t3) == "9868.HK"


def test_ticker_slash_split_prefers_suffixed_segment():
    t3 = make_t3(stock_code="", extraction={"ticker": "XPEV/9868.HK"})
    assert select_target_symbol(t3) == "9868.HK"
    assert ticker_segments(t3) == ["XPEV", "9868.HK"]


def test_ticker_slash_split_falls_back_to_first_segment():
    t3 = make_t3(stock_code="", extraction={"ticker": "XPEV/XPEV2"})
    assert select_target_symbol(t3) == "XPEV"


@pytest.mark.parametrize("symbol,market", [
    ("9868.HK", "HK"),
    ("300750.SZ", "CN"),
    ("600519.SS", "CN"),
    ("600519", "CN"),
    ("TSLA", "US"),
])
def test_market_inference(symbol, market):
    assert infer_market(symbol) == market


def test_target_name_falls_back_to_ticker():
    result = adapt(make_t3(company_name=""))
    assert result.intent.target_name == "WB.US"


# =============================================================================
# Target price + currency heuristic
# =============================================================================

def test_target_price_passthrough_when_currency_declared():
    result = adapt()
    tp = result.intent.target_price
    assert tp is not None
    assert tp.value == 7.5
    assert tp.currency == "USD"
    assert tp.prior_value == 6.6
    assert result.intent.metadata["target_price_currency_inferred"] is False


@pytest.mark.parametrize("symbol,currency", [
    ("9868.HK", "HKD"),
    ("300750.SZ", "CNY"),
    ("600519.SS", "CNY"),
    ("600519", "CNY"),
    ("TSLA", "USD"),
    (None, "USD"),
])
def test_currency_inference_from_suffix(symbol, currency):
    assert infer_currency(symbol) == currency


def test_target_price_currency_inferred_when_null():
    t3 = make_t3(
        stock_code="9868.HK",
        extraction={
            "ticker": "9868.HK",
            "target_price": {"value": 88.0, "currency": None, "prior_value": None},
        },
    )
    intent = adapt(t3).intent
    assert intent.target_price.currency == "HKD"
    assert intent.target_price.prior_value is None
    assert intent.metadata["target_price_currency_inferred"] is True


def test_no_target_price_when_value_null():
    t3 = make_t3(extraction={
        "target_price": {"value": None, "currency": None, "prior_value": None},
    })
    intent = adapt(t3).intent
    assert intent.target_price is None
    assert intent.metadata["target_price_currency_inferred"] is False


def test_intent_target_price_model_roundtrip():
    tp = IntentTargetPrice(value=10.0, currency="USD", prior_value=12.5)
    restored = json.loads(tp.model_dump_json())
    assert restored == {"value": 10.0, "currency": "USD", "prior_value": 12.5}


# =============================================================================
# Horizon mapping (four tiers)
# =============================================================================

@pytest.mark.parametrize("months,hint", [
    (None, "long_term"),   # 12M sell-side convention
    (1, "short_term"),
    (2, "short_term"),
    (3, "medium_term"),
    (6, "medium_term"),
    (7, "long_term"),
    (12, "long_term"),
])
def test_horizon_mapping(months, hint):
    assert map_horizon_months(months) == hint


def test_horizon_flows_into_intent():
    result = adapt(make_t3(extraction={"horizon_months": None}))
    assert result.intent.time_horizon_hint == "long_term"


# =============================================================================
# Conviction lookup (R6)
# =============================================================================

@pytest.mark.parametrize("rating,conviction", [
    ("Buy", 0.7),
    ("Sell", 0.7),
    ("Outperform", 0.7),
    ("Underperform", 0.7),
    ("Overweight", 0.6),
    ("Underweight", 0.6),
    ("Neutral", 0.4),
    ("Hold", 0.4),
])
def test_conviction_lookup(rating, conviction):
    result = adapt(make_t3(extraction={"rating_current": rating}))
    assert result.intent.conviction == conviction


def test_conviction_source_is_always_derived_lookup():
    for rating in ("Buy", "Hold", "卖出"):
        result = adapt(make_t3(extraction={"rating_current": rating}))
        assert result.intent.conviction_source == CONVICTION_SOURCE
        assert CONVICTION_SOURCE == "derived_lookup"


# =============================================================================
# rating_action / prior_direction
# =============================================================================

def test_rating_action_passthrough_and_null_to_unknown():
    assert adapt().intent.rating_action == "upgrade"
    t3 = make_t3(extraction={"rating_action": None})
    assert adapt(t3).intent.rating_action == "unknown"


def test_prior_direction_via_same_table():
    assert adapt().intent.prior_direction == "neutral"  # Equal-weight
    t3 = make_t3(extraction={"rating_prior": "Gibberish"})
    assert adapt(t3).intent.prior_direction is None
    t3 = make_t3(extraction={"rating_prior": None})
    assert adapt(t3).intent.prior_direction is None


# =============================================================================
# F2 anchor lineage
# =============================================================================

def test_f2_anchor_match_exact_symbol():
    result = adapt(f2=make_f2(resolved_symbol="WB.US"))
    intent = result.intent
    assert intent.block_ids == ["block_1", "block_2"]
    assert intent.evidence_span_ids == ["span_a", "span_b", "span_top"]


def test_f2_anchor_match_via_segment_set():
    # Anchor resolved to the US line, target selected the HK line —
    # both spellings live in the report's "/"-segment set.
    t3 = make_t3(stock_code="", extraction={"ticker": "XPEV/9868.HK"})
    result = adapt(t3=t3, f2=make_f2(resolved_symbol="XPEV"))
    assert result.intent.target_symbol == "9868.HK"
    assert result.intent.block_ids == ["block_1", "block_2"]


def test_f2_anchor_no_match_yields_empty_lineage():
    result = adapt(f2=make_f2(resolved_symbol="TSLA"))
    assert result.intent.block_ids == []
    assert result.intent.evidence_span_ids == []


def test_no_f2_yields_empty_lineage():
    result = adapt(f2=None)
    assert result.intent.block_ids == []
    assert result.intent.evidence_span_ids == []


# =============================================================================
# Stable intent id (idempotency)
# =============================================================================

def test_intent_id_is_stable_across_reruns():
    a = adapt().intent.intent_id
    b = adapt().intent.intent_id
    assert a == b
    assert a == derive_intent_id("broker_abc123", "WB.US", "Overweight", "2025-09-01")


def test_intent_id_changes_with_rating():
    a = adapt(make_t3(extraction={"rating_current": "Buy"})).intent.intent_id
    b = adapt(make_t3(extraction={"rating_current": "Sell"})).intent.intent_id
    assert a != b


# =============================================================================
# Full canonical intent validation (real schema, no mocks)
# =============================================================================

def test_full_intent_passes_schema_validation():
    result = adapt(f2=make_f2())
    intent = result.intent
    assert isinstance(intent, NormalizedInvestmentIntent)
    assert not result.skipped

    # Lineage
    assert intent.envelope_id == "env_deadbeef0001"
    assert intent.creator_id == "摩根士丹利"

    # Declarative semantics
    assert intent.direction == "bullish"
    assert intent.actionability == "recommendation"  # A2 schema slot (spec R2)
    assert intent.position_delta_hint == "none"  # zero position commitment
    assert intent.ambiguity_flags == []  # recommendation+none is validator-clean

    assert intent.target_type == "stock"
    assert intent.target_symbol == "WB.US"
    assert intent.market == "US"
    assert intent.metadata["key_thesis"] == "广告复苏"

    # Round-trip through dict (strict model)
    restored = NormalizedInvestmentIntent.from_dict(intent.to_dict())
    assert restored.intent_id == intent.intent_id


# =============================================================================
# CLI run() joins (tmp_path fixtures, still hand-built data)
# =============================================================================

def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_run_joins_and_skip_reasons(tmp_path):
    data_root = tmp_path / "data"
    # F0 record joined by metadata.source_filepath
    _write_json(
        data_root / "F0_intake" / "broker" / "broker_abc123.json", make_f0()
    )
    # a receipt that must be ignored by the index
    _write_json(
        data_root / "F0_intake" / "broker" / "broker_abc123.receipt.json",
        {"receipt": True},
    )
    _write_json(
        data_root / "F1_standardized" / "broker_abc123" / "content_envelope.json",
        make_envelope(),
    )
    _write_json(data_root / "F2_anchored" / "broker_abc123.json", make_f2())

    # F0 present but no envelope
    _write_json(
        data_root / "F0_intake" / "broker" / "broker_no_env.json",
        make_f0(
            content_id="broker_no_env",
            metadata={"source_filepath": "/vol/no_env.pdf"},
        ),
    )

    t3_lines = [
        make_t3(),                                          # ok
        make_t3(filepath="/vol/missing.pdf"),               # no_f0
        make_t3(filepath="/vol/no_env.pdf"),                # no_envelope
    ]
    jsonl = tmp_path / "t3.jsonl"
    jsonl.write_text(
        "\n".join(json.dumps(l, ensure_ascii=False) for l in t3_lines),
        encoding="utf-8",
    )

    # dry-run: nothing written
    stats = run(jsonl, data_root, execute=False)
    assert stats.total == 3
    assert stats.adapted == 1
    assert stats.written == 0
    assert stats.skips["no_f0"] == 1
    assert stats.skips["no_envelope"] == 1
    assert not (data_root / "F3_intents").exists()

    # execute: writes one intent, idempotent on re-run
    stats = run(jsonl, data_root, execute=True)
    assert stats.written == 1
    files = list((data_root / "F3_intents").glob("*.json"))
    assert len(files) == 1
    first_write = json.loads(files[0].read_text(encoding="utf-8"))

    stats = run(jsonl, data_root, execute=True)  # re-run does not double
    files = list((data_root / "F3_intents").glob("*.json"))
    assert len(files) == 1

    intent = json.loads(files[0].read_text(encoding="utf-8"))
    assert intent["intent_id"].startswith("bri_")
    assert intent["evidence_span_ids"] == ["span_a", "span_b", "span_top"]
    # Re-runs keep the original created_at -> unchanged intents stay byte-stable.
    assert intent["created_at"] == first_write["created_at"]
    assert intent == first_write


def test_run_counts_unmapped_rating_long_tail(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "F0_intake" / "broker" / "broker_abc123.json", make_f0()
    )
    _write_json(
        data_root / "F1_standardized" / "broker_abc123" / "content_envelope.json",
        make_envelope(),
    )
    jsonl = tmp_path / "t3.jsonl"
    jsonl.write_text(
        json.dumps(
            make_t3(extraction={"rating_current": "Conviction List"}),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    stats = run(jsonl, data_root, execute=False)
    assert stats.skips["unmapped_rating"] == 1
    assert stats.unmapped_ratings["Conviction List"] == 1
