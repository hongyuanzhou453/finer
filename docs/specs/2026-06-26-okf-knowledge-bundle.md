# Finer OKF Knowledge Bundle — 设计契约

> 版本: 0.1.0 (draft) | 创建: 2026-06-26 | 更新: 2026-06-26
> 状态: **phase 0-1 已落地（2026-06-26）。** bundle 已建于 `knowledge/okf/`（8 文件，链接校验 0 坏链）；4 条 memory 已加指针。**待确认**：AGENTS/CLAUDE/MEMORY.md 入口指针。**未做**：validator（phase 2）、B3 入口下沉。
> 用途: 把 OKF(Open Knowledge Format)作为 Finer OS 的 **derived / curated knowledge layer** 引入,作为后续建树与 validator 的权威参考。

---

## 1. 概述与定位

OKF 是 Google Cloud 2026-06-12 发布的 Open Knowledge Format v0.1 draft:一个目录树,里面是带 YAML frontmatter 的 Markdown concept 文件,`index.md` 用于 progressive disclosure,`log.md` 记历史,链接为普通 Markdown 链接。OKF 自身明确**不替代** domain-specific schema,而是引用它们。来源:[Google Cloud blog](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) / [OKF SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)。

### 在 Finer 中是什么

`knowledge/okf/` 是一个 **in-repo、进 git、跨工具可读的 curated knowledge graph**,把当前裂成两块的 curated 知识合并:

- in-repo 散文档(`AGENTS.md` / `docs/specs/*`):结构化弱、不可机器查询;
- Claude-private memory(`~/.claude/projects/.../memory/`):结构化强,但**不在 repo、不进 git、Codex/MiMo 读不到**。

OKF 填的正是 memory 因"私有 + 不在 repo"补不上的缺口。这与 `CLAUDE.md` §0 / `AGENTS.md`「需要跨工具共同遵守的规则必须沉淀到本仓库」一致。

### 不是什么(硬边界)

- **不改运行时架构。** Pydantic schema、pipeline code、F-stage contract 仍是唯一运行时真值。OKF 是 derived 层。
- **不引入新 stage 命名,不复活 L0-L8 / V0-V6。** OKF 只承载 F0-F8 知识,沿用现有命名体系。
- **不改 `pipeline/orchestrator.py`、`src/finer/schemas/`、`AGENTS.md`、`CLAUDE.md`。** 见 §8 迁移边界。

### 核心价值主张

agent(尤其非 Claude 工具)进入项目时,有一个 in-repo、版本化、可机器校验的知识图谱可遍历,快速定位到正确的 canonical 文档,外加 playbook / known-issue 这类「没有别的家」的 curated 知识。

### 核心风险

OKF 退化为第四份**手写真相**,与 `docs/specs/*` / Pydantic schema / memory 分裂。全部缓解手段收敛到一条原则:**link, don't restate**(§6)。

---

## 2. 已对齐的决定(固化)

经三轮方向讨论确认,采用 **A1 + B1 起步,标注 B3 为演进**。本文固化,避免重复论证。

### 决定 A — OKF vs memory 边界:采用 **A1(按知识性质切)**

| 判据 | 归属 |
|---|---|
| 能从 repo + git 重建、且非 Claude 独占要读 | **OKF**(in-repo, 进 git, 跨工具) |
| 关于用户本人 / 给 Claude 的工作纪律 / 带时间快照的会话进度 | **memory**(Claude-private) |

- 重叠的旧 memory 条目:**内容迁 OKF,memory 留一行指针**保留自动召回锚点(memory 有自动召回、OKF 没有)。
- 否决 A4(不划边界 = 两套重叠手写真相);A2(按读者切)判据不稳、迁移量过大;A3(OKF 取代 memory 项目类)丢失自动召回,过度。

### 决定 B — 入口:采用 **B1 起步,B3 演进**

硬约束:Claude Code 自动加载 `CLAUDE.md` / `AGENTS.md`,但**不自动加载 `knowledge/okf/`**。判据是「会不会因漏读而出事」。

