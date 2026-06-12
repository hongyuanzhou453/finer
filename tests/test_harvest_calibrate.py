"""calibrate() 契约测试：chosen 顶层恰好 6 键、grounded 条件下的 conviction 阶梯。

守护 HQ v1 流程契约：harvest 产出的 draft chosen 经 accept 透传导出后，
必须能通过 scripts/validate_dpo_hq.py 的 chosen schema 检查（6 键、无额外 key）。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from harvest_rejected import CHOSEN_KEYS, UNRESOLVED_TICKER, calibrate, harvest  # noqa: E402


def _calibrate(raw_obj, evidence: str):
    return calibrate(json.dumps(raw_obj, ensure_ascii=False), evidence)


def test_chosen_keys_exactly_six_on_all_paths():
    evidence = "腾讯控股 0700.HK 目标价 450，逢低布局"
    committal = _calibrate(
        {
            "ticker": "0700.HK",
            "direction": "bullish",
            "action_chain": [{"action_type": "long", "target_price_low": 450}],
            "confidence": 0.9,  # 模型附带的额外顶层 key，必须被删
        },
        evidence,
    )
    unparseable = calibrate("not json at all", evidence)
    neutral = _calibrate(
        {"ticker": "UNSPECIFIED", "direction": "neutral", "action_chain": []},
        "泛泛讨论市场情绪，无标的",
    )
    for chosen in (committal, unparseable, neutral):
        assert set(chosen.keys()) == set(CHOSEN_KEYS)
        assert "evidence_quote" not in chosen
        assert "confidence" not in chosen


def test_ungrounded_ticker_caps_conviction_even_with_grounded_price():
    # 价位 450 在原文可溯，但 AAPL 在原文完全找不到 → 不能给 0.8，压到 0.3
    evidence = "有人说目标价 450，但没提是哪家公司"
    chosen = _calibrate(
        {
            "ticker": "AAPL",
            "direction": "bullish",
            "conviction": 0.9,
            "action_chain": [{"action_type": "long", "target_price_low": 450}],
        },
        evidence,
    )
    assert chosen["conviction"] == 0.3
    assert chosen["direction"] == "bullish"  # 方向保留，不清零
    assert chosen["ticker"] == UNRESOLVED_TICKER  # 不透传幻觉 ticker AAPL，置哨兵待人工锚定


def test_grounded_ticker_and_price_gets_max_conviction():
    evidence = "腾讯控股 0700.HK 看到 450 不是梦"
    chosen = _calibrate(
        {
            "ticker": "0700.HK",
            "direction": "bullish",
            "action_chain": [{"action_type": "long", "target_price_low": 450}],
        },
        evidence,
    )
    assert chosen["conviction"] == 0.8


def test_watchlist_fallback_carries_time_horizon_key():
    chosen = calibrate("garbage output", "任意原文")
    assert chosen["direction"] == "watchlist"
    assert chosen["ticker"] == "NONE"
    assert "time_horizon" in chosen


def test_ungrounded_committal_becomes_unresolved():
    # 标的不可溯的承诺观点：方向保留、conviction 0.3、ticker 置 UNRESOLVED（不透传幻觉值）。
    # 这是根因 1 的核心：基座把"泡泡玛特"幻觉成不相干 A 股代码，不能原样进 chosen。
    chosen = _calibrate(
        {
            "ticker": "002857.SZ",  # 基座幻觉：原文讲泡泡玛特，却填成不相干代码
            "direction": "bullish",
            "action_chain": [],
        },
        "泡泡玛特业绩会说门店升级远超去年，店效接近全国平均一倍",
    )
    assert chosen["ticker"] == UNRESOLVED_TICKER
    assert chosen["direction"] == "bullish"  # 方向保留
    assert chosen["conviction"] == 0.3
    assert set(chosen.keys()) == set(CHOSEN_KEYS)  # 6 键不破


def test_harvest_preserves_base_ticker_guess_in_meta():
    # harvest 层：ungrounded committal 的基座原始猜测留痕到 meta.ticker_guess（不进 chosen）。
    cands = [{"id": "p1", "creator": "x", "source_file": "f",
              "evidence_text": "纯粹讨论宏观情绪和宏观叙事，没有任何标的或股票代码"}]
    out = harvest(cands, model="mock", mock=True, temperature=0.0)
    pairs = out["pairs"]
    assert pairs, "基座过度承诺 vs 克制 chosen 必不相同，应保留该对"
    chosen = json.loads(pairs[0]["chosen"])
    assert chosen["ticker"] == UNRESOLVED_TICKER  # mock 编造的标的在原文不可溯
    assert pairs[0]["meta"].get("ticker_guess")  # 基座原始猜测留痕，不丢
    assert "ticker_guess" not in chosen  # 猜测不进 chosen（不污染训练文本）
