# 自改进标注闭环 — 设计文档

> 日期: 2026-06-13
> F-stage: 跨 F1 / F1.5 / F2 / F3 / F5 / F+ (Training Loop)
> 状态: proposed（现状已只读核查，待评审）
> 关联: [RLVR-guided DPO 任务卡](2026-06-12-rlvr-guided-dpo-task-card.md)、[F6 RLHF→DPO 映射](2026-06-07-f6-rlhf-to-dpo-mapping.md)、[百炼 DPO handoff](2026-06-12-bailian-dpo-run-handoff.md)

## 0. 结论

把 KOL 异构资料（群聊 / 研报 PDF / 直播转录 / 策略截图）转成高质量 DPO 偏好对的过程，做成一个**自改进闭环**：模型提议 → verifier 三态裁决 → 人工裁决 → 沉淀成确定性资产（registry 别名、reward 权重、DPO 偏好）→ 下一轮机器能确定性处理的边界扩大、人只处理新增判断。

**关键结论：这是"接线"工程，不是"从零造"。** 2026-06-13 核查显示底座大部分已存在（OCR bbox provenance、entity_registry.resolve、registry-gap 候补），真正缺的是接线 + 两个小能力（registry 写回、verifier 三态）。

## 1. 目标：自改进闭环

```
异构资料（群聊 / 研报PDF / 直播转录 / 策略截图）
  │  F1 OCR/ASR/解析（带 provenance 锚点：原图 bbox、时间戳）
  ▼
标准化文本 + 来源锚点（ContentEnvelope + ContentBlock[].bbox）
  │  F1.5 主题分块（一对多：一条策略 → 多个独立观点 TopicBlock）
  ▼
候选抽取：Qwen-Max + GLM-5.1 双模型提议（分歧自动标记）
  ▼
verifier (rewards.py) 三态裁决 ── 查 entity_registry.resolve()
  ├─ grounded ────────────→ 高分候选
  ├─ hallucination ───────→ 重罚 / 丢弃
  └─ registry-gap ────┐
  ▼                   │
人工裁决（只看：分歧处 / registry-gap / 策略语义 / 低置信）
  ├─ 确认·修正 → chosen ──→ DPO 训练对（rejected = qwen3-8b 自己的输出）
  ├─ registry-gap 确认 ───→ 回填 entity_registry  ──┐ 回流①
  └─ accept/reject 记录 ──→ 校准 reward 权重 ───────┐│ 回流③
  ▼                                                ││
DPO 微调 qwen3-8b ──→ 下轮抽取更准 ──→ 人工改得更少 ─┘│ 回流②
                                                     ▼
                              verifier 越用越准、误杀递减 ◄┘
```

### 三个自改进回流

| 回流 | 机制 | 效果 |
|---|---|---|
| **① registry 回流** | registry-gap 经人工确认回填 entity_registry | 同一别名下次自动 grounded，verifier 误杀逐轮递减 |
| **② 模型回流** | 人裁决后的高质量 chosen → DPO → 模型抽取更准 | 下一轮人工要改的更少，标注负担递减 |
| **③ reward 校准回流** | 人对 verifier 高分项的 accept/reject 反馈 | 高分总被 reject → reward 设计有问题，及时校准，防 reward hacking |

核心理念：**人的判断被持续沉淀成确定性资产，而不是每轮重复劳动。**

## 2. 现状盘点（2026-06-13 只读核查）

| 命门 | 实际现状 | 文件 | 缺口 |
|---|---|---|---|
| **verifier grounding** | 纯字符串 `in text`（`ticker_in_text` / `number_in_text`），**未 import entity_registry**；rewards.py 待建 | `scripts/eval_compare.py:157-192` | 接 resolve() + 三态 |
| **entity_registry** | `resolve(别名)→(ticker,market,type)` 已存在（本就是 alias 表），但**纯静态表、零写回方法** | `src/finer/entity_registry.py:168` | 加 `add_alias` + 持久化 |
| **registry-gap 回填** | `append_registry_gap`→`registry_gaps.jsonl` + `/registry-gap` 端点已有，**无 consumer，候补不自动入库** | `annotation_store.py:474`、`annotation.py:231` | 接通"人工 confirm→入库" |
| **OCR provenance** | `BoundingBox`(x0,y0,x1,y1) + `ContentBlock.bbox` + table/chart/ocr_unreadable 分类全齐，OCR→block 已接 bbox | `content_envelope.py:35,278`、`image_ocr_standardizer.py:240-275` | 确认 bbox 穿透到 EvidenceSpan |

