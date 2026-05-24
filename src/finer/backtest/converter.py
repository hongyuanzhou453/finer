"""TradeAction → Backtest Engine record converter.

Bridges F5 TradeAction schema to the dict format expected by
BacktestEngine.run_backtest().

Key mapping:
- TradeAction.timestamp → action['timestamp']
- TradeAction.target.ticker_normalized → action['ticker']
- TradeAction.direction → action['direction']
- TradeAction.action_chain[0].action_type → action['action_type']
- TradeAction.trade_action_id → action['trade_action_id']
- TradeAction.source.creator_id → action['kol_id']
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from finer.schemas.trade_action import TradeAction, TradeDirection, ActionType

logger = logging.getLogger(__name__)

# Map TradeDirection → engine direction string
_DIRECTION_MAP = {
    TradeDirection.BULLISH: "bullish",
    TradeDirection.BEARISH: "bearish",
}

# Map ActionType → engine action_type string
_ACTION_TYPE_MAP = {
    ActionType.LONG: "long",
    ActionType.SHORT: "short",
    ActionType.CLOSE_LONG: "close_long",
    ActionType.CLOSE_SHORT: "close_short",
    ActionType.BUY_CALL: "buy_call",
    ActionType.BUY_PUT: "buy_put",
    ActionType.BUY_AND_HOLD: "long",
}


def trade_action_to_record(action: TradeAction) -> Optional[Dict[str, Any]]:
    """Convert a single TradeAction to backtest engine input format.

    Returns None if the action is not backtestable (neutral, watch, hold, etc.).

    Timing priority for canonical TradeActions:
    1. execution_timing.action_executable_at (canonical path)
    2. effective_trade_at (legacy/partial)
    3. timestamp (fallback)
    """
    # Skip non-actionable directions
    if action.direction not in _DIRECTION_MAP:
        logger.debug("Skipping non-backtestable direction: %s", action.direction)
        return None

    # Get primary action type
    primary = action.get_primary_action()
    if primary is None:
        return None

    action_type = _ACTION_TYPE_MAP.get(primary.action_type)
    if action_type is None:
        logger.debug("Skipping non-backtestable action_type: %s", primary.action_type)
        return None

    # Timing: prefer execution_timing.action_executable_at for canonical actions
    if action.execution_timing and action.execution_timing.action_executable_at:
        ts = action.execution_timing.action_executable_at
    elif action.effective_trade_at:
        ts = action.effective_trade_at
    else:
        ts = action.timestamp

    return {
        "timestamp": ts.isoformat(),
        "ticker": action.normalize_ticker(),
        "direction": _DIRECTION_MAP[action.direction],
        "action_type": action_type,
        "trade_action_id": action.trade_action_id,
        "kol_id": action.source.creator_id,
        # --- trace fields (R4-A) ---
        "intent_id": action.intent_id,
        "policy_id": action.policy_id,
        "evidence_span_ids": action.evidence_span_ids or [],
    }


def trade_actions_to_records(actions: List[TradeAction]) -> List[Dict[str, Any]]:
    """Convert a list of TradeActions to backtest engine input format.

    Filters out non-backtestable actions and logs skipped count.
    """
    records: List[Dict[str, Any]] = []
    skipped = 0

    for action in actions:
        record = trade_action_to_record(action)
        if record is not None:
            records.append(record)
        else:
            skipped += 1

    if skipped:
        logger.info("Converted %d/%d TradeActions to backtest records (skipped %d)",
                     len(records), len(actions), skipped)

    return records


def extract_tickers_from_actions(actions: List[TradeAction]) -> List[str]:
    """Extract unique normalized tickers from TradeAction list."""
    tickers = set()
    for action in actions:
        ticker = action.normalize_ticker()
        if ticker:
            tickers.add(ticker)
    return sorted(tickers)