| 内容类型 | 起步(B1) | 演进(B3) |
|---|---|---|
| 硬规则(F0-F8 边界、禁跨 stage、密钥、Line F envelope、验证命令) | 留 `AGENTS.md` / `CLAUDE.md` 全文 | 不变,永远留全文 |
| 导航 / 状态(文件速查表、stage 状态、断点清单) | 留 AGENTS,OKF 仅链接 | validator + freshness 上线后下沉 OKF |

- 起步阶段 **AGENTS 不动**,只在 AGENTS/CLAUDE 各加一行指针指向 `knowledge/okf/index.md`。
- 否决 B2(OKF 做入口、AGENTS 砍成指针):硬规则细节流失到非自动加载区,破 derived 定位,牵连跨工具契约。
- **B3 演进的前置条件:§7 validator + freshness 检查跑顺。** 未达成前不下沉任何「必须被读到」的内容。

### 两决定的耦合

选 B1 → A 的迁移压力最小(OKF 不必承载 AGENTS 内容)。若将来走 B3,OKF 要同时吃 memory 知识 + AGENTS 导航,量更大,故 **validator 必须先于 B3 落地**。

---

## 3. Knowledge-surface 对账表(本文核心产出)

每类知识只能有一个 canonical;OKF 角色限 `derived`(可承载,但只链接不重述)或 `absent`(不进 OKF)。

| 知识类型 | Canonical 真值 | OKF 角色 | OKF 可重述? |
|---|---|---|---|
| F-stage 契约(input/output/职责) | `docs/specs/f-stage-contracts.md` | derived | 否,仅链接 + 加 status/关系 |
| F1 标准化契约 | `docs/specs/f1-standardization-contract.md` | derived | 否,仅链接 |
| 数据 Schema 定义 | `src/finer/schemas/*.py`(Pydantic) | derived | 否,仅链接 + 列依赖关系 |
| 数据目录契约 | `CLAUDE.md` §5 | derived | 否,仅链接 |
| API 端点 | FastAPI 生成的 OpenAPI schema | absent(起步) | — 不手写端点概念,链 OpenAPI |
| 已知架构断点 | `AGENTS.md`「最严重架构断点」+ 相关 spec | derived | 部分:可加关系/状态,事实链接 |
| Playbook(golden path、audit-trace 调试等) | **OKF 自身**(无其他家) | **canonical** | 是 — 这是 OKF 唯一持有正文的类别 |
| 硬规则 / 跨工具契约 | `AGENTS.md` / `CLAUDE.md` | absent | — 留自动加载区 |
| 用户画像 / 偏好 | memory `type: user` | absent | — Claude-private |
| 给 Claude 的反馈纪律 | memory `type: feedback` | absent | — Claude-private |
| 会话进度 / 轮次快照 | memory `type: project` | absent | — 时间快照,留 memory |
| 外部资源指针(URL/dashboard) | memory `type: reference` | absent | — |

> 注意:**Playbook 是 OKF 唯一 canonical 持有正文的类别**,因为它在别处没有家。其余一切要么链接 canonical,要么不进 OKF。

---

## 4. OKF vs memory 迁移清单(phase 1)

按决定 A1,起步只迁「稳定架构事实 + 无家的 playbook」,**逐条判**,其余一律留 memory。

| memory 条目 | 处置 | 落点 OKF concept |
|---|---|---|
| `project-overview.md`(F0-F8 架构) | 迁内容,memory 留指针 | `Finer Stage` 索引 |
| `data-schemas.md`(核心数据模型) | 迁内容,memory 留指针 | `Finer Schema` 索引 |
| `canonical-collar-progress.md`(断点部分) | 断点迁,进度快照留 memory | `Finer Known Issue` |
| `f2-llm-entity-proposal.md`(断点部分) | 断点迁,进度/命中率快照留 memory | `Finer Known Issue` |
| `multi-agent-collaboration.md` | **撤销迁移** — 读取后核实为过期通用 CC 工作流（引用的 `/feature-dev`、`code-explorer` 等当前已不存在），不迁；playbook 改用 canonical-golden-path | — |
| `directory-contract.md` | 不迁,OKF 链接到 `CLAUDE.md` §5 | — |
| `coding-conventions` / `testing-and-validation` | 不迁(CLAUDE.md 已有),留 memory | — |
| `feedback-*` / `*-round*` / `advisor-*` / `user` 画像 | 留 memory(会话性/纪律性/时间快照) | — |
| `dashboard-*` / `api-routes` / 各模块实现笔记 | 起步不迁,边界模糊逐条判 | 待定 |

