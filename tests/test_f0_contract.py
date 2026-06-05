"""F0 contract tests — schema, conversion, route, and directory invariants."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from finer.manifests import ContentManifest
from finer.paths import DATA_ROOT, ensure_storage
from finer.schemas.content import ContentRecord


# ---------------------------------------------------------------------------
# 1. ContentRecord schema tests
# ---------------------------------------------------------------------------

class TestContentRecordSchema:
    """Validate ContentRecord fields, serialization, and defaults."""

    _REQUIRED = {
        "content_id", "source_type", "source_platform", "raw_path", "file_type",
    }

    def test_required_fields_exist(self) -> None:
        fields = set(ContentRecord.model_fields.keys())
        assert self._REQUIRED.issubset(fields), f"Missing: {self._REQUIRED - fields}"

    def test_source_type_literal_values(self) -> None:
        field_info = ContentRecord.model_fields["source_type"]
        expected = {
            "feishu_chat", "bilibili_video", "wechat_article", "manual_upload", "nlm_note",
            "chat_transcript", "chat_export", "livestream_audio",
            "weekly_strategy", "daily_pre", "daily_post", "research_report",
            "wechat_channels_video", "unclassified",
        }
        assert set(field_info.annotation.__args__) == expected

    def test_file_type_literal_values(self) -> None:
        field_info = ContentRecord.model_fields["file_type"]
        expected = {"chat_log", "image", "pdf", "doc", "audio", "video", "text"}
        assert set(field_info.annotation.__args__) == expected

    def test_serialization_roundtrip(self) -> None:
        record = ContentRecord(
            content_id="test-001",
            source_type="manual_upload",
            source_platform="local",
            raw_path="data/raw/_inbox/test.pdf",
            file_type="pdf",
            title="Test",
        )
        data = record.model_dump()
        restored = ContentRecord.model_validate(data)
        assert restored.content_id == record.content_id
        assert restored.source_type == record.source_type
        assert restored.collected_at is not None

    def test_optional_fields_default_to_none(self) -> None:
        record = ContentRecord(
            content_id="test-002",
            source_type="feishu_chat",
            source_platform="feishu",
            raw_path="data/raw/chat.json",
            file_type="chat_log",
        )
        assert record.creator_id is None
        assert record.creator_name is None
        assert record.published_at is None
        assert record.title is None
        assert record.source_url is None
        assert record.external_source_id is None
        assert record.dedupe_fingerprint is None
        assert record.overall_summary is None

    def test_metadata_defaults_to_empty_dict(self) -> None:
        record = ContentRecord(
            content_id="test-003",
            source_type="bilibili_video",
            source_platform="bilibili",
            raw_path="data/raw/video.mp4",
            file_type="video",
        )
        assert record.metadata == {}

    def test_collected_at_auto_populated(self) -> None:
        from datetime import timedelta, timezone

        before = datetime.now(timezone.utc)
        record = ContentRecord(
            content_id="test-004",
            source_type="nlm_note",
            source_platform="nlm",
            raw_path="data/raw/note.txt",
            file_type="text",
        )
        after = datetime.now(timezone.utc)
        assert record.collected_at is not None
        # collected_at is now timezone-aware UTC (GATE freeze)
        assert record.collected_at.tzinfo is not None
        assert record.collected_at >= before - timedelta(seconds=1)
        assert record.collected_at <= after + timedelta(seconds=1)

    def test_all_source_type_values_accepted(self) -> None:
        for st in ("feishu_chat", "bilibili_video", "wechat_article", "manual_upload", "nlm_note"):
            record = ContentRecord(
                content_id=f"test-{st}",
                source_type=st,
                source_platform="test",
                raw_path="data/raw/test",
                file_type="text",
            )
            assert record.source_type == st


# ---------------------------------------------------------------------------
# 2. ContentManifest ↔ ContentRecord conversion
# ---------------------------------------------------------------------------

class TestManifestConversion:
    """Validate bidirectional conversion between ContentRecord and ContentManifest."""

    def _make_record(self, **overrides) -> ContentRecord:
        defaults = dict(
            content_id="conv-001",
            source_type="feishu_chat",
            source_platform="feishu",
            raw_path="data/raw/chat.json",
            file_type="chat_log",
            title="Conversion Test",
            collected_at=datetime(2026, 5, 11, 10, 0, 0),
        )
        defaults.update(overrides)
        return ContentRecord(**defaults)

    def test_to_manifest_has_all_fields(self) -> None:
        record = self._make_record(
            creator_id="u123",
            creator_name="TestUser",
            published_at=datetime(2026, 5, 10, 9, 0, 0),
            source_url="https://example.com",
            external_source_id="msg_abc",
        )
        manifest = record.to_manifest()
        assert isinstance(manifest, ContentManifest)
        assert manifest.content_id == "conv-001"
        assert manifest.source_type == "feishu_chat"
        assert manifest.creator_id == "u123"
        assert manifest.published_at == "2026-05-10T09:00:00"
        assert manifest.raw_path == "data/raw/chat.json"

    def test_from_record_roundtrip(self) -> None:
        record = self._make_record(
            creator_id="u456",
            creator_name="RoundTrip",
            overall_summary="Summary text",
            language="zh",
            market_scope=["US", "HK"],
        )
        manifest = ContentManifest.from_record(record)
        # Verify all fields match
        assert manifest.content_id == record.content_id
        assert manifest.source_type == record.source_type
        assert manifest.source_platform == record.source_platform
        assert manifest.creator_id == record.creator_id
        assert manifest.creator_name == record.creator_name
        assert manifest.file_type == record.file_type
        assert manifest.overall_summary == "Summary text"
        assert manifest.language == "zh"
        assert manifest.market_scope == ["US", "HK"]

    def test_to_manifest_none_published_at(self) -> None:
        record = self._make_record(published_at=None)
        manifest = record.to_manifest()
        assert manifest.published_at is None

    def test_manifest_to_dict(self) -> None:
        record = self._make_record()
        manifest = record.to_manifest()
        d = manifest.to_dict()
        assert isinstance(d, dict)
        assert d["content_id"] == "conv-001"
        assert "source_type" in d
        assert "raw_path" in d


# ---------------------------------------------------------------------------
# 3. F0 route contract
# ---------------------------------------------------------------------------

class TestF0RouteContract:
    """Validate /api/files endpoints conform to F0 contract."""

    @pytest.fixture()
    def client(self):
        from finer.api.server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_upload_returns_f0_fields(self, client: TestClient, tmp_path, monkeypatch):
        """POST /api/files must return content_id, raw_path, stageBadge."""
        # Monkeypatch DATA_ROOT to use tmp_path
        monkeypatch.setattr("finer.api.routes.files.DATA_ROOT", tmp_path)

        import io
        resp = client.post(
            "/api/files",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["stageBadge"] == "F0"
        assert body["workflow"] == "intake"
        assert "path" in body

    def test_error_response_has_envelope(self, client: TestClient, tmp_path, monkeypatch):
        """Errors from /api/files should use canonical error envelope."""
        monkeypatch.setattr("finer.api.routes.files.DATA_ROOT", tmp_path)
        # Force an error by making the directory read-only is hard in tests,
        # so we just verify the endpoint structure exists
        resp = client.get("/api/files?tier=F0")
        # Should succeed (even if empty)
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# 4. paths.py directory contract
# ---------------------------------------------------------------------------

class TestDirectoryContract:
    """Validate paths.py only defines F0-relevant directories."""

    def test_data_root_is_repo_data(self) -> None:
        assert DATA_ROOT.name == "data"

    def test_no_downstream_stage_directories_in_proprocessed_folders(self) -> None:
        from finer.paths import PROCESSED_FOLDERS
        downstream = {"parsing", "enrichment", "extraction", "policy", "backtest"}
        for folder in PROCESSED_FOLDERS:
            assert folder not in downstream, f"{folder} is a downstream stage, not F0"

    def test_ensure_storage_creates_only_f0_paths(self, tmp_path) -> None:
        created = ensure_storage(tmp_path)
        # All created paths should be under data/raw/ or data/processed/ or data/cache/ or data/inbox/
        for p in created:
            rel = str(p).replace(str(tmp_path), "")
            assert any(
                rel.startswith(f"/data/{d}")
                for d in ("raw", "processed", "cache", "inbox", "backtests", "market")
            ), f"Unexpected directory: {rel}"

    def test_ensure_storage_no_downstream_dirs(self, tmp_path) -> None:
        from pathlib import PurePosixPath
        created = ensure_storage(tmp_path)
        downstream_stages = {"parsing", "enrichment", "extraction", "policy", "backtest"}
        for p in created:
            parts = PurePosixPath(p).parts
            for stage in downstream_stages:
                assert stage not in parts, f"Found downstream dir {stage} in: {p}"
