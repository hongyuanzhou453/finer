# Round 3 Task Matrix — Cat Lord + Trader Ji → F5 Canonical Actions + F8 Equity Curve

> Baseline: `9e0c878` (T5 committed, Round 2 Gate PASS)
> Date: 2026-05-16
> Goal: two KOLs (猫大人FIRE, trader韭/9友) produce F5 canonical TradeActions + F8 equity curves with auditable intermediate results at every F-stage

## Dependency Graph

```
T1a (ModelRouter + PromptRegistry) ──→ T3 (F3 Intent LLM) ──→ T6 (Golden Path F3→F5) ──→ T7 (F8 E2E)
T5 (ExecutionTiming extraction) ✓ DONE
T8a (Legacy dead code scan) ────────── independent
T8b (F7 opinions mock cleanup) ────── independent
```

## Shared Conflict Files

| File | Agents | Strategy |
|---|---|---|
| `src/finer/extraction/intent_extractor.py` | T1a (read), T3 (write) | T1a 只读扫描结构；T3 在 Phase 2 修改 |
| `src/finer/model_config.py` | T1a only | T1a 独占 |
| `src/finer/llm/router.py` | T1a only | T1a 新建 |
| `src/finer/prompts/` | T1a only | T1a 新建 |
| `src/finer/api/routes/opinions.py` | T8b only | T8b 独占 |
| `src/finer/pipeline/canonical_runner.py` | T6 only | T6 在 Phase 3 修改 |

## Recommended Merge Order

1. **T8a** — legacy scan (read-only, no merge needed)
2. **T8b** — opinions mock cleanup (independent)
3. **T1a** — ModelRouter + PromptRegistry + F3 prompt (Phase 1 bottleneck)
4. **T3** — F3 Intent LLM integration (Phase 2, depends on T1a)
5. **T6** — Golden Path Pipeline F3→F5 (Phase 3, depends on T3)
6. **T7** — F8 Backtest E2E + frontend (Phase 4, depends on T6)

---

## Agent Task Cards

### T1a — ModelRouter + PromptRegistry + F3 Prompt

```text
Parallel line: T1a — Model Infrastructure
F-stage: cross-cutting (F3 prompt first)
Input schema: LLMClient, model_config.py, intent_prompt.py
Output schema: ModelRouter, PromptRegistry, F3 Jinja2 template
Baseline: 9e0c878
```

**Owning files**
- `src/finer/llm/router.py` (new)
- `src/finer/prompts/registry.py` (new)
- `src/finer/prompts/f3_intent_extraction/system.j2` (new)
- `src/finer/prompts/f3_intent_extraction/user.j2` (new)
- `src/finer/model_config.py` (add ReasoningModelRegistry)
- `tests/test_model_router.py` (new)
- `tests/test_prompt_registry.py` (new)

**Forbidden files**
- `src/finer/api/routes/**`
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/pipeline/canonical_runner.py`

**What to do**
1. Add `ReasoningModelRegistry` to `model_config.py`: `mimo-v2.5-pro` → `MIMO_API_KEY`, base_url `https://token-plan-cn.xiaomimimo.com/v1`, `api_key_header="api-key"`, `api_key_scheme=None`, `max_tokens_field="max_completion_tokens"`
2. Create `src/finer/llm/router.py` — `ModelRouter`:
   - `call(prompt, *, task_type="text", system_prompt=None) -> str`
   - `call_json(prompt, *, system_prompt=None, response_model=None) -> dict`
   - Selects registry by task_type, picks model, calls `LLMClient`, auto-fallback on failure
3. Create `src/finer/prompts/registry.py` — `PromptRegistry`:
   - `render(template_name, **kwargs) -> str` using Jinja2
   - Templates have YAML frontmatter (name, stage, version, model_hint)
4. Migrate F3 prompt: `intent_prompt.py` → `prompts/f3_intent_extraction/system.j2` + `user.j2`

