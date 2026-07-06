"""Tests for finer.ml.rewards — DPO/RLVR 单一确定性奖励源.

覆盖 M2 第一步：registry-aware grounding（含后缀容忍 + 跨市场防碰撞）、
RewardBreakdown 结构硬门与维度归一、pair_preference 决策。
"""

from __future__ import annotations

from finer.ml.rewards import (
    RewardBreakdown,
    ScoredCandidate,
    pair_preference,
    score_extraction,
    tickers_match,
    ticker_base,
    ticker_grounded,
)

# 确定性测试用的小 registry（不依赖真实 ENTITY_REGISTRY 内容，避免随其变更而脆）
REG = {
    "紫金矿业": ("601899.SH", "CN", "ticker"),
    "上证": ("000001.SH", "CN", "ticker"),
    "平安银行": ("000001.SZ", "CN", "ticker"),
    "长和": ("00001.HK", "HK", "ticker"),
}


# --------------------------------------------------------------------------- ticker 归一
def test_ticker_base_strips_suffix_and_zeros():
    assert ticker_base("601899") == "601899"
    assert ticker_base("601899.SH") == "601899"
    assert ticker_base("00352.HK") == "352"
    assert ticker_base("$AAPL") == "AAPL"


def test_tickers_match_bare_vs_suffixed():
    assert tickers_match("601899", "601899.SH")
    assert tickers_match("601899.SH", "601899")


def test_tickers_match_rejects_cross_market_collision():
    # 去零后基码都是 "1"，但市场不同 → 不应判为同一标的
    assert not tickers_match("000001.SH", "000001.SZ")
    assert not tickers_match("00001.HK", "000001.SH")
    # 同市场同码 → 匹配
    assert tickers_match("000001.SZ", "1.SZ")


# --------------------------------------------------------------------------- grounding
def test_grounding_resolves_code_via_company_name():
    # 旧 loose_ticker bug：601899(裸) vs 601899.SH(registry) 后缀对不上而漏判
    assert ticker_grounded("601899", "今天紫金矿业大涨，看好", registry=REG)
    assert ticker_grounded("601899.SH", "紫金矿业基本面好", registry=REG)


def test_grounding_bare_code_in_evidence():
    assert ticker_grounded("601899", "601899 涨停", registry=REG)


def test_grounding_none_is_exempt():
    assert ticker_grounded("NONE", "无任何标的", registry=REG)
    assert ticker_grounded("", "无任何标的", registry=REG)


def test_grounding_rejects_sentinel_junk():
    # committal 却给哨兵/占位，证据无对应 → 不应 grounded
    assert not ticker_grounded("UNSPECIFIED", "标的未明确，仅泛泛而谈", registry=REG)
    assert not ticker_grounded("XAU", "黄金继续看涨", registry=REG)


def test_grounding_cross_market_not_false_positive():
    # 平安银行=000001.SZ，证据只提"上证"(=000001.SH)，不应把平安判 grounded
    assert not ticker_grounded("000001.SZ", "今天上证指数大涨", registry=REG)
    # 证据提平安银行本身 → grounded
    assert ticker_grounded("000001.SZ", "平安银行业绩超预期", registry=REG)


def test_grounding_registry_gap_returns_false():
    # 公司不在 registry 且证据无裸码 → 无从查 → 未 grounded（registry 覆盖缺口）
    assert not ticker_grounded("002889.SZ", "这家公司很有前景", registry=REG)


# --------------------------------------------------------------------------- score_extraction
def _committal(ticker="601899", conviction=0.6, rationale="基本面向好"):
    return {
        "ticker": ticker,
        "direction": "bullish",
        "conviction": conviction,
        "action_chain": [],
        "time_horizon": "中期",
        "rationale": rationale,
    }


def test_score_structure_gate_zeroes_total():
    rb = score_extraction("not a json", "证据")
    assert isinstance(rb, RewardBreakdown)
    assert rb.structure == 0.0
    assert rb.total == 0.0


def test_score_committal_grounded_is_high():
    rb = score_extraction(_committal(), "紫金矿业大涨")  # 默认真实 registry 含紫金矿业
    assert rb.committal is True
    assert rb.flags.get("ticker_grounded") is True
    assert rb.total > 0.8


def test_score_sentinel_committal_is_penalized():
    rb = score_extraction(_committal(ticker="UNSPECIFIED", conviction=0.7), "泛泛而谈")
    assert rb.flags.get("ticker_grounded") is False
    assert "sentinel_ticker_committal" in rb.penalties
    assert rb.total < 0.3


def test_score_overconfidence_lowers_calibration():
    grounded = score_extraction(_committal(conviction=0.6), "紫金矿业大涨")
    overconf = score_extraction(_committal(conviction=0.99), "紫金矿业大涨")
    assert overconf.calibration < grounded.calibration


def test_score_abstention_form_scores_well():
    abstain = {
        "ticker": "NONE",
        "direction": "watchlist",
        "conviction": 0.3,
        "action_chain": [],
        "time_horizon": "观望",
        "rationale": "证据不足，暂观望",
    }
    rb = score_extraction(abstain, "市场情绪不明")
    assert rb.committal is False
    assert rb.abstention == 1.0
    assert rb.total > 0.8


# --------------------------------------------------------------------------- pair_preference
def _cand(cid, total):
    rb = RewardBreakdown(
        total=total, structure=1.0, grounding=total, calibration=total,
        abstention=0.0, committal=True,
    )
    return ScoredCandidate(candidate_id=cid, output_raw="{}", reward=rb)


def test_pair_preference_picks_chosen_and_rejected():
    d = pair_preference([_cand("a", 0.9), _cand("b", 0.3)], min_chosen_score=0.5, min_margin=0.1)
    assert d.status == "pair"
    assert d.chosen.candidate_id == "a"
    assert d.rejected.candidate_id == "b"
    assert d.margin > 0.1


def test_pair_preference_near_tie():
    d = pair_preference([_cand("a", 0.85), _cand("b", 0.82)], min_chosen_score=0.5, min_margin=0.1)
    assert d.status == "near_tie"
    assert d.chosen is None


def test_pair_preference_all_failed():
    d = pair_preference([_cand("a", 0.3), _cand("b", 0.2)], min_chosen_score=0.5, min_margin=0.1)
    assert d.status == "all_failed"
