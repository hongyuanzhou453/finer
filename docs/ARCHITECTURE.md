# Finer OS 架构文档 v2.0

> **版本**: 3.0.0
> **最后更新**: 2026-04-28
> **状态**: **F0-F8 是 Finer OS 唯一主架构。** 本文档是 F0-F8 流水线的可执行契约。旧命名 L0-L8 和 V0-V6 已废弃（deprecated），仅在下文第 16 章 Legacy Mapping 和 `docs/specs/f-stage-contracts.md` 中保留供迁移参考。
> **原则**: 所有代码、文档、commit message、API 设计、Agent 任务边界必须以 F0-F8 为唯一命名体系。任何新引入 L0-L8 或 V0-V6 命名的 PR 必须被拒绝。

---

## 目录

1. [项目愿景](#1-项目愿景)
2. [F0-F8 流水线总览](#2-f0-f8-流水线总览)
3. [F-stage 详解](#3-f-stage-详解)
4. [数据模型](#4-数据模型)
5. [API 参考](#5-api-参考)
6. [前端架构](#6-前端架构)
7. [外部集成](#7-外部集成)
8. [配置管理](#8-配置管理)
9. [成熟度状态总表](#9-成熟度状态总表)
10. [已知问题与断点](#10-已知问题与断点)
11. [部署与运维](#11-部署与运维)
12. [开发规范](#12-开发规范)
13. [数据治理](#13-数据治理)
14. [非功能性需求](#14-非功能性需求)
15. [Agent Execution Rules（Agent 执行规则）](#15-agent-execution-rulesagent-执行规则)
16. [Legacy Mapping（旧命名对照）](#16-legacy-mapping旧命名对照)

---

## 1. 项目愿景

### 1.1 核心目标

**将财经 KOL 的所有发布内容按时间线整理，并进行回测，验证如果对这个 KOL 进行跟随交易的收益率和市场表现。**

### 1.2 三个不可约子目标

| # | 子目标 | 本质问题 |
|---|---|---|
| G1 | **KOL 内容采集与归一化** | 任意平台的 KOL 内容 → 统一结构化记录 |
| G2 | **按时间线聚合** | 以 KOL 为中心轴，以时间为排序键，构建完整的"观点编年史" |
| G3 | **跟随交易回测** | 模拟一个"完全跟单者"的 Portfolio 随时间的收益曲线，与基准对比 |

### 1.3 配套文档

| 文档 | 用途 |
|---|---|
| `docs/architecture-v2-migration-map.md` | L→F、V→F 迁移对照表 |
| `docs/specs/f-stage-contracts.md` | 每阶段输入/输出/Schema/禁止职责/验收清单 |
| `docs/architecture-alignment-plan.md` | Phase A-G 分阶段实施计划 |

---

## 2. F0-F8 流水线总览

### 2.1 技术栈

| 层级 | 技术选型 |
|---|---|
| **后端** | Python 3.11+ / FastAPI / Pydantic V2 |
| **前端** | TypeScript / Next.js 16 / React 19 / TailwindCSS 4 |
| **LLM** | GLM-5.1 (SVIPS) / Qwen-Plus (DashScope) / Qwen-VL-Plus |
| **数据存储** | 文件系统 (JSON/Markdown) + SQLite 索引层 |
| **外部服务** | Finance-Skills / Feishu API / NotebookLM |

### 2.2 Canonical 流水线

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Finer OS F0-F8 Canonical Pipeline                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  F0 INTAKE        F1 STANDARDIZE     F2 ANCHOR          F3 INTENT           │
│  ┌──────────┐     ┌──────────┐       ┌──────────┐       ┌──────────┐        │
│  │ 飞书     │     │ Envelope │       │ Quality  │       │direction │        │
│  │ B站      │ ──→ │ Block    │ ──→   │ Temporal │ ──→   │actionab- │        │
│  │ 微信     │     │ 类型:13  │       │ Entity   │       │ility     │        │
│  │ 手动     │     │ 来源:7   │       │ Evidence │       │conviction│        │
│  └──────────┘     └──────────┘       └──────────┘       └──────────┘        │
│                                                                     │        │
│                                                                     ▼        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         F4 POLICY                                     │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │   │
│  │  │Global Base │→│Style Arch. │→│Risk Pref.  │→│KOL Persona │     │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                     │        │
│                                                                     ▼        │
│  F5 EXECUTE        F6 REVIEW          F7 TIMELINE        F8 BACKTEST       │
│  ┌──────────┐     ┌──────────┐       ┌──────────┐       ┌──────────┐       │
│  │ Trade    │     │ RLHF     │       │ KOL      │       │Portfolio │       │
│  │ Action   │ ──→ │ 人工复核 │ ──→   │ 观点状态 │ ──→   │跟单模拟  │       │
│  │+intent_id│     │ DPO导出  │       │ 分歧图谱 │       │KOL评分   │       │
│  │+policy_id│     └──────────┘       └──────────┘       └──────────┘       │
│  └──────────┘                                                              │
│                                                                              │
│  F+ TRAINING LOOP (跨阶段闭环，非独立 F-stage)                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  F6 RLHF数据 + F7 时间线 + F8 回测结果 → SFT/DPO → 改进 F1/F3/F4    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 F-stage 速览

| Stage | 名称 | 输入 | 输出 | 核心 Schema | 状态 |
|---|---|---|---|---|---|
| **F0** | Intake | 飞书/B站/微信/手动 | ContentRecord + 原始文件 | ContentRecord | implemented |
| **F1** | Standardize | F0 输出 | ContentEnvelope + ContentBlock[] | ContentEnvelope, ContentBlock | partial |
| **F2** | Anchor | F1 输出 | +QualityCard +TemporalAnchor +EntityAnchor +EvidenceSpan | QualityCard, TemporalAnchor, EntityAnchor, EvidenceSpan | partial |
| **F3** | Intent | F2 (gate≥soft_pass) | NormalizedInvestmentIntent[] | NormalizedInvestmentIntent | partial |
| **F4** | Policy | F3 Intent[] | PolicyMappedIntent[] | PolicyMappingResult | **missing** |
| **F5** | Execute | F4 PolicyMappedIntent[] | TradeAction[] (+intent_id, +policy_id, +evidence_span_ids) | TradeAction | partial |
| **F6** | Review | F5 TradeAction[] | Reviewed TradeAction + RLHFFeedback | RLHFFeedback | implemented |
| **F7** | Timeline | F3/F5/F6 输出 | KOLTimeline + ViewpointState + TargetOpinionGraph | KOLTimeline, ViewpointState | partial |
| **F8** | Backtest | F5 TradeAction[] + 价格数据 | BacktestResult + KOLScore | BacktestResult | partial |
| **F+** | Training | F6/F7/F8 输出 | SFT/DPO 训练数据 | — | contract-only |

### 2.4 成熟度状态定义

| 状态 | 含义 | 判断标准 |
|---|---|---|
| **implemented** | 端到端可用 | 输入→存储→API→前端→测试全链路打通 |
| **partial** | 部分实现 | 核心逻辑存在，但有关键缺口（如缺上游输入、缺下游消费、测试不覆盖） |
| **placeholder** | 占位 | 函数/方法存在但只写死返回值或空操作，不执行真实逻辑 |
| **mock-backed** | 依赖 mock 数据 | 真实数据路径存在但在无数据时 fallback 到随机/假数据 |
| **contract-only** | 仅有契约 | Schema 定义了但无实现代码，或仅有 fixture 测试 |
| **missing** | 完全缺失 | 代码库中不存在对应模块 |

---

## 3. F-stage 详解

### 3.1 F0: Intake（接入）

**职责**: 多源数据接入，统一入库。原始内容原样存档，不做任何语义处理。

**输入**: 飞书群聊消息、B站视频、微信公众号文章、手动上传文件

**输出**: `ContentRecord` + 原始文件归档到 `data/raw/`

**Schema**: `ContentRecord` (`schemas/content.py`)

**Owning files**:
- `ingestion/feishu_poller.py` — 飞书消息轮询
- `ingestion/orchestrator.py` — 接入编排
- `ingestion/bilibili_adapter.py` — B站视频
- `ingestion/wechat_adapter.py` + `wechat_exporter_client.py` — 微信公众号
- `ingestion/nlm_sync.py` — NotebookLM 同步
- `api/routes/files.py` — 手动上传 + 文件管理

**当前状态**: `implemented` (飞书), `partial` (B站/微信)

**禁止职责**:
- 不做 OCR/ASR/文本解析
- 不做话题拆分或实体抽取
- 不做任何 LLM 调用
- 不做内容质量判断

---

### 3.2 F1: Standardize（标准化）

**职责**: 将异构原始内容统一为 `ContentEnvelope` → `ContentBlock` 结构。每种来源类型有不同的 block 化策略。

**输入**: F0 原始文件 + ContentRecord

**输出**: `ContentEnvelope` 包含 `ContentBlock[]`（13 种 block 类型）

**Schema**: `ContentEnvelope`, `ContentBlock` (`schemas/content_envelope.py`)

**Block 类型（13 种）**:
`chat_message`, `paragraph`, `image_text`, `table_region`, `chart_region`, `audio_segment`, `video_segment`, `quote`, `link_reference`, `section_title`, `ocr_unreadable`, `code_block`, `attachment_ref`

**来源类型（7 种）**:
`feishu_chat`, `feishu_doc`, `image`, `pdf`, `audio_transcript`, `video_transcript`, `wechat_article`, `manual`

**Owning files**:
- `schemas/content_envelope.py` — Schema 定义
- `parsing/content_standardizer.py` — 标准化逻辑
- `parsing/vision_extractor.py` — 图片→block
- `parsing/audio_extractor.py` — 音频→block

**当前状态**: `partial`
- Schema 定义完整（ContentEnvelope, ContentBlock, 13 种 block 类型, 7 种来源类型）
- 图片 OCR→block 标准化不完整（ARCHITECTURE.md A3: 表格/图表区域 OCR 不可靠）
- 飞书聊天→block 线程/说话人恢复未实现
- PDF→block 跨页结构保留未端到端验证
- 音频转录→block 语义分段未自动化

**禁止职责**:
- 不做质量评估（那是 F2 的职责）
- 不做投资意图判断
- 不做实体链接或标准化
- 不做时间解析

---

### 3.3 F2: Anchor（锚定）

**职责**: 对 F1 的输出进行质量评估、时间锚定、实体锚定、证据链建立。决定哪些内容可以进入 F3。

**输入**: F1 `ContentEnvelope` + `ContentBlock[]`

**输出**: F1 输出 + `QualityCard`（6 维）+ `TemporalAnchor`（4 类时间）+ `EntityAnchor` + `EvidenceSpan`

**Schema**: `QualityCard`, `TemporalAnchor`, `EntityAnchor`, `EvidenceSpan` (均定义在 `schemas/content_envelope.py`)

**6 维质量卡**:

| 维度 | 含义 | 判断方式 |
|---|---|---|
| `readability` | 文本可读性 | OCR/ASR 乱码率 |
| `semantic_completeness` | 语义完整性 | 是否缺页、截断 |
| `financial_relevance` | 金融相关性 | 是否包含投资相关内容 |
| `entity_resolution` | 实体可解析 | 股票/公司能否标准化 |
| `temporal_resolution` | 时间可解析 | 是否有可用的时间信息 |
| `evidence_traceability` | 证据可追溯 | intent 能否回到原文位置 |

**4 类时间锚**:

| 类型 | 含义 | 示例 |
|---|---|---|
| `published_at` | 内容发布时间 | 2026-04-12 20:00 |
| `mentioned_at` | 文本中提到的时间 | "上周" |
| `resolved_at` | 解析后的绝对时间 | 2026-04-05 ~ 2026-04-11 |
| `effective_trade_at` | 回测交易生效时间 | 2026-04-06 开盘 |

**门控等级**:

| 等级 | 条件 | 处理 |
|---|---|---|
| `pass` | 关键字段完整，证据可追溯 | 自动进入 F3 |
| `soft_pass` | 小缺陷但不影响意图判断 | 进入 F3，标注 warning |
| `review` | 时间/标的/动作存在歧义 | 进入人工复核队列 |
| `reject` | 内容不可读或证据断裂 | 不进入 F3，仅存档 |

**Owning files**:
- `schemas/content_envelope.py` — QualityCard, TemporalAnchor, EvidenceSpan 定义
- `enrichment/__init__.py` — TopicSplitter, EntityExtractor
- `enrichment/market_context.py` — MarketContextEnricher (P0)
- `enrichment/sentiment_fusion.py` — SentimentFusionEnricher (P1)
- `entity_registry.py` — 统一实体注册表 (~150 映射)

**当前状态**: `partial`
- Schema 定义完整
- QualityCard 定义了但未在全链路强制使用
- TemporalAnchor 大部分字段为空（缺少自动时间解析）
- EntityAnchor 在 enrichment 中有部分实现，但未与统一注册表完全打通
- EvidenceSpan 定义了但当前 TradeAction 直提路径不经过它

**禁止职责**:
- 不做投资意图提取（F3）
- 不做交易动作生成（F5）
- 不做 policy 映射（F4）

---

### 3.4 F3: Intent（意图）

**职责**: 从质量过关的 ContentEnvelope 中提取标准化投资意图。F3 只回答"这个 KOL 表达了什么观点"，不回答"应该怎么交易"。

**输入**: F2 输出（gate ≥ soft_pass 的 ContentEnvelope）

**输出**: `NormalizedInvestmentIntent[]`

**Schema**: `NormalizedInvestmentIntent` (`schemas/investment_intent.py`)

**四轴定义**:

| 轴 | 含义 | 可选值 |
|---|---|---|
| `direction` | 多空方向 | bullish / bearish / neutral / watchlist / risk_warning |
| `actionability` | 可操作程度 | opinion / watch / explicit_action |
| `position_delta_hint` | 仓位变化提示 | open / add / reduce / hold / exit / none |
| `conviction` | 信念强度 | 0.0–1.0 float |

**Owning files**:
- `schemas/investment_intent.py` — Schema 定义 + validators
- `extraction/intent_extractor.py` — 当前仅有 rule-based 关键词匹配原型

**当前状态**: `partial`
- Schema 定义完整，validator 齐全
- **仅有 rule-based 关键词匹配原型**（`BULLISH_KEYWORDS`, `BEARISH_KEYWORDS` 等硬编码列表）
- **无 LLM-based 提取器**：没有 Instructor + LLM 调用来真正从 KOL 文本中提取 Intent
- confidence 硬编码（0.6–0.8），不做实际置信度评估
- `extract_intents_from_envelope()` 存在但从未被 pipeline 调用

**关键契约**: **F3 MUST NOT generate TradeAction.** F3 的职责止于意图表达。仓位比例、目标价格、止损止盈、触发条件等交易参数一律不得在 F3 出现。

**禁止职责**:
- ❌ 不生成仓位比例（position_size_pct）
- ❌ 不生成目标价格（target_price_low, target_price_high）
- ❌ 不生成触发条件（trigger_condition）
- ❌ 不生成止损止盈
- ❌ 不直接生成 TradeAction
- ❌ 不执行交易动作映射

---

### 3.5 F4: Policy（策略映射）

**职责**: 将 Intent 转换为可执行的 TradeAction 参数。**F4 is the only legal Intent-to-TradeAction policy mapping layer.** 同一句"加仓"在不同 KOL 风格下应产生不同的仓位/持仓期/动作强度。任何绕过 F4 直接从 Intent 或原始文本生成 TradeAction 的路径，均为 deprecated。

**输入**: F3 `NormalizedInvestmentIntent[]`

**输出**: `PolicyMappedIntent[]`（Intent + policy 参数：仓位比例、时间范围、风险约束）

**Schema**: `PolicyMappingResult`（待创建）

**5 层 Policy 结构**:

```
Global Base Policy          — 通用金融语言→动作基准映射（人工规则）
  → Style Archetype Policy  — 短线/景气/价值/烟蒂等风格差异（聚类 + 人工命名）
    → Risk Preference Policy — 激进/均衡/保守（从历史内容统计）
      → KOL Persona Policy   — 个体 KOL 的口头禅、动作含义（200-1000 条内容总结）
        → Content Correction  — 当前上下文的临时修正（F3 抽取时动态生成）
```

**Owning files**: **不存在 — 整个 F4 层代码缺失**

**当前状态**: `missing`
- `architecture-alignment-plan.md` 定义了 5 层 policy 架构
- 代码库中无 PolicyMapper 类、无 policy 配置文件、无 persona 模型
- 当前 `trade_action_extractor.py` 直接从文本生成 TradeAction，完全跳过 policy 层

**禁止职责**:
- ❌ 不生成新的 Intent（Intent 只能来自 F3）
- ❌ 不修改 Intent 的 direction（除非有 audit log）
- ❌ 不覆盖 conviction 而不记录理由

---

### 3.6 F5: Execute（交易执行）

**职责**: 从 PolicyMappedIntent 生成可执行、可回测、可审计的 TradeAction。

**输入**: F4 `PolicyMappedIntent[]`

**输出**: `TradeAction[]`，每条 **必须** 包含 `intent_id`, `policy_id`, `evidence_span_ids`

**Schema**: `TradeAction` (`schemas/trade_action.py`, 750 行)

**Owning files**:
- `schemas/trade_action.py` — 完整 TradeAction schema（含 enums, nested models, validators）
- `extraction/trade_action_extractor.py` (851 行) — GLM-5.1 + Finance-Skills 混合策略提取器

**当前状态**: `partial`
- TradeAction schema 完整（750 行，含 ActionChain, MarketEnrichment, RLHFFeedback, BacktestResult）
- TradeActionExtractor 功能齐全（confidence 阈值、batch 提取、enrichment、validation）
- **但存在三个关键缺陷**:
  1. **跳过了 F3/F4**：直接从原始文本生成 TradeAction，没有经过 Intent→Policy 路径
  2. **缺少 intent_id / policy_id 字段**：TradeAction 与 Intent/Policy 之间没有 ID 关联
  3. **creator_id 几乎从未被填充**（ARCHITECTURE.md A4），KOL 归属链断裂

**必须增加的字段**:
```python
class TradeAction(BaseModel):
    # 新增：上游追溯
    intent_id: str                    # F3 Intent ID
    policy_id: str                    # F4 PolicyMappingResult ID
    evidence_span_ids: List[str]      # F2 EvidenceSpan IDs
```

**关键契约**: **F5 canonical TradeAction MUST include intent_id, policy_id, evidence_span_ids.** 这三个字段是 TradeAction 可审计性的必要条件。缺少任一字段的 TradeAction 不得进入 F6 Review 或 F8 Backtest。

**禁止职责**:
- ❌ 不直接从原始文本生成 TradeAction（必须经过 F3→F4→F5）
- ❌ 不跳过 policy 层自行决定仓位/触发条件
- ❌ 不生成没有 intent_id 的 TradeAction
- ❌ 不生成没有 evidence_span_ids 的 TradeAction

---

### 3.7 F6: Review（复核）

**职责**: 人工审核 TradeAction + Intent，收集 RLHF 反馈，导出 DPO 训练数据。

**输入**: F5 `TradeAction[]` + F3 `Intent[]`（用于证据对比）

**输出**: Reviewed TradeAction + `RLHFFeedback` + DPO 训练数据

**Schema**: `RLHFFeedback` (定义在 `schemas/trade_action.py`)

**Owning files**:
- `api/routes/rlhf.py` (667 行) — submit/pending/stats/export-DPO
- `api/routes/review.py` — 复核流程
- 前端: `rlhf-review-panel/` (9 个组件)

**当前状态**: `implemented`
- RLHF 提交/待审核列表/统计/DPO 导出端点完整
- 前端复核面板完整（方向/标的/操作链复核、快捷标签、整体评分）
- DPO 数据可导出

**禁止职责**:
- 不修改原始 EvidenceSpan
- 不直接修改 Intent（应通过 F3 重新提取）
- 不修改 TradeAction 而不记录 reviewer_id 和 reviewed_at

---

### 3.8 F7: Timeline（时间线）

**职责**: 以 KOL 为中心轴构建观点时间线，维护每个 KOL 对每个标的的 ViewpointState，支持跨文档观点演化追踪和多 KOL 分歧分析。

**输入**: F3 Intent[] + F5 TradeAction[] + F6 Review 结果

**输出**: `KOLTimeline` + `ViewpointState`（每 KOL 每标的）+ `TargetOpinionGraph`（多 KOL 同标的）

**Schema**: `KOLTimeline`, `TimelineEntry`, `ViewpointState`, `KOLComparison`

**Owning files**:
- `timeline/engine.py` — TimelineEngine
- `timeline/models.py` — Timeline 数据模型
- `api/routes/opinions.py` — 观点时间线 API（真实数据 + mock fallback）

**当前状态**: `partial`
- 基础 Timeline 查询可用（按 KOL/时间/标的筛选）
- **ViewpointState 未实现**：不维护"同一 KOL 对同一标的的观点演化"
- **TargetOpinionGraph 未实现**：不支持多 KOL 同标的分歧图谱
- opinions.py API 在无真实数据时 fallback 到 `random.choice()` mock 数据
- 依赖上游 `creator_id` 填充（当前几乎不填充）

**禁止职责**:
- 不生成新的 TradeAction
- 不修改 Intent 或 TradeAction 数据
- 不做回测计算（那是 F8）

---

### 3.9 F8: Backtest（回测）

**职责**: 基于 TradeAction 和市场数据模拟跟单 Portfolio，计算收益、风险指标，评估 KOL 表现。

**输入**: F5 TradeAction[]（含 effective_trade_at）+ 市场价格数据（yfinance / CachedPriceProvider）

**输出**: `BacktestResult` (return_pct, Sharpe, Sortino, Calmar, MaxDrawdown, VaR) + `KOLScore`

**Schema**: `BacktestResult`, `BacktestConfig` (定义在 `backtest/engine.py`)

**Owning files**:
- `backtest/engine.py` (832 行) — 完整 BacktestEngine + PortfolioSimulator
- `backtest/prices.py` — CachedPriceProvider, MockPriceProvider
- `api/routes/backtest.py` — 回测 API（run/results/compare/prices）

**当前状态**: `partial`
- **BacktestEngine 完整实现**（止损/止盈/时间退出、Sharpe/Sortino/Calmar/MaxDrawdown/VaR）
- **但 pipeline orchestrator 的 F8 stage runner 是 placeholder**（legacy 代码中名为 `_run_l8_backtest()`，标记为 deprecated）：只写 JSON，不调用 BacktestEngine
- **价格数据默认使用 MockPriceProvider**：`_prepare_price_data()` 在没有真实价格时用随机模拟数据
- 缺少 `effective_trade_at` 与 `timestamp` 的区分
- KOL 评分结果依赖 mock 数据

**禁止职责**:
- 不使用 mock 价格进行生产回测
- 不在没有 effective_trade_at 的情况下执行回测
- 不生成 TradeAction（只消费）

---

### 3.10 F+: Training Loop（训练闭环）

**职责**: 从 F6（RLHF）、F7（时间线）、F8（回测结果）生成高质量训练数据，微调模型改进 F1/F3/F4 的提取质量。

**当前状态**: `contract-only`
- RLHF 数据导出接口存在（`api/routes/rlhf.py` export-DPO）
- DPO trainer 存在（`ml/dpo_trainer.py`）
- 但训练数据量不足，未实际执行过训练

**注意**: F+ 不是编号 F-stage，而是跨阶段的闭环过程。

---

## 4. 数据模型

### 4.1 F-stage 数据流

```
F0 ContentRecord
  └→ F1 ContentEnvelope
       └→ F1 ContentBlock (13 种类型)
            └→ F2 QualityCard / TemporalAnchor / EntityAnchor / EvidenceSpan
                 └→ F3 NormalizedInvestmentIntent
                      └→ F4 PolicyMappingResult
                           └→ F5 TradeAction (+intent_id, +policy_id, +evidence_span_ids)
                                └→ F6 RLHFFeedback (人工修正)
                                     └→ F7 KOLTimeline / ViewpointState / TargetOpinionGraph
                                          └→ F8 BacktestResult / KOLScore
```

### 4.2 核心 Schema 速览

| Schema | 所属 F-stage | 文件 | 状态 |
|---|---|---|---|
| `ContentRecord` | F0 | `schemas/content.py` | implemented |
| `ContentEnvelope` | F1 | `schemas/content_envelope.py` | implemented |
| `ContentBlock` | F1 | `schemas/content_envelope.py` | implemented |
| `QualityCard` | F2 | `schemas/content_envelope.py` | implemented |
| `TemporalAnchor` | F2 | `schemas/content_envelope.py` | implemented |
| `EntityAnchor` | F2 | `schemas/content_envelope.py` | implemented |
| `EvidenceSpan` | F2 | `schemas/evidence.py` | implemented |
| `NormalizedInvestmentIntent` | F3 | `schemas/investment_intent.py` | implemented |
| `PolicyMappingResult` | F4 | (待创建) | **missing** |
| `TradeAction` | F5 | `schemas/trade_action.py` | implemented |
| `RLHFFeedback` | F6 | `schemas/trade_action.py` (嵌套) | implemented |
| `KOLTimeline` | F7 | `timeline/models.py` | implemented |
| `ViewpointState` | F7 | (待创建) | **missing** |
| `BacktestResult` | F8 | `backtest/engine.py` | implemented |

---

## 5. API 参考

### 5.1 路由总览

| 路由前缀 | F-stage | 功能 |
|---|---|---|
| `/api/files` | F0 | 文件管理、上传、列表 |
| `/api/enrichment` | F1, F2 | 富化、实体抽取、话题拆分 |
| `/api/aggregation` | F2 | 实体消歧、上下文聚合 |
| `/api/extraction` | F5 | TradeAction 提取（legacy 直提路径） |
| `/api/review` | F6 | 复核流程 |
| `/api/rlhf` | F6 | RLHF 反馈 |
| `/api/opinions` | F7 | 观点时间线 |
| `/api/kol` | F7, F8 | KOL 评级 |
| `/api/backtest` | F8 | 回测运行、结果查询、策略对比 |
| `/api/wechat` | F0 | 微信接入 |
| `/api/bilibili` | F0 | B站接入 |
| `/api/system` | — | 系统状态 |

### 5.2 响应格式

```python
# 成功
{"ok": true, "data": {...}}

# 错误
{"ok": false, "error": {"code": "NOT_FOUND", "message": "..."}}
```

### 5.3 关键端点

| 端点 | 方法 | F-stage | 用途 |
|---|---|---|---|
| `/api/files` | GET | F0 | 获取资产列表 |
| `/api/enrichment/split` | POST | F1 | 话题分割 |
| `/api/enrichment/extract` | POST | F2 | 实体抽取 |
| `/api/extraction/extract` | POST | F5 | TradeAction 提取 (legacy) |
| `/api/extraction/pipeline` | POST | F5 | 运行提取流水线 (legacy) |
| `/api/review/save` | POST | F6 | 保存复核结果 |
| `/api/rlhf/submit` | POST | F6 | 提交 RLHF 反馈 |
| `/api/opinions/timeline` | GET | F7 | 观点时间线 |
| `/api/kol/rating/{id}` | GET | F7 | KOL 评级 |
| `/api/backtest/run` | POST | F8 | 运行回测 |
| `/api/backtest/compare` | POST | F8 | 多 KOL 策略对比 |

---

## 6. 前端架构

### 6.1 工作流视图

```typescript
const WORKFLOW_VIEWS: WorkflowView[] = [
  { id: "intake",      stage: "F0", title: "接入台 / INTAKE" },
  { id: "enrichment",  stage: "F1", title: "标准化 / STANDARDIZE" },
  { id: "library",     stage: "F2", title: "锚定台 / ANCHOR" },
  { id: "parsing",     stage: "F1", title: "解析台 / PARSING" },      // legacy
  { id: "extraction",  stage: "F5", title: "执行台 / EXECUTE" },      // legacy 直提路径
  { id: "review",      stage: "F6", title: "复核台 / REVIEW" },
  { id: "backtest",    stage: "F8", title: "回测台 / BACKTEST" },
];
```

> **注意**: 前端 `WORKFLOW_VIEWS` 仍使用旧命名，迁移到 F-stage 命名是后续任务。当前前端视图中 F3(Intent) 和 F4(Policy) 尚未有对应视图。

---

## 7. 外部集成

### 7.1 LLM 服务

| 模型 | 用途 | F-stage |
|---|---|---|
| Qwen-VL-Plus | 图片 OCR、图表分析 | F1 |
| GLM-5.1 (SVIPS) | 文本富化、意图提取、实体识别 | F1, F2, F3 |
| Qwen-Max | 结构化提取 (Instructor) | F3, F5 |
| Qwen-Plus (DashScope) | 降级备用 | All |

### 7.2 Finance-Skills

| 技能 | 用途 | F-stage |
|---|---|---|
| `yfinance-data` | 行情数据 | F8 |
| `funda-data` | 基本面数据 | F2, F8 |
| `sentiment-analysis` | 情绪分析 | F2 |
| `news-aggregator` | 新闻聚合 | F2 |

---

## 8. 配置管理

| 文件 | 内容 | Git |
|---|---|---|
| `.env` | API 密钥 | ignore |
| `configs/*.yaml` | 服务配置（飞书、Finance-Skills） | commit |
| `configs/*.yaml.example` | 配置模板 | commit |
| `src/finer/config.py` | 配置加载器 | commit |

---

## 9. 成熟度状态总表

### 9.1 按 F-stage

| F-stage | 名称 | 状态 | 关键缺口 |
|---|---|---|---|
| F0 | Intake | **implemented** | 微信/B站部分实现 |
| F1 | Standardize | **partial** | 非文本内容 block 化不完整 |
| F2 | Anchor | **partial** | QualityCard 未强制使用，时间解析缺失 |
| **F3** | **Intent** | **partial** | **仅有 rule-based 原型，无 LLM 提取器** |
| **F4** | **Policy** | **missing** | **整个层不存在** |
| F5 | Execute | **partial** | 绕过 F3/F4，缺 intent_id/policy_id |
| F6 | Review | **implemented** | RLHF 链路完整 |
| F7 | Timeline | **partial** | ViewpointState/分歧图谱缺失，mock fallback |
| F8 | Backtest | **partial** | Pipeline placeholder，mock 价格默认 |
| F+ | Training | **contract-only** | 数据量不足，未实际训练 |

### 9.2 按模块

| 模块 | F-stage | 状态 |
|---|---|---|
| `ingestion/feishu_poller.py` | F0 | implemented |
| `ingestion/orchestrator.py` | F0 | partial |
| `ingestion/bilibili_adapter.py` | F0 | partial |
| `ingestion/wechat_adapter.py` | F0 | partial |
| `schemas/content_envelope.py` | F1, F2 | implemented |
| `parsing/content_standardizer.py` | F1 | partial |
| `parsing/vision_extractor.py` | F1 | partial |
| `parsing/audio_extractor.py` | F1 | partial |
| `enrichment/__init__.py` | F2 | partial |
| `enrichment/market_context.py` | F2 | partial |
| `enrichment/sentiment_fusion.py` | F2 | partial |
| `entity_registry.py` | F2 | implemented |
| `schemas/investment_intent.py` | F3 | contract-only |
| `extraction/intent_extractor.py` | F3 | partial (rule-based only) |
| **(F4 Policy 模块不存在)** | F4 | **missing** |
| `schemas/trade_action.py` | F5 | implemented |
| `extraction/trade_action_extractor.py` | F5 | partial (bypasses F3/F4) |
| `api/routes/rlhf.py` | F6 | implemented |
| `api/routes/review.py` | F6 | implemented |
| `api/routes/opinions.py` | F7 | mock-backed |
| `api/routes/kol.py` | F7 | mock-backed |
| `timeline/engine.py` | F7 | partial |
| `backtest/engine.py` | F8 | implemented |
| `api/routes/backtest.py` | F8 | partial (mock prices default) |
| `pipeline/orchestrator.py` | cross-stage | partial (F8 placeholder) |

---

## 10. 已知问题与断点

### 10.1 最严重断点：F3 → F4 → F5 未闭环

**这是当前项目最关键的架构断裂**。

```
当前实际路径（LEGACY — 标记为 deprecated）:
  原始文本 → TradeActionExtractor(LLM) → TradeAction
  跳过: F1 标准化 → F2 锚定 → F3 Intent → F4 Policy

目标路径（CANONICAL）:
  F0 原始内容 → F1 ContentEnvelope → F2 Quality/Temporal/Entity/Evidence
    → F3 NormalizedInvestmentIntent → F4 PolicyMapping
      → F5 TradeAction (+intent_id, +policy_id, +evidence_span_ids)
```

**具体后果**:
1. `api/routes/opinions.py` 返回的"观点"实际是 TradeAction，不是 Intent
2. `api/routes/kol.py` 的 KOL 评级无法归因到具体 KOL（creator_id 为空）
3. `api/routes/backtest.py` 回测的 TradeAction 没有经过 policy 个性化
4. 不同 KOL 对同一标的的观点无法区分仓位和持有期差异

### 10.2 架构问题 (A1-A10)

| # | 问题 | 对应 F-stage | 严重度 |
|---|---|---|---|
| A1 | F1 标准化对非文本内容不完整 | F1 | 🔴 高 |
| A2 | F3 Intent 仅有 rule-based 原型 | F3 | 🔴 高 |
| A3 | TemporalAnchor 四类时间未区分 | F2 | 🔴 高 |
| A4 | creator_id 未稳定填充，KOL 归属断裂 | F0, F5 | 🔴 高 |
| A5 | TradeAction 绕过 F3/F4，证据链弱 | F5 | 🔴 高 |
| A6 | F4 Policy 层完全缺失 | F4 | 🔴 高 |
| A7 | F2 质量卡未强制作为 F3 门控 | F2→F3 | 🟡 中 |
| A8 | F8 pipeline orchestrator 是 placeholder | F8 | 🟡 中 |
| A9 | F7 ViewpointState/分歧图谱缺失 | F7 | 🟡 中 |
| A10 | F+ 训练数据链路未验证 | F+ | 🟡 中 |

### 10.3 版本规划

```
v2.0 (当前)  — F0-F8 canonical 架构文档
v2.1 (2 周)  — F1/F2 schema 强制 + F3 LLM 提取器 + F4 Global Base Policy MVP
v2.2 (4 周)  — F4 完整 5 层 policy + F5 intent_id/policy_id 回填
v2.3 (6 周)  — F7 ViewpointState + 分歧图谱 + F8 pipeline 闭环
v3.0 (8+ 周) — F+ Training Loop: SFT/DPO 训练
```

---

## 11. 部署与运维

### 11.1 启动命令

```bash
# 后端 API
uvicorn finer.api.server:app --reload --port 8000

# 前端 Dashboard
cd src/finer_dashboard && npm run dev

# CLI
python -m finer.cli init-storage
python -m finer.cli feishu-sync
```

### 11.2 数据目录（按 F-stage 组织）

```
data/
├── F0_intake/          ← 原始文件 + ContentRecord
├── F1_standardized/    ← ContentEnvelope + ContentBlock
├── F2_anchored/        ← +QualityCard +TemporalAnchor +EntityAnchor +EvidenceSpan
├── F3_intents/         ← NormalizedInvestmentIntent
├── F4_policy_mapped/   ← PolicyMappingResult (待创建)
├── F5_executed/        ← TradeAction
├── F6_reviewed/        ← Reviewed TradeAction + RLHFFeedback
├── F7_timeline/        ← KOLTimeline + ViewpointState
├── F8_metrics/         ← BacktestResult
├── raw/                ← 原始文件归档
├── rlhf/               ← RLHF 反馈数据
├── cache/              ← 应用缓存
└── processed/          ← manifests, documents, transcripts
```

---

## 12. 开发规范

### 12.1 F-stage 间调用规则

| F-stage | 可调用的下游 | 可调用的公共服务 |
|---|---|---|
| F0 | 无（只写存储） | `services/converter.py` |
| F1 | 无 | `services/llm.py`, `services/perception.py` |
| F2 | F1（只读） | `services/llm.py`, `services/finance_skills_client.py`, `entity_registry.py` |
| F3 | F1, F2（只读） | `services/llm.py` |
| F4 | F3（只读） | 规则引擎 |
| F5 | F4（只读） | `services/llm.py`, `services/finance_skills_client.py` |
| F6 | F3, F5（只读） | `services/` |
| F7 | F3, F5, F6（只读） | `services/repository.py` |
| F8 | F5（只读）+ 价格数据 | `backtest/engine.py`, `backtest/prices.py` |

**禁止**:
- 跨 F-stage 直接调用（如 F5 直接调 F1）
- F5 不经过 F3/F4 直接从原始文本生成 TradeAction
- 在 API route 中写业务逻辑（route 只做参数解析和响应格式化）

### 12.2 代码风格

- Python: PEP 8，完整类型注解，snake_case
- TypeScript: ESLint，camelCase
- Schema 字段: snake_case

### 12.3 Git 约定

- Commit: `type(scope): description`
- Type: feat / fix / refactor / docs / test / chore
- Scope 使用 F-stage: f0 / f1 / f2 / f3 / f4 / f5 / f6 / f7 / f8 / dashboard / schemas / ml

---

## 13. 数据治理

### 13.1 数据生命周期

```
F0 创建 → F1 标准化 → F2 锚定 → F3 意图 → F4 策略 → F5 执行 → F6 复核 → F7 时间线 → F8 回测 → 归档
```

### 13.2 数据血缘

```
F0 ContentRecord.content_id
  → F1 ContentEnvelope.envelope_id
    → F2 EvidenceSpan.evidence_span_id
      → F3 NormalizedInvestmentIntent.intent_id
        → F4 PolicyMappingResult.policy_id
          → F5 TradeAction.trade_action_id (+intent_id, +policy_id, +evidence_span_ids)
            → F6 RLHFFeedback → TradeAction.trade_action_id
              → F7 KOLTimeline → F8 BacktestResult
```

每条数据可沿 ID 链回溯到原始来源。

---

## 14. 非功能性需求

### 14.1 性能

| 指标 | 目标 |
|---|---|
| API 响应时间 (P95) | < 2s (非 LLM) |
| LLM 调用延迟 | < 30s (单次) |
| 文件上传 | 支持 100MB |

### 14.2 可靠性

| 指标 | 实现 |
|---|---|
| LLM 降级 | `model_config.py` 自动 fallback |
| Finance-Skills 降级 | 不可用时跳过市场数据 |
| 数据不丢失 | F0 原始文件永存 |

### 14.3 安全性

| 要求 | 状态 |
|---|---|
| API 密钥不进代码 | ✅ `.env` + `os.environ` |
| 输入校验 | ✅ Pydantic 验证 |
| 文件访问控制 | ❌ 未实现 |

---

## 15. Agent Execution Rules（Agent 执行规则）

以下规则适用于所有开发和检查 Agent。违反任一条即为架构违规，Code Review 必须拒绝。

### 15.1 每个 Agent 必须声明 F-stage

Agent 在开始任务时必须声明自己所处的 F-stage，且只能修改该 stage 的 owning files。

| Agent | F-stage | 可修改文件 |
|---|---|---|
| Intake Agent | F0 | `ingestion/`, `api/routes/files.py`, `schemas/content.py` |
| Standardize Agent | F1 | `parsing/`, `schemas/content_envelope.py` |
| Anchor Agent | F2 | `enrichment/`, `aggregation/`, `entity_registry.py` |
| Intent Agent | F3 | `extraction/intent_extractor.py`, `schemas/investment_intent.py` |
| Policy Agent | F4 | `policy/`, `schemas/policy.py` |
| Execute Agent | F5 | `extraction/trade_action_extractor.py`, `schemas/trade_action.py` |
| Review Agent | F6 | `api/routes/rlhf.py`, `api/routes/review.py` |
| Timeline Agent | F7 | `timeline/`, `api/routes/opinions.py`, `api/routes/kol.py` |
| Backtest Agent | F8 | `backtest/`, `api/routes/backtest.py`, `pipeline/orchestrator.py` |

### 15.2 每个 Agent 必须声明输入输出 Schema

Agent 的输入和输出必须严格对应所属 F-stage 的 Allowed Input 和 Required Output Schema。详见 `docs/specs/f-stage-contracts.md`。

### 15.3 每个 Agent 不得跨 Stage 写业务逻辑

Agent 不得在所属 F-stage 的 owning files 中写入属于其他 F-stage 的业务逻辑:

- F5 Execute Agent 不得在 `trade_action_extractor.py` 中实现 Intent 提取逻辑（那是 F3 的职责）
- F3 Intent Agent 不得在 `intent_extractor.py` 中生成 TradeAction（那是 F5 的职责）
- F4 Policy Agent 不得修改 Intent 的 direction（除非有 audit log）

### 15.4 检查 Agent 必须验证是否绕过 F3/F4

Code Review 和 CI 检查必须包含以下验证:

1. F5 的 TradeAction 是否包含非空 intent_id（未绕过 F3）
2. F5 的 TradeAction 是否包含非空 policy_id（未绕过 F4）
3. 是否存在直接调用 `extract_from_text()` 而不经过 F3->F4 的代码路径
4. F3 输出中是否包含 position_size_pct / target_price / trigger_condition（违规）
5. F4 输出中是否修改了 F3 的 direction 而没有 audit log

### 15.5 禁止跨 Stage 直接调用

| F-stage | 可调用的下游 | 可调用的公共服务 |
|---|---|---|
| F0 | 无（只写存储） | `services/converter.py` |
| F1 | 无 | `services/llm.py`, `services/perception.py` |
| F2 | F1（只读） | `services/llm.py`, `services/finance_skills_client.py`, `entity_registry.py` |
| F3 | F1, F2（只读） | `services/llm.py` |
| F4 | F3（只读） | 规则引擎 |
| F5 | F4（只读） | `services/llm.py`, `services/finance_skills_client.py` |
| F6 | F3, F5（只读） | `services/` |
| F7 | F3, F5, F6（只读） | `services/repository.py` |
| F8 | F5（只读）+ 价格数据 | `backtest/engine.py`, `backtest/prices.py` |

**禁止**: 跨 F-stage 直接调用（如 F5 直接调 F1）。F5 不经过 F3/F4 直接从原始文本生成 TradeAction 属于架构违规。

---

## 16. Legacy Mapping（旧命名对照）

> **重要**: 旧命名 L0-L8 和 V0-V6 **仅供迁移参考**，不再作为主架构描述。所有新代码、文档、commit message 必须使用 F0-F8。

### 15.1 L0-L8 → F0-F8

| 旧 L 层 | 旧名称 | → | 新 F-stage | 新名称 | 说明 |
|---|---|---|---|---|---|
| L0 | 接入层 | → | **F0** | Intake | 职责相同 |
| L1 | 富化层 | → | **F2** | Anchor | 重新定位为锚定（质量+时间+实体） |
| L2 | 标准化层 | → | **F1** | Standardize | 重新定位为内容标准化 |
| L3 | 解析层 | → | **F1** | Standardize | OCR/ASR 归入标准化 |
| L4 | 聚合层 | → | **F2** | Anchor | 实体消歧/上下文聚合归入锚定 |
| L5 | 抽取层 | → | **F5** | Execute | TradeAction 抽取 → 执行层 |
| L6 | 复核层 | → | **F6** | Review | 职责相同 |
| L7 | 时间线层 | → | **F7** | Timeline | 职责相同，需升级为 ViewpointState |
| L8 | 回测层 | → | **F8** | Backtest | 职责相同 |

### 15.2 V0-V6 → F0-F8

| 旧 V 层 | 旧名称 | → | 新 F-stage | 新名称 | 说明 |
|---|---|---|---|---|---|
| S0 | Raw Source | → | **F0** | Intake | 职责相同 |
| V0 | Content Standardization | → | **F1** | Standardize | 职责相同 |
| V0.5 | Quality/Temporal/Entity | → | **F2** | Anchor | 职责相同 |
| V1 | Investment Intent | → | **F3** | Intent | 职责相同 |
| V2 | Policy Mapping | → | **F4** | Policy | 职责相同 |
| V3 | TradeAction | → | **F5** | Execute | 职责相同 |
| V4 | Timeline/Viewpoint | → | **F7** | Timeline | 职责相同（注意 F6 Review 在中间） |
| V5 | Backtest/Evaluation | → | **F8** | Backtest | 职责相同 |
| V6 | Training Loop | → | **F+** | Training | 非独立 F-stage |

### 15.3 数据目录迁移

| 旧目录 | → | 新目录 |
|---|---|---|
| `data/L0_ingest/` | → | `data/F0_intake/` |
| `data/L1_enrichment/` + `data/L2_standardized/` | → | `data/F1_standardized/` |
| `data/L3_aligned/` + `data/L4_parsed/` | → | `data/F2_anchored/` |
| `data/L5_candidate/` | → | `data/F3_intents/` + `data/F5_executed/` |
| `data/L6_annotated/` | → | `data/F6_reviewed/` |
| `data/L7_model_results/` | → | `data/F7_timeline/` |
| `data/L8_metrics/` | → | `data/F8_metrics/` |

### 15.4 文件路径对照

| 旧文件 | F-stage | 说明 |
|---|---|---|
| `ingestion/feishu_poller.py` | F0 | 不变 |
| `parsing/content_standardizer.py` | F1 | 不变 |
| `parsing/vision_extractor.py` | F1 | 不变 |
| `schemas/content_envelope.py` | F1, F2 | 不变 |
| `enrichment/__init__.py` | F2 | 不变 |
| `enrichment/market_context.py` | F2 | 不变 |
| `extraction/intent_extractor.py` | F3 | 需升级为 LLM-based |
| **(新文件)** `policy/policy_mapper.py` | F4 | **待创建** |
| **(新文件)** `schemas/policy.py` | F4 | **待创建** |
| `extraction/trade_action_extractor.py` | F5 | 需增加 intent_id/policy_id |
| `schemas/trade_action.py` | F5 | 需增加 intent_id/policy_id/evidence_span_ids |
| `api/routes/rlhf.py` | F6 | 不变 |
| `timeline/engine.py` | F7 | 需增加 ViewpointState |
| `backtest/engine.py` | F8 | 不变 |
| `pipeline/orchestrator.py` | cross-stage | 需重写为 F0-F8 流程，修复 F8 placeholder |

---

*文档版本: 2.0.0 | 最后更新: 2026-04-28 | Canonical pipeline: F0-F8 | Legacy L/V naming: deprecated*
