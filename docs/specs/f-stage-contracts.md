# F-Stage Contracts — 每阶段契约定义

> 版本: 1.0.0 | 创建: 2026-04-28
> 用途: 定义每个 F-stage 的精确输入/输出/Schema/禁止职责/验收清单。作为 Agent 任务边界和 Code Review 的权威参考。

---

## 使用说明

每个 F-stage 条目包含:
- **输入**: 必须从前置阶段获得的 Schema 实例
- **输出**: 本阶段必须产出的 Schema 实例
- **Owning files**: 本阶段代码的权威文件列表
- **状态**: implemented / partial / placeholder / mock-backed / contract-only / missing
- **禁止职责**: Agent 绝不能在本阶段做的事情
- **验收清单**: Agent 完成任务后必须通过的检查项

---

## F0: Intake（接入）

### 输入
- 飞书群聊消息（via Feishu API / lark-cli）
- B站视频（via BBDown / bilibili API）
- 微信公众号文章（via wechat-article-exporter）
- 手动上传文件
- NotebookLM 笔记

### 输出
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

### Owning files
- `ingestion/feishu_poller.py`
- `ingestion/orchestrator.py`
- `ingestion/bilibili_adapter.py`
- `ingestion/wechat_adapter.py`
- `ingestion/wechat_exporter_client.py`
- `ingestion/nlm_sync.py`
- `ingestion/classifier.py`
- `api/routes/files.py`
- `schemas/content.py`

### 禁止职责
- ❌ 不做 OCR/ASR/文本解析
- ❌ 不做话题拆分或实体抽取
- ❌ 不做任何 LLM 调用
- ❌ 不做内容质量判断
- ❌ 不修改原始文件内容

### 验收清单
- [ ] 飞书消息可成功轮询并下载附件
- [ ] ContentRecord 持久化到 `data/F0_intake/`
- [ ] 原始文件完整归档到 `data/raw/`
- [ ] creator_id 在飞书接入时从群配置填充
- [ ] 文件去重检查（content_id 唯一性）

---

## F1: Standardize（标准化）

### 输入
- F0 `ContentRecord`
- F0 原始文件（图片/聊天记录/PDF/音频/文档）

### 输出
```python
ContentEnvelope(
    envelope_id: str,
    source_id: str,            # → F0 ContentRecord.content_id
    source_type: Literal[      # 7 种
        "feishu_chat", "feishu_doc", "image", "pdf",
        "audio_transcript", "video_transcript", "wechat_article", "manual"
    ],
    creator_id: Optional[str],
    creator_name: Optional[str],
    published_at: Optional[datetime],
    collected_at: datetime,
    source_uri: Optional[str],
    raw_path: Optional[str],
    blocks: List[ContentBlock], # 至少 1 个
    lineage: DataLineage,       # 来源追溯
    metadata: dict,
)

ContentBlock(
    block_id: str,
    envelope_id: str,
    block_type: Literal[        # 13 种
        "chat_message", "paragraph", "image_text", "table_region",
        "chart_region", "audio_segment", "video_segment", "quote",
        "link_reference", "section_title", "ocr_unreadable",
        "code_block", "attachment_ref"
    ],
    text: str,                  # 块内文本（可空，如图表区）
    order_index: int,           # 在 envelope 内的顺序
    speaker: Optional[str],     # 聊天消息的说话人
    page_index: Optional[int],  # PDF 页码
    image_region: Optional[dict],  # {x, y, w, h} 图片区域坐标
    start_time_sec: Optional[float],  # 音频起始秒
    end_time_sec: Optional[float],    # 音频结束秒
    parent_block_id: Optional[str],
    thread_id: Optional[str],   # 聊天线程 ID
    metadata: dict,
)
```

### Owning files
- `schemas/content_envelope.py`
- `parsing/content_standardizer.py`
- `parsing/vision_extractor.py`
- `parsing/audio_extractor.py`
- `parsing/funasr_client.py`
- `parsing/mimo_asr_client.py`

### 禁止职责
- ❌ 不做质量评估（F2）
- ❌ 不做投资意图判断（F3）
- ❌ 不做实体链接（F2）
- ❌ 不做时间解析（F2）
- ❌ 不丢弃低质量块（只标记，由 F2 门控决定）

### 验收清单
- [ ] 图片→ContentBlock: 标题/段落/表格/图表区域分别成块
- [ ] 图片 block 保留 image_region 坐标
- [ ] 飞书聊天→ContentBlock: 按消息/说话人/时间拆分
- [ ] 飞书聊天保留 thread_id / speaker
- [ ] 音频转录→ContentBlock: 按语义段落+时间戳拆分
- [ ] PDF→ContentBlock: 保留标题层级和表格结构
- [ ] 所有 ContentBlock 可追溯到原始文件

