"""WeChat API Routes — REST endpoints for WeChat integration.

Provides endpoints for:
- QR code login with state machine
- Account management
- Article listing and syncing
- F0 ContentRecord integration
- Exporter health check
"""

from fastapi import APIRouter, Query

from finer.errors.exceptions import FinerError
from finer.errors.codes import ErrorCode
from datetime import datetime
from pathlib import Path
from typing import List
import logging

from finer.schemas.wechat import (
    LoginSessionResponse,
    LoginStatusResponse,
    AccountResponse,
    ArticleResponse,
    ArticleListResponse,
    SyncResultResponse,
    WeChatStatusResponse,
    ExporterHealthResponse,
    WeChatUnifiedConfig,
    WeChatSourceType,
    LoginStatus,
    ArticleSyncStatus,
)
from finer.services.wechat_session_store import (
    WeChatSessionStore,
    LoginState,
)
from finer.ingestion.wechat_exporter_client import WeChatExporterClient
from finer.ingestion.wechat_adapter import get_unified_wechat_adapter
from finer.paths import REPO_ROOT
from finer.config import load_wechat_service_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wechat"])

# --- Singletons (module-level, persists across requests) ---

_session_store = WeChatSessionStore(default_ttl=300)
_exporter_client: WeChatExporterClient | None = None


def _get_exporter_client() -> WeChatExporterClient:
    """Get or create the exporter client singleton.

    If a confirmed login session exists, sync the auth_key to the client
    so that article operations use the same authenticated session.
    """
    global _exporter_client
    if _exporter_client is None:
        config = load_wechat_service_config(REPO_ROOT)
        _exporter_client = WeChatExporterClient(base_url=config.exporter_url)

    # Sync auth_key from confirmed session if client doesn't have one
    if not _exporter_client.auth_key:
        for s in _session_store.get_confirmed_sessions():
            if s.exporter_session_id:
                _exporter_client.auth_key = s.exporter_session_id
                break
    return _exporter_client


def _get_adapter_config() -> WeChatUnifiedConfig:
    """Load WeChat config for the unified adapter."""
    config = load_wechat_service_config(REPO_ROOT)
    return WeChatUnifiedConfig(
        source_type=WeChatSourceType(config.source_type),
        exporter_url=config.exporter_url,
        prefer_exporter=config.prefer_exporter,
        cache_credentials=config.cache_credentials,
    )


# --- Login Endpoints ---

@router.post("/login", response_model=LoginSessionResponse)
async def create_login_session():
    """Create a new login session with QR code.

    Returns a session_id and QR data URI. Frontend should poll
    /login/{session_id}/status until state is confirmed or expired.
    """
    session = _session_store.create_session()

    try:
        client = _get_exporter_client()
        qr_bytes = await client.get_qrcode()

        session.qr_image_bytes = qr_bytes
        qr_data_uri = session.build_qr_data_uri()

        _session_store.transition(session.session_id, LoginState.QR_READY)

        return LoginSessionResponse(
            session_id=session.session_id,
            qr_data_uri=qr_data_uri,
            qr_url=qr_data_uri,
            expires_in=session.ttl_seconds,
            status=LoginStatus.QR_READY,
            source=WeChatSourceType.EXPORTER_SERVICE,
        )
    except Exception as e:
        logger.error(f"Failed to create login session: {e}")
        _session_store.transition(session.session_id, LoginState.FAILED, str(e))
        raise FinerError(ErrorCode.WX_EXT_001, f"Exporter unavailable: {e}", stage="F0", operation="wechat_login", source_channel="wechat", retryable=True, cause=e)


@router.get("/login/{session_id}/qr")
async def get_qr_code(session_id: str):
    """Get QR code data URI for a session."""
    session = _session_store.get_session(session_id)
    if session is None:
        raise FinerError(ErrorCode.WX_AUTH_001, "Session not found", stage="F0", operation="wechat_qr", source_channel="wechat", retryable=False)

    qr_data_uri = session.build_qr_data_uri()
    if not qr_data_uri:
        raise FinerError(ErrorCode.WX_AUTH_001, "QR code not available for this session", stage="F0", operation="wechat_qr", source_channel="wechat", retryable=False)

    return {"session_id": session_id, "qr_data_uri": qr_data_uri}


