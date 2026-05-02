# F1 Standardization Router — Implementation Report

**Date**: 2026-04-30
**F-stage**: F1
**Module**: `src/finer/parsing/standardization_router.py`
**Tests**: `tests/test_f1_standardization_router.py`

## Overview

Implemented the unified F1 entry point (`StandardizationRouter`) that routes F0 `ContentRecord` to the correct canonical adapter based on file suffix, content_type, and source_platform. Also implemented `ManualTextStandardizer` as the fallback adapter for .md/.txt files without specialized handlers.

## Changes

| File | Type | Description |
|------|------|-------------|
| `src/finer/parsing/standardization_router.py` | New | Unified router with adapter selection, dispatch, failure handling, report generation (~220 lines) |
| `src/finer/parsing/manual_text_standardizer.py` | New | F1 canonical adapter for plain text/markdown (~200 lines) |
| `src/finer/parsing/__init__.py` | Modified | Added exports: `StandardizationRouter`, `StandardizationReport`, `StandardizationError`, `ManualTextStandardizer` |
| `tests/test_f1_standardization_router.py` | New | 30 unit tests across 6 test classes |
| `docs/specs/f1-standardization-contract.md` | Modified | Added router section with routing rules, report schema, sample results |

## Routing Rules

| Priority | Condition | Adapter | Profile |
|----------|-----------|---------|---------|
| 1 | `.pdf` suffix | `PDFStandardizer` | `pdf_layout_v1` |
| 2 | `.png/.jpg/.jpeg/.webp/.bmp` suffix | `ImageOCRLayoutStandardizer` | `image_ocr_layout_v1` |
| 3 | `.md` + `content_type` 为 `chat_transcript`/`chat_export` | `FeishuChatMarkdownStandardizer` | `feishu_chat_v1` |
| 4 | `.md/.txt` fallback | `ManualTextStandardizer` | `manual_text_v1` |
| 5 | `livestream_audio` content_type | `StandardizationError` raised | — |
| 6 | No match | `ocr_unreadable` failure envelope | `failure` |

## Sample Routing Results

| Sample | Suffix | content_type | Platform | Routed to | Canonical |
|--------|--------|-------------|----------|-----------|-----------|
| `chat_maodaren_0312` | `.md` | `chat_transcript` | `feishu` | `FeishuChatMarkdownStandardizer` | PASS |
| `img_9you_0416` | `.png` | `unclassified` | — | `ImageOCRLayoutStandardizer` | PASS |
| `img_9you_0409` | `.png` | `unclassified` | — | `ImageOCRLayoutStandardizer` | PASS |
| `img_maodaren_0319` | `.jpg` | `unclassified` | — | `ImageOCRLayoutStandardizer` | PASS |
| `pdf_maodaren_0415` | `.pdf` | `unclassified` | — | `PDFStandardizer` | PASS |

## ManualTextStandardizer

New canonical adapter for .md/.txt fallback. NOT using legacy `standardize_text_source()` because it produces:
- Different ContentBlock shape (`block_id`, `order`, `quality_card`, `evidence_spans` vs canonical `order_index`, `quality`, `provenance`)
- Legacy block types (`"heading"`, `"list"`, `"table"`) that fail `validate_canonical_f1()`

`ManualTextStandardizer` produces canonical output directly:
- Markdown heading → `section_title`
- URL-containing text → `link_reference`
- Default → `paragraph`
- Platform noise → `system_event`
- All blocks carry `BlockProvenance` with `source_hash`
- `schema_version="v1.0"`, `source_type="manual_text"`, `standardization_profile="manual_text_v1"`

## Error Handling

- All adapter calls wrapped in try/except; failure → canonical `ocr_unreadable` envelope (never crash)
- `StandardizationError` re-raised for reserved types (audio)
- Failure envelope: `metadata["failure_reason"]` records the error detail
- Logger: single-line warning (`"Adapter {name} failed for {file}: {ExceptionType}"`)

