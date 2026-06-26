# F2 锚定命中率优化 — 候选降噪 + registry 插入 + 中文候选生成测定

> 日期: 2026-06-26
> F-stage: F2 (enrichment / entity anchoring)
> 分支: docs/f0-review-fixes
> 关联: [canonical 收口批次](2026-06-25-canonical-collar-batch-a.md)、[MiMo 图片/PDF 接入 F1](2026-06-13-mimo-image-pdf-f1-intake.md)

## 1. 概述

承接审计 REVISE 批次 C 的「F1 image/OCR 命中率（all-local 16.5%）」条目，对 F2 实体锚定的 all-local cohort 命中率做了一轮提升：候选流降噪 + 6 个人工核验实体插入 registry，**命中率 16.50% → 17.70%（+1.2pp）**，零锚文档 71→68。随后尝试用规则改进中文实体候选生成以规模化拉命中率，**经真实语料测定为净负（precision ~6%）/零召回，已 revert**；结论是中文候选生成应走 constrained-LLM 路线（与 F1.5 架构方向一致），非规则。

## 2. 变更清单

| 文件 | 类型 | commit | 说明 |
|------|------|--------|------|
| `scripts/backfill_f2_anchor.py` | 修改 | `c95649f7` | `_NOISY_UPPER_TOKENS` 扩展：财务指标/时间/货币/IP token 入 stoplist |
| `tests/test_backfill_f2_anchor.py` | 修改 | `c95649f7` | `test_gap_candidates_filter_metric_time_and_currency_tokens` |
| `src/finer/entity_registry.py` | 修改 | `95f849f9` | 插入 6 实体 / 12 alias（中金/曹操出行/高盛/MUFG/SAP/CRWV） |
| `tests/test_entity_anchoring.py` | 修改 | `95f849f9` | `test_f2_gap_review_additions_resolve_and_scan` |
| `tests/test_backfill_f2_anchor.py` | 修改 | `95f849f9` | fixture `曹操出行`→虚构 `云图出行` 解耦（已注册实体不再当 gap 候选） |

> 中文候选生成的规则实现（bracket + post-marker 抽取 + affix 剥离）经测定后**完全 revert，未落盘**。

## 3. 架构影响

- **`entity_registry.py`（F2 真相源）**：`ENTITY_REGISTRY` 新增 6 entity / 12 alias，全部 `ticker` etype，HK 用 `.HK` 后缀、US 裸 ticker，与既有约定一致。`entity_anchoring.py` 扫描该 dict，故插入即生效于全部下游 F2 锚定。
- **候选生成器精度**：`backfill_f2_anchor.py` gap-review 候选流（喂 `build_f2_gap_review_batch` → 人工 → `apply_f2_gap_reviews`）的 upper-token 路径降噪，all-local 候选 59→29。
- **契约零改动**：`EntityAnchor` / `ContentEnvelope` / gap-review JSONL 字段未变。
- **registry 插入 ≠ registry_gaps.jsonl**：`apply_f2_gap_reviews.py` 只 append `data/dpo/registry_gaps.jsonl`（DPO/追踪用），不改 `ENTITY_REGISTRY`、不影响锚定命中率。要拉命中率必须改 `entity_registry.py` 源（本轮做法）。

## 4. 关键决策

- **只插可验证 ticker 的真实可交易实体**。27 个清洗后候选经 context 核验仅 6 个可插入（22%）。排除 21 个：用户名（ASG/LBC/JIN/SS/ZJJ 的「X的提问」）、误判（`ICE`=移民局非交易所、`MA`=均线非万事达）、组织（OPEC）、类别（BDC/ASIC）、非交易基金（BCRED/HPS）、私有公司（BMC/ZF）、数据源（CPB=荷兰经济局/CLS=财联社）。盲插选项示例里的 OPEC/BCRED/HPS 会污染 registry。
- **中文候选生成规则方案经测定 revert**。实现了 bracket（`【地平线】`）+ post-marker（`[实体]纳入/上市/涨停` + 前缀 stance-verb/功能词剥离 + 后缀语法字剥离）两条抽取路径，合成用例全对（地平线/寒武纪/商汤/中芯国际/比亚迪正确隔离）。但真实 3051-block 语料测定：① 宽 marker（上市/纳入）+ bracket → **precision ~6%**（18 候选仅 `地平线` 真实，其余为强调引号 `"隐性承诺"/"恐怖统治"` 与非实体句 `6-7月集中上市`）；② 严格 marker（涨停/跌停/借壳）→ **零召回**（这批对话截图无此类句式）。无规则甜区。**保留 net-negative 的代码违背工程纪律，故全部 revert，只留学习。**
- **fixture 解耦**：`曹操出行` 插入 registry 后会被锚定、不再是 gap 候选，3 个 gap-候选测试改用虚构 `云图出行`（cue `出行`、不在 registry），保留测试意图。

## 5. 验证结果

- `test_f2_gap_review_additions_resolve_and_scan`：resolve + scan_text 验证 6 实体锚定（3908.HK/2643.HK/GS/MUFG/SAP/CRWV）。
- registry 消费套件（entity_anchoring/enrichment/apply_f2/backfill_f2/build_f2/market_lookup/audit_api/backtest_canonical/select_candidates/harvest_calibrate/files_upload_f0）：**155 passed**。
- all-local dry-run（只读，写 /tmp）量化：hit_blocks 507→540（+33）、命中率 16.50%→17.70%、anchors 564→584（+20）、零锚文档 71→68（−3）。约 5.5 hit-block/实体。
- 中文候选生成规则版：合成用例通过，真实语料 precision ~6% / 零召回 → revert，工作树干净（`git status` 仅 FINER_ML_SUMMARY.md 未跟踪）。

## 6. 未解决项

1. **中文实体候选生成需 constrained-LLM**：规则在对话型 KOL 语料无法区分 `地平线`（实体）与 `倒春寒`/`隐性承诺`（强调引号短语）。真杠杆是 LLM 候选提议 + 确定性 validator（F1.5 架构既定方向），属较大独立任务。
2. **all-local 低命中率部分是结构性的**：拖累主体是 maodaren/9you 对话截图（2653 块 @ 11.6%），实体密度天然低；curated-pdf 53.2%。candidate-gen 改进在此 cohort 上限有限。
3. **F1 `ocr_thin` 206 块** 未处理（OCR 过薄，需重 OCR，与 bbox Phase 3 同源）。
4. **F0 `unclassified` 2653 块** source_type 从未分类，是另一条间接杠杆。
5. **边界候选未插**：`MSCI`（指数 vs MSCI Inc 歧义）、`GC0W`（纽约金主连 commodity）、`NV`（=英伟达但 2 字母易误锚）留待后续。
6. registry 插入是手工逐条核验，规模化依赖 1（LLM 候选）。
