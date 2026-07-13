# Finer 自进化 Skill 模式 — 受约束迭代回路的统一规范

> 日期: 2026-06-30
> F-stage: cross-stage（F+ Training / F2 Anchor / F8 Backtest / F3-F4-F5）
> 状态: proposed
> 分支: docs/f0-review-fixes
> 来源: 华泰金工《自进化 Skill—选股策略的自动迭代》(沈洋/何康, 2026-05-25) 方法论迁移
> 关联: [RLVR-guided DPO v2 任务卡](2026-06-12-rlvr-guided-dpo-task-card.md)、[自进化标注循环](2026-06-13-self-improving-annotation-loop.md)、[F2 锚定命中率](2026-06-26-f2-anchor-hit-rate.md)、[DPO 百炼训练线](2026-06-07-dpo-bailian-training-line.md)

## 0. 结论

把华泰报告里**「约束先行的自进化研究循环」**抄进 finer——但抄的是**三层纪律（协议 / 版本 / 隔离）**，不是选股策略本身。

finer 内部已经有多个「带量化目标、需反复调参」的组件（DPO/RLVR 训练、F2 命中率、KOL 评分权重、F8 回测、F3-F4-F5 策略阈值）。它们今天都在以**非正式、不可复现、易过拟合**的方式被手工迭代。本规范把这些迭代回路统一为一个模式：**Finer-Skill**——一个有「固定内核 + 机器可读可调配置 + 量化评价指标 + 版本化结果 + 样本隔离」的受约束组件。

两条关键改写（finer ≠ 选股）：

1. **样本隔离按 id，不按日期。** 报告按时间段切 train/val/test（因为选股策略是时间序列）。finer 的可调组件作用在 *内容 / passage / 实体* 上，不是单一时间序列，所以隔离必须按 **content-id / block-id** 切 dev / holdout / sealed。这一点 DPO 回路**已经做对了**（`scripts/validate_dpo_hq.py` 把 train/eval id 重叠做成硬失败），F2 等组件需要照抄。
2. **「Skill」= 可迭代的受约束组件，不是策略产品。** 不要在 finer 里造一个「选股器」。finer 不选股，它从 KOL 内容抽事件；可迁移的只有循环纪律。

落地优先级（详见 §7）：**M1 修 F2 样本隔离（小、对症过拟合风险）→ M2 给 DPO/RLVR 回路补 `rewards.py` + 版本注册表（价值最高，已 2/3 完成）→ M3 KOL 权重寻优 / F4 阈值外置（可选）。**

---

## 1. 背景：报告讲了什么、我们抄什么

报告借鉴 Karpathy 的 AutoResearch，把量化选股研究组织为「可执行、可回溯、可约束」的自进化流程。核心论点反直觉：**价值不在于让模型无约束搜参数，而在于用三层结构把「模型能改什么」框死。**

| 报告层 | 回答的问题 | 报告落地物 | finer 该抄的内核 |
|---|---|---|---|
| 策略协议层 | 策略可以怎样变化 | `SKILL.md`（固定内核 + 可调边界 vs 禁改公共代码） | 不变量 / 可调面分离，写成文档纪律 |
| 版本管理层 | 每次变化如何被记录复盘 | `result/skills/{name}/v{n}/`（每版留配置+权重+回测） | 每轮迭代留一条可重建记录 |
| 样本隔离层 | 策略真变好还是更贴合历史 | 训练集生成 / 验证集决定保留 / **测试集不进自动调参闭环** | **按 id 切** dev/holdout/sealed |

报告的实证教训（同样要抄成 finer 的迭代纪律，见 §6）：

- 50 次实验只保留 11 次，夏普 0.69→0.89——提升**温和但稳健**，框架给的是「可复现 + 抗过拟合 + 可审计」，不是 alpha 魔法。
- **有效改进全来自「不偏离内核的小幅可解释调整」**（红利防守权重、阈值、缓冲池数量）；复杂因子替换 / 偏离逻辑的尝试**都没能稳定进入优势版本**。
- 验证集与测试集夏普相关系数仅 **0.34**——验证集筛选有效但远非强相关，所以测试集必须隔离、保留版仍需人工复核。