## Test Results

```
tests/test_f1_standardization_router.py     30 passed
tests/test_f1_standardization_fixtures.py   80 passed
tests/test_pdf_document_standardizer.py     48 passed
tests/test_image_ocr_layout_standardizer.py 60 passed
                                            ──────────
                                            218 passed
```

**Test coverage by class**:
- `TestSelectAdapter`: 11 tests — pdf, png, jpg, chat_transcript, feishu platform, unclassified md, txt, chat_export, livestream_audio raises, unknown suffix
- `TestManualText`: 7 tests — canonical envelope, heading→section_title, URL→link_reference, empty→ocr_unreadable, canonical validation, provenance, order_index
- `TestRouteEndToEnd`: 3 tests — pdf/image/chat fixtures route correctly
- `TestReport`: 2 tests — report fields populated, canonical validation true
- `TestFailureHandling`: 5 tests — corrupt PDF, missing file, unsupported type, audio raises, failure envelope passes validator
- `TestCanonicalValidation`: 3 tests — manual text, empty text, unsupported all pass validator

## P1 Fixes (post-review)

### P1-1: Feishu platform alone misroutes generic markdown into chat adapter

**Problem**: `_select_adapter()` routed any `.md` from `source_platform == "feishu"` to `FeishuChatMarkdownStandardizer`, even when `content_type` was `unclassified`. A regular Feishu markdown note became a feishu_chat envelope with a `system_event: no_parseable_messages` fallback, losing the actual document text.

**Fix**: Removed `source_platform == "feishu"` from the routing condition. Now only routes to feishu_chat when `content_type in ("chat_transcript", "chat_export")`. Feishu platform + unclassified content_type → `ManualTextStandardizer`.

### P1-2: Router failure envelope hides intended source type

**Problem**: `_build_failure_envelope()` always set `source_type="manual_text"` regardless of whether the failed record was image/pdf/video. Downstream reporting couldn't distinguish unsupported video from generic manual text.

**Fix**: Added `_infer_source_type()` that maps suffix/content_type to a meaningful source_type (pdf→"pdf", image→"image", chat→"feishu_chat", else→"manual_text"). Failure envelope now uses this inferred source_type. Also added `metadata["intended_source_type"]` on the failure block for explicit downstream traceability.

## Test Results

```
tests/test_f1_standardization_router.py     33 passed
tests/test_f1_standardization_fixtures.py   80 passed
tests/test_pdf_document_standardizer.py     48 passed
tests/test_image_ocr_layout_standardizer.py 60 passed
                                            ──────────
                                            221 passed
```

**Test coverage by class**:
- `TestSelectAdapter`: 12 tests — pdf, png, jpg, chat_transcript, feishu platform alone→manual_text, feishu+chat_transcript→feishu_chat, unclassified md, txt, chat_export, livestream_audio raises, unknown suffix
- `TestManualText`: 7 tests — canonical envelope, heading→section_title, URL→link_reference, empty→ocr_unreadable, canonical validation, provenance, order_index
- `TestRouteEndToEnd`: 3 tests — pdf/image/chat fixtures route correctly
- `TestReport`: 2 tests — report fields populated, canonical validation true
- `TestFailureHandling`: 8 tests — corrupt PDF, missing file, unsupported type, audio raises, failure envelope passes validator, source_type matches input (P1-2), intended_source_type metadata (P1-2)
- `TestCanonicalValidation`: 3 tests — manual text, empty text, unsupported all pass validator

## Unimplemented Source Types

| source_type | Status |
|-------------|--------|
| `audio_transcript` / `livestream_audio` | Reserved — raises `StandardizationError` |
| `video_transcript` / `bilibili_video` | Not implemented — `unsupported` path |
| `wechat_article` / `wechat_video` | Not implemented — `unsupported` path (unless suffix matches) |
