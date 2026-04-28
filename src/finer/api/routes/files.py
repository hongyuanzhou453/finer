"""Files API — asset listing, upload, and enrichment entity contents."""

from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from typing import Optional

from finer.api.routes.files_utils import (
    DATA_ROOT,
    WORKFLOW_BY_TIER,
    _assets_cache,
    get_manifests_index,
    format_display_name,
    file_type_for,
    _build_source_summary,
)
from finer.api.routes.asset_builder import build_workflow_assets

router = APIRouter()


@router.get("")
async def get_files(
    tier: str = Query("F1"),
    source_type: Optional[str] = Query(None),
    source_group_id: Optional[str] = Query(None),
    sort_by: str = Query("file_timestamp"),
):
    workflow = WORKFLOW_BY_TIER.get(tier, "library")
    try:
        files = build_workflow_assets(workflow)

        if source_type and source_type != "all":
            files = [f for f in files if f.source_type == source_type]

        if source_group_id:
            files = [f for f in files if f.source_group_id == source_group_id]

        summary = _build_source_summary(files)

        return {
            "contract": "canonical_asset_v1",
            "tier": tier,
            "workflow": workflow,
            "files": [f.model_dump(by_alias=True) for f in files],
            **summary,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to build canonical asset view")


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    try:
        target_dir = DATA_ROOT / "raw" / "_inbox" / "unclassified"
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / file.filename
        with open(file_path, "wb") as buffer:
            import shutil
            shutil.copyfileobj(file.file, buffer)

        _assets_cache.clear()

        return {
            "success": True,
            "contract": "canonical_asset_v1",
            "message": f"File {file.filename} imported into canonical intake inbox",
            "path": str(file_path),
            "workflow": "intake",
            "stageBadge": "F0"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload file")


@router.get("/enrichment/{entity}")
async def get_enrichment_entity_contents(entity: str):
    """Get contents associated with an enrichment entity (ticker/company/topic)."""
    import json
    enrichment_index_path = DATA_ROOT / "L1_enrichment" / "content_index.json"

    if not enrichment_index_path.exists():
        return {"entity": entity, "contents": []}

    try:
        enrichment_index = json.loads(enrichment_index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"entity": entity, "contents": []}

    content_ids = enrichment_index.get("index", {}).get(entity, [])
    if not content_ids:
        return {"entity": entity, "contents": []}

    index = get_manifests_index()
    manifests_by_content_id = index["by_content_id"]

    contents = []
    seen_ids = set()

    for content_id in content_ids:
        if content_id in seen_ids:
            continue
        seen_ids.add(content_id)

        manifest_tuple = manifests_by_content_id.get(content_id)
        if manifest_tuple:
            manifest, manifest_path = manifest_tuple
            source_path = manifest.get("source_path", "")
            title = manifest.get("title", content_id)
            content_type = manifest.get("content_type", "unknown")
            creator_name = manifest.get("creator_name", "unknown")

            display_name = format_display_name(title, content_type)

            contents.append({
                "id": content_id,
                "name": display_name,
                "type": file_type_for(source_path or title),
                "creatorName": creator_name,
                "contentType": content_type,
                "sourcePath": source_path,
                "manifestPath": str(manifest_path),
            })

    return {"entity": entity, "contents": contents}
