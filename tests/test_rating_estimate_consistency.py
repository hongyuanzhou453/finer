"""M1 评级—预测口径背离检测的判定纪律测试。

本模块的假阳性 = 对券商的不实指控，因此测试的重点是**每一道排除门都真的挡住了**，
而不只是「正例能报出来」。
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from finer.credibility.rating_estimate_consistency import (
    MIN_CHANGE_PCT,
    detect_inconsistencies,
    detect_inconsistency,
)


def make_intent(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "intent_id": "bri_test0001",
        "creator_id": "高盛",
        "direction": "bullish",
        "target_symbol": "0700.HK",
        "rating_action": "maintain",
        "evidence_span_ids": ["span_a", "span_b"],
        "metadata": {
            "report_id": 4242,
            "report_date": "2026-03-01",
            "rating_current": "Buy",
        },
    }
    base.update(over)
    return base


def make_t6(estimates: list, **over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "schema_version": "t6-v0.1",
        "report_id": 4242,
        "date": "2026-03-01",
        "extraction": {
            "estimates": estimates,
            "evidence_quotes": ["我们将 2026E EPS 下调 8%，但维持买入评级"],
        },
        "validation": {"json_ok": True, "evidence_ok": True},
    }
    base.update(over)
    return base


def est(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "metric": "eps",
        "metric_name_raw": "摊薄EPS",
        "period": "2026E",
        "value": 1.8,
        "unit": "元",
        "action": "cut",
        "change_pct": -8.0,
    }
    base.update(over)
    return base


# ── 正例 ──────────────────────────────────────────────────────────────────────


def test_bullish_rating_with_cut_estimate_is_flagged():
    event, reason = detect_inconsistency(make_intent(), make_t6([est()]))
    assert reason is None
    assert event is not None
    assert event.rating_direction == "bullish"
    assert len(event.conflicting_estimates) == 1
    assert event.conflicting_estimates[0].action == "cut"
    assert event.report_id == 4242
    assert event.has_both_sides
    assert event.max_change_pct == pytest.approx(8.0)


def test_bearish_rating_with_raised_estimate_is_flagged():
    event, reason = detect_inconsistency(
        make_intent(direction="bearish"),
        make_t6([est(action="raised", change_pct=12.0)]),
    )
    assert reason is None
    assert event is not None
    assert event.conflicting_estimates[0].action == "raised"


# ── 每一道排除门 ───────────────────────────────────────────────────────────────


def test_neutral_rating_never_flagged():
    """从「中性」推不出任何矛盾。"""
    event, reason = detect_inconsistency(
        make_intent(direction="neutral"), make_t6([est()])
    )
    assert event is None and reason == "intent_direction_not_directed"


def test_agreeing_estimate_not_flagged():
    """看多 + 上调预测 = 自洽，不是背离。"""
    event, reason = detect_inconsistency(
        make_intent(), make_t6([est(action="raised", change_pct=9.0)])
    )
    assert event is None and reason == "no_conflicting_estimate"


def test_non_core_metric_not_flagged():
    """毛利率下调不构成对整体判断的矛盾（营收可能同时放量）。"""
    event, reason = detect_inconsistency(
        make_intent(), make_t6([est(metric="gross_margin")])
    )
    assert event is None and reason == "no_conflicting_estimate"


def test_unchanged_action_not_flagged():
    for action in ("unchanged", "new", "unknown"):
        event, reason = detect_inconsistency(
            make_intent(), make_t6([est(action=action)])
        )
        assert event is None, f"{action} 不应被判为调整"
        assert reason == "no_conflicting_estimate"


def test_small_change_is_noise_not_conflict():
    event, reason = detect_inconsistency(
        make_intent(), make_t6([est(change_pct=-(MIN_CHANGE_PCT - 0.1))])
    )
    assert event is None and reason == "no_conflicting_estimate"


def test_missing_change_pct_is_not_flagged():
    """幅度未知 → 无法证明超出噪声区间 → 宁可漏报。"""
    event, reason = detect_inconsistency(
        make_intent(), make_t6([est(change_pct=None)])
    )
    assert event is None and reason == "no_conflicting_estimate"


def test_ungrounded_evidence_blocks_flag():
    """引文未逐字命中原文 → 不可下钻 → 不报。"""
    t6 = make_t6([est()])
    t6["validation"]["evidence_ok"] = False
    event, reason = detect_inconsistency(make_intent(), t6)
    assert event is None and reason == "t6_evidence_not_grounded"


def test_failed_extraction_blocks_flag():
    t6 = make_t6([est()])
    t6["validation"]["json_ok"] = False
    event, reason = detect_inconsistency(make_intent(), t6)
    assert event is None and reason == "t6_json_failed"


def test_no_quotes_blocks_flag():
    t6 = make_t6([est()])
    t6["extraction"]["evidence_quotes"] = []
    event, reason = detect_inconsistency(make_intent(), t6)
    assert event is None and reason == "no_evidence_quotes"


def test_empty_estimates_skipped():
    event, reason = detect_inconsistency(make_intent(), make_t6([]))
    assert event is None and reason == "no_estimates"


def test_target_price_move_is_irrelevant():
    """估值倍数扩张是正当逻辑：目标价字段根本不参与判定。"""
    t6 = make_t6([est()])
    t6["extraction"]["valuation"] = {"method": "PE", "params_raw": "上调至 30x"}
    event, _ = detect_inconsistency(
        make_intent(metadata={**make_intent()["metadata"], "target_price": 999}), t6
    )
    assert event is not None  # 仍按 estimate 冲突判定，与目标价无关


def test_change_pct_accepts_string_forms():
    event, _ = detect_inconsistency(make_intent(), make_t6([est(change_pct="-8%")]))
    assert event is not None
    assert event.conflicting_estimates[0].change_pct == pytest.approx(-8.0)


def test_malformed_estimate_entries_are_skipped_not_crashed():
    event, reason = detect_inconsistency(make_intent(), make_t6(["not-an-object", 42]))
    assert event is None and reason == "no_conflicting_estimate"


# ── 批量 ──────────────────────────────────────────────────────────────────────


def test_batch_collects_events_and_skip_reasons():
    pairs = [
        (make_intent(), make_t6([est()])),                       # 命中
        (make_intent(direction="neutral"), make_t6([est()])),    # 中性排除
        (make_intent(), make_t6([])),                            # 无 estimate
    ]
    report = detect_inconsistencies(pairs)
    assert len(report.events) == 1
    assert report.skips["intent_direction_not_directed"] == 1
    assert report.skips["no_estimates"] == 1
