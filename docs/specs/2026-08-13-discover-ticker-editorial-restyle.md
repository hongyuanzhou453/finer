# /discover + /ticker 版式改造（机构研报排版）

## 概述

把 dashboard 的两个消费面页面（`/discover`、`/ticker`、`/ticker/[symbol]`）从 Tailwind
默认调色板（zinc/amber/emerald/blue-600 字面量）迁到仓库既有的编辑式设计 token，并按
机构研报的版面纪律重排：报头横规、页头声明带、编号章节、booktabs 密排表、Wilson 区间条、
计数构成条。**数据口径与字段一个都没改**；新增的可视化全部是页面上已显示数字的再编码，
新增的聚合只有「同口径计数合计」（计数不是比率，不受 CRD-2 效力门约束）。

起因是评估「BW Research 式密排研报版面能否被 Finer 参考」。结论：版式可借，信息模型不可借
（方向判断 / 行动信号 / 强弱排名撞 2026-08-02 定位红线）。本轮只落地版式那一半。

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/components/crd/primitives.tsx` | 新增 | CRD 消费面共享排版原子（12 个组件 + 3 个格式化器） |
| `src/finer_dashboard/src/app/discover/page.tsx` | 重写 | 报头 + 页头三栏声明带 + 编号章节 + 密排记录卡 |
| `src/finer_dashboard/src/app/ticker/[symbol]/page.tsx` | 重写 | 报头 + 陈旧度状态条 + 三个编号章节 + booktabs 表 |
| `src/finer_dashboard/src/app/ticker/page.tsx` | 修改 | 入口页统一到同一套 token 与报头 |
| `src/finer_dashboard/src/components/kol-snapshot/primitives.tsx` | 修改 | `SectionHeader` 本地实现删除，改为再导出 crd 版（避免第三份拷贝） |

新增组件：`Masthead` / `SectionHeader` / `MetricTile` / `WilsonBar` / `CompositionRibbon` /
`SpreadBar` / `DirectionTag` / `TierBadge` / `Disclosure` / `NoteList` / `BlankCell` /
`StatusBanner` / `LoadingRow` / `ErrorPanel`。

## 架构影响

- **无 schema 变更、无 API 变更、无 contracts.ts 变更。** 消费的仍是
  `GET /api/creator/records?signal_class=`（`CreatorRecordCard[]`）与
  `GET /api/ticker/{symbol}/consensus`（`TickerConsensusView`），
  契约见 `src/finer_dashboard/src/lib/contracts.ts:1789-1876`。
- **F-stage 边界不变**：纯前端 presentation 层，无业务逻辑。
- `components/crd/` 成为 CRD 消费面（CRD-1 记录卡 / CRD-3 共识）的排版单一真相源；
  `kol-snapshot/primitives.tsx` 的 `SectionHeader` 已收编。宣传站
  `src/finer_site/src/components/{kol-check,records}/primitives.tsx` 仍各有一份副本，
  跨目录合并未在本轮范围内。

## 关键决策

1. **效力类图形一律中性墨色，不用红绿。** `WilsonBar` / `TierBadge` 用 accent-gold +
   foreground，不用 `--chart-up/-down`。命中率不是方向；给它上红绿等于用色彩通道说
   「这家更好」，而跨期持续性检验并不支持这个读法。方向类元素（`DirectionTag`、
   方向票构成条）保持中国惯例红涨绿跌。

   > 附带发现：BW Research 三张参考图用的是**西方口径**（流出/空头=红，流入/多头=绿），
   > 与本仓库 `--chart-up #e11b22` 正好相反。照抄配色会把语义倒过来。

2. **Wilson 区间条画在 0–100% 全域，不做自适应缩放。** 实测 14 张可读卡的
   `ci_width` 跨度是 9.4pt–42.4pt；全域固定轨道让「区间窄 vs 区间宽掉半个量程」的
   对比直接可见，且跨卡可比。自适应缩放会让每张卡的宽度含义不同。

3. **市场预期作为参照虚线画进区间条。** 这不是在做超额主张——恰恰相反，区间是否
   覆盖参照线一眼可读，把「样本不足以区分」变成图形事实。CLAUDE.md §3 要求
   「超额列强制并排 95% 区间」，此前只以文字并排。

