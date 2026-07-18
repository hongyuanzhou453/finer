"""Files API — asset listing and upload (F0 intake).

Primary query path is catalog-first via Project Memory asset_index.
Falls back to filesystem scan (degraded_scan) when Project Memory is unavailable.
"""

from fastapi import APIRouter, UploadFile, File, Query
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from pathlib import Path
import hashlib
import json
import logging
import uuid

from finer.api.routes.files_utils import (
    DATA_ROOT,
    WORKFLOW_BY_TIER,
    MAX_UPLOAD_BYTES,
    ALLOWED_UPLOAD_EXTENSIONS,
    _assets_cache,
    _build_source_summary,
    sanitize_upload_filename,
    upload_file_type,
    is_allowed_upload_mime,
    unique_landing_path,
)
from finer.api.routes.asset_builder import build_workflow_assets
from finer.errors.exceptions import FinerError, FinerInternalError
from finer.errors.codes import ErrorCode
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.utils.time import now_utc

logger = logging.getLogger(__name__)
router = APIRouter()

# Local-upload F0 landing platform (canonical: data/raw/local, data/F0_intake/local).
_LOCAL_PLATFORM = "local"


def _project_memory_db_path() -> Path:
    """Resolve the Project Memory DB under the *active* data root.

    Anchoring on the module-level ``DATA_ROOT`` (rather than importing the frozen
    ``PROJECT_MEMORY_DB`` constant) means that when a test monkeypatches
    ``files.DATA_ROOT`` to a tmp path the upload's PM write targets a tmp DB —
    never the live catalog. In production ``DATA_ROOT`` is the real data root, so
    this resolves to the same ``data/project_memory/finer.project.sqlite3`` the
    catalog reads.
    """
    return DATA_ROOT / "project_memory" / "finer.project.sqlite3"


def _record_imported_to_pm(record: ContentRecord, receipt: ImportReceipt) -> None:
    """Register an uploaded ContentRecord in Project Memory (idempotent).

    Thin seam over the frozen ``F0IndexWriter`` so tests can inject a temp DB by
    patching this function or ``files.DATA_ROOT``. Failure here must not lose the
    on-disk record/receipt that were already persisted, so the caller treats
    PM-write errors as soft.
    """
    from finer.ingestion.f0_index_writer import F0IndexWriter

    F0IndexWriter(db_path=_project_memory_db_path()).record_imported(record, receipt)

# Canonical F-stage → asset_index.stage mapping
_TIER_TO_STAGE = {
    "F0": "F0",
    "F1": "F1",
    "F2": "F2",
    "F5": "F5",
    "F6": "F6",
    "F8": "F8",
}


