# F2 锚定 pipeline 设计

> 日期: 2026-06-14
> F-stage: F2 Anchor
> 状态: proposed（现状已核查 + 真实数据探针）
> 关联: [自改进标注闭环](2026-06-13-self-improving-annotation-loop.md)（F2 EntityAnchor 是其实体基础设施）、AGENTS.md（F2 标 `partial`）

## 0. 结论

canonical F2 锚定**从未产出**：全部 401 个 F1 envelope，quality_card 100%（F1 产），但 entity_anchors / temporal_anchors / block.evidence_spans **全为 0%**。"推 F2"= 建 F2 锚定 pipeline，是实质开发。但不是从零——schema 齐全、`entity_registry.resolve()` 现成、legacy `EntityExtractor` 可借鉴、QualityCard 已有。

EntityAnchor 是优先项：价值最高（直接补强当前在"空 anchor"上跑的 F3）、与自改进闭环 verifier 共用同一个 registry、gap 自然喂闭环回流①。

## 1. 现状（2026-06-14 核查）

| 项 | 状态 |
|---|---|
| F2 schema | ✅ 齐全：`schemas/entity_anchor.py`、QualityCard、TemporalAnchor、EvidenceSpan |
| entity_anchors 产出 | ❌ 0/401 |
| temporal_anchors 产出 | ❌ 0/401 |
| block.evidence_spans 产出 | ❌ 0/401 |
| `entity_registry` | ✅ resolve() 现成，但**仅约 60 实体**、精确字典匹配无模糊 |
| legacy `EntityExtractor` | ✅ 可复用：registry 扫描 + LLM 发现两步（`enrichment/__init__.py:156`） |
| 下游 canonical_runner/golden_path | ⚠️ 期望 F2-anchored envelope，当前 anchors 空着跑（`golden_path.py:124` `or []`）——这是 F3→F5 未真正闭环的一部分根因 |

## 2. 探针发现（14 个 L0 策略 PDF，357 block，纯字符串/正则不烧钱）

- **registry 别名精确扫描命中 52%**（188/357 block），命中全部正确（京东→JD、A股→000001.SH、泡泡玛特→9992.HK、储能→ENERGY_STORAGE）。
- **裸正则发现"未知实体"不可行**：gap top 被 `AI/ETF/IPO/CPI/CTA` 英文缩写 + `BEEC/BEFCE/FCEDD` 乱码串淹没。**结论：实体发现层必须 registry 精确扫描（确定）+ LLM（发现），不能用正则。**
- **ETF 整类缺失**：registry 无 SOXX/SOXL/SMH/QQQ 等 ETF；策略稿大量用 ETF。是资产类别级缺口，不是个别黑话。
- **字符 doubling 残留**："加加餐餐""结结合合"每字重复（渲染 OCR 副产品，集中在文件名/标题行），会让 registry 精确扫描漏命中。见 §10。

## 3. EntityAnchor 设计（两层 + gap 路由）

```
block.text
  │
  ├─ L1 确定层（registry 精确扫描，0 成本、可审计）
  │    ENTITY_REGISTRY 别名出现在 text → EntityAnchor(高置信)
  │    记录 alias、ticker、market、char offset
  │
  └─ L2 发现层（仅对 L1 未命中 block，LLM gate 烧钱）
       LLM 抽候选标的 → resolve()
       ├─ 命中 → 补 EntityAnchor(中置信，标记 llm_discovered)
       └─ resolve 不到 → registry-gap 候补 → registry_gaps.jsonl
                                              （人工 confirm → 回填 registry，闭环回流①）
```

设计要点：
- **L1 先行、可独立跑通**：52% 覆盖、确定、零成本、可审计。第一步只做 L1，验证锚定质量。
- **L2 必须 gate**：每个未命中 block 一次 LLM，烧钱；先小样本验证发现质量与 gap 信号，再放量（沿用 OCR/harvest 的烧钱闸纪律）。
- **不用裸正则发现实体**（探针已证噪声淹没）。
- **EntityAnchor 与闭环 verifier 共用 `resolve()`**：F2 锚定用什么解析，verifier grounding 就用什么裁决，registry-gap 信号共享，一份 registry 喂两处。

## 4. TemporalAnchor 设计

