# 百炼 DPO 实跑交接包

> 最后更新: 2026-06-12
> F-stage: F+ Training Loop / F6 Review 支撑面
> 状态: 实跑 handoff。当前 active path 已切到 `data/dpo/hq_v1/`；默认不重新付费 harvest，先完成 HQ draft 人工全量审核。

## 0. 结论

当前仓库已经不应再从 `data/dpo/candidates.jsonl` 重走普通主线。现在的实跑主线是：

```text
data/dpo/hq_v1/source_candidates.jsonl  # 220 条 HQ 候选，已生成
  -> data/dpo/hq_v1/pairs_draft.jsonl   # 152 对 qwen3-8b 真实 draft，已生成
  -> /annotation HQ full-review         # 待人工全量 accept/edit/reject
  -> data/dpo/hq_v1/pairs_cleaned.jsonl
  -> validate_dpo_hq.py
  -> to_bailian.py
  -> 百炼 DPO LoRA
  -> run_inference.py + eval_compare.py
  -> /training 页面回填
```

不要把现有 `data/dpo/data.jsonl` 直接当正式百炼实跑上传源；那是旧主线转换产物，不是 HQ v1 cleaned 包。

当前 blocker 很清楚：

```text
HQ draft 校验:
- pairs_draft.jsonl: rows=152
- validate_dpo_hq.py: ok=False errors=364 warnings=8
- 其中 304 个 errors 是 152 条都未人工签核（missing reviewer_id + missing review_verdict）
- 剩余 60 个内容 errors 是 ticker not grounded
- train/eval overlap: []
- duplicate prompt: []

annotation HQ 模式:
- pairs_review total=152 annotated=0
- blocker: 全量审核队列 0/152，尚未完成抽检

eval:
- default eval source 有 30 条 passages、9 条 annotations
- hq_v1/eval/passages.jsonl 当前缺失
- eval_set.jsonl / before.jsonl / after.jsonl / report.json 均未生成
```

所以当前优先级不是再次调用 qwen3-8b，而是：**先完成 152 对 HQ draft 全量人工审核，再补齐 held-out eval gold**。除非人工审核发现 draft 系统性不可救，才考虑用已修改的 `harvest_rejected.py` 重新付费 harvest。

`scripts/train_dpo.py` 仍不是百炼云端实跑入口；它只用于本地 TRL smoke-test 或 GPU fallback。

## 1. 真相源

本交接包按以下当前仓库文件整理：

| 文件 | 角色 |
|---|---|
| `docs/specs/2026-06-07-dpo-bailian-training-line.md` | 方法论、偏好原则、百炼 ChatML 格式、三指标、阶段计划 |
| `scripts/harvest_rejected.py` | 真实基座 qwen3-8b 生成 rejected，并确定性校准 chosen |
| `scripts/to_bailian.py` | 内部 `{prompt, chosen, rejected}` JSONL 转百炼 DPO ChatML |
| `scripts/train_dpo.py` | 本地 TRL/LoRA 训练脚本；`--smoke-test` 验证本地训练循环 |
| `scripts/run_inference.py` | 评测集上跑 before/after 推理，供 `eval_compare.py` 消费 |
| `scripts/eval_compare.py` | 生成三指标真实报告 |
| `scripts/validate_dpo_hq.py` | HQ 上传包质量门：全量人工签核、chosen 6 键、train/eval 不重叠 |
| `src/finer/services/annotation_store.py` | `/annotation` 的 JSONL 存储、formal export 与质量阻断规则 |
| `src/finer_dashboard/src/app/training/page.tsx` | dashboard `/training` 静态页，真实结果需要手动回填 |
| `src/finer_site/src/app/training/page.tsx` | public site `/training` 镜像页；是否同步由发布策略决定 |
| `data/dpo/hq_v1/pairs_draft_triage.md` | 60 条 ticker 不可溯 pair 的人工分诊清单 |
| `data/dpo/hq_v1/pairs_draft_diagnostic.md` | 伪 accept-all 诊断摘要，说明 draft 内容硬伤 |

