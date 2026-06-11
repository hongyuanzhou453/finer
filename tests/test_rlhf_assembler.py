"""Tests for F6 RLHF assembler — corrections → DPO Preference bridge (环 B).

锁住 docs/specs/2026-06-07-f6-rlhf-to-dpo-mapping.md §6 的桥接行为。
"""

import json

import pytest

from finer.services.rlhf_assembler import (
    build_preference,
    extraction_to_dict,
    normalize_action_step,
    apply_corrections,
)


ORIGINAL = {
    "ticker": "AAPL",
    "direction": "neutral",
    "action_chain": [],
    "evidence_text": "AAPL 在 150 附近支撑，回踩 148-152 可建仓",
}


# ---------------------------------------------------------------------------
# build_preference 主行为
# ---------------------------------------------------------------------------
def test_correction_produces_preference_pair():
    """有修正 → is_original_correct=False，chosen=修正、rejected=原始。"""
    pref = build_preference(
        ORIGINAL,
        {"ticker": "AAPL", "direction": "bullish",
         "action_chain": [{"action_type": "long", "target_price_low": 148, "target_price_high": 152}]},
        flagged_as_error=False,
    )
    assert pref["is_original_correct"] is False
    assert "neutral" in pref["rejected"] and "bullish" in pref["chosen"]
    chosen = json.loads(pref["chosen"])
    assert chosen["action_chain"][0]["target_price_low"] == 148.0


def test_no_correction_marks_original_correct():
    """无修正未标记 → is_original_correct=True（DPOExporter 会跳过）。"""
    pref = build_preference(ORIGINAL, None, flagged_as_error=False)
    assert pref["is_original_correct"] is True


def test_all_none_corrections_treated_as_no_correction():
    """前端未改任何字段（全 None）→ 视为原始正确。"""
    pref = build_preference(
        ORIGINAL, {"ticker": None, "direction": None, "action_chain": None}, False
    )
    assert pref["is_original_correct"] is True


def test_flagged_without_correction_is_incorrect():
    """仅标记异常、无修正 → is_original_correct=False。"""
    pref = build_preference(ORIGINAL, None, flagged_as_error=True)
    assert pref["is_original_correct"] is False


def test_partial_correction_direction_only():
    pref = build_preference(ORIGINAL, {"direction": "bearish"}, False)
    assert pref["is_original_correct"] is False
    assert "bearish" in pref["chosen"] and "neutral" in pref["rejected"]


# ---------------------------------------------------------------------------
# camelCase ↔ snake_case 规整
# ---------------------------------------------------------------------------
def test_normalize_action_step_camelcase():
    """前端 camelCase action step → 后端 snake_case。"""
    step = normalize_action_step({
        "actionType": "long", "instrumentType": "stock",
        "triggerCondition": "price < 150", "targetPriceLow": "148", "targetPriceHigh": "152",
    })
    assert step["action_type"] == "long"
    assert step["instrument_type"] == "stock"
    assert step["trigger_condition"] == "price < 150"
    assert step["target_price_low"] == 148.0 and step["target_price_high"] == 152.0


def test_normalize_action_step_drops_empty():
    step = normalize_action_step({"actionType": "watch"})
    assert step == {"action_type": "watch"}


def test_extraction_to_dict_accepts_both_cases():
    d = extraction_to_dict({
        "ticker": "TSLA", "direction": "bullish",
        "actionChain": [{"actionType": "long", "targetPriceLow": 250}],
        "timeHorizon": "weekly",
    })
    assert d["ticker"] == "TSLA"
    assert d["action_chain"][0]["action_type"] == "long"
    assert d["time_horizon"] == "weekly"


def test_apply_corrections_replaces_chain():
    original = extraction_to_dict(ORIGINAL)
    corrected = apply_corrections(original, {"action_chain": [{"action_type": "short"}]})
    assert corrected["action_chain"] == [{"action_type": "short"}]
    # 原 dict 不被就地改坏
    assert original["action_chain"] == []


def test_chosen_rejected_valid_json():
    pref = build_preference(ORIGINAL, {"direction": "bullish"}, False)
    json.loads(pref["chosen"])
    json.loads(pref["rejected"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
