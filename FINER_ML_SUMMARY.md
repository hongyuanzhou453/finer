# Finer OS —— ML / 对齐技术总结（供教授讲解）

> 作者视角：LLM 后训练与对齐工程师｜成稿日期：2026-06-23
> 铁律：本文所有结论均回溯到**代码与配置**并标注证据路径（必要时给行号）。凡代码无支撑者，一律标「未在代码中证实」。**「代码真实做到的」与「文档/文案声称的」分栏对照**，不一致处单列于第 §9。
> 一句话定位：把 KOL 社媒投研内容抽成**结构化、可溯源、可回测**的交易观点；ML 核心不是「预测涨跌」，而是用 **DPO + 确定性 verifier** 教模型**忠实抽取 + 证据不足时敢弃权**。

---

# 第一部分【ML 思想】

## S1. 核心问题：把「抽取忠实度」做成可优化目标

项目要解决的不是"预测股价对不对"，而是**"模型有没有忠实于原文、敢不敢在证据不足时弃权"**。这条偏好轴被命名为**「证据对齐的克制」(evidence-aligned restraint)**，并被刻意设计成"一条原则同时驱动三项可测指标"。

- 证据：[docs/specs/2026-06-07-dpo-bailian-training-line.md:25](docs/specs/2026-06-07-dpo-bailian-training-line.md) §3 偏好原则表 —— `chosen` = 证据充分给方向+挂原文可溯证据 / 证据不足给 `watchlist`+低 conviction+诚实 rationale；`rejected` = 弱证据硬给 buy/sell、编造原文没有的 ticker/价位。
- 代码内化：训练脚本的玩具样本注释直接写明哲学 —— "chosen 克制/挂证据，rejected 过度承诺"，prompt 为"证据不足应观望，勿编造"。见 [scripts/train_dpo.py:171](scripts/train_dpo.py)（`smoke_dataset`）与 [src/finer/ml/dpo_trainer.py:121](src/finer/ml/dpo_trainer.py)（prompt 要求"证据不足时**降低 conviction**，而非强行给中性"）。

> 讲解点：这是一个**对齐(alignment)问题**而非纯监督问题——"什么是好答案"无法用单一 gold label 表达（同一段话可有多个合理抽取），所以用**偏好对(preference pair)**而非 SFT 标签来表达"A 比 B 更克制可信"。

## S2. 设计哲学一：reward / verifier「只查表，绝不做语义判断」

verifier 的红线是**确定性、可审计、可复现**——把"语义"（别名、俗称、指代）沉淀进一张**可回填的查找表 `entity_registry`**，而 verifier 本身只做查表 + 规则裁决。

- 证据：[docs/specs/2026-06-13-self-improving-annotation-loop.md:73](docs/specs/2026-06-13-self-improving-annotation-loop.md) —— "verifier 永远做『查表 + 确定性裁决』，绝不做语义判断……一旦让 verifier 自己猜『泡泡』是不是泡泡玛特，它就退化成另一个会幻觉的模型，硬门意义尽失。"
- 落地：F2 实体锚定就是确定性扫描，零 LLM。[src/finer/enrichment/entity_anchoring.py:1](src/finer/enrichment/entity_anchoring.py)（"确定性层……零 LLM 成本、可审计、可复现"），CJK 别名子串匹配 / ASCII 别名词边界匹配（避免 "LI" 误命中 "QUALITY"）。

> 讲解点：这是对 "LLM-as-judge" 的有意规避——judge 用模型就会引入新的幻觉源与不可复现性。项目把可验证的部分交给规则、不可验证的语义交给"人 + 可回填的表"。

## S3. 设计哲学二：奖励刻意**不看**收益 / 回测 / KOL 事后表现

抽取模型的训练信号**只允许看 `prompt / evidence_text / output`**，禁止泄漏未来收益。这是防止"事后正确"污染"忠实抽取"的关键判断。

- 证据（三处重复强调）：
  - [docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md:108](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) —— "reward 只能看 prompt/evidence_text/output，不得看未来收益、F8 回测结果或 KOL 事后表现。"
  - 同文件:225 —— "不得把 F8 市场收益放进 extractor 训练 reward。F8 可用于 KOL scorer 和独立评估，不用于『原文说什么』的抽取模型训练信号。"
  - [docs/specs/2026-06-13-self-improving-annotation-loop.md:129](docs/specs/2026-06-13-self-improving-annotation-loop.md) —— "F8 市场收益不进 extractor 训练 reward。"
- 隔离的另一侧：收益**确实**被使用，但只在 **F7/F8 的 KOL 评分器**里（`return_score` 权重 0.30），与抽取训练完全分离。见 [src/finer/ml/kol_scorer.py:74](src/finer/ml/kol_scorer.py)、[kol_scorer.py:130](src/finer/ml/kol_scorer.py)。

> 讲解点：这是很成熟的 reward design 判断——"忠实于信源"与"信源本身对不对"是两个正交问题，混在一起会让模型学会"挑事后涨的票说得更自信"，即一种 reward hacking。

