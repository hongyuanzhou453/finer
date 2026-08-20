"""RLHF Feedback API — collect and manage human feedback for model improvement.

This module provides endpoints for:
- Submitting feedback on extracted TradeActions
- Managing pending reviews
- Exporting data for DPO/RLHF training
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from pathlib import Path
import json
from datetime import datetime
import uuid
import re

from finer.schemas.event import TradingAction
from finer.schemas.trade_action import PipelineSnapshot
from finer.paths import REPO_ROOT, DATA_ROOT
from finer.services.rlhf_assembler import (
    action_to_extraction_dict,
    build_pipeline_snapshot,
    build_preference,
)

router = APIRouter()
RLHF_DIR = DATA_ROOT / "rlhf"
FEEDBACKS_DIR = RLHF_DIR / "feedbacks"
INDEX_PATH = RLHF_DIR / "index.json"


# ============================================================================
# Schema Definitions
# ============================================================================

class ActionChainFeedback(BaseModel):
    """Feedback for a single action in the action chain."""
    model_config = ConfigDict(strict=True)

    sequence_order: int = Field(..., description="Order in action chain")
    action_type_correct: bool = Field(True, description="Whether action type is correct")
    action_type_correction: Optional[str] = Field(None, description="Corrected action type")
    trigger_correct: bool = Field(True, description="Whether trigger condition is correct")
    trigger_correction: Optional[str] = Field(None, description="Corrected trigger")
    target_price_correct: bool = Field(True, description="Whether target price is correct")
    target_price_correction: Optional[Dict[str, float]] = Field(
        None, description="Corrected price range {low, high}"
    )


class Preference(BaseModel):
    """DPO preference data for training."""
    model_config = ConfigDict(strict=True)

    chosen: Optional[str] = Field(None, description="JSON string of corrected output")
    rejected: Optional[str] = Field(None, description="JSON string of original (incorrect) output")
    is_original_correct: bool = Field(
        True, description="Whether original extraction was correct"
    )


class RLHFFeedback(BaseModel):
    """Complete feedback record for a TradeAction."""
    model_config = ConfigDict(strict=True)

    feedback_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique feedback identifier"
    )
    trade_action_id: str = Field(..., description="ID of the reviewed TradeAction")
    event_id: Optional[str] = Field(None, description="Parent event ID")
    content_id: Optional[str] = Field(None, description="Source content ID")

    # Overall rating
    rating: int = Field(..., ge=1, le=5, description="Overall quality rating 1-5")

    # Ticker validation
    ticker_correct: bool = Field(True, description="Whether ticker extraction is correct")
    ticker_correction: Optional[str] = Field(None, description="Corrected ticker")

    # Direction validation
    direction_correct: bool = Field(True, description="Whether direction is correct")
    direction_correction: Optional[Literal[
        "bullish", "bearish", "neutral", "watchlist", "risk_warning"
    ]] = Field(None, description="Corrected direction")

    # Action chain feedback
    action_chain_feedback: List[ActionChainFeedback] = Field(
        default_factory=list,
        description="Per-action feedback"
    )

    # Quick tags for common issues
    quick_tags: List[str] = Field(
        default_factory=list,
        description="Quick issue tags: '标的有误', '方向相反', '动作缺失', '价格错误', '条件错误'"
    )

    # Free-form notes
    notes: Optional[str] = Field(None, description="Additional reviewer notes")

    # Reviewer metadata
    reviewer_id: Optional[str] = Field(None, description="Reviewer identifier")
    reviewed_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of review"
    )

    # DPO training data
    preference: Optional[Preference] = Field(
        None,
        description="Preference data for DPO training"
    )

    # Original extraction for reference
    original_extraction: Optional[Dict[str, Any]] = Field(
        None,
        description="Original extraction result being reviewed"
    )

    # Pipeline version anchor — filled SERVER-SIDE from the reviewed action
    # (see rlhf_assembler.build_pipeline_snapshot); never trusted from client.
    pipeline_snapshot: Optional[PipelineSnapshot] = Field(
        None,
        description="Which pipeline version produced the judged output"
    )


class ReviewCorrections(BaseModel):
    """人工审核的逐字段修正（前端 RLHFReviewPanel 提交）。

    用于后端 build_preference 组装 DPO Preference。action_chain 为整链替换。
    """
    ticker: Optional[str] = Field(None, description="修正后的 ticker")
    direction: Optional[str] = Field(None, description="修正后的 direction")
    action_chain: Optional[List[Dict[str, Any]]] = Field(
        None, description="修正后的完整 action_chain（替换原链）"
    )


class RLHFFeedbackCreate(BaseModel):
    """Request body for creating a new feedback.

    两种提供 preference 的方式（二选一）：
    1. 直接给 `preference`（向后兼容）。
    2. 给 `corrections` + `original_extraction`（+ `flagged_as_error`），后端
       自动用 build_preference 组装 —— 前端 RLHFReviewPanel 走此路径。
    """
    trade_action_id: str
    event_id: Optional[str] = None
    content_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    ticker_correct: bool = True
    ticker_correction: Optional[str] = None
    direction_correct: bool = True
    direction_correction: Optional[str] = None
    action_chain_feedback: List[ActionChainFeedback] = []
    quick_tags: List[str] = []
    notes: Optional[str] = None
    reviewer_id: Optional[str] = None
    preference: Optional[Preference] = None
    original_extraction: Optional[Dict[str, Any]] = None
    # corrections-based preference assembly (环 B 桥)
    corrections: Optional[ReviewCorrections] = None
    flagged_as_error: bool = False


class RLHFFeedbackUpdate(BaseModel):
    """Request body for updating feedback."""
    rating: Optional[int] = Field(None, ge=1, le=5)
    ticker_correct: Optional[bool] = None
    ticker_correction: Optional[str] = None
    direction_correct: Optional[bool] = None
    direction_correction: Optional[str] = None
    action_chain_feedback: Optional[List[ActionChainFeedback]] = None
    quick_tags: Optional[List[str]] = None
    notes: Optional[str] = None
    preference: Optional[Preference] = None


class PendingActionChainStep(BaseModel):
    """复核面板需要的操作链步骤（camelCase：直接喂前端，不再要中间适配器）。"""
    model_config = ConfigDict(strict=True)

    id: str
    actionType: str
    instrumentType: str = ""
    triggerCondition: str = ""
    targetPriceLow: Optional[str] = None
    targetPriceHigh: Optional[str] = None
    #: F5 ActionStep 没有分步置信度与状态。**不编造**——前端按缺失渲染。
    confidence: Optional[float] = None
    status: Optional[str] = None


class PendingActionItem(BaseModel):
    """待复核项。

    字段名刻意用 camelCase 对齐 `RLHFReviewPanel.RLHFReviewItem`：面板拿到
    响应后是 `setItems(data.items)` 直接赋值、没有适配层，snake_case 会让
    originalText/rationale/actionChain 全部渲染成 undefined（这正是该面板
    从未真正跑起来的原因之一）。
    """
    model_config = ConfigDict(strict=True)

    id: str
    trade_action_id: str
    content_id: Optional[str] = None
    sourceFile: str = ""
    originalText: str = ""
    extractedAt: Optional[str] = None

    ticker: str
    direction: str
    rationale: str = ""
    timeHorizon: str = ""
    actionChain: List[PendingActionChainStep] = Field(default_factory=list)

    #: F5 只有单一 confidence，没有分字段置信度。给出的是同一个值，
    #: 语义是「这条抽取整体的把握」，不是「ticker 判对的把握」——
    #: 前端文案必须如实标注，不得把它读成分字段准确度。
    confidence: Optional[float] = None

    has_feedback: bool = False
    feedback_id: Optional[str] = None


class RLHFStats(BaseModel):
    """Statistics on feedback collection."""
    model_config = ConfigDict(strict=True)

    total_feedbacks: int = 0
    average_rating: float = 0.0
    rating_distribution: Dict[str, int] = Field(default_factory=lambda: {
        "1": 0, "2": 0, "3": 0, "4": 0, "5": 0
    })
    ticker_accuracy: float = 0.0
    direction_accuracy: float = 0.0
    common_tags: List[Dict[str, Any]] = Field(default_factory=list)
    pending_reviews: int = 0
    dpo_ready_count: int = 0


class DPOExportItem(BaseModel):
    """Single DPO training example."""
    model_config = ConfigDict(strict=True)

    prompt: str
    chosen: str
    rejected: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Helper Functions
# ============================================================================

def ensure_directories():
    """Create necessary directories if they don't exist."""
    FEEDBACKS_DIR.mkdir(parents=True, exist_ok=True)
    RLHF_DIR.mkdir(parents=True, exist_ok=True)


