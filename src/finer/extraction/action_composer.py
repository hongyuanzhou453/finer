"""Single canonical TradeAction constructor (F5 truth source).

Every production path that materializes a TradeAction MUST go through
:func:`compose_trade_action` — pipeline/canonical_runner (programmatic and
LLM-guided F5) and CanonicalActionBuilder (golden path / acceptance scripts)
all delegate here. The composer owns:

- the canonical-trace invariants (intent_id / policy_id / evidence /
  execution_timing present, canonical_trace_status == "canonical"),
- the shared metadata contract (:func:`build_action_metadata` — exit-rule
  hints + F3 trading-style signals),
- the version stamp (model_version / extraction_method / version_info),
  closing the "actions carry no pipeline version" gap that blocked F8
  settle attribution and RLHF feedback anchoring.

It deliberately does NOT own per-path field policy: callers resolve their
own direction rules, evidence text, rationale wording, trigger types, etc.
and pass the results in. What is unified is the construction site and its
invariants, not every field's derivation. `tests/test_single_constructor.py`
pins this: no other module may call `TradeAction(` directly.

History: the runner used to hand-roll TradeAction construction and silently
drifted from the builder twice (ADD/REDUCE collapse, dropped style/exit
metadata — see docs/specs/2026-07-10-f5-style-metadata-repair.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent
from finer.schemas.trade_action import (
    ActionStep,
    ExecutionTiming,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    ValidationStatus,
)
from finer.services.versioning import VersionManager


# =============================================================================
# Input Validation Errors
# =============================================================================


class CanonicalBuildError(ValueError):
    """Raised when the composer receives invalid inputs.

    Subclasses distinguish specific rejection reasons for callers that
    need to handle different failure modes programmatically.
    """


class MissingIntentIdError(CanonicalBuildError):
    """NormalizedInvestmentIntent.intent_id is missing or empty."""


class MissingPolicyIdError(CanonicalBuildError):
    """PolicyMappedIntent.policy_id is missing or empty."""


class EmptyEvidenceSpanIdsError(CanonicalBuildError):
    """evidence_span_ids is empty — at least one F2 span is required."""


class MissingExecutionTimingError(CanonicalBuildError):
    """execution_timing is None."""


# =============================================================================
# Shared metadata contract
# =============================================================================


def derive_signal_class(intent: NormalizedInvestmentIntent) -> str:
    """Classify an action by signal kind from the intent's actionability.

    ``actionability == "recommendation"`` is the canonical marker for a
    declarative institutional rating (broker research) — see
    ``policy/global_base.py`` recommendation branch. Everything else is a KOL's
    own trading statement. This structured derivation replaces re-parsing the
    free-text institutional marker out of policy risk_notes (C7).
    """
    return "broker_recommendation" if intent.actionability == "recommendation" else "kol_statement"


def build_action_metadata(
    intent: NormalizedInvestmentIntent,
    policy_mapped_intent: PolicyMappedIntent,
) -> Dict[str, object]:
    """Collect policy hints and F3 style signals into TradeAction.metadata.

    Shared by every F5 construction path so the downstream contract is
    identical everywhere. Numeric exit-rule hints are only written when
    present so that F8 per-action backtest can distinguish "policy
    configured" from "fall back to module defaults". The F3 trading-style
    signals feed the KOL trading-style profile aggregator and are likewise
    only written when informative.
    """
    metadata: Dict[str, object] = {
        "action_hint_original": policy_mapped_intent.action_hint,
        "position_sizing_hint": policy_mapped_intent.position_sizing_hint,
        "holding_period_hint": policy_mapped_intent.holding_period_hint,
        # Carry the signal classification into metadata too, so audit tools that
        # read metadata (not just the top-level field) see the institutional marker.
        "signal_class": derive_signal_class(intent),
    }
    if policy_mapped_intent.stop_loss_pct_hint is not None:
        metadata["stop_loss_pct"] = policy_mapped_intent.stop_loss_pct_hint
    if policy_mapped_intent.take_profit_pct_hint is not None:
        metadata["take_profit_pct"] = policy_mapped_intent.take_profit_pct_hint
    if policy_mapped_intent.max_holding_days_hint is not None:
        metadata["max_holding_days"] = policy_mapped_intent.max_holding_days_hint
    if intent.margin_flag is not None:
        metadata["margin_flag"] = intent.margin_flag
    if intent.leverage_flag is not None:
        metadata["leverage_flag"] = intent.leverage_flag
    if intent.entry_timing_style != "unknown":
        metadata["entry_timing_style"] = intent.entry_timing_style
    return metadata


# =============================================================================
# Composer
# =============================================================================

_VERSION_MANAGER = VersionManager()


def compose_trade_action(
    *,
    # -- canonical trace (invariants enforced here) --
    intent: NormalizedInvestmentIntent,
    policy_mapped_intent: PolicyMappedIntent,
    evidence_span_ids: List[str],
    execution_timing: ExecutionTiming,
    # -- path-resolved structural parts (per-path policy stays with callers) --
    source: SourceInfo,
    target: TargetInfo,
    direction: TradeDirection,
    action_chain: List[ActionStep],
    rationale: str,
    # -- divergent fields (defaults == CanonicalActionBuilder behaviour) --
    confidence: Optional[float] = None,
    conviction: Optional[float] = None,
    effective_trade_at: Optional[datetime] = None,
    validation_status: Optional[ValidationStatus] = None,
    requires_manual_review: bool = False,
    time_horizon: Optional[str] = None,
    tags: Optional[List[str]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    # Empty evidence is only legal when the caller's F2 gate already ran and
    # the envelope genuinely has no F2 index (runner behaviour). The builder
    # keeps the strict default.
    allow_empty_evidence: bool = False,
    # -- version stamp --
    extractor_version: Optional[str] = None,
    extraction_method: str = "llm",
    f5_strategy: Optional[str] = None,
) -> TradeAction:
    """Assemble the one true canonical TradeAction.

    Raises:
        TypeError: on non-structured inputs (raw text can never sneak in).
        MissingIntentIdError / MissingPolicyIdError /
        EmptyEvidenceSpanIdsError / MissingExecutionTimingError: on broken
        canonical trace inputs.
    """
    validate_structured_inputs(
        intent, policy_mapped_intent, evidence_span_ids, execution_timing
    )
    _validate_required_fields(
        intent,
        policy_mapped_intent,
        evidence_span_ids,
        allow_empty_evidence=allow_empty_evidence,
    )

    metadata: Dict[str, Any] = build_action_metadata(intent, policy_mapped_intent)
    if extra_metadata:
        metadata.update(extra_metadata)

    version_info = _VERSION_MANAGER.create_version_info(
        model_name=extractor_version or "unassigned",
        prompt_template="",
        temperature=0.0,
        additional_params={
            "f5_strategy": f5_strategy,
            "extraction_method": extraction_method,
        },
    )

    kwargs: Dict[str, Any] = {
        "intent_id": intent.intent_id,
        "policy_id": policy_mapped_intent.policy_id,
        "signal_class": derive_signal_class(intent),
        "evidence_span_ids": list(evidence_span_ids),
        "effective_trade_at": effective_trade_at,
        "execution_timing": execution_timing,
        "source": source,
        "target": target,
        "direction": direction,
        "action_chain": action_chain,
        "confidence": (
            confidence
            if confidence is not None
            else min(intent.confidence, policy_mapped_intent.mapping_confidence)
        ),
        "conviction": conviction if conviction is not None else intent.conviction,
        "requires_manual_review": requires_manual_review,
        "rationale": rationale,
        "metadata": metadata,
        "tags": tags if tags is not None else [],
        "extraction_method": extraction_method,
        "version_info": version_info,
    }
    if validation_status is not None:
        kwargs["validation_status"] = validation_status
    if time_horizon is not None:
        kwargs["time_horizon"] = time_horizon
    # model_version keeps its schema default ("v1.0") when the caller has no
    # real extractor version — an honest "unstamped" marker for legacy tests.
    if extractor_version is not None:
        kwargs["model_version"] = extractor_version

    ta = TradeAction(**kwargs)

    # With evidence present the trace must be fully canonical; an (explicitly
    # allowed) empty evidence list is honestly "partial" per the schema
    # validator — never anything weaker.
    expected_status = "canonical" if evidence_span_ids else "partial"
    assert ta.canonical_trace_status == expected_status, (
        f"Internal error: composed action should have status "
        f"'{expected_status}', got '{ta.canonical_trace_status}'"
    )
    return ta


# =============================================================================
# Validation helpers
# =============================================================================


def validate_structured_inputs(
    intent: object,
    policy_mapped_intent: object,
    evidence_span_ids: object,
    execution_timing: object,
) -> None:
    """Reject non-structured inputs (raw strings, dicts, etc.).

    Public so that delegating callers (CanonicalActionBuilder, runner) can
    fail fast with the canonical TypeError before deriving path-specific
    fields from the inputs.
    """
    if not isinstance(intent, NormalizedInvestmentIntent):
        raise TypeError(
            f"intent must be NormalizedInvestmentIntent, got {type(intent).__name__}. "
            f"The canonical composer does NOT accept raw text."
        )
    if not isinstance(policy_mapped_intent, PolicyMappedIntent):
        raise TypeError(
            f"policy_mapped_intent must be PolicyMappedIntent, "
            f"got {type(policy_mapped_intent).__name__}. "
            f"The canonical composer does NOT accept raw text."
        )
    if not isinstance(execution_timing, ExecutionTiming):
        raise TypeError(
            f"execution_timing must be ExecutionTiming, "
            f"got {type(execution_timing).__name__}. "
            f"The canonical composer does NOT accept raw text."
        )
    if not isinstance(evidence_span_ids, list):
        raise TypeError(
            f"evidence_span_ids must be a list of strings, "
            f"got {type(evidence_span_ids).__name__}."
        )


def _validate_required_fields(
    intent: NormalizedInvestmentIntent,
    policy_mapped_intent: PolicyMappedIntent,
    evidence_span_ids: List[str],
    *,
    allow_empty_evidence: bool,
) -> None:
    """Reject when required upstream IDs are missing."""
    if not intent.intent_id:
        raise MissingIntentIdError(
            "NormalizedInvestmentIntent.intent_id is required for canonical trace. "
            "Cannot build canonical TradeAction without F3 intent_id."
        )
    if not policy_mapped_intent.policy_id:
        raise MissingPolicyIdError(
            "PolicyMappedIntent.policy_id is required for canonical trace. "
            "Cannot build canonical TradeAction without F4 policy_id."
        )
    if not evidence_span_ids and not allow_empty_evidence:
        raise EmptyEvidenceSpanIdsError(
            "evidence_span_ids must contain at least one F2 EvidenceSpan ID. "
            "Cannot build canonical TradeAction without evidence."
        )