## S4. 设计哲学三：自改进闭环（人把判断沉淀成确定性资产）

把"异构资料 → 高质量偏好对"做成闭环：**模型提议 → verifier 三态裁决 → 人工裁决 → 沉淀为确定性资产（registry 别名 / reward 权重 / DPO 偏好）→ 下一轮机器能确定性处理的边界扩大、人只处理新增判断**。

- 证据：[docs/specs/2026-06-13-self-improving-annotation-loop.md:10](docs/specs/2026-06-13-self-improving-annotation-loop.md) 与三个回流表 (:42)：①registry 回流（误杀逐轮递减）②模型回流（DPO 让抽取更准、人工改得更少）③reward 校准回流（人对高分项 accept/reject → 防 reward hacking）。
- ⚠️ **状态：`proposed`（待评审），非已建成**。该文件头 (:3) 标 `proposed（现状已只读核查，待评审）`；其 verifier 三态依赖的 `rewards.py` 标「待建」([self-improving-annotation-loop.md:54](docs/specs/2026-06-13-self-improving-annotation-loop.md))。**闭环的"接线"尚未完成**（详见 §9）。

## S5. 工程纪律即对齐纪律：「不编造数字」红线

项目把"诚实"作为一等公民写进脚本与文档：评测脚本对玩具数据强制打 `DEMO 非真实成绩` 横幅；LLM judge 没接线时**故意抛错而非静默伪造**。

- 证据：[scripts/eval_compare.py:240](scripts/eval_compare.py)（`_llm_call` 抛 `NotImplementedError`，注释"现在故意抛错而非静默伪造，守住『不编造』红线"）；[scripts/eval_compare.py:459](scripts/eval_compare.py)（DEMO 横幅）；[docs/specs/2026-06-07-dpo-bailian-training-line.md:11](docs/specs/2026-06-07-dpo-bailian-training-line.md)（红线"不编造提升数字"）。

---

# 第二部分【ML 方法】

## M1. 后训练方法栈：只有 DPO（无 SFT、无在线 RL）

| 方法 | 是否实现 | 证据 |
|---|---|---|
| **SFT** | ❌ 未在代码中证实 | 仓库无 SFT 训练脚本；百炼支持 `CPT→SFT→DPO` 但 Finer 只用 DPO（[rlvr-guided-dpo-task-card.md:31](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md)） |
| **DPO (Direct Preference Optimization)** | ✅ 已实现并真实跑过 | 两条线：本地 TRL（smoke-test）+ 百炼云端真实训练（见下） |
| **RLVR / 在线 RL (GRPO/GSPO)** | ❌ 未实现（路径 B 预研） | [rlvr-guided-dpo-task-card.md:219](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) §9"路径 B 不在本任务卡内实现，只保留接口边界" |
| **Reward Model 训练** | ❌ 明确不做 | [rlvr-guided-dpo-task-card.md:245](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md)"不训练 reward model；当前数据规模不足，且 verifier 可解释性更重要" |

DPO 的损失/参考实现来自 HuggingFace TRL（论文 arXiv:2305.18290），见 [src/finer/ml/dpo_trainer.py:10](src/finer/ml/dpo_trainer.py) 文件头引用。

## M2. 基座模型与两条训练线（关键：默认值 ≠ 实际使用）

**真实训练走百炼云端 `qwen3-8b` 的 DPO-LoRA**；本地 TRL 脚本只做 CPU smoke-test 证明"训练循环可运行"。

- 实际基座：`qwen3-8b`（阿里云百炼 / Model Studio）。证据：[src/finer/ml/dpo_trainer.py:249](src/finer/ml/dpo_trainer.py)（`to_bailian_record` 注释"上传百炼做 DPO LoRA（qwen3-8b）"）、[scripts/train_dpo.py:4](scripts/train_dpo.py)（"真实训练走百炼云端 Qwen3-8B"）、[docs/specs/2026-06-16-dpo-annotation-session-handoff.md:33](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)（部署模型 `qwen3-8b-fa6d13e664dd`）。
- ⚠️ **代码默认值不一致**：`DPOConfig.model_name_or_path` 与 argparse 默认仍是 `Qwen/Qwen2.5-14B-Instruct`（[dpo_trainer.py:59](src/finer/ml/dpo_trainer.py)、[train_dpo.py:227](scripts/train_dpo.py)）——那是本地 TRL 路径的占位默认，**不是实际微调的基座**。讲解时不要把 14B 当成真实基座。
- 训练依赖 `transformers/trl/peft/accelerate/datasets` **不在 `pyproject.toml`**（[pyproject.toml:21](pyproject.toml) 仅 openai/instructor/dashscope），装在 `.venv`，[dpo-bailian-training-line.md:192](docs/specs/2026-06-07-dpo-bailian-training-line.md) 自承"训练依赖尚未声明进 pyproject"。→ 印证"真实训练在云端、本地只 smoke-test"。

