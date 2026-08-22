# Dashboard 激活轮：接上已建好的，拔掉编造的数字

> 范围：`1729fa4f`（合并 main）之后的 6 个提交，33 文件 +940/−740。
> 分支 `claude/nervous-villani-7587cb`，已推送。

## 概述

一句话：**把三个建好却没有入口的界面接上，同时把「0-99 信誉分」这条私有
评分链路从全仓拔除**。两件事看似无关，实际同源——都是「已建好没接上」和
「门开在错位置」这两个反复出现的失效模式，也是本仓库前端资产台账
（`2026-08-15-frontend-asset-ledger.md`）判定的核心病症。

本轮没有新增任何产品概念。新增的三个路由消费的都是早已存在的后端端点，
删除的都是没有测量依据的数字。

## 变更清单

### A. 导航手术（`e2e0bd77`）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/components/layout/header.tsx` | 修改 | 加入 `/discover` `/ticker` `/audit`；摘除 `/kol/compare`；`/radar` 后移；移除装饰 tagline |
| `src/finer_dashboard/src/app/discover/layout.tsx` | 新增 | AppShell |
| `src/finer_dashboard/src/app/ticker/layout.tsx` | 新增 | AppShell（覆盖 `/ticker` 与 `/ticker/[symbol]`） |

**核实前提**：main 的 `0814fd31` 已把三页加进**首页侧边栏**，但侧边栏只挂在
`/`——从任何 AppShell 页面出发都走不到。`/audit` 不套 AppShell：它自带
全屏三栏布局与「返回工作台」，再套会双层顶栏。

### B. F6 复核台（`06cb2475`）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/api/routes/rlhf.py` | 修改 | `/pending` 数据源 legacy `L0_ingestion/extractions/` → canonical F5；`PendingActionItem` 改发面板所需的 camelCase 形状 |
| `src/finer_dashboard/src/app/review/{page,layout}.tsx` | 新增 | 落地页（飞轮状态四格）+ 打开抽屉 |
| `src/finer_dashboard/src/components/rlhf-review-panel/{RLHFReviewPanel,TickerReview,DirectionReview,ActionChainReview}.tsx` | 修改 | 置信度字段转可空，缺失渲染「—」「未提供」「未标注」 |
| `src/finer_dashboard/src/lib/mock-contracts.ts` | **删除** | 456 行，零引用、零文档提及、零 spec 依赖 |

### C. 下线 0-99 信誉分（`90f718bc` + `96d8af90`）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/api/routes/opinions.py` | 修改 | `topKols` 改携带完整 `SampleSufficiency`；删除 `credibility`/`lowSample`/`avgRating`；`_credibility_score` 与 `_CRED_PRIOR_K`/`_CRED_LOW_SAMPLE_N` 彻底删除；`_kol_credibility_map` → `_kol_settled_count_map`；默认序改已结算样本量 |
| `src/finer/timeline/stance_snapshot.py` | 修改 | 快照存 `settled` 而非 `credibility`；`score_change` → `record_change` |
| `src/finer_dashboard/src/components/kol-radar/{CredibilityBoard,ActionableCalls,ChangeFeed}.tsx` | 修改 | 去分数列与金色进度条；命中率过门才渲染且必与 95% 区间并排 |
| `src/finer_dashboard/src/components/kol-ticker/{TickerStanceTimeline,WhoWasRight}.tsx` | 修改 | 「信誉 NN」→「N 笔已结算」 |
| `src/finer_dashboard/src/lib/fixtures/{kol-radar,kol-ticker}.ts` | 修改 | `CredibilityRow` 去 `credibility`/`lowSample`，加 `wilsonLow/High`/`tier`/`ratiosPermitted`；fixture 阈值从私有 n<5 改 canonical 15；自带 Wilson 计算 |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 修改 | 映射服务端 sufficiency；缺 sufficiency 按**不放行**处理 |
| `tests/test_opinions_signal_isolation.py` `tests/test_stance_snapshot.py` | 修改 | 更新 4 条钉旧口径的断言 + 新增旧快照量纲守护 |

### D. 清编造零 + 设计令牌守护（`6906ffba`）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/lib/adapters.ts` | 修改 | 删 `maxReturn/minReturn/avgHoldingDays = 0` 与 `dimensionScores` 五槽补零 |
| `src/finer_dashboard/src/lib/contracts.ts` | 修改 | `KOLDetail.stats` 去三个不存在的字段；`dimensionScores` 固定五槽 → `Record<string, number>` |
| `src/finer_dashboard/src/app/kol/[id]/page.tsx` | 修改 | 两格编造数换成真计数；维度为空时明说 |
| `tests/test_design_token_parity.py` | 新增 | `globals.css` / `lib/utils.ts` 跨 app 逐字节相同 + 红涨绿跌取值守护 |