def _try_catalog_query(
    stage: str,
    limit: int,
    offset: int,
    q: Optional[str],
    source_type: Optional[str],
    source_group_id: Optional[str],
) -> Optional[dict]:
    """Attempt to serve the request from Project Memory asset_index.

    Returns a dict with 'files' list and 'projectMemory' metadata,
    or None if Project Memory is unavailable.
    """
    try:
        from finer.paths import PROJECT_MEMORY_DB
        if not PROJECT_MEMORY_DB.exists():
            return None

        from finer.services.project_memory.connection import get_connection
        from finer.services.project_memory.schema import SchemaInspector, SchemaHealth
        from finer.services.project_memory.asset_index import AssetIndexService
        from finer.services.project_memory.name_lineage import NameLineageService

        conn = get_connection(PROJECT_MEMORY_DB)
        inspector = SchemaInspector(conn)
        report = inspector.validate_schema()

        if report.status not in (SchemaHealth.HEALTHY, SchemaHealth.DEGRADED):
            logger.warning(
                "Project Memory schema status=%s, falling back to degraded scan",
                report.status.value,
            )
            return None

        asset_svc = AssetIndexService(conn)
        name_svc = NameLineageService(conn)

        # Query assets
        if q:
            raw_assets = asset_svc.search(q, stage=stage, limit=limit + offset)
        else:
            raw_assets = asset_svc.list_assets(
                stage=stage, limit=limit + offset, offset=0
            )

        # Apply pagination after search (search doesn't support offset directly)
        if q:
            raw_assets = raw_assets[offset : offset + limit]

        # Filter by source_type / source_group_id if provided
        if source_type and source_type != "all":
            raw_assets = [a for a in raw_assets if a.get("source_type") == source_type]
        if source_group_id:
            raw_assets = [a for a in raw_assets if a.get("source_group_id") == source_group_id]

        # Build response assets with name_lineage
        files = []
        for a in raw_assets:
            content_id = a["content_id"]

            # Resolve name lineage
            names = name_svc.get_names_for_content(content_id)
            name_lineage = _build_name_lineage(names, a)

            # Resolve content_version_id
            content_version_id = None
            try:
                row = conn.execute(
                    "SELECT active_content_version_id FROM contents WHERE content_id = ?",
                    (content_id,),
                ).fetchone()
                if row:
                    content_version_id = row["active_content_version_id"]
            except Exception:
                pass

            # Resolve source_record_id
            source_record_id = None
            try:
                row = conn.execute(
                    "SELECT primary_source_record_id FROM contents WHERE content_id = ?",
                    (content_id,),
                ).fetchone()
                if row:
                    source_record_id = row["primary_source_record_id"]
            except Exception:
                pass

            files.append({
                "id": a["asset_id"],
                "contentId": content_id,
                "contentVersionId": content_version_id,
                "stage": a["stage"],
                "name": a.get("display_name", content_id),
                "sourceRecordId": source_record_id,
                "sourceGroupId": a.get("source_group_id"),
                "latestArtifactId": a.get("latest_artifact_id"),
                "manifestId": a.get("manifest_id"),
                "nameLineage": name_lineage,
            })

        # Get asset_index updated_at for metadata
        asset_index_updated_at = None
        try:
            row = conn.execute(
                "SELECT MAX(updated_at) FROM asset_index WHERE stage = ?",
                (stage,),
            ).fetchone()
            if row and row[0]:
                asset_index_updated_at = row[0]
        except Exception:
            pass

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

        schema_version = report.version

        return {
            "files": files,
            "projectMemory": {
                "projectId": project_id,
                "schemaVersion": str(schema_version) if schema_version else None,
                "dbPath": str(PROJECT_MEMORY_DB),
                "assetIndexUpdatedAt": asset_index_updated_at,
                "degraded": report.status == SchemaHealth.DEGRADED,
            },
        }

    except Exception as e:
        logger.warning("Project Memory catalog query failed: %s", e, exc_info=True)
        return None


def _build_name_lineage(names: dict, asset: dict) -> dict:
    """Build nameLineage dict from name_bindings grouped data."""
    lineage = {
        "originalFilename": None,
        "f0DisplayName": None,
        "f1EnvelopeTitle": None,
        "splitFilename": None,
        "materializedFilename": None,
    }

    # Map namespace.kind to lineage fields
    for key, bindings in names.items():
        if not bindings:
            continue
        primary = next((b for b in bindings if b.get("is_primary")), bindings[0])
        value = primary.get("display_value")
        if not value:
            continue

        if key == "source.original_filename":
            lineage["originalFilename"] = value
        elif key == "f0.display_name":
            lineage["f0DisplayName"] = value
        elif key == "f1.envelope_title":
            lineage["f1EnvelopeTitle"] = value
        elif key == "f1.split_filename":
            lineage["splitFilename"] = value
        elif key == "materialization.filename":
            lineage["materializedFilename"] = value

    # Fallback: use asset display_name if lineage is empty
    display_name = asset.get("display_name")
    if display_name and not any(lineage.values()):
        lineage["f0DisplayName"] = display_name

    return lineage


