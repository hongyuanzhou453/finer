"""BBDown API Routes — REST endpoints for Bilibili download integration.

Provides endpoints for:
- Video info fetching
- Audio/subtitle download
- Video transcription
"""

from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import Optional
import logging

from finer.schemas.bbdown import (
    BBDownVideoInfo,
    BBDownDownloadRequest,
    BBDownTaskResponse,
    BBDownConfigResponse,
    BBDownTranscribeRequest,
    BBDownTranscribeResult,
)
from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError
from finer.ingestion.bbdown_client import (
    BBDownAdapter,
    BBDownConfig,
    BBDownError,
    BBDownUnavailableError,
)
from finer.paths import DATA_ROOT

logger = logging.getLogger(__name__)
router = APIRouter()

# Singleton adapter
_adapter: Optional[BBDownAdapter] = None


def get_adapter() -> BBDownAdapter:
    """Get or create the F0 BBDown download adapter singleton.

    F0/F1 boundary (R-11): this builds a download-only adapter and deliberately
    does NOT import or wire the F1 ASR client (``finer.parsing.mimo_asr_client``).
    The ASR client is an F1 dependency; it is injected lazily, only by the
    F1-adjacent ``/transcribe`` endpoint via :func:`_resolve_asr_client`, so the
    F0 download surface never depends on F1.
    """
    global _adapter
    if _adapter is None:
        from finer.config import load_bbdown_config
        from finer.paths import REPO_ROOT

        bbdown_cfg = load_bbdown_config(REPO_ROOT)

        _adapter = BBDownAdapter(
            config=BBDownConfig(
                api_url=bbdown_cfg.api_url,
                auto_start=bbdown_cfg.auto_start,
                cookie=bbdown_cfg.cookie,
                download_dir=Path(bbdown_cfg.download_dir),
            ),
        )
    return _adapter


def _resolve_asr_client():
    """Lazily build the F1 ASR client for the F1-adjacent transcribe path.

    R-11: keep this F0 download router free of any static ``finer.parsing``
    import. ASR is owned by F1; the transcribe endpoint resolves it at call time
    through ``importlib`` so the F0 module never statically depends on F1.
    """
    import importlib

    from finer.config import load_mimo_asr_config
    from finer.paths import REPO_ROOT

    asr_module = importlib.import_module("finer.parsing.mimo_asr_client")
    mimo_cfg = load_mimo_asr_config(REPO_ROOT)
    return asr_module.MiMoASRClient(mimo_cfg)


def _bbdown_unavailable_error(operation: str, exc: BBDownUnavailableError) -> FinerError:
    """Map a BBDown-unavailable failure onto the canonical F0_EXT_001 envelope."""
    return FinerError(
        ErrorCode.F0_EXT_001,
        str(exc),
        stage="F0",
        operation=operation,
        source_channel="bilibili",
        retryable=True,
        fix_hint=getattr(exc, "fix_hint", "install .NET 8 runtime"),
        cause=exc,
    )


