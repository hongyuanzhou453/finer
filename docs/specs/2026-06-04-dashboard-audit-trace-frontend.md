# Dashboard 产品化 — 证据审计台 /audit（前端设计方案）

> 状态：**规划中**（待用户确认后进入实现，本文档不含已执行代码改动）
> 日期：2026-06-04
> 类型：前端 / dashboard 产品化 / 信息架构
> 范围：`src/finer_dashboard/**`（前端先行）+ 后端 API 契约交付物（不在本轮实现）
> 负责人：用户 + Claude Code

---

## 1. 概述（Overview）

把 marketing demo 已经验证过的"证据链 / canonical trace"形态**产品化、接真实数据**，在 dashboard 新建一个以 **TradeAction 为中心**的全屏视图 **`/audit`（证据审计台）**：点一条交易动作 → 完整展开 **F3 Intent → F4 Policy → F5 TradeAction** 三段链路 + F2 证据高亮 + 四时钟 ExecutionTiming。

这是 Finer "可审计、不黑箱" 在产品里的第一次真正兑现，也补齐当前最大的前端设计债务：**F3 Intent、F4 Policy 在产品里完全不可见**。

本轮采用**前端先行**：用对齐 Pydantic schema 的 fixtures 把视图做出来，同时产出后端需补的 canonical trace API 契约，后端按契约实现（不在本轮范围）。

---

## 2. 背景与现状诊断（Context）

### 2.1 当前 dashboard 是两套割裂的视角，都没有证据链

| 视角 | 落点 | 证据/溯源现状 |
|---|---|---|
| file-centric 流水线浏览器 | `/`（Sidebar 按 F-stage 切 + `AssetFile` 卡片网格 + InspectorPanel） | InspectorPanel 的 "Provenance Rail" 是**硬编码 6 步文案**（`components/layout/inspector-panel.tsx:39-46` 的 `provenanceSteps`），`buildEvidenceSummary` 按 type/tier 返回模板文案，**非真实链路** |
| KOL-centric 研究视图 | `/research`、`/kol/[id]`、`/backtest` | `components/research/provenance-rail.tsx` 只有能力维度 + 回测参数，**没有 intent→policy→evidence** |

### 2.2 五个缺口

| # | 缺口 | 证据 |
|---|---|---|
| C1 | **canonical trace 产品里完全不可见** | 全前端无 `intent_id`/`policy_id`/`evidence_span` 的展示（仅 `landing/page.tsx` 文案提到）；demo 验证过、真产品没有 |
| C2 | **F3 Intent 无契约、无视图** | `contracts.ts` 无 `NormalizedInvestmentIntent`（仅有 `PolicyMappedIntent`） |
| C3 | **F4 Policy 有契约、无视图** | `PolicyMappingResult`/`PolicyDecision`/`PolicyLayerTrace`/`PolicyRiskConstraints` 全套在 `contracts.ts:873-991`，**零展示** |
| C4 | InspectorPanel 溯源是占位 | 应（在 `/audit` 跑通后）回填真实 trace 入口 |
| C5 | **后端缺 canonical trace 查询 API** | 现有 `/api/lineage/{id}/trace`（`api/routes/lineage.py:90`）返回的是旧的 content/segment/event 血缘（`segment_ids`/`event_ids`），**不是 F3→F4→F5 链路**；前端根本没在用它（前端 `lineage` 全是 `NameLineage` 文件名别名） |

### 2.3 可直接复用的资产

- **demo-workbench 交互模式**（`finer_site/src/components/demo/demo-workbench.tsx`，已验证）：
  - `HighlightedSource`（原文按 EvidenceSpan 高亮，`indexOf` 定位 + hover 联动）
  - `EvidencePanel`（证据片段列表 + canonical trace 表 + 四时钟表）
