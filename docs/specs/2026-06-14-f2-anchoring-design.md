# F2 锚定 pipeline 设计

> 日期: 2026-06-14
> F-stage: F2 Anchor
> 状态: F2 deterministic producer + dry-run-first backfill + gap review export + 相对时间规则层已落地；LLM 发现层后置
> 关联: [自改进标注闭环](2026-06-13-self-improving-annotation-loop.md)（F2 EntityAnchor 是其实体基础设施）、AGENTS.md（F2 标 `partial`）

## 0. 结论

canonical F2 锚定的确定性层已落地：`src/finer/enrichment/entity_anchoring.py` 负责 registry 精确扫描并生成 EntityAnchor + block-level EvidenceSpan，同时基于 `published_at`、显式日期、相对时间规则生成稳定 TemporalAnchor；`scripts/backfill_f2_anchor.py` 负责从 `data/F1_standardized` 生成 `data/F2_anchored`。默认只 dry-run，不重写 data 产物。

历史问题仍成立：F2 不是从零开始，schema 齐全、`entity_registry.resolve()` 现成、legacy `EntityExtractor` 可借鉴、QualityCard 已有；但 LLM 发现层、自动 registry merge、节假日/复杂相对时间解析仍未落地。

EntityAnchor 是优先项：价值最高（直接补强当前在"空 anchor"上跑的 F3）、与自改进闭环 verifier 共用同一个 registry、gap 自然喂闭环回流①。

## 1. 现状（2026-06-14 核查）

| 项 | 状态 |
|---|---|
| F2 schema | ✅ 齐全：`schemas/entity_anchor.py`、QualityCard、TemporalAnchor、EvidenceSpan |
| entity_anchors 产出 | ✅ 确定性层已实现：`build_f2_deterministic_envelope()` 写入 envelope-level anchors |
| temporal_anchors 产出 | ✅ `published_at`、显式日期、相对时间规则层已实现；节假日/复杂表达后置 |
| block.evidence_spans 产出 | ✅ 确定性层已实现：每个 registry alias occurrence 写入 block.evidence_spans |
| F2 backfill CLI | ✅ `scripts/backfill_f2_anchor.py`，默认 `--scope curated-pdf --dry-run` |
| `entity_registry` | ✅ resolve() 现成，但**仅约 60 实体**、精确字典匹配无模糊 |
| legacy `EntityExtractor` | ✅ 可复用：registry 扫描 + LLM 发现两步（`enrichment/__init__.py:156`） |
| 下游 canonical_runner/golden_path | ⚠️ 期望 F2-anchored envelope，当前 anchors 空着跑（`golden_path.py:124` `or []`）——这是 F3→F5 未真正闭环的一部分根因 |

## 2. 探针发现（14 个 curated 策略 PDF，357 block，纯字符串/正则不烧钱）

- **registry 别名精确扫描命中 52.7%**（188/357 block），命中全部正确（京东→JD、A股→000001.SH、泡泡玛特→9992.HK、储能→ENERGY_STORAGE）。
- **裸正则发现"未知实体"不可行**：gap top 被 `AI/ETF/IPO/CPI/CTA` 英文缩写 + `BEEC/BEFCE/FCEDD` 乱码串淹没。**结论：实体发现层必须 registry 精确扫描（确定）+ LLM（发现），不能用正则。**
- **ETF 整类缺口已开始回填**：SOXX/SOXL/SMH/QQQ/IGV/EWY/SPY 已进入 registry，长尾 ETF、品牌词和组织名仍需继续用 report/review loop 收敛。
- **字符 doubling 残留**："加加餐餐""结结合合"每字重复（渲染 OCR 副产品，集中在文件名/标题行），会让 registry 精确扫描漏命中。见 §10。

## 3. EntityAnchor 设计（两层 + gap 路由）

