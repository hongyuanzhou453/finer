# Agent Task — F1 MiMo Multimodal Pipeline Validation

**Date**: 2026-05-02
**Owner stage**: F1 Standardize
**Touch scope**: `src/finer/model_config.py`, `src/finer/llm/client.py`, `src/finer/ingestion/vision_utils.py`, `src/finer/parsing/*standardizer.py`, F1 tests, F1 docs
**Primary schema**: `ContentEnvelope`, `ContentBlock`, `BlockQuality`, `BlockProvenance`
**Vision provider**: Xiaomi MiMo `mimo-v2.5` only

## Mission

Finish the F1 multimodal standardization path so images and PDFs can be processed in real engineering scenarios, not only mocked fixture cases. The core requirement is auditable standardization: every successful block carries evidence/provenance, and every failed extraction emits explicit failure blocks instead of fake content.

## Hard Boundaries

- F1 must only standardize content. Do not create topics, entities, investment intent, policies, or trade actions.
- Do not add a second vision model fallback unless the F1 architecture is explicitly reset.
- Do not hardcode API keys or write them to `.env`, docs, fixtures, logs, or snapshots.
- Do not fabricate `image_text` or `paragraph` content when OCR fails. Use `ocr_unreadable` plus `system_event`/metadata.
- Live provider tests must be opt-in and skipped in normal CI.

## Provider Contract

Use MiMo through the existing OpenAI-compatible `LLMClient`.

Required runtime configuration:

```bash
export MIMO_API_KEY="..."
# Required for Token Plan keys (`tp-*`); standard API keys can use the default.
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"
```

Implementation must support:

- model name: `mimo-v2.5`
- auth header: `api-key`
- no `Bearer` prefix for MiMo
- token field: `max_completion_tokens`
- image payload: `data:{mime_type};base64,{payload}` or supported image URL
- provenance model audit: `BlockProvenance.model_name == "mimo-v2.5"` for OCR/VL-derived blocks

## Current Verified Baseline

The parent task already verified:

- three image fixtures call real MiMo OCR and pass canonical validation
- real PDF fixture passes canonical validation
- a temporary scanned PDF generated from an image fixture calls MiMo OCR and passes canonical validation
- token plan keys require `MIMO_BASE_URL`/`MIMO_VISION_BASE_URL`; using `tp-*` against `https://api.xiaomimimo.com/v1` returns invalid key

Your job is to turn this into durable engineering coverage.

## Required Work

1. Re-audit F1 canonical contract:
   - `docs/specs/f1-standardization-contract.md`
   - `src/finer/schemas/content_envelope.py`
   - `src/finer/parsing/standardization_router.py`

2. Confirm adapter behavior:
   - `ImageOCRLayoutStandardizer`
   - `PDFStandardizer`
   - `ManualTextStandardizer`
   - `FeishuChatMarkdownStandardizer`

3. Add an opt-in live MiMo test suite:
   - skipped unless `FINER_ENABLE_LIVE_MIMO=1`
   - skipped if `MIMO_API_KEY` is missing
   - should not print the key
   - should validate at least one image fixture
   - should validate one scanned PDF probe
   - should assert canonical validation passes
   - should assert `ocr_unreadable` is not the only block when MiMo succeeds
   - should assert OCR/VL-derived blocks carry `model_name`

4. Preserve deterministic non-live tests:
   - fake HTTP client for MiMo request shape
   - fallback semantics when provider unavailable
   - canonical validator coverage
   - no legacy source/block type leakage

5. Improve failure reporting if needed:
   - distinguish missing key, invalid key, HTTP error, timeout, empty model response, PDF render failure
   - failures must remain canonical `ocr_unreadable` envelopes/blocks

6. Validate PDF rendering path:
   - text-native PDF path
   - scanned/image-only PDF path
   - corrupt/missing PDF path
   - page-level `page_index`
   - `source_hash`
   - table/chart overlap guards

## Acceptance Criteria

The task is complete only if:

- all F1 non-live tests pass
- live MiMo tests pass when the env variables are present
- no secret appears in code, docs, test output, or fixtures
- image fixture outputs contain real content blocks when MiMo is available
- scanned PDF outputs contain real content blocks when MiMo is available
- provider failure outputs are canonical and explicit
- every OCR/VL-derived block has `BlockProvenance.model_name`
- docs state the exact env contract for standard API keys and Token Plan keys

## Review Report Required

Return a report with:

- files changed
- exact commands run
- non-live test results
- live MiMo test results, with only redacted key references
- fixture-by-fixture block type summaries
- canonical validator results
- any remaining F1 engineering gaps
- whether F1 is ready for F1.5 topic assembly input, and under what assumptions

