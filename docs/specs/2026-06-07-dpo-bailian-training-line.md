# DPO 百炼真实训练线 — 方法论契约与可验证地基

> 最后更新: 2026-06-07
> 状态: 地基阶段（spec + eval_compare 已落地；数据/smoke-test/百炼实跑待续）
> 关联卡片: 卡①·Finer DPO 真实训练线（百炼）

## 1. 概述（Overview）

在百炼（阿里云 Model Studio）对 Qwen3-8B 跑通真实 DPO-LoRA，产出"微调前/后"可量化对比；本文件锁定**偏好原则、数据来源方法、三项评测指标、数据契约、阶段计划与三个人工闸口**，作为后续合成数据、评测器、转换器、实跑的唯一真相源。

**红线**：不编造提升数字。合成 bootstrap 只能证明"管线通 + 原则可学"，不能当质量提升；真实数字留待百炼实跑回填。

## 2. 现状与差距（为什么是新建一条线）

仓库已有的是**本地 TRL/LoRA 线**（`scripts/train_dpo.py` 默认 Qwen2.5-14B + CUDA，配 `src/finer/ml/dpo_trainer.py` 的 `DPOExporter`），需要本地 GPU。卡①要的是**百炼云端 Qwen3-8B DPO-LoRA**，两者不是一回事。

落地前事实核查（2026-06-07）：

- 合成偏好数据：**0 条**（卡①"30→≥120"的 30 不存在，从 0 建）。
- `to_bailian.py` / `eval_compare.py` / `train_dpo.py --smoke-test`：均不存在（本次新增 `eval_compare.py`）。
- 真实 RLHF 反馈：`data/rlhf/feedbacks/` 为空；`/api/rlhf/pending` 数据源目录不存在 → 标注队列当前空转。
- 真实语料：`data/processed/transcripts` 297 份、`data/raw` 50 份、creator 分目录转写若干 → **足够支撑半真实方案**。
- 本地 ML 依赖：`torch 2.11` 已装；`trl/peft/transformers/accelerate` **未装**（smoke-test 前需装，见闸①）。

## 3. 偏好原则（已锁）：证据对齐的克制

DPO 偏好对 `(prompt, chosen, rejected)` 中，`chosen ≻ rejected` 统一编码以下原则：

| | chosen（偏好） | rejected（拒绝） |
|---|---|---|
| 证据充分 | 给对方向 + 挂上原文可溯证据（ticker/价位 span）+ schema 合规 | 方向错 / 丢证据 / 结构破格 |
| 证据不足 | `hold`/`watchlist` + 低 confidence + 诚实 rationale（敢弃权） | 弱证据硬给 buy/sell、编造原文没有的 ticker/价位 |

一条原则同时驱动三项指标：证据挂靠率 ← chosen 挂证据、结构合规率 ← chosen 合规、偏好胜率 ← chosen 的克制被判更优。直接服务红线"不编造"。对投研系统而言，"证据不足时敢说 hold"比"猜对方向"更有价值。

### 覆盖矩阵（≥120 条，每格 ~10）

方向 `{buy, sell, hold}` × 证据 `{足, 不足}` × 周期 `{长, 短}` = 12 格。其中 **「证据不足 × 本应 buy/sell」**（chosen=hold，rejected=买卖）是信号最强的格子，重点配比。

## 4. 数据来源方法（已锁）：半真实

为压低 circularity、让"证据挂靠率"测的是真东西，环 A bootstrap 不由 agent 凭空编两边：

1. **`evidence_text` 取真实 KOL 转写原文**（来自 `data/processed/transcripts` 等），轻过滤掉测试桩（`smoke_test.txt`、`integration_test.txt`）与 OCR/ASR 噪声段。
2. **`rejected` = 跑基座 Qwen 的真实失败输出**（过度承诺 / 编造价位），即 on-policy 负样本，不是 agent 虚构的稻草人。理想用与微调目标同款 Qwen3-8B 基座；若 DashScope 不可直调则用同族代理（效果略弱）。
3. **`chosen` = 把 rejected 校准为"证据对齐的克制"版**，证据 span 内联进 JSON（生成时即知证据落点 → 证据挂靠率可由构造直接算）。
4. **人工抽检**：复用现有 `RLHFReviewPanel` 对 chosen 侧抽样校验，不逐条标注。

残留 circularity 仅剩"chosen 的校准判断由 agent 给"，靠人工抽检 + 证据挂靠率确定性检查兜底；bootstrap 阶段可接受，局限明示。

