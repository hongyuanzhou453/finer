# Round 2 Task Matrix — KOL → TradeAction → BacktestResult → Revenue Chart

> Baseline: `261dba5` (Gate PASS)
> Date: 2026-05-15
> Goal: one KOL's content flows through canonical F3→F4→F5→F8→frontend revenue chart

## Dependency Graph

```
C1 (clean extraction.py) ──────────────┐
                                        ├─→ D1 (F8 E2E) ──→ D2 (revenue chart)
B1/F7 (clean opinions.py) ─────────────┘
                                        ╭─→ A3 (import console)
A1 (F0 index stabilize) ───────────────╯
A2 (channel adapters) ───────────────────→ (independent, no downstream)
```

## Shared Conflict Files

| File | Agents | Strategy |
|---|---|---|
| `src/finer/api/routes/extraction.py` | C1 only | C1 独占 |
| `src/finer/api/routes/opinions.py` | B1/F7 only | 独占 |
| `src/finer/api/routes/backtest.py` | D1 only | D1 独占 |
| `src/finer_dashboard/src/lib/contracts.ts` | D2, A3 | D2 先合，A3 rebase |
| `src/finer_dashboard/src/lib/api-client.ts` | D2, A3 | D2 先合，A3 rebase |
| `src/finer_dashboard/src/lib/f8-visualization.ts` | D2 only | D2 独占 |

## Recommended Merge Order

1. **C1** — extraction.py legacy cleanup (no downstream blocker)
2. **B1/F7** — opinions.py mock cleanup (no downstream blocker)
3. **A1** — F0 index stabilize
4. **A2** — channel adapters (independent)
5. **D1** — F8 backend E2E (after C1 validates canonical path)
6. **D2** — F8 frontend revenue chart (after D1 API stable)
7. **A3** — import console (after A1 + D2, rebase contracts.ts)

---

## Agent Task Cards

### C1 — extraction.py Legacy Bypass Cleanup

```text
Parallel line: C1 — Canonical Runner
F-stage: F3→F4→F5
Input schema: ContentEnvelope → EvidenceSpan[] → NormalizedInvestmentIntent → TradeAction
Output schema: extraction.py with legacy=true path removed or gated as deprecated
```

**Owning files**
- `src/finer/api/routes/extraction.py`

