"""F0 · WeChat article discovery — pluggable sources that yield article URLs.

Discovery answers "which articles exist that I have not imported yet". WeChat
publishes no public endpoint for this, so every answer comes from a bridge, and
every bridge so far has had a lifetime measured in months:

======================  =======================================================
搜狗微信                index went stale; account search returns empty (2026)
公众平台 fakeid 搜索     closed by WeChat 2026-07-29; killed every tool using it
feeddd                  shut down 2023-07
微信读书 cookie 接口     alive but under active 风控 (-2041 滑块, 2026-08)
======================  =======================================================

So the contract here is deliberately minimal — a source only has to produce
:class:`DiscoveredArticle` entries with a URL. Everything expensive and
long-lived (fetch, archive, ContentRecord, receipt) lives in
:mod:`finer.ingestion.wechat_url_intake` and does not care which bridge is
alive this quarter. Adding or replacing a bridge is a new class here plus a
registry entry; no other F0 code changes.

``RssDiscovery`` covers every bridge that speaks RSS/Atom — Wechat2RSS,
we-mp-rss, RSSHub routes, self-hosted feeds — which is most of them, and needs
no credentials of its own.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional, Protocol, runtime_checkable

from finer.errors import ErrorCode, FinerError
from finer.ingestion.wechat_public_article import WECHAT_ARTICLE_HOST

logger = logging.getLogger(__name__)

_ARTICLE_URL_RE = re.compile(
    r"https?://mp\.weixin\.qq\.com/s(?:/[A-Za-z0-9_\-]+|\?[^\s\"'<>]+)"
)


@dataclass(frozen=True)
class DiscoveredArticle:
    """One article found by a discovery source.

    Only ``url`` is load-bearing — title and published_at are hints used for
    logging and ordering. The authoritative values come from the article page
    itself at fetch time, because bridges routinely truncate titles and
    normalize timestamps to their own crawl time.

    ``content_html`` carries the bridge's own copy of the body when it ships
    one (Wechat2RSS puts full text in ``content:encoded``). It is the fallback
    payload for articles whose URL cannot be re-fetched from source — see
    :func:`~finer.ingestion.wechat_public_article.is_short_link`. Content that
    came from a bridge is labelled as such in the record, never passed off as
    a direct fetch.
    """

    url: str
    title: str = ""
    published_at: Optional[datetime] = None
    account_name: str = ""
    discovery_source: str = "unknown"
    content_html: str = ""

    @property
    def fetchable(self) -> bool:
        """True when the URL form can be fetched directly from WeChat."""
        from finer.ingestion.wechat_public_article import is_short_link

        return is_short_link(self.url)


@runtime_checkable
class WeChatDiscovery(Protocol):
    """A source of WeChat article URLs."""

    name: str

    def discover(self) -> list[DiscoveredArticle]:
        """Return currently-visible articles, newest first where known."""
        ...


def extract_article_urls(text: str) -> list[str]:
    """Pull ``mp.weixin.qq.com`` article URLs out of arbitrary text, in order.

    Deliberately tolerant: bridges embed article links in RSS ``<link>``,
    ``<guid>``, HTML-escaped ``content:encoded`` bodies, and redirect wrappers.
    A regex over the raw payload finds them all, and validation happens at
    fetch time anyway.
    """
    seen: set[str] = set()
    urls: list[str] = []
    for match in _ARTICLE_URL_RE.finditer(text.replace("&amp;", "&")):
        url = match.group(0).rstrip(".,;)\"'")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _parse_feed_datetime(value: str) -> Optional[datetime]:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class RssDiscovery:
    """Discovery from any RSS/Atom feed whose entries link to WeChat articles.

    Works with Wechat2RSS, we-mp-rss, RSSHub wechat routes, and any self-hosted
    bridge, because it keys on the article URL rather than on a feed dialect.

    The feed's own body text is only mined for URLs as a fallback when an entry
    has no usable ``link``/``guid`` — some bridges put the real article link
    only inside the HTML body.
    """

    def __init__(
        self,
        feed_url: str,
        *,
        name: str = "",
        timeout: float = 20.0,
        account_name: str = "",
    ) -> None:
        self.feed_url = feed_url
        self.name = name or f"rss:{urllib.parse.urlparse(feed_url).netloc}"
        self.timeout = timeout
        self.account_name = account_name

    def _fetch(self) -> str:
        parsed = urllib.parse.urlparse(self.feed_url)
        if parsed.scheme not in {"http", "https"}:
            raise FinerError(
                ErrorCode.F0_IN_001,
                f"Feed URL must be http(s): {self.feed_url!r}",
                stage="F0",
                operation="wechat_discovery",
                source_channel="wechat",
                retryable=False,
            )
        request = urllib.request.Request(
            self.feed_url,
            headers={"User-Agent": "finer-f0/1.0 (+wechat-discovery)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FinerError(
                ErrorCode.F0_EXT_001,
                f"WeChat discovery feed unreachable: {exc}",
                stage="F0",
                operation="wechat_discovery",
                source_channel="wechat",
                retryable=True,
                cause=exc,
                details={"feed_url": self.feed_url},
            ) from exc

    def discover(self) -> list[DiscoveredArticle]:
        payload = self._fetch()
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            logger.warning(
                "Feed %s is not well-formed XML (%s); falling back to URL scan",
                self.feed_url,
                exc,
            )
            return [
                DiscoveredArticle(url=url, discovery_source=self.name)
                for url in extract_article_urls(payload)
            ]

        # A per-account feed names the account at channel level, not per item;
        # without this the record's creator_name degrades to a raw __biz blob.
        account_name = self.account_name
        if not account_name:
            for node in root.iter():
                if _localname(node.tag) in {"channel", "feed"}:
                    for child in node:
                        if _localname(child.tag) == "title" and (child.text or "").strip():
                            account_name = child.text.strip()
                            break
                    break

        found: list[DiscoveredArticle] = []
        seen: set[str] = set()
        for entry in root.iter():
            if _localname(entry.tag) not in {"item", "entry"}:
                continue
            fields: dict[str, str] = {}
            for child in entry:
                key = _localname(child.tag)
                if key == "link" and not (child.text or "").strip():
                    fields.setdefault("link", child.attrib.get("href", ""))
                else:
                    fields.setdefault(key, (child.text or "").strip())

            url = ""
            for candidate in (fields.get("link", ""), fields.get("guid", "")):
                if candidate and urllib.parse.urlparse(candidate).hostname == WECHAT_ARTICLE_HOST:
                    url = candidate
                    break
            if not url:
                body = " ".join(
                    fields.get(key, "") for key in ("encoded", "description", "content", "summary")
                )
                urls = extract_article_urls(body)
                url = urls[0] if urls else ""
            if not url or url in seen:
                continue
            seen.add(url)

            published = None
            for key in ("pubDate", "published", "updated", "date"):
                if fields.get(key):
                    published = _parse_feed_datetime(fields[key])
                    if published:
                        break

            found.append(
                DiscoveredArticle(
                    url=url,
                    title=fields.get("title", ""),
                    published_at=published,
                    account_name=account_name,
                    discovery_source=self.name,
                    content_html=fields.get("encoded", "") or fields.get("content", ""),
                )
            )

        fetchable = sum(1 for a in found if a.fetchable)
        logger.info(
            "Discovery %s yielded %d articles (%d directly fetchable, %d with bridge content)",
            self.name,
            len(found),
            fetchable,
            sum(1 for a in found if a.content_html),
        )
        if found and not fetchable:
            logger.warning(
                "Feed %s emits only long-form URLs, which WeChat challenges. "
                "Imports will fall back to the feed's own content where present.",
                self.name,
            )
        return found


class StaticUrlDiscovery:
    """Discovery from an explicit URL list — a file, a paste, a manual queue.

    This is the always-available floor: no bridge, no credentials, nothing that
    can be closed by an upstream policy change. When every automated source is
    down, forwarding links into a text file still keeps the channel fed.
    """

    def __init__(self, urls: Iterable[str], *, name: str = "manual") -> None:
        self.name = name
        self._urls = [u.strip() for u in urls if u.strip()]

    @classmethod
    def from_file(cls, path, *, name: str = "manual") -> "StaticUrlDiscovery":
        from pathlib import Path

        text = Path(path).read_text(encoding="utf-8")
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return cls(lines, name=name)

    def discover(self) -> list[DiscoveredArticle]:
        return [
            DiscoveredArticle(url=url, discovery_source=self.name) for url in self._urls
        ]
