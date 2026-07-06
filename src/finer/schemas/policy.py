"""F4 Policy Schema — Intent-to-Action mapping layer.

This module defines the canonical data structures for the F4 Policy stage:
PolicyMappingResult, PolicyMappedIntent, PolicyDecision, PolicyLayerTrace,
and PolicyRiskConstraints.

F4 is the *only* legal conversion layer from F3 Intent to F5-executable
parameters. All position sizing, holding period, and risk constraints are
*hints* at this stage — not execution facts. F5 makes the final commitment.

Design Principles:
1. F4 provides hints, not execution facts
2. Every PolicyMappingResult MUST reference a valid F3 intent_id
3. F4 MUST NOT modify the original intent's direction
4. All policy layers produce an audit trail (PolicyLayerTrace)
5. Risk constraints are bounds, not targeting instructions
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, model_validator


# =============================================================================
# Literal Types
# =============================================================================

ACTION_HINT_LITERAL = Literal[
    "watch_only",            # 仅观察，不做任何操作
    "watch_or_no_trade",     # 观察或不交易
    "avoid_or_watch_risk",   # 规避或观望风险
    "open_position",         # 开新仓位
    "add_position",          # 加仓
    "reduce_position",       # 减仓
    "hold_position",         # 持有
    "close_position",        # 清仓/平仓
    "review_required",       # 需人工审核
]

POSITION_SIZING_HINT_LITERAL = Literal[
    "none",              # 无仓位变动
    "small",             # 小仓位（通常 <10%）
    "medium",            # 中等仓位（通常 10-25%）
    "large",             # 大仓位（通常 25-50%）
    "review_required",   # 需人工确定
]

MAX_POSITION_HINT_LITERAL = Literal[
    "none",
    "small",
    "medium",
    "large",
]

HOLDING_PERIOD_HINT_LITERAL = Literal[
    "intraday",          # 日内
    "short_term",        # 日-周
    "medium_term",       # 周-月
    "long_term",         # 月-年
    "review_required",   # 需人工确定
]

CANONICAL_TRACE_STATUS_LITERAL = Literal[
    "canonical",         # 完整追溯链: intent_id + policy_id + evidence_span_ids
    "partial",           # 部分追溯: 至少一个 ID 缺失
    "missing",           # 无追溯: 没有任何上游 ID
]

DECISION_TYPE_LITERAL = Literal[
    "action_override",       # 覆盖默认动作映射
    "sizing_adjust",         # 调整仓位大小
    "holding_adjust",        # 调整持有期
    "risk_bound",            # 设定风险边界
    "confidence_adjust",     # 调整置信度
    "human_escalation",      # 升级到人工审核
    "no_op",                 # 无操作
]

# =============================================================================
# Policy Risk Constraints
# =============================================================================

class PolicyRiskConstraints(BaseModel):
    """Risk boundaries applied by the policy layer.

    These are *constraints* (upper/lower bounds), not targeting instructions.
    F5 must respect these but may tighten them further.

    Attributes:
        max_position_hint: Upper bound on position size for this intent.
        requires_human_review: Whether this mapped intent must be reviewed.
        risk_notes: Human-readable risk notes from policy evaluation.
    """
    model_config = ConfigDict(strict=True)

    max_position_hint: MAX_POSITION_HINT_LITERAL = Field(
        ...,
        description="Upper bound on position size from policy assessment "
                    "(none/small/medium/large). Not a target — a ceiling."
    )

    requires_human_review: bool = Field(
        False,
        description="Whether this mapped intent requires mandatory human review "
                    "before F5 execution"
    )

    risk_notes: List[str] = Field(
        default_factory=list,
        description="Human-readable risk notes explaining policy decisions "
                    "(e.g., 'KOL has mixed track record on this sector')"
    )

    # ------------------------------------------------------------------
    # Optional risk bounds
    # ------------------------------------------------------------------

    max_concentration_pct: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Maximum portfolio concentration allowed for this target "
                    "sector or ticker"
    )

    stop_loss_hint: Optional[str] = Field(
        None,
        description="Natural-language stop-loss hint (e.g., 'tight stop at -5%'). "
                    "Not a precise trigger — F5 resolves."
    )

    stop_loss_pct_hint: Optional[float] = Field(
        None,
        lt=0,
        description="Numeric stop-loss hint as signed fraction (e.g., -0.10 = exit "
                    "at -10% adverse move). A hint for downstream simulation, not "
                    "an execution instruction."
    )

    take_profit_pct_hint: Optional[float] = Field(
        None,
        gt=0,
        description="Numeric take-profit hint as signed fraction (e.g., 0.20 = exit "
                    "at +20% favorable move). A hint for downstream simulation, not "
                    "an execution instruction."
    )

    max_holding_days_hint: Optional[int] = Field(
        None,
        gt=0,
        description="Maximum holding period hint in calendar days before time-based "
                    "exit in downstream simulation."
    )

    time_decay_days: Optional[int] = Field(
        None,
        ge=0,
        description="Number of days after which conviction decays without new evidence"
    )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )


# =============================================================================
# Policy Layer Trace
# =============================================================================

class PolicyLayerTrace(BaseModel):
    """Audit trail for a single policy layer's decision.

    Each of the 5 policy layers produces one PolicyLayerTrace, recording
    what it changed and why. The full trace enables debugging and A/B testing
    of policy configurations.

    Attributes:
        layer_name: Policy layer identifier (e.g., 'GlobalBase', 'StyleArchetype').
        layer_version: Version string for reproducibility.
        applied: Whether this layer was active for this intent.
        reason: Human-readable rationale for the layer's decision.
        modifications: List of specific changes made (e.g., 'sizing: none→small').
        order_index: Execution order within the policy stack (0-based).
    """
    model_config = ConfigDict(strict=True)

    layer_name: str = Field(
        ...,
        min_length=1,
        description="Policy layer identifier (e.g., 'GlobalBase', 'StyleArchetype', "
                    "'RiskPreference', 'KOLPersona', 'ContentCorrection')"
    )

    layer_version: str = Field(
        ...,
        min_length=1,
        description="Version string of the layer config used (e.g., 'global-base-v1')"
    )

    applied: bool = Field(
        ...,
        description="Whether this layer was active and produced modifications"
    )

    reason: str = Field(
        "",
        description="Human-readable rationale for what this layer did or why it was skipped"
    )

    modifications: List[str] = Field(
        default_factory=list,
        description="List of specific modifications made by this layer "
                    "(e.g., 'action_hint: watch_only→open_position', "
                    "'position_sizing: none→small')"
    )

    order_index: int = Field(
        0,
        ge=0,
        description="Execution order within the policy stack (0 = first layer applied)"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )


# =============================================================================
# Policy Decision
# =============================================================================

class PolicyDecision(BaseModel):
    """A single atomic decision within the policy mapping.

    PolicyMappingResult may contain multiple PolicyDecisions for complex
    intents (e.g., an intent that modifies both action and sizing).
    """
    model_config = ConfigDict(strict=True)

    decision_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this decision"
    )

    policy_id: str = Field(
        ...,
        min_length=1,
        description="Parent PolicyMappingResult.policy_id"
    )

    layer: str = Field(
        ...,
        min_length=1,
        description="Policy layer that made this decision "
                    "(e.g., 'GlobalBase', 'KOLPersona')"
    )

    decision_type: DECISION_TYPE_LITERAL = Field(
        ...,
        description="Type of decision made (action override, sizing adjust, etc.)"
    )

    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of the decision"
    )

    rationale: str = Field(
        "",
        description="Why this decision was made (audit trail)"
    )

    overrides_previous: bool = Field(
        False,
        description="Whether this decision overrides one from an earlier layer"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )


# =============================================================================
# Policy Mapping Result
# =============================================================================

class PolicyMappingResult(BaseModel):
    """Canonical output of F4 Policy stage.

    Maps a single F3 NormalizedInvestmentIntent to policy-guided action hints.
    Each PolicyMappingResult bridges exactly one Intent to downstream F5.

    Key invariants:
    - MUST reference a valid F3 intent_id
    - MUST NOT modify the original intent's direction (F4 only adds hints)
    - MUST include mapping_rationale for auditability
    - position_sizing_hint is a HINT, not an execution instruction

    Example:
        An intent "我看好宁德时代" (bullish, opinion, none)
        mapped through GlobalBase+StyleArchetype might produce:
        - action_hint: "watch_only"
        - position_sizing_hint: "none"
        - holding_period_hint: "review_required"
    """
    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Identity & Lineage
    # =========================================================================

    policy_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this policy mapping result (UUID)"
    )

    intent_id: str = Field(
        ...,
        min_length=1,
        description="Reference to F3 NormalizedInvestmentIntent.intent_id. "
                    "Every PolicyMappingResult MUST trace back to exactly one Intent."
    )

    creator_id: Optional[str] = Field(
        None,
        description="Content creator / KOL identifier (Feishu user ID, etc.)"
    )

    kol_id: Optional[str] = Field(
        None,
        description="KOL identifier — alias for creator_id when the KOL is the "
                    "primary subject. At least one of creator_id/kol_id should be set."
    )

    policy_version: str = Field(
        "global-base-v1",
        min_length=1,
        description="Policy version identifier for reproducibility "
                    "(e.g., 'global-base-v1', 'style-archetype-v2')"
    )

    policy_layers_applied: List[str] = Field(
        default_factory=list,
        description="Ordered list of policy layer names that were applied "
                    "(e.g., ['GlobalBase', 'StyleArchetype', 'RiskPreference', 'KOLPersona'])"
    )

    # =========================================================================
    # Action & Position Hints (F4-specific — NOT present in F3)
    # =========================================================================

    action_hint: ACTION_HINT_LITERAL = Field(
        ...,
        description="Policy-guided action hint. This is a *suggestion* derived "
                    "from the F3 intent through policy layers. F5 may refine it "
                    "but should not fundamentally contradict it without audit."
    )

    position_sizing_hint: POSITION_SIZING_HINT_LITERAL = Field(
        ...,
        description="Policy-guided position sizing hint (none/small/medium/large). "
                    "This is a *hint*, not a commitment. F5 makes the final sizing decision."
    )

    holding_period_hint: HOLDING_PERIOD_HINT_LITERAL = Field(
        ...,
        description="Policy-guided holding period hint (intraday/short_term/medium_term/"
                    "long_term). This is a *hint*, not a fixed exit date."
    )

    # =========================================================================
    # Risk Constraints
    # =========================================================================

    risk_constraints: PolicyRiskConstraints = Field(
        default_factory=lambda: PolicyRiskConstraints(
            max_position_hint="small",
            requires_human_review=False,
        ),
        description="Risk boundaries applied by policy layers. F5 must respect "
                    "these constraints."
    )

    # =========================================================================
    # Audit & Rationale
    # =========================================================================

    mapping_rationale: str = Field(
        ...,
        min_length=1,
        description="Human-readable rationale explaining how the F3 intent was "
                    "mapped to these F4 hints. Required for auditability and debugging."
    )

    layer_traces: List[PolicyLayerTrace] = Field(
        default_factory=list,
        description="Per-layer audit trail showing what each policy layer decided. "
                    "Empty if policy mapping is trivial (no layers applied)."
    )

    decisions: List[PolicyDecision] = Field(
        default_factory=list,
        description="Atomic policy decisions generated during mapping. "
                    "Multiple decisions may exist for complex intents."
    )

    # =========================================================================
    # Confidence & Metadata
    # =========================================================================

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this policy mapping (0-1). Reflects how well "
                    "the policy layers agree and how clear the intent was. "
                    "NOT the same as F3 intent confidence."
    )

    original_intent_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Original F3 intent confidence, preserved for comparison"
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="ISO 8601 timestamp when this policy mapping was created"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @model_validator(mode='after')
    def validate_kol_identifier(self) -> PolicyMappingResult:
        """Ensure at least one of creator_id or kol_id provides KOL identity."""
        if self.creator_id is None and self.kol_id is None:
            # Not a hard error (some content may be anonymous), but log as warning
            pass
        return self

    @model_validator(mode='after')
    def validate_policy_layers_match_traces(self) -> PolicyMappingResult:
        """Warn if policy_layers_applied doesn't match layer_traces."""
        if self.policy_layers_applied and self.layer_traces:
            applied_from_traces = [
                t.layer_name for t in self.layer_traces if t.applied
            ]
            if set(self.policy_layers_applied) != set(applied_from_traces):
                # Not a hard error — traces may be more granular
                pass
        return self