```
block.text
  │
  ├─ 确定性层（registry 精确扫描，0 成本、可审计）
  │    ENTITY_REGISTRY 别名出现在 text → EntityAnchor(高置信)
  │    记录 alias、ticker、market、char offset
  │
  └─ LLM 发现层（仅对确定性层未命中 block，LLM gate 烧钱）
       LLM 抽候选标的 → resolve()
       ├─ 命中 → 补 EntityAnchor(中置信，标记 llm_discovered)
       └─ resolve 不到 → registry-gap 候补 → registry_gaps.jsonl
                                              （人工 confirm → 回填 registry，闭环回流①）
```

设计要点：
- **确定性层先行、可独立跑通**：52% 覆盖、确定、零成本、可审计。第一步只做确定性锚定，验证锚定质量。
- **LLM 发现层必须 gate**：每个未命中 block 一次 LLM，烧钱；先小样本验证发现质量与 gap 信号，再放量（沿用 OCR/harvest 的烧钱闸纪律）。
- **不用裸正则发现实体**（探针已证噪声淹没）。
- **EntityAnchor 与闭环 verifier 共用 `resolve()`**：F2 锚定用什么解析，verifier grounding 就用什么裁决，registry-gap 信号共享，一份 registry 喂两处。

## 4. TemporalAnchor 设计

- 已实现基准：`envelope.published_at`（F1/F0 显式发布时间）→ `anchor_type=published_at`，stable `anchor_id`，`resolution_strategy=explicit_date`，`confidence=1.0`。
- 已实现 block 显式日期：完整年日期（如 `2026-04-01`、`2026年4月1日`）→ `anchor_type=mentioned_at` + temporal EvidenceSpan；中文月日（如 `4月1日`）仅在存在 `published_at` 时用发布年份解析。
- 已实现相对时间规则：`今天/明天/昨天`、`本周/这周/下周/上周`、`下周一` 等周内表达、`本月/下月/上月`，全部仅基于 `published_at` 解析。
- 已实现 guarded numeric event date：`04.08 非农` 这类数字月日只有在数字日期后方短窗口出现 `非农/CPI/PPI/FOMC/议息/财报/业绩/会议` 等事件 cue 时才解析。
- 不从 `ingested_at` 推断发布时间；`published_at` 缺失或不可解析时不伪造 TemporalAnchor。
- 不接受裸数字月日（如 `4.1`、`10/15`），避免把价格、比例、命中率误判成日期。
- 后置：`节后`、交易日/节假日 calendar、复杂自然语言时间表达。
- 后置复杂表达可走规则优先，小样本验证后再考虑 LLM。
- 服务于 F5 ExecutionTiming 四时钟与 F7 timeline。

## 5. EvidenceSpan 设计

- 标记每个 anchor 在 block 内的 char offset（start/end）。
- 挂 provenance：文本层 block 可挂像素级 bbox，渲染 OCR/图片 block 只能挂页/文件级（**继承 [闭环文档](2026-06-13-self-improving-annotation-loop.md) §10 bbox 结论**：当前粒度不均衡，像素级 bbox 是后续增强任务 task_1f0cf016）。
- block.evidence_spans 填充后，下游 F3/F5 的 evidence_span_ids 才有真实指向。

## 6. F2 backfill orchestrator

已新增 F2 锚定入口：

```
读 F1 envelope (data/F1_standardized)
  → 对每个 block: EntityAnchor(确定性扫描[+LLM 发现]) + EvidenceSpan
  → 对 envelope/block: TemporalAnchor(基于 published_at + 高精度显式日期 + 相对时间规则)
  → 写回 envelope.entity_anchors / temporal_anchors / block.evidence_spans
  → 落 data/F2_anchored（JSON，可逆）
```

- 输入 schema：ContentEnvelope（F1）
- 输出 schema：F2-anchored ContentEnvelope（填充 anchors）
- 幂等、可 dry-run、可只挑增量 envelope（沿用 F1 backfill 模式）
- 当前入口：`python scripts/backfill_f2_anchor.py --scope curated-pdf --dry-run`
- 当前默认 scope：F1 `source_type=pdf` 且 F0 `source_type` 属于 `livestream_audio/research_report/weekly_strategy`
- 当前不接 deprecated `pipeline/orchestrator.py`，不接 F5 文件管线。