@router.get("/video/{bvid}", response_model=BBDownVideoInfo)
async def get_video_info(bvid: str):
    """Get Bilibili video information.

    Args:
        bvid: BV ID (e.g., BV1xx411c7mD)

    Returns:
        Video metadata
    """
    adapter = get_adapter()
    try:
        return await adapter.get_video_info(bvid)
    except BBDownUnavailableError as e:
        raise _bbdown_unavailable_error("bbdown_video_info", e)
    except BBDownError as e:
        logger.error(f"Failed to get video info: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@router.post("/download", response_model=BBDownTaskResponse)
async def create_download_task(request: BBDownDownloadRequest):
    """Create a download task.

    Args:
        request: Download request with BVID and options

    Returns:
        Task response with status
    """
    adapter = get_adapter()
    try:
        if request.download_audio and not request.download_video:
            path = await adapter.download_audio(request.bvid_or_url)
            return BBDownTaskResponse(
                task_id=adapter._extract_bvid(request.bvid_or_url),
                bvid=adapter._extract_bvid(request.bvid_or_url),
                status="completed",
                progress=1.0,
                audio_path=str(path) if path else None,
            )
        else:
            # For video downloads, use the task-based approach
            from finer.ingestion.bbdown_client import BBDownClient

            async with BBDownClient(adapter.config) as client:
                task = await client.add_download_task(request)
                return task
    except BBDownUnavailableError as e:
        raise _bbdown_unavailable_error("bbdown_download", e)
    except BBDownError as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@router.post("/transcribe/{bvid}", response_model=BBDownTranscribeResult)
async def transcribe_video(
    bvid: str,
    prefer_subtitle: bool = Query(default=True, description="优先使用 CC 字幕"),
    language: str = Query(default="zh", description="语言"),
):
    """Transcribe video using subtitle or ASR.

    F1-adjacent (NOT an F0 acceptance path): transcription is downstream of F0
    intake. F0 only owns raw download + ContentRecord (see ``/api/bilibili/import``).
    The F1 ASR client is injected lazily here (R-11) so the F0 download surface
    stays free of any F1 dependency.

    Priority:
    1. CC subtitle (if available and prefer_subtitle=True)
    2. MiMo ASR (if configured)

    Args:
        bvid: BV ID
        prefer_subtitle: Whether to prefer CC subtitle over ASR
        language: Language code

    Returns:
        Transcription result with segments
    """
    adapter = get_adapter()
    # Inject the F1-owned ASR client only for this F1-adjacent path.
    if adapter.asr_client is None:
        try:
            adapter.asr_client = _resolve_asr_client()
        except Exception as e:  # ASR optional; subtitle path may still succeed
            logger.warning(f"ASR client unavailable, subtitle-only transcribe: {e}")
    try:
        result = await adapter.transcribe_video(bvid, prefer_subtitle, language)
        return BBDownTranscribeResult(**result)
    except BBDownUnavailableError as e:
        raise _bbdown_unavailable_error("bbdown_transcribe", e)
    except BBDownError as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@router.get("/config", response_model=BBDownConfigResponse)
async def get_config():
    """Get BBDown service configuration and status.

    Returns:
        Configuration and health status
    """
    from finer.config import load_bbdown_config
    from finer.paths import REPO_ROOT

    cfg = load_bbdown_config(REPO_ROOT)

    # Check if BBDown is running
    is_running = False
    version = None

    try:
        import httpx

        response = httpx.get(f"{cfg.api_url}/get-tasks/", timeout=5.0)
        is_running = response.status_code == 200
    except Exception:
        pass

    return BBDownConfigResponse(
        service_url=cfg.api_url,
        is_running=is_running,
        version=version,
        supported_qualities=[],  # Would need to query BBDown
        supported_audio_qualities=[],
    )


@router.post("/tasks/{task_id}/status", response_model=BBDownTaskResponse)
async def get_task_status(task_id: str):
    """Get status of a download task.

    Args:
        task_id: Task ID (usually the AID)

    Returns:
        Task status
    """
    from finer.ingestion.bbdown_client import BBDownClient

    adapter = get_adapter()
    try:
        async with BBDownClient(adapter.config) as client:
            return await client.get_task_status(task_id)
    except BBDownError as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@router.post("/tasks/cleanup")
async def cleanup_finished_tasks():
    """Remove all finished tasks from BBDown.

    Returns:
        Number of tasks removed
    """
    from finer.ingestion.bbdown_client import BBDownClient

    adapter = get_adapter()
    try:
        async with BBDownClient(adapter.config) as client:
            await client.remove_finished_tasks()
            return {"ok": True, "message": "Finished tasks removed"}
    except BBDownError as e:
        logger.error(f"Failed to cleanup tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Check BBDown integration health.

    Returns:
        Health status
    """
    from finer.config import load_bbdown_config, load_mimo_asr_config
    from finer.paths import REPO_ROOT
    import httpx

    bbdown_cfg = load_bbdown_config(REPO_ROOT)
    mimo_cfg = load_mimo_asr_config(REPO_ROOT)

    bbdown_healthy = False
    mimo_healthy = False

    # Check BBDown
    try:
        response = httpx.get(f"{bbdown_cfg.api_url}/get-tasks/", timeout=5.0)
        bbdown_healthy = response.status_code == 200
    except Exception:
        pass

    # Check MiMo ASR
    try:
        response = httpx.get(
            mimo_cfg.api_url.rsplit("/", 1)[0] + "/health",
            timeout=5.0,
        )
        mimo_healthy = response.status_code == 200
    except Exception:
        pass

    return {
        "bbdown": {
            "url": bbdown_cfg.api_url,
            "healthy": bbdown_healthy,
            "auto_start": bbdown_cfg.auto_start,
        },
        "mimo_asr": {
            "url": mimo_cfg.api_url,
            "healthy": mimo_healthy,
        },
        "overall": bbdown_healthy or mimo_healthy,
    }
