"""Canonical Action Builder — F3 + F4 + F2 Evidence -> F5 TradeAction.

Enforces the canonical F3 -> F4 -> F5 path.  Every TradeAction produced
by this builder carries intent_id, policy_id, evidence_span_ids, and
execution_timing, guaranteeing full lineage from intent through policy
to executable action.

Design Principles:
1. MUST NOT accept raw text — only structured inputs from F2/F3/F4.
2. MUST NOT call the legacy direct extractor.
3. MUST reject inputs when required upstream IDs are missing.
4. Action chain mapping is rule-based (simple lookup), not LLM-driven.
5. Every TradeAction produced has canonical_trace_status == "canonical".

Usage::

    builder = CanonicalActionBuilder()
    ta = builder.build(
        intent=f3_intent,                    # NormalizedInvestmentIntent
        policy_mapped_intent=f4_mapped,      # PolicyMappedIntent
        evidence_span_ids=["span-001"],      # from F2
        execution_timing=timing,             # ExecutionTiming
    )
    assert ta.canonical_trace_status == "canonical"
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import ACTION_HINT_LITERAL, PolicyMappedIntent
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    ExecutionTiming,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
    ValidationStatus,
)


# =============================================================================
# Input Validation Errors
# =============================================================================


class CanonicalBuildError(ValueError):
    """Raised when CanonicalActionBuilder receives invalid inputs.

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
# Action Hint -> (ActionType, ValidationStatus, notes) mapping
# =============================================================================

# Each entry: (ActionType, default_status, default_notes)
_ACTION_HINT_MAP: Dict[str, Tuple[ActionType, str, Optional[str]]] = {
    "consider_buy":        (ActionType.BUY_AND_HOLD, "review", "Pending human review"),
    "consider_sell":       (ActionType.CLOSE_LONG,   "review", "Pending human review"),
    "watch_only":          (ActionType.WATCH,         None,    None),
    "review_required":     (ActionType.WATCH,         "under_review", "Flagged for manual review"),
    "open_position":       (ActionType.LONG,          None,    None),
    "add_position":        (ActionType.ADD,           None,    None),
    "close_position":      (ActionType.CLOSE_LONG,    None,    None),
    # Extended mappings for action_hints not in the primary spec
    "watch_or_no_trade":   (ActionType.WATCH,         None,    None),
    "avoid_or_watch_risk": (ActionType.WATCH,         None,    "Risk avoidance signal"),
    "reduce_position":     (ActionType.REDUCE,        None,    "Partial position reduction"),
    "hold_position":       (ActionType.HOLD,          None,    None),
}

