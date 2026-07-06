"""Golden Path — single-envelope canonical F3→F4→F5 pipeline.

Provides ``run_golden_path(envelope)`` which chains:
  F3: LLMIntentExtractor (ModelRouter + PromptRegistry)
  F4: PolicyMapper (GlobalBasePolicy)
  F5: CanonicalActionBuilder

Writes intermediate artifacts to ``data/F3_intents/``, ``data/F4_policy_mapped/``,
``data/F5_executed/``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List

from finer.extraction.canonical_action_builder import CanonicalActionBuilder
from finer.extraction.intent_extractor import LLMIntentExtractor
from finer.extraction.timing_builder import build_execution_timing
from finer.llm.router import ModelRouter
from finer.policy.policy_mapper import PolicyMapper
from finer.prompts.registry import PromptRegistry
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappingBatch
from finer.schemas.trade_action import TradeAction

logger = logging.getLogger(__name__)

_DATA_ROOT = Path("data")


@dataclass(frozen=True)
class GoldenPathResult:
    """All canonical TradeActions produced from one ContentEnvelope.

    ``run_golden_path`` previously returned only ``trade_actions[0]``, silently
    dropping the rest when an envelope yielded multiple intents. This result
    object exposes the full set; callers that only need the single
    representative action use :attr:`primary_action`.
    """

    envelope_id: str
    data_root: Path
    trade_actions: List[TradeAction]
    intents: List[NormalizedInvestmentIntent]
    policy_batch: PolicyMappingBatch

    @property
    def primary_action(self) -> TradeAction:
        """First TradeAction — the representative action for single-intent flows.

        Raises:
            ValueError: when no trade actions were produced. ``run_golden_path``
                already raises before returning in that case, so a result handed
                back to a caller always has at least one action.
        """
        if not self.trade_actions:
            raise ValueError(
                f"GoldenPathResult for {self.envelope_id} has no trade actions"
            )
        return self.trade_actions[0]

    @property
    def action_count(self) -> int:
        return len(self.trade_actions)

    @property
    def intent_count(self) -> int:
        return len(self.intents)

    @property
    def policy_mapping_count(self) -> int:
        return len(self.policy_batch.mapped_intents)


def _json_default(obj: Any) -> Any:
    """JSON serializer for non-serializable types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return str(obj)


def _write_json(path: Path, data: Any) -> None:
    """Write JSON file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)


def run_golden_path(
    envelope: ContentEnvelope,
    *,
    data_root: Path | str = _DATA_ROOT,
) -> GoldenPathResult:
    """Run canonical F3→F4→F5 for a single ContentEnvelope.

    Args:
        envelope: F2-anchored ContentEnvelope with blocks and anchors.
        data_root: Root directory for writing intermediate artifacts.

    Returns:
        GoldenPathResult holding every canonical TradeAction (each with
        canonical_trace_status == "canonical"). Use ``.primary_action`` for the
        single representative action; ``.trade_actions`` for the full set.

    Raises:
        ValueError: If no intents are extracted or no actionable intents produced.
    """
    data_root = Path(data_root)

    # ── Quality Gate: reject envelopes that fail quality gate before F3 ──────
    from finer.services.quality_gate import evaluate_envelope_quality

    gate_result = evaluate_envelope_quality(envelope)
    if gate_result.status == "reject":
        raise ValueError(
            f"Envelope {envelope.envelope_id} rejected by quality gate "
            f"(score={gate_result.score:.2f}, reasons={gate_result.reasons}). "
            f"Cannot proceed to F3 intent extraction."
        )

    # ── F3: Intent Extraction ────────────────────────────────────────────────
    extractor = LLMIntentExtractor(
        router=ModelRouter(),
        prompt_registry=PromptRegistry(),
    )
    extraction_result = extractor.extract(envelope)

    if not extraction_result.intents:
        raise ValueError(
            f"No intents extracted from envelope {envelope.envelope_id}. "
            f"Processing notes: {extraction_result.processing_notes}"
        )

    intents = extraction_result.intents
    logger.info(
        "F3 extracted %d intent(s) from %s",
        len(intents), envelope.envelope_id,
    )

    # Write F3 artifacts
    f3_dir = data_root / "F3_intents"
    for intent in intents:
        _write_json(
            f3_dir / f"{intent.intent_id}.json",
            intent.model_dump(),
        )

    # ── F4: Policy Mapping ───────────────────────────────────────────────────
    mapper = PolicyMapper()
    batch = mapper.map_batch(intents)

    logger.info("F4 mapped %d intent(s)", len(batch.mapped_intents))

    # Write F4 artifacts
    f4_dir = data_root / "F4_policy_mapped"
    for pmr in batch.mappings:
        _write_json(f4_dir / f"{pmr.policy_id}.json", pmr.model_dump())
    _write_json(
        f4_dir / f"{envelope.envelope_id}.batch.json",
        batch.model_dump(),
    )

    # ── F5: Canonical TradeAction ────────────────────────────────────────────
    builder = CanonicalActionBuilder()
    temporal_anchors = getattr(envelope, "temporal_anchors", None) or []

    pmi_by_intent = {pmi.intent_id: pmi for pmi in batch.mapped_intents}
    trade_actions: List[TradeAction] = []

    for intent in intents:
        pmi = pmi_by_intent.get(intent.intent_id)
        if pmi is None:
            logger.warning("No policy mapping for intent %s", intent.intent_id)
            continue

        timing = build_execution_timing(
            envelope,
            temporal_anchors=temporal_anchors,
            market=intent.market or "CN",
            intent_id=intent.intent_id,
        )

        ta = builder.build(
            intent=intent,
            policy_mapped_intent=pmi,
            evidence_span_ids=list(intent.evidence_span_ids),
            execution_timing=timing,
        )
        trade_actions.append(ta)

    if not trade_actions:
        raise ValueError(
            f"No actionable TradeActions produced from envelope {envelope.envelope_id}. "
            f"All intents were rejected by the policy mapper."
        )

    # Write F5 artifacts
    f5_dir = data_root / "F5_executed"
    for ta in trade_actions:
        _write_json(
            f5_dir / f"{ta.trade_action_id}.json",
            ta.model_dump(),
        )

    logger.info(
        "F5 produced %d TradeAction(s) for %s",
        len(trade_actions), envelope.envelope_id,
    )

    return GoldenPathResult(
        envelope_id=envelope.envelope_id,
        data_root=data_root,
        trade_actions=trade_actions,
        intents=intents,
        policy_batch=batch,
    )
