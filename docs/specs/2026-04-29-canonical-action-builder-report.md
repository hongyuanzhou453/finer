# CanonicalActionBuilder Implementation Report

**Date**: 2026-04-29
**Agent**: Agent 6 — Canonical F3→F4→F5 Constructor

## Overview

Implemented `CanonicalActionBuilder`, the canonical constructor that enforces the F3 Intent → F4 Policy → F5 TradeAction path. Every `TradeAction` produced by this builder carries full lineage (`intent_id`, `policy_id`, `evidence_span_ids`, `execution_timing`) and has `canonical_trace_status == "canonical"`.

## Changes

| File | Type | Description |
|------|------|-------------|
| `src/finer/extraction/canonical_action_builder.py` | NEW | CanonicalActionBuilder class + error types |
| `src/finer/extraction/__init__.py` | MODIFY | Added imports for CanonicalActionBuilder and error types |
| `tests/test_canonical_action_builder.py` | NEW | 38 tests covering success, rejection, type guards, mapping |
| `docs/specs/2026-04-29-canonical-action-builder-report.md` | NEW | This report |

## Interface Design

### `CanonicalActionBuilder.build()`

```python
def build(
    self,
    intent: NormalizedInvestmentIntent,         # F3
    policy_mapped_intent: PolicyMappedIntent,    # F4
    evidence_span_ids: List[str],               # F2
    execution_timing: ExecutionTiming,           # Timing policy
) -> TradeAction:
```

**Inputs** — only structured Pydantic models, never raw text:
- `NormalizedInvestmentIntent` from F3 (target, direction, intent_id, confidence)
- `PolicyMappedIntent` from F4 (policy_id, action_hint, sizing/holding hints)
- `evidence_span_ids` from F2 (at least one required)
- `ExecutionTiming` from timing policy (publication, decision, executable times)

**Output** — `TradeAction` with:
- `canonical_trace_status == "canonical"`
- `intent_id`, `policy_id`, `evidence_span_ids` populated
- `execution_timing` set directly on the TradeAction
- Policy hints preserved in `metadata` for downstream consumers

### Error Hierarchy

```
CanonicalBuildError (ValueError)
├── MissingIntentIdError
├── MissingPolicyIdError
├── EmptyEvidenceSpanIdsError
└── MissingExecutionTimingError
```

Type mismatches raise `TypeError` with explicit messages stating "does NOT accept raw text."

## Action Chain Mapping Rules

| action_hint (F4) | ActionType (F5) | Validation Status | Notes |
|---|---|---|---|
| `consider_buy` | BUY_AND_HOLD | PENDING (review) | Pending human review |
| `consider_sell` | CLOSE_LONG | PENDING (review) | Pending human review |
| `watch_only` | WATCH | PENDING | |
| `review_required` | WATCH | UNDER_REVIEW | `requires_manual_review=True` |
| `open_position` | LONG | PENDING | |
| `add_position` | LONG | PENDING | |
| `close_position` | CLOSE_LONG | PENDING | |
| `watch_or_no_trade` | WATCH | PENDING | Extended |
| `avoid_or_watch_risk` | WATCH | PENDING | Extended |
| `reduce_position` | CLOSE_LONG | PENDING | Extended |
| `hold_position` | HOLD | PENDING | Extended |
| (unknown) | WATCH | UNDER_REVIEW | Fallback with warning note |

## Key Design Decisions

1. **ExecutionTiming on TradeAction directly** — Agent 4 added `execution_timing` as an optional field on `TradeAction` and updated the `canonical_trace_status` validator to require it. The builder passes it directly (not just in metadata) so the validator produces "canonical" status.

2. **Confidence = min(intent, policy)** — Uses the lower of F3 intent confidence and F4 policy mapping confidence. Conservative approach: if either layer is uncertain, the TradeAction reflects that.

3. **consider_buy/consider_sell not in ACTION_HINT_LITERAL** — These hints appear in the spec requirements but are not valid `ACTION_HINT_LITERAL` values (the policy mapper doesn't produce them). They're mapped internally via `_resolve_action_chain()` and tested via that method directly, not through `PolicyMappedIntent`.

4. **SourceInfo.evidence_text uses intent_id** — Since the builder MUST NOT accept raw text, `evidence_text` is set to `"[canonical] intent_id=..."` rather than any source text. The actual evidence text lives in the F2 EvidenceSpan records referenced by `evidence_span_ids`.

5. **No LLM calls** — All mapping is deterministic rule-based lookup. The builder is stateless and safe to reuse.

## Integration Notes

- **F4 PolicyMapper** → produces `PolicyMappedIntent` with `action_hint` — consumed directly by the builder
- **F2 EvidenceSpan** → IDs passed as `evidence_span_ids` list
- **Timing policy** (Agent 3) → produces `ExecutionTiming` — consumed directly
- **Legacy extractor** (`trade_action_extractor.py`) — NOT called, NOT modified. The builder is an alternative path for canonical actions.
- **canonical_trace_status validator** (Agent 4) — requires `execution_timing` field on TradeAction for "canonical" status. The builder sets this.

## Test Results

```
tests/test_canonical_action_builder.py       38 passed
tests/test_canonical_f3_f4_f5_contract.py    45 passed
─────────────────────────────────────────────
Total                                         83 passed
```

Test categories:
- **TestBuildSuccess** (5 tests) — happy path with all required inputs
- **TestBuildRejection** (4 tests) — missing intent_id, policy_id, evidence_span_ids, execution_timing
- **TestTypeGuards** (6 tests) — rejects strings, dicts for all input parameters
- **TestActionChainMapping** (12 tests) — all action_hint mappings including extended
- **TestDirectionMapping** (5 tests) — bullish/bearish/neutral/mixed/unknown
- **TestConfidenceHandling** (2 tests) — min of intent and policy confidence
- **TestReviewFlag** (2 tests) — review flag propagation
- **TestRationale** (1 test) — rationale contains key information
- **TestSerialization** (1 test) — JSON round-trip

## Open Issues

- The contract test (`test_canonical_f3_f4_f5_contract.py`) has a flaky test (`test_v1_to_f4_to_f5_bridge`) that occasionally fails when run in batch but passes in isolation. Likely a fixture file race condition from concurrent agent writes.
- `consider_buy` / `consider_sell` from the spec are not in `ACTION_HINT_LITERAL`. If the policy mapper needs to produce these, `ACTION_HINT_LITERAL` in `schemas/policy.py` must be extended first.
