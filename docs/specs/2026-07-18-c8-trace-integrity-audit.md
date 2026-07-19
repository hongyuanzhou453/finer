# C8 · AUD-3 三向引用完整性审计（只读，进 CI）

> 版本：v1.0 | 日期：2026-07-18（跨零点收尾 07-19）| 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C8
> 依赖：C7（F4 落盘 + 1,773 回填）——C8 正好审计 C7 补上的 F4 可解引用

## 1. 概述（Overview）

新增只读审计 `scripts/audit_trace_integrity.py`：遍历全部 F5 action，按 /audit assembler 的同一路径约定验三向可解引用（`intent_id→F3` / `policy_id→F4` / `evidence_span_ids→F2`），输出完整率报告（人读 + JSON）并逐条列出断链 action_id 与断链类型。配 CI 门槛测试 `tests/test_audit_trace_integrity.py`（intent/policy 必须 100%，evidence 设 C7 后真实值为底，C9 收紧到 100%）。**只读，不改任何数据。**

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/audit_trace_integrity.py` | 新增 | `audit_trace_integrity(data_root)` 遍历 `F5_executed/*_actions.json` 全部 action，验 `F3_intents/{intent_id}.json` / `F4_policy_mapped/{policy_id}.json` / `F2_evidence/{span_id}.json`(全解析)；断链分类 6 型（missing_intent_id / f3_intent_missing / missing_policy_id / f4_policy_missing / missing_evidence_ids / f2_evidence_missing）；出 `AuditReport`（rates + 逐条 broken）。CLI：`--data-root`/`--json`/`--list-limit`。**只读** |
| `tests/test_audit_trace_integrity.py` | 新增 | 5 例：tmp fixture 逻辑测试（6 断链型全覆盖 + rates + JSON roundtrip + 跳 .bak- 目录 + 缺 F5 目录空报告）；**真实数据门槛守卫**（intent≥100% / policy≥100% / evidence≥5% 底；无数据时 skip） |

## 3. 架构影响（Architecture Impact）

- **F-stage 边界**：横向只读审计（Line V 扩展）。路径约定与 `services/audit_assembler.py` 一致（同一 join key），是 /audit 可解引用性的独立验证器——不复用 assembler 实现，直接验契约，故 assembler 变了 audit 仍守约定。
- **禁改遵守**：一切数据与业务代码零改动；脚本只读 F-stage 目录，仅可选写 JSON 报告到指定路径。
- **CI 守护**：门槛测试进 pytest —— intent/policy 100% 是硬回归门（新 action 若缺 F3/F4 artifact 立刻红）；evidence 底门随 C9 收紧。

## 4. 关键决策（Key Decisions）

1. **evidence 要求「全 span 解析」才算 intact**：一条 action 的 evidence_span_ids 只要有一个 span 无 F2 sidecar，就记 `f2_evidence_missing`（附 missing/total 计数）。同时报 span 级解析率，便于看清缺口幅度。
2. **门槛按 C7 后真实值设定**：intent/policy=100%（C7 让 policy 达 100%），evidence=5% 底（现 6.6%）。C9 F2 重锚写全 sidecar 后把 `EVIDENCE_MIN` 提到 1.0。**不把 evidence 门设成现值精确卡**——留小余量避免噪声红，但仍能抓大回归。
3. **门槛测试对真实数据 + 无数据 skip**：data/ 是 gitignore、机器相关；CI 无数据时 `total_actions==0` → `pytest.skip`，本地/有数据时才断言。既满足卡的「门槛断言」，又不让空 CI 误红。
4. **审计独立于 assembler 实现**：直接按路径约定验文件存在，不 import assembler 的私有解析器——真正的契约审计，而非「assembler 能不能读」。

## 5. 验证结果（Verification）

- 真实数据审计（1,899 F5 action）：
  - `intent_id → F3`：**1899/1899 = 100.0%**
  - `policy_id → F4`：**1899/1899 = 100.0%**（C7 回填之功；回填前 bri 全断）
  - `evidence → F2`（全 span）：**126/1899 = 6.6%**；span 级 505/78315 = 0.6%
  - break_counts：`{'f2_evidence_missing': 1773}` —— 全部 1,773 条 bri action 的 evidence span 无 F2 sidecar（**C9 F2 重锚的活**；非 C8 修）
  - JSON 报告：`data/run_state/audit_trace_integrity.json`（gitignore；1,773 broken 条目全列）
- 测试：`pytest tests/test_audit_trace_integrity.py` → **5 passed**（逻辑 4 + 真实数据门槛 1）。
- 全量：`pytest -q` → **3694 passed, 22 skipped**。

## 6. 未解决项（Open Issues）

- **evidence 6.6% 是已知缺口，非 C8 修**：1,773 条 bri action declare 了 evidence_span_ids（up to 184/条）但对应 `F2_evidence/{span_id}.json` sidecar 不存在（broker F2 路径没写 per-span sidecar）。C9 F2 重锚会写全 → 届时把 `EVIDENCE_MIN` 提到 1.0。
- **bri evidence 数量偏大（单条 up to 184 span）**：疑似引用了整个 envelope 的 span 而非精确 grounding；属 evidence 质量问题（C9 精化），C8 只审可解引用不审精确性。
- **门槛提升是 C9 收口动作**：C9 完成后本卡的 `EVIDENCE_MIN` 应改 1.0，使 CI 硬守三向 100%。
