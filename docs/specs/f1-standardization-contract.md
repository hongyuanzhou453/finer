# F1 Standardization Contract

> Version: 2026-04-30
> Status: canonical alpha implementation contract
> Scope: F1 Standardize only. This document replaces the older V0/L3/SegmentRecord-style standardization language for new work.

## Purpose

F1 Standardize converts every F0 raw content item into a single canonical `ContentEnvelope` with ordered `ContentBlock` records.

F1 answers only this question:

> How should heterogeneous raw material be represented as traceable, replayable content blocks for F1.5 and F2?

F1 does not decide investment topics, intent, entity anchors, policy, or trade actions.

## Allowed Input

F1 may read:

- F0 `ContentRecord`
- the F0 raw file referenced by `ContentRecord.raw_path` or equivalent source path
- extracted raw text from OCR/ASR/document converters when that text is treated as source material

F1 must preserve enough provenance for downstream audit to trace each block back to the F0 source.

## Required Output

F1 must output:

```python
ContentEnvelope(
    envelope_id: str,
    source_record_id: str,       # -> F0 ContentRecord.content_id
    source_type: SourceType,
    creator_id: str | None,
    creator_name: str | None,
    title: str | None,
    published_at: datetime | None,
    collected_at: datetime | None,
    source_uri: str | None,
    raw_path: str | None,
    blocks: list[ContentBlock],
    standardization_profile: str,
    metadata: dict,
)
```

```python
ContentBlock(
    block_id: str,
    envelope_id: str,
    block_type: BlockType,
    text: str,
    order_index: int,
    speaker: str | None,
    timestamp: datetime | None,
    page_index: int | None,
    bbox: BoundingBox | None,
    start_time_sec: float | None,
    end_time_sec: float | None,
    parent_block_id: str | None,
    thread_id: str | None,
    quality: BlockQuality,
    provenance: BlockProvenance,
    metadata: dict,
)
```

## Canonical Source Types

```python
SourceType = Literal[
    "feishu_chat",
    "feishu_doc",
    "wechat_article",
    "image",
    "pdf",
    "audio_transcript",
    "video_transcript",
    "manual_text",
]
```

Audio and video transcript source types are reserved in the contract. This planning round does not implement an audio adapter.

## Canonical Block Types

```python
BlockType = Literal[
    "chat_message",
    "paragraph",
    "section_title",
    "image_text",
    "table_region",
    "chart_region",
    "audio_segment",
    "video_segment",
    "quote",
    "link_reference",
    "attachment_ref",
    "ocr_unreadable",
    "system_event",
]
```

Deprecated V0 block types must be migrated as follows:

| Deprecated type | Canonical replacement |
|---|---|
| `heading` | `section_title` |
| `list` | `paragraph` or `quote`, depending on source semantics |
| `table` | `table_region` |
| `chart` | `chart_region` |
| `image_region` | `image_text`, `table_region`, `chart_region`, or `ocr_unreadable` |
| `transcript_segment` | `audio_segment` or `video_segment` |
| `unknown` | `system_event` or `paragraph` with low standardization quality |

`SegmentRecord` is not a canonical F1 output. Existing `SegmentRecord` paths are legacy migration inputs only.

## BlockQuality

F1 quality measures standardization reliability, not investment relevance.

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

The scores must be deterministic wherever possible:

- `readability`: text length, garbage character ratio, repeated character ratio, residual HTML ratio, language/number/punctuation balance.
- `extraction_confidence`: parser success, OCR confidence, ASR confidence, or fallback estimate from extractor features.
- `structural_confidence`: confidence that the block boundary and block type are correct.
- `completeness`: whether content is missing, empty, truncated, unreadable, or attachment-only.
- `noise_score`: likelihood that the block is platform/system/meta noise rather than substantive content.

Common `quality_flags`:

```text
html_cleaned
timestamp_parsed
timestamp_missing
speaker_parsed
speaker_missing
qa_format_detected
empty_forward
attachment_missing
system_noise
ocr_low_confidence
ocr_unreadable
layout_uncertain
table_parse_failed
chart_parse_weak
asr_low_confidence
diarization_uncertain
raw_offset_missing
```

LLMs may assist OCR/chart descriptions, but F1 quality scores must not depend on subjective LLM-only judgement.

## BlockProvenance

Every block must carry provenance sufficient for audit:

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

