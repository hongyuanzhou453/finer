"""WeChat Artifact Store — Raw artifact persistence for WeChat articles.

Saves raw HTML, normalized Markdown, and metadata sidecar JSON under
data/raw/wechat/{account_id}/. Tracks incremental sync state to avoid
re-fetching already-synced articles.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ArticleArtifacts:
    """Paths and hashes for a saved article's raw artifacts."""
    raw_html_path: Optional[Path]
    raw_md_path: Path
    html_sha256: Optional[str]
    md_sha256: str
    sidecar_path: Path


class WeChatArtifactStore:
    """Manages raw artifact persistence and incremental sync state."""

    def __init__(self, root: Path):
        self._root = root
        self._raw_dir = root / "data" / "raw" / "wechat"
        self._raw_dir.mkdir(parents=True, exist_ok=True)

    def _account_dir(self, account_id: str) -> Path:
        d = self._raw_dir / account_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_article_artifacts(
        self,
        account_id: str,
        article_id: str,
        html: bytes,
        markdown: str,
    ) -> ArticleArtifacts:
        """Save raw HTML and normalized Markdown artifacts.

        Args:
            account_id: WeChat account ID
            article_id: Article ID
            html: Raw HTML bytes (may be empty if not available)
            markdown: Normalized Markdown content

        Returns:
            ArticleArtifacts with paths and SHA256 hashes
        """
        account_dir = self._account_dir(account_id)

        # Save Markdown
        md_path = account_dir / f"{article_id}.md"
        md_bytes = markdown.encode("utf-8")
        md_path.write_bytes(md_bytes)
        md_sha256 = hashlib.sha256(md_bytes).hexdigest()

        # Save HTML if available
        html_path: Optional[Path] = None
        html_sha256: Optional[str] = None
        if html:
            html_path = account_dir / f"{article_id}.html"
            html_path.write_bytes(html)
            html_sha256 = hashlib.sha256(html).hexdigest()

        # Build metadata sidecar
        sidecar = {
            "article_id": article_id,
            "account_id": account_id,
            "raw_html_path": str(html_path) if html_path else None,
            "raw_md_path": str(md_path),
            "raw_html_sha256": html_sha256,
            "raw_md_sha256": md_sha256,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        sidecar_path = account_dir / f"{article_id}.sidecar.json"
        sidecar_path.write_text(
            json.dumps(sidecar, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(f"Saved artifacts for {account_id}/{article_id}")

        return ArticleArtifacts(
            raw_html_path=html_path,
            raw_md_path=md_path,
            html_sha256=html_sha256,
            md_sha256=md_sha256,
            sidecar_path=sidecar_path,
        )

    def _sync_state_path(self, account_id: str) -> Path:
        return self._account_dir(account_id) / "sync_state.json"

    def load_sync_state(self, account_id: str) -> Set[str]:
        """Load the set of already-synced article IDs for an account."""
        path = self._sync_state_path(account_id)
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return set(data.get("synced_article_ids", []))
        except Exception as e:
            logger.warning(f"Failed to load sync state for {account_id}: {e}")
            return set()

    def save_sync_state(self, account_id: str, synced_ids: Set[str]) -> None:
        """Persist the set of synced article IDs for an account."""
        path = self._sync_state_path(account_id)
        data = {
            "account_id": account_id,
            "synced_article_ids": sorted(synced_ids),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(f"Saved sync state for {account_id}: {len(synced_ids)} articles")
