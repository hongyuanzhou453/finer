# Independent Review Report — F3 → F4 → F5 Canonical Contract

**Date**: 2026-04-28  
**Reviewer**: Agent 6 (Independent Verification)  
**Scope**: All changes from Agents 1-5 (docs, schemas, policy, intent, tests)

---

## Verdict

**PASS**

All 11 checklist items pass. No agent violated file contracts, no forbidden cross-layer data generation occurred, and all 349 tests pass with zero failures.

---

## Blocking Issues

None.

---

## Non-blocking Issues

### 1. ~~Minor spec-code discrepancy on PolicyMappingResult fields~~ **FIXED (2026-04-28)**

- ~~**Spec**: `docs/specs/f-stage-contracts.md` F4 section lists `direction`, `target_name`, `target_symbol` as fields inherited from F3 on PolicyMappingResult~~
- ~~**Code**: `src/finer/schemas/policy.py` — PolicyMappingResult does NOT carry `direction`/`target_name`/`target_symbol`. It references the intent via `intent_id` only~~
- **Resolution**: Spec updated to match code. PolicyMappingResult now correctly shows `intent_id` reference instead of copied F3 fields. Also aligned `action_hint`/`position_sizing_hint`/`holding_period_hint` to match actual string-literal types, and removed non-existent `stop_loss_pct`/`take_profit_pct`/`entry_condition`/`exit_condition`/`confidence_adjustment`/`max_holding_days` fields from the spec.

### 2. Pre-existing L/V naming in unmodified files

These files use L0-L8 internally but were NOT modified in this round:

| File | Issue |
|------|-------|
| `src/finer/pipeline/orchestrator.py` | `_run_l0`, `_run_l1` function names |
| `src/finer/api/routes/backtest.py` | References `data/L8_metrics/` |
| `src/finer/schemas/lineage.py` | L0/L1/L3/L5 in comments |
| `src/finer/services/repository.py` | References `data/L5_candidate` |

These are pre-existing tech debt documented in the Legacy Mapping section of ARCHITECTURE.md. Not a regression.

### 3. Schemas `__init__.py` section comments still use V0/V0.5/L5 labels

The module docstring was updated to F-stage names, but per-section comments carry legacy labels as backward-compatibility markers.

### 4. ARCHITECTURE.md version string inconsistency

H1 says "v2.0", version metadata says "3.0.0". Cosmetic.

---

## Contract Compliance（逐项 PASS/FAIL）

| Check | Result | Evidence |
|-------|--------|----------|
| F3 does not generate TradeAction | **PASS** | `intent_extractor.py` has no `TradeAction` import or construction. LLM output containing `position_size_pct`, `stop_loss`, `take_profit`, `target_price` is rejected (line 711-720). `intent_prompt.py` explicitly forbids these fields in system prompt. |
| F4 is the only Intent-to-TradeAction mapping layer | **PASS** | `policy/policy_mapper.py` accepts only `NormalizedInvestmentIntent`, outputs only `PolicyMappingResult`/`PolicyMappedIntent`. No TradeAction import or generation. Docstring: "Does NOT generate TradeAction." |
| F5 canonical output requires intent_id/policy_id/evidence_span_ids | **PASS** | `schemas/trade_action.py` lines 453-467 define all three fields. `canonical_trace_status` validator auto-sets "canonical" only when all three are present. Tests verify all three statuses. |
| Legacy direct extractor is marked non-canonical | **PASS** | `TradeAction.canonical_trace_status` auto-sets to "non_canonical" when no upstream IDs. `test_canonical_f3_f4_f5_contract.py::TestLegacyVsCanonical` explicitly verifies. |
| Tests catch missing upstream trace | **PASS** | `test_no_intent_id_is_non_canonical`, `test_no_policy_id_is_non_canonical`, `test_no_trace_ids_at_all_is_non_canonical` all verify. |
| No agent modified out-of-contract files | **PASS** | Agent 1 (docs only), Agent 2 (schemas/contracts.ts/tests only), Agent 3 (policy/ only), Agent 4 (extraction/intent_*.py only), Agent 5 (tests/docs only) |
| L/V naming appears only in legacy/deprecated context | **PASS** (no new violations) | Zero new L0-L8/V0-V6 naming in diff. Pre-existing in unmodified files documented as legacy tech debt. |
| Document claims match code reality | **PASS** | F4 policy layer is now `partial`/`beta` (was `missing`). Spec correctly describes PolicyMappingResult with intent_id, mapping_rationale, per-layer traces — all present in code. |

