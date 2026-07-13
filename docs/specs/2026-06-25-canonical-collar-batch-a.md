# 2026-06-25 Canonical 主链路收口 · 批次 A + B

## 概述

按第三方审计 REVISE 结论的"先收口真实主链路 + 证据质量 + legacy 隔离"方向，落地**批次 A（安全收口）+ 批次 B（F2 证据硬门）**：
- **批次 A**：让 `run_golden_path` 不再静默丢 action、把 `/api/extraction/extract` 降级出 canonical 语义、前端 `/audit` 默认切真实后端数据。**让"canonical"标签变诚实**。
- **批次 B**：把 F5 的证据来源从"F3 自证"改为"F2 真实 block 证据"，加 F2-grounding 硬门——接不到 F2 证据的 intent 被 reject；伪造/raw-text envelope 的 action 降级 `partial`，不再假报 canonical（顺带收口批次 A 残留）。

全量后端测试 **2952 passed / 0 failed**、card5 端到端验收、前端 build 全部通过。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/pipeline/golden_path.py` | 修改 | 新增 `GoldenPathResult` dataclass；`run_golden_path` 返回类型 `TradeAction` → `GoldenPathResult`（含全部 action + intents + policy_batch + 计数属性）；`return trade_actions[0]` → 返回完整 result |
| `scripts/card5_acceptance.py` | 修改 | 迁移到 `run_golden_path(...).primary_action`；AS-5d 打印 `action_count` |
| `scripts/card7_feishu_real_f5_run.py` | 修改 | 迁移到 `.primary_action`；trace 新增 `f5_action_count` 与 `trade_actions[]`（落盘全部 action，不再只记第一条） |
| `tests/test_golden_path.py` | 修改 | 迁移到 `.primary_action`；新增 `test_returns_golden_path_result` 与 `test_returns_all_trade_actions_for_multi_intent_envelope`（2 intent → 2 action → 2 F5 文件） |
| `src/finer/api/routes/extraction.py` | 修改 | `POST /extract` 降级为 DEV/DEMO：docstring 明示非 canonical、加 `logger.warning`、`model` 标签 `canonical-{strategy}` → `dev-rawtext-{strategy}` |
| `src/finer_dashboard/src/lib/audit-api.ts` | 修改 | `AUDIT_USE_FIXTURES` 默认翻转为 live（`=== "true"` 才用 fixtures）；修正"后端未实现"过期注释 |
| `src/finer_dashboard/src/app/audit/page.tsx` | 修改 | "演示数据 · Sample data" 徽章常显（移动端不再隐藏）+ 红色强化 |

## 架构影响

- **`run_golden_path` 返回契约变更**：`TradeAction` → `GoldenPathResult`。调用方仅 `scripts/` 与 `tests/`，**无 API route 依赖**（已 grep 确认），blast radius 受控。
- **canonical 语义入口收敛**：`POST /api/extraction/extract` 不再宣称 canonical。canonical 主链路入口为：
  - HTTP：`POST /api/extraction/pipeline`（从 `data/F2_anchored` 读取，已优先走 `run_canonical_from_envelope`）
  - 程序内：`finer.pipeline.canonical_runner.run_canonical_from_envelope()`
- **前端 `/audit` 默认数据源 = live backend**（`GET /api/audit/actions`、`/api/audit/actions/{id}/trace`，见 `src/finer/api/routes/audit.py`）。fixtures 仅作显式 opt-in 且强标 sample。

## 关键决策

1. **`run_golden_path` 选破坏性改返回类型，而非加新 `*_batch` 函数。** 审计要求"函数本身不再只返回第一条"；加新函数会让有损的旧名继续做默认，违背收口目的。
2. **`/extract` 保留功能、仅降级标签，不删除。** 审计明确"降级为 dev/demo"而非"删除"；裸文本便捷入口对开发联调有价值。
3. **`/extract` 产出对象的 `canonical_trace_status` 本次未改（仍自报 canonical）。** 该字段降级涉及 `CanonicalActionBuilder` / 伪造 envelope 的证据逻辑，属批次 B 深水区。本次只收口 API 表层 `model` 标签，对象级 trace status 留作 open issue。
4. **前端默认 live。** 后端 `audit.py` + `tests/test_audit_api.py` 已就绪，具备切真实数据条件；本地无后端时 dev 可 `NEXT_PUBLIC_AUDIT_USE_FIXTURES=true` 回退。

## 验证结果

| 命令 | 结果 |
|------|------|
| `pytest tests/test_golden_path.py tests/test_canonical_runner_quality_gate.py tests/test_canonical_from_envelope.py -q` | 35 passed |
| `pytest tests/test_golden_path.py tests/test_extraction.py tests/test_intent_extractor_canonical.py -q` | 66 passed |
| `python scripts/card5_acceptance.py` | AS-5a..AS-5d PASS；`action_count=1`，`canonical_trace_status==canonical` |
| `cd src/finer_dashboard && npx tsc --noEmit` | clean（无类型错误） |
| `cd src/finer_dashboard && npm run build` | success，`/audit` 静态路由构建通过 |

（批次 A 单独验证时未跑全量；批次 B 已补跑全量见下。）

---

## 批次 B — F2 证据硬门

### 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/pipeline/canonical_runner.py` | 修改 | 新增 `_index_f2_evidence`（按 `evidence_span_id` / `resolved_symbol` / `block_id` 索引 F2 block 证据，容忍 dict 形态）+ `_resolve_f2_grounding`（symbol 优先、block 兜底）；两个 builder（programmatic/llm）改用 F2 grounding 设置 `action.evidence_span_ids` 并加 `evidence_not_grounded_in_f2` 硬门；`run_canonical_from_envelope` / `run_canonical_from_artifacts` 构建 F2 索引替换 F3 自证 evidence_map；持久化的 `F2_evidence` sidecar 改为真实 F2 span |
| `tests/test_canonical_from_envelope.py` | 修改 | `_f2_envelope` 升级为真实 F2 形态（每 anchor 在 block 上挂 grounding span 并回链 `evidence_span_id`/`metadata`）；新增 `test_action_evidence_is_f2_grounded_not_f3`、`test_ungrounded_intent_rejected_by_f2_gate` |

