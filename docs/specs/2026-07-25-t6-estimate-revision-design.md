# T6 盈利预测整合设计稿（EstimateRevision — 决策记录，本轮不实现）

> 状态：**design-only**（D2，2026-07-25 架构收口轮）。用户已拍板：T9 落地、T6 只出设计。
> 实现窗口：与 CRD-1（credibility/scoring 层）同一轮启动。

## 1. 问题

MiMo 烧录产物 T6（盈利预测深抽，`t6_deep_equity/burn_t6.jsonl` 15.9MB + r2 6.6MB，
约 6,556 份研报）包含券商对个股的**盈利指标序列**：指标 × 期间 × 修订幅度
（EPS/营收/毛利率 等，FY24/FY25/FY26），估值参数（目标 PE/PB/DCF 假设）、
催化剂时间窗、beat/miss 判定。这是「券商预测 vs 实际」可回测信誉资产的原料。

**为什么不能塞 metadata**：`NormalizedInvestmentIntent` 目前唯一的数值槽位是
`target_price`（`IntentTargetPrice{value, currency, prior_value}`）。盈利预测是
「指标序列」不是标量——塞 `intent.metadata` 会重蹈 `key_thesis` 的覆辙
（自由 dict 无 schema 校验、无 contracts.ts 镜像、无 drift 守卫、下游消费各自
解析各自漂移）。A2 的教训：**槽位必须 schema-first**。

**为什么本轮不实现**：真实消费方是 CRD-1（信源可信度打分——预测精度是比
「方向对错」高一个数量级的信誉信号），而 CRD-1 尚未立项。现在落库 = 无消费方
的纯负债（north-star roadmap 红线：不为未来功能囤 schema）。

## 2. Schema 草图（实现轮的起点，非最终契约）

```python
# schemas/investment_intent.py（新增子模型，挂在 NormalizedInvestmentIntent 上）

ESTIMATE_METRIC_LITERAL = Literal[
    "eps", "revenue", "gross_margin", "operating_margin",
    "net_income", "ebitda", "other",
]
ESTIMATE_REVISION_LITERAL = Literal["raise", "cut", "maintain", "initiate", "unknown"]

class EstimateRevision(BaseModel):
    """One metric × period estimate revision, carried verbatim from source."""
    metric: ESTIMATE_METRIC_LITERAL
    metric_raw: Optional[str]          # 原文指标名（other 时必填）
    period: str                        # "FY2026" / "2026E" / "1H26" — 原文口径
    new_value: Optional[float]
    prior_value: Optional[float]
    unit: Optional[str]                # "CNY", "%", "bn USD"…
    revision_action: ESTIMATE_REVISION_LITERAL
    revision_pct: Optional[float]      # (new-prior)/|prior|，可缺
    evidence_quote: Optional[str]      # 原文引句（T6 有 evidence_quotes）

# NormalizedInvestmentIntent 增：
estimate_revisions: List[EstimateRevision] = Field(default_factory=list)
```

同步义务（实现轮 checklist）：
1. `contracts.ts`：`EstimateRevision` 类型 + 两个 Literal 提为 `export type`；
2. `scripts/check_contract_drift.py` REGISTRY 登记 `EstimateMetric` / `EstimateRevisionAction`；
3. 每字段 `Field(description=...)`；
4. 存量 intent 反序列化兼容（default_factory=list，零迁移）。

## 3. 适配器与数据流（实现轮）

- `extraction/estimate_revision_adapter.py`：第三个声明式适配器（A3/T9 同模式）：
  T6 JSONL 行 → 已有 bri intent 的 `estimate_revisions` **就地增补**（T6 与 T3
  同源同 filepath join；不新建 intent，避免重复 action）。适配器纯函数、零 LLM、
  `--execute` 前 dry-run 报告 join 命中率。
- F4/F5 不消费 estimate_revisions（不影响 action 生成）；唯一消费方是 CRD-1：
  `credibility/estimate_accuracy.py` 把 `estimate_revisions × 实际财报值`（需接
  财报数据源，finance-skills 已有部分能力）折算成预测精度分。
- beat/miss 与催化剂时间窗 → F7 timeline 事件原料（次优先级）。

## 4. 依赖与顺序

```
CRD-1 立项（north-star Phase 1）
  └─ EstimateRevision schema（本设计稿 §2）
       └─ estimate_revision_adapter（§3，join bri intent）
            └─ credibility/estimate_accuracy（消费方，CRD-1 内）
```

前置数据核验（实现轮第一步）：T6 行的 `filepath` ↔ bri intent 的
`metadata.source_filepath` join 命中率抽样；T6 字段完备率（new/prior 双值比例
决定 revision_pct 可算比例）。

## 5. 本轮已铺垫的接口

- T9 适配器（D1）已建立「第二声明式适配器」的模式模板与 `t9i_` 命名空间隔离；
  T6 适配器可直接复制该模式（差异：增补已有 intent 而非新建）。
- `broker_runner` 已参数化 `intent_glob`/`output_prefix`——若 T6 实现轮决定
  新建 intent 家族（`t6i_`），执行器零改动可用。
