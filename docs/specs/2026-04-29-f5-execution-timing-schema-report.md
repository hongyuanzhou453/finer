# F5 ExecutionTiming Schema Implementation Report

> 日期: 2026-04-29 | Agent: F5 ExecutionTiming Schema Agent

## Overview

将 `ExecutionTiming` 模型添加到 `TradeAction` schema，为 F5 Execute 阶段提供结构化的交易时机信息。`canonical_trace_status` 的判定逻辑已更新：canonical 状态现在要求 `execution_timing` 存在。

## Changes

### Modified Files

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `src/finer/schemas/trade_action.py` | 修改 | 新增 `MarketSession` 枚举、`ExecutionTiming` 模型、`TradeAction.execution_timing` 字段；更新 `validate_canonical_trace` 验证器 |
| `tests/test_schemas.py` | 修改 | 新增 `TestMarketSession`、`TestExecutionTiming`、`TestTradeActionExecutionTiming` 测试类；更新 2 个现有测试以包含 `execution_timing` |
| `tests/test_canonical_f3_f4_f5_contract.py` | 修改 | 新增 `make_test_timing` helper；更新 `make_canonical_trade_action` 和 5 处 inline TradeAction 构造 |

### New File

| 文件 | 说明 |
|---|---|
| `docs/specs/2026-04-29-f5-execution-timing-schema-report.md` | 本报告 |

## Architecture Impact

### Schema Changes

**新增枚举 `MarketSession`**:
- `pre_market` / `regular` / `after_close` / `non_trading_day` / `unknown`

**新增模型 `ExecutionTiming`** (`strict=True`):

| 字段 | 类型 | Required | 说明 |
|---|---|---|---|
| `intent_published_at` | `datetime` | Yes | KOL 内容发布时间 |
| `intent_effective_at` | `Optional[datetime]` | No | KOL 文本指向的生效时间（相对时间未解析时为 None） |
| `action_decision_at` | `datetime` | Yes | 系统生成 TradeAction 的时间 |
| `action_executable_at` | `datetime` | Yes | 按交易日历计算的最早可执行时间 |
| `market` | `str` | Yes | 市场标识（HK/CN/US） |
| `timezone` | `str` | Yes | IANA 时区（Asia/Hong_Kong） |
| `market_session_at_publish` | `MarketSession` | No (default: UNKNOWN) | 发布时的市场状态 |
| `execution_delay_reason` | `Optional[str]` | No | 延迟执行原因 |
| `timing_policy_id` | `str` | Yes | 使用的时机策略 ID |

**TradeAction 新增字段**:
- `execution_timing: Optional[ExecutionTiming] = None`
- 保持 Optional 以兼容 legacy non_canonical TradeAction

### Canonical Trace Status 逻辑变更

**Before**:
```
canonical = intent_id + policy_id + evidence_span_ids >= 1
```

**After**:
```
canonical = intent_id + policy_id + evidence_span_ids >= 1 + execution_timing present
```

缺少 `execution_timing` 的 TradeAction 即使有完整的三字段追溯链，也会被降级为 `partial`。这符合 `f-stage-contracts.md` F5 章节的要求："只有 canonical 状态且包含 execution_timing 的 TradeAction 允许进入 F6 Review 和 F8 Backtest。"

### Data Flow Impact

```
F3 Intent → F4 PolicyMappingResult → F5 TradeAction
                                         ├─ intent_id (from F3)
                                         ├─ policy_id (from F4)
                                         ├─ evidence_span_ids (from F2)
                                         └─ execution_timing (NEW, from F5 timing computation)
                                              ├─ intent_published_at (from F1)
                                              ├─ action_executable_at (from market calendar + policy)
                                              └─ timing_policy_id (from timing policy)
```

## Key Decisions

1. **execution_timing 降级 canonical → partial**: 不直接报 ValidationError，而是将 `canonical_trace_status` 降级为 `partial`。这样既强制了规范要求，又不会破坏现有的 legacy TradeAction（它们是 `non_canonical`，不受影响）。

2. **MarketSession 用 str + Enum 而非 Literal**: 使用 `str, Enum` 保持与其他枚举（TradeDirection, ActionType 等）一致的风格。

3. **ExecutionTiming 使用 strict=True**: 与其他嵌套模型（SourceInfo, TargetInfo 等）保持一致，确保类型安全。

4. **intent_effective_at 保持 Optional**: 对应 F2 TemporalAnchor 中相对时间未解析的情况（`resolved_time=None`），与 `effective_trade_at` 字段语义对齐。

## Test Results

```
======================= 105 passed, 7 warnings in 0.17s ========================
```

### New Tests (16 tests)

| 测试类 | 测试数 | 覆盖内容 |
|---|---|---|
| `TestMarketSession` | 3 | 枚举值、字符串转换、无效值拒绝 |
| `TestExecutionTiming` | 8 | 创建、全字段、序列化、缺失必填字段、所有 session 值 |
| `TestTradeActionExecutionTiming` | 5 | 无 timing 降级、有 timing 升级、legacy 兼容、部分追溯、JSON round-trip |

### Existing Tests Updated (7 tests)

- `test_trade_action_canonical_with_full_ids` — 添加 execution_timing
- `test_trade_action_serialization_with_trace` — 添加 execution_timing
- `make_canonical_trade_action` helper — 默认包含 execution_timing
- 5 处 inline TradeAction 构造 — 添加 execution_timing

## Risks

1. **下游消费者**: 任何直接检查 `canonical_trace_status == "canonical"` 且不传 `execution_timing` 的代码将得到 `partial`。当前仅影响测试 fixtures（已修复），但如有其他 Agent 或模块构造 canonical TradeAction，需同步更新。

2. **前端 contracts.ts**: `ExecutionTiming` 和 `MarketSession` 的 TypeScript 类型定义需要同步（不在本次任务范围内）。

3. **timing_policy_id 约束**: 当前为自由字符串。未来 timing policy 实现后应改为枚举或受控列表。
