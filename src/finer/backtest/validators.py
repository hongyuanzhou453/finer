"""Canonical TradeAction validators for the F8 backtest pipeline.

Extracted from api/routes/backtest.py so that the same validation logic
is reusable across the API layer, E2E scripts, and tests.
"""

from __future__ import annotations

from typing import Any, Dict, List

from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError


def validate_canonical_action(action: Dict[str, Any], index: int) -> None:
    """Validate that a TradeAction dict satisfies canonical requirements.

    Canonical TradeActions must have:
    - intent_id (non-empty string)
    - policy_id (non-empty string)
    - evidence_span_ids (list with len >= 1)
    - execution_timing.action_executable_at (non-null)

    Raises FinerError(F8_IN_001) on validation failure.
    """
    errors: List[str] = []

    intent_id = action.get("intent_id")
    if not intent_id:
        errors.append("missing intent_id")

    policy_id = action.get("policy_id")
    if not policy_id:
        errors.append("missing policy_id")

    evidence_span_ids = action.get("evidence_span_ids")
    if not evidence_span_ids or not isinstance(evidence_span_ids, list) or len(evidence_span_ids) < 1:
        errors.append("missing or empty evidence_span_ids")

    execution_timing = action.get("execution_timing")
    if not execution_timing or not isinstance(execution_timing, dict):
        errors.append("missing execution_timing")
    elif not execution_timing.get("action_executable_at"):
        errors.append("missing execution_timing.action_executable_at")

    if errors:
        raise FinerError(
            ErrorCode.F8_IN_001,
            f"TradeAction[{index}] is not canonical: {'; '.join(errors)}. "
            "Canonical TradeActions must have intent_id, policy_id, "
            "evidence_span_ids (len>=1), and execution_timing.action_executable_at.",
            stage="F8",
            operation="validate_canonical_action",
            retryable=False,
            details={"action_index": index, "trade_action_id": action.get("trade_action_id")},
        )
