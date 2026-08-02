"""统计效力门的数据契约（CRD-2）。

回答「n 多大才允许把一个分数呈现给用户」，以及一个**独立**的问题：
「这个分数允不允许被当成对未来的主张」。

两者必须分开：瑞银 n=435 的历史超额估得很准（样本充分），但它不能预测
未来超额（无跨期持续性）。把两者混为一谈，正是 2026-08-02 定位转向
所纠正的那个错误。
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

#: 样本充分性分档。模块级常量，供 contracts.ts 镜像与 drift REGISTRY 引用。
SAMPLE_TIER_LITERAL = Literal["sufficient", "provisional", "insufficient"]

#: 前端呈现策略。``count_only`` = 灰态只显条数，不显任何比率。
DISPLAY_POLICY_LITERAL = Literal["show", "show_with_warning", "count_only"]


class PredictiveClaimVerdict(BaseModel):
    """某个指标是否被许可用于关于**未来**的主张。

    未检验一律 ``permitted=False``——「没有证据说它不行」不是「有证据说它行」。
    """

    metric: str = Field(description="指标标识，如 broker_excess_win_rate")
    permitted: bool = Field(
        description="是否许可做预测性主张。只能由一次通过预声明判据的持续性"
                    "检验翻为 True，不得因业务需要手改"
    )
    tested_at: Optional[str] = Field(
        default=None, description="检验日期（ISO date），未检验为 None"
    )
    sample_size: Optional[int] = Field(
        default=None, description="检验时的可用样本数"
    )
    evidence: Optional[str] = Field(
        default=None, description="检验记录的文档路径（可下钻）"
    )
    summary: Optional[str] = Field(
        default=None, description="一句话结论，供 UI 直接展示"
    )
    scope_note: Optional[str] = Field(
        default=None, description="结论的适用边界，防止被越界引用"
    )


class SampleSufficiency(BaseModel):
    """一个比率型指标的样本充分性判定。

    由 ``credibility/significance.py`` 产出；CRD-1 记录卡强制携带，
    前端强制消费——这是硬门，不是可选徽章。
    """

    settled_n: int = Field(description="已结算条数（判定的分母）")
    total_n: int = Field(description="全部条数，含未结算")
    successes: int = Field(description="命中条数（分子）")

    point_estimate: Optional[float] = Field(
        default=None,
        description="点估计（命中率）。settled_n=0 时为 None，绝不填 0",
    )
    wilson_low: Optional[float] = Field(default=None, description="Wilson 区间下界")
    wilson_high: Optional[float] = Field(default=None, description="Wilson 区间上界")
    ci_width: Optional[float] = Field(
        default=None, description="区间宽度，UI 用它决定是否值得画误差条"
    )
    confidence: float = Field(description="区间置信水平，如 0.95")

    coverage_ratio: Optional[float] = Field(
        default=None,
        description="settled/total。过低说明「能结算的那部分」可能系统性"
                    "不同于全体（幸存者偏差）",
    )
    coverage_penalised: bool = Field(
        default=False, description="是否因覆盖率不足被强制降档"
    )

    tier: SAMPLE_TIER_LITERAL = Field(description="样本充分性分档")
    display_policy: DISPLAY_POLICY_LITERAL = Field(
        description="前端呈现策略；count_only 时不得显示任何比率"
    )

    predictive_claim: Optional[PredictiveClaimVerdict] = Field(
        default=None,
        description="该指标能否用于对未来的主张。与 tier **相互独立**："
                    "样本充分不蕴含可预测",
    )

    notes: List[str] = Field(
        default_factory=list,
        description="面向用户的声明（覆盖率不足、样本不足、无持续性证据等），"
                    "UI 应逐条展示而非折叠",
    )