## 7. 与自改进闭环衔接

| 闭环要素 | F2 如何对接 |
|---|---|
| registry resolve | F2 EntityAnchor 确定性层/发现层直接用，与 verifier grounding 同源 |
| registry-gap 回流① | F2 发现层 resolve 不到的标的 → `registry_gaps.jsonl` → 人工 confirm 回填 → 命中率逐轮升 |
| verifier 三态 | F2 anchor 的置信度（确定性层高/发现层中/gap）天然映射 grounded/registry-gap |

**建 F2 EntityAnchor = 给闭环打实体基础设施，两条线并一条。**

## 8. 分步实施

| 步 | 内容 | 烧钱 | 验收 |
|---|---|---|---|
| 1 | EntityAnchor **确定性扫描** + 小样本 | 否 | ✅ 14 PDF 锚定命中 52.7%、anchor char offset 正确、单测覆盖 |
| 2 | registry 扩充：ETF 整类 + KOL 黑话（回流①第一批） | 否 | 命中率提升；新增别名 resolve 往返 |
| 3 | EntityAnchor **LLM 发现 + gap 路由** + 小样本 | **是**（gate） | gap 正确进 registry_gaps；无幻觉锚定 |
| 4 | TemporalAnchor（published_at + 高精度显式日期） | 否 | ✅ curated-pdf temporal=33/time spans=19；all-local temporal=566/time spans=361 |
| 4b | TemporalAnchor（相对时间规则解析） | 否 | ✅ curated-pdf temporal=501/time spans=487；all-local temporal=1246/time spans=1041 |
| 5 | EvidenceSpan + bbox 挂接 | 否 | ✅ char offset + provenance 粒度正确，bbox/page/file granularity 单测覆盖 |
| 6 | F2 backfill orchestrator 串联 + 落 F2_anchored | LLM 发现部分 | ✅ dry-run-first CLI 已落地；全量写入需另行授权 |

当前已完成确定性锚定 + `published_at` 时间锚 + 高精度显式日期锚 + 相对时间规则层 + dry-run-first backfill。下一步再决定节假日/复杂时间表达、LLM 发现层和是否全量写入。

## 8.1 当前 dry-run 口径（2026-06-24）

命令：

```bash
python scripts/backfill_f2_anchor.py --scope curated-pdf --dry-run
```

结果：

| 指标 | 数值 |
|---|---:|
| scanned F1 envelopes | 401 |
| selected curated PDFs | 14 |
| existing F2 artifacts | 14 |
| todo writes | 0 |
| blocks | 357 |
| hit blocks | 190 (53.2%) |
| entity anchors | 210 |
| temporal anchors | 501 |
| temporal evidence spans | 487 |
| evidence spans | 1592 |

本次只记录 dry-run 口径，不重写 `data/F2_anchored`。

## 8.2 当前诊断输出（2026-06-24）

`scripts/backfill_f2_anchor.py` 已从单纯 dry-run 统计扩展为证据质量诊断入口：

