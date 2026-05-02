# PDF Document Standardizer — Implementation Report

**Date**: 2026-04-30
**F-stage**: F1
**Adapter**: `PDFStandardizer`
**Module**: `src/finer/parsing/pdf_standardizer.py`
**Tests**: `tests/test_pdf_document_standardizer.py`

## Overview

Implemented the F1 canonical adapter for PDF document standardization. Converts multi-page PDF documents into `ContentEnvelope` with ordered `ContentBlock[]`. Uses pdfplumber for text/table extraction with OCR fallback for scanned pages via vision API.

## Changes

| File | Type | Description |
|------|------|-------------|
| `src/finer/parsing/pdf_standardizer.py` | New | F1 canonical PDF adapter (~800 lines) |
| `tests/test_pdf_document_standardizer.py` | New | 40 unit tests across 11 test classes |
| `src/finer/parsing/__init__.py` | Modified | Added `PDFStandardizer` export |

## Per-Page Standardization Strategy

Each PDF page is processed independently through `_process_page()`:

1. **Full text extraction** — `page.extract_text()` for the raw page text
2. **Table extraction** — `page.extract_tables()` via pdfplumber, converted to markdown-like `| col | col |` format → `table_region` blocks
3. **Text extraction** — Split page text into paragraphs by blank lines, classify each, skip paragraphs that overlap with table regions → `section_title`, `paragraph`, `link_reference` blocks
4. **Chart/image detection** — If page has 3+ images covering >40% of page area → `chart_region` block
5. **OCR fallback** — If extracted text < 30 chars and no tables found, render page to PNG and send to vision API → replace text blocks with OCR results
6. **Unreadable guard** — If still no blocks for the page after all extraction paths → `ocr_unreadable` block
7. **Cover page marking** — `page_idx == 0` gets `metadata["cover_page"] = True` on all blocks

## Text Extraction vs OCR Fallback Trigger Conditions

| Condition | Action |
|-----------|--------|
| `page.extract_text()` ≥ 30 chars | Use pdfplumber text extraction (primary path) |
| `page.extract_text()` < 30 chars AND tables detected | Use table extraction only, skip OCR |
| `page.extract_text()` < 30 chars AND no tables | Trigger OCR fallback via vision API |
| Vision API returns < 10 chars | Emit `ocr_unreadable` block for the page |
| Vision API unavailable (no API key) | Emit `ocr_unreadable` block |

**OCR fallback** renders the page to a 150 DPI PNG via `page.to_image()`, base64 encodes it, and sends to the vision model with a Chinese prompt for markdown extraction. OCR-extracted blocks get `quality_flags: ["ocr_extracted"]` and `model_name` from the LLM client.

## Text Classification Logic

`_classify_text()` determines block_type for each paragraph:

1. **URL-containing short text** (< 300 chars with `https?://` match) → `link_reference`
2. **Short text** (≤ 2 lines, < 80 chars, no sentence-ending punctuation) → `section_title`
3. **Everything else** → `paragraph`

The link check runs before the title check to prevent URLs from being misclassified as section titles.

## Noise Detection

Noise patterns detected via regex, NOT silently deleted:

| Type | Patterns | Example |
|------|----------|---------|
| `watermark` | 仅供...内部...使用, CONFIDENTIAL, 严禁转载 | "仅供内部使用" |
| `page_footer` | 第X页/共Y页, page X of Y, 免责声明: | "第3页/共10页" |
| `platform_noise` | 来自飞书/微信, 扫码识别 | "来自飞书" |
| `page_header` | Flywheel, 配色应用指引, 品牌色/边框/功能色 | "Flywheel" |

Noise blocks are `system_event` type with `metadata.noise_type`, `noise_score: 0.9`, and listed in envelope `metadata.noise_watermark`.

## Quality Scoring Logic

Deterministic scoring (no LLM dependency) via `_score_block_quality()`:

| Dimension | Formula |
|-----------|---------|
| `readability` | 0.0 (empty), 0.4 (<20 chars), min(1.0, 0.6 + len/500) (normal). Halved if garbage_ratio > 10% |
| `structural_confidence` | 0.9 (title), 0.8 (table/chart), 0.95 (system_event), 0.7 (paragraph) |
| `extraction_confidence` | 0.85 (>50 chars, low garbage), 0.7 (>20 chars), 0.5 (>0, "short_text" flag), 0.0 (empty) |
| `completeness` | 1.0 (>10 chars), len/10.0 (≤10 chars) |
| `noise_score` | 0.1 (content blocks), 0.8 (system_event) |

**Garbage detection**: Non-printable chars (excluding `\n\r\t`). >10% → `readability *= 0.5` + `garbage_chars_detected` flag. >30% → additional `high_garbage_ratio` flag.

## Chart/Image Region Detection

`_detect_chart_regions()` uses image density heuristics:
- Counts `page.images` and sums their area
- If 3+ images AND image_area/page_area > 0.4 → emits a single `chart_region` block covering the full page
- Block text summarizes: first 200 chars of page text + "[Page contains N images and M graphic elements]"
- Metadata includes `image_count`, `rect_count`, `image_density`

## Post-Extraction Guards

1. **Empty PDF guard**: If the entire PDF yielded zero blocks → `_build_extraction_failure_block()` emits a single `ocr_unreadable` block with `quality_flags: ["extraction_empty", "ocr_failed"]`
2. **Empty page guard**: If a specific page has no blocks after all extraction paths → `_build_unreadable_page_block()` emits `ocr_unreadable` with `quality_flags: ["ocr_unreadable", "empty_page"]`

## P1 Fixes (post-implementation)

### P1-1: `_classify_text` URL/title priority