## M3. 是否 LoRA / 全参微调？—— **LoRA（参数高效微调），非全参**

- 本地 TRL 路径的 LoRA 配置（可见、确定）：`r=16, alpha=32, dropout=0.05, target_modules=[q_proj, k_proj, v_proj, o_proj], task_type=CAUSAL_LM`。见 [scripts/train_dpo.py:69](scripts/train_dpo.py)（`build_lora_config`）与 [src/finer/ml/dpo_trainer.py:60](src/finer/ml/dpo_trainer.py)。
- 参考模型：`ref_model=None`，PEFT 下以"禁用 adapter 的同模型"作 reference（[train_dpo.py:153](scripts/train_dpo.py)）——DPO 标准做法，省一份模型显存。
- DPO 超参（本地路径）：`beta=0.01`（结构化输出用低 KL 惩罚）、`learning_rate=5e-7`（保守防灾难性遗忘）、`loss_type="sigmoid"`、`num_train_epochs=1`。见 [dpo_trainer.py:46](src/finer/ml/dpo_trainer.py)。
- ⚠️ 百炼云端 LoRA 的实际 `r/alpha` 由百炼控制台设定（`dpo_lora`），**不在仓库代码内**（[dpo-bailian-training-line.md:214](docs/specs/2026-06-07-dpo-bailian-training-line.md)）；真实训练曲线显示实际跑了 **3 epoch**（非默认 1，见 M7）。即"代码默认超参"与"云端实际超参"是两套，仓库只能证实本地一套。

## M4. 奖励 / verifier 设计：四维拆解（确定性规则，非模型判分）

设计上的奖励 = **结构硬门 × (0.50·grounding + 0.40·calibration + 0.10·abstention) − penalty**，归一到 `[0,1]`。

- 设计来源：[docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md:96](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) §4 权重表。
- 四维判定规则与代码落点（**全部是确定性规则，无模型判分**）：

| 维度 | 权重 | 判定规则 | 当前代码落点 |
|---|---|---|---|
| **structure** | gate（硬门） | JSON 可解析 + 枚举合法 + 价格区间 `low≤high≥0`；不合规 → `total=0`、失去 chosen 资格 | [scripts/eval_compare.py:86](scripts/eval_compare.py) `validate_structure` |
| **grounding** | 0.50 | committal 输出的 ticker 与所有引用数字必须在原文可溯；幻觉标的/价位重罚 | [eval_compare.py:182](scripts/eval_compare.py) `assess_evidence` + `ticker_in_text`(:168) + `number_in_text`(:157) |
| **calibration** | 0.40 | conviction 与证据强度匹配，分 4 桶：标的+价位皆溯源 `0.8` / 标的可溯无价位 `0.6` / 价位被编 `0.45` / 标的未验证 `0.3` | [scripts/harvest_rejected.py:207](scripts/harvest_rejected.py) `calibrate` |
| **abstention** | 0.10 | 仅对"证据不足"形态给分，与 calibration 的低 conviction **分开记账**（防弃权被双重奖励——迭代1塌缩教训） | 设计见 task-card:103；Python 端**未聚合实现** |

> ⚠️ **最重要的核验点**：上述**统一加权奖励函数 `src/finer/ml/rewards.py` 在后端 Python 中不存在**（`ls` 确认无此文件；ml/ 仅 `dpo_trainer/export_dpo/kol_scorer/model_config`）。各维度的**判定组件**已分散实现在三个脚本里，但"加权聚合成单一标量 reward"这一步：
> - 后端：**未实现**（task-card 状态 `proposed`，§4"建议新增 rewards.py"）。
> - 前端：**唯一可执行的加权实现**在 TypeScript 演示站 [src/finer_site/src/demo/annotation-data.ts:50](src/finer_site/src/demo/annotation-data.ts)（structure gate→total=0、`grounding=(0.6 if ticker)+(0.4 if price)`、calibration 桶、`abstention=committal?0.4:1`，权重 0.5/0.4/0.1）。它"deterministically and for free"地演示奖励怎么算，但**不参与训练**。
> - 因此 [handoff:41](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) 称"RLVR 奖励（已实现）"是**夸大**：精确说法是"判定组件已实现 + 前端演示实现 + 后端统一奖励真相源未建 + 已完成的第一轮 DPO 未使用该加权 reward"。

**verifier 校验什么 / 刻意不校验什么**：
- 校验：结构合规、ticker 可溯、引用价格/数字可溯、conviction 与证据匹配、是否在该弃权时弃权。
- 刻意不校验：未来收益、回测结果、KOL 事后对错（§S3）；也**不做语义/指代判断**（§S2，交给 registry + 人）。

## M5. 数据管线：「半真实」偏好对构造 + 分层 + 人工硬门

核心创新是**压低 circularity（自我循环 / 数据泄漏）**的"半真实"方案：

