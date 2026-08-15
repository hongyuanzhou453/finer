# Finer 前端资产台账（2026-08-15）

> 由 10 个只读 agent 并行盘点产出：5 路清点（dashboard 路由 / dashboard 组件 /
> site 全量 / 设计 token / 前后端契约）+ 4 路交叉审计（死资产、跨 app 重复、
> 定位对齐、健康度）+ 1 路合成。共清点 161 项资产、产出 56 条发现。
>
> 主控已逐条核实的关键结论：`/records` 均值收益漏在 count_only 门外（34 张
> count_only 卡中 24 张受影响，KeyBanc settled=1 印 +58.0%）；`/kol/compare`
> 零网络调用且占主导航第 4 格；`opinion-timeline`(1,818 行) /
> `rlhf-review-panel`(1,743 行) / `mock-contracts.ts`(456 行) 外部引用方均为 0；
> 主导航八项不含 `/discover` `/ticker` `/audit`。

> 盘点范围：`/Users/zhouhongyuan/Desktop/finer/.claude/worktrees/nervous-villani-7587cb` 的两个 Next.js app（`src/finer_dashboard`、`src/finer_site`）。仅只读调查，未修改任何文件。基准日期 2026-08-15。

---

## 1. 一句话总览

Finer 前端是**两个 Next.js app 的双份世界**：对外站 `finer_site`（6 路由，已上线 finer.t800.click，主叙事已完成 2026-08-02 定位转向）基本干净；内部 `finer_dashboard`（22 路由、159 个 ts/tsx）则处于**「新消费面已建好但没接上导航、旧评分口径还占着主导航」的分裂状态**——真正执行 CRD-2 效力门的 `/discover` `/ticker/[symbol]` `/audit` 三条主线**零入站链接**，而硬编码假数据的 `/kol/compare`、按信誉分排名的 `/radar` 稳坐一级导航；此外 4,017 行代码从任何入口不可达，globals.css / kol-radar 派生库 / TradingStyleCard 等在两 app 逐字节双份且已开始单侧分叉。

---

## 2. 资产地图

状态定义：**现役** = 有入口且喂真实数据；**演示** = fixture/冻结快照驱动的展示件；**废弃语义** = 承载「评分/排名/谁更准」信息模型（与 2026-08-02 定位冲突）；**孤儿** = 无任何入站链接或无任何消费方。

### 2.1 finer_dashboard — 页面路由（22 条）

