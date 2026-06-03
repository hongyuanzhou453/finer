# Finer OS 宣传站 — 独立静态站 + 交互式 Demo 实施方案

> 状态：**规划中**（待用户确认后进入 Phase 1，本文档不含任何已执行的业务代码改动）
> 日期：2026-06-03
> 类型：前端 / 营销物料 / 独立部署
> 负责人：用户 + Claude Code

---

## 1. 概述（Overview）

把仓库内已有的高完成度 landing 页（`src/finer_dashboard/src/app/landing/`）抽离为一个**独立的纯静态宣传站**，复用其视觉资产与文案，新增一个**纯前端模拟的交互式 Demo**（参考 `agentsroom.dev/zh/try` 的 mock-UI 形态：可交互、但全部为演示数据、不连真实后端），最终部署到 **Cloudflare Pages**，绑定域名 **finer.t800.click**。

成果形态：一个可独立部署、零后端依赖、海内外可达的宣传 + 招聘 + 产品演示站。

---

## 2. 背景与现状（Context）

### 2.1 已有可复用资产
- **landing 页**：`src/finer_dashboard/src/app/landing/page.tsx`（593 行，10 段），设计语言成熟（晨星红 + 暖纸底 + 衬线大标题），完成度高，直接复用。
- **landing 组件**：`src/finer_dashboard/src/components/landing/product-frame.tsx`、`pipeline-strip.tsx`。
- **真实产品截图**：`src/finer_dashboard/public/landing/{research,backtest,workbench,review}.png`（1440 宽）。
- **品牌资产**：`docs/assets/logo.png`、`docs/assets/finer-social-preview.png`。
- **设计 token**：dashboard `globals.css` 内的 CSS 变量（`--morningstar-red`、`--table-border`、`--ink-soft`、`--surface-strong`、`--accent-gold` 等）+ TailwindCSS 4 配置。

### 2.2 现有 landing 不能直接上线的三个障碍
1. **它是 dashboard 内的路由，不是独立站**。CTA 全部指向 `/`、`/research`、`/backtest`（需后端的内部页）。
2. **它假设后端在跑**。`next.config.ts` 把 `/api/*` 反代到 `localhost:8000`，公网无此后端。
3. **截图与示例数据里有需统一脱敏的标识**（KOL handle、`reviewer_id` 等）。

### 2.3 Demo 形态参考
`agentsroom.dev/zh/try` = 纯前端模拟 UI：访客可切项目、选 agent、在终端输入并看到"回复"，但顶部明示"所有项目、智能体和回复均为模拟数据"。这与用户诉求一致："挂点真实体验，但不是真实后端运行，让用户理解操作流程。" 该形态与 Finer "可审计、不黑箱、不夸大" 的品牌调性高度契合——"演示数据"标注是品牌加分项而非减分项。

---

## 3. 架构决策（Key Decisions）

| # | 决策 | 理由 |
|---|---|---|
| D1 | **新建独立静态站**，不在 `finer_dashboard` 内改造 | dashboard 需连后端开发，且暴露整站到公网有数据/安全风险；解耦后两者独立演进，且不触碰 Round 4 的 `finer_dashboard/**` 红线 |
| D2 | 技术栈沿用 **Next.js static export**（`output: 'export'`） | 现有 landing 是 React/Next JSX，直接搬运最省力；产物为纯静态 HTML/JS/CSS，适配 Cloudflare Pages |
| D3 | 新目录 **`src/finer_site/`** | 与 `src/finer/`（后端）、`src/finer_dashboard/`（工作台）命名并列一致 |
| D4 | Demo 用 **纯前端 mock + fixtures**，零后端 | 满足"真实操作体验但不跑后端"；无 `/api` 依赖，可静态部署 |
| D5 | 示例 KOL 用 **虚构化名 persona** | 规避把真人与虚构评分/回测绑定的名誉与误导风险；延续现有 `trader_ji` 网络ID风格 |
| D6 | 部署 **Cloudflare Pages**，域名 **finer.t800.click** | 域名已在用户 Cloudflare 账户（状态"活动"，Free），nameserver 已就位，绑定子域一键完成；先全球可达，不背 ICP 备案 |

