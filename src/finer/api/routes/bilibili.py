"""Bilibili API Routes — F0 intake + F1-adjacent transcription endpoints.

F0 (intake) — canonical:
- GET  /api/bilibili/video/{bvid}  — get video info
- POST /api/bilibili/import/{bvid} — download raw artifacts + produce ContentRecord
                                     + ImportReceipt + Project Memory row (R-10)

F1-adjacent (downstream of F0, NOT an F0 acceptance path):
- POST /api/bilibili/transcribe/{bvid} — download audio + ASR transcribe
- POST /api/bilibili/sync/{bvid}        — legacy: promote an existing transcript

F0 scope (AGENTS.md): F0 only outputs ContentRecord + raw archive + import
receipt + F0 local index. It does NOT do ASR/topic/anchor/intent/TradeAction.
The transcribe path is therefore F1-adjacent and intentionally excluded from F0
acceptance.

All endpoints follow the project's canonical error envelope (Line F).
"""

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import Any, Optional, List
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import logging

from finer.ingestion.bilibili_adapter import (
    BilibiliAdapter,
    BilibiliVideoInfo,
    TranscriptResult,
    BilibiliClient,
)
from finer.ingestion.bbdown_client import (
    BBDownAdapter,
    BBDownConfig,
    BBDownError,
    BBDownUnavailableError,
    BilibiliRawArtifacts,
)

from finer.errors import FinerError, ErrorCode, error_response
from finer.paths import REPO_ROOT, DATA_ROOT, f0_raw_dir, f0_record_path, f0_receipt_path
from finer.manifests import ContentManifest, _infer_file_type, write_manifest, build_content_id
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.utils.time import now_utc

logger = logging.getLogger(__name__)

router = APIRouter()
BILIBILI_DIR = DATA_ROOT / "raw" / "bilibili"
# Canonical F0 platform key (data/raw/bilibili, data/F0_intake/bilibili).
BILIBILI_PLATFORM = "bilibili"


# Request/Response Models

class VideoInfoResponse(BaseModel):
    """Video metadata response."""
    bvid: str
    aid: int = 0
    title: str
    uploader: str
    uploader_id: int
    publish_time: str
    duration: int
    description: str
    cover_url: str
    page_count: int
    tags: List[str]


class TranscriptSegmentResponse(BaseModel):
    """Single transcript segment."""
    start_time: float
    end_time: float
    text: str
    timestamp_str: str


class TranscribeResponse(BaseModel):
    """Transcription result response."""
    bvid: str
    title: str
    uploader: str
    duration_seconds: float
    model: str
    segments_count: int
    full_text_length: int
    transcript_path: Optional[str] = None
    metadata_path: Optional[str] = None
    segments: List[TranscriptSegmentResponse]


class SyncRequest(BaseModel):
    """Sync to F0 Intake request."""
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class SyncResponse(BaseModel):
    """Sync to F0 Intake response."""
    bvid: str
    content_id: str
    f0_path: str
    transcript_path: str
    metadata_path: str
    status: str


class TaskStatusResponse(BaseModel):
    """Background task status."""
    task_id: str
    bvid: str
    status: str  # pending, running, completed, failed
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[TranscribeResponse] = None
    error: Optional[str] = None


class ImportRequest(BaseModel):
    """F0 import request for one B站 video (raw artifacts only)."""
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    download_video: bool = Field(
        False, description="Also download the full video file (default: audio only)."
    )
    download_audio: bool = Field(True, description="Download the audio stream.")
    download_subtitle: bool = Field(True, description="Download CC subtitle if present.")


class ImportResponse(BaseModel):
    """F0 import result for one B站 video."""
    bvid: str
    content_id: str
    f0_path: str
    record_path: str
    receipt_path: str
    raw_artifacts: dict[str, str]
    status: str  # imported | already_imported
    content_record: ContentRecord
    receipt: dict[str, Any]


# In-memory task tracking (for demo, should use Redis in production)
_tasks: dict[str, TaskStatusResponse] = {}


# F0 import helpers


def _bilibili_content_id(uploader_id: object, bvid: str) -> str:
    """Stable content_id derived from platform identifiers (uploader_id + BV号)."""
    return hashlib.sha256(
        f"bilibili:{uploader_id}:{bvid}".encode("utf-8")
    ).hexdigest()[:32]