| 路径 | 类型 | 数据源 | 状态 | 备注 |
|---|---|---|---|---|
| `src/app/layout.tsx` | 根 layout | — | 现役 | 只设 html/body + metadata，**不含导航**；`/discover` `/ticker` `/audit` `/radar` `/demo/*` `/research` 全部只吃这层，进去后无法导航回主站 |
| `src/app/page.tsx` | 页面 `/` | live API | 现役 | 三栏工作台（Sidebar + MainBoard + InspectorPanel）；:196 残留 `console.log`；:220 调幽灵端点 `/api/files/enrichment/{entity}` |
| `src/app/discover/page.tsx` | 页面 `/discover` | live API | 现役 | **全仓唯一严格执行 CRD-2 效力门的页面**（758 行，count_only 走 BlankCell，均值/中位收益都在 `!countOnly` 内）；:513 明写「默认序 = 已结算样本量降序」。零入站链接 |
| `src/app/ticker/page.tsx` | 页面 `/ticker` | 静态 | 现役 | 输入框 + 4 个示例代码，`router.push` 到 `/ticker/[symbol]`。零入站链接 |
| `src/app/ticker/[symbol]/page.tsx` | 页面 | live API | 现役 | CRD-3 共识记录（377 行）；陈旧度横幅、booktabs 信源表、目标价离散度。`directional_agreement` 无 n 下限（见问题 #11） |
| `src/app/audit/page.tsx` | 页面 `/audit` | live API（可切 fixture） | 现役 | F3→F4→F5 trace 时间线；`NEXT_PUBLIC_AUDIT_USE_FIXTURES` 显式开关 + 「Sample data」徽章，是 fixture 治理的正确样板。仅 Sidebar 有入口 |
| `src/app/research/page.tsx` + `layout.tsx` | 页面 `/research` | live API | 孤儿 | 249 行，真数据、写得干净、无合成占位；唯一入站是 `/landing`——而 `/landing` 自身零入站，故**传递性不可达** |
| `src/app/radar/page.tsx` | 页面 `/radar` | live API | 废弃语义 | 主导航第 2 格。渲染 `CredibilityBoard`（0-99 信誉分排行）+ `EarningsRace`（TOP EARNERS 排名重排动画），**真实数据 + 无任何 sufficiency** |
| `src/app/radar/kol/[kolId]/page.tsx` | 页面 | live API | 废弃语义 | 「兑现命中率」裸点估计无区间无 tier；「标的兑现榜 TICKER SCOREBOARD · 按平均兑现排名」 |
| `src/app/kol/page.tsx` | 页面 `/kol` | live API | 废弃语义 | 主导航第 3 格。排序三选项 `score/accuracy/return`，**默认 score，无样本量选项**；第三格印 `totalOpinions` 而非分母 `settled_opinions` |
| `src/app/kol/[id]/page.tsx` | 页面 | live API | 废弃语义 | 「能力雷达」把后端已删除的 timeliness/clarity/depth 回填 0.0 渲染成条形图；「最大收益 +0.0%」「平均持仓 0 天」是 adapter 硬编码常量 |
| `src/app/kol/compare/page.tsx` | 页面 | **硬编码** | 废弃语义 | 主导航第 4 格。4 个假 KOL 全部写死（overallScore 4.2/3.8/4.5/4.0），**零网络请求**，`getBestKOL()` 给最优值打 ★ |
| `src/app/kol/[id]/backtest/page.tsx` | 跳板 | live API | 现役 | 拉最近一条回测后 `router.replace` |
| `src/app/kol/[id]/backtest/[backtestId]/page.tsx` | 页面 | live API | 现役 | F8 回测详情：累计收益、风险收益散点、百分位表、方法论条 |
| `src/app/backtest/page.tsx` + `layout.tsx` | 页面 `/backtest` | live API | 现役 | 主导航第 5 格。任务列表 + 删除 |
| `src/app/annotation/page.tsx` + `layout.tsx` | 页面 `/annotation` | live API | 现役 | 11 行壳，全部逻辑在 `AnnotationWorkbench`；`/api/annotation/**` 是唯一 10/10 端点全消费的 router |
| `src/app/training/page.tsx` + `layout.tsx` | 页面 `/training` | 静态 | 废弃语义 | 主导航第 7 格。874 行中 840 行与公开站 `/training` 重复，且停在转向前口径（:71「1-5 星评分」） |
| `src/app/landing/page.tsx` + `layout.tsx` | 页面 `/landing` | 静态 | 孤儿 | 669 行，全仓零 href 指向；:55「回测与评分」、:380「整体 1-5 星评分」；却是 `/research` `/training` `/annotation` `/backtest` 的唯一链出源 |
| `src/app/settings/page.tsx` + `layout.tsx` | 页面 `/settings` | 部分硬编码 | 废弃语义 | 主导航第 8 格。`DataSourceConfig` 是真的；`mockKOLConfigs` 三个假 KOL 开关不落盘 |
| `src/app/demo/kol-radar/page.tsx` | 页面 | fixture | 演示 / 废弃语义 | demo 树枢纽（被引 7 次）；metadata 自述「可信度榜、此刻可跟」 |
| `src/app/demo/kol/[kolId]/page.tsx` | 页面 | fixture | 演示 / 废弃语义 | `deriveKolSnapshot(KOL_RADAR_FIXTURE, kolId)` |
| `src/app/demo/ticker/[ticker]/page.tsx` | 页面 | fixture | 演示 / 废弃语义 | 「共识裁决 / 谁对了 / 立场时间线」 |
| `src/app/demo/audit/[viewpointId]/page.tsx` | 页面 | fixture | 演示 | 单观点证据链，口径无问题 |
| `src/app/demo/kol-snapshot/page.tsx` | 页面 | fixture | 孤儿 | 17 行，零入站，与 `/demo/kol/[kolId]` 功能重合 |
| `src/app/demo/kol-rating/page.tsx` | 页面 | **live API** | 孤儿 / 废弃语义 | 零入站；硬编码 `kolId="demo_001"`，组件内 `fetch('/api/kol/rating/demo_001')` 打真后端而该 id 全仓不存在 → 必然失败 |

### 2.2 finer_dashboard — 组件目录（18 个）与 lib

