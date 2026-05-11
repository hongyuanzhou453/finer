"""F0 Project Memory — startup check contract.

This module defines startup behavior for the F0 SQLite index.
A1 first round: contract only — functions raise NotImplementedError.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from finer.paths import F0_INDEX_DB_PATH
from finer.schemas.f0_index import F0IndexHealth


class F0IndexStartupState(str, Enum):
    """Startup states for F0 index."""
    READY = "ready"
    STALE = "stale"
    MISSING = "missing"
    CORRUPT = "corrupt"


@dataclass
class F0StartupResult:
    """Result of F0 index startup check."""
    state: F0IndexStartupState
    health: F0IndexHealth | None
    message: str
    action_taken: str  # "none" | "loaded" | "background_rebuild_scheduled"


def check_f0_index_on_startup(db_path: Path = F0_INDEX_DB_PATH) -> F0StartupResult:
    """Check F0 index health at startup. NEVER triggers full rebuild synchronously.

    Rules:
    1. If index exists and healthy -> load, return READY
    2. If index exists but stale -> load stale data, schedule background rebuild, return STALE
    3. If index missing -> return MISSING (do NOT scan raw dirs)
    4. If index corrupt -> return CORRUPT (do NOT scan raw dirs)

    This function MUST NOT:
    - Recursively scan data/raw/
    - Walk data/processed/manifests/
    - Block startup for rebuild
    """
    raise NotImplementedError("A1 first round: contract only")


def rebuild_f0_index(db_path: Path = F0_INDEX_DB_PATH, *, background: bool = True) -> str:
    """Rebuild F0 index from manifest files on disk.

    Args:
        db_path: Path to SQLite database
        background: If True, run in background thread and return task_id

    Returns:
        task_id if background, "sync_complete" if synchronous

    This function:
    - Reads all manifest JSONs from data/processed/manifests/
    - Upserts into content_records table
    - Updates index_metadata with rebuild timestamp
    - Does NOT read raw files (manifests are the source)
    """
    raise NotImplementedError("A1 first round: contract only")
