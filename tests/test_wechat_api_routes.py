"""Tests for WeChat API routes."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    from finer.api.server import app
    return TestClient(app)


class TestLoginEndpoints:
    @patch("finer.api.routes.wechat._get_exporter_client")
    def test_create_login_session_success(self, mock_get_client, client):
        mock_client = AsyncMock()
        mock_client.get_qrcode.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        mock_get_client.return_value = mock_client

        resp = client.post("/api/wechat/login")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "qr_ready"
        assert data["qr_data_uri"].startswith("data:image/png;base64,")

    @patch("finer.api.routes.wechat._get_exporter_client")
    def test_create_login_session_exporter_unavailable(self, mock_get_client, client):
        mock_client = AsyncMock()
        mock_client.get_qrcode.side_effect = ConnectionError("Connection refused")
        mock_get_client.return_value = mock_client

        resp = client.post("/api/wechat/login")
        assert resp.status_code == 502

    @patch("finer.api.routes.wechat._get_exporter_client")
    def test_login_status_not_found(self, mock_get_client, client):
        resp = client.get("/api/wechat/login/nonexistent/status")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "WX_AUTH_001"

    @patch("finer.api.routes.wechat._get_exporter_client")
    def test_qr_endpoint_not_found(self, mock_get_client, client):
        resp = client.get("/api/wechat/login/nonexistent/qr")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "WX_AUTH_001"


class TestAccountEndpoints:
    @patch("finer.api.routes.wechat.get_unified_wechat_adapter")
    def test_list_accounts_empty(self, mock_adapter_fn, client):
        mock_adapter = AsyncMock()
        mock_adapter.list_accounts.return_value = []
        mock_adapter_fn.return_value = mock_adapter

        resp = client.get("/api/wechat/accounts")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSyncPagination:
    @patch("finer.api.routes.wechat._get_exporter_client")
    def test_sync_paginates_articles(self, mock_get_client, client):
        """Sync should loop get_articles until has_more is False."""
        from finer.ingestion.wechat_exporter_client import ArticleListResult, WeChatArticleInfo

        mock_client = AsyncMock()
        # First page: 10 articles, has_more=True
        page1_articles = [
            WeChatArticleInfo(aid=f"art_{i}", title=f"Article {i}", link=f"https://example.com/{i}", create_time=1700000000)
            for i in range(10)
        ]
        # Second page: 3 articles, has_more=False
        page2_articles = [
            WeChatArticleInfo(aid=f"art_{i}", title=f"Article {i}", link=f"https://example.com/{i}", create_time=1700000000)
            for i in range(10, 13)
        ]

        mock_client.get_articles = AsyncMock(
            side_effect=[
                ArticleListResult(articles=page1_articles, total=13, has_more=True),
                ArticleListResult(articles=page2_articles, total=13, has_more=False),
            ]
        )
        mock_client.export_article = AsyncMock(return_value="# Article content")
        mock_client.auth_key = "test_key"
        mock_get_client.return_value = mock_client

        with patch("finer.api.routes.wechat.load_wechat_service_config"):
            resp = client.post("/api/wechat/sync/test_account")

        assert resp.status_code == 200
        data = resp.json()
        # get_articles called twice (page 1 + page 2)
        assert mock_client.get_articles.call_count == 2
        # First call: begin=0, size=10
        assert mock_client.get_articles.call_args_list[0].kwargs.get("begin") == 0 or \
               mock_client.get_articles.call_args_list[0].args[1] == 0
        # Second call: begin=10, size=10
        assert mock_client.get_articles.call_args_list[1].kwargs.get("begin") == 10 or \
               mock_client.get_articles.call_args_list[1].args[1] == 10


class TestExporterHealth:
    @patch("finer.api.routes.wechat.load_wechat_service_config")
    def test_health_exporter_available(self, mock_config, client):
        mock_config.return_value = MagicMock(exporter_url="http://localhost:3001")

        with patch("httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_resp
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = client.get("/api/wechat/exporter/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True

    @patch("finer.api.routes.wechat.load_wechat_service_config")
    def test_health_exporter_unavailable(self, mock_config, client):
        mock_config.return_value = MagicMock(exporter_url="http://localhost:9999")
        resp = client.get("/api/wechat/exporter/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
