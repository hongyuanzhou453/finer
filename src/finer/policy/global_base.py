"""Global Base Policy — Canonical baseline mapping rules.

F4 Policy layer 0: Provides default action-to-hint mappings, position sizing
bands, holding period defaults, and risk constraints that apply universally
before any KOL-specific or style-specific adjustments.

This is the first and most foundational policy layer. All other layers
(StyleArchetype, RiskPreference, KOLPersona, ContentCorrection) refine
or override these defaults.

Design:
  - Pure rule-based, no LLM, no external data.
  - Does NOT depend on KOL persona or trading style.
  - All position hints are qualitative (none/small/medium/large), not
    numeric percentages. Those are only determined at F5 execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from finer.policy.policy_config import PolicyTuning, load_policy_tuning
from finer.schemas.policy import (
    ACTION_HINT_LITERAL,
    POSITION_SIZING_HINT_LITERAL,
    HOLDING_PERIOD_HINT_LITERAL,
    MAX_POSITION_HINT_LITERAL,
    PolicyRiskConstraints,
)


# =============================================================================
# Mapping rule: (actionability, direction, position_delta_hint) -> action_hint
# =============================================================================

_ACTION_RULES: Dict[Tuple[str, str, str], str] = {
    # -- Opinion + Bullish →
    ("opinion", "bullish", "none"):       "watch_or_no_trade",
    ("opinion", "bullish", "unknown"):    "watch_or_no_trade",
    ("opinion", "bullish", "hold"):       "watch_or_no_trade",

    # -- Opinion + Bearish →
    ("opinion", "bearish", "none"):       "avoid_or_watch_risk",
    ("opinion", "bearish", "unknown"):    "avoid_or_watch_risk",
    ("opinion", "bearish", "hold"):       "avoid_or_watch_risk",

    # -- Opinion + Neutral/Mixed/Unknown →
    ("opinion", "neutral", "none"):       "watch_only",
    ("opinion", "mixed", "none"):         "watch_only",
    ("opinion", "unknown", "none"):       "watch_only",
    ("opinion", "neutral", "unknown"):    "watch_only",
    ("opinion", "mixed", "unknown"):      "watch_only",
    ("opinion", "unknown", "unknown"):    "watch_only",

    # -- Watch (any direction) →
    ("watch", "bullish", "none"):         "watch_only",
    ("watch", "bearish", "none"):         "watch_only",
    ("watch", "neutral", "none"):         "watch_only",
    ("watch", "mixed", "none"):           "watch_only",
    ("watch", "unknown", "none"):         "watch_only",

    # -- Explicit Action + Open →
    ("explicit_action", "bullish", "open"):  "open_position",
    ("explicit_action", "bearish", "open"):  "review_required",   # could be short — escalate
    ("explicit_action", "neutral", "open"):  "review_required",
    ("explicit_action", "mixed", "open"):    "review_required",

    # -- Explicit Action + Add →
    ("explicit_action", "bullish", "add"):   "add_position",
    ("explicit_action", "bearish", "add"):   "review_required",   # adding to short? escalate
    ("explicit_action", "neutral", "add"):   "review_required",
    ("explicit_action", "mixed", "add"):     "review_required",

    # -- Explicit Action + Reduce →
    ("explicit_action", "bullish", "reduce"):    "reduce_position",
    ("explicit_action", "bearish", "reduce"):    "reduce_position",
    ("explicit_action", "neutral", "reduce"):    "reduce_position",
    ("explicit_action", "mixed", "reduce"):      "reduce_position",

    # -- Explicit Action + Hold →
    ("explicit_action", "bullish", "hold"):  "hold_position",
    ("explicit_action", "bearish", "hold"):  "hold_position",
    ("explicit_action", "neutral", "hold"):  "hold_position",
    ("explicit_action", "mixed", "hold"):    "hold_position",

    # -- Explicit Action + Exit →
    ("explicit_action", "bullish", "exit"):  "close_position",
    ("explicit_action", "bearish", "exit"):  "close_position",
    ("explicit_action", "neutral", "exit"):  "close_position",
    ("explicit_action", "mixed", "exit"):    "close_position",

    # -- Explicit Action + none/unknown →
    ("explicit_action", "bullish", "none"):     "review_required",
    ("explicit_action", "bearish", "none"):     "review_required",
    ("explicit_action", "neutral", "none"):     "review_required",
    ("explicit_action", "bullish", "unknown"):  "review_required",
    ("explicit_action", "bearish", "unknown"):  "review_required",
    ("explicit_action", "neutral", "unknown"):  "review_required",
}

# =============================================================================
# Position sizing bands
# =============================================================================

# Position sizing bands moved to the tunable surface (configs/skills/f3f4-policy.yaml
# → PolicyTuning.conviction_bands()). Defaults mirror the historical thresholds
# (0.35 / 0.70), so behavior is unchanged. Global Base NEVER outputs "large".

# =============================================================================
# Default holding period by action_hint
# =============================================================================

_HOLDING_PERIOD_MAP: Dict[str, HOLDING_PERIOD_HINT_LITERAL] = {
    "watch_only":           "review_required",
    "watch_or_no_trade":    "review_required",
    "avoid_or_watch_risk":  "review_required",
    "open_position":        "medium_term",
    "add_position":         "medium_term",
    "reduce_position":      "short_term",
    "hold_position":        "medium_term",
    "close_position":       "short_term",
    "review_required":      "review_required",
}


# =============================================================================
# GlobalBasePolicy
# =============================================================================

@dataclass
class GlobalBasePolicy:
    """Global Base Policy — canonical baseline configuration.

    Provides:
      - Deterministic action_hint mapping from F3 intent axes.
      - Conviction-based position sizing hints (none/small/medium).
      - Default holding period assignments.
      - Baseline risk constraints.

    All outputs are hints; F5 makes the final execution decision.

    Attributes:
        policy_version:  Version string for reproducibility.
        policy_layer_name: Layer identifier used in trace / audits.
        max_position_ceiling: Hard upper bound on position_sizing_hint.
            Even if conviction is high, global-base will not exceed
            this ceiling. Higher layers can relax it.
        default_requires_human_review: Default for requires_human_review flag.
    """

    policy_version: str = "global-base-v1"
    policy_layer_name: str = "GlobalBase"

    # The global base NEVER outputs "large" position sizing on its own.
    # "large" only becomes available after StyleArchetype or RiskPreference
    # layers explicitly relax this ceiling.
    max_position_ceiling: MAX_POSITION_HINT_LITERAL = "medium"

    default_requires_human_review: bool = False

    # Tunable surface (configs/skills/f3f4-policy.yaml). Defaults mirror the
    # historical hardcoded thresholds, so behavior is unchanged until the YAML
    # overrides them. GlobalBase only consumes the *base* (style-independent)
    # values; per-style overlays are applied by higher layers (PolicyMapper).
    tuning: PolicyTuning = field(default_factory=load_policy_tuning)

    # ------------------------------------------------------------------
    # Action hint lookup
    # ------------------------------------------------------------------

    def lookup_action_hint(
        self,
        actionability: str,
        direction: str,
        position_delta_hint: str,
    ) -> ACTION_HINT_LITERAL:
        """Resolve the action_hint for a given F3 intent.

        Args:
            actionability:   opinion | watch | explicit_action | review_required.
            direction:       bullish | bearish | neutral | mixed | unknown.
            position_delta_hint: open | add | reduce | hold | exit | none | unknown.

        Returns:
            Policy-guided action hint.

        If no rule matches the exact triple, falls back to:
          - "review_required" for explicit_action without a clear match.
          - "watch_only" for opinion/watch without a clear match.
        """
        # Explicit review_required from F3 — escalate immediately
        if actionability == "review_required":
            return "review_required"

        key = (actionability, direction, position_delta_hint)
        if key in _ACTION_RULES:
            return _ACTION_RULES[key]  # type: ignore[return-value]

        # Fallback — try partial matches
        # opinion or watch with unknown position_delta_hint
        if actionability in ("opinion", "watch"):
            return "watch_only"

        # explicit_action without a matching rule → needs human review
        if actionability == "explicit_action":
            return "review_required"

        return "review_required"

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def compute_position_sizing_hint(
        self,
        action_hint: ACTION_HINT_LITERAL,
        conviction: float,
        ambiguity_flags: Optional[List[str]] = None,
    ) -> POSITION_SIZING_HINT_LITERAL:
        """Compute position sizing hint from action_hint and conviction.

        Rules:
        - Non-trade actions (watch_only, watch_or_no_trade, avoid_or_watch_risk,
          review_required) → "none".
        - Ambiguous intents (multiple flags) → "review_required".
        - Otherwise, conviction drives the band: <0.35 → none, 0.35-0.7 → small,
          >0.7 → medium.
        - Global base ceiling is "medium"; "large" is never output.

        Args:
            action_hint:      Resolved action hint.
            conviction:       F3 conviction (0.0-1.0).
            ambiguity_flags:  F3 ambiguity flags (e.g., 'multiple_targets').

        Returns:
            Position sizing hint.
        """
        # Non-trade actions → no position
        if action_hint in ("watch_only", "watch_or_no_trade",
                           "avoid_or_watch_risk", "review_required"):
            return "none"

        # Ambiguous intent → escalate
        if ambiguity_flags and len(ambiguity_flags) >= 2:
            return "review_required"

        # Conviction-based sizing (thresholds from the tunable surface)
        hint: POSITION_SIZING_HINT_LITERAL = "none"
        for threshold, band in self.tuning.conviction_bands():
            if conviction >= threshold:
                hint = band  # type: ignore[assignment]

        # Clamp to global-base ceiling
        ceiling_order = {"none": 0, "small": 1, "medium": 2, "large": 3, "review_required": 99}
        if ceiling_order.get(hint, 0) > ceiling_order.get(self.max_position_ceiling, 0):
            hint = self.max_position_ceiling  # type: ignore[assignment]

        return hint

    # ------------------------------------------------------------------
    # Holding period
    # ------------------------------------------------------------------

    def compute_holding_period_hint(
        self,
        action_hint: ACTION_HINT_LITERAL,
    ) -> HOLDING_PERIOD_HINT_LITERAL:
        """Assign a default holding period hint based on action_hint.

        Args:
            action_hint: Resolved action hint.

        Returns:
            Holding period hint.
        """
        return _HOLDING_PERIOD_MAP.get(action_hint, "review_required")

    # ------------------------------------------------------------------
    # Risk constraints
    # ------------------------------------------------------------------

    def compute_risk_constraints(
        self,
        action_hint: ACTION_HINT_LITERAL,
        conviction: float,
        ambiguity_flags: Optional[List[str]] = None,
    ) -> PolicyRiskConstraints:
        """Build risk constraints for this mapping.

        Args:
            action_hint:      Resolved action hint.
            conviction:       F3 conviction score.
            ambiguity_flags:  F3 ambiguity flags.

        Returns:
            Risk constraints.
        """
        # Determine max_position_hint
        max_pos: MAX_POSITION_HINT_LITERAL
        if action_hint in ("watch_only", "watch_or_no_trade",
                           "avoid_or_watch_risk", "review_required"):
            max_pos = "none"
        elif conviction >= 0.7:
            max_pos = "medium"
        else:
            max_pos = "small"

        # Determine if human review is required
        requires_review = self.default_requires_human_review
        if action_hint == "review_required":
            requires_review = True
        if ambiguity_flags and len(ambiguity_flags) >= 2:
            requires_review = True
        if conviction < self.tuning.human_review_below and action_hint not in (
            "watch_only", "watch_or_no_trade", "avoid_or_watch_risk"
        ):
            requires_review = True

        # Risk notes
        risk_notes: List[str] = []
        if requires_review:
            risk_notes.append("Flagged for human review by GlobalBasePolicy")
        if conviction < self.tuning.risk_note_below:
            risk_notes.append("Low conviction — consider tighter risk controls")
        if action_hint in ("open_position", "add_position"):
            risk_notes.append("New position opened — monitor closely for first 72h")
        if action_hint == "close_position":
            risk_notes.append("Position exit — verify against current holdings in F5")
        if ambiguity_flags:
            for flag in ambiguity_flags:
                risk_notes.append(f"Ambiguity: {flag}")

        # Numeric exit-rule hints for downstream simulation (F8 per-action).
        # GlobalBase emits the *base* (style-independent) hints from the tunable
        # surface; defaults mirror the historical F8 constants so backtests stay
        # unchanged. Per-style tuning is overlaid by higher layers (PolicyMapper
        # reads tuning.by_style keyed on the KOL's declared entry_style).
        position_taking = action_hint in (
            "open_position", "add_position", "reduce_position",
            "close_position", "hold_position",
        )
        base_exit = self.tuning.base_exit

        return PolicyRiskConstraints(
            max_position_hint=max_pos,
            requires_human_review=requires_review,
            risk_notes=risk_notes,
            stop_loss_pct_hint=base_exit.stop_loss_pct if position_taking else None,
            take_profit_pct_hint=base_exit.take_profit_pct if position_taking else None,
            max_holding_days_hint=base_exit.max_holding_days if position_taking else None,
        )