**Problem**: `_classify_text` checked for `section_title` before `link_reference`. Short text containing URLs (e.g., "详情 https://example.com/report") was misclassified as `section_title`.

**Fix**: Reordered checks — URL detection runs first, then title classification.

### P1-2: `source_hash` not auto-populated

**Problem**: `_build_block` passed `source_hash=None` to `BlockProvenance` when callers didn't provide it. Tests expected auto-population.

**Fix**: Changed `_build_block` to compute `source_hash = source_hash or self._hash_text(text)` — always populates the field.

### P1-3: Missing `QualityCard` import in tests

**Problem**: Test file was missing `from finer.schemas.quality import QualityCard`, causing `NameError` in 3 tests.

**Fix**: Added the import.

### P1-4: Invalid/unreadable PDFs crash instead of canonical failure output

**Problem**: `standardize()` called `pdfplumber.open()` without try/except. Corrupt, encrypted, or non-PDF files raised `PdfminerException` instead of returning a canonical `ContentEnvelope` with an `ocr_unreadable` failure block. F1 adapters must surface unreadable inputs as auditable canonical output, not crash.

**Fix**: Wrapped `pdfplumber.open()` in try/except. On failure, the adapter logs a warning and returns a canonical envelope containing a single `ocr_unreadable` block with `quality_flags: ["pdf_unreadable", "open_failed"]`. Added `_build_unreadable_pdf_block()` method. Added 4 tests: corrupt PDF, missing file, empty file, canonical validator pass on failure envelope.

### P2-1: Table text duplicated into paragraph blocks

**Problem**: `_text_likely_in_table()` only checked for markdown table markers (`|` and `---`). On the real PDF fixture, page 2 emitted both a `table_region` and a `paragraph` containing substantially the same text, so F1.5 would see duplicated evidence.

**Fix**: Replaced `_text_likely_in_table()` with `_bbox_overlaps_table()` that uses spatial bbox intersection. For each paragraph, `_extract_text_blocks()` now estimates the text bbox first, then checks if >50% of the text area overlaps with any table bbox. If so, the paragraph is skipped. Refactored the method signature to accept `text_bbox` and `table_bboxes` list. Added 4 tests for bbox overlap detection (high overlap, no overlap, partial overlap, multiple tables).

## Uncovered Risks

1. **Vision API dependency**: OCR fallback uses Xiaomi `mimo-v2.5` and requires `MIMO_API_KEY`. Without it, scanned pages produce `ocr_unreadable` blocks. Production deployment needs MiMo API key configuration. Token Plan keys (`tp-*`) also require the matching token-plan base URL via `MIMO_BASE_URL` or `MIMO_VISION_BASE_URL`.

2. **Text bbox estimation accuracy**: `_estimate_text_bbox()` uses character matching against `page.extract_words()`. Complex layouts (multi-column, rotated text) may produce inaccurate bboxes, affecting table overlap detection.

3. **Chart detection threshold**: The 3+ images / 40% density threshold may miss single large charts or over-detect pages with many small icons.

4. **Large PDFs**: No page limit or streaming. Very large PDFs (100+ pages) may hit memory limits.

## Test Results

```
tests/test_pdf_document_standardizer.py     48 passed
tests/test_f1_standardization_fixtures.py   80 passed
                                            ─────────────────
                                            128 passed
```

**Test coverage by class**:
- `TestParagraphSplitting`: 4 tests — double newline, single newline, no newlines, mixed
- `TestTextClassification`: 4 tests — title, paragraph, URL link reference, period-ending
- `TestNoiseDetection`: 6 tests — watermark, footer, platform noise, header, normal text, noise_type metadata
- `TestTableExtraction`: 2 tests — markdown format, bbox extraction
- `TestQualityScoring`: 6 tests — long text, empty text, short text, garbage chars, title structural, system_event noise
- `TestProvenance`: 3 tests — fields populated, source_hash auto-populated, model_name on OCR blocks
- `TestPageIndex`: 2 tests — page_index set, different pages
- `TestCoverPage`: 2 tests — cover_page metadata, not on page 1
- `TestCanonicalValidation`: 2 tests — schema_version v1.0, source_type pdf
- `TestEnvelopeConstruction`: 2 tests — sequential order_index, envelope_id propagated
- `TestFixtureIntegration`: 7 tests × 1 fixture — valid envelope, page_index populated, required types, min region types, no legacy types, canonical validation, cover/chapter identified
- `TestUnreadablePDF`: 4 tests — corrupt PDF, missing file, empty file, canonical validator on failure envelope (P1-4)
- `TestTableBboxOverlap`: 4 tests — high overlap, no overlap, partial overlap, multiple tables (P2-1)

**Test coverage by class**:
- `TestParagraphSplitting`: 4 tests — double newline, single newline, no newlines, mixed
- `TestTextClassification`: 4 tests — title, paragraph, URL link reference, period-ending
- `TestNoiseDetection`: 6 tests — watermark, footer, platform noise, header, normal text, noise_type metadata
- `TestTableExtraction`: 2 tests — markdown format, bbox extraction
- `TestQualityScoring`: 6 tests — long text, empty text, short text, garbage chars, title structural, system_event noise
- `TestProvenance`: 3 tests — fields populated, source_hash auto-populated (P1-2), model_name on OCR blocks
- `TestPageIndex`: 2 tests — page_index set, different pages
- `TestCoverPage`: 2 tests — cover_page metadata, not on page 1
- `TestCanonicalValidation`: 2 tests — schema_version v1.0, source_type pdf
- `TestEnvelopeConstruction`: 2 tests — sequential order_index, envelope_id propagated
- `TestFixtureIntegration`: 7 tests × 1 fixture — valid envelope, page_index populated, required types, min region types, no legacy types, canonical validation, cover/chapter identified