这套论点**就是 finer CLAUDE.md 的「约束先行」原则**，也与 finer 既有设计（F-stage 边界、schema 即真相源、RLVR verifier 只查表不做语义判断）同构。本规范不是加新功能，是给已经在跑的迭代回路一个成熟度模板。

---

## 2. Finer-Skill 定义

一个组件要成为可自进化的 **Finer-Skill**，必须同时具备：

1. **固定内核（invariants）**：禁止迭代触碰的逻辑——确定性算子、schema 真相源、公共工具函数。
2. **可调面（tunable surface）**：机器可读的参数集（阈值、权重、词表、桶边界），只能在此面内迭代。
3. **量化评价指标**：每轮迭代用同一个指标判断是否保留（hit-rate / reward / rank-corr / Sharpe 等）。
4. **样本隔离**：指标在与「调参所用数据」不相交的 **holdout id 集**上测量。
5. **版本化结果**：每轮产出一条可重建记录（配置快照 + 指标 + id 分区指纹 + 父版本）。

不满足 1–5 的「调参」只是手工试验，不是 Skill 迭代。

---

## 3. 三层框架的 Finer 改写

### 3.1 协议层 — `SKILL.md`

每个 Skill 在其组件目录下放一份 **committed** 的 `SKILL.md`（协议属代码纪律，进 git；run 产物进 `data/`，见 §3.2），至少声明：

- **内核（禁改）**：列出不变量。例：F2 → 「`entity_anchoring.py` 扫描算子、`EntityAnchor` 契约、word-boundary 规则禁改」；DPO → 「verifier 只查表裁决、F8 收益不进 reward、schema 真相源不改」。
- **可调面**：列出本 Skill 允许迭代的参数及其文件位置（指向 §4 的 `skill_config`）。
- **单假设纪律**：每轮迭代只动一个主要假设（见 §6）。
- **保留判据**：holdout 指标提升多少 + 哪些 health-metric 不得恶化，才允许保留为新版本。

放置位置（committed）：`src/finer/ml/SKILL.md`、`src/finer/enrichment/SKILL.md`、`src/finer/backtest/SKILL.md`、`src/finer/policy/SKILL.md`。

### 3.2 版本层 — `data/skills/{name}/v{n}/`

每轮迭代留一条**可重建记录**。run 产物体量大、按 CLAUDE.md `data/` 不进 git，故版本目录落在 `data/`，与现有 `data/dpo/hq_v1/` 同性质。

新 Skill 统一用 `data/skills/{skill_name}/v{n}/`；DPO 现有 `data/dpo/{version}/`（hq_v1、rlvr_v2…）**grandfathered 沿用**，移动属数据迁移，需用户确认（见 §10）。

每个版本目录至少含：

```
data/skills/{name}/v{n}/
  skill_config.snapshot.yaml   # 本轮实际使用的可调参数全量快照
  metrics.json                 # 本轮在 holdout 上的指标
  manifest.json                # 可重建记录（见下）
  eval/                        # holdout 集或其指针（不重复 sealed 集）
```

`manifest.json` 是核心可回溯对象：

```json
{
  "skill": "f2-entity-anchoring",
  "version": "v2",
  "parent_version": "v1",
  "hypothesis": "扩展 stoplist 降噪 + 插入 6 个人工核验实体",
  "code_commit": "95f849f9",
  "config_snapshot": "skill_config.snapshot.yaml",
  "dev_partition_hash": "sha256:…",        // 用于挑词/调参的 id 集指纹
  "holdout_partition_hash": "sha256:…",    // 用于测指标的 id 集指纹（与 dev 不相交）
  "sealed_set_pointer": "data/dpo/hq_v1/eval/eval_set.jsonl",  // 仅人工复核
  "metrics": { "hit_rate": 0.177, "inserted_entity_precision": 0.22 },
  "retained": true,
  "retained_reason": "holdout hit-rate +1.0pp 且 precision gate 通过",
  "created_at": "2026-06-26T00:00:00Z"
}
```

意义：策略优化不再是一次次零起点试验，而是逐步形成一条**可回溯的优化路径**——即便某轮失败，也能从 manifest 明确知道失败来自哪个可调维度。

### 3.3 隔离层 — id-based dev / holdout / sealed（关键改写）