**留指针格式**(memory 条目正文头部加一行):

```
> 架构事实已迁移至 knowledge/okf/stages/index.md;本条仅保留召回锚点与会话进度。
```

---

## 5. Concept type taxonomy(起步 4 类)

type 跟着内容长,不预先铺满。8 类起步 = 一堆 thin/empty 文件先烂掉。

> 约定：每个子目录的 `index.md` 是 OKF 保留文件（聚合 / progressive disclosure 节点），不带 concept `type` 及必填字段；只有具体 concept 文件受 §6 契约约束。

### 起步采用

| type | 职责 | 正文性质 |
|---|---|---|
| `Finer Stage` | F0-F8 各阶段的导航节点:status、上下游关系、断点链接 | 链接为主 |
| `Finer Schema` | 核心 Pydantic 模型的导航节点:依赖关系、canonical 文件位置 | 链接为主 |
| `Finer Known Issue` | 已知架构断点:症状、影响、关联 stage/schema | 关系 + 链接 |
| `Finer Playbook` | golden path、audit-trace 调试等可复用流程 | **正文(唯一 canonical 类)** |

### 砍掉 / 缓做(及原因)

| type | 处置 | 原因 |
|---|---|---|
| `Finer API Endpoint` | 砍 | 最高 drift 最低价值;端点多且常变,FastAPI 已用 OpenAPI 自描述。要 API 知识就链生成的 OpenAPI schema |
| `Finer Artifact` | 缓做 | 与 `CLAUDE.md` §5 数据目录契约大量重叠,先链接 |
| `Finer Quality Gate` | 缓做 | 当前内容稀薄,等有内容再开 |
| `Finer Training Dataset` | 缓做 | 同上,F+ 仍 contract-only |

---

## 6. Frontmatter 契约与 "link, don't restate"

### 铁律:link, don't restate

OKF 文件正文只放**别处没有的东西**——关系、status、「为什么」、known-issue 关联、playbook。**事实本身一律链接出去。** 任何手写重述 canonical 事实的字段都是 drift 源。

具体:**禁止**在 frontmatter 或正文重述契约定义(如把 `f-stage-contracts.md` 的 input/output schema 抄进来)。`owner_paths` 等索引字段允许保留,但**仅供 validator 对账存在性,不作为契约真相**。

### 必填 frontmatter 字段

| 字段 | 含义 | 必填 |
|---|---|---|
| `type` | §5 的 concept type 之一 | 是 |
| `title` | 概念标题 | 是 |
| `description` | 一行摘要(用于召回相关性判断) | 是 |
| `canonical_source` | 指向 repo 内真值文档/代码的路径(Playbook 类填 `self`) | 是 |
| `status` | 沿用 `f-stage-contracts.md` 成熟度词:`production`/`beta`/`alpha`/`placeholder`/`partial` | 是 |
| `timestamp` | ISO8601 含时区 | 是 |
| `tags` | 检索标签 | 否 |
| `f_stage` | 当 type=`Finer Stage`/`Finer Known Issue` 时必填,取值 `F0/F1/F1.5/F2/F3/F4/F5/F6/F7/F8/F+` | 条件 |
| `owner_paths` | 相关代码路径(仅供 validator 对账,非真相) | 否 |
| `links` | 关联 concept 的相对链接 | 否 |

### 范例(Stage 概念,link 形态)

