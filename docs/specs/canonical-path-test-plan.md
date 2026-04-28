# Canonical Path Test Plan: F3 -> F4 -> F5

> Version: 1.0.0 | Created: 2026-04-28
> Purpose: Define the test coverage and acceptance criteria for the F3->F4->F5 canonical path.

## Test File

**File**: `tests/test_canonical_f3_f4_f5_contract.py` (45 tests, all pass)

## Architecture Covered

```
F1 ContentEnvelope
  -> F2 EvidenceSpan / QualityCard / TemporalAnchor / EntityAnchor
    -> F3 NormalizedInvestmentIntent (+evidence_span_ids)
      -> F4 PolicyMappingResult (+intent_id, +policy_id)
        -> F5 TradeAction (+intent_id, +policy_id, +evidence_span_ids)
```

## Test Classes and Coverage

### 1. TestCanonicalTraceContract (6 tests)
Validates the fundamental contract: when is a TradeAction canonical vs non-canonical.

| Test | Coverage |
|---|---|
| `test_full_canonical_trace_is_canonical` | intent_id + policy_id + evidence_span_ids -> canonical |
| `test_no_intent_id_is_non_canonical` | missing intent_id -> never canonical |
| `test_no_policy_id_is_non_canonical` | missing policy_id -> never canonical |
| `test_no_evidence_span_ids_partial` | missing evidence_span_ids status check |
| `test_no_trace_ids_at_all_is_non_canonical` | zero upstream IDs -> non_canonical |
| `test_canonical_trade_action_serialization` | trace fields survive JSON round-trip |

### 2. TestLegacyVsCanonical (4 tests)
Legacy direct extractor output compared against canonical path.

| Test | Coverage |
|---|---|
| `test_legacy_output_no_trace` | Legacy TA has no intent_id/policy_id |
| `test_legacy_output_still_valid_trade_action` | Legacy TA still satisfies minimum schema |
| `test_canonical_and_legacy_distinct_status` | Different trace_status values |
| `test_legacy_output_explicitly_labeled_non_canonical` | canonical_trace_status = "non_canonical" |

### 3. TestFullCanonicalChain (2 tests)
End-to-end F1 -> F5 chain construction with real Pydantic models.

| Test | Coverage |
|---|---|
| `test_f1_to_f3_with_evidence` | Build F1 envelope -> attach F2 evidence/entities/temporal -> produce F3 intents -> F4 policy -> F5 TradeAction. Verifies full ID chain. |
| `test_full_chain_round_trip_serialization` | All 4 models survive JSON round-trip |

### 4. TestKOLSamples (7 tests)
Real-style KOL content samples per acceptance checklist.

| Test | Coverage |
|---|---|
| `test_image_strategy_opinion_not_action` | Image strategy: opinion should not become buy |
| `test_chat_log_compound_signal` | Chat log: hold+add compound -> add, not open |
| `test_relative_time_unresolved` | Relative time ("上周"): temporal anchor is None |
| `test_relative_time_cannot_enter_backtest` | Unresolved time -> requires_manual_review or skip |
| `test_opinion_only_not_auto_buy` | "看好" -> watch_only, NOT open_position |
| `test_explicit_add_can_enter_add_position` | "加仓" -> add_position + small |
| `test_explicit_reduce_maps_to_reduce_position` | "减仓" -> reduce_position + small |

### 5. TestCatLordFixtureIntegration (3 tests)
Reuses existing cat lord fixtures from `tests/fixtures/kol/`.

| Test | Coverage |
|---|---|
| `test_v1_intents_have_evidence_ids` | All V1 intents from fixture have evidence_span_ids |
| `test_v1_intents_usable_for_f4_policy` | Each V1 intent can produce valid F4 PolicyMappingResult |
| `test_v1_to_f4_to_f5_bridge` | V1 intent -> F4 policy -> F5 canonical TradeAction bridge |

### 6. TestF3F4F5Boundaries (5 tests)
Hard boundaries between F3/F4/F5 stages.

| Test | Coverage |
|---|---|
| `test_f3_must_not_contain_position_percentage` | F3 has no position_size_pct, target_price, etc. |
| `test_f4_has_hints_not_facts` | F4 has position_sizing_hint (string), not position_size_pct (float) |
| `test_f4_must_not_modify_direction` | F4 has no direction field (inherits from F3) |
| `test_f5_has_action_chain_not_f4` | ActionChain only in F5 |
| `test_f3_intent_has_evidence_not_action_chain` | F3 has evidence_span_ids, not action_chain |

### 7. TestF3Acceptance (4 tests)
Per `docs/specs/f-stage-contracts.md` F3 Acceptance Checklist.

