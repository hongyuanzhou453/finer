"""WeChat ContentRecord Builder — Convert exporter article data to F0 ContentRecord.

Builds a valid ContentRecord with all required traceability fields
for the WeChat acquisition chain.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from finer.schemas.content import ContentRecord
from finer.services.wechat_artifact_store import ArticleArtifacts

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, typing only
    from finer.ingestion.wechat_public_article import PublicArticle

logger = logging.getLogger(__name__)


def _derive_content_id(
    account_id: str,
    article_id: str,
    platform: str = "wechat",
) -> str:
    """Derive a stable, deterministic content_id from platform identifiers.

    Uses SHA256 of platform + account_id + article_id to ensure the same
    article always gets the same content_id across re-syncs.
    """
    raw = f"{platform}:{account_id}:{article_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_content_record(
    article: object,
    account_id: str,
    account_name: str,
    artifacts: ArticleArtifacts,
    exporter_session_id: str = "",
    exporter_request_id: str = "",
) -> ContentRecord:
    """Build a ContentRecord from exporter article data and saved artifacts.

    Args:
        article: Article object — supports both WeChatArticle (article_id,
                 content_url) and WeChatArticleInfo (aid, link) attribute names.
        account_id: WeChat account ID (fakeid)
        account_name: WeChat account display name
        artifacts: Saved artifact paths and hashes
        exporter_session_id: Exporter session identifier
        exporter_request_id: Exporter request identifier

    Returns:
        Valid ContentRecord with full traceability metadata
    """
    # Normalize article_id and content_url across both data sources
    article_id = getattr(article, "article_id", None) or str(getattr(article, "aid", ""))
    article_url = getattr(article, "content_url", None) or getattr(article, "link", "") or ""

    content_id = _derive_content_id(account_id, article_id)

    # Compute dedupe fingerprint from stable content identifiers
    dedupe_fingerprint = hashlib.sha256(
        f"wechat:{account_id}:{article_id}".encode("utf-8")
    ).hexdigest()[:16]

    # Handle published_at — may be None for some articles
    published_at_missing = False
    create_time = getattr(article, "publish_time", None) or getattr(article, "create_time", None)
    if create_time:
        published_at = create_time
        if isinstance(published_at, (int, float)):
            published_at = datetime.fromtimestamp(published_at, tz=timezone.utc)
    else:
        published_at = datetime.now(timezone.utc)
        published_at_missing = True

    now = datetime.now(timezone.utc)

    metadata = {
        "account_id": account_id,
        "account_name": account_name,
        "article_id": article_id,
        "article_url": article_url,
        "exporter_session_id": exporter_session_id,
        "exporter_request_id": exporter_request_id,
        "fetch_started_at": now.isoformat(),
        "fetch_completed_at": now.isoformat(),
        "raw_html_path": str(artifacts.raw_html_path) if artifacts.raw_html_path else None,
        "raw_md_path": str(artifacts.raw_md_path),
        "raw_html_sha256": artifacts.html_sha256,
        "raw_md_sha256": artifacts.md_sha256,
        "acquisition_status": "success",
        "published_at_missing": published_at_missing,
    }

    return ContentRecord(
        content_id=content_id,
        creator_id=account_id,
        creator_name=account_name,
        source_platform="wechat",
        source_type="wechat_article",
        published_at=published_at,
        title=getattr(article, "title", None),
        source_url=article_url or None,
        external_source_id=article_id,
        dedupe_fingerprint=dedupe_fingerprint,
        metadata=metadata,
        raw_path=str(artifacts.raw_md_path),
        file_type="text",
    )


def build_public_article_record(
    article: "PublicArticle",
    artifacts: ArticleArtifacts,
    *,
    acquired_via: str = "public_url",
    discovery_source: str = "manual",
) -> ContentRecord:
    """Build a ContentRecord for a credential-free public-page fetch.

    Separate from :func:`build_content_record` because the two paths key on
    different identifier spaces: the exporter keys on ``fakeid`` + ``aid``,
    while a public page keys on ``gh_*`` + ``mid``/``idx``. The same article
    fetched both ways would therefore land on different ``content_id`` values —
    acceptable today because the exporter path has produced zero real records,
    but worth knowing before any backfill mixes the two.

    ``discovery_source`` records *how the URL was found* (``manual``, an RSS
    bridge, a commercial API), which is the field to audit when a discovery
    source silently goes stale.
    """
    account_id = article.account_id
    article_id = article.article_id
    content_id = _derive_content_id(account_id, article_id)
    dedupe_fingerprint = hashlib.sha256(
        f"wechat:{account_id}:{article_id}".encode("utf-8")
    ).hexdigest()[:16]

    published_at_missing = article.published_at is None
    published_at = article.published_at or datetime.now(timezone.utc)
    # Bridge feeds report local offsets (Wechat2RSS emits +0800). Every
    # timestamp crossing a contract boundary must be aware UTC, and a naive
    # value is assumed to already be UTC rather than shifted.
    published_at = (
        published_at.astimezone(timezone.utc)
        if published_at.tzinfo
        else published_at.replace(tzinfo=timezone.utc)
    )
    now = datetime.now(timezone.utc)

    metadata = {
        "account_id": account_id,
        "account_name": article.account_name,
        "account_ghid": article.ghid,
        "account_biz": article.biz,
        "article_id": article_id,
        "article_url": article.source_url,
        "article_mid": article.mid,
        "article_idx": article.idx,
        "author": article.author,
        "acquired_via": acquired_via,
        "discovery_source": discovery_source,
        "fetch_started_at": now.isoformat(),
        "fetch_completed_at": now.isoformat(),
        "raw_html_path": str(artifacts.raw_html_path) if artifacts.raw_html_path else None,
        "raw_md_path": str(artifacts.raw_md_path),
        "raw_html_sha256": artifacts.html_sha256,
        "raw_md_sha256": artifacts.md_sha256,
        "acquisition_status": "success",
        "published_at_missing": published_at_missing,
        "image_count": len(article.image_urls),
    }

    return ContentRecord(
        content_id=content_id,
        creator_id=account_id,
        creator_name=article.account_name or account_id,
        source_platform="wechat",
        source_type="wechat_article",
        published_at=published_at,
        title=article.title or None,
        source_url=article.source_url,
        external_source_id=article_id,
        dedupe_fingerprint=dedupe_fingerprint,
        metadata=metadata,
        raw_path=str(artifacts.raw_md_path),
        file_type="text",
    )
