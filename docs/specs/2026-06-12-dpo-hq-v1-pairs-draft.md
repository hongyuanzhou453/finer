# DPO HQ v1 pairs_draft 生成与 calibrate 契约修复

## 概述

完成 HQ v1 训练集获取的模型生成步：220 条真实候选经 `qwen3-8b` 真实调用产出 152 对偏好数据（`data/dpo/hq_v1/pairs_draft.jsonl`），全部进入全量人工审核队列。生成前修复了 `calibrate()` 的三个契约缺陷，使 draft chosen 与 `validate_dpo_hq.py` 的 schema 硬约束对齐——伪 accept-all 校验显示 92/152 对 accept 即可通过，剩余 60 对只含一类需人工裁决的 error（ticker not grounded）。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/harvest_rejected.py` | 修改 | calibrate 契约修复（见关键决策）；新增 `CHOSEN_KEYS` 与 `normalize_chosen()` |
| `tests/test_harvest_calibrate.py` | 新增 | calibrate 契约测试 ×4（6 键收敛、ungrounded 压 0.3、grounded 给 0.8、watchlist 带 time_horizon） |
| `data/dpo/hq_v1/pairs_draft.jsonl` | 新增（数据，不入 git） | 152 对真实偏好数据，meta 携带 `hq_category` / `hq_score` |

## 架构影响

- 属 F+ Training 线，不触及 F0-F8 主链路代码。
- 数据契约：harvest 产出的 chosen 顶层 key 现在**恰好等于** `scripts/validate_dpo_hq.py:REQUIRED_CHOSEN_KEYS` 的 6 键（`ticker/direction/conviction/action_chain/time_horizon/rationale`），保证 `annotation_store.export_pairs_cleaned()`（accept 透传、不做 schema 规整）导出的行可直接过校验。
- API / 前端契约无变化；标注后台仍走 `GET /api/annotation/items?task_id=pairs_review`。

## 关键决策

1. **`calibrate()` conviction 阶梯补 `grounded` 条件**：原 `if grounded_prices:` 在「价位可溯但标的不可溯」时给 0.8 最高信念，与分支注释「标的+价位都可溯」矛盾，且产出「对未验证标的更自信」的反向训练信号。修为 `if grounded and grounded_prices:`，ungrounded 一律落 0.3。烟测中 3/5 保留对命中此 bug，是修复的直接证据。
2. **chosen 统一 6 键收敛（`normalize_chosen`）**：删除 `evidence_quote` 额外 key（quote 已内联 rationale；validator 按 extra keys 判 error）、`WATCHLIST_CHOSEN` 补 `time_horizon: None`。理由：`export_pairs_cleaned` 对 accept 的 chosen 是透传，draft 不合 schema 就会把机械修改成本全部转嫁给人工审核。
3. **ungrounded committal 不自动降级观望**：保留方向、压 conviction 至 0.3，交人工裁决。实体库缺中文别名（如 A 股代码无别名映射）与真编造在规则层不可区分，自动降级会把正确的方向观点改错；标注后台已有 `POST /api/annotation/registry-gap` 承接别名缺口登记。
4. **先烟测后全量**：脚本为覆盖写、无断点续跑，10 条烟测写 /tmp，确认质量后全量 220 直写正式路径，避免半成品混入。

## 验证结果

| 验证项 | 命令/方式 | 结果 |
|--------|----------|------|
| 语法 + 单测 | `pytest tests/test_harvest_calibrate.py tests/test_annotation_store.py tests/test_annotation_api.py` | 34 passed |
| mock 全流程 | `harvest_rejected.py --mock --limit 20` | 20 对，6 键契约 0 违规 |
| 真实烟测（修复后） | `--model qwen3-8b --limit 10` → /tmp | 6 对保留；原 3 个 bug 对正确产出 rejected(0.4-0.6 过度自信) → chosen(0.3 克制) |
| 全量生成 | `--model qwen3-8b`（220 条，无 limit） | 调用成功 220、失败 0、降级观望 8、基座答对丢弃 68、保留 152 对 |
| draft 完整性 | 自检脚本 | 6 键违规 0；类别 abstain 36 / bearish_risk 25 / bullish_action 48 / multi_context 43；eval 泄漏 0（30 个 held-out id）；重复 prompt 0；chosen==rejected 0；mock 标记 0 |
| 伪 accept-all 校验 | `validate_dpo_hq.py --min-size 120 --max-size 160` | errors=60，全部为 `ticker not grounded in evidence`（92 对零 error）；warnings=8（trigger 数字不可溯，非阻塞） |
| 标注后台 HQ 模式 | uvicorn :8311 + `FINER_ANNOTATION_DPO_DIR=data/dpo/hq_v1` 等三个 env | `/api/annotation/tasks` 显示 pairs_review total=152；items 返回 152 条含 evidence_text/chosen/rejected；缺 `hq_v1/eval/passages.jsonl` 不报错（eval_gold 队列为 0） |

## 未解决项

1. **人工全量审核未开始**（设计如此）：152 对需逐对 accept/edit/reject。其中 60 对 committal+ticker 不可溯，需裁决「登记 registry-gap（别名缺口）」或「edit 修正/降级」。
2. **导出量与校验窗口**：draft 152 对 > validator 默认 `--max-size 150`。若审核 reject 少于 2 对，校验会报 dataset_size error——属预期闸口，届时按实际质量决定收紧审核或显式放宽 `--max-size`。
3. conviction 阶梯的 0.45 / 0.6 档在本批为空（grounded 标的几乎都伴随可溯价位），分布是否合理待审核反馈。
4. `data/dpo/eval/eval_set.jsonl` 尚不存在（泄漏检查目前只对 `passages.jsonl` 的 30 个 id 生效）。