| 路径 | 类型 | 数据源 | 状态 | 备注 |
|---|---|---|---|---|
| `src/components/crd/primitives.tsx` | 基础件（538 行） | live API | 现役 | CRD 消费面唯一新基础件；0 调色板字面量；`WilsonBar`:169 声明「不自行放行，调用方必须先判 display_policy」，`BlankCell` 是留白件。被 4 文件引 |
| `src/components/audit/` (8 文件) | 审计台 | live API | 现役 | trace-timeline / evidence-source（char offset 对齐 + indexOf 兜底）/ execution-clocks 四时钟；0 字面量 |
| `src/components/kol-snapshot/` (9 文件) | 快照族 | live + fixture | 现役 / 废弃语义 | `primitives.tsx` 是全仓被引最广的旧基础件（23 文件）；但 `KOLSnapshot.tsx:335/364` 的命中率无门、「兑现榜按平均兑现排名」违红线 |
| `src/components/kol-radar/` (9 文件) | 雷达族 | live + fixture | 废弃语义 | `CredibilityBoard`（自述 the product spine，按信誉分排名）、`EarningsRace`（TOP EARNERS + 排名动画）；`links.ts` 做 DEMO/LIVE 双链，是唯一 fixture↔live 同构的一族 |
| `src/components/kol-ticker/` (5 文件) | 横截面族 | fixture | 演示 / 废弃语义 | `WhoWasRight`「谁对了 · ranked by realized follow-P&L」；仅 demo 消费，无 live 路径 |
| `src/components/kol-rating-card/` (7 文件, 1,589 行) | 晨星评价卡 | live API | 废弃语义 / 事实孤儿 | 唯一消费方是必然 404 的 `/demo/kol-rating`。`StarRating`（五星+金银铜牌+优秀/较差）、`DimensionScores`（0-100，**绿=好红=差，与红涨绿跌正相反**）。`FocusAreas.tsx`(245 行) 从未被 JSX 渲染，仅 barrel re-export。2026-08-15 刚在其上做了效力门根治 |
| `src/components/layout/` (8 文件) | 骨架 | live API | 现役 | `header.tsx:18-27` 八项导航（实测确认）；`sidebar.tsx` 只补 `/radar` `/audit` `/settings`；`inspector-panel.tsx:96` 调幽灵端点后静默置空 |
| `src/components/annotation-workbench/` (7 文件, 2,945 行) | HQ 标注台 | live API | 现役 | 仓内最大组件目录；`AnnotationWorkbench.tsx` 960 行、`EvalGoldForm.tsx` 906 行；字面量最重（~313 处） |
| `src/components/studio/annotation-workbench.tsx` (552 行) | 首页内嵌复核 | live API | 现役 | 与上者**同名不同物**，第二套标注 UI |
| `src/components/rlhf-review-panel/` (10 文件, 1,743 行) | F6 复核面板 | live API | **孤儿** | 第三套标注/复核 UI，零消费方；仓内唯一提及是 `/training` 页的散文 |
| `src/components/opinion-timeline/` (6 文件, 1,818 行) | 观点时间线 | live API | **孤儿** | 零消费方；`index.ts` 里还写着「使用示例」文档 |
| `src/components/import-console/` (5 文件) | F0 Import Console | live API | 现役（间接） | 只被 `DataSourceConfig.tsx:6` 引用，无页面直接 import |
| `src/components/data-source-config/` (6 文件) | F0 渠道配置 | live API | 现役 | `WeChatConfig.tsx:222` 调后端不存在的 `DELETE /api/wechat/accounts/{id}` |
| `src/components/f8-charts/` (3 文件) | F8 图表 | live API | 现役 | ECharts 薄封装 + `CumulativeReturnResearch`；0 字面量 |
| `src/components/research/` (5 文件) | Research 三栏 | live API | 废弃语义 | `kol-object-rail.tsx:9-14` 排序器写死 `score/accuracy/return`，默认「评分」；`research-canvas.tsx:104` 全文件无 sufficiency |
| `src/components/kol-audit/` (2 文件) | 单观点审计 | fixture | 演示 | 仅 `/demo/audit/[viewpointId]` 消费 |
| `src/components/error-panel/` (2 文件) | Line F 错误面板 | — | 现役 | 渲染 request_id/stage/retryable/fix_hint；9 处引用。:282 把 `http://127.0.0.1:8000/...` 硬编码成用户可点链接 |
| `src/components/landing/` (2 文件) | 落地装饰 | 静态 | 孤儿（半） | `product-frame.tsx` 与 site 版 **md5 逐字节相同**；`pipeline-strip.tsx` 仅差一词且差的正是口径（dashboard「回测评分」vs site「回测结算」） |
| `src/lib/contracts.ts` | 契约镜像 | — | 现役 | 122 个导出类型；:552-568 `KOL.dimensionScores` 五维非 null，不走 sufficiency 通道，与同 type 里已 nullable 的 overallScore 并存 |
| `src/lib/adapters.ts` | 视图模型转换 | live API | 废弃语义 | :343-347 五处 `?? 0` 回填维度分；:418-420 硬编码 `maxReturn/minReturn/avgHoldingDays = 0` |
| `src/lib/api-client.ts` / `api-proxy.ts` | 请求层 | live API | 现役 | `api-client.ts:186` 裸 `as T`，contracts 的 122 个类型在此退化为「但愿如此」；`api-proxy.ts:20` 认 `BACKEND_ORIGIN` |
| `src/lib/audit-api.ts` / `f8-visualization.ts` / `finance-format.ts` | 工具 | — | 现役 / 混合 | `finance-format.ts` 红涨绿跌注释完整，但 `scoreToneClass`(0-5 评分) 是废弃语义，`directionStyle` 只 case 了 bullish/bearish，watchlist 与 risk_warning 全落「中性」 |
| `src/lib/fixtures/` (6 文件) | fixture 层 | fixture | 演示 | `kol-radar.ts` 是 LIVE 路径的类型与派生真相源（不能单独删）；`kol-snapshot.ts` 同时充当 `/radar/kol/[kolId]` 的类型源 |
| `src/lib/mock-contracts.ts` (456 行) | mock 类型 | — | **孤儿** | 全仓零引用 |
| `src/app/api/**/route.ts` (14 个) | 代理 | live API | 现役 12 / 孤儿 2 | 孤儿：`rlhf/[...path]`（唯一消费方不可达）、`files/enrichment/[...path]`（**后端无此端点**） |
| `public/*.svg` (5 个) + `public/landing/*.png` | 静态资源 | — | 孤儿 | file/next/vercel/globe/window.svg 是 create-next-app 样板；4 张 PNG（668K）唯一引用方是孤儿页 `/landing` |

### 2.3 finer_site — 页面与组件（6 路由）