# =============================================================================
# Policy Mapped Intent (F4 output container)
# =============================================================================

class PolicyMappedIntent(BaseModel):
    """Output container linking an F3 Intent to its F4 Policy mapping.

    This is the primary output of the F4 stage. Each instance binds exactly
    one F3 Intent to its policy-guided hints, plus audit metadata.

    Design:
        - mapped_id: unique identifier for this mapping
        - intent_id: back-reference to F3
        - policy_id: back-reference to PolicyMappingResult
        - All hints are derived from PolicyMappingResult, summarized for F5 consumption
    """
    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Identity
    # =========================================================================

    mapped_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this PolicyMappedIntent (UUID)"
    )

    intent_id: str = Field(
        ...,
        min_length=1,
        description="Reference to F3 NormalizedInvestmentIntent.intent_id"
    )

    policy_id: str = Field(
        ...,
        min_length=1,
        description="Reference to F4 PolicyMappingResult.policy_id"
    )

    # =========================================================================
    # Intent Summary (from F3, preserved for context)
    # =========================================================================

    original_intent_summary: str = Field(
        ...,
        min_length=1,
        description="Human-readable summary of the original F3 intent. "
                    "Preserved so F5 consumers don't need to look up F3 separately."
    )

    # =========================================================================
    # Policy-Driven Hints
    # =========================================================================

    action_hint: ACTION_HINT_LITERAL = Field(
        ...,
        description="Policy-guided action hint for F5 execution"
    )

    position_sizing_hint: POSITION_SIZING_HINT_LITERAL = Field(
        ...,
        description="Policy-guided position sizing hint for F5 execution"
    )

    holding_period_hint: HOLDING_PERIOD_HINT_LITERAL = Field(
        ...,
        description="Policy-guided holding period hint for F5 execution"
    )

    stop_loss_pct_hint: Optional[float] = Field(
        None,
        lt=0,
        description="Numeric stop-loss hint carried from PolicyRiskConstraints "
                    "(signed fraction, e.g., -0.10)"
    )

    take_profit_pct_hint: Optional[float] = Field(
        None,
        gt=0,
        description="Numeric take-profit hint carried from PolicyRiskConstraints "
                    "(signed fraction, e.g., 0.20)"
    )

    max_holding_days_hint: Optional[int] = Field(
        None,
        gt=0,
        description="Maximum holding period hint in calendar days carried from "
                    "PolicyRiskConstraints"
    )

    # =========================================================================
    # Risk & Review
    # =========================================================================

    risk_notes: List[str] = Field(
        default_factory=list,
        description="Risk notes from policy evaluation. F5 should propagate these "
                    "into the TradeAction."
    )

    mapping_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this policy mapping (0-1). "
                    "Carried from PolicyMappingResult.confidence."
    )

    requires_human_review: bool = Field(
        False,
        description="Whether F5 should flag the resulting TradeAction for human review"
    )

    # =========================================================================
    # Metadata
    # =========================================================================

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="ISO 8601 timestamp when this mapped intent was created"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @model_validator(mode='after')
    def validate_requires_review_consistency(self) -> PolicyMappedIntent:
        """If action_hint or sizing_hint is review_required, force the flag."""
        if self.action_hint == "review_required" and not self.requires_human_review:
            self.requires_human_review = True
        if self.position_sizing_hint == "review_required" and not self.requires_human_review:
            self.requires_human_review = True
        return self


