# RLVR-guided DPO v2 任务卡

> 日期: 2026-06-12
> F-stage: F+ Training Loop
> 状态: proposed (rev2, 2026-06-12 审查修订)
> 前置依赖: HQ v1 人工全量审核与百炼 DPO baseline report

## 0. 结论

Finer 适合把 RLVR 和现有 DPO/HQ 流程结合，但第一步不应直接上在线 RL。当前最稳路径是 **verifier-guided iterative DPO**：把已有确定性 verifier 收敛为 `src/finer/ml/rewards.py`，用于 k-best 采样、自动构造候选偏好对和评测，而最终训练包仍走 HQ 全量人工审核 + 百炼 DPO LoRA。

真正的在线 RLVR/GRPO 可以作为第二阶段。平台事实已更新：百炼当前不仅有 SFT/CPT/DPO 调优线，也提供 `reinforcement` 训练 API，算法支持 `gspo/grpo`，奖励函数通过 HTTP 服务接入。因此旧判断“百炼不支持 online RL”不再作为硬约束；实际约束是工程和运维成本更高，需要先证明 reward 不会被 hack。

## 1. 现状基线

| 资产 | 位置 | 可复用能力 | 当前边界 |
|---|---|---|---|
| 结构校验 | `scripts/eval_compare.py::validate_structure` | JSON 合规、枚举合法、价格区间合法 | 评测脚本内实现，尚未抽为训练可复用模块 |
| 证据溯源 | `scripts/eval_compare.py::assess_evidence` / `ticker_in_text` / `number_in_text` | 标的、价位、trigger 数字是否来自原文 | 数字匹配仍偏字符串级，格式化差异会漏配 |
| 校准器 | `scripts/harvest_rejected.py::calibrate` | conviction 阶梯、去编造价位、`UNRESOLVED` 哨兵 | 当前用于 rejected->chosen 校准，不是统一 reward API |
| HQ 硬门 | `scripts/validate_dpo_hq.py` | 6 键 chosen schema、reviewer coverage、train/eval leakage、grounding | 只校验 cleaned pairs，不参与采样排序 |
| HQ v1 draft | `docs/specs/2026-06-12-dpo-hq-v1-pairs-draft.md` | 220 候选真实调用后保留 152 对 draft | 仍需人工全量审核，不能当作最终训练 truth |
| 上游修复 | `docs/specs/2026-06-12-dpo-harvest-select-root-cause-fix.md` | 幻觉 ticker 收敛为 `UNRESOLVED`，非投资内容过滤 | 重算结果存于 `pairs_draft.recalibrated.jsonl`，未替换 active draft（2026-06-12 曾被未经确认替换，同日审查发现后已恢复原 draft）；替换属数据红线，需用户确认 |

## 2. 平台事实核查

核查日期: 2026-06-12。

官方文档当前给出两条不同入口：

1. 控制台模型调优页仍以 SFT / CPT / DPO 为主线，描述为 `CPT(optional) -> SFT -> DPO(optional)`；这适合 Finer 当前 HQ v1 baseline。
2. 强化学习训练手册提供独立 RL API：`training type = reinforcement`，`algorithm` 当前支持 `gspo/grpo`，并要求 `reward_func_address` 指向 HTTP 奖励函数服务；模型列表包含 Qwen3-8B / 14B / 32B 及 base 版本。

任务卡采用以下判定：

- **短期路径 A**：继续走百炼 DPO LoRA，把 verifier reward 变成数据构造与筛选信号，不引入在线 rollout 运维。
- **中期路径 B**：如果路径 A 两轮后 reward 稳定、baseline 有真实提升，再评估百炼 GRPO 或自管 TRL GRPO。两者都必须复用同一个 `rewards.py` 逻辑，避免评测 reward 与训练 reward 漂移。

## 3. 路径 A 目标

把“已有 verifier”从脚本局部 helper 升级为 F+ Training 的单一奖励真相源，并用它生成第二轮 DPO 数据。

### 成功标准

- `src/finer/ml/rewards.py` 暴露稳定接口，`eval_compare.py`、`validate_dpo_hq.py` 不再各自复制核心 reward 逻辑；`harvest_rejected.py::calibrate()` 通过共享 conviction 桶常量对齐（它是改写器，不整体替换）。
- 新增 k-best 采样脚本可以对每个 prompt 采样 `k=4..8` 个候选，打分并输出 draft pairs。
- 输出 pairs 必须仍经过 HQ 全量人工审核；verifier 只能排序、筛选、打标签，不能直接替代人工 truth。
- 不改 F0-F8 主链路 schema，不改 `.env`、CI、数据库 schema，不触碰生产部署。