@router.get("")
async def get_files(
    tier: str = Query("F1"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    source_group_id: Optional[str] = Query(None),
    sort_by: str = Query("file_timestamp"),
):
    # Resolve canonical stage from tier
    stage = _TIER_TO_STAGE.get(tier)
    workflow = WORKFLOW_BY_TIER.get(tier, "library")

    # Attempt catalog-first query
    if stage:
        catalog_result = _try_catalog_query(
            stage=stage,
            limit=limit,
            offset=offset,
            q=q,
            source_type=source_type,
            source_group_id=source_group_id,
        )
        if catalog_result is not None:
            return {
                "ok": True,
                "source": "catalog",
                "contract": "canonical_asset_v1",
                "tier": tier,
                "workflow": workflow,
                "files": catalog_result["files"],
                "projectMemory": catalog_result["projectMemory"],
            }

    # Degraded fallback: filesystem scan via asset_builder. This is a heavy
    # synchronous scan (manifests + previews, slow/LLM-backed on a cold cache),
    # so offload it to the threadpool — a GET must never block the event loop.
    try:
        files = await run_in_threadpool(build_workflow_assets, workflow)

        if source_type and source_type != "all":
            files = [f for f in files if f.source_type == source_type]

        if source_group_id:
            files = [f for f in files if f.source_group_id == source_group_id]

        # Apply limit/offset
        total = len(files)
        files = files[offset : offset + limit]

        summary = _build_source_summary(files)

        return {
            "ok": True,
            "source": "degraded_scan",
            "contract": "canonical_asset_v1",
            "tier": tier,
            "workflow": workflow,
            "files": [f.model_dump(by_alias=True) for f in files],
            "projectMemory": None,
            **summary,
        }
    except FinerError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to build canonical asset view for tier=%s workflow=%s",
            tier, workflow,
        )
        raise FinerInternalError(
            ErrorCode.API_INT_001,
            f"Failed to build canonical asset view: {type(e).__name__}: {e}",
            cause=e,
            tier=tier,
            workflow=workflow,
        ) from e


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    """F0 local-upload intake.

    Lands the raw payload under ``data/raw/local/`` and registers a canonical
    ``ContentRecord`` + ``ImportReceipt`` in Project Memory so the upload is
    traceable by F1 (R-16). The filename is reduced to a safe basename before any
    path is constructed (R-17), and the payload is gated by a size cap +
    extension/MIME allowlist (R-28).
    """
    request_id = f"req-{uuid.uuid4().hex[:12]}"

    # 1. Filename safety (R-17): collapse to a basename, reject traversal.
    try:
        safe_name = sanitize_upload_filename(file.filename)
    except ValueError as exc:
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Rejected unsafe upload filename: {exc}",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=False,
            status_code=400,
            request_id=request_id,
            fix_hint="Re-upload with a plain filename (no path separators or '..').",
        )

    extension = Path(safe_name).suffix.replace(".", "").lower()

    # 2. Extension allowlist (R-28).
    file_type = upload_file_type(extension)
    if file_type is None:
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Unsupported upload file type: '.{extension or '(none)'}'",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=False,
            status_code=400,
            request_id=request_id,
            fix_hint=(
                "Allowed extensions: "
                + ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
            ),
        )

    # 3. MIME secondary gate (R-28).
    if not is_allowed_upload_mime(file.content_type):
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Unsupported upload content type: '{file.content_type}'",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=False,
            status_code=400,
            request_id=request_id,
            fix_hint="Upload a text, document, image, audio, or video file.",
        )

    # 4. Read payload with a hard size cap (R-28) and hash for dedupe.
    try:
        payload = await file.read()
    except Exception as exc:
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Failed to read upload stream: {exc}",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=True,
            request_id=request_id,
            cause=exc,
        )

    if len(payload) > MAX_UPLOAD_BYTES:
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Upload exceeds size limit ({len(payload)} > {MAX_UPLOAD_BYTES} bytes)",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=False,
            status_code=413,
            request_id=request_id,
            fix_hint=f"Split the file or keep it under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    if not payload:
        raise FinerError(
            ErrorCode.F0_IO_001,
            "Refusing to import an empty file",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=False,
            status_code=400,
            request_id=request_id,
            fix_hint="Upload a non-empty file.",
        )

    fingerprint = hashlib.sha256(payload).hexdigest()
    content_id = str(uuid.uuid4())
    collected_at = now_utc()

    # 5. Land raw payload under canonical data/raw/local/ (non-clobbering).
    #    Paths are anchored on the module-level DATA_ROOT so test isolation
    #    (monkeypatching files.DATA_ROOT) keeps writes inside tmp_path while the
    #    on-disk layout still matches the GATE f0_raw_dir / f0_record_path shape.
    try:
        raw_dir = DATA_ROOT / "raw" / _LOCAL_PLATFORM
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = unique_landing_path(raw_dir, safe_name)
        raw_path.write_bytes(payload)

        rel_raw_path = str(raw_path.relative_to(DATA_ROOT))

        record = ContentRecord(
            content_id=content_id,
            source_type="manual_upload",
            source_platform=_LOCAL_PLATFORM,
            collected_at=collected_at,
            title=raw_path.stem,
            raw_path=rel_raw_path,
            file_type=file_type,
            dedupe_fingerprint=fingerprint,
            metadata={
                "original_filename": safe_name,
                "registered_via": "api_upload",
                "content_type": file.content_type,
                "byte_size": len(payload),
            },
        )

        receipt = ImportReceipt(
            run_id=f"local-{content_id}",
            request_id=request_id,
            source_channel="local_upload",
            source_kind="manual_upload",
            status="completed",
            content_id=content_id,
            dedupe_fingerprint=fingerprint,
            collected_at=collected_at,
            started_at=collected_at,
            finished_at=now_utc(),
            raw_sha256={"upload": fingerprint},
            raw_paths={"upload": str(raw_path)},
            records_created=1,
        )

        # 6. Persist ContentRecord + ImportReceipt JSON under data/F0_intake/local/.
        intake_dir = DATA_ROOT / "F0_intake" / _LOCAL_PLATFORM
        intake_dir.mkdir(parents=True, exist_ok=True)
        record_path = intake_dir / f"{content_id}.json"
        receipt_path = intake_dir / f"{content_id}.receipt.json"
        record_path.write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )
        receipt.record_path = str(record_path)
        receipt_path.write_text(
            receipt.model_dump_json(indent=2), encoding="utf-8"
        )
    except FinerError:
        raise
    except Exception as exc:
        logger.exception("Local upload failed to persist record for %s", safe_name)
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Failed to persist uploaded content: {type(exc).__name__}: {exc}",
            stage="F0",
            operation="file_upload",
            source_channel="local",
            retryable=True,
            request_id=request_id,
            content_id=content_id,
            cause=exc,
        )

    # 7. Register in Project Memory (asset_index hot row + contents chain).
    #    PM is the catalog; if it is unavailable the on-disk record still exists
    #    and a rebuild can recover it, so a PM failure is logged, not fatal.
    pm_registered = True
    try:
        _record_imported_to_pm(record, receipt)
    except Exception as exc:
        pm_registered = False
        logger.warning(
            "Upload %s persisted on disk but Project Memory registration failed: %s",
            content_id, exc, exc_info=True,
        )

    _assets_cache.clear()

    return {
        "success": True,
        "contract": "canonical_asset_v1",
        "message": f"File {safe_name} imported into canonical F0 intake",
        "contentId": content_id,
        "sourceRecordId": f"sr_{hashlib.sha256(f'sr:{content_id}'.encode()).hexdigest()[:16]}",
        "rawPath": rel_raw_path,
        "recordPath": str(record_path),
        "dedupeFingerprint": fingerprint,
        "projectMemoryRegistered": pm_registered,
        "requestId": request_id,
        "path": str(raw_path),
        "workflow": "intake",
        "stageBadge": "F0",
    }
