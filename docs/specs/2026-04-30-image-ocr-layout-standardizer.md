# Image OCR/Layout Standardizer — Implementation Report

**Date**: 2026-04-30
**F-stage**: F1
**Adapter**: `ImageOCRLayoutStandardizer`
**Module**: `src/finer/parsing/image_ocr_standardizer.py`
**Tests**: `tests/test_image_ocr_layout_standardizer.py`

## Overview

Implemented the F1 canonical adapter for image content standardization. Converts image OCR markdown or layout region data into `ContentEnvelope` with ordered `ContentBlock[]`. Supports three input paths: pre-extracted OCR markdown, structured layout regions with bounding boxes, and vision API fallback.

## Changes

| File | Type | Description |
|------|------|-------------|
| `src/finer/parsing/image_ocr_standardizer.py` | New | F1 canonical image adapter (~400 lines) |
| `tests/test_image_ocr_layout_standardizer.py` | New | 62 unit tests across 10 test classes |
| `src/finer/parsing/__init__.py` | Modified | Added `ImageOCRLayoutStandardizer` export |
| `tests/fixtures/f1_standardization/img_*.json` | Modified | `required_block_types` updated: `image_text` → `ocr_unreadable` for no-OCR fixtures |

## Three Image Types — Chunking Strategy

### 1. Long OCR text + watermark (img_9you_0416, 2026-04-16 13:27)

**Input**: OCR markdown with headers, body paragraphs, watermarks, page footers.

**Chunking**:
- Split on markdown headers (`#`, `##`, etc.) → `section_title` blocks
- Split on blank lines → `image_text` blocks
- Detect markdown table patterns (`| col | col |` + separator) → `table_region` blocks
- Watermark text ("仅供内部使用") → `system_event` block with `noise_type: watermark`
- Page footer ("第X页/共Y页") → `system_event` block with `noise_type: page_footer`

**Output**: Mixed block types with watermarks isolated in `system_event` blocks, never mixed into content.

### 2. Long concatenated multi-source slide (img_9you_0409, 2026-04-09 21:11)

**Input**: OCR markdown with multiple sections from different sources (A股/港股/美股), tables, platform noise.

**Chunking**:
- Each market section header → `section_title`
- Body text per section → `image_text`
- Data tables → `table_region`
- Source attribution ("来源：Wind") → `image_text`
- Platform noise ("来自飞书") → `system_event` with `noise_type: platform_noise`

**Output**: Multiple `section_title` blocks (4+ per image), structured content blocks with noise isolated.

### 3. Two-column investment research slide (img_maodaren_0319, 2026-03-19 00:42)

**Input**: OCR markdown with structured financial data, risk factors, links.

**Chunking**:
- Slide title → `section_title`
- Data points and analysis → `image_text`
- URLs → `link_reference` blocks
- Quoted text → `quote` blocks

**Output**: Clean section_title + image_text + link_reference structure.

## Input Path Priority

When multiple inputs are available, the adapter uses this priority order:

1. **Layout regions** (richest — preserves bbox, region_role, nested_source_type)
2. **OCR markdown** (deterministic chunking, no spatial data)
3. **Vision API fallback** (calls LLM, subject to API availability)
4. **Generated fallback** (section_title + ocr_unreadable — no fabricated content)

**P1-2 fix**: When both `layout_regions` and `ocr_markdown` exist, layout takes precedence because it preserves spatial evidence (bbox) that pure OCR chunking discards.

## OCR Low Confidence Handling

- **No OCR data**: Falls back to vision API. If vision API fails, produces `section_title` (metadata) + `ocr_unreadable` (failure signal). Does **not** fabricate `image_text` placeholder blocks.
- **Whitespace-only OCR** (P1-3 guard): If OCR markdown is present but contains only whitespace, the extraction produces zero blocks. A post-extraction guard detects this and emits an `ocr_unreadable` failure block so the envelope never passes canonical validation as empty.
- **Short text** (< 20 chars): `extraction_confidence` reduced to 0.5, `quality_flags: ["short_text"]`.
- **Garbage characters** (> 10% non-printable): `readability` halved, `quality_flags: ["garbage_chars_detected"]`.
- **High garbage** (> 30%): Additional flag `"high_garbage_ratio"`.

## Watermark / Noise Handling

Watermarks, page headers/footers, and platform noise are **not silently deleted**. They are:

1. Detected via regex patterns (Chinese + English):
   - Watermark: "仅供...内部...使用", "CONFIDENTIAL", "严禁转载"
   - Page footer: "第X页/共Y页", "page X of Y"
   - Platform noise: "来自飞书", "扫码识别"
2. Classified as `system_event` blocks
3. Tagged with `metadata.noise_type` (`watermark`, `page_footer`, `platform_noise`)
4. Given `noise_score: 0.9` in `BlockQuality`
5. Listed in envelope `metadata.noise_watermark` array

Content blocks are **never mixed** with noise — noise detection runs before content classification.