```
真实 KOL 群聊原文 (chat_history_*.md)
  │ select_dpo_hq_candidates.py：正则+词表分类 + grounding 门 + 分层抽样
  ▼ candidates.jsonl（按 bullish/bearish/abstain/multi 配额分层）
  │ harvest_rejected.py：跑基座 qwen3-8b 拿"真实失败"做 rejected（on-policy 负样本）
  │                      对 rejected 做确定性规则校准 → chosen（去编造价位/降信念/UNRESOLVED 哨兵）
  ▼ pairs.jsonl
  │ 人工全量审核（/annotation 标注台，verdict ∈ {accept, edit}）
  │ validate_dpo_hq.py：6 键 schema + grounding + train/eval 泄漏硬门 + 去重
  ▼ to_bailian.py → 百炼 ChatML data.jsonl → 百炼 DPO-LoRA
```

- **rejected = 被训模型自己的 on-policy 输出**（不是 agent 虚构的稻草人），chosen 可来自更优来源。证据：[scripts/harvest_rejected.py:4](scripts/harvest_rejected.py)、[handoff:50](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)"rejected 必须是被训模型自己的 on-policy 输出"。这是 DPO 有效性的关键（off-policy rejected 会让学习信号失效）。
- **chosen = 确定性规则校准**（不引入 agent 自由发挥，进一步压低 circularity）：去编造价位、证据不足**降 conviction 而非清零方向**、幻觉 ticker 置 `UNRESOLVED` 哨兵不透传。见 [harvest_rejected.py:169](scripts/harvest_rejected.py) `calibrate`。
- **基座答对则丢弃**（chosen==rejected → 无偏好信号）：[harvest_rejected.py:264](scripts/harvest_rejected.py)。
- **grounding 门 / 防闲聊混入**：committal 类别若无可锚定标的 → 降级 abstain；纯闲聊（无标的+无价格+无信号）硬过滤。见 [scripts/select_dpo_hq_candidates.py:209](scripts/select_dpo_hq_candidates.py)、[:283](scripts/select_dpo_hq_candidates.py)。刻意排除裸 `[A-Z]{2,5}`（飞书链接英文串会误判 ticker），见 `STRICT_CODE_RE` [:32](scripts/select_dpo_hq_candidates.py)。
- **分层抽样**：按 `bullish_action/bearish_risk/abstain/multi_context` 配额（默认 70/45/55/50），固定 seed 可复现。见 [select_dpo_hq_candidates.py:311](scripts/select_dpo_hq_candidates.py)、[:58](scripts/select_dpo_hq_candidates.py)。
- **人工硬门 `validate_dpo_hq.py`**：每对必须有 `reviewer_id` + `review_verdict∈{accept,edit}`；**train/eval 重叠 id = 硬失败**（防泄漏）；chosen 恰好 6 键；committal chosen 的 ticker 必须 grounded；价格必须在原文出现；prompt 去重；数据集大小 120–150。见 [scripts/validate_dpo_hq.py:147](scripts/validate_dpo_hq.py)、泄漏门 [:159](scripts/validate_dpo_hq.py)。

**规模（注意区分"资产总量"与"第一轮子集"，[handoff:38](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) 强调勿混）**：
- 资产总量：`100 条人工偏好 + 31 条文献真值`。
- HQ v1：220 候选 → 真实调用后保留 **152 对 draft** → 人工审 **115 cleaned** → 发现 55 条 ticker 问题 → **精选 20 条 registry-验证 grounded 子集**做第一轮训练。
- 第一轮 held-out 评测：min_signal=2 重建 40 条强信号源 → 标注 **29 条有效 gold**（committal 83%、零 train/eval 泄漏）。
- 证据：[handoff:15-18](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)、[rlvr-guided-dpo-task-card.md:22](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md)。
- 真值来源：真实 KOL 群聊原文（`maodaren`/`9you` 两个 creator）+ 研报 PDF（`F1训练集/`，OCR 后作 F1 输入，**非 DPO 训练对**）；gold 由人工标注。

## M6. 评测方法学：三指标 + 双 judge（其一未接线）

评测器 [scripts/eval_compare.py](scripts/eval_compare.py) 对齐 `before.jsonl`/`after.jsonl` 算三指标：

| 指标 | 性质 | 计算 | 证据 |
|---|---|---|---|
| **结构合规率** structure_compliance_rate | 确定性、免费 | 通过 `validate_structure` 的比例；枚举以 `schemas/trade_action.py` 为真相源 | [eval_compare.py:281](scripts/eval_compare.py) `compute_side` |
| **证据挂靠率** evidence_attachment_rate（= 1 − 编造率） | 确定性、免费、**直测"不编造"** | 仅在**承诺性输出**上计分母；grounded = ticker 可溯 **且** 所有引用数字可溯；`hallucination_rate = (committal−grounded)/committal` | [eval_compare.py:182](scripts/eval_compare.py)、[:302](scripts/eval_compare.py) |
| **偏好胜率** preference_win_rate | 需 judge | `(wins + 0.5·ties)/considered` | [eval_compare.py:313](scripts/eval_compare.py) |

