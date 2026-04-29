# F1.5 Topic Assembler Implementation Report

**Date**: 2026-04-29
**Agent**: Agent 3 — Topic Assembler
**Status**: Complete

## Overview

Implemented a deterministic keyword-based `TopicAssembler` that groups `ContentBlock[]` into `TopicBlock[]` for F1.5 (Topic Assembly). No LLM calls — pure rule-based assembly.

## Files Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/finer/parsing/topic_assembler.py` | **CREATE** | Core assembler with keyword rules and merging logic |
| `src/finer/parsing/__init__.py` | MODIFY | Added `TopicAssembler` export |
| `tests/test_topic_assembler.py` | **CREATE** | 25 tests covering all requirements |
| `docs/specs/2026-04-29-f1-5-topic-assembler-report.md` | **CREATE** | This report |

Note: `src/finer/schemas/topic_block.py` was already created by Agent 1. No schema modifications were needed.

## Algorithm Description

### Input
- `ContentEnvelope` with ordered `ContentBlock[]`

### Processing Steps

1. **Keyword Scanning**: Each block's text is matched against 5 topic rules using compiled regex patterns:
   - **泡泡玛特**: `泡泡玛特|POP MART|9992.HK|9992HK` (confidence: 0.95)
   - **巴菲特**: `巴菲特|Buffett|伯克希尔|股东信|价值投资` (confidence: 0.85)
   - **老铺黄金**: `老铺黄金|老铺` (confidence: 0.75, short keyword flag)
   - **卫星化学**: `卫星化学|卫星` (confidence: 0.75, short keyword flag)
   - **新能源**: `新能源|NEV|蔚来|小鹏|理想|理想汽车|比亚迪|CATL|宁德时代` (confidence: 0.90)

2. **Best-Match Selection**: If multiple rules match a block, the highest-confidence rule wins. Ties broken by rule order (first defined wins).

3. **Consecutive Merging**: Consecutive blocks assigned to the same topic are merged into a single `TopicBlock`. Non-consecutive blocks with the same topic produce separate `TopicBlock`s.

4. **Unassigned Collection**: Blocks matching no rule go to `unassigned_block_ids`.

### Output
- `TopicAssemblyResult` with `topic_blocks[]` and `unassigned_block_ids[]`

### Key Technical Decision: Regex Boundary Handling

Python's `\b` (word boundary) does not work correctly at ASCII/CJK character transitions. For example, `\bMART\b` fails to match "MART的" because CJK characters are not treated as word boundaries.

**Solution**: Use ASCII letter lookaround `(?<![a-zA-Z])...(?![a-zA-Z])` instead of `\b` for Latin keywords. This prevents false positives inside other Latin words while correctly matching at ASCII/CJK boundaries.

## Confidence Scoring

Confidence is rule-determined, not uniform:
- **0.95**: Unambiguous company name (泡泡玛特) with stock code
- **0.90**: Industry keyword with multiple specific companies (新能源)
- **0.85**: Person/institution name (巴菲特/伯克希尔)
- **0.75**: Short keyword that could be substring (老铺, 卫星)

## Test Results

```
25 passed, 0 failed (0.13s)
```

### Test Coverage

| Category | Tests | Requirement Met |
|----------|-------|-----------------|
| Basic functionality | 9 | >= 5 TopicBlocks, non-empty source_block_ids, raw_text traceability, unassigned blocks, no intent fields, block accounting |
| Topic matching | 5 | All 5 topic rules detect correctly |
| Confidence | 2 | Varied by specificity, not all 1.0 |
| Consecutive merge | 2 | Same-topic merge, different-topic separation |
| Edge cases | 4 | Empty envelope, no matches, single block, index range |
| Metadata | 2 | assembly_strategy, segmentation_reason |
| Extensibility | 1 | Custom rules via extra_rules parameter |

### Verification Commands

```bash
pytest tests/test_topic_assembler.py -q
# 25 passed

python -m compileall src/finer/parsing
# Compiles cleanly
```

## Open Issues

1. **Fixture dependency**: Agent 2's `tests/fixtures/kol/cat_lord_topic_assembly_input.json` was not available. Tests use inline fixture data. When the fixture is available, an integration test should be added.

2. **No LLM fallback**: The current assembler is purely keyword-based. Multi-block context (e.g., a block that discusses 泡泡玛特 without using any keyword) is not detected. A future enhancement could add an LLM-based fallback for ambiguous cases.

3. **NEV vs specific stock disambiguation**: If a block mentions both "理想" (NEV keyword) and "泡泡玛特", it will be assigned to whichever rule has higher confidence. Currently NEV (0.90) loses to 泡泡玛特 (0.95). This ordering may need tuning based on real-world data.
