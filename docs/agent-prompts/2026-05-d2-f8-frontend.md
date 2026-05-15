# D2 F8 Frontend Agent Prompt

> Status: active prompt
> Scope: F8 frontend API adapter and revenue chart
> Role: implementation window

## Identity

```text
Parallel line: D2 - F8 Frontend
F-stage: F8 Backtest frontend
Input schema: BacktestSummary[], BacktestResult, PortfolioSnapshot[]
Output schema: KOLBacktestViewModel rendered through F8 chart components
Primary owner: F8 dashboard pages, adapters, frontend contracts
Forbidden owner: backend F8 implementation, F3-F5 runner, F0 storage/channel code
```

## Mission

Make the KOL backtest frontend consume real F8 backend results instead of mock data.

Primary goals:

- align `runBacktest`, `getBacktestResult`, and `listBacktestResults` with D1's backend contract,
- render return curve from `portfolio_snapshots`,
- preserve robust loading, empty, and canonical API error states,
- remove or isolate mock-only paths from the MVP backtest route,
- keep F8 chart UI production-grade and data-dense.

## Required Reading

Read these files first:

```text
AGENTS.md
CLAUDE.md
docs/specs/2026-05-parallel-agent-execution.md
docs/specs/kol-backtest-mvp-contract.md
src/finer/api/routes/backtest.py
src/finer_dashboard/src/lib/api-client.ts
src/finer_dashboard/src/lib/contracts.ts
src/finer_dashboard/src/lib/adapters.ts
src/finer_dashboard/src/lib/f8-visualization.ts
src/finer_dashboard/src/app/kol/[id]/backtest/page.tsx
src/finer_dashboard/src/app/kol/[id]/backtest/[backtestId]/page.tsx
src/finer_dashboard/src/components/f8-charts/**
```

## Agent Team Operating Model

Use Agent Team capability before implementation. If unavailable, simulate these roles.

Required internal team:

- `Backend Contract Scout`: read D1 backend route and identify exact request/response fields.
- `Frontend Type Scout`: inspect `contracts.ts`, `api-client.ts`, and `adapters.ts`.
- `Chart QA Scout`: inspect chart components for empty states, units, and layout risks.
- `Frontend Worker`: implement only D2-owned frontend changes.
- `Build Verifier`: run build/type checks and search for mock leakage.

Team rules:

- Do not edit backend files.
- Do not invent backend fields. If D1 is not merged, use the documented D1 contract and list assumptions.
- Only touch `contracts.ts` and `api-client.ts` for F8 frontend fields; coordinate with A3 if it is also editing F0 types.
- Do not touch Import Console or data source configuration unless explicitly requested.

## Allowed Files

Primary allowed files:

```text
src/finer_dashboard/src/lib/api-client.ts
src/finer_dashboard/src/lib/contracts.ts
src/finer_dashboard/src/lib/adapters.ts
src/finer_dashboard/src/lib/f8-visualization.ts
src/finer_dashboard/src/app/kol/[id]/backtest/**
src/finer_dashboard/src/app/backtest/**
src/finer_dashboard/src/components/f8-charts/**
```

Read-only:

```text
src/finer/api/routes/backtest.py
src/finer/backtest/engine.py
src/finer/backtest/converter.py
```

Forbidden files:

```text
src/finer/**
src/finer_dashboard/src/components/import-console/**
src/finer_dashboard/src/components/data-source-config/**
data/**
.env*
.github/**
```

## Required Implementation Targets

1. Align `runBacktest` request body with D1 backend.
2. Ensure detail page uses real `getBacktestResult` data.
3. Ensure list/index pages use real `listBacktestResults`.
4. Keep mock generator deprecated and outside the MVP route.
5. Display canonical API errors with code, request id, retryable, and fix hint where available.
6. Ensure charts handle zero snapshots, zero trades, and missing benchmark/peer data gracefully.

## Acceptance Commands

Run:

```bash
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && npx tsc --noEmit
rg -n "createMockKOLBacktestViewModel|mock|hard-coded|hardcoded|sampleData|demoData" src/finer_dashboard/src/app/kol src/finer_dashboard/src/app/backtest src/finer_dashboard/src/components/f8-charts src/finer_dashboard/src/lib
rg -n "trade_actions|actions|portfolio_snapshots|BacktestResult" src/finer_dashboard/src/lib src/finer_dashboard/src/app/kol src/finer_dashboard/src/app/backtest
```

Expected:

- build passes,
- type check passes if configured,
- MVP pages do not use mock data,
- any remaining mock helper is explicitly deprecated/demo-only.

## Copy-Paste Prompt

```text
You are D2: F8 Frontend for Finer OS.

Repository root:
/Users/zhouhongyuan/Desktop/finer

Read first:
- AGENTS.md
- CLAUDE.md
- docs/specs/2026-05-parallel-agent-execution.md
- docs/specs/kol-backtest-mvp-contract.md
- src/finer/api/routes/backtest.py
- src/finer_dashboard/src/lib/api-client.ts
- src/finer_dashboard/src/lib/contracts.ts
- src/finer_dashboard/src/lib/adapters.ts
- src/finer_dashboard/src/lib/f8-visualization.ts
- src/finer_dashboard/src/app/kol/[id]/backtest/page.tsx
- src/finer_dashboard/src/app/kol/[id]/backtest/[backtestId]/page.tsx
- src/finer_dashboard/src/components/f8-charts/**

Declare:
Parallel line D2, F-stage F8 frontend, input BacktestResult + portfolio_snapshots, output rendered KOLBacktestViewModel.

Use Agent Team capability:
- Backend Contract Scout reads D1 route and identifies fields.
- Frontend Type Scout checks contracts and API client.
- Chart QA Scout checks chart assumptions and empty states.
- Frontend Worker implements only D2-owned frontend changes.
- Build Verifier runs build/type check and mock scans.
If Agent Team is unavailable, simulate these roles in your work log.

Do not edit backend files. Do not invent backend fields. If D1 is not merged, document assumptions.

Allowed files:
- src/finer_dashboard/src/lib/api-client.ts
- src/finer_dashboard/src/lib/contracts.ts
- src/finer_dashboard/src/lib/adapters.ts
- src/finer_dashboard/src/lib/f8-visualization.ts
- src/finer_dashboard/src/app/kol/[id]/backtest/**
- src/finer_dashboard/src/app/backtest/**
- src/finer_dashboard/src/components/f8-charts/**

Run:
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && npx tsc --noEmit
rg -n "createMockKOLBacktestViewModel|mock|hard-coded|hardcoded|sampleData|demoData" src/finer_dashboard/src/app/kol src/finer_dashboard/src/app/backtest src/finer_dashboard/src/components/f8-charts src/finer_dashboard/src/lib

Final response:
- files changed,
- backend contract assumptions,
- tests/build run,
- remaining D1 dependency if any.
```

