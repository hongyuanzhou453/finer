"""F0 · WeChat public article acquisition — credential-free ``mp.weixin.qq.com`` fetch.

Replaces the *fetch* leg of the dead exporter chain. The exporter path needed a
hosted Nuxt service, an official-account owner's QR login, and a 7-day token;
this one needs an article URL and nothing else — no cookie, no login, no
third-party service, therefore no account to get banned.

What it does **not** do: discovery. A public article page can only be fetched
once its URL is known; WeChat exposes no public "list an account's articles"
endpoint. Discovery is a separate, pluggable concern (see
``WeChatArticleDiscovery`` implementations).

Identity
--------
A public page carries every identifier F0 needs for a stable, re-fetchable
identity, so records survive re-runs and short-link churn:

===============  ==========================================================
``user_name``    ``gh_1652e0dbaabd`` — canonical account id (creator_id)
``__biz``        ``MzA3NTg4MDUzNQ==`` — account id in URL/base64 space
``mid`` + ``idx``  canonical article identity within the account
``ct``           publish timestamp (unix seconds)
===============  ==========================================================

The ``/s/<token>`` short link is deliberately *not* the identity: one article
can be reachable through several tokens.

Parser lineage: the HTML→Markdown state machine follows the approach in
hxer7963/podcast-summary ``wechat_fetch.py`` (MIT), adapted here to carry raw
HTML through for archival and to classify non-article page states.
"""

from __future__ import annotations

import html as html_module
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from html.parser import HTMLParser
from typing import Optional

from finer.errors import ErrorCode, FinerError

logger = logging.getLogger(__name__)

WECHAT_ARTICLE_HOST = "mp.weixin.qq.com"

# A mobile UA is what the article page is authored for; it returns the same
# document a phone would get. Verified working from a residential IP at
# 26 req/min sustained (2026-08-03). Datacenter IPs get the "环境异常"
# interstitial regardless of UA — reputation is the gate here, not the UA.
_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"https://{WECHAT_ARTICLE_HOST}/",
}

_BLOCK_TAGS = {"p", "div", "section", "blockquote", "table", "tr", "ul", "ol"}
_SKIP_TAGS = {"script", "style", "noscript", "svg"}

# Python's HTMLParser is not HTML5-aware: it reports a bare ``<img>`` or
# ``<br>`` through handle_starttag with no matching handle_endtag, while the
# self-closed ``<img />`` form goes through handle_startendtag and stays
# balanced. Counting the unbalanced form would inflate the nesting depth
# permanently, so the real ``</div>`` closing #js_content never registers and
# the page footer bleeds into the article body. Excluded symmetrically on both
# sides so a stray ``</br>`` cannot decrement either.
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# Page-state markers, checked before parsing. WeChat serves these as HTTP 200
# with a ~32KB body, so status code alone cannot distinguish them.
_DELETED_MARKERS = ("该内容已被发布者删除", "已被发布者删除")
_VIOLATION_MARKERS = ("此内容因违规无法查看", "此帐号已被屏蔽", "内容涉嫌违反相关法律法规")
_BLOCKED_MARKERS = ("环境异常", "访问过于频繁", "完成验证后即可继续访问")

# The captcha page has a JS-rendered variant whose served HTML contains none of
# the visible strings above — it is a ~17KB shell that draws the challenge
# client-side. Detecting it by shell markers matters more than it looks: an
# undetected challenge parses as an empty article, and EMPTY is terminal, so a
# merely rate-limited article would be dropped and never retried.
_CAPTCHA_MARKERS = (
    "wappoc_appmsgcaptcha",
    "secitptpage/verify.html",
    "mmbizwap:secitptpage",
    "poc_token",
)


class ArticleState(str, Enum):
    """Outcome of loading a public article page.

    ``DELETED``/``VIOLATION`` are terminal facts about the article and must not
    be retried; ``BLOCKED`` is about *us* (rate/IP reputation) and is the only
    state worth backing off on.
    """

    OK = "ok"
    DELETED = "deleted"
    VIOLATION = "violation"
    BLOCKED = "blocked"
    EMPTY = "empty"


_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9_.=+-]")


def sanitize_path_component(value: str, *, fallback: str) -> str:
    """Make an identifier safe to use as a single filesystem path component.

    Account and article identifiers reach us from untrusted places — query
    parameters of a URL supplied by a third-party RSS bridge, and ``var``
    declarations scraped out of a remote page — and then become directory and
    file names under ``data/raw/wechat/``. Without this, a feed carrying
    ``__biz=../../../etc`` writes outside the data root entirely.

    Even benign values need it: ``__biz`` is base64, whose alphabet includes
    ``/``, which would silently split one account across nested directories.

    Traversal segments are rejected outright rather than escaped, so no input
    can produce ``.`` or ``..`` by any encoding route.
    """
    cleaned = _UNSAFE_PATH_CHARS.sub("_", value.strip())
    if not cleaned or set(cleaned) <= {".", "_"}:
        return fallback
    return cleaned[:120]