def load_index() -> Dict[str, Any]:
    """Load the feedback index."""
    ensure_directories()
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"feedbacks": {}, "stats": {}}
    return {"feedbacks": {}, "stats": {}}


def save_index(index: Dict[str, Any]):
    """Save the feedback index."""
    ensure_directories()
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_feedback_path(feedback_id: str) -> Path:
    """Get path to feedback file."""
    return FEEDBACKS_DIR / f"{feedback_id}.json"


def load_feedback(feedback_id: str) -> Optional[RLHFFeedback]:
    """Load a single feedback by ID."""
    path = get_feedback_path(feedback_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        # Lax validation: JSON round-trips serialize datetimes as strings,
        # which the model's strict config would reject (latent since day one
        # — data/rlhf was empty until the first real feedback landed).
        return RLHFFeedback.model_validate(data, strict=False)
    return None


def update_index_stats(index: Dict[str, Any]) -> Dict[str, Any]:
    """Recalculate statistics from feedback files."""
    feedbacks = index.get("feedbacks", {})

    if not feedbacks:
        return {
            "total": 0,
            "avg_rating": 0.0,
            "rating_distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            "ticker_accuracy": 0.0,
            "direction_accuracy": 0.0,
            "common_tags": [],
            "dpo_ready": 0,
        }

    total = len(feedbacks)
    ratings = []
    ticker_correct_count = 0
    direction_correct_count = 0
    tag_counts: Dict[str, int] = {}
    dpo_ready = 0

    for fb_id, fb_meta in feedbacks.items():
        fb = load_feedback(fb_id)
        if fb:
            ratings.append(fb.rating)
            if fb.ticker_correct:
                ticker_correct_count += 1
            if fb.direction_correct:
                direction_correct_count += 1
            for tag in fb.quick_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if fb.preference and not fb.preference.is_original_correct:
                dpo_ready += 1

    avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
    rating_dist = {str(i): ratings.count(i) for i in range(1, 6)}

    # Sort tags by frequency
    common_tags = sorted(
        [{"tag": k, "count": v} for k, v in tag_counts.items()],
        key=lambda x: -x["count"]
    )[:10]

    return {
        "total": total,
        "avg_rating": round(avg_rating, 2),
        "rating_distribution": rating_dist,
        "ticker_accuracy": round(ticker_correct_count / total, 2) if total > 0 else 0.0,
        "direction_accuracy": round(direction_correct_count / total, 2) if total > 0 else 0.0,
        "common_tags": common_tags,
        "dpo_ready": dpo_ready,
    }


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/submit")
async def submit_feedback(body: RLHFFeedbackCreate):
    """Submit a new feedback for a TradeAction.

    Creates a feedback record and updates the index.
    """
    ensure_directories()

    # 版本锚定：服务端从被评 action 的文件真值回填（不信 client）。
    # action 找不到时 snapshot 置 None，不阻塞提交。
    pipeline_snapshot = None
    reviewed_action = None
    try:
        from finer.services.repository import TradeActionRepository

        repo = TradeActionRepository()
        reviewed_action = repo.load(body.trade_action_id)
        if reviewed_action is not None:
            record = repo.db.get_by_id(body.trade_action_id)
            source_file = record.get("file_path") if record else None
            pipeline_snapshot = build_pipeline_snapshot(reviewed_action, source_file)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "pipeline snapshot unavailable for %s: %s", body.trade_action_id, exc
        )

    # original_extraction 兜底：client 没给时由 action 组装（含 evidence_text，
    # 否则 DPO export 会因缺 evidence_text 全量跳过）。
    original_extraction = body.original_extraction
    if not original_extraction and reviewed_action is not None:
        original_extraction = action_to_extraction_dict(reviewed_action)

    # 组装 DPO preference：优先用直接提供的 preference；否则用 corrections + original 组装（环 B 桥）
    preference = body.preference
    if preference is None and (body.corrections is not None or original_extraction):
        pref_dict = build_preference(
            original_extraction,
            body.corrections.model_dump() if body.corrections else None,
            body.flagged_as_error,
        )
        preference = Preference(**pref_dict)

    feedback = RLHFFeedback(
        trade_action_id=body.trade_action_id,
        event_id=body.event_id,
        content_id=body.content_id,
        rating=body.rating,
        ticker_correct=body.ticker_correct,
        ticker_correction=body.ticker_correction,
        direction_correct=body.direction_correct,
        direction_correction=body.direction_correction,
        action_chain_feedback=body.action_chain_feedback,
        quick_tags=body.quick_tags,
        notes=body.notes,
        reviewer_id=body.reviewer_id,
        preference=preference,
        original_extraction=original_extraction,
        pipeline_snapshot=pipeline_snapshot,
        reviewed_at=datetime.now(),
    )

    # Save feedback file
    feedback_path = get_feedback_path(feedback.feedback_id)
    feedback_path.write_text(
        json.dumps(feedback.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )

    # Update index
    index = load_index()
    index["feedbacks"][feedback.feedback_id] = {
        "trade_action_id": feedback.trade_action_id,
        "event_id": feedback.event_id,
        "content_id": feedback.content_id,
        "rating": feedback.rating,
        "reviewed_at": feedback.reviewed_at.isoformat(),
        "has_preference": feedback.preference is not None,
    }
    index["stats"] = update_index_stats(index)
    save_index(index)

    return {
        "success": True,
        "feedback_id": feedback.feedback_id,
        "path": str(feedback_path),
    }


@router.get("/pending")
async def get_pending_actions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    has_feedback: Optional[bool] = Query(None, description="Filter by feedback status"),
):
    """待人工复核的 canonical F5 TradeAction 列表。

    数据源（2026-08-17 修正）：原本 glob 的是 ``data/L0_ingestion/extractions/``
    ——L0→F0 迁移后该目录**根本不存在**，所以这个端点一直返回空数组，
    `RLHFReviewPanel` 也就永远没有可复核的条目。而 DPO 实训的前置正是
    「用该面板对已结算 action 积累偏好对」（docs/specs/2026-07-13-...md P2#8）。
    现改为读 canonical F5，与记分卡/记录卡同一个 repository。

    只回已结算的 action（有 backtest_result.return_pct）：复核的价值在于
    「判断对不对」，未结算的还没有对错可言。
    """
    from finer.services.repository import TradeActionRepository

    pending_items: List[PendingActionItem] = []
    index = load_index()

    # Build a map of already reviewed action_ids
    reviewed_actions = {
        fb["trade_action_id"]: fb_id
        for fb_id, fb in index.get("feedbacks", {}).items()
    }

    repo = TradeActionRepository(
        db_path=DATA_ROOT / "cache" / "trade_actions.db",
        action_dir=DATA_ROOT / "F5_executed",
    )
    for action in repo.load_all_actions():
        if (action.metadata or {}).get("superseded_by"):
            continue
        br = action.backtest_result
        if br is None or br.return_pct is None:
            continue

        action_id = action.trade_action_id
        has_fb = action_id in reviewed_actions
        if has_feedback is not None and has_fb != has_feedback:
            continue

        target = action.target
        chain = [
            PendingActionChainStep(
                id=f"{action_id}-{step.sequence}",
                actionType=getattr(step.action_type, "value", str(step.action_type)),
                instrumentType=getattr(
                    target.instrument_type, "value", str(target.instrument_type or "")
                ) if target is not None else "",
                triggerCondition=step.trigger_condition or "",
                targetPriceLow=(
                    str(step.target_price_low) if step.target_price_low is not None else None
                ),
                targetPriceHigh=(
                    str(step.target_price_high) if step.target_price_high is not None else None
                ),
            )
            for step in (action.action_chain or [])
        ]

        pending_items.append(PendingActionItem(
            id=action_id,
            trade_action_id=action_id,
            content_id=action.source.content_id if action.source else None,
            sourceFile=(action.source.content_id if action.source else "") or "",
            originalText=(action.source.evidence_text if action.source else "") or "",
            extractedAt=action.timestamp.isoformat() if action.timestamp else None,
            ticker=(target.ticker if target else "") or "",
            direction=getattr(action.direction, "value", str(action.direction)),
            rationale=action.rationale or "",
            timeHorizon=action.time_horizon or "",
            actionChain=chain,
            confidence=action.confidence,
            has_feedback=has_fb,
            feedback_id=reviewed_actions.get(action_id),
        ))

    # 未复核的排在前面；同组内按抽取时间倒序（extractedAt 是 ISO 字符串，
    # 字典序即时间序——原代码对 datetime 调 fromisoformat，一旦有数据必崩）。
    pending_items.sort(key=lambda x: (x.has_feedback, x.extractedAt or ""), reverse=False)
    pending_items.sort(key=lambda x: x.extractedAt or "", reverse=True)
    pending_items.sort(key=lambda x: x.has_feedback)

    # Apply pagination
    total = len(pending_items)
    paginated = pending_items[offset:offset + limit]

    return {
        "items": [item.model_dump() for item in paginated],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }


