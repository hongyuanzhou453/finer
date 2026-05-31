# 前端打磨与宣传站建设 — 审阅报告

> 日期：2026-05-29
> 范围：仅 `src/finer_dashboard/`（前端），未触碰后端 / Pydantic schema / API 契约
> 作者：Claude Code（architect / frontend implementer）

## 1. 概述（Overview）

把 Finer OS 前端统一收敛到一套「晨星编辑风」设计系统，并新增两个对外可展示的 surface：对象中心的 **KOL 研究视图（`/research`）** 和 **通用展示/招聘向宣传站（`/landing`）**。同时把既有 `/kol`、回测台、主工作台、侧边栏的配色（统一为中国惯例红涨绿跌）与密度（硬边、紧凑、token 化）对齐到同一语言。全部改动限于前端，绑定既有真实 API，不引入 mock 数据。

## 2. 变更清单（Changes）

### 2.1 新增文件

| 文件 | 行数 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/lib/finance-format.ts` | 59 | app 级共享金融格式化/配色助手（中国惯例红涨绿跌） |
| `src/finer_dashboard/src/app/research/layout.tsx` | 7 | 研究视图独立全高滚动布局 |
| `src/finer_dashboard/src/app/research/page.tsx` | 238 | KOL 研究视图编排（对象中心三栏 + 移动端选择器） |
| `src/finer_dashboard/src/components/research/kol-object-rail.tsx` | 187 | 左栏 KOL 对象选择器 |
| `src/finer_dashboard/src/components/research/research-canvas.tsx` | 226 | 中栏研究画布（结论优先 + 复用 F8 收益曲线） |
| `src/finer_dashboard/src/components/research/provenance-rail.tsx` | 153 | 右栏能力维度 + 回测溯源 + 审计入口 |
| `src/finer_dashboard/src/components/research/format.ts` | 8 | re-export shim → `@/lib/finance-format` |
| `src/finer_dashboard/src/components/research/index.ts` | 3 | barrel 导出 |
| `src/finer_dashboard/src/app/landing/layout.tsx` | 19 | 宣传站独立布局 + SEO metadata |
| `src/finer_dashboard/src/app/landing/page.tsx` | 404 | 宣传站主页面（9 个分区，hybrid-landing） |
| `src/finer_dashboard/src/components/landing/product-frame.tsx` | 53 | 编辑风浏览器框（包真实截图，`next/image`） |
| `src/finer_dashboard/src/components/landing/pipeline-strip.tsx` | 45 | F0-F8 canonical 管线条 |
| `src/finer_dashboard/public/landing/research.png` | — | 真实截图素材（KOL 研究视图，1440×900） |
| `src/finer_dashboard/public/landing/backtest.png` | — | 真实截图素材（F8 回测审计，1440×1040） |
| `src/finer_dashboard/public/landing/workbench.png` | — | 真实截图素材（F0-F8 工作台，1440×900） |
| `.claude/launch.json` | — | Claude Preview 本地配置（已 gitignore，非提交项） |

新增前端代码合计约 **1402 行**。

### 2.2 修改文件（配色/密度对齐，共 9 文件，+142 / −175 行）

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/app/kol/page.tsx` | 修改 | 评分/收益配色翻转为红涨绿跌；删本地 `getScoreColor`/`getPlatformLabel`；`editorial-card` + `tabular-nums` + token 边框 |
| `src/finer_dashboard/src/app/kol/[id]/page.tsx` | 修改 | `directionStyle`/`returnToneClass`；删本地反向配色函数；统计卡密度收紧 |
| `src/finer_dashboard/src/app/kol/compare/page.tsx` | 修改 | avgReturn 配色翻转；best 高亮 绿→晨星红；对比表 token + `tabular-nums` |
| `src/finer_dashboard/src/app/backtest/page.tsx` | 修改 | totalReturn 绿涨→红涨；maxDrawdown 红→绿（下行带负号）；状态语义色保留；`editorial-card` |
| `src/finer_dashboard/src/app/kol/[id]/backtest/page.tsx` | 修改 | `bg-[#f3efe7]` → `bg-[var(--background)]` |
| `src/finer_dashboard/src/app/kol/[id]/backtest/[backtestId]/page.tsx` | 修改 | 错误红 `#a50032`→晨星红；硬编码 hex → token；导出按钮保留 hover |
| `src/finer_dashboard/src/components/f8-charts/kol-backtest-research.tsx` | 修改 | 蓝色头像 `#1f55af`→晨星红；修正 RiskReturn 注释（颜色描述写反）；灰 hex → token；MetricPercentile 绿→中性；保留 `chartColors` echarts hex |
| `src/finer_dashboard/src/app/page.tsx` | 修改 | 主工作台卡片网格/列表密度收紧（`min-h`、padding、gap、图标）；stone → token |
| `src/finer_dashboard/src/components/layout/sidebar.tsx` | 修改 | `rounded-2xl/xl`→`rounded-sm`；nav 按钮/卡片 padding 收紧；段间距压缩 |

