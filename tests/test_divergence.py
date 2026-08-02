"""CRD-4 言行不一检测。

本模块的假阳性等于对信源的不实指控，所以这里的**反例比正例重要**：
每一条 assert-not 都对应一种会造出不实指控的失败模式，其中两条是
2026-08-02 在真实数据上实际发生过的。
"""

from __future__ import annotations

import pytest

from finer.credibility.divergence import (
    detect_divergences,
    publication_clock_from_actions,
)

CLOCK = {}


def _intent(iid, *, creator="ji", ticker="AAPL", direction="bullish",
            actionability="opinion", horizon=None, at="2026-03-01T09:00:00+08:00",
            spans=("sp-1",)):
    CLOCK[iid] = at
    return {
        "intent_id": iid, "creator_id": creator, "target_symbol": ticker,
        "target_type": "stock", "direction": direction,
        "actionability": actionability, "time_horizon_hint": horizon,
        "evidence_span_ids": list(spans),
        "created_at": "2026-07-14T00:00:00",     # 批处理戳，永远不该被采信
    }


def _run(intents):
    return detect_divergences(intents, published_at_of=lambda i: CLOCK.get(i["intent_id"]))


# ---------------------------------------------------------------------------
# 真冲突
# ---------------------------------------------------------------------------


def test_concurrent_say_vs_do_is_detected():
    r = _run([
        _intent("s1", direction="bearish", actionability="opinion",
                at="2026-03-01T09:00:00+08:00"),
        _intent("d1", direction="bullish", actionability="explicit_action",
                at="2026-03-05T09:00:00+08:00"),
    ])
    assert len(r.events) == 1
    e = r.events[0]
    assert e.said_direction == "bearish" and e.did_direction == "bullish"
    assert e.gap_days == 4 and e.window_days == 14
    assert e.both_sides_have_evidence


def test_horizon_widens_the_window():
    """声明自称长期，窗口就该长——但窗口来自声明本身，不是我们猜的。"""
    r = _run([
        _intent("s2", direction="bullish", actionability="opinion",
                horizon="long_term", at="2026-03-01T09:00:00+08:00"),
        _intent("d2", direction="bearish", actionability="explicit_action",
                at="2026-05-01T09:00:00+08:00"),          # 61 天后
    ])
    assert len(r.events) == 1 and r.events[0].window_days == 90


# ---------------------------------------------------------------------------
# 会造出不实指控的失败模式 —— 必须不报
# ---------------------------------------------------------------------------


def test_changing_your_mind_later_is_not_divergence():
    """先看空、三个月后做多，是改变主意，不是言行不一。"""
    r = _run([
        _intent("s3", direction="bearish", actionability="opinion",
                at="2026-01-01T09:00:00+08:00"),
        _intent("d3", direction="bullish", actionability="explicit_action",
                at="2026-04-01T09:00:00+08:00"),
    ])
    assert r.events == []
    assert r.skips.get("no_concurrent_conflict", 0) >= 1


def test_broker_recommendation_can_never_trigger():
    """券商给买入评级却没买入，不是言行不一 —— 它本来就不交易。

    误把 recommendation 当「做」会把每一家券商都误告一遍。
    """
    r = _run([
        _intent("s4", creator="高盛", direction="bullish",
                actionability="recommendation", at="2026-03-01T09:00:00+08:00"),
        _intent("s5", creator="高盛", direction="bearish",
                actionability="recommendation", at="2026-03-02T09:00:00+08:00"),
    ])
    assert r.events == []
    assert r.creators_with_both_tiers == []
    assert r.skips.get("not_say_or_do") == 2


def test_neutral_and_mixed_never_conflict():
    """从「中性」推不出任何矛盾。"""
    for d in ("neutral", "mixed"):
        r = _run([
            _intent(f"s6{d}", direction=d, actionability="opinion"),
            _intent(f"d6{d}", direction="bullish", actionability="explicit_action",
                    at="2026-03-02T09:00:00+08:00"),
        ])
        assert r.events == []