**两种 judge（关键诚实点）**：
- `ref`（ref-match）：与 gold 字段匹配分（direction/ticker/committal 一致性，0–3），免费、可用。多标的样本用 `match-any`。见 [eval_compare.py:198](scripts/eval_compare.py)、[:220](scripts/eval_compare.py)。**脚本自承局限**：ref-match 看不到证据是否真实溯源，可能"before 编造价位但方向/标的恰好对时给高分"（[:201](scripts/eval_compare.py)）——所以须与证据挂靠率并列看。
- `llm`（pairwise，A/B 位置互换消偏置）：**传输层未接线**，`_llm_call` 故意抛 `NotImplementedError`（[eval_compare.py:240](scripts/eval_compare.py)）。→ **当前真实评测只能用 ref judge**。
- 防自我循环：偏好胜率必须用**训练未见的独立 held-out 评测集**（[eval_compare.py:492](scripts/eval_compare.py)、[:80](docs/specs/2026-06-07-dpo-bailian-training-line.md)）。

## M7. 真实结果（标来源 + 局限，不美化）

### (a) 第一轮下游评测（核心交付，[handoff:24](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)）

| 指标 | before（基座 qwen3-8b） | after（DPO 微调） |
|---|---|---|
| 结构合规率 | 100% | 100% |
| 证据挂靠率 | 33.3% | **77.8%** |
| 编造率 | 66.7% | **22.2%** |
| 偏好胜率 after≻before | — | **87.1%**（W/T/L = 13/14/2） |

- 口径：held-out eval **n=29**，**judge=ref**，训练仅用 **20 条** registry-验证精选偏好对，**第一轮、小样本**。
- 局限（handoff 自述，必须照讲）：[handoff:32](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)"第一轮、小样本、chosen 是**校准器质量**、方向验证**非最终模型水平**——after 几乎不退步(负2)、约半数进步"。即 87.1% 胜率里 14/29 是"平"，真实"进步"约半数。

### (b) 真实 DPO 训练过程曲线（xlsx 产物，硬证据）

`DPO-result-2.0/`（推断对应第一轮 finer-DPO-2.0 / qwen3-8b / ~20 条，6 step × 3 epoch）：
- `train/loss` 1.5475 → 0.2470；`eval/loss` 0.9614 → 0.6002
- `rewards/accuracies` 0 → **1.0**；`rewards/margins` 0 → **2.169**
- `logps/chosen` −127.4 → **−65.4**（chosen 概率显著上升）；`logps/rejected` −68.77 → **−68.77**（rejected 几乎不动）
- → 教科书式 DPO 行为：拉高 chosen 似然、压住 rejected。但 `rewards/accuracies=1.0` 在 20 条上达成提示**训练集已完全可分（小样本易过拟合）**，须与下游 held-out 指标并看。

`Qwen-3B训练结果/`（27 step × 3 epoch，≈150 条；推断为更早迭代）：`train/loss` 3.3525 → 0.5042，`rewards/margins` 0 → 1.053。

> ⚠️ **术语澄清（教授易混）**：xlsx 里的 `rewards/*` 是 **DPO 的隐式奖励** `β·log(π_θ/π_ref)`，是 TRL DPOTrainer 的标准诊断量，**不是** §M4 那个 RLVR 外部 verifier reward。两个"reward"同名不同物。

### (c) demo / smoke-test 数字（明确非真实成绩）

- `eval_compare.py --demo`：结构合规 0.80→1.00、证据挂靠 0.00→1.00、偏好胜率 0.90（n=5）——[dpo-bailian-training-line.md:133](docs/specs/2026-06-07-dpo-bailian-training-line.md)，**玩具数据**。（本次 2026-06-23 实跑复现一致，枚举真相源 = `finer.schemas.trade_action` 未漂移；同时确认 `--judge llm` 抛 `NotImplementedError` 不静默伪造。）
- `train_dpo.py --smoke-test`：tiny-Qwen2 + CPU + 2 步，`train_loss=0.6914≈ln2`（随机起点 sanity 值）——[dpo-bailian-training-line.md:151](docs/specs/2026-06-07-dpo-bailian-training-line.md)，只证"训练循环可运行"。

## M8. Agent 流水线 F0–F8 与「证据可溯 / 可回测」的代码实现

Canonical pipeline：`F0 Intake → F1 Standardize → F1.5 Topic Assembly → F2 Anchor → F3 Intent → F4 Policy → F5 Execute → F6 Review → F7 Timeline → F8 Backtest`（[AGENTS.md](AGENTS.md)）。与 ML/对齐直接相关的实现：

