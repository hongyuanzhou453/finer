# 散户向 KOL 晨星体检 Demo（真实数据匿名化冻结快照）

## 概述

在 `src/finer_site` 新增一条散户向、可分享的单页 demo `/kol-check`：对**一位真实（匿名化）KOL** 的喊单做"晨星式体检"，跑在**真实 F5 canonical TradeAction 的冻结快照**上（标的/时序/原话/回测保真，身份匿名）。目标形态 = 异步分享给潜在用户自己看，全前端静态、不连后端。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer_site/scripts/freeze_kol_check_snapshot.py` | 新增 | 冻结+匿名化脚本：读 `data/F5_executed/*.json` 非 bak 的 42 条 action，取 `trader_ji` 37 条，映射为 `KOLRadarData` + `TradingStyleProfile` + `auditById`，输出 `data.json` |
| `src/finer_site/src/demo/kol-check/data.json` | 新增（生成物） | 冻结快照：1 个匿名 KOL、37 viewpoints、观测风格、逐条 F3→F8 审计负载 |
| `src/finer_site/src/demo/kol-check/kol-snapshot.ts` | 新增（移植裁剪） | 类型 + 派生（deriveSummary/deriveHighlights/netStance/deriveTickerRotation）。删造假 fixture，改本地 contract 引用 |
| `src/finer_site/src/demo/kol-check/kol-radar.ts` | 新增（移植裁剪） | 类型 + 派生（deriveCredibilityBoard/deriveEarningsBoard 等）。删 5 个造假 persona，保留纯函数 |
| `src/finer_site/src/demo/kol-check/kol-l2.ts` | 新增（移植） | `deriveKolSnapshot` 逐字移植 |
| `src/finer_site/src/demo/kol-check/contracts-style.ts` | 新增 | `TradingStyleProfile` 类型切片（~40 行，替代 dashboard 50KB contracts.ts） |
| `src/finer_site/src/demo/kol-check/fixtures.ts` | 新增 | 类型化加载 data.json，导出 RADAR/TRADING_STYLE/AUDIT_BY_ID/KOL_ID + AuditRecord 类型 |
| `src/finer_site/src/components/kol-check/primitives.tsx` | 新增（移植） | DirectionTag/ReturnChip/ConfidenceMeter/SectionHeader 等，逐字移植改引用 |
| `src/finer_site/src/components/kol-check/TradingStyleCard.tsx` | 新增（移植） | 言行不一卡（declared vs observed），逐字移植改引用 |
| `src/finer_site/src/components/kol-check/ViewpointTimeline.tsx` | 新增（增强） | 逐条观点 + 内联可展开 F3→F4→F5→F8 审计抽屉（真实 trace id）；单 URL 无路由 |
| `src/finer_site/src/components/kol-check/KolCheckReport.tsx` | 新增（自写） | 散户向页壳：hero 体检结论 → 01 言行不一 → 02 标的兑现榜 → 03 战绩时间线 |
| `src/finer_site/src/app/kol-check/page.tsx` | 新增 | 路由（server component + SiteHeader/SiteFooter chrome） |
| `src/finer_site/src/app/sitemap.ts` | 修改 | 加 `/kol-check` 条目 |

## 架构影响

- **零后端依赖**：与 finer_site 既有约定一致（`output:'export'`），新增第 5 条静态路由。数据是冻结 JSON，非 live API。
- **派生逻辑是移植的契约**：信誉分样本量收缩（PRIOR_K=4）、命中率、按结算时点分箱等来自 dashboard `src/lib/fixtures/`，逐字移植以避免重写走样。已用 tsx harness 在真实数据上验证输出与手算一致。
- **不触碰 Round 4 红线** `src/finer_dashboard/**`：只在 `src/finer_site/` 新增。
- **契约切片**：`contracts-style.ts` 镜像 `src/finer/schemas/kol_profile.py` 的 TradingStyleProfile，字段与后端 + data.json 对齐。

## 关键决策

1. **单 KOL 体检，而非多 KOL 雷达**：真实数据只有 1 个实质 KOL（trader_ji，37 条；sandbox 是孤儿测试数据，剔除）。多 KOL 可信度榜需要多人，编造会破坏诚实性——故砍掉雷达/共识/收益榜，聚焦单个真实 KOL 的问责报告。
2. **匿名化口径**：`trader_ji`/`trader韭`/feishu id/绝对路径全部剥离，化名 `科技成长派 · 匿名KOL`（代号 kol-anon-tech，单常量可改）。**保留**真实标的/时序/回测/KOL 原话。
3. **市场显示从 ticker 后缀归一**：真实 `market` 字段有误标（9992.HK 标 US），按 `.HK/.SH/.SZ/无后缀→US` 归一显示（ticker 是权威源，非伪造）。
4. **审计走内联抽屉而非独立路由**：保持单 URL（利于分享），每条 viewpoint 附完整审计负载（intent/policy id、四时钟、F8 回测、F2 span），点开即见 canonical 全链。
5. **诚实基调**：命中率 27.6%、等权跟单 −4.2%、言行不一——照实展示。卖点是"系统抓出来了"（问责），不是嘲讽 KOL。

## 验证结果

- `npx tsc --noEmit` → exit 0（clean）
- `npm run build` → ✓ 10/10 静态页生成，`/kol-check` 作为 `○ (Static)` prerender
- tsx harness 跑真实数据：信誉分 57、命中率 0.276（8胜/21负/29结算）、平均 −4.22%、最佳/最差都是泡泡玛特（+26.6%/−17.1%）、观测左侧 6/右侧 1 vs 自述右侧（冲突）
- 浏览器预览（localhost:4311/kol-check）：零 console error；全 3 段渲染正确；审计抽屉展开显示真实 trace id（F3 intent 483212a7…、F4 policy d947173c…、四时钟、F8 −0.8%/30天/到期平仓、4 条 F2 span）

## 未解决项

1. **逐字原话的再识别风险 + ASR 噪声**：evidenceText 保留 KOL 真实原话（最强证据，但精确措辞可被搜索反查身份；部分是直播转写有口语噪声）。公开分享前需用户决定：保持逐字 / 轻度改写 / 判定化名已足够。
2. **公开部署未做**（红线，需用户明确授权）：当前只到本地验收。`/kol-check` 上线到 finer.t800.click = 对外发布一位真人（匿名）的战绩单，属公开发布动作，需用户拍板 + 上条原话决策落定后再做。
3. **shareable 图**：本地 preview 在用户 localhost；对外可分享形态即部署后的公网 URL。
