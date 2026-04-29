# F1.5 TopicBlock Schema — Implementation Report

## Overview

Created the `TopicBlock` and `TopicAssemblyResult` Pydantic V2 schemas for the F1.5 Topic Assembly sub-stage. This is schema-only; no assembler, LLM, or business pipeline code was added.

## Files Modified

| File | Action | Description |
|------|--------|-------------|
| `src/finer/schemas/topic_block.py` | **CREATE** | TopicType enum, TOPIC_TYPE_LITERAL, TopicBlock, TopicAssemblyResult |
| `src/finer/schemas/__init__.py` | **MODIFY** | Added F1.5 imports and `__all__` exports |
| `tests/test_topic_block_schema.py` | **CREATE** | 28 tests covering serialization, validation, edge cases |

## Models & Fields Added

### `TopicType` (enum, `str, Enum`)

8 members: `single_stock`, `industry`, `macro_policy`, `market_commentary`, `investment_philosophy`, `portfolio_update`, `news_forward`, `other`

### `TOPIC_TYPE_LITERAL`

`Literal` alias for the same 8 values. Used as the field type on `TopicBlock.topic_type` to stay compatible with `strict=True`.

### `TopicBlock` (BaseModel, `strict=True`)

| Field | Type | Default | Validators |
|-------|------|---------|------------|
| `topic_block_id` | `str` | `tb_{uuid4[:12]}` | — |
| `envelope_id` | `str` | required | — |
| `source_block_ids` | `List[str]` | required | must not be empty |
| `topic_title` | `str` | required | — |
| `topic_type` | `TOPIC_TYPE_LITERAL` | required | — |
| `primary_entity_ids` | `List[str]` | `[]` | — |
| `secondary_entity_ids` | `List[str]` | `[]` | — |
| `start_block_index` | `int` | required, `>= 0` | — |
| `end_block_index` | `int` | required, `>= 0` | must be `>= start_block_index` |
| `start_time` | `Optional[datetime]` | `None` | — |
| `end_time` | `Optional[datetime]` | `None` | must not be before `start_time` |
| `summary` | `str` | `""` | — |
| `raw_text` | `str` | required | must not be empty |
| `segmentation_reason` | `str` | `""` | — |
| `confidence` | `float` | `1.0`, `[0.0, 1.0]` | — |
| `ambiguity_flags` | `List[str]` | `[]` | — |

### `TopicAssemblyResult` (BaseModel, `strict=True`)

| Field | Type | Default |
|-------|------|---------|
| `assembly_id` | `str` | `asm_{uuid4[:12]}` |
| `envelope_id` | `str` | required |
| `topic_blocks` | `List[TopicBlock]` | `[]` |
| `unassigned_block_ids` | `List[str]` | `[]` |
| `assembly_strategy` | `str` | `""` |
| `created_at` | `datetime` | `datetime.now()` |

## Key Design Decision

**`topic_type` uses `TOPIC_TYPE_LITERAL` (Literal) not `TopicType` (Enum) as field type.**

Reason: `model_config = ConfigDict(strict=True)` rejects plain string inputs for Enum fields in Pydantic V2. The existing codebase pattern (`content_envelope.py`) uses `Literal` types with `strict=True`. The `TopicType` enum is kept as a programmatic reference (e.g., iteration, membership checks), while `TOPIC_TYPE_LITERAL` is the actual validation type. This matches the contract spec in `f-stage-contracts.md` line 184.

## Validators

All 5 required validators implemented as `@model_validator(mode='after')`:

1. `source_block_ids` not empty
2. `confidence` in `[0.0, 1.0]` (via `Field(ge=0.0, le=1.0)`)
3. `end_block_index >= start_block_index`
4. `end_time` not before `start_time` (when both present)
5. `raw_text` not empty

## Test Results

```
pytest tests/test_topic_block_schema.py -q
28 passed
```

Test coverage:
- TopicType enum values and count
- TopicBlock creation (minimal / full)
- Roundtrip serialization (model_dump, model_dump_json)
- Default ID uniqueness
- String-to-Literal deserialization
- Invalid confidence (< 0, > 1)
- Invalid block index (end < start, negative)
- Empty source_block_ids
- end_time before start_time
- Empty raw_text
- Time range with only one bound
- TopicAssemblyResult creation, roundtrip, empty blocks

## Verification Commands

```bash
pytest tests/test_topic_block_schema.py -q         # 28 passed
python -m compileall src/finer/schemas/topic_block.py  # clean
```

## Open Issues

- The `parsing/topic_assembler.py` (assembler logic) is not yet created — this report only covers the schema layer.
- The `TopicType` enum and `TOPIC_TYPE_LITERAL` are redundant by design; if the project drops `strict=True` in the future, the field type can switch to `TopicType` directly and `TOPIC_TYPE_LITERAL` can be deprecated.
- `topic_type` does not yet enforce that invalid string values are rejected with a clear error message — Pydantic's Literal validation handles this, but the error message is generic.

## Risks

- None for the schema layer itself. Downstream risk is that F2 (entity anchoring) and F3 (intent extraction) must be updated to accept `TopicBlock` as input, but that's out of scope for this task.
