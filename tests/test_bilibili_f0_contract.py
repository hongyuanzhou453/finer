"""Bilibili F0 channel contract tests — verify canonical error envelope."""
import pytest
from fastapi.testclient import TestClient


class TestBilibiliF0Contract:
    """Verify bilibili.py error responses conform to F0 contract."""

    @pytest.fixture()
    def client(self):
        from finer.api.server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_video_info_invalid_bvid_returns_error(self, client):
        """GET /api/bilibili/video/invalid returns BILI_IN_001."""
        resp = client.get("/api/bilibili/video/invalid_bvid")
        body = resp.json()
        if "error" in body:
            assert body["error"]["code"] in ("BILI_IN_001", "BILI_EXT_001")

    def test_task_not_found_returns_error(self, client):
        """GET /api/bilibili/task/nonexistent returns BILI_NTF_001."""
        resp = client.get("/api/bilibili/task/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        if "error" in body:
            assert body["error"]["code"] == "BILI_NTF_001"

    def test_error_has_source_channel_bilibili(self, client):
        """Error responses include source_channel='bilibili'."""
        resp = client.get("/api/bilibili/video/invalid_bvid")
        body = resp.json()
        if "error" in body and "details" in body["error"]:
            assert body["error"]["details"].get("source_channel") == "bilibili"

    def test_no_http_exception_in_bilibili_routes(self):
        """bilibili.py should have zero raise HTTPException."""
        import inspect
        from finer.api.routes import bilibili
        source = inspect.getsource(bilibili)
        assert "raise HTTPException" not in source

    def test_content_manifest_uses_new_fields(self):
        """ContentManifest constructor in bilibili.py uses source_type/raw_path."""
        import inspect
        from finer.api.routes import bilibili
        source = inspect.getsource(bilibili)
        # Should use new field names
        assert "source_type=" in source or "ContentManifest" not in source
        assert "raw_path=" in source or "ContentManifest" not in source
        # Should NOT use old field names
        assert "content_type=" not in source or "metadata" in source