def _bilibili_dedupe_fingerprint(uploader_id: object, bvid: str) -> str:
    """Hash-based dedupe fingerprint for idempotent re-import."""
    return hashlib.sha256(
        f"bilibili:{uploader_id}:{bvid}".encode("utf-8")
    ).hexdigest()[:16]


def _build_bilibili_receipt(
    *,
    run_id: str,
    record: ContentRecord,
    record_path: Path,
    artifacts: BilibiliRawArtifacts,
    status: str = "completed",
    records_created: int = 1,
    records_skipped: int = 0,
) -> ImportReceipt:
    """Build the GATE ImportReceipt for one F0 bilibili import.

    Raw-archive roles map directly to the downloaded artifact set (audio / video
    / subtitle / source_info). No transcript is referenced — F0 import does not
    depend on transcription (R-10).
    """
    finished = now_utc()
    raw_paths = {role: str(path) for role, path in artifacts.artifact_paths.items()}
    raw_sha256 = {
        role: _sha256_file(path)
        for role, path in artifacts.artifact_paths.items()
        if path.exists()
    }
    return ImportReceipt(
        run_id=run_id,
        source_channel="bilibili",
        source_kind="bilibili_video",
        status=status,
        content_id=record.content_id,
        external_source_id=record.external_source_id,
        dedupe_fingerprint=record.dedupe_fingerprint,
        collected_at=record.collected_at,
        started_at=finished,
        finished_at=finished,
        raw_sha256=raw_sha256,
        raw_paths=raw_paths,
        record_path=str(record_path),
        records_created=records_created,
        records_skipped=records_skipped,
    )


