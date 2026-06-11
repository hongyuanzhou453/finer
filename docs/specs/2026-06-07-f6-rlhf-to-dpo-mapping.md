# F6 RLHF 反馈 → DPO 偏好对 字段映射规范（环 B）

> 最后更新: 2026-06-07
> 关联: [DPO 百炼训练线](2026-06-07-dpo-bailian-training-line.md)（本文件是其"环 B 真实反馈飞轮"的契约）
> 卡片: 卡①② —— 写从 F6 真实反馈导出 preferences 的脚本 + 字段映射规范

## 1. 概述

环 B 的数据来源是**真实 F6 人工审核**：模型抽取 TradeAction → 人在 `RLHFReviewPanel` 审核纠错 →
转成 DPO 偏好对 `(prompt, chosen, rejected)` → 导出 HuggingFace 或百炼格式训练。

本规范锁定 **F6 `RLHFFeedback` 字段 → DPO 偏好对** 的映射、筛选条件、两种输出格式，
并**点明当前最关键的接线缺口**（corrections → preference 未组装），供环 B 落地时按图施工。

> ⚠️ 环 B 真实跑要等 `data/rlhf/feedbacks/` 有数据（当前为空）。本规范与导出代码已就绪，
> 但"人工审核 → preference 落库"这一步当前**未接线**（见 §6），不补则导出恒为空。

## 2. 源 Schema（F6）

`src/finer/api/routes/rlhf.py`：

- `Preference`（[rlhf.py:46](../../src/finer/api/routes/rlhf.py)）：
  - `chosen: Optional[str]` —— 修正后输出的 **JSON 串**
  - `rejected: Optional[str]` —— 原始（错误）输出的 **JSON 串**
  - `is_original_correct: bool` —— 原抽取是否正确
- `RLHFFeedback`（[rlhf.py:57](../../src/finer/api/routes/rlhf.py)）：`rating(1-5)`、`ticker_correct/_correction`、
  `direction_correct/_correction`、`action_chain_feedback[]`、`quick_tags[]`、`preference`、`original_extraction{evidence_text, ticker, ...}`。

## 3. 目标 Schema（DPO）

- `DPOTrainingItem`（`src/finer/ml/dpo_trainer.py`）：`prompt / chosen / rejected` + 元数据。
- 导出落盘：
  - HuggingFace `train.jsonl`：`{prompt, chosen, rejected}`（纯字符串）—— 本地 TRL。
  - 百炼 `data.jsonl`：ChatML，`chosen/rejected` 为对象 —— 上传百炼 DPO LoRA（见关联 spec §6）。

## 4. 字段映射表（canonical = `DPOExporter.feedback_to_dpo_item`）

| F6 来源 | → DPO | 变换 |
|---|---|---|
| `original_extraction.evidence_text` | `prompt` | `format_dpo_prompt(evidence_text)`（完整抽取模板，**canonical**）|
| `preference.chosen`（JSON 串） | `chosen` | 透传 |
| `preference.rejected`（JSON 串） | `rejected` | 透传 |
| `preference.is_original_correct` | 筛选闸 | 必须为 `False`（否则无学习信号，跳过）|
| `rating` | 筛选闸 + 元数据 | `rating ≥ min_rating`（默认 3）|
| `original_extraction.ticker` | `meta.ticker` | 过滤用 |
| `quick_tags` | `meta.quick_tags` | 分析用 |
| `feedback_id` | `meta.feedback_id` | 溯源 |

## 5. 筛选条件（一条 F6 反馈能进训练集，全部满足）

1. `rating ≥ min_rating`（默认 3）
2. `preference` 存在
3. `preference.is_original_correct == False`
4. `preference.chosen` 与 `preference.rejected` 均非空
5. `original_extraction.evidence_text` 非空
6. 校验：chosen/rejected 均为合法 JSON；chosen 含 `ticker`+`direction`；`chosen != rejected`

## 6. ✅ 接线桥（本次已补）：corrections → preference

原缺口：DPO 导出消费 `preference.chosen/rejected`，但人工审核结果（corrections）此前无路径写入该字段，
且前端提交体与后端字段名不符。**本次已打通**，三处改动：