## 2. 当前仓库数据状态

只读盘点结果：

| 路径 | 当前行数 | 结论 |
|---|---:|---|
| `data/dpo/candidates.jsonl` | 150 | 可作为 harvest 输入候选池 |
| `data/dpo/pairs.jsonl` | 150 | 旧主线偏好对；HQ 校验失败，不能直接作为正式上传包 |
| `data/dpo/data.jsonl` | 150 | 由旧 pairs 转出的百炼 ChatML；不能直接当正式上传包 |
| `data/dpo/eval/passages.jsonl` | 30 | held-out 评测任务源 |
| `data/dpo/eval/annotations.jsonl` | 9 | 只标了 9 条；formal eval export 当前被阻断 |
| `data/dpo/eval/eval_set.jsonl` | 缺失 | 需要 `/annotation` 导出 |
| `data/dpo/eval/before.jsonl` | 缺失 | 需要基座推理生成 |
| `data/dpo/eval/after.jsonl` | 缺失 | 需要百炼部署模型推理生成 |
| `data/dpo/eval/report.json` | 缺失 | 需要 `eval_compare.py` 生成 |
| `data/dpo/hq_v1/source_candidates.jsonl` | 220 | HQ v1 分层候选，已生成 |
| `data/dpo/hq_v1/pairs_draft.jsonl` | 152 | 当前 active draft；真实 qwen3-8b 已跑完，待人工全量审核 |
| `data/dpo/hq_v1/pairs_draft_triage.md` | 81 | 60 条 ticker 不可溯的分诊建议：registry-gap 6 / edit 43 / reject 11 |
| `data/dpo/hq_v1/pairs_draft_diagnostic.md` | 87 | 伪 accept-all 诊断：无泄漏、无重复 prompt，内容硬伤集中在 ticker grounding |
| `data/dpo/hq_v1/eval/passages.jsonl` | 缺失 | HQ mode annotation eval 队列为空；需复制/重建 held-out 评测源 |

当前 `/annotation` formal export 阻断：

```text
eval_gold: total=30 annotated=9
blockers:
- 还有 21 条样本未标 gold 或排除
- 还有 2 条弱信号样本未排除
- 有效 gold 样本少于 20 条

pairs_review: total=150 annotated=0
blockers:
- 默认抽样队列 0/30，尚未完成抽检
```

当前 HQ mode `/annotation` 阻断：

```text
eval_gold: total=0 annotated=0
blockers:
- 评测集任务源为空，请先重建任务源
- 有效 gold 样本少于 20 条

pairs_review: total=152 annotated=0
blockers:
- 全量审核队列 0/152，尚未完成抽检
```

## 3. 前置输入

### 3.1 必需输入

| 输入 | 路径/来源 | 要求 |
|---|---|---|
| 训练候选段落 | `data/dpo/hq_v1/source_candidates.jsonl` | HQ v1 候选池，当前 220 行；默认不再回退普通 `candidates.jsonl` |
| 偏好对 draft | `data/dpo/hq_v1/pairs_draft.jsonl` | 当前 active draft，152 对，需人工全量审核 |
| DashScope key | shell 环境变量 `DASHSCOPE_API_KEY` | 只在本地 shell 设置，不写 `.env`、代码、日志、commit |
| 百炼训练目标 | 控制台选择 `qwen3-8b` | DPO LoRA；百炼 ChatML 中 `chosen/rejected` 必须是 `{role, content}` 对象 |
| held-out 评测源 | `data/dpo/eval/passages.jsonl` 或复制到 `data/dpo/hq_v1/eval/passages.jsonl` | 当前 default 30 行；必须经人工 gold 标注导出 `eval_set.jsonl` |

### 3.2 推荐隔离目录

当前不建议再新建普通 `data/dpo/runs/*` 作为主线；`data/dpo/hq_v1/` 已经是本次 HQ run 目录。若要保留完整外部实跑快照，可在百炼上传前另存：

