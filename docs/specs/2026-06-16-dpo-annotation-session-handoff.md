# DPO 标注·训练·展示 Session 交接（2026-06-16）

> 目的：记录本对话（标注 → DPO 训练 → 真实前后对比 → bio+ML 案例展示页）的全部进展、产物、关键决策与未来计划，供**新对话窗口直接接续**。新 session 读本文件即可上手，无需回放整段对话。

## 0. 一句话状态

DPO 第一轮闭环已跑通（标注 → 百炼训练 → 真实 before/after 对比图）；bio+ML 申研用的案例展示页 `/case` 已 build 通过并提交；F2 实体锚定设计 + L1 实现就绪，待第二轮治本。

---

## 1. 已完成（本对话）

| 工作 | 结果 |
|---|---|
| **评测集重建** | 旧 30 条 held-out 源全是弱信号（signal=1），陷"弱信号清零 vs gold≥20"死结。用 `min_signal=2` 重建 40 条强信号源，标注出 **29 条有效 gold**（committal 83%、零 train/eval 泄漏、judge=ref 可用） |
| **标注台 bug 修复** | `annotation_store.py` 的 `list_items` + `enums` 在 full-review 模式漏判 `full_pair_review_required`，导致前端只显示 30 抽样、152 全量审不了。已修，两端点一致返回 152 |
| **数据质量把关** | 152 对 draft → 人工审 115 cleaned。发现 55 条 chosen ticker 有问题（占位"标的待核"+ 错配），**精选 20 条 registry-验证 grounded 子集**（committal 55%）做第一轮 |
| **DPO 第一轮** | 20 条精选 → 百炼 Qwen3-8B · LoRA → before(基座)/after(微调) 推理 → `eval_compare` 出真实对比 |
| **案例展示页** | `src/finer_site/src/app/case/page.tsx`，bio+ML 申研用，build 过，commit `dd2f7f51` |
| **F2 设计 + L1** | EntityAnchor L1 产出器 + 自改进闭环/F2 锚定设计文档，commit `3e1e4eeb` |

## 2. DPO 第一轮真实结果（核心交付）

| 指标 | before(基座 Qwen3-8B) | after(DPO 微调) |
|---|---|---|
| 结构合规率 | 100% | 100% |
| 证据挂靠率 | 33.3% | **77.8%** |
| 编造率 | 66.7% | **22.2%** |
| 偏好胜率(after vs before) | — | **87.1%**（胜13/平14/负2） |

**来源**：held-out eval n=29，judge=ref，训练用 20 条 registry-验证精选偏好对。
**局限（必须如实写）**：第一轮、小样本、chosen 是校准器质量、方向验证非最终模型水平——after 几乎不退步(负2)、约半数进步。
**模型**：百炼部署 模型 Code `qwen3-8b-fa6d13e664dd`（模型名 `qwen3-8b_2d4d1af0`，服务 finer-DPO-2.0）。

## 3. 数字口径（新 session 必须一致——CV/邮件/case 页都引这套）

- **DPO 结果**：上表，标清"held-out eval / judge=ref / n=29 / 训练 20 条 / 第一轮"。
- **数据资产** vs **第一轮子集**：`100 条人工偏好 + 31 条文献真值` 是资产总量；`20 训练 + 29 eval` 是第一轮实验子集。两者是总池/精选关系，不要混。
- **committal 49% → 18%**：来自数据处理统计（整批 cleaned 49% → 剔脏数据后塌缩 18%），**不是** DPO 成果，是"为什么不能简单剔除"的证据。
- **13.03 亿 tokens / 12,045 请求 / 93.6% 缓存 / ≈$792.84**：跨 Finer + ESM 蛋白等**全部项目总量，非 Finer 单一**。
- **RLVR 奖励**（已实现）：`结构门 ×(0.50·grounding + 0.40·calibration + 0.10·abstention)`，只奖励忠实回溯证据，不看回测/行情/未来收益。

## 4. 关键决策与教训（避免新 session 重踩坑）

1. **数据质量 > 模型选择**——第一轮最大结论。
2. **ticker 错配是核心坑**：chosen 把"禾赛"填成赫斯石油(HES)、"泡泡玛特"填成别的代码——实体歧义。根因是 chosen 生成端没接 entity_registry。
3. **registry 修复不能全自动**：自动修会误修（"速腾"被改成 HSAI/禾赛，因速腾聚创不在 registry、原文又提了禾赛）。ticker 真值要人定，registry 只给候选。
4. **剔除脏数据 ≠ 解决**：剔掉 ticker 有问题的 55 条会让 committal 从 49% 塌到 18%（承诺样本恰好是被错配的那批）。正解是**修复 ticker**不是剔除。
5. **人机分工**：人核语义/方向，registry 核 ticker 代码（人记不住"禾赛=HSAI 不是 HES"）。
6. **DPO 机制**：rejected 必须是被训模型自己的 on-policy 输出，chosen 可来自更优 off-policy 来源。
7. **bio 桥接（申研王牌）**：ticker→registry 实体标准化 ＝ biomedical 的 gene/protein/drug normalization；数据质量较真 ＝ 假阳性/批次/金标准。

