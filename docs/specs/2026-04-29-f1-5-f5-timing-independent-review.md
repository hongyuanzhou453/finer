# Independent Review: F1.5 TopicBlock + F5 Timing + Canonical Action Builder

**Reviewer**: Agent 7 (Independent Review)
**Date**: 2026-04-29
**Scope**: Agent 1-6 deliverables for F1.5 topic assembly, F5 execution timing, and F3→F4→F5 canonical action builder

---

## 1. Overview

Agent 1-6 的核心产出全部存在且功能正确（178 个新增测试全部通过）。初始审查发现 Agent 4 修改 `TradeAction.validate_canonical_trace` 时新增 `execution_timing` 为 canonical 必要条件，但未同步更新 `test_policy_schema.py` 中 5 个已有测试，导致全量测试 5 FAIL。已在审查后修复，全量测试 951 passed / 0 failed。

---

## 2. Agent-by-Agent Verification

### Agent 1: TopicBlock Pydantic Schema

| 检查项 | 结果 |
|--------|------|
| `src/finer/schemas/topic_block.py` 存在 | ✅ |
| `tests/test_topic_block_schema.py` 存在 | ✅ |
| 使用 Pydantic V2 + `ConfigDict(strict=True)` | ✅ |
| `TopicType` 使用 `Literal` 而非 `Enum` | ✅ (L21: `TopicType = Literal["price_action", "fundamental",...]`) |
| Field 全部有 `description` | ✅ |
| 28 tests passed | ✅ |

### Agent 2: Cat Lord Golden Fixture

| 检查项 | 结果 |
|--------|------|
| `tests/fixtures/kol/cat_lord_topic_assembly_input.json` 存在 | ✅ |
| `tests/fixtures/kol/cat_lord_topic_assembly_expected.json` 存在 | ✅ |
| `tests/fixtures/kol/README.md` 存在 | ✅ |
| input JSON 包含 `topic_assembly` + `content_blocks` + `metadata` | ✅ (6 content blocks, 3 topics expected) |
| expected JSON 包含 `topics` + `metadata` | ✅ (3 TopicBlock: price_action, event, macro_trend) |
| `TopicType` 使用 Literal 字符串（非 Enum value） | ✅ |

### Agent 3: Deterministic TopicAssembler

| 检查项 | 结果 |
|--------|------|
| `src/finer/parsing/topic_assembler.py` 存在 | ✅ |
| `tests/test_topic_assembler.py` 存在 | ✅ |
| 位于 `parsing/` 目录（F1 标准化层） | ✅ |
| 纯规则引擎，无 LLM 调用 | ✅ (无 openai/dashscope/instructor import) |
| 导入合规：仅引用 `schemas/` 公共模块 | ✅ (`content_envelope`, `topic_block`) |
| 25 tests passed | ✅ |

### Agent 4: ExecutionTiming Schema

| 检查项 | 结果 |
|--------|------|
| `src/finer/schemas/trade_action.py` 包含 `ExecutionTiming` 类 | ✅ (L392-443) |
| `MarketSession` 使用 `str, Enum` | ✅ (L84-94) |
| `ExecutionTiming` 使用 `ConfigDict(strict=True)` | ✅ (L401) |
| `TradeAction.execution_timing` 字段存在 | ✅ (L559-564, `Optional[ExecutionTiming]`) |
| `validate_canonical_trace` 包含 `has_timing` 检查 | ✅ (L713) |
| **破坏性变更未同步**：`test_policy_schema.py` 5 个测试未更新 | ❌ **ISSUE** |

### Agent 5: Deterministic Timing Policy

| 检查项 | 结果 |
|--------|------|
| `src/finer/execution/__init__.py` 存在 | ✅ |
| `src/finer/execution/timing_policy.py` 存在 | ✅ |
| `tests/test_execution_timing_policy.py` 存在 | ✅ |
| 位于 `execution/` 目录 | ✅ |
| 纯规则引擎，无 LLM 调用 | ✅ |
| 仅导入 `schemas/trade_action.py`（公共模块） | ✅ |
| 42 tests passed (34 + 8 parametrized) | ✅ |

### Agent 6: Canonical Action Builder

| 检查项 | 结果 |
|--------|------|
| `src/finer/extraction/canonical_action_builder.py` 存在 | ✅ |
| `tests/test_canonical_action_builder.py` 存在 | ✅ |
| 位于 `extraction/` 目录（F5） | ✅ |
| 导入合规：F3 intent + F4 policy + F2 evidence/temporal + F5 trade_action | ✅ (均为 schema 公共模块) |
| 无跨 F-stage 直接调用 | ✅ |
| 36 tests passed | ✅ |
| `canonical_action_builder.py` 代码质量 | ✅ (dataclass, frozen, type hints 完整, docstrings) |

---

## 3. Test Results

### Targeted Tests (Agent 1-6 deliverables)

```
tests/test_topic_block_schema.py .............. 28 passed
tests/test_topic_assembler.py ................. 25 passed
tests/test_execution_timing_policy.py ......... 42 passed
tests/test_canonical_action_builder.py ........ 36 passed
tests/test_canonical_f3_f4_f5_contract.py ..... 47 passed
-------------------------------------------------------
Total: 178 passed, 0 failed
```

### Full Test Suite

