"""F0 Index API — Import Console query endpoints (contract only)."""
from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/f0-index", tags=["F0 Project Memory"])


@router.get("/records")
async def list_f0_records(
    source_type: str | None = None,
    source_platform: str | None = None,
    creator_id: str | None = None,
    sort_by: str = "collected_at",
    sort_order: str = "desc",
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    """Query F0 content records from index. Contract only."""
    raise NotImplementedError("A1 first round: contract only")


@router.get("/health")
async def get_f0_index_health() -> dict:
    """Return F0 index health status. Contract only."""
    raise NotImplementedError("A1 first round: contract only")


@router.post("/rebuild")
async def trigger_f0_index_rebuild(background: bool = True) -> dict:
    """Explicitly trigger F0 index rebuild. Contract only."""
    raise NotImplementedError("A1 first round: contract only")