```bash
RUN_DIR=data/dpo/hq_v1
mkdir -p "$RUN_DIR/eval"
cp data/dpo/eval/passages.jsonl "$RUN_DIR/eval/passages.jsonl"
```

不要覆盖 `data/dpo/pairs.jsonl` 或 `data/dpo/data.jsonl`；它们属于旧默认主线。

## 4. 执行顺序

### Step 0. 本地训练循环 smoke-test

这一步不参与百炼云端训练，只证明本地 TRL DPO 训练代码还可跑。

```bash
.venv/bin/python scripts/train_dpo.py --smoke-test
```

预期：tiny Qwen + CPU + 2 步，最后出现 `SMOKE TEST PASSED: DPO 训练循环可运行`。失败时先修本地训练依赖；不要把这一步失败误判为百炼 ChatML 不可用。

回滚点：无 repo 产物。脚本使用临时目录；失败只影响本地环境检查。

### Step 1. 收口当前 pending code

当前工作树里有两组未提交训练数据质量修复：

- `scripts/harvest_rejected.py` / `tests/test_harvest_calibrate.py`：ungrounded committal 不再透传基座幻觉 ticker，而是写 `UNRESOLVED` 哨兵，并把基座猜测放到 `meta.ticker_guess`。
- `scripts/select_dpo_hq_candidates.py` / `tests/test_select_candidates.py`：候选筛选里的强标的信号改用 `groundable_entity_hits`，排除裸英文误命中，并把同一证券的裸代码与带交易所代码去重，避免闲聊/链接混入候选或单标的误判为 multi_context。

先确认这组修改保持：

```bash
pytest tests/test_select_candidates.py -q
pytest tests/test_harvest_calibrate.py -q
pytest tests/test_annotation_store.py tests/test_annotation_api.py -q
```

当前验证结果：

- `tests/test_select_candidates.py`: 4 passed。
- `tests/test_harvest_calibrate.py`: 6 passed。
- `tests/test_annotation_store.py tests/test_annotation_api.py`: 30 passed。

决策：

- 保留这组代码修改，作为未来重新 harvest 的正确行为。
- 不用它去改写既有 `data/dpo/hq_v1/pairs_draft.jsonl`；既有 draft 已有 triage 清单，先走人工审核。

回滚点：

- 如果这组修改后来被放弃，只影响未来 harvest，不影响已经生成的 `pairs_draft.jsonl`。
- 不要为了让已有 draft 看起来干净而批量把 ticker 机械改成 `UNRESOLVED`；人工分诊里已有 60 条具体建议。

### Step 2. 准备 HQ annotation 工作台

把 default held-out 评测源复制进 HQ run 目录：

```bash
RUN_DIR=data/dpo/hq_v1
mkdir -p "$RUN_DIR/eval"
cp data/dpo/eval/passages.jsonl "$RUN_DIR/eval/passages.jsonl"
```

启动 HQ mode backend：

```bash
FINER_ANNOTATION_DPO_DIR=data/dpo/hq_v1 \
FINER_ANNOTATION_PAIRS_SOURCE=pairs_draft.jsonl \
FINER_ANNOTATION_FULL_PAIR_REVIEW=1 \
uvicorn finer.api.server:app --reload --port 8000
```

启动前端：

```bash
cd src/finer_dashboard
npm run dev
```

浏览器打开 `http://localhost:3000/annotation`。

### Step 3. 人工全量审核 HQ pairs

进入「DPO 偏好对抽检」。这次不是默认抽样，而是 full-review：152 对都要 accept/edit/reject。

- `A` / accept：保留 chosen。
- `E` / edit：修正 chosen。
- `R` / reject：剔除该 pair。
- 如果编辑后 `chosen == rejected`，导出时会自动剔除。

优先按 `data/dpo/hq_v1/pairs_draft_triage.md` 分诊：

| 类别 | 数量 | 动作 |
|---|---:|---|
| registry-gap | 6 | 若标的确实正确，补实体别名或在 chosen 中用正确可溯 ticker；再 accept/edit |
| edit | 43 | 修正错锚 ticker、商品/指数口径、多标的混填，或降级 watchlist |
| reject | 11 | 纯宏观/方法论/非投资内容，直接 reject |

