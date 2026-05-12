"""Shared utilities for file/asset routes — constants, caching, formatting, I/O helpers."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import os
import logging
import re
import time
import hashlib
from functools import lru_cache
from finer.schemas.contract import AssetFile, SourceType
from finer.config import load_feishu_config
from finer.paths import REPO_ROOT, DATA_ROOT
from datetime import datetime

logger = logging.getLogger(__name__)

# Import performance tracking
try:
    from finer.services.performance import PerformanceTracker
    _PERF_TRACKER_AVAILABLE = True
except ImportError:
    _PERF_TRACKER_AVAILABLE = False

WORKFLOW_BY_TIER = {
    # F-stage canonical keys
    "F0": "intake",
    "F1": "library",       # Standardize (merged L2 library + L3 parsing)
    "F2": "enrichment",    # Anchor
    "F5": "extraction",    # Execute
    "F6": "review",
    "F8": "backtest",
    # Legacy L-tier keys (backward compat, deprecated)
    "L0": "intake",
    "L1": "enrichment",
    "L2": "library",
    "L3": "parsing",
    "L5": "extraction",
    "L6": "review",
    "L8": "backtest",
}

STAGE_BADGE_BY_WORKFLOW = {
    "intake": "F0",
    "enrichment": "F2",
    "library": "F1",
    "parsing": "F1",
    "extraction": "F5",
    "review": "F6",
    "backtest": "F8",
}

# Pre-compiled regex for timestamp extraction
_TIMESTAMP_PATTERN = re.compile(r"(\d{8})_(\d{4})")

# Pool directory identifiers (shared with integrations.py)
FEISHU_POOL_NAME = "feishu_sync_pool"
NLM_POOL_NAME = "nlm_sync_pool"

# Cache settings
_CACHE_TTL_SECONDS = 60
_assets_cache: Dict[str, tuple[List[AssetFile], float]] = {}
_manifests_index: Optional[Dict[str, Any]] = None
_index_built_at: float = 0


# ---------------------------------------------------------------------------
# Manifest index management
# ---------------------------------------------------------------------------

def _build_manifests_index() -> Dict[str, Any]:
    """Build a unified index of all manifests for fast lookup."""
    manifest_paths = collect_files_from_directories([
        DATA_ROOT / "processed" / "manifests",
        DATA_ROOT / "L3_aligned" / "manifests",
    ])

    manifests_by_content_id = {}
    manifests_by_source_name = {}

    for mp in manifest_paths:
        data = read_json_file(mp)
        if data and data.get("content_id"):
            manifests_by_content_id[data["content_id"]] = (data, mp)
            src = data.get("raw_path") or data.get("source_path") or data.get("title") or data.get("content_id", "")
            manifests_by_source_name[Path(src).name] = (data, mp)

    return {
        "by_content_id": manifests_by_content_id,
        "by_source_name": manifests_by_source_name,
        "count": len(manifests_by_content_id),
    }


def get_manifests_index() -> Dict[str, Any]:
    """Get manifests index with lazy loading and caching."""
    global _manifests_index, _index_built_at
    now = time.time()

    if _manifests_index is None or (now - _index_built_at > 300):
        # Track file scan performance
        if _PERF_TRACKER_AVAILABLE:
            with PerformanceTracker("file_scan"):
                _manifests_index = _build_manifests_index()
        else:
            _manifests_index = _build_manifests_index()
        _index_built_at = now
        logger.debug("Built manifests index with %d entries", _manifests_index["count"])

    return _manifests_index


# ---------------------------------------------------------------------------
# Source / config helpers
# ---------------------------------------------------------------------------

def _get_source_groups() -> Dict[str, Dict[str, str]]:
    """Lazy-loaded source groups from feishu.yaml config."""
    try:
        config = load_feishu_config(REPO_ROOT)
        return {
            chat["chat_id"]: {
                "name": chat.get("name", "Unknown"),
                "type": "feishu",
                "notebook_id": chat.get("notebook_id", ""),
            }
            for chat in config.get("feishu", {}).get("watched_chats", [])
        }
    except FileNotFoundError:
        logger.debug("feishu.yaml not found, using empty source groups")
        return {}
    except Exception as e:
        logger.warning("Failed to load source groups: %s", e)
        return {}


def get_source_groups() -> Dict[str, Dict[str, str]]:
    """Get source groups with lazy loading."""
    return _get_source_groups()


# ---------------------------------------------------------------------------
# File formatting utilities
# ---------------------------------------------------------------------------

def format_file_size(file_path: Path) -> str:
    try:
        size = file_path.stat().st_size
    except OSError:
        return "--"
    mb = size / 1024 / 1024
    if mb < 0.01:
        return f"{max(1, round(size / 1024))} KB"
    return f"{mb:.2f} MB"


def format_display_name(title: str, content_type: Optional[str] = None) -> str:
    """Format file name for better readability.

    This is the legacy format kept for backward compatibility.
    For new code, prefer build_display_info() which returns structured fields.
    """
    if not title:
        return title

    # Pattern 1: chat_history_YYYYMMDD_HHMM_to_YYYYMMDD_HHMM
    chat_pattern = re.match(
        r'chat_history_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})_to_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})',
        title
    )
    if chat_pattern:
        _, m1, d1, h1, min1, _, m2, d2, h2, min2 = chat_pattern.groups()
        return f"聊天记录 ({m1}-{d1} {h1}:{min1} 至 {m2}-{d2} {h2}:{min2})"

    # Pattern 2: chat_history_YYYYMMDD_HHMM (single timestamp)
    chat_single = re.match(
        r'chat_history_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})',
        title
    )
    if chat_single:
        _, m, d, h, min = chat_single.groups()
        return f"聊天记录 ({m}-{d} {h}:{min})"

    # Pattern 3: Feishu image pattern YYYYMMDD_HHMM_img_v3_...
    img_pattern = re.match(
        r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})_img_',
        title
    )
    if img_pattern:
        _, m, d, h, min = img_pattern.groups()
        return f"图片 ({m}-{d} {h}:{min})"

    # Pattern 4: Date prefix YYYYMMDD_ or YYYY-MM-DD
    date_prefix = re.match(
        r'(\d{4})-?(\d{2})-?(\d{2})[_\s](.+)',
        title
    )
    if date_prefix:
        y, m, d, rest = date_prefix.groups()
        rest = re.sub(r'\.[^.]+$', '', rest)
        if len(rest) > 30:
            rest = rest[:30] + '...'
        return f"{m}-{d} {rest}"

    # Default: remove extension and truncate
    name = re.sub(r'\.[^.]+$', '', title)
    if len(name) > 40:
        name = name[:40] + '...'
    return name


def file_type_for(file_path: str) -> str:
    ext = Path(file_path).suffix.replace(".", "").lower()
    return ext or "file"


# ---------------------------------------------------------------------------
# Semantic title generation (LLM-powered)
# ---------------------------------------------------------------------------

# In-memory cache: content_hash → (title, timestamp)
_semantic_title_cache: Dict[str, tuple[str, float]] = {}
_SEMANTIC_TITLE_TTL = 3600  # 1 hour


def _content_hash(text: str) -> str:
    """Stable hash for cache key, truncated to 16 hex chars."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def generate_semantic_title(text: str) -> str:
    """Generate a short semantic title for file content via LLM.

    Falls back to empty string on any failure. Results are cached by
    content hash to avoid redundant LLM calls.

    Args:
        text: File content to summarize. Will be truncated to ~2000 chars
              for prompt length control.

    Returns:
        A 10-15 character Chinese title, or empty string on failure.
    """
    if not text or not text.strip():
        return ""

    # Check cache
    cache_key = _content_hash(text)
    now = time.time()

    if cache_key in _semantic_title_cache:
        cached_title, cached_time = _semantic_title_cache[cache_key]
        if now - cached_time < _SEMANTIC_TITLE_TTL:
            return cached_title

    # Truncate content to avoid oversized prompts
    truncated = text.strip()[:2000]

    try:
        from finer.llm import LLMClient

        client = LLMClient.auto()
        if not client:
            logger.debug("No LLM client available for semantic title generation")
            return ""

        prompt = (
            "请用10-15个字概括以下内容的主题，不要包含时间信息：\n\n"
            f"{truncated}\n\n"
            "只输出标题，不要其他内容。"
        )
        result = client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50,
        )
        if not result:
            return ""

        title = result.strip().strip("\"'")

        # Basic sanity: reject obviously bad outputs
        if len(title) > 30 or len(title) < 2:
            logger.warning("Semantic title out of expected length range: %r", title)
            return ""

        # Cache result
        _semantic_title_cache[cache_key] = (title, now)
        return title

    except Exception:
        logger.debug("Failed to generate semantic title", exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# File type classification for display
# ---------------------------------------------------------------------------

_FILE_TYPE_DISPLAY_MAP: Dict[str, str] = {
    "png": "图片", "jpg": "图片", "jpeg": "图片", "gif": "图片",
    "webp": "图片", "bmp": "图片", "svg": "图片",
    "pdf": "PDF",
    "doc": "文档", "docx": "文档", "xls": "文档", "xlsx": "文档",
    "ppt": "文档", "pptx": "文档",
    "txt": "文本", "md": "文本", "json": "文本", "csv": "文本",
    "yaml": "文本", "yml": "文本",
}


def classify_file_type(
    extension: Optional[str],
    is_chat_export: bool = False,
) -> str:
    """Return a display-friendly file type label.

    Args:
        extension: File extension without dot (e.g. 'pdf', 'png').
        is_chat_export: Whether the file is a chat export record.

    Returns:
        Chinese label: '聊天记录', '图片', 'PDF', '文档', '文本', or '文件'.
    """
    if is_chat_export:
        return "聊天记录"
    if not extension:
        return "文件"
    return _FILE_TYPE_DISPLAY_MAP.get(extension.lower(), "文件")


def _is_chat_export(file_name: str, content_text: Optional[str] = None) -> bool:
    """Heuristic to detect if a file is a chat export record."""
    name_lower = file_name.lower()
    if "聊天记录" in name_lower or "chat" in name_lower or "chat_history" in name_lower:
        return True
    if content_text:
        head = content_text[:500]
        chat_markers = ["聊天记录", "群聊", "消息记录"]
        if any(marker in head for marker in chat_markers):
            return True
    return False


# ---------------------------------------------------------------------------
# Source name extraction
# ---------------------------------------------------------------------------

def extract_source_name(
    file_name: str,
    source_group_name: Optional[str] = None,
) -> str:
    """Extract a human-readable source name.

    Prefers source_group_name (e.g. feishu chat name) when available.
    Otherwise derives from file_name by stripping timestamps and extensions.
    """
    if source_group_name:
        return source_group_name

    name = file_name
    name = re.sub(r"\.[^.]+$", "", name)               # strip extension
    name = re.sub(r"^\d{4}[-_]?\d{2}[-_]?\d{2}[\s_]*", "", name)  # strip leading date
    name = re.sub(r"[-_]\d{6}$", "", name)              # strip trailing HHMMSS
    name = name.replace("_", " ").strip()

    return name if name else file_name


# ---------------------------------------------------------------------------
# Structured display info builder (new)
# ---------------------------------------------------------------------------

def build_display_info(
    file_name: str,
    extension: Optional[str] = None,
    source_group_name: Optional[str] = None,
    content_text: Optional[str] = None,
    enable_semantic_title: bool = True,
) -> Dict[str, Any]:
    """Build all display-related fields for an asset file.

    Combines legacy format_display_name with semantic classification and
    optional LLM title generation.

    Args:
        file_name: Raw file name.
        extension: File extension (no dot).
        source_group_name: Named source (e.g. feishu chat title).
        content_text: File content for LLM title generation.
        enable_semantic_title: Whether to call LLM for semantic title.
            Set to False for bulk operations or when content is unavailable.

    Returns:
        Dict with keys: fileType, sourceName, semanticTitle, displayName.
    """
    # Legacy display name (always available as fallback)
    display_name = format_display_name(file_name, extension)

    # File type classification
    is_chat = _is_chat_export(file_name, content_text)
    file_type = classify_file_type(extension, is_chat_export=is_chat)

    # Source name
    source_name = extract_source_name(file_name, source_group_name)

    # Semantic title (best-effort, may be empty)
    semantic_title = ""
    if enable_semantic_title and content_text:
        semantic_title = generate_semantic_title(content_text)

    return {
        "displayName": display_name,
        "fileType": file_type,
        "sourceName": source_name,
        "semanticTitle": semantic_title,
    }


# ---------------------------------------------------------------------------
# Generic I/O helpers
# ---------------------------------------------------------------------------

def read_json_file(file_path: Path) -> Optional[Any]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def read_preview(file_path: Optional[Path], max_length=240) -> str:
    if not file_path or not file_path.exists():
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        text = " ".join(text.split()).strip()
        return text[:max_length]
    except Exception:
        return ""


def build_match_tokens(content_id: str, title: Optional[str] = None, source_path: Optional[str] = None) -> List[str]:
    stem = Path(source_path).stem if source_path else ""
    raw_tokens = [content_id, title or "", stem]
    return [t.lower() for t in raw_tokens if t]


def first_matching_path(paths: List[Path], tokens: List[str]) -> Optional[Path]:
    for candidate in paths:
        base = candidate.name.lower()
        if any(base in token or token in base for token in tokens):
            return candidate
    return None


def existing_directories(paths: List[Path]) -> List[Path]:
    return [p for p in paths if p.exists() and p.is_dir()]


def collect_files_from_directories(paths: List[Path]) -> List[Path]:
    results = []
    for d in existing_directories(paths):
        for root, dirs, files in os.walk(d):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if not f.startswith('.'):
                    results.append(Path(root) / f)
    return results


# ---------------------------------------------------------------------------
# Manifest metadata extraction
# ---------------------------------------------------------------------------

def extract_source_info(manifest: Optional[Dict], source_path: Optional[str]) -> tuple[SourceType, Optional[str], Optional[str]]:
    """Extract source type, group id and group name from manifest metadata."""
    source_platform = manifest.get("source_platform", "unknown") if manifest else "unknown"
    metadata = manifest.get("metadata", {}) if manifest else {}

    source_type: SourceType = "unknown"
    group_id = None
    group_name = None

    # Normalize platform aliases
    if source_platform == "nlm":
        source_platform = "notebooklm"

    feishu_chat_id = metadata.get("feishu_chat_id")
    if feishu_chat_id or source_platform == "feishu":
        source_type = "feishu"
        if feishu_chat_id:
            group_id = feishu_chat_id
            group_info = get_source_groups().get(feishu_chat_id, {})
            group_name = group_info.get("name") or metadata.get("chat_name") or feishu_chat_id

    elif metadata.get("nlm_notebook_id") or source_platform == "notebooklm":
        source_type = "notebooklm"
        group_id = metadata.get("nlm_notebook_id")
        group_name = metadata.get("nlm_notebook_name", group_id)

    elif source_platform == "wechat":
        source_type = "wechat"
        group_id = metadata.get("account_id")
        group_name = metadata.get("account_name", group_id)

    elif source_platform == "bilibili":
        source_type = "bilibili"
        group_id = metadata.get("uploader_id")
        group_name = metadata.get("uploader", group_id)

    elif source_platform in ("manual", "local", "upload") or not feishu_chat_id:
        if source_path:
            if FEISHU_POOL_NAME in source_path:
                source_type = "feishu"
            elif NLM_POOL_NAME in source_path:
                source_type = "notebooklm"
            else:
                source_type = "local"
        else:
            source_type = "local"

    return source_type, group_id, group_name


def extract_file_timestamp(manifest: Optional[Dict], file_path: Optional[Path]) -> Optional[str]:
    """Extract file timestamp from manifest, filename pattern, or file mtime."""
    if manifest and manifest.get("published_at"):
        return manifest["published_at"][:19]

    if file_path and file_path.name:
        match = _TIMESTAMP_PATTERN.match(file_path.name)
        if match:
            date_str, time_str = match.groups()
            try:
                dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M")
                return dt.isoformat()
            except ValueError:
                pass

    if file_path:
        try:
            mtime = file_path.stat().st_mtime
            return datetime.fromtimestamp(mtime).isoformat()
        except OSError:
            pass

    return None


# ---------------------------------------------------------------------------
# Source summary
# ---------------------------------------------------------------------------

def _build_source_summary(assets: List[AssetFile]) -> Dict[str, Any]:
    """Build summary of source groups and counts."""
    source_counts: Dict[str, int] = {"feishu": 0, "notebooklm": 0, "local": 0, "wechat": 0, "bilibili": 0, "unknown": 0}
    group_counts: Dict[str, Dict[str, Any]] = {}

    for a in assets:
        source_counts[a.source_type] = source_counts.get(a.source_type, 0) + 1
        if a.source_group_id:
            if a.source_group_id not in group_counts:
                group_counts[a.source_group_id] = {
                    "id": a.source_group_id,
                    "name": a.source_group_name or a.source_group_id,
                    "type": a.source_type,
                    "fileCount": 0,
                }
            group_counts[a.source_group_id]["fileCount"] += 1

    return {
        "totalBySource": source_counts,
        "sourceGroups": list(group_counts.values()),
    }


# ---------------------------------------------------------------------------
# File name sanitization
# ---------------------------------------------------------------------------

def safe_file_name(value: str) -> str:
    """Sanitize a string for use as a file name. Allows CJK, word chars, dots, hyphens."""
    return re.sub(r'[^\w一-鿿.-]+', '_', value)