- **demo 类型**（`finer_site/src/demo/types.ts`）：字段名已 mirror 真实 schema，`ExecutionTiming` / `EvidenceSpan` / `TradeAction` 可直接对齐迁移
- **前端已有 F4 Policy 全套类型**（`contracts.ts:873`）
- **晨星设计系统**：`globals.css` token（`--morningstar-red`、`--table-border`、`--ink-soft`、`--surface-strong`、`--accent-gold`、`--chart-up/peer`）+ 现有组件库

### 2.4 后端真实能力（已核对）

- canonical pipeline 已可运行：`extraction.py` 的 `run_canonical_extraction` → `F5_executed`，产出 `TradeAction.canonical_trace_status == "canonical"`，带 `intent_id`/`policy_id`/`evidence_span_ids`/`execution_timing`（四时钟）。
- 但**没有"按 trade_action_id 取 canonical TradeAction + 完整上游 trace"的查询端点**。这是 C5，也是本轮要为后端定义的契约。

---

## 3. 关键决策（Key Decisions）

| # | 决策 | 状态 | 理由 |
|---|---|---|---|
| D1 | 落点 = **新建 `/audit` 证据审计台**（TradeAction 为中心的独立全屏视图） | ✅ 用户确认 | 动线独立、不干扰现有工作台；直接产品化 demo-workbench 已验证的形态 |
| D2 | 数据策略 = **前端先行 + fixtures + 定义 API 契约** | ✅ 用户确认 | 不阻塞、不碰后端代码、符合 contract-first；fixtures 对齐 schema，后端 API 就绪后零成本切换 |
| D3 | 不做 UX spec 的"导航重构 + 概览仪表盘 + KOL 评价系统" | 建议 | KOL 评价组件已实现；那份 spec 用废弃 L0-L8 命名、部分过时；价值低于证据链 |
| D4 | `/audit` 中栏做 **F3→F4→F5 三段链路展开**，而非只展示 id 链 | 建议 | demo 只展示 `intent_id`/`policy_id`（id 链）；产品要展开 Policy 的 `layer_traces`（"为什么这条 Intent 变成了这个 Action"），这是产品比 demo 更深的地方 |
| D5 | fixtures 在 dashboard 内独立一份（不跨 repo 复用 finer_site demo fixtures） | 建议 | finer_site 是独立静态站；dashboard 应有自己对齐 schema 的 fixtures，避免跨目录耦合 |

---

## 4. `/audit` 信息架构与页面设计

### 4.1 三栏布局（wireframe）

```
┌─ Top bar ────────────────────────────────────────────────────────────────┐
│ Finer OS / Audit Trace   [trace_status: canonical ▾] [KOL ▾] [标的 ▾]  ⌕  │  ← fixtures 模式显示 "Sample data" 标识
├──────────────┬───────────────────────────────────────┬────────────────────┤
│ 左：动作清单  │ 中：F3→F4→F5 链路时间线（核心）         │ 右：证据 + 四时钟    │
│              │                                        │                    │
│ [TradeAction]│  ● F3 INTENT                           │ 原文 source        │
│  600519 看多 │    actionability / direction /         │  ┌──────────────┐  │
│  canonical✓  │    conviction / position_delta_hint /  │  │「茅台回调到位 │  │
│ ───────────  │    time_horizon / ambiguity_flags      │  │ ...」高亮      │  │
│ [TradeAction]│    evidence_span_ids ───────────┐      │  └──────────────┘  │
│  000858 加仓 │  │                               │      │                    │
│  partial⚠    │  ● F4 POLICY                     │      │ EvidenceSpan 列表  │
│ ───────────  │    action_hint / sizing / holding│ hover│  es-1 [12,28] ...  │
│ [TradeAction]│    layer_traces（逐层 applied?    │ ◀──┼─ es-2 [40,55] ...  │
│  ...         │      + reason + modifications）   │      │                    │
│              │    decisions / risk_constraints   │      │ 四时钟 ExecutionTiming│
│ 筛选/排序     │    mapping_rationale              │      │  intent_published  │
│              │  ● F5 TRADEACTION                 │      │  intent_effective  │
│              │    action_chain（逐步 trigger）   │      │  action_decision   │
│              │    canonical_trace_status 徽章    │      │  action_executable │
│              │    [查看回测审计 →]               │      │  session @ publish │
└──────────────┴───────────────────────────────────────┴────────────────────┘
```