| 路径 | 类型 | 数据源 | 状态 | 备注 |
|---|---|---|---|---|
| `src/app/layout.tsx` | 根 layout | 静态 | 现役 | metadata 已收敛新定位「不告诉你谁更准 / 查得清每一句话」 |
| `src/app/page.tsx` | 页面 `/` | 静态 | 现役 | 955 行，7 锚点区。:225 hero 仍无条件承诺「每个数字 3 次点击到原文证据」，与 `/records` 自述「公开快照不含研报原文」矛盾；RECORD_STATS(4,919) 与快照 manifest(4,587) 两个规模数字并存无口径标注 |
| `src/app/records/page.tsx` + `components/records/` (4 文件) | 页面 `/records` | **真实语料冻结快照** | 现役 | 消费面主力。runtime fetch `/records-data/manifest.json`(57KB) + 28 个 creator 行文件(2.8MB) 懒加载。**count_only 门漏渲均值收益**（见问题 #2） |
| `src/app/kol-check/page.tsx` + `components/kol-check/` (4 文件) | 页面 `/kol-check` | **真实 F5 匿名化冻结** | 现役 / 孤儿入口 | 全站无任何链接指向，仅 sitemap + 直链可达。页头持续性横幅写得好，但命中率用自造 n<5 门判定，canonical 门下应为 `show_with_warning` |
| `src/app/demo/page.tsx` + `components/demo/` (6 文件) | 页面 `/demo` | **全虚构 fixture** | 演示 | 公开站最主要 CTA 落点。:488 印「胜率（历史记录）72.0% · n=2」——n=2 下 0.72 数学上不可能 |
| `src/app/training/page.tsx` | 页面 `/training` | 静态 | 现役 | 1083 行，2026-08-10 已做定位同步；dashboard 那份是它的陈旧子集 |
| `src/app/case/page.tsx` | 页面 `/case` | 静态 | 孤儿（半） | 受众 = bio+ML 导师；仅落地页正文一处内链（:636），不在 nav/footer。site 唯一带调色板字面量的文件（25 处 stone-） |
| `src/components/shared/primitives.tsx` | 站点共享原子 | — | 现役 | 站点级唯一真相源（DIRECTION_META / fmtRate / fmtSignedPct 用 U+2212 / TierBadge）；:152 `TIER_META[tier]` **无兜底**，而它正是唯一吃 runtime JSON 的一侧 |
| `src/components/landing/` (3 文件) | 站点骨架 | 静态 | 现役 | SiteHeader/SiteFooter + ProductFrame + PipelineStrip |
| `src/demo/types.ts` / `data.ts` | 演示类型与数据 | 虚构 | 演示 / 废弃语义 | `Kol.rating`(1-5 星) 与 `capability[]` 为 5 个人设全填了值，**零渲染消费者** |
| `src/demo/annotation-data.ts` | RLVR 打分器 | 虚构 | 演示 | 确定性 `scoreExtraction`（structure 硬门 + 三轴） |
| `src/demo/records/types.ts` | 快照 TS 镜像 | — | 现役 | `SignalClass` 只有 2 值（后端与 dashboard 是 3 值，缺 kol_statement）；不在 drift 守护范围 |
| `src/demo/kol-check/kol-radar.ts` (540 行) | 派生库 | 冻结快照 | 废弃语义 | 与 dashboard `lib/fixtures/kol-radar.ts` **437 行逐字节相同**，仅 1 行注释不同。`deriveCredibilityBoard`(0-99 信誉分)/`deriveActionableCalls` 是活代码；191 行零消费者 |
| `src/demo/kol-check/{fixtures,kol-snapshot,kol-l2,contracts-style}.ts` | 派生/契约切片 | 冻结快照 | 现役 | `contracts-style.ts` 是 contracts.ts 的手抄副本，`display_name` 可空性已与后端分叉 |
| `public/records-data/*.json` (29 文件, 2.8MB) | 数据源 | **真实冻结快照** | 现役 | as_of 2026-08-10，4,587 action / 2,740 settled；48 张卡中 34 张 count_only |
| `public/landing/` (11 文件, 3.6MB) + `public/og/` | 静态资源 | — | 现役 | 6 个文件与 dashboard 侧 **md5 逐字节相同**（同一批 PNG 存了两份） |
| `wrangler.jsonc` / `next.config.ts` / `DEPLOY.md` | 配置 | — | 现役 | assets-only Worker；`next.config.ts:7-8` 注释仍写已作废的 Cloudflare Pages 路线 |

### 2.4 跨 app 共享层（实为双份拷贝）

| 路径 | 类型 | 状态 | 备注 |
|---|---|---|---|
| `*/src/app/globals.css` | 设计令牌 | 现役 · **双份** | md5 均 `30707dcb...`，4800 bytes，逐字节相同；非 symlink 非共享包；site 侧自 2026-06-04 拷贝后没人动过。无任何漂移守护 |
| `*/src/lib/utils.ts` | `cn()` | 现役 · 双份 | md5 `d9837f38...`，6 行逐字节相同 |
| `components/landing/product-frame.tsx` | 装饰件 | 现役 · 双份 | md5 `7efccd44...` 逐字节相同 |
| `TradingStyleCard.tsx` (223 行 ×2) | 组件 | 现役 · 双份 | 仅差 4 行（注释 + import 源 + 一处折行） |
| `SectionHeader / DirectionTag / ConfidenceMeter / ReturnChip` | 排版原子 | 现役 · 3-6 份 | JSX 逐字节相同，仅类型参数与兜底有无不同 |
| 无 `tailwind.config.*` | 配置 | 现役 | Tailwind v4 CSS-first；`@theme inline` 只登记 5 项，其余 19 个 token 靠 arbitrary value（`--ink-soft` 在 dashboard 被引 280 次） |
| 无任何 webfont | 字体 | 现役 | 无 next/font、无 @font-face、无 woff/ttf。site 的 `--font-display-serif` 首选 Noto Serif CJK SC 在多数访客机器不存在，公开站标题静默降级 |

---

## 3. 消费面 vs 内部面

