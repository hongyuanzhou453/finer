# Finer 架构 v2 迁移对照表

> 版本: 1.0.0 | 创建: 2026-04-28
> 用途: L0-L8 和 V0-V6 到 F0-F8 的完整映射。旧命名仅保留于此文件，不再出现在主架构文档中。

---

## 1. 命名体系对照

### 1.1 L0-L8 → F0-F8

| 旧 L 层 | 旧中文名 | 旧目录 | → | 新 F-stage | 新中文名 | 新目录 | 变更说明 |
|---|---|---|---|---|---|---|---|
| L0 | 接入层 | `ingestion/` | → | **F0** | Intake (接入) | `ingestion/` | 职责不变 |
| L1 | 富化层 | `enrichment/` | → | **F2** | Anchor (锚定) | `enrichment/` | 重新定位：从"富化"升级为"质量+时间+实体锚定" |
| L2 | 标准化层 | — | → | **F1** | Standardize (标准化) | `parsing/` | 重新定位：内容标准化而非格式标准化 |
| L3 | 解析层 | `parsing/` | → | **F1** | Standardize | 合并：OCR/ASR 归入 F1 标准化 |
| L4 | 聚合层 | `aggregation/` | → | **F2** | Anchor | 合并：实体消歧/上下文聚合归入 F2 锚定 |
| L5 | 抽取层 | `extraction/` | → | **F5** | Execute (执行) | 重新定位：从"抽取"升级为"执行"，且必须有 F3/F4 前置 |
| — | — | — | → | **F3** | Intent (意图) | **新增**：投资意图层，前置于 TradeAction |
| — | — | — | → | **F4** | Policy (策略) | **新增**：意图→交易映射层 |
| L6 | 复核层 | `api/routes/` | → | **F6** | Review (复核) | 职责不变 |
| L7 | 时间线层 | `timeline/` | → | **F7** | Timeline (时间线) | 职责相同，需升级 |
| L8 | 回测层 | `backtest/` | → | **F8** | Backtest (回测) | 职责不变 |

### 1.2 V0-V6 → F0-F8

| 旧 V 层 | 旧名称 | → | 新 F-stage | 新名称 |
|---|---|---|---|---|
| S0 | Raw Source | → | **F0** | Intake |
| V0 | Content Standardization | → | **F1** | Standardize |
| V0.5 | Quality/Temporal/Entity | → | **F2** | Anchor |
| V1 | NormalizedInvestmentIntent | → | **F3** | Intent |
| V2 | Policy Mapping | → | **F4** | Policy |
| V3 | ExecutableTradeAction | → | **F5** | Execute |
| V4 | Timeline + Viewpoint State | → | **F7** | Timeline |
| V5 | Backtest + KOL Evaluation | → | **F8** | Backtest |
| V6 | Training Data + Model Improvement | → | **F+** | Training Loop (非独立 stage) |

### 1.3 三方对照总表

| F | L | V | 名称 | 状态 |
|---|---|---|---|---|
| **F0** | L0 | S0 | Intake | implemented |
| **F1** | L2, L3 | V0 | Standardize | partial |
| **F2** | L1, L3, L4 | V0.5 | Anchor | partial |
| **F3** | — | V1 | Intent | partial |
| **F4** | — | V2 | Policy | **missing** |
| **F5** | L5 | V3 | Execute | partial |
| **F6** | L6 | — | Review | implemented |
| **F7** | L7 | V4 | Timeline | partial |
| **F8** | L8 | V5 | Backtest | partial |
| **F+** | — | V6 | Training | contract-only |

---

## 2. 文件迁移对照

### 2.1 现有文件 → F-stage 归属

