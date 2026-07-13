---
title: Finer OKF Change Log
description: OKF bundle 变更历史
timestamp: 2026-06-26T00:00:00+08:00
---

# Log

## 2026-06-26 — phase 1 bootstrap

- 建 bundle 骨架：`index` / `log` + `stages` / `schemas` 聚合 index + 3 个 known-issues + 1 个 playbook。
- 迁移来源（按 [spec](../../docs/specs/2026-06-26-okf-knowledge-bundle.md) §4）：
  - memory `project-overview` / `data-schemas` —— **带 48 天过期警告且确有漂移**（目录结构、视觉模型已变），故仅 link 到 AGENTS.md + 代码，不 restate。
  - memory `canonical-collar-progress` / `f2-llm-entity-proposal` —— 提炼结构性断点为 known-issue；命中率/进度数字留 memory。
- 撤销 spec §4 的一项：`multi-agent-collaboration` 经读取核实为**过期的通用 Claude Code 工作流**（引用的 `/feature-dev`、`code-explorer` 等当前 agent registry 已不存在），不作 playbook 源；playbook 改用 canonical golden path。
- 未做（留后续 phase）：validator（phase 2）、B3 入口下沉、stage 单文件拆分。

约定：每个子目录的 `index.md` 是 OKF 保留文件（progressive disclosure 聚合节点），不带 concept `type`；只有具体 concept 文件带 `type` 及必填字段。
