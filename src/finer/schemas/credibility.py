"""CRD-1 记录卡与 CRD-3 个股共识的数据契约。

定位前提（2026-08-02 转向）：两者的产出都是**历史记录**，不是预测。

- 记录卡**强制**内嵌 ``SampleSufficiency``（CRD-2 硬门）——没有效力判定的
  比率不允许离开后端；前端按 ``display_policy`` 呈现，不得绕过。
- 共识是「谁说了什么」的聚合（等权、仅方向），**不是**「谁说得对」：
  conviction 是编造值，敏感度未评估前不用它加权（红线 §8-8）。
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from finer.schemas.significance import SampleSufficiency

#: 共识方向档。模块级常量，供 contracts.ts 镜像与 drift REGISTRY 引用。
CONSENSUS_DIRECTION_LITERAL = Literal["bullish", "bearish", "neutral", "mixed"]

#: 记录陈旧度。阈值取自研报的实际节奏：券商对同一标的通常按季度更新，
#: 所以 90 天内算「近期」，一年以上算「档案」。
STALENESS_LITERAL = Literal["current", "aging", "stale", "archival"]


class CreatorRecordCard(BaseModel):
    """一个信源的历史记录卡（CRD-1）。

    如实呈现已发生的事实；**不含任何排名即推荐的语义**。是否可展示、
    以什么姿态展示，由内嵌的 ``sufficiency`` 决定，前端强制消费。
    """

    creator_id: str
    signal_class: Optional[str] = Field(
        default=None, description="记录口径（broker_recommendation / kol_statement）"
    )

    n_total: int = Field(description="全部 action 数（含未结算）")
    n_settled: int = Field(description="已结算数")
    wins: int = Field(description="命中数")

    mean_return: Optional[float] = Field(default=None, description="均值收益（已结算）")
    median_return: Optional[float] = Field(default=None)
    expected_win_rate: Optional[float] = Field(
        default=None, description="按市场构成推出的纯暴露预期胜率"
    )
    market_mix: Dict[str, int] = Field(
        default_factory=dict, description="市场构成，审计「分数里有多少是市场暴露」"
    )

    first_action_at: Optional[str] = Field(
        default=None, description="最早一条 action 的信号时刻（诚实暴露窗口起点）"
    )
    last_action_at: Optional[str] = Field(default=None)

    sufficiency: SampleSufficiency = Field(
        description="CRD-2 效力门判定（含预测性主张裁决）。必填——"
                    "没有它的比率不允许离开后端"
    )


class ConsensusSourceRow(BaseModel):
    """个股共识里一个信源的**最新**立场（重述已去重，最新一篇为准）。"""

    creator_id: str
    direction: CONSENSUS_DIRECTION_LITERAL
    rating: Optional[str] = Field(default=None, description="原文评级标签，如 Overweight")
    target_price_value: Optional[float] = None
    target_price_currency: Optional[str] = None
    report_date: Optional[str] = None
    intent_id: str = Field(description="下钻入口：由此可达 F3→F2 证据原文")
    n_reports: int = Field(default=1, description="该信源对此标的的报告总数（含历史）")


class TargetPriceSummary(BaseModel):
    """目标价分布。只聚合同币种；单位可疑的显式排除并计数。"""

    currency: str
    n: int
    min_value: float
    median_value: float
    max_value: float
    excluded_unit_ambiguous: int = Field(
        default=0,
        description="因单位可疑被排除的条数（如 .L 股镑/便士混存，"
                    "见 2026-08-03 数据质量审计）",
    )
    excluded_currency_mismatch: int = Field(default=0)


class TickerConsensusView(BaseModel):
    """一只标的的共识记录（CRD-3）：谁说了什么，不判断谁说得对。"""

    ticker: str = Field(description="canonical 符号")
    #: 语料是静态档案而非活水（2026-08-05 实测：中位标的最新报告为 2025-12，
    #: 70% 的标的三个月以上无更新）。不标注截止日期，用户会把陈旧记录读成
    #: 「当前共识」——那是本页最容易产生的误导。
    latest_report_date: Optional[str] = Field(
        default=None, description="本页所有立场里最新的一篇报告日期（YYYY-MM-DD）"
    )
    as_of_days: Optional[int] = Field(
        default=None, description="最新一篇距今天数；None 表示无日期可判"
    )
    staleness: Optional[STALENESS_LITERAL] = Field(
        default=None,
        description="陈旧度分档，前端据此决定提示强度；None 表示无日期可判",
    )
    target_names: List[str] = Field(default_factory=list, description="出现过的公司名写法")

    n_sources: int = Field(description="有立场的信源数（每源只计最新一篇）")
    direction_counts: Dict[str, int] = Field(
        default_factory=dict, description="最新立场的方向分布（等权）"
    )
    directional_agreement: Optional[float] = Field(
        default=None,
        description="有明确方向的最新立场中多数方向的占比；无方向立场时为 None",
    )

    latest_by_source: List[ConsensusSourceRow] = Field(default_factory=list)
    target_prices: Optional[TargetPriceSummary] = None

    notes: List[str] = Field(
        default_factory=list,
        description="口径声明（等权、单位排除、无预测性等），UI 逐条展示",
    )