For image blocks, `bbox` should be filled when layout information is available. For chat markdown blocks, raw offsets should be filled when the source is text.

## Canonical Adapter Status

| Adapter | Source types / inputs | Status | Notes |
|---|---|---|---|
| `FeishuChatMarkdownStandardizer` | Feishu chat markdown exports | Implemented | Parses timestamped chat messages, failed forwards, system metadata, speakers, Q/A metadata, and raw text offsets. |
| `ImageOCRLayoutStandardizer` | `.png/.jpg/.jpeg/.webp/.bmp` | Implemented, provider-dependent | Produces canonical failure blocks when OCR/VL is unavailable. Uses layout regions first, then OCR markdown, then vision API fallback. |
| `PDFStandardizer` | `.pdf` | Implemented | Extracts page text, tables, chart/image-heavy regions, scanned-page OCR fallback, page indexes, and layout bbox when available. |
| `ManualTextStandardizer` | `.md/.txt` fallback | Implemented | Safe canonical fallback for plain text and markdown that is not a chat export. |
| `AudioTranscriptStandardizer` | audio transcript files | Reserved | Not implemented in this round. |
| `VideoTranscriptStandardizer` | video transcript files | Reserved | Not implemented in this round. |
| `FeishuDocStandardizer` | Feishu doc exports / docx / JSON | Not implemented | High-priority future adapter. |
| `WebArticleStandardizer` / `WechatArticleStandardizer` | saved HTML / markdown / article export | Not implemented | High-priority future adapter; F0 should fetch/save raw material, F1 should only standardize saved files. |
| `PPTStandardizer` | `.ppt/.pptx` | Not implemented | Future layout-heavy adapter. |
| `SpreadsheetStandardizer` | `.xls/.xlsx/.csv` | Not implemented | Future table/data adapter; needs explicit sheet/range provenance. |

## First Canonical Adapters

### Feishu Chat Markdown

`FeishuChatMarkdownStandardizer` must parse exports such as:

```text
### [2026-03-12 15:36:00] ou_xxx (text)
Q: ...
A: ...
```

It must output:

- `chat_message` blocks for normal messages
- `attachment_ref` blocks for failed or missing forwarded/attached content
- `system_event` blocks for platform events and system noise
- parsed `speaker`, `timestamp`, `message_type`, and `qa_format` metadata
- deterministic `BlockQuality` and `BlockProvenance`

It must clean mechanical wrappers such as `<p>...</p>` without changing source meaning.

### Image OCR/Layout

`ImageOCRLayoutStandardizer` must map OCR/layout output into:

- `section_title`
- `image_text`
- `table_region`
- `chart_region`
- `ocr_unreadable`

If only OCR markdown is available, the adapter should still emit canonical block types. If layout data is available, it must preserve `bbox` and region metadata.

### Audio Transcript

Audio is reserved but not implemented in this round. The future `AudioTranscriptStandardizer` must output `audio_segment` blocks with `start_time_sec` and `end_time_sec` whenever transcript timestamps are available.

## Forbidden Responsibilities

F1 must not:

- assemble topics
- infer investment direction
- infer actionability
- generate `NormalizedInvestmentIntent`
- generate `TradeAction`
- resolve canonical `EntityAnchor` IDs
- discard original content silently

F1 may mark noise and low-quality blocks. Downstream stages decide whether to use, review, or reject them.

## Acceptance Checklist

- [x] Feishu chat markdown is split into timestamped `chat_message` blocks.
- [x] Message `speaker`, `timestamp`, `message_type`, and Q/A structure are preserved when present.
- [x] Failed forwards and missing attachments are represented as `attachment_ref`, not high-quality narrative text.
- [x] System/platform noise is represented as `system_event` with high `noise_score`.
- [x] Image OCR/layout output is split into title/text/table/chart/unreadable region blocks when OCR/layout evidence exists.
- [x] Image standardization emits explicit `ocr_unreadable` failure blocks when OCR/VL extraction is unavailable or empty.
- [x] Image blocks preserve `bbox` when layout coordinates exist.
- [x] PDF standardization emits page-indexed blocks and preserves table/chart bbox when available.
- [x] Every block has deterministic `BlockQuality`.
- [x] Every block has `BlockProvenance`.
- [x] Audio transcript block types remain reserved in docs but are not required for this implementation round.

