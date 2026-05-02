# Agent Task — WeChat Article Exporter Integration

**Date**: 2026-05-02
**Owner stage**: F0 Intake + frontend data-source UI
**Touch scope**: `src/finer/ingestion/wechat_*`, `src/finer/api/routes/wechat.py`, `src/finer/schemas/wechat.py`, `src/finer_dashboard/src/components/data-source-config/`, `src/finer_dashboard/src/app/api/wechat/`, tests and docs for this feature
**Reference design**: `docs/reference/morningstar-cn-design-system.md`
**Reference implementation**: `wechat-article-exporter` project / `src/finer/ingestion/wechat_exporter_client.py`

## Mission

Bring the WeChat article acquisition capability from `wechat-article-exporter` into Finer OS as a reliable F0 ingestion path. The outcome must not be a loose proxy around the exporter. Finer OS should own the login/session state, article discovery, article export, raw artifact persistence, and F0 `ContentRecord` traceability.

## Hard Boundaries

- Do not modify F1.5/F2/F3+ logic.
- Do not parse investment topics, intent, entities, or trade actions.
- Do not store cookies, tokens, or QR auth payloads in code, docs, logs, screenshots, or committed fixtures.
- Do not replace the canonical F0/F1 schema with exporter-specific shapes.
- Do not delete existing WeChat code. If code is obsolete, mark it deprecated and route around it after tests prove the replacement path.

## Architecture Target

Implement WeChat acquisition as this flow:

```text
Frontend QR/Login UI
  -> Finer API `/api/wechat/*`
  -> WeChat exporter integration/service layer
  -> raw article artifacts under `data/raw/wechat/{account_id}/`
  -> F0 ContentRecord with trace metadata
  -> optional F1 standardization later through `wechat_article`
```

F0 must persist the raw evidence first. F1 should standardize saved HTML/Markdown later; F0 must not emit already-summarized article text as the only source.

## Required Traceability

Every fetched article must have enough metadata to reconstruct the acquisition chain:

- `content_id`: stable F0 id derived from platform/account/article id or canonical URL hash
- `source_platform`: `wechat`
- `content_type`: `wechat_article`
- `source_path`: saved raw artifact path
- `source_uri`: original WeChat article URL when available
- `published_at`: article publish time if exporter provides it; otherwise acquisition time plus `published_at_missing` flag
- `metadata.account_id`
- `metadata.account_name`
- `metadata.article_id`
- `metadata.article_url`
- `metadata.exporter_session_id`
- `metadata.exporter_request_id`
- `metadata.fetch_started_at`
- `metadata.fetch_completed_at`
- `metadata.raw_html_path`
- `metadata.raw_markdown_path`
- `metadata.raw_html_sha256`
- `metadata.raw_markdown_sha256`
- `metadata.cookie_store_id` or equivalent opaque credential reference, never the cookie value
- `metadata.acquisition_status`: `success | login_required | expired | failed`
- `metadata.acquisition_error_type` and `metadata.acquisition_error_message` for failures

## Backend Requirements

1. Audit the existing WeChat path:
   - `src/finer/ingestion/wechat_adapter.py`
   - `src/finer/ingestion/wechat_exporter_client.py`
   - `src/finer/api/routes/wechat.py`
   - `src/finer/schemas/wechat.py`
   - `docs/specs/wechat-integration.md`

2. Compare the current QR login implementation against `wechat-article-exporter`:
   - How the exporter initializes session cookies.
   - Which endpoint returns QR bytes vs QR URL.
   - How it polls status: pending, scanned, confirmed, expired, failed.
   - Why the current Finer OS QR image can refresh blank or expired.

3. Implement a stable login state machine:
   - `created`
   - `qr_ready`
   - `waiting_scan`
   - `scanned`
   - `confirmed`
   - `expired`
   - `failed`

4. Ensure QR display endpoint returns a browser-displayable payload:
   - Prefer base64 data URI when the upstream returns image bytes.
   - Preserve content type.
   - Do not expose upstream cookies to the frontend.

5. Article acquisition must save raw artifacts:
   - raw HTML if available
   - normalized Markdown if exporter provides it or if Finer converts it deterministically
   - metadata sidecar JSON with hashes and timestamps

6. Return `ContentRecord` objects, not ad hoc article dicts, when importing into the canonical pipeline.

## Frontend Requirements

Use `docs/reference/morningstar-cn-design-system.md` as the visual contract.

The WeChat UI should be a dense institutional data-source console:

- white page background, black/gray text, red only as precise status/brand signal
- underline tabs, not pill-heavy marketing tabs
- rule-based tables, no large rounded nested cards
- compact QR/login panel with clear scan states
- account list with source/account/status columns
- article table with title, publish time, source account, acquisition status, raw artifact link, F0 id
- sync controls as restrained outline buttons or black primary CTA

Required UX states:

- exporter service unavailable
- no logged-in account
- QR loading
- QR ready
- scanned but not confirmed
- login confirmed
- QR expired with refresh action
- article list loading
- article sync success
- article sync partial failure

## Tests

Add or update tests so the feature is not only visually wired:

- unit tests for QR/session state mapping
- tests for QR byte-to-data-URI conversion
- tests for article artifact hashing and sidecar metadata
- tests proving imported articles become valid `ContentRecord`
- API route tests for login/status/articles/sync paths
- frontend component tests if the project already supports them; otherwise include a Playwright smoke script or documented manual verification

Network/live WeChat tests must be opt-in and skipped by default unless a documented env flag is set.

## Review Report Required

Return a report with:

- files changed
- architecture before/after
- exact reason the old QR flow failed, or "not reproduced" with evidence
- traceability fields implemented
- tests run and results
- live/manual verification steps
- remaining risks, especially WeChat anti-bot/login instability
- screenshots or paths for frontend verification if available

