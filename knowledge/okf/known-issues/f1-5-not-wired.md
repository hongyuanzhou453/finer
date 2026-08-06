---
type: Finer Known Issue
title: F1.5 Topic Assembly（已于 2026-07-12 接入 canonical pipeline）
description: 历史断点，已解决——长内容按 topic 身份逐组过 F3；保留本条作为迁移背景
tags: [f1.5, topic-assembly, llm, resolved]
f_stage: F1.5
status: resolved
canonical_source: AGENTS.md
owner_paths:
  - src/finer/parsing/topic_assembler.py
  - src/finer/schemas/topic_block.py
timestamp: 2026-06-26T00:00:00+08:00
---

# F1.5 未接入 canonical pipeline（已解决）

> **状态更新（2026-08-06 核实）：已于 2026-07-12 接入，本条保留为迁移背景。**
> `run_canonical_from_envelope` 在质量门与 F3 之间经 `parsing/topic_routing.py`
> 路由：长内容（默认 ≥8 块或 ≥2400 字，`FINER_F15_MODE` 可控）装配 TopicBlock
> 后按 topic 身份逐组提取。权威见 [AGENTS.md](../../../AGENTS.md) 与
> [docs/specs/2026-07-12-f15-canonical-wiring.md](../../../docs/specs/2026-07-12-f15-canonical-wiring.md)。

**历史症状**：`schemas/topic_block.py`、`parsing/topic_assembler.py`、LLM constrained adapter 均已存在，但未接入 canonical 顶层 pipeline。规则版只作 fast path / fallback / regression baseline。

**主方向**：constrained LLM topic proposal + 确定性 validator（与 F2 的 [llm_entity_proposal.py](../../../src/finer/enrichment/llm_entity_proposal.py) 同构）。F1.5 只做语义 topic assembly，不解析 F1 原始格式细节。

权威来源：[AGENTS.md](../../../AGENTS.md) F1.5 段。
