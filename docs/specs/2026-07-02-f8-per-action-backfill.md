# F8 回测落库 — per-action 评估器 + 真实价格回填

## 概述

live 化地基 B 落地：为 58 条真实 F5 TradeAction 产出**真实回测结果**并原子写回权威文件。42 条有效评估（Yahoo 真实日线），命中率 52%；opinions API 零改动自动出真值；`/radar` 可信度榜第一次由真实兑现驱动排名（sandbox 71 分·60%·5笔 反超 trader_ji 68 分·51%·37笔），样本量收缩公式在真数据上验证正确。问责脊柱（观点→价格→回测→命中率→信誉分→榜单）全线真值运转。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/backtest/per_action.py` | 新增 | 薄 per-action 评估器：方向校正跟单 P&L（bullish=+1，bearish/risk_warning=−1），entry=执行时钟当日或之后首根收盘，exit=止损−10%/止盈+20%/30天/数据尽头，净收益扣 0.3% 往返成本，产出 schema `BacktestResult`（分数单位）；退化样本（入场后无 bar）跳过不产噪声 |
| `src/finer/services/repository.py` | 修改 | 新增 `update_backtest_result`（克隆 update_validation_status 的原子写 pattern：锁+单读+只改一键+tmp/fsync/os.replace+重建索引） |
| `scripts/backfill_f8_backtest.py` | 新增 | 编排：读 F5 → Yahoo chart API 拉日线（免密钥，`.SH→.SS`/`DXY→DX-Y.NYB` 映射，21 标的实测全通）→ 逐条评估 → dry-run 默认 / `--apply` 带备份写回 + F8 provenance + 价格快照落 `data/market/yahoo_snapshots/` |
| `tests/test_backtest_per_action.py` | 新增 | 10 用例：止盈/止损/时间退出/空头方向校正/入场对齐/中性跳过/无价跳过/入场后无bar跳过/数据尽头 |
| `src/finer/api/routes/opinions.py` | 修改 | `priceChange` round 2→4 位（2 位=1% 粒度会把 +0.3% 抹成 0，命中计数失真——实测 sandbox 60%→20% 的偏差即此因） |
| `data/F5_executed/*_actions.json` | 数据回填 | 42 条 `backtest_result`（🔴 红线，已授权；备份 `F5_executed.bak-20260702-173915`） |
| `data/F8_metrics/per_action_backfill_20260702-173915.json` | 新增 | 批次 provenance（价格源/逐条结果） |

## 架构影响

- **为什么不用组合引擎**（摸底 3 视角汇聚的结论）：`BacktestEngine` 是组合级工具——同 ticker 已有持仓直接 skip（000001.SH×16 只会产 1 笔）、bearish+close_long 分发进开空分支、混合时区 timestamps 直接 `pd.to_datetime` 崩（实测）。逐条归因需要 per-action 独立评估，薄评估器 ~130 行且与前端"return_pct=方向校正跟单 P&L"契约精确一致。
- **价格数据结论**：既有两条路皆死（tushare：无 token/库未装/parquet 空/不覆盖指数与美港；finance-skills：无 key 且服务端 307→静态页）。Yahoo chart API 免密钥直连**实测全通**（美/港/A股/指数/DXY），只有伪 ticker OPTICAL_MODULE 404（预期跳过）。快照落盘保证可复现。
- **写回而非读时 join**：符合"文件权威源"约定，opinions/kol/audit 三个读面零改动；F8_metrics 留批次 artifact 作 provenance。
- **回测时钟修正**：58 条 `timestamp` 全是 2026-06-25（提取时刻），真实执行时钟 `action_executable_at` 分布在 2026-01-26→03-30——窗口充足，30 天持仓全部可闭合，"只有 5 个交易日"的担忧不成立。

## 关键决策

1. **bearish/risk_warning 一律按方向校正 P&L 评估**（跌了算对），与 dashboard 契约和 kol-radar fixture 语义一致；不模拟真实做空的借券等细节（0.3% 往返成本统一近似摩擦）。
2. **入场后无 bar → 跳过**：dry-run 首轮暴露 000905.SH 只拉到 1 根 bar，两条 action 退化成"当天进出 −0.3%"噪声——加 `insufficient_bars` 跳过，44→42 条，宁缺毋假。
3. **中性 11 条 / 伪 ticker 4 条 / 数据缺口 3 条保持 null**：前端本来就有"待回测"空态，诚实呈现。
4. **round(2)→round(4)**：分数收益用 2 位小数=1% 粒度，边缘命中被抹平（sandbox 3/5 被显示成 1/5），4 位修复后前后端命中数逐笔对账一致。

## 验证结果

- 单测：`tests/test_backtest_per_action.py` 10/10；全量 `pytest tests/` **3013 passed**（基线 3003+10）零回归。
- dry-run：21 标的价格覆盖（240-252 bar），42 评估 / 11 中性 / 3 无价 / 2 入场后无bar；命中 22/42=52%。
- apply：42/42 写回 0 失败；备份+provenance+价格快照齐全。
- API：`/timeline` priceChange/holdingDays 出真值（EWY +20%/9天、MU 空 −14.6%/2天）；settled 分布 {trader_ji:19/37, sandbox:3/5} 与脚本逐笔一致。
- `/radar` 实测截图：可信度榜真实分化——sandbox 71（60%·5笔）> trader_ji 68（51%·37笔），样本量收缩数学验证（(3+2)/(5+4)=55.6%→71；(19+2)/(37+4)=51.2%→68）；"样本少"标随 37 笔消失。

## 未解决项

1. **回填是一次性脚本**：新 F5 提取产出的 action 不会自动回测。长期应把 per-action 评估接入管线（如 F5 落盘后异步跑）或定时任务；Yahoo fetch 也可升级为 `prices.py` 的正式 provider。
2. **观点象限（问责页）**：live 快照页现在有 returnPct 了，观点象限/兑现榜应已自动点亮——尚未逐屏截图验证。
3. **exit_reason=UNKNOWN 的数据尽头语义**：schema ExitReason 无 END_OF_PERIOD，暂用 UNKNOWN；如常态化应扩枚举。
4. 信誉分仍为前端派生（kol-radar.ts）；后端 KOLScorer 聚合（graduation plan 卡3）仍待做，届时把公式后移成唯一真相源。
5. OPTICAL_MODULE 等伪 ticker 的根治在 F2 锚定质量（照妖镜清单第 1 条）。
