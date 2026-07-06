# KOL 观点潮汐快照 — 前端标杆页

## 概述

为 Finer dashboard 新增一个「KOL 个人时间线快照」标杆页（`/demo/kol-snapshot`），把"期货资金潮汐 / 每日 CTA 全景"那套晨星编辑部式金融日报版式落到 Finer 的 F7 数据上，用于验证该视觉语言在 KOL→观点 数据形态下是否成立。结果：成立，且 F7 既有 schema 足以支撑该版式。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer_dashboard/src/lib/fixtures/kol-snapshot.ts` | 新增 | view-model 类型（映射 F7 契约）+ 老纪/trader_ji 的 13 条 schema-faithful 示例 + `deriveSummary`/`netStance`/`deriveHighlights` 派生函数 |
| `src/finer_dashboard/src/components/kol-snapshot/primitives.tsx` | 新增 | 共享原子件：`SectionHeader`(编号分栏)、`DirectionTag`、`ReturnChip`、`ConfidenceMeter`、`DirectionLegend`、方向色映射、格式化器 |
| `src/finer_dashboard/src/components/kol-snapshot/TickerRotation.tsx` | 新增 | 标的兑现榜（per-ticker 立场+平均兑现排名表 + 居中分歧条），01 区块用 |
| `src/finer_dashboard/src/components/kol-snapshot/useEchart.ts` | 新增 | 极简 ECharts 绑定 hook（init/resize/dispose） |
| `src/finer_dashboard/src/components/kol-snapshot/ViewpointQuadrant.tsx` | 新增 | 观点象限 ECharts 散点（置信度×实际收益，按方向着色） |
| `src/finer_dashboard/src/components/kol-snapshot/StanceTide.tsx` | 新增 | 立场潮汐 ECharts 面积线（逐月累计净多空） |
| `src/finer_dashboard/src/components/kol-snapshot/ViewpointTimeline.tsx` | 新增 | 观点时间线竖向卡片（下钻） |
| `src/finer_dashboard/src/components/kol-snapshot/KOLSnapshot.tsx` | 新增 | 主编排：masthead + 立场英雄区 + 本期研判 + 01 立场总览 + 02 观点象限 + 03 时间线 + 时间范围筛选 |
| `src/finer_dashboard/src/components/kol-snapshot/index.ts` | 新增 | barrel 导出 |
| `src/finer_dashboard/src/app/demo/kol-snapshot/page.tsx` | 新增 | demo 路由，喂 fixture |

未改动任何后端、schema、共享 `contracts.ts` 或既有页面。

## 架构影响

- **不触碰 F-stage 边界与 schema**。本页是纯展示层，view-model 字段一一对应 F7 契约（`timeline/models.py::KOLTimeline / TimelineSummary` 与 `schemas/trade_action.py::TradeAction`），但**未**修改 Pydantic 模型或 `contracts.ts`，因此不构成契约变更。
- **数据源无关设计**：`<KOLSnapshot data={KOLSnapshotData} />` 吃一个 view-model。当前 demo 路由喂 fixture；F7 数据养肥后，真实路由（建议 `/kol/[id]/snapshot`）改喂 `GET /api/opinions/timeline?kols=<id>` + `/stats/summary` 的适配结果即可，组件零改动。
- **方向色沿用中国惯例**：看多=红(`--chart-up`)、看空=绿(`--chart-down`)，与 `globals.css` 既有 token 和参考页一致；置信度/质量用金色(`--accent-gold`)、风险用青(`--accent-teal`)作为独立通道。
- **复用既有设计系统**：`.editorial-card`、`.segmented-control`、`--surface-strong` 等均直接复用，未新增全局样式。

## 关键决策

1. **fixture 而非 live API**。真实 F7 有 58 条 TradeAction，但 `creator_id` 多为 `"unknown"`、`backtest_result`/`enrichment`/`rlhf` 多为 null——直接绑 live 会得到"匿名 KOL、无收益、无研判"的空页，无法验证视觉语言。故绑一份贴合 schema 的代表性 fixture（建模于真实画像 老纪/trader_ji），保留 live 切换缝。
2. **「观点象限」作为签名图**。x=置信度、y=实际回测收益、色=方向，直接可视化 KOL 校准度（高调看好的事后真涨了吗），最贴 Finer「可回测可审计」卖点。
3. **ECharts 颜色必须用具体 hex**。canvas 渲染器不解析 `var(--…)` 与 `color-mix()`；散点着色改为内联 hex 映射（首版误用 CSS 变量导致点全灰，已修）。
4. **页面落点 `/demo/kol-snapshot`**。沿用既有 `/demo/*` 约定，明确标注为设计标杆，不冒充已接 live 的生产路由。

### 打磨 round（标杆定型）

锁定模板（选项1），改了三个真问题，非泛化美化：
- Hero caption 原为期货页抄来的"资金方向 ≠ 价格方向"（KOL 页无"资金"概念）→ 改为"立场为模型隐含 · 收益来自完全跟单回测 · 非投资建议"。
- 「01」原为重复 Hero 的多空广度条 → 重做为**标的兑现榜**（per-ticker 立场 + 平均兑现排名 + 居中分歧条），对应参考页的板块轮动/净流入榜，去冗余加信息。
- 「02 观点象限」原"如何读"为灰字段落且无颜色图例 → 改为 2×2 象限释义 key + 五向色图例（红看多/绿看空/灰中性/金观察/青风险），补上缺失的色彩 key。

## 验证结果

- `npx tsc --noEmit`：新增文件无类型错误（`NO_ERRORS_IN_NEW_FILES`）。
- `npx eslint <新增文件>`：`LINT_CLEAN_EXIT_0`。
- 浏览器预览（preview，desktop 1280+）：三屏截图确认 masthead / 英雄立场区（▲ 偏多 净多+7）/ 立场潮汐线 / 本期研判+4 卡 / 观点象限散点（着色正确）/ 时间线卡片 均正常渲染；`preview_console_logs(error)` 无错误。
- 派生数值正确：总观点 13、净多 +7、平均置信度 72%、验证率 92%、命中率 73%、最佳兑现 中芯 +15.6%、最大教训 寒武纪 −11.8%。
- 交互：时间范围筛选（近1月/近3月/全部）实测可用，近1月正确收敛为 4 条 / 净多 +0 / 分歧，summary 与图表同步重算。

## 未解决项

1. **F7 数据成熟度**：上线 `/kol/[id]/snapshot` 前需补齐 KOL 身份归属（`creator_id` 解析）与回测回填，否则真实页会显著比标杆页空。这是该标杆暴露出的真实数据缺口。
2. **本期研判叙事生成**：fixture 中 narrative 为手写；生产需 F7/LLM 依据 timeline 自动综合（当前后端无此产出）。
3. **未接 live API**：`/kol/[id]/snapshot` 真实路由与 `opinions` API → view-model 的适配层尚未编写。
4. **响应式**：已核对桌面（1280+）与移动（375）。hero / 研判 / 象限三处栅格在 `lg` 断点堆叠为单列，标的兑现榜表格在 375 无横向溢出（tableW 335）。更多机型与超宽屏未逐一核对。
5. **契约同步**：若决定将此 view-model 固化进 `contracts.ts`，需新增 `KOLSnapshotData` 等类型并与后端对齐（当前刻意未动，避免无 live 数据时污染契约）。
