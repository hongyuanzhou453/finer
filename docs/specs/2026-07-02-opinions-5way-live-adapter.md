# 五向放开 + 前端 live 适配层 — dashboard 第一次吃真数据

## 概述

按"② 五向放开 → ① 前端切 live"的定案顺序，完成两件事：(1) opinions API 的方向语义从 3 向坍缩放开为完整 5 向 TradeDirection 并附加 market/traceStatus 字段；(2) 新增 opinions→view-model 的 live 适配层与两个 LIVE 路由（`/radar` 观点雷达、`/radar/kol/[kolId]` KOL 问责页），**观点雷达与问责页第一次渲染真实管线数据**（58 条 F5 TradeAction，2 个归属 KOL）。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/api/routes/opinions.py` | 修改 | `TimelineOpinion.direction` Literal 3→5；`_DIRECTION_MAP` 1:1 透传（去 risk_warning→bearish、watchlist→neutral 坍缩）；stats `byDirection` 5 桶；converter 附加 `market`/`traceStatus` |
| `src/finer_dashboard/src/components/opinion-timeline/OpinionTimeline.tsx` | 修改 | `OpinionDirection` 3→5；`TimelineOpinion` 增 market/traceStatus（前后端契约同步） |
| `.../opinion-timeline/TimelineNode.tsx` | 修改 | `DIRECTION_STYLES` 补 watchlist/risk_warning；标签三元改 `DIRECTION_LABELS` 全映射 |
| `.../opinion-timeline/OpinionDetailModal.tsx` | 修改 | `DIRECTION_CONFIG` 补 2 向 |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 新增 | live 适配器：分页拉取（后端 limit≤100，cursor=offset）→ 按 author 分组 → `KOLRadarData`/`KOLSnapshotData`；未归属观点排除并计数 |
| `src/finer_dashboard/src/app/radar/page.tsx` | 新增 | LIVE 观点雷达（loading/后端未起/空数据/正常四态 + LIVE 横幅） |
| `src/finer_dashboard/src/app/radar/kol/[kolId]/page.tsx` | 新增 | LIVE KOL 问责页 |

## 架构影响

- **API 契约变更（放宽，向后兼容除穷举 switch 外）**：direction 值域扩大；前端所有 `Record<OpinionDirection,…>` 穷举映射已同步补齐。stats byDirection 增 2 桶（additive）。
- **fixture 与 live 双轨并存**：`/demo/*` 保留为设计标杆；`/radar/*` 为真实数据轨。同一套 KOLRadar/KOLSnapshot 组件、同一套派生函数，仅数据源不同——验证了"组件数据源无关"的设计。
- **诚实映射纪律**（适配器注释固化）：changes=[]（无快照-diff）、narrative=占位说明（无 F7/LLM 综合）、style/specialties=未标注（无 KOL profile 接线）、未归属观点排除不冒充。

## 关键决策

1. **② 先于 ①**：五向是前端 fidelity 前提，先放契约再切数据源，避免切两次。真实 58 条现值均为 3 向（bullish18/bearish29/neutral11），放开今天零可见变化、纯保真。
2. **live 路由独立命名空间 `/radar/*`**，不覆盖 `/demo/*` 标杆——对照入口互链（LIVE 横幅 ↔ 设计标杆）。
3. **未归属观点排除而非合桶**：author 为空/unknown 的观点不进 KOL 分组（当前 0 条，58 条全归属，回填生效的直接证明），计数展示在横幅。

## 验证结果

- 后端：`py_compile` OK；`pytest -k opinion` 22 passed；TestClient 确认 `market=US / traceStatus=canonical` 上线、`byDirection` 5 桶。
- 前端：`tsc --noEmit` clean；`eslint` exit 0。
- 端到端（uvicorn :8000 + next dev + 浏览器）：
  - `/radar`：LIVE 横幅（58 条 · 2 KOL · 异动为空）；裁决"分歧"（1 多家/1 空家）；可信度榜 trader_ji/sandbox 各 68 分带**样本少**标、命中率"—·0 笔"（无回测→先验分，诚实）；近期异动空态；真实 call 渲染（苹果 AAPL 看空、美团 3690.HK 看多、宁德时代 300750.SZ 看多…）。
  - `/radar/kol/trader_ji`：▼ 偏空 净空−12（15多/27空/10中性）、52 条、验证率 0/52、已结算 0、研判占位。
  - 错误态实测：limit=1000 曾触发 422 → 适配器改分页后恢复；后端未起时显示 uvicorn 启动提示 + 标杆链接。
  - 无 console error。

## 未解决项（真数据照出来的管线质量问题——正是本 milestone 的产出）

1. **F1/F2 质量缺陷用户可见了**：部分 evidence/summary 是退化重复 token（"EWY | EWY | EWY…"）；`光模块·OPTICAL_MODULE` 伪 ticker（F2 实体锚定失败未映射真实标的）；置信度清一色 85%（提取默认值，无区分度）。→ 应回流为 F1 OCR 质量与 F2 锚定的修复输入。
2. **无 F8 回测数据**：所有 priceChange=null → 命中率全"—"、信誉分全为先验 68、观点象限/兑现榜空。下一块就是 F8 回测落库（graduation plan 地基 B）。
3. **雷达内下钻链接仍指向 `/demo/*`**（TickerConsensus→/demo/ticker、时间线→/demo/audit）：live 轨的 L3/L4 尚未建，点击会落到 fixture 页。待 live 化推进时统一 basePath。
4. 老 opinion-timeline 组件族是西式配色（emerald=看多/red=看空），与操作台中国惯例相反——既存设计债，未在本次改动。
