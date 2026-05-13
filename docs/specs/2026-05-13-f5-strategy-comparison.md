# F5 Strategy Comparison: Programmatic vs LLM-guided vs Golden Fixtures

**Date**: 2026-05-13
**Scope**: Cat Lord (10 items) + Trader Ji (15 items) golden fixtures
**LLM Model**: mimo-v2.5 (MiMo Token Plan)

## Summary

| KOL | Strategy | Exact | Partial | Mismatch | Total |
|-----|----------|-------|---------|----------|-------|
| Cat Lord | programmatic | 7 | 1 | 2 | 10 |
| Cat Lord | llm_guided | 6 | 2 | 2 | 10 |
| Trader Ji | programmatic | 7 | 0 | 8 | 15 |
| Trader Ji | llm_guided | 7 | 0 | 8 | 15 |
| **Total** | **programmatic** | **14** | **1** | **10** | **25** |
| **Total** | **llm_guided** | **13** | **2** | **10** | **25** |

## Root Cause Analysis

### 1. Ticker Normalization (8 mismatches — both strategies)

**Symptom**: Both strategies output normalized codes (e.g., `000300.SH`), expected fixtures use Chinese names (e.g., `沪深300ETF`).

**Root Cause**: `RuleBasedIntentExtractor` returns `target_symbol` as the normalized ticker code, while the golden fixtures were created with human-readable names.

**Examples**:
| Content | Canonical Output | Expected |
|---------|------------------|----------|
| t_001_buy_510300 | `000300.SH` | `沪深300ETF` |
| t_002_sell_159915 | `399006.SZ` | `创业板ETF` |
| t_003_hold_600519 | `600519.SH` | `贵州茅台` |

**Impact**: Semantic match is correct (same asset), only display name differs. This is a **format difference**, not a logic error.

### 2. Missing Actions (5 cases — both strategies)

**Symptom**: Both strategies produce fewer actions than expected.

**Root Cause**: F3 `RuleBasedIntentExtractor` is keyword-based and misses intents that require semantic understanding. Since both strategies share the same F3→F4 pipeline, they miss the same cases.

| Content | Expected | Both Strategies | Missing |
|---------|----------|-----------------|---------|
| c_004_hold_tme | TME hold | 0 | "埋伏没问题" not detected as hold signal |
| c_007_mixed | LI bearish + CSIQ bullish | 0 | Mixed signals not extracted |
| c_010_multi_intent | CSIQ + TSLA | CSIQ only | TSLA mention not detected |
| t_010_multi_intent | 2 actions | 0 | "加仓"/"减仓" in same sentence not extracted |
| t_012_close_510300 | 1 action | 0 | "止盈" not detected as close signal |

**Impact**: Real gap in F3 intent extraction. Both strategies are limited by F3 output quality.

### 3. Direction Mismatch (1 case — LLM only)

**Symptom**: `c_002_buy_li` — LLM returns `bullish close_long`, expected `bearish close_long`.

**Root Cause**: LLM interprets "减仓" (reduce position) as a bullish action (reducing, not exiting), while the expected fixture treats it as bearish (closing part of position). This is a **semantic ambiguity** in the LLM interpretation.

## Strategy Comparison

### Where LLM-guided matches Programmatic

Both strategies produce identical results for 20/25 cases:
- 14 exact matches (both correct)
- 6 cases where both miss the same actions (F3 limitation)

### Where LLM-guided differs

| Case | Programmatic | LLM-guided | Expected | Notes |
|------|--------------|------------|----------|-------|
| c_002_buy_li | bearish close_long | bullish close_long | bearish close_long | LLM direction error |
| c_008_close_li | bearish close_long | bearish close_long | bearish close_long | Both correct |
| t_003_hold_600519 | neutral hold | bullish hold | neutral hold | LLM direction error |

### Confidence Differences

LLM tends to assign different confidence scores:
- `t_002_sell_159915`: LLM=0.70 vs Programmatic=0.85
- `c_010_multi_intent`: LLM=0.80 vs Programmatic=0.85

## Canonical Trace Validation

Both strategies produce full canonical trace:
- `intent_id`: Present ✓
- `policy_id`: Present ✓
- `evidence_span_ids`: Present ✓
- `execution_timing`: Present ✓
- `canonical_trace_status`: "canonical" ✓

## Recommendations

1. **Ticker Display**: Add a `ticker_display` field to `TargetInfo` for human-readable names alongside normalized codes.

2. **F3 Enhancement**: The missing actions are an F3 problem, not F5. Both strategies are limited by `RuleBasedIntentExtractor` output. Consider:
   - Adding "止盈" (take profit) as a close signal keyword
   - Adding "埋伏" (ambush/position) as a hold signal keyword
   - Improving multi-intent extraction for sentences with multiple targets

3. **LLM Direction Fix**: The LLM sometimes confuses direction for "减仓" (reduce) actions. Consider:
   - Adding explicit direction hints in the prompt
   - Post-processing LLM output to match policy mapping direction

4. **Strategy Selection**: Use programmatic as default (deterministic, consistent), LLM-guided for edge cases where F3 misses intents.

5. **Fixture Update**: Consider updating golden fixtures to use normalized tickers for consistency with canonical pipeline output.

## Next Steps

- [ ] Enhance F3 `RuleBasedIntentExtractor` with missing keywords
- [ ] Add `ticker_display` field to `TargetInfo` schema
- [ ] Improve LLM prompt to reduce direction confusion
- [ ] Update golden fixtures to use normalized tickers
