"""Opinion Timeline API — 观点时间线数据查询.

Reads real TradeAction data from F5/F6 layers via TradeActionRepository,
with mock data fallback when no real data is available.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from finer.paths import DATA_ROOT
from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError
from finer.schemas.trade_action import (
    ActionStep as TradeActionStep,
    TradeAction,
    ValidationStatus,
)
from finer.services.repository import TradeActionRepository
from finer.services.storage import DateRange

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# 类型定义
# ============================================

class ActionStep(BaseModel):
    id: str
    actionType: Literal["watch", "long", "short", "close_long", "close_short"]
    triggerCondition: Optional[str] = None
    targetPriceLow: Optional[str] = None
    targetPriceHigh: Optional[str] = None


class TimelineOpinion(BaseModel):
    id: str
    timestamp: str
    ticker: str
    tickerName: Optional[str] = None
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(..., ge=0, le=1)
    verificationStatus: Literal["success", "failed", "pending"]

    # 验证结果
    priceChange: Optional[float] = None
    holdingDays: Optional[int] = None

    # 来源信息
    sourceText: str
    author: Optional[str] = None
    platform: Optional[str] = None

    # Action Chain
    actionChain: Optional[List[ActionStep]] = None

    # RLHF 状态
    rlhfStatus: Optional[Literal["pending", "reviewed", "skipped"]] = None
    rlhfRating: Optional[int] = None


class TimelineData(BaseModel):
    opinions: List[TimelineOpinion]
    total: int
    hasMore: bool
    nextCursor: Optional[str] = None


class TimelineMeta(BaseModel):
    tickers: List[str]
    kols: List[str]
    totalOpinions: int
    timeRange: Dict[str, str]


# ============================================
# Repository 单例
# ============================================

_repository: Optional[TradeActionRepository] = None


def _get_repository() -> TradeActionRepository:
    """Get or create the TradeActionRepository singleton."""
    global _repository
    if _repository is None:
        _repository = TradeActionRepository()
    return _repository


# ============================================
# TradeAction -> TimelineOpinion 转换
# ============================================

# ActionType 枚举值到前端展示值的映射
_ACTION_TYPE_MAP = {
    "long": "long",
    "short": "short",
    "close_long": "close_long",
    "close_short": "close_short",
    "buy_call": "long",
    "sell_call": "close_long",
    "buy_put": "short",
    "sell_put": "close_short",
    "hold": "watch",
    "watch": "watch",
    "buy_and_hold": "long",
}

# TradeDirection 枚举值到前端方向值的映射
_DIRECTION_MAP = {
    "bullish": "bullish",
    "bearish": "bearish",
    "neutral": "neutral",
    "watchlist": "neutral",
    "risk_warning": "bearish",
}

# ValidationStatus 枚举值到前端验证状态值的映射
_VALIDATION_STATUS_MAP = {
    "pending": "pending",
    "verified": "success",
    "failed": "failed",
    "under_review": "pending",
}


def _convert_action_step(step: TradeActionStep) -> ActionStep:
    """Convert a schema ActionStep to the API ActionStep model."""
    action_type_value = step.action_type.value
    mapped_type = _ACTION_TYPE_MAP.get(action_type_value, "watch")

    return ActionStep(
        id=f"step-{step.sequence}",
        actionType=mapped_type,  # type: ignore[arg-type]
        triggerCondition=step.trigger_condition,
        targetPriceLow=str(step.target_price_low) if step.target_price_low is not None else None,
        targetPriceHigh=str(step.target_price_high) if step.target_price_high is not None else None,
    )


def trade_action_to_opinion(action: TradeAction) -> TimelineOpinion:
    """Convert a TradeAction to a TimelineOpinion for the API response."""
    direction_value = action.direction.value
    mapped_direction = _DIRECTION_MAP.get(direction_value, "neutral")

    status_value = action.validation_status.value
    mapped_status = _VALIDATION_STATUS_MAP.get(status_value, "pending")

    # Extract price change from backtest result
    price_change = None
    holding_days = None
    if action.backtest_result:
        price_change = action.backtest_result.return_pct
        holding_days = action.backtest_result.holding_days

    # Map RLHF feedback
    rlhf_status: Optional[str] = None
    rlhf_rating: Optional[int] = None
    if action.rlhf_feedback:
        if action.rlhf_feedback.rating is not None:
            rlhf_status = "reviewed"
            rlhf_rating = action.rlhf_feedback.rating
        elif action.rlhf_feedback.is_correct is not None:
            rlhf_status = "reviewed"
        else:
            rlhf_status = "pending"

    # Convert action chain
    action_chain: Optional[List[ActionStep]] = None
    if action.action_chain:
        action_chain = [_convert_action_step(s) for s in action.action_chain]

    # Extract author from source info
    author = action.source.creator_id
    # Platform is not directly available in TradeAction; use content_url domain or leave empty
    platform = None

    # Ticker name from target info
    ticker_name = action.target.company_name

    return TimelineOpinion(
        id=action.trade_action_id,
        timestamp=action.timestamp.isoformat(),
        ticker=action.target.ticker_normalized or action.target.ticker,
        tickerName=ticker_name,
        direction=mapped_direction,  # type: ignore[arg-type]
        confidence=round(action.confidence, 2),
        verificationStatus=mapped_status,  # type: ignore[arg-type]
        priceChange=round(price_change, 2) if price_change is not None else None,
        holdingDays=holding_days,
        sourceText=action.source.evidence_text,
        author=author,
        platform=platform,
        actionChain=action_chain,
        rlhfStatus=rlhf_status,  # type: ignore[arg-type]
        rlhfRating=rlhf_rating,
    )


# ============================================
# 真实数据查询
# ============================================

def _load_actions_from_dir(action_dir: Path) -> List[TradeAction]:
    """Load all TradeAction JSON files from a directory (recursive)."""
    actions: List[TradeAction] = []
    if not action_dir.exists():
        return actions
    for file_path in action_dir.glob("**/*.action.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            actions.append(TradeAction.from_dict(data))
        except Exception as e:
            logger.warning("Failed to load TradeAction from %s: %s", file_path, e)
    return actions


def _has_real_data() -> bool:
    """Check if any TradeAction data exists in the file system."""
    l5_dir = DATA_ROOT / "L5_candidate"    # legacy dir
    l6_dir = DATA_ROOT / "L6_annotated"    # legacy dir
    for d in (l5_dir, l6_dir):
        if d.exists() and any(d.glob("**/*.action.json")):
            return True
    return False


def _query_real_timeline(
    ticker_list: List[str],
    direction_list: List[str],
    kol_list: List[str],
    start_time: datetime,
    end_time: datetime,
    offset: int,
    limit: int,
) -> tuple[List[TimelineOpinion], int]:
    """Query real TradeAction data and convert to TimelineOpinion list.

    Reads from both L5_candidate/F5 (via repository index) and L6_annotated/F6
    (direct file scan). Deduplicates by trade_action_id.

    Returns:
        Tuple of (opinions, total_count).
    """
    repo = _get_repository()

    # Collect all actions, deduplicated by trade_action_id
    seen_ids: set[str] = set()
    all_actions: List[TradeAction] = []

    # --- F5 data: use repository index for efficient querying ---
    date_range = DateRange(start=start_time, end=end_time)

    if len(kol_list) == 1:
        # Single KOL: use DB-level filter
        records = repo.db.query(
            creator_id=kol_list[0],
            direction=direction_list[0] if len(direction_list) == 1 else None,
            date_range=date_range,
            limit=10000,
            offset=0,
        )
    else:
        records = repo.db.query(
            direction=direction_list[0] if len(direction_list) == 1 else None,
            date_range=date_range,
            limit=10000,
            offset=0,
        )

    for record in records:
        file_path = record.get("file_path")
        if not file_path:
            continue
        try:
            action = repo._load_from_file(Path(file_path))
            if action.trade_action_id not in seen_ids:
                seen_ids.add(action.trade_action_id)
                all_actions.append(action)
        except Exception as e:
            logger.warning("Failed to load TradeAction from %s: %s", file_path, e)

    # --- F6 data: direct file scan (annotated/reviewed actions, legacy L6_annotated dir) ---
    l6_dir = DATA_ROOT / "L6_annotated"
    for action in _load_actions_from_dir(l6_dir):
        if action.trade_action_id not in seen_ids:
            seen_ids.add(action.trade_action_id)
            all_actions.append(action)

    # --- In-memory filters for multi-value fields ---
    if len(kol_list) > 1:
        all_actions = [a for a in all_actions if a.source.creator_id in kol_list]
    if len(direction_list) > 1:
        all_actions = [a for a in all_actions if a.direction.value in direction_list]
    if ticker_list:
        normalized_tickers = {t.upper() for t in ticker_list}
        all_actions = [
            a for a in all_actions
            if (a.target.ticker_normalized or a.target.ticker).upper() in normalized_tickers
        ]

    # Sort by timestamp descending
    all_actions.sort(key=lambda a: a.timestamp, reverse=True)

    total = len(all_actions)

    # Apply pagination
    paginated = all_actions[offset: offset + limit]

    # Convert to TimelineOpinion
    opinions = [trade_action_to_opinion(a) for a in paginated]

    return opinions, total


def _load_all_actions() -> List[TradeAction]:
    """Load all TradeAction data from F5 (via repository) and F6 (file scan, legacy L6_annotated dir).

    Deduplicates by trade_action_id.
    """
    repo = _get_repository()
    seen_ids: set[str] = set()
    all_actions: List[TradeAction] = []

    # F5 data via repository index
    records = repo.db.query(limit=100000, offset=0)
    for record in records:
        file_path = record.get("file_path")
        if not file_path:
            continue
        try:
            action = repo._load_from_file(Path(file_path))
            if action.trade_action_id not in seen_ids:
                seen_ids.add(action.trade_action_id)
                all_actions.append(action)
        except Exception as e:
            logger.warning("Failed to load TradeAction from %s: %s", file_path, e)

    # F6 data via direct file scan (legacy L6_annotated dir)
    l6_dir = DATA_ROOT / "L6_annotated"
    for action in _load_actions_from_dir(l6_dir):
        if action.trade_action_id not in seen_ids:
            seen_ids.add(action.trade_action_id)
            all_actions.append(action)

    return all_actions


def _get_real_meta() -> TimelineMeta:
    """Get meta information from real data (F5 + F6)."""
    all_actions = _load_all_actions()

    tickers_set: set[str] = set()
    kols_set: set[str] = set()
    timestamps: List[str] = []

    for action in all_actions:
        tickers_set.add(action.target.ticker_normalized or action.target.ticker)
        if action.source.creator_id:
            kols_set.add(action.source.creator_id)
        timestamps.append(action.timestamp.isoformat())

    now = datetime.now()
    time_range = {
        "min": min(timestamps) if timestamps else (now - timedelta(days=365)).isoformat(),
        "max": max(timestamps) if timestamps else now.isoformat(),
    }

    return TimelineMeta(
        tickers=sorted(tickers_set),
        kols=sorted(kols_set),
        totalOpinions=len(all_actions),
        timeRange=time_range,
    )


def _get_real_stats(time_range: str, ticker: Optional[str]) -> Dict[str, Any]:
    """Get statistics summary from real data (F5 + F6)."""
    all_actions = _load_all_actions()

    now = datetime.now()
    time_range_map = {
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "1Y": timedelta(days=365),
        "ALL": timedelta(days=365 * 2),
    }
    start_time = now - time_range_map.get(time_range, timedelta(days=30))

    # Filter by time range and ticker
    filtered: List[TradeAction] = []
    for action in all_actions:
        if action.timestamp < start_time:
            continue
        if ticker and (action.target.ticker_normalized or action.target.ticker).upper() != ticker.upper():
            continue
        filtered.append(action)

    if not filtered:
        return {
            "total": 0,
            "byDirection": {"bullish": 0, "bearish": 0, "neutral": 0},
            "byStatus": {"success": 0, "failed": 0, "pending": 0},
            "avgConfidence": 0.0,
            "avgPriceChange": 0.0,
            "topTickers": [],
            "topKols": [],
        }

    # Aggregate
    by_direction: Dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
    by_status: Dict[str, int] = {"success": 0, "failed": 0, "pending": 0}
    confidences: List[float] = []
    price_changes: List[float] = []
    ticker_counts: Dict[str, int] = {}
    ticker_success: Dict[str, List[bool]] = {}
    kol_counts: Dict[str, int] = {}

    for action in filtered:
        # Direction
        d = action.direction.value
        if d in by_direction:
            by_direction[d] += 1
        elif d == "watchlist":
            by_direction["neutral"] += 1
        elif d == "risk_warning":
            by_direction["bearish"] += 1

        # Validation status
        s = action.validation_status.value
        mapped_s = _VALIDATION_STATUS_MAP.get(s, "pending")
        if mapped_s in by_status:
            by_status[mapped_s] += 1

        confidences.append(action.confidence)

        # Backtest price change
        if action.backtest_result and action.backtest_result.return_pct is not None:
            price_changes.append(action.backtest_result.return_pct)

        # Ticker counts
        t = action.target.ticker_normalized or action.target.ticker
        ticker_counts[t] = ticker_counts.get(t, 0) + 1
        if action.validation_status == ValidationStatus.VERIFIED:
            ticker_success.setdefault(t, []).append(True)
        elif action.validation_status == ValidationStatus.FAILED:
            ticker_success.setdefault(t, []).append(False)

        # KOL counts
        kol = action.source.creator_id or ""
        if kol:
            kol_counts[kol] = kol_counts.get(kol, 0) + 1

    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    avg_price_change = round(sum(price_changes) / len(price_changes), 2) if price_changes else 0.0

    # Top tickers
    top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_ticker_list = [
        {
            "ticker": t,
            "count": cnt,
            "successRate": round(
                sum(1 for v in ticker_success.get(t, []) if v) / len(ticker_success[t]), 2
            ) if t in ticker_success and ticker_success[t] else 0.0,
        }
        for t, cnt in top_tickers
    ]

    # Top KOLs
    top_kols = sorted(kol_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_kol_list = [
        {"author": k, "count": cnt, "avgRating": 0.0}
        for k, cnt in top_kols
    ]

    return {
        "total": len(filtered),
        "byDirection": by_direction,
        "byStatus": by_status,
        "avgConfidence": avg_confidence,
        "avgPriceChange": avg_price_change,
        "topTickers": top_ticker_list,
        "topKols": top_kol_list,
    }


# ============================================
# Mock 数据生成（fallback）
# ============================================

def _generate_mock_opinion(index: int, base_time: datetime) -> TimelineOpinion:
    """生成单个模拟观点."""
    import math
    import random

    tickers = [
        ("NVDA", "英伟达"),
        ("AAPL", "苹果"),
        ("TSLA", "特斯拉"),
        ("AMD", "超微半导体"),
        ("MSFT", "微软"),
        ("GOOGL", "谷歌"),
        ("AMZN", "亚马逊"),
        ("META", "Meta"),
        ("BRK.B", "伯克希尔B"),
        ("JPM", "摩根大通"),
    ]

    authors = ["分析师张三", "李四", "王五", "财通证券", "中信证券", "高盛研究", "摩根士丹利", "内部研究"]
    platforms = ["财通证券", "中信证券", "高盛研究", "摩根士丹利", "内部研究", "外部研报"]

    directions = ["bullish", "bearish", "neutral"]
    verification_statuses = ["success", "failed", "pending"]

    ticker, ticker_name = random.choice(tickers)
    direction = random.choice(directions)
    status = random.choice(verification_statuses)

    # 根据方向调整成功/失败概率
    if direction == "bullish":
        status_weights = [0.5, 0.3, 0.2]  # success, failed, pending
    elif direction == "bearish":
        status_weights = [0.4, 0.4, 0.2]
    else:
        status_weights = [0.6, 0.2, 0.2]

    status = random.choices(verification_statuses, weights=status_weights)[0]

    # 生成时间戳
    time_offset = timedelta(
        days=random.randint(0, 90),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )
    timestamp = (base_time - time_offset).isoformat()

    # 生成置信度 (根据验证状态调整)
    if status == "success":
        confidence = random.uniform(0.6, 0.95)
    elif status == "failed":
        confidence = random.uniform(0.4, 0.8)
    else:
        confidence = random.uniform(0.5, 0.9)

    # 生成验证结果
    price_change = None
    holding_days = None
    if status != "pending":
        if direction == "bullish":
            price_change = random.uniform(-15, 35)
        elif direction == "bearish":
            price_change = random.uniform(-35, 15)
        else:
            price_change = random.uniform(-10, 10)
        holding_days = random.randint(3, 60)

    # 生成原文
    direction_texts = {
        "bullish": {"performance": "强劲", "trend": "上涨", "valuation": "合理", "view": "多", "suggestion": "积极关注", "earnings": "超预期", "reaction": "积极"},
        "bearish": {"performance": "疲软", "trend": "下跌", "valuation": "偏高", "view": "空", "suggestion": "谨慎对待", "earnings": "低于预期", "reaction": "负面"},
        "neutral": {"performance": "平稳", "trend": "震荡", "valuation": "合理", "view": "中性", "suggestion": "观望为主", "earnings": "符合预期", "reaction": "平稳"},
    }
    texts = direction_texts[direction]

    source_templates = [
        f"分析师认为{ticker}在当前市场环境下具有较好的投资价值，建议关注后续走势。从技术面来看，支撑位明确，可考虑逢低布局。",
        f"{ticker}近期表现{texts['performance']}，技术面显示有进一步{texts['trend']}空间。",
        f"从基本面分析来看，{ticker}估值处于{texts['valuation']}区间，短期看{texts['view']}。建议投资者{texts['suggestion']}。",
        f"{ticker}发布了{texts['earnings']}的财报，市场反应{texts['reaction']}。后续需关注催化剂。",
    ]
    source_text = random.choice(source_templates)

    # 生成 Action Chain
    action_chain = None
    if random.random() > 0.3:
        num_steps = random.randint(1, 3)
        action_chain = []
        action_types = ["watch", "long", "short", "close_long", "close_short"]

        for i in range(num_steps):
            step = ActionStep(
                id=f"step-{i}",
                actionType=random.choice(action_types[:3] if i == 0 else action_types),
                triggerCondition="突破前高" if i == 0 and random.random() > 0.5 else None,
                targetPriceLow=str(random.randint(100, 300)),
                targetPriceHigh=str(random.randint(300, 600)),
            )
            action_chain.append(step)

    # RLHF 状态
    rlhf_status = random.choice(["pending", "reviewed", "skipped", None])
    rlhf_rating = random.randint(1, 5) if rlhf_status == "reviewed" else None

    return TimelineOpinion(
        id=f"opinion-{index}",
        timestamp=timestamp,
        ticker=ticker,
        tickerName=ticker_name,
        direction=direction,
        confidence=round(confidence, 2),
        verificationStatus=status,
        priceChange=round(price_change, 2) if price_change else None,
        holdingDays=holding_days,
        sourceText=source_text,
        author=random.choice(authors),
        platform=random.choice(platforms),
        actionChain=action_chain,
        rlhfStatus=rlhf_status,
        rlhfRating=rlhf_rating,
    )


# ============================================
# API 端点
# ============================================

@router.get("/timeline", response_model=TimelineData)
async def get_timeline(
    timeRange: str = Query("1M", description="时间范围: 1W, 1M, 3M, 1Y, ALL"),
    tickers: Optional[str] = Query(None, description="标的列表，逗号分隔"),
    directions: Optional[str] = Query(None, description="方向列表，逗号分隔"),
    kols: Optional[str] = Query(None, description="KOL列表，逗号分隔"),
    cursor: Optional[str] = Query(None, description="分页游标"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取观点时间线数据."""
    # 解析筛选条件
    ticker_list = tickers.split(",") if tickers else []
    direction_list = directions.split(",") if directions else []
    kol_list = kols.split(",") if kols else []

    # 计算时间范围
    now = datetime.now()
    time_range_map = {
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "1Y": timedelta(days=365),
        "ALL": timedelta(days=365 * 2),
    }
    start_time = now - time_range_map.get(timeRange, timedelta(days=30))

    # 解析游标
    offset = int(cursor) if cursor else 0

    # 尝试读取真实数据
    use_real_data = _has_real_data()

    if use_real_data:
        try:
            opinions, total = _query_real_timeline(
                ticker_list=ticker_list,
                direction_list=direction_list,
                kol_list=kol_list,
                start_time=start_time,
                end_time=now,
                offset=offset,
                limit=limit,
            )
            has_more = offset + limit < total
            next_cursor = str(offset + limit) if has_more else None

            return TimelineData(
                opinions=opinions,
                total=total,
                hasMore=has_more,
                nextCursor=next_cursor,
            )
        except Exception as e:
            logger.warning("Failed to query real data, falling back to mock: %s", e)

    # Fallback: mock 数据
    import random

    total_count = random.randint(100, 500)
    opinions = []

    for i in range(offset, offset + limit):
        if i >= total_count:
            break
        opinion = _generate_mock_opinion(i, now)

        # 应用筛选
        if ticker_list and opinion.ticker not in ticker_list:
            continue
        if direction_list and opinion.direction not in direction_list:
            continue
        if kol_list and opinion.author not in kol_list:
            continue

        # 时间范围筛选
        opinion_time = datetime.fromisoformat(opinion.timestamp)
        if opinion_time < start_time:
            continue

        opinions.append(opinion)

    has_more = offset + limit < total_count
    next_cursor = str(offset + limit) if has_more else None

    return TimelineData(
        opinions=opinions,
        total=total_count,
        hasMore=has_more,
        nextCursor=next_cursor,
    )


