"""CRD-2 统计效力门。

钉住的核心不变量：**样本充分性与预测性主张是两道独立的门**。
一个 n=435、区间很窄的历史超额，仍然不许可被当成对未来的主张——
这正是 2026-08-02 定位转向所纠正的错误，代码必须让它无法被绕过。
"""

from __future__ import annotations

import pytest
import yaml

from typing import get_args

from finer.credibility.significance import (
    SignificanceGate,
    get_significance_gate,
    metric_for_signal_class,
    wilson_interval,
)
from finer.schemas.trade_action import SIGNAL_CLASS_LITERAL


@pytest.fixture
def gate(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "significance.yaml").write_text(
        yaml.safe_dump({
            "version": 1,
            "confidence": 0.95,
            "tiers": {
                "sufficient": {"min_settled": 30, "display_policy": "show"},
                "provisional": {"min_settled": 15,
                                "display_policy": "show_with_warning"},
            },
            "coverage": {"min_ratio": 0.5},
            "predictive_claim": {
                "proven_metric": {
                    "permitted": True, "tested_at": "2026-01-01",
                    "sample_size": 5000, "evidence": "docs/x.md",
                    "summary": "通过", "scope_note": "仅限 A 市场",
                },
                "disproven_metric": {
                    "permitted": False, "tested_at": "2026-08-02",
                    "sample_size": 2889, "evidence": "docs/y.md",
                    "summary": "2 正/4 负，中位 |z|=0.32",
                    "scope_note": "不适用于 KOL",
                },
            },
        }, allow_unicode=True),
        encoding="utf-8",
    )
    return SignificanceGate(root=tmp_path, ttl_seconds=0.0)


# ---------------------------------------------------------------------------
# Wilson 区间
# ---------------------------------------------------------------------------


def test_wilson_zero_n_is_none_not_zero():
    """n=0 必须是 None。填 0 会让「没数据」看起来像「胜率 0%」。"""
    assert wilson_interval(0, 0) is None


def test_wilson_brackets_point_estimate():
    lo, hi = wilson_interval(45, 100)
    assert lo < 0.45 < hi
    assert 0.0 <= lo and hi <= 1.0


def test_wilson_narrows_with_n():
    small = wilson_interval(15, 30)
    large = wilson_interval(500, 1000)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_extreme_proportion_stays_in_range():
    """全胜时正态近似会给出上界 >1；Wilson 不会。"""
    lo, hi = wilson_interval(8, 8)
    assert hi <= 1.0 and lo > 0.5


# ---------------------------------------------------------------------------
# 门 1：样本充分性
# ---------------------------------------------------------------------------


def test_sufficient_sample_shows(gate):
    r = gate.assess(successes=200, settled_n=435)
    assert r.tier == "sufficient" and r.display_policy == "show"
    assert r.point_estimate == pytest.approx(200 / 435)
    assert r.ci_width is not None


def test_provisional_sample_warns(gate):
    r = gate.assess(successes=9, settled_n=20)
    assert r.tier == "provisional" and r.display_policy == "show_with_warning"
    assert any("仅供参考" in n for n in r.notes)


def test_insufficient_sample_is_count_only(gate):
    r = gate.assess(successes=3, settled_n=7)
    assert r.tier == "insufficient" and r.display_policy == "count_only"
    assert any("样本不足" in n for n in r.notes)


def test_zero_settled_leaves_estimate_none(gate):
    r = gate.assess(successes=0, settled_n=0, total_n=40)
    assert r.point_estimate is None and r.wilson_low is None
    assert r.tier == "insufficient"


def test_illegal_counts_rejected(gate):
    with pytest.raises(ValueError):
        gate.assess(successes=10, settled_n=5)


# ---------------------------------------------------------------------------
# 覆盖率（幸存者偏差）
# ---------------------------------------------------------------------------


def test_low_coverage_downgrades_even_when_n_is_large(gate):
    """n 够大但只结算了三成 —— 能结算的那部分可能系统性不同。"""
    r = gate.assess(successes=60, settled_n=100, total_n=400)
    assert r.coverage_penalised is True
    assert r.tier == "provisional"          # 从 sufficient 降一档
    assert any("覆盖率" in n for n in r.notes)


def test_adequate_coverage_does_not_penalise(gate):
    r = gate.assess(successes=60, settled_n=100, total_n=150)
    assert r.coverage_penalised is False and r.tier == "sufficient"


# ---------------------------------------------------------------------------
# 门 2：预测性主张 —— 与门 1 相互独立
# ---------------------------------------------------------------------------


def test_large_sample_does_not_license_prediction(gate):
    """本门存在的全部理由：样本充分 ≠ 可以拿来预测。"""
    r = gate.assess(successes=200, settled_n=435, metric="disproven_metric")
    assert r.tier == "sufficient"                      # 门 1 通过
    assert r.predictive_claim.permitted is False       # 门 2 不通过
    assert any("不构成对未来的预测" in n for n in r.notes)
    assert r.predictive_claim.scope_note == "不适用于 KOL"