- 基准：`envelope.published_at`（绝对锚点）+ `block.timestamp`（部分已有）。
- 解析 block 内相对时间表达（"下周""节后""04.08 非农"）→ 绝对时间区间。
- 优先规则解析（确定、可审计）；复杂表达可后置 LLM。
- 服务于 F5 ExecutionTiming 四时钟与 F7 timeline。

## 5. EvidenceSpan 设计

- 标记每个 anchor 在 block 内的 char offset（start/end）。
- 挂 provenance：文本层 block 可挂像素级 bbox，渲染 OCR/图片 block 只能挂页/文件级（**继承 [闭环文档](2026-06-13-self-improving-annotation-loop.md) §10 bbox 结论**：当前粒度不均衡，像素级 bbox 是后续增强任务 task_1f0cf016）。
- block.evidence_spans 填充后，下游 F3/F5 的 evidence_span_ids 才有真实指向。

## 6. F2 orchestrator

新增 F2 锚定入口（脚本或 pipeline stage）：

```
读 F1 envelope (data/F1_standardized)
  → 对每个 block: EntityAnchor(L1[+L2]) + EvidenceSpan
  → 对 envelope: TemporalAnchor(基于 published_at)
  → 写回 envelope.entity_anchors / temporal_anchors / block.evidence_spans
  → 落 data/F2_anchored（JSON，可逆）
```

- 输入 schema：ContentEnvelope（F1）
- 输出 schema：F2-anchored ContentEnvelope（填充 anchors）
- 幂等、可 dry-run、可只挑增量 envelope（沿用 F1 backfill 模式）

## 7. 与自改进闭环衔接

| 闭环要素 | F2 如何对接 |
|---|---|
| registry resolve | F2 EntityAnchor L1/L2 直接用，与 verifier grounding 同源 |
| registry-gap 回流① | F2 L2 resolve 不到的标的 → `registry_gaps.jsonl` → 人工 confirm 回填 → 命中率逐轮升 |
| verifier 三态 | F2 anchor 的置信度（L1 高/L2 中/gap）天然映射 grounded/registry-gap |

**建 F2 EntityAnchor = 给闭环打实体基础设施，两条线并一条。**

## 8. 分步实施

| 步 | 内容 | 烧钱 | 验收 |
|---|---|---|---|
| 1 | EntityAnchor **L1**（registry 扫描）+ 小样本 | 否 | 14 PDF 锚定命中 ≈52%、anchor char offset 正确、0 误锚 |
| 2 | registry 扩充：ETF 整类 + KOL 黑话（回流①第一批） | 否 | 命中率提升；新增别名 resolve 往返 |
| 3 | EntityAnchor **L2**（LLM 发现 + gap 路由）+ 小样本 | **是**（gate） | gap 正确进 registry_gaps；无幻觉锚定 |
| 4 | TemporalAnchor（规则解析） | 否 | 相对时间→绝对正确 |
| 5 | EvidenceSpan + bbox 挂接 | 否 | char offset + provenance 粒度正确 |
| 6 | F2 orchestrator 串联 + 落 F2_anchored | L2 部分 | dry-run→小样本→全量；envelope anchors 非空 |

先做步骤 1（L1，零成本跑通），用真实命中校准，再决定 L2 和全量节奏。

## 9. 烧钱点与红线

- **L2 LLM 发现**是唯一烧钱点：每未命中 block 一次调用。先 `--max` 小样本验证，再放量；用户授权后全量。
- registry 回填需**人工 confirm**（沿用 `append_registry_gap` 既有约束，标注端不直写 registry）。
- 不用裸正则/LLM 直接造 ticker——resolve 不到就进 gap，不硬编。
- F2 不改 F1 envelope 的 blocks/quality_card（只追加 anchors），不动 F0-F8 顶层命名。

## 10. Open Issues / 副产品

- **字符 doubling（渲染 OCR 副产品）**：文件名/标题行出现"加加餐餐"逐字重复。若正文也有，会压低 registry 精确扫描命中率。需核查 doubling 范围；属 F1 OCR 残留，独立于 F2，但影响 F2 命中率——建议在步骤 1 顺带统计 doubling 对命中的影响。
- **L2 LLM 选型**：发现层用 Qwen-Max（结构化抽取对口）还是 GLM-5.1，待小样本 bake-off（沿用闭环 §5：不用 MiMo Pro）。
- **registry 规模**：当前 ~60 实体，对 KOL 全量内容覆盖率待测（探针仅 14 PDF）；图片类 387 envelope 的命中率未测。