@router.get("/login/{session_id}/status", response_model=LoginStatusResponse)
async def check_login_status(session_id: str):
    """Poll login status for a session.

    Frontend should call this every 2-3 seconds until status is
    confirmed, expired, or failed.
    """
    session = _session_store.get_session(session_id)
    if session is None:
        raise FinerError(ErrorCode.WX_AUTH_001, "Session not found", stage="F0", operation="wechat_poll_status", source_channel="wechat", retryable=False)

    # If already terminal, return immediately
    if session.is_terminal:
        return LoginStatusResponse(
            session_id=session.session_id,
            status=LoginStatus(session.state.value),
            account_id=session.account_id,
            account_name=session.account_name,
            error_msg=session.login_error,
        )

    # Poll the exporter for scan status
    try:
        client = _get_exporter_client()
        from finer.ingestion.wechat_exporter_client import ScanStatus

        result = await client.poll_scan_status()

        if result.status == ScanStatus.CONFIRMED:
            _session_store.transition(session_id, LoginState.CONFIRMED)
            session.account_name = getattr(result, "nickname", "") or session.account_name
            # Store auth_key for article operations
            if _exporter_client and _exporter_client.auth_key:
                session.exporter_session_id = _exporter_client.auth_key
        elif result.status == ScanStatus.SCANNED:
            _session_store.transition(session_id, LoginState.SCANNED)
        elif result.status == ScanStatus.EXPIRED:
            _session_store.transition(session_id, LoginState.EXPIRED, "QR code expired")
        elif result.status == ScanStatus.ERROR:
            _session_store.transition(session_id, LoginState.FAILED, result.error_message or "Unknown error")

    except Exception as e:
        logger.warning(f"Failed to poll scan status: {e}")
        # Don't fail the endpoint — just return current state

    return LoginStatusResponse(
        session_id=session.session_id,
        status=LoginStatus(session.state.value),
        account_id=session.account_id if session.state == LoginState.CONFIRMED else None,
        account_name=session.account_name if session.state == LoginState.CONFIRMED else None,
        error_msg=session.login_error if session.state in (LoginState.FAILED, LoginState.EXPIRED) else None,
    )


# --- Account Endpoints ---

@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts():
    """List all cached WeChat accounts."""
    adapter = get_unified_wechat_adapter(REPO_ROOT, _get_adapter_config())
    accounts = await adapter.list_accounts()

    return [
        AccountResponse(
            account_id=acc.account_id,
            account_name=acc.account_name,
            last_sync=acc.last_sync,
            article_count=acc.article_count,
            is_valid=acc.is_valid,
        )
        for acc in accounts
    ]


# --- Article Endpoints ---

