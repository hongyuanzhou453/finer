"""Canonical F3 → F4 → F5 Pipeline Runner.

Provides three entry points:

1. run_canonical_from_artifacts() — **canonical**: consumes structured
   upstream artifacts (intents, policy mappings, evidence spans, temporal
   anchors, envelope).  Every TradeAction carries intent_id, policy_id,
   evidence_span_ids, and execution_timing.  Non-executable policy hints
   are recorded as RejectedIntent for audit.

2. run_canonical_from_envelope() — **canonical**: consumes a real (F1/F2)
   ContentEnvelope and runs F3→F4→F5, so F3 resolves target symbols from
   envelope.entity_anchors and F5 timing uses envelope.temporal_anchors.
   This is the entry point the F5 route uses for F2-anchored envelopes.

3. run_canonical_extraction() — **deprecated**: accepts raw text,
   fabricates a minimal ContentEnvelope, and runs F3→F4→F5.
   Retained only for backward compatibility and legacy baseline.

Two F5 strategies:
  - "programmatic": deterministic construction from policy hints (no LLM)
  - "llm_guided": LLM-assisted generation with policy context

Both strategies produce TradeActions with full canonical trace:
  intent_id + policy_id + evidence_span_ids + execution_timing

F2-grounding hard gate: a TradeAction's ``evidence_span_ids`` are re-resolved
against the envelope's F2 block evidence (``_index_f2_evidence`` /
``_resolve_f2_grounding``), not the intent's own F3 spans. When the envelope is
F2-anchored, an intent that cannot be grounded in F2 evidence is rejected
(``evidence_not_grounded_in_f2``). Fabricated/raw-text (dev) envelopes carry no
F2 evidence, so their actions get empty evidence and the TradeAction validator
downgrades them to ``partial`` — they no longer masquerade as canonical.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from finer.schemas.content_envelope import BlockQuality, ContentBlock, ContentEnvelope
from finer.schemas.quality import QualityCard
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.temporal import TemporalAnchor
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import (
    PolicyContext,
    PolicyMappedIntent,
    PolicyMappingBatch,
    PolicyMappingResult,
)
from finer.extraction.timing_builder import build_execution_timing
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
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
    # Opinion tier: pure viewpoints materialize as WATCH actions (timeline
    # tracking + 观点兑现回测), never as executable positions. Dropping them
    # at F5 starved the viewpoint products of exactly the thing they present.
    # avoid_or_watch_risk is the BEARISH twin of the watch hints — leaving it
    # out silently filtered every bearish pure opinion off the timeline
    # (live regen 2026-07-05: 4 unanimous bearish stances vanished at F5,
    # skewing the radar bullish by funnel, not by content).
    "watch_only": ActionType.WATCH,
    "watch_or_no_trade": ActionType.WATCH,
    "avoid_or_watch_risk": ActionType.WATCH,
}

# Hints that materialize as the non-executable opinion tier (all three
# non-trading hints in schemas/policy.py's vocabulary)
OPINION_TIER_HINTS: set[str] = {"watch_only", "watch_or_no_trade", "avoid_or_watch_risk"}

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

    # Index F2 block evidence from the envelope, then fold in the explicitly-passed
    # F2 spans so grounding resolves even when the envelope blocks don't embed them.
    f2_span_by_id, f2_symbol_map, f2_block_map = _index_f2_evidence(envelope)
    for span in evidence_spans:
        f2_span_by_id.setdefault(span.evidence_span_id, span)
        bid = getattr(span, "block_id", None)
        if bid and span.evidence_span_id not in f2_block_map.setdefault(bid, []):
            f2_block_map[bid].append(span.evidence_span_id)

    # Build temporal anchor index
    temporal_list = temporal_anchors or []

    # F5: TradeAction construction
    if strategy == "programmatic":
        result = _build_actions_programmatic(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            f2_span_by_id=f2_span_by_id,
            f2_symbol_map=f2_symbol_map,
            f2_block_map=f2_block_map,
            temporal_anchors=temporal_list,
        )
    else:
        result = await _build_actions_llm(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            f2_span_by_id=f2_span_by_id,
            f2_symbol_map=f2_symbol_map,
            f2_block_map=f2_block_map,
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


def _coerce_envelope_anchors(envelope: ContentEnvelope) -> None:
    """Coerce dict-shaped anchors into model instances (idempotent).

    ContentEnvelope types entity_anchors / temporal_anchors as ``List[Any]``, so
    ``ContentEnvelope.model_validate()`` on a serialized F2 envelope leaves them
    as plain dicts. F3/F5 expect EntityAnchor / TemporalAnchor attribute access,
    so coerce here. Envelopes built in memory (already model instances) pass
    through untouched.
    """
    entities = getattr(envelope, "entity_anchors", None) or []
    if any(isinstance(a, dict) for a in entities):
        envelope.entity_anchors = [
            EntityAnchor.model_validate(a) if isinstance(a, dict) else a
            for a in entities
        ]
    temporal = getattr(envelope, "temporal_anchors", None) or []
    if any(isinstance(a, dict) for a in temporal):
        # TemporalAnchor is strict=True (rejects ISO-string datetimes); from_dict
        # converts resolved_time strings before validation.
        envelope.temporal_anchors = [
            TemporalAnchor.from_dict(a) if isinstance(a, dict) else a
            for a in temporal
        ]


def _resolve_intent_extractor(intent_extractor: Optional[Any] = None):
    """F3 extractor resolution: explicit injection > FINER_F3_EXTRACTOR=llm > rule-based.

    The LLM extractor (constrained proposal, per the repo's stated F3 direction)
    is opt-in via env until its output is validated on this corpus; construction
    failures degrade to the deterministic rule-based baseline with a note.
    """
    import os

    from finer.extraction.intent_extractor import RuleBasedIntentExtractor

    if intent_extractor is not None:
        return intent_extractor, None

    if os.environ.get("FINER_F3_EXTRACTOR", "").strip().lower() == "llm":
        try:
            from finer.extraction.intent_extractor import (
                ConsensusIntentExtractor,
                LLMIntentExtractor,
            )
            from finer.llm.router import ModelRouter
            from finer.prompts.registry import PromptRegistry

            base = LLMIntentExtractor(
                router=ModelRouter(), prompt_registry=PromptRegistry()
            )
            # The MiMo endpoint samples non-deterministically even at temp=0,
            # so llm mode defaults to N-run majority-vote consensus (user
            # decision 2026-07-05). FINER_F3_CONSENSUS_RUNS=1 opts out. A
            # garbage value must not silently kill llm mode via the broad
            # except below — fall back to the default of 3 instead.
            try:
                runs = int(os.environ.get("FINER_F3_CONSENSUS_RUNS", "") or "3")
            except ValueError:
                runs = 3
            if runs > 1:
                return ConsensusIntentExtractor(base, runs=runs), None
            return base, None
        except Exception as e:  # missing keys/config must not break the pipeline
            return (
                RuleBasedIntentExtractor(),
                f"LLM extractor unavailable ({e}); fell back to rule-based",
            )

    return RuleBasedIntentExtractor(), None


def _extract_with_fallback(extractor: Any, envelope: ContentEnvelope):
    """Run F3 with the resolved extractor; degrade to rule-based on failure.

    Fallback triggers on exceptions and on empty output from a non-rule
    extractor (an LLM returning nothing usually means quota/key issues, not a
    signal-free document — the deterministic baseline settles which it is).
    """
    from finer.extraction.intent_extractor import RuleBasedIntentExtractor

    result = None
    try:
        result = extractor.extract(envelope)
    except Exception as e:
        logger.warning(
            "F3 extractor %s failed on %s (%s); falling back to rule-based",
            type(extractor).__name__,
            envelope.envelope_id,
            e,
        )

    if (result is None or not result.intents) and not isinstance(
        extractor, RuleBasedIntentExtractor
    ):
        fallback_result = RuleBasedIntentExtractor().extract(envelope)
        if result is None or fallback_result.intents:
            fallback_result.processing_notes.append(
                f"fell back from {type(extractor).__name__}"
            )
            return fallback_result
    return result


async def run_canonical_from_envelope(
    envelope: ContentEnvelope,
    context: Optional[Dict[str, Any]] = None,
    strategy: str = "programmatic",
    persist_dir: Optional[Path] = None,
    intent_extractor: Optional[Any] = None,
) -> List[TradeAction]:
    """Canonical F3 → F4 → F5 pipeline over a real (F1/F2) ContentEnvelope.

    This is the entry point the F5 route should use for F2-anchored envelopes.
    Unlike :func:`run_canonical_extraction` — which fabricates a minimal envelope
    from raw text and therefore discards entity/temporal anchors — this consumes a
    fully-anchored F2 envelope, so F3 resolves ``target_symbol`` from
    ``envelope.entity_anchors`` and F5 timing uses ``envelope.temporal_anchors``.

    Args:
        envelope: F1/F2 ContentEnvelope (with entity_anchors / temporal_anchors).
        context: Optional extraction context (``kol_id`` / ``author`` for policy).
            Falls back to ``envelope.creator_id`` when not provided.
        strategy: F5 construction strategy — "programmatic" or "llm_guided".
        persist_dir: When set, F3 intents, F4 policy mappings, and the F2 evidence
            spans referenced by the emitted actions are written as per-id sidecars
            under ``persist_dir/F3_intents``, ``persist_dir/F4_policy_mapped`` and
            ``persist_dir/F2_evidence`` so the audit trace assembler can populate
            the Intent / Policy / Evidence panels. None (default) skips persistence.

    Returns:
        List of canonical TradeActions (canonical_trace_status == "canonical").
    """
    if strategy not in ("programmatic", "llm_guided"):
        raise ValueError(f"Unknown strategy: {strategy!r}. Use 'programmatic' or 'llm_guided'.")

    context = context or {}

    # F2 anchors may arrive as dicts (JSON round-trip via List[Any] fields);
    # coerce them so F3/F5 can use EntityAnchor / TemporalAnchor attributes.
    _coerce_envelope_anchors(envelope)

    # Quality Gate: reject envelopes that fail quality gate before F3
    from finer.services.quality_gate import evaluate_envelope_quality

    gate_result = evaluate_envelope_quality(envelope)
    if gate_result.status == "reject":
        logger.info(
            "Envelope %s rejected by quality gate (score=%.2f, reasons=%s)",
            envelope.envelope_id, gate_result.score, gate_result.reasons,
        )
        return []

    # F3: Intent extraction (consumes envelope.entity_anchors for symbol resolution).
    # Extractor is injectable; default resolves via FINER_F3_EXTRACTOR (llm|rule),
    # degrading to the deterministic rule-based baseline on any LLM failure.
    extractor, resolve_note = _resolve_intent_extractor(intent_extractor)
    if resolve_note:
        logger.warning("%s (envelope %s)", resolve_note, envelope.envelope_id)
    intent_result = _extract_with_fallback(extractor, envelope)
    intents = intent_result.intents if intent_result else []

    if not intents:
        logger.info("No intents extracted from envelope %s", envelope.envelope_id)
        return []

    # F4: Policy mapping
    from finer.policy.policy_mapper import PolicyMapper

    kol_id = (
        context.get("kol_id")
        or context.get("author")
        or getattr(envelope, "creator_id", None)
    )
    policy_ctx = PolicyContext(kol_id=kol_id) if kol_id else None
    mapper = PolicyMapper(context=policy_ctx)
    policy_batch = mapper.map_batch(intents)

    # F5: TradeAction construction grounded in F2 block evidence (not F3 self-evidence).
    # Index the envelope's deterministic F2 spans so each action's evidence_span_ids
    # resolve to real F2 evidence, and ungrounded intents are rejected.
    f2_span_by_id, f2_symbol_map, f2_block_map = _index_f2_evidence(envelope)
    temporal_list = list(getattr(envelope, "temporal_anchors", []) or [])

    if strategy == "programmatic":
        result = _build_actions_programmatic(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            f2_span_by_id=f2_span_by_id,
            f2_symbol_map=f2_symbol_map,
            f2_block_map=f2_block_map,
            temporal_anchors=temporal_list,
        )
    else:
        text = "\n".join(
            getattr(b, "text", "") or "" for b in getattr(envelope, "blocks", [])
        ).strip()
        result = await _build_actions_llm(
            intents=intents,
            policy_batch=policy_batch,
            envelope=envelope,
            f2_span_by_id=f2_span_by_id,
            f2_symbol_map=f2_symbol_map,
            f2_block_map=f2_block_map,
            temporal_anchors=temporal_list,
            text=text,
        )

    logger.info(
        "Canonical (envelope) complete: %s → %d intents → %d policy mappings → "
        "%d trade actions (strategy=%s)",
        envelope.envelope_id,
        len(intents),
        len(policy_batch.mappings),
        result.executable_count,
        strategy,
    )

    # Persist F3/F4/evidence intermediate artifacts as per-id sidecars so the
    # audit trace assembler can resolve intent_id → Intent card, policy_id →
    # Policy card, and evidence_span_ids → Evidence panel.
    if persist_dir is not None and result.trade_actions:
        used_evidence_ids = {
            eid for action in result.trade_actions for eid in action.evidence_span_ids
        }
        used_spans = [
            f2_span_by_id[eid] for eid in used_evidence_ids if eid in f2_span_by_id
        ]
        _persist_canonical_artifacts(
            intents,
            policy_batch.mappings,
            used_spans,
            persist_dir,
            envelope_id=envelope.envelope_id,
            f3_extractor_version=getattr(intent_result, "extractor_version", None),
            f3_processing_notes=list(getattr(intent_result, "processing_notes", []) or []),
        )

    return result.trade_actions


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

    return await run_canonical_from_envelope(envelope, context, strategy=strategy)


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
    f2_span_by_id: Optional[Dict[str, EvidenceSpan]] = None,
    f2_symbol_map: Optional[Dict[str, List[str]]] = None,
    f2_block_map: Optional[Dict[str, List[str]]] = None,
    temporal_anchors: Optional[List[Any]] = None,
) -> CanonicalRunnerResult:
    """Build TradeActions deterministically from policy hints.

    Each TradeAction's ``evidence_span_ids`` are re-grounded against the F2
    evidence index (``f2_span_by_id`` / ``f2_symbol_map`` / ``f2_block_map``).
    When the envelope is F2-anchored, an intent that cannot be grounded is
    rejected (``evidence_not_grounded_in_f2``). Non-executable policy hints are
    recorded as RejectedIntent for audit.
    """
    f2_span_by_id = f2_span_by_id or {}
    f2_symbol_map = f2_symbol_map or {}
    f2_block_map = f2_block_map or {}
    # Only enforce the F2-grounding hard gate when the envelope actually carries
    # F2 evidence. A fabricated/raw-text (dev) envelope has none, so its actions
    # get empty evidence → TradeAction validator downgrades them to "partial".
    envelope_has_f2 = bool(f2_span_by_id)

    intent_map: Dict[str, NormalizedInvestmentIntent] = {
        i.intent_id: i for i in intents
    }

    actions: List[TradeAction] = []
    rejected: List[RejectedIntent] = []

    for mapped in policy_batch.mapped_intents:
        # Unknown hints → rejection record. watch_only is NOT rejected any
        # more: it materializes as the opinion tier (WATCH action) below,
        # passing exactly the same target/sector/F2-grounding gates.
        if (
            mapped.action_hint not in EXECUTABLE_HINTS
            and mapped.action_hint not in OPINION_TIER_HINTS
        ):
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

        # Validate ticker (a target is required regardless of evidence)
        if not intent.target_symbol and not intent.target_name:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="no_ticker_symbol",
            ))
            continue

        # Sector/concept targets are real KOL viewpoints but not tradable
        # instruments — their registry "symbol" is a placeholder (e.g.
        # 光模块 -> OPTICAL_MODULE). Reject with an audit trail instead of
        # letting the placeholder masquerade as a ticker.
        if intent.target_type == "sector":
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="sector_target_not_tradable",
            ))
            continue

        # A bare target_name must not masquerade as a ticker either
        # (TargetInfo.ticker would otherwise carry a Chinese company name).
        if not intent.target_symbol:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="unresolved_target_symbol",
            ))
            continue

        # F2-grounding hard gate: the action's evidence must trace to F2 block
        # evidence. F3's own uuid spans never match F2, so re-resolve grounding
        # against the F2 index (by ticker, then source blocks).
        evidence_ids = _resolve_f2_grounding(intent, f2_symbol_map, f2_block_map)
        if envelope_has_f2 and not evidence_ids:
            rejected.append(RejectedIntent(
                intent_id=mapped.intent_id,
                policy_id=mapped.policy_id,
                action_hint=mapped.action_hint,
                reason="evidence_not_grounded_in_f2",
            ))
            continue

        action_type = ACTION_HINT_TO_ACTION_TYPE[mapped.action_hint]
        direction = _resolve_direction(intent, mapped)
        position_pct = POSITION_SIZING_TO_PCT.get(mapped.position_sizing_hint)

        timing = build_execution_timing(
            envelope=envelope,
            market=intent.market or "CN",
            temporal_anchors=temporal_anchors,
            intent_id=intent.intent_id,
        )

        # Build evidence text from the grounded F2 evidence spans, expanded to
        # sentence context via the block texts (mention tokens alone degrade).
        evidence_text = _build_evidence_text(
            evidence_ids, f2_span_by_id, block_texts=_block_texts(envelope)
        )

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
                ticker=intent.target_symbol,
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
            # confidence = pipeline structural certainty (lower of F3/F4, same
            # semantics as CanonicalActionBuilder); conviction = KOL belief
            # strength from F3 — the two were conflated before, which is why
            # every live action showed the same flat confidence.
            confidence=min(intent.confidence, mapped.mapping_confidence),
            conviction=intent.conviction,
            time_horizon=mapped.holding_period_hint,
            requires_manual_review=mapped.requires_human_review,
            rationale=_build_action_rationale(intent, mapped, evidence_text),
            metadata={
                "action_hint_original": mapped.action_hint,
                "tier": "opinion" if mapped.action_hint in OPINION_TIER_HINTS else "trade",
            },
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
    f2_span_by_id: Optional[Dict[str, EvidenceSpan]] = None,
    f2_symbol_map: Optional[Dict[str, List[str]]] = None,
    f2_block_map: Optional[Dict[str, List[str]]] = None,
    temporal_anchors: Optional[List[Any]] = None,
    text: Optional[str] = None,
) -> CanonicalRunnerResult:
    """Build TradeActions using LLM with policy context, then backfill trace IDs.

    Like the programmatic builder, each action's ``evidence_span_ids`` are
    re-grounded against the F2 evidence index; LLM actions that cannot be
    grounded are dropped when the envelope is F2-anchored.
    """
    from finer.llm import LLMClient

    f2_span_by_id = f2_span_by_id or {}
    f2_symbol_map = f2_symbol_map or {}
    f2_block_map = f2_block_map or {}
    envelope_has_f2 = bool(f2_span_by_id)

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
  "confidence": "<float 0-1, calibrated to evidence strength — use the full range, do NOT default to one value>",
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
            intents, policy_batch, envelope,
            f2_span_by_id, f2_symbol_map, f2_block_map, temporal_anchors,
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

        # Same non-tradable gates as the programmatic path
        if matched_intent.target_type == "sector":
            rejected.append(RejectedIntent(
                intent_id=matched_mapped.intent_id,
                policy_id=matched_mapped.policy_id,
                action_hint=matched_mapped.action_hint,
                reason="sector_target_not_tradable",
            ))
            continue
        if not matched_intent.target_symbol:
            rejected.append(RejectedIntent(
                intent_id=matched_mapped.intent_id,
                policy_id=matched_mapped.policy_id,
                action_hint=matched_mapped.action_hint,
                reason="unresolved_target_symbol",
            ))
            continue

        direction_str = raw.get("direction", "bullish")
        direction = TradeDirection(direction_str) if direction_str in TradeDirection.__members__.values() else TradeDirection.BULLISH

        atype = ActionType(raw.get("action_type", "long")) if raw.get("action_type") in ActionType.__members__.values() else ActionType.LONG

        timing = build_execution_timing(
            envelope=envelope,
            market=matched_intent.market or "CN",
            temporal_anchors=temporal_anchors,
            intent_id=matched_intent.intent_id,
        )

        # F2-grounding gate: drop LLM actions that cannot be traced to F2 evidence
        evidence_ids = _resolve_f2_grounding(matched_intent, f2_symbol_map, f2_block_map)
        if envelope_has_f2 and not evidence_ids:
            logger.debug(
                "Dropping LLM action for %s: not grounded in F2 evidence",
                matched_intent.intent_id,
            )
            continue
        evidence_text = _build_evidence_text(
            evidence_ids, f2_span_by_id, block_texts=_block_texts(envelope)
        )

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
            conviction=matched_intent.conviction,
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
    # open_position / add_position / watch hints: use intent direction.
    # mixed/unknown have no TradeDirection member — they are honestly
    # NEUTRAL, not bullish (the old BULLISH default fabricated a stance:
    # live regen 2026-07-05 turned a consensus "000001.SH mixed" into a
    # bullish action).
    return (
        TradeDirection(intent.direction)
        if intent.direction in TradeDirection.__members__.values()
        else TradeDirection.NEUTRAL
    )


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


_SENTENCE_DELIMS = "。！？；\n"


def _block_texts(envelope: ContentEnvelope) -> Dict[str, str]:
    """block_id -> full block text (tolerates dict-shaped blocks)."""
    out: Dict[str, str] = {}
    for block in getattr(envelope, "blocks", None) or []:
        if isinstance(block, dict):
            bid, text = block.get("block_id"), block.get("text")
        else:
            bid, text = getattr(block, "block_id", None), getattr(block, "text", None)
        if bid and isinstance(text, str) and text:
            out[bid] = text
    return out


def _sentence_window(text: str, start: int, end: int, max_chars: int = 120) -> str:
    """Expand a [start, end) span to the surrounding sentence (bounded)."""
    n = len(text)
    s = max(0, min(start if start is not None else 0, n))
    e = max(s, min(end if end is not None else s, n))

    left = s
    for i in range(s - 1, max(-1, s - max_chars - 1), -1):
        if i < 0 or text[i] in _SENTENCE_DELIMS:
            left = i + 1
            break
        left = i
    right = e
    for i in range(e, min(n, e + max_chars)):
        right = i + 1
        if text[i] in _SENTENCE_DELIMS:
            break
    return text[left:right].strip()


def _build_evidence_text(
    evidence_ids: List[str],
    evidence_map: Optional[Dict[str, EvidenceSpan]],
    block_texts: Optional[Dict[str, str]] = None,
    max_snippets: int = 3,
) -> str:
    """Build human-readable evidence text from evidence span IDs.

    F2 spans are mention-level anchors — their ``text`` is just the alias hit
    ("亚马逊"), so joining them verbatim produced degenerate "X | X | X" strings
    (49/58 live actions). Instead, expand each span to its surrounding sentence
    via the block text, dedupe, and keep the first few distinct snippets. The
    full span-id list stays on the action for audit; this is display text only.
    """
    if not evidence_map:
        return ""
    snippets: List[str] = []
    seen: set = set()
    for eid in evidence_ids:
        span = evidence_map.get(eid)
        if span is None:
            continue
        snippet = ""
        block_text = (block_texts or {}).get(getattr(span, "block_id", None) or "")
        if block_text:
            snippet = _sentence_window(
                block_text,
                getattr(span, "char_start", None),
                getattr(span, "char_end", None),
            )
        if not snippet:
            snippet = getattr(span, "text", "") or ""
        # normalize whitespace and shed F1 fake-table pipe framing
        snippet = " ".join(snippet.split()).strip("|- ")
        if snippet and snippet not in seen:
            seen.add(snippet)
            snippets.append(snippet)
        if len(snippets) >= max_snippets:
            break
    return " | ".join(snippets)


def _index_f2_evidence(
    envelope: ContentEnvelope,
) -> tuple[Dict[str, EvidenceSpan], Dict[str, List[str]], Dict[str, List[str]]]:
    """Index a F2-anchored envelope's block-level evidence for F5 grounding.

    F3 mints its own intent-keyword spans with fresh uuids that never match the
    deterministic F2 block spans, so an F5 gate that resolves the intent's own
    ``evidence_span_ids`` is self-referential. This indexes the *F2* evidence —
    the spans materialized by ``enrichment.entity_anchoring`` onto each block and
    referenced by every ``EntityAnchor`` — so F5 can ground each TradeAction in
    real F2 evidence (audit optimization #2).

    Tolerates dict-shaped blocks/spans/anchors (serialized F2 envelopes round-trip
    through ``List[Any]`` fields).

    Returns:
        (span_by_id, symbol_to_span_ids, block_to_span_ids) — all keyed by the
        canonical F2 ``evidence_span_id``. ``symbol_to_span_ids`` is keyed by
        ``EntityAnchor.resolved_symbol`` (ticker grounding); ``block_to_span_ids``
        by ``block_id`` (fallback grounding for symbol-less sector/index intents).
    """
    span_by_id: Dict[str, EvidenceSpan] = {}
    block_to_span_ids: Dict[str, List[str]] = {}

    for block in getattr(envelope, "blocks", None) or []:
        if isinstance(block, dict):
            block_id = block.get("block_id")
            raw_spans = block.get("evidence_spans") or []
        else:
            block_id = getattr(block, "block_id", None)
            raw_spans = getattr(block, "evidence_spans", None) or []
        for raw in raw_spans:
            try:
                span = raw if isinstance(raw, EvidenceSpan) else EvidenceSpan.model_validate(raw)
            except Exception:  # noqa: BLE001 - skip malformed F2 spans, don't crash F5
                continue
            span_by_id[span.evidence_span_id] = span
            if block_id:
                block_to_span_ids.setdefault(block_id, []).append(span.evidence_span_id)

    symbol_to_span_ids: Dict[str, List[str]] = {}
    for anchor in getattr(envelope, "entity_anchors", None) or []:
        if isinstance(anchor, dict):
            symbol = anchor.get("resolved_symbol")
            meta = anchor.get("metadata") or {}
            single = anchor.get("evidence_span_id")
        else:
            symbol = getattr(anchor, "resolved_symbol", None)
            meta = getattr(anchor, "metadata", None) or {}
            single = getattr(anchor, "evidence_span_id", None)
        if not symbol:
            continue
        ids = list(meta.get("evidence_span_ids") or [])
        if single:
            ids.append(single)
        # dedup preserving order; keep only spans that resolve to F2 block evidence
        ids = [i for i in dict.fromkeys(ids) if i in span_by_id]
        if ids:
            symbol_to_span_ids.setdefault(symbol, []).extend(ids)

    return span_by_id, symbol_to_span_ids, block_to_span_ids


def _resolve_f2_grounding(
    intent: NormalizedInvestmentIntent,
    symbol_to_span_ids: Dict[str, List[str]],
    block_to_span_ids: Dict[str, List[str]],
) -> List[str]:
    """Resolve the F2 evidence span IDs that ground an intent's TradeAction.

    Symbol-first (the ticker mention proves the target is grounded in F2), then a
    block-level fallback for symbol-less sector/index intents. Empty result means
    the intent cannot be grounded in F2 evidence → F5 rejects it when the envelope
    is F2-anchored.
    """
    symbol = getattr(intent, "target_symbol", None)
    if symbol and symbol_to_span_ids.get(symbol):
        return list(dict.fromkeys(symbol_to_span_ids[symbol]))

    ids: List[str] = []
    for block_id in getattr(intent, "block_ids", None) or []:
        ids.extend(block_to_span_ids.get(block_id, []))
    return list(dict.fromkeys(ids))


def _build_action_rationale(
    intent: NormalizedInvestmentIntent,
    mapped: PolicyMappedIntent,
    evidence_text: str,
) -> str:
    """Compose a human-readable rationale for the audit/review surface.

    Grounded in the F3 intent (direction + target), the F4 action hint, and the
    KOL's own evidence text — instead of the opaque ``"<action> via <uuid>"``
    placeholder that told a human auditor nothing.
    """
    target = intent.target_name or intent.target_symbol or "标的"
    decision = f"{intent.direction} {target} · {mapped.action_hint}"
    # first snippet only — the dashboard summary truncates to ~40 chars, so a
    # joined list would crowd out the actual context sentence
    first = (evidence_text or "").split(" | ")[0]
    snippet = " ".join(first.split())[:160]
    return f"{decision}｜依据：{snippet}" if snippet else decision


def _persist_canonical_artifacts(
    intents: List[NormalizedInvestmentIntent],
    mappings: List[PolicyMappingResult],
    evidence_spans: List[EvidenceSpan],
    persist_dir: Path,
    envelope_id: Optional[str] = None,
    f3_extractor_version: Optional[str] = None,
    f3_processing_notes: Optional[List[str]] = None,
) -> None:
    """Write F3 intents, F4 policy mappings, and F2 evidence spans as per-id JSON.

    The audit trace assembler reads ``{persist_dir}/F3_intents/{intent_id}.json``,
    ``{persist_dir}/F4_policy_mapped/{policy_id}.json`` and
    ``{persist_dir}/F2_evidence/{evidence_span_id}.json`` to populate the Intent,
    Policy and Evidence panels; persisting them here closes the gap where the
    route wrote only F5 (so those panels were always empty).

    Result-level F3 extraction provenance (validator rejection counts,
    consensus vote records, fallback notes) lives on the extraction RESULT,
    not on any intent — without ``{envelope_id}.notes.json`` those audit
    decisions vanish when the run's stdout does.
    """
    f3_dir = Path(persist_dir) / "F3_intents"
    f4_dir = Path(persist_dir) / "F4_policy_mapped"
    evidence_dir = Path(persist_dir) / "F2_evidence"
    try:
        f3_dir.mkdir(parents=True, exist_ok=True)
        f4_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        if envelope_id and f3_processing_notes:
            import json as _json

            (f3_dir / f"{envelope_id}.notes.json").write_text(
                _json.dumps(
                    {
                        "envelope_id": envelope_id,
                        "extractor_version": f3_extractor_version,
                        "processing_notes": f3_processing_notes,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        for intent in intents:
            (f3_dir / f"{intent.intent_id}.json").write_text(
                intent.model_dump_json(indent=2), encoding="utf-8"
            )
        for mapping in mappings:
            (f4_dir / f"{mapping.policy_id}.json").write_text(
                mapping.model_dump_json(indent=2), encoding="utf-8"
            )
        for span in evidence_spans:
            (evidence_dir / f"{span.evidence_span_id}.json").write_text(
                span.model_dump_json(indent=2), encoding="utf-8"
            )
    except OSError as exc:
        logger.warning("Failed to persist F3/F4/evidence artifacts to %s: %s", persist_dir, exc)


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
