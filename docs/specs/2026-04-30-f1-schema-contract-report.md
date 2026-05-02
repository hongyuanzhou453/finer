# F1 Schema Contract Report

## Environment

- **pwd**: `/Users/zhouhongyuan/Desktop/finer`
- **git root**: `/Users/zhouhongyuan/Desktop/finer`
- **commit**: `545a993` (F1.5 TopicBlock, F5 ExecutionTiming, Canonical Action Builder)
- **git status before**: uncommitted LLM integration files (deepseek_client.py, llm_topic_assembly_adapter.py, tests)

---

## Changed Files

| File | Change Type | Description |
|------|-------------|-------------|
| `src/finer/schemas/content_envelope.py` | Modified | Added BoundingBox, BlockQuality, BlockProvenance models; updated BLOCK_TYPE_LITERAL and SOURCE_TYPE_LITERAL; updated ContentBlock with canonical fields (order_index, quality, envelope_id, timestamp, thread_id, provenance, bbox as BoundingBox); backward compat for order, quality_card, bbox list; datetime string parsing in ContentEnvelope validator |
| `src/finer/schemas/__init__.py` | Modified | Added exports: BoundingBox, BlockQuality, BlockProvenance |
| `tests/test_content_envelope_schema.py` | Rewritten | 38 tests using canonical F1 field names + backward compat coverage |

---

## Contract Implemented

### New Models

**BoundingBox** (`src/finer/schemas/content_envelope.py:47-57`)
```python
BoundingBox(x0: float, y0: float, x1: float, y1: float)
```
Spatial bounding box for image/PDF content regions. All coordinates ge=0.

**BlockQuality** (`src/finer/schemas/content_envelope.py:60-91`)
```python
BlockQuality(
    readability: float,
    extraction_confidence: float,
    structural_confidence: float,
    completeness: float,
    noise_score: float,
    quality_flags: list[str],
)
```
F1 standardization quality. Measures reliability, NOT investment relevance. All scores 0.0-1.0.

**BlockProvenance** (`src/finer/schemas/content_envelope.py:94-119`)
```python
BlockProvenance(
    raw_path: str | None,
    raw_offset_start: int | None,
    raw_offset_end: int | None,
    extractor: str,
    extractor_version: str,
    model_name: str | None,
    source_hash: str | None,
)
```
Audit trail tracing each block to its F0 source. `extractor` and `extractor_version` are required.

### SourceType (updated)

```python
SOURCE_TYPE_LITERAL = Literal[
    # F1 canonical
    "feishu_chat", "feishu_doc", "wechat_article", "image",
    "pdf", "audio_transcript", "video_transcript", "manual_text",
    # Deprecated (backward compat)
    "chat",     # -> "feishu_chat"
    "text",     # -> "manual_text"
]
```

### BlockType (updated)

```python
BLOCK_TYPE_LITERAL = Literal[
    # F1 canonical
    "chat_message", "paragraph", "section_title", "image_text",
    "table_region", "chart_region", "audio_segment", "video_segment",
    "quote", "link_reference", "attachment_ref", "ocr_unreadable", "system_event",
    # Deprecated (backward compat)
    "heading",           # -> "section_title"
    "list",              # -> "paragraph" or "quote"
    "table",             # -> "table_region"
    "chart",             # -> "chart_region"
    "image_region",      # -> "image_text" / "table_region" / "chart_region" / "ocr_unreadable"
    "transcript_segment",# -> "audio_segment" or "video_segment"
    "unknown",           # -> "system_event" or "paragraph"
]
```

### ContentBlock (canonical fields)

| Field | Type | Status |
|-------|------|--------|
| `block_id` | `str` | Required (auto-generated) |
| `envelope_id` | `str \| None` | New, populated by ContentEnvelope |
| `block_type` | `BLOCK_TYPE_LITERAL` | Required |
| `text` | `str` | Required |
| `order_index` | `int` | **Canonical** (was `order`) |
| `speaker` | `str \| None` | Optional |
| `timestamp` | `datetime \| None` | New |
| `page_index` | `int \| None` | Optional |
| `bbox` | `BoundingBox \| None` | Changed from `List[float]` |
| `start_time_sec` | `float \| None` | Optional |
| `end_time_sec` | `float \| None` | Optional |
| `parent_block_id` | `str \| None` | Optional |
| `thread_id` | `str \| None` | New |
| `quality` | `BlockQuality \| QualityCard` | **Canonical** (was `quality_card`) |
| `provenance` | `BlockProvenance \| None` | New |
| `evidence_spans` | `list` | Optional |
| `metadata` | `dict` | Optional |

### ContentEnvelope (new fields)

| Field | Type | Status |
|-------|------|--------|
| `source_record_id` | `str \| None` | New (F0 ContentRecord.content_id) |
| `standardization_profile` | `str \| None` | New |
| `raw_path` | `str \| None` | New |
| `collected_at` | `datetime \| None` | New |

---

## Compatibility Notes

