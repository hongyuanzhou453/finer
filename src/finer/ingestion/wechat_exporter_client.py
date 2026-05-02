"""WeChat Article Exporter Client — HTTP client for wechat-article-exporter service.

This client interacts with the wechat-article-exporter Nuxt.js application,
which proxies the WeChat official account backend APIs for article export.

Reference: https://github.com/kelipovanatalja453-bot/wechat-article-exporter
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Fixed-window rate limiter for exporter API calls.

    Uses a sliding window of timestamps to enforce a maximum number
    of requests per minute.
    """

    def __init__(self, requests_per_minute: int = 60):
        self._max_requests = requests_per_minute
        self._window = 60.0  # seconds
        self._timestamps: deque[float] = deque()

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        now = time.monotonic()
        # Purge timestamps outside the window
        while self._timestamps and self._timestamps[0] < now - self._window:
            self._timestamps.popleft()

        if len(self._timestamps) >= self._max_requests:
            # Wait until the oldest timestamp expires
            sleep_until = self._timestamps[0] + self._window
            wait = sleep_until - now
            if wait > 0:
                logger.debug(f"Rate limiter: waiting {wait:.1f}s")
                await asyncio.sleep(wait)

        self._timestamps.append(time.monotonic())


class ScanStatus(str, Enum):
    """QR code scan status."""
    WAITING = "waiting"      # Waiting for scan
    SCANNED = "scanned"      # QR scanned, waiting for confirm
    CONFIRMED = "confirmed"  # Login confirmed
    EXPIRED = "expired"      # QR code expired
    ERROR = "error"          # Error occurred


@dataclass
class ScanResult:
    """Result of polling scan status."""
    status: ScanStatus
    auth_key: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class WeChatAccountInfo:
    """WeChat official account info from search."""
    fakeid: str
    nickname: str
    alias: str = ""
    round_head_img: str = ""
    service_type: int = 0
    signature: str = ""


@dataclass
class WeChatArticleInfo:
    """Article info from publish list."""
    aid: str
    title: str
    link: str = ""
    cover: str = ""
    digest: str = ""
    create_time: int = 0
    author: str = ""
    read_num: int = 0
    like_num: int = 0


@dataclass
class ArticleListResult:
    """Result of article list query."""
    articles: list[WeChatArticleInfo] = field(default_factory=list)
    total: int = 0
    has_more: bool = False


class WeChatExporterError(Exception):
    """Base exception for WeChat exporter client."""
    pass


class LoginRequiredError(WeChatExporterError):
    """Raised when operation requires login but no auth key is available."""
    pass


