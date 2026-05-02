"""WeChat ContentRecord Builder — Convert exporter article data to F0 ContentRecord.

Builds a valid ContentRecord with all required traceability fields
for the WeChat acquisition chain.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from finer.schemas.content import ContentRecord
from finer.services.wechat_artifact_store import ArticleArtifacts

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
        creator_name=account_name,
        source_platform="wechat",
        content_type="wechat_article",
        published_at=published_at,
        title=getattr(article, "title", None),
        source_url=article_url or None,
        source_path=str(artifacts.raw_md_path),
        metadata=metadata,
    )
