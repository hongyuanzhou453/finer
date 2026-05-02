from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Literal
from datetime import datetime

class ContentRecord(BaseModel):
    """
    Core metadata container for a piece of financial content.
    """
    model_config = ConfigDict(strict=False)

    content_id: str = Field(..., description="Unique identifier for the content")
    creator_name: str = Field(..., description="Name of the content creator (e.g., trader韭)")
    source_platform: str = Field(..., description="Platform where the content originated")
    content_type: Literal[
        "weekly_strategy_image",
        "daily_pre_image",
        "daily_post_image",
        "bilibili_video",
        "livestream_audio",
        "wechat_article",
        "wechat_video",
        "manual_upload",
        # F0 real data types (from production manifests)
        "chat_transcript",
        "chat_export",
        "unclassified",
        "research_report",
    ] = Field(..., description="Type of the content")
    
    published_at: datetime = Field(..., description="Time when the content was published")
    overall_summary: Optional[str] = Field(None, description="Executive summary of the whole content")
    title: Optional[str] = Field(None, description="Optional title of the content")
    source_url: Optional[str] = Field(None, description="URL to the original content if available")
    source_path: str = Field(..., description="Local path to the raw material file")
    
    language: Optional[str] = Field(None, description="Primary language of the content")
    market_scope: Optional[List[Literal["US", "HK", "A", "MIXED"]]] = Field(
        None, description="Market areas covered in the content"
    )
    metadata: dict = Field(default_factory=dict, description="Additional flexible metadata")