三类 id 集，权限边界严格区分：

| 集 | 用途 | 权限 | finer 现状 |
|---|---|---|---|
| **dev** | 生成候选、挑词、调参 | 可进自动调参闭环 | DPO: train 集；F2: gap-review 候选来源 |
| **holdout** | 决定某版本是否保留 | 只读量指标，**不可反向用于调参** | DPO: eval 集（id 硬隔离）；**F2: 缺失** |
| **sealed** | 最终人工复核、评估真实外推 | **不进任何自动闭环** | DPO: `hq_v1/eval/eval_set.jsonl`（全量人工审核） |

**硬约束**：

- 隔离按 **content-id / block-id** 切，不按日期。每个版本的 manifest 必须记录 `dev_partition_hash` 与 `holdout_partition_hash` 且二者 id 不相交；CI / 校验脚本把重叠做成硬失败（照搬 `scripts/validate_dpo_hq.py` 的 `train/eval overlap id` 硬门）。
- holdout 提升 **≠** 真实能力。报告相关系数 0.34 是警告：保留版仍需 sealed 集人工复核 + 多指标判断，不能只看单一 holdout 指标。

---

## 4. 目录与文件约定

| 内容 | 落点 | 是否 committed |
|---|---|---|
| 协议纪律 | `src/finer/{component}/SKILL.md` | 是 |
| 默认可调参（已有） | `configs/ml_models.yaml` 的 `kol_scorer` / `backtest` / `dpo` 段 | 是 |
| 默认可调参（待迁移） | `configs/skills/{name}.yaml`（F2 阈值/词表元参、F3-F4 阈值） | 是 |
| 版本 run 产物 | `data/skills/{name}/v{n}/`（DPO 沿用 `data/dpo/{version}/`） | 否（data/ gitignore） |
| Skill 注册索引 | 本规范 §5 表 + 后续 `docs/specs/skills-registry.md`（可选） | 是 |

**复用优先、增量改写**：不做「大一统 `skill_config.yaml` 一次性重写」——那会打断现有 loader。`ml_models.yaml` 已有的 `kol_scorer`/`backtest`/`dpo` 段直接视为对应 Skill 的 skill_config；F2/F3/F4 当前硬编码的阈值**逐个迁出到 `configs/skills/`**，迁一个验证一个。`config_snapshot.yaml` 是「本轮实际值」的冻结拷贝，与默认配置解耦。

---

## 5. 组件落点与优先级

| Skill | 组件 | 适配度 | 已具备 | 缺失（=本规范要补的） |
|---|---|---|---|---|
| **dpo-rlvr-loop** | `ml/` + `scripts/` | **高** | 协议(任务卡红线)、**id 级隔离硬门**、版本雏形(`data/dpo/hq_v1/`) | `rewards.py` 单一奖励源未建、闭环未自动化、无独立 val 集、HQ baseline 当前 `ok=false` |
| **f2-entity-anchoring** | `enrichment/` | 中（最有教学意义） | 内核/可调分离干净、命中率指标、stoplist 集中真相源 | **样本隔离缺失→过拟合**、registry 原地改源码无版本 |
| **kol-scorer** | `ml/kol_scorer.py` | 中（结构最像报告） | 4 维加权 YAML 可调(`ml_models.yaml` kol_scorer)、回测真值 | 无权重寻优闭环、回测结果不回流权重 |
| **f8-backtest** | `backtest/` | 中 | 确定性回测、可调 config、产物留存 | 无优化目标、无时间切分、config 只存 4/15 字段、无版本血缘、无 benchmark 相对指标 |
| **f3f4f5-policy** | `policy/` + `extraction/` | 中 | `GlobalBasePolicy._ACTION_RULES` 规则表=理想固定内核 | 阈值全硬编码(非 YAML)、无分阶段正确性指标、F6 反馈不回流 |

> 「适配度」= 当前距离一个完整 Finer-Skill 的接近程度。高 = 三层基本就位只差收尾；中 = 内核/可调结构存在但缺隔离或版本或指标。

---

## 6. 迭代纪律（从报告抄的工程原则）

写进每个 Skill 的 `SKILL.md`，由 Agent / 人共同遵守：

