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

from finer.schemas.investment_intent import (
    HORIZON_EXIT_TIERS,
    resolve_horizon_tier,
)
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
# Recommendation branch: (direction, position_delta_hint) -> action_hint
# =============================================================================
# actionability == "recommendation" covers declarative institutional ratings
# (broker research: buy / sell / hold ratings, initiations, target prices)
# where the author commits ZERO position of their own. The policy output is
# honestly "follow the institutional recommendation" — it must never be
# dressed up as "the analyst opened a position themselves".
#
# Two hard rules (spec 2026-07-15 broker-research R4):
#   1. A sell rating (bearish recommendation) is a NORMAL, executable
#      reduce/avoid signal. Initiation-at-sell is routine in broker research,
#      not an anomaly — it MUST NOT fall into the review_required human queue
#      (unlike (explicit_action, bearish, open), which stays escalated because
#      a person opening a bearish position could be shorting).
#   2. Global base never opens shorts. Bearish recommendations map to
#      reducing / exiting long exposure, never to opening short positions.
#
# For recommendations the rating direction dominates the position_delta_hint:
# the rating IS the recommendation; delta text is secondary color. This is why
# (bearish, hold) and (bearish, open/add) still resolve to reduce_position.
_RECOMMENDATION_RULES: Dict[Tuple[str, str], str] = {
    # -- Recommendation + Bullish (buy / overweight / initiate-buy) →
    #    executable open semantics; sizing flows through the normal
    #    conviction pipeline; no forced human review.
    ("bullish", "open"):    "open_position",
    ("bullish", "add"):     "add_position",
    ("bullish", "reduce"):  "reduce_position",   # bullish rating + trimming advice
    ("bullish", "hold"):    "hold_position",
    ("bullish", "exit"):    "close_position",
    ("bullish", "none"):    "open_position",     # maintain/initiate buy: the rating itself is the signal
    ("bullish", "unknown"): "open_position",

    # -- Recommendation + Bearish (sell / underweight / initiate-sell) →
    #    executable reduce/avoid semantics. Never review_required, never short.
    ("bearish", "open"):    "reduce_position",   # "open short" advice → base layer follows as reduce long exposure
    ("bearish", "add"):     "reduce_position",
    ("bearish", "reduce"):  "reduce_position",
    ("bearish", "hold"):    "reduce_position",   # rating direction dominates contradictory delta text
    ("bearish", "exit"):    "close_position",
    ("bearish", "none"):    "reduce_position",   # maintain/initiate sell: reduce/avoid, NOT human queue
    ("bearish", "unknown"): "reduce_position",

    # -- Recommendation + Neutral (hold / market-perform) → watch.
    ("neutral", "open"):    "watch_only",
    ("neutral", "add"):     "watch_only",
    ("neutral", "reduce"):  "watch_only",
    ("neutral", "hold"):    "watch_only",
    ("neutral", "exit"):    "watch_only",
    ("neutral", "none"):    "watch_only",
    ("neutral", "unknown"): "watch_only",
}

# =============================================================================
# Position sizing bands
# =============================================================================

_CONVICTION_BANDS: List[Tuple[float, POSITION_SIZING_HINT_LITERAL]] = [
    (0.0,  "none"),
    (0.35, "small"),
    (0.7,  "medium"),
    # Global Base NEVER outputs "large" — that requires higher layers.
]

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

# Horizon tier (from resolve_horizon_tier) → holding_period_hint. Used when
# the F3 intent carries an explicit time_horizon_hint: the author's stated
# horizon dominates the action_hint coarse default above, so a broker's
# 12-month view lands in "long_term" (→ 180d F8 window via TradeAction
# .time_horizon) instead of the 90d "medium_term" open-position default.
_TIER_TO_HOLDING_PERIOD: Dict[str, HOLDING_PERIOD_HINT_LITERAL] = {
    "short":  "short_term",
    "medium": "medium_term",
    "long":   "long_term",
}