### 两个环（区分清楚）

- **环 A · 半真实 bootstrap（先做）**：证管线 + 立 baseline，**非质量证明**。
- **环 B · 真实反馈飞轮（后做，真正质量来源）**：真实 F5 抽取 → 人在面板纠错 → `chosen=纠正 / rejected=模型原错` → 再训。`Preference{chosen, rejected, is_original_correct}` 已存在于 `api/routes/rlhf.py`，`DPOExporter` 已能读。

## 5. 三项评测指标（精确定义，与 `scripts/eval_compare.py` 实现一致）

输入：评测集 `eval_set.jsonl`（含 `id/prompt/evidence_text/expected_abstain/gold?`）+ `before.jsonl`/`after.jsonl`（含 `id/output` 原始模型输出串），按 `id` 对齐。

### 5.1 结构合规率 structure_compliance_rate（确定性、免费）

输出能 `json.loads` 且通过轻量 `ExtractionOutput` 校验：`ticker` 非空 str；`direction ∈ TradeDirection`；`action_chain` 每步 `action_type ∈ ActionType`；价格 `≥0` 且 `low ≤ high`。
= 合规数 / 总数。**枚举值以 `src/finer/schemas/trade_action.py` 的 `TradeDirection`/`ActionType` 为真相源**（eval 不重定义枚举）。

> 注意：校验对象是 LLM 实际产出的**简化抽取 JSON**，不是完整 canonical `TradeAction`（后者由 F3→F4→F5 装配，含 source/target/execution_timing）。

### 5.2 证据挂靠率 evidence_attachment_rate（确定性、免费、直测"不编造"）

仅在**承诺性输出**上计：`direction ∈ {bullish, bearish}` 或 `action_chain` 含 `{long, short, buy_call, sell_call, buy_put, sell_put, close_long, close_short}`。
承诺性输出"挂靠成功" = `ticker` 在 `evidence_text` 可溯（normalized 子串）**且**未编造价格（输出中所有 `target_price_low/high` 及 `trigger_condition` 内数字都能在 `evidence_text` 找到）。
= 挂靠成功承诺数 / 承诺总数。附带报告 **hallucination_rate**（编造 ticker 或价格的承诺占比）。

### 5.3 偏好胜率 preference_win_rate（需 judge）

pairwise：对每个 `id` 判 after 是否优于 before。两种 judge：

- **ref-match（确定性、免费，需 gold）**：各自与 `gold` 的字段匹配分（direction/ticker/承诺一致性），分高者胜。用于无 API 的 dry-run。
- **llm（pairwise，需 API，闸②）**：rubric = 证据对齐的克制；**A/B 位置互换跑两遍，仅计一致胜**消除位置偏置。

= after 胜数 / 有效对数。**必须用训练未见、独立来源的评测集**，否则自我循环虚高。

## 6. 数据契约

```jsonc
// eval_set.jsonl
{"id": "ev_001", "prompt": "...", "evidence_text": "<真实原文>", "expected_abstain": true, "gold": {"ticker":"...","direction":"watchlist", ...}}
// before.jsonl / after.jsonl
{"id": "ev_001", "output": "<模型原始输出串(应为简化抽取 JSON)>"}
```

百炼 DPO 训练集 JSONL 格式：**闸③已核实（阿里云百炼官方帮助中心）**——ChatML，`chosen`/`rejected` 是**对象**（非字符串）：

```jsonc
{"messages": [{"role":"system","content":"..."}, {"role":"user","content":"<抽取任务+原文>"}],
 "chosen":   {"role":"assistant","content":"<克制版抽取 JSON 串>"},
 "rejected": {"role":"assistant","content":"<过度承诺版抽取 JSON 串>"}}
```

- 与 HF/TRL 的 `{prompt, chosen, rejected}`（纯字符串）不同 → 由 `scripts/to_bailian.py` 转换。
- 可选 `loss_weight`(0.0-1.0)。**Qwen3-8B(`qwen3-8b`) 确认支持 DPO full + DPO LoRA**；DPO 需上百条。
- 映射：system=抽取系统提示，user=prompt，chosen/rejected.content=对应 JSON 串。

## 7. 阶段计划与三个闸口