### 4.2 交互流

1. **进入** `/audit`：左栏加载 TradeAction 列表（fixtures），默认选中第一条。
2. **选动作**：中栏渲染该动作的 F3→F4→F5 三段；右栏渲染原文高亮 + 证据列表 + 四时钟。
3. **证据联动**：hover 中栏 F3 的 `evidence_span_ids` 或右栏证据片段 → 原文对应高亮加深（复用 demo 的 `activeSpanId` 机制）。
4. **筛选**：顶部按 `trace_status`（canonical / partial / non_canonical）、KOL、标的过滤左栏。
5. **链路完整性**：`non_canonical` 动作显式标注"缺失上游"（哪一段断裂），不隐藏——延续诚实原则。
6. **跳转**：F5 段提供"查看完整回测审计"链到现有 `/kol/[id]/backtest/[backtestId]`。

### 4.3 为什么是 TradeAction 为中心

TradeAction 是唯一同时持有 `intent_id` + `policy_id` + `evidence_span_ids` + `execution_timing` 的实体（`canonical_trace_status` 由此四者自动校验）。以它为锚，整条链路可一次性展开，且能直接暴露"链路是否断裂"——这正是审计的核心。

---

## 5. 组件设计

### 5.1 新建（`src/finer_dashboard/src/components/audit/`）

| 组件 | 职责 | 复用来源 |
|---|---|---|
| `trace-timeline.tsx` | F3→F4→F5 三段纵向链路容器（中栏核心） | 新建 |
| `intent-card.tsx` | F3 `NormalizedInvestmentIntent` 展示 | 新建（字段见 §6.1） |
| `policy-trace-card.tsx` | F4 `PolicyMappingResult`：`layer_traces` 逐层 + `decisions` + `risk_constraints` + `mapping_rationale` | 新建（契约已在 `contracts.ts:911`） |
| `evidence-source.tsx` | 原文高亮 + `EvidenceSpan` 列表 + hover 联动 | **移植** demo `HighlightedSource` + `EvidencePanel` 上半 |
| `execution-clocks.tsx` | 四时钟 `ExecutionTiming` + market session | **移植** demo `EvidencePanel` 四时钟段 |
| `action-list.tsx` | 左栏 TradeAction 列表 + 筛选/排序 | 参考 demo `KolList` + 现有卡片样式 |
| `trace-status-badge.tsx` | `canonical` / `partial` / `non_canonical` 徽章 | 新建（绿/金/灰） |

### 5.2 数据层 / 页面（`src/finer_dashboard/src/`）

| 文件 | 职责 |
|---|---|
| `app/audit/page.tsx` | 三栏组装 + 状态机（选中动作、activeSpanId、筛选） |
| `lib/audit-api.ts` | 数据层抽象：`getActions()` / `getTraceBundle(id)`，内部按 `NEXT_PUBLIC_AUDIT_USE_FIXTURES` 在 fixtures 与真实 `apiFetch` 间切换 |
| `lib/fixtures/audit-trace.ts` | 对齐 schema 的 fixtures（≥3 条：1 canonical 完整、1 partial 缺 F4、1 non_canonical legacy） |

### 5.3 设计语言

严格沿用晨星 token：红涨绿跌（`--chart-up` / `#0f9b6c`）、`--morningstar-red` 主色、`--accent-gold` 用于 `partial`/`watch`、衬线大标题 + 等宽字体展示 id/字段。与 demo-workbench 视觉一致（demo 本就抽自 dashboard token）。

---

## 6. 数据契约（前端）

