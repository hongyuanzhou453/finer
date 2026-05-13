"""Backtest result persistence — JSON serialization to data/backtests/.

Storage layout:
    data/backtests/
    ├── {backtest_id}.json          — full BacktestResult
    └── index.json                  — chronological index of all runs

Each result JSON includes:
- run metadata (id, timestamp, config)
- performance metrics
- trade list
- portfolio snapshots (optional, can be large)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from finer.paths import DATA_ROOT

logger = logging.getLogger(__name__)

BACKTESTS_DIR = DATA_ROOT / "F8_metrics"


def _ensure_dir() -> None:
    BACKTESTS_DIR.mkdir(parents=True, exist_ok=True)


def _index_path() -> Path:
    return BACKTESTS_DIR / "index.json"


def _load_index() -> List[Dict[str, Any]]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(index: List[Dict[str, Any]]) -> None:
    _ensure_dir()
    _index_path().write_text(
        json.dumps(index, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def save_backtest_result(
    result_dict: Dict[str, Any],
    *,
    include_snapshots: bool = False,
) -> Path:
    """Save a BacktestResult dict to JSON and update the index.

    Args:
        result_dict: Serialized BacktestResult (model_dump(mode='json')).
        include_snapshots: Whether to include portfolio_snapshots in the file.
            Snapshots can be large; omit for index-only storage.

    Returns:
        Path to the saved JSON file.
    """
    _ensure_dir()

    backtest_id = result_dict.get("backtest_id", "unknown")
    file_path = BACKTESTS_DIR / f"{backtest_id}.json"

    # Optionally strip snapshots to save space
    save_dict = dict(result_dict)
    if not include_snapshots:
        save_dict.pop("portfolio_snapshots", None)

    file_path.write_text(
        json.dumps(save_dict, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Backtest result saved: %s", file_path)

    # Update index
    index_entry = {
        "backtest_id": backtest_id,
        "start_date": result_dict.get("start_date"),
        "end_date": result_dict.get("end_date"),
        "run_timestamp": result_dict.get("run_timestamp"),
        "total_return": result_dict.get("total_return"),
        "sharpe_ratio": result_dict.get("sharpe_ratio"),
        "max_drawdown": result_dict.get("max_drawdown"),
        "total_trades": result_dict.get("total_trades"),
        "file": str(file_path.name),
    }

    index = _load_index()
    # Deduplicate by backtest_id
    index = [e for e in index if e.get("backtest_id") != backtest_id]
    index.append(index_entry)
    _save_index(index)

    return file_path


def load_backtest_result(backtest_id: str) -> Optional[Dict[str, Any]]:
    """Load a saved BacktestResult by ID."""
    file_path = BACKTESTS_DIR / f"{backtest_id}.json"
    if not file_path.exists():
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load backtest %s: %s", backtest_id, e)
        return None


def list_backtest_results() -> List[Dict[str, Any]]:
    """List all saved backtest results (from index)."""
    return _load_index()
