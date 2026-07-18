"""Normalized Investment Intent Schema — Pre-TradeAction abstraction layer.

This module defines NormalizedInvestmentIntent, a semantic abstraction layer
between raw event extraction and executable TradeAction. It captures the
*intent* behind investment-related statements without committing to
specific position sizing or execution details.

Key Design Principles:
1. Intent ≠ Action: Opinion/watch != explicit trading action
2. No position commitment: position_delta_hint is a *hint*, not an instruction
3. Semantic clarity — actionability 三分语义:
   - "我看好宁德时代"      → opinion          (纯观点，无行动意图)
   - "我加仓宁德时代"      → explicit_action  (本人真实仓位变动)
   - "机构建议买入宁德时代" → recommendation   (零仓位承诺的机构建议，
     如券商研报评级：分析师声明立场但从不持仓，既非 opinion 也非 explicit_action)

Examples:
    "我看好宁德时代" → bullish + opinion/watch + none
    "我加仓宁德时代" → bullish + explicit_action + add
    "继续持有腾讯" → bullish/neutral + explicit_action + hold
    "Overweight, PT US$31.00" → bullish + recommendation + none (+ target_price)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


# =============================================================================
# Target Type Definitions
# =============================================================================

TARGET_TYPE_LITERAL = Literal[
    "stock",
    "sector",
    "index",
    "macro",
    "commodity",
    "crypto",
    "unknown",
]

DIRECTION_LITERAL = Literal[
    "bullish",
    "bearish",
    "neutral",
    "mixed",
    "unknown",
]

ACTIONABILITY_LITERAL = Literal[
    "opinion",         # 纯观点，无行动意图（「我看好」）
    "watch",           # 观察名单，待机
    "explicit_action", # 明确的行动指令（「我加仓」——本人仓位变动）
    "recommendation",  # 机构建议（「机构建议买入」——零仓位承诺的声明式评级，如研报）
    "review_required", # 需人工审核
]

POSITION_DELTA_HINT_LITERAL = Literal[
    "open",    # 开新仓
    "add",     # 加仓
    "reduce",  # 减仓
    "hold",    # 持有
    "exit",    # 清仓
    "none",    # 无仓位变动
    "unknown",
]

RISK_PREFERENCE_LITERAL = Literal[
    "aggressive",
    "balanced",
    "conservative",
    "unknown",
]

TIME_HORIZON_LITERAL = Literal[
    "intraday",
    "short_term",    # 日-周
    "medium_term",   # 周-月
    "long_term",     # 月-年
    "unknown",
]

ENTRY_TIMING_STYLE_LITERAL = Literal[
    "left_side",   # 左侧：抄底/越跌越买/逢低布局
    "right_side",  # 右侧：突破追入/放量确认/趋势确立后进
    "unknown",
]

PRIOR_DIRECTION_LITERAL = Literal[
    "bullish",
    "bearish",
    "neutral",
]

RATING_ACTION_LITERAL = Literal[
    "upgrade",    # 上调评级
    "downgrade",  # 下调评级
    "maintain",   # 维持评级
    "initiate",   # 首次覆盖
    "unknown",
]

CONVICTION_SOURCE_LITERAL = Literal[
    "stated",          # 作者显式声明的信念强度
    "derived_lookup",  # 评级查表推导（如 Overweight→固定值）——不得进 credibility 计算
    "model_inferred",  # 模型推断（默认）
]


# =============================================================================
# Horizon → Exit Window Mapping (single source of truth for F4/F8)
# =============================================================================

#: Exit-window tiers in **days**, keyed by tier name. This is the single
#: source of truth for horizon-aware exit rules — F4 (policy exit hints) and
#: F8 (backtest max holding window) MUST import from here instead of
#: hardcoding day counts.
#:
#: ``long`` is capped at 180 days as a deliberate compromise forced by corpus
#: depth: broker-research target prices conventionally imply a 12-month
#: horizon, but the current corpus spans only ~10 months, so a 365-day window
#: would leave almost every long-horizon action unsettleable. Raise this cap
#: as the corpus accumulates history.
HORIZON_EXIT_TIERS: dict[str, int] = {
    "short": 30,
    "medium": 90,
    "long": 180,
}

#: time_horizon_hint value → HORIZON_EXIT_TIERS tier name.
_TIME_HORIZON_TO_TIER: dict[str, str] = {
    "intraday": "short",
    "short_term": "short",
    "medium_term": "medium",
    "long_term": "long",
}


def resolve_horizon_tier(time_horizon_hint: Optional[str]) -> str:
    """Map a ``time_horizon_hint`` value to a :data:`HORIZON_EXIT_TIERS` tier.

    Unknown / missing / unrecognized hints default to ``"long"``: broker
    research target prices conventionally imply ~12 months, so absence of an
    explicit horizon must not silently shrink the settlement window to the
    historical 30-day default (R5: measuring 12-month judgments with a 30-day
    stopwatch renders coin flips as confident scores).

    Args:
        time_horizon_hint: A TIME_HORIZON_LITERAL value (or None / free text).

    Returns:
        A key of HORIZON_EXIT_TIERS ("short" | "medium" | "long").
    """
    if not time_horizon_hint:
        return "long"
    return _TIME_HORIZON_TO_TIER.get(time_horizon_hint, "long")


# =============================================================================
# IntentTargetPrice Sub-model
# =============================================================================

class IntentTargetPrice(BaseModel):
    """Declarative target price carried verbatim by the source content.

    Only populated when the source *explicitly states* a target price (e.g.
    broker report P1: "Price Target US$7.50→US$6.60"). Never derived.
    """
    model_config = ConfigDict(strict=True)

    value: float = Field(
        ...,
        description="Stated target price value (e.g. 6.60)"
    )

    currency: str = Field(
        ...,
        description="Currency code as stated in the source (e.g. 'USD', 'HKD', 'CNY')"
    )

    prior_value: Optional[float] = Field(
        None,
        description="Previous target price when the source states a revision "
                    "(e.g. US$7.50→US$6.60 → prior_value=7.50); None if not stated"
    )


# =============================================================================
# NormalizedInvestmentIntent Model
# =============================================================================

class NormalizedInvestmentIntent(BaseModel):
    """
    Normalized investment intent extracted from content.

    This is a semantic abstraction layer between raw text and TradeAction.
    It captures the *intent* behind investment statements without committing
    to specific position sizing or execution details.

    Core Design:
        - intent_id: Unique identifier
        - envelope_id: Parent container ID (e.g., content block)
        - block_ids: Source text block identifiers
        - target_*: What is being discussed
        - direction: Bullish/bearish/neutral sentiment
        - actionability: Opinion vs explicit action
        - position_delta_hint: Position change hint (NOT an instruction)
        - conviction: Strength of belief (0-1)
        - confidence: Model confidence in extraction (0-1)

    Key Distinction:
        "我看好宁德时代" = bullish + opinion/watch + none
        "我加仓宁德时代" = bullish + explicit_action + add

    The position_delta_hint is a *hint*, not a trading instruction.
    It signals the semantic category of the statement, which downstream
    layers (TradeAction generator) can use to determine actual actions.
    """
    model_config = ConfigDict(strict=True)

    # =========================================================================
    # Identity & Lineage
    # =========================================================================

    intent_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this intent"
    )

    schema_version: str = Field(
        "1.0",
        description="Schema version for compatibility tracking"
    )

    envelope_id: str = Field(
        ...,
        description="Parent container ID (e.g., content envelope, segment)"
    )

    block_ids: List[str] = Field(
        default_factory=list,
        description="Source text block identifiers that contributed to this intent"
    )

    creator_id: Optional[str] = Field(
        None,
        description="Content creator identifier (Feishu user ID, etc.)"
    )

    # =========================================================================
    # Target Information
    # =========================================================================

    target_type: TARGET_TYPE_LITERAL = Field(
        ...,
        description="Type of investment target (stock, sector, index, etc.)"
    )

    target_name: str = Field(
        ...,
        description="Human-readable name (e.g., '宁德时代', 'Tesla', '新能源板块')"
    )

    target_symbol: Optional[str] = Field(
        None,
        description="Normalized ticker symbol if applicable (e.g., '300750.SZ', 'TSLA')"
    )

    market: Optional[str] = Field(
        None,
        description="Market identifier (e.g., 'CN', 'US', 'HK')"
    )

    # =========================================================================
    # Sentiment & Direction
    # =========================================================================

    direction: DIRECTION_LITERAL = Field(
        ...,
        description="Overall sentiment direction (bullish/bearish/neutral/mixed/unknown)"
    )

    actionability: ACTIONABILITY_LITERAL = Field(
        ...,
        description="Whether this is an opinion, watch signal, or explicit action"
    )

    position_delta_hint: POSITION_DELTA_HINT_LITERAL = Field(
        ...,
        description="Hint about position change (NOT a trading instruction)"
    )

    # =========================================================================
    # Declarative Rating Fields (broker research / institutional sources)
    # =========================================================================
    # These carry *stated* facts from declarative sources (e.g. broker report
    # first pages). They are never inferred; absence means "not stated".

    target_price: Optional[IntentTargetPrice] = Field(
        None,
        description="Declarative target price. May ONLY be populated from "
                    "sources that explicitly state it (e.g. broker report "
                    "price target); LLM inference paths MUST NOT fill this "
                    "field (F3 prompts forbid proposing prices). None = not "
                    "stated by the source."
    )

    prior_direction: Optional[PRIOR_DIRECTION_LITERAL] = Field(
        None,
        description="Stance held *before* this statement, when the source "
                    "declares it (e.g. rating change 前态: Neutral→Overweight "
                    "→ prior_direction='neutral'); None = not stated"
    )

    rating_action: Optional[RATING_ACTION_LITERAL] = Field(
        None,
        description="Declared rating action for institutional recommendations "
                    "(upgrade/downgrade/maintain/initiate/unknown); None = "
                    "not a rating event or not stated"
    )

    # =========================================================================
    # Conviction & Preferences
    # =========================================================================

    conviction: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of belief/conviction (0-1)"
    )

    conviction_source: CONVICTION_SOURCE_LITERAL = Field(
        "model_inferred",
        description="Provenance of the conviction value: 'stated' = author "
                    "explicitly quantified their belief; 'derived_lookup' = "
                    "mapped from a rating table (e.g. Overweight→fixed value) "
                    "— derived_lookup convictions MUST NOT enter credibility "
                    "scoring (R6: lookup values are editorial constants, not "
                    "evidence of judgment); 'model_inferred' = LLM-estimated "
                    "(default)"
    )

    sentiment_score: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Quantified sentiment score from analysis"
    )

    risk_preference_hint: RISK_PREFERENCE_LITERAL = Field(
        "unknown",
        description="Implied risk preference from context"
    )

    time_horizon_hint: TIME_HORIZON_LITERAL = Field(
        "unknown",
        description="Implied time horizon from context"
    )

    # =========================================================================
    # Trading Style Signals (auxiliary)
    # =========================================================================
    # These are auxiliary style observations feeding the KOL trading-style
    # profile. They never affect direction/actionability/position mapping.

    margin_flag: Optional[bool] = Field(
        None,
        description="True if the KOL explicitly mentions margin financing "
                    "(融资/两融/融资买入) for this intent; None = not mentioned "
                    "(never guessed)"
    )

    leverage_flag: Optional[bool] = Field(
        None,
        description="True if the KOL explicitly mentions leverage (杠杆/合约/"
                    "X倍/期货保证金) for this intent; None = not mentioned "
                    "(never guessed)"
    )

    entry_timing_style: ENTRY_TIMING_STYLE_LITERAL = Field(
        "unknown",
        description="Entry timing style signal: left_side = contrarian entries "
                    "(抄底/越跌越买/逢低布局), right_side = trend-following entries "
                    "(突破追入/放量确认); unknown when no explicit semantics"
    )

    # =========================================================================
    # Evidence & Context
    # =========================================================================

    temporal_anchor_ids: List[str] = Field(
        default_factory=list,
        description="Temporal reference IDs (e.g., '明天', '下周', '财报后')"
    )

    evidence_span_ids: List[str] = Field(
        default_factory=list,
        description="Text span IDs that provide evidence for this intent"
    )

    ambiguity_flags: List[str] = Field(
        default_factory=list,
        description="Flags indicating ambiguities (e.g., 'multiple_targets', 'unclear_direction')"
    )

    # =========================================================================
    # Model Metadata
    # =========================================================================

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in this extraction (0-1)"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extensible metadata"
    )

    # Timestamp for when this intent was created
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When this intent was extracted"
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @model_validator(mode='after')
    def validate_actionability_consistency(self) -> NormalizedInvestmentIntent:
        """
        Validate consistency between actionability and position_delta_hint.

        Rules:
        - opinion + (open/add/reduce/exit) → suspicious, flag for review
        - explicit_action + none → suspicious, flag for review
        """
        if self.actionability == "opinion":
            # Opinion should not have explicit position changes
            if self.position_delta_hint in ["open", "add", "reduce", "exit"]:
                if "opinion_with_position_hint" not in self.ambiguity_flags:
                    self.ambiguity_flags.append("opinion_with_position_hint")

        if self.actionability == "explicit_action":
            # Explicit action should have a position hint
            if self.position_delta_hint == "none":
                if "action_without_position_hint" not in self.ambiguity_flags:
                    self.ambiguity_flags.append("action_without_position_hint")

        return self

    @model_validator(mode='after')
    def validate_direction_consistency(self) -> NormalizedInvestmentIntent:
        """
        Validate consistency between direction and position_delta_hint.

        Rules:
        - bearish + (open/add) → suspicious (bearish usually means reduce/exit/short)
        - bullish + exit → suspicious (bullish usually means hold/add/open)
        """
        if self.direction == "bearish":
            if self.position_delta_hint in ["open", "add"]:
                # Bearish + open/add = short signal, flag
                if "bearish_position_mismatch" not in self.ambiguity_flags:
                    self.ambiguity_flags.append("bearish_position_mismatch")

        if self.direction == "bullish":
            if self.position_delta_hint == "exit":
                # Bullish + exit is unusual
                if "bullish_exit_mismatch" not in self.ambiguity_flags:
                    self.ambiguity_flags.append("bullish_exit_mismatch")

        return self

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def is_actionable(self) -> bool:
        """
        Check if this intent represents an actionable signal.

        Returns:
            True if actionability is explicit_action or watch with sufficient confidence.
        """
        if self.actionability == "explicit_action":
            return self.confidence >= 0.5
        if self.actionability == "watch":
            return self.confidence >= 0.7  # Higher threshold for watch signals
        return False

    def needs_review(self) -> bool:
        """
        Check if this intent needs manual review.

        Returns:
            True if review_required or has ambiguity flags.
        """
        return (
            self.actionability == "review_required"
            or len(self.ambiguity_flags) > 0
            or self.confidence < 0.5
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary with ISO 8601 timestamps.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return self.model_dump(mode='json')

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedInvestmentIntent:
        """
        Create NormalizedInvestmentIntent from dictionary.

        Args:
            data: Dictionary with intent data.

        Returns:
            NormalizedInvestmentIntent instance.
        """
        # Handle datetime string conversion
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        return cls.model_validate(data)

    def summarize(self) -> str:
        """
        Get human-readable summary of this intent.

        Returns:
            Summary string for logging/debugging.
        """
        target = self.target_symbol or self.target_name
        return (
            f"[{self.intent_id[:8]}] "
            f"{self.direction} on {target} "
            f"({self.actionability}, {self.position_delta_hint}) "
            f"conviction={self.conviction:.2f} "
            f"confidence={self.confidence:.2f}"
        )


# =============================================================================
# Container Models
# =============================================================================

class IntentBatch(BaseModel):
    """Container for multiple intents from a single extraction."""
    model_config = ConfigDict(strict=True)

    intents: List[NormalizedInvestmentIntent] = Field(
        default_factory=list,
        description="List of extracted intents"
    )

    envelope_id: Optional[str] = Field(
        None,
        description="Parent envelope ID"
    )

    extraction_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When extraction was performed"
    )

    model_version: str = Field(
        "v1.0",
        description="Model version used for extraction"
    )

    # Statistics
    total_intents: int = Field(0, description="Total number of intents")
    actionable_count: int = Field(0, description="Number of actionable intents")
    review_required_count: int = Field(0, description="Number needing review")

    @model_validator(mode='after')
    def compute_stats(self) -> IntentBatch:
        """Auto-compute statistics."""
        self.total_intents = len(self.intents)
        self.actionable_count = sum(1 for i in self.intents if i.is_actionable())
        self.review_required_count = sum(1 for i in self.intents if i.needs_review())
        return self
