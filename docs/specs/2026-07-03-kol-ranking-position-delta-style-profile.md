# KOL 收益排名动画 + 加减仓语义细粒度 + 交易风格双层画像

## 概述（Overview）

一次性落地三个需求：①观点雷达首页新增周/月 KOL 收益排名动画区块（fixture 标杆 + live 同构）；②修复 F4→F5 加仓/减仓语义坍缩（ActionType 增 ADD/REDUCE、仓位 delta 字段、止损/止盈策略可配置化）；③KOL profile 新增融资/杠杆/做空/左右侧四维交易风格画像（declared 人工标注层 + observed 行为统计层）。后端 3089 测试全过，前端 build 通过，demo 页浏览器实测通过。

## 变更清单（Changes）

### 需求 A：收益排名动画（纯前端）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/lib/fixtures/kol-radar.ts` | 修改 | 新增 `EarningsRow` + `deriveEarningsBoard(data, 7\|30)`；补 3 条结算时点落入周窗口的 viewpoints（TA-lz-05/TA-hk-05/TA-k-05），保留赛道阿尔法周窗口 0 样本 |
| `src/finer_dashboard/src/components/kol-radar/EarningsRace.tsx` | 新增 | framer-motion `layout`+`layoutId` 名次重排动画、周/月 Tab、名次徽章、收益条、lowSample 徽标、空态 |
| `src/finer_dashboard/src/components/kol-radar/KOLRadar.tsx` | 修改 | MarketSentiment 后插入「收益榜 · TOP EARNERS」区块 |
| `src/finer_dashboard/src/components/kol-radar/index.ts` | 修改 | 导出 EarningsRace |

### 需求 B：加减仓语义细粒度

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/schemas/trade_action.py` | 修改 | ActionType 增 `ADD`/`REDUCE`（side-agnostic）；ExitReason 增 `END_OF_PERIOD`；ActionStep 增 `position_delta_pct`（-1~1 有符号）+ 符号校验器 |
| `src/finer/schemas/policy.py` | 修改 | PolicyRiskConstraints / PolicyMappedIntent 各增 `stop_loss_pct_hint`/`take_profit_pct_hint`/`max_holding_days_hint` |
| `src/finer/policy/global_base.py` | 修改 | `compute_risk_constraints` 对 position-taking hint 填默认 `-0.10/+0.20/30`（与旧硬编码等值） |
| `src/finer/policy/policy_mapper.py` | 修改 | `_build_mapped_intent` 透传 3 个 hint |
| `src/finer/extraction/canonical_action_builder.py` | 修改 | `add_position→ADD`、`reduce_position→REDUCE`；新增 `_build_metadata`（exit 阈值 3 键 + F3 风格信号 3 键，非默认值才写入） |
| `src/finer/backtest/per_action.py` | 修改 | `ExitRules` frozen dataclass + `exit_rules_of(action)`（读 metadata，畸形值静默回落常量）；数据尽头 fallback UNKNOWN→END_OF_PERIOD |
| `src/finer/backtest/converter.py` | 修改 | legacy 组合引擎映射补 `ADD→long`/`REDUCE→close_long`（防新枚举被静默跳过的回归） |
| `src/finer/api/routes/opinions.py` | 修改 | `_ACTION_TYPE_MAP` 增 add/reduce；API ActionStep Literal 扩 7 值 + `positionDeltaPct` 透传 |
| `src/finer_dashboard/src/lib/contracts.ts` | 修改 | ActionType/ExitReason union 同步；ActionStep 增 `position_delta_pct` |
| `src/finer_dashboard/src/components/opinion-timeline/OpinionTimeline.tsx` | 修改 | ActionStep union 扩 7 值 + `positionDeltaPct` |
| `src/finer_dashboard/src/components/opinion-timeline/OpinionDetailModal.tsx` | 修改 | 加仓/减仓标签 + bearish 方向感知文案（加空仓/减空仓）+ 仓位变动展示 + 「增持现有仓位/部分减持·非清仓」副标 |
| `src/finer_dashboard/src/components/audit/trace-timeline.tsx` | 修改 | `Record<ActionType,string>` 补 add/reduce（编译护栏捕获） |

### 需求 C：交易风格双层画像

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/schemas/investment_intent.py` | 修改 | F3 增 `margin_flag`/`leverage_flag: Optional[bool]`、`entry_timing_style: left_side\|right_side\|unknown`（auxiliary） |
| `src/finer/prompts/f3_intent_extraction/system.j2` | 修改 | Output Schema 增 3 字段 + §8 Trading Style Signals 判定规则（未提及一律 null/unknown，不猜） |
| `src/finer/extraction/intent_extractor.py` | 修改 | LLM 输出路径解析+校验 3 字段（rule-based 路径靠 schema 默认值） |
| `src/finer/schemas/kol_profile.py` | 修改 | 新增 `DeclaredTradingStyle`（三态 bool + entry_style + evidence_notes）、`ObservedTradingStyle`（short_ratio/mention counts/多数决 entry style/low_sample）、`TradingStyleProfile` |
| `src/finer/services/trading_style.py` | 新增 | `load_declared_style`（YAML trading_style 块）、`compute_observed_style`（F5 action 统计）、`build_style_profile` |
| `src/finer/services/repository.py` | 修改 | 新增公开 `load_all_actions()`（绕过 SQLite 索引直扫文件） |
| `src/finer/api/routes/kol_style.py` | 新增 | `GET /api/kol/style/{creator_id}`，双 None 仍 200；错误走 FinerError envelope |
| `src/finer/api/server.py` | 修改 | 注册 kol_style router（同 `/api/kol` prefix） |
| `configs/creators/trader_ji.yaml` | 修改 | 增 `trading_style:` 示例标注块 |
| `src/finer_dashboard/src/lib/contracts.ts` | 修改 | 镜像 3 个类型（snake_case 与 Pydantic 一致） |
| `src/finer_dashboard/src/components/kol-snapshot/TradingStyleCard.tsx` | 新增 | 4 维度 ×「自述/实际行为/一致性」三列；✓一致(accent-teal)/⚠冲突(morningstar-red)/—数据不足；标注依据列表；空态 |
| `src/finer_dashboard/src/components/kol-snapshot/KOLSnapshot.tsx` | 修改 | 「本期研判」后插入交易风格画像 section |
| `src/finer_dashboard/src/lib/fixtures/kol-snapshot.ts` | 修改 | `KOLSnapshotData.tradingStyle?` + 老纪示例（自述右侧 vs 行为左侧的冲突态设计冻结） |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 修改 | `fetchTradingStyle()` 容错 fetch（照抄 fetchCredibilityOverrides 模式） |
| `src/finer_dashboard/src/app/radar/kol/[kolId]/page.tsx` | 修改 | Promise.all 并取 style profile，失败降级空态 |