def _sha256_file(path: Path) -> str:
    """Stream-hash a file to hex sha256 (artifacts may be large)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _register_f0_index(record: ContentRecord, receipt: ImportReceipt) -> None:
    """Best-effort Project Memory registration for a successful F0 import.

    Idempotent (``F0IndexWriter.record_imported`` uses INSERT OR IGNORE). Any
    failure (PM DB missing/locked) is logged and swallowed so an import is never
    lost just because the hot index could not be updated. Tests patch this to a
    no-op to avoid writing to the live project database.
    """
    try:
        from finer.ingestion.f0_index_writer import F0IndexWriter

        F0IndexWriter().record_imported(record, receipt)
    except Exception as exc:  # pragma: no cover - PM availability is environmental
        logger.warning(
            "Project Memory registration skipped for %s: %s",
            record.content_id,
            exc,
        )


def _build_content_record_from_artifacts(
    artifacts: BilibiliRawArtifacts,
    *,
    content_id: str,
    dedupe_fingerprint: str,
    raw_path: Path,
    file_type: str,
    req: Optional["ImportRequest"],
) -> ContentRecord:
    """Assemble the canonical F0 ContentRecord from a raw artifact set."""
    info = artifacts.info
    published_at = info.publish_time
    if published_at is None:
        published_at = now_utc()

    return ContentRecord(
        content_id=content_id,
        source_type="bilibili_video",
        source_platform=BILIBILI_PLATFORM,
        creator_id=str(info.uploader_id),
        creator_name=info.uploader or None,
        published_at=published_at,
        title=info.title or None,
        raw_path=str(raw_path),
        file_type=file_type,
        metadata={
            "bvid": artifacts.bvid,
            "aid": info.aid,
            "uploader_id": info.uploader_id,
            "duration": info.duration,
            "tags": (req.tags if req else None) or info.tags,
            "category": req.category if req else None,
            "raw_artifacts": {
                role: str(path) for role, path in artifacts.artifact_paths.items()
            },
            "source_info_path": str(artifacts.source_info_path),
            "ingest_time": now_utc().isoformat(),
        },
        source_url=f"https://www.bilibili.com/video/{artifacts.bvid}",
        external_source_id=artifacts.bvid,
        dedupe_fingerprint=dedupe_fingerprint,
        language="zh",
        market_scope=["US", "HK", "A"],
    )


# Helper functions

def video_info_to_response(info: BilibiliVideoInfo) -> VideoInfoResponse:
    """Convert BilibiliVideoInfo to response model."""
    return VideoInfoResponse(
        bvid=info.bvid,
        aid=info.aid,
        title=info.title,
        uploader=info.uploader,
        uploader_id=info.uploader_id,
        publish_time=info.publish_time.isoformat(),
        duration=info.duration,
        description=info.description,
        cover_url=info.cover_url,
        page_count=info.page_count,
        tags=info.tags,
    )


def transcript_to_response(
    result: TranscriptResult,
    transcript_path: Optional[Path] = None,
    metadata_path: Optional[Path] = None,
) -> TranscribeResponse:
    """Convert TranscriptResult to response model."""
    segments = [
        TranscriptSegmentResponse(
            start_time=seg.start_time,
            end_time=seg.end_time,
            text=seg.text,
            timestamp_str=seg.format_timestamp(seg.start_time),
        )
        for seg in result.segments[:100]  # Limit for API response
    ]

    return TranscribeResponse(
        bvid=result.video_info.bvid,
        title=result.video_info.title,
        uploader=result.video_info.uploader,
        duration_seconds=result.duration_seconds,
        model=result.model,
        segments_count=len(result.segments),
        full_text_length=len(result.full_text),
        transcript_path=str(transcript_path) if transcript_path else None,
        metadata_path=str(metadata_path) if metadata_path else None,
        segments=segments,
    )


# API Endpoints

@router.get("/video/{bvid}", response_model=VideoInfoResponse)
async def get_video_info(bvid: str):
    """Get B站 video information.

    Args:
        bvid: BV ID (e.g., BV1xx411c7mD) or URL

    Returns:
        VideoInfoResponse with metadata
    """
    try:
        client = BilibiliClient()
        info = client.get_video_info(bvid)
        return video_info_to_response(info)

    except ValueError as e:
        raise FinerError(
            ErrorCode.BILI_IN_001,
            str(e),
            stage="F0",
            operation="bilibili_video_info",
            source_channel="bilibili",
            retryable=False,
            cause=e,
        )
    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
        raise FinerError(
            ErrorCode.BILI_EXT_001,
            f"Failed to fetch video info: {e}",
            stage="F0",
            operation="bilibili_video_info",
            source_channel="bilibili",
            retryable=True,
            cause=e,
        )


def _build_bbdown_adapter() -> BBDownAdapter:
    """Build the F0 BBDown download adapter (download-only, no ASR).

    Loads channel config when available; falls back to defaults rooted at the
    canonical raw archive dir so the import path works even without a config file.
    """
    download_dir = f0_raw_dir(BILIBILI_PLATFORM)
    try:
        from finer.config import load_bbdown_config

        cfg = load_bbdown_config(REPO_ROOT)
        return BBDownAdapter(
            config=BBDownConfig(
                api_url=cfg.api_url,
                auto_start=cfg.auto_start,
                cookie=cfg.cookie,
                download_dir=Path(cfg.download_dir),
            )
        )
    except Exception as exc:  # pragma: no cover - config optional
        logger.debug("BBDown config load failed, using defaults: %s", exc)
        return BBDownAdapter(config=BBDownConfig(download_dir=download_dir))


@router.post("/import/{bvid}", response_model=ImportResponse)
async def import_video(bvid: str, req: Optional[ImportRequest] = None):
    """Import one B站 video into F0 (raw artifacts only) — canonical F0 path.

    Pipeline (R-10):
    1. Download the raw artifact set via BBDown — audio (default) and/or video,
       CC subtitle if present, plus a ``{bvid}.source.json`` — with no ASR.
    2. Build the canonical ``ContentRecord`` (source_type=bilibili_video) from the
       raw artifacts and persist it under ``data/F0_intake/bilibili/``.
    3. Emit a GATE ``ImportReceipt`` and register the import in Project Memory.

    This endpoint never transcribes and never requires DASHSCOPE — it does NOT
    depend on ``/transcribe`` having run first (the old ``/sync`` gate is gone).
    If BBDown / its .NET 8 runtime is unavailable, returns a canonical
    ``F0_EXT_001`` error (retryable) with a fix hint instead of crashing.

    Args:
        bvid: BV ID or URL
        req: Optional import parameters (tags, category, artifact selection)

    Returns:
        ImportResponse with content_id, F0 paths, raw artifact map, and receipt.
    """
    req = req or ImportRequest()
    try:
        client = BilibiliClient()
        parsed_bvid = client.parse_bvid(bvid)
    except ValueError as e:
        raise FinerError(
            ErrorCode.BILI_IN_001,
            str(e),
            stage="F0",
            operation="bilibili_import",
            source_channel="bilibili",
            retryable=False,
            cause=e,
        )

    adapter = _build_bbdown_adapter()
    raw_dir = f0_raw_dir(BILIBILI_PLATFORM)

    try:
        artifacts = await adapter.download_raw_artifacts(
            parsed_bvid,
            output_dir=raw_dir,
            download_video=req.download_video,
            download_audio=req.download_audio,
            download_subtitle=req.download_subtitle,
        )
    except BBDownUnavailableError as e:
        # .NET 8 missing / BBDown not installed → external dependency unavailable.
        raise FinerError(
            ErrorCode.F0_EXT_001,
            str(e),
            stage="F0",
            operation="bilibili_import",
            source_channel="bilibili",
            retryable=True,
            fix_hint=getattr(e, "fix_hint", "install .NET 8 runtime"),
            cause=e,
        )
    except BBDownError as e:
        raise FinerError(
            ErrorCode.BILI_EXT_001,
            f"BBDown download failed: {e}",
            stage="F0",
            operation="bilibili_import",
            source_channel="bilibili",
            retryable=True,
            cause=e,
        )
    except Exception as e:
        logger.error(f"Bilibili F0 import failed: {e}", exc_info=True)
        raise FinerError(
            ErrorCode.F0_EXT_001,
            f"Bilibili F0 import failed: {e}",
            stage="F0",
            operation="bilibili_import",
            source_channel="bilibili",
            retryable=True,
            cause=e,
        )

    info = artifacts.info
    content_id = _bilibili_content_id(info.uploader_id, parsed_bvid)
    dedupe_fingerprint = _bilibili_dedupe_fingerprint(info.uploader_id, parsed_bvid)

    record_path = f0_record_path(BILIBILI_PLATFORM, content_id)
    receipt_path = f0_receipt_path(BILIBILI_PLATFORM, content_id)

    # The ContentRecord's primary raw_path is the richest available artifact:
    # video > audio > subtitle > source_info JSON.
    primary_raw = (
        artifacts.video_path
        or artifacts.audio_path
        or artifacts.subtitle_path
        or artifacts.source_info_path
    )
    file_type = _infer_file_type(primary_raw.suffix)

    # Idempotent dedupe: if a ContentRecord already exists, return already_imported.
    if record_path.exists():
        try:
            existing = ContentRecord.model_validate_json(
                record_path.read_text(encoding="utf-8")
            )
        except Exception:
            existing = _build_content_record_from_artifacts(
                artifacts,
                content_id=content_id,
                dedupe_fingerprint=dedupe_fingerprint,
                raw_path=primary_raw,
                file_type=file_type,
                req=req,
            )
        receipt_data: dict[str, Any] = {}
        if receipt_path.exists():
            try:
                receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
            except Exception:
                receipt_data = {}
        return ImportResponse(
            bvid=parsed_bvid,
            content_id=content_id,
            f0_path=str(record_path.parent),
            record_path=str(record_path),
            receipt_path=str(receipt_path),
            raw_artifacts={r: str(p) for r, p in artifacts.artifact_paths.items()},
            status="already_imported",
            content_record=existing,
            receipt=receipt_data,
        )

    try:
        record = _build_content_record_from_artifacts(
            artifacts,
            content_id=content_id,
            dedupe_fingerprint=dedupe_fingerprint,
            raw_path=primary_raw,
            file_type=file_type,
            req=req,
        )

        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        receipt = _build_bilibili_receipt(
            run_id=f"bili_{content_id}",
            record=record,
            record_path=record_path,
            artifacts=artifacts,
        )
        receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

        # Best-effort: also persist a manifest for backward compatibility.
        try:
            manifest = ContentManifest.from_record(record)
            write_manifest(REPO_ROOT, manifest)
        except Exception as exc:  # pragma: no cover - manifest is non-critical
            logger.debug("Manifest write skipped for %s: %s", content_id, exc)

        _register_f0_index(record, receipt)
    except FinerError:
        raise
    except Exception as e:
        logger.error(f"Bilibili F0 record persist failed: {e}", exc_info=True)
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Failed to persist F0 record: {e}",
            stage="F0",
            operation="bilibili_import",
            source_channel="bilibili",
            retryable=True,
            cause=e,
        )

    return ImportResponse(
        bvid=parsed_bvid,
        content_id=content_id,
        f0_path=str(record_path.parent),
        record_path=str(record_path),
        receipt_path=str(receipt_path),
        raw_artifacts={r: str(p) for r, p in artifacts.artifact_paths.items()},
        status="imported",
        content_record=record,
        receipt=receipt.model_dump(mode="json"),
    )


@router.post("/transcribe/{bvid}", response_model=TranscribeResponse)
async def transcribe_video(
    bvid: str,
    language: str = Query(default="zh", description="Transcription language"),
    save_files: bool = Query(default=True, description="Save transcript and metadata to disk"),
):
    """Download and transcribe B站 video (F1-adjacent — NOT an F0 acceptance path).

    Transcription is downstream of F0 intake: F0 only owns raw download +
    ContentRecord (see ``POST /api/bilibili/import``). This endpoint additionally
    runs Paraformer ASR, which requires ``DASHSCOPE_API_KEY``; that credential is
    required lazily here (R-09), so configuring the bilibili F0 channel never
    depends on it.

    This endpoint performs:
    1. Fetches video metadata
    2. Downloads audio stream
    3. Transcribes using Paraformer (requires DASHSCOPE_API_KEY)
    4. Saves transcript and metadata

    Args:
        bvid: BV ID or URL
        language: Language for transcription (zh, en)
        save_files: Whether to save files to disk

    Returns:
        TranscribeResponse with transcript segments
    """
    try:
        adapter = BilibiliAdapter(output_dir=BILIBILI_DIR)
        result = adapter.transcribe(bvid, language=language)

        transcript_path = None
        metadata_path = None

        if save_files:
            transcript_path = adapter.save_transcript(result)
            metadata_path = adapter.save_metadata(result)

        return transcript_to_response(result, transcript_path, metadata_path)

    except ValueError as e:
        # Missing DASHSCOPE_API_KEY is required lazily (R-09): surface it as a
        # retryable upstream-dependency error with a fix hint, not "invalid BV id".
        if "DASHSCOPE_API_KEY" in str(e):
            raise FinerError(
                ErrorCode.BILI_EXT_001,
                "Transcription requires DASHSCOPE_API_KEY (F1-adjacent ASR).",
                stage="F1",
                operation="bilibili_transcribe",
                source_channel="bilibili",
                retryable=True,
                fix_hint="Set DASHSCOPE_API_KEY in the environment to enable ASR.",
                cause=e,
            )
        raise FinerError(
            ErrorCode.BILI_IN_001,
            str(e),
            stage="F0",
            operation="bilibili_transcribe",
            source_channel="bilibili",
            retryable=False,
            cause=e,
        )
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise FinerError(
            ErrorCode.BILI_EXT_001,
            f"Transcription failed: {e}",
            stage="F1",
            operation="bilibili_transcribe",
            source_channel="bilibili",
            retryable=True,
            cause=e,
        )


@router.post("/transcribe-async/{bvid}", response_model=TaskStatusResponse)
async def transcribe_video_async(
    bvid: str,
    background_tasks: BackgroundTasks,
    language: str = Query(default="zh"),
):
    """Start asynchronous transcription task.

    For long videos, use this endpoint to avoid timeout.
    Check status with /task/{task_id} endpoint.

    Args:
        bvid: BV ID or URL
        language: Transcription language

    Returns:
        TaskStatusResponse with task_id
    """
    import uuid

    task_id = str(uuid.uuid4())
    client = BilibiliClient()
    parsed_bvid = client.parse_bvid(bvid)

    # Create task record
    task = TaskStatusResponse(
        task_id=task_id,
        bvid=parsed_bvid,
        status="pending",
        created_at=datetime.now().isoformat(),
    )
    _tasks[task_id] = task

    # Define background task
    def run_transcription():
        _tasks[task_id].status = "running"
        try:
            adapter = BilibiliAdapter(output_dir=BILIBILI_DIR)
            result = adapter.transcribe(parsed_bvid, language=language)

            transcript_path = adapter.save_transcript(result)
            metadata_path = adapter.save_metadata(result)

            response = transcript_to_response(result, transcript_path, metadata_path)

            _tasks[task_id].result = response
            _tasks[task_id].status = "completed"
            _tasks[task_id].completed_at = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"Async transcription failed: {e}")
            _tasks[task_id].status = "failed"
            _tasks[task_id].error = str(e)
            _tasks[task_id].completed_at = datetime.now().isoformat()

    background_tasks.add_task(run_transcription)

    return task


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get status of an async transcription task.

    Args:
        task_id: Task ID from transcribe-async

    Returns:
        TaskStatusResponse with current status and result if completed
    """
    if task_id not in _tasks:
        raise FinerError(
            ErrorCode.BILI_NTF_001,
            "Task not found",
            stage="F0",
            operation="bilibili_task_status",
            source_channel="bilibili",
            retryable=False,
        )

    return _tasks[task_id]


