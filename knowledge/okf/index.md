---
title: Finer OKF Knowledge Bundle
description: Finer OS 的 derived/curated knowledge layer 入口（in-repo、跨工具、版本化）
timestamp: 2026-06-26T00:00:00+08:00
---

# Finer OKF Knowledge Bundle

Finer OS 的 **derived / curated knowledge layer**：in-repo、进 git、跨工具可读。给任何 agent 一个可遍历的导航层，从这里 progressive disclosure 进入，快速定位到 canonical 真值。

## 铁律：link, don't restate

本 bundle **不持有运行时真值**。运行时真相在：

- Pydantic schema — `src/finer/schemas/`
- F-stage 契约 — [docs/specs/f-stage-contracts.md](../../docs/specs/f-stage-contracts.md)
- 跨工具硬规则 — [AGENTS.md](../../AGENTS.md) / [CLAUDE.md](../../CLAUDE.md)

OKF concept 只放别处没有的东西：关系、status、「为什么」、断点关联、playbook。**事实一律链接出去**。唯一例外是 Playbook（无其他家，持有正文）。

设计契约见 [okf-knowledge-bundle spec](../../docs/specs/2026-06-26-okf-knowledge-bundle.md)。

## 导航

| 类别 | 入口 | 说明 |
|---|---|---|
| Stage | [stages/](stages/index.md) | F0-F8 阶段导航 + 成熟度 |
| Schema | [schemas/](schemas/index.md) | 核心 Pydantic 模型依赖链 + 文件位置 |
| Known Issue | [known-issues/](known-issues/) | 已知架构断点 |
| Playbook | [playbooks/](playbooks/) | 可复用流程（OKF 唯一持有正文的类别） |
| CRD 消费层 | [ARCHITECTURE.md §8.5](../../docs/ARCHITECTURE.md) | 可信度/共识只读视图 + 投影（**非 F-stage**） |

> **动 CRD 或任何面向用户的数字前，先读定位前提**：跨期持续性检验结论为
> 「券商历史超额不能预测未来超额」，产品定位是「审计谁说过什么」而非
> 「预测谁更准」。两条硬纪律（样本充分 ≠ 可以预测；`signal_class` 口径隔离）
> 见 [CLAUDE.md](../../CLAUDE.md) 与
> [2026-08-02-positioning-pivot-proposal.md](../../docs/specs/2026-08-02-positioning-pivot-proposal.md)。

## OKF vs memory 边界

两套 curated 层，职责不重叠：

| | OKF（本 bundle） | Claude memory |
|---|---|---|
| 位置 | in-repo、进 git | `~/.claude/.../memory/`、Claude-private |
| 读者 | 任何工具（Codex / MiMo / Claude） | 仅 Claude Code |
| type 体系 | Finer Stage / Schema / Known Issue / Playbook | user / feedback / project / reference |
| 内容 | 可从 repo+git 重建的架构事实 + playbook | 用户画像、工作纪律、会话进度快照 |

判据：能从 repo+git 重建且跨工具要读 → OKF；关于用户 / 给 Claude 的纪律 / 时间快照 → memory。详见 spec §2–§3。

## 命名约束

只用 F0-F8 canonical 命名。**禁止** L0-L8 / V0-V6（这是 `AGENTS.md` 的硬规则，OKF 同样适用）。