## 4. `rewards.py` 接口设计

建议新增 `src/finer/ml/rewards.py`：

```python
@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    structure: float
    grounding: float
    calibration: float
    abstention: float
    penalties: dict[str, float]
    flags: dict[str, bool]
    reasons: list[str]


def score_extraction(output: str | dict[str, Any], evidence_text: str) -> RewardBreakdown:
    """Score one model extraction against source evidence."""


@dataclass(frozen=True)
class ScoredCandidate:
    candidate_id: str
    output_raw: str
    reward: RewardBreakdown


@dataclass(frozen=True)
class PreferenceDecision:
    status: Literal["pair", "near_tie", "all_failed"]
    chosen: ScoredCandidate | None
    rejected: ScoredCandidate | None
    margin: float | None
    reasons: list[str]


def pair_preference(
    candidates: list[ScoredCandidate],
    *,
    min_chosen_score: float,
    min_margin: float,
) -> PreferenceDecision:
    """Pick chosen/rejected for DPO draft construction."""
```

初始权重建议：

| 维度 | 权重 | 规则 |
|---|---:|---|
| structure | gate | JSON 可解析、枚举合法、价格区间合法；**不合规 → total=0、失去 chosen 资格**（解析失败时 grounding/calibration 根本无法计算，故为硬门而非加权项；breakdown 保留 structure 字段仅作诊断） |
| grounding | 0.50 | committal 输出必须 ticker + 数字可溯；幻觉标的/价位重罚 |
| calibration | 0.40 | conviction 与证据强度匹配：0.8 / 0.6 / 0.45 / 0.3 桶（桶常量定义在 rewards.py，为单一真相源） |
| abstention | 0.10 | 仅对证据不足形态的样本给分；与 calibration 的低 conviction 加分分开记账，防止弃权被双重奖励（迭代1塌缩教训） |
| penalty | dynamic | extra keys、`UNRESOLVED` 进入最终 chosen、重复 prompt、输出过短/空 rationale |

关键约束：

- reward 只能看 `prompt/evidence_text/output`，不得看未来收益、F8 回测结果或 KOL 事后表现。
- `UNRESOLVED` 可以作为 draft 审核哨兵，但不得进入 final cleaned training set。
- `NONE` 只表示“无标的观望”；committal + unknown ticker 必须用 `UNRESOLVED` 继续触发人工处理。
- `committal_rate` 必须作为 reward health metric，而不是单纯追求 total score。
- `RewardBreakdown.total` 归一到 `[0,1]`：加权和扣 penalty 后 clamp。§5 的 `min_margin` 与 §8 的 margin 阈值均以该量纲为前提。

## 5. k-best 采样构对脚本契约

建议新增 `scripts/sample_rlvr_dpo_candidates.py`。

> **闸（烧钱，需用户授权）**：全量采样 ≈ 160 prompts × 6 samples ≈ **960 次 qwen3-8b 真实调用**，约为 HQ v1 harvest（闸②）的 6 倍量级。执行前必须用户确认计费；先 `--max-prompts 5` 试跑核对计费口径与输出质量，再放全量。`DASHSCOPE_API_KEY` 只走 shell 环境变量，不进 `.env`/代码/日志。

输入：

```bash
python scripts/sample_rlvr_dpo_candidates.py \
  --in data/dpo/hq_v1/source_candidates.jsonl \
  --out data/dpo/rlvr_v2/pairs_draft.jsonl \
  --report data/dpo/rlvr_v2/reward_report.json \
  --model qwen3-8b \
  --samples-per-prompt 6 \
  --temperature 0.7 \
  --max-prompts 160
```

输出 JSONL 仍沿用 DPO pair 形状：

```json
{
  "prompt": "...",
  "chosen": "{\"ticker\":\"...\"}",
  "rejected": "{\"ticker\":\"...\"}",
  "meta": {
    "passage_id": "...",
    "source": "rlvr_k_best_v2",
    "samples_per_prompt": 6,
    "chosen_reward": {"total": 0.82, "structure": 1.0},
    "rejected_reward": {"total": 0.31, "structure": 1.0},
    "reward_margin": 0.51,
    "requires_human_review": true
  }
}
```

选择规则：

- chosen = 最高分候选，且结构合规、无最终态 `UNRESOLVED`、无 hallucinated committal。
- rejected = 最低分候选，或结构合规但 grounding/calibration 明显差的候选。
- 若最高分与最低分 margin `< 0.2`，不输出 pair，写入 `near_tie.jsonl` 供人工抽检。
- 若所有候选都不合格，不自动调用 `calibrate()` 制造 chosen；写入 `all_failed.jsonl`，避免把 verifier 的修补结果误当模型学习目标。