@router.get("/articles/{account_id}", response_model=ArticleListResponse)
async def list_articles(
    account_id: str,
    page: int = 0,
    page_size: int = 10,
    query: str | None = None,
):
    """List articles from a WeChat account.

    Uses the shared authenticated exporter client so that articles
    are fetched with the login session's credentials.
    """
    client = _get_exporter_client()

    try:
        result = await client.get_articles(account_id, begin=page * page_size, size=min(page_size, 10))
        articles = [
            ArticleResponse(
                article_id=str(a.aid),
                title=a.title,
                author=a.author,
                digest=a.digest,
                publish_time=datetime.fromtimestamp(a.create_time) if a.create_time else None,
                content_url=a.link,
                read_count=a.read_num,
                like_count=a.like_num,
                status=ArticleSyncStatus.PENDING,
            )
            for a in result.articles
        ]

        return ArticleListResponse(
            account_id=account_id,
            articles=articles,
            total=result.total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Failed to list articles: {e}")
        raise FinerError(ErrorCode.WX_EXT_001, f"Failed to list articles: {e}", stage="F0", operation="wechat_list_articles", source_channel="wechat", retryable=True, cause=e)


# --- Sync Endpoint ---

@router.post("/sync/{account_id}", response_model=SyncResultResponse)
async def sync_articles(
    account_id: str,
    max_articles: int | None = None,
    include_images: bool = False,
):
    """Sync articles from a WeChat account.

    Saves raw artifacts and builds F0 ContentRecords.
    Uses incremental sync — only fetches articles not yet synced.
    """
    from finer.services.wechat_artifact_store import WeChatArtifactStore
    from finer.services.wechat_content_record_builder import build_content_record

    client = _get_exporter_client()
    artifact_store = WeChatArtifactStore(REPO_ROOT)

    # Resolve account display name: try confirmed session, then account search
    account_name = account_id
    for s in _session_store.get_confirmed_sessions():
        if s.account_name:
            account_name = s.account_name
            break
    # If still a raw id, try searching the account via exporter
    if account_name == account_id:
        try:
            search_results = await client.search_account(account_id)
            if search_results:
                account_name = search_results[0].nickname
        except Exception:
            pass  # fallback to account_id

    try:
        # Load incremental sync state
        synced_ids = artifact_store.load_sync_state(account_id)

        # Paginate through all articles (get_articles caps size at 10)
        all_articles = []
        begin = 0
        page_size = 10
        while True:
            result = await client.get_articles(account_id, begin=begin, size=page_size)
            all_articles.extend(result.articles)
            if not result.has_more:
                break
            begin += page_size
            if max_articles and len(all_articles) >= max_articles:
                break

        synced_count = 0
        failed_count = 0
        errors: list[str] = []
        content_record_ids: list[str] = []
        article_paths: list[str] = []

        for article in all_articles:
            article_id = str(article.aid)
            if article_id in synced_ids:
                continue
            if max_articles and synced_count >= max_articles:
                break

            try:
                # Fetch raw content via exporter
                content = await client.export_article(
                    article.link, format="markdown"
                )

                # Save artifacts
                saved = artifact_store.save_article_artifacts(
                    account_id=account_id,
                    article_id=article_id,
                    html=b"",  # exporter returns markdown, not raw html
                    markdown=content,
                )

                # Build ContentRecord
                record = build_content_record(
                    article=article,
                    account_id=account_id,
                    account_name=account_name,
                    artifacts=saved,
                    exporter_session_id=_exporter_client.auth_key or "",
                )

                # Persist ContentRecord
                f0_dir = REPO_ROOT / "data" / "F0_intake" / "wechat" / account_id
                f0_dir.mkdir(parents=True, exist_ok=True)
                record_path = f0_dir / f"{record.content_id}.json"
                record_path.write_text(
                    record.model_dump_json(indent=2),
                    encoding="utf-8",
                )

                content_record_ids.append(record.content_id)
                article_paths.append(str(saved.raw_md_path))
                synced_count += 1

                # Update incremental sync state
                synced_ids.add(article_id)

            except Exception as e:
                failed_count += 1
                errors.append(f"Article {article_id}: {e}")
                logger.error(f"Failed to sync article {article_id}: {e}")

        # Persist updated sync state
        artifact_store.save_sync_state(account_id, synced_ids)

        return SyncResultResponse(
            account_id=account_id,
            synced_count=synced_count,
            failed_count=failed_count,
            articles=article_paths,
            content_record_ids=content_record_ids,
            errors=errors,
            l0_triggered=synced_count > 0,
        )

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise FinerError(ErrorCode.WX_EXT_001, f"Sync failed: {e}", stage="F0", operation="wechat_sync", source_channel="wechat", retryable=True, cause=e)


# --- Exporter Health ---

@router.get("/exporter/health", response_model=ExporterHealthResponse)
async def exporter_health():
    """Check wechat-article-exporter service health."""
    import time as _time

    config = load_wechat_service_config(REPO_ROOT)
    url = config.exporter_url

    try:
        import httpx
        start = _time.time()
        # Use proxy=None to bypass system proxy for local connections
        transport = httpx.AsyncHTTPTransport(proxy=None)
        async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
            resp = await client.get(f"{url}/api/web/login/scan")
            latency = (_time.time() - start) * 1000
            return ExporterHealthResponse(
                available=resp.status_code in (200, 401, 404),
                url=url,
                latency_ms=round(latency, 1),
            )
    except Exception as e:
        return ExporterHealthResponse(
            available=False,
            url=url,
            error=str(e),
        )


# --- Status Endpoint ---

@router.get("/status", response_model=WeChatStatusResponse)
async def get_wechat_status():
    """Get overall WeChat integration status."""
    config = load_wechat_service_config(REPO_ROOT)
    adapter = get_unified_wechat_adapter(REPO_ROOT, _get_adapter_config())

    # Check exporter availability
    exporter_available = False
    try:
        import httpx
        transport = httpx.AsyncHTTPTransport(proxy=None)
        async with httpx.AsyncClient(timeout=3.0, transport=transport) as client:
            resp = await client.get(f"{config.exporter_url}/api/web/login/scan")
            exporter_available = resp.status_code in (200, 401, 404)
    except Exception:
        pass

    accounts = await adapter.list_accounts()
    total_articles = sum(acc.article_count for acc in accounts)
    last_sync = max(
        (acc.last_sync for acc in accounts if acc.last_sync),
        default=None,
    )

    return WeChatStatusResponse(
        enabled=True,
        source_type=WeChatSourceType(config.source_type),
        exporter_available=exporter_available,
        exporter_url=config.exporter_url,
        accounts_count=len(accounts),
        total_articles_synced=total_articles,
        last_sync=last_sync,
        cache_dir=str(REPO_ROOT / "data" / "cache" / "wechat"),
        output_dir=str(REPO_ROOT / "data" / "raw" / "wechat"),
    )
