from fastapi import APIRouter, Body
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import json
from datetime import datetime
import re
from finer.paths import ensure_storage, REPO_ROOT, DATA_ROOT
from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError
from finer.schemas.contract import ReviewPayload
from finer.api.routes.files_utils import safe_file_name

router = APIRouter()
REVIEW_STORE_DIR = DATA_ROOT / "processed" / "review_store"
APPROVED_EVENTS_DIR = DATA_ROOT / "processed" / "approved_events"

class ReviewSaveRequest(BaseModel):
    assetId: str
    contentId: str
    status: str # "pending" | "approved" | "rejected"
    reviewerNotes: str
    assetName: Optional[str] = None
    payload: ReviewPayload

@router.post("")
async def save_review(body: ReviewSaveRequest):
    if not body.contentId or not body.payload:
        raise FinerError(ErrorCode.F6_IN_001, "Missing contentId or review payload", stage="F6", operation="submit_review", retryable=False)

    REVIEW_STORE_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    base_name = safe_file_name(body.contentId or body.assetId or "review_record")
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    review_record = {
        "version": "canonical_review_v1",
        "saved_at": timestamp,
        "asset_id": body.assetId,
        "content_id": body.contentId,
        "asset_name": body.assetName or body.contentId,
        "status": body.status,
        "reviewer_notes": body.reviewerNotes or "",
        "review_payload": body.payload.model_dump(by_alias=True)
    }
    
    review_path = REVIEW_STORE_DIR / f"{base_name}.review.json"
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review_record, f, ensure_ascii=False, indent=2)
        
    approved_path = None
    if body.status == "approved":
        approved_path = APPROVED_EVENTS_DIR / f"{base_name}.approved.json"
        approved_event = {
            "version": "canonical_approved_event_v1",
            "approved_at": timestamp,
            "content_id": body.contentId,
            "asset_name": body.assetName or body.contentId,
            "reviewer_notes": body.reviewerNotes or "",
            "event": body.payload.model_dump(by_alias=True)
        }
        with open(approved_path, "w", encoding="utf-8") as f:
            json.dump(approved_event, f, ensure_ascii=False, indent=2)
            
    return {
        "success": True,
        "contract": "canonical_review_v1",
        "reviewPath": str(review_path),
        "approvedPath": str(approved_path) if approved_path else None,
        "status": body.status
    }