### 3.1 受众与访问地域
用户选择"海内外兼顾"。第一版上 Cloudflare Pages（全球 CDN，国内"能访问但速度一般"），**不做 ICP 备案**。若后续国内体验不达标，再单独评估国内云 + 备案或 Cloudflare 企业版中国网络——不阻塞当前发布。

---

## 4. 站点信息架构（Site Structure）

复用现有 10 段，关键改动两处：CTA 全部对外化 + 新增交互 Demo 入口。

| # | Section | 来源 | 改动 |
|---|---|---|---|
| 1 | 顶部导航 | 复用 | 「进入工作台」→「启动在线演示」；新增 GitHub 图标链 |
| 2 | Hero | 复用 | 主 CTA「查看 KOL 研究视图」→「启动在线演示」（指向 `/demo`）；次 CTA 保留「看回测证据」（页内锚点） |
| 3 | F0–F8 Pipeline strip | 复用 | 无 |
| 4 | **交互式 Demo 入口区** | **新增** | 宣传页中段放一个"启动在线演示"大卡片 + 一帧 demo 预览截图，点击进 `/demo` |
| 5 | F8 回测 money shot | 复用 | 无 |
| 6 | 四能力 grid | 复用 | 无 |
| 7 | AI · human-in-the-loop / RLHF | 复用 | `reviewer_id` 示例值脱敏 |
| 8 | Engineering / 招聘 | 复用 | 文末 CTA 指向邮箱 |
| 9 | Gallery | 复用 | 截图统一 persona（见 §6） |
| 10 | Join CTA | 复用 | 「体验研究视图/进入工作台」→「启动在线演示」+「联系我们（邮箱）」 |
| 11 | Footer | 复用 | 产品链接改为页内锚点 + GitHub + 邮箱；保留免责声明 |

### 4.1 对外 CTA 落点（已确认）
- **邮箱**：`kelipovanatalja453@gmail.com`（招聘/联系）
- **GitHub**：`https://github.com/kelipovanatalja453-bot/finer`
- **在线演示**：站内 `/demo`

---

## 5. 交互式 Demo 设计（核心新增）

### 5.1 形态
- 独立全屏路由 **`/demo`**（仿 dashboard 工作台外观的缩小版），宣传页中段卡片为入口。
- 顶部固定一条横幅：**「演示数据 · Sample data only · 不连接真实后端」**。
- 全部交互由**预置 fixtures + 前端状态机**驱动，无网络请求。

### 5.2 五项交互（第一版全做，已确认）
1. **F0→F8 流水线走查**：点任一 stage，右侧切换显示该阶段的预置产物（一条内容如何逐层变成结构化判断）。
2. **选示例 KOL → 研究视图**：评分卡、累计收益曲线、观点列表。
3. **TradeAction → 证据溯源高亮**（差异化核心）：点一条交易动作，高亮回溯到原文 EvidenceSpan，展示 `intent_id / policy_id / evidence_span_ids` 链路。
4. **回测曲线动画**：预置数据 + 入场动画，呈现累计收益/夏普/回撤/胜率。
5. **模拟 RLHF 反馈**：在 F6 面板提交一条评分/修正，看界面状态变化（演示"人在回路"），但仅前端状态，不落库。

### 5.3 Demo 数据架构
- fixtures 目录：`src/finer_site/src/demo/fixtures/*.json`。
- **优先**：本地起后端 + dashboard，抓取关键接口真实响应（研究视图、回测、F6 队列），脱敏后存为 fixtures，保证界面 1:1。
- **退化**：若后端环境不便，手工构造贴近真实 Pydantic schema 的 fixtures（字段名/类型与 `src/finer/schemas/` 对齐）。
- 类型对齐：fixtures 的 TS 类型引用/复刻 `src/finer_dashboard/src/lib/contracts.ts`，避免字段漂移。

