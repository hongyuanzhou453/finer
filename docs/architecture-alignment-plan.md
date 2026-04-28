# Finer 架构对齐规划 v2.0

> 创建: 2026-04-27 | 更新: 2026-04-28 (F0-F8 canonical 迁移)
> 目标: 将 Finer 从"直接抽取 TradeAction 的原型系统"，对齐到 F0-F8 canonical pipeline

---

## 1. 对齐原则

### 1.1 不把模型训练当作第一步

当前核心瓶颈不是缺更强模型，而是中间语义层不清楚。优先级:

1. 先统一原始内容标准化结构（F1 Standardize）
2. 再定义投资意图 schema（F3 Intent）
3. 再定义 policy 和交易动作映射（F4 Policy）
4. 最后才进入 SFT/DPO/LoRA 等训练（F+）

### 1.2 区分三种完成度

| 状态 | 含义 |
|---|---|
| Schema 完成 | 数据结构存在，字段可校验 |
| 逻辑完成 | 核心算法/规则/模型调用可运行 |
| 端到端完成 | 输入、存储、API、前端、测试全链路打通 |

### 1.3 五类成熟度

详见 ARCHITECTURE.md 2.4 节。简表:

| 状态 | 含义 |
|---|---|
| implemented | 端到端可用 |
| partial | 核心逻辑存在，有关键缺口 |
| placeholder | 占位实现，不执行真实逻辑 |
| mock-backed | 真实路径存在但 fallback 到随机/假数据 |
| contract-only | 仅有 Schema，无实现 |
| missing | 完全不存在 |

---

## 2. 当前架构与目标架构差异

### 2.1 当前实际路径（LEGACY — deprecated）

```
F0 ingestion (飞书/B站/微信)
  → F1 enrichment (话题/实体 — 不完整)
  → F1 perception / OCR / ASR
  → F2 aggregation summary
  → F5 direct TradeAction extraction ← 跳过 F3 Intent, 跳过 F4 Policy
  → F6 review / RLHF
  → F7 timeline (by TradeAction, 不是 by Intent)
  → F8 backtest (pipeline placeholder)
```

### 2.2 目标路径（CANONICAL）

```
F0 Intake
  → F1 Standardize (ContentEnvelope + ContentBlock)
  → F2 Anchor (QualityCard + TemporalAnchor + EntityAnchor + EvidenceSpan)
  → F3 Intent (NormalizedInvestmentIntent — 四轴: direction/actionability/position_delta_hint/conviction)
  → F4 Policy (5 层 policy: Global→Style→Risk→Persona→Correction)
  → F5 Execute (TradeAction +intent_id +policy_id +evidence_span_ids)
  → F6 Review (RLHF + 人工复核)
  → F7 Timeline (KOLTimeline + ViewpointState + TargetOpinionGraph)
  → F8 Backtest (Portfolio 模拟 + KOL 评分)
```

### 2.3 主要差距

| # | 差距 | 当前状态 | 目标 |
|---|---|---|---|
| 1 | F1 标准化不完整 | 非文本内容 block 化缺失 | 图片/聊天/文档/音频统一进 ContentBlock |
| 2 | F3 仅有 rule-based 原型 | 硬编码关键词，无 LLM 调用 | LLM-based Intent 提取器 |
| 3 | F4 整个层缺失 | 代码不存在 | 5 层 policy 映射 |
| 4 | F5 直接面对原始文本 | 绕过 F3/F4 | 只接收 F4 的 PolicyMappedIntent |
| 5 | F5 缺 intent_id/policy_id | TradeAction 孤立 | 完整上游 ID 追溯 |
| 6 | F7 无 ViewpointState | 只有 TradeAction 列表 | 观点状态机 + 分歧图谱 |
| 7 | F8 pipeline placeholder | 不调用 BacktestEngine | 端到端回测闭环 |

---

## 3. 分阶段任务拆分

### Phase A: F-stage 契约冻结 (P0)

**目标**: 定义 F1-F5 的完整 Schema 契约，先不大改现有代码。

