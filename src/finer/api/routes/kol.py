"""KOL Rating API — KOL 评级数据查询.

Provides rating and performance metrics for KOLs (Key Opinion Leaders).

契约根治（2026-08-15）：
- ``rating`` 由 ``Dict[str, Any]`` 收紧为强类型 ``KOLRatingSummary``——
  此前后端漏发 / 前端多要字段互相看不见，曾导致前端白屏
  （``rating.badges.length``，badges 从未存在于任何后端响应）。
- 比率（successRate / avgReturn / overallRating）过 CRD-2 效力门：
  响应携带 ``SampleSufficiency``，``display_policy == count_only`` 时比率
  字段为 None——0 是一个会被当真的数字，缺失必须显式为空。
- 删除两处编造：30 天合成时间线（``(i % 3) * 0.2`` 抖动 + 假收益倍数）
  与 timeliness/depth/clarity 三个硬编码维度分。timeline 只在有真实
  portfolio_snapshots 时给出；dimensions 只保留有数据依据且过门的轴。

评分卡信息模型（overallRating / dimensions）已被定位转向判为废弃语义
（CRD-1），本轮只做契约与诚实性收口，整体下线归 C11 KOL 清理批次。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from finer.credibility.significance import get_significance_gate
from finer.paths import DATA_ROOT
from finer.schemas.significance import SampleSufficiency

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
    #: 评分随效力门置空——时间线不得成为绕过 count_only 的旁路通道。
    rating: Optional[float] = None
    return_pct: Optional[float] = None


class RecentOpinion(BaseModel):
    id: str
    ticker: str
    ticker_name: Optional[str] = None
    direction: str
    timestamp: str
    result: Optional[str] = None  # success, failed, pending


class KOLRatingSummary(BaseModel):
    """评级摘要（camelCase 对齐现役前端组件；contracts.ts 逐字段镜像）。"""

    kolId: str
    name: str
    platform: str
    totalOpinions: int = Field(description="口径内 action 总数（含未结算）")
    settledOpinions: int = Field(
        description="已裁决条数（验证或证伪；比率的分母）"
    )
    #: 以下三个是比率/比率派生量——display_policy == count_only 时一律 None。
    overallRating: Optional[float] = Field(
        default=None, description="1-5 派生分；由 successRate 派生，随门置空"
    )
    avgReturn: Optional[float] = Field(
        default=None, description="平均收益（百分点）；无已结算收益时为 None"
    )
    successRate: Optional[float] = Field(
        default=None, description="0-1 结算命中率；随门置空"
    )
    sufficiency: SampleSufficiency = Field(
        description="CRD-2 效力门判定；前端必须按 display_policy 呈现"
    )


class KOLRatingResponse(BaseModel):
    rating: KOLRatingSummary
    dimensions: List[DimensionScore]
    timeline: List[TimelinePoint]
    focusAreas: List[str]
    recentOpinions: List[RecentOpinion]


def _gated_summary(
    kol_id: str,
    name: str,
    platform: str,
    *,
    successes: int,
    settled_n: int,
    total_n: int,
    avg_return: Optional[float],
    overall_rating: Optional[float],
) -> KOLRatingSummary:
    """构造过门的评级摘要——比率只在 display_policy 允许时放行。"""
    sufficiency = get_significance_gate().assess(
        successes=successes, settled_n=settled_n, total_n=total_n
    )
    permitted = sufficiency.display_policy != "count_only"
    success_rate = successes / settled_n if settled_n > 0 else None
    return KOLRatingSummary(
        kolId=kol_id,
        name=name,
        platform=platform,
        totalOpinions=total_n,
        settledOpinions=settled_n,
        overallRating=round(overall_rating, 1) if permitted and overall_rating is not None else None,
        avgReturn=round(avg_return, 2) if permitted and avg_return is not None else None,
        successRate=round(success_rate, 4) if permitted and success_rate is not None else None,
        sufficiency=sufficiency,
    )


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


def _load_latest_backtest(kol_id: str) -> Optional[Dict[str, Any]]:
    """Load the latest backtest_result.json for this KOL, if present.

    Backtest artifacts live under ``data/review/{kol_id}/F8_backtest/``
    (see ``src/finer/backtest/storage.py``). We read the canonical
    ``backtest_result.json`` deterministically — no scanning, no fallback.
    """
    path = DATA_ROOT / "review" / kol_id / "F8_backtest" / "backtest_result.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load backtest for %s: %s", kol_id, exc)
        return None


def _rating_from_backtest(kol_id: str, backtest: Dict[str, Any]) -> KOLRatingResponse:
    """Derive a deterministic KOL rating from a real F8 backtest result.

    Used when no F5/F6 action records exist for the KOL but a backtest run does.
    All numbers come from the backtest artifact — no random fallback, no synthesis.
    """
    win_rate = float(backtest.get("win_rate", 0.0))
    total_trades = int(backtest.get("total_trades", 0))
    sharpe = float(backtest.get("sharpe_ratio", 0.0))
    trades_raw = backtest.get("trades") or []

    # Average per-trade return (percent). Backtest stores fractional return_pct.
    if trades_raw:
        avg_return_per_trade = sum(float(t.get("return_pct", 0.0)) for t in trades_raw) / len(trades_raw) * 100
    else:
        avg_return_per_trade = None

    # Overall rating (1-5): 60% win-rate component, 40% sharpe component.
    win_component = win_rate * 5.0  # 0..5
    sharpe_component = max(0.0, min(5.0, 2.5 + sharpe))  # sharpe 0 → 2.5, +2.5 → 5
    overall_rating = round(0.6 * win_component + 0.4 * sharpe_component, 1)
    overall_rating = max(1.0, min(5.0, overall_rating))

    summary = _gated_summary(
        kol_id,
        *_registry_identity(kol_id, "Backtest"),
        successes=round(win_rate * total_trades),
        settled_n=total_trades,
        total_n=total_trades,
        avg_return=avg_return_per_trade,
        overall_rating=overall_rating,
    )

    # 维度分只保留有数据依据的两轴（win_rate / sharpe），且随效力门一起
    # 撤下——把比率画成 0-5 的环并不改变它是比率。timeliness/depth/clarity
    # 曾是硬编码常量（3.5/3.0/3.5），没有任何测量依据，已删除。
    dimensions = []
    if summary.successRate is not None:
        dimensions = [
            DimensionScore(dimension="accuracy", score=round(max(0.0, min(5.0, win_rate * 5.0)), 1), label="准确率"),
            DimensionScore(dimension="consistency", score=round(max(0.0, min(5.0, 2.5 + sharpe * 0.5)), 1), label="一致性"),
        ]

    # Timeline derived from real portfolio_snapshots (up to 30 evenly-sampled points).
    # 曲线是记录不是承诺（PRT-2）：真实累计收益保留；评分随门置空。
    snapshots = backtest.get("portfolio_snapshots") or []
    timeline: List[TimelinePoint] = []
    if snapshots:
        step = max(1, len(snapshots) // 30)
        sampled = snapshots[::step][-30:]
        for s in sampled:
            d = str(s.get("date", ""))[:10]
            cum_ret = float(s.get("cumulative_return", 0.0)) * 100
            timeline.append(TimelinePoint(
                date=d,
                rating=summary.overallRating,
                return_pct=round(cum_ret, 2),
            ))

    # Focus areas from distinct tickers traded (deterministic order by frequency, then alpha).
    ticker_counts: Dict[str, int] = {}
    for t in trades_raw:
        tk = str(t.get("ticker", "")).strip()
        if tk:
            ticker_counts[tk] = ticker_counts.get(tk, 0) + 1
    focus_areas = sorted(ticker_counts.keys(), key=lambda k: (-ticker_counts[k], k))[:5]

    # Recent opinions: last 10 trades by exit_date (descending).
    sorted_trades = sorted(
        trades_raw,
        key=lambda t: (str(t.get("exit_date", "")), str(t.get("entry_date", ""))),
        reverse=True,
    )[:10]
    recent_opinions: List[RecentOpinion] = []
    for t in sorted_trades:
        side = str(t.get("side", "long"))
        direction = "bullish" if side == "long" else ("bearish" if side == "short" else "neutral")
        ret_pct = float(t.get("return_pct", 0.0)) * 100
        result_label = "success" if ret_pct > 0 else ("failed" if ret_pct < 0 else "pending")
        recent_opinions.append(RecentOpinion(
            id=str(t.get("trade_id", "")),
            ticker=str(t.get("ticker", "")),
            ticker_name=None,
            direction=direction,
            timestamp=str(t.get("exit_date") or t.get("entry_date") or ""),
            result=result_label,
        ))

    return KOLRatingResponse(
        rating=summary,
        dimensions=dimensions,
        timeline=timeline,
        focusAreas=focus_areas,
        recentOpinions=recent_opinions,
    )


def _empty_rating(kol_id: str) -> KOLRatingResponse:
    """Deterministic zero/empty rating when no actions and no backtest exist.

    Returned in place of synthetic random fallback. Frontend gracefully renders
    empty timeline / focus areas / opinions.
    """
    return KOLRatingResponse(
        rating=_gated_summary(
            kol_id,
            *_registry_identity(kol_id, "Unknown"),
            successes=0,
            settled_n=0,
            total_n=0,
            avg_return=None,
            overall_rating=None,
        ),
        # 无数据就是无数据：不再返回五个 0 分维度——0 是一个会被当真的分数。
        dimensions=[],
        timeline=[],
        focusAreas=[],
        recentOpinions=[],
    )


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
        # No F5/F6 actions — fall back to real backtest result if one exists,
        # else return a deterministic empty rating. No random/mock fallback.
        backtest = _load_latest_backtest(kol_id)
        if backtest is not None:
            return _rating_from_backtest(kol_id, backtest)
        return _empty_rating(kol_id)

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

    # 结算口径：validation_status 已裁决（verified/failed）为分母；
    # 未裁决（pending 等）只进 totalOpinions。
    settled_n = success_count + failed_count
    avg_return = sum(returns) / len(returns) if returns else None

    overall_rating: Optional[float] = None
    if settled_n > 0:
        success_rate = success_count / settled_n
        overall_rating = 1 + success_rate * 3 + (1 if (avg_return or 0) > 0 else 0)
        overall_rating = max(1.0, min(5.0, round(overall_rating, 1)))

    summary = _gated_summary(
        kol_id,
        *_registry_identity(kol_id, "Internal"),
        successes=success_count,
        settled_n=settled_n,
        total_n=total,
        avg_return=avg_return,
        overall_rating=overall_rating,
    )

    # 维度分只保留有数据依据的准确率轴，且随门撤下。此前的一致性
    # （3 + rate*2）与 timeliness/depth/clarity 常量没有测量依据，已删除。
    dimensions = []
    if summary.successRate is not None:
        dimensions = [
            DimensionScore(
                dimension="accuracy",
                score=round(summary.successRate * 5, 1),
                label="准确率",
            ),
        ]

    # 本路径没有真实时间序列（action 无逐日净值）。此前在这里合成
    # 30 天假时间线（评分抖动 + 假收益倍数）——编造数据，已删除；
    # 前端对空时间线有优雅降级。
    timeline: List[TimelinePoint] = []

    # Focus areas (top tickers)
    focus_areas = sorted(tickers.keys(), key=lambda t: tickers[t], reverse=True)[:5]

    # Recent opinions（按真实 timestamp 降序，不再假设文件序）
    recent_opinions = []
    sorted_actions = sorted(
        actions, key=lambda a: str(a.get("timestamp", "")), reverse=True
    )
    for action in sorted_actions[:10]:
        target = action.get("target", {})
        recent_opinions.append(RecentOpinion(
            id=action.get("trade_action_id", "unknown"),
            ticker=target.get("ticker_normalized") or target.get("ticker", "UNKNOWN"),
            ticker_name=target.get("company_name"),
            direction=action.get("direction", "neutral"),
            timestamp=str(action.get("timestamp", "")),
            result=action.get("validation_status", "pending"),
        ))

    return KOLRatingResponse(
        rating=summary,
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
    """KOL list item with rating data, aligned with frontend KOL type.

    比率字段 Optional：效力门 count_only 时为 None（不得填 0——0 会被当真）。
    """
    id: str
    name: str
    platform: str = ""
    platform_id: str = ""
    overall_score: Optional[float] = Field(None, description="Overall rating 1-5; 门未过时 None")
    dimension_scores: Dict[str, float] = Field(default_factory=dict)
    accuracy: Optional[float] = Field(None, description="Accuracy percentage 0-100; 门未过时 None")
    avg_return: Optional[float] = Field(None, description="Average return percentage; 门未过时 None")
    total_opinions: int = 0
    settled_opinions: int = 0
    last_active: str = ""
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True


def _registry_identity(kol_id: str, fallback_platform: str) -> tuple[str, str]:
    """(name, platform) from the creator registry, byte-for-byte fallback on miss.

    Exact-match only (no alias resolution): action data attributed to a
    historical canonical id (e.g. kol_cat_lord_fire) keeps its own row here
    instead of silently merging into the registered profile's row.
    """
    from finer.services.kol_registry import get_registry

    profile = get_registry().get(kol_id)
    if profile is None:
        return kol_id, fallback_platform
    name = profile.display_name or kol_id
    platform = profile.platforms[0] if profile.platforms else fallback_platform
    return name, platform


def _discover_kol_ids() -> List[str]:
    """Discover all KOL IDs from data layers.

    Two sources, both deterministic:
    1. F5/F6 action.json files (legacy L5_candidate / L6_annotated dirs).
    2. Backtest-attributed runs under ``data/review/{kol_id}/F8_backtest/``.

    Without (2), KOLs that only have backtest results (the common case for
    fixture-driven runs like ``trader_ji`` / ``kol_cat_lord_fire``) would be
    invisible to ``GET /api/kol/list/enriched``.
    """
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

    review_root = DATA_ROOT / "review"
    if review_root.exists():
        for kol_dir in review_root.iterdir():
            if not kol_dir.is_dir():
                continue
            if (kol_dir / "F8_backtest" / "backtest_result.json").exists():
                kol_id = kol_dir.name
                kol_ids.setdefault(kol_id, 0)
                # Give at least 1 weight so it sorts above never-seen ids.
                kol_ids[kol_id] = max(kol_ids[kol_id], 1)

    # 3. Registry profiles: a freshly onboarded creator (YAML only, no data
    # yet) appears in the list immediately with an empty rating — "加一份
    # YAML 即上架". Zero weight so data-backed KOLs sort first.
    try:
        from finer.services.kol_registry import get_registry

        for profile in get_registry().list_profiles():
            kol_ids.setdefault(profile.creator_id, 0)
    except Exception:  # registry must never take the list down
        pass

    # Stable sort: count desc, then id asc for determinism on ties.
    return [k for k, _ in sorted(kol_ids.items(), key=lambda x: (-x[1], x[0]))]


@router.get("/list/enriched", response_model=List[KOLListItem])
async def list_kols_enriched():
    """List all KOLs with full rating data."""
    kol_ids = _discover_kol_ids()
    result: List[KOLListItem] = []

    from finer.services.kol_registry import get_registry

    registry = get_registry()
    for kol_id in kol_ids:
        rating = _calculate_kol_rating(kol_id)
        dim_scores = {d.dimension: d.score for d in rating.dimensions}
        r = rating.rating
        profile = registry.get(kol_id)

        result.append(KOLListItem(
            id=kol_id,
            name=r.name,
            platform=r.platform,
            overall_score=r.overallRating,
            dimension_scores=dim_scores,
            accuracy=round(r.successRate * 100, 1) if r.successRate is not None else None,
            avg_return=r.avgReturn,
            total_opinions=r.totalOpinions,
            settled_opinions=r.settledOpinions,
            last_active=rating.timeline[-1].date if rating.timeline else "",
            tags=rating.focusAreas[:3],
            enabled=profile.enabled if profile else True,
        ))

    return result