剩余 92 对伪 accept-all 内容无 hard error，但仍要人工快速确认；不要批量 accept-all。

完成后用页面按钮 formal export，产物：

```text
data/dpo/hq_v1/pairs_cleaned.jsonl
```

回滚点：

- formal export 被阻断：按页面或 API 返回的 blocker 处理，不要改脚本绕过。
- 签核质量差：新开 `RUN_ID` 重跑或继续编辑；不要用 draft export 冒充正式数据。

### Step 4. 评测集 gold 标注并导出

同一个 backend 使用 `FINER_ANNOTATION_DPO_DIR=data/dpo/hq_v1` 时，评测源来自：

```text
data/dpo/hq_v1/eval/passages.jsonl
```

在 `/annotation` 进入「评测集 Gold 标注」，完成后 formal export：

```text
data/dpo/hq_v1/eval/eval_set.jsonl
```

formal export 的硬门槛来自 `AnnotationStore`：

- 30 条任务源全部标注 gold 或排除。
- 图片占位样本必须排除。
- 弱信号样本必须排除。
- 有效 gold 样本至少 20 条。
- 训练/评测 id 不得重叠。

回滚点：

- gold 不足 20：继续标注或重建 held-out 任务源。
- train/eval 重叠：必须换评测源，不能删除检查或用训练集评测。

### Step 5. HQ 质量门

在转百炼前跑严格校验：

```bash
.venv/bin/python scripts/validate_dpo_hq.py \
  --pairs data/dpo/hq_v1/pairs_cleaned.jsonl \
  --eval data/dpo/hq_v1/eval/eval_set.jsonl \
  --report data/dpo/hq_v1/hq_quality_report.json
```

必须满足：

- exit code 为 0。
- `hq_quality_report.json` 中 `ok=true`。
- `train_eval_overlap_ids=[]`。
- 行数在默认 `120-150` 内，或显式用 `--min-size/--max-size` 给出本次实验边界。
- 每条 chosen 顶层 key 恰好为：

```text
ticker, direction, conviction, action_chain, time_horizon, rationale
```

回滚点：

- 缺 reviewer/verdict：回 `/annotation` 补签核。
- chosen schema 错：编辑对应 pair，重新 export。
- ticker/price 不可溯：修 chosen 或 reject。

### Step 6. 转百炼 ChatML

```bash
.venv/bin/python scripts/to_bailian.py \
  --in data/dpo/hq_v1/pairs_cleaned.jsonl \
  --out data/dpo/hq_v1/data.jsonl
```

产物：

```text
data/dpo/hq_v1/data.jsonl
```

百炼每行结构应是：

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "chosen": {"role": "assistant", "content": "..."},
  "rejected": {"role": "assistant", "content": "..."}
}
```

成功标准：

- `converted >= 120`。
- `chosen 合法 JSON == converted`。
- `rejected 合法 JSON == converted`。

回滚点：

- `chosen == rejected` 被 drop：回 pairs 签核修正。
- converted 低于百炼建议规模：不要上传，回到 harvest 或签核。

### Step 7. 百炼控制台实跑

在百炼控制台执行：

1. 上传 `data/dpo/hq_v1/data.jsonl`。
2. 基座选择 `qwen3-8b`。
3. 训练方式选择 DPO LoRA。
4. 训练完成后部署模型，记录部署模型 id。

需要手动记录到 run 目录的元信息：

```text
data/dpo/hq_v1/bailian_run_notes.md
```

建议记录：

```markdown
# Bailian DPO Run Notes

