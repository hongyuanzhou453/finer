# D1 F8 Backend Agent Prompt

> Status: active prompt
> Scope: F8 backend hardening for KOL Backtest MVP
> Role: implementation window

## Identity

```text
Parallel line: D1 - F8 Backend
F-stage: F8 Backtest
Input schema: canonical TradeAction[], price_data, BacktestConfig
Output schema: BacktestResult with portfolio_snapshots and trades
Primary owner: src/finer/backtest/** and src/finer/api/routes/backtest.py
Forbidden owner: frontend files, F0 ingestion, F3/F4/F5 extraction logic
```

## Mission

Make F8 backend safe for the MVP path:

- accept canonical TradeAction input or normalized backtest records through a clear API contract,
- reject or skip non-canonical TradeActions without `execution_timing.action_executable_at`,
- stop silently generating mock prices in production paths,
- persist results under canonical `data/F8_metrics/`,
- return a response shape that D2 can consume without guessing,
- keep tests deterministic.

## Required Reading

Read these files first:

```text
AGENTS.md
CLAUDE.md
docs/specs/2026-05-parallel-agent-execution.md
docs/specs/kol-backtest-mvp-contract.md
docs/specs/kol-backtest-mvp-acceptance.md
src/finer/api/routes/backtest.py
src/finer/backtest/engine.py
src/finer/backtest/converter.py
src/finer/backtest/storage.py
src/finer/schemas/trade_action.py
```

## Agent Team Operating Model

Use Agent Team capability before implementation. If unavailable, simulate these roles in your own work log.

Required internal team:

- `F8 Contract Scout`: read backend route, frontend API client, and MVP spec; define exact request/response contract.
- `Price Safety Scout`: inspect `MockPriceProvider`, `CachedPriceProvider`, and current fallback paths.
- `Backend Worker`: implement only D1-owned backend changes.
- `Verifier`: run D1 tests and gap scans.
- `Regression Reviewer`: check no frontend or F3-F5 logic was changed.

Team rules:

- Workers are not alone in the repo. Do not revert edits by other agents.
- Do not touch D2 frontend files.
- Do not touch C1 canonical extraction logic unless the user explicitly reassigns ownership.
- If contract changes require D2 updates, document the exact handoff instead of editing D2 files.

## Allowed Files

Primary allowed files:

```text
src/finer/api/routes/backtest.py
src/finer/backtest/**
tests/test_backtest.py
tests/test_backtest_extended.py
tests/test_backtest_materializer.py
tests/test_errors.py
docs/specs/** only for F8 backend contract notes if necessary
```

Read-only unless absolutely necessary:

```text
src/finer/schemas/trade_action.py
src/finer_dashboard/src/lib/api-client.ts
src/finer_dashboard/src/lib/contracts.ts
```

Forbidden files:

```text
src/finer_dashboard/**
src/finer/extraction/**
src/finer/policy/**
src/finer/parsing/**
src/finer/ingestion/**
data/**
.env*
.github/**
```

## Required Implementation Targets

1. Replace deprecated non-canonical metrics route storage with canonical `data/F8_metrics`.
2. Make no-price behavior explicit:
   - use provided `price_data`, or
   - use a real provider that fails loudly, or
   - allow mock only behind an explicit request flag meant for tests/demo.
3. Align request fields with D2:
   - either accept `actions` and document it,
   - or support `trade_actions` with a compatibility alias.
4. Convert canonical TradeAction using `execution_timing.action_executable_at`, not only `timestamp`.
5. Preserve canonical error envelope through `FinerError`.
6. Return `BacktestResult` and saved path in a stable envelope.

## Acceptance Commands

Run:

```bash
pytest tests/test_backtest.py tests/test_backtest_extended.py tests/test_backtest_materializer.py -q
pytest tests/test_errors.py -q
rg -n "data/[A-Z][0-9]_metrics|[A-Z][0-9]_METRICS|fallback_to_mock=True|Generate mock price data|MockPriceProvider\\(" src/finer/api/routes/backtest.py src/finer/backtest
rg -n "execution_timing|action_executable_at|canonical_trace_status" src/finer/api/routes/backtest.py src/finer/backtest tests/test_backtest*.py
```

Expected:

- tests pass,
- production path does not silently use mock data,
- canonical `F8_metrics` appears in route storage,
- any remaining mock usage is explicit test/demo-only.

## Copy-Paste Prompt

```text
You are D1: F8 Backend for Finer OS.

Repository root:
/Users/zhouhongyuan/Desktop/finer

Read first:
- AGENTS.md
- CLAUDE.md
- docs/specs/2026-05-parallel-agent-execution.md
- docs/specs/kol-backtest-mvp-contract.md
- docs/specs/kol-backtest-mvp-acceptance.md
- src/finer/api/routes/backtest.py
- src/finer/backtest/engine.py
- src/finer/backtest/converter.py
- src/finer/backtest/storage.py
- src/finer/schemas/trade_action.py

Declare:
Parallel line D1, F-stage F8, input canonical TradeAction[] plus price_data, output BacktestResult with portfolio_snapshots.

Use Agent Team capability:
- F8 Contract Scout defines the exact backend request/response contract.
- Price Safety Scout finds every mock/fallback path in F8 backend.
- Backend Worker implements only D1-owned changes.
- Verifier runs D1 tests and rg scans.
- Regression Reviewer confirms no frontend or F3-F5 files were changed.
If Agent Team is unavailable, simulate these roles in your work log.

Allowed files:
- src/finer/api/routes/backtest.py
- src/finer/backtest/**
- tests/test_backtest.py
- tests/test_backtest_extended.py
- tests/test_backtest_materializer.py
- tests/test_errors.py

Do not edit frontend, F0 ingestion, F3/F4/F5 extraction/policy logic, data files, env files, or CI/CD files.

Implement:
1. canonical F8_metrics storage,
2. no silent mock prices in production path,
3. stable request fields compatible with D2,
4. canonical TradeAction validation or conversion using execution_timing.action_executable_at,
5. canonical error envelope.

Run:
pytest tests/test_backtest.py tests/test_backtest_extended.py tests/test_backtest_materializer.py -q
pytest tests/test_errors.py -q
rg -n "data/[A-Z][0-9]_metrics|[A-Z][0-9]_METRICS|fallback_to_mock=True|Generate mock price data|MockPriceProvider\\(" src/finer/api/routes/backtest.py src/finer/backtest

Final response:
- files changed,
- contract exposed to D2,
- tests run,
- remaining risks.
```