---

## 6. 数据脱敏方案（Privacy）

### 6.1 Persona 映射（虚构化名，统一风格）
现有 `trader_ji`、`kol_cat_lord_fire` 本身已是虚构化名（不指向真人），可保留；新增 demo persona 与之统一：

| 用途 | handle | 中文昵称 | 风格 |
|---|---|---|---|
| 主示例 | `trader_ji` | 老纪 | 个股短线（沿用） |
| 价值 | `value_laozhang` | 价值老张 | 长线价值 |
| 趋势 | `trend_hunter_k` | 趋势猎手K | 动量/趋势 |
| 港股 | `hk_veteran` | 港股老兵 | 港股 |
| 赛道 | `sector_alpha` | 赛道阿尔法 | 行业轮动 |

> 以上为初版建议，可在实现前替换为用户偏好的化名。

### 6.2 其他字段
- `reviewer_id: analyst_zhang` → `reviewer_demo`（或「审核员A」）。
- 所有评分/收益/胜率数字：保留但全站「演示数据」标注，不暗示为真实战绩。

### 6.3 截图处理
- 推荐 Phase 2 准备 persona 示例数据后**重新截图**，保证截图与 demo 内 persona 全站一致。
- 现有 4 张截图作为兜底（其 handle 已是化名，合规），仅一致性略差。

---

## 7. 技术实现（Implementation）

### 7.1 目录结构（计划）
```
src/finer_site/
├── package.json              # 独立依赖（next/react/lucide/tailwind）
├── next.config.ts            # output: 'export'，无 rewrites
├── tsconfig.json
├── public/
│   ├── landing/{research,backtest,workbench,review}.png   # 从 dashboard 复制（或重截）
│   ├── og/finer-social-preview.png                        # 从 docs/assets 复制
│   └── favicon / logo
├── src/
│   ├── app/
│   │   ├── layout.tsx        # SEO metadata、字体、全局样式
│   │   ├── page.tsx          # 宣传主页（搬运 + 改造现有 landing）
│   │   ├── globals.css       # 搬运设计 token（CSS 变量）
│   │   └── demo/page.tsx     # 全屏 mock 工作台
│   ├── components/
│   │   ├── landing/{product-frame,pipeline-strip}.tsx     # 搬运
│   │   └── demo/*            # mock 工作台组件（新增）
│   ├── demo/fixtures/*.json  # 脱敏演示数据
│   └── lib/contracts.ts      # 复刻 dashboard 契约类型（demo 用）
```

### 7.2 关键配置
- `next.config.ts`：`output: 'export'`；**移除** `/api` rewrites（静态站无后端）。
- 内部链接：所有指向 dashboard 内部页的 `<Link>` 改为页内锚点、`/demo`、或外链。
- 设计 token：从 dashboard `globals.css` 抽取 landing 实际用到的 CSS 变量，搬到 `finer_site` 的 `globals.css`。

### 7.3 SEO / 元数据
- `metadata`：title、description、`openGraph`（`og:image` = social-preview.png、`og:url` = `https://finer.t800.click`）、`twitter:card`。
- `canonical` = `https://finer.t800.click`。
- `sitemap.xml`、`robots.txt`、`favicon`（用 logo.png 派生）。

### 7.4 构建产物
`npm run build` → `out/`（纯静态），即 Cloudflare Pages 的发布目录。

---

## 8. 部署方案（Deployment）

### 8.1 目标
Cloudflare Pages 托管 `out/`，绑定 **finer.t800.click**，自动 HTTPS。

### 8.2 谁做什么（红线清晰）
| 步骤 | 谁 | 说明 |
|---|---|---|
| 写代码 / static export 配置 / 本地 build | Claude | — |
| 创建 Cloudflare Pages 项目 | **用户** | 后台操作，账户权限 |
| 连接 GitHub repo 授权（若走 Git 集成） | **用户** | 不经过 Claude |
| 绑定自定义域名 finer.t800.click | **用户** | Pages 后台点选，**自动加 CNAME**，无需手填 DNS |
| API Token / Zone ID / 密码 | **不交给 Claude** | 红线；如走 CI 自动部署，用户在本地配环境变量 |

