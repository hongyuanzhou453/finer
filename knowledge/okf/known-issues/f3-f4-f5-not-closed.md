---
type: Finer Known Issue
title: F3→F4→F5 canonical 路径未完全闭环
description: legacy trade_action_extractor 仍可绕过 F3/F4 直接从文本生成 TradeAction
tags: [f3, f4, f5, canonical, architecture-break]
f_stage: F5
status: partial
canonical_source: AGENTS.md
owner_paths:
  - src/finer/extraction/trade_action_extractor.py
  - src/finer/extraction/intent_extractor.py
  - src/finer/policy/policy_mapper.py
  - src/finer/schemas/trade_action.py
timestamp: 2026-06-26T00:00:00+08:00
---

# F3→F4→F5 未完全闭环

**症状**：legacy `trade_action_extractor.py` 仍能直接从原始文本生成 `TradeAction`，绕过 F3 Intent 与 F4 Policy。

**当前状态（截至 2026-06-26，以下游 spec 为权威）**：

- `TradeAction` schema 已补 `intent_id` / `policy_id` / `evidence_span_ids` + `canonical_trace_status` 校验器。
- canonical runner 已上 F2 evidence 硬门（无 F2 grounding → 降级 `partial`，不假报 canonical），见 [canonical-collar-batch-a](../../../docs/specs/2026-06-25-canonical-collar-batch-a.md)。
- 仍存：legacy extractor 未下线；F3/F4 落盘含非执行 intent 未过滤。

**硬规则（AGENTS.md）**：F3 **MUST NOT** 生成 TradeAction；F5 canonical TradeAction **MUST** 含 `intent_id` / `policy_id` / `evidence_span_ids` / `execution_timing`。

**怎么跑 canonical 路径**：见 [canonical golden path](../playbooks/canonical-golden-path.md)。

权威来源：[AGENTS.md](../../../AGENTS.md)「最严重架构断点」 · [f-stage-contracts.md](../../../docs/specs/f-stage-contracts.md)。
