# Eval Gold 纪律（Batch D2）

## 概述

建立 eval gold 的持续供给与版本纪律：每个 pipeline-drive run 产出的新 F5 action 按 creator 分层抽样 10% 进 gold 标注队列，gold 行强制携带 pipeline_version 版本章，管线版本变更时旧 gold 降级为 reference（不删除）；同时把 `scripts/eval_compare.py` 的 `--eval-set` 默认指向唯一真身 `data/dpo/hq_v1/eval/eval_set.jsonl`，消除旧 docstring 指向不存在路径的问题。

## 纪律条款（canonical）

1. **抽样进队**：每个 pipeline-drive run 产出的新 F5 action（`data/F5_executed/*_actions.json`），必须按 creator 分层抽样 10%（`--rate 0.1`）、每 creator 最少 3 条（`--per-creator-min 3`）进 gold 队列 `data/dpo/eval_queue/queue_<YYYYMMDD-HHMMSS>.jsonl`。抽样确定性（组内按 `trade_action_id` 字典序取前 N，不用 random），重跑可对账。
2. **标注走既有 annotation workbench**：队列行的 `id` 键名对齐 `schemas/annotation.py:EvalGoldAnnotation` 的 `id`，标注产物走 eval_gold 任务既有流程，不另建标注面。
3. **版本章强制**：每条 gold 队列行必须携带 `pipeline_version`：`schema_version` / `prompt_version`（真相源 `src/finer/services/versioning.py` 的 `CURRENT_SCHEMA_VERSION` / `CURRENT_PROMPT_VERSION`）、`model_version`（action 级）、`f5_model`（wrapper 级）、`extraction_config_hash`（`action.version_info`，可空）、`source_file`（wrapper 的上游输入文件）。无版本章的行不得进入 formal eval_set。
4. **版本变更降级**：schema_version / prompt_version / f5_model 任一变更后，旧版本章的 gold 降级为 reference——保留在盘上供回归参照，但不再计入当前版本的 formal 评测分母。**不删除**。
5. **eval_set 唯一真身**：`data/dpo/hq_v1/eval/` 是 eval_set 的唯一权威目录；`data/dpo/eval/` 等旧路径不再作为消费入口。`scripts/eval_compare.py` 默认读取 `data/dpo/hq_v1/eval/eval_set.jsonl`。

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/eval_compare.py` | 修改 | `--eval-set` 加默认值 `data/dpo/hq_v1/eval/eval_set.jsonl`；非 demo 必填校验收窄为 `--before/--after`；docstring 用例路径从不存在的 `data/dpo/eval/` 改为 `data/dpo/hq_v1/eval/` |
| `scripts/sample_eval_gold.py` | 新增 | F5 现役 action 按 creator 分层确定性抽样，生成携带 pipeline_version 版本章的 gold 待标注队列；支持 `--rate` / `--per-creator-min` / `--dry-run` / `--out-dir` |
| `docs/specs/2026-07-11-eval-gold-discipline.md` | 新增 | 本文档 |

## 架构影响

- **F6 Review / F+ Training Loop**：gold 队列是 F5 输出（`data/F5_executed/`）到标注工作台（`src/finer/schemas/annotation.py` eval_gold 任务）之间的新中间物，落盘 `data/dpo/eval_queue/`（JSONL，文件即真相源，不引入 SQLite 表）。
- **数据契约**：队列行不新增 Pydantic schema——它是标注任务源（对齐 `EvalGoldAnnotation.id` 的键名约定），不是 canonical pipeline 数据；`pipeline_version` 字段组是纪律性附件，消费方是 formal export 的降级判断。
- **消费方**：`scripts/eval_compare.py` 的 eval_set 输入路径默认值变化只影响 CLI 缺省，显式传参行为不变；`--before/--after` 仍必填。
- 不触碰 F0-F8 运行时代码、API route、`contracts.ts`。

## 关键决策

1. **确定性抽样而非 random**：组内按 `trade_action_id` 字典序取前 N。牺牲统计随机性，换取重跑对账能力（同一批 F5 数据任何时候重跑得到同一队列），这对"每个 run 抽 10%"的审计纪律比随机性更重要。
2. **per-creator 下限 3 条**：小样本 creator（如 sandbox）按 10% 只会抽 0-1 条，不足以形成该 creator 的评测锚点；下限 3 保证每个 creator 至少有最小可比较集。
3. **降级不删除**：旧版本 gold 是人工标注资产，管线版本升级后仍可作为跨版本回归参照；删除会破坏"可审计"底线。降级的判定依据就是版本章，因此版本章是强制项。
4. **版本章的 `extraction_config_hash` 允许为空**：当前现役 42 条 F5 action 的 `version_info` 全部为 null（历史产物未回填），强制非空会把现役数据全部挡在队列外；先记录为空、在 F5 constructor 补齐 version_info 后收紧。
5. **eval_compare 只给 `--eval-set` 加默认**：`--before/--after` 是模型实跑产物，没有稳定的合理默认路径，保持必填避免误用旧文件出假对比。

## 验证结果

```bash
$ python scripts/eval_compare.py --demo
# 零外部文件自检通过（输出摘录）：
# 枚举真相源: finer.schemas.trade_action
# 样本数: before=5  after=5
# 结构合规率 0.80 → 1.00 (+0.20)；证据挂靠率 0.00 → 1.00 (+1.00)
# 偏好胜率 after≻before = 0.90 [judge=ref W/T/L=4/1/0 n=5]