| Test | Coverage |
|---|---|
| `test_opinion_produces_watch_not_action` | "我看好" -> opinion, position_delta_hint=none |
| `test_explicit_add_produces_action` | "我加仓" -> explicit_action, position_delta_hint=add |
| `test_every_intent_has_evidence` | Every Intent has >= 1 evidence_span_id |
| `test_ambiguous_samples_preserve_flags` | Ambiguity flags preserved, not discarded |

### 8. TestF4Acceptance (4 tests)
Per `docs/specs/f-stage-contracts.md` F4 Acceptance Checklist.

| Test | Coverage |
|---|---|
| `test_policy_mapping_has_intent_id` | Every PolicyMappingResult references intent_id |
| `test_policy_mapping_has_policy_id_auto_generated` | Auto-generated policy_id is non-empty |
| `test_same_position_delta_differs_by_style` | Same "加仓" -> different sizing/holding per style |
| `test_opinion_no_position_hint` | position_delta_hint=none -> no position generated |

### 9. TestF5Acceptance (4 tests)
Per `docs/specs/f-stage-contracts.md` F5 Acceptance Checklist.

| Test | Coverage |
|---|---|
| `test_canonical_action_has_intent_id` | Every canonical TA has intent_id |
| `test_canonical_action_has_policy_id` | Every canonical TA has policy_id |
| `test_canonical_action_has_evidence_span_ids` | Every canonical TA has >= 1 evidence_span_id |
| `test_non_canonical_actions_not_backtest_ready` | Non-canonical TA flagged, not backtest-ready |

### 10. TestBacktestReadiness (3 tests)
F8 Backtest readiness requirements.

| Test | Coverage |
|---|---|
| `test_canonical_with_effective_time_is_backtest_ready` | Has effective_trade_at |
| `test_no_effective_time_is_backtest_incomplete` | Missing effective_trade_at blocks backtest |
| `test_relative_time_unresolved_no_effective` | Relative time -> no effective_trade_at |

### 11. TestBatchIntegration (2 tests)
Container-level statistics.

| Test | Coverage |
|---|---|
| `test_intent_batch_stats` | IntentBatch computes actionable_count, review_required_count |
| `test_policy_mapping_batch_stats` | PolicyMappingBatch computes total_mappings, review_required_count |

### 12. TestDataLineage (1 test)
Full ID chain traceability from content to TradeAction.

| Test | Coverage |
|---|---|
| `test_id_chain_traceability` | content_id -> envelope_id -> block_id -> evidence_span_id -> intent_id -> policy_id -> trade_action_id |

## Running Tests

```bash
# Canonical path tests only
pytest tests/test_canonical_f3_f4_f5_contract.py -v

# Full suite (canonical + existing + cat lord)
pytest tests/test_canonical_f3_f4_f5_contract.py \
      tests/test_cat_lord_pipeline_integration.py \
      tests/test_cat_lord_fixture_contract.py \
      tests/test_cat_lord_image_fixture_contract.py \
      tests/test_schemas.py \
      tests/test_investment_intent_schema.py \
      tests/test_policy_schema.py \
      tests/test_policy_mapper.py \
      tests/test_intent_extractor.py \
      tests/test_intent_extractor_canonical.py \
      -v
```

## Design Principles

1. **No real LLM/API calls**: All data constructed via Pydantic models. Mock intents and policies conform to real schemas.
2. **Real schemas only**: Every test object is a valid Pydantic model instance (not raw dicts).
3. **Legacy comparison**: Legacy direct extractor output is tested independently from canonical path output.
4. **Cat lord reuse**: Existing `tests/fixtures/kol/` fixtures are consumed where appropriate.

## Missing Business Implementation (Contract-Only)

These gaps exist in business code. Tests already cover the contracts:

| Gap | Test Coverage | Status |
|---|---|---|
| F3 LLM-based intent extractor (Instructor/LLM) | `tests/test_intent_extractor_canonical.py` | Schema defined, rule-based only |
| F4 Policy Mapper (5-layer policy stack) | `tests/test_policy_schema.py`, `tests/test_policy_mapper.py` | Schema + GlobalBase MVP exist, StyleArchetype/KOLPersona missing |
| F5 Canonical constructor (intent_id -> TradeAction) | `tests/test_canonical_f3_f4_f5_contract.py` | Contract enforced; no pipeline integrator |
| F2 -> F3 gate enforcement in pipeline | `tests/test_canonical_f3_f4_f5_contract.py` (F2 section) | Schema defined; pipeline orchestration missing |
| F8 backtest readiness check (effective_trade_at) | `tests/test_canonical_f3_f4_f5_contract.py` (TestBacktestReadiness) | BacktestEngine exists; pipeline not checking effective_trade_at |