## 5. 关键产物清单

**核心（DPO 线，data/ 已 gitignore 不入库）**：
- `data/dpo/hq_v1/pairs_select20.jsonl` 训练精选 / `data.jsonl` 百炼 ChatML 包
- `data/dpo/hq_v1/eval/eval_set.jsonl`(29) / `before.jsonl` / `after.jsonl` / `report.json`（在用户终端机器）
- `src/finer_site/src/app/case/page.tsx` 案例页（已 commit）

**F2/闭环（已 commit `3e1e4eeb`）**：
- `docs/specs/2026-06-13-self-improving-annotation-loop.md`、`2026-06-14-f2-anchoring-design.md`
- `src/finer/enrichment/entity_anchoring.py` + `tests/test_entity_anchoring.py`
- `src/finer/services/annotation_store.py`（full-review 修复）

**已清理**：pairs_clean60.jsonl + clean60 报告 + eval/*.bak（废弃中间）。

## 6. 未来计划（按优先级）

1. **Word 文档**（给导师，蓝图见 §9）——新 session 用 docx skill 一次出图文版。
2. **第二轮 DPO（治本）**：① 生成端接 `entity_registry.resolve`（禾赛自动→HSAI，不再错配）② 扩 registry（补 ETF SOXX/SOXL/SMH、速腾聚创、范式等缺失标的）③ 扩量（registry 干净后救回那 55 条承诺样本，committal 和数据量都上去）。
3. **OCR/行情线提交**：git 里剩 ~32 个未提交文件（market_data/* + image_ocr/pdf_standardizer + layout_ocr + backfill_f1/f2 + 相关 doc/test），是之前 session 的 OCR 与行情工作线，需单独分线 commit。
4. **F2 orchestrator 落地**：`scripts/backfill_f2_anchor.py`（已存在，把 L1 锚定写回 envelope → F2_anchored）。
5. **/case 导航互链**：`site-chrome` 的 SiteHeader 加 `/case` 入口；`/demo`、`/training` 反链 `/case`。

## 7. 红线 / 约束

- DPO 用**真实结果**（第一轮已完成），但每个数字标清来源 + 局限；不夸大。
- 13 亿 token 标"跨项目总量"；100/31 是资产、20/29 是第一轮子集，别混。
- 删除文件 / 数据迁移 / 批量重建 / SQLite 结构变更 → **必须用户确认**。
- 不 push（当前 commit 在分支 `docs/f0-review-fixes`，未推送）；不 rebase/reset。
- `DASHSCOPE_API_KEY` 只在用户 shell，不进代码/日志/命令行（推理由用户在自己终端跑）。

## 8. 新 session 怎么接（关键命令）

**标注台**（full-review 模式必须带环境变量，否则退回 30 抽样）：
```bash
FINER_ANNOTATION_DPO_DIR=data/dpo/hq_v1 FINER_ANNOTATION_PAIRS_SOURCE=pairs_draft.jsonl FINER_ANNOTATION_FULL_PAIR_REVIEW=1 \
  uvicorn finer.api.server:app --reload --port 8000
cd src/finer_dashboard && npm run dev   # → localhost:3000/annotation
```

**训练链路**：harvest → draft → `/annotation` 审 → `validate_dpo_hq.py` → `to_bailian.py` → 百炼控制台 DPO LoRA → `run_inference.py`(before/after，用户终端跑，需 key) → `eval_compare.py` → 出图。

**案例页**：`cd src/finer_site && npm run dev` → `/case`；改完 `npm run build` 验证。

## 9. Word 文档蓝图（给导师 · bio+ML 申研 · 图文并茂）

标题：**从社媒噪声到可审计投资信号 —— 一个端到端 ML 系统的标注、对齐训练与评估（本科独立项目）**

1. 摘要：系统一句话 + DPO 前后核心数字 + 可迁移 bio。〔图1 系统流程 F0–F8〕
2. 问题与系统设计：噪声→结构化可审计信号（金融 testbed）；Finer OS + registry + 三态 verifier。〔图2 标注平台截图〕
3. 数据与标注：偏好标注流程 + 质量门 + 三态；100 偏好 + 31 真值。
4. 对齐训练：DPO(on/off-policy) + RLVR 奖励公式；Qwen3-8B 百炼 LoRA。
5. 真实挑战与解决 ★：ticker 错配/塌缩/误修 + 解决 + bio 同构（gene/drug normalization）。
6. 结果：DPO 前后三指标 + 胜率 87.1%（标来源 + 局限）。〔图3 前后对比图〕
7. 可迁移性与反思：实体标准化/数据质量/专家对齐 → biomedical；数据质量>模型、人机分工。
8. 附：demo finer.t800.click · code github.com/hongyuanzhou453/finer · 工程量(跨项目 token)。

图素材：图1 让 AI 画 F0–F8；图2 用户截标注台；图3 截本对话做的 DPO 对比图（show_widget `dpo_before_after_finer_v2`）。

---
*本文件即交接锚点。新 session 从 §0 状态 + §6 计划 + §8 命令接续即可。*