def build_action_metadata(
    intent: NormalizedInvestmentIntent,
    policy_mapped_intent: PolicyMappedIntent,
) -> Dict[str, object]:
    """Collect policy hints and F3 style signals into TradeAction.metadata.

    Shared by CanonicalActionBuilder and pipeline/canonical_runner so every
    F5 construction path carries the same downstream contract. Numeric
    exit-rule hints are only written when present so that F8 per-action
    backtest can distinguish "policy configured" from "fall back to module
    defaults". The F3 trading-style signals feed the KOL trading-style
    profile aggregator and are likewise only written when informative.
    """
    metadata: Dict[str, object] = {
        "action_hint_original": policy_mapped_intent.action_hint,
        "position_sizing_hint": policy_mapped_intent.position_sizing_hint,
        "holding_period_hint": policy_mapped_intent.holding_period_hint,
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


# Map F3 direction to TradeDirection enum
_DIRECTION_MAP: Dict[str, TradeDirection] = {
    "bullish":  TradeDirection.BULLISH,
    "bearish":  TradeDirection.BEARISH,
    "neutral":  TradeDirection.NEUTRAL,
    "mixed":    TradeDirection.NEUTRAL,
    "unknown":  TradeDirection.NEUTRAL,
}


# =============================================================================
# CanonicalActionBuilder
# =============================================================================


class CanonicalActionBuilder:
    """Builds canonical TradeActions through the F3 -> F4 -> F5 path.

    This builder is stateless and safe to reuse.  It accepts only
    structured inputs (Pydantic models + ID lists) and never reads
    raw text or calls legacy extractors.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        intent: NormalizedInvestmentIntent,
        policy_mapped_intent: PolicyMappedIntent,
        evidence_span_ids: List[str],
        execution_timing: ExecutionTiming,
    ) -> TradeAction:
        """Construct a canonical TradeAction from F3 + F4 + F2 + timing.

        Args:
            intent: F3 NormalizedInvestmentIntent (provides target, direction,
                    intent_id, creator, confidence).
            policy_mapped_intent: F4 PolicyMappedIntent (provides policy_id,
                    action_hint, sizing/holding hints).
            evidence_span_ids: F2 evidence span IDs.  MUST be non-empty.
            execution_timing: Structured timing from the timing policy.

        Returns:
            TradeAction with canonical_trace_status == "canonical".

        Raises:
            MissingIntentIdError: if intent.intent_id is empty.
            MissingPolicyIdError: if policy_mapped_intent.policy_id is empty.
            EmptyEvidenceSpanIdsError: if evidence_span_ids is empty.
            MissingExecutionTimingError: if execution_timing is None.
            TypeError: if any argument is the wrong type.
        """
        # -- Type guards (reject raw text / wrong types) --
        self._validate_types(intent, policy_mapped_intent, evidence_span_ids, execution_timing)

        # -- Required-field validation --
        self._validate_required_fields(intent, policy_mapped_intent, evidence_span_ids, execution_timing)

        # -- Map action_hint -> ActionType + status --
        action_type, status, notes = self._resolve_action_chain(
            policy_mapped_intent.action_hint
        )

        # -- Map direction --
        direction = _DIRECTION_MAP.get(intent.direction, TradeDirection.NEUTRAL)

        # -- Build SourceInfo --
        source = self._build_source(intent)

        # -- Build TargetInfo --
        target = self._build_target(intent)

        # -- Build ActionStep --
        action_step = ActionStep(
            sequence=1,
            action_type=action_type,
            trigger_type=TriggerType.NEWS_EVENT,
        )

        # -- Determine validation status --
        validation_status = self._resolve_validation_status(
            status, policy_mapped_intent
        )

        # -- Build TradeAction --
        ta = TradeAction(
            # Canonical trace fields (F3 -> F4 -> F5 chain)
            intent_id=intent.intent_id,
            policy_id=policy_mapped_intent.policy_id,
            evidence_span_ids=list(evidence_span_ids),
            # Timing
            effective_trade_at=execution_timing.intent_effective_at,
            execution_timing=execution_timing,
            # Core fields
            source=source,
            target=target,
            direction=direction,
            action_chain=[action_step],
            # Confidence: use the lower of intent and policy confidence
            confidence=min(intent.confidence, policy_mapped_intent.mapping_confidence),
            # KOL belief strength, distinct from extraction confidence
            conviction=intent.conviction,
            # Validation
            validation_status=validation_status,
            requires_manual_review=(
                policy_mapped_intent.requires_human_review
                or status == "under_review"
            ),
            # Rationale
            rationale=self._build_rationale(intent, policy_mapped_intent, action_type),
            # Store policy hints in metadata for downstream consumers
            metadata=self._build_metadata(intent, policy_mapped_intent),
            tags=["canonical", "f3-f4-f5"],
        )

        # The validator in TradeAction auto-sets canonical_trace_status,
        # but let's assert for safety.
        assert ta.canonical_trace_status == "canonical", (
            f"Internal error: canonical_trade_action should have status 'canonical', "
            f"got '{ta.canonical_trace_status}'"
        )

        return ta

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(
        intent: NormalizedInvestmentIntent,
        policy_mapped_intent: PolicyMappedIntent,
    ) -> Dict[str, object]:
        return build_action_metadata(intent, policy_mapped_intent)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_types(
        intent: object,
        policy_mapped_intent: object,
        evidence_span_ids: object,
        execution_timing: object,
    ) -> None:
        """Reject non-structured inputs (raw strings, dicts, etc.)."""
        if not isinstance(intent, NormalizedInvestmentIntent):
            raise TypeError(
                f"intent must be NormalizedInvestmentIntent, got {type(intent).__name__}. "
                f"CanonicalActionBuilder does NOT accept raw text."
            )
        if not isinstance(policy_mapped_intent, PolicyMappedIntent):
            raise TypeError(
                f"policy_mapped_intent must be PolicyMappedIntent, got {type(policy_mapped_intent).__name__}. "
                f"CanonicalActionBuilder does NOT accept raw text."
            )
        if not isinstance(execution_timing, ExecutionTiming):
            raise TypeError(
                f"execution_timing must be ExecutionTiming, got {type(execution_timing).__name__}. "
                f"CanonicalActionBuilder does NOT accept raw text."
            )
        if not isinstance(evidence_span_ids, list):
            raise TypeError(
                f"evidence_span_ids must be a list of strings, got {type(evidence_span_ids).__name__}."
            )

    @staticmethod
    def _validate_required_fields(
        intent: NormalizedInvestmentIntent,
        policy_mapped_intent: PolicyMappedIntent,
        evidence_span_ids: List[str],
        execution_timing: ExecutionTiming,
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
        if not evidence_span_ids:
            raise EmptyEvidenceSpanIdsError(
                "evidence_span_ids must contain at least one F2 EvidenceSpan ID. "
                "Cannot build canonical TradeAction without evidence."
            )
        # execution_timing being None is caught by the type check, but
        # guard against it explicitly for clarity.
        if execution_timing is None:
            raise MissingExecutionTimingError(
                "execution_timing is required. Cannot build canonical TradeAction "
                "without timing information."
            )

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_action_chain(
        action_hint: ACTION_HINT_LITERAL,
    ) -> Tuple[ActionType, Optional[str], Optional[str]]:
        """Map a policy action_hint to (ActionType, status_override, notes).

        Returns:
            Tuple of (ActionType, status_override_or_None, notes_or_None).
            status_override is None when the default PENDING is appropriate.
        """
        entry = _ACTION_HINT_MAP.get(action_hint)
        if entry is None:
            # Unknown action_hint: fall back to WATCH with a warning note
            return (
                ActionType.WATCH,
                "under_review",
                f"Unmapped action_hint '{action_hint}' — defaulting to WATCH",
            )
        return entry

    @staticmethod
    def _resolve_validation_status(
        status_hint: Optional[str],
        policy_mapped_intent: PolicyMappedIntent,
    ) -> ValidationStatus:
        """Determine ValidationStatus from the action mapping and policy."""
        if status_hint == "under_review":
            return ValidationStatus.UNDER_REVIEW
        if status_hint == "review":
            return ValidationStatus.PENDING
        if policy_mapped_intent.requires_human_review:
            return ValidationStatus.UNDER_REVIEW
        return ValidationStatus.PENDING

    @staticmethod
    def _build_source(intent: NormalizedInvestmentIntent) -> SourceInfo:
        """Build SourceInfo from F3 intent.  No raw text accepted."""
        return SourceInfo(
            creator_id=intent.creator_id,
            content_id=intent.envelope_id,
            evidence_text=f"[canonical] intent_id={intent.intent_id}",
        )

    @staticmethod
    def _build_target(intent: NormalizedInvestmentIntent) -> TargetInfo:
        """Build TargetInfo from F3 intent."""
        return TargetInfo(
            ticker=intent.target_symbol or intent.target_name,
            market=intent.market,
            company_name=intent.target_name,
        )

    @staticmethod
    def _build_rationale(
        intent: NormalizedInvestmentIntent,
        policy_mapped_intent: PolicyMappedIntent,
        action_type: ActionType,
    ) -> str:
        """Build a human-readable rationale for the TradeAction."""
        target = intent.target_symbol or intent.target_name
        return (
            f"Canonical F3->F4->F5: "
            f"intent '{intent.direction}' on {target} "
            f"(actionability={intent.actionability}, "
            f"position_delta_hint={intent.position_delta_hint}) "
            f"| policy action_hint={policy_mapped_intent.action_hint} "
            f"-> ActionType.{action_type.value} "
            f"| sizing={policy_mapped_intent.position_sizing_hint}, "
            f"holding={policy_mapped_intent.holding_period_hint}"
        )
