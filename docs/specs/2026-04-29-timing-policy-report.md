# F5 Timing Policy — MarketCalendarTimingPolicy 实现报告

> 日期: 2026-04-29
> Agent: Timing Policy Agent (Agent 5)
> F-stage: F5 Execute — 三层择时系统第 1 层

---

## 1. 概述

实现 F5 三层择时系统的第 1 层：确定性交易日历规则（Market Calendar Rules）。该模块根据 KOL 内容发布时间和市场交易时段，确定性地计算 `action_executable_at`——TradeAction 最早可执行时间。零 LLM 参与，完全可复现。

## 2. 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/execution/__init__.py` | 新增 | 模块入口，导出核心类型 |
| `src/finer/execution/timing_policy.py` | 新增 | MarketCalendarTimingPolicy 主实现（~350 行） |
| `tests/test_execution_timing_policy.py` | 新增 | 42 个测试，覆盖所有要求场景 |
| `docs/specs/2026-04-29-timing-policy-report.md` | 新增 | 本报告 |

## 3. 算法

### 3.1 Session 分类

对给定的 `published_at` + `market` + `timezone`，按以下顺序分类：

```
1. 转换到市场本地时区（zoneinfo 自动处理 DST）
2. 判断是否为交易日：
   - 周末（Sat/Sun）→ non_trading_day
   - 假日（通过 HolidayProvider）→ non_trading_day
3. 交易日内按时段分类：
   - t < pre_market_start          → pre_market
   - t < first_session_open        → pre_market
   - first_open <= t <= last_close  → regular（含午间休市）
   - t > last_close                 → after_close
```

### 3.2 Executable Time 计算

| Session | action_executable_at |
|---|---|
| `regular` | published_at + min_reaction_delay（默认 5 分钟） |
| `pre_market` | 当日第一个 session 的 open 时间 |
| `after_close` | 下一个交易日的 open 时间 |
| `non_trading_day` | 下一个交易日的 open 时间 |
| `unknown` | published_at + min_reaction_delay |

### 3.3 午间休市处理

HK（09:30-12:00, 13:00-16:00）和 CN（09:30-11:30, 13:00-15:00）有午间休市。在 AM 收盘和 PM 开盘之间的时段，分类为 `regular`——因为订单可以排队等待 PM session 执行。这符合"交易日内可执行"的语义。

## 4. 市场规则

| 市场 | 时区 | 交易时段 | 盘前开始 |
|---|---|---|---|
| HK | Asia/Hong_Kong (UTC+8) | 09:30-12:00, 13:00-16:00 | 09:00 |
| CN | Asia/Shanghai (UTC+8) | 09:30-11:30, 13:00-15:00 | 09:15 |
| US | America/New_York (UTC-5/-4) | 09:30-16:00 | 04:00 |

- 周末：Sat/Sun（所有市场统一）
- 假日：通过 `HolidayProvider` 协议扩展，默认无假日
- DST：通过 `zoneinfo.ZoneInfo` 自动处理（US EST↔EDT）

## 5. 测试结果

```
42 passed, 0 failed (0.06s)
```

### 测试覆盖

| 场景 | 测试数 | 状态 |
|---|---|---|
| 周五 HK 盘后 → 周一开盘 | 3 | ✅ |
| 周六/周日 → 周一开盘 | 3 | ✅ |
| 盘中交易 → 5 分钟延迟 | 7 | ✅ |
| 盘前 → 当日开盘 | 5 | ✅ |
| US/HK/CN 时区正确性 | 6 | ✅ |
| 午间休市处理 | 2 | ✅ |
| 假日扩展点 | 3 | ✅ |
| is_trading_day 辅助方法 | 4 | ✅ |
| 未知市场降级 | 1 | ✅ |
| 序列化 | 2 | ✅ |
| 自定义市场注册 | 1 | ✅ |
| 月末/年末边界 | 3 | ✅ |
| Agent hint 预留接口 | 2 | ✅ |

### 关键测试用例