- **证据可溯（grounding 的工程基础）**：
  - F2 确定性实体锚定：registry 别名扫描 → `EntityAnchor` + 出现位置 `occurrences`（供 `EvidenceSpan` 消费）。[src/finer/enrichment/entity_anchoring.py:67](src/finer/enrichment/entity_anchoring.py)。
  - 溯源链设计：`TradeAction 字段 ← EvidenceSpan ← OCR span(ContentBlock) ← 原图 bbox`，并要求"追到原图、不接受只追到 OCR 中间产物"。[self-improving-annotation-loop.md:91](docs/specs/2026-06-13-self-improving-annotation-loop.md)。
  - ⚠️ 现状缺口（如实）：MiMo 渲染 OCR 是 chat-vision 范式，**源头不产 bbox**——实测 14 个 PDF：pdfplumber 文本层 253 block 100% 带 bbox，渲染 OCR 104 block **0 带 bbox**。即 region 级锚点断在源头，第一轮走"页级溯源"兜底。[self-improving-annotation-loop.md:135](docs/specs/2026-06-13-self-improving-annotation-loop.md)。
- **可回测（防前视偏差 look-ahead bias）**：
  - `ExecutionTiming` **四时钟显式区分**：`intent_published_at / intent_effective_at / action_decision_at / action_executable_at`。[src/finer/schemas/trade_action.py:403](src/finer/schemas/trade_action.py)。
  - 回测引擎用 `action_executable_at`（可执行时点）而非决策时点取价，避免用"还不可交易的价格"。[src/finer/backtest/converter.py:48](src/finer/backtest/converter.py)、校验器 [validators.py:22](src/finer/backtest/validators.py)（要求 `action_executable_at` 非空 + `evidence_span_ids` 长度 ≥1）。
- ⚠️ **架构断点（非 ML，但影响"证据链"完整性）**：F3→F4→F5 canonical pipeline 未闭环，legacy `trade_action_extractor.py` 仍从原文直接生成 `non_canonical` TradeAction。[AGENTS.md](AGENTS.md)"最严重架构断点"。→ 即"带 intent_id/policy_id/evidence_span_ids 的可溯 TradeAction"schema 已就绪但主链路尚未产出真实数据。

---

# 第三部分【诚实校验：代码 vs 文案】

## §9. 「文档/文案声称」与「代码真实做到」不一致清单

| # | 声称（出处） | 代码真实情况 | 证据 |
|---|---|---|---|
| 1 | "RLVR 奖励（已实现）`结构门×(0.50·grounding+0.40·calibration+0.10·abstention)`"（[handoff:41](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)） | 后端 `src/finer/ml/rewards.py` **不存在**；统一加权奖励**仅前端 TS 演示实现**（annotation-data.ts），**未参与已完成的第一轮 DPO**。判定组件分散在 eval_compare/harvest/validate 三脚本 | `ls ml/` 无 rewards.py；[rlvr-guided-dpo-task-card.md:10](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) 状态 `proposed` |
| 2 | "自改进闭环" | 设计 `proposed`，verifier 三态 + registry 写回(`add_alias`) + reward 校准回流均**待建** | [self-improving-annotation-loop.md:3](docs/specs/2026-06-13-self-improving-annotation-loop.md),[:54](docs/specs/2026-06-13-self-improving-annotation-loop.md);`entity_registry.py` 无 `add_alias` |
| 3 | 基座默认 `Qwen2.5-14B-Instruct`（代码默认值） | 实际微调基座是 **`qwen3-8b`**（百炼）；14B 只是本地 TRL 占位默认，从未真实使用 | [dpo_trainer.py:59](src/finer/ml/dpo_trainer.py) vs [handoff:33](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) |
| 4 | "RLVR" 作为方法名贯穿宣传站 | 后端 Python **无 `rlvr` 标识符**；`verifier`/`reward` 仅各 1 处**无关命中**（[codes.py:226](src/finer/errors/codes.py) 的 verifier 指 API 认证验证器；[enriched_event.py:148](src/finer/schemas/enriched_event.py) 的 reward 是 `risk_reward_ratio` 风险收益比）——**无任何 RLVR verifier/reward 模块**；`rlvr` 仅见于 `src/finer_site/**`（7 文件）+ `docs/**` | grep 2026-06-23 |
| 5 | LLM judge（偏好胜率 pairwise） | 传输层**未接线**，故意抛错；真实评测只能 ref judge | [eval_compare.py:240](scripts/eval_compare.py) |

## §10. 负面 / 警示结果（如实，不美化）