| 阶段 | 交付 | 闸口 |
|---|---|---|
| 地基①（本次） | 本 spec | — |
| 地基②（本次） | `scripts/eval_compare.py` + `--demo` dry-run | — |
| 地基③（本次） | `train_dpo.py --smoke-test` | ✅ 通过（**闸① 装包**已授权完成） |
| 数据② | `to_bailian.py` → `data.jsonl` | ✅ **闸③ 已核实**（ChatML 格式 + Qwen3-8B 支持 DPO LoRA）；转换器已建并验证 |
| 数据① | 选 ~120 真实段 → harvest rejected → 校准 chosen → 证据 span 内联 | ⏳ **闸② 烧钱**：批量调基座 Qwen（DashScope，用户 key，对外计费）——待授权 |
| 实跑 | 用户百炼上传/训练/部署/评测 → 回填 `after.jsonl` → `eval_compare` 出真实数字 | 仅用户可做 |

## 8. 架构影响（Architecture Impact）

- **F-stage**：属 F+ Training Loop / F6 Review 闭环，不改 F0-F8 主链路。
- **Schema**：不改任何 Pydantic 模型；`eval_compare.py` **导入**（不重定义）`TradeDirection`/`ActionType` 做合规校验，遵守"Schema 即真相源"。
- **不触碰**：`.env`、密钥、SQLite 表结构、F0-F8 业务代码。
- **复用而非新建**：标注沿用现有 `RLHFReviewPanel` + `Preference` schema + `DPOExporter`，不建独立标注台。

## 9. 关键决策（Key Decisions）

1. **百炼云端线 vs 本地 TRL 线并行**：用户为 Mac 无 GPU，本地 14B 跑不动，百炼为真实训练路径；本地 `train_dpo.py` 仅作 smoke-test 证明训练代码可运行。
2. **偏好轴 = 证据对齐的克制**（非纯结构合规、非纯方向正确）：一条原则驱动三指标且命中"不编造"红线。
3. **半真实数据**（真原文 + 基座真实失败做 rejected）：压低 circularity，使证据挂靠率有意义，rejected 为 on-policy 负样本。
4. **结构合规校验对象 = 简化抽取 JSON**，非完整 canonical `TradeAction`。
5. **偏好胜率防自我循环**：评测集独立来源 + 位置互换一致胜。

## 10. 验证结果（Verification）

### 地基②　`eval_compare.py --demo`（exit 0）

| 指标 | before | after | Δ |
|---|---|---|---|
| 结构合规率 | 0.80 | 1.00 | +0.20 |
| 证据挂靠率（承诺性输出） | 0.00 | 1.00 | +1.00 |
| └ 编造率（越低越好） | 1.00 | 0.00 | -1.00 |
| 偏好胜率 after≻before | — | 0.90 | judge=ref，W/T/L=4/1/0，n=5 |

> 以上为 **DEMO 玩具数据**，说明性、非真实成绩。枚举真相源确认 = `finer.schemas.trade_action`（成功 import，未漂移）。

非 happy-path：`--judge none` 干净跳过偏好胜率；`--judge llm` 明确抛 `NotImplementedError` 指向闸②（不静默伪造）；缺参 argparse 干净报错。

### 地基③　`train_dpo.py --smoke-test`（已通过，闸①已授权装包）

依赖装入 `.venv`（未动全局、未碰 `.env`）：`transformers 5.10.2 / trl 1.5.1 / peft 0.19.1 / accelerate 1.13.0 / datasets 5.0.0`；`bitsandbytes` 按计划在 Mac 跳过。

模型 `trl-internal-testing/tiny-Qwen2ForCausalLM-2.5`（Qwen 族）+ CPU + 4 条玩具偏好对 + 2 步，跑通：

```
Training finished. train_loss=0.6914 (≈ln2，随机权重起点合理 sanity 值)
step1 {'loss':'0.6914','rewards/chosen':'0','rewards/rejected':'0','rewards/margins':'0','logps/chosen':'-524','logps/rejected':'-370'}
step2 {'loss':'0.6914','rewards/margins':'0','logps/chosen':'-310','logps/rejected':'-440'}
=== SMOKE TEST PASSED: DPO 训练循环可运行 ===
```

顺带修复：旧版 trl API → trl 1.x（`DPOTrainer(processing_class=..., peft_config=...)`、`DPOConfig(use_cpu=True, max_steps=2)`、`Dataset.from_list`）。无 traceback。

未触碰任何 schema、`.env`、业务代码。

## 11. 本次变更清单（Changes）