### 8.3 部署方式（二选一）
- **A. Git 集成（推荐）**：宣传站随 `finer` repo 一起；Pages 设 root directory = `src/finer_site`、build command = `npm run build`、output = `out`。push 即自动构建。
- **B. 手动 / wrangler**：本地 `npm run build` 后 `wrangler pages deploy out`（需用户本地配 `CLOUDFLARE_API_TOKEN`）。

---

## 9. 分期计划（Phasing）

| Phase | 内容 | 产出 | 谁验证 |
|---|---|---|---|
| **P1 静态站抽离** | 建 `finer_site`、搬运 landing、CTA 对外化、SEO、去后端依赖 | 可 `build` 的静态宣传站（无 demo） | 本地预览，全站无死链/无 localhost 引用 |
| **P2 交互 Demo** | persona fixtures、重截图、`/demo` mock 工作台、5 项交互、演示标注 | 完整可交互 demo | 本地走查 5 项交互 |
| **P3 部署上线** | build 产物、部署说明；用户建 Pages + 绑域名 | finer.t800.click 可访问 | HTTPS + og 预览正常 |

---

## 10. 验证计划（Verification）

```bash
cd src/finer_site
npm run build          # static export 成功，out/ 生成
npm run lint           # ESLint 通过
npx tsc --noEmit       # 类型检查（如配置）
npx serve out          # 本地预览，人工走查宣传页 + 5 项 demo 交互
```
- 检查项：无残留 `localhost:8000` / `/api` 依赖；无指向 dashboard 内部页的死链；无真人姓名；全站「演示数据」标注到位。
- 可选：Lighthouse（性能 / SEO / 可访问性）。

---

## 11. 边界 — 不做什么（Out of Scope / 红线）

- **不修改** `src/finer_dashboard/**`（Round 4 红线）与后端 `src/finer/**`。
- **不连真实后端、不暴露 `/api`、不暴露真实 KOL 数据**。
- **不引入** L0-L8 / V0-V6 旧命名（AGENTS.md 硬约束）。
- **不在 demo 把 mock 说成 real**（诚实原则，避免重蹈被清除的 mock-as-real 反模式）。
- **不碰** 用户的 Cloudflare 凭证 / DNS 账户 / 密钥。
- 第一版**不做** ICP 备案、不做国内云部署、不做中/英双语（英文版列为 future）。

---

## 12. 待确认 / Open Issues

1. **目录名** `src/finer_site/` 是否可接受（备选 `site/`、`apps/web/`）。
2. **Persona 化名** §6.1 是否采用，或替换为用户偏好的名字。
3. **Demo 数据来源**：抓真实响应脱敏（需本地跑后端） vs 手工构造 fixtures —— 取决于后端环境是否方便。
4. **部署方式**：Git 集成（自动） vs 手动 wrangler。
5. **英文版**：是否需要（当前规划中文版优先，英文 future）。
6. **截图**：是否重截以统一 persona（推荐重截）。

---

## 13. 关联文档

- `CLAUDE.md` §12 大规模任务文档化（本文档遵循其结构）
- `src/finer_dashboard/src/app/landing/page.tsx`（复用源）
- 参考：`https://agentsroom.dev/zh/try`（demo 形态）

---

## 14. Phase 1 实施记录（2026-06-03 · 已完成）