@router.get("/action/{action_id}")
async def get_action_detail(action_id: str):
    """Get detailed information about a TradeAction.

    Returns the original extraction and any existing feedback.
    """
    index = load_index()

    # Find the feedback for this action
    feedback_id = None
    for fb_id, fb_meta in index.get("feedbacks", {}).items():
        if fb_meta.get("trade_action_id") == action_id:
            feedback_id = fb_id
            break

    # Try to find the original extraction
    extraction_dir = DATA_ROOT / "L0_ingestion" / "extractions"
    original_extraction = None

    if extraction_dir.exists():
        for extraction_file in extraction_dir.glob("*.json"):
            try:
                data = json.loads(extraction_file.read_text(encoding="utf-8"))
                for event in data.get("events", []):
                    event_id = event.get("event_id")
                    content_id = event.get("content_id")
                    ticker = event.get("ticker", "")

                    candidate_id = event_id or f"action_{content_id}_{ticker}"
                    if candidate_id == action_id:
                        original_extraction = event
                        break
                if original_extraction:
                    break
            except (json.JSONDecodeError, KeyError):
                continue

    # Load existing feedback if any
    feedback = None
    if feedback_id:
        feedback = load_feedback(feedback_id)

    return {
        "action_id": action_id,
        "original_extraction": original_extraction,
        "feedback": feedback.model_dump() if feedback else None,
        "feedback_id": feedback_id,
    }