**Forbidden files**
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/api/routes/backtest.py`
- `src/finer/api/routes/opinions.py`
- `src/finer/ingestion/**`

**What to do**
- Remove or deprecate the `legacy=true` parameter from `/api/extraction/extract` and `/api/extraction/pipeline`.
- Remove the `extract_from_text()` call path (lines 162-167, 353-356).
- Remove `L4_PARSED_DIR` / `L5_candidate` legacy directory references (lines 23-24, 277-297).
- Keep the canonical F3→F4→F5 path as the only code path.
- If keeping `legacy` as a parameter temporarily, make it raise `NotImplementedError` with a clear migration message.

**Deliverables**
- `extraction.py` with no `extract_from_text()` calls in active code paths
- Tests updated to remove legacy bypass coverage

**Acceptance commands**
```bash
pytest tests/test_canonical_f3_f4_f5_contract.py tests/test_canonical_action_builder.py tests/test_intent_extractor_canonical.py tests/test_policy_mapper.py -q
rg -n "extract_from_text\(" src/finer/api/routes/extraction.py
rg -n "legacy" src/finer/api/routes/extraction.py
```

---

### B1/F7 — opinions.py Mock Opinion Cleanup

```text
Parallel line: B1/F7 — Timeline Opinions
F-stage: F7 Timeline
Input schema: ViewpointState, BacktestResult, real opinion queries
Output schema: opinions.py with mock fallback removed or gated
```

**Owning files**
- `src/finer/api/routes/opinions.py`

**Forbidden files**
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/api/routes/backtest.py`
- `src/finer/api/routes/extraction.py`
- `src/finer/ingestion/**`

**What to do**
- Remove `_generate_mock_opinion()` function (line 502+).
- Remove mock fallback branches in `get_timeline`, `get_stats`, `get_opinion` (lines 681-692, 727-729, 753-755, 811-815).
- When real data query fails, return proper error response using canonical error envelope (`FinerError` with `stage="F7"`).
- Keep the endpoint shapes stable — only the data source changes.

**Deliverables**
- `opinions.py` with zero mock data generation
- All failure paths return `{"ok": false, "error": {...}}` with `request_id`, `stage`, `retryable`, `fix_hint`

**Acceptance commands**
```bash
pytest tests/ -q -k "opinion"
rg -n "_generate_mock_opinion|mock.*fallback|fallback.*mock" src/finer/api/routes/opinions.py
rg -n "FinerError\|request_id\|fix_hint" src/finer/api/routes/opinions.py
```

---

### D1 — F8 Backend E2E

```text
Parallel line: D1 — F8 Backend
F-stage: F8 Backtest
Input schema: canonical TradeAction[] with intent_id/policy_id/evidence_span_ids/execution_timing
Output schema: BacktestResult with portfolio_snapshots, trades, metrics
```

**Owning files**
- `src/finer/backtest/**` (except price provider mock paths — keep as test-only)
- `src/finer/api/routes/backtest.py`

**Forbidden files**
- `src/finer_dashboard/**`
- `src/finer/api/routes/extraction.py`
- `src/finer/api/routes/opinions.py`
- `src/finer/ingestion/**`
- `src/finer/pipeline/canonical_runner.py`

**What to do**
- Validate incoming TradeActions have required canonical fields: `intent_id`, `policy_id`, `evidence_span_ids`, `execution_timing.action_executable_at`.
- Reject or skip actions missing these fields with `FinerError(ErrorCode.F8_IN_001, ...)`.
- Ensure the E2E path works: `POST /api/backtest/run` with `price_data` → materialize → compute portfolio snapshots → persist to `data/F8_metrics/` → return `BacktestResult`.
- Confirm `GET /api/backtest/{id}` returns the persisted result with `portfolio_snapshots`.
- Remove `use_mock` parameter from production route (keep in test-only endpoint if needed).
- Add an E2E integration test that feeds a fixture TradeAction and asserts the response shape.

**Deliverables**
- Backtest route validates canonical TradeAction fields
- `data/F8_metrics/` persistence confirmed
- E2E test: fixture TradeAction → BacktestResult with portfolio_snapshots

**Acceptance commands**
```bash
pytest tests/test_backtest.py tests/test_backtest_extended.py tests/test_backtest_materializer.py -q
rg -n "use_mock\|fallback_to_mock" src/finer/api/routes/backtest.py
rg -n "intent_id\|policy_id\|evidence_span\|execution_timing" src/finer/api/routes/backtest.py
ls data/F8_metrics/ 2>/dev/null | head -5
```

---

### D2 — F8 Frontend Revenue Chart

```text
Parallel line: D2 — F8 Frontend
F-stage: F8 Backtest frontend
Input schema: BacktestResult (from D1 API)
Output schema: KOLBacktestViewModel with rendered revenue curve
```

**Owning files**
- `src/finer_dashboard/src/app/kol/[id]/backtest/page.tsx`
- `src/finer_dashboard/src/app/kol/[id]/backtest/[backtestId]/page.tsx`
- `src/finer_dashboard/src/app/backtest/page.tsx`
- `src/finer_dashboard/src/lib/f8-visualization.ts`
- `src/finer_dashboard/src/lib/contracts.ts`
- `src/finer_dashboard/src/lib/api-client.ts`
- Chart components under `src/finer_dashboard/src/components/backtest/` (if exist)

**Forbidden files**
- `src/finer/backtest/**`
- `src/finer/api/routes/**`
- `src/finer/ingestion/**`
- `src/finer/pipeline/**`

**What to do**
- Remove or isolate the hard-coded mock data in `f8-visualization.ts:212` (the function comment says "will be removed in a future cleanup" — this is that cleanup).
- Ensure the revenue chart reads from `BacktestResult.portfolio_snapshots` via the D1 API, not from mock data.
- Handle loading, empty, and error states using the canonical error envelope (`error.code`, `request_id`, `fix_hint`).
- Confirm `runBacktest` client function matches D1's request/response shape (already aligned in round 1 commit `036d0ea`).
- Ensure `contracts.ts` TypeScript types match D1's Pydantic `BacktestResult` model.

**Deliverables**
- `f8-visualization.ts` with no mock data
- Revenue chart renders from real `portfolio_snapshots`
- Error states display canonical error fields

**Acceptance commands**
```bash
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && npx tsc --noEmit
rg -n "mock\|hard-coded\|hardcoded\|sampleData\|demoData" src/finer_dashboard/src/app/kol src/finer_dashboard/src/app/backtest src/finer_dashboard/src/lib/f8-visualization.ts
rg -n "portfolio_snapshots\|return_curve\|revenue" src/finer_dashboard/src/app/kol src/finer_dashboard/src/components/backtest 2>/dev/null
```

---

### A1 — F0 Index Stabilize

```text
Parallel line: A1 — Project Memory Storage
F-stage: F0 Storage
Input schema: ContentRecord, import runs, source cursors
Output schema: stable /api/f0-index/* endpoints, rebuild behavior
```

**Owning files**
- `src/finer/startup.py`
- `src/finer/api/routes/f0_index.py`
- `src/finer/services/project_memory.py` (if exists)
- `src/finer/schemas/f0_index.py`
- `tests/test_f0_project_memory.py`

**Forbidden files**
- `src/finer/api/routes/backtest.py`
- `src/finer/api/routes/extraction.py`
- `src/finer/api/routes/opinions.py`
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/ingestion/**` (except startup index integration)

**What to do**
- Ensure `/api/f0-index/health` returns accurate `total_records`, `needs_rebuild`, `last_rebuild_at`.
- Ensure `/api/f0-index/records` supports pagination (`limit`, `offset`) and returns `ContentRecord` summaries.
- Ensure `/api/f0-index/rebuild` triggers background rebuild and returns immediately.
- Startup path reads index metadata first; never recursively scans `data/raw/` by default.
- Add test coverage for health, records query, and rebuild trigger.

**Deliverables**
- Stable health/records/rebuild endpoints
- Startup uses index, not recursive scan
- Test coverage for all 3 endpoints

**Acceptance commands**
```bash
pytest tests/test_f0_project_memory.py -q
rg -n "rglob\|os.walk\|glob(" src/finer/startup.py
rg -n "needs_rebuild\|last_rebuild" src/finer/api/routes/f0_index.py
```

---

### A2 — Channel Adapters Stabilize

```text
Parallel line: A2 — F0 Channel Adapters
F-stage: F0 Intake
Input schema: external source metadata, raw artifacts
Output schema: ContentRecord with dedupe_fingerprint, import receipt
```

**Owning files**
- `src/finer/ingestion/wechat_adapter.py`
- `src/finer/ingestion/wechat_exporter_client.py`
- `src/finer/ingestion/bilibili_adapter.py`
- `src/finer/api/routes/bilibili.py`
- `src/finer/api/routes/wechat.py`
- `src/finer/services/wechat_content_record_builder.py`
- Channel tests under `tests/`

**Forbidden files**
- `src/finer/api/routes/backtest.py`
- `src/finer/api/routes/extraction.py`
- `src/finer/api/routes/opinions.py`
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/pipeline/**`

**What to do**
- Remove `_get_mock_articles` / `_get_mock_content` from `wechat_adapter.py` (lines 568-636).
- Ensure WeChat and Bilibili adapters output `ContentRecord` with `dedupe_fingerprint`, `external_source_id`, `creator_id`.
- Ensure all error paths use `FinerError` with `source_channel` set.
- Verify dedupe prevents duplicate `ContentRecord` creation on re-import.

**Deliverables**
- `wechat_adapter.py` with no mock article/content generation
- Both adapters output complete `ContentRecord` with dedupe
- All errors use canonical envelope

**Acceptance commands**
```bash
pytest tests/test_wechat_content_record.py tests/test_wechat_artifact_store.py tests/test_wechat_api_routes.py tests/test_bilibili.py -q
rg -n "_get_mock_articles\|_get_mock_content" src/finer/ingestion/wechat_adapter.py
rg -n "dedupe_fingerprint\|external_source_id" src/finer/services/wechat_content_record_builder.py src/finer/ingestion/bilibili_adapter.py
rg -n "FinerError\|source_channel" src/finer/api/routes/bilibili.py src/finer/api/routes/wechat.py
```

---

### A3 — Import Console Stabilize

```text
Parallel line: A3 — Import Console
F-stage: F0 Frontend
Input schema: /api/f0-index/* responses, canonical error envelope
Output schema: data source / import console UI
```

**Owning files**
- `src/finer_dashboard/src/components/import-console/ImportConsole.tsx`
- `src/finer_dashboard/src/components/import-console/IndexHealthCard.tsx`
- `src/finer_dashboard/src/components/import-console/SourceChannelStatus.tsx`
- `src/finer_dashboard/src/lib/contracts.ts` (after D2 merges)
- `src/finer_dashboard/src/lib/api-client.ts` (after D2 merges)

**Forbidden files**
- `src/finer/api/routes/**`
- `src/finer/backtest/**`
- `src/finer/ingestion/**`
- `src/finer/pipeline/**`

**What to do**
- Ensure Import Console reads from `/api/f0-index/health` and `/api/f0-index/records` (A1 endpoints).
- Display `error.code`, `request_id`, `retryable`, `fix_hint` on failure — no raw tracebacks.
- Never display "processed" for F0-only content — use "imported" or "indexed".
- Ensure source channel status shows real channel data when available, empty state when not.
- After D2 merges, rebase `contracts.ts` / `api-client.ts` and verify no type conflicts.

**Deliverables**
- Import Console renders real F0 index data
- Error display uses canonical fields
- No "processed" label on F0 content

**Acceptance commands**
```bash
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && npx tsc --noEmit
rg -n "processed" src/finer_dashboard/src/components/import-console
rg -n "requestId\|request_id\|fixHint\|fix_hint\|retryable" src/finer_dashboard/src/components/import-console
```
