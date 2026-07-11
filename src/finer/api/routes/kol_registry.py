"""KOL Profile Registry API — read-only view over configs/creators/*.yaml.

Third router mounted on /api/kol (alongside kol.py and kol_style.py; the
path sets are disjoint). Business logic lives in services/kol_registry.py;
routes only translate. There is no write API — editing a profile means
editing its YAML (TTL 60s picks it up).
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from finer.errors import ErrorCode, FinerNotFoundError
from finer.services.kol_registry import get_registry

router = APIRouter()


@router.get("/registry")
async def list_creator_profiles(
    include_disabled: bool = Query(False, description="包含 enabled=false 的档案"),
) -> dict:
    """List all creator profiles from the registry."""
    profiles = get_registry().list_profiles(include_disabled=include_disabled)
    return {
        "ok": True,
        "data": {
            "creators": [p.model_dump(mode="json") for p in profiles],
            "total": len(profiles),
        },
    }


@router.get("/registry/{key}")
async def get_creator_profile(key: str) -> dict:
    """One creator profile; `key` may be a creator_id or any registered alias."""
    profile = get_registry().get_resolved(key)
    if profile is None:
        raise FinerNotFoundError(
            ErrorCode.API_NTF_001,
            f"No creator profile for '{key}'",
            stage="F6_review",
            operation="get_creator_profile",
            retryable=False,
            details={
                "creator_id": key,
                "fix_hint": "Add configs/creators/{creator_id}.yaml (copy "
                            "configs/creators/_template.yaml) or register the "
                            "alias on an existing profile.",
            },
        )
    return {"ok": True, "data": profile.model_dump(mode="json")}