**底座成熟度**：OCR provenance > registry resolve / gap 候补 > verifier 三态（待建）。

## 3. verifier 三态设计（F+）

grounding 校验对象从"字面"改为"别名"，但**不放松硬门**：

- **grounded**：chosen.ticker 的某个已登记别名出现在 evidence_text（经 `entity_registry.resolve()`）→ 高分
- **hallucination**：ticker 与原文无任何可解析关联 → 重罚（真幻觉，硬门照拦）
- **registry-gap / UNRESOLVED**：原文有明显实体指代但 registry 未收录该别名 → **不罚、不当幻觉**，标记送人工 + 回填

接法（二选一，实施时定）：
1. 反查：取 chosen.ticker → registry 反查其全部别名集合 → 检查任一别名 ∈ evidence_text（需 registry 支持 ticker→aliases 反查）。
2. 正解扫描：扫 evidence_text 中的已知别名提及 → resolve 成 ticker 集合 → 检查 chosen.ticker ∈ 该集合。

**设计哲学（红线）**：verifier 永远做"查表 + 确定性裁决"，绝不做语义判断。语义（别名/俗称/指代）沉淀进 entity_registry 这个可审计、可回填的查找表。一旦让 verifier 自己"猜"泡泡是不是泡泡玛特，它就退化成另一个会幻觉的模型，硬门意义尽失。

## 4. schema 渐进（F1.5 / F5）

策略推送一条 = 多标的 + 条件分支 + 仓位 + 事件时间线，当前单条 6 键 TradeAction 装不下。**渐进，不一次性重构真相源**：

- **第一层（先做）：一对多** —— 一个 passage → 多个 TradeAction。不改 TradeAction 本身，改抽取范式（F1.5 拆 topic，每 topic 一个 action）。
- **第二层（看现状）：条件触发** —— 先看 `action_chain` 能否表达"突破X买入/回落Y加仓"，能则复用，不能先入 rationale。
- **第三层（暂缓）：仓位 sizing、事件驱动时机** —— 第一轮不碰，避免范围爆炸。

## 5. 真值三层（F3 / F5 / F6）

真值 ≠ 最强模型输出。真值 = 忠实 + 可溯源 + 正确。

- **模型提议**：Qwen-Max（primary extraction，instructor+TradeAction）+ GLM-5.1（fallback extraction）**双跑**，分歧处自动标记送人工重点看。**不用 MiMo-V2.5-Pro**（reasoning 模型做忠实抽取错配、易过度发挥、未配结构化输出）。
- **verifier 硬门**：§3 三态，机器可验证。
- **人裁决**：条件理解、多标的拆分、策略语义——verifier 管不了的部分。专业策略内容的真值瓶颈是"懂不懂策略语言"，不是模型智商。

## 6. 可追溯性穿透（F1→F2，不能放松）

溯源链必须穿透每一层、追到原图，不能只追到 OCR 中间产物：

```
TradeAction 字段 ← evidence_span ← OCR span(ContentBlock) ← 原图 bbox
                ↑
        ticker ← entity_registry: 别名映射 ← 原文别名提及
```

任何一个抽取值都能一路点回原图上那块像素。OCR 错误（SOXL→SOXI）若只追到 OCR 文本，会变成"看似可溯、实溯到错文本"的隐患——所以要么 OCR 高准 + 人校对，要么始终保留原图供核对。

## 7. 分步任务卡（接线清单）

每个任务独立 owning，按并行执行规范声明。依赖：B→C，B→A，D 独立，E/F 独立。

| 任务 | F-stage | owning files | 输入→输出 | 验收 |
|---|---|---|---|---|
| **A. verifier 三态** | F+ | `src/finer/ml/rewards.py`(新)、`tests/test_rewards.py`(新) | output+evidence → RewardBreakdown(三态) | `pytest tests/test_rewards.py`；grounded/hallucination/registry-gap 三态最小覆盖 + total∈[0,1] |
| **B. registry 写回** | F2 | `src/finer/entity_registry.py`、`tests/test_entity_registry.py` | add_alias(别名,ticker) → 持久化 | add+resolve 往返单测；新增别名后 resolve 命中 |
| **C. registry 回填 consumer** | F+/F6 | `scripts/backfill_registry.py`(新) 或 annotation_store consume 方法 | `registry_gaps.jsonl` →（人工 confirm）→ entity_registry | 候补入库往返；**红线：必须人工 confirm，不自动入库** |
| **D. bbox 穿透** | F2 | `src/finer/enrichment/*`、`schemas/`（EvidenceSpan） | ContentBlock.bbox → EvidenceSpan | OCR→block→evidence span 全程带 bbox（先核查现状，见 §10） |
| **E. 双模型提议** | F3/F5 | `src/finer/extraction/*` | evidence → Qwen-Max + GLM 候选 + 分歧标记 | 双跑输出；分歧项标记正确 |
| **F. 一对多抽取** | F1.5/F5 | `parsing/topic_assembler.py`、`extraction/*` | 多观点 passage → 多 TradeAction | 策略 fixture：一 passage→N action，各带独立 evidence_span |