**任务**:
1. 确认 F1 `ContentEnvelope`, `ContentBlock` schema 为最终版本
2. 确认 F2 `QualityCard`, `TemporalAnchor`, `EntityAnchor`, `EvidenceSpan` schema
3. 确认 F3 `NormalizedInvestmentIntent` schema
4. 新建 F4 `PolicyMappingResult` schema（此前不存在）
5. 在 F5 `TradeAction` 中新增 `intent_id`, `policy_id`, `evidence_span_ids` 字段
6. 更新 `docs/specs/f-stage-contracts.md` 为每个 F-stage 的权威契约

**验收**:
- 每个 F-stage 的输入/输出 Schema 可序列化/反序列化
- F5 TradeAction schema 包含 intent_id, policy_id, evidence_span_ids
- 所有 Schema 有完整 Field(description=...) 注释

### Phase B: F1 标准化 MVP (P0)

**目标**: 把复杂文件统一清洗为 envelope/block。

**任务**:
1. 图片 OCR 输出从 Markdown 升级为 ContentBlock list（含标题/段落/表格/图表/image_region）
2. 飞书聊天记录按消息、说话人、时间拆 ContentBlock
3. 音频转录按语义段落和时间戳拆 ContentBlock
4. PDF/文档按标题、段落、表格拆 ContentBlock
5. 为每个 ContentBlock 生成基本质量信息（可读性、完整性）

**验收**:
- 至少支持图片、聊天记录、飞书文档、音频转录四类输入
- 每个 ContentBlock 能追溯到原始文件或原始消息
- 低质量 block 被标记但不丢弃

### Phase C: F2 锚定 (P0)

**目标**: 解决时间错配和标的错配。

**任务**:
1. 实现 TemporalAnchor 四类时间字段
2. 相对时间解析（"上周/这周/下个月"）加入 confidence
3. EntityAnchor 从"文本识别"升级为"公司/股票/板块标准化"
4. 质量门控：gate = pass/soft_pass/review/reject
5. 对无法解析的时间和实体进入 review 队列

**验收**:
- "上周坚定抄底光模块，这周资金回归"能解析相对时间
- 同一内容中多个时间表达能分别落锚
- 标的、板块、指数可区分

### Phase D: F3 Intent 提取 (P0)

**目标**: 用 LLM 替换 rule-based 原型，实现 Intent 提取。

**任务**:
1. 实现 LLM-based IntentExtractor（Instructor + Qwen-Max）
2. 写 prompt 模板（direction/actionability/position_delta_hint/conviction 四轴输出）
3. 接入 F2 质量门控：仅 gate ≥ soft_pass 的 envelope 进入提取
4. 输出 ambiguity_notes 保留模糊样本
5. 建立 F3 人工复核面板字段

**验收**:
- "我看好宁德时代" → actionability=opinion, position_delta_hint=none
- "我加仓宁德时代" → actionability=explicit_action, position_delta_hint=add
- "目前依然持有，稍微加仓一点" 不被映射为全仓买入
- F3 输出能追溯到 F2 evidence_span_ids

### Phase E: F4 Policy 映射 (P1)

**目标**: 建立 Intent→TradeAction 的唯一合法桥接。

**任务**:
1. 实现 Global Base Policy（通用金融语言→动作基准映射）
2. 定义 Style Archetype Policy（短线/景气/价值/烟蒂）
3. 定义 Risk Preference Policy（激进/均衡/保守）
4. 为 KOL 生成 Persona Policy 草案（从 200-1000 条历史内容）
5. 实现 PolicyMapper: Intent → PolicyMappedIntent

**验收**:
- 同一句"加仓"在不同风格 KOL 下得到不同持仓期/动作强度
- F3 Intent 不放仓位比例，F4 Policy 生成默认仓位假设
- 所有 policy 映射可审计（保留 policy_version 和 mapping_rationale）

### Phase F: F7 时间线与观点状态机 (P2)

**目标**: 从"动作列表"升级为"观点演化"。

**任务**:
1. 实现同一 KOL 同一标的的 Intent 串联（ViewpointState）
2. 维护观点状态：增强/减弱/反转/退出
3. 实现多 KOL 同标的 TargetOpinionGraph
4. 移除 opinions.py 的 mock fallback 或加显式标记