### Legacy Fields Kept (backward compat)

| Legacy Usage | Canonical Equivalent | Mechanism |
|---|---|---|
| `ContentBlock(order=0)` | `ContentBlock(order_index=0)` | `mode="before"` validator maps `order` -> `order_index` |
| `block.order` (read) | `block.order_index` | `@property` returns `order_index` |
| `block.order = 5` (write) | `block.order_index = 5` | `@order.setter` delegates to `order_index` |
| `ContentBlock(quality_card=qc)` | `ContentBlock(quality=qc)` | `mode="before"` validator maps `quality_card` -> `quality` |
| `block.quality_card` | `block.quality` | `@property` returns `quality` |
| `ContentBlock(bbox=[x0,y0,x1,y1])` | `ContentBlock(bbox=BoundingBox(...))` | `mode="before"` validator converts list to BoundingBox |
| `ContentEnvelope(title="...")` | `ContentEnvelope(source_title="...")` | `mode="before"` validator maps `title` -> `source_title` |
| `source_type="chat"` | `source_type="feishu_chat"` | Kept in `SOURCE_TYPE_LITERAL` |
| `source_type="text"` | `source_type="manual_text"` | Kept in `SOURCE_TYPE_LITERAL` |
| `block_type="heading"` | `block_type="section_title"` | Kept in `BLOCK_TYPE_LITERAL` |
| `block_type="table"` | `block_type="table_region"` | Kept in `BLOCK_TYPE_LITERAL` |
| `block_type="chart"` | `block_type="chart_region"` | Kept in `BLOCK_TYPE_LITERAL` |
| `block_type="image_region"` | `block_type="image_text"` etc. | Kept in `BLOCK_TYPE_LITERAL` |
| `block_type="transcript_segment"` | `block_type="audio_segment"` | Kept in `BLOCK_TYPE_LITERAL` |
| `block_type="list"` | `block_type="paragraph"` / `"quote"` | Kept in `BLOCK_TYPE_LITERAL` |
| `block_type="unknown"` | `block_type="system_event"` | Kept in `BLOCK_TYPE_LITERAL` |

### Legacy Fields Deprecated

No fields were removed. All deprecated types and field names are still accepted.

### Datetime String Parsing

ContentEnvelope now parses ISO 8601 datetime strings in `mode="before"` validator for `published_at`, `collected_at`, `ingested_at`. This enables `model_validate_json()` to work with string datetime values in strict mode.

---

## Tests

### Command

```bash
python -m pytest tests/test_content_envelope_schema.py tests/test_schemas.py tests/test_content_standardizer.py -q
```

### Result

```
147 passed, 8 warnings
```

### Full Suite

```bash
python -m pytest -q
```

```
986 passed, 22 skipped, 0 failed
```

### Test Coverage

| Test Class | Tests | Coverage |
|---|---|---|
| `TestBoundingBox` | 3 | Creation, validation, edge cases |
| `TestBlockQuality` | 4 | Creation, defaults, bounds |
| `TestBlockProvenance` | 3 | Creation, minimal, model_name |
| `TestContentBlockCanonical` | 4 | Minimal, all fields, validation, auto-id |
| `TestContentBlockBackwardCompat` | 5 | order alias, quality_card alias, bbox list, both-set precedence |
| `TestContentEnvelopeCanonical` | 5 | Minimal, all fields, title alias, block order, envelope_id propagation |
| `TestContentEnvelopeHelpers` | 6 | get_block_by_id, get_blocks_by_type, get_text_content, serialization, compute_overall_quality, get_blocks_requiring_review |
| `TestSourceTypes` | 3 | Canonical, deprecated, invalid |
| `TestBlockTypes` | 3 | Canonical, deprecated, invalid |
| `TestEnvelopeBackwardCompat` | 2 | QualityCard passthrough, blocks with QualityCard |

---

## Risks / Follow-ups

1. **`quality` field type is `Union[BlockQuality, QualityCard]`**: This allows both types to pass through. New code should use `BlockQuality`. The union is necessary because `content_standardizer.py` (not modifiable in this task) still constructs blocks with `QualityCard`.

2. **Deprecated block/source types still in Literal**: They should be removed once all adapters are migrated to canonical types. Migration mapping is documented in `docs/specs/f1-standardization-contract.md`.

3. **`schema_version` default is `"v0.5"`**: Changed from original "v0.5" to keep backward compat. Should be updated to "v1.0" when the standardizer is updated to produce canonical output.

4. **`BlockProvenance` is optional on ContentBlock**: The F1 contract says every block must have provenance, but making it required would break all existing code that doesn't populate it. Adapters should be updated to populate provenance before it becomes required.

5. **`temporal_anchors` / `entity_anchors` on ContentEnvelope**: These are F2 extraction hooks, not F1 output. Kept for backward compat. F1 standardizers should not populate these.

6. **`_quality_card_to_block_quality` helper**: Currently unused (quality_card passes through as-is). Kept for potential future use if explicit conversion is needed.
