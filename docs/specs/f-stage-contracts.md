# F-Stage Contracts -- 每阶段可执行契约

> 版本: 2.1.0 | 创建: 2026-04-28 | 更新: 2026-04-30
> 状态: **F0-F8 是 Finer OS 唯一主架构。** 旧命名 L0-L8 和 V0-V6 已废弃（deprecated），仅在下文 [Legacy Mapping](#legacy-mapping) 章节和 `docs/ARCHITECTURE.md` 第 15 节保留供迁移参考。
> 用途: 定义每个 F-stage 的精确输入/输出/Schema/禁止职责/验收清单。作为 Agent 任务边界、Code Review 和 CI 检查的权威参考。

---

## 使用说明

每个 F-stage 条目包含以下必填字段：

| 字段 | 含义 |
|---|---|
| **Purpose** | 本阶段要解决的唯一问题 |
| **Maturity Status** | `production` / `beta` / `alpha` / `placeholder` |
| **Allowed Input** | 法律上允许进入本阶段的 Schema 实例 |
| **Required Output** | 本阶段必须产出的 Schema 实例 |
| **Owning Files** | 本阶段代码的权威文件列表 |
| **Forbidden Responsibilities** | Agent 和代码绝不能在本阶段执行的操作 |
| **Acceptance Checklist** | Agent 完成任务后必须通过的检查项 |

### 成熟度定义

| 状态 | 含义 | 判断标准 |
|---|---|---|
| **production** | 端到端生产可用 | 输入->存储->API->前端->测试全链路打通 |
| **beta** | 核心逻辑存在但有关键缺口 | 可用但不完整（缺上游输入、缺下游消费、测试不覆盖） |
| **alpha** | 原型/实验阶段 | 功能存在但不可靠（rule-based only、mock fallback、无 LLM） |
| **placeholder** | 占位/缺失 | 函数/方法存在但空操作，或完全不存在对应模块 |

---

## F0: Intake（接入）

- **Purpose**: 多源数据接入，原始内容原样存档，不做任何语义处理。
- **Maturity Status**: `production`（飞书），`beta`（B站/微信）
- **Allowed Input**: 飞书群聊消息、B站视频、微信公众号文章、手动上传文件、NotebookLM 笔记
- **Required Output**: `ContentRecord` + 原始文件归档到 `data/F0_intake/` 和 `data/raw/`

### 输出 Schema

```python
ContentRecord(
    content_id: str,           # UUID
    source_type: str,          # feishu_chat | bilibili_video | wechat_article | manual_upload | nlm_note
    source_platform: str,      # 飞书 | B站 | 微信 | 本地 | NotebookLM
    creator_id: Optional[str], # KOL 标识（如果能确定）
    creator_name: Optional[str],
    published_at: Optional[datetime],
    collected_at: datetime,
    title: Optional[str],
    raw_path: str,             # 原始文件路径
    file_type: str,            # chat_log | image | pdf | doc | audio | video | text
    metadata: dict,
)
```

### Owning Files

- `ingestion/feishu_poller.py`
- `ingestion/orchestrator.py`
- `ingestion/bilibili_adapter.py`
- `ingestion/wechat_adapter.py`
- `ingestion/wechat_exporter_client.py`
- `ingestion/nlm_sync.py`
- `ingestion/classifier.py`
- `api/routes/files.py`
- `schemas/content.py`

### Forbidden Responsibilities

- 不做 OCR/ASR/文本解析
- 不做话题拆分或实体抽取
- 不做任何 LLM 调用
- 不做内容质量判断
- 不修改原始文件内容

### Acceptance Checklist

- [ ] 飞书消息可成功轮询并下载附件
- [ ] ContentRecord 持久化到 `data/F0_intake/`
- [ ] 原始文件完整归档到 `data/raw/`
- [ ] creator_id 在飞书接入时从群配置填充
- [ ] 文件去重检查（content_id 唯一性）

---

## F1: Standardize（标准化）

- **Purpose**: 将 F0 原始内容标准化为唯一 canonical `ContentEnvelope` + ordered `ContentBlock[]`，解决结构边界、提取质量、来源追溯问题。
- **Maturity Status**: `alpha`（契约重置中；旧 V0/L3/SegmentRecord 路径待迁移）
- **Allowed Input**: F0 `ContentRecord` + F0 原始文件（飞书聊天 markdown、图片、PDF/文档、微信文章；音频转录预留）
- **Required Output**: `ContentEnvelope` 包含 canonical `ContentBlock[]`。详见 `docs/specs/f1-standardization-contract.md`。

### 输出 Schema 摘要

```python
ContentEnvelope(
    envelope_id: str,
    source_record_id: str,       # -> F0 ContentRecord.content_id
    source_type: Literal[
        "feishu_chat", "feishu_doc", "wechat_article", "image",
        "pdf", "audio_transcript", "video_transcript", "manual_text",
    ],
    creator_id: Optional[str],
    creator_name: Optional[str],
    title: Optional[str],
    published_at: Optional[datetime],
    collected_at: Optional[datetime],
    source_uri: Optional[str],
    raw_path: Optional[str],
    blocks: List[ContentBlock],
    standardization_profile: str,
    metadata: dict,
)

ContentBlock(
    block_id: str,
    envelope_id: str,
    block_type: Literal[
        "chat_message", "paragraph", "section_title", "image_text",
        "table_region", "chart_region", "audio_segment", "video_segment",
        "quote", "link_reference", "attachment_ref", "ocr_unreadable",
        "system_event",
    ],
    text: str,
    order_index: int,
    speaker: Optional[str],
    timestamp: Optional[datetime],
    page_index: Optional[int],
    bbox: Optional[BoundingBox],
    start_time_sec: Optional[float],
    end_time_sec: Optional[float],
    parent_block_id: Optional[str],
    thread_id: Optional[str],
    quality: BlockQuality,
    provenance: BlockProvenance,
    metadata: dict,
)
```

### F1 标准化质量

F1 的质量评估是 **standardization quality**，不是 F2 的投资相关性或实体锚定质量。

```python
BlockQuality(
    readability: float,
    extraction_confidence: float,
    structural_confidence: float,
    completeness: float,
    noise_score: float,
    quality_flags: List[str],
)
```

评分必须优先由确定性特征计算：乱码比例、HTML 残留、parser 命中、timestamp/speaker 解析、OCR/ASR 原始置信度、layout/bbox 完整度、空转发/缺附件/系统消息识别等。LLM 可辅助图片图表描述，但不能作为唯一质量评分来源。

### Owning Files

- `schemas/content_envelope.py`
- `parsing/content_standardizer.py`
- `parsing/vision_extractor.py`
- `parsing/standardization_quality_scorer.py`（待创建）
- `parsing/feishu_chat_markdown_standardizer.py`（待创建或并入 `content_standardizer.py`）
- `parsing/image_ocr_layout_standardizer.py`（待创建或并入 `vision_extractor.py`）
- `parsing/audio_extractor.py`（音频预留；本轮不实现 canonical adapter）
- `docs/specs/f1-standardization-contract.md`

### Forbidden Responsibilities

- 不做 topic assembly（F1.5）
- 不做投资意图判断（F3）
- 不生成 `NormalizedInvestmentIntent`
- 不生成 `TradeAction`
- 不解析 canonical `EntityAnchor` ID（F2）
- 不静默丢弃低质量或噪声块，只能标记质量和噪声

### Acceptance Checklist

- [ ] 飞书聊天 markdown -> `chat_message` / `attachment_ref` / `system_event`
- [ ] 飞书聊天 block 保留 `speaker`、`timestamp`、`message_type`、Q/A 格式标记
- [ ] 图片 OCR/layout -> `section_title` / `image_text` / `table_region` / `chart_region` / `ocr_unreadable`
- [ ] 图片 block 在 layout 可用时保留 `bbox`
- [ ] 所有 block 有 deterministic `BlockQuality`
- [ ] 所有 block 有 `BlockProvenance`
- [ ] 音频 `audio_segment` 在契约中保留，但本轮实现不强制
- [ ] 旧 `SegmentRecord` 不再作为 F1 canonical output，只能作为迁移输入

---

## F1.5: Topic Assembly（主题组装）

- **Purpose**: 将 F1 已标准化的 `ContentBlock[]` 组装成按标的、行业、宏观、投资哲学等语义主题划分的 `TopicBlock[]`。F1.5 只处理语义边界，不再解析 markdown header、OCR 布局、HTML 或 ASR 结构。
- **Maturity Status**: `alpha`（`TopicBlock` schema、规则 baseline、Cat Lord golden fixture、LLM constrained adapter 已存在；canonical pipeline 集成未完成）
- **Allowed Input**: F1 `ContentEnvelope` + `ContentBlock[]`
- **Required Output**: `TopicAssemblyResult` + `TopicBlock[]`

### 输出 Schema

```python
TopicBlock(
    topic_block_id: str,
    envelope_id: str,
    source_block_ids: List[str],     # -> F1 ContentBlock.block_id

    topic_title: str,
    topic_type: Literal[
        "single_stock", "industry", "macro_policy",
        "market_commentary", "investment_philosophy",
        "portfolio_update", "news_forward", "other"
    ],

    primary_entity_ids: List[str],   # current schema; should migrate to entity mentions/hints before F2
    secondary_entity_ids: List[str], # current schema; should migrate to entity mentions/hints before F2

    start_block_index: int,
    end_block_index: int,
    start_time: Optional[datetime],
    end_time: Optional[datetime],

    summary: str,
    raw_text: str,
    segmentation_reason: str,
    confidence: float,
    ambiguity_flags: List[str],
)

TopicAssemblyResult(
    assembly_id: str,
    envelope_id: str,
    topic_blocks: List[TopicBlock],
    unassigned_block_ids: List[str],
    assembly_strategy: str,
    created_at: datetime,
)
```

### Owning Files

- `schemas/topic_block.py`
- `parsing/topic_assembler.py`
- `parsing/llm_topic_assembly_adapter.py`
- `tests/fixtures/kol/cat_lord_topic_assembly_input.json`
- `tests/fixtures/kol/cat_lord_topic_assembly_expected.json`

### Forbidden Responsibilities

- 不抽取投资意图（F3）
- 不生成 TradeAction（F5）
- 不做交易判断或仓位判断
- 不丢弃原始 ContentBlock
- 不修改原始文本证据，只通过 `source_block_ids` 引用
- 不替代 F2 的实体、时间、质量、证据锚定
- 不解析 F1 原始格式细节（markdown heading、HTML wrapper、OCR bbox、ASR timestamp）

### Architecture Decision

- 规则版 `TopicAssembler` 只作为 fast path / fallback / regression baseline。
- 主方向是 constrained LLM topic proposal + deterministic validator：LLM 只能返回 existing `source_block_ids` 分组和 topic 元信息，系统端重建 `raw_text` 并校验 missing/fabricated/duplicated block IDs。
- 运行时不得自动把 LLM 发现的新 topic 写入生产规则库。规则库更新必须通过离线候选、回归测试和人工/CI 准入。
- F1.5 位于 F2 之前，不应长期输出正式 `EntityAnchor` ID。后续 schema 应迁移到 `primary_entity_mentions` / `entity_resolution_hints`，由 F2 解析为 canonical anchors。

### Acceptance Checklist

- [ ] 猫大人长聊天 fixture 可拆出泡泡玛特、新能源、巴菲特股东信、老铺黄金、卫星化学等独立 TopicBlock
- [ ] 每个 TopicBlock 至少包含 1 个 `source_block_id`
- [ ] TopicBlock 的 `raw_text` 由 source blocks 拼接得到，不凭空生成
- [ ] `start_block_index` / `end_block_index` 与 source block 顺序一致
- [ ] 无法归类的 block 进入 `unassigned_block_ids`
- [ ] TopicBlock 不输出 direction / actionability / position_delta_hint / TradeAction
- [ ] 非连续但语义连续的 source blocks 允许合并，并通过 `ambiguity_flags=["non_contiguous_blocks"]` 标记

---

## F2: Anchor（锚定）

- **Purpose**: 对 F1.5 TopicBlock（或无主题组装时的 F1 ContentBlock）进行质量评估、时间锚定、实体锚定、证据链建立。决定哪些内容可以进入 F3。
- **Maturity Status**: `beta`
- **Allowed Input**: F1 `ContentEnvelope` + F1.5 `TopicBlock[]`
- **Required Output**: F1/F1.5 完整结构 + `QualityCard`（6 维）+ `TemporalAnchor[]`（4 类时间）+ `EntityAnchor[]` + `EvidenceSpan[]`

### 输出 Schema

F1 完整结构 + 以下附加字段:

```python
# 附加到 ContentEnvelope:
quality_card: QualityCard       # 6 维质量评估
temporal_anchors: List[TemporalAnchor]  # 4 类时间锚
entity_anchors: List[EntityAnchor]      # 实体锚

# 附加到 ContentBlock:
evidence_span: Optional[EvidenceSpan]   # 证据定位
quality_card: QualityCard               # block 级质量

QualityCard(
    readability: float,              # 0-1, 文本可读性
    semantic_completeness: float,    # 0-1, 语义完整性
    financial_relevance: float,      # 0-1, 金融相关性
    entity_resolution: float,        # 0-1, 实体可解析度
    temporal_resolution: float,      # 0-1, 时间可解析度
    evidence_traceability: float,    # 0-1, 证据可追溯度
    gate: Literal["pass", "soft_pass", "review", "reject"],
    warnings: List[str],
)

TemporalAnchor(
    anchor_id: str,
    text_span: str,                  # 原文片段
    anchor_type: Literal["published", "mentioned", "resolved", "effective_trade"],
    resolved_start: Optional[datetime],
    resolved_end: Optional[datetime],
    confidence: float,               # 0-1
    resolution_rule: Optional[str],  # 解析规则说明
    needs_review: bool,
)

EntityAnchor(
    anchor_id: str,
    raw_text: str,                   # 原文中出现的名称
    resolved_name: Optional[str],    # 标准化公司名
    resolved_symbol: Optional[str],  # 标准化 ticker
    entity_type: Literal["stock", "sector", "index", "crypto", "fund", "commodity"],
    market: Optional[str],           # US/HK/CN/CRYPTO
    confidence: float,
    needs_review: bool,
)

EvidenceSpan(
    evidence_span_id: str,
    block_id: str,                   # -> F1 ContentBlock.block_id
    char_start: int,
    char_end: int,
    text: str,                       # 截取的原文证据
    confidence: float,
    span_type: str,                  # intent_keyword | entity_mention | time_mention | action_trigger
)
```

### Owning Files

- `schemas/content_envelope.py` -- QualityCard, TemporalAnchor (schema)
- `schemas/evidence.py` -- EvidenceSpan
- `enrichment/__init__.py` -- TopicSplitter, EntityExtractor
- `enrichment/market_context.py` -- MarketContextEnricher
- `enrichment/sentiment_fusion.py` -- SentimentFusionEnricher
- `entity_registry.py` -- 统一实体注册表
- `aggregation/__init__.py` -- EntityLinker, ContextAggregator

### Forbidden Responsibilities

- 不做投资意图提取（F3）
- 不做交易动作生成（F5）
- 不做 policy 映射（F4）
- 不丢弃 gate=reject 的内容（存档但标记）

### Acceptance Checklist

- [ ] 每个 ContentEnvelope 有 QualityCard
- [ ] QualityCard 6 维均有值（非默认 0）
- [ ] 相对时间（"上周/这周/下个月"）能解析为绝对日期范围
- [ ] 同一内容中多个时间表达分别落 TemporalAnchor
- [ ] EntityAnchor 使用 entity_registry.py 标准化股票/行业名
- [ ] 无法解析的实体标记 needs_review=True
- [ ] EvidenceSpan 精确指向 block 内的 char_start/char_end
- [ ] gate=reject 的 envelope 不进入 F3

---

## F3: Intent（意图）

- **Purpose**: 从质量过关的内容中提取标准化投资意图。F3 只回答"这个 KOL 表达了什么观点/动作暗示"，不回答"应该怎么交易"。
- **Maturity Status**: `alpha`（仅有 rule-based 原型，无 LLM 提取器）
- **Allowed Input**: F2 `ContentEnvelope`（gate >= soft_pass）
- **Required Output**: `NormalizedInvestmentIntent[]`

> **CRITICAL BOUNDARY: F3 MUST NOT generate TradeAction.**
> F3 的职责止于意图表达。仓位比例、目标价格、止损止盈、触发条件等交易参数一律不得在 F3 出现。

### 输出 Schema

```python
NormalizedInvestmentIntent(
    intent_id: str,
    envelope_id: str,            # -> F1 ContentEnvelope
    block_ids: List[str],        # -> F1 ContentBlock (证据来源块)
    creator_id: Optional[str],   # KOL ID
    target_type: str,            # stock | sector | index | crypto
    target_name: str,            # 目标名称
    target_symbol: Optional[str],# 标准化 ticker
    market: Optional[str],       # US/HK/CN/CRYPTO
    direction: Literal["bullish", "bearish", "neutral", "watchlist", "risk_warning"],
    actionability: Literal["opinion", "watch", "explicit_action"],
    position_delta_hint: Literal["open", "add", "reduce", "hold", "exit", "none"],
    conviction: float,           # 0.0-1.0 信念强度
    confidence: float,           # 0.0-1.0 提取置信度
    evidence_span_ids: List[str],# -> F2 EvidenceSpan
    ambiguity_flags: List[str],  # unknown_target | mixed_signal | vague_time | etc.
    sentiment_score: Optional[float],
    time_horizon: Optional[str], # intraday | short_term | swing | medium_term | long_term
    processing_notes: List[str],
    metadata: dict,
)

IntentExtractionResult(          # 批量容器
    envelope_id: str,
    intents: List[NormalizedInvestmentIntent],
    evidence_spans: List[EvidenceSpan],
    extraction_timestamp: datetime,
    extractor_version: str,      # 提取器版本标识
    processing_notes: List[str],
)
```

### 四轴定义

| 轴 | 含义 | 可选值 |
|---|---|---|
| `direction` | 多空方向 | bullish / bearish / neutral / watchlist / risk_warning |
| `actionability` | 可操作程度 | opinion / watch / explicit_action |
| `position_delta_hint` | 仓位变化提示 | open / add / reduce / hold / exit / none |
| `conviction` | 信念强度 | 0.0--1.0 float |

### Owning Files

- `schemas/investment_intent.py` -- Schema + validators
- `extraction/intent_extractor.py` -- 提取器实现

### Forbidden Responsibilities

- 不生成仓位比例（position_size_pct）
- 不生成目标价格（target_price_low, target_price_high）
- 不生成触发条件（trigger_condition）
- 不生成止损止盈
- **F3 MUST NOT generate TradeAction**（交易动作是 F5 的职责）
- 不做交易执行映射
- 不丢弃模糊样本（标注 ambiguity_flags 但不丢弃）

### Acceptance Checklist

- [ ] "我看好宁德时代" -> actionability=opinion, position_delta_hint=none
- [ ] "我加仓宁德时代" -> actionability=explicit_action, position_delta_hint=add
- [ ] "目前持有，稍微加仓一点" -> direction=bullish, position_delta_hint=add, conviction < 0.8
- [ ] "清仓宁德时代" -> actionability=explicit_action, position_delta_hint=exit
- [ ] "关注一下腾讯" -> direction=neutral/watch, actionability=watch
- [ ] 每个 Intent 至少有 1 个 evidence_span_id
- [ ] 模糊样本保留 ambiguity_flags（如 unknown_target）
- [ ] 提取器不输出 position_size_pct / target_price / trigger_condition
- [ ] "看好"和"加仓"产生不同的 actionability
- [ ] direction 和 conviction 独立，不因"强烈看好"自动变成 explicit_action

---

## F4: Policy（策略映射）

- **Purpose**: 根据策略规则，将 F3 的抽象 Intent 映射为动作/仓位/持仓期 hint。F4 输出 hint，不输出 TradeAction。**F4 是 Intent -> 策略 hint 的唯一合法层。**
- **Maturity Status**: `beta`（GlobalBasePolicy + PolicyMapper 已实现，StyleArchetype/KOLPersona 策略层待补）
- **Allowed Input**: F3 `NormalizedInvestmentIntent[]`
- **Required Output**: `PolicyMappingResult[]`（Intent + 动作 hint + 仓位 hint + 持仓期 hint + 风险约束，不生成 TradeAction）

> **CRITICAL BOUNDARY: F4 is the only legal Intent-to-TradeAction policy mapping layer.**
> 任何绕过 F4 直接从 Intent 或原始文本生成 TradeAction 的路径，均为 legacy/deprecated。同一句"加仓"在不同 KOL 风格下应产生不同的仓位/持仓期/动作强度。

### 输出 Schema

```python
PolicyMappingResult(
    policy_id: str,              # UUID，唯一标识
    intent_id: str,              # -> F3 NormalizedInvestmentIntent
    creator_id: Optional[str],   # 内容创作者 / KOL 标识
    kol_id: Optional[str],       # creator_id 的别名，至少设一个
    policy_version: str,         # 使用的 policy 版本（如 "global-base-v1"）
    policy_layers_applied: List[str],  # ["GlobalBase", "StyleArchetype", "KOLPersona"]

    # F4 生成的动作/仓位/持仓期 hint（是 hint，不是成交事实）
    action_hint: Literal["watch_only", "consider_buy", "consider_sell",
                         "review_required", "no_action"],
    position_sizing_hint: Literal["none", "small", "medium", "large"],
    holding_period_hint: Literal["intraday", "short_term", "medium_term",
                                  "long_term", "review_required"],

    # 风险约束
    risk_constraints: PolicyRiskConstraints,

    # 审计
    mapping_rationale: str,      # 映射理由（human-readable）
)
```

> **注意**：PolicyMappingResult **不复制** F3 的 `direction` / `target_name` / `target_symbol` / `conviction` 字段，而是通过 `intent_id` 引用上游 Intent。这是有意设计：F4 只有权写 hint，不能修改 F3 的方向或目标信息，避免策略层无意中改变信号语义。

# Policy Context (输入到 F4)
PolicyContext(
    kol_id: str,                       # KOL 标识
    style_archetype: str,              # 短线/景气/价值/烟蒂/混合
    risk_preference: str,              # 激进/均衡/保守
    persona_summary: Optional[str],    # 从历史内容总结的 persona
)
```

### Policy 5 层结构

```
Global Base Policy          -> 通用语言->动作基准映射
  Style Archetype Policy    -> 短线/景气/价值/烟蒂风格差异
    Risk Preference Policy  -> 激进/均衡/保守
      KOL Persona Policy    -> 个体 KOL 语言习惯修正
        Content Correction   -> 当前上下文临时修正
```

### Owning Files

- `schemas/policy.py` — PolicyMappingResult, PolicyMappedIntent, PolicyLayerTrace 等（670 行）
- `policy/__init__.py` — F4 模块入口
- `policy/policy_mapper.py` — PolicyMapper: 无状态 mapper，F3 Intents → F4 PolicyMappedIntent[]
- `policy/global_base.py` — GlobalBasePolicy: 规则引擎（第 1 层已实现）
- **(待创建)** `policy/style_archetypes.py` — 第 2 层：Style Archetype Policy
- **(待创建)** `policy/risk_preferences.py` — 第 3 层：Risk Preference Policy
- **(待创建)** `policy/kol_persona.py` — 第 4 层：KOL Persona Policy

### Forbidden Responsibilities

- 不生成新的 Intent（Intent 只能来自 F3）
- 不修改 Intent 的 direction（除非有 audit log）
- 不覆盖 conviction 而不记录理由
- 不直接生成 TradeAction（那是 F5 的职责）
- `position_sizing_hint` 必须是 hint，不得作为成交事实写入 TradeAction

### Acceptance Checklist

- [ ] 同一句"加仓"在"短线风格"下 -> position_sizing_hint 较小, max_holding_days 较短
- [ ] 同一句"加仓"在"价值风格"下 -> position_sizing_hint 较大, max_holding_days 较长
- [ ] 同一句"加仓"在"激进偏好"下 -> stop_loss_pct 较小（容忍更大回撤）
- [ ] 每个 PolicyMappingResult 包含 mapping_rationale
- [ ] Global Base Policy 覆盖所有常见 actionability 类型
- [ ] F3 的 position_delta_hint=none 时 F4 不生成仓位
- [ ] policy_version 可追溯
- [ ] **任何绕过 F4 直接生成 TradeAction 的路径被标记为 deprecated**

---

## F5: Execute（交易执行）

- **Purpose**: 从 F4 PolicyMappedIntent 生成可执行、可回测、可审计的 TradeAction。
- **Maturity Status**: `beta`（schema 完整，但当前实际路径绕过 F3/F4）
- **Allowed Input**: F4 `PolicyMappingResult[]`（canonical）；legacy 路径接受原始文本（已弃用，仅用于对照实验）
- **Required Output**: `TradeAction[]`，每条 **必须** 包含 `intent_id`, `policy_id`, `evidence_span_ids`, `execution_timing`

> **CRITICAL BOUNDARY: F5 canonical TradeAction MUST include intent_id, policy_id, evidence_span_ids, execution_timing.**
> 前三个字段是 TradeAction 证据链可审计性的必要条件，`execution_timing` 是交易时间可复现和防未来函数的必要条件。`canonical_trace_status` 的判定：
> - **canonical**: intent_id present + policy_id present + len(evidence_span_ids) >= 1
> - **partial**: intent_id 或 policy_id 存在，但 evidence_span_ids 为空，或三者不完整
> - **non_canonical**: 没有 intent_id **且** 没有 policy_id（legacy direct-extraction）
> 
> 只有 canonical 状态且包含 `execution_timing` 的 TradeAction 允许进入 F6 Review 和 F8 Backtest。

### 输出 Schema

```python
TradeAction(
    trade_action_id: str,
    intent_id: str,              # **REQUIRED** -> F3 Intent
    policy_id: str,              # **REQUIRED** -> F4 PolicyMappingResult
    evidence_span_ids: List[str],# **REQUIRED** -> F2 EvidenceSpan
    execution_timing: ExecutionTiming,  # **REQUIRED** -> F5 timing contract

    timestamp: datetime,
    source: SourceInfo,
    target: TargetInfo,
    direction: TradeDirection,
    action_chain: List[ActionStep],
    confidence: float,

    enrichment: Optional[MarketEnrichment],
    validation_status: ValidationStatus,
    backtest_result: Optional[BacktestResult],
    rlhf_feedback: Optional[RLHFFeedback],
)

ExecutionTiming(
    intent_published_at: datetime,          # KOL 内容发布时间
    intent_effective_at: Optional[datetime],# KOL 文本指向的生效时间
    action_decision_at: datetime,           # 系统生成 TradeAction 的时间
    action_executable_at: datetime,         # 按交易日历计算的最早可执行时间

    market: str,
    timezone: str,
    market_session_at_publish: Literal[
        "pre_market", "regular", "after_close",
        "non_trading_day", "unknown"
    ],
    execution_delay_reason: Optional[str],
    timing_policy_id: str,
)
```

### 新增字段（必须）

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `intent_id` | `str` | F3 | 追溯原始投资意图 |
| `policy_id` | `str` | F4 | 追溯使用的 policy 版本 |
| `evidence_span_ids` | `List[str]` | F2 | 追溯原文证据位置 |
| `execution_timing` | `ExecutionTiming` | F5 | 区分 KOL 发布时间、intent 生效时间、系统决策时间和最早可执行时间 |

### 三层择时系统

1. **Market Calendar Rules**：确定性交易日历规则。盘中发布时 `action_executable_at = 当前时间 + 最小延迟`；盘后、周末、节假日发布时 `action_executable_at = 下一交易日开盘或 policy 指定的下一合法交易时段`。
2. **Policy Timing Rules**：F4 policy 输出 timing hint，如 `follow_next_open`, `follow_after_open_30min`, `follow_vwap_window`, `wait_for_pullback`, `wait_for_breakout`, `review_required`, `no_action`。
3. **Optional Timing Agent / Quant Bot**：LLM 或量化 bot 只能在交易日历和 F4 timing hint 给定的候选集合内辅助选择，并必须记录 rationale；不能自由生成交易时间。

### Owning Files

- `schemas/trade_action.py`
- `extraction/trade_action_extractor.py`
- `extraction/enriched_extractor.py`

### Forbidden Responsibilities

- 不直接从原始文本生成 TradeAction（必须经过 F3->F4->F5）-- canonical 路径
- 不跳过 F4 Policy 层自行决定仓位/触发条件
- 不生成没有 intent_id 的 TradeAction
- 不生成没有 evidence_span_ids 的 TradeAction
- 不生成没有 execution_timing 的 TradeAction
- 不让 LLM 直接自由决定 action_executable_at
- 不绕过交易日历把盘后/休市观点按不可成交时间回测

### Acceptance Checklist

- [ ] 每条 TradeAction 包含非空的 intent_id
- [ ] 每条 TradeAction 包含非空的 policy_id
- [ ] 每条 TradeAction 包含至少 1 个 evidence_span_id
- [ ] 每条 TradeAction 包含 execution_timing
- [ ] 周五盘后发布的 intent 不得生成周五盘后可成交的 action_executable_at
- [ ] Timing Agent / Quant Bot 输出只能选择合法候选时间，并记录 timing_policy_id
- [ ] TradeActionExtractor 的 canonical 入口方法只接收 PolicyMappedIntent（不接收原始文本）
- [ ] Legacy `extract_from_text()` 标记为 `@deprecated`

---

## Legacy Direct Extraction Path（已弃用）

当前 `extraction/trade_action_extractor.py` 中存在一条 **legacy direct extraction path**，其输入为原始文本，输出为 TradeAction，完全跳过 F3 Intent 和 F4 Policy 层。

```
Legacy path (DEPRECATED):
  原始文本 -> TradeActionExtractor.extract_from_text() -> TradeAction
  跳过: F1 标准化 -> F1.5 主题组装 -> F2 锚定 -> F3 Intent -> F4 Policy

Canonical path:
  F0 -> F1 -> F1.5 -> F2 -> F3 Intent -> F4 Policy -> F5 TradeAction
```

### 处理规则

1. **可作为 baseline 或对照实验使用**：在评估 F3/F4/F5 canonical 路径质量时，legacy direct extraction 的输出可作为对比基线。
2. **不得作为 canonical F5 输入路径**：任何生产流水线、API 端点、前端视图不得依赖 legacy direct extraction path 作为唯一数据来源。
3. **必须标记 `@deprecated`**：`extract_from_text()` 及类似直接收原始文本的方法必须添加 deprecation 标记。
4. **新代码不得调用**：所有新开发的功能必须走 F3->F4->F5 canonical 路径。

---

## F6: Review（复核）

- **Purpose**: 人工审核 TradeAction + Intent，收集 RLHF 反馈，导出 DPO 训练数据。
- **Maturity Status**: `production`
- **Allowed Input**: F5 `TradeAction[]` + F3 `Intent[]`（用于证据对比）
- **Required Output**: Reviewed TradeAction + `RLHFFeedback` + DPO 训练数据

### 输出 Schema

```python
# 已存在的 schema，不变
RLHFFeedback(
    rating: Optional[int],           # 1-5
    is_correct: Optional[bool],
    corrections: List[str],
    corrected_direction: Optional[str],
    corrected_ticker: Optional[str],
    reviewer_id: str,
    reviewed_at: datetime,
)
```

### Owning Files

- `api/routes/rlhf.py`
- `api/routes/review.py`
- 前端: `rlhf-review-panel/`

### Forbidden Responsibilities

- 不修改原始 EvidenceSpan
- 不直接修改 Intent（应通过 F3 重新提取）
- 不修改 TradeAction 而不记录 reviewer_id 和 reviewed_at

### Acceptance Checklist

- [ ] RLHF 提交/查询/统计/DPO 导出端点正常
- [ ] 人工修正被记录在 corrections 中
- [ ] reviewed_at 和 reviewer_id 必填

---

## F7: Timeline（时间线）

- **Purpose**: 以 KOL 为中心轴构建观点时间线，维护每个 KOL 对每个标的的 ViewpointState，支持跨文档观点演化追踪和多 KOL 分歧分析。
- **Maturity Status**: `alpha`（基础 Timeline 可用，但 ViewpointState/TargetOpinionGraph 缺失，有 mock fallback）
- **Allowed Input**: F3 `Intent[]` + F5 `TradeAction[]` + F6 Review 结果
- **Required Output**: `KOLTimeline` + `ViewpointState`（每 KOL 每标的）+ `TargetOpinionGraph`（多 KOL 同标的）

### 输出 Schema

```python
KOLTimeline(
    kol_id: str,
    timeline: List[TimelineEntry],  # 按时序排列
    generated_at: datetime,
)

TimelineEntry(
    timestamp: datetime,
    intent: NormalizedInvestmentIntent,  # F3
    trade_action: Optional[TradeAction], # F5 (可能为空，如果只有观点没有交易)
    viewpoint_state: Optional[ViewpointState],
)

ViewpointState(
    kol_id: str,
    target_symbol: str,
    current_direction: str,
    current_position_hint: str,
    conviction: float,
    active_thesis: List[str],      # 当前持有论点
    risk_factors: List[str],       # 当前风险因素
    last_updated_at: datetime,
    supporting_intent_ids: List[str],
    contradiction_intent_ids: List[str],
    state_transitions: List[StateTransition],  # 状态变化历史
)

TargetOpinionGraph(
    target_symbol: str,
    kols: List[KOLOpinion],        # 各 KOL 对该标的的观点
    consensus: Optional[str],       # bullish/bearish/neutral/mixed
    divergence_score: float,        # 0-1, 分歧程度
)
```

### Owning Files

- `timeline/engine.py`
- `timeline/models.py`
- `api/routes/opinions.py`
- `api/routes/kol.py`

### Forbidden Responsibilities

- 不生成新的 TradeAction
- 不修改 Intent 或 TradeAction 数据
- 不做回测计算（F8）

### Acceptance Checklist

- [ ] 可查询指定 KOL + 时间范围的时间线
- [ ] ViewpointState 正确反映观点变化（增强/减弱/反转/退出）
- [ ] 同一 KOL 对同一标的的多条 Intent 正确串联
- [ ] TargetOpinionGraph 展示多 KOL 共识/分歧
- [ ] 无真实数据时不返回 mock 数据（返回空列表 + 明确标记）

---

## F8: Backtest（回测）

- **Purpose**: 基于 TradeAction 和市场数据模拟跟单 Portfolio，计算收益、风险指标，评估 KOL 表现。
- **Maturity Status**: `beta`（BacktestEngine 完整实现，但 pipeline orchestrator 中为 placeholder，mock 价格默认）
- **Allowed Input**: F5 `TradeAction[]`（含 effective_trade_at）+ 市场价格数据（via CachedPriceProvider / yfinance）
- **Required Output**: `BacktestResult` (return_pct, Sharpe, Sortino, Calmar, MaxDrawdown, VaR) + `KOLScore`

### 输出 Schema

```python
BacktestResult(
    backtest_id: str,
    total_return: float,         # 总收益率
    annualized_return: float,    # 年化收益率
    sharpe_ratio: float,
    sortino_ratio: float,
    calmar_ratio: float,
    max_drawdown: float,         # 最大回撤
    var_95: float,               # 95% VaR
    win_rate: float,             # 胜率
    total_trades: int,
    holding_days: Optional[int],
    start_date: datetime,
    end_date: datetime,
    run_timestamp: datetime,
)
```

### Owning Files

- `backtest/engine.py`
- `backtest/prices.py`
- `api/routes/backtest.py`
- `pipeline/orchestrator.py` -- F8 stage runner

### Forbidden Responsibilities

- 不使用 mock 价格进行生产回测
- 不在没有 effective_trade_at 的情况下执行回测
- 不生成 TradeAction

### Acceptance Checklist

- [ ] pipeline orchestrator 的 F8 阶段调用真实 BacktestEngine
- [ ] 回测使用真实价格数据（至少 yfinance）
- [ ] 回测结果持久化到 `data/F8_metrics/`
- [ ] Mock 价格仅在 `use_mock=True` 且非生产环境下使用
- [ ] 回测结果包含 backtest_id 可追溯到输入 TradeAction

---

## F+: Training Loop（训练闭环）

- **Purpose**: 从 F6（RLHF）、F7（时间线）、F8（回测结果）生成高质量训练数据，微调模型改进 F1/F3/F4 的提取质量。F+ 不是编号 F-stage，而是跨阶段的闭环过程。
- **Maturity Status**: `placeholder`（数据导出接口存在，但训练数据量不足，未执行过实际训练）
- **Allowed Input**: F6 RLHF 标注数据 + F7 时间线验证数据 + F8 回测结果
- **Required Output**: SFT 训练数据集（JSONL）+ DPO 偏好对数据集（JSONL）+ 微调后的模型权重

### Acceptance Checklist

- [ ] DPO 导出包含 F3 Intent 级别标签（不仅仅是 TradeAction 级别）
- [ ] 训练样本可追溯到 F2 evidence_span_ids
- [ ] 模型评估使用 F8 回测结果而非单独的训练/测试集

---

## Agent Execution Rules

以下规则适用于所有开发和检查 Agent。违反任一条即为架构违规，Code Review 必须拒绝。

### 1. 每个 Agent 必须声明 F-stage

Agent 在开始任务时必须声明自己所处的 F-stage，且只能修改该 stage 的 owning files。

| Agent | F-stage | 可修改文件 | 可读文件 |
|---|---|---|---|
| Intake Agent | F0 | `ingestion/`, `api/routes/files.py`, `schemas/content.py` | 无 |
| Standardize Agent | F1 | `schemas/content_envelope.py`, `parsing/content_standardizer.py`, `parsing/vision_extractor.py`, `parsing/standardization_quality_scorer.py`, `parsing/feishu_chat_markdown_standardizer.py`, `parsing/image_ocr_layout_standardizer.py`, `docs/specs/f1-standardization-contract.md` | F0 输出 |
| Topic Assembly Agent | F1.5 | `parsing/topic_assembler.py`, `parsing/llm_topic_assembly_adapter.py`, `schemas/topic_block.py` | `schemas/content_envelope.py`, F1 输出 |
| Anchor Agent | F2 | `enrichment/`, `aggregation/`, `entity_registry.py` | `schemas/content_envelope.py`, `schemas/topic_block.py`, F1.5 输出 |
| Intent Agent | F3 | `extraction/intent_extractor.py`, `schemas/investment_intent.py` | F1.5/F2 输出 |
| Policy Agent | F4 | `policy/`, `schemas/policy.py` | `schemas/investment_intent.py`, F3 输出 |
| Execute Agent | F5 | `extraction/trade_action_extractor.py`, `schemas/trade_action.py` | `schemas/policy.py`, F4 输出 |
| Review Agent | F6 | `api/routes/rlhf.py`, `api/routes/review.py` | F3/F5 输出 |
| Timeline Agent | F7 | `timeline/`, `api/routes/opinions.py`, `api/routes/kol.py` | F3/F5/F6 输出 |
| Backtest Agent | F8 | `backtest/`, `api/routes/backtest.py`, `pipeline/orchestrator.py` | F5 输出 |

### 2. 每个 Agent 必须声明输入输出 Schema

Agent 的输入和输出必须严格对应所属 F-stage 的 Allowed Input 和 Required Output Schema。不得接收或产出本 stage 契约未定义的 Schema 类型。

### 3. 每个 Agent 不得跨 Stage 写业务逻辑

Agent 不得在所属 F-stage 的 owning files 中写入属于其他 F-stage 的业务逻辑。例如:

- F5 Execute Agent 不得在 `trade_action_extractor.py` 中实现 Intent 提取逻辑（那是 F3 的职责）
- F3 Intent Agent 不得在 `intent_extractor.py` 中生成 TradeAction（那是 F5 的职责）
- F4 Policy Agent 不得修改 Intent 的 direction（除非有 audit log）

### 4. 检查 Agent 必须验证是否绕过 F3/F4

Code Review 和 CI 检查必须包含以下验证:

- [ ] F5 的 TradeAction 是否包含非空 intent_id（未绕过 F3）
- [ ] F5 的 TradeAction 是否包含非空 policy_id（未绕过 F4）
- [ ] 是否存在直接调用 `extract_from_text()` 而不经过 F3->F4 的代码路径
- [ ] F3 输出中是否包含 position_size_pct / target_price / trigger_condition（违规）
- [ ] F4 输出中是否修改了 F3 的 direction 而没有 audit log

### 5. Agent 验收通用规则

1. 必须修改或新增测试（不只是改业务代码）
2. 必须列出修改文件清单
3. 必须运行验证命令（pytest / npm run build）
4. 所有输出必须可 JSON 序列化/反序列化
5. 所有从 KOL 内容抽出的结果必须保留证据链
6. 不能仅凭自述声称"完成"，必须有测试/fixture 输出确认

---

## Legacy Mapping（旧命名仅用于迁移参考）

> **重要**: 以下 L0-L8 和 V0-V6 命名已废弃（deprecated）。仅在阅读旧代码、旧文档或执行数据目录迁移时参考。新代码、文档、commit message 必须使用 F0-F8。

### L0-L8 -> F0-F8

| 旧 L 层 (deprecated) | 旧名称 | -> | 新 F-stage | 说明 |
|---|---|---|---|---|
| L0 | 接入层 | -> | **F0** Intake | 职责相同 |
| L1 | 富化层 | -> | **F2** Anchor | 重新定位为锚定 |
| L2 | 标准化层 | -> | **F1** Standardize | 重新定位为标准化 |
| L3 | 解析层 | -> | **F1** Standardize | OCR/ASR 归入标准化 |
| L4 | 聚合层 | -> | **F2** Anchor | 实体消歧归入锚定 |
| L5 | 抽取层 | -> | **F5** Execute | 直提路径已弃用 |
| L6 | 复核层 | -> | **F6** Review | 职责相同 |
| L7 | 时间线层 | -> | **F7** Timeline | 需升级为 ViewpointState |
| L8 | 回测层 | -> | **F8** Backtest | 职责相同 |

### V0-V6 -> F0-F8

| 旧 V 层 (deprecated) | 旧名称 | -> | 新 F-stage | 说明 |
|---|---|---|---|---|
| S0 | Raw Source | -> | **F0** Intake | 职责相同 |
| V0 | Content Standardization | -> | **F1** Standardize | 职责相同 |
| V0.5 | Quality/Temporal/Entity | -> | **F2** Anchor | 职责相同 |
| V1 | Investment Intent | -> | **F3** Intent | 职责相同 |
| V2 | Policy Mapping | -> | **F4** Policy | 职责相同 |
| V3 | TradeAction | -> | **F5** Execute | 职责相同 |
| V4 | Timeline/Viewpoint | -> | **F7** Timeline | 注意 F6 Review 在中间 |
| V5 | Backtest/Evaluation | -> | **F8** Backtest | 职责相同 |
| V6 | Training Loop | -> | **F+** Training | 非独立 F-stage |

---

*版本: 2.1.0 | 更新: 2026-04-30 | F0-F8 Canonical Pipeline | L0-L8 / V0-V6 deprecated*