**Deliverables**
- `src/finer/llm/router.py`
- `src/finer/prompts/registry.py`
- `src/finer/prompts/f3_intent_extraction/system.j2`
- `src/finer/prompts/f3_intent_extraction/user.j2`
- `model_config.py` with ReasoningModelRegistry
- `tests/test_model_router.py`
- `tests/test_prompt_registry.py`

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/test_intent_extractor_canonical.py tests/test_canonical_f3_f4_f5_contract.py -q
.venv/bin/python -c "from finer.llm.router import ModelRouter; print('OK')"
.venv/bin/python -c "from finer.prompts.registry import PromptRegistry; r = PromptRegistry(); print(r.render('f3_intent_extraction/user', content_text='test', creator_name='test', creator_id='test', source_type='test', published_at='2026-01-01', known_entities='test'))"
rg -n "system_prompt" src/finer/llm/router.py | head -5
```

---

### T3 — F3 Intent LLM Integration

```text
Parallel line: T3 — F3 LLM
F-stage: F3 Intent
Input schema: ContentEnvelope, ModelRouter, PromptRegistry
Output schema: IntentExtractionResult with LLM extraction
Baseline: 9e0c878 (rebase on T1a merge)
```

**Owning files**
- `src/finer/extraction/intent_extractor.py` (modify LLMIntentExtractor)

**Forbidden files**
- `src/finer/api/routes/**`
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/pipeline/**`
- `src/finer/ingestion/**`

**What to do**
1. Modify `LLMIntentExtractor` to use `ModelRouter.call_json()` + `PromptRegistry.render()`
2. Replace old `LLMCallable` single-param signature with dependency injection of `ModelRouter` + `PromptRegistry`
3. Keep `RuleBasedIntentExtractor` as fallback
4. Verify with Cat Lord and Trader Ji fixtures

**Deliverables**
- `intent_extractor.py` using ModelRouter + PromptRegistry
- `tests/test_intent_extractor_llm.py` (new, LLM integration test)

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/test_intent_extractor_canonical.py -q
rg -n "LLMCallable" src/finer/extraction/intent_extractor.py
rg -n "system_prompt" src/finer/extraction/intent_extractor.py
```

---

### T6 — Golden Path Pipeline (F3→F5)

```text
Parallel line: T6 — Golden Path
F-stage: F3→F4→F5
Input schema: ContentEnvelope (from fixture)
Output schema: TradeAction with canonical_trace_status="canonical"
Baseline: 9e0c878 (rebase on T3 merge)
```

**Owning files**
- `src/finer/pipeline/golden_path.py` (new)
- `src/finer/pipeline/canonical_runner.py` (minor wiring)
- `tests/test_golden_path.py` (new)

**Forbidden files**
- `src/finer/api/routes/**`
- `src/finer/backtest/**`
- `src/finer_dashboard/**`
- `src/finer/ingestion/**`

**What to do**
1. Create `src/finer/pipeline/golden_path.py`: ContentEnvelope → F3 → F4 → F5 → TradeAction
2. Wire `run_canonical_from_artifacts()` to be API-callable
3. End-to-end with Cat Lord fixture: `canonical_trace_status == "canonical"`, all required fields non-empty
4. Write intermediate results to `data/F3_intents/`, `data/F4_policy_mapped/`, `data/F5_executed/`

**Deliverables**
- `src/finer/pipeline/golden_path.py`
- `tests/test_golden_path.py`
- Cat Lord fixture end-to-end verification

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/test_golden_path.py -q
rg -n "canonical_trace_status" src/finer/extraction/canonical_action_builder.py
ls data/F3_intents/ data/F4_policy_mapped/ data/F5_executed/ 2>/dev/null | head -10
```

---

### T7 — F8 Backtest E2E + Frontend Read-Only

```text
Parallel line: T7 — F8 E2E
F-stage: F8 Backtest
Input schema: TradeAction[] from T6
Output schema: BacktestResult with portfolio_snapshots, equity curve data
Baseline: 9e0c878 (rebase on T6 merge)
```

**Owning files**
- `src/finer/api/routes/backtest.py` (validate canonical TradeAction)
- `src/finer_dashboard/src/lib/f8-visualization.ts` (remove mock, render from real data)
- `tests/test_backtest_e2e.py` (new)

**Forbidden files**
- `src/finer/extraction/**`
- `src/finer/pipeline/**`
- `src/finer/ingestion/**`
- `src/finer_dashboard/src/lib/contracts.ts` (defer to later round)
- `src/finer_dashboard/src/lib/api-client.ts` (defer to later round)

**What to do**
1. Validate `POST /api/backtest/run` accepts canonical TradeAction (with `intent_id`, `policy_id`, `evidence_span_ids`, `execution_timing`)
2. End-to-end: Cat Lord TradeActions → backtest → BacktestResult → `data/F8_metrics/`
3. Frontend `f8-visualization.ts`: remove mock data, render equity curve from real `portfolio_snapshots`
4. Frontend read-only: no changes to contracts.ts / api-client.ts

**Deliverables**
- Backtest route validates canonical TradeAction fields
- `data/F8_metrics/` persistence confirmed
- `f8-visualization.ts` with no mock data
- E2E test: fixture TradeAction → BacktestResult with portfolio_snapshots

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/test_backtest.py tests/test_backtest_extended.py tests/test_backtest_materializer.py -q
rg -n "mock\|hard-coded\|sampleData\|demoData" src/finer_dashboard/src/lib/f8-visualization.ts
ls data/F8_metrics/ 2>/dev/null | head -5
```

---

### T8a — Legacy Dead Code Scan (Read-Only)

```text
Parallel line: T8a — Legacy Cleanup Scan
F-stage: cross-cutting (read-only scan)
Input schema: src/finer/extraction/extractor.py, enriched_extractor.py
Output schema: reference report + deletion recommendation
Baseline: 9e0c878
```

**Owning files**
- None (read-only scan)

**What to do**
1. Scan all references to `extractor.py` and `enriched_extractor.py`
2. Output reference report: file path, line number, active/dead status
3. Recommend deletion with risk assessment

**Forbidden**: all file modifications

**Acceptance commands**
```bash
rg -n "from finer.extraction.extractor|from finer.enriched_extractor|import extractor|import enriched_extractor" src/ tests/ scripts/
rg -n "ExtractedEvent|EnrichedExtractedEvent" src/ tests/
```

**Execution Record**
- T8a scan completed, report archived at `docs/specs/2026-05-t8a-legacy-scan-report.md`
- Deletion of `extractor.py`, `enriched_extractor.py`, `run_event_extraction.py` was explicitly approved by user (red-line rule: deletion requires human confirmation)
- Orchestrator executed deletion commit `066212cb` after user approval
- Owner separation: scan agent (read-only) produced report; orchestrator (with user approval) executed deletion

---

### T8b — F7 Opinions Mock Cleanup

```text
Parallel line: T8b — F7 Mock Cleanup
F-stage: F7 Timeline
Input schema: opinions.py mock fallbacks
Output schema: opinions.py with mock removed, failures → FinerError
Baseline: 9e0c878
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
1. Delete `_generate_mock_opinion()` function
2. Delete all mock fallback branches
3. Failures → `FinerError` canonical envelope with `request_id`, `stage="F7"`, `retryable`, `fix_hint`
4. Empty data → return empty list, not mock

**Deliverables**
- `opinions.py` with zero mock data generation
- All failure paths return canonical error envelope

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/ -q -k "opinion"
rg -n "_generate_mock_opinion|mock.*fallback|fallback.*mock" src/finer/api/routes/opinions.py
rg -n "FinerError\|request_id\|fix_hint" src/finer/api/routes/opinions.py
```

---

## Phase Summary

| Phase | Tasks | Dependency | Parallel? |
|---|---|---|---|
| Phase 0 | Line V | none | done ✓ |
| Phase 1 | T1a, T8a, T8b | none | yes (3 windows) |
| Phase 2 | T3 | T1a | no |
| Phase 3 | T6 | T3 | no |
| Phase 4 | T7 | T6 | no |

## Definition of Done

Round 3 is complete when:

1. Cat Lord fixture: ContentEnvelope → F5 TradeAction with `canonical_trace_status == "canonical"` → F8 BacktestResult with `portfolio_snapshots`
2. Trader Ji fixture: same pipeline produces valid results
3. Both equity curves render in frontend from real data (no mock)
4. Every F-stage intermediate result is written to its `data/F{N}_*/` directory for human review
5. All acceptance commands pass

---

## Open Issues / Known Gaps

### GAP-1: F8 canonical reject 测试名实不符（需补真实测试）

**位置**: `tests/test_backtest_canonical.py:197-224`
**现状**: 四个 `test_engine_rejects_*` 测试只是删除字段后断言字段缺失，**没有实际调用 BacktestEngine 或 API route 验证 reject 行为**。测试内部注释承认："The engine itself doesn't validate canonical fields — this test documents that upstream validation must gate inputs."
**风险**: 如果上游 validation 被绕过或 engine 接口变更，这些测试不会捕获回归。
**需要补充**:
1. API-level 测试：`POST /api/backtest/run` 传入缺少 `intent_id` / `policy_id` / `evidence_span_ids` / `execution_timing` 的 TradeAction，验证返回 422 或 canonical error envelope
2. Engine-level 测试（如 engine 新增 canonical validation）：验证 engine 直接拒绝 non-canonical input
3. 测试名应改为 `test_*_documents_gap` 或补上真正 reject 逻辑后恢复原名
**优先级**: Round 4

### GAP-2: F8 backtest record 不保留 F3→F5 trace fields

**位置**: `scripts/run_backtest_e2e.py:65-72` (`_raw_action_to_record`)
**现状**: canonical TradeAction 转换为 engine record 时，`intent_id`、`policy_id`、`evidence_span_ids`、`execution_timing` 被丢弃，只保留 `trade_action_id`、`ticker`、`direction`、`action_type`、`timestamp`、`kol_id`。
**影响**: 回测结果（trades.json）无法反查到 F3 Intent → F4 Policy → F5 TradeAction 的完整 trace chain。审计回溯时丢失关键 lineage。
**需要修复**:
1. `_raw_action_to_record` 保留 `intent_id`、`policy_id`、`evidence_span_ids`
2. BacktestEngine 输出的 trade record 携带这些 fields
3. `trades.json` 和 `backtest_result.json` 中可追溯到原始 canonical action
**优先级**: Round 4 F8 improvement
