---
title: Finer Stages (F0-F8)
description: F0-F8 阶段导航与成熟度；契约真值在 f-stage-contracts.md
timestamp: 2026-06-26T00:00:00+08:00
---

# Finer Stages

> 阶段职责 / 输入输出 / owning files 的**契约真值**在 [f-stage-contracts.md](../../../docs/specs/f-stage-contracts.md) 与 [AGENTS.md](../../../AGENTS.md) 核心文件速查表。本页只做导航 + 成熟度，不 restate（避免像 memory 那样漂移）。

| Stage | 名称 | 成熟度 | 关联 |
|---|---|---|---|
| F0 | Intake | implemented | [f-stage-contracts](../../../docs/specs/f-stage-contracts.md) |
| F1 | Standardize | alpha（契约重置中） | [f1 契约](../../../docs/specs/f1-standardization-contract.md) · [契约重置断点](../known-issues/f1-contract-reset.md) |
| F1.5 | Topic Assembly | alpha（未接入 pipeline） | [F1.5 未接入断点](../known-issues/f1-5-not-wired.md) |
| F2 | Anchor | partial | [f-stage-contracts](../../../docs/specs/f-stage-contracts.md) |
| F3 | Intent | partial | [F3→F4→F5 断点](../known-issues/f3-f4-f5-not-closed.md) |
| F4 | Policy | partial | [F3→F4→F5 断点](../known-issues/f3-f4-f5-not-closed.md) |
| F5 | Execute | partial | [F3→F4→F5 断点](../known-issues/f3-f4-f5-not-closed.md) · [canonical golden path](../playbooks/canonical-golden-path.md) |
| F6 | Review | implemented | [f-stage-contracts](../../../docs/specs/f-stage-contracts.md) |
| F7 | Timeline | partial | — |
| F8 | Backtest | partial | — |
| F+ | Training | contract-only | — |

完整流水线与架构见 [ARCHITECTURE.md](../../../docs/ARCHITECTURE.md)。成熟度词义（implemented / alpha / partial / …）见 [f-stage-contracts.md](../../../docs/specs/f-stage-contracts.md) 成熟度定义。
