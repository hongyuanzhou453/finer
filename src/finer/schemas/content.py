from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional, List, Literal
from datetime import datetime


class ContentRecord(BaseModel):
    """
    F0 canonical content record — the single source of truth for intake metadata.

    Every piece of content entering the Finer pipeline MUST have a ContentRecord.
    This schema is defined by docs/specs/f-stage-contracts.md.
    """

    model_config = ConfigDict(strict=False)

    # --- identity ---
    content_id: str = Field(..., description="UUID v4 unique identifier for the content")

    # --- source classification ---
    source_type: Literal[
        "feishu_chat",
        "bilibili_video",
        "wechat_article",
        "manual_upload",
        "nlm_note",
        "chat_transcript",
        "chat_export",
        "livestream_audio",
        "weekly_strategy",
        "daily_pre",
        "daily_post",
        "research_report",
        "unclassified",
    ] = Field(..., description="Canonical intake source type")
    source_platform: str = Field(..., description="Platform where the content originated (feishu, bilibili, wechat, local, nlm)")

    # --- creator ---
    creator_id: Optional[str] = Field(None, description="Stable creator identifier (e.g. feishu user id, bilibili uid)")
    creator_name: Optional[str] = Field(None, description="Human-readable creator display name")

    # --- timestamps ---
    published_at: Optional[datetime] = Field(None, description="Original publication time (may be unknown)")
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="Time the content was collected/ingested")

    # --- content metadata ---
    title: Optional[str] = Field(None, description="Optional title of the content")
    raw_path: str = Field(..., description="Relative path to the raw material file under data/raw/")
    file_type: Literal[
        "chat_log",
        "image",
        "pdf",
        "doc",
        "audio",
        "video",
        "text",
    ] = Field(..., description="File type of the raw material")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional flexible metadata (extension, registered_via, etc.)")

    # --- optional linkage ---
    source_url: Optional[str] = Field(None, description="URL to the original content if available")
    external_source_id: Optional[str] = Field(None, description="Platform-native ID (e.g. feishu message_id, bilibili BV号)")
    dedupe_fingerprint: Optional[str] = Field(None, description="Hash-based deduplication fingerprint")

    # --- backward-compatible optional fields ---
    overall_summary: Optional[str] = Field(None, description="Executive summary of the whole content")
    language: Optional[str] = Field(None, description="Primary language of the content (BCP-47)")
    market_scope: Optional[List[Literal["US", "HK", "A", "MIXED"]]] = Field(
        None, description="Market areas covered in the content"
    )

    def to_manifest(self) -> "ContentManifest":
        """Convert to a dataclass-based ContentManifest for storage/serialization."""
        from finer.manifests import ContentManifest

        return ContentManifest(
            content_id=self.content_id,
            source_type=self.source_type,
            source_platform=self.source_platform,
            creator_id=self.creator_id,
            creator_name=self.creator_name,
            published_at=self.published_at.isoformat() if self.published_at else None,
            collected_at=self.collected_at.isoformat(),
            title=self.title,
            raw_path=self.raw_path,
            file_type=self.file_type,
            metadata=dict(self.metadata),
            source_url=self.source_url,
            external_source_id=self.external_source_id,
            dedupe_fingerprint=self.dedupe_fingerprint,
            overall_summary=self.overall_summary,
            language=self.language,
            market_scope=list(self.market_scope) if self.market_scope else None,
        )