### 架构影响

- F5 canonical TradeAction 的 `evidence_span_ids` 现解析到 **F2 block 证据**（按 ticker / 源 block），不再是 F3 自造 uuid span。审计可见证据 = F2 确定性锚定。
- F2-anchored envelope 中接不到 F2 证据的 intent → F5 **reject**（`evidence_not_grounded_in_f2`），不进入 F8。
- 伪造/raw-text envelope（无 F2 证据）→ `action.evidence_span_ids=[]` → `TradeAction` validator 自动降级 `partial`。**批次 A 残留（对象级假 canonical）随之收口**：raw-text 路径实测 `status=partial`、`evidence=[]`。
- F8 validator（`backtest/validators.py`）保持结构门（`len>=1`）不变；F2-grounding 门设在 F5 边界（符合审计"F5 reject"）。

### 关键决策

1. **重对账放在 F5 边界（canonical_runner），不动 F3 内部。** F3 还要服务无 F2 锚点的 golden_path/raw-text；在 F5 把 action 证据接到 F2，既达成 grounding 又不破坏 F3 其他消费路径。
2. **grounding = symbol 优先 + block 兜底**（design A）。tradeable ticker 必须有 F2 ticker span；symbol-less sector/index intent 用源 block 的 F2 span 兜底——与用户既有"index/sector 如实保留+标注"决定一致（strict symbol-only 会误杀它们）。
3. **dev/raw-text 降级 `partial` 而非 reject。** 保留 `/extract` demo 可用性，同时对象级状态不再假报 canonical。

### 验证结果

| 命令 | 结果 |
|------|------|
| `pytest tests/ -q`（全量） | **2952 passed, 15 skipped, 0 failed**（58s） |
| `pytest tests/test_canonical_from_envelope.py -q` | 10 passed（含 2 个新硬门测试） |
| raw-text 探针 `run_canonical_extraction("看好宁德时代…")` | `status=partial`、`evidence=[]`（批次 A 残留已修复） |

## 未解决项

1. **真实数据已重生成（2026-06-25，用户确认）**：新增 `scripts/regen_canonical_f5.py`（备份→清空→pipeline 重跑→校验每个 action 的 `evidence_span_ids` 解析到 F2_evidence）。产出 12 F5 wrapper / **58 action 全 canonical 全 F2-grounded（0 ungrounded）** / 158 F3 / 158 F4 / 430 F2_evidence；备份 `/tmp/finer_f5_backup_pre_f2gate`。58<59 = F2 门 reject 1 个 ungroundable action（合法）；2 个 0-action envelope 经核查合法（一个无实体锚点、一个全是 watch/avoid 非执行 hint）。`pytest tests/test_audit_api.py` 16 passed。**遗留**：F3/F4=158 未按 P2 过滤（含未产出 action 的 intent），P2 persist-filtering 与 P1 envelope 解析在未合并分支 `origin/fix/audit-envelope-resolution`，待三方合并（base 取当前 HEAD）。
2. **批次 C（证据稳定后）**：F4 仅 `GlobalBasePolicy`（Style/KOLPersona/Risk 未实现）；F1 image/OCR 命中率（`all-local` dry-run hit rate 16.6%）；统一 `src/finer/ml/rewards.py` reward 真相源（当前不存在）。审计明确：先统一 deterministic reward/verifier 再继续 DPO/RLVR，保持 small + human-gated。
