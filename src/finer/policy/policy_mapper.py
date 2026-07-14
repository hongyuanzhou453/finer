"""Policy Mapper — F4 Intent-to-Policy engine.

Canonical entry point for transforming F3 NormalizedInvestmentIntent
instances into PolicyMappingResult + PolicyMappedIntent pairs.

This mapper:
  - Accepts ONLY NormalizedInvestmentIntent or lists thereof.
  - Outputs ONLY PolicyMappingResult, PolicyMappedIntent, or PolicyMappingBatch.
  - Does NOT call any LLM.
  - Does NOT read raw long-form text.
  - Does NOT generate TradeAction.
  - Does NOT determine actual execution prices.

All mapping is rule-based through the GlobalBasePolicy. Higher layers
(StyleArchetype, RiskPreference, KOLPersona, ContentCorrection) are NOT
yet implemented and will be added in subsequent iterations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

logger = logging.getLogger(__name__)

from finer.schemas.investment_intent import NormalizedInvestmentIntent, IntentBatch
from finer.schemas.policy import (
    ACTION_HINT_LITERAL,
    POSITION_SIZING_HINT_LITERAL,
    HOLDING_PERIOD_HINT_LITERAL,
    PolicyMappingResult,
    PolicyMappedIntent,
    PolicyMappingBatch,
    PolicyRiskConstraints,
    PolicyLayerTrace,
    PolicyDecision,
    PolicyContext,
)

from finer.policy.global_base import GlobalBasePolicy


# =============================================================================
# PolicyMapper
# =============================================================================

class PolicyMapper:
    """F4 Policy Mapper — transforms F3 Intent to F4 policy hints.

    Usage::

        mapper = PolicyMapper()
        result = mapper.map_intent(intent)
        # Or batch:
        batch = mapper.map_batch([intent1, intent2, intent3])

    The mapper is stateless and safe to reuse across multiple intents.
    """

    def __init__(
        self,
        policy: Optional[GlobalBasePolicy] = None,
        context: Optional[PolicyContext] = None,
        style_resolver: Optional[Callable[[str], Optional[str]]] = None,
    ):
        """Initialize the mapper.

        Args:
            policy:  GlobalBasePolicy instance. If None, uses defaults.
            context: Optional PolicyContext with KOL/style/risk info.
                     Currently ignored (only GlobalBase is active).
                     Reserved for future StyleArchetype/KOLPersona layers.
            style_resolver: Optional ``creator_id -> declared entry_style``
                     resolver used to apply per-style exit-rule overrides
                     (``tuning.by_style``). If None, a best-effort KOL-registry
                     lookup is used. Only consulted when the active policy's
                     ``tuning.by_style`` is non-empty, so the default (empty)
                     surface never touches the registry.
        """
        self._policy = policy or GlobalBasePolicy()
        self._context = context
        self._style_resolver = style_resolver

    def _resolve_entry_style(self, creator_id: Optional[str]) -> Optional[str]:
        """Best-effort ``creator_id -> declared entry_style`` (never raises)."""
        if not creator_id:
            return None
        if self._style_resolver is not None:
            try:
                return self._style_resolver(creator_id)
            except Exception:  # noqa: BLE001 — style resolution is best-effort
                return None
        try:
            from finer.services.kol_registry import get_registry

            declared = get_registry().declared_style(creator_id)
            return declared.entry_style if declared else None
        except Exception:  # noqa: BLE001 — registry unavailable → base rules
            return None

    def _apply_style_exit_overlay(
        self,
        risk_constraints: PolicyRiskConstraints,
        intent: NormalizedInvestmentIntent,
    ) -> tuple[PolicyRiskConstraints, Optional[str]]:
        """Overlay per-style exit-rule hints (StyleArchetype-lite).

        Inert unless the active tuning declares ``by_style`` overrides AND the
        intent is position-taking (has exit hints). Returns the (possibly
        overridden) constraints plus the applied style label (or None).
        """
        tuning = getattr(self._policy, "tuning", None)
        if not tuning or not tuning.by_style:
            return risk_constraints, None
        # Non-trade intents carry no exit hints — nothing to tune.
        if risk_constraints.stop_loss_pct_hint is None:
            return risk_constraints, None

        style_label = self._resolve_entry_style(intent.creator_id)
        if not style_label or style_label not in tuning.by_style:
            return risk_constraints, None

        hints = tuning.by_style[style_label]
        overridden = risk_constraints.model_copy(
            update={
                "stop_loss_pct_hint": hints.stop_loss_pct,
                "take_profit_pct_hint": hints.take_profit_pct,
                "max_holding_days_hint": hints.max_holding_days,
                "risk_notes": risk_constraints.risk_notes
                + [f"Exit rules tuned for declared style '{style_label}'"],
            }
        )
        return overridden, style_label

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_intent(self, intent: NormalizedInvestmentIntent) -> PolicyMappingResult:
        """Map a single F3 intent to F4 policy hints.

        Args:
            intent: F3 NormalizedInvestmentIntent.

        Returns:
            PolicyMappingResult with action_hint, position_sizing_hint,
            holding_period_hint, risk_constraints, mapping_rationale,
            and full audit trail.

        Raises:
            TypeError: If intent is not a NormalizedInvestmentIntent.
        """
        if not isinstance(intent, NormalizedInvestmentIntent):
            raise TypeError(
                f"PolicyMapper.map_intent() accepts only NormalizedInvestmentIntent, "
                f"got {type(intent).__name__}"
            )

        return self._map_single(intent)

    def map_batch(
        self,
        intents: List[NormalizedInvestmentIntent],
    ) -> PolicyMappingBatch:
        """Map a batch of F3 intents to F4 policy hints.

        Args:
            intents: List of F3 NormalizedInvestmentIntent instances.

        Returns:
            PolicyMappingBatch containing all PolicyMappingResult and
            PolicyMappedIntent records, with auto-computed statistics.

        Raises:
            TypeError: If any element is not a NormalizedInvestmentIntent.
            ValueError: If intents is empty.
        """
        if not intents:
            raise ValueError("map_batch() requires at least one intent")

        for i, intent in enumerate(intents):
            if not isinstance(intent, NormalizedInvestmentIntent):
                raise TypeError(
                    f"map_batch() item [{i}] is not NormalizedInvestmentIntent, "
                    f"got {type(intent).__name__}"
                )

        mappings: List[PolicyMappingResult] = []
        mapped_intents: List[PolicyMappedIntent] = []

        for intent in intents:
            pmr = self._map_single(intent)
            mappings.append(pmr)
            pmi = self._build_mapped_intent(pmr, intent)
            mapped_intents.append(pmi)

        return PolicyMappingBatch(
            mappings=mappings,
            mapped_intents=mapped_intents,
            policy_version=self._policy.policy_version,
        )

    def map_intent_batch(self, batch: IntentBatch) -> PolicyMappingBatch:
        """Map an IntentBatch container.

        Convenience wrapper around map_batch().

        Args:
            batch: F3 IntentBatch.

        Returns:
            PolicyMappingBatch.
        """
        return self.map_batch(batch.intents)

    # ------------------------------------------------------------------
    # Internal mapping logic
    # ------------------------------------------------------------------

    def _map_single(self, intent: NormalizedInvestmentIntent) -> PolicyMappingResult:
        """Core single-intent mapping logic.

        Steps:
          1. Resolve action_hint from F3 axes.
          2. Compute position_sizing_hint from conviction.
          3. Compute holding_period_hint.
          4. Build risk constraints.
          5. Generate mapping rationale.
          6. Build audit trail (layer_traces).
        """
        policy = self._policy

        # --- Step 1: Action hint ---
        action_hint = policy.lookup_action_hint(
            actionability=intent.actionability,
            direction=intent.direction,
            position_delta_hint=intent.position_delta_hint,
        )

        # --- Step 2: Position sizing ---
        position_sizing_hint = policy.compute_position_sizing_hint(
            action_hint=action_hint,
            conviction=intent.conviction,
            ambiguity_flags=intent.ambiguity_flags if intent.ambiguity_flags else None,
        )

        # --- Step 3: Holding period ---
        holding_period_hint = policy.compute_holding_period_hint(
            action_hint=action_hint,
        )

        # --- Step 4: Risk constraints (GlobalBase = style-independent base) ---
        risk_constraints = policy.compute_risk_constraints(
            action_hint=action_hint,
            conviction=intent.conviction,
            ambiguity_flags=intent.ambiguity_flags if intent.ambiguity_flags else None,
        )

        # --- Step 4b: Per-style exit-rule overlay (inert unless tuned) ---
        risk_constraints, applied_style = self._apply_style_exit_overlay(
            risk_constraints, intent
        )

        # --- Step 5: Mapping rationale ---
        rationale = self._build_rationale(intent, action_hint, position_sizing_hint)

        # --- Step 6: Confidence ---
        mapping_confidence = self._compute_confidence(intent, action_hint)

        # --- Step 7: Pre-generate policy_id ---
        # PolicyDecision requires policy_id, so we need it before constructing
        # both the result and its decisions.
        policy_id = str(uuid4())

        # --- Step 8: Build layer traces ---
        layer_traces = self._build_layer_traces(
            intent=intent,
            action_hint=action_hint,
            position_sizing_hint=position_sizing_hint,
            holding_period_hint=holding_period_hint,
        )
        policy_layers_applied = [policy.policy_layer_name]
        if applied_style:
            policy_layers_applied.append("StyleExitOverlay")
            layer_traces.append(
                PolicyLayerTrace(
                    layer_name="StyleExitOverlay",
                    layer_version=policy.policy_version,
                    applied=True,
                    reason=f"Declared entry_style='{applied_style}' has a by_style exit override",
                    modifications=[
                        f"stop_loss_pct_hint: → {risk_constraints.stop_loss_pct_hint}",
                        f"take_profit_pct_hint: → {risk_constraints.take_profit_pct_hint}",
                        f"max_holding_days_hint: → {risk_constraints.max_holding_days_hint}",
                    ],
                    order_index=1,
                )
            )

        # --- Step 9: Build decisions ---
        decisions = self._build_decisions(
            policy_id=policy_id,
            intent=intent,
            action_hint=action_hint,
            position_sizing_hint=position_sizing_hint,
        )

        return PolicyMappingResult(
            policy_id=policy_id,
            intent_id=intent.intent_id,
            creator_id=intent.creator_id,
            kol_id=intent.creator_id,
            policy_version=policy.policy_version,
            policy_layers_applied=policy_layers_applied,
            action_hint=action_hint,
            position_sizing_hint=position_sizing_hint,
            holding_period_hint=holding_period_hint,
            risk_constraints=risk_constraints,
            mapping_rationale=rationale,
            layer_traces=layer_traces,
            decisions=decisions,
            confidence=mapping_confidence,
            original_intent_confidence=intent.confidence,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_rationale(
        self,
        intent: NormalizedInvestmentIntent,
        action_hint: ACTION_HINT_LITERAL,
        position_sizing_hint: POSITION_SIZING_HINT_LITERAL,
    ) -> str:
        """Build a human-readable mapping rationale."""
        target = intent.target_symbol or intent.target_name
        parts = [
            f"Intent '{intent.summarize()}'",
            f"→ GlobalBase: action_hint={action_hint}",
            f"(from actionability={intent.actionability}, "
            f"direction={intent.direction}, "
            f"position_delta_hint={intent.position_delta_hint})",
            f"position_sizing_hint={position_sizing_hint}",
            f"(conviction={intent.conviction:.2f})",
        ]
        if intent.ambiguity_flags:
            parts.append(f"ambiguity_flags={intent.ambiguity_flags}")
        return " | ".join(parts)

    def _compute_confidence(
        self,
        intent: NormalizedInvestmentIntent,
        action_hint: ACTION_HINT_LITERAL,
    ) -> float:
        """Compute mapping confidence.

        Based on F3 confidence, with deductions for:
        - review_required output (lower confidence in mapping).
        - High ambiguity.
        """
        base = intent.confidence

        if action_hint == "review_required":
            base = min(base, 0.6)

        if intent.ambiguity_flags:
            # Each ambiguity flag reduces confidence slightly
            deduction = min(0.15, 0.05 * len(intent.ambiguity_flags))
            base = max(0.2, base - deduction)

        return round(base, 3)

    def _build_layer_traces(
        self,
        intent: NormalizedInvestmentIntent,
        action_hint: ACTION_HINT_LITERAL,
        position_sizing_hint: POSITION_SIZING_HINT_LITERAL,
        holding_period_hint: HOLDING_PERIOD_HINT_LITERAL,
    ) -> List[PolicyLayerTrace]:
        """Build the Per-layer audit trail.

        Currently only GlobalBase is active.
        """
        trace = PolicyLayerTrace(
            layer_name=self._policy.policy_layer_name,
            layer_version=self._policy.policy_version,
            applied=True,
            reason=(
                f"Mapped (actionability={intent.actionability}, "
                f"direction={intent.direction}, "
                f"position_delta_hint={intent.position_delta_hint}) "
                f"→ action_hint={action_hint}"
            ),
            modifications=[
                f"action_hint: → {action_hint}",
                f"position_sizing_hint: → {position_sizing_hint}",
                f"holding_period_hint: → {holding_period_hint}",
            ],
            order_index=0,
        )
        return [trace]

    def _build_decisions(
        self,
        policy_id: str,
        intent: NormalizedInvestmentIntent,
        action_hint: ACTION_HINT_LITERAL,
        position_sizing_hint: POSITION_SIZING_HINT_LITERAL,
    ) -> List[PolicyDecision]:
        """Build atomic policy decisions."""
        decision = PolicyDecision(
            policy_id=policy_id,
            layer=self._policy.policy_layer_name,
            decision_type="action_override",
            description=(
                f"Map ({intent.actionability}, {intent.direction}, "
                f"{intent.position_delta_hint}) → {action_hint}"
            ),
            rationale=(
                f"GlobalBase rule: intent with actionability={intent.actionability}, "
                f"direction={intent.direction}, "
                f"position_delta_hint={intent.position_delta_hint} "
                f"maps to action_hint={action_hint}"
            ),
            overrides_previous=False,
        )
        return [decision]

    def _build_mapped_intent(
        self,
        pmr: PolicyMappingResult,
        intent: NormalizedInvestmentIntent,
    ) -> PolicyMappedIntent:
        """Build a PolicyMappedIntent from a PolicyMappingResult + original intent."""
        return PolicyMappedIntent(
            intent_id=pmr.intent_id,
            policy_id=pmr.policy_id,
            original_intent_summary=intent.summarize(),
            action_hint=pmr.action_hint,
            position_sizing_hint=pmr.position_sizing_hint,
            holding_period_hint=pmr.holding_period_hint,
            stop_loss_pct_hint=pmr.risk_constraints.stop_loss_pct_hint,
            take_profit_pct_hint=pmr.risk_constraints.take_profit_pct_hint,
            max_holding_days_hint=pmr.risk_constraints.max_holding_days_hint,
            risk_notes=pmr.risk_constraints.risk_notes,
            mapping_confidence=pmr.confidence,
            requires_human_review=pmr.risk_constraints.requires_human_review,
        )