---

## F2: Anchor（锚定）

### 输入
- F1 `ContentEnvelope` + `ContentBlock[]`

### 输出
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
    block_id: str,                   # → F1 ContentBlock.block_id
    char_start: int,
    char_end: int,
    text: str,                       # 截取的原文证据
    confidence: float,
    span_type: str,                  # intent_keyword | entity_mention | time_mention | action_trigger
)
```

### Owning files
- `schemas/content_envelope.py` — QualityCard, TemporalAnchor (schema)
- `schemas/evidence.py` — EvidenceSpan
- `enrichment/__init__.py` — TopicSplitter, EntityExtractor
- `enrichment/market_context.py` — MarketContextEnricher
- `enrichment/sentiment_fusion.py` — SentimentFusionEnricher
- `entity_registry.py` — 统一实体注册表
- `aggregation/__init__.py` — EntityLinker, ContextAggregator

### 禁止职责
- ❌ 不做投资意图提取（F3）
- ❌ 不做交易动作生成（F5）
- ❌ 不做 policy 映射（F4）
- ❌ 不丢弃 gate=reject 的内容（存档但标记）

### 验收清单
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

### 输入
- F2 `ContentEnvelope`（gate ≥ soft_pass）

### 输出
```python
NormalizedInvestmentIntent(
    intent_id: str,
    envelope_id: str,            # → F1 ContentEnvelope
    block_ids: List[str],        # → F1 ContentBlock (证据来源块)
    creator_id: Optional[str],   # KOL ID
    target_type: str,            # stock | sector | index | crypto
    target_name: str,            # 目标名称
    target_symbol: Optional[str],# 标准化 ticker
    market: Optional[str],       # US/HK/CN/CRYPTO
    direction: Literal["bullish", "bearish", "neutral", "watchlist", "risk_warning"],
    actionability: Literal["opinion", "watch", "explicit_action"],
    position_delta_hint: Literal["open", "add", "reduce", "hold", "exit", "none"],
    conviction: float,           # 0.0–1.0 信念强度
    confidence: float,           # 0.0–1.0 提取置信度
    evidence_span_ids: List[str],# → F2 EvidenceSpan
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

### Owning files
- `schemas/investment_intent.py` — Schema + validators
- `extraction/intent_extractor.py` — 提取器实现

### 禁止职责
- ❌ 不生成仓位比例（position_size_pct）
- ❌ 不生成目标价格（target_price_low, target_price_high）
- ❌ 不生成触发条件（trigger_condition）
- ❌ 不生成止损止盈
- ❌ 不直接生成 TradeAction
- ❌ 不做交易执行映射
- ❌ 不丢弃模糊样本（标注 ambiguity_flags 但不丢弃）

### 验收清单
- [ ] "我看好宁德时代" → actionability=opinion, position_delta_hint=none
- [ ] "我加仓宁德时代" → actionability=explicit_action, position_delta_hint=add
- [ ] "目前持有，稍微加仓一点" → direction=bullish, position_delta_hint=add, conviction < 0.8
- [ ] "清仓宁德时代" → actionability=explicit_action, position_delta_hint=exit
- [ ] "关注一下腾讯" → direction=neutral/watch, actionability=watch
- [ ] 每个 Intent 至少有 1 个 evidence_span_id
- [ ] 模糊样本保留 ambiguity_flags（如 unknown_target）
- [ ] 提取器不输出 position_size_pct / target_price / trigger_condition
- [ ] "看好"和"加仓"产生不同的 actionability
- [ ] direction 和 conviction 独立，不因"强烈看好"自动变成 explicit_action

---

## F4: Policy（策略映射）

### 输入
- F3 `NormalizedInvestmentIntent[]`

### 输出
```python
PolicyMappingResult(
    policy_id: str,
    intent_id: str,              # → F3 Intent
    policy_version: str,         # 使用的 policy 版本
    policy_layers_applied: List[str],  # ["GlobalBase", "StyleArchetype", "KOLPersona"]

    # 从 F3 Intent 继承（不修改）
    direction: str,
    target_name: str,
    target_symbol: str,

    # F4 生成
    position_size_pct: float,    # 仓位比例 (0.0–1.0)
    max_holding_days: int,       # 最大持仓天数
    stop_loss_pct: Optional[float],    # 止损比例
    take_profit_pct: Optional[float],  # 止盈比例
    entry_condition: Optional[str],    # 入场条件描述
    exit_condition: Optional[str],     # 出场条件描述
    confidence_adjustment: float,      # policy 调整后的置信度

    # 审计
    mapping_rationale: str,      # 映射理由（human-readable）
    metadata: dict,
)

# Policy Context (输入到 F4)
PolicyContext(
    kol_id: str,                 # KOL 标识
    style_archetype: str,        # 短线/景气/价值/烟蒂/混合
    risk_preference: str,        # 激进/均衡/保守
    persona_summary: Optional[str],  # 从历史内容总结的 persona
)
```

### Policy 5 层结构
```
Global Base Policy          → 通用语言→动作基准映射
  Style Archetype Policy    → 短线/景气/价值/烟蒂风格差异
    Risk Preference Policy  → 激进/均衡/保守
      KOL Persona Policy    → 个体 KOL 语言习惯修正
        Content Correction   → 当前上下文临时修正
```

### Owning files
- **(待创建)** `schemas/policy.py`
- **(待创建)** `policy/__init__.py`
- **(待创建)** `policy/policy_mapper.py`
- **(待创建)** `policy/global_base.py`
- **(待创建)** `policy/style_archetypes.py`
- **(待创建)** `policy/risk_preferences.py`
- **(待创建)** `policy/kol_persona.py`

### 禁止职责
- ❌ 不生成新的 Intent（Intent 只能来自 F3）
- ❌ 不修改 Intent 的 direction（除非有 audit log）
- ❌ 不覆盖 conviction 而不记录理由
- ❌ 不直接生成 TradeAction（那是 F5 的职责）

### 验收清单
- [ ] 同一句"加仓"在"短线风格"下 → position_size_pct 较小, max_holding_days 较短
- [ ] 同一句"加仓"在"价值风格"下 → position_size_pct 较大, max_holding_days 较长
- [ ] 同一句"加仓"在"激进偏好"下 → stop_loss_pct 较小（容忍更大回撤）
- [ ] 每个 PolicyMappingResult 包含 mapping_rationale
- [ ] Global Base Policy 覆盖所有常见 actionability 类型
- [ ] F3 的 position_delta_hint=none 时 F4 不生成仓位
- [ ] policy_version 可追溯

---

## F5: Execute（交易执行）

### 输入
- F4 `PolicyMappingResult[]`

### 输出
```python
TradeAction(
    trade_action_id: str,
    intent_id: str,              # **REQUIRED** → F3 Intent
    policy_id: str,              # **REQUIRED** → F4 PolicyMappingResult
    evidence_span_ids: List[str],# **REQUIRED** → F2 EvidenceSpan

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
```

### 新增字段（必须）
| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `intent_id` | `str` | F3 | 追溯原始投资意图 |
| `policy_id` | `str` | F4 | 追溯使用的 policy 版本 |
| `evidence_span_ids` | `List[str]` | F2 | 追溯原文证据位置 |

### Owning files
- `schemas/trade_action.py`
- `extraction/trade_action_extractor.py`
- `extraction/enriched_extractor.py`

### 禁止职责
- ❌ 不直接从原始文本生成 TradeAction（必须经过 F3→F4→F5）
- ❌ 不跳过 F4 Policy 层自行决定仓位/触发条件
- ❌ 不生成没有 intent_id 的 TradeAction
- ❌ 不生成没有 evidence_span_ids 的 TradeAction

### 验收清单
- [ ] 每条 TradeAction 包含非空的 intent_id
- [ ] 每条 TradeAction 包含非空的 policy_id
- [ ] 每条 TradeAction 包含至少 1 个 evidence_span_id
- [ ] TradeActionExtractor 的入口方法只接收 PolicyMappedIntent（不接收原始文本）
- [ ] Legacy `extract_from_text()` 标记为 deprecated

---

## F6: Review（复核）

### 输入
- F5 `TradeAction[]`
- F3 `Intent[]`（用于证据对比）

### 输出
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

### Owning files
- `api/routes/rlhf.py`
- `api/routes/review.py`
- 前端: `rlhf-review-panel/`

### 禁止职责
- ❌ 不修改原始 EvidenceSpan
- ❌ 不直接修改 Intent（应通过 F3 重新提取）
- ❌ 不修改 TradeAction 而不记录 reviewer_id 和 reviewed_at

### 验收清单
- [ ] RLHF 提交/查询/统计/DPO 导出端点正常
- [ ] 人工修正被记录在 corrections 中
- [ ] reviewed_at 和 reviewer_id 必填

---

## F7: Timeline（时间线）

### 输入
- F3 `Intent[]` + F5 `TradeAction[]` + F6 Review 结果

### 输出
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

### Owning files
- `timeline/engine.py`
- `timeline/models.py`
- `api/routes/opinions.py`
- `api/routes/kol.py`

### 禁止职责
- ❌ 不生成新的 TradeAction
- ❌ 不修改 Intent 或 TradeAction 数据
- ❌ 不做回测计算（F8）

### 验收清单
- [ ] 可查询指定 KOL + 时间范围的时间线
- [ ] ViewpointState 正确反映观点变化（增强/减弱/反转/退出）
- [ ] 同一 KOL 对同一标的的多条 Intent 正确串联
- [ ] TargetOpinionGraph 展示多 KOL 共识/分歧
- [ ] 无真实数据时不返回 mock 数据（返回空列表 + 明确标记）

---

## F8: Backtest（回测）

### 输入
- F5 `TradeAction[]`（含 effective_trade_at）
- 市场价格数据（via CachedPriceProvider / yfinance）

### 输出
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

### Owning files
- `backtest/engine.py`
- `backtest/prices.py`
- `api/routes/backtest.py`
- `pipeline/orchestrator.py` — F8 stage runner

### 禁止职责
- ❌ 不使用 mock 价格进行生产回测
- ❌ 不在没有 effective_trade_at 的情况下执行回测
- ❌ 不生成 TradeAction

### 验收清单
- [ ] pipeline orchestrator 的 F8 阶段调用真实 BacktestEngine
- [ ] 回测使用真实价格数据（至少 yfinance）
- [ ] 回测结果持久化到 `data/F8_metrics/`
- [ ] Mock 价格仅在 `use_mock=True` 且非生产环境下使用
- [ ] 回测结果包含 backtest_id 可追溯到输入 TradeAction

---

## F+: Training Loop（训练闭环）

### 输入
- F6 RLHF 标注数据
- F7 时间线验证数据
- F8 回测结果

### 输出
- SFT 训练数据集（JSONL）
- DPO 偏好对数据集（JSONL）
- 微调后的模型权重

### 当前状态
`contract-only` — 数据导出接口存在，但训练数据量不足，未执行过实际训练。

### 验收清单
- [ ] DPO 导出包含 V1 Intent 级别标签（不仅仅是 TradeAction 级别）
- [ ] 训练样本可追溯到 F2 evidence_span_ids
- [ ] 模型评估使用 F8 回测结果而非单独的训练/测试集

---

## Agent 任务边界

每个 Agent 只修改自己 F-stage 的 owning files:

| Agent | F-stage | 可修改文件 | 可读文件 |
|---|---|---|---|
| Intake Agent | F0 | `ingestion/`, `api/routes/files.py`, `schemas/content.py` | 无 |
| Standardize Agent | F1 | `parsing/content_standardizer.py`, `parsing/vision_extractor.py`, `parsing/audio_extractor.py` | `schemas/content_envelope.py`, F0 输出 |
| Anchor Agent | F2 | `enrichment/`, `aggregation/`, `entity_registry.py` | `schemas/content_envelope.py`, F1 输出 |
| Intent Agent | F3 | `extraction/intent_extractor.py`, `schemas/investment_intent.py` | F1/F2 输出 |
| Policy Agent | F4 | `policy/`, `schemas/policy.py` | `schemas/investment_intent.py`, F3 输出 |
| Execute Agent | F5 | `extraction/trade_action_extractor.py`, `schemas/trade_action.py` | `schemas/policy.py`, F4 输出 |
| Review Agent | F6 | `api/routes/rlhf.py`, `api/routes/review.py` | F3/F5 输出 |
| Timeline Agent | F7 | `timeline/`, `api/routes/opinions.py`, `api/routes/kol.py` | F3/F5/F6 输出 |
| Backtest Agent | F8 | `backtest/`, `api/routes/backtest.py`, `pipeline/orchestrator.py` | F5 输出 |

### Agent 验收通用规则

1. 必须修改或新增测试（不只是改业务代码）
2. 必须列出修改文件清单
3. 必须运行验证命令（pytest / npm run build）
4. 所有输出必须可 JSON 序列化/反序列化
5. 所有从 KOL 内容抽出的结果必须保留证据链
6. 不能仅凭自述声称"完成"，必须有测试/fixture 输出确认

---

*更新: 2026-04-28*
