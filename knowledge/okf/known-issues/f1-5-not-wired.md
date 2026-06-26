---
type: Finer Known Issue
title: F1.5 Topic Assembly 未接入 canonical pipeline
description: schema/adapter 已存在，但规则版仅作 fallback，主方向是 constrained-LLM proposal + 确定性 validator
tags: [f1.5, topic-assembly, llm]
f_stage: F1.5
status: alpha
canonical_source: AGENTS.md
owner_paths:
  - src/finer/parsing/topic_assembler.py
  - src/finer/schemas/topic_block.py
timestamp: 2026-06-26T00:00:00+08:00
---

# F1.5 未接入 canonical pipeline

**症状**：`schemas/topic_block.py`、`parsing/topic_assembler.py`、LLM constrained adapter 均已存在，但未接入 canonical 顶层 pipeline。规则版只作 fast path / fallback / regression baseline。

**主方向**：constrained LLM topic proposal + 确定性 validator（与 F2 的 [llm_entity_proposal.py](../../../src/finer/enrichment/llm_entity_proposal.py) 同构）。F1.5 只做语义 topic assembly，不解析 F1 原始格式细节。

权威来源：[AGENTS.md](../../../AGENTS.md) F1.5 段。