$ python scripts/sample_eval_gold.py --dry-run --rate 0.1
# 版本章来源: finer.services.versioning (schema=1.0 prompt=2.0)
# 扫描 data/F5_executed: 42 条现役 F5 action
# 分层抽样计划 (rate=0.1, per-creator-min=3):
#   sandbox      现役   5 条 → 抽样   3 条
#   trader_ji    现役  37 条 → 抽样   4 条
# 合计抽样 7 条
# (--dry-run 模式，仅打印计划，不写文件)  ← 确认未创建 data/dpo/eval_queue/

$ python scripts/eval_compare.py            # 无参数
# eval_compare.py: error: 非 --demo 模式必须提供 --before / --after（--eval-set 有默认值）
# --help 中 --eval-set 正确显示 default: data/dpo/hq_v1/eval/eval_set.jsonl
```

全部通过。本批次未执行真实写入（`data/dpo/eval_queue/` 尚不存在，由首次非 dry-run 运行创建）。

## 现状基线（缺口）

- `data/dpo/hq_v1/eval/eval_set.jsonl`：**29 行**（formal eval 真身）
- `data/dpo/hq_v1/eval/annotations.jsonl`：**40 条**标注
- F3 四轴（direction / actionability / position_delta_hint / conviction，定义见 `docs/specs/f-stage-contracts.md`）gold：**只有 cat_lord 4 条 expected fixture**（`tests/fixtures/kol/cat_lord_*_expected_v*.json`），没有覆盖现役 creator 的 F3 四轴 gold——这是当前最大缺口。eval_set 只覆盖 F5 侧简化抽取（ticker/direction/action_chain），F3 中间轴无独立评测锚点。

## 未解决项

1. F3 四轴 gold 缺口：本批次只建立 F5 侧 gold 队列纪律，F3 四轴 gold 的抽样与标注面未覆盖（需先在 annotation workbench 增加 F3 任务类型）。
2. 现役 F5 action `version_info` 全空：`extraction_config_hash` 暂以 null 进版本章，待 F5 canonical constructor 回填 `version_info` 后收紧为必填。
3. 降级为 reference 的机械化：目前是纪律条款（人工按版本章比对），尚无脚本自动把旧版本章 gold 移出 formal 分母；待 formal export 流程接入 `pipeline_version` 校验。
4. 首次真实入队未执行：`data/dpo/eval_queue/` 的首个 `queue_*.jsonl` 需在下一次 pipeline-drive run 后由 owner 运行非 dry-run 命令生成。
