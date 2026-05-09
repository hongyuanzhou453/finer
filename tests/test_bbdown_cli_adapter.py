"""Tests for BBDown CLI-backed adapter behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from finer.ingestion.bbdown_client import BBDownAdapter, BBDownConfig


def _completed(args: list[str], stdout: str = "", stderr: str = "", code: int = 0):
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=stdout, stderr=stderr)


def test_cli_env_adds_dotnet_tools_and_cookie(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    env = BBDownAdapter._cli_env("cookie-value")

    assert str(Path.home() / ".dotnet" / "tools") in env["PATH"]
    assert "/opt/homebrew/bin" in env["PATH"]
    assert env["BBDOWN_COOKIE"] == "cookie-value"


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [
        ("11m58s", 718),
        ("37m33s", 2253),
        ("1h02m03s", 3723),
        ("02:03", 123),
        ("01:02:03", 3723),
        ("bad", 0),
    ],
)
def test_parse_duration(raw, seconds):
    assert BBDownAdapter._parse_duration(raw) == seconds


@pytest.mark.anyio
async def test_get_video_info_uses_cli_info_and_parses_output(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    output = """
BBDown version 1.6.3, Bilibili Downloader.
[2026-05-09 19:20:44.550] - 获取aid结束: 116491760572977
[2026-05-09 19:20:44.742] - 视频标题: 【硬核】提前退休计划
[2026-05-09 19:20:44.742] - 发布时间: 2026-04-30 12:29:30 +08:00
[2026-05-09 19:20:44.742] - UP主页: https://space.bilibili.com/315846984
[2026-05-09 19:20:44.742] - P1: [37936435113] [【硬核】提前退休计划] [37m33s]
[2026-05-09 19:20:44.745] - 共计 1 个分P, 已选择：ALL
"""

    def fake_run(args, **kwargs):
        calls.append(args)
        return _completed(args, stdout=output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = BBDownAdapter(BBDownConfig(download_dir=tmp_path, cookie="configured-cookie"))

    info = await adapter.get_video_info("BV1Vb9hBVE4C")

    assert info.bvid == "BV1Vb9hBVE4C"
    assert info.aid == 116491760572977
    assert info.uploader_id == 315846984
    assert info.publish_time.year == 2026
    assert info.duration == 2253
    assert info.page_count == 1
    assert "--only-show-info" in calls[0]
    assert "--info-only" not in calls[0]
    assert "-c" in calls[0]
    assert "configured-cookie" in calls[0]


@pytest.mark.anyio
async def test_download_audio_uses_cli_audio_only(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        work_dir = Path(args[args.index("--work-dir") + 1])
        (work_dir / "BV1audioTest.m4a").write_text("audio", encoding="utf-8")
        return _completed(args)

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = BBDownAdapter(BBDownConfig(download_dir=tmp_path, cookie="configured-cookie"))

    audio_path = await adapter.download_audio("BV1audioTest")

    assert audio_path == tmp_path / "BV1audioTest.m4a"
    assert "--audio-only" in calls[0]
    assert "--skip-subtitle" in calls[0]
    assert "-c" in calls[0]


@pytest.mark.anyio
async def test_download_subtitle_searches_title_named_files(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    info_output = """
[2026-05-09 19:20:44.550] - 获取aid结束: 1
[2026-05-09 19:20:44.742] - 视频标题: 标题命名字幕
[2026-05-09 19:20:44.742] - 发布时间: 2026-04-30 12:29:30 +08:00
[2026-05-09 19:20:44.742] - UP主页: https://space.bilibili.com/2
[2026-05-09 19:20:44.742] - P1: [3] [标题命名字幕] [11m58s]
"""

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--sub-only" in args:
            (tmp_path / "标题命名字幕.zh-CN.json").write_text(
                '{"body":[{"from":1.0,"to":2.0,"content":"hello"}]}',
                encoding="utf-8",
            )
            return _completed(args)
        return _completed(args, stdout=info_output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = BBDownAdapter(BBDownConfig(download_dir=tmp_path))

    subtitle = await adapter.download_subtitle("BV1subtitle")

    assert subtitle is not None
    assert subtitle.segments == [{"start_time": 1.0, "end_time": 2.0, "text": "hello"}]
    sub_call = next(call for call in calls if "--sub-only" in call)
    assert "--skip-ai=false" in sub_call


@pytest.mark.anyio
async def test_transcribe_video_uses_subtitle_before_asr(monkeypatch, tmp_path):
    adapter = BBDownAdapter(BBDownConfig(download_dir=tmp_path))

    async def fake_get_video_info(_):
        return type(
            "Info",
            (),
            {
                "bvid": "BV1fake",
                "title": "T",
                "duration": 1,
            },
        )()

    async def fake_download_subtitle(*_args, **_kwargs):
        from finer.schemas.bbdown import BBDownSubtitle, SubtitleFormat

        return BBDownSubtitle(
            language="zh",
            format=SubtitleFormat.JSON,
            content="{}",
            segments=[{"start_time": 0, "end_time": 1, "text": "字幕优先"}],
        )

    monkeypatch.setattr(adapter, "get_video_info", fake_get_video_info)
    monkeypatch.setattr(adapter, "download_subtitle", fake_download_subtitle)

    result = await adapter.transcribe_video("BV1fake", prefer_subtitle=True)

    assert result["source"] == "cc_subtitle"
    assert result["full_text"] == "字幕优先"
