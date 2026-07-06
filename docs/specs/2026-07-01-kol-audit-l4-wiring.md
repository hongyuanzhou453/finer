# L4 接线 — 每条观点下钻单条证据审计

## 概述

把"可审计"落到每个数字：为每条观点新增 per-viewpoint 证据审计页 `/demo/audit/[viewpointId]`，并把三处出现观点的地方（KOL 问责页时间线、标的横截面时间线、雷达可跟卡）全部接 Link 下钻。至此晨星式四层漏斗（首页雷达 → KOL 问责页 / 标的横截面 → 单条证据审计）全打通。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer_dashboard/src/lib/fixtures/kol-audit.ts` | 新增 | `findViewpointById(id)`：跨 radar（分 KOL）+ snapshot fixture 定位 viewpoint + KOL 上下文 |
| `.../components/kol-audit/ViewpointAudit.tsx` + `index.ts` | 新增 | 聚焦式证据审计视图：F2 证据 / F5 动作 / F8 回测 staged 呈现；复用 audit 的 `TraceStatusBadge` + snapshot kit |
| `.../app/demo/audit/[viewpointId]/page.tsx` | 新增 | 动态路由（Next16 async params + 未找到降级） |
| `.../components/kol-snapshot/ViewpointTimeline.tsx` | 修改 | 每条卡包 `<Link>` → `/demo/audit/[id]` + 「证据链 →」提示 |
| `.../components/kol-ticker/TickerStanceTimeline.tsx` | 修改 | 同上 |
| `.../components/kol-radar/ActionableCalls.tsx` | 修改 | 「证据链下钻 · 即将开放」占位 → 真实 Link「查看证据链 →」 |

未改后端 / 既有 `/audit` 控制台 / schema。

## 架构影响

- **四层漏斗全打通**：雷达首页 → KOL 问责页(L2) / 标的横截面(L3) → 单条证据审计(L4)。每个 viewpoint / call / timeline 卡均可下钻至其证据。
- **不碰既有 `/audit` 控制台**：它是独立 fixture（3 条真 canonical trace）+ 独立 API 契约。L4 新建 `/demo/audit/[id]` 与之并存，互不干扰；ViewpointAudit 页内多处链到 `/audit` 看完整 canonical 示例。
- **复用**：audit 的 `TraceStatusBadge`（纯组件）+ snapshot kit（DirectionTag/ReturnChip/ConfidenceMeter/fmt*）。

## 关键决策

1. **不伪造 canonical trace，只展示 demo 真有的层 + 诚实标注缺口**。探查确认：`/audit` 的 3 条 trace 与我的 viewpoint id **无交集**，且 viewpoint 数据太薄（有 F2 证据引文 + F5 动作基础 + F8 回测，但**无完整原文、无四时钟、无真 F3 意图 / F4 策略**）。故 ViewpointAudit 只 staged 呈现 F2→F5→F8，并用 dashed 面板明确标注「F3 意图 / F4 策略未在 demo 物化，完整 canonical 示例见 /audit」，不拿单时间戳编四时钟、不拿空壳假装 canonical。
2. **findViewpointById 跨两套 fixture**：viewpoint id 来自 radar（TA-lz-*/TA-ji-* 等）与 snapshot（TA-trader_ji-*），无碰撞，统一解析。
3. **卡片整卡可点 + 「证据链 →」teal 提示**；雷达可跟卡的旧占位「即将开放」同步兑现为真实链接。

## 验证结果

- `npx tsc --noEmit` + `npx eslint`：kol-audit / ViewpointAudit / route / 三处 timeline+calls 全 clean。
- 浏览器（desktop + mobile 375）：
  - `/demo/audit/TA-lz-01`（平安）正常渲染 F2 证据 + F5 动作(85%/已验证) + F8 兑现 +18.2%/持仓64天 + CANONICAL 徽标 + 返回问责页链接；无 console error；移动端无横向溢出。
  - snapshot fixture id `TA-trader_ji-001`（茅台）解析成功 → 证明 findViewpointById 跨两套 fixture。
  - pending 观点 `TA-hk-04`（美团）F8 显示「待回测」、F5「待验证」，边界正常。
- 下钻链接计数：KOL 问责页时间线 4 条、标的横截面时间线 3 条、雷达可跟卡 4 条「查看证据链 →」，href 全部指向正确 `/demo/audit/[id]`。

## 未解决项

1. **诚实性微张力**：viewpoint.traceStatus 多为 "canonical"，故徽标显示 CANONICAL，而 scope note 说 F3/F4 未物化。已用 note 澄清（徽标=管线状态声明，note=demo 数据深度），但两者并存仍有轻微张力；根因是 viewpoint fixture 乐观地把 traceStatus 设为 canonical 却未携带 F3/F4 明细。
2. **真实审计接入**：要让 per-viewpoint 展示真 F3 意图 / F4 策略 / 四时钟 / 完整原文高亮，需 viewpoint 携带或后端提供更深 trace（即 `/audit` 的 AuditTraceBundle 深度）。
3. **反向导航**：ViewpointAudit 固定链回「KOL 问责页」；从标的横截面点进来的用户回到的是 KOL 页而非标的页（无 referrer 感知，属可接受简化）。