## 3. 架构影响（Architecture Impact）

- **未改任何后端、Pydantic schema 或 API 契约**；`src/finer_dashboard/src/lib/contracts.ts` 未改动。
- **新增 2 个前端路由**：`GET /research`（对象中心 KOL 研究视图，static）、`GET /landing`（宣传站，static），均独立于 app 根工作台 `/`，不污染既有 IA。
- **数据绑定全部走既有真实 endpoint**（经 `lib/api-client.ts` + `lib/adapters.ts`）：
  - `GET /api/kol/list/enriched` → `KOLListItemRaw[]`
  - `GET /api/kol/rating/{kolId}` → `KOLRatingResponse`
  - `GET /api/backtest/results?kol_id=` → `BacktestSummary[]`
  - `GET /api/backtest/results/{backtestId}` → `BacktestResult`
  - 复用 `backtestResultToViewModel()` / `kolRatingToDetail()` / `kolListItemToKOL()` adapter
- **配色约定统一**：`src/lib/finance-format.ts` 成为 app 级单一真相源（红涨绿跌，对齐 `globals.css` 的 `--chart-up`/`--chart-down` token 与 `finer-financial-frontend-design` skill）。`components/research/format.ts` 退化为 re-export，避免下游 import 改动。
- **复用 F8 图表组件**：研究视图与回测台共用 `components/f8-charts/kol-backtest-research.tsx`（`CumulativeReturnResearch` 等），无重复实现。
- **设计系统收敛**：`/research`、`/kol/*`、`/backtest`、`/`（工作台）、sidebar、`/landing` 现共用一套——暖纸底、衬线标题、晨星红、`rounded-sm` 硬边、token 边框、`tabular-nums`。

## 4. 关键决策（Key Decisions）

1. **双视图 IA（新增而非替换）**：保留 F-stage 工作台（pipeline ops 用途），新增 KOL 对象中心研究视图（产品价值 G2「以 KOL 为中心轴的观点编年史」）。两份参考文档（OpenClue / 自治研究 OS）主张对象中心，但它们描述的是更「自治/活体」的产品形态，Finer 现状是冻结输入批处理，故只取 IA 原则，不照搬自治组件。
2. **KOL universe 合并策略**：`/api/kol/list/enriched` 当前返回空 `[]`，但 rating/backtest 数据真实存在。研究视图左栏取 `enriched 列表 ∪ 有回测的 KOL`（后者经 rating endpoint 水合），**不造任何占位数据**——视图能用现存真实数据渲染，且更稳健。
3. **配色统一为中国惯例（红涨绿跌）**：依据 `globals.css` 既有 token 与 skill 要求。旧 `/kol`、`/backtest`、f8-charts 原为西方反向（绿涨/蓝头像/`#a50032` 杂红），已全部翻转/对齐。状态语义色（completed=绿、failed=红、play=绿）属功能语义，**刻意保留**。
4. **宣传站内容纪律**：只演示后端真做得到的环节（F0-F8 + 回测），**不演示**自治/活体论点等未实现能力——避免把 Round 3 刚清除的 mock-as-real 反模式以「宣传话术」形式请回。
5. **真实截图当主视觉**：用 playwright CLI 捕获 `/research`、回测审计页、工作台为 PNG 落盘 `public/landing/`，而非抽象 3D blob / 紫蓝渐变 / HTML 仿制。
6. **密度纪律 vs 品牌层**：institutional-finance 的紧凑密度（硬边、tabular-nums、token 边框）应用于工作面；暖纸 + 衬线 + 晨星红的品牌气质保留——二者并存不冲突。

