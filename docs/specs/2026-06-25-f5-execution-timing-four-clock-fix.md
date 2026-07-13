# F5 ExecutionTiming — 四时钟倒挂修复

> 2026-06-25 · F5 / ExecutionTiming · branch `fix/f5-execution-timing-clocks`

## 概述 (Overview)

canonical F5 的 59/59 个 TradeAction 都出现 `intent_effective_at` 早于 `intent_published_at`
（观点"生效"早于"发布"）——这是 look-ahead，会污染 F8 回测入场时点。根因：timing builder
把 F2 的 `mentioned_at` 锚点（文中*提及*的历史日期）当成了"生效时间"。本次移除该错误回退，
并为 `ExecutionTiming` 增加四时钟单调性校验器兜底。修复后 14/14 真实 F2 envelope 构造 timing
零倒挂。

## 变更清单 (Changes)

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/extraction/timing_builder.py` | 修改 | `_resolve_intent_effective_at` 移除 `mentioned_at` 回退；只有显式 `effective_trade_at` 锚点才填充 `intent_effective_at`，否则 None |
| `src/finer/schemas/trade_action.py` | 修改 | `ExecutionTiming` 新增 `validate_clock_monotonicity` model_validator：`effective>=published`、`decision>=published`、`executable>=decision` |
| `tests/test_timing_builder.py` | 修改 | `test_mentioned_at_fallback`→`test_mentioned_at_is_not_used_as_effective`（断言 None）；`test_effective_trade_at_preferred`→`test_effective_trade_at_used`（fixture effective 改为 >= published）；新增 `test_past_mentioned_at_does_not_invert_clocks` 复刻真实数据回归 |
| `tests/test_schemas.py` | 修改 | `test_execution_timing_with_all_fields` fixture 改为时间前向一致（原先 now() 发布 + 2026-04 生效/可执行，违反单调性） |
| `docs/specs/2026-06-25-f5-execution-timing-four-clock-fix.md` | 新增 | 本文档 |

## 架构影响 (Architecture Impact)

- **F5 schema 收紧**：`ExecutionTiming` 现在拒绝时钟倒挂的数据。这是 AGENTS.md 规则 #6
  （四时钟必须显式区分）的强化，也与 schema docstring 自述目标"prevents look-ahead bias /
  future-function"一致。
- **下游 F8 回测**：`intent_effective_at` 不再是错误的历史日期，回测不会以"信号尚未发布"
  的时点入场。当前 14 个 envelope 无 `effective_trade_at` 锚点 → effective 统一为 None
  （未解析），由回测/timing policy 用 `action_executable_at`（市场日历推算，>= published）
  作为可执行时点。
- **审计台副作用（重要）**：新校验器会拒绝**现存** `data/F5_executed` 的 59 个 action
  （它们仍是旧的倒挂数据）。assembler 的 `_safe_load_model_from_obj` 捕获 ValidationError →
  返回 None → 这 59 个在审计台**消失**，直到用修复后的 route 重新生成。这是"fail loudly"
  的预期行为：旧数据确实非法。

## 关键决策 (Key Decisions)

1. **只移除 `mentioned_at` 回退，不动 `effective_trade_at` 语义。** 数据实测：14 个 F2 文件
   共 487 个 `mentioned_at`、14 个 `published_at`、**0 个 `effective_trade_at`**。所以 100%
   的倒挂都来自 mentioned_at 回退，移除它即完全修复。`effective_trade_at`（显式"生效交易时间"）
   保持可信，不施加额外约束——避免对"effective 能否早于 published"这一存在争议的语义过度收紧。
2. **无 effective_trade_at 时 effective = None，而非默认 published。** None 是 schema 既有的
   "未解析"状态（`Optional`），诚实表达"不知道生效时点"，比猜一个值更安全；既有
   `test_no_anchors` 已是此预期。
3. **校验器三条都是无争议单调性。** `effective>=published`（不能在发布前生效）、
   `decision>=published`、`executable>=decision`。真实数据 decision==published、
   executable>=decision 恒成立，effective 修复后为 None → 三条全过。
4. **校验器拒绝旧数据是特性不是 bug。** 让这类倒挂以后在写盘/读盘时直接报错，而不是静默
   产出错误回测。

## 验证结果 (Verification)

执行环境：worktree `/Users/zhouhongyuan/Desktop/finer-timing-fix`
（`fix/f5-execution-timing-clocks`，基于 `docs/f0-review-fixes` HEAD `1c9e16e9`）。

**1. 真实 14 个 F2 envelope 重建 timing（修复后代码）**
```
built timing for 14/14 real envelopes (validator passed on all)
  intent_effective_at None: 14 | set: 0 | INVERTED: 0
BEFORE: 59/59 inverted   AFTER: 0 inverted  -> FIXED
```

**2. 现存 on-disk 数据在新校验器下**
```
valid: 0 | rejected: 59 / 59   （确认旧倒挂数据被正确拒绝）
```

**3. 全量套件 `pytest tests/ -q`**
```
3 failed, 2788 passed, 70 skipped
```
3 个失败为 `test_mimo_vision_config` / `test_live_mimo_multimodal` 预存 flake（env/顺序相关，
与本改动无关，多次确认）。本次新增 3 个 timing 回归测试全过，无新增失败。

## 未解决项 (Open Issues)

- **需重生成 `data/F5_executed`（批量重建，需用户确认）**：用修复后的 route 重跑 14 个 F2 →
  覆盖 59 个 action，使其携带前向一致的四时钟、并重新通过校验器在审计台显示。**在重生成之前，
  审计台会因校验器拒绝旧数据而为空。**
- **F2 缺 `effective_trade_at` 锚点**：14 个 envelope 全无 effective 锚点，故 effective 恒 None。
  若要让 effective 携带真实前向生效时点（如"下周一建仓"），需 F2 时间锚定产出
  `effective_trade_at`（>= published）。属 F2 上游增强，单独排期。
- **分支整合 + push**：本修复在 `fix/f5-execution-timing-clocks`，待合并回 `docs/f0-review-fixes`。
