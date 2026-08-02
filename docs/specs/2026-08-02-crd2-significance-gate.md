# CRD-2 统计效力门（实施记录，2026-08-02）

> 依据：`2026-08-02-positioning-pivot-proposal.md` §3.3——定位转向后
> CRD-2 从「配套硬门」升为 **P0 第一优先**。
> 理由：本轮实测「30pp 的横截面差距其实是噪声」，这道门是唯一能防止把噪声
> 当能力呈现给用户的机制。没有它，记录卡就是在骗人。

## 1. 概述

新增 `src/finer/credibility/`（CRD 组的第一个模块），回答两个**相互独立**的问题：

1. **样本充分性**——n 够不够让这个比率有意义。
2. **预测性主张许可**——这个指标有没有被证明能预测未来。

把两者混为一谈正是定位转向所纠正的错误：瑞银 n=435 的历史超额估得**很准**
（门 1 通过），但它**不能**预测未来超额（门 2 不通过）。一个按历史超额排序的
榜单，即使每个数字都统计显著，仍然是在宣称一件数据不支持的事。

## 2. 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `configs/significance.yaml` | 新增 | 阈值与预测性主张许可的**文件真值** |
| `src/finer/schemas/significance.py` | 新增 | `SampleSufficiency`、`PredictiveClaimVerdict` + 两个模块级 Literal |
| `src/finer/credibility/__init__.py` | 新增 | CRD 组包，定位前提写在 docstring |
| `src/finer/credibility/significance.py` | 新增 | Wilson 区间 + `SignificanceGate`（TTL 缓存，模式同 `kol_registry`） |
| `src/finer/backtest/scorecard.py` | 修改 | `GroupStats` 增 `total_n` / `sufficiency`；`ranked` 改由门判定；渲染增 95% 区间列、预测性声明、provisional 档 |
| `tests/test_significance_gate.py` | 新增 | 20 个单测 |

## 3. 关键设计

### 3.1 两道门必须独立

`SampleSufficiency.tier` 与 `predictive_claim.permitted` 是两个字段，
`assess()` 同时产出但互不影响。单测
`test_large_sample_does_not_license_prediction` 直接钉住这条：
n=435、tier=sufficient，而 `permitted=False`。

### 3.2 未检验一律不许可

`predictive_claim` 段按指标登记。**未登记的指标返回 `permitted=False`**——
「没有证据说它不行」不是「有证据说它行」。`kol_excess_win_rate` 与
`consensus_direction` 都以 `permitted: false` + `tested_at: null` 显式登记，
避免它们因为「还没测所以没写」而被默认放行。

许可只能由一次通过预声明判据的检验翻为 true，配置里写明这一条。

### 3.3 失败模式偏向保守

配置读不到 / 顶层不是映射 / 分档名或呈现策略不认识 → 一律退到
`insufficient` + `count_only` + 不许可。**「读不到阈值」绝不能退化成「放行」。**
三个单测分别钉住这三种损坏形态。

### 3.4 用 Wilson 而非正态近似

小样本与极端比例下正态近似会给出越界（>1）或过窄的区间，而本层最需要
诚实的恰恰是小样本。单测钉住 8/8 全胜时上界仍 ≤1。
不引入 scipy——常用置信水平查表，其余用 Beasley-Springer-Moro 逼近。

### 3.5 结算覆盖率是独立的降档条件

`settled/total` 低于阈值时，即使 n 很大也降一档：能结算的那部分可能系统性
不同于全体（例如取不到价的小盘股被整体排除）。当前真实数据覆盖率
77%–100%，无一触发——**这条路径目前只有单测覆盖，尚未被真实数据检验过**。

## 4. 实测结果

### 4.1 门的过滤效果（23 家信源）

| 呈现策略 | 家数 |
|---|---:|
| `show` | 12 |
| `show_with_warning` | 2（美银 25、汇丰 17） |
| `count_only` | 9 |
| 因覆盖率降档 | 0 |
| 允许做预测性主张 | **0** |

### 4.2 横截面排名几乎不可分辨

对 12 家可展示信源做两两比较，看 95% Wilson 区间是否重叠：

**66 个配对中只有 2 个（3.0%）不重叠。**

| 可分辨的配对 |
|---|
| RBC 55.0% > 杰富瑞 39.9% |
| RBC 55.0% > 野村 30.0% |

且两对都涉及 RBC——它恰是加拿大敞口最重的一家（CA 市场语料胜率 73.6%），
剥离市场暴露后其超额只有 +3.4%。

这个数字与持续性检验相互印证：**不仅历史不能预测未来，连"谁比谁强"这件
横截面的事，在当前样本下也基本说不出口。** 记分卡因此在表头直接写
「不要据此排序选择信源」。

## 5. 验证

```
pytest tests/test_significance_gate.py -q   →  20 passed
pytest tests/test_scorecard.py -q           →  11 passed（既有断言未改）
scripts/check_contract_drift.py             →  见 §6
pytest tests/ -q                            →  见 §6
```

`ranked` 改由门判定后，既有 `MIN_RANKED_N` 断言仍通过——因为
`tiers.sufficient.min_settled` 与该常量一致；常量降级为门加载失败时的兜底。

## 6. 未解决项

- **contracts.ts 未镜像**：`SampleSufficiency` 目前无前端消费方，drift 检查
  是 TS→Python 方向故不报错。UI 轮消费时须同步镜像并在 `REGISTRY` 登记
  `SAMPLE_TIER_LITERAL` / `DISPLAY_POLICY_LITERAL`。
- **覆盖率降档路径未被真实数据检验**（§3.5）。
- **门尚未强制**：目前只有 `scorecard.py` 调用。CRD-1 记录卡与 PROJ-1 投影
  落地时须一并强制，否则仍可绕过。
- `market` 维度的 GroupStats 未挂门（市场基线是口径不是评价对象，
  但若将来对外展示市场胜率，同样需要门）。