@dataclass(frozen=True)
class PublicArticle:
    """One fetched public article, normalized for F0 intake."""

    state: ArticleState
    source_url: str
    ghid: str = ""
    biz: str = ""
    mid: str = ""
    idx: str = ""
    title: str = ""
    account_name: str = ""
    author: str = ""
    published_at: Optional[datetime] = None
    markdown: str = ""
    html: bytes = b""
    image_urls: tuple[str, ...] = ()

    @property
    def article_id(self) -> str:
        """Stable per-account article identity: ``{mid}_{idx}``.

        Falls back to the short-link token when a page omits ``mid``/``idx``
        (rare, seen on some migrated accounts) so a record can still be built.
        Returns ``""`` when neither is available — see :attr:`has_identity`.

        The fallback is taken *only* from the ``/s/<token>`` form. A long-form
        URL's path is the bare ``/s``, so treating its tail as an id would give
        every such article the identifier ``"s"`` and collapse them all onto one
        ``content_id`` — the second article imported would be reported as a
        duplicate and silently lost.

        Sanitized because this value becomes a filename.
        """
        if self.mid and self.idx:
            return sanitize_path_component(f"{self.mid}_{self.idx}", fallback="")
        if is_short_link(self.source_url):
            tail = urllib.parse.urlparse(self.source_url).path.rsplit("/", 1)[-1]
            return sanitize_path_component(tail, fallback="")
        return ""

    @property
    def account_id(self) -> str:
        """Canonical account identity, preferring the ``gh_`` name over ``__biz``.

        Returns ``""`` when the page carried neither. Sanitized because this
        value becomes a directory name.
        """
        return sanitize_path_component(self.ghid or self.biz, fallback="")

    @property
    def has_identity(self) -> bool:
        """True when this article can be given a unique, reproducible id.

        Without both halves there is nothing to key a ``content_id`` on, and
        anything we invent would either collide with other articles or change
        between runs. Importing such a page is worse than skipping it: a
        collision loses a real article, and a random id breaks idempotency.
        """
        return bool(self.account_id and self.article_id)

    @property
    def ok(self) -> bool:
        return self.state is ArticleState.OK


class RateLimiter:
    """Thread-safe minimum-interval limiter.

    Deliberately a floor on spacing rather than a token bucket: WeChat's
    interstitial is triggered by bursts, so an evenly-paced stream is both
    safer and simpler to reason about than a bucket that permits a burst.
    """

    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval


# Default pacing: 6s between requests (10 req/min), well under the 26 req/min
# that ran clean in testing. Discovery latency for this pipeline is measured in
# hours, so there is nothing to buy by going faster.
DEFAULT_RATE_LIMITER = RateLimiter(6.0)


