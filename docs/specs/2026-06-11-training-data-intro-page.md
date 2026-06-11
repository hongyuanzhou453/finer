# 训练数据介绍页（/training）— 人工标注 · RLHF · DPO 叙事页

> 最后更新: 2026-06-11
> 状态: 已实现并验证（前端纯静态页 + 导航入口）
> 关联: [DPO 百炼训练线](2026-06-07-dpo-bailian-training-line.md)、[F6 RLHF→DPO 映射](2026-06-07-f6-rlhf-to-dpo-mapping.md)、[标注工作台](2026-06-10-annotation-workbench.md)

## 1. 概述（Overview）

在 finer_dashboard 新增介绍性子网页 `/training`，把「人工标注 → RLHF → DPO 训练数据」这条线讲清楚：三类人工标注任务、训练集与人工验证集为何严格分开、证据对齐的偏好原则、三项评测指标、以及百炼 DPO 训练线的真实进展。**纯静态叙事页**，不依赖后端，永远可渲染。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/app/training/page.tsx` | 新增 | 介绍页主体（server component，无 "use client"）：Hero / 三类标注 / 训练 vs 验证 / 偏好原则 / 两个环 / 三指标 / 数据流双轨 / 百炼现状 / CTA + 内置 `FlowTrack` 子组件 |
| `src/finer_dashboard/src/app/training/layout.tsx` | 新增 | 用 `AppShell` 包裹（含全局导航 Header），导出页面 metadata |
| `src/finer_dashboard/src/components/layout/header.tsx` | 修改 | 导航新增「训练数据」入口（`GraduationCap` 图标，置于「标注」与「设置」之间） |

## 3. 架构影响（Architecture Impact）

- **F-stage**：F+ Training Loop / F6 Review 的对外说明面，**不改 F0-F8 主链路、不碰任何 schema、不新增 API**。
- **数据来源**：纯静态，无 fetch；不调用 `/api/annotation/*` 或 `/api/rlhf/*`。所有结构与数字取自仓库内已落地的 spec / schema / 脚本，非运行时数据。
- **布局边界**：复用 `AppShell`（与 `/annotation` 一致），故带全局导航；视觉语言复用 `/landing` 的编辑风设计 token（`--ink-soft`、`--surface-strong`、`--table-border`、`--accent-gold`、`--grid-line`、`--shadow-soft`、`morningstar-red`），与营销站统一但运行在 dashboard 外壳内。
- **契约同步**：未涉及 Pydantic / `contracts.ts` 变更（无新数据结构）。

## 4. 关键决策（Key Decisions）

1. **独立入口 `/training` 而非 `/annotation` 子页**（用户选定）：`/annotation` 保持为标注工具，介绍页用按钮链入工具，职责清晰、互不干扰。
2. **纯静态叙事而非实时仪表盘**（用户选定）：对外/开源展示最稳，永远可渲染；代价是数字为文档既有事实而非运行时计数。
3. **诚实优先，命中项目「不编造数字」红线**：
   - `eval_compare --demo` 的提升数字是玩具数据，**本页不作为真实成绩展示**；微调前/后真实数字明确标注「留白，待用户百炼实跑回填」。
   - 「迭代 2」校准对比（committal 5→46、watchlist 56→8、0/150）如实标注为「校准器在真实数据上的行为对比，不是模型微调成绩」。
   - 百炼训练线阶段表用三态徽章（已就绪 / 待授权 / 待用户）区分已建成与未建成。
4. **训练集 vs 人工验证集单列对比**：直接回应用户诉求，并把「防自我循环」「防泄漏」两条红线显式成卡片。
5. **server component + 文本内花括号用 HTML 实体转义**（`&#123;`/`&#125;`），避免 JSX 把 `{creator}`、`{buy, sell, hold}` 当表达式解析。

## 5. 验证结果（Verification）

| 命令 / 检查 | 结果 |
|---|---|
| `cd src/finer_dashboard && npm run build` | ✅ 编译成功；TypeScript 0 error；`/training` 作为 `○ (Static)` 预渲染路由产出（17 页全部通过） |
| 实时 dev server SSR `curl :3000/training` | ✅ HTTP 200 · 141 KB；17/17 关键标题/内容命中；`nextjs__container_errors` / `Application error` / `Unhandled Runtime Error` 均为 0 |
| 花括号字面渲染 | ✅ `kol_profiles/notes/{creator}.jsonl`、`{buy, sell, hold} × {足, 不足} × {长, 短}` 正确显示 |
| 导航入口 | ✅ `href="/training"`「训练数据」已在 header 渲染（active 高亮走既有 `pathname.startsWith` 逻辑） |

> 说明：preview MCP 无法在同项目目录再起第二个 Next 16 dev server，且 :3000 上有用户手动启动的实例；未 kill 用户进程，改以 production build + 实时 SSR 抓取做功能验证。视觉验证可直接访问 `http://localhost:3000/training`。

## 6. 未解决项（Open Issues）

- 视觉回归仅靠 build + SSR 内容核验，未做截图/像素级比对（受同目录双 dev server 限制）；如需截图需临时接管 dev server。
- 静态数字会随训练线推进而过期（如 held-out 30 段、覆盖矩阵 ≥120、迭代 2 计数）；后续若数字变动需手动同步本页或改为实时拉取。
- 未加 `/training` 的端到端导航测试（项目前端当前无 e2e 测试基建）。