## 6. 与 HQ 人工数据混合

路径 A 的训练包不应变成纯 verifier 数据。建议第二轮 DPO 数据混合：

| 来源 | 配比 | 预期行数 | 用途 |
|---|---:|---:|---|
| HQ v1 人工全审 cleaned pairs | ~60% | 120-150 | 锁住人工偏好和真实纠错 |
| RLVR k-best pairs（人工审核后） | ~30% | 60-80 | 提升格式、溯源、校准的可验证轴 |
| hard negatives / near ties 人工精选 | ~10% | 20-30 | 防 reward hacking，补 verifier 看不到的方向理解/rationale 质量 |

混合包总量目标 **200-260 行**（与 §7 validate 边界一致），输出 `data/dpo/rlvr_v2/train_mix.jsonl`。混合脚本可以后置为 `scripts/mix_dpo_datasets.py`，但必须给每行打 `meta.source`——注意当前 HQ v1 数据行的 meta **没有** source 字段，对 HQ 行是补打而非保留——并在 report 里输出 source、direction、committal、conviction 分布。

## 7. 验证门

路径 A 完成前必须跑：

```bash
pytest tests/test_harvest_calibrate.py tests/test_select_candidates.py tests/test_annotation_store.py tests/test_annotation_api.py -v
python scripts/eval_compare.py --demo
# RLVR 增量包（人工审核后）
python scripts/validate_dpo_hq.py \
  --pairs data/dpo/rlvr_v2/pairs_cleaned.jsonl \
  --eval data/dpo/hq_v1/eval/eval_set.jsonl \
  --report data/dpo/rlvr_v2/quality_report.json \
  --min-size 60 \
  --max-size 90

# 最终混合训练包
python scripts/validate_dpo_hq.py \
  --pairs data/dpo/rlvr_v2/train_mix.jsonl \
  --eval data/dpo/hq_v1/eval/eval_set.jsonl \
  --report data/dpo/rlvr_v2/train_mix_quality_report.json \
  --min-size 200 \
  --max-size 260
```

held-out 评测集**必须复用 HQ v1 baseline 同一份** `data/dpo/hq_v1/eval/eval_set.jsonl`；v2 不得另建评测集做 before/after 对比，否则与 baseline 不可比。如果该 `eval_set.jsonl` 仍不存在，任务不得声称有真实质量提升；只能报告 reward 分布、人工审核通过率和 demo/self-test 结果。

必须新增/更新测试：

- `tests/test_rewards.py`：结构 gate、grounding、calibration、abstention、penalty、total clamp 的最小覆盖。
- `tests/test_rewards_equivalence.py`：**迁移等价性回归**——在固定 fixture（`--demo` 数据 + 既有 152 对 draft 输出）上，`eval_compare.py` 迁移到 rewards.py 前后三指标逐位一致；若做不到等价，必须用新仪器重跑 HQ v1 baseline report，禁止新旧仪器混用对比。
- `tests/test_sample_rlvr_dpo_candidates.py`：k-best 选择、near-tie 跳过、all-failed 不造 chosen、meta provenance。
- 现有 `test_harvest_calibrate.py` 保持通过，确保 `calibrate()` 与 `rewards.py` 的 conviction 桶一致。

## 8. Reward hacking 防线

已发生过的失败形态：旧校准器把真实承诺大量清零成 watchlist，DPO 学到“无脑观望”。路径 A 必须显式监控：

| 指标 | 触发阈值 | 处理 |
|---|---:|---|
| chosen committal rate | `< 35%` 或较 HQ v1 下降 `> 20pp` | 阻止导出，检查 abstention reward 是否过高 |
| non-committal 构成漂移 | 单一非承诺类别（neutral/watchlist/risk_warning）占比 `> 55%`，或较 HQ v1 基线上升 `> 15pp` | 阻止导出，抽样看是否塌缩进单一保守类别（迭代1塌缩时合计 97% 非承诺，只盯 watchlist 单项会漏报塌进 neutral 的情形） |
| chosen hallucination rate | `> 5%` | 阻止导出，修 grounding reward |
| `UNRESOLVED` in cleaned chosen | `> 0` | 硬失败 |
| reward margin median | `< 0.2` | 不足以构成偏好信号，转人工或重采样 |
| source imbalance | 单一 source `> 70%` | 重混合，避免模型只学 verifier 风格 |

参考基线（HQ v1 draft 152 对，2026-06-12 实测）：committal 39.5%（bullish 51 / bearish 9），neutral 45.4%，watchlist 7.9%，risk_warning 7.2%。