**验收**:
- 可展示腾讯从"不看好 600"到"500 附近逐渐加仓"的演化
- 可展示福寿园从"现金模式看好"到"财报不及预期减仓"的演化
- 可对同一标的聚合多个 KOL 的不同观点

### Phase G: F8 回测闭环 (P2)

**目标**: 将 F5 TradeAction 真正接入回测和 KOL 评分。

**任务**:
1. F8 pipeline 调用真实 BacktestEngine（修复 placeholder）
2. 明确 effective_trade_at 和交易价格选择规则
3. 支持单 KOL、同标的多 KOL、共识策略回测
4. KOL 评分从 mock 升级为真实 pipeline 输出
5. 回测结果回写 intent/action/profile

**验收**:
- 指定 KOL + 时间范围可一键生成 timeline 和 backtest
- 回测结果能回溯到 intent、block、原文证据
- KOL 评分不是 mock 数据

---

## 4. Policy 分层设计

### 4.1 为什么不能只用统一 policy

同一句"加仓"在不同 KOL 风格下含义不同:
- 短线割头皮: 加仓可能只代表日内资金试探
- 板块景气流: 加仓可能代表对产业趋势确认
- 价值投资流: 加仓可能代表估值进入安全边际

### 4.2 5 层 Policy 结构

```
F4 PolicyMapper
  Global Base Policy          — 通用金融语言→动作基准映射（人工规则）
    → Style Archetype Policy  — 短线/景气/价值/烟蒂等风格差异
      → Risk Preference Policy — 激进/均衡/保守
        → KOL Persona Policy   — 个体 KOL 的口头禅、动作含义
          → Content Correction  — 当前上下文的临时修正
```

| 层级 | 作用 | 生成方式 |
|---|---|---|
| Global Base | 通用语言→意图基准映射 | 人工规则 + 少量标注 |
| Style Archetype | 风格差异 | 聚类 + 人工命名 |
| Risk Preference | 止损和仓位习惯 | 从历史内容统计 |
| KOL Persona | 个体语义映射 | 200-1000 条内容总结 |
| Content Correction | 上下文临时修正 | F3 抽取时动态生成 |

---

## 5. 多源内容处理策略

| 来源 | 难点 | F1 处理重点 |
|---|---|---|
| 图片策略 | OCR、版面、表格、图表 | 多 block 拆分，保留 image_region |
| 长聊天记录 | 多人混杂、回复关系 | 按 KOL、话题、时间窗口重组 |
| 飞书链接文档 | 文档结构、嵌入图片 | 拉取正文 + 子资源 + 引用关系 |
| PDF | 页眉页脚、表格、跨页 | 页块、表格块、标题层级 |
| 音频转录 | 口语、断句、ASR 错误 | 语义断句、时间戳、说话人 |

---

## 6. 质量卡与门控机制

### 6.1 六维质量卡（F2）

| 维度 | 目标 | 判断方式 |
|---|---|---|
| completeness | 内容完整 | 是否缺页、缺图、截断 |
| readability | 文本可读 | OCR/ASR 乱码率 |
| structure | 结构恢复 | 标题/表格/段落是否识别 |
| temporal_resolvability | 时间可解析 | 是否有发布/指称/生效时间 |
| entity_resolvability | 标的可链接 | 股票名/代码能否标准化 |
| evidence_fidelity | 证据可追溯 | intent 能否回到原文位置 |

### 6.2 门控等级

| 等级 | 条件 | 处理 |
|---|---|---|
| pass | 关键字段完整，证据可追溯 | 自动进入 F3 |
| soft_pass | 小缺陷但不影响意图 | 进入 F3，标注 warning |
| review | 时间/标的/动作存在歧义 | 进入 F6 人工复核 |
| reject | 内容不可读或证据断裂 | 不进 F3，仅存档 |

---

## 7. 模型/API/训练分工

| 方案 | 适合做什么 | 不适合做什么 |
|---|---|---|
| **API 模型** (Qwen/GLM) | F1 多模态标准化、F3 Intent 初始抽取、F4 persona 总结 | 批量处理、需稳定输出的场景 |
| **规则/本地模型** | F2 文件完整性检测、实体标准化、基础质量评估 | 复杂语义理解 |
| **开源基座微调** | 后期: F3 intent 分类、KOL 风格分类 | 第一阶段就做 |