### 测试

| 文件 | 类型 | 说明 |
|---|---|---|
| `tests/test_canonical_action_builder.py` | 修改 | 映射断言改 ADD/REDUCE；exit 阈值 metadata、风格信号 metadata 正反例 |
| `tests/test_backtest_per_action.py` | 修改 | END_OF_PERIOD；metadata 驱动阈值、畸形 metadata 回落、显式 rules 优先 |
| `tests/test_schemas.py` | 修改 | position_delta_pct 符号校验器正反例 |
| `tests/test_policy_mapper.py` | 修改 | 默认 exit hint 等值断言（零漂移钉住）+ 透传断言 |
| `tests/test_opinions_action_mapping.py` | 新增 | 全枚举显式映射钉住（防静默降级 watch）+ 13 组映射 + delta 透传 |
| `tests/test_trading_style.py` | 新增 | declared 加载/缺失/非法、short_ratio、多数决、low_sample、双 None profile、真实 trader_ji 配置解析 |

## 架构影响（Architecture Impact）

- **F3**：`NormalizedInvestmentIntent` 增 3 个 auxiliary 风格字段，不影响四轴判定；存量 JSON 兼容（全 optional 带默认）。F3 职责边界不变（不产 TradeAction）。
- **F4**：数值 exit hint 以 `*_hint` 后缀进入 `PolicyRiskConstraints`/`PolicyMappedIntent`，守住「F4 是 hint 不是执行事实」边界；GlobalBase v1 默认值与 F8 旧硬编码严格等值。
- **F5**：`_ACTION_HINT_MAP` 语义坍缩修复；风格信号与 exit 阈值经 `TradeAction.metadata` 下行（沿用 `action_hint_original` 先例，TradeAction schema 零结构变更）。
- **F8**：per-action 回测架构未动，仅阈值来源从模块常量升级为「metadata 优先、常量兜底」；`evaluate_action` 签名向后兼容（rules 参数可选），现有调用方 `api/routes/extraction.py` 零改动。
- **API 契约**：`/api/opinions/timeline` ActionStep 扩 7 值 + `positionDeltaPct`；新端点 `GET /api/kol/style/{creator_id}`。`contracts.ts` 已同步。
- **前端**：收益榜与风格卡均为「组件内派生/容错 fetch」模式，fixture（/demo/kol-radar、/demo/kol-snapshot）与 live（/radar、/radar/kol/[kolId]）同构，live 数据缺失时优雅降级。

