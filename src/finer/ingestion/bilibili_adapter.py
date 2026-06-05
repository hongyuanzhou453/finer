"""Bilibili Adapter — Download and transcribe B站 videos.

Provides video info fetching, audio download, and transcription
using Alibaba Cloud Paraformer model via DashScope API.

Architecture:
- Video info: Direct API call to B站
- Audio download: HTTP download with session handling
- Transcription: Paraformer-ASR via DashScope
- Output: Markdown with timestamps

References:
- BBDown: https://github.com/nilaoda/BBDown
- zhiziX: https://github.com/zhiziX/zhiziX
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class BilibiliVideoInfo:
    """Video metadata from B站."""
    bvid: str
    title: str
    uploader: str
    uploader_id: int
    publish_time: datetime
    duration: int  # seconds
    description: str
    cover_url: str
    aid: int = 0
    page_count: int = 1
    tags: list[str] = field(default_factory=list)


@dataclass
class TranscriptSegment:
    """Single transcript segment with timestamp."""
    start_time: float  # seconds
    end_time: float  # seconds
    text: str

    def format_timestamp(self, seconds: float) -> str:
        """Format seconds to [HH:MM:SS] format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"

    def to_markdown(self) -> str:
        """Format as markdown line."""
        return f"{self.format_timestamp(self.start_time)} {self.text}"


@dataclass
class TranscriptResult:
    """Complete transcript result."""
    video_info: BilibiliVideoInfo
    segments: list[TranscriptSegment]
    full_text: str
    model: str
    duration_seconds: float

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [
            f"# 视频转录: {self.video_info.title}",
            f"- UP主: {self.video_info.uploader}",
            f"- 发布时间: {self.video_info.publish_time.strftime('%Y-%m-%d %H:%M')}",
            f"- BV号: {self.video_info.bvid}",
            f"- 时长: {self.duration_seconds:.1f}秒",
            f"- 转录模型: {self.model}",
            "",
            "## 转录内容",
            "",
        ]

        for segment in self.segments:
            lines.append(segment.to_markdown())

        return "\n".join(lines)