1. **后端 assembler service**（[services/rlhf_assembler.py](../../src/finer/services/rlhf_assembler.py)）——
   `build_preference(original_extraction, corrections, flagged_as_error)`：
   - `rejected = json(原始抽取)`、`chosen = json(应用 corrections 后的抽取)`
   - `is_original_correct = 无任何 correction 且未标记异常`
   - 兼容前端 camelCase 与后端 snake_case，统一规整为简化抽取 JSON。
   - 业务逻辑放 service 层（CLAUDE.md §3：route 不写业务逻辑）。
2. **后端 `/submit`**（[rlhf.py](../../src/finer/api/routes/rlhf.py)）：`RLHFFeedbackCreate` 新增 `corrections`(ReviewCorrections)
   与 `flagged_as_error`；`preference` 缺省时调 `build_preference` 组装。直接给 `preference` 仍兼容。
3. **前端 `RLHFReviewPanel.handleSubmit`**：提交体对齐后端 —— `trade_action_id`/`quick_tags`/
   `original_extraction`（含 `evidence_text`）/`corrections`/`flagged_as_error`，action_chain 驼峰转下划线。

Next 中间层 `/api/rlhf/[...path]/route.ts` 是纯代理，**无需改动**，原样透传对齐后的 body。

## 7. 已知不一致：两条导出路径的 prompt 不同

- `DPOExporter`（canonical）用 `format_dpo_prompt(evidence_text)` —— 完整抽取模板（含要求/schema 选项）。
- `/api/rlhf/export`（[rlhf.py:544](../../src/finer/api/routes/rlhf.py)）用一行式 `f"从以下文本提取 Trade Action:\n{evidence_text}"`。

**canonical 以 `DPOExporter` 为准**。建议把 `/api/rlhf/export` 改为调用 `format_dpo_prompt`，
避免训练 prompt 分叉（本次未改该端点，列为待办）。

## 8. 输出（本次新增百炼格式）

```bash
# 从 F6 反馈导出，二选一或都要
python -m finer.ml.export_dpo --output_dir data/dpo_rlhf --format hf       # train.jsonl（本地 TRL）
python -m finer.ml.export_dpo --output_dir data/dpo_rlhf --format bailian  # data.jsonl（百炼 ChatML）
python -m finer.ml.export_dpo --output_dir data/dpo_rlhf --format both
```

实现：`DPOExporter.save_bailian_format()` + 模块级 `to_bailian_record()`（`dpo_trainer.py`，与
`scripts/to_bailian.py` 共用同一转换器，单一真相源）。

## 9. 验证（本次）

`data/rlhf/feedbacks/` 为空，故用**合成一条 F6 反馈**（方向 neutral→bullish 修正）验证 F6→百炼全路径：

- `DPOExporter(rlhf_dir=tmp).export_dataset()` → 1 条 `DPOTrainingItem`
- `save_bailian_format()` → 1 行百炼 ChatML，结构合法，`chosen` 含 bullish（修正）/`rejected` 含 neutral（原错）✓
- `scripts/to_bailian.py --demo` 重构后仍走包内 `to_bailian_record` ✓
- `export_dpo --format {hf,bailian,both}` 生效 ✓

接线桥（§6）：
- 端到端 `corrections → build_preference → Preference → DPOExporter → 百炼 ChatML` 验证通过（chosen=bullish 修正/rejected=neutral 原错）✓
- `tests/test_rlhf_assembler.py` 10 项全过（含边界：无修正/仅 flag/全 None/camelCase 规整）✓
- 前端 `tsc --noEmit` 0 error ✓

## 10. 未解决项

- ~~接线缺口（§6）~~ ✅ 已补（assembler + 前后端对齐，测试锁定）。
- **prompt 不一致（§7）**：`/api/rlhf/export` 未对齐 `format_dpo_prompt`（独立小待办，本次未碰）。
- 真实跑等 `data/rlhf/feedbacks/` 有数据（依赖 F5 canonical pipeline 产出 + 人工审核闭环）。
- `RLHFReviewPanel` 高亮的证据 span 未落库（见关联 spec），证据挂靠率在真实路径需要它。
