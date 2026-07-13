# 标的横截面 — 操作台第三层（某标的众 KOL 视角）

## 概述

把"晨星式"四层下钻补到第三层：从观点雷达「标的共识」卡下钻到**标的横截面** `/demo/ticker/[ticker]`，回答"某标的众 KOL 怎么看、谁对了"。雷达卡已接 Link，四层漏斗（首页雷达 → 标的横截面 → 单条审计）真正打通。同样走"冻结契约 → 并行造区块 → 聚焦 review"流程。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer_dashboard/src/lib/fixtures/kol-ticker.ts` | 新增 | 数据脑：`deriveTickerCrossSection`（共识裁决 + 谁对了榜 + 跨KOL时间线 + per-ticker 研判）+ `listTickers` + VM 类型 |
| `.../components/kol-ticker/TickerVerdict.tsx` | 新增 | 英雄区：众 KOL 裁决（共识/分歧 + 分方向兑现 + 命中 + 研判） |
| `.../components/kol-ticker/WhoWasRight.tsx` | 新增 | 签名榜：谁对了（按本票兑现排名 + KOL 整体战绩） |
| `.../components/kol-ticker/TickerStanceTimeline.tsx` | 新增 | 跨 KOL 立场时间线（演变 + 分歧） |
| `.../components/kol-ticker/KOLTickerCrossSection.tsx` + `index.ts` | 新增 | 编排器 + barrel |
| `.../app/demo/ticker/[ticker]/page.tsx` | 新增 | 动态路由（Next16 async params + 未找到降级） |
| `.../components/kol-radar/TickerConsensus.tsx` | 修改 | 每张共识卡包 `<Link>` 下钻 `/demo/ticker/{ticker}` |

## 架构影响

- **四层下钻打通到第三层**：雷达首页（L 等价词）→ KOL 问责页 → **标的横截面** → 证据审计。雷达 8 张共识卡现为真实链接。命名仍避开 L0-L8（AGENTS.md 硬禁），用中文层级词。
- **复用**：完全复用 kol-snapshot 组件库（DirectionTag/ReturnChip/ConfidenceMeter/SectionHeader）+ kol-radar 的 `deriveCredibilityBoard`（取信誉分/命中率/样本量）。数据同源 `KOL_RADAR_FIXTURE`，无新 fixture。
- **未改后端/schema/contracts**。

## 关键决策

1. **"谁对了"按本票跟单 P&L 排名**，但同时挂 KOL **整体战绩**（总命中率 + 样本量 + 样本少标），区分"对了这一次"与"值得长期信"——回应散户真正的疑问"该不该信他下一次"。
2. **分歧票按方向拆兑现**：分歧标的不显示单一"群体兑现"（会让散户误以为"跟大家能赚"），改为"多 X% / 空 Y%"（比亚迪：多 −7.2% / 空 +6.6%），让"站错边要亏"直接可见。
3. **crowdReturn 口径统一为每 KOL 当前立场**（与"谁对了/命中"同一人群），避免把某 KOL 已被翻向放弃的旧观点计入群体兑现——与雷达 TickerConsensus 的 avgReturn 也对齐了（寒武纪两处均 −1.9%）。
4. **单 KOL 标的不称"共识"**：`soloDirection` 让 1 人覆盖的标的显示其本人方向（看多/看空/风险）而非"共识看多"。
5. **当前立场问责语义锁定**（注释）：谁对了取 KOL 最新立场，最新未结算即记"待结算"，不回退到更早已结算观点；旧立场仍在时间线呈现。

## 验证结果

- `npx tsc --noEmit` + `npx eslint`：kol-ticker 全部新增/修改文件 clean。
- 浏览器（desktop + mobile 375）：比亚迪三方分歧渲染正确（分方向兑现 多−7.2/空+6.6、谁对了榜带总命中战绩、研判叙事、跨KOL时间线）；神华单 KOL 显示"看多"非"共识看多"；无 console error；移动端 WhoWasRight 横向滚动、页面无溢出。
- 下钻验证：雷达 8 张共识卡均为 `/demo/ticker/*` 链接，点击进入对应横截面。
- **聚焦 review（data-logic + 散户产品 2 视角）已应用收口**：crowdReturn 口径统一、分歧票按方向拆分、谁对了挂整体战绩、单 KOL 去"共识"措辞、当前立场问责注释。

## 未解决项

1. **此票历史胜负序列**：reviewer 建议把 `callCount`（如老纪此票 2 次）展开成胜负序列（先错 −11.8% 后对 +4.1%）。当前用 KOL 整体战绩近似，逐票胜负序列未做。
2. **真实数据接入**：与 kol-radar 同源缝隙——信誉分需 KOLScorer、五向需 opinions 路由放开、creator_id 归属需补齐。
3. **L4 单条证据审计下钻**：时间线每条观点尚未链到 /audit（占位）。
4. 绿色文本对比度（全站 a11y）已单列任务处理。
