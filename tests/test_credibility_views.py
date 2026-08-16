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


# ---------------------------------------------------------------------------
# 陈旧度标注（语料是静态档案，不标注就会被读成「当前共识」）
# ---------------------------------------------------------------------------


def _view(latest_date):
    from finer.credibility.consensus import build_ticker_consensus
    return build_ticker_consensus(
        [_intent("高盛", "NVDA", date=latest_date)], "NVDA"
    )


def test_latest_report_date_is_the_max_across_sources():
    view = build_ticker_consensus([
        _intent("高盛", "NVDA", date="2025-11-01"),
        _intent("瑞银", "NVDA", date="2026-03-15"),
    ], "NVDA")
    assert view.latest_report_date == "2026-03-15"


@pytest.mark.parametrize(
    "days,band",
    [(10, "current"), (120, "aging"), (300, "stale"), (500, "archival")],
)
def test_staleness_bands(days, band):
    from datetime import date, timedelta
    from finer.credibility.consensus import with_staleness

    today = date(2026, 8, 5)
    v = with_staleness(_view((today - timedelta(days=days)).isoformat()), today=today)
    assert v.staleness == band and v.as_of_days == days
    assert any("本页记录截至" in n for n in v.notes)


def test_staleness_is_not_materialized_into_the_view():
    """未经 with_staleness 的视图不带天数——物化固化第二天就是错的。"""
    v = _view("2026-01-01")
    assert v.latest_report_date == "2026-01-01"
    assert v.as_of_days is None and v.staleness is None


def test_view_without_any_report_date_is_left_alone():
    from finer.credibility.consensus import with_staleness

    view = build_ticker_consensus(
        [{"intent_id": "x", "creator_id": "a", "target_symbol": "NVDA",
          "direction": "bullish", "metadata": {}}], "NVDA"
    )
    out = with_staleness(view)
    assert out.staleness is None and not any("截至" in n for n in out.notes)


# ---------------------------------------------------------------------------
# 币种归一（CRD-3）：别名合桶、子单位分桶、平局确定性
# ---------------------------------------------------------------------------


def test_currency_aliases_are_one_bucket_not_a_mismatch():
    """同一币种的不同写法不得被算成「币种不符」。

    回归：分桶键曾是 `(currency or "?").upper()`，于是 KRW / W / Won 成了三个桶，
    多数派之外的被计入 `excluded_currency_mismatch`——页面对**同币种**的报价
    宣称「币种不一致已排除」，既少算样本又给出错误的诚实声明。
    实测全语料 104 条 excluded 里 52 条（41 只票）是这么来的。
    """
    view = build_ticker_consensus([
        _intent("a", "005930.KS", tp=400000.0, cur="KRW"),
        _intent("b", "005930.KS", tp=440000.0, cur="W"),
        _intent("c", "005930.KS", tp=480000.0, cur="Won"),
    ], "005930.KS")
    s = view.target_prices
    assert s.currency == "KRW"
    assert s.n == 3, "三种写法是同一个币种，必须都进聚合"
    assert s.excluded_currency_mismatch == 0
    assert s.median_value == 440000.0


def test_pence_is_not_merged_into_pounds():
    """便士与镑差 100 倍，**只差大小写**的 GBp / GBP 绝不能合桶。

    回归：`.upper()` 把 GBp 抹成 GBP。现役数据有 43 只非 .L 英股带这类标签，
    不受 .L 后缀门保护；目前每只只有一家信源覆盖才没炸。
    """
    from finer.credibility.consensus import normalize_currency
    assert normalize_currency("GBp") != normalize_currency("GBP")
    assert normalize_currency("p") == normalize_currency("pence") == "GBX"


def test_major_and_subunit_together_is_unit_ambiguous():
    """镑与便士同时出现 = 这只票单位不明，整只不聚合（不看后缀）。"""
    view = build_ticker_consensus([
        _intent("a", "BATS", tp=3400.0, cur="GBp"),   # 便士
        _intent("b", "BATS", tp=34.0, cur="GBP"),     # 镑
    ], "BATS")
    assert view.target_prices is None, "单位不明却给出了中位数"
    assert any("单位可疑" in n for n in view.notes)


def test_unknown_currency_label_is_not_guessed():
    """表里没有的写法自成一桶被排除，不猜。

    `KWF` 是现役数据里的 1 条，疑似 KWD 笔误——映射笔误等于编造。
    """
    from finer.credibility.consensus import normalize_currency
    assert normalize_currency("KWF") == "KWF"


def test_no_majority_currency_means_no_aggregate():
    """币种无多数派时不选胜者——取决于读取顺序（或字母序）的「共识」不是共识。

    原实现用 `max()`，取的是 dict 插入序：同样的数据换个读取顺序就换一个中位数。
    实测 19 只票是这种情形，多为双重上市（A/H、ADR/本地）。
    逐源报价行照常展示，信息不丢。
    """
    both = [
        _intent("a", "X", tp=100.0, cur="TWD"), _intent("b", "X", tp=110.0, cur="TWD"),
        _intent("c", "X", tp=3.0, cur="USD"), _intent("d", "X", tp=3.5, cur="USD"),
    ]
    a = build_ticker_consensus(both, "X")
    b = build_ticker_consensus(list(reversed(both)), "X")
    assert a.target_prices is None and b.target_prices is None
    assert any("无多数派" in n for n in a.notes)
    assert len(a.latest_by_source) == 4, "逐源行必须还在"
