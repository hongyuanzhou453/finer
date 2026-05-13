"""Canonical F3 → F4 → F5 Pipeline Runner.

Provides run_canonical_extraction() which chains:
  F3 RuleBasedIntentExtractor → F4 PolicyMapper → F5 TradeAction construction

Two F5 strategies:
  - "programmatic": deterministic construction from policy hints (no LLM)
  - "llm_guided": LLM-assisted generation with policy context

Both strategies produce TradeActions with full canonical trace:
  intent_id + policy_id + evidence_span_ids + execution_timing
"""

from __future__ import annotations

import logging
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


# ── Public API ───────────────────────────────────────────────────────────────

async def run_canonical_extraction(
    text: str,
    context: Dict[str, Any],
    strategy: str = "programmatic",
) -> List[TradeAction]:
    """Canonical F3 → F4 → F5 pipeline.

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
    if strategy not in ("programmatic", "llm_guided"):
        raise ValueError(f"Unknown strategy: {strategy!r}. Use 'programmatic' or 'llm_guided'.")

    # F1: Build minimal ContentEnvelope from raw text
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

    # F5: TradeAction construction
    if strategy == "programmatic":
        actions = _build_actions_programmatic(intents, policy_batch, envelope)
    else:
        actions = await _build_actions_llm(text, intents, policy_batch, envelope)

    logger.info(
        "Canonical extraction complete: %d intents → %d policy mappings → %d trade actions (strategy=%s)",
        len(intents),
        len(policy_batch.mappings),
        len(actions),
        strategy,
    )
    return actions


# ── F1: Envelope construction ────────────────────────────────────────────────

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
) -> List[TradeAction]:
    """Build TradeActions deterministically from policy hints."""
    # Index intents by id for quick lookup
    intent_map: Dict[str, NormalizedInvestmentIntent] = {
        i.intent_id: i for i in intents
    }

    actions: List[TradeAction] = []
    now = datetime.now()

    for mapped in policy_batch.mapped_intents:
        if mapped.action_hint not in EXECUTABLE_HINTS:
            continue

        intent = intent_map.get(mapped.intent_id)
        if intent is None:
            logger.warning("Intent %s not found in intent map, skipping", mapped.intent_id)
            continue

        action_type = ACTION_HINT_TO_ACTION_TYPE[mapped.action_hint]
        direction = _resolve_direction(intent, mapped)
        position_pct = POSITION_SIZING_TO_PCT.get(mapped.position_sizing_hint)

        timing = _build_execution_timing(
            envelope=envelope,
            market=intent.market or "CN",
        )

        ta = TradeAction(
            intent_id=intent.intent_id,
            policy_id=mapped.policy_id,
            evidence_span_ids=list(intent.evidence_span_ids),
            execution_timing=timing,
            effective_trade_at=None,
            source=SourceInfo(
                creator_id=envelope.creator_id or "unknown",
                content_id=envelope.envelope_id,
                evidence_text=mapped.original_intent_summary[:200],
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

    return actions


# ── F5 Strategy B: LLM-guided ────────────────────────────────────────────────

async def _build_actions_llm(
    text: str,
    intents: List[NormalizedInvestmentIntent],
    policy_batch: PolicyMappingBatch,
    envelope: ContentEnvelope,
) -> List[TradeAction]:
    """Build TradeActions using LLM with policy context, then backfill trace IDs."""
    from finer.llm import LLMClient

    intent_map: Dict[str, NormalizedInvestmentIntent] = {
        i.intent_id: i for i in intents
    }

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
        return []

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
        return _build_actions_programmatic(intents, policy_batch, envelope)

    # Backfill trace IDs from policy mappings
    actions: List[TradeAction] = []
    now = datetime.now()

    # Build lookup from (target, action_hint) → mapped intent
    mapped_by_target: Dict[tuple, PolicyMappedIntent] = {}
    for mapped in policy_batch.mapped_intents:
        if mapped.action_hint in EXECUTABLE_HINTS:
            intent = intent_map.get(mapped.intent_id)
            if intent:
                key = (intent.target_symbol or intent.target_name, mapped.action_hint)
                mapped_by_target[key] = mapped

    for raw in raw_actions:
        ticker = raw.get("ticker", "")
        action_hint_raw = raw.get("action_type", "long")
        # Map LLM action_type back to possible policy action_hints
        hint_from_type = {
            "long": ["open_position", "add_position"],
            "close_long": ["close_position", "reduce_position"],
            "hold": ["hold_position"],
        }
        action_hints = hint_from_type.get(action_hint_raw, ["open_position"])

        # Find matching mapped intent
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
            logger.debug("No policy mapping match for LLM action: %s %s", ticker, action_hint)
            continue

        direction_str = raw.get("direction", "bullish")
        direction = TradeDirection(direction_str) if direction_str in TradeDirection.__members__.values() else TradeDirection.BULLISH

        atype = ActionType(raw.get("action_type", "long")) if raw.get("action_type") in ActionType.__members__.values() else ActionType.LONG

        timing = _build_execution_timing(
            envelope=envelope,
            market=matched_intent.market or "CN",
        )

        ta = TradeAction(
            intent_id=matched_intent.intent_id,
            policy_id=matched_mapped.policy_id,
            evidence_span_ids=list(matched_intent.evidence_span_ids),
            execution_timing=timing,
            source=SourceInfo(
                creator_id=envelope.creator_id or "unknown",
                content_id=envelope.envelope_id,
                evidence_text=matched_mapped.original_intent_summary[:200],
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

    return actions


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
) -> ExecutionTiming:
    """Build ExecutionTiming from envelope metadata."""
    now = datetime.now()
    published = envelope.published_at or now

    timezone = "Asia/Shanghai" if market == "CN" else "America/New_York"
    if market == "HK":
        timezone = "Asia/Hong_Kong"

    return ExecutionTiming(
        intent_published_at=published,
        intent_effective_at=None,
        action_decision_at=now,
        action_executable_at=now,
        market=market,
        timezone=timezone,
        market_session_at_publish=MarketSession.UNKNOWN,
        timing_policy_id="canonical-runner-v1",
    )


def _parse_llm_json(response: str) -> List[Dict[str, Any]]:
    """Parse JSON array from LLM response, handling markdown fences."""
    import json

    text = response.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON array")
        return []