@router.post("/sync/{bvid}", response_model=SyncResponse)
async def sync_to_f0_intake(
    bvid: str,
    req: Optional[SyncRequest] = None,
):
    """Legacy: promote an already-transcribed video into F0 (F1-adjacent).

    Deprecated in favor of ``POST /api/bilibili/import``, which produces a
    canonical ``ContentRecord`` + ``ImportReceipt`` + Project Memory row directly
    from the raw artifact set, with no transcript dependency. This endpoint is
    kept only for the older "transcribe first, then sync the markdown" flow and
    still requires ``/transcribe`` to have run.

    This endpoint:
    1. Checks if a transcript exists (404 with BILI_NTF_001 otherwise)
    2. Creates an F0 ContentRecord + manifest
    3. Copies the transcript into the F0 ingestion directory

    Args:
        bvid: BV ID
        req: Optional sync parameters (tags, category)

    Returns:
        SyncResponse with F0 paths
    """
    try:
        client = BilibiliClient()
        parsed_bvid = client.parse_bvid(bvid)

        # Find transcript files
        transcript_file = None
        metadata_file = None

        for uploader_dir in BILIBILI_DIR.iterdir():
            if uploader_dir.is_dir():
                candidate = uploader_dir / f"{parsed_bvid}_transcript.md"
                if candidate.exists():
                    transcript_file = candidate
                    metadata_file = uploader_dir / f"{parsed_bvid}_metadata.json"
                    break

        if not transcript_file:
            raise FinerError(
                ErrorCode.BILI_NTF_001,
                f"Transcript not found for {parsed_bvid}. Run /transcribe first.",
                stage="F0",
                operation="bilibili_sync",
                source_channel="bilibili",
                retryable=False,
            )

        # Create F0 content ID
        import json
        import shutil
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

        # Derive stable content_id from platform identifiers
        content_id = hashlib.sha256(
            f"bilibili:{metadata['uploader_id']}:{parsed_bvid}".encode("utf-8")
        ).hexdigest()[:32]

        # Compute dedupe fingerprint
        dedupe_fingerprint = hashlib.sha256(
            f"bilibili:{metadata['uploader_id']}:{parsed_bvid}".encode("utf-8")
        ).hexdigest()[:16]

        # Create F0 directory structure
        f0_dir = DATA_ROOT / "F0_intake" / "bilibili" / str(metadata["uploader_id"])
        f0_dir.mkdir(parents=True, exist_ok=True)

        # Dedupe check: skip if ContentRecord already exists
        existing_record = f0_dir / f"{content_id}.json"
        if existing_record.exists():
            return SyncResponse(
                bvid=parsed_bvid,
                content_id=content_id,
                f0_path=str(f0_dir),
                transcript_path=str(f0_dir / f"{parsed_bvid}.md"),
                metadata_path=str(existing_record),
                status="already_synced",
            )

        f0_transcript = f0_dir / f"{parsed_bvid}.md"

        # Copy transcript
        shutil.copy(transcript_file, f0_transcript)

        # Build ContentRecord (canonical F0 output)
        published_at = None
        try:
            published_at = datetime.fromisoformat(metadata["publish_time"])
        except (ValueError, KeyError):
            published_at = datetime.now(timezone.utc)

        record = ContentRecord(
            content_id=content_id,
            source_type="bilibili_video",
            source_platform="bilibili",
            creator_id=str(metadata["uploader_id"]),
            creator_name=metadata.get("uploader"),
            published_at=published_at,
            title=metadata.get("title"),
            raw_path=str(f0_transcript),
            file_type=_infer_file_type(f0_transcript.suffix),
            metadata={
                "bvid": parsed_bvid,
                "aid": metadata.get("aid", 0),
                "uploader_id": metadata["uploader_id"],
                "duration": metadata.get("duration", 0),
                "tags": (req.tags if req else []) or metadata.get("tags", []),
                "category": req.category if req else None,
                "ingest_time": datetime.now().isoformat(),
            },
            source_url=f"https://www.bilibili.com/video/{parsed_bvid}",
            external_source_id=parsed_bvid,
            dedupe_fingerprint=dedupe_fingerprint,
            language="zh",
            market_scope=["US", "HK", "A"],
        )

        # Persist ContentRecord as JSON
        record_path = f0_dir / f"{record.content_id}.json"
        record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        # Also persist manifest for backward compatibility
        manifest = ContentManifest.from_record(record)
        manifest_path = write_manifest(REPO_ROOT, manifest)

        return SyncResponse(
            bvid=parsed_bvid,
            content_id=content_id,
            f0_path=str(f0_dir),
            transcript_path=str(f0_transcript),
            metadata_path=str(manifest_path),
            status="synced",
        )

    except FinerError:
        # Already-canonical errors (e.g. transcript-not-found) must propagate with
        # their own code, not be re-wrapped as F0_IO_001 by the handler below.
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise FinerError(
            ErrorCode.F0_IO_001,
            f"Sync failed: {e}",
            stage="F0",
            operation="bilibili_sync",
            source_channel="bilibili",
            retryable=True,
            cause=e,
        )