1. **迭代 1 真实训练"学坏"了**：150 条训练数据 chosen 里 **97% 非承诺、committal 仅 5 条**，89%(42/47) 真实承诺被错误清零为 watchlist，"DPO 忠实学到**无脑观望**"。根因：校准器用字面子串判可溯性，中文"腾讯音乐/阿特斯" vs ticker "TME/CSIQ"对不上。[dpo-bailian-training-line.md:234](docs/specs/2026-06-07-dpo-bailian-training-line.md) §14。
2. **committal 49% → 18% 的塌缩 ≠ 训练成果**：这是"剔除 55 条脏 ticker 数据"导致的统计塌缩（承诺样本恰好是被错配那批），被用作"为什么不能简单剔除脏数据"的反面证据，**不是 DPO 指标**。勿当成绩引用。[handoff:39](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)。
3. **第一轮胜率 87.1% 含 14/29「平局」**：after 几乎不退步、约半数进步——是"小样本、第一轮、chosen 为校准器质量"的弱结论，非"最终模型水平"。[handoff:32](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)。
4. **ticker 实体歧义是核心坑**：chosen 把"禾赛"填成赫斯石油 HES、"泡泡玛特"填成错码；根因是 chosen 生成端未接 `entity_registry`；且自动修复会误修（"速腾"被改成禾赛 HSAI）→ 结论"ticker 真值要人定，registry 只给候选"。[handoff:46-48](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)。
5. **`rewards/accuracies=1.0`（训练集）**：20 条上完全可分，是小样本过拟合信号，单看会虚高；须与 held-out 证据挂靠率并看（§M7b）。
6. **成本数字 ≈$792.84 / 13.03 亿 tokens 是跨项目总量**，非 Finer 单一，勿归因到本项目。[handoff:40](docs/specs/2026-06-16-dpo-annotation-session-handoff.md)。

---

# 附表 ①：术语表（项目叫法 ↔ 标准 ML 术语）

| 项目叫法 | 标准 ML 术语 | 说明 |
|---|---|---|
| 证据对齐的克制 (evidence-aligned restraint) | 偏好对齐的目标轴 (preference alignment objective) | DPO 偏好对统一编码的"好答案"定义：忠实 + 该弃权时弃权 |
| DPO | Direct Preference Optimization (arXiv:2305.18290) | 用 (chosen, rejected) 偏好对直接优化策略，免显式 reward model |
| 半真实数据 (semi-real) | on-policy negatives + rule-calibrated positives | rejected=基座自身输出(on-policy)，chosen=确定性规则校准 |
| circularity | 自我循环 / 数据泄漏 / 评测-训练同源 | 刻意压低：chosen 不用 agent 自由生成、judge 用独立 held-out |
| verifier / RLVR 奖励 | rule-based verifiable reward（确定性奖励） | 查表+规则裁决，非 learned reward model、非 LLM-judge |
| 结构门 (structure gate) | hard gate / 结构约束的硬过滤 | 不合规直接 total=0，非加权项 |
| grounding | answer attribution / 证据可溯性 | ticker+数字必须能在原文找到 |
| calibration (conviction 桶) | confidence calibration | 信念强度与证据强度匹配（0.8/0.6/0.45/0.3） |
| abstention | selective prediction / 弃权 | 证据不足输出 watchlist/hold 而非硬给方向 |
| committal | 承诺性输出 | direction∈{bullish,bearish} 或动作链含买卖 |
| `rewards/accuracies`,`margins`（xlsx） | DPO 隐式奖励 `β·log(π_θ/π_ref)` | TRL 标准诊断量，**≠** verifier reward |
| LoRA r/alpha | 参数高效微调 PEFT (low-rank adaptation) | **非全参微调**；只训低秩 adapter |
| ref_model=None (PEFT) | 共享参考策略 | 禁用 adapter 的同模型作 π_ref |
| entity_registry | 实体规范化表 (entity normalization / linking) | 别名→(ticker,market,type)；类比 bio 的 gene/drug normalization |
| 四时钟 ExecutionTiming | look-ahead-bias 防护的时点分离 | decision_at vs executable_at 分离，回测取价用后者 |
| ref-match judge | reference-based automatic eval | 与 gold 字段匹配打分（确定性、免 API） |
| 路径 A / 路径 B | verifier-guided iterative DPO / online RL(GRPO) | A=用 verifier 筛数据仍走 DPO；B=在线 RL（未实现） |

# 附表 ②：数字 ↔ 出处对照表