## Canonical Validator

`ContentEnvelope.validate_canonical_f1()` is the strict validation entry point for F1 output. It returns a list of violation strings — empty means canonical PASS.

### Usage

```python
violations = envelope.validate_canonical_f1()
if violations:
    for v in violations:
        print(f"  - {v}")
    raise ValueError(f"F1 canonical validation failed: {len(violations)} violations")
```

### Checks

| # | Rule | Rationale |
|---|------|-----------|
| 1 | `source_type` must not be legacy (`chat`, `text`) | Canonical requires `feishu_chat` or `manual_text` |
| 2 | `block_type` must not be legacy (`heading`, `list`, `table`, `chart`, `image_region`, `transcript_segment`, `unknown`) | Canonical types are `section_title`, `paragraph`, `table_region`, `chart_region`, `image_text`, `audio_segment`, `system_event`, etc. |
| 3 | Each `block.quality` must be `BlockQuality`, not `QualityCard` | F1 standardization quality ≠ F2 investment relevance |
| 4 | Each `block.provenance` must exist | Every block needs an audit trail to F0 |
| 5 | `order_index` must be sequential from 0 | Canonical ordering guarantee |
| 6 | Each `block.envelope_id` must equal `envelope.envelope_id` | Structural integrity |
| 7 | `temporal_anchors` and `entity_anchors` must be empty | These are populated by F2, not F1 |
| 8 | `standardization_profile` must be set | Identifies which standardizer produced the output |
| 9 | `source_record_id` must be set | F0 → F1 audit chain: downstream must trace back to ContentRecord |
| 10 | `blocks` must not be empty | Adapter failure or unreadable input must emit at least one `system_event` or `ocr_unreadable` block |
| 11 | `schema_version` must be `"v1.0"` | Canonical schema version; `v0.5` is backward compat only |

### BoundingBox Geometry

`BoundingBox` enforces `x1 >= x0` and `y1 >= y0` at model validation time. A bounding box with inverted coordinates is always invalid.

### Backward Compatibility vs Canonical

The schema accepts both legacy and canonical field values at construction time. `validate_canonical_f1()` is the strict gate that rejects legacy values. This allows:

- Legacy code to keep working (construction succeeds)
- Canonical output to be verified explicitly (call `validate_canonical_f1()` after construction)
- Migration to be incremental (fix violations one by one)

## Fixture Acceptance

5 个 F0 真实样本，用于验证 F1 adapter 输出满足 canonical contract。Fixture 位于 `tests/fixtures/f1_standardization/`。

测试命令：`python -m pytest tests/test_f1_standardization_fixtures.py -q`

### 设计原则

1. **Manifest 即真相源**：所有断言定义在 `manifest['assertions']` 中，测试引擎从 manifest 读取并执行，不硬编码 per-sample 检查。
2. **F0 ContentRecord 输入**：adapter 接收已验证的 F0 `ContentRecord` + `raw_path`，不是裸路径或 ad hoc dict。测试从 manifest 构建 `ContentRecord` 并传入 adapter。
3. **精确元数据匹配**：输出 `source_record_id` 必须等于 manifest `source_record_id`，`standardization_profile` 必须等于 manifest `expected_profile`，`raw_path` 必须等于解析后的绝对路径。
4. **无 golden text 比对**：断言是结构性的，adapter 实现变化不会导致 fixture 失败。

### 样本清单

| # | Fixture ID | 类型 | 来源 | 描述 |
|---|---|---|---|---|
| 1 | `chat_maodaren_0312` | `feishu_chat` | maodaren | 1079 条飞书群消息，03-12 ~ 04-20 |
| 2 | `img_9you_0416` | `image` | 9you | PNG 截图，OCR 未提取（API key 缺失） |
| 3 | `pdf_maodaren_0415` | `pdf` | maodaren | 14MB 第三方研报 PDF |
| 4 | `img_9you_0409` | `image` | 9you | PNG 截图，OCR 未提取 |
| 5 | `img_maodaren_0319` | `image` | maodaren | PNG 截图，含吉利汽车财报分析上下文 |

### Manifest-driven 断言引擎

断言引擎从 `manifest['assertions']` 读取断言键并分发到对应 handler。Manifest 是唯一真相源——测试不硬编码 per-sample 检查。

#### 通用断言键（所有 manifest 必须声明）