1. **周五 HK 盘后看多腾讯**: `_hk(2026, 4, 24, 17, 0)` → `2026-04-27 09:30 HKT`（下周一开盘）
2. **周六发布**: `_hk(2026, 4, 25, 10, 0)` → `2026-04-27 09:30 HKT`
3. **盘中发布**: `_hk(2026, 4, 23, 10, 30)` → `2026-04-23 10:35 HKT`（+5min）
4. **盘前发布**: `_hk(2026, 4, 23, 8, 0)` → `2026-04-23 09:30 HKT`（当日开盘）
5. **UTC 输入跨时区**: `2026-04-23 10:00 UTC` → HK after_close，US regular

## 6. 架构影响

### 6.1 与 ExecutionTiming 的关系

当前 `schemas/trade_action.py` 中的 `ExecutionTiming` 模型尚未实现（ARCHITECTURE.md 标记为 `contract-only`）。本模块使用本地 `ExecutionTimingResult` 数据类作为输出，字段与 `ExecutionTiming` 契约 1:1 对应：

| ExecutionTimingResult (local) | ExecutionTiming (contract) |
|---|---|
| `action_executable_at` | `action_executable_at` |
| `market_session_at_publish` | `market_session_at_publish` |
| `execution_delay_reason` | `execution_delay_reason` |
| `timing_policy_id` | `timing_policy_id` |
| `intent_published_at` | `intent_published_at` |
| `market` | `market` |
| `timezone` | `timezone` |

当 Agent 4 实现 `ExecutionTiming` Pydantic 模型后，`compute_timing()` 返回值可直接映射。

### 6.2 F5 三层定位

本模块是第 1 层（Market Calendar Rules）的完整实现：

- **第 1 层（本模块）**: 确定性交易日历 → `action_executable_at`
- **第 2 层（F4 Policy Timing Rules）**: timing hints 如 `follow_next_open`，由 F4 policy 输出
- **第 3 层（Timing Agent / Quant Bot）**: 通过 `compute_timing_with_agent_hint()` 预留接口

第 3 层接口已定义但不执行任何 agent 逻辑——agent_hint 仅记录在 `execution_delay_reason` 中，不改变计算结果。

### 6.3 禁止事项遵守

- ✅ 无 LLM 调用
- ✅ 无跨 F-stage 调用
- ✅ 未修改 `trade_action.py`、`parsing/`、`extraction/`、`policy/`、`backtest/`

## 7. 关键决策

### 7.1 午间休市归类为 regular

HK/CN 的午间休市（AM 收盘后、PM 开盘前）归类为 `regular` 而非 `after_close`。理由：在此时段提交的订单可以在 PM session 执行，属于"同交易日可执行"语义。

### 7.2 本地数据类 vs Pydantic 模型

使用 `@dataclass` 而非 Pydantic BaseModel，因为：
- `ExecutionTiming` 在 `trade_action.py` 中尚未实现，不应引入对未完成 schema 的依赖
- dataclass 更轻量，`to_dict()` 手动处理 datetime 序列化
- Agent 4 完成 `ExecutionTiming` 后可无缝迁移

### 7.3 HolidayProvider 协议

使用 `Protocol` 而非 ABC，因为：
- 符合鸭子类型风格
- `NoOpHolidayProvider` 是简单的 dataclass，不需要继承
- 用户可传入任何实现了 `is_holiday(date, market) -> bool` 的对象

## 8. 局限性

| 局限 | 影响 | 缓解方案 |
|---|---|---|
| 无内置假日日历 | 无法自动跳过公众假日 | 通过 HolidayProvider 接口接入外部假日数据源 |
| 无盘前/盘后交易时段 | US 盘前交易（04:00-09:30）不单独处理 | 可扩展 MarketConfig 增加 extended_hours_sessions |
| 无跨日特殊时段 | 如 US 盘后交易（16:00-20:00） | 同上 |
| 简化的 HK 假期处理 | 不处理半日市（如除夕下午休市） | 需要更精细的 HolidayProvider |
| 时区硬编码在配置中 | 无法处理同一市场多时区（如 US 跨时区交易所） | 当前设计已足够，US 统一使用 ET |

## 9. 验证命令

```bash
# 测试
pytest tests/test_execution_timing_policy.py -q
# Result: 42 passed in 0.06s

# 编译检查
python -m compileall src/finer/execution
# Result: 2 files compiled successfully
```
