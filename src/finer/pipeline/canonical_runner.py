"""Canonical F3 → F4 → F5 Pipeline Runner.

Provides two entry points:

1. run_canonical_from_artifacts() — **canonical**: consumes structured
   upstream artifacts (intents, policy mappings, evidence spans, temporal
   anchors, envelope).  Every TradeAction carries intent_id, policy_id,
   evidence_span_ids, and execution_timing.  Non-executable policy hints
   are recorded as RejectedIntent for audit.

2. run_canonical_extraction() — **deprecated**: accepts raw text,
   fabricates a minimal ContentEnvelope, and runs F3→F4→F5.
   Retained only for backward compatibility and legacy baseline.

Two F5 strategies:
  - "programmatic": deterministic construction from policy hints (no LLM)
  - "llm_guided": LLM-assisted generation with policy context

Both strategies produce TradeActions with full canonical trace:
  intent_id + policy_id + evidence_span_ids + execution_timing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from finer.schemas.content_envelope import BlockQuality, ContentBlock, ContentEnvelope
from finer.schemas.quality import QualityCard
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import (
    PolicyContext,
    PolicyMappedIntent,
    PolicyMappingBatch,
    PolicyMappingResult,
)
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    ExecutionTiming,
    MarketSession,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)

logger = logging.getLogger(__name__)

# ── Canonical constants ──────────────────────────────────────────────────────

EXECUTABLE_HINTS: set[str] = {
    "open_position",
    "add_position",
    "reduce_position",
    "close_position",
    "hold_position",
}

ACTION_HINT_TO_ACTION_TYPE: dict[str, ActionType] = {
    "open_position": ActionType.LONG,
    "add_position": ActionType.LONG,
    "close_position": ActionType.CLOSE_LONG,
    "reduce_position": ActionType.CLOSE_LONG,
    "hold_position": ActionType.HOLD,
}

ACTION_HINT_TO_DIRECTION: dict[str, TradeDirection] = {
    "open_position": TradeDirection.BULLISH,
    "add_position": TradeDirection.BULLISH,
    "close_position": TradeDirection.BEARISH,
    "reduce_position": TradeDirection.BEARISH,
    "hold_position": TradeDirection.NEUTRAL,
}

POSITION_SIZING_TO_PCT: dict[str, Optional[float]] = {
    "none": None,
    "small": 0.05,
    "medium": 0.10,
    "large": 0.20,
    "review_required": None,
}


# ── Result models ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RejectedIntent:
    """Audit record for a non-executable policy hint that was excluded from F5."""

    intent_id: str
    policy_id: str
    action_hint: str
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CanonicalRunnerResult:
    """Output of the canonical F3→F4→F5 runner.

    Contains both the executable TradeActions and the rejected non-executable
    intents for full audit trail.
    """

    trade_actions: List[TradeAction]
    rejected_intents: List[RejectedIntent]
    total_intents: int = 0
    total_policy_mappings: int = 0
    strategy: str = "programmatic"

    @property
    def executable_count(self) -> int:
        return len(self.trade_actions)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_intents)


# ── Public API ───────────────────────────────────────────────────────────────


async def run_canonical_from_artifacts(
    intents: List[NormalizedInvestmentIntent],
    policy_batch: PolicyMappingBatch,
    evidence_spans: List[EvidenceSpan],
    envelope: ContentEnvelope,
    temporal_anchors: Optional[List[Any]] = None,
    strategy: str = "programmatic",
) -> CanonicalRunnerResult:
    """Canonical F3 → F4 → F5 pipeline consuming upstream artifacts.

    This is the **canonical entry point**. It accepts structured outputs
    from F1/F2/F3/F4 and produces TradeActions with full provenance chain.

    Args:
        intents: F3 NormalizedInvestmentIntent list.
        policy_batch: F4 PolicyMappingBatch (mappings + mapped_intents).
        evidence_spans: F2 EvidenceSpan list for validation and evidence text.
        envelope: F1 ContentEnvelope (provides published_at, creator_id, etc.).
        temporal_anchors: F2 TemporalAnchor list (optional, for timing resolution).
        strategy: F5 construction strategy — "programmatic" or "llm_guided".

    Returns:
        CanonicalRunnerResult with trade_actions and rejected_intents.
    """
    if strategy not in ("programmatic", "llm_guided"):
        raise ValueError(f"Unknown strategy: {strategy!r}. Use 'programmatic' or 'llm_guided'.")

    if not intents:
        logger.info("No intents provided to canonical runner")
        return CanonicalRunnerResult(strategy=strategy)

    # Index evidence spans by ID for validation
    evidence_map: Dict[str, EvidenceSpan] = {
        span.evidence_span_id: span for span in evidence_spans
    }

    # Build temporal anchor index
    temporal_list = temporal_anchors or []

    # F5: TradeAction construction
    if strategy == "programmatic":
        result = _build_actions_programmatic(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            evidence_map=evidence_map,
            temporal_anchors=temporal_list,
        )
    else:
        result = await _build_actions_llm(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            evidence_map=evidence_map,
            temporal_anchors=temporal_list,
        )

    result.total_intents = len(intents)
    result.total_policy_mappings = len(policy_batch.mapped_intents)
    result.strategy = strategy

    logger.info(
        "Canonical extraction complete: %d intents → %d policy mappings → "
        "%d trade actions, %d rejected (strategy=%s)",
        len(intents),
        len(policy_batch.mapped_intents),
        result.executable_count,
        result.rejected_count,
        strategy,
    )
    return result


async def run_canonical_extraction(
    text: str,
    context: Dict[str, Any],
    strategy: str = "programmatic",
) -> List[TradeAction]:
    """Canonical F3 → F4 → F5 pipeline.

    .. deprecated::
        Use :func:`run_canonical_from_artifacts` with upstream artifacts instead.
        This function fabricates a minimal ContentEnvelope from raw text and
        should only be used for legacy baseline or backward compatibility.

    Args:
        text: Raw text content to extract trade actions from.
        context: Extraction context with keys:
            - source_id (str): Content source identifier
            - author (str, optional): Content author / KOL ID
            - timestamp (str, optional): ISO 8601 content timestamp
            - kol_id (str, optional): KOL identifier for policy context
        strategy: F5 construction strategy:
            - "programmatic": deterministic, no LLM
            - "llm_guided": LLM-assisted with policy context

    Returns:
        List of canonical TradeActions (canonical_trace_status == "canonical").
    """
    logger.warning(
        "run_canonical_extraction() is deprecated. "
        "Use run_canonical_from_artifacts() with upstream artifacts."
    )

    if strategy not in ("programmatic", "llm_guided"):
        raise ValueError(f"Unknown strategy: {strategy!r}. Use 'programmatic' or 'llm_guided'.")

    # F1: Build minimal ContentEnvelope from raw text (legacy path)
    envelope = _build_envelope(text, context)

    # F3: Intent extraction
    from finer.extraction.intent_extractor import RuleBasedIntentExtractor

    extractor = RuleBasedIntentExtractor()
    intent_result = extractor.extract(envelope)
    intents = intent_result.intents

    if not intents:
        logger.info("No intents extracted from text")
        return []

    # F4: Policy mapping
    from finer.policy.policy_mapper import PolicyMapper

    kol_id = context.get("kol_id") or context.get("author")
    policy_ctx = PolicyContext(kol_id=kol_id) if kol_id else None
    mapper = PolicyMapper(context=policy_ctx)
    policy_batch = mapper.map_batch(intents)

    # F5: TradeAction construction via the canonical entry point
    evidence_map: Dict[str, EvidenceSpan] = {
        span.evidence_span_id: span for span in intent_result.evidence_spans
    }
    temporal_list = list(getattr(envelope, 'temporal_anchors', []) or [])

    if strategy == "programmatic":
        result = _build_actions_programmatic(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            evidence_map=evidence_map,
            temporal_anchors=temporal_list,
        )
    else:
        result = await _build_actions_llm(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            evidence_map=evidence_map,
            temporal_anchors=temporal_list,
            text=text,
        )

    logger.info(
        "Canonical extraction complete: %d intents → %d policy mappings → %d trade actions (strategy=%s)",
        len(intents),
        len(policy_batch.mappings),
        result.executable_count,
        strategy,
    )
    return result.trade_actions


# ── F1: Envelope construction (legacy path only) ────────────────────────────

def _build_envelope(text: str, context: Dict[str, Any]) -> ContentEnvelope:
    """Build a minimal ContentEnvelope from raw text for F3 consumption."""
    import uuid

    block = ContentBlock(
        block_id=f"block-{uuid.uuid4().hex[:8]}",
        block_type="paragraph",
        text=text,
        order_index=0,
        quality=BlockQuality(
            readability=1.0,
            extraction_confidence=0.8,
            structural_confidence=1.0,
            completeness=1.0,
            noise_score=0.0,
            quality_flags=[],
        ),
        evidence_spans=[],
        metadata={},
    )

    published_at = None
    if ts := context.get("timestamp"):
        try:
            published_at = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            pass

    return ContentEnvelope(
        envelope_id=f"env-{uuid.uuid4().hex[:8]}",
        source_type="text",
        creator_id=context.get("author") or context.get("kol_id"),
        published_at=published_at,
        ingested_at=datetime.now(),
        blocks=[block],
        quality_card=QualityCard(
            readability_score=0.8,
            semantic_completeness_score=0.8,
            financial_relevance_score=0.8,
            entity_resolution_score=0.8,
            temporal_resolution_score=0.8,
            evidence_traceability_score=0.8,
            overall_score=0.8,
            gate_status="pass",
            gate_reasons=[],
        ),
        temporal_anchors=[],
        entity_anchors=[],
        metadata={},
    )


# ── F5 Strategy A: Programmatic ──────────────────────────────────────────────

def _build_actions_programmatic(
    intents: List[NormalizedInvestmentIntent],
    policy_batch: PolicyMappingBatch,
    envelope: ContentEnvelope,
    evidence_map: Optional[Dict[str, EvidenceSpan]] = None,
    temporal_anchors: Optional[List[Any]] = None,
) -> CanonicalRunnerResult:
    """Build TradeActions deterministically from policy hints.

    Records non-executable policy hints as RejectedIntent for audit.
    """
    intent_map: Dict[str, NormalizedInvestmentIntent] = {
        i.intent_id: i for i in intents
    }

    actions: List[TradeAction] = []
    rejected: List[RejectedIntent] = []

    for mapped in policy_batch.mapped_intents:
        # Non-executable → rejection record
        if mapped.action_hint not in EXECUTABLE_HINTS:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="non_executable_action_hint",
            ))
            continue

        intent = intent_map.get(mapped.intent_id)
        if intent is None:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="intent_not_found",
            ))
            continue

        # Validate evidence
        evidence_ids = list(intent.evidence_span_ids)
        if not evidence_ids:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="no_evidence_spans",
            ))
            continue

        # Validate evidence resolution
        if evidence_map:
            missing = [eid for eid in evidence_ids if eid not in evidence_map]
            if missing:
                rejected.append(RejectedIntent(
                    intent_id=mapped.intent_id,
                    policy_id=mapped.policy_id,
                    action_hint=mapped.action_hint,
                    reason="evidence_span_missing",
                ))
                continue

        # Validate ticker
        if not intent.target_symbol and not intent.target_name:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="no_ticker_symbol",
            ))
            continue

        action_type = ACTION_HINT_TO_ACTION_TYPE[mapped.action_hint]
        direction = _resolve_direction(intent, mapped)
        position_pct = POSITION_SIZING_TO_PCT.get(mapped.position_sizing_hint)

        timing = _build_execution_timing(
            envelope=envelope,
            market=intent.market or "CN",
            temporal_anchors=temporal_anchors,
            intent_id=intent.intent_id,
        )

        # Build evidence text from evidence spans
        evidence_text = _build_evidence_text(evidence_ids, evidence_map)

        ta = TradeAction(
            intent_id=intent.intent_id,
            policy_id=mapped.policy_id,
            evidence_span_ids=evidence_ids,
            execution_timing=timing,
            effective_trade_at=None,
            source=SourceInfo(
                creator_id=envelope.creator_id or "unknown",
                content_id=envelope.envelope_id,
                evidence_text=evidence_text[:500],
            ),
            target=TargetInfo(
                ticker=intent.target_symbol or intent.target_name,
                market=intent.market or "CN",
                ticker_normalized=intent.target_symbol,
                instrument_type=_target_type_to_instrument(intent.target_type),
                company_name=intent.target_name if intent.target_symbol else None,
            ),
            direction=direction,
            action_chain=[
                ActionStep(
                    sequence=1,
                    action_type=action_type,
                    trigger_type=TriggerType.MANUAL,
                    position_size_pct=position_pct,
                ),
            ],
            confidence=intent.confidence,
            time_horizon=mapped.holding_period_hint,
            requires_manual_review=mapped.requires_human_review,
            rationale=f"Canonical F3→F4→F5: {mapped.action_hint} via {mapped.policy_id}",
        )
        actions.append(ta)

    return CanonicalRunnerResult(
        trade_actions=actions,
        rejected_intents=rejected,
    )


# ── F5 Strategy B: LLM-guided ────────────────────────────────────────────────

async def _build_actions_llm(
    intents: List[NormalizedInvestmentIntent],
    policy_batch: PolicyMappingBatch,
    envelope: ContentEnvelope,
    evidence_map: Optional[Dict[str, EvidenceSpan]] = None,
    temporal_anchors: Optional[List[Any]] = None,
    text: Optional[str] = None,
) -> CanonicalRunnerResult:
    """Build TradeActions using LLM with policy context, then backfill trace IDs."""
    from finer.llm import LLMClient

    intent_map: Dict[str, NormalizedInvestmentIntent] = {
        i.intent_id: i for i in intents
    }

    # Derive text from envelope blocks if not provided
    if text is None:
        text = "\n\n".join(
            b.text for b in envelope.blocks
            if hasattr(b, 'text') and b.text and len(b.text.strip()) >= 4
        )

    # Build prompt with policy context
    policy_context_lines = []
    for mapped in policy_batch.mapped_intents:
        if mapped.action_hint not in EXECUTABLE_HINTS:
            continue
        intent = intent_map.get(mapped.intent_id)
        if intent is None:
            continue
        policy_context_lines.append(
            f"- intent_id={mapped.intent_id}, target={intent.target_symbol or intent.target_name}, "
            f"direction={intent.direction}, action_hint={mapped.action_hint}, "
            f"position_sizing={mapped.position_sizing_hint}, holding={mapped.holding_period_hint}"
        )

    if not policy_context_lines:
        return CanonicalRunnerResult(trade_actions=[], rejected_intents=[])

    policy_context = "\n".join(policy_context_lines)

    prompt = f"""Based on the following text and pre-computed policy mappings, generate a JSON array of trade actions.

