---
type: Finer Playbook
title: 跑通 canonical F3→F4→F5 主链路
description: 从 ContentEnvelope 跑出 F2-grounded canonical TradeAction 的入口、不变量与验证
tags: [canonical, golden-path, f3, f4, f5]
status: partial
canonical_source: self
timestamp: 2026-06-26T00:00:00+08:00
---

# Playbook：canonical golden path

把一个 F1 `ContentEnvelope` 跑成 canonical、F2-grounded 的 `TradeAction`。

## 入口

- **API**：`POST /api/extraction/pipeline`（canonical）。
- ⚠️ **不要**用 `POST /api/extraction/extract` —— 已降级为 DEV/DEMO（raw-text，产出非 canonical），见 [canonical-collar-batch-a](../../../docs/specs/2026-06-25-canonical-collar-batch-a.md)。
- 程序入口：canonical runner 的 `run_canonical_from_envelope()`（确切路径见同 spec）。

## 关键不变量

- F5 canonical `TradeAction` 必须含 `intent_id` / `policy_id` / `evidence_span_ids` / `execution_timing`。
- **F2 evidence 硬门**：action 的 evidence 必须 grounded 在 F2 block span（symbol 优先、block 兜底）；无 grounding → 降级 `partial`，不假报 canonical。
- 断点上下文见 [F3→F4→F5 未闭环](../known-issues/f3-f4-f5-not-closed.md)。

## 验证

- `pytest tests/`
- 端到端测试计划见 [canonical-path-test-plan](../../../docs/specs/canonical-path-test-plan.md)。