| 文件路径 | 当前 L 层 | → | F-stage | 迁移动作 |
|---|---|---|---|---|
| `ingestion/feishu_poller.py` | L0 | → | F0 | 不变 |
| `ingestion/orchestrator.py` | L0 | → | F0 | 不变 |
| `ingestion/bilibili_adapter.py` | L0 | → | F0 | 不变 |
| `ingestion/wechat_adapter.py` | L0 | → | F0 | 不变 |
| `ingestion/wechat_exporter_client.py` | L0 | → | F0 | 不变 |
| `ingestion/nlm_sync.py` | L0 | → | F0 | 不变 |
| `ingestion/classifier.py` | L0 | → | F0 | 不变 |
| `api/routes/files.py` | L0 | → | F0 | 不变 |
| `api/routes/wechat.py` | L0 | → | F0 | 不变 |
| `api/routes/bilibili.py` | L0 | → | F0 | 不变 |
| `schemas/content.py` | L0 | → | F0 | 不变 |
| `schemas/content_envelope.py` | new | → | F1, F2 | 不变 |
| `parsing/content_standardizer.py` | L3 | → | F1 | 不变 |
| `parsing/vision_extractor.py` | L3 | → | F1 | 不变 |
| `parsing/audio_extractor.py` | L3 | → | F1 | 不变 |
| `parsing/funasr_client.py` | L3 | → | F1 | 不变 |
| `parsing/mimo_asr_client.py` | L3 | → | F1 | 不变 |
| `parsing/context_summarizer.py` | L3 | → | F1 | 不变 |
| `enrichment/__init__.py` | L1 | → | F2 | 不变 |
| `enrichment/market_context.py` | L1 | → | F2 | 不变 |
| `enrichment/sentiment_fusion.py` | L1 | → | F2 | 不变 |
| `entity_registry.py` | — | → | F2 | 不变 |
| `aggregation/__init__.py` | L4 | → | F2 | 可合并到 enrichment/ |
| `api/routes/enrichment.py` | L1 | → | F2 | 不变 |
| `api/routes/aggregation.py` | L4 | → | F2 | 不变 |
| `schemas/investment_intent.py` | new | → | F3 | 不变 |
| `extraction/intent_extractor.py` | L5 | → | F3 | **需重写**（从 rule-based → LLM-based） |
| **(新文件)** `policy/__init__.py` | — | → | **F4** | **待创建** |
| **(新文件)** `policy/policy_mapper.py` | — | → | **F4** | **待创建** |
| **(新文件)** `schemas/policy.py` | — | → | **F4** | **待创建** |
| `schemas/trade_action.py` | L5 | → | F5 | 需增加 intent_id/policy_id/evidence_span_ids |
| `extraction/trade_action_extractor.py` | L5 | → | F5 | 需改为接收 PolicyMappedIntent |
| `extraction/enriched_extractor.py` | L5 | → | F5 | 不变（但需适配新输入） |
| `extraction/extractor.py` | L5 | → | F5 | 不变 |
| `api/routes/extraction.py` | L5 | → | F5 | 不变 |
| `api/routes/rlhf.py` | L6 | → | F6 | 不变 |
| `api/routes/review.py` | L6 | → | F6 | 不变 |
| `timeline/engine.py` | L7 | → | F7 | 需增加 ViewpointState |
| `timeline/models.py` | L7 | → | F7 | 需增加 ViewpointState schema |
| `api/routes/opinions.py` | L7 | → | F7 | 需移除/标记 mock fallback |
| `api/routes/kol.py` | L7 | → | F7 | 需移除/标记 mock fallback |
| `backtest/engine.py` | L8 | → | F8 | 不变 |
| `backtest/prices.py` | L8 | → | F8 | 不变 |
| `api/routes/backtest.py` | L8 | → | F8 | 需移除 mock 价格默认 |
| `pipeline/orchestrator.py` | cross | → | cross-stage | **需重写**为 F0-F8 流程 |
| `services/finance_skills_client.py` | — | → | F2, F8 | 不变 |
| `services/llm.py` | — | → | cross-stage | 不变 |

### 2.2 数据目录迁移