### 新建 `src/finer_site/`
- 配置：`package.json`、`next.config.ts`（`output: 'export'` + `images.unoptimized`）、`tsconfig.json`、`postcss.config.mjs`、`eslint.config.mjs`、`.gitignore`
- 设计 token：`src/app/globals.css`（原样搬运 dashboard，保留 `--morningstar-red` 双红值：`@theme` 亮红 `#e11b22` / `:root` 深红 `#9f1d22`）
- 工具：`src/lib/utils.ts`（`cn`）
- 组件：`src/components/landing/{product-frame,pipeline-strip}.tsx`（搬运）
- 页面：`src/app/layout.tsx`（SEO/OG/canonical/robots，`metadataBase = finer.t800.click`）、`page.tsx`（改造主页 + 新增 demo 入口区）、`demo/page.tsx`（占位页）
- SEO route：`src/app/sitemap.ts`、`robots.ts`；favicon `src/app/icon.png`
- 资产：`public/landing/*.png`（4）、`public/og/finer-social-preview.png`

### CTA 对外化
- 所有 dashboard 内部路由（`/`、`/research`、`/backtest`）→ `/demo` 或页内锚点
- GitHub：`github.com/kelipovanatalja453-bot/finer`；邮箱：`mailto:kelipovanatalja453@gmail.com`
- `Github` 品牌图标（lucide 1.8.0 已移除）→ 内联 GitHub SVG mark
- `reviewer_id: analyst_zhang` → `reviewer_demo`（脱敏）

### 验证
- `npm run build` → ✅ 6 路由全静态 export，`out/` 生成（index/demo/404/icon/robots/sitemap）
- `npm run lint` → ✅ 0 error / 0 warning
- 死链检查 → ✅ 无 dashboard 内部路由、无 `localhost:8000`（`/api/` 仅存于 RLHF 讲解文案）
- preview（:4311）→ ✅ 主页 1:1 还原、demo 入口区、`/demo` 占位页渲染正常
- SEO → ✅ `sitemap.xml`/`robots.txt`/`og` 均指向 `finer.t800.click`

### Phase 1 未覆盖（交给 Phase 2）
- 截图仍为 dashboard 旧截图（含 `trader_ji`/`kol_cat_lord_fire`），P2 统一 persona 后重截
- `/demo` 当前为占位页，P2 实现 5 项交互

---

## 15. Phase 2 实施记录（2026-06-03 · 已完成）

### 数据层（`src/demo/`）
- `types.ts` — 对齐真实 schema 字段名的 TS 类型（TradeAction / EvidenceSpan / ExecutionTiming / RLHFFeedback / Intent 枚举值取自 `src/finer/schemas/trade_action.py`）
- `data.ts` — 5 个脱敏 persona（老纪 `trader_ji` / 价值老张 / 趋势猎手K / 港股老兵 / 赛道阿尔法），各含评分 / 6 指标 / 累计收益序列 / 能力雷达 + 2 条 TradeAction（完整链路：intent + evidence + 四时钟 timing + backtest + rlhf）；`STAGE_DETAILS` 9 段 F0-F8 产物（固定样本：老纪茅台 600519）

### 组件（`src/components/demo/`）
- `return-chart.tsx` — 纯 SVG 累计收益曲线 + 沪深300 基准虚线 + draw-in 动画（无图表库；红涨绿跌）
- `pipeline-rail.tsx` — 可点击 F0-F8 流水线 + 阶段产物详情（受控）
- `demo-workbench.tsx` — 全屏三栏工作台（左 KOL / 中研究视图 / 右证据+RLHF）+ 状态管理 + 全部 5 项交互

### 5 项交互（逐一验证 working）
1. F0-F8 流水线走查（点 stage → 阶段产物详情，F5 验证）
2. 选 KOL（左栏 → 中栏研究视图 + 右栏证据联动切换，价值老张验证）
3. TradeAction 证据溯源（点 TA → 右栏原文高亮 + EvidenceSpan + canonical trace + 四时钟）
4. 回测曲线 draw-in 动画（切换 KOL 重绘）
5. 模拟 RLHF 反馈（评分 + is_correct + 提交 → 生成 RLHFFeedback JSON，DOM 验证 `recorded=true`）