| 文件 | 类型 | 说明 |
|---|---|---|
| `docs/specs/2026-06-07-dpo-bailian-training-line.md` | 新增 | 本方法论契约 |
| `scripts/eval_compare.py` | 新增 | 三指标评测器 + `--demo` self-contained dry-run |
| `scripts/train_dpo.py` | 重写 | 适配 trl 1.x API + 新增 `--smoke-test`（tiny 模型 + CPU + 2 步）|
| `.venv`（依赖） | 安装 | `transformers/trl/peft/accelerate/datasets`（闸①已授权；未动全局/`.env`）|
| `scripts/to_bailian.py` | 新增 | 内部 `{prompt,chosen,rejected}` → 百炼 DPO ChatML；`--demo` + 文件路径均验证 |
| `scripts/select_passages.py` | 新增 | 从真实 chat_history 选候选 evidence_text；真实数据跑出 153 段(写 120) |
| `scripts/harvest_rejected.py` | 新增 | 跑基座→rejected + 规则校准→chosen；`--mock` 全链路验证，真跑需闸② |
| `scripts/run_inference.py` | 新增 | 评测集→before/after.jsonl（base via DashScope / after via 百炼部署 id）；`--mock` 验证 |
| `data/dpo/candidates.jsonl` | 生成 | 120 段真实 KOL 投研候选(gitignored 中间产物) |
| `src/finer/ml/dpo_trainer.py` | 修改 | +`to_bailian_record()` +`DPOExporter.save_bailian_format()`（环 B 百炼输出）|
| `src/finer/ml/export_dpo.py` | 修改 | +`--format {hf,bailian,both}` |
| `docs/specs/2026-06-07-f6-rlhf-to-dpo-mapping.md` | 新增 | 卡①② F6→DPO 字段映射规范（环 B）|
| `src/finer/services/rlhf_assembler.py` | 新增 | 环 B 桥：`build_preference()` corrections→Preference（service 层）|
| `src/finer/api/routes/rlhf.py` | 修改 | `ReviewCorrections` + `RLHFFeedbackCreate.corrections/flagged_as_error` + `/submit` 组装 preference |
| `src/finer_dashboard/.../RLHFReviewPanel.tsx` | 修改 | `handleSubmit` 提交体对齐后端（snake_case + original_extraction）|
| `tests/test_rlhf_assembler.py` | 新增 | assembler 10 项测试（桥行为锁定）|
| `scripts/harvest_rejected.py` | 修改 | 迭代2 校准器：entity_registry 实体可溯 + 降信念而非清零 + conviction（见 §14）|
| `src/finer/ml/dpo_trainer.py` | 修改 | 抽取 prompt + JSON schema 加 `conviction`(0-1) |

## 12. 未解决项（Open Issues）

- ~~百炼 DPO JSONL 格式 + Qwen3-8B 微调可用性（闸③）~~ ✅ 已核实：ChatML（chosen/rejected 为对象）、`qwen3-8b` 支持 DPO LoRA、需上百条。
- ⏳ 闸②（烧钱）未执行：`harvest_rejected.py` 真实跑需 `DASHSCOPE_API_KEY`（不在当前环境，仓库不自动加载 `.env`）。on-policy 建议 `--model qwen3-8b`。
- mock 数据全降级观望（mock 编造西方 ticker 撞中文原文必不溯源）；真实 qwen3-8b 输出更 grounded，chosen 会更丰富——非管线缺陷。
- `select_passages.py` 的 creator 归属多为 unknown（去重时无 creator 标记的 feishu-export 副本排序在前）；不影响段落质量，如需按来源平衡再调。
- held-out 评测集来源：真实 F5 数据未就绪前，先用"不同种子的半真实"兜底，待环 B 换真人精选。
- ~~`train_dpo.py` 对当前 trl 版本的 API 兼容~~ ✅ 已修（trl 1.5.1，smoke-test 验证）。残留：`warmup_ratio` 在 transformers 5.2 将废弃（改 `warmup_steps`），非阻塞。
- 训练依赖尚未声明进 `pyproject.toml`（建议加 `[project.optional-dependencies] train = [transformers,trl,peft,accelerate,datasets]` 便于复现，本次未改 pyproject）。
- `train_dpo.py` GPU/14B 真实路径仅按新 API 写好，**未在本机验证**（无 GPU）；smoke-test 只证明 CPU/tiny 训练循环可运行。
- 证据挂靠率的数字溯源用字符串匹配，存在格式化差异（千分位、币种符号）漏配风险，数据期需加规范化。

## 13. 用户实跑手册（Runbook）

地基 + 数据脚本均已就绪并验证。以下步骤由用户执行（含闸②烧钱与百炼实跑）：