```
972 collected → 946 passed, 5 failed, 21 skipped（修复后：972 collected → 951 passed, 0 failed, 21 skipped）
```

**5 FAILURES** — 全部在 `tests/test_policy_schema.py`：

| 测试 | 原因 |
|------|------|
| `TestCanonicalTrace::test_trade_action_with_full_canonical_trace` | fixture 缺 `execution_timing` |
| `TestCanonicalTrace::test_trade_action_carrying_upstream_ids` | 构造缺 `execution_timing` |
| `TestCanonicalTrace::test_canonical_trace_status_auto_set` | 构造缺 `execution_timing` |
| `TestCanonicalTrace::test_trade_action_serialization_with_trace` | fixture 缺 `execution_timing` |
| `TestFullChainF3F4F5::test_full_chain_canonical` | 构造缺 `execution_timing` |

**根因**：Agent 4 修改 `validate_canonical_trace` 新增 `has_timing` 条件，但未更新 `test_policy_schema.py` 中的 `canonical_trade_action_for_trace` fixture 和内联构造。Agent 6 正确更新了 `test_schemas.py`（其 diff 可见添加了 `ExecutionTiming` 构造），但漏掉了同目录下的 `test_policy_schema.py`。

---

## 4. Architecture Compliance

| 规则 | 结果 |
|------|------|
| `topic_assembler.py` 在 `parsing/`（F1） | ✅ |
| `timing_policy.py` 在 `execution/` | ✅ |
| `canonical_action_builder.py` 在 `extraction/`（F5） | ✅ |
| 无跨 F-stage 直接调用 | ✅ |
| `canonical_action_builder.py` 不含 LLM 调用 | ✅ |
| `timing_policy.py` 不含 LLM 调用 | ✅ |
| `topic_assembler.py` 不含 LLM 调用 | ✅ |
| `schemas/__init__.py` 导出 TopicBlock 相关类型 | ✅ (`TopicType`, `TOPIC_TYPE_LITERAL`, `TopicBlock`, `TopicAssemblyResult`) |
| API route 中无业务逻辑（本次无新增 route） | ✅ N/A |

---

## 5. Schema Contract Compliance

| 检查项 | 结果 |
|--------|------|
| `TopicBlock` 使用 Pydantic V2 `ConfigDict(strict=True)` | ✅ |
| `TopicType` 使用 `Literal`（非 Enum） | ✅ |
| `ExecutionTiming` 使用 `ConfigDict(strict=True)` | ✅ |
| `MarketSession` 使用 `str, Enum` | ✅ (供 ExecutionTiming 内部使用，JSON 序列化为字符串) |
| `TradeAction.validate_canonical_trace` 要求 `execution_timing` | ✅ |
| `canonical_trace_status` 三态：canonical/partial/non_canonical | ✅ |
| 所有新增 Field 有 `description` | ✅ |

---

## 6. Issues Found

### ISSUE-1: test_policy_schema.py 5 个测试因 ExecutionTiming 变更失败 (P0)

**严重程度**：High — 全量测试不通过

**描述**：Agent 4 在 `trade_action.py` 的 `validate_canonical_trace` 中新增 `has_timing = self.execution_timing is not None` 条件，使得 "canonical" 状态现在需要 4 个条件同时满足：`intent_id + policy_id + evidence_span_ids + execution_timing`。但 `tests/test_policy_schema.py` 中 5 个测试构造 `TradeAction` 时未提供 `execution_timing`，导致 `canonical_trace_status` 被判定为 `"partial"` 而非预期的 `"canonical"`。

**影响范围**：
- `tests/test_policy_schema.py:141-160` — `canonical_trade_action_for_trace` fixture
- `tests/test_policy_schema.py:540-555` — `test_trade_action_carrying_upstream_ids`
- `tests/test_policy_schema.py:596-607` — `test_canonical_trace_status_auto_set`
- `tests/test_policy_schema.py:849-867` — `test_full_chain_canonical`

**修复方案**：在 `test_policy_schema.py` 的 `canonical_trade_action_for_trace` fixture 和相关测试中添加 `execution_timing` 构造（参考 `test_schemas.py` 中已有的修复模式）。

### ISSUE-2: 工作未提交 (P1)

**严重程度**：Medium — 所有 Agent 产出均为 uncommitted 状态

**描述**：`git status` 显示 6 个 modified 文件 + 12 个 untracked 文件，均为 Agent 1-6 的工作产出。尚未 commit。

---

## 7. Verdict

### PASS（修复后）

**初始审查结果**：FAIL — 全量测试 5 FAIL，`test_policy_schema.py` 中 5 个测试缺少 `execution_timing` 构造。

**修复内容**：在 `test_policy_schema.py` 中添加 `ExecutionTiming` 导入，并在以下 4 处补充 execution_timing 构造：
- `canonical_trade_action_for_trace` fixture
- `test_trade_action_carrying_upstream_ids`
- `test_canonical_trace_status_auto_set`
- `test_full_chain_canonical`

**修复后验证**：`pytest -q` → **951 passed, 21 skipped, 0 failed**

**Agent 1-6 产出全部验证通过**：
- 12/12 文件存在
- 178 个新增测试全部通过
- 架构合规（无跨 F-stage 违规）
- Schema 合约合规（Pydantic V2 + strict + Literal）