# =============================================================================
# Horizon-aware exit parameters (spec 2026-07-15 broker-research R5)
# =============================================================================
# tier -> (stop_loss_pct_hint, take_profit_pct_hint). The window in days for
# each tier comes from HORIZON_EXIT_TIERS in schemas/investment_intent.py —
# the single source of truth shared with F8. Do NOT re-declare day counts here.
#
# Why per-horizon at all: the historical flat -10% / +20% / 30d rules were
# tuned for short-swing KOL calls. Applying a 30-day stopwatch to a broker
# target price that conventionally implies ~12 months measures noise, not
# judgment (R5: "构造上的抛硬币渲染成自信数字").
#
# Parameter rationale (explicit judgment call, documented for audit):
#   - "short" (30d) is byte-identical to the historical F8 flat constants
#     (-10% / +20% / 30d) so legacy-equivalent inputs have zero drift.
#   - Stops widen with horizon: a longer-horizon call must survive interim
#     drawdowns that are noise at that horizon. Pure sqrt-time scaling of a
#     -10%@30d stop would give ≈ -17%@90d and ≈ -24.5%@180d; we deliberately
#     cap tighter (-15% / -20%) as a hard per-position loss floor — wider than
#     the short tier, but below what raw volatility scaling would permit.
#   - Take-profit stays at 2x the stop magnitude in every tier, preserving
#     the legacy 2:1 reward-to-risk shape instead of inventing a new one.
_HORIZON_EXIT_PARAMS: Dict[str, Tuple[float, float]] = {
    "short":  (-0.10, 0.20),
    "medium": (-0.15, 0.30),
    "long":   (-0.20, 0.40),
}