| 面 | 路由 | 数据真实度 | 效力门执行 | 可达性 |
|---|---|---|---|---|
| **对外消费面**（finer_site，已上线） | `/`、`/records`、`/kol-check`、`/demo`、`/training`、`/case` | `/records` 真实语料冻结快照（4,587 action）；`/kol-check` 真实 F5 匿名化（37 viewpoint / 29 settled）；`/demo` **全虚构**；其余静态文案 | `/records` 做了 count_only 降级但**均值收益漏在门外**；`/kol-check` 用自造 n<5 门；`/demo` 无门 | 全部可达，但 `/kol-check` 与 `/case` 事实上是导航孤儿 |
| **内部消费面**（dashboard CRD 三线） | `/discover`、`/ticker/[symbol]`、`/audit` | 全部真实 API | `/discover` 是全仓最严格的一处（`rg display_policy` 命中面仅 4 文件）；`/audit` 有显式 fixture 开关 | **零入站链接**，只能手敲 URL；且无 AppShell，进去后无法返回 |
| **内部工作台**（dashboard 主导航 8 项） | `/`、`/radar`、`/kol`、`/kol/compare`、`/backtest`、`/annotation`、`/training`、`/settings` | `/`、`/backtest`、`/annotation` 真实；`/radar`、`/kol` 真实数据但旧口径无门；`/kol/compare` **100% 编造**；`/settings` 部分编造；`/training` 静态陈旧副本 | 基本没有。`/radar` 用后端私有 n<5 门冒充；`/kol` 无 sufficiency 字段可用 | 全部在导航里 |
| **演示面**（dashboard `/demo/*` 6 条） | kol-radar / kol-snapshot / kol/[kolId] / ticker/[ticker] / audit/[viewpointId] / kol-rating | fixture（`kol-rating` 例外：打 live API 且 id 必 404） | 无 | `kol-radar` 是枢纽；`kol-snapshot`、`kol-rating` 零入站 |
| **孤儿层** | `/landing`、`/research`（传递性） | `/research` 真实数据、代码干净 | `research-canvas.tsx:104` 无门 | 不可达 |

**结论**：产品在「对外说什么」上已经收敛，在「内部展示什么」上没有。定位收敛的工作只在公开站做了——`pipeline-strip` 的「回测评分 vs 回测结算」、`kol-radar` 的「TOP EARNERS vs 跟单收益汇总」、`deriveTickerRotation` 的「标的兑现榜 vs 标的结算记录」三处分叉方向完全一致：**site 改了，dashboard 的拷贝停在转向前**。

---

## 4. 重点问题（按严重度）

### P0 — 违反已拍板红线，且用户可见

**#1 后端 `/api/opinions/stats/summary` 另开一条私有比率通道，绕过 CRD-2；主导航第 2 格直接消费**
`src/finer/api/routes/opinions.py:475-489` 用 `_CRED_PRIOR_K=4` / `_CRED_LOW_SAMPLE_N=5` 把命中率收缩成 0-99「信誉分」（已实测确认），:773-777 逐 KOL 发出 `hitRate/credibility/lowSample` **无任何 sufficiency**——而 `configs/significance.yaml:16-22` 的 canonical 门是 30/15，这里的 n<5 宽了 3-6 倍。前端 `components/kol-radar/CredibilityBoard.tsx:2` 自述「the product spine, KOL leaderboard ranked by derived 信誉分」，:111-120 渲染裸点估计 + 名次 + 金色进度条；同页 `EarningsRace.tsx` 是「TOP EARNERS」带排名重排动画。
→ **建议**：删 `_credibility_score`，改调 `get_significance_gate().assess()`，topKols 携带完整 SampleSufficiency；CredibilityBoard 去掉信誉分列与名次列、命中率并排 Wilson 区间 + TierBadge、默认序改已结算样本量。短期做不完就先从 `header.tsx:20` 摘掉 `/radar`。这是本轮唯一的**后端**红线问题。

**#2 公开站 `/records` 的 count_only 门只挡住命中率，「均值收益（历史）」在门外无条件渲染**
已实测确认：`src/finer_site/src/components/records/RecordCardWall.tsx:107-122` 的 `<dl>` 是 `CardRatioBlock` 的**兄弟节点**，无条件 `fmtSignedPct(card.mean_return)` 并 `returnColor()` 上红绿；`CreatorRecordView.tsx:209-218` 同型。manifest 里 34 张 count_only 卡中 24 张 mean_return 非空：KeyBanc settled=1 印 **+58.0%**、花旗板块观点 coverage 3.7% 印 +20.4%——这些卡自己的 `notes[0]` 就写着「样本不足，不展示比率，仅显示计数」。dashboard `app/discover/page.tsx:333-370` 是正确参照（均值/中位都在 `!countOnly` 内）。
→ **建议**：把均值收益搬进 `CardRatioBlock` 的过门分支，两处同改；加一条 fixture 断言「manifest 里任何 count_only 卡的渲染输出不得含 `%`」。这与 memory 里「门在缺信息时放行」完全同型。

**#3 `/kol/compare` 是纯硬编码假数据 + ★「最佳」标记，占据主导航一格**
`app/kol/compare/page.tsx:17-22` 写死四个 KOL 的分数/准确率/收益，`rg 'fetch|apiFetch'` = 0 网络调用；:51-56 `getBestKOL()` 逐指标选最大值，:203-222 给 best 上 `text-morningstar-red` 并追加 `<span>★</span>`。`header.tsx:21` 实测确认在导航里。同批假 KOL 也出现在 `/settings:20-24` 的 `mockKOLConfigs`（开关不落盘）。
→ **建议**：直接下线路由 + 摘导航项。若需横向对比，重建在 `/discover` 的口径上（只比「说过什么」：最新立场、覆盖重叠、新鲜度、已结算样本量，不出单一优劣分）。