| 断言键 | 描述 |
|---|---|
| `blocks_non_empty` | 至少产出一个 block |
| `order_index_sequential` | order_index 从 0 连续递增 |
| `every_block_has_quality` | 每个 block 有 `BlockQuality`（非 `QualityCard`） |
| `every_block_has_provenance` | 每个 block 有 `BlockProvenance`（extractor + extractor_version 非空） |
| `passes_canonical_validator` | `validate_canonical_f1()` 返回空 violations |

#### F0 元数据传播断言键（所有 manifest 必须声明）

| 断言键 | 描述 |
|---|---|
| `source_record_id_match` | `envelope.source_record_id == manifest['source_record_id']` |
| `standardization_profile_match` | `envelope.standardization_profile == manifest['expected_profile']` |
| `raw_path_match` | `envelope.raw_path == 解析后的绝对路径` |

#### 类型安全断言键

| 断言键 | 描述 |
|---|---|
| `source_type_must_be` | source_type 必须等于 manifest 声明值 |
| `block_type_must_not_be_legacy` | 无 heading/list/table/chart/image_region/transcript_segment/unknown |
| `quality_must_be_block_quality` | 每个 block 的 quality 必须是 BlockQuality |

#### 按样本类型声明的断言键

| 断言键 | 适用类型 | 描述 |
|---|---|---|
| `required_block_types` | 所有 | 必须出现的 block_type 列表 |
| `speaker_parsed` | chat | chat_message block 的 speaker 已解析 |
| `timestamp_parsed` | chat | chat_message block 的 timestamp 已解析 |
| `page_index_populated` | pdf | block 必须有 page_index |
| `min_region_types` | pdf | 至少识别 N 种区域类型 |
| `must_identify_cover_or_chapter` | pdf | 必须有 section_title 或 paragraph |
| `bbox_populated_when_layout_available` | image | 有 layout 数据时必须填充 bbox |

### adapter 输入契约

adapter 标准化签名：

```python
def standardize(self, f0_record: ContentRecord, raw_path: Path) -> ContentEnvelope
```

- `f0_record`：通过 F0 schema 验证的 `ContentRecord`（content_id、creator_name、source_platform、content_type、published_at、source_path、metadata）
- `raw_path`：原始文件绝对路径
- 返回值：满足 canonical contract 的 ContentEnvelope

### 工程风险

#### Sample 1: 聊天记录

- `merge_forward` fetch failed 消息应映射为 `attachment_ref`，不能丢失或伪装为正文
- `post` 类型消息含内嵌 `[Image: ...]` 标记，需拆分为 `attachment_ref` 或保留为 metadata
- Q/A 格式消息（`Q:...A:...`）是单条还是拆分为两条 block，影响 F2 锚定
- 1079 条消息产出大量 block，需验证 order_index 连续性和 envelope_id 一致性
- 消息时间跨度 40 天，timestamp 解析需处理 +08:00 时区

#### Sample 2: 图片 (04-16)

- OCR 文本未提取（`MIMO_API_KEY` 未配置、Token Plan base URL 未配置，或 MiMo vision API 不可用），adapter 需产出 `ocr_unreadable` failure block，不能跳过或伪造 `image_text`
- 无 layout 数据时 bbox 不可用，需验证 `BlockQuality.extraction_confidence` 降级
- 图片可能包含金融图表，OCR 单独不够，需 layout 分析

#### Sample 3: PDF (04-15)

- 14MB PDF 解析耗时可能超测试 timeout，需设置合理 timeout
- PDF 页数未知，需验证 page_index 覆盖范围（封面/目录/正文/附录）
- 研报通常含表格和图表，需 `table_region`/`chart_region` block
- bbox 在 PDF 场景是页面坐标系（points），非像素坐标系
- `feishu_message_id` 为 `"manual"`（非自动同步），来源可信度需在 metadata 中标注

#### Sample 4: 图片 (04-09)

- 470KB 图片比 04-16 样本大，可能含更复杂布局
- 与 `img_9you_0416` 共享同一 `feishu_chat_id`，需验证 adapter 对同群不同图片的处理一致性

#### Sample 5: 图片 (03-19)

- `context_text` 包含吉利汽车财报分析，图片可能是财报截图或数据图表
- 147KB 较小，可能是单区域截图而非复杂多区域文档
- OCR 未提取，但 `context_text` 可作为 fallback 信息源（adapter 是否使用待定）

