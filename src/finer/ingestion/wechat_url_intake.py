"""F0 · WeChat article intake from a known URL.

The acquisition-independent half of the WeChat channel. Given an article URL —
however it was discovered — this produces the full F0 four-piece set: raw
archive, ContentRecord, ImportReceipt, and Project Memory index row.

Why this is split from discovery
--------------------------------
On 2026-07-29 WeChat closed the official-account backend endpoint that let a
logged-in account search *other* accounts' articles, and every self-hosted tool
built on it broke within 48 hours (wechat-article-exporter announced end of
maintenance on 07-30). Finer's exporter path died with them.

The lesson is that a WeChat *discovery* source has an expected lifetime
measured in months, while *fetching* a public article page has been stable for
years and needs no credentials. So discovery is a swappable input that only has
to yield URLs, and everything downstream of a URL lives here and survives the
next outage.

``discovery_source`` is stamped into each record's metadata so a source that
quietly goes stale is visible in the data rather than only in its absence.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from finer.errors import ErrorCode, FinerError
from finer.ingestion.wechat_public_article import (
    ArticleState,
    PublicArticle,
    RateLimiter,
    fetch_public_article,
)
from finer.paths import REPO_ROOT
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.services.wechat_artifact_store import WeChatArtifactStore
from finer.services.wechat_content_record_builder import build_public_article_record
from finer.utils.time import now_utc

if TYPE_CHECKING:  # pragma: no cover - typing only
    from finer.ingestion.wechat_discovery import DiscoveredArticle

logger = logging.getLogger(__name__)

_PLATFORM = "wechat"


def _f0_intake_dir(root: Path) -> Path:
    """Canonical F0 intake dir, rooted at *root* so tests can redirect writes.

    Mirrors ``paths.f0_intake_dir`` but parameterized: ``paths`` resolves
    against the module-level repo root, which would make every test write into
    the live ``data/`` tree.
    """
    return root / "data" / "F0_intake" / _PLATFORM


@dataclass
class ArticleImportOutcome:
    """Result of importing one article URL.

    ``status`` is one of:

    ``imported``   a new ContentRecord, receipt and raw archive were written
    ``duplicate``  already present; nothing rewritten (unless ``force``)
    ``skipped``    the page is not an article (deleted / violation / empty)

    Genuine acquisition failures raise :class:`~finer.errors.FinerError` rather
    than returning an outcome, so a caller can never mistake a blocked fetch
    for a successful import.
    """

    status: str
    source_url: str
    content_id: Optional[str] = None
    record_path: Optional[Path] = None
    receipt_path: Optional[Path] = None
    raw_md_path: Optional[Path] = None
    article_state: Optional[ArticleState] = None
    reason: str = ""
    record: Optional[ContentRecord] = None

    @property
    def imported(self) -> bool:
        return self.status == "imported"


def _build_receipt(
    *,
    record: ContentRecord,
    record_path: Path,
    md_path: Path,
    md_sha256: str,
    html_path: Optional[Path],
    html_sha256: Optional[str],
    acquired_via: str,
) -> ImportReceipt:
    """Build the GATE receipt for an article import.

    Artifact roles name their provenance rather than just their format:
    ``public_html`` is the byte-exact page WeChat served (first-hand evidence),
    while ``bridge_markdown`` came from a third-party feed. An audit that
    cannot tell those apart cannot judge how much the record is worth.
    """
    prefix = "bridge" if acquired_via == "bridge_content" else "public"
    raw_sha256 = {f"{prefix}_markdown": md_sha256}
    raw_paths = {f"{prefix}_markdown": str(md_path)}
    if html_path and html_sha256:
        raw_sha256[f"{prefix}_html"] = html_sha256
        raw_paths[f"{prefix}_html"] = str(html_path)

    finished = now_utc()
    return ImportReceipt(
        run_id=f"wxpub_{record.content_id}",
        source_channel="wechat",
        source_kind="wechat_article",
        status="completed",
        content_id=record.content_id,
        external_source_id=record.external_source_id,
        dedupe_fingerprint=record.dedupe_fingerprint,
        collected_at=record.collected_at,
        started_at=finished,
        finished_at=finished,
        raw_sha256=raw_sha256,
        raw_paths=raw_paths,
        record_path=str(record_path),
        records_created=1,
    )


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via tmp + fsync + ``os.replace``.

    Matches the pattern in ``pipeline.driver`` and ``services.repository``. An
    in-place write killed mid-flight leaves a 0-byte or half-written JSON that
    a later reader reports as an unattributable ``JSONDecodeError``; with this,
    a reader sees either the old content or the complete new content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _assert_contained(root: Path, account_id: str, article_id: str, *, url: str) -> None:
    """Refuse to write outside ``{root}/data/raw/wechat/``.

    A backstop behind
    :func:`~finer.ingestion.wechat_public_article.sanitize_path_component`.
    Both identifiers originate in untrusted input — a third-party feed's URL
    query, or ``var`` declarations scraped from a remote page — and both become
    path components. Sanitizing at the source is the fix; this makes a future
    regression in that sanitizer fail loudly instead of writing to disk.
    """
    base = (root / "data" / "raw" / "wechat").resolve()
    target = (base / account_id / f"{article_id}.md").resolve()
    if base not in target.parents:
        raise FinerError(
            ErrorCode.F0_IO_001,
            "Refusing to write a WeChat artifact outside the raw archive root",
            stage="F0",
            operation="wechat_article_archive",
            source_channel="wechat",
            retryable=False,
            details={"source_url": url, "account_id": account_id, "article_id": article_id},
        )


def _register_f0_index(record: ContentRecord, receipt: ImportReceipt) -> bool:
    """Best-effort Project Memory registration (idempotent INSERT OR IGNORE).

    A hot-index failure must never lose an import: the raw archive plus
    ContentRecord on disk remain the rebuildable source of truth.
    """
    try:
        from finer.ingestion.f0_index_writer import F0IndexWriter

        F0IndexWriter().record_imported(record, receipt)
        return True
    except Exception as exc:  # pragma: no cover - PM availability is environmental
        logger.warning(
            "Project Memory registration skipped for %s: %s", record.content_id, exc
        )
        return False


def import_article(
    url: str,
    *,
    root: Path = REPO_ROOT,
    discovery_source: str = "manual",
    force: bool = False,
    limiter: Optional[RateLimiter] = None,
    article: Optional[PublicArticle] = None,
    acquired_via: str = "public_url",
    register_index: bool = True,
) -> ArticleImportOutcome:
    """Fetch one public WeChat article and land it as F0 intake.

    Args:
        url: Public ``mp.weixin.qq.com`` article URL.
        root: Repository root; artifacts go under ``{root}/data/raw/wechat/``.
        discovery_source: How this URL was found — stamped into metadata so a
            stale discovery source is auditable.
        force: Re-fetch and overwrite an already-imported article.
        limiter: Rate limiter override; ``None`` keeps the module's paced
            default rather than disabling pacing.
        article: Pre-fetched page, used by tests and by callers that already
            hold the page. Skips the network entirely.
        register_index: Set False to skip Project Memory (tests, dry runs).

    Returns:
        An :class:`ArticleImportOutcome`.
    """
    # Pass the limiter only when the caller set one: fetch_public_article's own
    # default is the shared paced limiter, and forwarding None would silently
    # disable rate limiting for every import that did not name one.
    if article is not None:
        fetched = article
    elif limiter is not None:
        fetched = fetch_public_article(url, limiter=limiter)
    else:
        fetched = fetch_public_article(url)

    if fetched.state is not ArticleState.OK:
        logger.info("Skipping %s — page state is %s", url, fetched.state.value)
        return ArticleImportOutcome(
            status="skipped",
            source_url=url,
            article_state=fetched.state,
            reason=f"page state: {fetched.state.value}",
        )

    if not fetched.has_identity:
        # Better to skip than to invent an id: anything we make up either
        # collides with another article (losing it as a "duplicate") or changes
        # between runs (breaking idempotency).
        logger.warning(
            "Skipping %s — page carries no usable account/article identity", url
        )
        return ArticleImportOutcome(
            status="skipped",
            source_url=url,
            article_state=fetched.state,
            reason="no usable identity (missing account id or mid/idx)",
        )

    store = WeChatArtifactStore(root)
    account_id = fetched.account_id
    article_id = fetched.article_id
    _assert_contained(root, account_id, article_id, url=url)

    # Probe for an existing import before writing anything. content_id is a
    # pure function of (account_id, article_id), so this is a cheap stat, not
    # a directory scan.
    #
    # The probe keys on the *receipt*, which is written last: keying on the
    # record would make an import that died between the two writes look
    # complete forever, leaving a ContentRecord with no receipt that no rerun
    # would ever repair.
    from finer.services.wechat_content_record_builder import _derive_content_id

    content_id = _derive_content_id(account_id, article_id)
    intake_dir = _f0_intake_dir(root)
    record_path = intake_dir / f"{content_id}.json"
    receipt_path = intake_dir / f"{content_id}.receipt.json"
    if receipt_path.exists() and not force:
        logger.info("Article already imported: %s (%s)", content_id, url)
        return ArticleImportOutcome(
            status="duplicate",
            source_url=url,
            content_id=content_id,
            record_path=record_path,
            receipt_path=receipt_path,
            article_state=fetched.state,
            reason="import receipt already on disk",
        )

    artifacts = store.save_article_artifacts(
        account_id=account_id,
        article_id=article_id,
        html=fetched.html,
        markdown=_render_markdown(fetched),
    )

    record = build_public_article_record(
        fetched,
        artifacts,
        acquired_via=acquired_via,
        discovery_source=discovery_source,
    )

    intake_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(record_path, record.model_dump_json(indent=2))

    receipt = _build_receipt(
        record=record,
        record_path=record_path,
        md_path=artifacts.raw_md_path,
        md_sha256=artifacts.md_sha256,
        html_path=artifacts.raw_html_path,
        html_sha256=artifacts.html_sha256,
        acquired_via=acquired_via,
    )
    # Written last, and it is what the duplicate probe keys on, so a crash
    # anywhere above leaves the import visibly incomplete and a rerun redoes it.
    _atomic_write_text(receipt_path, receipt.model_dump_json(indent=2))

    if register_index:
        _register_f0_index(record, receipt)

    synced = store.load_sync_state(account_id)
    synced.add(article_id)
    store.save_sync_state(account_id, synced)

    logger.info("Imported WeChat article %s (%s)", content_id, fetched.title)
    return ArticleImportOutcome(
        status="imported",
        source_url=url,
        content_id=content_id,
        record_path=record_path,
        receipt_path=receipt_path,
        raw_md_path=artifacts.raw_md_path,
        article_state=fetched.state,
        record=record,
    )


def import_discovered(
    discovered: "DiscoveredArticle",
    *,
    root: Path = REPO_ROOT,
    force: bool = False,
    limiter: Optional[RateLimiter] = None,
    register_index: bool = True,
    allow_bridge_content: bool = True,
) -> ArticleImportOutcome:
    """Import one discovered article, fetching from source where possible.

    Direct fetch is always preferred: it archives the page WeChat actually
    served, which is the stronger evidence. When the URL form is unfetchable
    (long-form links, which WeChat challenges unconditionally) this falls back
    to the bridge's own copy of the body, and labels it as such —
    ``acquired_via="bridge_content"`` with the bridge named in
    ``discovery_source``, so no downstream reader can mistake a second-hand
    body for a direct fetch.

    Set ``allow_bridge_content=False`` to require first-hand evidence and skip
    anything that cannot be fetched from source.
    """
    from finer.ingestion.wechat_public_article import parse_bridge_article

    if discovered.fetchable:
        return import_article(
            discovered.url,
            root=root,
            discovery_source=discovered.discovery_source,
            force=force,
            limiter=limiter,
            register_index=register_index,
        )

    if not (allow_bridge_content and discovered.content_html):
        return ArticleImportOutcome(
            status="skipped",
            source_url=discovered.url,
            reason=(
                "long-form URL is not fetchable from WeChat and the bridge "
                "supplied no content"
            ),
        )

    article = parse_bridge_article(
        discovered.content_html,
        discovered.url,
        title=discovered.title,
        account_name=discovered.account_name,
        published_at=discovered.published_at,
    )
    return import_article(
        discovered.url,
        root=root,
        discovery_source=discovered.discovery_source,
        force=force,
        article=article,
        acquired_via="bridge_content",
        register_index=register_index,
    )


def import_discovered_articles(
    discovered: list["DiscoveredArticle"],
    *,
    root: Path = REPO_ROOT,
    force: bool = False,
    limiter: Optional[RateLimiter] = None,
    register_index: bool = True,
    allow_bridge_content: bool = True,
) -> list[ArticleImportOutcome]:
    """Import a batch of discovered articles serially, surviving per-item errors."""
    outcomes: list[ArticleImportOutcome] = []
    for item in discovered:
        try:
            outcomes.append(
                import_discovered(
                    item,
                    root=root,
                    force=force,
                    limiter=limiter,
                    register_index=register_index,
                    allow_bridge_content=allow_bridge_content,
                )
            )
        except Exception as exc:
            logger.error("Import failed for %s: %s", item.url, exc)
            outcomes.append(
                ArticleImportOutcome(status="failed", source_url=item.url, reason=str(exc))
            )
    return outcomes


def _render_markdown(article: PublicArticle) -> str:
    """Render the archived Markdown with a provenance header.

    The header duplicates fields also held in the ContentRecord on purpose: the
    raw archive has to stand alone as evidence if the index is ever rebuilt.
    """
    published = (
        article.published_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if article.published_at
        else "unknown"
    )
    header = [
        f"# {_header_safe(article.title) or 'untitled'}",
        "",
        f"> 公众号：{_header_safe(article.account_name) or article.account_id}",
        f"> 作者：{_header_safe(article.author) or '未知'}",
        f"> 发布时间：{published}",
        f"> 原文链接：{article.source_url}",
        f"> 账号标识：{article.ghid or article.biz}",
        f"> 文章标识：{article.article_id}",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + article.markdown + "\n"


def _header_safe(value: str) -> str:
    """Flatten a value so it cannot forge extra provenance lines.

    Title and account name can come from a third-party feed. A title containing
    a newline plus ``> 原文链接：…`` would otherwise write a second, fake source
    line into the archive that an auditor reads as ours.
    """
    return re.sub(r"\s+", " ", (value or "").replace(">", "＞")).strip()


def import_article_urls(
    urls: list[str],
    *,
    root: Path = REPO_ROOT,
    discovery_source: str = "manual",
    force: bool = False,
    limiter: Optional[RateLimiter] = None,
    register_index: bool = True,
) -> list[ArticleImportOutcome]:
    """Import a batch of article URLs, one at a time, without aborting on error.

    Batch import is deliberately serial: the rate limiter is the thing keeping
    this path un-blocked, and concurrency would defeat it. A per-URL failure is
    logged and recorded as a ``failed`` outcome so one dead link cannot sink a
    whole discovery run.
    """
    outcomes: list[ArticleImportOutcome] = []
    for url in urls:
        try:
            outcomes.append(
                import_article(
                    url,
                    root=root,
                    discovery_source=discovery_source,
                    force=force,
                    limiter=limiter,
                    register_index=register_index,
                )
            )
        except Exception as exc:
            logger.error("Import failed for %s: %s", url, exc)
            outcomes.append(
                ArticleImportOutcome(
                    status="failed", source_url=url, reason=str(exc)
                )
            )
    return outcomes
