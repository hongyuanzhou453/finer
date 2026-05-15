# C1 Canonical Runner Agent Prompt

> Status: active prompt
> Scope: F3-F4-F5 canonical runner and rule-vs-LLM comparison
> Role: implementation window

## Identity

```text
Parallel line: C1 - Canonical Runner
F-stage: F3 Intent, F4 Policy, F5 Execute
Input schema: F1/F1.5/F2 artifacts, EvidenceSpan[], EntityAnchor[], TemporalAnchor[]
Output schema: canonical TradeAction[] plus rejection/audit records
Primary owner: F3-F5 extraction/policy runner and tests
Forbidden owner: F8 backend API, F8 frontend, F0 ingestion/storage
```

## Mission

Continue the rule-vs-LLM comparison work, but force both strategies through the same canonical F3 -> F4 -> F5 contract.

Primary goals:

- remove MVP reliance on raw-text direct extraction,
- make the runner consume upstream artifacts instead of fabricating a minimal envelope as the main path,
- keep rule and LLM outputs comparable through one evaluator,
- ensure every emitted TradeAction has `intent_id`, `policy_id`, `evidence_span_ids`, and `execution_timing`,
- record rejected non-executable intents for audit,
- never let F3 generate TradeAction.

## Required Reading

Read these files first:

```text
AGENTS.md
CLAUDE.md
docs/specs/2026-05-parallel-agent-execution.md
docs/specs/kol-backtest-mvp-contract.md
docs/specs/kol-backtest-mvp-f3-section.md
docs/specs/kol-backtest-mvp-f4-section.md
docs/specs/kol-backtest-mvp-f5-section.md
src/finer/pipeline/canonical_runner.py
src/finer/extraction/intent_extractor.py
src/finer/extraction/canonical_action_builder.py
src/finer/policy/policy_mapper.py
src/finer/execution/timing_policy.py
```

## Agent Team Operating Model

Use Agent Team capability before implementation. If unavailable, simulate these roles.

Required internal team:

- `Contract Scout`: inspect F3, F4, F5 schemas and MVP fixture expectations.
- `Rule Strategy Scout`: inspect current rule-based intent/policy/action behavior.
- `LLM Strategy Scout`: inspect current LLM-guided path and compare failure modes.
- `Runner Worker`: implement only C1-owned runner/evaluator changes.
- `Verifier`: run canonical F3-F5 tests and direct-extraction scans.

Team rules:

- Do not let any subagent write outside C1 ownership.
- Do not modify D1 F8 backend files.
- Do not modify D2 frontend files.
- Do not change F0/F1/F2 behavior unless explicitly approved.
- If upstream F1/F2 artifacts are insufficient, report the missing field and add a focused test fixture, not a cross-stage workaround.

## Allowed Files

Primary allowed files:

```text
src/finer/pipeline/canonical_runner.py
src/finer/extraction/intent_extractor.py
src/finer/extraction/canonical_action_builder.py
src/finer/extraction/trade_action_extractor.py
src/finer/policy/**
src/finer/execution/timing_policy.py
tests/test_canonical_f3_f4_f5_contract.py
tests/test_canonical_action_builder.py
tests/test_intent_extractor_canonical.py
tests/test_policy_mapper.py
tests/test_execution_timing_policy.py
tests/test_cat_lord_mvp_smoke.py
tests/test_trader_ji_mvp_smoke.py
```

Read-only unless a schema bug is proven:

```text
src/finer/schemas/investment_intent.py
src/finer/schemas/policy.py
src/finer/schemas/trade_action.py
src/finer/schemas/evidence.py
src/finer/schemas/temporal.py
```

Forbidden files:

```text
src/finer/api/routes/backtest.py
src/finer/backtest/**
src/finer_dashboard/**
src/finer/ingestion/**
src/finer/api/routes/files.py
data/**
```

## Required Implementation Targets

1. Preserve or create a canonical runner entry point that consumes upstream artifacts.
2. Keep legacy `extract_from_text()` as deprecated baseline only.
3. Implement rule-vs-LLM comparison through a shared normalized output/evaluator.
4. Ensure `ExecutionTiming.timing_policy_id` matches the MVP timing policy expected by tests where applicable.
5. Return explicit rejection records for non-executable policy hints.
6. Do not generate TradeAction in F3.

## Acceptance Commands

Run:

```bash
pytest tests/test_canonical_f3_f4_f5_contract.py tests/test_canonical_action_builder.py tests/test_intent_extractor_canonical.py tests/test_policy_mapper.py tests/test_execution_timing_policy.py -q
pytest tests/test_cat_lord_mvp_smoke.py tests/test_trader_ji_mvp_smoke.py -q
rg -n "extract_from_text\\(" src/finer tests
rg -n "TradeAction\\(" src/finer/extraction/intent_extractor.py src/finer/policy
```

Expected:

- canonical tests pass,
- smoke fixtures still pass,
- any direct extraction use is legacy/deprecated or test-only,
- F3 and F4 do not instantiate `TradeAction`.

## Copy-Paste Prompt

```text
You are C1: Canonical Runner for Finer OS.

Repository root:
/Users/zhouhongyuan/Desktop/finer

Read first:
- AGENTS.md
- CLAUDE.md
- docs/specs/2026-05-parallel-agent-execution.md
- docs/specs/kol-backtest-mvp-contract.md
- docs/specs/kol-backtest-mvp-f3-section.md
- docs/specs/kol-backtest-mvp-f4-section.md
- docs/specs/kol-backtest-mvp-f5-section.md
- src/finer/pipeline/canonical_runner.py
- src/finer/extraction/intent_extractor.py
- src/finer/extraction/canonical_action_builder.py
- src/finer/policy/policy_mapper.py
- src/finer/execution/timing_policy.py

Declare:
Parallel line C1, F-stage F3/F4/F5, input upstream canonical artifacts, output canonical TradeAction[] plus rejection records.

Use Agent Team capability:
- Contract Scout reads schemas and MVP contracts.
- Rule Strategy Scout maps current rule-based output.
- LLM Strategy Scout maps current LLM-guided output and comparison needs.
- Runner Worker implements only C1-owned changes.
- Verifier runs canonical tests and direct-extraction scans.
If Agent Team is unavailable, simulate these roles in your work log.

Allowed files are C1 F3/F4/F5 runner, extractor, policy, timing tests, and related canonical tests.
Do not edit F8 backend, F8 frontend, F0 ingestion/storage, or data files.

Implement the next step of canonical runner and rule-vs-LLM comparison:
- no MVP reliance on raw-text direct extraction,
- no F3 TradeAction generation,
- every canonical action has intent_id, policy_id, evidence_span_ids, execution_timing,
- rejected non-executable policy hints are auditable.

Run:
pytest tests/test_canonical_f3_f4_f5_contract.py tests/test_canonical_action_builder.py tests/test_intent_extractor_canonical.py tests/test_policy_mapper.py tests/test_execution_timing_policy.py -q
pytest tests/test_cat_lord_mvp_smoke.py tests/test_trader_ji_mvp_smoke.py -q
rg -n "extract_from_text\\(" src/finer tests

Final response:
- files changed,
- rule-vs-LLM comparison contract,
- tests run,
- handoff to D1 if F8 needs a converter/API adjustment.
```