4. **`mean_return` / `median_return` 不上色。** 这两列是跨卡可扫的绩效量；给它红绿
   等于给卡墙加了一个按业绩排序的视觉通道，与「默认序是样本量、不是排名」冲突。
   逐笔收益（`ReturnChip`，用于 /records 行级）不受此约束——那里红绿是那一笔的事实方向。

5. **修掉一个声明消失的缺陷。** 原 `/discover` 的预测性声明条件是
   `claim && !claim.permitted`——`claim` 为 `null` 时整块消失，而 `null` 恰恰意味着
   「该指标从没被检验过」，是最该出声明的情形。改为默认渲染，只在
   `claim?.permitted === true` 时撤下。这与 `src/finer/credibility/significance.py:40-43`
   记录的事故判例同源。

6. **构成条图例只标计数，不标百分比。** 几何形状已经表达份额；再写一个比率会让它
   看起来像一个受效力门约束的统计量。

7. **`count_only` 走显式留白格（虚线框），不填零。** 板块观点口径 24 张卡全部
   `count_only`，整屏零比率——这是系统主动说「我不知道」的展示面，不是需要藏起来的缺陷。

8. **修掉页面无法滚动的隐患。** `app/layout.tsx:20` 是 `flex h-full overflow-hidden`，
   页面根节点此前是普通 div，内容超出视口会被裁掉。三页根节点改为
   `finer-scrollbar h-full w-full overflow-y-auto`。

9. **口径开关用 `role="tablist"/"tab"`。** `.segmented-control` 的样式钩子是
   `button[aria-selected="true"]`，而 `role=button` 不支持 `aria-selected`
   （jsx-a11y 报警）。tab 角色既合法又保留样式。

## 验证结果

后端：`.venv/bin/python -m uvicorn finer.api.server:app --port 8000`（主仓，读
`data/projections.sqlite3`，`computed_at=2026-08-06`）。前端：worktree dev server。

```
npx tsc --noEmit          → exit 0，无输出
npm run lint              → 0 problems（改造前后均为 0，未新增告警）
npm run build             → ✓ Compiled successfully in 4.9s；23/23 static pages
```

浏览器实测（真实数据，非 fixture）：

| 场景 | 结果 |
|---|---|
| `/discover` 个股评级 | 24 信源 / 4,187 条 / 2,683 已结算 / 14 张可读比率；Wilson 条与参照线正确 |
| `/discover` 板块观点 | 24 张全 `count_only`；`document.body.innerText` 正则匹配百分数 → **null**（零比率泄漏） |
| `/ticker/NVDA` | 9 源全 bullish，`staleness=current`，目标价 205/284/350 USD，n=8（高盛无目标价显示 —） |
| `/ticker/AZN.L` | `staleness=stale`（234 天，红条），看多1/看空1 双色构成条，目标价 **留白格**（.L 镑/便士混存被整体排除） |
| `/ticker/005930.KS` | 排除计数可见：「单位可疑 0 条 · 币种不一 3 条」；表内 KRW/W/Won 三种原文写法照实呈现 |
| `/ticker/ZZZZ.XX` | ErrorPanel 正常，附代码写法提示 |
| 移动端 375×812 | `documentElement.scrollWidth === clientWidth`（无横向溢出）；表格在自身容器内横滚；章节标题单行不折 |

dev server 日志尾部：`GET /discover 200` × 3，`✓ Compiled`（早前日志里的 parse error 属
中间态，已修复）。

## 第二轮（2026-08-14）：/audit token 收敛 + 语义反转修复

第一轮遗留项 2/4 在本轮关闭。勘察结论先行：**/audit 已全在 token 上**（零 zinc/amber
字面量），它是三栏应用壳而非报告页，不需要 Masthead 重排；真正要收的是色彩语义缺陷。

### 变更清单（第二轮）

