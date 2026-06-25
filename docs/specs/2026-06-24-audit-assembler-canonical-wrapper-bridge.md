# Audit Assembler — Canonical `*_actions.json` Wrapper Bridge

> 2026-06-24 · F5 / Audit Trace backend · branch `feat/dashboard-audit-trace`

## 概述 (Overview)

证据审计台 `/audit` 的后端 assembler 之前只认 golden_path 风格的每动作单文件
`{trade_action_id}.json`，并显式跳过 `*_actions.json`。但 canonical F2→F3→F4→F5
route（`api/routes/extraction.py`）在真实数据上产出的是 **包裹格式**
`{stem}_actions.json`（`{source_file, extracted_at, model, actions:[...]}`）。本次让
`audit_assembler.py` 兼容包裹格式：遍历 `actions` 展开为逐动作 audit row，区分
canonical wrapper 与 legacy 批量产物，保留 `source_file` 链接。结果：真实
`data/F5_executed`（13 文件 / 59 action）现已被审计台 list/trace 端点完整返回。

## 变更清单 (Changes)

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/services/audit_assembler.py` | 修改 | 解析 canonical `*_actions.json` 包裹文件；新增 `_load_wrapper_entries` / `_is_canonical_wrapper` / `_safe_load_json` / `_safe_load_model_from_obj`；`_build_index_entry` / `_envelope_context` / `_materialized_trace_status` 增加 `source_file` 与 `trust_self_declared`；`IndexedTradeAction` 增加 `source_file` / `from_wrapper` 字段；移除旧的全量跳过 helper `_should_skip_f5_file` |
| `tests/test_audit_api.py` | 修改 | 新增 6 个测试：wrapper 展开、trace bundle 保留 source_file、legacy wrapper（无 canonical marker）仍跳过、HTTP 端点、wrapper 与单文件共存、真实 `data/F5_executed` skipif 冒烟测试 |
| `docs/specs/2026-06-24-audit-assembler-canonical-wrapper-bridge.md` | 新增 | 本文档 |

## 架构影响 (Architecture Impact)

- **只读、零跨层调用**：assembler 仍只读磁盘工件、不调用 pipeline、不写数据，符合
  F6/audit 只读约束。
- **API 契约不变**：`GET /api/audit/actions` 的 `TradeActionSummary` 10 个字段保持不变
  （`test_action_summary_contract_keys` 仍校验精确键集）。`GET /api/audit/actions/{id}/trace`
  的 `AuditTraceBundle` 顶层键集不变；仅在 `envelope` 子对象**新增可选** `source_file`
  键（None 时经 `_drop_none` 丢弃），对前端是向后兼容的附加字段。
- **格式区分点**：canonical wrapper 以 `model` 字段前缀 `canonical-` 判定
  （route 写 `canonical-f2-envelope` / `canonical-programmatic`）。legacy 批量产物
  （旧 extractor，`model` 为原始模型名或缺失）继续被跳过——这正是 `_seed_action_set`
  里无 `model` 的 `legacy_source_actions.json` 仍不计入的原因。
- **trace status 物化**：route 只落 F5，不持久化 F3_intents / F4_policy_mapped 侧车文件。
  对 wrapper 来源的 action（`from_wrapper=True`），当其自带完整 provenance
  （intent_id + policy_id + evidence_span_ids + execution_timing）时，信任其
  schema 已校验的 `canonical_trace_status`，不因侧车缺失而降级为 `partial`。
  golden_path 单文件路径行为完全不变（仍按侧车文件物化）。

## 关键决策 (Key Decisions)

1. **选方案 (a) 改 assembler，而非 (b) 让 route 多写每动作文件。** 把"读取兼容性"
   收敛在唯一消费者（assembler）一处，避免 route 双写磁盘、避免两份真相源漂移。
2. **canonical / legacy 判别用 `model` 前缀，而非"动作里有没有 intent_id"。**
   现有测试里 `legacy_source_actions.json` 内嵌的恰恰是一条带 provenance 的 canonical
   动作却**应被跳过**；若按动作 provenance 判别会破坏该用例。`model=canonical-*`
   是 route 显式写入的稳定标记，零误伤。
3. **wrapper 动作走 JSON round-trip 校验**（`model_validate_json(json.dumps(raw))`）。
   TradeAction 的 enum / datetime 字段是 strict 校验，`model_validate(dict)` 会报
   `is_instance_of` / `datetime_type`；JSON 路径才会做字符串→enum/datetime 的 coercion，
   与既有 `_safe_load_model` 的 `model_validate_json` 行为一致。
4. **真实数据验证用 skipif 冒烟测试**而非硬依赖。`data/` 是 gitignored，CI 无此目录；
   测试默认指向 `<repo>/data` 且无 canonical wrapper 时自动 skip，可用
   `FINER_AUDIT_REAL_DATA_ROOT` 覆盖（worktree 验证时指向主仓库 `data/`）。

## 验证结果 (Verification)

执行环境：worktree `/Users/zhouhongyuan/Desktop/finer-audit-bridge`（`feat/dashboard-audit-trace`），
venv `…/finer/.venv`，真实数据指向主仓库 `…/finer/data`。

**1. 真实数据 — assembler 直调**
```
list_action_summaries(limit=1000) -> total: 59
trace_status 分布: {'canonical': 59}
get_trace_bundle(...) -> status: canonical, envelope.source_file:
  /Users/.../data/F2_anchored/local_8463bb239ea40f59013e5865.json