### 6.1 `contracts.ts` 补充 F3 Intent 类型（对齐 `schemas/investment_intent.py`）

```typescript
// F3 Intent enums（取自 investment_intent.py:32-80）
export type IntentTargetType = "stock" | "sector" | "index" | "macro" | "commodity" | "crypto" | "unknown";
export type IntentDirection = "bullish" | "bearish" | "neutral" | "mixed" | "unknown";
export type IntentActionability = "opinion" | "watch" | "explicit_action" | "review_required";
export type PositionDeltaHint = "open" | "add" | "reduce" | "hold" | "exit" | "none" | "unknown";
export type IntentRiskPreference = "aggressive" | "balanced" | "conservative" | "unknown";
export type IntentTimeHorizon = "intraday" | "short_term" | "medium_term" | "long_term" | "unknown";

export type NormalizedInvestmentIntent = {
  intent_id: string;
  schema_version: string;
  envelope_id: string;
  block_ids: string[];
  creator_id?: string;
  target_type: IntentTargetType;
  target_name: string;
  target_symbol?: string;
  market?: string;
  direction: IntentDirection;
  actionability: IntentActionability;
  position_delta_hint: PositionDeltaHint;
  conviction: number;           // 0-1
  sentiment_score?: number;     // -1..1
  risk_preference_hint: IntentRiskPreference;
  time_horizon_hint: IntentTimeHorizon;
  temporal_anchor_ids: string[];
  evidence_span_ids: string[];
  ambiguity_flags: string[];
  confidence: number;           // 0-1
  metadata: Record<string, unknown>;
  created_at: string;
};
```

### 6.2 `contracts.ts` 新增 trace bundle 聚合类型

```typescript
/** F1/F0 原文上下文（审计高亮所需的最小子集） */
export type EnvelopeContext = {
  envelope_id: string;
  source_text: string;
  source_published_at?: string;
  creator_id?: string;
  kol_id?: string;
};

/** 一次性返回整条 F0→F5 链路的审计包 */
export type AuditTraceBundle = {
  trade_action: TradeAction & TradeActionTrace & { execution_timing: ExecutionTiming };
  intent: NormalizedInvestmentIntent | null;     // null = 链路在 F3 断裂
  policy: PolicyMappingResult | null;            // null = 链路在 F4 断裂
  evidence_spans: EvidenceSpan[];                // F2
  envelope: EnvelopeContext;                     // F1/F0 原文
};
```

> `TradeAction` / `ExecutionTiming` / `EvidenceSpan` 若 `contracts.ts` 现无完整定义，从 `finer_site/src/demo/types.ts` 迁移对齐版本（字段已 mirror 后端）。

### 6.3 fixtures 设计（`lib/fixtures/audit-trace.ts`）

- 至少 3 条 `AuditTraceBundle`，覆盖三种 `canonical_trace_status`。
- `canonical` 样本：复用 demo 的"老纪/茅台 600519"链路，但 **F4 Policy 用真实结构**（`layer_traces` 至少 GlobalBasePolicy 一层，含 `applied`/`reason`/`modifications`；`decisions` 1-2 条；`risk_constraints` 完整）。
- `partial` 样本：`policy = null`，`canonical_trace_status = "partial"`，UI 显式标注"F4 Policy 缺失"。
- `non_canonical` 样本：`intent = null` + `policy = null`（legacy 直提），标注"未经 F3/F4，证据链不完整"。

---

## 7. 后端 API 契约交付物（本轮只定义，不实现）

> 给后端的明确契约。与现有 `/api/lineage/*`（legacy content/segment/event 血缘）**区分开**，建议挂在 `/api/audit/*` 或 `extraction.py` 下。
>
> **可执行任务卡（后端 Agent 冷启动）见 `docs/specs/2026-06-04-audit-trace-backend-api-task.md`** —— 含数据源、bundle 组装链路、字段派生、evidence 缺口处理、error envelope、注册与验收 DoD。