# Legacy flat exit defaults — identical to the historical F8 constants.
# Used when the caller provides no time-horizon information, so existing
# call sites (and backtest results) stay bit-for-bit unchanged.
_LEGACY_FLAT_EXIT: Tuple[float, float, int] = (-0.10, 0.20, 30)


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
            actionability:   opinion | watch | explicit_action | recommendation
                             | review_required.
            direction:       bullish | bearish | neutral | mixed | unknown.
            position_delta_hint: open | add | reduce | hold | exit | none | unknown.

        Returns:
            Policy-guided action hint.

        If no rule matches the exact triple, falls back to:
          - "review_required" for explicit_action without a clear match.
          - "watch_only" for opinion/watch without a clear match.
          - "watch_only" for recommendation without a clear match — a
            declarative institutional rating never lands in the human queue
            by construction (R4).
        """
        # Explicit review_required from F3 — escalate immediately
        if actionability == "review_required":
            return "review_required"

        # Recommendation branch: declarative institutional ratings
        # (broker research). Dedicated table — direction dominates, sell
        # ratings are executable reduce/avoid, never review_required.
        if actionability == "recommendation":
            rec_key = (direction, position_delta_hint)
            if rec_key in _RECOMMENDATION_RULES:
                return _RECOMMENDATION_RULES[rec_key]  # type: ignore[return-value]
            # mixed / unknown rating direction → observe, not human queue
            return "watch_only"

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

        # Conviction-based sizing
        hint: POSITION_SIZING_HINT_LITERAL = "none"
        for threshold, band in _CONVICTION_BANDS:
            if conviction >= threshold:
                hint = band

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
        *,
        time_horizon_hint: Optional[str] = None,
    ) -> HOLDING_PERIOD_HINT_LITERAL:
        """Assign a holding period hint.

        Resolution order:
          1. Non-trade / escalated action hints (watch_*, review_required)
             always yield "review_required" — a holding period for a
             non-position action is meaningless, horizon or not.
          2. When ``time_horizon_hint`` is provided, the author's stated
             horizon dominates: it is routed through
             :func:`resolve_horizon_tier` (single source of truth shared
             with F8) and mapped tier → holding_period_hint.
          3. Otherwise fall back to the coarse per-action_hint defaults
             (legacy behavior, bit-for-bit unchanged for horizon-unaware
             callers).

        Args:
            action_hint:       Resolved action hint.
            time_horizon_hint: F3 ``intent.time_horizon_hint``. Pass ``None``
                when the intent carries no horizon information. Like
                ``compute_risk_constraints``, any provided string (including
                "unknown") resolves through ``resolve_horizon_tier``.

        Returns:
            Holding period hint.
        """
        base = _HOLDING_PERIOD_MAP.get(action_hint, "review_required")
        if time_horizon_hint is None or base == "review_required":
            return base
        tier = resolve_horizon_tier(time_horizon_hint)
        return _TIER_TO_HOLDING_PERIOD[tier]

    # ------------------------------------------------------------------
    # Risk constraints
    # ------------------------------------------------------------------

    def compute_risk_constraints(
        self,
        action_hint: ACTION_HINT_LITERAL,
        conviction: float,
        ambiguity_flags: Optional[List[str]] = None,
        *,
        time_horizon_hint: Optional[str] = None,
        actionability: Optional[str] = None,
    ) -> PolicyRiskConstraints:
        """Build risk constraints for this mapping.

        Args:
            action_hint:      Resolved action hint.
            conviction:       F3 conviction score.
            ambiguity_flags:  F3 ambiguity flags.
            time_horizon_hint: F3 ``intent.time_horizon_hint``. When provided
                (any string, including "unknown"), exit-rule hints are resolved
                per horizon tier via ``resolve_horizon_tier`` +
                ``HORIZON_EXIT_TIERS`` (R5). When ``None`` — i.e. the caller
                is horizon-unaware — the legacy flat -10%/+20%/30d defaults
                apply, keeping existing call sites bit-for-bit unchanged.
            actionability:    F3 ``intent.actionability``. When
                "recommendation", an honesty note is attached: the output
                follows an institutional recommendation, it is not the
                author's own position change.

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
        if conviction < 0.3 and action_hint not in ("watch_only", "watch_or_no_trade",
                                                     "avoid_or_watch_risk"):
            requires_review = True

        # Risk notes
        risk_notes: List[str] = []
        if requires_review:
            risk_notes.append("Flagged for human review by GlobalBasePolicy")
        if conviction < 0.4:
            risk_notes.append("Low conviction — consider tighter risk controls")
        if action_hint in ("open_position", "add_position"):
            risk_notes.append("New position opened — monitor closely for first 72h")
        if action_hint == "close_position":
            risk_notes.append("Position exit — verify against current holdings in F5")
        if ambiguity_flags:
            for flag in ambiguity_flags:
                risk_notes.append(f"Ambiguity: {flag}")

        position_taking = action_hint in (
            "open_position", "add_position", "reduce_position",
            "close_position", "hold_position",
        )

        # Honesty note: following an institutional rating is not the same
        # signal class as the author moving their own position. Downstream
        # consumers (F5/F6 review UI) must be able to tell them apart.
        if actionability == "recommendation" and position_taking:
            risk_notes.append(
                "Follows institutional recommendation (declarative rating); "
                "not the author's own position change"
            )

        # Numeric exit-rule hints for downstream simulation (F8 per-action).
        # Horizon-aware when the caller supplies time_horizon_hint (R5);
        # legacy flat constants otherwise (zero drift for existing callers).
        stop_pct: Optional[float] = None
        tp_pct: Optional[float] = None
        max_days: Optional[int] = None
        if position_taking:
            if time_horizon_hint is None:
                stop_pct, tp_pct, max_days = _LEGACY_FLAT_EXIT
            else:
                tier = resolve_horizon_tier(time_horizon_hint)
                stop_pct, tp_pct = _HORIZON_EXIT_PARAMS[tier]
                max_days = HORIZON_EXIT_TIERS[tier]
                risk_notes.append(
                    f"Exit window: '{tier}' tier ({max_days}d) resolved from "
                    f"time_horizon_hint={time_horizon_hint!r}"
                )

        return PolicyRiskConstraints(
            max_position_hint=max_pos,
            requires_human_review=requires_review,
            risk_notes=risk_notes,
            stop_loss_pct_hint=stop_pct,
            take_profit_pct_hint=tp_pct,
            max_holding_days_hint=max_days,
        )
