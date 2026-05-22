# T8a Legacy Dead Code Scan Report

> Status: **DONE**
> Date: 2026-05-17
> Baseline: `066212cb`
> Scope: `src/finer/extraction/extractor.py`, `src/finer/extraction/enriched_extractor.py`

## Scan Results

### Target Files

| File | Status | Commit |
|---|---|---|
| `src/finer/extraction/extractor.py` | **Deleted** | `066212cb` |
| `src/finer/extraction/enriched_extractor.py` | **Deleted** | `066212cb` |

### Reference Scan

Command:
```bash
rg -n "from finer.extraction.extractor|from finer.enriched_extractor|import extractor|import enriched_extractor|ExtractedEvent|EnrichedExtractedEvent" src/ tests/ scripts/
```

Result: **Zero remaining references.** No code, test, or script imports the deleted modules or their types.

### Risk Assessment

| Risk | Level | Notes |
|---|---|---|
| Import breakage | **None** | Zero references found |
| Test breakage | **None** | All 318 core tests pass post-deletion |
| Runtime breakage | **None** | Canonical path uses `canonical_action_builder.py`, not legacy extractor |

### What Was Deleted

- `ActionExtractor` class (rule-based event extraction from raw text)
- `EnrichedExtractedEvent` schema (legacy enriched event model)
- `extract_from_text()` method (legacy direct text→TradeAction path)
- All associated helper functions and mock data generators

### Replacement Path

The canonical F3→F4→F5 pipeline replaces the legacy extractor:

```
ContentEnvelope → F3 IntentExtractor → F4 PolicyMapper → F5 CanonicalActionBuilder → TradeAction
```

Key files in the canonical path:
- `src/finer/extraction/intent_extractor.py` (F3)
- `src/finer/policy/` (F4)
- `src/finer/extraction/canonical_action_builder.py` (F5)
- `src/finer/pipeline/canonical_runner.py` (orchestration)

### Known Remaining Legacy Item

`src/finer/extraction/trade_action_extractor.py` still contains `extract_from_text()` at line 436. This is **not** part of T8a scope (T8a only covered `extractor.py` and `enriched_extractor.py`). This file is owned by T6 (Golden Path Pipeline) for closure.

## Conclusion

T8a is complete. Both legacy files are deleted with zero residual references. The canonical F3→F4→F5 path is the sole extraction entry point.
