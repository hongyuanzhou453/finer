"""KOL trading-style profile API routes.

Read-only endpoint exposing the two-layer (declared + observed)
TradingStyleProfile. Kept separate from kol.py to stay under the 500-line
route-file limit. Business logic lives in services/trading_style.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from finer.errors import ErrorCode
from finer.errors.exceptions import FinerInternalError
from finer.services.trading_style import build_style_profile

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/style/{creator_id}")
async def get_trading_style(creator_id: str) -> dict:
    """Return the trading-style profile for one creator.

    Both layers are nullable: declared=None means the creator YAML has no
    trading_style annotation, observed=None means no attributed F5 actions.
    A creator unknown on both layers still returns 200 so the frontend can
    render its "未标注 / 数据不足" empty states.
    """
    try:
        profile = build_style_profile(creator_id)
    except Exception as e:  # noqa: BLE001 — degrade to canonical envelope
        logger.exception("Failed to build style profile for %s", creator_id)
        raise FinerInternalError(
            ErrorCode.API_INT_001,
            f"Failed to build trading-style profile for {creator_id}",
            stage="F6_review",
            operation="get_trading_style",
            retryable=True,
            cause=e,
            details={
                "creator_id": creator_id,
                "fix_hint": "Check configs/creators/*.yaml syntax and "
                            "data/F5_executed action files.",
            },
        ) from e

    return {"ok": True, "data": profile.model_dump(mode="json")}