## Text
{text[:3000]}

## Policy Mappings (pre-computed by F4)
{policy_context}

## Output Format
Return a JSON array. Each element:
```json
{{
  "ticker": "stock ticker",
  "market": "US/CN/HK",
  "direction": "bullish/bearish/neutral",
  "action_type": "long/close_long/hold",
  "position_size_pct": 0.05,
  "confidence": 0.85,
  "notes": "brief rationale"
}}
```
Only include actions for the executable policy mappings listed above. Return [] if none."""

    client = LLMClient.auto()
    try:
        response = client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw_actions = _parse_llm_json(response)
    except Exception as e:
        logger.warning("LLM F5 failed, falling back to programmatic: %s", e)
        return _build_actions_programmatic(
            intents, policy_batch, envelope, evidence_map, temporal_anchors
        )

    # Backfill trace IDs from policy mappings
    actions: List[TradeAction] = []
    rejected: List[RejectedIntent] = []

    for raw in raw_actions:
        ticker = raw.get("ticker", "")
        action_hint_raw = raw.get("action_type", "long")
        hint_from_type = {
            "long": ["open_position", "add_position"],
            "close_long": ["close_position", "reduce_position"],
            "hold": ["hold_position"],
        }
        action_hints = hint_from_type.get(action_hint_raw, ["open_position"])

        matched_mapped = None
        matched_intent = None
        for mapped in policy_batch.mapped_intents:
            if mapped.action_hint not in action_hints:
                continue
            intent = intent_map.get(mapped.intent_id)
            if intent and (intent.target_symbol == ticker or intent.target_name == ticker):
                matched_mapped = mapped
                matched_intent = intent
                break

        if not matched_mapped or not matched_intent:
            logger.debug("No policy mapping match for LLM action: %s %s", ticker, action_hint_raw)
            continue

        direction_str = raw.get("direction", "bullish")
        direction = TradeDirection(direction_str) if direction_str in TradeDirection.__members__.values() else TradeDirection.BULLISH

        atype = ActionType(raw.get("action_type", "long")) if raw.get("action_type") in ActionType.__members__.values() else ActionType.LONG

        timing = _build_execution_timing(
            envelope=envelope,
            market=matched_intent.market or "CN",
            temporal_anchors=temporal_anchors,
            intent_id=matched_intent.intent_id,
        )

        evidence_ids = list(matched_intent.evidence_span_ids)
        evidence_text = _build_evidence_text(evidence_ids, evidence_map)

        ta = TradeAction(
            intent_id=matched_intent.intent_id,
            policy_id=matched_mapped.policy_id,
            evidence_span_ids=evidence_ids,
            execution_timing=timing,
            source=SourceInfo(
                creator_id=envelope.creator_id or "unknown",
                content_id=envelope.envelope_id,
                evidence_text=evidence_text[:500],
            ),
            target=TargetInfo(
                ticker=ticker,
                market=raw.get("market", matched_intent.market or "CN"),
                ticker_normalized=ticker,
            ),
            direction=direction,
            action_chain=[
                ActionStep(
                    sequence=1,
                    action_type=atype,
                    trigger_type=TriggerType.MANUAL,
                    position_size_pct=raw.get("position_size_pct"),
                ),
            ],
            confidence=raw.get("confidence", matched_intent.confidence),
            time_horizon=matched_mapped.holding_period_hint,
            rationale=f"LLM-guided F5: {raw.get('notes', matched_mapped.action_hint)}",
        )
        actions.append(ta)

    # Record non-executable mapped intents as rejected
    for mapped in policy_batch.mapped_intents:
        if mapped.action_hint not in EXECUTABLE_HINTS:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="non_executable_action_hint",
            ))

    return CanonicalRunnerResult(
        trade_actions=actions,
        rejected_intents=rejected,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_direction(
    intent: NormalizedInvestmentIntent,
    mapped: PolicyMappedIntent,
) -> TradeDirection:
    """Resolve TradeDirection from intent and policy mapping."""
    hint = mapped.action_hint
    if hint in ("close_position", "reduce_position"):
        return TradeDirection.BEARISH
    if hint == "hold_position":
        return TradeDirection.NEUTRAL
    # open_position / add_position: use intent direction
    return TradeDirection(intent.direction) if intent.direction in TradeDirection.__members__.values() else TradeDirection.BULLISH


def _target_type_to_instrument(target_type: str) -> str:
    """Map F3 target_type to F5 instrument_type."""
    mapping = {
        "stock": "stock",
        "etf": "etf",
        "index": "index_future",
        "crypto": "crypto",
        "sector": "unspecified",
        "company": "stock",
    }
    return mapping.get(target_type, "unspecified")


def _build_execution_timing(
    envelope: ContentEnvelope,
    market: str = "CN",
    temporal_anchors: Optional[List[Any]] = None,
    intent_id: Optional[str] = None,
) -> ExecutionTiming:
    """Build ExecutionTiming using MarketCalendarTimingPolicy.

    Uses the deterministic market calendar timing policy to compute
    action_executable_at, instead of ad-hoc datetime arithmetic.
    """
    from finer.execution.timing_policy import MarketCalendarTimingPolicy

    published_at = envelope.published_at or datetime.now()

    # Determine intent_effective_at from temporal anchors
    intent_effective_at = None
    if temporal_anchors:
        # Prefer effective_trade_at, then mentioned_at
        for anchor in temporal_anchors:
            if hasattr(anchor, 'anchor_type') and anchor.anchor_type == "effective_trade_at":
                if hasattr(anchor, 'resolved_time') and anchor.resolved_time:
                    intent_effective_at = anchor.resolved_time
                    break
        if intent_effective_at is None:
            for anchor in temporal_anchors:
                if hasattr(anchor, 'anchor_type') and anchor.anchor_type == "mentioned_at":
                    if hasattr(anchor, 'resolved_time') and anchor.resolved_time:
                        intent_effective_at = anchor.resolved_time
                        break

    # Determine timezone from market
    timezone_map = {
        "CN": "Asia/Shanghai",
        "HK": "Asia/Hong_Kong",
        "US": "America/New_York",
    }
    tz = timezone_map.get(market, "Asia/Shanghai")

    # Use MarketCalendarTimingPolicy for deterministic timing
    policy = MarketCalendarTimingPolicy()
    result = policy.compute_timing(
        published_at=published_at,
        market=market,
        timezone=tz,
        intent_effective_at=intent_effective_at,
    )

    return ExecutionTiming(
        intent_published_at=result.intent_published_at,
        intent_effective_at=intent_effective_at,
        action_decision_at=datetime.now(),
        action_executable_at=result.action_executable_at,
        market=result.market,
        timezone=result.timezone,
        market_session_at_publish=MarketSession(result.market_session_at_publish),
        timing_policy_id=result.timing_policy_id,
    )


def _build_evidence_text(
    evidence_ids: List[str],
    evidence_map: Optional[Dict[str, EvidenceSpan]],
) -> str:
    """Build concatenated evidence text from evidence span IDs."""
    if not evidence_map:
        return ""
    parts = []
    for eid in evidence_ids:
        span = evidence_map.get(eid)
        if span and hasattr(span, 'text'):
            parts.append(span.text)
    return " | ".join(parts)


def _parse_llm_json(response: str) -> List[Dict[str, Any]]:
    """Parse JSON array from LLM response, handling markdown fences."""
    import json

    text = response.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON array")
        return []