### E. `/timeline` 上线（`17c1fde1`）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/app/timeline/{page,layout}.tsx` | 新增 | 挂载 `OpinionTimeline` + 详情弹窗 |
| `src/finer_dashboard/src/components/opinion-timeline/{OpinionTimeline,TimelineNode,TimelineFilter,OpinionDetailModal}.tsx` | 修改 | 7 处裸查表加兜底；方向配色西方口径→中国惯例；置信度改中性墨阶；补 `signalClass` 类型与徽章 |
| `src/finer_dashboard/src/components/layout/header.tsx` | 修改 | 12 项溢出 → 主栏 8 项 +「更多」4 项 |

## 架构影响

- **无 schema 变更**，除 `stance_snapshot` 的持久化字段（`credibility` → `settled`，
  非数据库、无迁移脚本，见下方兼容策略）。
- **API 契约变更两处**，均已同步 `contracts.ts` 并经 `check_contract_drift.py` 守护：
  - `GET /api/opinions/stats/summary` 的 `topKols`：移除 `credibility`/`lowSample`/
    `avgRating`，新增 `wins`/`sufficiency`；
  - `GET /api/rlhf/pending`：`PendingActionItem` 由 8 个 snake_case 字段改为
    面板所需的 camelCase 形状（`originalText`/`rationale`/`actionChain` 等）。
- **F-stage 边界不变**。F6 的数据源从 legacy L0 目录改为 canonical F5，是
  修正而非跨层调用：`api/routes/rlhf.py` 经 `TradeActionRepository` 读取，
  与记分卡/记录卡同一条路径。
- **路由新增 3 条**：`/review`、`/timeline`，以及 `/discover` `/ticker` 的
  AppShell layout。

## 关键决策

### 1. 三次「挂路由」，三种不同的实际情况——每次都先核实

| 界面 | 实际缺什么 |
|---|---|
| `/discover` `/ticker` | 只缺全局导航入口与 AppShell（侧边栏入口 main 已加） |
| `/review` | **三层俱损**：后端数据源指向不存在的 `data/L0_ingestion/extractions/`（端点恒返空）、前后端契约从未对齐（`setItems(data.items)` 直接赋值，字段名全不匹配）、才轮到缺路由 |
| `/timeline` | 数据层是通的（裸 `TimelineData`、参数对得上、实测 4,919 条），但挂上后暴露 4 类从未运行过的缺陷 |

**教训**：「已建好没接上」不等于「只缺一根线」。台账基于代码可达性判定，
判不出数据源是否通、契约是否对齐。动手前必须实测端点。

### 2. 不编造缺失字段，但也不留永远的破折号

F5 只有整条抽取的 `confidence`，`ActionStep` 没有 confidence/status →
渲染「—」「未提供」「未标注」，不回填 0。

但 `/kol/[id]` 的「最大收益」「平均持仓」两格不同：后端**永远不会**提供
这三个字段（不是「暂时没有」）。留两个永久破折号会暗示数据在路上，所以
换成后端真有的计数（观点数 / 已结算 N/M）。**判据是「这个空缺会不会被
填上」**：会 → 留白；不会 → 换成真有的事实。

### 3. 信誉分：删概念而不是删事件

`score_change` 事件本身有价值（"这个信源的记录变了"），伪造的是它的**刻度**。
所以快照改存已结算样本量，事件语义随之变实：「信誉分 70 → 73」→
「已结算 12 → 15 笔」。

### 4. 旧快照的量纲陷阱

已落盘 5 个快照存的是 `credibility`（实测 `trader_ji=57`）。若新代码把它
当成「已结算 57 笔」与新快照的 12 相减，会凭空造出 **−58 笔的战绩暴跌**。
`diff_snapshots` 因此**只在两侧都有 `settled` 时才出事件**——缺基线不报，
首次部署后那次 diff 静默是正确行为。新增测试
`test_legacy_credibility_snapshot_emits_no_record_change` 钉死。

### 5. 效力门的两处阈值必须是同一处

`opinions.py` 的私有门是 `n<5`，canonical 门是 30/15
（`configs/significance.yaml`）——**宽了 3-6 倍，而松的那道恰恰是用户
看到的那道**。fixture 侧的 `deriveCredibilityBoard` 也从私有 n<5 改为
canonical 15，并自带 Wilson 计算（比率离开数据层必带区间）。

