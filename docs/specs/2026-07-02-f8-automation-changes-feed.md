# F8 管线自动化 + 时钟保真 + 近期异动真值化

## 概述

live 化收尾三件事一次完成：(1) **F8 自动化**——per-action 回测接入 F5 提取写盘路径（新提取自动带 backtest_result，fail-open），Yahoo 价格源升为包内模块；(2) **时钟保真**——`TimelineOpinion` 暴露真实信号时钟 `executableAt`（此前 `timestamp`=提取时刻把整批塌到 6-25 一个点），适配器全面改用真实时钟；(3) **近期异动真值化**——从观点历史直接派生真实事件（18 次翻向 + 3 次止损），点亮雷达最后一块空区。至此 live 雷达五个区块全部真值。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/backtest/yahoo_prices.py` | 新增 | 包内价格模块（免密钥 Yahoo chart API + symbol 映射 + 按天缓存 `data/cache/yahoo_prices/`） |
| `src/finer/api/routes/extraction.py` | 修改 | F5 写盘前逐条 auto-backtest（fail-open，`FINER_F8_AUTO_BACKTEST=0` 可关） |
| `src/finer/api/routes/opinions.py` | 修改 | `TimelineOpinion` 增 `executableAt`（canonical 执行时钟）+ `exitReason`（additive） |
| `scripts/backfill_f8_backtest.py` | 修改 | 瘦身复用包内 `yahoo_prices`，去重复实现 |
| `src/finer_dashboard/src/components/opinion-timeline/OpinionTimeline.tsx` | 修改 | 接口同步两个新字段 |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 修改 | `clockOf()` 全面改用真实时钟；`deriveLiveChanges()` 从历史派生翻向/止损事件（上限 12 条，倒序） |
| `src/finer_dashboard/src/app/radar/page.tsx` | 修改 | 横幅"异动为空"→"异动由观点历史派生（翻向/止损）" |

## 架构影响

- **F8 成为管线常态而非一次性脚本**：提取即回测，落盘的 wrapper 自带 backtest_result；新内容（信号时钟很近）会因入场后无 bar 被 `insufficient_bars` 跳过，随时间自然转正——不产假值。
- **时钟语义修正是这轮最重要的正确性修复**：此前"最新立场"在同一提取时刻的观点间随机决胜、潮汐图缩成单点、"7 天前"全假。`executableAt` 上线后：雷达期间显示真实 2026-01-26 — 03-30，潮汐呈现真实的 1-3 月转空曲线（0→−12），广度从 9/11/6 修正为 10/12/4（决胜正确化）。
- **异动不是快照-diff**：诚实定位为"从观点历史可直接观测的事实"（同 KOL 同标的连续方向变化 = 翻向；回测 exit_reason=stop_loss = 止损离场）。真正的按日快照-diff 服务仍属未来能力（graduation plan 卡 4），但对当前"历史批量导入"型数据，历史派生比快照-diff 更合语义。

## 关键决策

1. **additive 字段而非改 `timestamp` 语义**——`timestamp` 保持提取时刻（既有消费方不破坏），真实时钟走新字段，消费方显式选择。
2. **新高信念事件不做**：真实数据置信度清一色 0.85（提取默认值，无区分度），做了就是噪声——等 F3 置信度有区分度再启用。
3. **异动 feed 上限 12 条**（21 事件中取最新），保持可扫读。

## 验证结果

- `pytest` 全量 **3013 passed** 零回归；tsc/eslint clean；py_compile OK。
- API：`executableAt=2026-03-30`（vs `timestamp=2026-06-25`）、`exitReason=target_reached` 上线。
- `/radar` 浏览器实测：期间 2026-01-26 — 03-30；潮汐 1-3 月完整曲线；**近期异动 12 条真实事件**（trader_ji 上证指数 看空→中性→看多 等翻向 + 止损卡）；可信度榜真值无损（51%/60%）；无 console error。

## 未解决项

1. **同时钟翻向的顺序歧义**：同一 executableAt（如 000001.SH 03-02 的 bearish 与 bullish）之间的先后由数组顺序决定，翻向方向可能任意——根因是 F5 提取未保留原文内顺序，属数据粒度问题，已知不阻断。
2. **extraction 钩子内同步网络调用**：`fetch_daily_closes` 在 async 任务里是阻塞调用（每 ticker ~200ms，有日缓存）；后台任务可接受，量大时应改 executor/async client。
3. 异动派生在前端适配器；将来快照-diff 服务落地时应后移并统一（与信誉分后移同批）。
4. `deriveLiveChanges` 无单测（纯前端派生逻辑）；如稳定化可补 vitest。