```markdown
---
type: Finer Stage
title: F3 Intent
description: 从 anchored evidence 提取归一化投资意图。
tags: [f-stage, canonical, intent]
f_stage: F3
status: partial
canonical_source: docs/specs/f-stage-contracts.md
owner_paths:
  - src/finer/extraction/intent_extractor.py
  - src/finer/schemas/investment_intent.py
links:
  - ../schemas/index.md
  - ../known-issues/f3-f4-f5-not-closed.md
timestamp: 2026-06-26T00:00:00+08:00
---

F3 接受 F2 的 evidence,产出 `NormalizedInvestmentIntent`。
精确 input/output 契约见 [f-stage-contracts.md](../../docs/specs/f-stage-contracts.md#f3-intent)。

**关系**:上游 F2 Anchor,下游 F4 Policy。
**已知断点**:F3→F4→F5 未闭环,见 [[f3-f4-f5-not-closed]]。
**禁止**:F3 不得生成 TradeAction(职责止于 Intent)。
```

注意正文**没有**抄契约正文,只有关系/状态/链接。

---

## 7. Validator 策略(phase 2)

phase 1 **不写 validator**。phase 2 一个脚本检查:

### 存在性 / 合法性

- 每个非保留 `.md` 有 `type`,且 ∈ §5 起步 4 类;
- `f_stage`(若存在)∈ `F0/F1/F1.5/F2/F3/F4/F5/F6/F7/F8/F+`;
- **禁止 L0-L8 / V0-V6 新术语**出现在任何 concept;
- `owner_paths` 中每条路径在 repo 内存在;
- `canonical_source` 指向 repo 内真值文档/代码(或 Playbook 类的 `self`);
- cross-link 不坏(`links` 与正文 Markdown 链接目标存在)。

### Freshness(B3 前置)

- 若 `canonical_source` 文件的 git 最近改动时间**晚于** OKF 文件的 `timestamp`,告警「OKF 可能过期」。
- 这是 B3 下沉的前置门:freshness 检查不跑顺,不下沉任何「必须被读到」的内容。

---

## 8. 迁移边界(禁止事项)

- 不碰 `pipeline/orchestrator.py`、`src/finer/schemas/`、任何运行时代码;
- 不改 `AGENTS.md` / `CLAUDE.md` 的硬规则正文(起步仅各加一行指针);
- 不引入 L0-L8 / V0-V6,不新增 stage 命名;
- 不在 OKF 重述 canonical 事实(§6 铁律);
- 不实际删除 memory 条目(只加指针);
- 新增/修改 SQLite、批量重建/删除 — 本文不涉及,如未来涉及须先经用户确认。

---

## 9. 分阶段计划

| Phase | 内容 | 产出 |
|---|---|---|
| **0(本文)** | 边界 + taxonomy + frontmatter 契约 + 对账表 | 本 spec |
| **1** | 建 `knowledge/okf/` 树(仅 4 类有内容的);按 §4 迁 memory 那几条;AGENTS/CLAUDE 各加一行指针;memory 留指针 | OKF bundle v0.1 + index.md/log.md |
| **2** | 写 validator(§7 存在性 + freshness) | `scripts/okf_validate.py` + CI 钩子(可选) |
| **3(可选)** | B3:把速查表/stage 状态下沉 OKF(前置:phase 2 跑顺) | 薄化 AGENTS 导航段 |

### Phase 1 目录树(仅建有内容的)

```
knowledge/okf/
├── index.md              # progressive disclosure 入口
├── log.md                # 历史
├── stages/               # Finer Stage(F0-F8)
│   └── index.md
├── schemas/              # Finer Schema(核心模型)
│   └── index.md
├── known-issues/         # Finer Known Issue
│   └── f3-f4-f5-not-closed.md
└── playbooks/            # Finer Playbook(唯一 canonical 正文)
    └── canonical-golden-path.md
```

---

## 10. 未解决项

- **OKF `type` 命名 vs memory `type` enum 的显式区分**:OKF 用 `Finer Stage` 等,memory 用 `user/feedback/project/reference`,两套 type 服务不同层。phase 1 落地时需在 `index.md` 写清边界,避免混淆。
- **模块实现笔记类 memory**(`ingestion-pipeline` / `enrichment-layer` / `dashboard-*` 等)归属未定:介于「架构事实」与「会话进度」之间,起步不迁,phase 1 逐条判。
- **`timestamp` 维护**:phase 1 手填;phase 2 是否由 validator 在 canonical 变更时提示更新待定。
- **CI 接入**:validator 是否进 CI(blocking vs warning)待定,默认起步 warning。