### 截图统一
- `scripts/screenshot-demo.cjs`（复用 dashboard playwright + chromium）截真实 demo 工作台 → `public/landing/demo-workbench.png`
- 宣传页 demo 入口预览图改用该真图（"预览 = 真实 demo"）
- landing 其余截图（research/backtest/workbench/review）保留：均为合规化名，`trader_ji` 与 demo persona 一致

### 验证
- `npm run build` → ✅ 6 路由静态 export
- `npm run lint` → ✅ 0 error（`scripts/` 加入 ignore）
- preview（:4311）→ ✅ 5 项交互逐一点测通过

### 诚实性
- 全站「演示数据 · Sample data only · 不连接真实后端」标注
- RLHF 提交明示「演示中不会真正发送」，`reviewer_id = you_demo`
- persona 全为虚构化名、无真人；评分/收益均为示例

---

## 16. Phase 2.5 视觉与文案润色（2026-06-03 · 已完成）

### hero
- 标签「红涨绿跌 · 中国市场惯例」→「AI 抽取 · 人工裁决」（核心可信叙事上首屏）
- 右图 `research.png`（dashboard 真图、数据稀疏显空）→ `demo-hero.png`（demo 工作台全景，老纪）

### proof（F8 回测）
- 左图 `backtest.png`（`kol_cat_lord_fire`、稀疏）→ `demo-proof.png`（赛道阿尔法，曲线波动大 + 右栏证据链）

### demo 入口
- 预览图 → `demo-entry.png`（价值老张），与 hero / proof 错开 KOL，避免三处雷同

### Roadmap 区块（human-loop 区新增）
- 「模型微调尚未启动」单句 → 独立 Roadmap：水平**进度轴**（RLHFFeedback ✓ / DPO 导出 ✓ 已建成 → Prompt 工程 / 插件调用 / 模型微调 规划中，实线转虚线、实心红 vs 描边金）+ 3 张规划卡 + 诚实脚注
- 保留「已建成与未建成都说清楚」的诚实基调，规避画饼
- `scripts/screenshot-demo.cjs` 增加按 KOL 截图；新增 `scripts/shoot-element.cjs`

### 验证
- `build` ✅ / `lint` ✅ / preview ✅（hero 元素丰富、Roadmap 进度轴 + 卡片渲染正确）

### 未清理（待用户确认）
- `research.png` / `backtest.png` / `demo-workbench.png` 不再被引用，仍保留在 `public/landing/`（删除需用户确认）

---

## 17. GitHub README 优化（2026-06-03 · 已完成）

用最新 demo 视觉资产优化 GitHub 项目页（`README.md` + `README.en.md` 双语对称改 5 处）：
- 主图升级：hero `research.png` → `docs/assets/demo-hero.png`；回测 `backtest.png` → `demo-proof.png`（demo 工作台丰富图替换旧空旷图）；`review.png` / `workbench.png` 保留为真实产品佐证
- 新增「🌐 在线演示 / Live Demo」小节：5 项交互 + `demo-entry.png` + finer.t800.click 链接，标注演示数据·纯前端
- 新增「训练闭环 Roadmap」小节：✅ RLHFFeedback / DPO 导出 → 🔜 Prompt 工程 / 插件调用 / 模型微调，保留诚实基调
- badges 加 live demo；快捷导航加在线演示入口
- demo 图归集到 `docs/assets/`（README 资产独立，不耦合 `finer_site` 路径）

### 部署验证
- 线上 `finer-site.kelipovanatalja453.workers.dev`：首页（hero 新标签/demo 图/Roadmap）+ `/demo`（5 KOL/证据溯源/四时钟/RLHF）内容正确，无需改动

### 待用户操作
- `git push`（红线，用户执行）：需 commit `README.md` / `README.en.md` / `docs/assets/demo-*.png` 才在 GitHub 生效
- 绑定 `finer.t800.click` 自定义域名（否则 README 链接暂指向未绑定域名；暂不绑可改用 workers.dev）
- repo Settings → Social preview 上传 `docs/assets/finer-social-preview.png`