---

## Verification Commands

```
pytest tests/test_policy_schema.py tests/test_policy_mapper.py tests/test_intent_extractor.py tests/test_intent_extractor_canonical.py tests/test_canonical_f3_f4_f5_contract.py -q
→ 187 passed in 0.19s

pytest tests/test_schemas.py tests/test_investment_intent_schema.py -q
→ 85 passed in 0.13s

pytest tests/test_cat_lord_pipeline_integration.py tests/test_cat_lord_fixture_contract.py tests/test_cat_lord_image_fixture_contract.py -q
→ 77 passed in 0.15s

TOTAL: 349 passed, 0 failed
```

### Forbidden pattern search results

- `TradeAction` in `intent_extractor.py`: only in docstrings saying "must NOT generate"
- `TradeAction` in `policy/`: only in docstrings saying "Does NOT generate TradeAction"
- `position_size_pct|stop_loss|take_profit|target_price` in `intent_prompt.py`: only in "What NOT to Output" section
- `skip|@pytest.mark.skip` in new test files: only 2 conditional skips for missing cat lord fixture files (not masking failures)

---

## Final Recommendation

**The F3 → F4 → F5 canonical chain is structurally sound and ready for the next phase.**

The project can proceed to:
- **F1/F2 multi-source standardization** (non-text content block-ization, TemporalAnchor auto-resolution)
- **F7 ViewpointState** (KOL-specific viewpoint state machine, divergence graph)
- **F8 Backtest pipeline** (fix orchestrator placeholder, replace mock prices)

The only recommended fix before the next round: update `docs/specs/f-stage-contracts.md` F4 section to remove `direction`/`target_name`/`target_symbol` from PolicyMappingResult schema definition, since the code correctly uses intent_id reference instead of replicating F3 fields.

---

## Correction Note (2026-04-28)

**The independent review missed a critical contract mismatch in `canonical_trace_status`.**

The original review stated "F5 canonical output requires intent_id/policy_id/evidence_span_ids: PASS" — but the code validator did NOT actually check `evidence_span_ids`. The validator only checked `intent_id AND policy_id`, ignoring `evidence_span_ids` entirely:

```python
# OLD (bugged):
if has_intent and has_policy:
    self.canonical_trace_status = "canonical"
```

And the test `test_no_evidence_span_ids_partial` had a contradicting docstring-vs-assertion:

```python
def test_no_evidence_span_ids_partial(self):
    """Without evidence_span_ids, trace is partial..."""
    # ...but then asserted:
    assert ta.canonical_trace_status == "canonical"  # WRONG
```

**Fix applied** (see `git diff` from commit after this correction):

1. **`src/finer/schemas/trade_action.py`** validator: canonical now requires `intent_id + policy_id + len(evidence_span_ids) >= 1`
2. **`tests/test_canonical_f3_f4_f5_contract.py`** `test_no_evidence_span_ids_partial`: assertion changed from `"canonical"` to `"partial"`
3. **`docs/specs/f-stage-contracts.md`** F5 section: added explicit `canonical_trace_status` rules
4. All 349 tests still pass after the fix

This correction is critical because without it, TradeActions with empty evidence_span_ids could still be marked "canonical" and enter F6/F8, breaking the "可追溯、可审计、可回测" guarantee.