**#4 `/kol/[id]` 把后端已删除或被门撤下的维度回填 0.0 渲染成条形图**
`src/finer/api/routes/kol.py:206-215` 明写「timeliness/depth/clarity 曾是硬编码常量，没有测量依据，已删除」，不过门时 `dimensions=[]`；但 `lib/adapters.ts:368-372` 把 dimScores 初始化为五个 0 再覆盖，`app/kol/[id]/page.tsx:272-296` 无条件渲染全部 5 项。后果：count_only 时整屏 5 个「0.0」条。同页 :182-190 的「最大收益 **+0.0%**」「平均持仓 **0 天**」来自 `adapters.ts:418-420` 硬编码常量（后端根本没这三个字段）。
→ **建议**：adapters 去掉全部 `?? 0` 与硬编码 0，改 nullable 传 null，页面按已有 null 分支留白。`KOLRatingCard.tsx:261/271` 已经是正确姿势（`dimensions.length > 0` 才渲染整节），照抄即可。

**#5 4,017 行 / 17 个文件从任何 Next 入口不可达**
`components/opinion-timeline/`(1,818 行)、`components/rlhf-review-panel/`(1,743 行)、`lib/mock-contracts.ts`(456 行)。全仓 rg 排除自身目录后零命中，无任何测试引用；唯一提及是两个 `/training` 页的散文句。叠加：`kol-rating-card/` 全族 1,589 行只挂在必然 404 的 `/demo/kol-rating` 上，`FocusAreas.tsx` 更是从未被 JSX 渲染（仅 barrel re-export 造成的可达性假阳性），而 2026-08-15 今天刚在这族上投入了契约根治工时。
→ **建议**：mock-contracts 无争议直删。rlhf-review-panel 需先定性 F6 复核的唯一实现（`components/annotation-workbench/` 2,945 行已在跑，第三套 `studio/annotation-workbench.tsx` 552 行挂首页——**三套并存只有两套有入口**）。kol-rating-card 全族随 `/demo/kol-rating` 一并删。

**#6 CRD 消费面三页零入站，旧口径页占满导航**
实测 `header.tsx:18-27` 八项为 `/ /radar /kol /kol/compare /backtest /annotation /training /settings`；sidebar 只补 `/radar /audit /settings`。**`/discover`（唯一全门页）、`/ticker`、`/ticker/[symbol]` 零 href**，`rg '/discover'` 全仓唯一命中是 `crd/primitives.tsx:2` 的注释。`/research` 唯一入站来自零入站的 `/landing`。同时 `/discover /ticker /audit /research` 都不套 AppShell，进去无导航可回。
→ **建议**：导航表加 `/discover` `/ticker` `/audit`，摘 `/kol/compare`；给 `/research` 一个真入口（否则删 `/landing` 时它彻底失联）；这四页一并套 AppShell。

**#7 公开站 `package.json` / `package-lock.json` 被 `.gitignore` 吞掉，fresh clone 无法构建部署**
根 `.gitignore:28` 的 `*.json` 命中两者，:29-33 的负向列表没有任何一条覆盖 finer_site 的 npm 清单。附加风险：dashboard 的 `package.json` 同样命中该规则，只是因为早于规则入库才幸存，一次 `git rm --cached` 就掉同一个坑。DEPLOY.md 已记录但未根治。
→ **建议**：补 `!src/finer_site/package.json`、`!src/finer_site/package-lock.json`、`!src/finer_dashboard/package.json` 三行并 `git add -f`。

### P1 — 双份实现已开始单侧分叉

**#8 `globals.css` 在两 app 逐字节双份，零漂移守护**
md5 均 `30707dcb...`（4800 bytes）。今天一致纯属 site 侧自 2026-06-04 拷贝后没人动过，dashboard 侧此后已有两次 token 改动。`scripts/check_contract_drift.py:35` 只指向 dashboard 的 `contracts.ts` 且只校验枚举值集，CSS 完全在守护外。下次改 `--chart-up` 公开站静默保持旧值。
→ **建议**：三选一写进 CLAUDE.md：构建期生成 + CI 校验 md5 / 抽 `packages/tokens` / 至少加一条 md5 相同断言。

**#9 同一红线两处手写，修复只落一侧**
- `deriveTickerRotation`：site `kol-snapshot.ts:209` 已改 `b.settledCount - a.settledCount`（docstring「Stable output order, not a ranking」），dashboard `lib/fixtures/kol-snapshot.ts:454` 仍 `b.avgReturn - a.avgReturn`（docstring 仍写「标的兑现榜…winners first」）。两文件其余部分逐字节相同，**唯一差异就是这一行排序**，而 dashboard 那份被 `/radar/kol/[kolId]` 的 live 路径渲染。
- `pipeline-strip.tsx`：唯一差异是 F8 的 `desc`，dashboard「回测**评分**」vs site「回测**结算**」。
- `kol-radar` 派生库：437 行逐字节相同，唯一分叉的那行注释恰是「收益榜 TOP EARNERS」vs「跟单收益汇总」。
→ **建议**：以 site 为准回流 dashboard；把这类跨 app 镜像文件列一张清单，改动须成对。

