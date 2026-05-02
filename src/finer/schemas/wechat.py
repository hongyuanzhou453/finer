"""WeChat API Schemas — Request/Response models for WeChat integration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class LoginStatus(str, Enum):
    """Login session status — maps to session store LoginState."""
    CREATED = "created"
    QR_READY = "qr_ready"
    WAITING_SCAN = "waiting_scan"
    SCANNED = "scanned"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    FAILED = "failed"


class ArticleSyncStatus(str, Enum):
    """Article sync status."""
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    FAILED = "failed"


class WeChatSourceType(str, Enum):
    """Source type for WeChat integration."""
    DIRECT_API = "direct_api"           # Direct WeChat MP API
    EXPORTER_SERVICE = "exporter_service"  # wechat-article-exporter service
    HYBRID = "hybrid"                   # Use both with fallback


class ArticleExportFormat(str, Enum):
    """Article export format."""
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    TEXT = "text"


# Configuration models

class WeChatUnifiedConfig(BaseModel):
    """Unified WeChat configuration."""
    model_config = ConfigDict(strict=True)

    source_type: WeChatSourceType = Field(
        default=WeChatSourceType.HYBRID,
        description="Integration mode",
    )
    exporter_url: Optional[str] = Field(
        default="http://localhost:3000",
        description="wechat-article-exporter service URL",
    )
    prefer_exporter: bool = Field(
        default=True,
        description="Prefer exporter service when both available",
    )
    cache_credentials: bool = Field(default=True)
    cache_dir: str = Field(default="data/cache/wechat")
    output_dir: str = Field(default="data/raw/wechat")


# Request models

class SyncRequest(BaseModel):
    """Request to sync articles from an account."""
    account_id: str = Field(..., description="WeChat account ID")
    max_articles: Optional[int] = Field(None, description="Maximum articles to sync")
    include_images: bool = Field(False, description="Download images locally")
    include_comments: bool = Field(False, description="Include article comments")
    include_metadata: bool = Field(True, description="Include read/like counts")
    trigger_l0: bool = Field(True, description="Trigger F0 ingestion after sync")


class ArticleListRequest(BaseModel):
    """Request to list articles."""
    account_id: str = Field(..., description="WeChat account ID")
    page: int = Field(0, ge=0, description="Page number")
    page_size: int = Field(10, ge=1, le=50, description="Articles per page")
    query: Optional[str] = Field(None, description="Search query")


# Response models

class LoginSessionResponse(BaseModel):
    """Login session with QR code."""
    model_config = ConfigDict(strict=True)

    session_id: str = Field(..., description="Session ID for status polling")
    qr_data_uri: str = Field(default="", description="Browser-displayable data URI for QR code")
    qr_url: str = Field(default="", description="QR code URL or data URI (legacy)")
    qr_base64: Optional[str] = Field(None, description="QR code as base64 (legacy)")
    expires_in: int = Field(300, description="QR code validity in seconds")
    status: LoginStatus = Field(LoginStatus.CREATED)
    source: WeChatSourceType = Field(
        default=WeChatSourceType.HYBRID,
        description="Which integration source was used",
    )


class LoginStatusResponse(BaseModel):
    """Login status check result."""
    model_config = ConfigDict(strict=True)

    session_id: str
    status: LoginStatus
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    avatar_url: Optional[str] = None
    error_msg: Optional[str] = None


class AccountResponse(BaseModel):
    """WeChat account info."""
    model_config = ConfigDict(strict=True)

    account_id: str
    account_name: str
    avatar_url: Optional[str] = None
    signature: Optional[str] = None
    last_sync: Optional[datetime] = None
    article_count: int = 0
    is_valid: bool = True


class ArticleComment(BaseModel):
    """Article comment data."""
    model_config = ConfigDict(strict=True)

    comment_id: str
    author: str
    content: str
    like_count: int = 0
    reply_count: int = 0
    create_time: Optional[datetime] = None
    replies: List["ArticleComment"] = Field(default_factory=list)


class ArticleResponse(BaseModel):
    """Article metadata."""
    model_config = ConfigDict(strict=True)

    article_id: str
    title: str
    author: Optional[str] = None
    digest: Optional[str] = None
    publish_time: Optional[datetime] = None
    content_url: Optional[str] = None
    cover_url: Optional[str] = None
    local_path: Optional[str] = None

    # Stats (from exporter with credentials)
    read_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0

    # Comments
    comments: List[ArticleComment] = Field(default_factory=list)

    # Metadata
    source_type: WeChatSourceType = WeChatSourceType.DIRECT_API
    status: ArticleSyncStatus = ArticleSyncStatus.PENDING


class ArticleListResponse(BaseModel):
    """List of articles."""
    model_config = ConfigDict(strict=True)

    account_id: str
    articles: List[ArticleResponse]
    total: int
    page: int
    page_size: int


class SyncResultResponse(BaseModel):
    """Result of article sync."""
    model_config = ConfigDict(strict=True)

    account_id: str
    synced_count: int
    failed_count: int = 0
    articles: List[str] = Field(default_factory=list, description="Paths to synced articles")
    content_record_ids: List[str] = Field(default_factory=list, description="F0 ContentRecord IDs")
    errors: List[str] = Field(default_factory=list)
    l0_triggered: bool = False
    sync_time: datetime = Field(default_factory=datetime.now)
    source_type: WeChatSourceType = WeChatSourceType.HYBRID


class ExporterHealthResponse(BaseModel):
    """Exporter service health check result."""
    model_config = ConfigDict(strict=True)

    available: bool
    url: str
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class WeChatStatusResponse(BaseModel):
    """Overall WeChat integration status."""
    model_config = ConfigDict(strict=True)

    enabled: bool = True
    source_type: WeChatSourceType = WeChatSourceType.HYBRID
    exporter_available: bool = False
    exporter_url: Optional[str] = None
    accounts_count: int
    total_articles_synced: int
    last_sync: Optional[datetime] = None
    cache_dir: str
    output_dir: str


class WeChatCredential(BaseModel):
    """WeChat credentials for read counts and comments."""
    model_config = ConfigDict(strict=True)

    biz: str = Field(..., description="Account biz parameter")
    uin: str = Field(..., description="User UIN")
    key: str = Field(..., description="Key parameter")
    pass_ticket: str = Field(..., description="Pass ticket")
    wap_sid2: Optional[str] = None
    appmsg_token: Optional[str] = None
    cookie: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    valid: bool = True