@router.get("/search")
async def search_bilibili_videos(
    keyword: str = Query(default="", description="Search keyword"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=50, description="Results per page"),
):
    """Search Bilibili videos by keyword.

    Args:
        keyword: Search keyword (empty returns no results)
        page: Page number (1-based)
        page_size: Results per page (1-50)

    Returns:
        Search results with video metadata
    """
    if not keyword:
        return {"ok": True, "data": {"videos": [], "total": 0}}

    try:
        client = BilibiliClient()
        results = client.search_videos(keyword, page, page_size)
        return {"ok": True, "data": results}
    except Exception as e:
        logger.error(f"Bilibili search failed: {e}")
        return error_response(ErrorCode.BILI_EXT_001, str(e))


@router.get("/list")
async def list_transcribed_videos(
    limit: int = Query(default=20, le=100),
    uploader_id: Optional[int] = None,
):
    """List all transcribed videos.

    Args:
        limit: Maximum number of results
        uploader_id: Filter by uploader ID

    Returns:
        List of transcribed video metadata
    """
    videos = []

    if not BILIBILI_DIR.exists():
        return {"videos": [], "total": 0}

    for uploader_dir in BILIBILI_DIR.iterdir():
        if not uploader_dir.is_dir():
            continue

        try:
            uploader_id_int = int(uploader_dir.name)
            if uploader_id and uploader_id_int != uploader_id:
                continue
        except ValueError:
            continue

        for metadata_file in uploader_dir.glob("*_metadata.json"):
            try:
                import json
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

                videos.append({
                    "bvid": metadata["bvid"],
                    "title": metadata["title"],
                    "uploader": metadata["uploader"],
                    "uploader_id": metadata["uploader_id"],
                    "publish_time": metadata["publish_time"],
                    "duration": metadata["duration"],
                    "transcribed_at": metadata["transcription"]["transcribed_at"],
                })

                if len(videos) >= limit:
                    break

            except Exception as e:
                logger.warning(f"Failed to parse {metadata_file}: {e}")
                continue

        if len(videos) >= limit:
            break

    return {
        "videos": videos,
        "total": len(videos),
    }


@router.delete("/{bvid}")
async def delete_transcription(bvid: str):
    """Delete transcription files.

    Args:
        bvid: BV ID

    Returns:
        Deletion status
    """
    client = BilibiliClient()
    parsed_bvid = client.parse_bvid(bvid)

    deleted_files = []

    for uploader_dir in BILIBILI_DIR.iterdir():
        if not uploader_dir.is_dir():
            continue

        transcript_file = uploader_dir / f"{parsed_bvid}_transcript.md"
        metadata_file = uploader_dir / f"{parsed_bvid}_metadata.json"

        for file_path in [transcript_file, metadata_file]:
            if file_path.exists():
                file_path.unlink()
                deleted_files.append(str(file_path))

    if not deleted_files:
        raise FinerError(
            ErrorCode.BILI_NTF_001,
            f"No files found for {parsed_bvid}",
            stage="F0",
            operation="bilibili_files",
            source_channel="bilibili",
            retryable=False,
        )

    return {
        "bvid": parsed_bvid,
        "deleted_files": deleted_files,
        "status": "deleted",
    }
