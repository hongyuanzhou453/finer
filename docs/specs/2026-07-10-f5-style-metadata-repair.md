# F5 风格/exit metadata 修复：runner 语义坍缩根因 + 原位数据修复

## 概述（Overview）

排查「07-05 共识 regen 产出的 42 条 F5 action 缺失风格信号与 exit hint、且无 ADD/REDUCE」的根因：`pipeline/canonical_runner.py` 手写构造 TradeAction，绕过了 `CanonicalActionBuilder` 的映射表与 metadata 契约。修复 runner（复用共享 metadata 构造 + 映射表钉子测试）、修正一处减仓方向文案语义 bug，并用原位修复脚本从 F3/F4 sidecar 真值补齐现有 42 条 action——**KOL 交易风格画像 observed 层自此接通真实数据**（老纪：自述右侧 vs 观测左侧 6/1 → ⚠冲突）。

## 变更清单（Changes）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/extraction/canonical_action_builder.py` | 修改 | metadata 构造抽为公开函数 `build_action_metadata(intent, mapped)`，builder 内部委托 |
| `src/finer/pipeline/canonical_runner.py` | 修改 | ①`ACTION_HINT_TO_ACTION_TYPE`：`add_position→ADD`、`reduce_position→REDUCE`（原为 LONG/CLOSE_LONG，与 builder 漂移）；②programmatic 与 LLM 两条 TradeAction 构造路径的 metadata 改为 `{**build_action_metadata(...), "tier": ...}`（LLM 路径原先完全没有 metadata） |
| `src/finer_dashboard/src/components/opinion-timeline/OpinionDetailModal.tsx` | 修改 | 修正方向感知文案：direction 是跟单符号非持仓侧——`(reduce, bearish)`=减多仓应显示「减仓」（原误显「减空仓」）；`(reduce, bullish)`=减空仓；ADD 侧维持 bearish→加空仓 |
| `scripts/repair_f5_style_exit_metadata.py` | 新增 | 原位修复：备份→按 intent_id/policy_id 从 F3/F4 sidecar 补 metadata（风格 3 键 + exit 3 键 + sizing/holding hint）→ `add_position/reduce_position` 的 action_type 升级 add/reduce → `TradeAction.from_dict` 回环校验后落盘 |
| `tests/test_canonical_runner_mapping.py` | 新增 | runner 表与 builder `_ACTION_HINT_MAP` 一致性钉子 + add/reduce 显式断言 + `build_action_metadata` 全键覆盖 |
| `data/F5_executed/*_actions.json` | 数据修复 | 42 条 action：7 条补入场风格信号（左6/右1）、8 条补 exit hint、6 条升级 add×2/reduce×4；id/direction/timing/backtest_result 未动 |

备份：`data/repair-backup-20260710-215042/F5_executed/`。

## 架构影响（Architecture Impact）

- **F5 构造契约收口**：任何构造 canonical TradeAction 的路径（builder / runner programmatic / runner LLM）现共享同一 metadata 函数，钉子测试防再漂移。这是 07-03 变更被 07-05 regen 静默丢弃的直接教训：**同一映射存两份就会漂**。
- **F4 sidecar 无需修复**：核查确认 `risk_constraints.stop_loss_pct_hint=-0.10/+0.20/30` 在 regen 时已正确写入（早前误判为缺失是探测方法错误——在 PolicyMappingResult 顶层找了 PolicyMappedIntent 的扁平字段）。
- **数据修复保持审计完整性**：trade_action_id/回测结果/F7 快照/audit trace 全部无感；exit hint 值与 F8 常量等值，回测零漂移。
- **observed 风格画像 live**：`GET /api/kol/style/trader_ji` 现返回真值 observed 层；`/api/opinions/timeline` actionChain 出现 `add`/`reduce`。

## 关键决策（Key Decisions）

1. **原位修复而非重跑 regen**：F3 sidecar 里信号是全的，丢失只发生在 runner 构造一步；从 sidecar 真值 patch 现有 action 保住全部 id 链与回测结果，且零 LLM 成本。完整 regen 序列留给下次真正需要重提取时。
2. **runner 保留自己的表**（含 opinion-tier WATCH 扩展），但用测试与 builder 表强制一致，而非强行合并两表——两者词表不同（runner 多 watch 三兄弟）。
3. **减仓文案按跟单符号解读**：canonical runner 对 `reduce_position` 恒给 BEARISH（减多仓=卖出信号），故 `(reduce, bearish)`→「减仓」、`(reduce, bullish)`→「减空仓」；原实现会把所有真实减仓 action 错标成「减空仓」。
4. 修复脚本只升级 `long→add`/`close_long→reduce` 且仅当 `action_hint_original` 匹配——其他路径产出的 action 一律不动。

## 验证结果（Verification）

```bash
pytest tests/ -q            # 3123 passed, 15 skipped
cd src/finer_dashboard && npm run build   # exit 0
python scripts/repair_f5_style_exit_metadata.py
# {"actions": 42, "style_filled": 7, "exit_filled": 8,
#  "action_type_upgraded": 6, "missing_intent": 0, "missing_policy": 0}
```

live 端到端（uvicorn :8000 + preview :3000，console 无错误）：
- `GET /api/kol/style/trader_ji` → observed: sample=37, directional=7, short_ratio=0.0, 左6/右1, `entry_style_observed=left_side`, low_sample=false。
- `/radar/kol/trader_ji` 风格卡（真实数据）：融资/杠杆 —数据不足；做空 ✓一致（不做空 vs 0%·n=7）；入场风格 ⚠冲突（自述右侧 vs 观测左侧 左6/右1）。
- `GET /api/opinions/timeline` actionChain 分布：watch 35 / reduce 4 / add 2 / close_long 1。
- `/audit` 列表出现 `reduce_position` 真实 action。

## 未解决项（Open Issues）

1. 融资/杠杆维度观测仍为 0——语料中确无相关表述（LLM 判定 null 符合「不猜」规则），非缺陷；待覆盖含两融/杠杆表述的语料后自然出真值。
2. `OpinionTimeline`/`OpinionDetailModal` 组件尚无页面消费（预置组件），加/减仓文案已过类型与构建验证，视觉验收待该组件上页。
3. 8000 端口旧 uvicorn 实例已被替换为新代码实例（旧实例无 `/api/kol/style` 路由）。
