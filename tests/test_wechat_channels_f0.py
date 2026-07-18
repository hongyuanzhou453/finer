"""Tests for WeChat Channels F0 import."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from finer.ingestion.wechat_channels_adapter import (
    WECHAT_CHANNELS_SOURCE_KIND,
    WeChatChannelsDownloadClient,
    WeChatChannelsF0Importer,
)
from finer.schemas.content import ContentRecord


def _profile_payload() -> dict:
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "errCode": 0,
            "errMsg": "ok",
            "data": {
                "object": {
                    "id": "14819096805414996657",
                    "contact": {
                        "username": "v2_test_finder@finder",
                        "nickname": "Test Creator",
                    },
                    "objectDesc": {
                        "description": "Market view short video",
                        "media": [
                            {
                                "url": "https://finder.video.qq.com/test.mp4",
                                "mediaType": 4,
                                "videoPlayLen": 41,
                                "width": 1080,
                                "height": 1440,
                                "fileSize": 12,
                                "decodeKey": "123456",
                                "coverUrl": "https://example.com/cover.jpg",
                                "spec": [{"fileFormat": "xWT111"}],
                            }
                        ],
                    },
                    "objectNonceId": "nonce_001",
                    "source_url": "",
                    "createtime": 1700000000,
                },
                "commentCount": 7,
            },
        },
    }


def test_wechat_channels_importer_writes_f0_artifacts(tmp_path: Path) -> None:
    video = tmp_path / "downloaded.mp4"
    video.write_bytes(b"video-bytes")
    importer = WeChatChannelsF0Importer(
        root=tmp_path,
        client=WeChatChannelsDownloadClient(),
    )

    result = importer.import_video(
        url="https://weixin.qq.com/sph/test",
        video_file_path=video,
        profile_payload=_profile_payload(),
    )

    assert result.status == "imported"
    assert result.artifacts.raw_video_path.exists()
    assert result.artifacts.raw_profile_path.exists()
    assert result.record_path.exists()
    assert result.receipt_path.exists()
    assert "data/raw/wechat/channels" in str(result.artifacts.raw_video_path)
    assert "data/F0_intake/wechat/channels" in str(result.record_path)

    record = ContentRecord.model_validate_json(result.record_path.read_text(encoding="utf-8"))
    assert record.file_type == "video"
    assert record.source_platform == "wechat"
    assert record.source_type == "wechat_channels_video"
    assert record.external_source_id == "14819096805414996657"
    assert record.metadata["source_kind"] == WECHAT_CHANNELS_SOURCE_KIND
    assert record.metadata["raw_video_sha256"] == result.artifacts.video_sha256
    assert record.metadata["raw_profile_path"] == str(result.artifacts.raw_profile_path)

    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert receipt["stage"] == "F0"
    assert receipt["source_channel"] == "wechat_channels"
    assert receipt["source_kind"] == WECHAT_CHANNELS_SOURCE_KIND
    assert receipt["content_id"] == record.content_id
    assert receipt["status"] == "completed"
    assert receipt["records_created"] == 1
    assert "video" in receipt["raw_sha256"]
    assert "profile" in receipt["raw_sha256"]
    assert "video" in receipt["raw_paths"]
    assert "profile" in receipt["raw_paths"]


def test_wechat_channels_importer_is_idempotent(tmp_path: Path) -> None:
    video = tmp_path / "downloaded.mp4"
    video.write_bytes(b"video-bytes")
    importer = WeChatChannelsF0Importer(
        root=tmp_path,
        client=WeChatChannelsDownloadClient(),
    )

    first = importer.import_video(
        url="https://weixin.qq.com/sph/test",
        video_file_path=video,
        profile_payload=_profile_payload(),
    )
    second = importer.import_video(
        url="https://weixin.qq.com/sph/test",
        video_file_path=video,
        profile_payload=_profile_payload(),
    )

    assert second.status == "already_imported"
    assert second.content_record.content_id == first.content_record.content_id
    assert second.record_path == first.record_path

    # Receipt must also be written for the already_imported path.
    assert second.receipt_path.exists()
    receipt = json.loads(second.receipt_path.read_text(encoding="utf-8"))
    assert receipt["source_channel"] == "wechat_channels"
    assert receipt["status"] == "skipped"
    assert receipt["records_created"] == 0


def test_wechat_channels_import_route(tmp_path: Path) -> None:
    from finer.api.routes import wechat
    from finer.api.server import app

    video = tmp_path / "downloaded.mp4"
    video.write_bytes(b"video-bytes")

    # Isolate PM registration: F0IndexWriter() binds to the LIVE project DB, and
    # REPO_ROOT is patched to tmp (so the ContentRecord file lands in tmp). Without
    # this patch the route writes stage_status F0='ready' for this /sph/test record
    # into the real DB; when tmp is torn down the record file vanishes, leaving an
    # orphan (ready + no ContentRecord) recreated on every run. PM registration is
    # covered by test_wechat_channels_import_registers_pm.
    with patch.object(wechat, "REPO_ROOT", tmp_path), patch(
        "finer.ingestion.wechat_channels_adapter.WeChatChannelsDownloadClient.get_feed_profile",
        return_value=_profile_payload(),
    ), patch("finer.api.routes.wechat._register_f0_index"):
        client = TestClient(app)
        resp = client.post(
            "/api/wechat/channels/import",
            json={
                "url": "https://weixin.qq.com/sph/test",
                "video_file_path": str(video),
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "imported"
    assert data["content_record"]["file_type"] == "video"
    assert data["content_record"]["metadata"]["source_kind"] == WECHAT_CHANNELS_SOURCE_KIND
    assert Path(data["record_path"]).exists()
    assert Path(data["receipt_path"]).exists()
    # Receipt in response must be a canonical ImportReceipt dump.
    assert data["receipt"]["source_channel"] == "wechat_channels"
    assert data["receipt"]["status"] == "completed"


def test_wechat_channels_import_registers_pm(tmp_path: Path) -> None:
    """Channels import route must register PM (best-effort) via _register_f0_index."""
    from finer.api.routes import wechat
    from finer.api.server import app

    video = tmp_path / "downloaded.mp4"
    video.write_bytes(b"video-bytes")

    with patch.object(wechat, "REPO_ROOT", tmp_path), patch(
        "finer.ingestion.wechat_channels_adapter.WeChatChannelsDownloadClient.get_feed_profile",
        return_value=_profile_payload(),
    ), patch("finer.api.routes.wechat._register_f0_index") as mock_register:
        client = TestClient(app)
        resp = client.post(
            "/api/wechat/channels/import",
            json={
                "url": "https://weixin.qq.com/sph/test",
                "video_file_path": str(video),
            },
        )

    assert resp.status_code == 200
    assert mock_register.call_count == 1
    # First arg is ContentRecord, second is ImportReceipt.
    call_args = mock_register.call_args
    from finer.schemas.content import ContentRecord as CR
    from finer.schemas.import_receipt import ImportReceipt as IR
    assert isinstance(call_args[0][0], CR)
    assert isinstance(call_args[0][1], IR)


def test_wechat_channels_import_route_requires_video_or_download() -> None:
    from finer.api.server import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/wechat/channels/import",
        json={"url": "https://weixin.qq.com/sph/test"},
    )

    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "F0_IN_001"
    assert data["error"]["details"]["stage"] == "F0"
    assert data["error"]["details"]["source_channel"] == "wechat"


# --- R-07: binary external-install resolution order ---


class TestBinaryExternalInstall:
    """resolve_wx_channels_download_bin must honor PATH > env > config > vendored."""

    def test_path_install_wins(self, tmp_path: Path) -> None:
        import os
        from finer.ingestion.wechat_channels_adapter import (
            WX_CHANNELS_DOWNLOAD_BIN_ENV,
            resolve_wx_channels_download_bin,
        )

        with patch(
            "finer.ingestion.wechat_channels_adapter.shutil.which",
            return_value="/usr/local/bin/wx_video_download",
        ), patch.dict(os.environ, {WX_CHANNELS_DOWNLOAD_BIN_ENV: "/env/wx_video_download"}):
            resolved = resolve_wx_channels_download_bin(tmp_path)
        assert resolved == Path("/usr/local/bin/wx_video_download")

    def test_env_override_used_when_not_on_path(self, tmp_path: Path) -> None:
        import os
        from finer.ingestion.wechat_channels_adapter import (
            WX_CHANNELS_DOWNLOAD_BIN_ENV,
            resolve_wx_channels_download_bin,
        )

        with patch("finer.ingestion.wechat_channels_adapter.shutil.which", return_value=None), patch.dict(
            os.environ, {WX_CHANNELS_DOWNLOAD_BIN_ENV: "/opt/wx/wx_video_download"}
        ):
            resolved = resolve_wx_channels_download_bin(tmp_path)
        assert resolved == Path("/opt/wx/wx_video_download")

    def test_vendored_is_last_resort(self, tmp_path: Path) -> None:
        import os
        from finer.ingestion.wechat_channels_adapter import resolve_wx_channels_download_bin

        vendored = tmp_path / "scripts" / "wx_channels_download" / "wx_video_download"
        vendored.parent.mkdir(parents=True)
        vendored.write_text("#!/bin/sh\n")

        env = {k: v for k, v in os.environ.items()}
        env.pop("WX_CHANNELS_DOWNLOAD_BIN", None)
        with patch("finer.ingestion.wechat_channels_adapter.shutil.which", return_value=None), patch.dict(
            os.environ, env, clear=True
        ):
            resolved = resolve_wx_channels_download_bin(tmp_path)
        assert resolved == vendored

    def test_returns_none_when_nothing_found(self, tmp_path: Path) -> None:
        import os
        from finer.ingestion.wechat_channels_adapter import resolve_wx_channels_download_bin

        env = {k: v for k, v in os.environ.items()}
        env.pop("WX_CHANNELS_DOWNLOAD_BIN", None)
        with patch("finer.ingestion.wechat_channels_adapter.shutil.which", return_value=None), patch.dict(
            os.environ, env, clear=True
        ):
            resolved = resolve_wx_channels_download_bin(tmp_path)
        assert resolved is None

    def test_missing_binary_download_raises_unavailable(self, tmp_path: Path) -> None:
        """A download with no resolvable binary is an external dep failure."""
        from finer.ingestion.wechat_channels_adapter import (
            WeChatChannelsDownloadClient,
            WeChatChannelsDownloaderUnavailable,
        )

        client = WeChatChannelsDownloadClient(downloader_bin=None)
        with pytest.raises(WeChatChannelsDownloaderUnavailable):
            client.download_media(media_url="https://x/y.mp4", decode_key=None, filename="y.mp4")


def test_channels_import_missing_binary_maps_to_f0_ext_001(tmp_path: Path) -> None:
    """R-08: downloader-unavailable (binary missing) -> retryable F0_EXT_001, not F0_IN_001."""
    import os
    from finer.api.routes import wechat
    from finer.api.server import app

    env = {k: v for k, v in os.environ.items()}
    env.pop("WX_CHANNELS_DOWNLOAD_BIN", None)

    with patch.object(wechat, "REPO_ROOT", tmp_path), patch(
        "finer.ingestion.wechat_channels_adapter.WeChatChannelsDownloadClient.get_feed_profile",
        return_value=_profile_payload(),
    ), patch("finer.ingestion.wechat_channels_adapter.shutil.which", return_value=None), patch.dict(
        os.environ, env, clear=True
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/wechat/channels/import",
            json={"url": "https://weixin.qq.com/sph/test", "download": True},
        )

    assert resp.status_code == 502
    data = resp.json()
    assert data["error"]["code"] == "F0_EXT_001"
    assert data["error"]["details"]["retryable"] is True
    assert data["error"]["details"]["source_channel"] == "wechat"


# --- R-06: exporter base URL single source of truth ---


def test_exporter_base_url_single_source_of_truth() -> None:
    """config default, YAML, and the exporter client must agree on one port."""
    from finer.config import WeChatServiceConfig, load_wechat_service_config
    from finer.ingestion.wechat_exporter_client import WeChatExporterClient
    from finer.paths import REPO_ROOT

    configured = load_wechat_service_config(REPO_ROOT).exporter_url
    # The dataclass default must match the YAML truth (no port disagreement).
    assert WeChatServiceConfig.exporter_url == configured
    # A client constructed without an explicit base_url resolves from config.
    assert WeChatExporterClient().base_url == configured.rstrip("/")


# --- R-21: simulated login must be gone ---


def test_no_simulated_login_in_adapter() -> None:
    """The debug _test_poll_count simulated-login path must not exist."""
    import inspect
    from finer.ingestion import wechat_mp_adapter

    source = inspect.getsource(wechat_mp_adapter)
    assert "_test_poll_count" not in source
    assert "Simulated login" not in source
    assert "测试公众号" not in source
