---
type: Finer Known Issue
title: F3→F4→F5 canonical 路径（已于 2026-07-12 闭环）
description: 历史断点，已解决——legacy 直提路径已被逃生门隔离，保留本条作为迁移背景
tags: [f3, f4, f5, canonical, resolved]
f_stage: F5
status: resolved
canonical_source: AGENTS.md
owner_paths:
  - src/finer/extraction/trade_action_extractor.py
  - src/finer/extraction/intent_extractor.py
  - src/finer/policy/policy_mapper.py
  - src/finer/schemas/trade_action.py
timestamp: 2026-06-26T00:00:00+08:00
---

# F3→F4→F5 未完全闭环（已解决）

> **状态更新（2026-08-06 核实）：本断点已于 2026-07-12 收口，本条保留为迁移背景。**
> canonical 链是唯一现役路径：F5 `TradeAction` 由单一构造点
> `extraction/action_composer.py:compose_trade_action` 产出；legacy 直提与
> deprecated L0-L8 orchestrator 在无 `FINER_ALLOW_LEGACY_PIPELINE=1` 逃生门时
> 硬报错。权威见 [AGENTS.md](../../../AGENTS.md) 与
> [docs/specs/2026-07-12-f5-single-source-collar.md](../../../docs/specs/2026-07-12-f5-single-source-collar.md)。
> 全语料三向审计现为 4,919/4,919 100%（`scripts/audit_trace_integrity.py`）。

**历史症状**：legacy `trade_action_extractor.py` 仍能直接从原始文本生成 `TradeAction`，绕过 F3 Intent 与 F4 Policy。

**当前状态（截至 2026-06-26，以下游 spec 为权威）**：

- `TradeAction` schema 已补 `intent_id` / `policy_id` / `evidence_span_ids` + `canonical_trace_status` 校验器。
- canonical runner 已上 F2 evidence 硬门（无 F2 grounding → 降级 `partial`，不假报 canonical），见 [canonical-collar-batch-a](../../../docs/specs/2026-06-25-canonical-collar-batch-a.md)。
- 仍存：legacy extractor 未下线；F3/F4 落盘含非执行 intent 未过滤。

**硬规则（AGENTS.md）**：F3 **MUST NOT** 生成 TradeAction；F5 canonical TradeAction **MUST** 含 `intent_id` / `policy_id` / `evidence_span_ids` / `execution_timing`。

**怎么跑 canonical 路径**：见 [canonical golden path](../playbooks/canonical-golden-path.md)。

权威来源：[AGENTS.md](../../../AGENTS.md)「最严重架构断点」 · [f-stage-contracts.md](../../../docs/specs/f-stage-contracts.md)。
