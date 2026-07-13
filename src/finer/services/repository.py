"""Repository layer for TradeAction management.

This module provides high-level operations for TradeAction records,
bridging the file-based storage with the SQLite index layer.

Key Design Principles:
1. File system is the authoritative source
2. Repository coordinates file I/O and index updates
3. Supports rebuilding index from files
4. Provides domain-specific query methods
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

from finer.paths import DATA_ROOT
from finer.schemas.trade_action import (
    BacktestResult,
    TradeAction,
    TradeDirection,
    ValidationStatus,
)
from finer.services.storage import DateRange, TradeActionDB
from finer.services.performance import track_performance

logger = logging.getLogger(__name__)

# Serializes read-modify-write cycles on action files (batch wrappers hold
# many sibling actions, so a lost update or torn write hurts more than one).
_WRITE_LOCK = threading.Lock()


@dataclass
class KOLTimeline:
    """Timeline summary for a KOL's trade actions."""
    creator_id: str
    total_actions: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    pending_count: int
    verified_count: int
    date_range: Optional[Dict[str, str]]
    tickers: Set[str] = field(default_factory=set)
    avg_confidence: float = 0.0


class TradeActionRepository:
    """Repository for TradeAction with file + index management.

    This is the primary interface for working with TradeAction records.
    It handles:
    - Reading/writing TradeAction files
    - Maintaining the SQLite index
    - Rebuilding index from files
    - Domain-specific queries
    """

    def __init__(
        self,
        db_path: Path = DATA_ROOT / "cache" / "trade_actions.db",
        action_dir: Path = DATA_ROOT / "F5_executed",
    ):
        """Initialize repository.

        Default action_dir is the canonical F5 tier (data/F5_executed); the
        previous default data/L5_candidate is deprecated L-naming and empty.

        Args:
            db_path: Path to SQLite index database.
            action_dir: Directory containing TradeAction JSON files.
        """
        self.db = TradeActionDB(db_path)
        self.action_dir = action_dir
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self.action_dir.mkdir(parents=True, exist_ok=True)
        self.db.db_path.parent.mkdir(parents=True, exist_ok=True)

    def index_trade_action(self, action: TradeAction, file_path: Optional[str] = None) -> None:
        """Index a TradeAction record.

        This method adds/updates the record in the SQLite index.
        It does NOT write to file - use save() for that.

        Args:
            action: TradeAction to index.
            file_path: Optional path to source file.
        """
        self.db.upsert(action, file_path)

    def save(self, action: TradeAction, file_path: Optional[Path] = None) -> Path:
        """Save a TradeAction to file and index it.

        Args:
            action: TradeAction to save.
            file_path: Optional explicit file path. If not provided,
                      uses action_dir/{ticker}_{timestamp}.action.json.

        Returns:
            Path to saved file.
        """
        if file_path is None:
            # Generate default path
            ticker = (action.target.ticker_normalized or action.target.ticker).upper()
            timestamp_str = action.timestamp.strftime("%Y%m%d_%H%M%S")
            file_path = self.action_dir / f"{ticker}_{timestamp_str}_{action.trade_action_id[:8]}.action.json"

        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(action.to_dict(), f, ensure_ascii=False, indent=2)

        # Update index
        self.index_trade_action(action, str(file_path))

        return file_path

    def load(self, trade_action_id: str) -> Optional[TradeAction]:
        """Load a TradeAction by ID.

        First checks the index for file path, then loads from file.

        Args:
            trade_action_id: ID of the action to load.

        Returns:
            TradeAction instance, or None if not found.
        """
        # Check index for file path
        record = self.db.get_by_id(trade_action_id)
        if record and record.get("file_path"):
            file_path = Path(record["file_path"])
            if file_path.exists():
                try:
                    return self._load_from_file(file_path, trade_action_id)
                except (KeyError, ValueError) as e:
                    # KeyError = stale index (id moved); ValueError incl.
                    # JSONDecodeError = corrupt/invalid file — keep the signal
                    # visible before degrading to a directory scan.
                    logger.warning(
                        "Index points %s at %s but load failed (%s: %s); "
                        "falling back to directory scan",
                        trade_action_id,
                        file_path,
                        type(e).__name__,
                        e,
                    )

        # Fall back to scanning directory (both layouts)
        for file_path in self._iter_action_files():
            try:
                for action in self.load_actions_from_file(file_path):
                    if action.trade_action_id == trade_action_id:
                        return action
            except Exception:
                continue

        return None

    def load_actions_from_file(self, file_path: Path) -> List[TradeAction]:
        """Load every TradeAction stored in a JSON file.

        Supports both persisted layouts:
        - single-action ``*.action.json`` (documented convention, CLAUDE.md §5)
        - batch wrapper ``*_actions.json`` with an ``actions`` list (current
          F5 extractor output)

        Invalid entries are skipped with a warning instead of failing the file.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and isinstance(data.get("actions"), list):
            raw_items = data["actions"]
        else:
            raw_items = [data]

        actions: List[TradeAction] = []
        for item in raw_items:
            try:
                actions.append(TradeAction.from_dict(item))
            except Exception as e:
                logger.warning("Skipping invalid action in %s: %s", file_path, e)
        return actions

    def _iter_action_files(self) -> Iterator[Path]:
        """Yield every action JSON file under action_dir (both layouts)."""
        seen: Set[Path] = set()
        for pattern in ("**/*.action.json", "**/*_actions.json"):
            for file_path in self.action_dir.glob(pattern):
                if file_path not in seen:
                    seen.add(file_path)
                    yield file_path

    def load_all_actions(self) -> List[TradeAction]:
        """Load every TradeAction by scanning action_dir directly.

        Bypasses the SQLite index on purpose — the index is a hot cache and
        may lag behind the files, while aggregate consumers (stats, style
        profiles) need file truth.
        """
        actions: List[TradeAction] = []
        for file_path in self._iter_action_files():
            try:
                actions.extend(self.load_actions_from_file(file_path))
            except Exception as e:
                logger.warning("Skipping unreadable action file %s: %s", file_path, e)
        return actions

    def _load_from_file(
        self, file_path: Path, trade_action_id: Optional[str] = None
    ) -> TradeAction:
        """Load a single TradeAction from a JSON file.

        Batch wrapper files hold many actions, so callers resolving a DB
        record must pass the record's trade_action_id to pick the right one.
        """
        actions = self.load_actions_from_file(file_path)
        if trade_action_id is not None:
            for action in actions:
                if action.trade_action_id == trade_action_id:
                    return action
            raise KeyError(
                f"trade_action_id {trade_action_id} not found in {file_path}"
            )
        if len(actions) == 1:
            return actions[0]
        raise ValueError(
            f"{file_path} holds {len(actions)} actions; trade_action_id required"
        )

    def query_by_kol(
        self,
        kol_id: str,
        date_range: Optional[DateRange] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TradeAction]:
        """Query trade actions by KOL/creator ID.

        Args:
            kol_id: Creator/KOL identifier.
            date_range: Optional date range filter.
            limit: Maximum results.
            offset: Pagination offset.

        Returns:
            List of matching TradeAction instances.
        """
        records = self.db.query(
            creator_id=kol_id,
            date_range=date_range,
            limit=limit,
            offset=offset,
        )

        actions = []
        for record in records:
            if record.get("file_path"):
                try:
                    action = self._load_from_file(
                        Path(record["file_path"]), record["trade_action_id"]
                    )
                    actions.append(action)
                except Exception:
                    continue

        return actions

    def query_by_kols(
        self,
        kol_ids: List[str],
        limit_per_kol: int = 100,
    ) -> Dict[str, List[TradeAction]]:
        """Batch query trade actions for multiple KOLs.

        Single database query for all KOLs, avoiding N+1 pattern.

        Args:
            kol_ids: List of KOL/creator IDs.
            limit_per_kol: Maximum results per KOL.

        Returns:
            Dict mapping kol_id -> list of TradeAction instances.
        """
        records_by_kol = self.db.query_by_kols(kol_ids, limit_per_kol)

        results: Dict[str, List[TradeAction]] = {}
        for kol_id, records in records_by_kol.items():
            actions = []
            for record in records:
                if record.get("file_path"):
                    try:
                        action = self._load_from_file(
                        Path(record["file_path"]), record["trade_action_id"]
                    )
                        actions.append(action)
                    except Exception:
                        continue
            results[kol_id] = actions

        return results

    def query_by_ticker(
        self,
        ticker: str,
        direction: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TradeAction]:
        """Query trade actions by ticker.

        Args:
            ticker: Ticker symbol (will be normalized).
            direction: Optional direction filter.
            limit: Maximum results.
            offset: Pagination offset.

        Returns:
            List of matching TradeAction instances.
        """
        records = self.db.query(
            ticker=ticker,
            direction=direction,
            limit=limit,
            offset=offset,
        )

        actions = []
        for record in records:
            if record.get("file_path"):
                try:
                    action = self._load_from_file(
                        Path(record["file_path"]), record["trade_action_id"]
                    )
                    actions.append(action)
                except Exception:
                    continue

        return actions

    def query_pending_review(self, limit: int = 50) -> List[TradeAction]:
        """Query trade actions pending manual review.

        Args:
            limit: Maximum results.

        Returns:
            List of TradeAction instances requiring review.
        """
        records = self.db.query(
            validation_status="pending",
            limit=limit,
        )

        actions = []
        for record in records:
            # Check requires_manual_review flag
            if record.get("requires_manual_review"):
                if record.get("file_path"):
                    try:
                        action = self._load_from_file(
                        Path(record["file_path"]), record["trade_action_id"]
                    )
                        actions.append(action)
                    except Exception:
                        continue

        return actions

    @track_performance("timeline_query")
    def get_timeline(self, kol_id: str) -> KOLTimeline:
        """Get timeline summary for a KOL.

        Args:
            kol_id: KOL/creator identifier.

        Returns:
            KOLTimeline with statistics.
        """
        stats = self.db.get_timeline_stats(kol_id)

        # Get unique tickers
        records = self.db.query(creator_id=kol_id, limit=1000)
        tickers = {r["ticker_normalized"] for r in records if r.get("ticker_normalized")}

        # Calculate average confidence
        confidences = [r["confidence"] for r in records if r.get("confidence") is not None]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return KOLTimeline(
            creator_id=kol_id,
            total_actions=stats["total_actions"],
            bullish_count=stats["by_direction"].get("bullish", 0),
            bearish_count=stats["by_direction"].get("bearish", 0),
            neutral_count=stats["by_direction"].get("neutral", 0),
            pending_count=stats["by_status"].get("pending", 0),
            verified_count=stats["by_status"].get("verified", 0),
            date_range=stats["date_range"],
            tickers=tickers,
            avg_confidence=avg_conf,
        )

    def rebuild_index(self, batch_size: int = 100) -> Dict[str, int]:
        """Rebuild the SQLite index from all TradeAction files.

        Scans the action directory and reindexes all .action.json files.

        Args:
            batch_size: Number of records to process per transaction.

        Returns:
            Dictionary with stats: indexed, failed, total.
        """
        # Clear existing index
        self.db.clear()

        indexed = 0
        failed = 0

        # Scan both persisted layouts (single .action.json + batch _actions.json)
        action_files = list(self._iter_action_files())
        total = len(action_files)

        for file_path in action_files:
            try:
                for action in self.load_actions_from_file(file_path):
                    self.index_trade_action(action, str(file_path))
                    indexed += 1
            except Exception as e:
                failed += 1
                logger.warning("Failed to index %s: %s", file_path, e)

        # Update metadata
        self.db.set_metadata("last_rebuild", datetime.now().isoformat())
        self.db.set_metadata("total_indexed", str(indexed))

        return {
            "indexed": indexed,
            "failed": failed,
            "total": total,
        }

    def count(
        self,
        creator_id: Optional[str] = None,
        ticker: Optional[str] = None,
        direction: Optional[str] = None,
        validation_status: Optional[str] = None,
        date_range: Optional[DateRange] = None,
    ) -> int:
        """Count trade actions matching filters.

        Args:
            creator_id: Filter by KOL ID.
            ticker: Filter by ticker.
            direction: Filter by direction.
            validation_status: Filter by validation status.
            date_range: Filter by date range.

        Returns:
            Count of matching records.
        """
        return self.db.count(
            creator_id=creator_id,
            ticker=ticker,
            direction=direction,
            validation_status=validation_status,
            date_range=date_range,
        )

    def get_all_kols(self) -> List[str]:
        """Get list of all indexed KOL IDs.

        Returns:
            List of unique creator_id values.
        """
        return self.db.get_distinct_values("creator_id")

    def get_all_tickers(self) -> List[str]:
        """Get list of all indexed tickers.

        Returns:
            List of unique normalized ticker values.
        """
        return self.db.get_distinct_values("ticker_normalized")

    def update_validation_status(
        self,
        trade_action_id: str,
        status: ValidationStatus,
        issues: Optional[List[str]] = None,
    ) -> bool:
        """Update validation status for a trade action.

        Updates the index only. To persist to file, load, modify, and save.

        Args:
            trade_action_id: ID of the action.
            status: New validation status.
            issues: Optional list of validation issues.

        Returns:
            True if updated successfully.
        """
        record = self.db.get_by_id(trade_action_id)
        if not record or not record.get("file_path"):
            return False

        try:
            file_path = Path(record["file_path"])
            with _WRITE_LOCK:
                # Single read; edit only the two keys on the raw item so
                # unknown fields survive (no full to_dict round-trip).
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict) and isinstance(data.get("actions"), list):
                    target = next(
                        (
                            item
                            for item in data["actions"]
                            if item.get("trade_action_id") == trade_action_id
                        ),
                        None,
                    )
                elif data.get("trade_action_id") == trade_action_id:
                    target = data
                else:
                    target = None
                if target is None:
                    return False

                target["validation_status"] = (
                    status.value if hasattr(status, "value") else status
                )
                if issues:
                    target["validation_issues"] = issues

                # Atomic replace: a crash mid-write must not corrupt the
                # authoritative file (batch wrappers hold sibling actions).
                tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, file_path)

                self.index_trade_action(
                    TradeAction.from_dict(target), str(file_path)
                )
            return True
        except Exception:
            logger.warning(
                "update_validation_status failed for %s",
                trade_action_id,
                exc_info=True,
            )
            return False

    def update_backtest_result(
        self,
        trade_action_id: str,
        result: BacktestResult,
    ) -> bool:
        """Write a per-action F8 BacktestResult into the authoritative F5 file.

        Same atomic pattern as update_validation_status: single read, patch only
        the target key on the raw item (unknown fields survive), tmp+fsync+
        os.replace, then reindex. Batch wrappers keep their sibling actions.

        Returns:
            True if updated successfully.
        """
        record = self.db.get_by_id(trade_action_id)
        if not record or not record.get("file_path"):
            return False

        try:
            file_path = Path(record["file_path"])
            with _WRITE_LOCK:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict) and isinstance(data.get("actions"), list):
                    target = next(
                        (
                            item
                            for item in data["actions"]
                            if item.get("trade_action_id") == trade_action_id
                        ),
                        None,
                    )
                elif data.get("trade_action_id") == trade_action_id:
                    target = data
                else:
                    target = None
                if target is None:
                    return False

                target["backtest_result"] = result.model_dump(mode="json")

                tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, file_path)

                self.index_trade_action(
                    TradeAction.from_dict(target), str(file_path)
                )
            return True
        except Exception:
            logger.warning(
                "update_backtest_result failed for %s",
                trade_action_id,
                exc_info=True,
            )
            return False

    def delete(self, trade_action_id: str, delete_file: bool = False) -> bool:
        """Delete a trade action from index and optionally from file.

        Args:
            trade_action_id: ID of the action to delete.
            delete_file: Whether to also delete the source file.

        Returns:
            True if deleted from index.
        """
        record = self.db.get_by_id(trade_action_id)

        if delete_file and record and record.get("file_path"):
            try:
                Path(record["file_path"]).unlink()
            except Exception:
                pass

        return self.db.delete(trade_action_id)


# Singleton instance for convenience (thread-safe)
from functools import lru_cache

@lru_cache(maxsize=1)
def get_repository() -> TradeActionRepository:
    """Get the singleton repository instance (thread-safe)."""
    return TradeActionRepository()
