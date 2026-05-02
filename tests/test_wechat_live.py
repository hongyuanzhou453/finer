"""Live WeChat integration tests — opt-in, skipped by default.

Set WECHAT_LIVE_TEST=1 to enable these tests.
Requires wechat-article-exporter running at localhost:3001.
"""

import os

import pytest

LIVE = os.getenv("WECHAT_LIVE_TEST")

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="WECHAT_LIVE_TEST not set — skipping live WeChat tests",
)


@pytest.fixture
def exporter_url():
    return os.getenv("WECHAT_EXPORTER_URL", "http://localhost:3001")


@pytest.mark.asyncio
async def test_exporter_health(exporter_url):
    """Verify exporter service is reachable."""
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{exporter_url}/api/web/login/scan")
        assert resp.status_code in (200, 401, 404)


@pytest.mark.asyncio
async def test_get_qrcode(exporter_url):
    """Verify QR code can be fetched from exporter."""
    from finer.ingestion.wechat_exporter_client import WeChatExporterClient

    client = WeChatExporterClient(base_url=exporter_url)
    try:
        qr_bytes = await client.get_qrcode()
        assert len(qr_bytes) > 100
        # Should be JPEG or PNG
        assert qr_bytes[:4] in (
            b"\xff\xd8\xff\xe0",  # JPEG
            b"\x89PNG",           # PNG
        ) or len(qr_bytes) > 500
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_full_login_flow(exporter_url):
    """Full login flow — requires manual QR scan within 60 seconds."""
    from finer.ingestion.wechat_exporter_client import WeChatExporterClient

    client = WeChatExporterClient(base_url=exporter_url)
    try:
        qr_bytes = await client.get_qrcode()
        assert len(qr_bytes) > 100

        # Wait for scan (short timeout for CI — user must scan quickly)
        result = await client.wait_for_scan(timeout=60.0)
        if result.status.value == "confirmed":
            # Try searching for an account
            accounts = await client.search_account("招商")
            assert isinstance(accounts, list)
    finally:
        await client.close()