class WeChatExporterClient:
    """HTTP client for wechat-article-exporter service.

    This client wraps the HTTP APIs exposed by the wechat-article-exporter
    Nuxt.js application, which acts as a proxy to WeChat official account
    backend APIs.

    Usage:
        async with WeChatExporterClient() as client:
            # Get QR code for login
            qr_image = await client.get_qrcode()

            # Poll for scan status
            result = await client.poll_scan_status()

            # Search for accounts
            accounts = await client.search_account("公众号名称")

            # Get articles
            articles = await client.get_articles(fakeid)
    """

    DEFAULT_BASE_URL = "http://localhost:3000"
    DEFAULT_TIMEOUT = 30.0
    POLL_INTERVAL = 2.0  # seconds between poll requests
    MAX_POLL_ATTEMPTS = 150  # 5 minutes max wait time

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        requests_per_minute: int = 60,
    ):
        """Initialize the client.

        Args:
            base_url: Base URL of the wechat-article-exporter service
            timeout: HTTP request timeout in seconds
            requests_per_minute: Maximum requests per minute (rate limit)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth_key: Optional[str] = None
        self._rate_limiter = _RateLimiter(requests_per_minute)

        # Shared async client (created on first use)
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "WeChatExporterClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the HTTP client is created."""
        if self._client is None:
            # Create client with explicit transport to bypass proxy
            transport = httpx.AsyncHTTPTransport(proxy=None)
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
                transport=transport,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with auth key if available."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        if self.auth_key:
            headers["Cookie"] = f"auth-key={self.auth_key}"
        return headers

    def _extract_auth_key(self, response: httpx.Response) -> Optional[str]:
        """Extract auth-key from response cookies."""
        cookies = response.cookies
        if "auth-key" in cookies:
            return cookies["auth-key"]

        # Try to extract from Set-Cookie header
        set_cookie = response.headers.get("set-cookie", "")
        if "auth-key=" in set_cookie:
            # Parse the cookie value
            for part in set_cookie.split(";"):
                part = part.strip()
                if part.startswith("auth-key="):
                    return part.split("=", 1)[1]
        return None

    async def start_login_session(self) -> str:
        """Start a new login session.

        Returns:
            Session ID (uuid cookie)

        Raises:
            WeChatExporterError: If the request fails
        """
        client = await self._ensure_client()
        import time
        import random

        sid = f"{int(time.time() * 1000)}{random.randint(0, 99)}"

        try:
            await self._rate_limiter.acquire()
            response = await client.post(
                f"/api/web/login/session/{sid}",
                headers=self._get_headers(),
            )

            if response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to start login session: HTTP {response.status_code}"
                )

            # Extract uuid from cookies
            uuid = ""
            if "uuid" in response.cookies:
                uuid = response.cookies["uuid"]

            logger.info(f"Started login session: {sid}")
            return uuid or sid

        except httpx.HTTPError as e:
            logger.error(f"HTTP error starting login session: {e}")
            raise WeChatExporterError(f"Failed to start login session: {e}") from e

    async def get_qrcode(self) -> bytes:
        """Get login QR code image.

        This method first creates a login session, then fetches the QR code.
        The uuid cookie from the session is passed to the QR code request.

        Returns:
            JPEG image bytes of the QR code

        Raises:
            WeChatExporterError: If the request fails
        """
        client = await self._ensure_client()

        try:
            import time

            # Step 1: Start login session
            sid = f"{int(time.time() * 1000)}{int(time.time() * 1000) % 100}"
            await self._rate_limiter.acquire()
            session_response = await client.post(
                f"/api/web/login/session/{sid}",
                headers=self._get_headers(),
            )

            if session_response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to start login session: HTTP {session_response.status_code}"
                )

            # Extract uuid cookie from response
            uuid_cookie = None
            if "uuid" in session_response.cookies:
                uuid_cookie = session_response.cookies["uuid"]
                logger.info(f"Got uuid cookie: {uuid_cookie[:8]}...")

            # Step 2: Get QR code with uuid cookie
            headers = self._get_headers()
            if uuid_cookie:
                headers["Cookie"] = f"uuid={uuid_cookie}"

            await self._rate_limiter.acquire()
            response = await client.get(
                f"/api/web/login/getqrcode?rnd={int(time.time() * 1000)}",
                headers=headers,
            )

            if response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to get QR code: HTTP {response.status_code}"
                )

            # Check if response is an image
            content_type = response.headers.get("content-type", "")
            if "image" in content_type or len(response.content) > 100:
                logger.info(f"Successfully retrieved login QR code ({len(response.content)} bytes, type: {content_type})")
                return response.content
            else:
                raise WeChatExporterError(
                    f"QR code response is not an image (content-type: {content_type}, size: {len(response.content)})"
                )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting QR code: {e}")
            raise WeChatExporterError(f"Failed to get QR code: {e}") from e

    async def poll_scan_status(self) -> ScanResult:
        """Poll the scan status once.

        Returns:
            ScanResult with current status and auth_key if login confirmed

        Note:
            For continuous polling, use wait_for_scan() instead.
        """
        client = await self._ensure_client()

        try:
            await self._rate_limiter.acquire()
            response = await client.get(
                "/api/web/login/scan",
                headers=self._get_headers(),
            )

            if response.status_code != 200:
                return ScanResult(
                    status=ScanStatus.ERROR,
                    error_message=f"HTTP {response.status_code}",
                )

            # Check for auth key in response cookies
            auth_key = self._extract_auth_key(response)
            if auth_key:
                self.auth_key = auth_key
                logger.info("Login confirmed, auth key obtained")
                return ScanResult(
                    status=ScanStatus.CONFIRMED,
                    auth_key=auth_key,
                )

            # Parse response body for status
            try:
                data = response.json()
                status_str = data.get("status", "waiting")

                if status_str == "confirmed":
                    # May have auth key in response
                    self.auth_key = data.get("auth_key") or auth_key
                    return ScanResult(
                        status=ScanStatus.CONFIRMED,
                        auth_key=self.auth_key,
                    )
                elif status_str == "scanned":
                    return ScanResult(status=ScanStatus.SCANNED)
                elif status_str == "expired":
                    return ScanResult(
                        status=ScanStatus.EXPIRED,
                        error_message="QR code expired",
                    )
                else:
                    return ScanResult(status=ScanStatus.WAITING)

            except Exception as e:
                logger.warning(f"Failed to parse scan status response: {e}")
                return ScanResult(status=ScanStatus.WAITING)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error polling scan status: {e}")
            return ScanResult(
                status=ScanStatus.ERROR,
                error_message=str(e),
            )

    async def wait_for_scan(self, timeout: float = 300.0) -> ScanResult:
        """Wait for QR code scan and confirmation.

        This method polls the scan status until:
        - Login is confirmed (returns CONFIRMED)
        - QR code expires (returns EXPIRED)
        - Timeout is reached (returns ERROR)

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            ScanResult with final status
        """
        start_time = asyncio.get_event_loop().time()
        attempts = 0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout or attempts >= self.MAX_POLL_ATTEMPTS:
                return ScanResult(
                    status=ScanStatus.ERROR,
                    error_message="Timeout waiting for scan",
                )

            result = await self.poll_scan_status()

            if result.status == ScanStatus.CONFIRMED:
                return result
            elif result.status == ScanStatus.EXPIRED:
                return result
            elif result.status == ScanStatus.ERROR:
                return result

            # Wait before next poll
            await asyncio.sleep(self.POLL_INTERVAL)
            attempts += 1

    async def complete_login(self) -> bool:
        """Complete the login process after scan confirmation.

        This calls the bizlogin endpoint to finalize the session.

        Returns:
            True if login successful, False otherwise
        """
        client = await self._ensure_client()

        try:
            await self._rate_limiter.acquire()
            response = await client.post(
                "/api/web/login/bizlogin",
                headers=self._get_headers(),
                json={},
            )

            if response.status_code != 200:
                logger.error(f"Bizlogin failed: HTTP {response.status_code}")
                return False

            # Extract auth key from response
            auth_key = self._extract_auth_key(response)
            if auth_key:
                self.auth_key = auth_key
                logger.info("Login completed successfully")
                return True

            # Check response body
            try:
                data = response.json()
                if data.get("success") or data.get("ret") == 0:
                    return True
            except Exception:
                pass

            return False

        except httpx.HTTPError as e:
            logger.error(f"HTTP error completing login: {e}")
            return False

    async def search_account(self, keyword: str) -> list[WeChatAccountInfo]:
        """Search for WeChat official accounts.

        Args:
            keyword: Search keyword (account name or ID)

        Returns:
            List of matching accounts

        Raises:
            LoginRequiredError: If not logged in
            WeChatExporterError: If request fails
        """
        if not self.auth_key:
            raise LoginRequiredError("Must be logged in to search accounts")

        client = await self._ensure_client()

        try:
            await self._rate_limiter.acquire()
            response = await client.get(
                "/api/web/mp/searchbiz",
                params={"keyword": keyword},
                headers=self._get_headers(),
            )

            if response.status_code == 401:
                raise LoginRequiredError("Session expired, please login again")

            if response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to search accounts: HTTP {response.status_code}"
                )

            data = response.json()

            accounts: list[WeChatAccountInfo] = []
            items = data.get("list") or data.get("items") or []

            for item in items:
                accounts.append(WeChatAccountInfo(
                    fakeid=item.get("fakeid", ""),
                    nickname=item.get("nickname", ""),
                    alias=item.get("alias", ""),
                    round_head_img=item.get("round_head_img", ""),
                    service_type=item.get("service_type", 0),
                    signature=item.get("signature", ""),
                ))

            logger.info(f"Found {len(accounts)} accounts for keyword: {keyword}")
            return accounts

        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching accounts: {e}")
            raise WeChatExporterError(f"Failed to search accounts: {e}") from e

    async def get_articles(
        self,
        fakeid: str,
        begin: int = 0,
        size: int = 10,
    ) -> ArticleListResult:
        """Get published articles from an official account.

        Args:
            fakeid: The fakeid of the official account (from search_account)
            begin: Starting index (0-based)
            size: Number of articles to fetch (max 10)

        Returns:
            ArticleListResult with articles and pagination info

        Raises:
            LoginRequiredError: If not logged in
            WeChatExporterError: If request fails
        """
        if not self.auth_key:
            raise LoginRequiredError("Must be logged in to get articles")

        client = await self._ensure_client()

        # Ensure size is within limits
        size = min(size, 10)

        try:
            await self._rate_limiter.acquire()
            response = await client.get(
                "/api/web/mp/appmsgpublish",
                params={
                    "id": fakeid,
                    "begin": begin,
                    "size": size,
                },
                headers=self._get_headers(),
            )

            if response.status_code == 401:
                raise LoginRequiredError("Session expired, please login again")

            if response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to get articles: HTTP {response.status_code}"
                )

            data = response.json()

            articles: list[WeChatArticleInfo] = []
            items = data.get("publish_page", {}).get("publish_list") or []

            for item in items:
                # Each item may have multiple articles (multi-article posts)
                article_data = item.get("publish_info", {})
                if isinstance(article_data, dict):
                    articles.append(WeChatArticleInfo(
                        aid=article_data.get("aid", ""),
                        title=article_data.get("title", ""),
                        link=article_data.get("link", ""),
                        cover=article_data.get("cover", ""),
                        digest=article_data.get("digest", ""),
                        create_time=article_data.get("create_time", 0),
                        author=article_data.get("author", ""),
                    ))
                else:
                    # Single article format
                    articles.append(WeChatArticleInfo(
                        aid=item.get("aid", "") or item.get("appmsgid", ""),
                        title=item.get("title", ""),
                        link=item.get("link", "") or item.get("content_url", ""),
                        cover=item.get("cover", ""),
                        digest=item.get("digest", ""),
                        create_time=item.get("create_time", 0) or item.get("update_time", 0),
                        author=item.get("author", ""),
                    ))

            total = data.get("publish_page", {}).get("total_count", 0) or len(articles)
            has_more = begin + size < total

            logger.info(
                f"Retrieved {len(articles)} articles from account {fakeid} "
                f"(total: {total}, has_more: {has_more})"
            )

            return ArticleListResult(
                articles=articles,
                total=total,
                has_more=has_more,
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting articles: {e}")
            raise WeChatExporterError(f"Failed to get articles: {e}") from e

    async def get_all_articles(
        self,
        fakeid: str,
        max_articles: Optional[int] = None,
    ) -> list[WeChatArticleInfo]:
        """Get all articles from an official account.

        Args:
            fakeid: The fakeid of the official account
            max_articles: Maximum number of articles to fetch (None for all)

        Returns:
            List of all articles
        """
        all_articles: list[WeChatArticleInfo] = []
        begin = 0
        page_size = 10

        while True:
            result = await self.get_articles(fakeid, begin, page_size)

            if not result.articles:
                break

            all_articles.extend(result.articles)

            if max_articles and len(all_articles) >= max_articles:
                return all_articles[:max_articles]

            if not result.has_more:
                break

            begin += page_size

        logger.info(
            f"Retrieved {len(all_articles)} total articles from account {fakeid}"
        )
        return all_articles

    async def export_article(
        self,
        article_url: str,
        format: str = "markdown",
    ) -> str:
        """Export article content.

        Args:
            article_url: URL of the article to export
            format: Export format ("markdown", "html", "text")

        Returns:
            Exported article content

        Note:
            This endpoint may not be available in all wechat-article-exporter
            versions. Check the service documentation.
        """
        if not self.auth_key:
            raise LoginRequiredError("Must be logged in to export articles")

        client = await self._ensure_client()

        try:
            await self._rate_limiter.acquire()
            response = await client.post(
                "/api/web/mp/export",
                params={"url": article_url, "format": format},
                headers=self._get_headers(),
            )

            if response.status_code == 401:
                raise LoginRequiredError("Session expired, please login again")

            if response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to export article: HTTP {response.status_code}"
                )

            data = response.json()
            content = data.get("content") or data.get("markdown", "")

            logger.info(f"Exported article: {article_url[:50]}...")
            return content

        except httpx.HTTPError as e:
            logger.error(f"HTTP error exporting article: {e}")
            raise WeChatExporterError(f"Failed to export article: {e}") from e

    async def get_article_detail(
        self,
        fakeid: str,
        article_id: str,
    ) -> dict[str, Any]:
        """Get detailed article information including stats.

        Args:
            fakeid: The fakeid of the official account
            article_id: The article ID (aid)

        Returns:
            Article detail dictionary with read/like/comment counts
        """
        if not self.auth_key:
            raise LoginRequiredError("Must be logged in to get article details")

        client = await self._ensure_client()

        try:
            await self._rate_limiter.acquire()
            response = await client.get(
                "/api/web/mp/appmsg",
                params={
                    "action": "getinfo",
                    "fakeid": fakeid,
                    "appmsgid": article_id,
                },
                headers=self._get_headers(),
            )

            if response.status_code == 401:
                raise LoginRequiredError("Session expired, please login again")

            if response.status_code != 200:
                raise WeChatExporterError(
                    f"Failed to get article detail: HTTP {response.status_code}"
                )

            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting article detail: {e}")
            raise WeChatExporterError(f"Failed to get article detail: {e}") from e


# Convenience function for quick login flow
async def login_with_qrcode(
    base_url: str = WeChatExporterClient.DEFAULT_BASE_URL,
    on_qrcode: Optional[callable] = None,
) -> WeChatExporterClient:
    """Perform interactive login with QR code.

    Args:
        base_url: Base URL of the wechat-article-exporter service
        on_qrcode: Optional callback to handle QR code bytes (e.g., display or save)

    Returns:
        Authenticated WeChatExporterClient instance
    """
    client = WeChatExporterClient(base_url)

    # Get QR code
    qr_image = await client.get_qrcode()

    if on_qrcode:
        on_qrcode(qr_image)
    else:
        # Default: save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(qr_image)
            print(f"QR code saved to: {f.name}")
            print("Please scan with WeChat app")

    # Wait for scan
    result = await client.wait_for_scan()

    if result.status != ScanStatus.CONFIRMED:
        await client.close()
        raise WeChatExporterError(
            f"Login failed: {result.error_message or result.status.value}"
        )

    # Complete login
    await client.complete_login()

    return client