- run_id:
- uploaded_data: data.jsonl
- base_model: qwen3-8b
- tuning_method: DPO LoRA
- bailian_job_id:
- deployed_model_id:
- started_at:
- finished_at:
- console_status:
- notes:
```

回滚点：

- 上传失败：检查 `data/dpo/hq_v1/data.jsonl` JSONL 和百炼错误；不改训练数据格式脚本绕过。
- 训练失败：保留百炼 job id、错误截图/日志、`data.jsonl` hash；新开 run 复跑。
- 部署失败：训练结果不等于可评测结果，必须等部署模型 id 可用后再进入 Step 8。

### Step 8. 同一评测集跑 before/after

基座：

```bash
.venv/bin/python scripts/run_inference.py \
  --eval-set data/dpo/hq_v1/eval/eval_set.jsonl \
  --out data/dpo/hq_v1/eval/before.jsonl \
  --model qwen3-8b \
  --temperature 0
```

微调后：

```bash
.venv/bin/python scripts/run_inference.py \
  --eval-set data/dpo/hq_v1/eval/eval_set.jsonl \
  --out data/dpo/hq_v1/eval/after.jsonl \
  --model "<百炼部署模型id>" \
  --temperature 0
```

如百炼部署使用自定义 OpenAI 兼容网关，补 `--base-url <url>`。

产物：

| 路径 | 内容 |
|---|---|
| `data/dpo/hq_v1/eval/before.jsonl` | 每行 `{"id", "output"}`，基座输出 |
| `data/dpo/hq_v1/eval/after.jsonl` | 每行 `{"id", "output"}`，微调后输出 |

成功标准：

```bash
wc -l data/dpo/hq_v1/eval/eval_set.jsonl \
      data/dpo/hq_v1/eval/before.jsonl \
      data/dpo/hq_v1/eval/after.jsonl
```

三者 id 覆盖应一致。`eval_compare.py` 会跳过缺失 id，但正式报告不应有大量缺失。

回滚点：

- before 失败：只重跑 before。
- after 失败：确认部署模型 id 和 endpoint，再重跑 after。
- 不得用 `--mock` 输出填充真实报告。

### Step 9. 生成真实三指标报告

```bash
.venv/bin/python scripts/eval_compare.py \
  --eval-set data/dpo/hq_v1/eval/eval_set.jsonl \
  --before data/dpo/hq_v1/eval/before.jsonl \
  --after data/dpo/hq_v1/eval/after.jsonl \
  --judge ref \
  --out data/dpo/hq_v1/eval/report.json