### 当前 fixture 验收状态

F1 adapter 输出断言已是实际验收门禁，不再是未实现 `xfail` 状态。

当前 F1 scoped 验证命令：

```bash
python -m pytest \
  tests/test_feishu_chat_markdown_standardizer.py \
  tests/test_image_ocr_layout_standardizer.py \
  tests/test_pdf_document_standardizer.py \
  tests/test_f1_standardization_router.py \
  tests/test_f1_standardization_fixtures.py \
  tests/test_content_envelope_schema.py -q
```

最近一次本地结果：`333 passed, 8 warnings`。

## StandardizationRouter

### 路由规则

`StandardizationRouter.route(f0_record, raw_path)` 根据以下优先级选择 adapter：

| 优先级 | 条件 | Adapter | Profile |
|--------|------|---------|---------|
| 1 | `raw_path` 后缀 `.pdf` | `PDFStandardizer` | `pdf_layout_v1` |
| 2 | `raw_path` 后缀 `.png/.jpg/.jpeg/.webp/.bmp` | `ImageOCRLayoutStandardizer` | `image_ocr_layout_v1` |
| 3 | `raw_path` 后缀 `.md` + `content_type` 为 `chat_transcript`/`chat_export` | `FeishuChatMarkdownStandardizer` | `feishu_chat_markdown_v1` |
| 4 | `raw_path` 后缀 `.md/.txt`（fallback） | `ManualTextStandardizer` | `manual_text_v1` |
| 5 | `content_type == "livestream_audio"` | 抛出 `StandardizationError`（reserved，未实现） | — |
| 6 | 无匹配 | 返回 `ocr_unreadable` 失败 envelope | `failure` |

### StandardizationReport

每次 `route()` 调用返回 `(envelope, report)` 元组：

```python
class StandardizationReport(TypedDict):
    envelope_id: str          # 与 envelope.envelope_id 一致
    adapter: str              # "pdf" / "image" / "feishu_chat" / "manual_text" / "unsupported"
    block_count: int          # envelope.blocks 长度
    low_quality_block_count: int  # extraction_confidence < 0.5 的 block 数
    warnings: list[str]       # canonical validation 失败信息、低质量 block 警告
    canonical_validation_passed: bool  # validate_canonical_f1() 是否通过
```

### 错误处理

- 所有 adapter 调用包裹在 try/except 中，失败时返回 `ocr_unreadable` envelope（不抛异常）
- `StandardizationError` 会重新抛出（用于 reserved 类型如音频）
- 失败 envelope 的 `metadata["failure_reason"]` 记录具体原因

### 样本路由结果

| 样本 | 文件后缀 | content_type | source_platform | 路由到 | canonical 验证 |
|------|----------|-------------|-----------------|--------|----------------|
| `chat_maodaren_0312` | `.md` | `chat_transcript` | `feishu` | `FeishuChatMarkdownStandardizer` | PASS |
| `img_9you_0416` | `.png` | `unclassified` | — | `ImageOCRLayoutStandardizer` | PASS |
| `img_9you_0409` | `.png` | `unclassified` | — | `ImageOCRLayoutStandardizer` | PASS |
| `img_maodaren_0319` | `.png` | `unclassified` | — | `ImageOCRLayoutStandardizer` | PASS |
| `pdf_maodaren_0415` | `.pdf` | `unclassified` | — | `PDFStandardizer` | PASS |

### 未实现的 source type

| source_type | 状态 |
|-------------|------|
| `audio_transcript` / `livestream_audio` | Reserved — 抛出 `StandardizationError` |
| `video_transcript` / `bilibili_video` | 未实现 — 走 `unsupported` 路径返回失败 envelope |
| `wechat_article` / `wechat_video` | 未实现 — 走 `unsupported` 路径（除非文件后缀匹配） |
| `feishu_doc` | 未实现 — markdown/docx/html/json 导出需专门 adapter |
| `ppt` / `pptx` | 未实现 — 需要页面、文本框、图表、图片区域级标准化 |
| `xls` / `xlsx` / structured spreadsheet | 未实现 — 需要 sheet/cell-range provenance |
| saved web article HTML | 未实现 — F0 应先保存 raw HTML/markdown，F1 再标准化 |