**#10 `fmtPct` 三处同名反语义 / `fmtSignedPct` 输出不一致**
`crd/primitives.tsx:20` = 无符号比率 + null 安全；`kol-snapshot/primitives.tsx:25` = **带「+」符号**的收益格式化且无 null 分支；site `kol-check/primitives.tsx:22` 是 `fmtSignedPct` 的别名。把命中率 0.462 传给带符号版会渲染成「+46.2%」——在这个产品里比率前的「+」会被读成超额。签名兼容，IDE 选错路径无任何类型报错。另 `fmtSignedPct` 负号字形（site U+2212 vs dashboard ASCII）与默认精度（1 vs 2）也不一致：同一个 -0.0268，site 渲染「−2.7%」、dashboard 渲染「-2.68%」，而两者展示的是同一批券商记录。
→ **建议**：比率用 `fmtRate`、收益用 `fmtSignedPct`，全仓禁用 `fmtPct` 这个名字；U+2212 与 digits=1 定为全仓约定写进 CLAUDE.md。

**#11 其余效力门与契约缺口**（合并同类）
- `GET /api/kol/list/enriched` 的 `KOLListItem`（`kol.py:445-462`）**无 sufficiency 字段**，单 KOL 端点却有——`/kol` 与 `/research` 只能印裸比率，且第三格印 `totalOpinions` 而非分母 `settled_opinions`。
- `KOLRatingCard` 只实现了 count_only 分支，`rg wilson|show_with_warning|tier` 在整个目录零命中——sufficiency 就在手上没用。
- 公开站 `/kol-check` 命中率 8/29（Wilson 95% 区间 14.7%–45.7%，宽 31pp）按 canonical 门属 `show_with_warning`，页面却用 `kol-radar.ts:219` 的 `LOW_SAMPLE_N=5` 判定 → 告警与区间双缺。
- 公开站 `/demo`（**最主要 CTA 落点**）印「胜率 72.0% · n=2」，而 n=2 只能取 0/0.5/1.0——0.72/0.51/0.58 都是编的，且 n 远低于 count_only 门。
- `/ticker/[symbol]` 的「方向一致度」无 n 下限，单信源标的会印 100%（性质上不是绩效比率，优先级最低，但 100% 会被读成「共识很强」）。
- `TierBadge` 两份：provisional 文案 dashboard「样本有限」vs site「临界样本」；**site 那份 `TIER_META[tier]` 无兜底**，而它恰是唯一吃 runtime 未校验 JSON 的一侧，未知 tier 直接 TypeError。

**#12 两条幽灵端点 + 两个后端地址真相源 + 零 error boundary**
- `GET /api/files/enrichment/{entity}` 后端不存在（`files.py` 只有 `@router.get("")` / `@router.post("")`），却有专门代理路由 + 两个调用点（`app/page.tsx:220`、`inspector-panel.tsx:96`），**两处都 catch 置空数组** → F2 文件夹下钻永远空列表且不报错。`DELETE /api/wechat/accounts/{id}` 同理。
- `next.config.ts:8` 硬编码 `http://localhost:8000` vs `api-proxy.ts:20` 认 `BACKEND_ORIGIN`：换后端地址时 `/discover /ticker /audit /backtest` 集体断，`/ /kol /annotation` 照常。
- 两 app **零 error boundary**（无 error.tsx/global-error.tsx/ErrorBoundary），叠加 `RecordsExplorer.tsx:72` 的 `manifest?.cards[signalClass]`（可选链在 manifest 处终止，cards 缺失即 render 期 TypeError，且不在 :63 的 catch 覆盖内）= **公开站白屏**。
- 后端 130 端点前端只消费 55 条（58% 从未调用）；`lineage.py:58` 的 `/{trade_action_id}` 遮蔽 :149 的 `/stats`，`GET /api/lineage/stats` 永远进不到 handler（因整个 router 零消费未被触发）。

### P2 — 卫生与一致性

