---
title: Finer Schemas
description: 核心 Pydantic 模型依赖链与文件位置；字段定义真值在 src/finer/schemas/
timestamp: 2026-06-26T00:00:00+08:00
---

# Finer Schemas

> 字段定义的**真值**是 `src/finer/schemas/` 下的 Pydantic 模型（见 [CLAUDE.md §2](../../../CLAUDE.md)）。本页只给依赖链 + 文件位置，不 restate 字段。

## Canonical 依赖链（F0-F8）

```
ContentRecord (F0)
  → ContentEnvelope + ContentBlock (F1)
    → TopicBlock (F1.5)
      → QualityCard + EntityAnchor + TemporalAnchor + EvidenceSpan (F2)
        → NormalizedInvestmentIntent (F3)
          → PolicyMappingResult (F4)
            → TradeAction + ExecutionTiming (F5)
```

## Class → 文件（前缀 `src/finer/schemas/`）

| Schema | 文件 | F-stage |
|---|---|---|
| ContentRecord | `content.py` | F0 |
| ContentEnvelope / ContentBlock | `content_envelope.py` | F1 |
| TopicBlock | `topic_block.py` | F1.5 |
| QualityCard | `quality.py` | F2 |
| EntityAnchor | `entity_anchor.py` | F2 |
| TemporalAnchor | `temporal.py` | F2 |
| EvidenceSpan | `evidence.py` | F2 |
| NormalizedInvestmentIntent | `investment_intent.py` | F3 |
| PolicyMappingResult | `policy.py` | F4 |
| TradeAction / ExecutionTiming | `trade_action.py` | F5 |

> 修改 schema 必须同步前端 `src/finer_dashboard/src/lib/contracts.ts`（见 [CLAUDE.md §2 前后端契约同步](../../../CLAUDE.md)）。