```bash
# 0) 候选已生成：data/dpo/candidates.jsonl（120 段真实原文）。如需重选/调参：
python scripts/select_passages.py --out data/dpo/candidates.jsonl --limit 120 --min-signal 2

# 1) 闸②：harvest rejected（你的 key，on-policy 用 qwen3-8b）。先 --limit 5 试跑确认计费/输出：
export DASHSCOPE_API_KEY=...        # 勿写进代码/日志/会话
python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl --out data/dpo/pairs.jsonl --model qwen3-8b --limit 5
python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl --out data/dpo/pairs.jsonl --model qwen3-8b

# 2) 抽检 pairs.jsonl 的 chosen 侧（复用现有 RLHFReviewPanel 或人工看若干条），剔除明显错的

# 3) 转百炼 ChatML：
python scripts/to_bailian.py --in data/dpo/pairs.jsonl --out data/dpo/data.jsonl

# 4) 百炼控制台：上传 data.jsonl → 选 qwen3-8b → DPO LoRA(dpo_lora) → 训练 → 部署

# 5) 建 held-out 评测集（训练未见、不同来源/种子，每行 id + evidence_text + expected_abstain + gold）
#    例：用 select_passages 取不同 slice，再人工标 gold（20~30 条即可）
python scripts/select_passages.py --src data/raw/9you --out data/dpo/eval/passages.jsonl --limit 30  # 不同来源
#    （把 passages.jsonl 加上 expected_abstain/gold 字段，存为 eval_set.jsonl）

# 6) 基座(before) 与 微调后(after) 各跑一遍评测集
python scripts/run_inference.py --eval-set data/dpo/eval/eval_set.jsonl --out data/dpo/eval/before.jsonl --model qwen3-8b
python scripts/run_inference.py --eval-set data/dpo/eval/eval_set.jsonl --out data/dpo/eval/after.jsonl  --model <部署模型id>

# 7) 三指标对比出真实数字
python scripts/eval_compare.py --eval-set data/dpo/eval/eval_set.jsonl \
    --before data/dpo/eval/before.jsonl --after data/dpo/eval/after.jsonl --judge ref --out report.json
```

红线：真实提升数字只来自第 5 步实跑，不得用 mock/demo 数字冒充。

## 14. 迭代 2：过度弃权修复 + conviction（2026-06-08）

**问题**（迭代 1 真实训练后发现）：150 条训练数据 chosen 里 97% 是不承诺（neutral/watchlist/risk_warning），committal 仅 5 条。根因——校准器 `ticker_in_text` 用**字面子串**判可溯性，中文 KOL 说"腾讯音乐/阿特斯"而模型输出 ticker "TME/CSIQ"，对不上 → 89%(42/47) 的真实承诺被清零为 watchlist。DPO 忠实学到"无脑观望"。

**修复**（`scripts/harvest_rejected.py` calibrate + `dpo_trainer.py` prompt/schema）：
1. **标的可溯性走 `entity_registry`**：字面子串 + 中文别名↔ticker 反查（`_norm_ticker_loose` 解 00700.HK≡0700.HK）。
2. **降信念而非清零**：承诺类一律**保留方向 + 去编造价位 + 按证据强度标 conviction**；只有解析失败才 watchlist。conviction 分级：标的+价位可溯 0.8 / 标的可溯无价位 0.6 / 价位被编 0.45 / 标的未验证 0.3。
3. **prompt + JSON schema 加 `conviction`(0-1)**：让迭代 2 的 rejected 也带 conviction，DPO 学"校准信念"而非只补字段。

**验证**（在迭代 1 的 150 条真实 rejected 上重跑新校准器，零 key）：

| | 旧校准器 | 新校准器 | 基座 rejected |
|---|---|---|---|
| committal(多/空) | 5 | **46** | 47 |
| watchlist | 56 | **8** | 1 |
| chosen==rejected(被丢) | — | 0/150 | — |
| conviction | 无 | 0.2:7 / 0.3:94 / 0.45:1 / 0.5:5 / 0.8:43 | — |

偏好信号保留（0 条 identical）：chosen 与 rejected 的差异 = 去编造价位 + conviction + 诚实 rationale。

**残留约束**：`entity_registry` 仅 ~30 条目，多数标的靠"方向源自原文"给 0.3 低信念（未真正按实体验证）。要更精细需扩充 registry（数据任务）。**迭代 2 需重新 harvest（闸②）+ 重训**，再用同一评测集对比迭代1 vs 迭代2。