## Multi-Column Layout Handling

When layout regions with bounding boxes are provided:
- Each region gets its own `ContentBlock` with `bbox: BoundingBox`
- `metadata.layout_available: true` marks the block as having spatial data
- `metadata.region_role` and `metadata.nested_source_type` record embedded content origins (e.g., `region_role: "embedded_tweet"`, `nested_source_type: "twitter"`)
- Region types map to canonical block types: `title` → `section_title`, `table` → `table_region`, `chart` → `chart_region`, `footer` → `system_event`

## P1 Fixes (post-review)

### P1-1: Fallback fabricates `image_text`

**Problem**: The fallback path emitted a placeholder `image_text` block (`[Image content not extracted: ...]`) for unreadable images, making them satisfy manifest requirements for `image_text` even though no image content was standardized. This was a false positive in the fixture gate.

**Fix**: Removed the fabricated `image_text` block from `_build_fallback_blocks`. Fallback now produces only:
- `section_title` — generated metadata title (low `extraction_confidence: 0.1`)
- `ocr_unreadable` — the actual failure signal

Updated the three image fixture manifests: `required_block_types` changed from `["image_text", "section_title"]` to `["ocr_unreadable", "section_title"]`.

### P1-2: Layout evidence discarded when OCR markdown exists

**Problem**: `standardize()` passed `layout_regions` into `_chunk_ocr_markdown()`, but that parameter was never used. If production had both OCR text and layout regions, F1 dropped bounding boxes and spatial boundaries.

**Fix**: Changed input path priority. When both `layout_regions` and `ocr_markdown` exist, the adapter now prefers layout regions (which preserve bbox, region_role, nested_source_type). Removed the unused `layout_regions` parameter from `_chunk_ocr_markdown`.

### P1-3: Whitespace-only OCR produces empty blocks

**Problem**: If `ocr_markdown` is present but contains only whitespace, `_chunk_ocr_markdown` returns an empty list, and the envelope fails `validate_canonical_f1()` with "blocks must not be empty".

**Fix**: Added a post-extraction guard in `standardize()`. After any extraction path, if no blocks were produced, emits a single `ocr_unreadable` failure block via `_build_extraction_failure_block()`.

## Uncovered Risks

1. **Vision API dependency**: The adapter's primary value comes from real OCR text. Vision/OCR is pinned to Xiaomi `mimo-v2.5`; without `MIMO_API_KEY`, images without pre-extracted OCR/layout data fall back to `section_title` metadata plus `ocr_unreadable` failure blocks. Production deployment requires MiMo API key configuration. Token Plan keys (`tp-*`) also require the matching token-plan base URL via `MIMO_BASE_URL` or `MIMO_VISION_BASE_URL`.

2. **Multi-language OCR**: Current noise patterns are Chinese/English only. Japanese, Korean financial documents may have unhandled noise patterns.

3. **Complex table detection**: Simple markdown table regex (`| col |` + `---`). Complex tables with merged cells, nested tables, or non-standard formatting may not be detected.

4. **Chart region identification**: The adapter relies on layout region metadata or markdown patterns to identify charts. Pure OCR text cannot reliably distinguish charts from tables.

5. **Image dimensions**: No image dimension analysis. Very long screenshots (>5000px) may need vertical splitting for downstream processing, which is not implemented.

6. **OCR confidence scores**: The vision API does not return per-region confidence scores. `extraction_confidence` is estimated from text quality heuristics, not actual OCR confidence.

## Test Results

```
tests/test_image_ocr_layout_standardizer.py    60 passed
tests/test_f1_standardization_fixtures.py      78 passed, 2 xfailed
                                               ─────────────────
                                               138 passed, 2 xfailed
```

**Test coverage by class**:
- `TestOCRMarkdownChunking`: 6 tests — headers, blank lines, tables, links, quotes, multiple headers
- `TestLayoutRegionMapping`: 7 tests — region type mapping, bbox extraction, empty regions, nested sources
- `TestNoiseDetection`: 7 tests — watermark, footer, platform noise, normal text, system_event blocks, content isolation
- `TestQualityScoring`: 6 tests — long text, empty text, short text, headers, garbage chars, noise blocks
- `TestProvenance`: 2 tests — provenance presence, source hash
- `TestMissingOCRFallback`: 6 tests — fallback blocks, no fabricated image_text (P1-1), error info, quality flags, whitespace-only OCR guard (P1-3), empty string OCR guard (P1-3)
- `TestCanonicalValidation`: 8 tests — schema version, source type, profile, legacy types, order, envelope_id
- `TestLayoutPath`: 3 tests — bbox end-to-end, canonical validation, layout-preferred-over-OCR (P1-2)
- `TestFixtureIntegration`: 4 tests × 3 fixtures — valid envelope, canonical validation, required types, no legacy types
- `TestRealOCRScenarios`: 3 tests — long OCR + watermark, long concatenated slide, two-column slide
