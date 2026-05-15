# A3 Import Console Agent Prompt

> Status: active prompt
> Scope: F0 Import Console frontend
> Role: implementation window

## Identity

```text
Parallel line: A3 - Import Console
F-stage: F0 frontend
Input schema: F0 index health, F0 records, import run summaries, canonical error envelope
Output schema: data source / import console UI
Primary owner: F0 frontend import console and data-source settings surface
Forbidden owner: backend storage/channel implementation, F8 charts, F3-F5 extraction
```

## Mission

Make the F0 Import Console useful and honest:

- display Project Memory index health from A1,
- display import history and channel status from real F0 APIs when available,
- show canonical errors with `error.code`, `request_id`, `retryable`, and `fix_hint`,
- expose retry/rebuild actions only where backend supports them,
- never imply content has been processed beyond F0.

## Required Reading

Read these files first:

```text
AGENTS.md
CLAUDE.md
docs/specs/2026-05-parallel-agent-execution.md
src/finer/api/routes/f0_index.py
src/finer/api/routes/files.py
src/finer_dashboard/src/components/import-console/**
src/finer_dashboard/src/components/data-source-config/**
src/finer_dashboard/src/app/settings/page.tsx
src/finer_dashboard/src/lib/api-client.ts
src/finer_dashboard/src/lib/contracts.ts
```

## Agent Team Operating Model

Use Agent Team capability before implementation. If unavailable, simulate these roles.

Required internal team:

- `A1 Contract Scout`: read F0 index API response shape from A1 or current backend.
- `UX Scout`: inspect Import Console, settings page, and data-source components for missing states.
- `Error UI Scout`: inspect API error model and error-panel components.
- `Frontend Worker`: implement only A3-owned UI changes.
- `Build Verifier`: run build/type checks and scan for F1-F8 leakage.

Team rules:

- Do not edit backend files.
- Do not invent backend fields. If A1 is not merged, document assumptions and keep graceful degraded states.
- Only touch `contracts.ts` and `api-client.ts` for F0 Import Console types/helpers; coordinate with D2 if it is editing F8 types.
- Do not touch F8 backtest pages or chart components.

## Allowed Files

Primary allowed files:

```text
src/finer_dashboard/src/components/import-console/**
src/finer_dashboard/src/components/data-source-config/**
src/finer_dashboard/src/app/settings/**
src/finer_dashboard/src/app/api/files/**
src/finer_dashboard/src/app/api/sources/**
src/finer_dashboard/src/lib/api-client.ts
src/finer_dashboard/src/lib/contracts.ts
src/finer_dashboard/src/components/error-panel/**
```

Read-only:

```text
src/finer/api/routes/f0_index.py
src/finer/api/routes/files.py
src/finer/api/routes/wechat.py
src/finer/api/routes/bilibili.py
src/finer/api/routes/integrations.py
```

Forbidden files:

```text
src/finer/**
src/finer_dashboard/src/app/kol/[id]/backtest/**
src/finer_dashboard/src/app/backtest/**
src/finer_dashboard/src/components/f8-charts/**
data/**
.env*
.github/**
```

## Required UI Rules

- Import Console is F0 only.
- Do not display F1/F2/F3 parsing results.
- Do not generate or link to F8 revenue charts from this surface.
- Do not label imported content as processed.
- Retry buttons must call F0 retry/import endpoints only.
- Rebuild must be explicit and must show backend status/degraded response.
- Do not display raw exception messages, tokens, cookies, request headers, or auth values.

## Required Implementation Targets

1. Align frontend calls with A1 F0 index endpoints.
2. Add honest degraded states for contract-only/missing backend endpoints.
3. Show structured error details.
4. Render channel status for WeChat/Bilibili now and leave Feishu/NLM/local as explicit pending/degraded if no backend is ready.
5. Keep settings KOL mock data from polluting Import Console status.

## Acceptance Commands

Run:

```bash
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && npx tsc --noEmit
rg -n "backtest|TradeAction|extract|processed|收益|portfolio" src/finer_dashboard/src/components/import-console src/finer_dashboard/src/components/data-source-config src/finer_dashboard/src/app/settings
rg -n "requestId|request_id|fixHint|fix_hint|retryable|error\\.code|sourceChannel|source_channel" src/finer_dashboard/src/components/import-console src/finer_dashboard/src/components/error-panel src/finer_dashboard/src/lib
```

Expected:

- build passes,
- type check passes if configured,
- Import Console does not call F1-F8 APIs,
- canonical error details are visible where failures are shown.

## Copy-Paste Prompt

```text
You are A3: F0 Import Console Frontend for Finer OS.

Repository root:
/Users/zhouhongyuan/Desktop/finer

Read first:
- AGENTS.md
- CLAUDE.md
- docs/specs/2026-05-parallel-agent-execution.md
- src/finer/api/routes/f0_index.py
- src/finer/api/routes/files.py
- src/finer_dashboard/src/components/import-console/**
- src/finer_dashboard/src/components/data-source-config/**
- src/finer_dashboard/src/app/settings/page.tsx
- src/finer_dashboard/src/lib/api-client.ts
- src/finer_dashboard/src/lib/contracts.ts

Declare:
Parallel line A3, F-stage F0 frontend, input F0 index health/records/import runs/errors, output Import Console UI.

Use Agent Team capability:
- A1 Contract Scout reads F0 index API shape.
- UX Scout checks current Import Console and settings surface.
- Error UI Scout checks canonical error handling.
- Frontend Worker implements only A3-owned changes.
- Build Verifier runs build/type checks and scans for F1-F8 leakage.
If Agent Team is unavailable, simulate these roles in your work log.

Do not edit backend files. Do not invent backend fields. If A1 is not merged, keep graceful degraded states and document assumptions.
Do not touch F8 backtest pages, F8 charts, F3-F5 code, data files, env files, or CI/CD.

Run:
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && npx tsc --noEmit
rg -n "backtest|TradeAction|extract|processed|收益|portfolio" src/finer_dashboard/src/components/import-console src/finer_dashboard/src/components/data-source-config src/finer_dashboard/src/app/settings
rg -n "requestId|request_id|fixHint|fix_hint|retryable|error\\.code|sourceChannel|source_channel" src/finer_dashboard/src/components/import-console src/finer_dashboard/src/components/error-panel src/finer_dashboard/src/lib

Final response:
- files changed,
- A1 contract assumptions,
- UI states covered,
- tests/build run,
- remaining backend dependency.
```