1. **单假设纪律**：每轮迭代只动一个主要可调维度（一个阈值 / 一组权重 / 一批词表）。多方向同时变则无法归因。
2. **小幅可解释 > 复杂堆叠**：优先红利防守权重式的微调（finer 对应：stoplist 扩展、阈值微调、权重重配）；**换 LLM 模型、重写 prompt 架构、替换复杂因子这类「偏离内核」的尝试，默认不进保留版**——除非在 holdout + sealed 双重验证下稳定胜出。F2 的中文规则候选生成已是反例（合成用例全对、真实语料 precision ~6%、已 revert，见 [F2 命中率 spec §4](2026-06-26-f2-anchor-hit-rate.md)）。
3. **holdout 决定保留，sealed 决定可信**：自动闭环只能看 holdout；任何版本进入「可信」前必须过 sealed 人工复核。
4. **复盘多指标、不止单一目标**：不只看 hit-rate / reward total，要看 health-metric（F2: 插入 precision、cohort 分解；DPO: `committal_rate`、幻觉率、margin 中位数；F8: 换手、行业暴露、相对 benchmark）。报告专门警告别让单一市场阶段或少数样本主导结论。
5. **失败也留版**：净负的改动 revert 代码但保留 manifest（`retained:false` + 原因），形成「优化方向网络」，避免重复踩坑。

---

## 7. 路线图

### M0 — 冻结模式（本规范）
产出本文档，定义三层 + 目录约定 + 纪律。不动任何可执行代码。

### M1 — F2 样本隔离修复（首个小验证，低风险）
**问题**：17.7%→18.6% 的命中率，候选从 all-local 队列人工挑、命中率又在**同一份** all-local 上量（[F2 spec §1/§5](2026-06-26-f2-anchor-hit-rate.md)），外推性存疑。报告相关系数 0.34 正是此类风险。
**动作**：
- 把 all-local block-id 集**确定性切分**为 dev（gap-review 候选来源）/ holdout（命中率测量），分区按 content-id 哈希、可复现。
- `scripts/check_f2_coverage_regression.py` 的命中率基线改为**只在 holdout 上量**；dev 上的提升仅供观察。
- registry 插入时校验「插入实体的支撑证据不来自 holdout id」，把 dev/holdout 重叠做成校验失败。
- 落一个 `data/skills/f2-entity-anchoring/v{n}/manifest.json`，回填 v1（16.5%）/v2（17.7%）历史。
**验收**：holdout 命中率可复现；现有 155-passed registry 套件不回归；新增分区不相交断言测试。

### M2 — DPO/RLVR 回路收尾（价值最高）
**前置诊断（2026-06-30 勘察修正）**：HQ baseline `ok=false` 有**两个独立原因**，且 size 是次要的：
- **size**：cleaned 实际只能到 **115**（accept 108 + edit 9 = 117，但 export 把 2 个 `chosen==rejected` 的 accept 正确丢弃 → 106 accept + 9 edit = 115）。原以为可到 117 有误。
- **主因：~56 条 `ticker not grounded in evidence` 硬错误**。抽样确认大部分是 `validate_dpo_hq.ticker_grounded`（= `ticker_in_text` 纯字符串匹配）的**误报**：chosen 用代码 `601899`、证据用公司名「紫金矿业」，字符串匹配跨不了名↔码。少部分是**真问题**（chosen 给了 `UNSPECIFIED`/`未明确`/`XAU` 黄金/`ETF（创新药）` 这类非真实股票代码却仍 committal），应改判 abstention 或剔除。
- **结论：HQ-green 不是降门槛 / 补数据能解决，是 grounding validator 质量问题。** 真正的修法是 registry-aware grounding——这正是 M2 rewards.py 的活，且**复用 F2 `entity_registry.py` 的名↔码映射**（跨 Skill 复用，正是本模式要暴露的价值）。降门槛/补数据议题作废。

