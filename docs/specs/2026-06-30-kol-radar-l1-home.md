# 观点雷达 — 操作台首页（顶层）标杆

## 概述

按"由终点向上回溯"确定的产品终点（**散户决策辅助 / KOL 观点的晨星**），自顶向下做出操作台**首页**标杆：一个跨 KOL 聚合的决策首页 `/demo/kol-radar`，回答"现在什么状况 / 信哪个 / 跟哪条"。复用上一轮的 kol-snapshot 组件库，用"冻结契约 → 并行造区块 → 对抗式 review"的多 Agent 流程产出并收口。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer_dashboard/src/lib/fixtures/kol-radar.ts` | 新增 | 数据脑：5 个 KOL（建模 finer_site demo 人设）含富化 viewpoints + 近期异动事件 + 4 个派生函数（市场情绪/可信度榜/可跟call/标的共识）+ 区块 VM 类型 + 信誉分（样本量校正） |
| `src/finer_dashboard/src/components/kol-radar/MarketSentiment.tsx` | 新增 | 英雄区：全 KOL 今日情绪（净多空 + 广度条 + 观点流向潮汐） |
| `.../kol-radar/ChangeFeed.tsx` | 新增 | 近期异动流（翻向/新call/止损/信誉/共识异动 + 相对时间） |
| `.../kol-radar/CredibilityBoard.tsx` | 新增 | 可信度榜（脊柱）：6 列机构表 + 信誉分 bar + 样本少标 + 横向滚动 |
| `.../kol-radar/ActionableCalls.tsx` | 新增 | 此刻可跟：可信度×信念×新鲜度排序的卡片 |
| `.../kol-radar/TickerConsensus.tsx` | 新增 | 标的共识/拥挤：多 KOL 多空对比 + 分歧/拥挤打脸预警 |
| `.../kol-radar/KOLRadar.tsx` + `index.ts` | 新增 | 编排器（调派生→喂区块）+ barrel |
| `src/finer_dashboard/src/app/demo/kol-radar/page.tsx` | 新增 | demo 路由 |
| `src/finer_dashboard/src/lib/fixtures/kol-snapshot.ts` | 修改 | 头注释去除 "1:1/no shape change" 过度声明，标注 live 端 5→3 方向坍缩 |

未改后端、schema、共享 `contracts.ts` 或既有页面。

## 架构影响

- **新增操作台层级模型（非 F-pipeline）**：首页（本页）→ KOL 问责页（已有 kol-snapshot 标杆）→ 标的横截面（待建）→ 单条证据审计（已有 /audit）。**刻意不使用 L1-L4 命名**——AGENTS.md 硬禁 L0-L8/V0-V6，故代码/文案统一用中文层级词。
- **数据源无关**：`KOLRadar` 吃 `KOLRadarData`，全部区块 VM 由派生函数计算。live 切换非 drop-in，缝隙在 `kol-radar.ts` 头注释列明（信誉分/五向/异动 diff/creator_id 归属四处后端尚不具备）。
- **复用 kol-snapshot 组件库**：SectionHeader / DirectionTag / ReturnChip / ConfidenceMeter / DirectionLegend / StanceTide 全部复用，未重造。

## 关键决策

1. **终点先定，再自顶向下**。用户要求由终点回溯：确认产品终点=散户决策辅助后，识别出真正缺的是**跨 KOL 的市场级首页**（参考"资金潮汐"本就是市场级聚合，而非单实体），而非继续做单 KOL 页。
2. **多 Agent 流程**：先在主循环写**冻结契约**（fixture + 全部派生 + VM 类型 + tsc 通过），再用 workflow **并行造 5 个区块**（每个单文件、吃 typed prop、读组件库），最后跑 **5 视角对抗式 review** 收口。冻结契约让 5 个并行 agent 产出一次性 tsc/eslint 全过、视觉一致。
3. **信誉分做样本量校正**：原始命中率会让 4/4 小样本拿到 96 分排第一（误导散户）。改为向 0.5 先验收缩（k=4 伪观测）：`adjRate=(wins+2)/(settled+4)`，并对 settled<5 打"样本少"标。价值老张 96→81+样本少。
4. **return_pct = 方向校正后的跟单 P&L**（非标的涨跌幅），故命中判定 `returnPct>0` 对多空均成立；已在注释显式锁定语义，避免误读。
5. **拥挤打脸信号**：crowded 且 avgReturn<0 的标的（寒武纪/东财）单独标"拥挤打脸"——散户"怕被割"最想先看的翻车锚点。

## 验证结果

- `npx tsc --noEmit`：kol-radar / kol-snapshot 全部新增+修改文件无类型错误（TSC_CLEAN）。
- `npx eslint`：exit 0。
- 浏览器预览（desktop + mobile 375）：5 区块均正常渲染；可信度榜在窄屏横向滚动、页面无横向溢出；无 console error。
- 数据故事成立：比亚迪三方分歧（老纪空/赛道多/K风险）、东财共识看多却 −6.1% 拥挤打脸、中芯共识看多 +15.6% 兑现、寒武纪分歧+拥挤打脸。
- **对抗式 review（5 视角，Opus 4.8，~520k tok）已应用收口**：信誉分样本校正+样本少标、近期异动+相对时间、死链占位文案化、分歧配色统一(teal)、拥挤打脸、ageDays 新鲜度、空态、`th scope`、潮汐口径澄清、L1-L4 命名清除、契约诚实注释。

## 未解决项

1. **绿色对比度**（a11y must-fix，已转独立任务）：`--chart-down #10b981` 对白底仅 2.48:1，未达 WCAG AA。属全站既有 token（kol-snapshot 同），需新增 `--chart-down-text` 深绿并改文本用例，跨页影响，单列任务处理。
2. **live 接入未做**：信誉分需 KOLScorer 聚合、五向需 opinions 路由放开方向粒度、异动需后端快照-diff、按 KOL 聚合需 creator_id 归属补齐。这些是后端数据工作，前端已留缝。
3. **下钻未接线**：KOL 行/数字/证据链均为占位（已文案化为"即将开放"），待 KOL 问责页 live 路由与 /audit 接线。
4. **chip 原子未抽取**：信誉徽标等仍有 30/32% 边框等微差（已对齐主要几处），可后续抽 `<Chip>` variant 统一。
5. **标的横截面（L3 等价页）未建**：从 TickerConsensus 下钻的"某标的众 KOL 观点"页是下一块。