## 8. 试点先行

**不要一次性补所有好资料、不要一次性建全闭环。** 先拿一张策略截图做单条端到端试点：OCR→分块→双模型抽取→verifier 三态→溯源→人审，走通整条链路，暴露真问题（OCR 准不准、schema 够不够、provenance 断没断、registry 命中率），再放量。"小投入验证、再规模化"。

## 9. 红线与非目标

- **不放松 verifier 硬门**：grounding 接 registry 别名表，但绝不退化成语义匹配。
- **verifier 不做语义判断**：语义沉淀进 entity_registry。
- **registry 回填需人工 confirm**：标注端不直写 registry（沿用 `append_registry_gap` 注释的既有约束）；批量入库需用户确认（CLAUDE.md 数据红线）。
- **rejected 必须是 qwen3-8b 自己的输出**：chosen 可用强模型，rejected 不可（否则 DPO 学习信号失效）。
- **不大改 TradeAction 真相源**：schema 渐进，先一对多。
- **provenance 追到原图**：不接受只追到 OCR 中间产物。
- **不在本闭环内做 GRPO/PPO/RM**（沿用 RLVR 任务卡 §11 边界）。
- **F8 市场收益不进 extractor 训练 reward**。

## 10. Open Issues（待核查 / 未决）

- **D 任务现状待核查**：`ContentBlock.bbox` 已确认存在（`content_envelope.py:278`），但 `EvidenceSpan`(F2) 是否承接/引用 bbox 未核查——实施 D 前先 grep `EvidenceSpan` schema 确认穿透是否已通、还是需新增字段。
- **§3 接法二选一**：registry 是否支持 ticker→aliases 反查（接法1）尚未确认；若不支持，用接法2（文本扫描别名）或给 registry 加反查索引。
- **MiMo OCR 位置锚点【2026-06-14 已核查】**：渲染 OCR 路径**源头不产 bbox**。实测 14 个 L0 PDF：pdfplumber 文本层 253 block 100% 带 bbox，渲染 OCR(mimo) 104 block **0 带 bbox**；全库图片 OCR 2534 block 全部无 bbox。全体 block raw_path(文件级) 100%、PDF page_index(页级) 100%。结论：MiMo 渲染 OCR 走整页→markdown、不输出 layout region，故无区域级锚点。**不是穿透断，是源头没产出 bbox。**
- **补渲染 OCR bbox 的卡点【2026-06-14 已查清】**：当前 OCR 是 **chat-vision 范式**（`pdf_standardizer._extract_page_via_vision` / `image_ocr_standardizer._extract_via_vision_api`：整页渲染→`chat_with_images`+"返回Markdown"prompt→纯文本）。这是"LLM 看图写字"，**响应结构上无 bbox**，故 `layout_regions` 消费口（`image_ocr_standardizer._build_blocks_from_regions`）从无写入方。补 bbox 三条路：① 接受页级溯源（第一轮推荐，文本层已像素级、OCR 块页级够人工核对）；② 换 layout-aware OCR 引擎（PaddleOCR/读光等原生出 bbox，像素级正解，需新依赖+重跑，独立立项）；③ prompt 让 vision LLM 估坐标（**不推荐**，坐标会漂会编，产生错位 bbox 比没有更危险）。**结论：MiMo chat-vision 拿不到可靠 bbox，第一轮走①，像素级硬需求则走②单独立项。** MiMo 是否另有带 bbox 的文档 OCR API 端点（区别于当前 chat vision）待查。
- **reward 校准回流（③）的落地形态**未设计：accept/reject 如何反馈到 reward 权重，留待路径 A 第二轮。
- **双模型成本**：E 任务双跑 = 2× API 调用，放量前需计费评估（沿用 RLVR 任务卡 §5 烧钱闸纪律）。
