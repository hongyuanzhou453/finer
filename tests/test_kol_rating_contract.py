"""/api/kol/rating 契约根治测试。

钉住三条：
  1. rating 是强类型 KOLRatingSummary（camelCase 与前端镜像一致），
     必带 sufficiency——Dict[str, Any] 时代前后端互相看不见的漂移不再可能；
  2. 效力门：count_only 时 successRate / avgReturn / overallRating 全为
     None（不是 0——0 会被当真）；样本充分时正常放行；
  3. 无数据路径（_empty_rating）不再返回五个 0 分维度与假时间线。
"""

from __future__ import annotations

from finer.api.routes.kol import (
    KOLRatingSummary,
    _empty_rating,
    _gated_summary,
    _rating_from_backtest,
)


def test_gated_summary_count_only_blanks_ratios() -> None:
    s = _gated_summary(
        "k1", "名字", "平台",
        successes=2, settled_n=3, total_n=10,
        avg_return=1.5, overall_rating=3.2,
    )
    assert isinstance(s, KOLRatingSummary)
    assert s.sufficiency.display_policy == "count_only"
    assert s.successRate is None
    assert s.avgReturn is None
    assert s.overallRating is None
    # 计数永远在场
    assert s.totalOpinions == 10
    assert s.settledOpinions == 3


def test_gated_summary_sufficient_passes_ratios() -> None:
    s = _gated_summary(
        "k1", "名字", "平台",
        successes=20, settled_n=40, total_n=40,
        avg_return=1.5, overall_rating=3.2,
    )
    assert s.sufficiency.display_policy in ("show", "show_with_warning")
    assert s.successRate == 0.5
    assert s.avgReturn == 1.5
    assert s.overallRating == 3.2


def test_empty_rating_has_no_fabricated_scores() -> None:
    resp = _empty_rating("nobody")
    assert resp.rating.totalOpinions == 0
    assert resp.rating.successRate is None
    assert resp.rating.overallRating is None
    assert resp.dimensions == []   # 不再有五个 0 分维度
    assert resp.timeline == []     # 不再有合成时间线
    assert resp.rating.sufficiency.display_policy == "count_only"


def test_backtest_path_small_sample_is_gated() -> None:
    backtest = {
        "win_rate": 0.6,
        "total_trades": 5,
        "sharpe_ratio": 0.4,
        "trades": [
            {"ticker": "AAPL", "return_pct": 0.1, "trade_id": "t1",
             "side": "long", "entry_date": "2026-01-05", "exit_date": "2026-02-01"},
        ],
        "portfolio_snapshots": [
            {"date": "2026-01-05", "cumulative_return": 0.0},
            {"date": "2026-02-01", "cumulative_return": 0.1},
        ],
    }
    resp = _rating_from_backtest("k2", backtest)
    assert resp.rating.settledOpinions == 5
    assert resp.rating.successRate is None          # n=5 → count_only
    assert resp.dimensions == []                    # 维度随门撤下
    # 真实净值曲线保留（曲线是记录不是承诺），但评分随门置空
    assert len(resp.timeline) == 2
    assert all(p.rating is None for p in resp.timeline)
    assert resp.timeline[-1].return_pct == 10.0


def test_backtest_path_sufficient_sample_shows() -> None:
    backtest = {
        "win_rate": 0.5,
        "total_trades": 40,
        "sharpe_ratio": 0.0,
        "trades": [{"ticker": "AAPL", "return_pct": 0.05, "trade_id": "t1",
                    "side": "long", "entry_date": "2026-01-05",
                    "exit_date": "2026-02-01"}],
        "portfolio_snapshots": [],
    }
    resp = _rating_from_backtest("k3", backtest)
    assert resp.rating.successRate == 0.5
    assert resp.rating.overallRating is not None
    # 维度只剩有数据依据的两轴，没有 timeliness/depth/clarity 常量
    dims = {d.dimension for d in resp.dimensions}
    assert dims == {"accuracy", "consistency"}
