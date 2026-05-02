# WeChat Article Exporter Integration — Review Report

**Date**: 2026-05-02
**Task spec**: `docs/specs/2026-05-02-agent-task-wechat-article-integration.md`

## Overview

Integrated wechat-article-exporter into Finer OS as a reliable F0 ingestion path. Fixed 5 critical bugs in the existing adapter, added session state machine, artifact persistence with SHA256 hashing, ContentRecord builder with full traceability, rate limiting, and redesigned frontend per Morningstar CN design system.

## Files Changed

| Action | File | Description |
|--------|------|-------------|
| New | `src/finer/services/wechat_session_store.py` | Login state machine with TTL-based expiry |
| New | `src/finer/services/wechat_artifact_store.py` | Raw artifact persistence + incremental sync |
| New | `src/finer/services/wechat_content_record_builder.py` | ContentRecord builder with trace metadata |
| Modify | `src/finer/ingestion/wechat_adapter.py` | Fixed 5 bugs (see below) |
| Modify | `src/finer/ingestion/wechat_exporter_client.py` | Added rate limiter (token-bucket) |
| Rewrite | `src/finer/api/routes/wechat.py` | New routes with session store + F0 integration |
| Modify | `src/finer/schemas/wechat.py` | Added LoginState enum, QR data URI, ExporterHealth |
| Modify | `src/finer_dashboard/src/lib/contracts.ts` | Added "wechat"/"bilibili" to SourceType + WeChat types |
| Rewrite | `src/finer_dashboard/src/components/data-source-config/WeChatConfig.tsx` | Morningstar CN design |
| Rewrite | `src/finer_dashboard/src/components/data-source-config/QRCodeDisplay.tsx` | State-driven display |
| Modify | `src/finer_dashboard/src/components/layout/source-filter.tsx` | Added wechat/bilibili labels |
| New | `tests/test_wechat_session_store.py` | 22 tests for state machine |
| New | `tests/test_qr_conversion.py` | 6 tests for bytes→data URI |
| New | `tests/test_wechat_artifact_store.py` | 10 tests for artifact persistence |
| New | `tests/test_wechat_content_record.py` | 10 tests for ContentRecord builder |
| New | `tests/test_wechat_api_routes.py` | 6 tests for API routes |
| New | `tests/test_wechat_live.py` | 3 opt-in live tests (skipped by default) |

## Architecture Before/After

**Before**: Each HTTP request to `/api/wechat/*` created a new `WeChatExporterClient` instance — session state (auth_key, uuid cookies) was lost between requests. QR login could never complete because the poll endpoint couldn't find the session. The `_login_via_exporter` method called `get_qrcode()` which returns bytes, then treated the result as a dict with `.get("qr_url")`. Article sync saved markdown files but produced no F0 ContentRecords.

**After**: Module-level singletons for `WeChatSessionStore` and `WeChatExporterClient` persist across requests. Login follows a deterministic state machine (created→qr_ready→waiting_scan→scanned→confirmed|expired|failed). QR bytes are converted to base64 data URIs immediately. Article sync saves raw artifacts with SHA256 hashes, builds valid `ContentRecord` objects, and persists them to `data/F0_intake/wechat/`. Incremental sync tracks already-synced article IDs to avoid re-fetching.

## Bugs Fixed

| # | Bug | Location | Fix |
|---|-----|----------|-----|
| 1 | `_login_via_exporter` treats bytes as dict | `wechat_adapter.py:L1042-1046` | `get_qrcode()` returns bytes; now encodes to base64 data URI |
| 2 | `search_account` tuple unpack | `wechat_adapter.py:L1097` | `search_account()` returns `list[WeChatAccountInfo]`, not tuple; access `.fakeid`, `.nickname` as attrs |
| 3 | `get_articles` tuple unpack | `wechat_adapter.py:L1136-1137` | `get_articles()` returns `ArticleListResult`, not tuple; access `.articles` list |
| 4 | `export_article` dict access | `wechat_adapter.py:L1215` | `export_article()` returns string, not dict; use directly |
| 5 | Session state lost across requests | `routes/wechat.py` | New client per request → module-level singleton + session store |
| 6 | `check_login_status` orphan sessions | `wechat_adapter.py:L1064-1078` | Properly handles `ScanResult` object instead of treating it as dict |

## Traceability Fields Implemented

Every fetched article's ContentRecord includes:

- `content_id`: SHA256(platform:account_id:article_id), stable across re-syncs
- `source_platform`: "wechat"
- `content_type`: "wechat_article"
- `source_path`: path to saved .md artifact
- `source_uri`: original article URL
- `published_at`: article publish time or acquisition time + `published_at_missing` flag
- `metadata.account_id`
- `metadata.account_name`
- `metadata.article_id`
- `metadata.article_url`
- `metadata.exporter_session_id`
- `metadata.exporter_request_id`
- `metadata.fetch_started_at`
- `metadata.fetch_completed_at`
- `metadata.raw_html_path`
- `metadata.raw_md_path`
- `metadata.raw_html_sha256`
- `metadata.raw_md_sha256`
- `metadata.acquisition_status`: success | login_required | expired | failed
- `metadata.published_at_missing`

## Tests Run

```
46 passed, 0 failed (2.44s)
```

- `test_wechat_session_store.py`: 22 tests — state transitions, TTL expiry, active session, confirmed sessions, purge
- `test_qr_conversion.py`: 6 tests — PNG/JPEG data URI, empty bytes, content preservation
- `test_wechat_artifact_store.py`: 10 tests — save markdown/HTML, SHA256, sidecar JSON, sync state
- `test_wechat_content_record.py`: 10 tests — basic fields, stable ID, metadata, published_at fallback, serialization
- `test_wechat_api_routes.py`: 6 tests — login success/failure, accounts, health check (mocked)
- `test_wechat_live.py`: 3 tests — skipped by default (requires `WECHAT_LIVE_TEST=1`)

Frontend build: `npm run build` passes.

## Live/Manual Verification Steps

1. Start exporter: `cd wechat-article-exporter && npm run dev` (port 3001)
2. Start backend: `uvicorn finer.api.server:app --reload --port 8000`
3. Start frontend: `cd src/finer_dashboard && npm run dev`
4. Navigate to data source config → WeChat tab
5. Click "获取二维码" → verify QR code displays as data URI image
6. Scan with WeChat → verify status transitions: qr_ready → scanned → confirmed
7. After login, verify accounts list shows the logged-in account
8. Click "同步全部" → verify articles saved to `data/raw/wechat/{account_id}/`
9. Verify ContentRecords created in `data/F0_intake/wechat/{account_id}/`
10. Verify `sync_state.json` tracks synced article IDs

## Remaining Risks

1. **WeChat anti-bot**: WeChat may rate-limit or block automated QR login flows. Rate limiter mitigates but cannot eliminate this risk.
2. **Exporter stability**: The wechat-article-exporter service is a third-party Nuxt.js app; its API contract may change. Health check endpoint provides early warning.
3. **Session TTL**: Default 300s may be too short for some users. Configurable via `WeChatSessionStore(default_ttl=...)`.
4. **Raw HTML not captured**: The exporter's `export_article` endpoint returns markdown, not raw HTML. The `raw_html_path` field will be null for exporter-sourced articles. Direct API path (legacy) captures HTML.
5. **No WeChatCredential storage**: The spec mentions `cookie_store_id` for credential references. Current implementation stores auth_key in the exporter client instance (in-memory). Persistent credential storage is deferred.