```

**2. 真实数据 — HTTP 端点（TestClient 打真实 route handler）**
```
GET /api/audit/actions            -> 200 | total: 59 | returned: 59
GET /api/audit/actions/{id}/trace -> 200 | status: canonical | source_file 保留
filter trace_status=canonical     -> 59
filter ticker=MU                  -> 1
```

**3. audit 测试套件**
```
FINER_AUDIT_REAL_DATA_ROOT=…/finer/data pytest tests/test_audit_api.py -q
-> 14 passed（8 原有 + 6 新增；真实数据冒烟测试实跑未 skip）
```

**4. 全量套件 `pytest tests/ -q`**
```
含本次改动:  3 failed, 2593 passed, 68 skipped
clean HEAD:  4 failed, 2587 passed, 67 skipped（未含本次改动，作对照）
```
3 个失败全部在 `test_mimo_vision_config.py` / `test_live_mimo_multimodal.py`
（外加 clean HEAD 偶发的 `test_f0_contract` datetime 用例）——与 audit 无关、不引用
audit、单独运行均通过（全量运行时受全局 env/registry 状态污染、顺序相关），属
feat 分支**预存**问题。本次改动相对 clean HEAD **+6 passed、零回归**。

**5. 前端 flag 连通性**
`lib/audit-api.ts`：`AUDIT_USE_FIXTURES = process.env.NEXT_PUBLIC_AUDIT_USE_FIXTURES !== "false"`。
设为 `false` 时 `getAuditActions` / `getAuditTrace` 调用的正是上面验证过的
`/api/audit/actions` 与 `/api/audit/actions/{id}/trace`，渲染 `res.actions`——后端返回 59
即审计台左栏非空。

## 未解决项 (Open Issues)

- **F3/F4 中间产物未持久化**：route 只落 F5，故 trace bundle 的 `intent` / `policy`
  恒为 `null`，证据列 `evidence_spans` 仍为 `[]`（F2 EvidenceSpan 未持久化，已知 stub）。
  审计台可经 `source_file` 回链 F2 envelope；若要展开完整 F3/F4 卡片，需 route 额外
  持久化 `F3_intents/{intent_id}.json`、`F4_policy_mapped/{policy_id}.json`。
- **envelope 解析靠 content_id 匹配**：wrapper action 的 `source.content_id`（`env_…`）
  与 F2 文件名（`local_…`）不一致，`_load_envelope_for_action` 取不到 envelope，
  envelope 上下文走 fallback（仍带 `source_file`）。若需富 envelope，需要在 route 写出
  时对齐 envelope_id 与文件名，或让 assembler 额外按 `source_file` 直读 F2。
- **分支整合**：本改动在 `feat/dashboard-audit-trace`；真实 F5 route+数据在
  `docs/f0-review-fixes`。两分支合并到同一处后，审计台即可对真实 canonical 数据开箱可用。
- **未做实时浏览器渲染截图**：受 worktree（有 audit 代码）与主仓库（有 data）分离、
  `DATA_ROOT` 无 env 覆盖、前端需 dev proxy 三重因素影响，未起双服务做截图；以真实 HTTP
  端点返回 + 前端连通性逻辑链作为等价证据。