- stdout 保留 totals、source coverage、zero-anchor / low-hit / gap candidate 样本，长列表默认截断。
- `--report-out <path>` 输出完整 JSON report，包含 `zero_anchor_diagnostics`、`low_hit_diagnostics`、`worst_f0_source_types`、`worst_f1_source_types`、`temporal_rules`、`temporal_strategies`、`temporal_granularity`、`gap_candidates`。
- `--gap-candidates-out <path>` 仅在显式传入时输出人工 review JSONL；字段包含 `alias_candidate`、source/block/path/context、`reason`、`candidate_type`、`score`、空 `review_status`。
- gap review JSONL 不包含 `ticker` / `market` / `entity_id`，不写 `registry_gaps.jsonl`，不改 entity registry；后续必须人工确认后再进入 registry 回填流程。
- gap candidate generator 已前置过滤财务指标/技术指标/泛行业词/动作短语，例如 `RSI`、`CAGR`、`DRAM`、`半导体`、`半导体设备`、`反弹买保险`；保留更像实体的 alias candidate 供人工排序。
- low-hit diagnostics 已细分 missed block 根因：`registry_gap_candidate`、`financial_text_no_candidate`、`no_financial_context`、`non_financial_or_macro`、`ocr_thin`、`empty_text`，每个 low-hit envelope 附带 `missed_block_reasons` 和最多 3 条 `missed_block_samples`。
- `scripts/build_f2_gap_review_batch.py` 可将全量 gap candidates 去重、排序并二次过滤明显非实体短语，生成小批次人工 review JSONL；每行带 `support_count` 和最多 3 条 supporting examples，默认只打印计划，显式 `--out` / `--markdown-out` 才写文件；传入 `--dpo-dir data/dpo` 时会按已存在的 `registry_gaps.jsonl` alias 跳过已人工确认候选，避免下一轮重复 review。
- `scripts/apply_f2_gap_reviews.py` 是人工确认后的 dry-run-first apply 入口；只处理 `review_status=approved` 的行，默认只规划，`--write --reviewer-id <id>` 才通过 `AnnotationStore.append_registry_gap()` 追加到 `registry_gaps.jsonl`。
- `scripts/check_f2_coverage_regression.py` 是只读 coverage gate；默认检查 `curated-pdf` 与 `all-local` 当前基线，约束 selected/block/hit/anchor/span/zero-anchor 下限或上限，并校验 gap candidate schema 不出现伪 grounded 字段。

## 8.3 registry 回填结果（2026-06-24）

已将人工确认或公开资料核对后带 ticker/market 的 F2 registry gaps 回填到 `ENTITY_REGISTRY`：

| alias | ticker | market |
|---|---|---|
| 新华保险 | 1336.HK | HK |
| 民生银行 | 1988.HK | HK |
| 吉利汽车 | 0175.HK | HK |
| 蓝思科技 | 6613.HK | HK |
| 中国光大银行 | 6818.HK | HK |
| 华能国际电力股份 | 0902.HK | HK |
| 中宠股份 | 002891.SZ | CN |
| 美光科技 / MU | MU | US |
| 希捷科技控股有限公司 | STX | US |
| 南亚科技股份有限公司 | 2408.TW | TW |
| VIX / 恐慌指数 | VIX | US |
| KOSPI / 韩国综合指数 | KS11 | KR |
| WTI / WTI原油 | WTI | COMMODITY |
| QQQ / 纳指100ETF | QQQ | US |
| SOXX / SOXL / SMH | SOXX / SOXL / SMH | US |
| IGV / EWY / SPY | IGV / EWY / SPY | US |
| SP500 / 标普500 | SPX | US |
| DXY / 美元指数 | DXY | US |
| TCL科技 | 000100.SZ | CN |
| ANTA / 安踏体育 | 2020.HK | HK |
| 速腾聚创 / RoboSense | 2498.HK | HK |

另经公开指数资料核对，已将 `费城半导体`、`费城半导体指数`、`PHLX Semiconductor`、`SOX` 回填为 `SOX / US / index`。不把 `SOXX` 这类 ETF 与 `SOX` 指数混写。

`曹操出行` 已进入 `registry_gaps.jsonl` sidecar，但缺少确认后的 ticker/market，暂不进入 `ENTITY_REGISTRY`。

回填后 all-local dry-run 新基线：

| 指标 | 回填前 | 回填后 |
|---|---:|---:|
| selected envelopes | 205 | 205 |
| blocks | 3051 | 3051 |
| hit blocks | 416 | 507 |
| hit rate | 13.6% | 16.6% |
| entity anchors | 444 | 564 |
| temporal anchors | — | 1246 |
| temporal evidence spans | — | 1041 |
| evidence spans | 1507 | 2813 |
| zero-anchor items | 92 | 71 |

`scripts/check_f2_coverage_regression.py` 的 `all-local` gate 已抬到回填后基线。当前 all-local report 导出 59 条 raw gap candidates；`scripts/build_f2_gap_review_batch.py --dpo-dir data/dpo` 对当前导出的候选批次已选中 0 条。