| 文件 | 说明 |
|---|---|
| `components/audit/primitives.tsx` | Tone 表全部落 token：green 由硬编码 `#0f9b6c` → `var(--chart-down)`；red → `var(--chart-up)`；新增 teal（风险提示，与 kol-snapshot 同词表）；`Meter` 填充 morningstar-red → accent-gold（置信度不是方向） |
| `components/audit/trace-status-badge.tsx` | canonical 徽章 → `--color-success` token（链路完整是成功语义，不是行情方向绿） |
| `components/audit/policy-trace-card.tsx` | 两处 `#0f9b6c`（layer 生效勾、「需人工复核：否」）→ success token |
| `components/audit/action-list.tsx` | risk_warning tone green → teal；回测收益列改用 `finance-format.returnToneClass`（顺带修正 0 归红——0 是未触发，应中性） |
| `components/audit/trace-timeline.tsx` | risk_warning tone green → teal |
| `components/kol-rating-card/PerformanceTimeline.tsx` | **西方口径反转修复**：看涨/盈利 emerald → `--chart-up` 红，看跌/亏损 red → `--chart-down` 绿；待验证 amber → accent-gold；中性 stone → ink-soft/surface-muted |
| `components/kol-rating-card/KOLRatingCard.tsx` | **修运行时崩溃**：`/api/kol/rating/{id}` 实测不返回 `badges`/`verifiedOpinions`/`accuracyRate`，TS 类型却声明必填 → `rating.badges.length` 白屏。类型对齐响应现实（三字段转可选），渲染守护；准确率缺失显示「—」留白，不填 0 |

### 关键决策（第二轮）

1. **五处 `#0f9b6c` 按语义分流，不是一刀切替换**：trace-status-badge 与
   policy-trace-card 的绿是「成功/通过」语义 → `--color-success`；action-list 的绿是
   「看空/下跌」方向语义 → `--chart-down`。两个 token 当前值恰好都是 #10b981，但语义
   通道分开后各自可独立演化。
2. **`DimensionScores`/`StarRating`/`FocusAreas` 刻意不动**：它们的红绿是「分数好坏」
   语义，而「评分卡」信息模型本身已被定位转向废掉（CRD-1 信誉分整体移除）。为废弃
   信息模型做 token 迁移是浪费；`PerformanceTimeline` 修是因为方向/盈亏反转是事实性
   错误。
3. **KOLRatingCard 的修法是让类型对齐后端现实**，不是 try/catch 或默认值填 0——
   准确率后端不给就显示「—」，0 是一个会被当真的数字。

### 验证（第二轮）

```
npx tsc --noEmit   → 0
npm run lint       → 0 problems
npm run build      → ✓ Compiled successfully；23/23
```

浏览器实测（真实数据）：/audit 看空 pill = rgb(16,185,129)（chart-down token 生效）、
Canonical 徽章 = success token、Meter 填充 = rgb(155,123,69)（accent-gold）、
看多 pill = rgb(225,27,34)；/demo/kol-rating 由白屏崩溃恢复为正常渲染，准确率显示
「—」。PerformanceTimeline 无活数据（后端 timeline 全空），其 token 类写法与 audit
Pill 同构、经同一构建验证。

## 第三轮（2026-08-14）：宣传站 primitives 副本合并

第一轮遗留项 1 在本轮关闭。前置：本 worktree 缺 finer_site 构建环境（根 `.gitignore`
的 `*.json` 吞掉 package.json），从主仓 `cp` 三个配置文件 + 物理拷贝 node_modules
（Turbopack 拒 symlink）；这些文件保持 untracked，不入 git。

### 变更清单（第三轮）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_site/src/components/shared/primitives.tsx` | 新增 | 站点级唯一真相源：`SiteDirection`（5 值超集）、`DIRECTION_META`、fmtRate / fmtSignedPct / fmtDate / fmtConfidence / returnColor、SectionHeader / DirectionTag / TierBadge / ConfidenceMeter |
| `src/finer_site/src/components/kol-check/primitives.tsx` | 重写为薄模块 | 共享原子再导出 + `fmtPct` 兼容别名（= fmtSignedPct）+ 领域件 ReturnChip（待回测/未触发措辞）；删除死导出 DirectionLegend / fmtMonthDay / DirectionMeta（全站零消费方） |
| `src/finer_site/src/components/records/primitives.tsx` | 重写为薄模块 | 共享原子再导出 + `DirectionChip` 兼容别名（= DirectionTag）+ 领域词表（signal class / 期限 / 动作 / 离场原因）+ SettleChip |
| `src/finer_site/src/demo/kol-check/kol-l2.ts` | 修改 | 第四份手写 `fmtPctSigned` 副本收编为共享 fmtSignedPct 的别名 import（叙事段的 "-17.1%" 即出自它） |

净变化：3 文件 43 insertions / 244 deletions + 新共享模块。

### 关键决策（第三轮）