def validate_article_url(url: str) -> str:
    """Return *url* if it is a public WeChat article link, else raise.

    Host is checked against an exact allowlist rather than a suffix match, so
    ``mp.weixin.qq.com.evil.test`` cannot slip through.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname != WECHAT_ARTICLE_HOST:
        raise FinerError(
            ErrorCode.F0_IN_001,
            f"Not a public WeChat article URL: {url!r}",
            stage="F0",
            operation="wechat_public_fetch",
            source_channel="wechat",
            retryable=False,
            details={"expected_host": WECHAT_ARTICLE_HOST},
        )
    return url


class _ArticleParser(HTMLParser):
    """Extracts ``#js_content`` as Markdown plus the page's metadata block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.parts: list[str] = []
        self.images: list[str] = []
        self.content_seen = False
        self._content_depth = 0
        self._skip_depth = 0
        self._link_stack: list[str] = []
        self._capture: Optional[str] = None
        self._capture_depth = 0
        self._capture_parts: list[str] = []

    @staticmethod
    def _as_dict(items: list[tuple[str, Optional[str]]]) -> dict[str, str]:
        return {key: value or "" for key, value in items}

    def handle_starttag(self, tag: str, items: list[tuple[str, Optional[str]]]) -> None:
        attrs = self._as_dict(items)
        classes = set(attrs.get("class", "").split())

        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key and attrs.get("content"):
                self.meta[key.lower()] = attrs["content"].strip()

        if self._capture is not None:
            if tag not in _VOID_TAGS:
                self._capture_depth += 1
        elif attrs.get("id") in {"js_name", "js_author_name", "publish_time"}:
            self._capture = attrs["id"]
            self._capture_depth = 1
            self._capture_parts = []
        elif tag == "h1" and (
            attrs.get("id") == "activity-name" or "rich_media_title" in classes
        ):
            self._capture = "title"
            self._capture_depth = 1
            self._capture_parts = []

        if self._content_depth == 0:
            if tag == "div" and (
                attrs.get("id") == "js_content" or "rich_media_content" in classes
            ):
                self._content_depth = 1
                self.content_seen = True
            return

        if tag not in _VOID_TAGS:
            self._content_depth += 1
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag in _BLOCK_TAGS:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif re.fullmatch(r"h[1-6]", tag):
            self.parts.append(f"\n\n{'#' * int(tag[1])} ")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "pre":
            self.parts.append("\n\n```\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "a":
            self._link_stack.append(attrs.get("href", ""))
            self.parts.append("[")
        elif tag == "img":
            src = attrs.get("data-src") or attrs.get("data-original") or attrs.get("src")
            if src and src.startswith(("http://", "https://")):
                self.images.append(html_module.unescape(src))
                self.parts.append(f"\n\n![]({html_module.unescape(src)})\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            # A stray </br> or </img> closes nothing; decrementing on it would
            # undo the balance that skipping the start tag just preserved.
            return

        if self._capture is not None:
            self._capture_depth -= 1
            if self._capture_depth == 0:
                value = re.sub(r"\s+", " ", "".join(self._capture_parts)).strip()
                if value:
                    self.meta[self._capture] = value
                self._capture = None
                self._capture_parts = []

        if self._content_depth == 0:
            return
        if self._content_depth == 1:
            self._content_depth = 0
            return

        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth:
            if tag in {"strong", "b"}:
                self.parts.append("**")
            elif tag in {"em", "i"}:
                self.parts.append("*")
            elif tag == "pre":
                self.parts.append("\n```\n\n")
            elif tag == "a":
                href = self._link_stack.pop() if self._link_stack else ""
                self.parts.append(
                    f"]({href})" if href.startswith(("http://", "https://")) else "]"
                )
            elif tag in _BLOCK_TAGS or re.fullmatch(r"h[1-6]", tag):
                self.parts.append("\n\n")
        self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._capture_parts.append(data)
        if self._content_depth and not self._skip_depth:
            self.parts.append(data)

    def markdown(self) -> str:
        text = "".join(self.parts).replace("\xa0", " ")
        # Trailing-whitespace trimming is done per line rather than with
        # ``re.sub(r"[ \t]+\n", ...)``: that pattern backtracks quadratically on
        # long space runs (54ms at 8k spaces, 4x per doubling), and WeChat
        # bodies routinely carry multi-KB runs of &nbsp; padding.
        text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
        return re.sub(r"\n{3,}", "\n\n", text).strip()


_PAGE_VARS = {
    "biz": r'var\s+biz\s*=\s*["\']([^"\']*)["\']',
    "mid": r'var\s+mid\s*=\s*["\']?(\d+)',
    "idx": r'var\s+idx\s*=\s*["\']?(\d+)',
    "ghid": r'var\s+user_name\s*=\s*["\']([^"\']*)["\']',
    "author": r'var\s+author\s*=\s*["\']([^"\']*)["\']',
    "title": r'var\s+msg_title\s*=\s*[\'"]([^\'"]*)',
}


def _is_structural_block(source: str, final_url: str = "") -> bool:
    """True for signals that cannot occur in article prose.

    The captcha shell's script markers and the redirect endpoint are machine
    artifacts, so unlike the visible Chinese notices they stay trustworthy even
    on a page that also has a real body.
    """
    if any(marker in source for marker in _CAPTCHA_MARKERS):
        return True
    return bool(final_url) and "wappoc_appmsgcaptcha" in final_url


def _classify(source: str, final_url: str = "", *, has_body: bool = False) -> ArticleState:
    """Classify a served page. BLOCKED is checked first and wins.

    An interstitial can quote any of the other markers, and misreading a
    challenge as DELETED would permanently retire a live article.

    ``has_body`` guards against the mirror-image mistake. The visible markers
    are ordinary Chinese sentences, and an article *about* censorship or
    account bans will quote them verbatim — exactly the kind of article this
    pipeline exists to capture. WeChat never serves an interstitial and a real
    ``#js_content`` body together, so once a body has been found, only signals
    that cannot appear in prose are still trusted: the captcha shell markers
    and the redirect URL.
    """
    if _is_structural_block(source, final_url):
        return ArticleState.BLOCKED
    if has_body:
        return ArticleState.OK
    if any(marker in source for marker in _BLOCKED_MARKERS):
        return ArticleState.BLOCKED
    if any(marker in source for marker in _VIOLATION_MARKERS):
        return ArticleState.VIOLATION
    if any(marker in source for marker in _DELETED_MARKERS):
        return ArticleState.DELETED
    return ArticleState.OK


def is_fetchable_url(url: str) -> bool:
    """True when WeChat will serve this URL's article page to us.

    Two forms work, and the distinction is a signature rather than the path:

    ``/s/<token>``
        The share short link. Always fetchable.
    ``/s?__biz=…&mid=…&idx=…&sn=…&chksm=…``
        The canonical long form **carrying its ``chksm`` signature**. Also
        fetchable — verified 2026-08-03: a chksm-signed URL returned a 3.1MB
        article page, while the same URL with ``chksm`` stripped returned the
        17KB captcha shell.

    A long-form URL *without* ``chksm`` is challenged unconditionally, across
    iOS/Android MicroMessenger and desktop Chrome alike, so it is a property of
    the URL rather than of rate or IP reputation.

    This is what separates discovery sources that are merely informative from
    ones that can actually feed the fetch leg: ``getalbum`` hands back signed
    URLs and so is self-sufficient, while Wechat2RSS strips the signature and
    can only be used via its own ``content:encoded`` body.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname != WECHAT_ARTICLE_HOST:
        return False
    if parsed.path.startswith("/s/"):
        return True
    query = urllib.parse.parse_qs(parsed.query)
    return bool(query.get("chksm") and query.get("__biz") and query.get("mid"))


def is_short_link(url: str) -> bool:
    """True for the ``/s/<token>`` share form specifically.

    Kept separate from :func:`is_fetchable_url` because the two answer
    different questions: this one is about URL shape, that one about whether a
    fetch will succeed.
    """
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname == WECHAT_ARTICLE_HOST and parsed.path.startswith("/s/")


def _published_at(source: str) -> Optional[datetime]:
    match = re.search(r'(?:var\s+ct\s*=\s*["\']?|"create_time"\s*:\s*"?)(\d{9,11})', source)
    if not match:
        return None
    try:
        return datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def parse_public_article(
    source: str, url: str, raw: bytes = b"", final_url: str = ""
) -> PublicArticle:
    """Parse a fetched article page into a :class:`PublicArticle`.

    Split from fetching so page-shape regressions can be tested against saved
    fixtures without network access. ``final_url`` is the post-redirect URL,
    which is what exposes the captcha bounce.
    """
    page_vars = {
        key: (match.group(1).strip() if (match := re.search(pattern, source)) else "")
        for key, pattern in _PAGE_VARS.items()
    }

    def _non_article(state: ArticleState) -> PublicArticle:
        return PublicArticle(
            state=state,
            source_url=url,
            ghid=page_vars["ghid"],
            biz=page_vars["biz"],
            mid=page_vars["mid"],
            idx=page_vars["idx"],
            html=raw,
        )

    # Structural signals can never appear in article prose, so they are safe to
    # trust before looking at the body — and checking them first avoids parsing
    # a ~17KB captcha shell.
    if _is_structural_block(source, final_url):
        return _non_article(ArticleState.BLOCKED)

    parser = _ArticleParser()
    parser.feed(source)
    body = parser.markdown()
    has_body = parser.content_seen and len(re.sub(r"\s+", "", body)) >= 20

    # Only now consult the visible markers, and only if no body was found: an
    # article quoting WeChat's own "该内容已被发布者删除" notice is a real article,
    # and dropping it would silently lose exactly the content this pipeline
    # cares most about.
    state = _classify(source, final_url, has_body=has_body)
    if state is not ArticleState.OK:
        return _non_article(state)
    if not has_body:
        state = ArticleState.EMPTY

    title = (
        html_module.unescape(page_vars["title"])
        or parser.meta.get("title", "")
        or parser.meta.get("og:title", "")
    )
    return PublicArticle(
        state=state,
        source_url=url,
        ghid=page_vars["ghid"],
        biz=page_vars["biz"],
        mid=page_vars["mid"],
        idx=page_vars["idx"],
        title=title,
        account_name=parser.meta.get("js_name", ""),
        author=html_module.unescape(page_vars["author"]) or parser.meta.get("js_author_name", ""),
        published_at=_published_at(source),
        markdown=body,
        html=raw,
        image_urls=tuple(parser.images),
    )


def identity_from_url(url: str) -> tuple[str, str, str]:
    """Pull ``(biz, mid, idx)`` out of a long-form article URL.

    The long form is unfetchable but still self-describing, which is what makes
    a bridge-sourced import auditable: identity comes from the WeChat URL,
    only the body comes from the bridge.
    """
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return (
        (query.get("__biz") or [""])[0],
        (query.get("mid") or [""])[0],
        (query.get("idx") or [""])[0],
    )


def parse_bridge_article(
    body_html: str,
    url: str,
    *,
    title: str = "",
    account_name: str = "",
    published_at: Optional[datetime] = None,
) -> PublicArticle:
    """Build a :class:`PublicArticle` from a bridge's copy of the body.

    Used only when the article's URL form cannot be fetched from WeChat. The
    result is deliberately distinguishable from a direct fetch: ``html`` stays
    empty (there is no served page to archive) and ``ghid`` is unset, because a
    long-form URL identifies its account by ``__biz`` rather than ``gh_*``.

    Note the identity consequence: the same article imported via a bridge
    (keyed on ``__biz``) and via a short link (keyed on ``gh_*``) yields two
    different ``content_id`` values. Both ids are recorded in metadata so the
    pair can be reconciled later; prefer one acquisition route per account.
    """
    biz, mid, idx = identity_from_url(url)
    parser = _ArticleParser()
    parser.feed(f'<div id="js_content">{body_html}</div>')
    markdown = parser.markdown()

    state = ArticleState.OK
    if len(re.sub(r"\s+", "", markdown)) < 20:
        state = ArticleState.EMPTY

    return PublicArticle(
        state=state,
        source_url=url,
        biz=biz,
        mid=mid,
        idx=idx,
        title=title,
        account_name=account_name,
        published_at=published_at,
        markdown=markdown,
        image_urls=tuple(parser.images),
    )


def fetch_public_article(
    url: str,
    *,
    timeout: float = 25.0,
    attempts: int = 3,
    limiter: Optional[RateLimiter] = DEFAULT_RATE_LIMITER,
) -> PublicArticle:
    """Fetch and parse one public WeChat article.

    Retries transport errors and ``BLOCKED`` interstitials with a widening
    backoff. Raises :class:`FinerError` when every attempt is blocked — a
    blocked page is never returned as data, because handing an interstitial to
    F1 as if it were an article is exactly the "导入成功 ≠ 解析成功" failure the
    F0 contract forbids.

    ``DELETED``/``VIOLATION``/``EMPTY`` are returned rather than raised: they
    are true, useful facts about the article that the caller should record.
    """
    validate_article_url(url)
    last_error: Optional[Exception] = None

    for attempt in range(max(1, attempts)):
        if limiter is not None:
            limiter.acquire()
        try:
            request = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                final_url = response.url
            try:
                source = raw.decode(charset, "replace")
            except LookupError:
                # An unknown charset label must not escape as a bare
                # LookupError past the Line F envelope; WeChat serves UTF-8.
                logger.warning("Unknown charset %r for %s; decoding as UTF-8", charset, url)
                source = raw.decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            logger.warning("WeChat fetch attempt %d/%d failed: %s", attempt + 1, attempts, exc)
        else:
            article = parse_public_article(source, url, raw=raw, final_url=final_url)
            if article.state is not ArticleState.BLOCKED:
                return article
            if not is_fetchable_url(url):
                # An unsigned long-form URL is challenged every time; retrying
                # only burns the backoff. Fail immediately with a usable hint.
                raise FinerError(
                    ErrorCode.F0_EXT_002,
                    "WeChat challenges long-form article URLs that carry no "
                    "chksm signature; use a /s/<token> short link or a signed "
                    "long URL (as returned by the album listing)",
                    stage="F0",
                    operation="wechat_public_fetch",
                    source_channel="wechat",
                    retryable=False,
                    details={"source_url": url, "url_form": "long"},
                )
            last_error = RuntimeError("WeChat anti-crawl interstitial")
            logger.warning(
                "WeChat returned an anti-crawl interstitial (attempt %d/%d)",
                attempt + 1,
                attempts,
            )

        if attempt < attempts - 1:
            time.sleep(5 * (attempt + 1))

    raise FinerError(
        ErrorCode.F0_EXT_001,
        f"Could not fetch WeChat article after {attempts} attempts: {last_error}",
        stage="F0",
        operation="wechat_public_fetch",
        source_channel="wechat",
        retryable=True,
        cause=last_error if isinstance(last_error, BaseException) else None,
        details={"source_url": url},
    )