### 7.1 `GET /api/audit/actions`

列出 canonical TradeAction 摘要（左栏）。

- Query: `kol_id?`, `ticker?`, `trace_status?` (`canonical|partial|non_canonical`), `validation_status?`, `limit?`, `offset?`
- Resp: `{ ok: true, data: { actions: TradeActionSummary[], total: number } }`
- `TradeActionSummary` = `{ trade_action_id, ticker, company_name, direction, summary, canonical_trace_status, validation_status, kol_id, created_at, backtest_return_pct? }`
- 数据源：`F5_executed` 目录扫描 + 索引（懒加载 + TTL 缓存，遵循 manifest 索引约定）。

### 7.2 `GET /api/audit/actions/{trade_action_id}/trace`

一次性返回整条链（中栏 + 右栏），结构 = §6.2 `AuditTraceBundle`。

- Resp: `{ ok: true, data: AuditTraceBundle }`
- 错误用 canonical error envelope（`request_id`/`stage`/`operation`/`retryable`/`fix_hint`，见 `src/finer/errors/`）。
- `stage` 应能指出断裂点（如 `"F4_policy"` when policy missing）。
- details 禁止出现 token/secret/password/cookie/authorization/api_key。

> 后端实现要点（供参考，不在本轮）：trade_action_id → 读 F5 → 按 `intent_id` 读 F3、`policy_id` 读 F4、`evidence_span_ids` 读 F2、`envelope_id` 读 F1 原文，组装为 bundle。

---

## 8. 分期计划（Phasing）

| Phase | 内容 | 产出 | 验证 |
|---|---|---|---|
| **P1 契约层** | 补 `contracts.ts`（§6.1/6.2）+ 本 spec §7 API 契约定稿 | 类型 + 契约 | `tsc --noEmit` |
| **P2 组件** | 迁移 demo 的 evidence/clocks；新建 intent-card / policy-trace-card / trace-timeline / action-list / badge；fixtures | 组件库 + fixtures | Storybook 式手测 / build |
| **P3 页面组装** | `app/audit/page.tsx` 三栏 + 状态机 + 筛选 + 证据联动 + fixtures 模式标识 | 可走查的 `/audit` | preview 走查全交互 |
| **P4 接后端** | `lib/audit-api.ts` 按 flag 切真实 `apiFetch`（待后端 §7 就绪） | 端到端真实数据 | 真实数据走查 |
| **P5 回填** | InspectorPanel / KOL 视图 加"在审计台查看"入口（C4） | 动线收口 | preview |

> P1-P3 为本轮前端范围；P4 依赖后端；P5 可选收尾。

---

## 9. 验证计划（Verification）

```bash
cd src/finer_dashboard
npx tsc --noEmit       # 契约 + 组件类型
npm run lint           # ESLint
npm run build          # 构建通过
npm run dev            # preview 走查 /audit
```

走查清单：
- 选动作 → 三段链路正确渲染（canonical / partial / non_canonical 三态）
- 证据 hover 联动高亮正常
- 四时钟四个时间显式区分
- 筛选 `trace_status` / KOL / 标的生效
- `non_canonical` 显式标注断裂点（不隐藏）
- fixtures 模式有"Sample data"标识（诚实原则）

---

## 10. 架构影响（Architecture Impact）

- **契约同步（CLAUDE.md §2）**：新增 F3 类型到 `contracts.ts`，字段名/类型与 `schemas/investment_intent.py` 一致；F4 复用既有类型。
- **F-stage 边界**：纯前端展示层，不跨层调用、不改 F0-F8 后端逻辑；§7 API 作为契约交付物，后端按契约实现。
- **Round 4 红线**：本轮只动 `src/finer_dashboard/**`（前端就是 Dashboard WIP 本身），不碰 `src/finer/**`（§7 仅文档契约）。
- **命名**：全程 F0-F8，无 L0-L8 / V0-V6。
- **诚实原则**：fixtures 模式显式标注 sample data；`non_canonical` 不伪装成完整链路（避免重蹈 mock-as-real）。

