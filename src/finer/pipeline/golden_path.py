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
from finer.schemas.trade_action import TradeAction

logger = logging.getLogger(__name__)

_DATA_ROOT = Path("data")


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
) -> TradeAction:
    """Run canonical F3→F4→F5 for a single ContentEnvelope.

    Args:
        envelope: F2-anchored ContentEnvelope with blocks and anchors.
        data_root: Root directory for writing intermediate artifacts.

    Returns:
        TradeAction with canonical_trace_status == "canonical".

    Raises:
        ValueError: If no intents are extracted or no actionable intents produced.
    """
    data_root = Path(data_root)

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

    return trade_actions[0]