1. **负号统一为 U+2212「−」**（records 既有约定胜出）：与「+」等宽，密排表格对得齐。
   kol-check 页负号从 ASCII 连字符迁到 U+2212 是本轮唯一的有意视觉变更。dashboard
   仍走 toFixed 的 ASCII（两 app 不同屏，跨 app 统一需 workspace 包，不在本轮）。
2. **DIRECTION_META 取 5 值超集**（kol-check 版），records 的 `RowDirection`（3 值）
   作为子集直接传入；`glyph` 字段随死导出一并删除（零消费方）。
3. **兼容别名而非改调用方**：`fmtPct` / `DirectionChip` 以 re-export 别名保留，5 个
   消费组件一行未改。DirectionChip 尺寸随共享 DirectionTag 从 px-1.5 变 px-2
   （+0.125rem，可接受的统一代价）。
4. **领域措辞留在领域文件**：ReturnChip（回测语境）、SettleChip、SIGNAL_CLASS_LABEL
   等词表不进 shared——共享层只放无语境原子。
5. **SectionHeader 顺带带上 dashboard 同款窄屏修复**（flex-wrap + whitespace-nowrap）。

### 验证（第三轮）

```
finer_site: npx tsc --noEmit → 0；npm run build → ✓ 11/11 static pages
```

浏览器实测（out/ 静态产物，port 4311）：
- `/kol-check`：全页正则扫描 ASCII 负号 `-d.d%` = **0 处**，U+2212 = 36 处
  （修 kol-l2 前残留 1 处 "-17.1%"，出自叙事段的第四份格式化器副本）；
  负收益 chip 计算色 rgb(16,185,129)=chart-down，正收益 rgb(225,27,34)=chart-up。
- `/records`：卡墙 + 下钻表（瑞银 670 行口径）渲染正常；DirectionChip 经共享
  DirectionTag 渲染，计算色/内边距符合预期；TierBadge 34 处；ASCII 负号 0 处。

## 第四轮（2026-08-15）：后端图表聚合 + /api/kol/rating 契约根治

第二轮遗留项 6/前端图表的后端前提在本轮落地。两条线，全部真实数据验证。

### A. 语料构成聚合（新图表的后端数据源）

