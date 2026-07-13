"""Audit Trace API routes.

Read-only endpoints for materializing F3 -> F4 -> F5 trace data for the
dashboard audit view.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from finer.errors import ErrorCode, FinerNotFoundError
from finer.services.audit_assembler import AuditAssembler

router = APIRouter()
_ASSEMBLER = AuditAssembler()


@router.get("/actions")
async def list_audit_actions(
    kol_id: str | None = None,
    ticker: str | None = None,
    trace_status: str | None = Query(None, pattern="^(canonical|partial|non_canonical)$"),
    validation_status: str | None = Query(
        None,
        pattern="^(pending|verified|failed|under_review)$",
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    """Return compact TradeAction rows for the audit action list."""

    data = _ASSEMBLER.list_action_summaries(
        kol_id=kol_id,
        ticker=ticker,
        trace_status=trace_status,
        validation_status=validation_status,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "data": data}


@router.get("/actions/{trade_action_id}/trace")
async def get_audit_trace(trade_action_id: str) -> dict:
    """Return the materialized F3/F4/F5 audit trace bundle for one action."""

    bundle = _ASSEMBLER.get_trace_bundle(trade_action_id)
    if bundle is None:
        raise FinerNotFoundError(
            ErrorCode.API_NTF_001,
            f"TradeAction not found: {trade_action_id}",
            stage="F5_audit",
            operation="get_trace",
            retryable=False,
            details={
                "trade_action_id": trade_action_id,
                "fix_hint": "Check the TradeAction id and data/F5_executed artifacts.",
            },
        )
    return {"ok": True, "data": bundle}
