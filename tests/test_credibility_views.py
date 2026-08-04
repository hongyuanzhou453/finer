"""CRD-1 记录卡 + CRD-3 共识。

钉住的不变量：卡必带效力门、共识每源只计最新一篇、目标价单位可疑必排除。
"""

from __future__ import annotations

import pytest

from finer.credibility.consensus import build_ticker_consensus
from finer.credibility.record_card import build_record_cards
from tests.test_scorecard import _action as _make_action


def _intent(creator, ticker, *, direction="bullish", rating="Buy",
            tp=None, cur="USD", date="2026-01-10", iid=None):
    return {
        "intent_id": iid or f"bri_{creator}_{ticker}_{date}",
        "creator_id": creator,
        "target_symbol": ticker,
        "target_name": f"{ticker} Corp",
        "direction": direction,
        "target_price": {"value": tp, "currency": cur} if tp else None,
        "metadata": {"rating_current": rating, "report_date": date},
    }


# ---------------------------------------------------------------------------
# CRD-3 共识
# ---------------------------------------------------------------------------


def test_latest_report_wins_per_source():
    """同券商多篇 = 立场时间序列，只有最新一篇进共识。"""
    view = build_ticker_consensus([
        _intent("高盛", "NVDA", direction="bullish", date="2026-01-05"),
        _intent("高盛", "NVDA", direction="bearish", date="2026-03-01"),
        _intent("瑞银", "NVDA", direction="bullish", date="2026-02-01"),
    ], "NVDA")
    assert view.n_sources == 2
    assert view.direction_counts == {"bearish": 1, "bullish": 1}
    gs = next(r for r in view.latest_by_source if r.creator_id == "高盛")
    assert gs.direction == "bearish" and gs.n_reports == 2


def test_symbol_dialects_merge_to_one_view():
    """AZN.LN 与 AZN.L 是同一标的的两种方言写法。"""
    view = build_ticker_consensus([
        _intent("高盛", "AZN.L", date="2026-01-05"),
        _intent("瑞银", "AZN.LN", date="2026-01-06"),
    ], "AZN.LN")
    assert view is not None and view.n_sources == 2
    assert view.ticker == "AZN.L"


def test_directional_agreement_ignores_neutral():
    view = build_ticker_consensus([
        _intent("a", "NVDA", direction="bullish"),
        _intent("b", "NVDA", direction="bullish"),
        _intent("c", "NVDA", direction="bearish"),
        _intent("d", "NVDA", direction="neutral"),
    ], "NVDA")
    assert view.directional_agreement == pytest.approx(2 / 3)


def test_all_neutral_agreement_is_none_not_zero():
    view = build_ticker_consensus([
        _intent("a", "NVDA", direction="neutral"),
    ], "NVDA")
    assert view.directional_agreement is None


def test_target_price_summary_same_currency_only():
    view = build_ticker_consensus([
        _intent("a", "NVDA", tp=200.0),
        _intent("b", "NVDA", tp=250.0),
        _intent("c", "NVDA", tp=240.0),
        _intent("d", "NVDA", tp=1500.0, cur="HKD"),   # 少数币种 → 排除
    ], "NVDA")
    s = view.target_prices
    assert s.currency == "USD" and s.n == 3
    assert s.median_value == 240.0
    assert s.excluded_currency_mismatch == 1


def test_uk_target_prices_excluded_as_unit_ambiguous():
    """.L 股镑/便士混存（2026-08-03 实测），聚合会 100 倍错——必须排除。"""
    view = build_ticker_consensus([
        _intent("a", "AZN.L", tp=10500.0, cur="GBP"),   # 便士
        _intent("b", "AZN.L", tp=105.0, cur="GBP"),     # 英镑
    ], "AZN.L")
    assert view.target_prices is None
    assert any("单位可疑" in n for n in view.notes)


def test_every_row_carries_drilldown_intent_id():
    view = build_ticker_consensus([_intent("a", "NVDA", iid="bri_x1")], "NVDA")
    assert view.latest_by_source[0].intent_id == "bri_x1"


def test_unknown_ticker_returns_none():
    assert build_ticker_consensus([_intent("a", "NVDA")], "NO.SUCH.ZZZ") is None
    assert build_ticker_consensus([], "NVDA") is None


def test_no_prediction_note_always_present():
    view = build_ticker_consensus([_intent("a", "NVDA")], "NVDA")
    assert any("不构成对未来的预测" in n for n in view.notes)


# ---------------------------------------------------------------------------
# CRD-1 记录卡
# ---------------------------------------------------------------------------


_SEQ = iter(range(10_000))


def _action(creator="高盛", settled=True, win=True):
    """复用 test_scorecard 的构造器；settled=False → 无 backtest_result。"""
    return _make_action(
        f"a{next(_SEQ)}",
        creator=creator,
        return_pct=(0.05 if win else -0.05) if settled else None,
    )


def test_card_embeds_sufficiency_and_orders_by_settled_n():
    actions = [_action("A") for _ in range(35)] + [_action("B") for _ in range(5)]
    cards = build_record_cards(actions)
    assert [c.creator_id for c in cards] == ["A", "B"]
    a, b = cards
    assert a.sufficiency.tier == "sufficient"
    assert b.sufficiency.display_policy == "count_only"
    assert b.sufficiency.point_estimate is not None  # 数据在卡里，呈现由门管


def test_card_counts_unsettled_in_total():
    actions = [_action("A") for _ in range(3)] + [
        _action("A", settled=False) for _ in range(2)
    ]
    card = build_record_cards(actions)[0]
    assert card.n_settled == 3 and card.n_total == 5
    assert card.sufficiency.coverage_ratio == pytest.approx(3 / 5)


def test_card_activity_window_is_populated():
    card = build_record_cards([_action("A") for _ in range(3)])[0]
    assert card.first_action_at is not None
    assert card.last_action_at >= card.first_action_at