## 9. 路径 B 预研边界

路径 B 不在本任务卡内实现，只保留接口边界：

- 百炼 GRPO：需要把 `rewards.py` 包装成 HTTP reward service，对齐官方 `reward_func_address` / token / timeout / retry 配置。注意官方要求 reward 服务为公网可达 HTTP 端点（文档示例为函数计算），意味着 prompt/evidence_text 将出仓库边界——进入路径 B 前必须先做数据出域评估。
- 自管 TRL GRPO：需要 LoRA checkpoint、rollout 采样、KL 约束和 GPU 预算；reward 函数仍调用 `src/finer/ml/rewards.py`。
- 无论哪条，都不得把 F8 市场收益放进 extractor 训练 reward。F8 可用于 KOL scorer 和独立评估，不用于“原文说什么”的抽取模型训练信号。

进入路径 B 的条件：

1. HQ v1 baseline 已经真实跑完：百炼 DPO LoRA + held-out `eval_compare` report。
2. 路径 A 至少两轮，人工审核通过率和 held-out 指标稳定。
3. reward health report 显示没有 watchlist collapse、ticker 幻觉迁移或 rationale 空洞化。

## 10. 实施顺序

1. **先收尾 HQ v1 baseline**：人工全量审核 152 对，导出 cleaned，跑 `validate_dpo_hq.py`，上百炼 DPO，回填 `after.jsonl`，产出真实 baseline report。
2. 抽出 `src/finer/ml/rewards.py`，把 `eval_compare.py`、`validate_dpo_hq.py` 的核心 verifier 改为 import 它；`harvest_rejected.py::calibrate()` 改为共享 rewards.py 的 conviction 桶常量并加一致性测试（calibrate 是改写器，不做整体 import 替换）。同步跑 §7 的迁移等价性回归，不等价则重跑 baseline。
3. 新增 `sample_rlvr_dpo_candidates.py`，先用 `--mock` 或小样本真实调用验证 provenance、报告和 near-tie 行为。
4. 全量 k-best 采样，输出 `data/dpo/rlvr_v2/pairs_draft.jsonl`，进入 HQ 标注后台全量审核。
5. 混合 HQ v1 + RLVR v2 cleaned pairs，转百炼 ChatML，跑第二轮 DPO。
6. 用同一 held-out eval set 跑 `eval_compare`，只报告真实 before/after，不补猜提升数字。

## 11. 非目标

- 不在本卡内实现 GRPO/PPO/RM。
- 不训练 reward model；当前数据规模不足，且 verifier 可解释性更重要。
- 不改 F3/F4/F5 canonical pipeline。
- 不把 `data/dpo/hq_v1/pairs_draft.recalibrated.jsonl` 自动替换为正式 draft；批量数据替换需用户确认。
- 不把市场收益、回测收益率、KOL 排名作为 extractor 训练 reward。

## 12. 外部资料

- 阿里云百炼控制台模型调优: https://help.aliyun.com/zh/model-studio/model-training-on-console
- 阿里云百炼模型调优简介: https://help.aliyun.com/zh/model-studio/model-training-overview
- 阿里云百炼强化学习训练手册: https://help.aliyun.com/zh/model-studio/rl-training-manual

## 13. 修订记录

- **rev2（2026-06-12，审查修订）**：① structure 由 0.25 加权项改为硬 gate，权重重分为 grounding 0.50 / calibration 0.40 / abstention 0.10；② §5 补烧钱闸（≈960 次 qwen3-8b 调用需用户授权 + `--max-prompts 5` 试跑）；③ §6 配比补预期行数，§7 validate 拆为增量包（60-90）与混合包（200-260）两道，修复原 `--max-size 220` 与配比的算术冲突；④ eval 路径 pin 死为 `data/dpo/hq_v1/eval/eval_set.jsonl`（与 baseline 同源）；⑤ 新增 `test_rewards_equivalence.py` 迁移等价性回归要求；⑥ §8「watchlist rate>50%」改为 non-committal 构成漂移监控，补 2026-06-12 实测基线；⑦ 补 `ScoredCandidate`/`PreferenceDecision` 定义与 `total∈[0,1]` 量纲；⑧ `meta.source` 对 HQ 行明确为补打；⑨ 路径 B 补数据出域评估前置；⑩ §1 记录 `pairs_draft.jsonl` 曾被未经确认替换、审查后已恢复（原 draft 恢复为 active，重算版存 `pairs_draft.recalibrated.jsonl`）。
- **rev1（2026-06-12）**：初稿。
