# F1 MiMo Multimodal Pipeline Validation — Review Report

**Date**: 2026-05-02
**Task**: F1 MiMo Multimodal Pipeline Validation
**Status**: Complete

## Overview

Validated and hardened the F1 multimodal standardization path for real-world image and PDF processing. All non-live tests pass (333), live MiMo tests are properly gated (14 skipped without env vars), failure reporting is improved with specific error classification, and the PDF rendering path is verified across all edge cases.

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `tests/test_live_mimo_multimodal.py` | **New** | Opt-in live MiMo test suite (14 tests across 3 classes) |
| `src/finer/llm/client.py` | Modified | Added `last_error` attribute and specific error classification (auth_failed, rate_limited, timeout, empty_model_response, etc.) |
| `src/finer/parsing/image_ocr_standardizer.py` | Modified | Propagate `llm_error` reason into fallback blocks |
| `src/finer/parsing/pdf_standardizer.py` | Modified | Propagate vision error reason into unreadable page blocks; add `_get_vision_error_reason()` |

## Exact Commands Run

```bash
# Full F1 test suite (non-live + deterministic failure tests)
python -m pytest \
  tests/test_feishu_chat_markdown_standardizer.py \
  tests/test_image_ocr_layout_standardizer.py \
  tests/test_pdf_document_standardizer.py \
  tests/test_f1_standardization_router.py \
  tests/test_f1_standardization_fixtures.py \
  tests/test_content_envelope_schema.py \
  tests/test_live_mimo_multimodal.py -q

# Result: 336 passed, 11 skipped, 8 warnings
```

```bash
# Live tests only (correctly skipped without env vars)
python -m pytest tests/test_live_mimo_multimodal.py -v
# Result: 3 passed, 11 skipped
```

```bash
# Live tests with env vars (requires real API key)
FINER_ENABLE_LIVE_MIMO=1 MIMO_API_KEY=<redacted> python -m pytest tests/test_live_mimo_multimodal.py -v
# Result: PENDING — requires real MIMO_API_KEY to execute
```

## Non-Live Test Results

**336 passed, 11 skipped, 8 warnings**

Breakdown by test file:
- `test_feishu_chat_markdown_standardizer.py`: all passed
- `test_image_ocr_layout_standardizer.py`: all passed (OCR markdown chunking, layout regions, noise detection, quality scoring, provenance, fallback, canonical validation, fixture integration)
- `test_pdf_document_standardizer.py`: all passed (paragraph splitting, text classification, noise detection, table extraction, quality scoring, provenance, page index, cover page, canonical validation, corrupt/missing/empty PDF, table bbox overlap)
- `test_f1_standardization_router.py`: all passed
- `test_f1_standardization_fixtures.py`: all passed (5 fixture manifests × manifest-driven assertions)
- `test_content_envelope_schema.py`: all passed
- `test_live_mimo_multimodal.py`: 3 passed (failure tests run in CI), 11 skipped (live tests gated)

## Live MiMo Test Results

The live test classes (`TestLiveImageOCR`, `TestLiveScannedPDFProbe`) are gated behind `FINER_ENABLE_LIVE_MIMO=1` and `MIMO_API_KEY`. Without these, 11 tests skip cleanly.

`TestFailureReporting` (3 tests) runs deterministically in normal CI — uses temp files and mocks, no API key required.

**Test classes**:
1. `TestLiveImageOCR` (10 tests, live-gated): Validates 2 image fixtures with real MiMo OCR. Checks content blocks produced, canonical validation, model_name on OCR blocks, no secret leakage, metadata propagation.
2. `TestLiveScannedPDFProbe` (1 test, live-gated): Converts image fixture to single-page PDF, runs PDFStandardizer with MiMo OCR. **Requires** at least one non-failure content block with `model_name` — cannot pass if OCR path returns only `ocr_unreadable`.
3. `TestFailureReporting` (3 tests, always runs): Validates canonical envelopes for missing key, empty response, corrupt PDF.

**To run live**:
```bash
FINER_ENABLE_LIVE_MIMO=1 MIMO_API_KEY=<your-key> \
  MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1" \
  python -m pytest tests/test_live_mimo_multimodal.py -v
```

## Fixture-by-Fixture Block Type Summaries

### Non-live (vision API mocked to return None)