# =============================================================================
# Policy Context (input to F4, not output)
# =============================================================================

class PolicyContext(BaseModel):
    """Input context provided to the F4 policy mapper.

    This is NOT an F4 output — it is the configuration/context that
    the policy mapper uses to transform F3 Intents into F4 hints.
    Defined here as a contract for what F4 implementations must accept.
    """
    model_config = ConfigDict(strict=True)

    kol_id: str = Field(
        ...,
        min_length=1,
        description="KOL identifier for persona lookup"
    )

    style_archetype: str = Field(
        "mixed",
        description="Trading style archetype (e.g., 'short_term', 'momentum', "
                    "'value', 'cyclical', 'mixed')"
    )

    risk_preference: str = Field(
        "balanced",
        description="Risk preference tier (e.g., 'aggressive', 'balanced', 'conservative')"
    )

    persona_summary: Optional[str] = Field(
        None,
        description="LLM-generated persona summary from historical KOL content "
                    "(200-1000 analyzed items)"
    )

    active_corrections: List[str] = Field(
        default_factory=list,
        description="Temporary content-level corrections from current context "
                    "(e.g., 'KOL explicitly said this is not investment advice')"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )


# =============================================================================
# Container Model
# =============================================================================

class PolicyMappingBatch(BaseModel):
    """Container for multiple PolicyMappingResults from one batch run."""
    model_config = ConfigDict(strict=True)

    batch_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique batch identifier"
    )

    mappings: List[PolicyMappingResult] = Field(
        default_factory=list,
        description="List of policy mapping results"
    )

    mapped_intents: List[PolicyMappedIntent] = Field(
        default_factory=list,
        description="List of mapped intents (F4 output ready for F5 consumption)"
    )

    policy_version: str = Field(
        "global-base-v1",
        min_length=1,
        description="Policy version used for this batch"
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When this batch was created"
    )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    total_mappings: int = Field(0, description="Total mapping results")
    total_mapped_intents: int = Field(0, description="Total mapped intents")
    review_required_count: int = Field(0, description="Count requiring human review")

    @model_validator(mode='after')
    def compute_stats(self) -> PolicyMappingBatch:
        """Auto-compute batch statistics."""
        self.total_mappings = len(self.mappings)
        self.total_mapped_intents = len(self.mapped_intents)
        self.review_required_count = sum(
            1 for mi in self.mapped_intents if mi.requires_human_review
        )
        return self