---

## 11. 边界 — 不做什么（Out of Scope）

- 不碰后端代码 `src/finer/**`（§7 只定义契约）。
- 不重构 KOL 评价系统（已实现）、不做 UX spec 的导航重构 / 概览仪表盘。
- 不实现 F2 独立 resolver（后端 TD-02，超范围）。
- 不引入 L0-L8 / V0-V6。
- 不把 fixtures 说成 real。

---

## 12. 待确认 / Open Issues

1. **`/audit` 入口位置**：① Sidebar 新增"审计台"tab；② 从 F5/F6 工作台某条资产跳入；③ 从 KOL 详情跳入。建议 ①（独立动线）+ 后续 ③ 收口。
2. **左栏列表数据源**：fixtures 阶段写死；真实阶段是否需要分页/大列表虚拟滚动（取决于 `F5_executed` 规模）。
3. **后端 §7 API 谁实现、何时**：本轮只交付契约；需排期。
4. **EvidenceSpan char offset**：demo 用 `indexOf` 兜底；真实数据应直接用 `char_start`/`char_end`（更稳，处理重复文本）。组件应优先 offset、`indexOf` 仅 fixtures 兜底。
5. **是否同步把 InspectorPanel 占位 provenance 标注为"演示性"**：在 `/audit` 上线前，现有占位是否需要加注，避免误导。

---

## 13. 关联文档

- `docs/specs/2026-06-03-finer-marketing-site.md`（demo-workbench 形态来源）
- `docs/specs/2026-06-03-full-project-review.md` §十（前端审阅，C1-C5 依据）
- `docs/specs/ux-information-architecture-and-kol-rating-system.md`（部分过时，KOL 评价参考）
- `docs/specs/f-stage-contracts.md`（F3/F4/F5 契约真相源）
- `src/finer/schemas/investment_intent.py`、`policy.py`、`trade_action.py`、`evidence.py`（schema 真相源）
- `src/finer_site/src/components/demo/demo-workbench.tsx`（可移植组件）

---

## 14. P1–P3 实施记录（2026-06-04 · 已完成）

> 前端先行、fixtures 驱动；未触后端代码（`src/finer/**` 零改动）。落点为独立全屏 `/audit` + Sidebar「审计台」入口。

### 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_dashboard/src/lib/contracts.ts` | 修改 | 末尾新增 F3 Intent（6 枚举 + `NormalizedInvestmentIntent`）、F2 `EvidenceSpan`、F5 TradeAction 审计子集（`ExecutionTiming`/`ActionStep`/`SourceInfo`/`TargetInfo` + 枚举）、`EnvelopeContext`/`TradeActionSummary`/`AuditTraceBundle` |
| `src/finer_dashboard/src/lib/fixtures/audit-trace.ts` | 新增 | 3 条 `AuditTraceBundle`（canonical 茅台 / partial 五粮液 / non_canonical 宁德）+ `AUDIT_SUMMARIES` |
| `src/finer_dashboard/src/lib/audit-api.ts` | 新增 | 数据层 `getAuditActions`/`getAuditTrace`，`AUDIT_USE_FIXTURES` 切换（默认 fixtures） |
| `src/finer_dashboard/src/components/audit/primitives.tsx` | 新增 | `Pill`/`FieldRow`/`SectionLabel`/`Meter` |
| `src/finer_dashboard/src/components/audit/trace-status-badge.tsx` | 新增 | canonical/partial/non_canonical 徽章 |
| `src/finer_dashboard/src/components/audit/evidence-source.tsx` | 新增 | 原文高亮 + `EvidenceSpan` 列表 + hover 联动 + offset resolve（offset 优先、`indexOf` 兜底） |
| `src/finer_dashboard/src/components/audit/execution-clocks.tsx` | 新增 | 四时钟；legacy 无时钟时诚实标注 |
| `src/finer_dashboard/src/components/audit/intent-card.tsx` | 新增 | F3 Intent 全字段 + ambiguity flags + evidence chips 联动 |
| `src/finer_dashboard/src/components/audit/policy-trace-card.tsx` | 新增 | F4 `layer_traces` 逐层（applied/reason/modifications）+ `decisions` + `risk_constraints` |
| `src/finer_dashboard/src/components/audit/trace-timeline.tsx` | 新增 | F3→F4→F5 三段纵向链路 + 断裂态 |
| `src/finer_dashboard/src/components/audit/action-list.tsx` | 新增 | 左栏清单 |
| `src/finer_dashboard/src/app/audit/page.tsx` | 新增 | 三栏组装 + 筛选 + 状态机 + sample-data 标识 |
| `src/finer_dashboard/src/components/layout/sidebar.tsx` | 修改 | 新增 Analysis section ·「审计台 Audit」入口（`Link` → `/audit`） |