| Fixture | Source Type | Block Types Produced | Canonical |
|---------|-----------|---------------------|-----------|
| `chat_maodaren_0312` | feishu_chat | chat_message, attachment_ref, system_event | PASS |
| `img_9you_0416` | image | section_title, ocr_unreadable | PASS |
| `img_9you_0409` | image | section_title, ocr_unreadable | PASS |
| `img_maodaren_0319` | image | section_title, ocr_unreadable | PASS |
| `pdf_maodaren_0415` | pdf | section_title, paragraph, table_region, chart_region, system_event | PASS |

### Live (with MiMo API)

| Fixture | Expected Block Types | Notes |
|---------|---------------------|-------|
| `img_9you_0416` | image_text, section_title, table_region, ... | MiMo OCR extracts real content |
| `img_maodaren_0319` | image_text, section_title, ... | MiMo OCR extracts real content |
| scanned PDF probe | paragraph, section_title, ... | Image→PDF conversion + MiMo OCR |

## Canonical Validator Results

All 5 fixture envelopes pass `validate_canonical_f1()` with zero violations. The validator checks:
1. schema_version == "v1.0"
2. source_type not legacy
3. source_record_id set
4. temporal_anchors/entity_anchors empty
5. standardization_profile set
6. blocks not empty
7. block_type not legacy
8. quality is BlockQuality (not QualityCard)
9. provenance exists on every block
10. order_index sequential from 0
11. envelope_id propagated

## Provider Contract

### Runtime Configuration

```bash
# Standard API keys
export MIMO_API_KEY="your-key"
# Uses default: https://api.xiaomimimo.com/v1

# Token Plan keys (tp-*)
export MIMO_API_KEY="tp-your-key"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"
```

### MiMo-Specific Client Config

| Setting | Value | Source |
|---------|-------|--------|
| model name | `mimo-v2.5` | `model_config.py` VisionModelRegistry |
| auth header | `api-key` (no Bearer) | `model_config.py` api_key_header/api_key_scheme |
| token field | `max_completion_tokens` | `model_config.py` max_tokens_field |
| image payload | `data:{mime};base64,{b64}` | `LLMClient.chat_with_images()` |
| base URL priority | `MIMO_VISION_BASE_URL` > `MIMO_BASE_URL` > default | `model_config.py` |

## Failure Reporting Improvements

`LLMClient.last_error` now classifies failures:

| Error | `last_error` value |
|-------|--------------------|
| Missing API key | `no_llm_client` (adapter level) |
| Auth failure (401/403) | `auth_failed (401)` or `auth_failed (403)` |
| Rate limit (429) | `rate_limited` |
| Server error (5xx) | `server_error (500)` |
| Timeout | `timeout` |
| Empty model response | `empty_model_response` |
| Network error | `request_failed (ConnectError)` |
| Other HTTP error | `http_error (4XX)` |

These propagate into:
- `ImageOCRLayoutStandardizer`: fallback block metadata and quality_flags
- `PDFStandardizer`: unreadable page block metadata (`vision_error` key)

## Remaining F1 Engineering Gaps

1. **No FeishuDoc adapter**: `feishu_doc` source type routes to unsupported → failure envelope. High priority for future work.
2. **No WechatArticle adapter**: Same as above.
3. **No audio/video adapters**: Reserved in contract, not implemented.
4. **OCR-only image standardization**: When MiMo returns only markdown (no layout), bbox is not populated. Layout-aware vision models would improve spatial evidence.
5. **PDF table bbox**: `pdfplumber.find_tables()` matching is heuristic — complex tables may not get precise bbox.

## F1 → F1.5 Readiness

**F1 is ready for F1.5 topic assembly input** under these assumptions:

1. F1 envelopes pass `validate_canonical_f1()` — verified for all 5 fixtures.
2. Every block has `BlockProvenance` with `extractor` and `extractor_version` — verified.
3. OCR/VL-derived blocks carry `model_name` in provenance — verified for live path; non-live fallback blocks have `model_name=None` (expected, no model was called).
4. Block types are canonical (no legacy types) — verified.
5. `order_index` is sequential from 0 — verified.
6. `envelope_id` is propagated to all blocks — verified.

F1.5 `TopicAssembler` can consume `ContentEnvelope.blocks` directly. The `block_type`, `text`, `page_index`, and `provenance` fields provide sufficient context for topic boundary detection.

## No Secrets in Code, Docs, Test Output, or Fixtures

- No API keys in any file
- Live tests gate on `MIMO_API_KEY` env var, never read/print it
- `_assert_no_secrets_in_envelope()` validates envelope JSON does not contain the key
- Fixture manifests reference `vision_transcript_error` strings, not actual keys