**动作**（基本就是 [RLVR 任务卡](2026-06-12-rlvr-guided-dpo-task-card.md) 的落地）：
- 建 `src/finer/ml/rewards.py` 为单一奖励真相源（`RewardBreakdown`：structure=硬门 / grounding 0.50 / calibration 0.40 / abstention 0.10），`eval_compare.py`、`validate_dpo_hq.py`、`harvest_rejected.py::calibrate` 不再各自复制核心逻辑。
- **grounding 改 registry-aware**：`ticker_grounded` 不再只 `ticker_in_text`，先经 `entity_registry` 把 chosen.ticker 反查公司名/别名，任一在证据中出现即算 grounded。残留真问题（UNSPECIFIED/未明确/商品/类别）改判 abstention 或剔除。

**▸ M2 第一步实测结果（2026-06-30，已落地）**
- 建 `src/finer/ml/rewards.py`（单一奖励源：常量+原语+grounding+`RewardBreakdown`/`score_extraction`/`pair_preference`）；`validate_dpo_hq.py` 改从此处取 grounding（删本地有 bug 的 `loose_ticker`/`ticker_grounded`）。`tests/test_rewards.py` 17 测全过；相关套件（harvest_calibrate/annotation_store/annotation_api）53 测全过。
- **实测：grounding 误报 54 → 49，只清掉 5**（紫金矿业/601899 这一类后缀归一化 bug：`loose_ticker("601899")` ≠ `loose_ticker("601899.SH")`，已用 market-aware `tickers_match` 修正，并顺带修掉 `000001.SH`/`00001.HK` 去零后基码同为 `1` 的**跨市场碰撞**潜在误报）。
- **残留 49 不是 grounding 代码问题**，分类：**A 垃圾/畸形 16**（`未明确`/`UNSPECIFIED`/`XAU` + 2 条多代码塞一字段 → 改判 abstention 或剔除，数据活）；**D registry 缺实体 32**（`速腾聚创`/`002889.SZ`/`HES`/`UNP`… 公司不在 `ENTITY_REGISTRY`，名↔码无从查）；**C 1**（`00001.HK` 长和，registry 缺）。
- **（初判）HQ-green 的瓶颈疑似 F2 `entity_registry` 覆盖率**——遂用 `scripts/build_dpo_grounding_gap_review.py` 抽 28 个唯一候选逐条核验。

**▸ 逐条核验结果（2026-07-01，推翻初判）**
- 读证据后发现：这 28 个 claimed ticker **绝大多数是模型幻觉/错码，不是 registry 缺实体**。铁证（记忆无关）：**同一公司被安多个不同代码**——泡泡玛特（证据明确港股：港元/做空股数/回购）被安 `002889.SZ`/`002857.SZ`/`00895.HK`/`09995.HK` 四个码；吉利（0175.HK）被安 `002594.SZ`/`002527.SZ`/`002528.SZ` 三个码。一家公司不可能有 4 个 ticker → **grounding 判未 grounded 完全正确，是 gate 在正常拦截坏对**。
- 分类：**仅 1 个真实且代码正确**（北方华创→002371.SZ，证据点名+代码对）；**~24 个是真实公司+错码**（禾赛被写 `HES`Hess、快手被写 `0177`、阳光电源被写 `300018`…）；余为 name-as-ticker（泡泡玛特/速腾聚创，真实港股但需正确 .HK 码）+ junk 漏网（`ETF（创新药）`）。
- **修正结论**：① 这批 claimed 代码**禁止入 registry**（会 ground 幻觉，正是 F2 spec 警告的污染）。② HQ-green 的真问题是**一批 chosen ticker 幻觉的坏训练对，被人工审核放过了**——grounding gate 事后才抓到。修法是**改正/剔除这些 pair 的 chosen ticker**（数据清洗），并把 grounding gate 前移到审核环节。③ F2 registry 扩展是**另一条独立价值线**：证据里的真实公司名（泡泡玛特/吉利/禾赛/零跑…）确实缺，可另建 NAME→核验代码 worklist 拉 F2 命中率——但**不会修 HQ-green**（因坏对的 chosen 码是错的，加对实体也 ground 不了错码）。
- **关键教训**：grounding gate 消费下游数据时，暴露的往往不是"上游覆盖不足"，而是"本层数据有幻觉"。别把幻觉当缺口去补。
- 加结构化版本注册（`data/dpo/{version}/manifest.json` 按 §3.2 schema），把现有 hq_v1 纳管。
- 在 train/eval 二分之外再切一个**独立 val 集**用于 reward 权重 / conviction 桶调参，避免直接在 pinned eval 上调参过拟合（当前只有 2-way 切分）。
- 把「提议→verifier 打分→留版→复评」接成可重跑 driver（k-best 采样脚本属烧钱闸，需用户授权计费）。
**验收**：reward 逻辑单源；eval_compare 三指标 before/after 在 holdout 上有真实对照；版本可回溯。