### 验证结果
- `npx tsc --noEmit` → ✅ EXIT 0
- `npm run lint` → ✅ EXIT 0
- `npm run build` → ✅ EXIT 0，`/audit` 作为 static route（○）产出
- preview 走查（`localhost:3000/audit`）：
  - ✅ 三态：canonical（茅台完整链路）/ partial（五粮液 F4 断裂）/ non_canonical（宁德 F3+F4 断裂）
  - ✅ F3 IntentCard 全字段 + ambiguity flag + evidence chips
  - ✅ F4 `layer_traces` 逐层（GlobalBasePolicy 生效 + StyleArchetypePolicy 跳过）+ decisions
  - ✅ 右栏 evidence（无 F2 时诚实标注）+ 四时钟（legacy 时诚实标注）
  - ✅ 证据 hover 联动：hover `es-mt-2` → 原文对应片段深色高亮 `rgba(225,27,34,0.3)`
  - ✅ 零 console error

### P5 回填 InspectorPanel 入口（2026-06-04 · 已完成）
- `src/finer_dashboard/src/components/layout/inspector-panel.tsx` 修改：删除硬编码 6 步假 provenance timeline（`provenanceSteps` / `activeStepIndex`），替换为「证据链审计 · Audit Trace」入口卡 → `Link` 跳 `/audit`；按 tier 区分 F5/F6（已可查看）vs 其他阶段（尚未生成 TradeAction）。同步清理 `Clock3` import。
- 验证：`tsc` ✅ / `lint` ✅ / 无 `provenanceSteps`·`activeStepIndex`·`Clock3` 残留；dev server HMR 重编译无错。InspectorPanel 审计卡的实时视觉需后端 + 选中资产，当前 preview 环境（无后端）暂不可观察；跳转目标 `/audit` 已独立验证。

### C4 KOL/研究视图入口 + ?kol 深链（2026-06-04 · 已完成）
- `app/audit/page.tsx`：支持 `?kol=<id>` 深链初筛 —— 仅当该 KOL 在数据中有 action 才筛并自动选中其首条，否则降级全量（不产生空列表，诚实）。
- `app/kol/[id]/page.tsx`：底部操作区加「在审计台查看证据链」按钮 → `/audit?kol=<id>`。
- `app/research/page.tsx`：header 加「审计台」入口 → `/audit?kol=<selectedId>`（未选时降级 `/audit`）。
- 验证：`tsc` ✅ / `lint` ✅；preview：`/audit?kol=trader_ji` 正确筛到茅台并自动选中、`/research` header 审计入口就位（href 按 selectedId 降级）。

### 未覆盖（后续）
- **P4 接后端**：待后端实现 §7 API 后，设 `NEXT_PUBLIC_AUDIT_USE_FIXTURES=false` 切真实数据。
- 前端无自动化测试（沿用项目现状）。