**推荐训练路线**:
```
Phase 0: API + 规则跑通 F1/F2/F3
Phase 1: 人工复核 300-500 个高质量 F3 intent 样本
Phase 2: Few-shot prompt library
Phase 3: 导出 SFT 数据，微调小模型做 intent 分类/抽取
Phase 4: 用 RLHF 偏好数据做 DPO
Phase 5: 用 F8 回测结果做 F4 policy 评估
```

---

## 8. 近期优先级

### P0: 必须先做
1. F3 LLM-based IntentExtractor（替换 rule-based 原型）
2. F5 TradeAction 增加 intent_id / policy_id / evidence_span_ids 字段
3. F4 Global Base Policy MVP（最小可用版本，先做一层）
4. F3→F4→F5 端到端集成测试（选 3-5 条真实 KOL 内容）

### P1: 紧随其后
1. F4 完整 5 层 policy
2. F2 TemporalAnchor 自动解析
3. F1 非文本内容 block 化
4. F8 pipeline 修复 placeholder

### P2: 再做
1. F7 ViewpointState + 分歧图谱
2. 移除 mock fallback 或加显式环境标记
3. F+ 训练数据生成

### P3: 数据稳定后
1. SFT/DPO 训练
2. 本地模型替代部分 API 调用
3. 自动 policy 优化

---

## 9. 立即可执行的下一批任务

1. **`feat(f3): LLM-based IntentExtractor`**
   - 用 Instructor + Qwen-Max 实现 Intent 提取
   - 写 F3 prompt 模板
   - 从 F2 envelope 生成 F3 NormalizedInvestmentIntent

2. **`feat(f5): add intent_id and policy_id to TradeAction`**
   - TradeAction schema 新增 intent_id, policy_id, evidence_span_ids
   - 更新 contracts.ts 同步

3. **`feat(f4): Global Base Policy MVP`**
   - 新建 `policy/` 模块
   - 新建 PolicyMappingResult schema
   - 实现 Global Base Policy（单层，不先做 5 层）

4. **`fix(f8): connect pipeline orchestrator to BacktestEngine`**
   - 修复 `pipeline/orchestrator.py` 中的 L8 placeholder
   - 让 `_run_f8_backtest()` 真正调用 BacktestEngine

5. **`test: F3→F4→F5 end-to-end integration`**
   - 选 5 条真实 KOL 飞书消息
   - 跑通 F1→F2→F3→F4→F5→F8 全链路
   - 对比 rule-based vs LLM-based vs 人工标注

---

## 10. 判断标准

如果一个改造不能回答下面任一问题，就不应优先做:

1. 这条 TradeAction 来自哪段原始证据？（evidence_span_ids）
2. 这个时间是发布时间、提及时间，还是交易生效时间？（TemporalAnchor）
3. 这个 KOL 的"加仓"在他的个人语境中代表什么？（F4 Policy）
4. 这个 intent 是观点、隐式动作，还是明确动作？（F3 Intent）
5. 这个样本质量是否足够进入模型训练？（F2 QualityCard）
6. 这个回测结果能否回溯到原始 KOL 内容？（F8 → F5 → F3 → F2 → F1 → F0）

---

## 11. 总结

Finer 当前最大问题是 **F3→F4→F5 未闭环**:

- F3 Intent 只有 rule-based 原型，没有 LLM 提取器
- F4 Policy 整层缺失
- F5 TradeAction 直接面对原始文本，跳过 F3/F4

在这三层稳定前，不建议把重点放在大规模训练或自动交易 policy 优化上。正确顺序是:

1. **F3**: 用 LLM 标准化 Intent 提取
2. **F4**: 建立 Intent→TradeAction 的 policy 桥接
3. **F5**: TradeAction 携带完整上游 ID 追溯
4. 然后才进入 F+ 训练闭环

---

*更新: 2026-04-28 | Canonical pipeline: F0-F8 | 旧 L/V 命名参考 docs/ARCHITECTURE.md Legacy Mapping*
