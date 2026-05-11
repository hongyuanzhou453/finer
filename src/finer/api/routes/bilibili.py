"""Bilibili API Routes — Video download and transcription endpoints.

Provides REST API for:
- GET /api/bilibili/video/{bvid} - Get video info
- POST /api/bilibili/transcribe/{bvid} - Download and transcribe
- POST /api/bilibili/sync/{bvid} - Sync to F0 Intake

All endpoints follow the project's API patterns.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from pathlib import Path
from datetime import datetime
import logging

from finer.ingestion.bilibili_adapter import (
    BilibiliAdapter,
    BilibiliVideoInfo,
    TranscriptResult,
    BilibiliClient,
)

from finer.errors import FinerError, ErrorCode, error_response
from finer.paths import REPO_ROOT, DATA_ROOT
from finer.manifests import ContentManifest, _infer_file_type, write_manifest, build_content_id

logger = logging.getLogger(__name__)

router = APIRouter()
BILIBILI_DIR = DATA_ROOT / "raw" / "bilibili"


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


# In-memory task tracking (for demo, should use Redis in production)
_tasks: dict[str, TaskStatusResponse] = {}


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


@router.post("/transcribe/{bvid}", response_model=TranscribeResponse)
async def transcribe_video(
    bvid: str,
    language: str = Query(default="zh", description="Transcription language"),
    save_files: bool = Query(default=True, description="Save transcript and metadata to disk"),
):
    """Download and transcribe B站 video.

    This endpoint performs:
    1. Fetches video metadata
    2. Downloads audio stream
    3. Transcribes using Paraformer
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
            stage="F0",
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
    """Sync transcribed video to F0 Intake layer.

    This endpoint:
    1. Checks if transcript exists
    2. Creates F0 manifest
    3. Copies to F0 ingestion directory

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
        content_id = f"bilibili_{parsed_bvid}"

        # Create F0 directory structure
        f0_dir = DATA_ROOT / "F0_intake" / "bilibili" / str(metadata["uploader_id"])
        f0_dir.mkdir(parents=True, exist_ok=True)

        f0_transcript = f0_dir / f"{parsed_bvid}.md"

        # Copy transcript
        shutil.copy(transcript_file, f0_transcript)

        # Build and persist manifest via canonical ContentManifest
        manifest = ContentManifest(
            content_id=content_id,
            source_type="bilibili_video",
            source_platform="bilibili",
            creator_id=str(metadata["uploader_id"]),
            creator_name=metadata["uploader"],
            published_at=metadata["publish_time"],
            collected_at=datetime.utcnow().replace(microsecond=0).isoformat(),
            title=metadata["title"],
            raw_path=str(f0_transcript),
            file_type=_infer_file_type(f0_transcript.suffix),
            metadata={
                "bvid": parsed_bvid,
                "aid": metadata.get("aid", 0),
                "uploader_id": metadata["uploader_id"],
                "duration": metadata["duration"],
                "tags": (req.tags if req else []) or metadata.get("tags", []),
                "category": req.category if req else None,
                "ingest_time": datetime.now().isoformat(),
            },
            source_url=f"https://www.bilibili.com/video/{parsed_bvid}",
            external_source_id=parsed_bvid,
            dedupe_fingerprint=None,
            language="zh",
            market_scope=["US", "HK", "A"],
        )

        manifest_path = write_manifest(REPO_ROOT, manifest)

        return SyncResponse(
            bvid=parsed_bvid,
            content_id=content_id,
            f0_path=str(f0_dir),
            transcript_path=str(f0_transcript),
            metadata_path=str(manifest_path),
            status="synced",
        )

    except HTTPException:
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