### M3 — KOL 权重寻优 / F4 阈值外置（可选）
- KOL: 以「评分 rank 与回测 Sharpe/return 的 rank-correlation」为目标，在 holdout KOL 集上调 `ml_models.yaml` 的 `v2_weights`，留版。
- F4: 把 `global_base.py` 硬编码 conviction 桶 / `intent_extractor.py` confidence 阈值迁到 `configs/skills/f3f4-policy.yaml`，先获得「可调面」，再谈迭代；评价指标用 F6 RLHF 标签做 conviction calibration。

---

## 8. 红线（不动的东西）

- 不改 F0-F8 主链路 schema、`schemas/` 真相源、F-stage 边界。
- 不改 `.env`、密钥、CI/CD、生产部署。
- **SQLite 表结构变更、旧数据迁移、批量重建/删除、把 `data/dpo/` 迁到 `data/skills/`——必须先获得用户确认**（CLAUDE.md 红线）。
- verifier / validator 永远做查表 + 确定性裁决，绝不做语义判断。
- F8 市场收益、KOL 事后表现**不得进入 extractor 训练 reward**（[自进化标注循环 §9](2026-06-13-self-improving-annotation-loop.md)）。
- holdout / sealed id 不得反向进入调参闭环。
- 烧钱操作（k-best 全量采样等）执行前必须用户确认计费；`DASHSCOPE_API_KEY` 等只走 shell env，不进 `.env`/代码/日志。

---

## 9. 验证方式

本规范本身不改可执行代码，验证落在各 M 阶段：

- **M1**：`pytest tests/test_entity_anchoring.py tests/test_backfill_f2_anchor.py -v` 全绿 + 新增「dev/holdout 分区不相交」断言通过；holdout 命中率两次运行一致（确定性）。
- **M2**：`pytest tests/ -v` 不回归；`rewards.py` 有单测覆盖 structure 硬门 / 三维加权 / penalty；`scripts/validate_dpo_hq.py` 对新 manifest 仍把 id 重叠判为硬失败。
- **M3**：KOL 权重调整前后 rank-corr 在 holdout 上可复现；F4 阈值迁移后 `pytest tests/test_policy*.py` 不回归。

---

## 10. 决策记录（2026-06-30 用户拍板）

| # | 议题 | 决策 | 状态 |
|---|---|---|---|
| 1 | DPO 版本目录迁移 `data/dpo/` → `data/skills/dpo/` | **Grandfather 保留 `data/dpo/`**（撤迁移） | ✅ 零风险；skills-registry 已指向 `data/dpo/`，版本 manifest 直接套上去；不动那 17 个引用文件 |
| 2 | HQ baseline `ok=false` | 原选「降门槛到 117」 | ❌ **作废**：勘察修正——cleaned 实际只能到 **115**（非 117），且真正阻塞是 ~56 条 grounding 误报（名↔码），降门槛/补数据都不解决。HQ-green 改并入 M2 registry-aware grounding（见 §7 M2 前置诊断） |
| 3 | 引入 `configs/skills/` 新目录 | 采纳 | ✅ 已建 `configs/skills/{README,f2-entity-anchoring.yaml,f3f4-policy.yaml}` 脚手架（镜像当前硬编码值，尚未 wire） |
| 4 | 纪律优先 vs 自动化 | 先把三层纪律+版本+隔离做扎实（M1/M2 非自动部分），自动 driver 往后放 | ✅ 路线图 §7 已同序 |
| 5 | 跨 Skill 注册索引 | 单独建 `docs/specs/skills-registry.md` | ✅ 已建 |

> 议题 1、2 涉及数据迁移 / 花钱 / 标注完整性，属 CLAUDE.md 红线；勘察暴露了拍板时未知的成本，故带成本二次确认后再执行，不阻塞 M1。