| 旧目录 | → | 新目录 | 说明 |
|---|---|---|---|
| `data/L0_ingest/` | → | `data/F0_intake/` | F0 接入产物 |
| `data/L1_enrichment/` | → | 合并到 `data/F2_anchored/` | F2 锚定产物 |
| `data/L2_standardized/` | → | `data/F1_standardized/` | F1 标准化产物 |
| `data/L3_aligned/` | → | 合并到 `data/F2_anchored/` | F2 时间/实体锚定 |
| `data/L4_parsed/` | → | 合并到 `data/F2_anchored/` | F2 聚合产物 |
| `data/L5_candidate/` | → | `data/F3_intents/` + `data/F5_executed/` | 拆分 Intent 和 TradeAction |
| `data/L6_annotated/` | → | `data/F6_reviewed/` | F6 复核产物 |
| `data/L7_model_results/` | → | `data/F7_timeline/` | F7 时间线产物 |
| `data/L8_metrics/` | → | `data/F8_metrics/` | F8 回测产物 |

---

## 3. 关键架构决策

### 3.1 为什么 F3 和 F5 必须分离

旧架构: 原始文本 → TradeActionExtractor → TradeAction（方向+仓位+价格+触发条件一次输出）

问题:
- "看好"和"加仓"在提取阶段无法区分 actionability
- 仓位比例无法根据 KOL 风格个性化
- 证据链断裂：无法从 TradeAction 追溯到原文的哪个句子产生了哪个判断

新架构:
- F3 只回答"这个 KOL 表达了什么观点"（方向、可操作程度、信念）
- F4 回答"这个观点在 X 风格下应该如何交易"（仓位、时间、触发条件）
- F5 只是组装执行动作，不做语义判断

### 3.2 为什么 F4 是唯一合法转换层

- F3 Intent 是纯观点表达，与交易无关
- 不同的 F4 Policy 对同一个 Intent 可能产生完全不同的 TradeAction
- 如果 F5 可以直接从 Intent 生成 TradeAction，就会绕过 policy 个性化
- 绕过的后果：不同 KOL 对同一标的的观点无法区分交易参数

### 3.3 Legacy Path: Raw Text → TradeAction

当前 `extraction/trade_action_extractor.py` 中的 `extract_from_text()` 路径是 **legacy path**，标记为 deprecated。

**Legacy path 仅在以下情况允许使用**:
- 快速原型验证
- 开发环境测试
- 不应用于生产 pipeline 或回测结果

**Canonical path**: F0 → F1 → F2 → F3 → F4 → F5

---

## 4. 迁移检查清单

### 4.1 Schema 层

- [x] F1: ContentEnvelope, ContentBlock schema 完整
- [x] F2: QualityCard, TemporalAnchor, EntityAnchor, EvidenceSpan schema 完整
- [x] F3: NormalizedInvestmentIntent schema 完整
- [ ] **F4: PolicyMappingResult schema 待创建**
- [ ] **F5: TradeAction 增加 intent_id, policy_id, evidence_span_ids**

### 4.2 实现层

- [x] F0: 飞书接入实现
- [ ] F1: 非文本 block 化
- [ ] F2: 时间自动解析
- [ ] **F3: LLM-based IntentExtractor**
- [ ] **F4: PolicyMapper 实现**
- [ ] **F5: 接入 F4 输入，移除直接文本提取路径**

### 4.3 Pipeline 层

- [ ] **F3→F4→F5 端到端集成**
- [ ] **F8 pipeline 修复 placeholder**
- [ ] F7 ViewpointState 实现
- [ ] F+ 训练数据生成验证

### 4.4 前端

- [ ] WORKFLOW_VIEWS 更新为 F0-F8 命名
- [ ] 新增 F3 Intent 视图
- [ ] 新增 F4 Policy 视图
- [ ] 移除 mock fallback 或加环境标记

---

*更新: 2026-04-28*
