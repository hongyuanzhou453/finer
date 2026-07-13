---
type: Finer Known Issue
title: F1 标准化契约重置中
description: 旧 V0 block type / legacy SegmentRecord / L3 perception 与 canonical F1 混杂
tags: [f1, contract-reset, standardization]
f_stage: F1
status: alpha
canonical_source: docs/specs/f1-standardization-contract.md
owner_paths:
  - src/finer/parsing
  - src/finer/schemas/content_envelope.py
  - src/finer/schemas/segment.py
timestamp: 2026-06-26T00:00:00+08:00
---

# F1 契约重置

**症状**：旧 V0 block type、legacy `SegmentRecord`、L3 perception 路径与 canonical F1 混杂，曾导致 F1.5 被迫承担 markdown / HTML / OCR / ASR 后处理等非语义分段职责。

**目标契约**：F1 只输出 canonical `ContentEnvelope` + `ContentBlock[]`，每个 block 带 standardization quality 与 provenance；不做 topic / entity / intent。

**硬规则**：新 F1 代码不得输出 legacy `SegmentRecord` 作为 canonical 结果。

权威来源：[f1-standardization-contract.md](../../../docs/specs/f1-standardization-contract.md)。