当前 all-local low-hit missed-block reason 分布：

| reason | missed blocks |
|---|---:|
| no_financial_context | 482 |
| financial_text_no_candidate | 214 |
| ocr_thin | 206 |
| registry_gap_candidate | 179 |
| non_financial_or_macro | 62 |

按 source 分桶：

- F0 source_type：上述 low-hit missed blocks 全部来自 `unclassified`。
- F1 source_type：`image` 贡献绝大多数 missed blocks（例如 `no_financial_context=462`、`registry_gap_candidate=170`、`ocr_thin=196`），`pdf` 仅有少量尾部缺口（例如 `no_financial_context=20`、`registry_gap_candidate=9`）。

解释：当前 low-hit 的最大根因不是缺少可人工确认的 registry gap，而是 unclassified/image 产物里大量 block 无金融上下文或 OCR 过薄；registry 扩充仍有价值，但应让 review batch 先保持 0 噪声，再转向 F1/OCR 与 source classification 诊断。

## 8.4 显式日期 + 相对时间 TemporalAnchor 结果（2026-06-24）

规则边界：

- 接受：`YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY.MM.DD`、`YYYY年M月D日`。
- 接受：`M月D日`，但必须有可解析 `published_at`，并用发布年份补全。
- 接受：`今天/明天/昨天`、`本周/这周/下周/上周`、`下周一`、`本月/下月/上月`，但必须有可解析 `published_at`。
- 接受：`04.08 非农` 这类数字月日 + 事件 cue；不接受没有事件 cue 的裸数字月日。
- 拒绝：`4.1`、`10/15` 等裸数字月日；本地 F1 中这类形态大量是价格、比例、命中率或表格分数。

dry-run 新基线：

| scope | selected | temporal anchors | temporal evidence spans | total evidence spans |
|---|---:|---:|---:|---:|
| curated-pdf | 14 | 501 | 487 | 1592 |
| all-local | 205 | 1246 | 1041 | 2813 |

all-local temporal rule 分布：

| rule | count |
|---|---:|
| relative_week_from_published_at | 318 |
| relative_day_from_published_at | 310 |
| full_date | 307 |
| published_at | 205 |
| month_day_from_published_year | 54 |
| relative_weekday_from_published_at | 46 |
| numeric_month_day_with_event_cue | 5 |
| relative_month_from_published_at | 1 |

## 9. 烧钱点与红线

- **LLM 发现层**是唯一烧钱点：每未命中 block 一次调用。先 `--max` 小样本验证，再放量；用户授权后全量。
- 相对时间解析只用规则层，不从 `ingested_at` 或当前时间推断缺失 `published_at`。
- registry 回填需**人工 confirm**（沿用 `append_registry_gap` 既有约束，标注端不直写 registry）。
- 不用裸正则/LLM 直接造 ticker——resolve 不到就进 gap，不硬编。
- F2 不改 F1 envelope 的 blocks/quality_card（只追加 anchors），不动 F0-F8 顶层命名。

## 10. Open Issues / 副产品

- **字符 doubling（渲染 OCR 副产品）**：文件名/标题行出现"加加餐餐"逐字重复。若正文也有，会压低 registry 精确扫描命中率。需核查 doubling 范围；属 F1 OCR 残留，独立于 F2，但影响 F2 命中率——建议在步骤 1 顺带统计 doubling 对命中的影响。
- **复杂时间表达**：`节后`、交易日/节假日 calendar、事件相对时间（如“财报后第二天”）仍需规则解析与 fixture。
- **LLM 发现层选型**：发现层用 Qwen-Max（结构化抽取对口）还是 GLM-5.1，待小样本 bake-off（沿用闭环 §5：不用 MiMo Pro）。
- **registry 规模**：当前 ~60 实体，对 KOL 全量内容覆盖率待测（探针仅 14 PDF）；图片类 387 envelope 的命中率未测。