def test_unregistered_metric_defaults_to_not_permitted(gate):
    """「没检验过」不等于「可以用」。"""
    v = gate.predictive_claim("never_tested")
    assert v.permitted is False
    assert "未检验" in (v.summary or "")


def test_proven_metric_permits_and_carries_scope(gate):
    v = gate.predictive_claim("proven_metric")
    assert v.permitted is True
    assert v.evidence == "docs/x.md" and v.scope_note == "仅限 A 市场"


def test_permitted_metric_adds_no_disclaimer_note(gate):
    r = gate.assess(successes=200, settled_n=435, metric="proven_metric")
    assert not any("不构成对未来的预测" in n for n in r.notes)


# ---------------------------------------------------------------------------
# 失效模式：读不到配置绝不能变成放行
# ---------------------------------------------------------------------------


def test_missing_config_falls_back_to_most_conservative(tmp_path):
    g = SignificanceGate(root=tmp_path, ttl_seconds=0.0)   # 没有 configs/
    r = g.assess(successes=500, settled_n=1000, metric="anything")
    assert r.tier == "insufficient" and r.display_policy == "count_only"
    assert r.predictive_claim.permitted is False


def test_corrupt_config_falls_back(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "significance.yaml").write_text(
        "just a string, not a mapping", encoding="utf-8"
    )
    g = SignificanceGate(root=tmp_path, ttl_seconds=0.0)
    assert g.assess(successes=500, settled_n=1000).tier == "insufficient"


def test_unknown_display_policy_degrades_to_count_only(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "significance.yaml").write_text(
        yaml.safe_dump({
            "tiers": {"sufficient": {"min_settled": 10,
                                     "display_policy": "shout_it_loudly"}},
        }),
        encoding="utf-8",
    )
    g = SignificanceGate(root=tmp_path, ttl_seconds=0.0)
    assert g.assess(successes=6, settled_n=20).display_policy == "count_only"


# ---------------------------------------------------------------------------
# 仓内真实配置
# ---------------------------------------------------------------------------


def test_repo_config_disallows_broker_prediction():
    """仓内 configs/significance.yaml 必须如实记录 08-02 的否定结论。"""
    v = get_significance_gate().predictive_claim("broker_excess_win_rate")
    assert v.permitted is False
    assert v.sample_size == 2889
    assert v.evidence and "persistence-test" in v.evidence


def test_repo_config_thresholds_are_loadable():
    r = get_significance_gate().assess(successes=200, settled_n=435)
    assert r.tier == "sufficient" and r.confidence == 0.95


# ---------------------------------------------------------------------------
# signal_class → 指标名映射（门 2 的挂载点）
# ---------------------------------------------------------------------------


def test_every_signal_class_maps_to_a_registered_metric():
    """每个 signal_class 都必须映射到一个**已在 yaml 登记**的指标。

    回归：两处调用点曾写成 ``"broker_excess_win_rate" if signal_class ==
    "broker_recommendation" else None``，于是板块口径拿到 metric=None，
    ``assess()`` 返回 ``predictive_claim=None``，而前端的横幅条件是
    ``claim && !claim.permitted`` —— 结果是 24 张板块卡**整块免责声明消失**。
    缺口的表现恰好是声明不见了，是最坏的失效方向。

    这条钉的是内容不是行为：逐个喂契约取值，新增第四个取值时会失败。
    """
    gate = get_significance_gate()
    for signal_class in get_args(SIGNAL_CLASS_LITERAL):
        metric = metric_for_signal_class(signal_class)
        assert metric is not None, f"{signal_class} 未映射指标名"
        verdict = gate.predictive_claim(metric)
        # 已登记的条目一定带 summary；未登记会退到「该指标未在…登记」的兜底文案。
        assert verdict.summary and "未在 configs/significance.yaml 登记" not in verdict.summary, (
            f"{metric} 未在 configs/significance.yaml 的 predictive_claim 段登记"
        )
        assert verdict.permitted is False, (
            f"{metric} 被标为许可——只有通过预声明判据的持续性检验才能翻 true"
        )


def test_assess_attaches_claim_for_every_signal_class():
    """比率离开后端时，三个口径都必须带上 predictive_claim（不得为 None）。"""
    gate = get_significance_gate()
    for signal_class in get_args(SIGNAL_CLASS_LITERAL):
        result = gate.assess(
            successes=2, settled_n=11, total_n=53,
            metric=metric_for_signal_class(signal_class),
        )
        assert result.predictive_claim is not None, f"{signal_class} 的声明缺席"
        assert result.predictive_claim.permitted is False
