# Finer Skills Registry — 可自进化组件注册表

> 维护人: 全体 Agent（新增 Skill 必须登记）
> 模式规范: [自进化 Skill 模式](2026-06-30-self-evolving-skill-pattern.md)
> 最后更新: 2026-06-30

本表登记所有按[自进化 Skill 模式](2026-06-30-self-evolving-skill-pattern.md)管理的「受约束可迭代组件」（Finer-Skill）。一个组件成为 Skill 的 5 个必要条件见模式规范 §2：固定内核 + 机器可读可调面 + 量化指标 + 样本隔离 + 版本化结果。

## 注册表

| Skill ID | 组件 | 协议 `SKILL.md` | 可调配置 | 版本根 | holdout / sealed | 量化指标 | 适配度 / 状态 |
|---|---|---|---|---|---|---|---|
| `dpo-rlvr-loop` | `src/finer/ml/` + `scripts/` | `src/finer/ml/SKILL.md` *(待建)* | `configs/ml_models.yaml::dpo` + `rewards.py::DEFAULT_WEIGHTS`/`CONVICTION_BUCKETS` ✅ | `data/dpo/{version}/`（grandfathered，迁移见模式 §10） | holdout: `data/dpo/{v}/eval/`；sealed: `data/dpo/hq_v1/eval/eval_set.jsonl` | verifier reward（structure 门 / grounding .50 / calibration .40 / abstention .10）+ eval_compare 三指标 | 高 · `rewards.py` 已建+grounding registry-aware；HQ-green 瓶颈转 F2 registry 覆盖 |
| `f2-entity-anchoring` | `src/finer/enrichment/` | `src/finer/enrichment/SKILL.md` *(待建)* | `configs/skills/f2-entity-anchoring.yaml` *(脚手架，未 wire)* | **待建（M1）**：all-local 按 block-id 切 dev/holdout | hit-rate / 插入实体 precision | 中 · M1 目标 |
| `kol-scorer` | `src/finer/ml/kol_scorer.py` | `src/finer/ml/SKILL.md`（与 dpo 共目录，分节） *(待建)* | `configs/ml_models.yaml::kol_scorer`（v2_weights 已 YAML 化） | `data/skills/kol-scorer/{v}/` *(待建)* | holdout KOL 集 *(待建)* | 评分 rank 与回测 Sharpe/return 的 rank-correlation | 中 · M3 |
| `f8-backtest` | `src/finer/backtest/` | `src/finer/backtest/SKILL.md` *(待建)* | `configs/ml_models.yaml::backtest`（仅 4/15 字段持久化，需补全） | `data/F8_metrics/{backtest_id}.json` + `index.json`（无血缘，需加 parent/version） | 无时间切分 *(待建)* | 每 KOL hit-rate / Sharpe（需加 benchmark 相对指标） | 中 · M3+ |
| `f3f4f5-policy` | `src/finer/policy/` + `src/finer/extraction/` | `src/finer/policy/SKILL.md` *(待建)* | `configs/skills/f3f4-policy.yaml` *(脚手架，阈值仍硬编码于 intent_extractor.py / global_base.py)* | `data/skills/f3f4f5-policy/{v}/` *(待建)* | 分阶段正确性 vs F6 RLHF 标签（conviction calibration） | 中 · M3 |

> *(待建)* = 模式已规定但尚未落地。空格 = 该列对该 Skill 尚无内容。

## 固定内核速查（禁止迭代触碰）

| Skill | 内核真相源（禁改） |
|---|---|
| `dpo-rlvr-loop` | verifier 只查表裁决；F8 收益不进 reward；`schemas/trade_action.py` 枚举；schema 真相源 |
| `f2-entity-anchoring` | `entity_anchoring.py` 扫描算子；`EntityAnchor` 契约；word-boundary 规则；`entity_registry.py` 是 registry 真相源 |
| `kol-scorer` | 评分维度定义；回测真值不可被评分反向污染 |
| `f8-backtest` | `engine.py` 日循环 + PnL 数学；`validators.py` canonical TradeAction 输入契约 |
| `f3f4f5-policy` | `global_base.py::_ACTION_RULES` 规则表；F3 只出 Intent 不出 TradeAction；F4 无 LLM |

## 新增 Skill 登记流程

1. 在组件目录建 `SKILL.md`（协议层：内核/可调面/单假设纪律/保留判据，见模式 §3.1）。
2. 把可调参落到 `configs/skills/{id}.yaml` 或 `configs/ml_models.yaml` 既有段。
3. 在本表加一行；在「固定内核速查」加内核真相源。
4. 首版迭代产出 `data/skills/{id}/v1/manifest.json`（可重建记录，schema 见模式 §3.2）。
5. 确认 holdout / sealed 的 id 隔离已就位（模式 §3.3），CI 把 dev/holdout 重叠判为硬失败。