**设计原则：只做计数聚合。** 计数不是比率，不受 CRD-2 效力门约束——这让全部
六类图表（月度活动/方向/市场/离场原因/期限档/窗口）无需新增任何 sufficiency
通道即可上线。schema 与 TS 层各有一道「疑似比率字段」防线
（`test_schema_has_no_ratio_fields` + contracts.ts 注释约定）。

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/schemas/credibility.py` | 新增 | `MonthlyActivityBucket` + `RecordCorpusAggregates`（纯计数 + notes） |
| `src/finer/credibility/aggregates.py` | 新增 | 唯一构造点；口径与 record_card 逐条对齐（superseded/空 creator 排除、signal_class 隔离、signal_clock_of 归月） |
| `src/finer/api/routes/creator_records.py` | 修改 | `GET /api/creator/records/aggregates?signal_class=`（TTL 120s 活算；**刻意不加投影表**——SQLite 表结构变更按规范需单独确认） |
| `tests/test_corpus_aggregates.py` | 新增 | 4 tests：计数/月度桶、排除口径对账、比率字段防线、空输入 |
| `contracts.ts` + `/discover` 02 区块 | 修改 | 月度双条（当月/已结算，防塌陷需列容器显式 h-full）、方向/期限/离场/市场四条构成带、notes 逐条展示 |

**对账验证（真实数据）**：broker_recommendation 口径 n_total=4,187 /
n_settled=2,683 / n_creators=24——与 /discover 卡墙页头合计**逐位一致**；
exit_reasons 1020/765/591/307 与站点快照实测分布一致；15 个月度桶，
2025-12 峰值 2,269（单月占 54%，notes 里声明这是入库节奏非行为节奏）。

### B. /api/kol/rating 契约根治

| 文件 | 说明 |
|---|---|
| `src/finer/api/routes/kol.py` | `rating: Dict[str, Any]` → 强类型 `KOLRatingSummary`（camelCase 镜像前端），新增 `settledOpinions` + 内嵌 `SampleSufficiency`；`_gated_summary` 统一放行逻辑 |
| 同上 | **删除两处编造**：action 路径的 30 天合成时间线（`(i%3)*0.2` 评分抖动 + 假收益倍数）与 timeliness/depth/clarity 硬编码维度分（3.5/3.0/3.5，无测量依据）；维度只保留数据依据轴且随门撤下；`_empty_rating` 不再返回五个 0 分维度 |
| 同上 | `TimelinePoint.rating` 转 Optional——时间线不得成为绕过 count_only 的旁路；真实净值曲线保留（PRT-2：曲线是记录不是承诺） |
| 同上 | `/list/enriched` 比率字段 Optional + `settled_opinions`；`last_active` 从 timeline[0]（旧假时间线的产物）改 timeline[-1] |
| `tests/test_kol_rating_contract.py` | 新增 5 tests：count_only 置空、sufficient 放行、空路径无编造、backtest 小样本门、backtest 达标样本 |
| `contracts.ts` | `KOLRatingResponse`/`KOLListItemRaw` 逐字段重镜像；`KOL`/`KOLDetail` 视图模型比率字段转 nullable |
| 6 个消费文件 | null 语义落地：排序 `?? -Infinity` 沉底、渲染「—」、compare 星标不落在 null 上；`/kol/[id]` 顺带修正准确率分母（settled 而非 total） |
| `KOLRatingCard.tsx` | 本地漂移类型全删，fetch 直接吃 canonical 契约 + 底部显式 adapter（dimensions 0-5→0-100、timeline 事件源改 recentOpinions——旧代码把净值点硬塞进事件组件渲染 undefined）；FocusAreas 改纯标签（后端只有代码列表，不喂零值编造「0% 准确率」）；count_only 横幅 |
| `RecentOpinions.tsx` | 页脚自算准确率 0 样本时 0% → null/「—」 |

**验证**：全量 `pytest tests/ -q` → **4,037 passed / 72 skipped**（含新 9 个 +
contract drift 守护）；tsc 0 错、lint 0 问题、build 23/23。live 实测
（worktree 代码 + 主仓数据经 data/ 子目录 symlink）：demo_001 与 trader_ji
（3 条）全字段 count_only 置空；enriched 列表 score/acc 为 null 但
settled 计数在场；`/kol` 页 93 处「—」、全页零个假 "0%"；`/demo/kol-rating`
从五个 0 分环 + 1 星「极差」变为「样本不足，仅显示计数」横幅。

**关键决策**：比率字段随门置空用 `None` 而非 0——0 是一个会被当真的数字；
这条贯穿后端 schema、adapter、六个渲染点与 RecentOpinions 页脚。评分卡
信息模型（overallRating/维度分）仍是废弃语义，本轮只做契约与诚实性收口，
整体下线归 C11。

## 第五轮（2026-08-15）：带比率的胜率切片（每片过效力门）

第四轮遗留项 8 落地：按市场 / 按月的胜率切片，**每一片强制内嵌
``SampleSufficiency``**——这是与第四轮计数聚合分模块的原因：``aggregates.py``
刻意不 import significance，``ratio_slices.py`` 刻意不允许任何比率绕过它。

### 变更清单（第五轮）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/schemas/credibility.py` | 新增 | `SLICE_DIMENSION_LITERAL` + `RatioSlice`（缺门构造即失败）+ `CorpusRatioSlices`（含 overall 参照片） |
| `src/finer/backtest/scorecard.py` | 修改 | 公开别名 `real_market_of` / `stats_for_group`——CRD 消费层复用同一套市场推导与分组统计，真相源不变 |
| `src/finer/credibility/ratio_slices.py` | 新增 | 唯一构造点；结算判定 = `is_scoreable`、win = return_pct>0、市场 = ticker 推导、月度 = signal clock；`metric=None`（切片从未做持续性检验，predictive permitted 恒 False） |
| `src/finer/credibility/aggregates.py` | 修改 | **市场计数改用 `real_market_of`**——第四轮用了存量标记，会复现 870 条国际股误标 US 的伪影（美股胜率 43.1%→47.8% 的那类） |
| `src/finer/api/routes/creator_records.py` | 修改 | `GET /api/creator/records/slices?signal_class=&dimension=market\|month`（TTL 活算；非法维度 422） |
| `scripts/check_contract_drift.py` | 修改 | REGISTRY 登记 `SliceDimension`（守护先红后绿，按设计工作） |
| `tests/test_ratio_slices.py` | 新增 | 7 tests：逐片带门、小样本 count_only、市场推导解毒、月度升序、口径隔离、缺门构造失败、非法维度 |
| `contracts.ts` + `/discover` 03 区块 | 修改 | `SliceRow`（count_only 只报计数；过门 = WilsonBar + 全口径参照虚线 + 均值收益并排）；卡墙顺位 02→04 |