@router.put("/action/{action_id}")
async def update_feedback(action_id: str, body: RLHFFeedbackUpdate):
    """Update an existing feedback for a TradeAction."""
    index = load_index()

    # Find the feedback for this action
    feedback_id = None
    for fb_id, fb_meta in index.get("feedbacks", {}).items():
        if fb_meta.get("trade_action_id") == action_id:
            feedback_id = fb_id
            break

    if not feedback_id:
        raise HTTPException(
            status_code=404,
            detail=f"No feedback found for action {action_id}"
        )

    # Load existing feedback
    feedback = load_feedback(feedback_id)
    if not feedback:
        raise HTTPException(
            status_code=404,
            detail=f"Feedback file not found: {feedback_id}"
        )

    # Apply updates
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(feedback, field, value)

    feedback.reviewed_at = datetime.now()

    # Save updated feedback
    feedback_path = get_feedback_path(feedback_id)
    feedback_path.write_text(
        json.dumps(feedback.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )

    # Update index
    index["feedbacks"][feedback_id]["rating"] = feedback.rating
    index["feedbacks"][feedback_id]["reviewed_at"] = feedback.reviewed_at.isoformat()
    index["feedbacks"][feedback_id]["has_preference"] = feedback.preference is not None
    index["stats"] = update_index_stats(index)
    save_index(index)

    return {
        "success": True,
        "feedback_id": feedback_id,
    }


@router.get("/stats")
async def get_feedback_stats():
    """Get statistics on feedback collection."""
    index = load_index()
    stats = update_index_stats(index)

    # Count pending (unreviewed) actions
    extraction_dir = DATA_ROOT / "L0_ingestion" / "extractions"
    total_actions = 0

    if extraction_dir.exists():
        for extraction_file in extraction_dir.glob("*.json"):
            try:
                data = json.loads(extraction_file.read_text(encoding="utf-8"))
                total_actions += len(data.get("events", []))
            except (json.JSONDecodeError, KeyError):
                continue

    pending_reviews = total_actions - stats["total"]

    return RLHFStats(
        total_feedbacks=stats["total"],
        average_rating=stats["avg_rating"],
        rating_distribution=stats["rating_distribution"],
        ticker_accuracy=stats["ticker_accuracy"],
        direction_accuracy=stats["direction_accuracy"],
        common_tags=stats["common_tags"],
        pending_reviews=max(0, pending_reviews),
        dpo_ready_count=stats["dpo_ready"],
    ).model_dump()


@router.get("/export")
async def export_dpo_data(
    min_rating: int = Query(1, ge=1, le=5, description="Minimum rating to include"),
    only_with_preference: bool = Query(True, description="Only include items with preference data"),
    format: str = Query("jsonl", pattern="^(json|jsonl)$"),
):
    """Export feedback data for DPO training.

    Returns data in format suitable for Direct Preference Optimization training.
    """
    index = load_index()
    feedbacks = index.get("feedbacks", {})

    export_items: List[DPOExportItem] = []

    for fb_id, fb_meta in feedbacks.items():
        if fb_meta.get("rating", 0) < min_rating:
            continue

        feedback = load_feedback(fb_id)
        if not feedback:
            continue

        if only_with_preference and (not feedback.preference or feedback.preference.is_original_correct):
            continue

        # Build DPO item
        if feedback.preference and feedback.preference.chosen and feedback.preference.rejected:
            export_items.append(DPOExportItem(
                prompt=f"从以下文本提取 Trade Action:\n{feedback.original_extraction.get('evidence_text', '')}",
                chosen=feedback.preference.chosen,
                rejected=feedback.preference.rejected,
                metadata={
                    "feedback_id": fb_id,
                    "rating": feedback.rating,
                    "ticker_correct": feedback.ticker_correct,
                    "direction_correct": feedback.direction_correct,
                    "quick_tags": feedback.quick_tags,
                }
            ))

    if format == "jsonl":
        # JSONL format (one JSON per line)
        lines = [
            json.dumps(item.model_dump(), ensure_ascii=False)
            for item in export_items
        ]
        return {
            "format": "jsonl",
            "count": len(export_items),
            "data": "\n".join(lines),
        }
    else:
        # JSON array format
        return {
            "format": "json",
            "count": len(export_items),
            "data": [item.model_dump() for item in export_items],
        }


@router.get("/feedbacks")
async def list_feedbacks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
):
    """List all feedbacks with optional filtering."""
    index = load_index()
    feedbacks = index.get("feedbacks", {})

    items = []
    for fb_id, fb_meta in feedbacks.items():
        rating = fb_meta.get("rating", 0)
        if min_rating is not None and rating < min_rating:
            continue
        if max_rating is not None and rating > max_rating:
            continue

        feedback = load_feedback(fb_id)
        if feedback:
            items.append(feedback.model_dump())

    # Sort by reviewed_at (newest first)
    items.sort(
        key=lambda x: x.get("reviewed_at", ""),
        reverse=True
    )

    total = len(items)
    paginated = items[offset:offset + limit]

    return {
        "items": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/feedback/{feedback_id}")
async def delete_feedback(feedback_id: str):
    """Delete a feedback record."""
    index = load_index()

    if feedback_id not in index.get("feedbacks", {}):
        raise HTTPException(
            status_code=404,
            detail=f"Feedback not found: {feedback_id}"
        )

    # Remove file
    feedback_path = get_feedback_path(feedback_id)
    if feedback_path.exists():
        feedback_path.unlink()

    # Update index
    del index["feedbacks"][feedback_id]
    index["stats"] = update_index_stats(index)
    save_index(index)

    return {"success": True, "deleted_id": feedback_id}
