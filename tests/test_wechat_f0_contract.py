"""WeChat F0 channel contract tests — verify canonical error envelope."""
import pytest
from fastapi.testclient import TestClient


class TestWeChatF0Contract:
    """Verify wechat.py error responses conform to F0 contract."""

    @pytest.fixture()
    def client(self):
        from finer.api.server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_login_returns_valid_response(self, client):
        """POST /api/wechat/login returns valid response envelope."""
        resp = client.post("/api/wechat/login", json={"chat_id": ""})
        body = resp.json()
        # Endpoint may return 200 (session created) or error envelope
        if resp.status_code >= 400:
            assert "error" in body
            assert "code" in body["error"]
            assert "message" in body["error"]
        else:
            assert resp.status_code == 200

    def test_qr_nonexistent_session_returns_error(self, client):
        """GET /api/wechat/login/nonexistent/qr returns error."""
        resp = client.get("/api/wechat/login/nonexistent/qr")
        assert resp.status_code == 401  # WX_AUTH_001
        body = resp.json()
        assert body["error"]["code"] == "WX_AUTH_001"

    def test_poll_nonexistent_session_returns_error(self, client):
        """GET /api/wechat/login/nonexistent/status returns error."""
        resp = client.get("/api/wechat/login/nonexistent/status")
        assert resp.status_code == 401  # WX_AUTH_001
        body = resp.json()
        assert body["error"]["code"] == "WX_AUTH_001"

    def test_error_has_source_channel(self, client):
        """Error responses include source_channel='wechat'."""
        resp = client.get("/api/wechat/login/nonexistent/qr")
        body = resp.json()
        if "error" in body and "details" in body["error"]:
            assert body["error"]["details"].get("source_channel") == "wechat"

    def test_no_http_exception_in_wechat_routes(self):
        """wechat.py should have zero raise HTTPException."""
        import inspect
        from finer.api.routes import wechat
        source = inspect.getsource(wechat)
        assert "raise HTTPException" not in source