### 关键决策（第五轮）

1. **参照线 = 全口径合并片，它自己也要过门**：overall 不过门就不画参照线
   （显示「合并样本不足，无参照线」）。参照的语义是「这片与全体的关系」，
   不是「这片好不好」。
2. **切片走 CRD-1 canonical 纪律**（值 + sufficiency 同发、前端按
   display_policy 把门），与记录卡同族一致；第四轮 kol.py 的后端置空是
   针对 legacy 面的加固，不改。
3. **市场维度必用 ticker 推导**——测试 `test_market_derived_from_ticker_not_stamp`
   钉死 0700.HK 误标 US 必须归 HK；顺带修正第四轮 aggregates 的同源伪影。
4. 月度切片大多 count_only 是**预期行为不是缺陷**（单月样本本来就少），
   notes 里明说——这正是效力门存在的意义的可视化。

### 验证（第五轮）

```
pytest tests/ -q  → 4,052 passed / 64 skipped / 0 failed
                    （补挂 F3/F4/F2 数据链接后，审计闭环 5 tests 与 F2 覆盖率
                     测试从 skip 转实跑通过；首轮 F2 测试的一次失败为新挂载
                     数据后的状态交互，复跑消失）
tsc / lint / build → 0 错 / 0 问题 / ✓
```

live 实测（真实数据，n=2,683 已结算）：

| 切片 | 实测 |
|---|---|
| 市场 30 片 | 美股 44.0%［41–47%］· 港股 26.8%［22–32%，明确低于参照］· 台股 65.4%［56–74%］· 17 片 count_only（DE/BE/NO/...） |
| 月度 15 片 | 5 片 count_only（2023-11 等）、2026-01 show_with_warning［29–71%］、2025-12 主体 46.2%［43–49%］ |
| 参照线 | 全口径合并 46.1%（n=2,683，show）两面板同源 |
| 板块口径 | 合并 45.6%（n=57，过门）、9 行 count_only |
| 非法维度 | 422 |

### 运维备注（symlink 数据环境的坑，验证期实录）

worktree 经 `data/` 子目录 symlink 借主仓数据时：**不要挂 `processed/`**——
`/api/stats` 会对缺语义摘要的 manifest 按需调 LLM，配合失效 key 变成
401 风暴（实测数千次/分钟）并饿死事件循环；readiness 探测也不要用
`/api/stats`。此外 `ln -sfn <dir> data` 在 data 已被服务端自动建目录后会把
链接落到 data/data——需按子目录逐个挂。

## 未解决项（更新后）

1. ~~宣传站 primitives 副本~~ → 第三轮已合并（含 kol-l2 的第四份暗副本）。
2. ~~PerformanceTimeline 西方口径~~ → 第二轮已修。
3. **`bg-morningstar-red` (#e11b22) 与 `var(--morningstar-red)` (#9f1d22) 同名不同值**，
   token 层需要收敛。涉及 ~40 文件的视觉回归，需要先拍板哪个红是 canonical，不宜顺手改。
4. ~~/audit 版式改造~~ → 勘察后判定不适用（应用壳形态正确），色彩语义已收敛。
5. 本轮不含任何新图表类型（直方图、发散条、月度序列）——那些需要后端新增聚合与
   `sufficiency`，属另一批工作。
6. ~~/api/kol/rating 契约漂移~~ → 第四轮已根治（强类型 + 效力门 + 删编造）。
7. ~~「平均收益 +0.0%」占位值~~ → 第四轮已修（门未过一律 null/留白）；评分卡
   信息模型整体下线仍归 C11。
8. ~~带比率的胜率切片~~ → 第五轮已落地（市场 + 月度两维，每片过门）。
   更多维度（按期限档、按方向的胜率）可按同一 `ratio_slices` 通道扩展，
   属增量而非新架构。
9. 语料构成聚合走活算 + TTL，未入投影表（SQLite 表结构变更需单独确认）；
   如聚合响应时延成为问题再提投影化。
