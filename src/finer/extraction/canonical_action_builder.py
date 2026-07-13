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

from typing import Dict, List, Optional, Tuple

from finer.extraction.action_composer import (
    # Re-exported for backward compatibility: these moved to action_composer,
    # the single canonical TradeAction construction site.
    CanonicalBuildError,
    EmptyEvidenceSpanIdsError,
    MissingExecutionTimingError,
    MissingIntentIdError,
    MissingPolicyIdError,
    build_action_metadata,
    compose_trade_action,
    validate_structured_inputs,
)
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

__all__ = [
    "CanonicalActionBuilder",
    "CanonicalBuildError",
    "EmptyEvidenceSpanIdsError",
    "MissingExecutionTimingError",
    "MissingIntentIdError",
    "MissingPolicyIdError",
    "build_action_metadata",
]


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
        # -- Type guards first (canonical TypeError before touching attrs) --
        validate_structured_inputs(
            intent, policy_mapped_intent, evidence_span_ids, execution_timing
        )

        # -- Map action_hint -> ActionType + status --
        action_type, status, notes = self._resolve_action_chain(
            policy_mapped_intent.action_hint
        )

        # -- Map direction --
        direction = _DIRECTION_MAP.get(intent.direction, TradeDirection.NEUTRAL)

        # -- Delegate assembly to the single canonical constructor --
        return compose_trade_action(
            intent=intent,
            policy_mapped_intent=policy_mapped_intent,
            evidence_span_ids=list(evidence_span_ids),
            execution_timing=execution_timing,
            source=self._build_source(intent),
            target=self._build_target(intent),
            direction=direction,
            action_chain=[
                ActionStep(
                    sequence=1,
                    action_type=action_type,
                    trigger_type=TriggerType.NEWS_EVENT,
                )
            ],
            rationale=self._build_rationale(intent, policy_mapped_intent, action_type),
            effective_trade_at=execution_timing.intent_effective_at,
            validation_status=self._resolve_validation_status(
                status, policy_mapped_intent
            ),
            requires_manual_review=(
                policy_mapped_intent.requires_human_review or status == "under_review"
            ),
            tags=["canonical", "f3-f4-f5"],
            f5_strategy="builder",
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
