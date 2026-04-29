# MiMo Orbit Application Note

> This document is written for the Xiaomi MiMo 100T / MiMo Orbit application review. It explains what Finer OS builds, why it is token-intensive, and where MiMo models can be used.

## Project Link

GitHub: <https://github.com/kelipovanatalja453-bot/finer>

## Short Description

Finer OS is an AI-native research pipeline that turns noisy financial KOL timelines into evidence-linked investment intents, reviewable trade actions, and backtestable KOL performance. It handles chat logs, image-based strategy posts, Feishu docs, PDFs, and audio/video transcripts, then standardizes them into `ContentEnvelope` / `ContentBlock`, extracts `NormalizedInvestmentIntent`, and prepares downstream policy mapping, timeline analysis, and backtesting.

## Form Answer Draft: AI / Agent Outcome

> 可直接复制到 MiMo Orbit 表单第 04 项，长度控制在 1200 字以内。

我正在构建 Finer OS：一个面向财经 KOL 的 Agent 驱动投研自动化系统。它解决的核心痛点是：KOL 的投资观点通常分散在聊天记录、截图策略、飞书文档、PDF、直播转录稿等非标准内容里，而且同一句话可能同时包含观点、动作、时间和风险。例如“腾讯大跌后我继续持有并小幅加仓”不能只做情绪分类，而要拆成标的、方向、可操作性、仓位变化暗示、信念强度、时间锚点和原文证据，后续才能进入回测。

目前项目已实现 F1/F2/F3 语义基础：F1 将多源内容标准化为 ContentEnvelope/ContentBlock；F2 加入 QualityCard、TemporalAnchor、EntityAnchor、EvidenceSpan；F3 抽取 NormalizedInvestmentIntent，区分”看好”和”加仓”等不同投资语义。项目也采用多 Agent 工作流拆分架构规划、schema 合约、质量门控、fixture 构建、图片策略验证和独立验收。公开仓库中已包含架构文档、执行报告、猫大人聊天/图片策略样本、F1/F3 测试与验证结果。

MiMo Token 将主要用于 OCR/图片策略理解、长聊天清洗、音频转录稿切分、相对时间解析、跨文档观点串联、F3 intent 抽取和 SFT/DPO 数据生成。目标是建立一套可复现的流程，用证据链和模拟跟单收益评估 KOL，而不是依赖主观印象。

## Core Pain Points Solved

1. **Noisy multimodal KOL content**

   KOLs do not publish in a clean research-report format. Inputs include screenshots, tables, charts, long chats, OCR artifacts, PDFs, and transcribed livestreams. Finer normalizes those inputs into a common F1 ContentEnvelope schema.

2. **Opinion is not the same as action**

   “I am bullish on CATL” and “I added CATL” are both positive, but they imply different investment actions. Finer separates `direction`, `actionability`, `position_delta_hint`, and `conviction`.

3. **Time references are ambiguous**

   KOL posts often contain relative time such as “last week”, “Q4”, or “after earnings”. Finer has a dedicated `TemporalAnchor` layer for published time, mentioned time, resolved time, and effective trade time.

4. **Backtesting requires traceability**

   A backtest result is only useful if every generated intent and action can be traced to source text. Finer uses `EvidenceSpan` and fixture-level tests to preserve that audit path.

5. **Different KOLs have different policy styles**

   The target architecture supports a layered policy stack: global baseline, style archetype, risk preference, and KOL-specific correction.

## Why This Needs Large Token Budgets

Finer is not a single prompt extraction project. It needs repeated high-context model calls across a full pipeline:

- OCR and chart/table interpretation for image strategies.
- Long-chat segmentation and thread recovery.
- Financial entity extraction and disambiguation.
- Temporal resolution from natural language.
- F3 intent extraction with evidence spans.
- Cross-document viewpoint state maintenance.
- Multi-KOL disagreement analysis.
- Human review, SFT sample generation, and DPO preference pair export.

As the number of KOLs grows from tens to hundreds, the workload becomes naturally token-intensive because each KOL requires historical persona/policy analysis plus per-post extraction and validation.

## Where MiMo Can Be Integrated

| F-stage | MiMo Usage |
|---|---|
| F1 Standardize | Normalize OCR, chat logs, PDFs, and transcripts into clean ContentBlocks |
| F2 Anchor | Extract time references, entities, evidence spans, and quality/ambiguity flags |
| F3 Intent | Generate structured `NormalizedInvestmentIntent` with confidence and rationale |
| F4 Policy | Infer KOL style, risk preference, and personalized mapping assumptions |
| F6 Review | Explain why an intent/action was produced and support human correction |
| F+ Training | Generate SFT/DPO data from corrected examples and backtest feedback |

## Evidence in the Repository

- `docs/ARCHITECTURE.md`: target architecture (F0-F8) and current implementation status.
- `docs/specs/f-stage-contracts.md`: F0-F8 stage contracts and schema definitions.
- `docs/architecture-alignment-plan.md`: F0-F8 architecture alignment plan.
- `docs/v0-v1-schema-contract-validation-report.md`: validation report for schema contracts and fixtures (historical).
- `src/finer/schemas/content_envelope.py`: F1 content envelope and content block schema.
- `src/finer/schemas/investment_intent.py`: F3 normalized investment intent schema.
- `src/finer/parsing/content_standardizer.py`: F1 standardizer.
- `src/finer/extraction/intent_extractor.py`: F3 intent extractor.
- `tests/fixtures/kol/`: KOL fixture cases for chat/document and image-strategy samples.
- `tests/test_cat_lord_image_v0_pipeline.py`: image strategy F1 pipeline validation.

## Current Validation Status

Latest public-release validation:

```text
597 passed, 21 skipped
```

The skipped tests are async tests that require a dedicated pytest async runtime configuration. They are tracked as an engineering follow-up and are not related to the F1/F3 schema and fixture contract.

## Next Milestones

1. Integrate MiMo into F1 standardization and F3 intent extraction as a selectable model backend.
2. Add long-context KOL persona / policy generation for 200-1000 historical posts per KOL.
3. Build F4 policy mapping from intent to executable `TradeAction`.
4. Add `ViewpointState` for same-KOL same-target opinion evolution.
5. Add multi-KOL target opinion graph for consensus and disagreement.
6. Export corrected samples into SFT/DPO datasets.

## One-Sentence Pitch

Finer OS uses Agent workflows and structured schemas to turn messy financial KOL timelines into auditable investment intents and backtestable performance, making it an ideal real-world benchmark and high-token application scenario for MiMo models.
