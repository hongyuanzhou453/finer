"""KOL Rating API — KOL 评级数据查询.

Provides rating and performance metrics for KOLs (Key Opinion Leaders).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from finer.paths import DATA_ROOT

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# 类型定义
# ============================================

class DimensionScore(BaseModel):
    dimension: str
    score: float = Field(..., ge=0, le=5)
    label: str


class TimelinePoint(BaseModel):
    date: str
    rating: float
    return_pct: Optional[float] = None


class RecentOpinion(BaseModel):
    id: str
    ticker: str
    ticker_name: Optional[str] = None
    direction: str
    timestamp: str
    result: Optional[str] = None  # success, failed, pending


class KOLRatingResponse(BaseModel):
    rating: Dict[str, Any]
    dimensions: List[DimensionScore]
    timeline: List[TimelinePoint]
    focusAreas: List[str]
    recentOpinions: List[RecentOpinion]


# ============================================
# 数据加载
# ============================================

def _load_kol_data(kol_id: str) -> Optional[Dict[str, Any]]:
    """Load KOL data from F5/F6 layers (legacy L5_candidate/L6_annotated dirs)."""
    # Try F6 first (annotated data, legacy L6_annotated dir)
    l6_dir = DATA_ROOT / "L6_annotated"
    if l6_dir.exists():
        for file_path in l6_dir.glob("**/*.action.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if data.get("source", {}).get("creator_id") == kol_id:
                    return data
            except Exception:
                continue

    # Try F5 (candidate data, legacy L5_candidate dir)
    l5_dir = DATA_ROOT / "L5_candidate"
    if l5_dir.exists():
        for file_path in l5_dir.glob("**/*.action.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if data.get("source", {}).get("creator_id") == kol_id:
                    return data
            except Exception:
                continue

    return None


def _calculate_kol_rating(kol_id: str) -> KOLRatingResponse:
    """Calculate KOL rating from available data."""
    # Load all actions for this KOL
    actions: List[Dict[str, Any]] = []

    for layer in ["L5_candidate", "L6_annotated"]:
        layer_dir = DATA_ROOT / layer
        if not layer_dir.exists():
            continue
        for file_path in layer_dir.glob("**/*.action.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if data.get("source", {}).get("creator_id") == kol_id:
                    actions.append(data)
            except Exception:
                continue

    if not actions:
        # Return mock data if no real data
        return _generate_mock_rating(kol_id)

    # Calculate metrics from real data
    total = len(actions)
    success_count = 0
    failed_count = 0
    returns: List[float] = []
    tickers: Dict[str, int] = {}
    directions: Dict[str, int] = {}

    for action in actions:
        validation = action.get("validation_status", "pending")
        if validation == "verified":
            success_count += 1
        elif validation == "failed":
            failed_count += 1

        backtest = action.get("backtest_result")
        if backtest and backtest.get("return_pct"):
            returns.append(backtest["return_pct"])

        target = action.get("target", {})
        ticker = target.get("ticker_normalized") or target.get("ticker", "UNKNOWN")
        tickers[ticker] = tickers.get(ticker, 0) + 1

        direction = action.get("direction", "neutral")
        directions[direction] = directions.get(direction, 0) + 1

    # Calculate rating
    success_rate = success_count / total if total > 0 else 0.5
    avg_return = sum(returns) / len(returns) if returns else 0.0

    # Overall rating (1-5 scale)
    overall_rating = 1 + success_rate * 3 + (avg_return > 0) * 1
    overall_rating = max(1, min(5, round(overall_rating, 1)))

    # Dimension scores
    dimensions = [
        DimensionScore(dimension="accuracy", score=round(success_rate * 5, 1), label="准确率"),
        DimensionScore(dimension="consistency", score=round(3 + success_rate * 2, 1), label="一致性"),
        DimensionScore(dimension="timeliness", score=round(3.5, 1), label="时效性"),
        DimensionScore(dimension="depth", score=round(3.0, 1), label="深度"),
        DimensionScore(dimension="clarity", score=round(3.5, 1), label="清晰度"),
    ]

    # Timeline (last 30 days)
    timeline = []
    now = datetime.now()
    for i in range(30):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        timeline.append(TimelinePoint(
            date=date,
            rating=round(overall_rating - 0.5 + (i % 3) * 0.2, 1),
            return_pct=round(avg_return * (1 + (i % 5) * 0.1), 2) if returns else None,
        ))

    # Focus areas (top tickers)
    focus_areas = sorted(tickers.keys(), key=lambda t: tickers[t], reverse=True)[:5]

    # Recent opinions
    recent_opinions = []
    for action in actions[:10]:
        target = action.get("target", {})
        recent_opinions.append(RecentOpinion(
            id=action.get("trade_action_id", "unknown"),
            ticker=target.get("ticker_normalized") or target.get("ticker", "UNKNOWN"),
            ticker_name=target.get("company_name"),
            direction=action.get("direction", "neutral"),
            timestamp=action.get("timestamp", now.isoformat()),
            result=action.get("validation_status", "pending"),
        ))

    return KOLRatingResponse(
        rating={
            "kolId": kol_id,
            "name": kol_id,
            "platform": "Internal",
            "overallRating": overall_rating,
            "avgReturn": round(avg_return, 2),
            "successRate": round(success_rate, 2),
            "totalOpinions": total,
        },
        dimensions=dimensions,
        timeline=timeline,
        focusAreas=focus_areas,
        recentOpinions=recent_opinions,
    )


def _generate_mock_rating(kol_id: str) -> KOLRatingResponse:
    """Generate mock rating data when no real data available."""
    import random

    overall_rating = round(3 + random.random() * 1.5, 1)
    avg_return = round(random.uniform(-5, 15), 2)

    dimensions = [
        DimensionScore(dimension="accuracy", score=round(3 + random.random() * 1.5, 1), label="准确率"),
        DimensionScore(dimension="consistency", score=round(3 + random.random() * 1.5, 1), label="一致性"),
        DimensionScore(dimension="timeliness", score=round(3.5, 1), label="时效性"),
        DimensionScore(dimension="depth", score=round(3.0, 1), label="深度"),
        DimensionScore(dimension="clarity", score=round(3.5, 1), label="清晰度"),
    ]

    now = datetime.now()
    timeline = []
    for i in range(30):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        timeline.append(TimelinePoint(
            date=date,
            rating=round(overall_rating - 0.3 + random.random() * 0.5, 1),
            return_pct=round(avg_return + random.uniform(-2, 2), 2),
        ))

    focus_areas = ["NVDA", "AAPL", "TSLA", "AMD", "MSFT"]

    tickers = [("NVDA", "英伟达"), ("AAPL", "苹果"), ("TSLA", "特斯拉")]
    recent_opinions = []
    for i, (ticker, name) in enumerate(tickers):
        recent_opinions.append(RecentOpinion(
            id=f"opinion-{i}",
            ticker=ticker,
            ticker_name=name,
            direction=random.choice(["bullish", "bearish", "neutral"]),
            timestamp=(now - timedelta(days=i)).isoformat(),
            result=random.choice(["success", "failed", "pending"]),
        ))

    return KOLRatingResponse(
        rating={
            "kolId": kol_id,
            "name": kol_id,
            "platform": "Mock",
            "overallRating": overall_rating,
            "avgReturn": avg_return,
            "successRate": round(0.5 + random.random() * 0.3, 2),
            "totalOpinions": random.randint(50, 200),
        },
        dimensions=dimensions,
        timeline=timeline,
        focusAreas=focus_areas,
        recentOpinions=recent_opinions,
    )


# ============================================
# API 端点
# ============================================

@router.get("/rating/{kol_id}", response_model=KOLRatingResponse)
async def get_kol_rating(kol_id: str):
    """Get rating and performance metrics for a KOL."""
    return _calculate_kol_rating(kol_id)


@router.get("/list")
async def list_kols():
    """List all available KOLs."""
    kols: Dict[str, int] = {}

    for layer in ["L5_candidate", "L6_annotated"]:
        layer_dir = DATA_ROOT / layer
        if not layer_dir.exists():
            continue
        for file_path in layer_dir.glob("**/*.action.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                kol_id = data.get("source", {}).get("creator_id")
                if kol_id:
                    kols[kol_id] = kols.get(kol_id, 0) + 1
            except Exception:
                continue

    return {
        "kols": [{"id": k, "count": c} for k, c in sorted(kols.items(), key=lambda x: -x[1])],
        "total": len(kols),
    }


class KOLListItem(BaseModel):
    """KOL list item with rating data, aligned with frontend KOL type."""
    id: str
    name: str
    platform: str = ""
    platform_id: str = ""
    overall_score: float = Field(0.0, description="Overall rating 1-5")
    dimension_scores: Dict[str, float] = Field(default_factory=dict)
    accuracy: float = Field(0.0, description="Accuracy percentage 0-100")
    avg_return: float = Field(0.0, description="Average return percentage")
    total_opinions: int = 0
    last_active: str = ""
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True


def _discover_kol_ids() -> List[str]:
    """Discover all KOL IDs from data layers."""
    kol_ids: Dict[str, int] = {}
    for layer in ["L5_candidate", "L6_annotated"]:
        layer_dir = DATA_ROOT / layer
        if not layer_dir.exists():
            continue
        for file_path in layer_dir.glob("**/*.action.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                kol_id = data.get("source", {}).get("creator_id")
                if kol_id:
                    kol_ids[kol_id] = kol_ids.get(kol_id, 0) + 1
            except Exception:
                continue
    return [k for k, _ in sorted(kol_ids.items(), key=lambda x: -x[1])]


@router.get("/list/enriched", response_model=List[KOLListItem])
async def list_kols_enriched():
    """List all KOLs with full rating data."""
    kol_ids = _discover_kol_ids()
    result: List[KOLListItem] = []

    for kol_id in kol_ids:
        rating = _calculate_kol_rating(kol_id)
        dim_scores = {d.dimension: d.score for d in rating.dimensions}
        r = rating.rating

        result.append(KOLListItem(
            id=kol_id,
            name=r.get("name", kol_id),
            platform=r.get("platform", ""),
            overall_score=r.get("overallRating", 0.0),
            dimension_scores=dim_scores,
            accuracy=round(r.get("successRate", 0.0) * 100, 1),
            avg_return=r.get("avgReturn", 0.0),
            total_opinions=r.get("totalOpinions", 0),
            last_active=rating.timeline[0].date if rating.timeline else "",
            tags=rating.focusAreas[:3],
        ))

    return result