## 5. 验证结果（Verification）

所有验证在 `src/finer_dashboard/` 下执行：

| 命令 | 结果 |
|---|---|
| `npx tsc --noEmit` | 通过（无类型错误；新增路由后 dev 类型缓存刷新后无残留） |
| `npm run lint` | 通过，0 warning |
| `npm run build` | 通过；`○ /research`、`○ /landing` 均为静态产物 |
| 浏览器截图（Claude Preview + playwright CLI） | `/research`、`/kol/[id]`、回测审计页、工作台、`/landing` 在 desktop(1440) 与 mobile(390) 宽度均确认渲染、响应式、真实数据/截图、红涨绿跌正确 |
| `grep` 残留反向配色（`text-green-`/`getDirectionColor`/`getScoreColor`） | `/kol` 路由内 = 0（仅状态语义绿保留） |
| `grep` 残留硬编码 hex（除 echarts `chartColors`） | F8 surface 内 = 0 |

> 注：完整后端 `pytest tests/` 未在本轮重跑（本轮纯前端，红线：不修任何 failing test）。前端无单元测试框架，验证以 build + 类型 + 浏览器截图为准。

## 6. 未解决项（Open Issues）

### 后端数据（影响宣传截图可信度，非前端可修）
1. `GET /api/kol/list/enriched` 返回空 `[]`（前端已用合并策略兜底，根因在后端 KOL 注册/富化未填充）。
2. `GET /api/kol/rating/{id}` **非确定性**：同一 KOL 多次调用返回不同评分/观点数；`platform="Mock"`；年化收益把 2 个月窗口强行年化（如 +135%/+187%），数学真实但误导。**对外正式发布前必须修后端**，否则截图同屏出现不一致数字会穿帮。

### 前端遗留债（不阻塞，按需收尾）
3. `src/finer_dashboard/src/app/kol/compare/page.tsx` 仍用硬编码 mock 数据（`availableKOLs` 假 KOL），违反项目 no-mock 纪律；本轮只做配色，未 de-mock（需接 `listKOLs` + 对比端点）。
4. `src/finer_dashboard/src/components/kol-rating-card/*`（仅用于 `/demo/kol-rating`）仍西方反向配色（emerald=涨），未对齐——不在 `/kol` 路由内，本轮未动。
5. `src/finer_dashboard/src/components/layout/inspector-panel.tsx` 的 "SELECTED ASSET" 卡仍为较软的圆角卡样式，是工作台最后一个未收紧的「软」面。
6. 主工作台移动端三栏（Sidebar + 主区 + Inspector）不折叠，窄屏横向溢出——既有结构问题，非本轮密度改动引入。

### 决策类
7. `/landing` 现为独立路由。是否提升为公开门面（`/` 入口、app 移至 `/app` 或子域）是更大的 IA 决策，本轮未做。

### 工作树卫生
8. 当前工作树存在**并行 agent 的未提交后端改动**（`src/finer/extraction/`、`pipeline/`、多个 `tests/`、`docs/research/`、`docs/specs/2026-05-wx-channels-dependency-policy.md` 等），**非本轮所做**。提交前必须按 ownership 分离，勿一次性 `git add .`。