### 6. 导航分组的边界即产品表态

12 项平铺溢出后，不是继续挤而是分组。`/radar` 与 `/kol` 落在「更多」里
不是因为不重要，是因为它们未接效力门、是转向前的形态。

「更多」用原生 `<details>`（自带点击外部收起与键盘可达），且必须放在
`<nav>` **外面**——nav 的 `overflow-x-auto` 会裁掉绝对定位的下拉。

### 7. 跨 app 令牌守护判据取「逐字节相同」

刻意不做「语义等价」的宽松比较：一旦允许差异，就得维护一张「哪些差异是
允许的」清单，而那个清单会立刻开始腐烂。两份要么合并成共享包（正确终局），
要么严格同步。

## 验证结果

```
pytest tests/ -q                         → 4,086 passed / 65 skipped / 0 failed
scripts/check_contract_drift.py          → 34 mapped enums in sync
scripts/audit_trace_integrity.py         → 4,919/4,919 三向引用完整（100%）
dashboard: tsc --noEmit / lint / build   → 0 错 / 0 问题 / 25 页
site:      tsc --noEmit / lint / build   → 0 错 / 5 problems（与 main 基线逐条一致）/ 11 页
```

**新增测试 7 条，其中 3 条跑过探针**（确认在旧代码上会失败，不是永远绿的
测试）：

| 测试 | 探针结果 |
|---|---|
| `test_top_kols_only_counts_non_superseded_kol_actions`（改断言） | 旧后端 FAILED / 新后端 PASSED |
| `test_legacy_credibility_snapshot_emits_no_record_change`（新增） | 用真实旧快照端到端验证：旧→新 diff 出 0 个事件 |
| `test_mirrored_file_is_byte_identical`（新增） | 往 site 侧追加一行注释 → FAILED；还原 → PASSED |

**浏览器实测**（真实数据，非 fixture）：

| 页面 | 结果 |
|---|---|
| `/review` | 2,803 条真实待复核；打开面板渲染 ARTV 记录（原文/理由/1 步操作链），操作链显示「未标注 —」而非「草稿 0%」 |
| `/timeline` | 4,919 条；卡面标注「券商 · 板块观点」，看多为红；弹窗显示原文引用/作者巴克莱/操作链做多 |
| `/kol/kol_cat_lord_fire` | 四格「— / — / 5 / 5-of-5」，能力雷达显示说明而非五个 0 分环 |
| `/discover` `/ticker/NVDA` | 顶栏在位、当前项高亮、无横向溢出 |
| 导航 | 主栏 8 项无溢出；「更多」下拉完整不被裁 |

**合成数据验证效力门**（真实语料 100% 是券商研报，R6 下 `topKols` 恒空）：
40 结算/20 胜 → `hitRate=0.5`、`policy=show`、95% 区间 [0.352, 0.648]；
3 结算/3 胜 → `hitRate=None`、`count_only`。旧口径下后者会得 **95 分排榜首**。

## 未解决项

1. **红 token 同名不同值**：`bg-morningstar-red`(#e11b22) 与
   `var(--morningstar-red)`(#9f1d22)。site 走工具类、dashboard 走 var，
   两 app 屏幕上的「晨星红」是两个颜色。需先拍板哪个是 canonical，
   涉及约 40 文件的视觉回归，未动。
2. **`_is_credibility_scoreable` 名字有误导**：它是 R6 口径隔离谓词
   （判「能否进 KOL 统计」），与已删除的信誉分无关，功能正确。改名会动
   多处调用点与测试，本轮未做。
3. **`/kol` `/radar` 仍未接效力门**：`KOLListItem` 无 `sufficiency` 字段，
   两页只能印裸比率。已在导航中降级到「更多」，页面本身未改造——按 UI-1
   重做还是删除是产品决策。
4. **`/kol/compare` 路由仍在**：已摘出导航，四个 KOL 硬编码、零网络调用。
   路由本身的删除待确认。
5. **宣传站 `finer_site` 的 `demo/kol-check/kol-radar.ts`** 仍保留
   `score_change` 类型（注释已标「不再作评价口径渲染」），未跟随 dashboard
   一并清理——两 app 的 fixture 层是独立副本。
6. **`/timeline` 与 `/radar` 能力重叠**：前者按时间平铺、后者按信源聚合，
   共用同一批 F5 action。`/radar` 改造或下线后需重新评估是否仍需两个入口。
