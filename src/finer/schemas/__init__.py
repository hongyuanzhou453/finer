"""Finer Schema Module.

This module defines the canonical data structures for the Finer pipeline:
- F0/F1: Content envelope and quality schemas
- F2: Entity/Temporal/Evidence anchoring
- F3: Investment intent (pre-TradeAction)
- F4: Policy mapping (intent-to-action hints)
- F5: Trade action output template
- F6: RLHF feedback
"""

# =============================================================================
# V0/V0.5 Content Envelope Schemas
# =============================================================================

from finer.schemas.quality import (
    QualityCard,
    GATE_STATUS_LITERAL,
)

from finer.schemas.evidence import (
    EvidenceSpan,
)

from finer.schemas.temporal import (
    TemporalAnchor,
    TEMPORAL_ANCHOR_TYPE_LITERAL,
    RESOLUTION_STRATEGY_LITERAL,
)

from finer.schemas.entity_anchor import (
    EntityAnchor,
    ENTITY_TYPE_LITERAL,
)

from finer.schemas.content_envelope import (
    ContentEnvelope,
    ContentBlock,
    BLOCK_TYPE_LITERAL,
    SOURCE_TYPE_LITERAL,
)

# =============================================================================
# F5 Extraction Schemas
# =============================================================================

from finer.schemas.event import (
    TradingAction,
    EventWithActions,
    ExtractionResult,
    # Type aliases for F5 extraction
    ACTION_TYPE_LITERAL,
    INSTRUMENT_TYPE_LITERAL,
)

from finer.schemas.enriched_event import (
    MarketDataSnapshot,
    SentimentSnapshot,
    StrategyAssessment,
    PriceValidation,
    EnrichedEventWithActions,
    EnrichedExtractionResult,
)

# =============================================================================
# V1 Investment Intent Schemas (Pre-TradeAction)
# =============================================================================

from finer.schemas.investment_intent import (
    # Type literals
    TARGET_TYPE_LITERAL,
    DIRECTION_LITERAL,
    ACTIONABILITY_LITERAL,
    POSITION_DELTA_HINT_LITERAL,
    RISK_PREFERENCE_LITERAL,
    TIME_HORIZON_LITERAL,
    # Main models
    NormalizedInvestmentIntent,
    IntentBatch,
)

# =============================================================================
# F4 Policy Mapping Schemas
# =============================================================================

from finer.schemas.policy import (
    # Literal types
    ACTION_HINT_LITERAL,
    POSITION_SIZING_HINT_LITERAL,
    MAX_POSITION_HINT_LITERAL,
    HOLDING_PERIOD_HINT_LITERAL,
    CANONICAL_TRACE_STATUS_LITERAL,
    DECISION_TYPE_LITERAL,
    # Models
    PolicyRiskConstraints,
    PolicyLayerTrace,
    PolicyDecision,
    PolicyMappingResult,
    PolicyMappedIntent,
    PolicyContext,
    PolicyMappingBatch,
)

# =============================================================================
# F5 Trade Action Schemas
# =============================================================================

from finer.schemas.trade_action import (
    # Enums
    TradeDirection,
    ActionType,
    TriggerType,
    ValidationStatus,
    ExitReason,
    # Nested models
    SourceInfo,
    TargetInfo,
    ActionStep,
    MarketEnrichment,
    RLHFFeedback,
    BacktestResult,
    # Main model
    TradeAction,
    TradeActionBatch,
)

from finer.schemas.kol_profile import (
    PlatformIdentity,
    KOLProfile,
    KOLProfileCreate,
    PlatformLink,
)

from finer.schemas.lineage import (
    DataLineage,
    VersionInfo,
    PipelineRunInfo,
)

# =============================================================================
# F1.5 Topic Assembly Schemas
# =============================================================================

from finer.schemas.topic_block import (
    TopicType,
    TOPIC_TYPE_LITERAL,
    TopicBlock,
    TopicAssemblyResult,
)

__all__ = [
    # From quality.py (V0/V0.5)
    "QualityCard",
    "GATE_STATUS_LITERAL",
    # From evidence.py (V0/V0.5)
    "EvidenceSpan",
    # From temporal.py (V0/V0.5)
    "TemporalAnchor",
    "TEMPORAL_ANCHOR_TYPE_LITERAL",
    "RESOLUTION_STRATEGY_LITERAL",
    # From entity_anchor.py (V0/V0.5)
    "EntityAnchor",
    "ENTITY_TYPE_LITERAL",
    # From content_envelope.py (F1/F2)
    "ContentEnvelope",
    "ContentBlock",
    "BLOCK_TYPE_LITERAL",
    "SOURCE_TYPE_LITERAL",
    # From event.py (F5 extraction)
    "TradingAction",
    "EventWithActions",
    "ExtractionResult",
    "ACTION_TYPE_LITERAL",
    "INSTRUMENT_TYPE_LITERAL",
    # From enriched_event.py
    "MarketDataSnapshot",
    "SentimentSnapshot",
    "StrategyAssessment",
    "PriceValidation",
    "EnrichedEventWithActions",
    "EnrichedExtractionResult",
    # From investment_intent.py (F3 intent layer)
    "TARGET_TYPE_LITERAL",
    "DIRECTION_LITERAL",
    "ACTIONABILITY_LITERAL",
    "POSITION_DELTA_HINT_LITERAL",
    "RISK_PREFERENCE_LITERAL",
    "TIME_HORIZON_LITERAL",
    "NormalizedInvestmentIntent",
    "IntentBatch",
    # From policy.py (F4 policy mapping)
    "ACTION_HINT_LITERAL",
    "POSITION_SIZING_HINT_LITERAL",
    "MAX_POSITION_HINT_LITERAL",
    "HOLDING_PERIOD_HINT_LITERAL",
    "CANONICAL_TRACE_STATUS_LITERAL",
    "DECISION_TYPE_LITERAL",
    "PolicyRiskConstraints",
    "PolicyLayerTrace",
    "PolicyDecision",
    "PolicyMappingResult",
    "PolicyMappedIntent",
    "PolicyContext",
    "PolicyMappingBatch",
    # From trade_action.py (F5 execution)
    "TradeDirection",
    "ActionType",
    "TriggerType",
    "ValidationStatus",
    "ExitReason",
    "SourceInfo",
    "TargetInfo",
    "ActionStep",
    "MarketEnrichment",
    "RLHFFeedback",
    "BacktestResult",
    "TradeAction",
    "TradeActionBatch",
    # From kol_profile.py
    "PlatformIdentity",
    "KOLProfile",
    "KOLProfileCreate",
    "PlatformLink",
    # From lineage.py
    "DataLineage",
    "VersionInfo",
    "PipelineRunInfo",
    # From topic_block.py (F1.5 topic assembly)
    "TopicType",
    "TOPIC_TYPE_LITERAL",
    "TopicBlock",
    "TopicAssemblyResult",
]