@router.get("/meta", response_model=TimelineMeta)
async def get_timeline_meta():
    """获取时间线元数据（可选的标的、KOL等）."""
    if _has_real_data():
        try:
            return _get_real_meta()
        except Exception as e:
            logger.warning("Failed to query real meta, falling back to mock: %s", e)

    # Fallback: mock 数据
    import random

    return TimelineMeta(
        tickers=["NVDA", "AAPL", "TSLA", "AMD", "MSFT", "GOOGL", "AMZN", "META", "BRK.B", "JPM"],
        kols=["分析师张三", "李四", "王五", "财通证券", "中信证券", "高盛研究", "摩根士丹利", "内部研究"],
        totalOpinions=random.randint(1000, 5000),
        timeRange={
            "min": (datetime.now() - timedelta(days=365)).isoformat(),
            "max": datetime.now().isoformat(),
        }
    )


@router.get("/stats/summary")
async def get_stats_summary(
    timeRange: str = Query("1M", description="时间范围"),
    ticker: Optional[str] = Query(None, description="标的筛选"),
):
    """获取统计摘要."""
    if _has_real_data():
        try:
            return {"ok": True, "data": _get_real_stats(timeRange, ticker)}
        except Exception as e:
            logger.warning("Failed to query real stats, falling back to mock: %s", e)

    # Fallback: mock 统计数据
    import random

    total = random.randint(500, 2000)

    data = {
        "total": total,
        "byDirection": {
            "bullish": random.randint(int(total * 0.4), int(total * 0.6)),
            "bearish": random.randint(int(total * 0.2), int(total * 0.35)),
            "neutral": random.randint(int(total * 0.1), int(total * 0.25)),
        },
        "byStatus": {
            "success": random.randint(int(total * 0.3), int(total * 0.5)),
            "failed": random.randint(int(total * 0.2), int(total * 0.35)),
            "pending": random.randint(int(total * 0.15), int(total * 0.3)),
        },
        "avgConfidence": round(random.uniform(0.6, 0.8), 2),
        "avgPriceChange": round(random.uniform(-5, 10), 2),
        "topTickers": [
            {"ticker": "NVDA", "count": random.randint(50, 150), "successRate": round(random.uniform(0.5, 0.8), 2)},
            {"ticker": "AAPL", "count": random.randint(40, 120), "successRate": round(random.uniform(0.5, 0.8), 2)},
            {"ticker": "TSLA", "count": random.randint(30, 100), "successRate": round(random.uniform(0.4, 0.7), 2)},
        ],
        "topKols": [
            {"author": "分析师张三", "count": random.randint(50, 150), "avgRating": round(random.uniform(3.5, 4.5), 1)},
            {"author": "财通证券", "count": random.randint(40, 120), "avgRating": round(random.uniform(3.5, 4.5), 1)},
        ],
    }
    return {"ok": True, "data": data}


@router.get("/{opinion_id}", response_model=TimelineOpinion)
async def get_opinion_detail(opinion_id: str):
    """获取单个观点详情."""
    # 尝试从真实数据加载 (F5 via repository, then F6 via file scan)
    if _has_real_data():
        try:
            # Try F5 via repository first
            repo = _get_repository()
            action = repo.load(opinion_id)
            if action:
                return trade_action_to_opinion(action)

            # Try F6 via direct file scan
            l6_dir = DATA_ROOT / "L6_annotated"
            for file_path in l6_dir.glob("**/*.action.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    candidate = TradeAction.from_dict(data)
                    if candidate.trade_action_id == opinion_id:
                        return trade_action_to_opinion(candidate)
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Failed to load real opinion %s, falling back to mock: %s", opinion_id, e)

    # Fallback: mock 数据
    now = datetime.now()
    opinion = _generate_mock_opinion(int(opinion_id.split("-")[-1]) if "-" in opinion_id else 0, now)

    if not opinion:
        raise FinerError(ErrorCode.F6_NTF_001, "Opinion not found", stage="F6", operation="get_opinion", retryable=False)

    return opinion