```

`report.json` key：

```json
{
  "demo": false,
  "enum_source": "finer.schemas.trade_action",
  "before": {
    "total": 0,
    "compliant": 0,
    "structure_compliance_rate": null,
    "committal": 0,
    "grounded": 0,
    "evidence_attachment_rate": null,
    "hallucination_rate": null
  },
  "after": {
    "total": 0,
    "compliant": 0,
    "structure_compliance_rate": null,
    "committal": 0,
    "grounded": 0,
    "evidence_attachment_rate": null,
    "hallucination_rate": null
  },
  "preference": {
    "judge": "ref",
    "considered": 0,
    "wins": 0,
    "ties": 0,
    "losses": 0,
    "win_rate": null
  }
}
```

真实报告必须满足：

- `"demo": false`。
- `before.total == after.total`。
- `preference.considered > 0`，否则 gold 缺失或 judge 不可用。
- 页面或对外文档只引用这个 report，不引用 `--demo` 输出。

回滚点：

- `preference.considered=0`：回到 eval gold，不要改 win_rate。
- evidence rate 为 `null`：说明没有承诺性输出分母，报告应如实展示 `n/a`。
- after 比 before 差：照实回填，不改指标定义。

## 5. `/training` 页面回填

当前 `/training` 是静态叙事页，不会自动读取 `data/dpo/hq_v1/eval/report.json`。

主回填文件：

```text
src/finer_dashboard/src/app/training/page.tsx
```

如要同步 public site，再改：

```text
src/finer_site/src/app/training/page.tsx
```

### 5.1 必填来源

回填前必须具备：

| 数据 | 路径 |
|---|---|
| 真实评测报告 | `data/dpo/hq_v1/eval/report.json` |
| before 输出 | `data/dpo/hq_v1/eval/before.jsonl` |
| after 输出 | `data/dpo/hq_v1/eval/after.jsonl` |
| 百炼 run notes | `data/dpo/hq_v1/bailian_run_notes.md` |
| HQ 质量报告 | `data/dpo/hq_v1/hq_quality_report.json` |

### 5.2 页面改动点

1. 顶部注释仍保留红线，但把“真实微调数字留待百炼实跑回填”改为“真实微调数字来自 `data/dpo/hq_v1/eval/report.json`”。
2. `STAGES` 中：
   - `数据①` 从 `pending` 改为 `done`，detail 写 `HQ 校验通过，N 条 pairs_cleaned`。
   - `实跑` 从 `user` 改为 `done`，detail 写 `百炼 DPO LoRA 已完成，report.json 已回填`。
3. 保留“迭代 2 校准器”卡片，但不要把它说成模型成绩。
4. 将右侧“红线 / 这一格目前留白”卡替换为真实结果卡。字段从 `report.json` 取：
   - 样本数：`before.total` / `after.total`
   - 结构合规率：`before.structure_compliance_rate` -> `after.structure_compliance_rate`
   - 证据挂靠率：`before.evidence_attachment_rate` -> `after.evidence_attachment_rate`
   - 编造率：`before.hallucination_rate` -> `after.hallucination_rate`
   - 偏好胜率：`preference.win_rate`
   - W/T/L：`preference.wins` / `preference.ties` / `preference.losses`
   - judge：`preference.judge`
   - run id、base model、deployed model id：来自 `bailian_run_notes.md`
5. 如果某项为 `null`，页面显示 `n/a`，不要补 0。

### 5.3 页面验证

dashboard：

```bash
cd src/finer_dashboard
npm run lint
npm run build
```

public site 如果同步：

```bash
cd src/finer_site
npm run lint
npm run build
```

验证口径：

- 页面不出现 `eval_compare --demo` 数字。
- 页面能看出 report 的 run id、样本数、judge。
- 没有把校准器行为对比当成微调前后成绩。
- 若 public site 未同步，文档或 final response 必须明确 dashboard 已回填、public site 未回填。

## 6. 失败回滚表

| 阶段 | 失败信号 | 回滚点 | 处理 |
|---|---|---|---|
| harvest limit5 | key 缺失、计费/endpoint 报错 | 无正式产物 | 修 shell 环境或 endpoint；不要写 `.env` |
| harvest full | `kept < 120` 或失败过多 | `data/dpo/hq_v1/pairs_draft.jsonl` 不覆盖 | 只在确认 draft 系统性不可救时才新 run |
| pairs 签核 | formal export 阻断 | `data/dpo/hq_v1/pairs_draft.jsonl` | 继续 `/annotation`，不使用 draft |
| HQ 校验 | `ok=false` | `data/dpo/hq_v1/hq_quality_report.json` | 按 errors 修 pair 或 reject |
| to_bailian | converted 低、chosen/rejected 非 JSON | `data/dpo/hq_v1/pairs_cleaned.jsonl` | 回签核，不改百炼格式要求 |
| 百炼训练 | 控制台训练失败 | `data/dpo/hq_v1/data.jsonl` + job id | 保留错误，新 run 或重训 |
| after 推理 | 部署模型 id 不可用 | `before.jsonl` 可保留 | 等部署可用后只重跑 after |
| eval_compare | missing ids、considered=0 | before/after/eval_set 三文件 | 补 id 覆盖或 gold，不编造指标 |
| `/training` 回填 | 页面展示和 report 不一致 | git diff | 改页面常量；不改 report |

## 7. 不允许的捷径

- 不用 `--mock` 生成训练数据或真实评测结果。
- 不用 `eval_compare.py --demo` 的数字填页面。
- 不把当前旧 `data/dpo/data.jsonl` 当正式上传源。
- 不删除 train/eval overlap 检查。
- 不把 `DASHSCOPE_API_KEY` 写进 `.env`、代码、文档、日志。
- 不为了让 HQ 校验通过而放宽 chosen schema 或注释校验。
- 不把本地 `train_dpo.py` 的 smoke-test 结果说成百炼实跑结果。