def test_unknown_ticker_excluded():
    """``unknown`` 是数据缺口不是标的，不能拿它聚合出冲突。"""
    r = _run([
        _intent("s7", ticker="unknown", direction="bearish", actionability="opinion"),
        _intent("d7", ticker="unknown", direction="bullish",
                actionability="explicit_action", at="2026-03-02T09:00:00+08:00"),
    ])
    assert r.events == []
    assert r.skips.get("unusable_ticker") == 2


def test_same_direction_is_not_conflict():
    r = _run([
        _intent("s8", direction="bullish", actionability="opinion"),
        _intent("d8", direction="bullish", actionability="explicit_action",
                at="2026-03-02T09:00:00+08:00"),
    ])
    assert r.events == []


def test_different_tickers_do_not_cross_contaminate():
    r = _run([
        _intent("s9", ticker="AAPL", direction="bearish", actionability="opinion"),
        _intent("d9", ticker="MSFT", direction="bullish",
                actionability="explicit_action", at="2026-03-02T09:00:00+08:00"),
    ])
    assert r.events == []


def test_restatements_collapse_to_one_event():
    """同一件事的重述不是 M×N 次言行不一。

    2026-08-02 实测：不去重时 1 次冲突被笛卡尔积放大成 37 条。
    """
    intents = [
        _intent(f"s10-{i}", direction="bearish", actionability="opinion",
                at=f"2026-03-0{i+1}T09:00:00+08:00")
        for i in range(4)
    ] + [
        _intent(f"d10-{i}", direction="bullish", actionability="explicit_action",
                at=f"2026-03-0{i+1}T15:00:00+08:00")
        for i in range(4)
    ]
    r = _run(intents)
    assert len(r.events) == 1
    assert r.skips.get("same_episode", 0) >= 1


# ---------------------------------------------------------------------------
# 时钟 —— 2026-08-02 真实踩过的坑
# ---------------------------------------------------------------------------


def test_missing_clock_is_a_hard_error_not_a_silent_fallback():
    """F3 的 created_at 是批处理戳（实测全语料只有 3 个日期）。

    拿它判「同期」会把一整批处理过的声明判成并发 —— 实测造出 37 条
    针对真人的假冲突。因此不给时钟必须直接报错，不能静默兜底。
    """
    with pytest.raises(ValueError, match="published_at_of"):
        detect_divergences([_intent("s11")])


def test_clock_is_built_from_f5_execution_timing():
    clock = publication_clock_from_actions([
        {"intent_id": "i1", "execution_timing": {
            "intent_published_at": "2026-03-01T09:00:00+08:00"}},
        {"intent_id": "i2", "execution_timing": {
            "action_decision_at": "2026-03-02T09:00:00+08:00"}},   # 回退次选
        {"intent_id": "i3"},                                        # 无时钟
        {"execution_timing": {"intent_published_at": "x"}},         # 无 intent_id
    ])
    assert clock == {
        "i1": "2026-03-01T09:00:00+08:00",
        "i2": "2026-03-02T09:00:00+08:00",
    }


def test_intent_without_clock_is_skipped_not_guessed():
    r = _run([
        _intent("s12", direction="bearish", actionability="opinion"),
        {"intent_id": "no-clock", "creator_id": "ji", "target_symbol": "AAPL",
         "target_type": "stock", "direction": "bullish",
         "actionability": "explicit_action", "evidence_span_ids": []},
    ])
    assert r.events == []
    assert r.skips.get("no_timestamp") == 1


# ---------------------------------------------------------------------------
# 可下钻
# ---------------------------------------------------------------------------


def test_event_without_both_sides_evidence_is_flagged():
    r = _run([
        _intent("s13", direction="bearish", actionability="opinion", spans=()),
        _intent("d13", direction="bullish", actionability="explicit_action",
                at="2026-03-02T09:00:00+08:00"),
    ])
    assert len(r.events) == 1
    assert r.events[0].both_sides_have_evidence is False
