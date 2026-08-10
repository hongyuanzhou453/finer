# 宣传站 /records 可下钻研报记录页（2026-08-10）

## 概述

把宣传站「记录与共识」从静态截图升级为可交互体验：新增 `/records` 页，在冻结的
真实语料快照上做三层下钻——信源记录卡墙 → 单信源全部研报结果 → 单条详情。
回应用户需求「各个外资研报的结果应该能点开查看具体的内容」。纯静态实现
（客户端 fetch 冻结 JSON），无后端依赖，与产品同一套效力门纪律。

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/export_site_records_snapshot.py` | 新增 | 快照导出器：读 F5 actions + F3 intents，产出记录卡（复用 `build_record_cards`，sufficiency 必填）与逐信源结果行；版权清洗（无研报原文、无分析师姓名） |
| `src/finer_site/public/records-data/*.json` | 新增 | 冻结快照（as_of 2026-08-10）：manifest（两口径 24+24 张卡）+ 28 个 creator-N.json，共 4,587 行 / 2,740 已结算，2.9MB 分文件按需加载。**注意 root .gitignore `*.json` 需 `git add -f`** |
| `src/finer_site/src/demo/records/types.ts` | 新增 | 快照 TS 类型（含 display_policy 三值：show / show_with_warning / count_only） |
| `src/finer_site/src/components/records/*.tsx` | 新增 | RecordsExplorer（单页状态机）+ RecordCardWall + CreatorRecordView + primitives |
| `src/finer_site/src/app/records/page.tsx` | 新增 | 页面外壳与 metadata |
| `src/finer_site/src/app/page.tsx` | 修改 | #records 区加 CTA「点开每家信源的完整记录」；/discover 截图 Link 到 /records |
| `src/finer_site/src/components/landing/site-chrome.tsx` | 修改 | footer 产品列加「信源记录」 |
| `src/finer_site/src/app/sitemap.ts` | 修改 | 加 /records |
| `README.md` / `README.en.md` | 修改 | 记录与共识章各加一句可交互快照入口（中英镜像） |

## 架构影响

无产品代码变更。快照导出器是 F5/F3 数据的只读消费者，复用
`finer.credibility.record_card.build_record_cards`（效力门 schema 必填）与
`finer.backtest.scorecard.is_scoreable`（结算判定），保证宣传页数字与产品
/discover 同源同口径。行文件混两种 signal_class，UI 按卡片口径过滤后
行数与卡面精确对账（复核 agent 逐位验证 6 张卡）。

## 关键决策

1. **同一纪律，不做营销版例外**：count_only（板块 24 张 + 个股 10 张）零比率渲染；
   show_with_warning（美银、汇丰）比率携带后端告警注（卡面与下钻头部两处）；
   持续性检验横幅由快照数据（predictive_claim.summary + notes）驱动渲染。
2. **版权边界**：公开快照只含结构化事实（评级/目标价/方向/日期/结算），
   不含研报原文片段与分析师姓名；详情面板注明完整证据链在产品 /audit 内。
3. **冻结不装实时**：as_of 三处常驻（页头/卡墙脚注/信源头部）；快照即档案。
4. **未来日期不遮掩**：摩根士丹利记录窗口含语料已知的未来时间戳（D1 审计器
   Q3 已立案），产品 /discover 同样如实显示，宣传页忠实镜像。
5. 单页状态机 + 行内展开详情（非子路由/抽屉），静态导出最稳；每页 50 行分页 +
   ticker 搜索 + 方向筛选。

## 验证结果

- `npx tsc --noEmit` 0 错误；`npm run build` 11 路由全静态生成（含 /records）
- 实现 agent playwright 冒烟 24 断言通过；独立复核 agent 逐位对账 6 张卡数字、
  全量 2,740 结算行 win 与收益符号一致性、双重放大检查（return_pct 仅 ×100 一次）
- 复核两条 should-fix 已修：show_with_warning 告警注随行下钻头部；
  表格容器加 max-height 使 sticky 表头真实生效
- 终检 playwright 走查：卡墙/瑞银 670 行/行详情/美银告警注四屏截图确认
- 禁词扫描（更准/最佳/Top/推荐/实时）仅存于否定句式

## 未解决项

- push 与部署待用户确认（公开发布红线）
- 快照刷新是手动流程（重跑导出器 + 构建 + 部署）；如需定期刷新可后续加脚本入口
- root .gitignore `*.json` 误伤快照数据文件（已 `git add -f` 绕过；独立修复任务进行中）