- **色彩红线实质违反**：`kol-rating-card/DimensionScores.tsx:21-24` 是绿(#10b981)=好 → 红(#ef4444)=差 的西方梯度，与全站红涨绿跌正相反，且 #10b981 恰是 `--chart-down` 字面值，与走 `--chart-up` 的 `PerformanceTimeline` 同屏。site `demo/reward-meter.tsx:11` `var(--chart-up, #0f9b6c)` 回退值写反（红 token 回退绿），导致 chosen/rejected 两卡几乎同色、视觉区分失效。`kol-radar/EarningsRace.tsx:38` 私有 `returnColor` 把 0 涂成上涨红。
- **同名 token 撞值**：`--color-morningstar-red`(#e11b22) vs `--morningstar-red`(#9f1d22) —— CSS 文件一致，但 site 走工具类、dashboard 走 var，两 app 屏幕上的「晨星红」是两个颜色。`--color-success` 与 `--chart-down` 完全同值(#10b981)，`trace-status-badge.tsx` 的隔离只存在于命名。
- **调色板字面量**：dashboard 1,193 处 / 51 文件，site 25 处 / 1 文件（全在 `case/page.tsx`）。分布是架构性的：0 字面量的全是转向后重建的消费面（crd/audit/kol-snapshot/f8-charts/discover/ticker），1,193 处全集中在转向前的内部工作台（annotation-workbench ~313、data-source-config 132、rlhf-review-panel ~159）——**迁移可按目录切，不会碰消费面**。
- **词表分裂**：`risk_warning` 有四种中文标签（风险/风险提示/风险警示/提示风险）、`watchlist` 两种（观察/观望）、`review_required` 两种（需复核/待审核）、离场原因三套。用户在 `/discover` 和 `/audit` 之间切换会看到不同的词。`finance-format.ts:42` 的 `directionStyle` 只 case 了 bullish/bearish，其余全落「中性」是真缺陷。
- **契约守护盲区**：`check_contract_drift.py` 只校验枚举值集，不校验字段名/结构/端点存在性；扫描面只有 dashboard 的 `contracts.ts`，site 的 `contracts-style.ts`（`display_name` 可空性已与后端分叉）、`demo/records/types.ts`（`SignalClass` 缺 kol_statement）全部在外。
- **杂项**：`ErrorPanel.tsx:282` 把 `http://127.0.0.1:8000/...` 渲染成用户可点链接；`app/page.tsx:196` 残留 `console.log`；site ESLint 3 errors（`RecordsExplorer:27` 那条导致整个组件拿不到 React Compiler 优化）；`site/next.config.ts:7-8` 注释仍指向 DEPLOY.md 明令作废的 Cloudflare Pages 路线；5 个 create-next-app 样板 SVG + 668K 只被孤儿页引用的截图 + 6 个跨 app 逐字节重复的图片；site 下发它自己 0 引用的 `.research-panel`/`.container`。
- **排除项（已核实无问题）**：两 app 全仓零 TODO/FIXME/@deprecated、零 `@ts-ignore`、`tsc --noEmit` strict 双绿、`.toFixed` 逐条核验安全、`console` 卫生仅 1 处残留。**本轮问题不在「标了没做的事」，而在「已建好没接上」和「门在缺信息时放行」两类**——与 2026-08-13 勘察结论一致。

---

## 5. 建议的下一步（按投入产出排序）

**① 修 `/records` 的均值收益漏渲（0.5 小时）— 影响面：已上线公开站，最高优先**
`RecordCardWall.tsx:107-122` + `CreatorRecordView.tsx:209-218` 把均值收益移进过门分支。这是唯一一条「已经在对外印着 n=1 的 +58.0%」的问题，改动 2 处 JSX，参照实现就在 `discover/page.tsx:333-370`。改完加 fixture 断言。

**② 导航手术：加 3 页、摘 2 页（1 小时）— 影响面：内部工作台全体使用者**
`header.tsx:18-27` 加入 `/discover` `/ticker` `/audit`，摘除 `/kol/compare` 与 `/training`（后者改外链公开站）。同时给这三页套 AppShell。零新功能，但直接改变「用户默认看到哪套口径」——目前的默认是评分排行榜，正确的那三页要手敲 URL。

**③ 一次性删除死资产 ~7,700 行（2 小时）— 影响面：仅代码库，零渲染影响**
`opinion-timeline/`(1,818) + `rlhf-review-panel/`(1,743) + `mock-contracts.ts`(456) + `kol-rating-card/` 全族 + `/demo/kol-rating`(1,638) + `/landing` 全套(752 + 668K 图片) + `/demo/kol-snapshot`(17) + 5 个样板 SVG + site 的 `Kol.rating`/`capability` + site `kol-radar.ts` 的 191 行零消费导出。**唯一前置决策**：F6 人工复核的唯一实现是 `annotation-workbench/` 还是要给 rlhf-review-panel 补一个 `/review` 路由。删 `/landing` 前先给 `/research` 一个入口。

**④ 修后端 `/api/opinions/stats/summary` 的私有效力门（0.5-1 天）— 影响面：主导航第 2 格 + 其下 KOL 页，唯一的后端红线**
删 `_credibility_score`/`_CRED_LOW_SAMPLE_N`，改调 `get_significance_gate().assess()`，topKols 携带完整 SampleSufficiency；`CredibilityBoard` 与 `EarningsRace` 按 `/discover` 的姿态重渲（Wilson + TierBadge + BlankCell，默认序改样本量）。**做不完就先摘导航**——真实数据的旧口径页比假数据页更危险，它看起来是可信的。顺带把 `KOLListItem` 补 sufficiency、`adapters.ts` 的全部 `?? 0` 与三个硬编码 0 清掉。

**⑤ 建跨 app 共享层 + 守护（1-2 天）— 影响面：所有未来改动的复发率**
按风险从低到高：`globals.css`（构建期生成 + md5 CI 断言）→ `cn()`/`product-frame` → `DirectionTag`/`SectionHeader`/`ConfidenceMeter`/`TierBadge`/`ReturnChip` 五个排版原子（用 5 值超集类型 + 统一兜底）→ `TradingStyleCard`（223 行仅差 4 行）→ `gateRatio(sufficiency, value)` 统一放行函数。同时把 `check_contract_drift.py` 的扫描面从单文件改为文件列表（纳入 site 的两个 TS 镜像），并加一条端点存在性校验——本轮的两条幽灵端点、KOL 五维分、lineage 路由遮蔽全部逃过了它。

**⑥ 兜底与卫生（0.5 天）— 影响面：公开站可用性**
两 app 各加 `global-error.tsx`（dashboard 直接复用 `components/error-panel/`）；`RecordsExplorer.tsx:72` 补第二个可选链 + 最小形状断言；`next.config.ts` 的 rewrite 改读 `BACKEND_ORIGIN`；`ErrorPanel.tsx:282` 改相对路径；删 `page.tsx:196` 的 console.log；修 site 三条 ESLint error；改 `site/next.config.ts:7-8` 的作废注释。

---

**待核实项**：`/ticker/[symbol]` 的 `directional_agreement` 是否真需要补 sufficiency（它描述的是当前信源方向占比而非历史胜率，性质上不同于 CRD-2 针对的绩效比率，建议与后端 `/api/ticker/{s}/consensus` 一并定性）；`kol_statement` 口径是否会进入公开站快照（若会，site 的 `SignalClass` 2 值窄化将静默失配）。