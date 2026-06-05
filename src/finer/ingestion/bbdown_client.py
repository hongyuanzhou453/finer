"""BBDown Client — Interface to BBDown CLI/API for Bilibili downloads.

BBDown is a C# .NET tool that provides:
- Video download (multiple qualities)
- Audio extraction
- CC subtitle download
- Multi-page support
- Cookie auth for premium content

This client wraps BBDown's JSON API server mode for integration.

Usage:
    async with BBDownClient() as client:
        info = await client.get_video_info("BV1xx411c7mD")
        task = await client.download_audio("BV1xx411c7mD")
        result = await client.wait_for_task(task.task_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from finer.schemas.bbdown import (
    BBDownDownloadRequest,
    BBDownSubtitle,
    BBDownTaskResponse,
    BBDownVideoInfo,
    DownloadTaskStatus,
    SubtitleFormat,
)

logger = logging.getLogger(__name__)


class BBDownError(Exception):
    """BBDown operation error."""
    pass


class BBDownNotRunningError(BBDownError):
    """BBDown service is not running."""
    pass


class BBDownNotInstalledError(BBDownError):
    """BBDown is not installed."""
    pass


class BBDownUnavailableError(BBDownError):
    """BBDown CLI cannot run in this environment (missing binary or .NET runtime).

    Raised when the F0 download layer cannot even start BBDown — either the
    ``BBDown`` binary is not on PATH, or it is present but its required .NET
    runtime is missing/incompatible (BBDown needs .NET 8). This is an external
    dependency failure (retryable once the runtime is installed), not bad user
    input, so callers map it onto a canonical ``F0_EXT_001`` error envelope
    instead of letting the raw failure crash F0 intake.
    """

    fix_hint = "install .NET 8 runtime"


@dataclass
class BBDownConfig:
    """BBDown configuration."""

    api_url: str = "http://localhost:12450"
    timeout: float = 300.0  # 5 minutes for large files
    download_dir: Path = field(default_factory=lambda: Path("data/raw/bilibili"))
    cookie: Optional[str] = None  # For premium content
    auto_start: bool = True  # Auto-start BBDown if not running


@dataclass
class BilibiliRawArtifacts:
    """Raw artifact set produced by an F0 BBDown download (R-10).

    Pure F0 provenance: raw media bytes on disk + a source-info JSON, plus the
    parsed BBDown video info. Contains NO transcript / ASR output — F0 download
    must never depend on transcription. The route layer turns this into a
    ``ContentRecord`` + ``ImportReceipt``.
    """

    bvid: str
    info: "BBDownVideoInfo"
    raw_dir: Path
    source_info_path: Path
    audio_path: Optional[Path] = None
    video_path: Optional[Path] = None
    subtitle_path: Optional[Path] = None
    # Map of artifact role -> filesystem path (only present roles included).
    artifact_paths: Dict[str, Path] = field(default_factory=dict)


class BBDownClient:
    """Client for BBDown API server.

    BBDown must be running in server mode:
        BBDown serve -l http://0.0.0.0:12450

    Or the client can auto-start it if auto_start=True.
    """

    def __init__(self, config: Optional[BBDownConfig] = None):
        self.config = config or BBDownConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._bbdown_process: Optional[subprocess.Popen] = None

    async def __aenter__(self) -> "BBDownClient":
        await self._ensure_service()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _ensure_service(self) -> None:
        """Ensure BBDown API service is running."""
        # Check if already running
        if await self._check_health():
            logger.info("BBDown service already running")
            return

        if not self.config.auto_start:
            raise BBDownNotRunningError(
                "BBDown service not running. Start with: BBDown serve -l http://0.0.0.0:12450"
            )

        # Try to start BBDown
        await self._start_bbdown()

    async def _check_health(self) -> bool:
        """Check if BBDown API is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.config.api_url}/get-tasks/")
                return response.status_code == 200
        except Exception:
            return False

    async def _start_bbdown(self) -> None:
        """Start BBDown in server mode."""
        # Check if BBDown is installed
        if not shutil.which("BBDown"):
            raise BBDownNotInstalledError(
                "BBDown not found. Install from: https://github.com/nilaoda/BBDown\n"
                "  dotnet tool install --global BBDown"
            )

        # Get BBDown version
        try:
            result = subprocess.run(
                ["BBDown", "--help"],
                capture_output=True,
                text=True,
            )
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            logger.info(f"BBDown version: {first_line}")
        except Exception as e:
            logger.warning(f"Could not get BBDown version: {e}")

        # Start BBDown in server mode
        listen_addr = self.config.api_url.replace("http://", "").replace("https://", "")
        cmd = ["BBDown", "serve", "-l", listen_addr]

        logger.info(f"Starting BBDown: {' '.join(cmd)}")
        self._bbdown_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for service to start
        for i in range(10):
            if await self._check_health():
                logger.info("BBDown service started")
                return
            await asyncio.sleep(1)

        raise BBDownError("Failed to start BBDown service")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.api_url,
                timeout=self.config.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        # Note: We don't kill the BBDown process on close
        # as it may be used by other clients

    async def get_video_info(self, bvid_or_url: str) -> BBDownVideoInfo:
        """Get video information without downloading.

        Note: BBDown API doesn't have a direct info endpoint,
        so we parse info from the download task or use bilibili_adapter.
        """
        # Extract BVID
        bvid = self._extract_bvid(bvid_or_url)

        # Try to get info from existing task
        client = await self._get_client()
        response = await client.get(f"/get-tasks/{bvid}")
        if response.status_code == 200:
            task_data = response.json()
            return self._parse_video_info_from_task(task_data)

        # Fallback: use bilibili_adapter for info
        from finer.ingestion.bilibili_adapter import BilibiliClient

        sync_client = BilibiliClient()
        info = sync_client.get_video_info(bvid)

        return BBDownVideoInfo(
            bvid=info.bvid,
            aid=info.aid,
            title=info.title,
            uploader=info.uploader,
            uploader_id=info.uploader_id,
            publish_time=info.publish_time,
            duration=info.duration,
            description=info.description,
            cover_url=info.cover_url,
            page_count=info.page_count,
            tags=info.tags,
            has_subtitle=False,  # Will be determined during download
        )

    def _extract_bvid(self, bvid_or_url: str) -> str:
        """Extract BVID from URL or return as-is."""
        # Pattern for BV ID
        bv_pattern = r"(BV[a-zA-Z0-9]{10})"
        match = re.search(bv_pattern, bvid_or_url)
        if match:
            return match.group(1)

        # Pattern for AV ID
        av_pattern = r"av(\d+)"
        match = re.search(av_pattern, bvid_or_url)
        if match:
            # Convert AV to BV (simplified - in production use proper conversion)
            return f"av{match.group(1)}"

        # Assume it's already a BVID
        return bvid_or_url

    async def add_download_task(
        self,
        request: BBDownDownloadRequest,
    ) -> BBDownTaskResponse:
        """Add a download task to BBDown."""
        client = await self._get_client()

        # Build BBDown command arguments
        args = self._build_download_args(request)

        # BBDown API expects a JSON body with Url field
        payload = {"Url": request.bvid_or_url}

        # Add optional parameters
        if request.cookie:
            payload["cookie"] = request.cookie
        elif self.config.cookie:
            payload["cookie"] = self.config.cookie

        if request.download_audio and not request.download_video:
            payload["audioOnly"] = True

        if request.download_subtitle:
            payload["subOnly"] = True

        if request.output_dir:
            payload["workDir"] = request.output_dir
        else:
            payload["workDir"] = str(self.config.download_dir)

        try:
            response = await client.post("/add-task", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                raise BBDownError(f"Invalid request: {e.response.text}")
            raise BBDownError(f"BBDown API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise BBDownNotRunningError(f"BBDown service not available: {e}")

        # BBDown returns 200 OK on success
        bvid = self._extract_bvid(request.bvid_or_url)
        return BBDownTaskResponse(
            task_id=bvid,  # BBDown uses AID as task ID
            bvid=bvid,
            status=DownloadTaskStatus.RUNNING,
        )

    def _build_download_args(self, request: BBDownDownloadRequest) -> List[str]:
        """Build BBDown CLI arguments from request."""
        args = [request.bvid_or_url]

        if request.download_video:
            args.extend(["-q", request.quality.value])

        if request.download_audio and not request.download_video:
            args.append("--audio-only")

        if request.download_subtitle:
            args.extend(["--sub-only"])

        if request.page_index is not None:
            args.extend(["-p", str(request.page_index)])

        if request.cookie:
            args.extend(["-c", request.cookie])
        elif self.config.cookie:
            args.extend(["-c", self.config.cookie])

        args.extend(["--work-dir", str(self.config.download_dir)])

        return args

    async def get_task_status(self, task_id: str) -> BBDownTaskResponse:
        """Get status of a download task."""
        client = await self._get_client()

        response = await client.get("/get-tasks/")
        response.raise_for_status()

        data = response.json()

        # Check running tasks
        for task in data.get("Running", []):
            if task.get("Aid") == task_id or task.get("Aid") == task_id.lstrip("av"):
                return self._parse_task_response(task, DownloadTaskStatus.RUNNING)

        # Check finished tasks
        for task in data.get("Finished", []):
            if task.get("Aid") == task_id or task.get("Aid") == task_id.lstrip("av"):
                status = (
                    DownloadTaskStatus.COMPLETED
                    if task.get("IsSuccessful")
                    else DownloadTaskStatus.FAILED
                )
                return self._parse_task_response(task, status)

        raise BBDownError(f"Task {task_id} not found")

    async def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout: float = 600.0,
    ) -> BBDownTaskResponse:
        """Wait for task completion."""
        elapsed = 0.0
        while elapsed < timeout:
            result = await self.get_task_status(task_id)

            if result.status in (DownloadTaskStatus.COMPLETED, DownloadTaskStatus.FAILED):
                return result

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise BBDownError(f"Task {task_id} timed out after {timeout}s")

    def _parse_task_response(
        self,
        data: Dict[str, Any],
        status: DownloadTaskStatus,
    ) -> BBDownTaskResponse:
        """Parse BBDown task response."""
        return BBDownTaskResponse(
            task_id=str(data.get("Aid", "")),
            bvid=data.get("Url", ""),
            status=status,
            progress=data.get("Progress", 0.0),
            audio_path=None,  # Will be determined from download dir
            error_message=None if data.get("IsSuccessful", True) else "Download failed",
        )

    def _parse_video_info_from_task(self, data: Dict[str, Any]) -> BBDownVideoInfo:
        """Parse video info from task data."""
        from datetime import datetime

        return BBDownVideoInfo(
            bvid=data.get("Url", ""),
            aid=int(data.get("Aid", 0)),
            title=data.get("Title", ""),
            uploader="",
            uploader_id=0,
            publish_time=datetime.fromtimestamp(data.get("VideoPubTime", 0)),
            duration=0,
            description="",
            cover_url=data.get("Pic", ""),
            page_count=1,
            tags=[],
            has_subtitle=False,
        )

    async def remove_finished_tasks(self) -> List[str]:
        """Remove all finished tasks."""
        client = await self._get_client()
        response = await client.get("/remove-finished")
        response.raise_for_status()
        return []

    async def remove_failed_tasks(self) -> List[str]:
        """Remove all failed tasks."""
        client = await self._get_client()
        response = await client.get("/remove-finished/failed")
        response.raise_for_status()
        return []


class BBDownAdapter:
    """High-level adapter for BBDown integration with Finer pipeline.

    Provides:
    - Video info fetching
    - Audio download for ASR
    - Subtitle extraction
    - Integration with MiMo ASR
    """

    def __init__(
        self,
        config: Optional[BBDownConfig] = None,
        asr_client: Optional[Any] = None,  # MiMoASRClient
    ):
        self.config = config or BBDownConfig()
        self.config.download_dir = Path(self.config.download_dir)
        self.bbdown = BBDownClient(self.config)
        self.asr_client = asr_client

    @staticmethod
    def _cli_env(cookie: Optional[str] = None) -> dict[str, str]:
        """Build a stable environment for BBDown CLI execution."""
        env = os.environ.copy()
        path_parts = [
            str(Path.home() / ".dotnet" / "tools"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            env.get("PATH", ""),
        ]
        env["PATH"] = os.pathsep.join(p for p in path_parts if p)
        if "DOTNET_ROOT" not in env:
            for candidate in [
                Path("/opt/homebrew/opt/dotnet/libexec"),
                Path("/usr/local/share/dotnet"),
                Path("/usr/share/dotnet"),
            ]:
                if candidate.exists():
                    env["DOTNET_ROOT"] = str(candidate)
                    break
        if cookie:
            env["BBDOWN_COOKIE"] = cookie
        return env

    @staticmethod
    def _parse_duration(duration: str) -> int:
        """Parse BBDown duration strings like ``11m58s`` or ``1h02m03s``."""
        value = duration.strip()
        if not value:
            return 0

        if ":" in value:
            parts = [int(p) for p in value.split(":")]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]

        match = re.fullmatch(
            r"(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?",
            value,
        )
        if not match:
            return 0
        return (
            int(match.group("hours") or 0) * 3600
            + int(match.group("minutes") or 0) * 60
            + int(match.group("seconds") or 0)
        )

    def _cookie(self) -> Optional[str]:
        return self.config.cookie or os.getenv("BBDOWN_COOKIE")

    def _cookie_args(self) -> list[str]:
        cookie = self._cookie()
        return ["-c", cookie] if cookie else []

    # Markers BBDown / the .NET host emit when the required runtime is missing or
    # the wrong major version (BBDown targets .NET 8). Matched case-insensitively
    # against combined stdout+stderr to detect a "BBDown can't even start" failure.
    _DOTNET_MISSING_MARKERS = (
        "you must install or update .net",
        "to run this application, you must install .net",
        "no .net runtimes were found",
        "the framework 'microsoft.netcore.app'",
        "framework: 'microsoft.netcore.app'",
        "not found",  # "...was not found." emitted by the .NET host
    )

    @classmethod
    def _is_dotnet_missing_output(cls, output: str) -> bool:
        """Detect a .NET-runtime-missing failure from BBDown/host CLI output."""
        lowered = output.lower()
        if "microsoft.netcore.app" in lowered or "download the .net runtime" in lowered:
            return True
        return any(marker in lowered for marker in cls._DOTNET_MISSING_MARKERS)

    def _run_cli(self, args: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
        """Run BBDown CLI and return the completed process.

        Raises :class:`BBDownUnavailableError` (mapped to ``F0_EXT_001`` upstream)
        when BBDown cannot run at all — the binary is missing from PATH, or it is
        present but its required .NET runtime is absent/incompatible. This keeps
        F0 intake from crashing on a missing external dependency (R-02).
        """
        env = self._cli_env(self._cookie())
        try:
            result = subprocess.run(
                ["BBDown", *args],
                cwd=str(cwd) if cwd else None,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BBDownUnavailableError(
                "BBDown binary not found on PATH. Install BBDown (requires .NET 8 "
                "runtime): dotnet tool install --global BBDown"
            ) from exc

        if result.returncode != 0 and self._is_dotnet_missing_output(
            self._combined_output(result)
        ):
            raise BBDownUnavailableError(
                "BBDown could not start: required .NET 8 runtime is missing or "
                "incompatible on this host."
            )
        return result

    @staticmethod
    def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
        return "\n".join(p for p in [result.stdout, result.stderr] if p)

    @staticmethod
    def _parse_publish_time(raw: str) -> datetime:
        value = raw.strip()
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            cleaned = re.sub(r"\s+[+-]\d{2}:\d{2}$", "", value)
            return datetime.fromisoformat(cleaned)

    @staticmethod
    def _safe_title_glob(title: str) -> str:
        return re.sub(r"[\[\]*?]", "", title).strip()

    async def get_video_info(self, bvid_or_url: str) -> BBDownVideoInfo:
        """Get video information."""
        bvid = self._extract_bvid(bvid_or_url)
        result = self._run_cli([
            bvid_or_url,
            "--only-show-info",
            "--hide-streams",
            "--skip-ai",
            *self._cookie_args(),
        ])
        output = self._combined_output(result)
        if result.returncode != 0:
            raise BBDownError(f"BBDown info failed: {output.strip()}")

        aid_match = re.search(r"获取aid结束:\s*(\d+)", output)
        title_match = re.search(r"视频标题:\s*(.+)", output)
        publish_match = re.search(r"发布时间:\s*(.+)", output)
        mid_match = re.search(r"space\.bilibili\.com/(\d+)", output)
        page_count_match = re.search(r"共计\s*(\d+)\s*个分P", output)
        page_matches = re.findall(
            r"P\d+:\s*\[[^\]]+\]\s*\[(?P<title>[^\]]+)\]\s*\[(?P<duration>[^\]]+)\]",
            output,
        )

        title = title_match.group(1).strip() if title_match else ""
        if not title and page_matches:
            title = page_matches[0][0].strip()

        duration = sum(self._parse_duration(item[1]) for item in page_matches)
        if not duration and page_matches:
            duration = self._parse_duration(page_matches[0][1])

        publish_time = (
            self._parse_publish_time(publish_match.group(1))
            if publish_match
            else datetime.fromtimestamp(0)
        )

        return BBDownVideoInfo(
            bvid=bvid,
            aid=int(aid_match.group(1)) if aid_match else 0,
            title=title,
            uploader="",
            uploader_id=int(mid_match.group(1)) if mid_match else 0,
            publish_time=publish_time,
            duration=duration,
            description="",
            cover_url="",
            page_count=int(page_count_match.group(1)) if page_count_match else max(len(page_matches), 1),
            tags=[],
            has_subtitle=False,
        )

    async def download_audio(
        self,
        bvid_or_url: str,
        output_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """Download audio file for ASR.

        Args:
            bvid_or_url: B站视频 BV ID 或 URL
            output_dir: 输出目录（默认使用 config.download_dir）

        Returns:
            下载的音频文件路径
        """
        search_dir = output_dir or self.config.download_dir
        search_dir = Path(search_dir)
        search_dir.mkdir(parents=True, exist_ok=True)
        bvid = self._extract_bvid(bvid_or_url)

        result = self._run_cli([
            bvid_or_url,
            "--audio-only",
            "--skip-cover",
            "--skip-subtitle",
            "--skip-ai",
            "-F",
            "<bvid>",
            "--work-dir",
            str(search_dir),
            *self._cookie_args(),
        ])
        output = self._combined_output(result)
        if result.returncode != 0:
            raise BBDownError(f"Audio download failed: {output.strip()}")

        for ext in [".m4a", ".mp3", ".flac", ".aac", ".m4s"]:
            audio_files = list(search_dir.glob(f"*{bvid}*{ext}"))
            if audio_files:
                return max(audio_files, key=lambda p: p.stat().st_mtime)

        audio_files = [
            p for ext in [".m4a", ".mp3", ".flac", ".aac", ".m4s"]
            for p in search_dir.glob(f"*{ext}")
        ]
        if audio_files:
            return max(audio_files, key=lambda p: p.stat().st_mtime)

        return None

    def _extract_bvid(self, bvid_or_url: str) -> str:
        """Extract BVID from URL or return as-is."""
        bv_pattern = r"(BV[a-zA-Z0-9]{10})"
        match = re.search(bv_pattern, bvid_or_url)
        if match:
            return match.group(1)
        return bvid_or_url

    async def download_subtitle(
        self,
        bvid_or_url: str,
        language: str = "zh-CN",
    ) -> Optional[BBDownSubtitle]:
        """Download CC subtitle if available.

        Args:
            bvid_or_url: B站视频 BV ID 或 URL
            language: 字幕语言

        Returns:
            字幕数据，如果视频没有字幕则返回 None
        """
        search_dir = Path(self.config.download_dir)
        search_dir.mkdir(parents=True, exist_ok=True)
        bvid = self._extract_bvid(bvid_or_url)
        before_run = time.time() - 1

        video_title = ""
        try:
            video_title = (await self.get_video_info(bvid_or_url)).title
        except Exception as exc:
            logger.debug("BBDown title lookup before subtitle download failed: %s", exc)

        result = self._run_cli([
            bvid_or_url,
            "--sub-only",
            "--skip-ai=false",
            "-F",
            "<bvid>",
            "--work-dir",
            str(search_dir),
            *self._cookie_args(),
        ])
        output = self._combined_output(result)
        if result.returncode != 0:
            logger.warning("Subtitle download failed: %s", output.strip())
            return None

        subtitle_file = self._find_subtitle_file(search_dir, bvid, video_title, before_run)
        if subtitle_file is None:
            return None

        content = subtitle_file.read_text(encoding="utf-8")
        fmt = subtitle_file.suffix.lstrip(".").lower()
        return BBDownSubtitle(
            language=language,
            format=SubtitleFormat(fmt),
            content=content,
            segments=self._parse_subtitle_segments(content, fmt),
        )

    def _find_subtitle_file(
        self,
        search_dir: Path,
        bvid: str,
        video_title: str = "",
        since: float = 0.0,
    ) -> Optional[Path]:
        """Find a BBDown subtitle file by BVID, title, then recent mtime."""
        candidates: list[Path] = []
        for ext in [".json", ".srt", ".ass"]:
            candidates.extend(search_dir.glob(f"*{bvid}*{ext}"))
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)

        if video_title:
            title_glob = self._safe_title_glob(video_title)
            if title_glob:
                title_candidates: list[Path] = []
                for ext in [".json", ".srt", ".ass"]:
                    title_candidates.extend(search_dir.glob(f"*{title_glob}*{ext}"))
                if title_candidates:
                    return max(title_candidates, key=lambda p: p.stat().st_mtime)

        recent = [
            p for ext in [".json", ".srt", ".ass"]
            for p in search_dir.glob(f"*{ext}")
            if p.stat().st_mtime >= since
        ]
        if recent:
            return max(recent, key=lambda p: p.stat().st_mtime)

        return None

    def _parse_subtitle_segments(
        self,
        content: str,
        format: str,
    ) -> List[Dict[str, Any]]:
        """Parse subtitle content into segments with timestamps."""
        segments = []

        if format == "json":
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        segments.append({
                            "start_time": item.get("from", 0),
                            "end_time": item.get("to", 0),
                            "text": item.get("content", ""),
                        })
                elif isinstance(data, dict) and "body" in data:
                    for item in data["body"]:
                        segments.append({
                            "start_time": item.get("from", 0),
                            "end_time": item.get("to", 0),
                            "text": item.get("content", ""),
                        })
            except json.JSONDecodeError:
                pass

        elif format == "srt":
            # Parse SRT format
            import re

            pattern = r"(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})\s+(.+?)(?=\n\n|\Z)"
            for match in re.finditer(pattern, content, re.DOTALL):
                start = self._parse_srt_time(match.group(2))
                end = self._parse_srt_time(match.group(3))
                text = match.group(4).strip().replace("\n", " ")
                segments.append({
                    "start_time": start,
                    "end_time": end,
                    "text": text,
                })

        return segments

    def _parse_srt_time(self, time_str: str) -> float:
        """Parse SRT timestamp to seconds."""
        parts = time_str.replace(",", ":").split(":")
        hours, minutes, seconds, millis = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds + millis / 1000

    async def download_raw_artifacts(
        self,
        bvid_or_url: str,
        *,
        output_dir: Optional[Path] = None,
        download_video: bool = False,
        download_audio: bool = True,
        download_subtitle: bool = True,
    ) -> BilibiliRawArtifacts:
        """F0 download: fetch raw media + source JSON for one B站 video (R-10).

        This is the canonical F0 entrypoint for the bilibili channel. It pulls
        the raw artifact set only — audio and/or video, the CC subtitle when one
        exists, and a ``{bvid}.source.json`` capturing BBDown's parsed video
        info — and never invokes ASR or any F1 transcription. The route layer
        turns the returned :class:`BilibiliRawArtifacts` into a ``ContentRecord``
        + ``ImportReceipt`` + Project Memory row, with no dependency on a
        transcript existing first (the old ``/sync``-after-``/transcribe`` gate).

        Raises:
            BBDownUnavailableError: BBDown / its .NET 8 runtime is unavailable.
                Surfaced upstream as a canonical ``F0_EXT_001`` error envelope.
            BBDownError: BBDown ran but the download itself failed.
        """
        raw_dir = Path(output_dir or self.config.download_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        bvid = self._extract_bvid(bvid_or_url)

        # 1. Source metadata (also the first point BBDown unavailability surfaces).
        info = await self.get_video_info(bvid_or_url)

        artifact_paths: dict[str, Path] = {}

        # 2. Raw media. Audio is the default ASR-feeding payload; video optional.
        audio_path: Optional[Path] = None
        video_path: Optional[Path] = None
        if download_audio:
            audio_path = await self.download_audio(bvid_or_url, raw_dir)
            if audio_path is not None:
                artifact_paths["audio"] = audio_path
        if download_video:
            video_path = await self._download_video(bvid_or_url, raw_dir)
            if video_path is not None:
                artifact_paths["video"] = video_path

        # 3. CC subtitle — best effort; many videos have none, which is not fatal.
        subtitle_path: Optional[Path] = None
        if download_subtitle:
            try:
                subtitle = await self.download_subtitle(bvid_or_url)
            except BBDownUnavailableError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Subtitle fetch during raw download failed: %s", exc)
                subtitle = None
            if subtitle is not None and subtitle.content:
                subtitle_path = raw_dir / f"{bvid}.{subtitle.language}.{subtitle.format.value}"
                subtitle_path.write_text(subtitle.content, encoding="utf-8")
                artifact_paths["subtitle"] = subtitle_path

        # 4. Source-info JSON (raw provenance for rebuilding the ContentRecord).
        source_info_path = raw_dir / f"{bvid}.source.json"
        source_info = {
            "bvid": info.bvid,
            "aid": info.aid,
            "title": info.title,
            "uploader": info.uploader,
            "uploader_id": info.uploader_id,
            "publish_time": info.publish_time.isoformat(),
            "duration": info.duration,
            "description": info.description,
            "cover_url": info.cover_url,
            "page_count": info.page_count,
            "tags": info.tags,
            "source_url": f"https://www.bilibili.com/video/{info.bvid}",
            "artifacts": {role: str(path) for role, path in artifact_paths.items()},
        }
        source_info_path.write_text(
            json.dumps(source_info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifact_paths["source_info"] = source_info_path

        return BilibiliRawArtifacts(
            bvid=bvid,
            info=info,
            raw_dir=raw_dir,
            source_info_path=source_info_path,
            audio_path=audio_path,
            video_path=video_path,
            subtitle_path=subtitle_path,
            artifact_paths=artifact_paths,
        )

    async def _download_video(
        self,
        bvid_or_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Download the raw video file (F0). No ASR; raw bytes only."""
        output_dir.mkdir(parents=True, exist_ok=True)
        bvid = self._extract_bvid(bvid_or_url)

        result = self._run_cli([
            bvid_or_url,
            "--skip-cover",
            "--skip-subtitle",
            "--skip-ai",
            "-F",
            "<bvid>",
            "--work-dir",
            str(output_dir),
            *self._cookie_args(),
        ])
        if result.returncode != 0:
            raise BBDownError(f"Video download failed: {self._combined_output(result).strip()}")

        for ext in [".mp4", ".mkv", ".flv", ".mov"]:
            files = list(output_dir.glob(f"*{bvid}*{ext}"))
            if files:
                return max(files, key=lambda p: p.stat().st_mtime)
        return None

    async def transcribe_video(
        self,
        bvid_or_url: str,
        prefer_subtitle: bool = True,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """Transcribe video using subtitle or ASR.

        Priority:
        1. Use CC subtitle if available (and prefer_subtitle=True)
        2. Fall back to MiMo ASR

        Returns:
            Transcript with segments and metadata
        """
        video_info = await self.get_video_info(bvid_or_url)
        bvid = video_info.bvid

        transcript_data = {
            "bvid": bvid,
            "title": video_info.title,
            "source": "unknown",
            "segments": [],
            "full_text": "",
            "duration_seconds": video_info.duration,
            "language": language,
        }

        # Try CC subtitle first
        if prefer_subtitle:
            subtitle = await self.download_subtitle(bvid_or_url, language)
            if subtitle and subtitle.segments:
                transcript_data["source"] = "cc_subtitle"
                transcript_data["segments"] = subtitle.segments
                transcript_data["full_text"] = " ".join(
                    seg.get("text", "") for seg in subtitle.segments
                )
                logger.info(f"Got transcript from CC subtitle for {bvid}")
                return transcript_data

        # Fall back to ASR
        if self.asr_client:
            logger.info(f"Downloading audio for ASR transcription: {bvid}")
            audio_path = await self.download_audio(bvid_or_url)
            if audio_path:
                try:
                    asr_result = await self.asr_client.transcribe(audio_path, language)
                    transcript_data["source"] = "mimo_asr"
                    transcript_data["segments"] = [s.to_dict() for s in asr_result.segments]
                    transcript_data["full_text"] = asr_result.full_text
                    transcript_data["duration_seconds"] = asr_result.duration_seconds
                    logger.info(f"Got transcript from ASR for {bvid}")
                    return transcript_data
                except Exception as e:
                    logger.error(f"ASR transcription failed: {e}")

        raise BBDownError(f"No transcript source available for {bvid}")


# Convenience functions
async def download_bilibili_audio(
    bvid_or_url: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Download audio from Bilibili video.

    Args:
        bvid_or_url: BV ID 或 B站 URL
        output_dir: 输出目录

    Returns:
        音频文件路径
    """
    config = BBDownConfig(
        download_dir=output_dir or Path("data/raw/bilibili/audio"),
    )
    adapter = BBDownAdapter(config)
    return await adapter.download_audio(bvid_or_url, output_dir)


async def transcribe_bilibili_video(
    bvid_or_url: str,
    prefer_subtitle: bool = True,
    language: str = "zh",
    asr_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Transcribe Bilibili video (F1-adjacent convenience helper).

    Cross-layer note (R-11): this download module is F0 and must NOT import the
    F1 ASR client (``finer.parsing.mimo_asr_client``). Transcription is an F1
    concern, so when the caller wants the ASR fallback it must inject an
    ``asr_client`` (the F1 caller owns building/wiring it). With no ``asr_client``
    only the CC-subtitle path is available; if a video has no subtitle the
    underlying adapter raises, surfacing the missing F1 dependency to the caller
    rather than reaching across the F0/F1 boundary here.

    Args:
        bvid_or_url: BV ID 或 B站 URL
        prefer_subtitle: 优先使用 CC 字幕
        language: 语言
        asr_client: F1-owned ASR client (e.g. MiMoASRClient), injected by caller.

    Returns:
        转录结果
    """
    config = BBDownConfig()
    adapter = BBDownAdapter(config, asr_client)
    return await adapter.transcribe_video(bvid_or_url, prefer_subtitle, language)