| 数字 | 含义 | 出处（脚本/文件） | 限定 |
|---|---|---|---|
| 33.3% → 77.8% | 证据挂靠率 before→after | [handoff:27](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | held-out n=29, judge=ref, 第一轮 |
| 66.7% → 22.2% | 编造率 before→after | [handoff:28](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | 同上 |
| 87.1% (W/T/L 13/14/2) | 偏好胜率 after≻before | [handoff:29](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | 含 14 平局，约半数真进步 |
| 100% → 100% | 结构合规率 before→after | [handoff:26](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | 基座已 100%，无提升空间 |
| 20 / 29 | 第一轮训练对数 / held-out gold 数 | [handoff:31](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | 实验子集，非资产总量 |
| 100 + 31 | 人工偏好资产 + 文献真值 | [handoff:38](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | 资产总量，勿与 20/29 混 |
| 220 → 152 → 115 → 20 | 候选→draft→cleaned→精选 | [handoff:17](docs/specs/2026-06-16-dpo-annotation-session-handoff.md),[task-card:22](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) | HQ v1 漏斗 |
| committal 39.5% (bull 51/bear 9) | HQ v1 152 对方向分布 | [task-card:217](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) | 2026-06-12 实测基线 |
| 49% → 18% | committal 剔脏数据塌缩 | [handoff:39](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | **数据处理统计，非 DPO 成果** |
| 迭代1：97% 非承诺 / committal 5 | 迭代1 训练集塌缩 | [dpo-bailian-training-line.md:234](docs/specs/2026-06-07-dpo-bailian-training-line.md) | 负面结果：学到无脑观望 |
| 迭代2 校准：committal 5→46, watchlist 56→8 | 校准器修复对比 | [dpo-bailian-training-line.md:245](docs/specs/2026-06-07-dpo-bailian-training-line.md) | 150 条 rejected 上重跑校准器（非新训练） |
| conviction 桶 0.8/0.6/0.45/0.3 | calibration 分级 | [harvest_rejected.py:207](scripts/harvest_rejected.py) | 确定性规则 |
| reward 权重 0.50/0.40/0.10 | grounding/calibration/abstention | [task-card:96](docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md) | **设计值；后端未聚合实现** |
| LoRA r=16, α=32, dropout=0.05 | 本地 TRL LoRA 配置 | [train_dpo.py:69](scripts/train_dpo.py) | 云端百炼配置不在仓库 |
| β=0.01, lr=5e-7, sigmoid, 1 epoch | DPO 超参（默认） | [dpo_trainer.py:46](src/finer/ml/dpo_trainer.py) | 实际云端跑 3 epoch（见 xlsx） |
| train_loss 1.55→0.25, margins 0→2.17 | DPO-result-2.0 训练曲线 | `DPO-result-2.0/*.xlsx` | 6 step×3ep，≈20 条；推断=第一轮 |
| train_loss 3.35→0.50 (27 step) | Qwen-3B训练结果曲线 | `Qwen-3B训练结果/*.xlsx` | ≈150 条；推断=更早迭代 |
| demo: 结构 0.80→1.00, 挂靠 0.00→1.00, 胜率 0.90 | eval_compare --demo | [dpo-bailian-training-line.md:133](docs/specs/2026-06-07-dpo-bailian-training-line.md) | **玩具数据，非真实成绩** |
| smoke train_loss=0.6914 | train_dpo --smoke-test | [dpo-bailian-training-line.md:151](docs/specs/2026-06-07-dpo-bailian-training-line.md) | tiny 模型 2 步，≈ln2 sanity |
| entity_registry **151** 条目 | 实体表规模 | `len(ENTITY_REGISTRY)` 运行确认（2026-06-23） | 文档旧称"~30"，已扩充 |
| OCR bbox：文本层 253 block 100% / 渲染 OCR 104 block 0% | provenance 现状核查 | [self-improving-annotation-loop.md:135](docs/specs/2026-06-13-self-improving-annotation-loop.md) | 14 个 PDF 实测 |
| return_weight=0.30 | KOL 评分收益权重 | [kol_scorer.py:130](src/finer/ml/kol_scorer.py) | F7/F8 评估用，**不入抽取训练 reward** |
| ≈$792.84 / 13.03 亿 tokens / 93.6% 缓存 | API 用量 | [handoff:40](docs/specs/2026-06-16-dpo-annotation-session-handoff.md) | **跨所有项目总量，非 Finer 单一** |

---

## 一页电梯讲解（口播版）

> Finer 把"投研抽取"做成一个**对齐问题**：不是预测涨跌，而是教模型**忠实于原文、证据不足时敢弃权**。方法是 **DPO**——在阿里云百炼上对 **qwen3-8b** 做 **LoRA**（r=16，非全参）。它的特色有三：①**半真实偏好数据**——rejected 用基座自己的过度承诺输出（on-policy 负样本），chosen 用**确定性规则**把它校准成"去编造价位、降信念不清零方向"，以此压低数据自我循环；②**确定性 verifier**——结构硬门 + grounding + calibration + abstention，全是查表规则不用模型判分，且**刻意不看收益/回测**（收益只用于另一个 KOL 评分器）；③评测用**确定性的证据挂靠率/编造率**为主、ref-match 胜率为辅。第一轮真实结果：编造率 66.7%→22.2%、证据挂靠 33.3%→77.8%、胜率 87.1%（但 n=29、含 14 平、第一轮小样本）。
>
> 必须诚实的三点：(1) 文案说的"RLVR 奖励已实现"——其**统一加权奖励函数后端不存在**（`rewards.py` 待建），只在前端演示站用 TS 实现了，已完成的第一轮 DPO 并未用它；(2) 迭代 1 真实"学坏"过——因中文名↔ticker 对不上，模型学成"无脑观望"，后用 entity_registry 修复；(3) `committal 49%→18%` 是剔脏数据的塌缩、不是成果。整套系统真正成熟的是**工程纪律与诚实口径**（demo 打横幅、judge 不接线就抛错、防泄漏硬门），这比那几个第一轮数字更有讲头。