class BilibiliClient:
    """Client for B站 API."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com",
        }
        self.timeout = 30.0

    def parse_bvid(self, url_or_bvid: str) -> str:
        """Extract BV ID from URL or return as-is."""
        # Already a BV ID
        if url_or_bvid.startswith("BV"):
            return url_or_bvid

        # Extract from URL patterns
        patterns = [
            r"bilibili\.com/video/(BV[a-zA-Z0-9]+)",
            r"b23\.tv/(BV[a-zA-Z0-9]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url_or_bvid)
            if match:
                return match.group(1)

        raise ValueError(f"Cannot parse BV ID from: {url_or_bvid}")

    def search_videos(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Search Bilibili videos by keyword.

        Placeholder implementation — returns empty results until
        a real search API integration is wired up.

        Args:
            keyword: Search keyword
            page: Page number (1-based)
            page_size: Results per page

        Returns:
            Dict with keys: videos, total, page, page_size
        """
        return {
            "videos": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }

    def get_video_info(self, bvid: str) -> BilibiliVideoInfo:
        """Fetch video metadata from B站 API."""
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            raise ValueError(f"B站 API error: {data.get('message', 'Unknown error')}")

        info = data["data"]

        return BilibiliVideoInfo(
            bvid=bvid,
            title=info["title"],
            uploader=info["owner"]["name"],
            uploader_id=info["owner"]["mid"],
            publish_time=datetime.fromtimestamp(info["pubdate"]),
            duration=info["duration"],
            description=info["desc"],
            cover_url=info["pic"],
            aid=info.get("aid", 0),
            page_count=info.get("videos", 1),
            tags=[tag.get("tag_name", "") for tag in info.get("tag", []) if isinstance(tag, dict)],
        )

    def get_audio_url(self, bvid: str, cid: Optional[int] = None) -> tuple[str, int]:
        """Get audio stream URL and size.

        Returns:
            Tuple of (audio_url, file_size_bytes)
        """
        # First get video info to find cid
        info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(info_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                raise ValueError(f"B站 API error: {data.get('message')}")

            if cid is None:
                cid = data["data"]["cid"]

            # Get audio stream URL (quality 30280 = 128kbps audio)
            play_url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=16&fnver=0&fnval=16&fourk=1"
            response = client.get(play_url, headers=self.headers)
            response.raise_for_status()
            play_data = response.json()

            if play_data.get("code") != 0:
                raise ValueError(f"Failed to get play URL: {play_data.get('message')}")

            # Extract audio URL from dash format
            dash = play_data["data"].get("dash", {})
            audio_streams = dash.get("audio", [])

            if not audio_streams:
                # Fallback to durl format
                durl = play_data["data"].get("durl", [])
                if durl:
                    return durl[0]["url"], durl[0].get("size", 0)
                raise ValueError("No audio stream found")

            # Select highest quality audio
            audio_streams.sort(key=lambda x: x.get("id", 0), reverse=True)
            audio_url = audio_streams[0]["baseUrl"]
            file_size = audio_streams[0].get("size", 0)

            return audio_url, file_size

    def download_audio(
        self,
        bvid: str,
        output_dir: Path,
        cid: Optional[int] = None,
    ) -> Path:
        """Download audio file from B站.

        Returns:
            Path to downloaded audio file (m4s format)
        """
        audio_url, expected_size = self.get_audio_url(bvid, cid)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{bvid}.m4s"

        # Download with progress
        headers = {
            **self.headers,
            "Range": "bytes=0-",  # Support resume
        }

        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            with client.stream("GET", audio_url, headers=headers) as response:
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", expected_size))
                downloaded = 0
                last_logged_mb = 0

                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = downloaded / total_size * 100
                            current_mb = int(downloaded / 1024 / 1024)
                            if current_mb > last_logged_mb:
                                logger.info(f"Downloaded {downloaded / 1024 / 1024:.1f}MB ({progress:.1f}%)")
                                last_logged_mb = current_mb

        logger.info(f"Audio downloaded to {output_path}")
        return output_path


class ParaformerTranscriber:
    """Audio transcriber using Alibaba Cloud Paraformer model.

    Uses DashScope API for transcription.
    Supports long audio with automatic segmentation.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY not found")

        self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
        self.model = "paraformer-realtime-v2"  # or "paraformer-v2" for offline

    def transcribe_file(
        self,
        audio_path: Path,
        language: str = "zh",
    ) -> list[TranscriptSegment]:
        """Transcribe audio file with timestamps.

        Args:
            audio_path: Path to audio file (m4s, wav, mp3, etc.)
            language: Language code (zh, en, etc.)

        Returns:
            List of transcript segments with timestamps
        """
        # Check file size - Paraformer has limits
        file_size_mb = audio_path.stat().st_size / 1024 / 1024

        if file_size_mb > 500:  # 500MB limit
            raise ValueError(f"Audio file too large: {file_size_mb:.1f}MB (max 500MB)")

        # Use file URL transcription for files > 10MB
        if file_size_mb > 10:
            return self._transcribe_large_file(audio_path, language)
        else:
            return self._transcribe_small_file(audio_path, language)

    def _transcribe_small_file(
        self,
        audio_path: Path,
        language: str,
    ) -> list[TranscriptSegment]:
        """Transcribe small file (< 10MB) with base64 upload."""
        import base64

        # Read and encode audio
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Determine content type
        suffix = audio_path.suffix.lower()
        content_type_map = {
            ".m4s": "audio/mp4",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
        }
        content_type = content_type_map.get(suffix, "audio/mp4")

        # Call API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "input": {
                "audio": f"data:{content_type};base64,{audio_base64}",
            },
            "parameters": {
                "language": language,
                "format": "timestamp",  # Request timestamps
            },
        }

        with httpx.Client(timeout=300.0) as client:
            response = client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

        return self._parse_transcription_result(result)

    def _transcribe_large_file(
        self,
        audio_path: Path,
        language: str,
    ) -> list[TranscriptSegment]:
        """Transcribe large file using file URL.

        For large files, we need to:
        1. Upload to temporary storage (or use OSS)
        2. Submit transcription task
        3. Poll for completion
        """
        # For now, split into segments
        # TODO: Implement proper file URL transcription with OSS upload
        logger.warning(f"Large file ({audio_path.stat().st_size / 1024 / 1024:.1f}MB), splitting into segments")

        segments = self._split_and_transcribe(audio_path, language)
        return segments

    def _split_and_transcribe(
        self,
        audio_path: Path,
        language: str,
        segment_duration: int = 300,  # 5 minutes
    ) -> list[TranscriptSegment]:
        """Split audio and transcribe in segments.

        Requires ffmpeg for splitting.
        """
        import subprocess

        # Get duration using ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]

        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffprobe failed: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                "ffprobe not found. Please install ffmpeg: "
                "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
            )

        total_duration = float(result.stdout.strip())
        logger.info(f"Audio duration: {total_duration:.1f}s")

        # Split and transcribe
        all_segments = []
        temp_dir = tempfile.mkdtemp(prefix="bilibili_transcribe_")

        try:
            num_segments = int(total_duration // segment_duration) + 1

            for i in range(num_segments):
                start_time = i * segment_duration
                segment_path = Path(temp_dir) / f"segment_{i}.m4a"

                # Extract segment using ffmpeg
                split_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", str(audio_path),
                    "-t", str(segment_duration),
                    "-c:a", "copy",
                    str(segment_path),
                ]

                subprocess.run(split_cmd, capture_output=True, check=True)

                if not segment_path.exists() or segment_path.stat().st_size == 0:
                    continue

                # Transcribe segment
                logger.info(f"Transcribing segment {i+1}/{num_segments}")
                segment_transcripts = self._transcribe_small_file(segment_path, language)

                # Adjust timestamps
                for seg in segment_transcripts:
                    seg.start_time += start_time
                    seg.end_time += start_time
                    all_segments.append(seg)

        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        return all_segments

    def _parse_transcription_result(self, result: dict) -> list[TranscriptSegment]:
        """Parse DashScope transcription result."""
        segments = []

        output = result.get("output", {})
        results = output.get("results", [])

        for item in results:
            text = item.get("transcription_text", "")
            begin_time = item.get("begin_time", 0) / 1000  # ms to seconds
            end_time = item.get("end_time", 0) / 1000

            if text.strip():
                segments.append(TranscriptSegment(
                    start_time=begin_time,
                    end_time=end_time,
                    text=text.strip(),
                ))

        # If no timestamp results, create single segment from full text
        if not segments:
            full_text = output.get("text", "")
            if full_text:
                segments.append(TranscriptSegment(
                    start_time=0.0,
                    end_time=0.0,
                    text=full_text,
                ))

        return segments


class BilibiliAdapter:
    """Main adapter for B站 video download and transcription.

    F0 scope (R-09): constructing this adapter is a pure F0 operation — it only
    wires up the B站 metadata/download client and never requires a transcription
    credential. The Paraformer transcriber (DashScope-backed) is F1-adjacent and
    is built lazily the first time :meth:`transcribe` runs, so a missing
    ``DASHSCOPE_API_KEY`` can no longer crash F0 intake at construction time.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ):
        self.client = BilibiliClient()
        # Defer the DASHSCOPE_API_KEY requirement to transcribe time (F1-adjacent),
        # so F0 download/import paths never crash just because ASR is unconfigured.
        self._api_key = api_key
        self._transcriber: Optional[ParaformerTranscriber] = None
        self.output_dir = output_dir or Path("data/raw/bilibili")

    @property
    def transcriber(self) -> ParaformerTranscriber:
        """Lazily build the Paraformer transcriber (requires DASHSCOPE_API_KEY).

        Accessing this property is F1-adjacent: it is the point where the
        DashScope credential is actually required. F0 download/import code paths
        must not touch it.
        """
        if self._transcriber is None:
            self._transcriber = ParaformerTranscriber(self._api_key)
        return self._transcriber

    def get_video_info(self, bvid_or_url: str) -> BilibiliVideoInfo:
        """Get video information."""
        bvid = self.client.parse_bvid(bvid_or_url)
        return self.client.get_video_info(bvid)

    def download_audio(
        self,
        bvid_or_url: str,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """Download audio from video."""
        bvid = self.client.parse_bvid(bvid_or_url)
        output = output_dir or self.output_dir / "audio"
        return self.client.download_audio(bvid, output)

    def transcribe(
        self,
        bvid_or_url: str,
        audio_path: Optional[Path] = None,
        language: str = "zh",
    ) -> TranscriptResult:
        """Download and transcribe video.

        Args:
            bvid_or_url: BV ID or URL
            audio_path: Optional existing audio file
            language: Language for transcription

        Returns:
            TranscriptResult with segments and metadata
        """
        bvid = self.client.parse_bvid(bvid_or_url)

        # Get video info
        video_info = self.client.get_video_info(bvid)

        # Download audio if not provided
        if audio_path is None:
            audio_path = self.download_audio(bvid)

        # Transcribe
        logger.info(f"Transcribing {bvid}...")
        segments = self.transcriber.transcribe_file(audio_path, language)

        # Build full text
        full_text = " ".join(seg.text for seg in segments)

        return TranscriptResult(
            video_info=video_info,
            segments=segments,
            full_text=full_text,
            model=self.transcriber.model,
            duration_seconds=video_info.duration,
        )

    def save_transcript(
        self,
        result: TranscriptResult,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """Save transcript to markdown file.

        Returns:
            Path to saved markdown file
        """
        output = output_dir or self.output_dir / str(result.video_info.uploader_id)
        output.mkdir(parents=True, exist_ok=True)

        filename = f"{result.video_info.bvid}_transcript.md"
        output_path = output / filename

        markdown_content = result.to_markdown()
        output_path.write_text(markdown_content, encoding="utf-8")

        logger.info(f"Transcript saved to {output_path}")
        return output_path

    def save_metadata(
        self,
        result: TranscriptResult,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """Save metadata to JSON file."""
        output = output_dir or self.output_dir / str(result.video_info.uploader_id)
        output.mkdir(parents=True, exist_ok=True)

        filename = f"{result.video_info.bvid}_metadata.json"
        output_path = output / filename

        metadata = {
            "bvid": result.video_info.bvid,
            "aid": result.video_info.aid,
            "title": result.video_info.title,
            "uploader": result.video_info.uploader,
            "uploader_id": result.video_info.uploader_id,
            "publish_time": result.video_info.publish_time.isoformat(),
            "duration": result.video_info.duration,
            "description": result.video_info.description,
            "cover_url": result.video_info.cover_url,
            "tags": result.video_info.tags,
            "transcription": {
                "model": result.model,
                "segments_count": len(result.segments),
                "full_text_length": len(result.full_text),
                "transcribed_at": datetime.now().isoformat(),
            },
        }

        output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"Metadata saved to {output_path}")
        return output_path


# Convenience functions

def transcribe_bilibili_video(
    url_or_bvid: str,
    output_dir: Optional[Path] = None,
    language: str = "zh",
    api_key: Optional[str] = None,
) -> tuple[Path, Path]:
    """Download and transcribe a B站 video.

    Args:
        url_or_bvid: BV ID or B站 URL
        output_dir: Output directory
        language: Transcription language
        api_key: DashScope API key

    Returns:
        Tuple of (transcript_path, metadata_path)
    """
    adapter = BilibiliAdapter(api_key=api_key, output_dir=output_dir)

    # Transcribe
    result = adapter.transcribe(url_or_bvid, language=language)

    # Save outputs
    transcript_path = adapter.save_transcript(result)
    metadata_path = adapter.save_metadata(result)

    return transcript_path, metadata_path