## 关键决策（Key Decisions）

1. **ADD/REDUCE 为 side-agnostic 2 值**而非 ADD_LONG/.../REDUCE_SHORT 4 值：对齐 F3 `position_delta_hint` 与 F4 hint 的设计；side 由 `TradeAction.direction` 判定；`(explicit_action, bearish, add)` 本就被 GlobalBase escalate 到 review，短侧无自动生成路径，4 值方案是死枚举。
2. **周/月收益窗口按「结算时点」**（`timestamp + holdingDays`）而非信号时点：持有期最长 30 天，按信号时点算周榜恒空；语义 = 本窗口落袋的跟单盈亏。主指标为等权累计收益。
3. **回测零漂移**：GlobalBase 默认 exit hint 与旧常量等值，用 `test_position_taking_hints_get_default_exit_rules` 显式钉住；唯一预期行为变化是数据尽头 exit_reason UNKNOWN→END_OF_PERIOD。
4. **canonical builder 不为 `position_delta_pct` 编数字**：F4 只有定性 sizing hint，F5 不制造精度假象；字段为人工审核和未来数值化 sizing 层预留。
5. **左右侧判定 v1 只用 F3 语义信号多数决**（n≥5 且 ≥60%）：不做 TriggerType×价格走势推断——builder 恒写 `NEWS_EVENT`，该路无数据，诚实降级。
6. **declared 层用三态 bool**（None=未标注 ≠ False=明确不用），前端「未观测到」不判冲突——语料未覆盖 ≠ 言行不一；只有 declared=false 且行为出现时才标 ⚠。
7. **一致性判定不用行情涨跌色**：本设计系统红涨绿跌，若用 chart 色「冲突」会渲染成正面绿色；改用 accent-teal（一致）/morningstar-red（冲突）。
8. **legacy converter 补 ADD/REDUCE 映射**：否则新枚举在旧组合引擎被静默跳过，构成行为回归（变更前 add/reduce hint 是可回测的）。

## 验证结果（Verification）

```bash
pytest tests/ -q
# ================ 3089 passed, 15 skipped, 39 warnings in 58.72s ================

cd src/finer_dashboard && npm run build
# ✓ Compiled successfully in 4.0s · 21/21 static pages
```

浏览器实测（preview，console 无错误）：
- `/demo/kol-radar`：收益榜周榜 老纪 +6.10% > 老张 +5.80% > 老兵 +4.70% > 猎手K −2.80%；月榜 5 KOL 含赛道阿尔法 −8.50%；Tab 切换重排动画正常；赛道阿尔法周窗口 0 样本正确缺席（降级态冻结）。
- `/demo/kol-snapshot`：交易风格卡 4 行渲染 = 融资 ✓一致 / 杠杆 —数据不足 / 做空 ✓一致 / 入场风格 ⚠冲突（自述右侧 vs 行为左5/右2），三种一致性状态全部冻结。
- `/demo/kol/[kolId]`：风格卡空态文案正确（该 demo 路径无 tradingStyle 数据，冻结空态）。
- `python -c "create_app()"`：`/api/kol/style/{creator_id}` 注册成功。

## 未解决项（Open Issues）

1. **observed 层暂无真实信号数据**：存量 F5 action 的 metadata 无 margin/leverage/entry_timing 键（F3 新字段需重新提取才会产生）；live 风格卡当前只有 short_ratio 一列有真值，其余显示「未观测到」。待下一轮 F3 全量重提取。
2. **live 收益榜数据稀疏**：creator_id 归属缺口（58/162 unknown）与 F8 回测覆盖不全未在本次范围内，live 周榜大概率显示空态/单 KOL；地基修复见 `docs/specs/2026-07-01-dashboard-live-graduation-plan.md` Wave 1-2。
3. **fixture 既有 4 条 viewpoint 结算时点晚于 generatedAt**（如 TA-lz-04），按本口径正确地不入任何窗口——属既有 fixture 数据不一致，未动老数据。
4. **收益榜/风格卡内 KOL 名未做问责页 Link**：live/demo 路由前缀不同（`/radar/kol` vs `/demo/kol`）而组件同构，留待路由前缀 prop 化统一处理。
5. **止损/止盈按 KOL/风格分层调参**未实现（v1 全局默认值），归属未来 F4 StyleArchetype/KOLPersona 层。
