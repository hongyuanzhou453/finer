"""System API — cache management, diagnostics, and error code catalog."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
import json as json_mod
import logging

from finer.api.routes.files_utils import (
    DATA_ROOT,
    _assets_cache,
    _manifests_index,
    _build_manifests_index,
    get_manifests_index,
)
from finer.api.routes.asset_builder import build_workflow_assets
from finer.errors.codes import (
    CATEGORY_STATUS,
    ErrorCodeInfo,
    list_error_codes,
    lookup_error_codes,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/autodrive")
async def get_autodrive_status(request: Request):
    """Status of the incremental pipeline auto-driver (roadmap ①).

    Reports whether the background driver is enabled/running and the summary of
    its last pass. ``enabled: false`` is the default — set
    ``FINER_PIPELINE_AUTODRIVE=1`` to turn the refresh cycle on.
    """
    driver = getattr(request.app.state, "autodriver", None)
    if driver is None:
        return {
            "enabled": False,
            "running": False,
            "detail": "auto-driver not initialized (no lifespan)",
        }
    return driver.status()


@router.post("/cache/invalidate")
async def invalidate_cache():
    """Manually invalidate all caches."""
    global _manifests_index
    _assets_cache.clear()
    _manifests_index = None
    return {"status": "ok", "message": "All caches invalidated"}


@router.post("/cache/warmup")
async def warmup_cache():
    """Pre-build caches for faster subsequent loads."""
    global _manifests_index

    _manifests_index = await run_in_threadpool(_build_manifests_index)

    for workflow in ["intake", "library", "parsing"]:
        await run_in_threadpool(build_workflow_assets, workflow, use_cache=True)

    return {
        "status": "ok",
        "manifests_indexed": _manifests_index["count"],
        "workflows_cached": ["intake", "library", "parsing"],
    }


@router.get("/diagnostics")
async def get_diagnostics():
    """Get diagnostic info about data, sync status, and Project Memory."""
    l0_count = sum(1 for _ in (DATA_ROOT / "L0_ingest").rglob("*") if _.is_file() and not _.name.endswith(".json"))
    raw_count = sum(1 for _ in (DATA_ROOT / "raw").rglob("*") if _.is_file() and not _.name.endswith(".json")) if (DATA_ROOT / "raw").exists() else 0
    manifest_count = len(get_manifests_index()["by_content_id"])

    sync_state_path = DATA_ROOT / ".feishu_sync_state.json"
    sync_state = {}
    if sync_state_path.exists():
        sync_state = json_mod.loads(sync_state_path.read_text())

    feishu_pool_count = sum(1 for _ in (DATA_ROOT / "feishu_sync_pool").iterdir() if _.is_file()) if (DATA_ROOT / "feishu_sync_pool").exists() else 0

    result = {
        "dataRoot": str(DATA_ROOT),
        "fileCounts": {
            "l0_ingest": l0_count,
            "raw": raw_count,
            "manifests": manifest_count,
            "feishu_pool_pending": feishu_pool_count,
        },
        "syncState": sync_state,
        "cacheStatus": {
            "assets_cache_entries": len(_assets_cache),
            "manifests_index_built": _manifests_index is not None,
        },
    }

    # Add Project Memory diagnostics
    result["projectMemory"] = _get_project_memory_diagnostics()

    return result


def _get_project_memory_diagnostics() -> dict:
    """Build Project Memory diagnostics block."""
    from finer.paths import PROJECT_MEMORY_DB

    if not PROJECT_MEMORY_DB.exists():
        return {
            "status": "missing",
            "projectId": None,
            "schemaVersion": None,
            "dbPath": str(PROJECT_MEMORY_DB),
            "contentCount": 0,
            "contentVersionCount": 0,
            "blockCount": 0,
            "topicBlockCount": 0,
            "objectCount": 0,
            "artifactCount": 0,
            "assetIndexCount": 0,
            "assetFtsCount": 0,
            "lastRebuildAt": None,
        }

    try:
        from finer.services.project_memory.connection import get_connection
        from finer.services.project_memory.schema import SchemaInspector

        conn = get_connection(PROJECT_MEMORY_DB)
        inspector = SchemaInspector(conn)
        report = inspector.validate_schema()
        counts = report.counts

        # Get project_id
        project_id = None
        try:
            row = conn.execute(
                "SELECT project_id FROM projects WHERE is_active = 1 LIMIT 1"
            ).fetchone()
            if row:
                project_id = row["project_id"]
        except Exception:
            pass

        # Get last rebuild timestamp
        last_rebuild_at = None
        try:
            row = conn.execute(
                "SELECT value FROM project_memory_meta WHERE key = 'last_asset_index_rebuild_at'"
            ).fetchone()
            if row:
                last_rebuild_at = row["value"]
        except Exception:
            pass

        # FTS count
        asset_fts_count = 0
        try:
            row = conn.execute("SELECT COUNT(*) FROM asset_index_fts").fetchone()
            if row:
                asset_fts_count = row[0]
        except Exception:
            pass

        return {
            "status": report.status.value,
            "projectId": project_id,
            "schemaVersion": str(report.version) if report.version else None,
            "dbPath": str(PROJECT_MEMORY_DB),
            "contentCount": counts.get("contents", 0),
            "contentVersionCount": counts.get("content_versions", 0),
            "blockCount": counts.get("content_blocks", 0),
            "topicBlockCount": counts.get("topic_blocks", 0),
            "objectCount": counts.get("storage_objects", 0),
            "artifactCount": counts.get("artifacts", 0),
            "assetIndexCount": counts.get("asset_index", 0),
            "assetFtsCount": asset_fts_count,
            "lastRebuildAt": last_rebuild_at,
        }

    except Exception as e:
        logger.warning("Failed to read Project Memory diagnostics: %s", e)
        return {
            "status": "corrupt",
            "projectId": None,
            "schemaVersion": None,
            "dbPath": str(PROJECT_MEMORY_DB),
            "contentCount": 0,
            "contentVersionCount": 0,
            "blockCount": 0,
            "topicBlockCount": 0,
            "objectCount": 0,
            "artifactCount": 0,
            "assetIndexCount": 0,
            "assetFtsCount": 0,
            "lastRebuildAt": None,
        }


def _info_to_dict(info: ErrorCodeInfo) -> dict[str, object]:
    """Convert ErrorCodeInfo to API response dict."""
    return {
        "code": info.code.value,
        "domain": info.domain,
        "category": info.category,
        "status_code": info.status_code,
        "title": info.title,
        "root_cause": info.root_cause,
        "fix_hint": info.fix_hint,
    }


@router.get("/error-codes")
async def get_error_codes(
    domain: str | None = None,
    category: str | None = None,
):
    """查询 Finer 错误码目录。

    支持按 domain（如 SYS、F1、LLM）和 category（如 IN、EXT、TMO）过滤。
    """
    codes = lookup_error_codes(domain=domain, category=category)
    return {
        "ok": True,
        "data": {
            "codes": [_info_to_dict(info) for info in codes],
            "categories": list(CATEGORY_STATUS.keys()),
        },
    }
