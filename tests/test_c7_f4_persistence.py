"""C7 — F4 PolicyMappingResult persistence round-trip.

The broker driver writes ``data/F4_policy_mapped/{policy_id}.json`` and the audit
assembler reads it back as a PolicyMappingResult. This pins that exact
serialization contract so /audit can resolve every action's policy segment.
"""

from __future__ import annotations

import json
from pathlib import Path

from finer.policy.policy_mapper import PolicyMapper
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyContext, PolicyMappingResult


def _recommendation_intent() -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id="bri_test_001",
        envelope_id="broker_env_1",
        block_ids=["b-1"],
        creator_id="高盛",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="recommendation",
        position_delta_hint="add",
        conviction=0.6,
        confidence=0.75,
    )


def test_f4_policy_mapping_result_roundtrip(tmp_path: Path) -> None:
    batch = PolicyMapper(context=PolicyContext(kol_id="高盛")).map_batch([_recommendation_intent()])
    assert batch.mappings, "mapper should produce at least one PolicyMappingResult"
    pmr = batch.mappings[0]

    # driver write (json.dump(pmr.model_dump(mode="json")))
    path = tmp_path / f"{pmr.policy_id}.json"
    path.write_text(json.dumps(pmr.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

    # audit read (PolicyMappingResult from F4_policy_mapped/{policy_id}.json)
    back = PolicyMappingResult.model_validate_json(path.read_text(encoding="utf-8"))
    assert back.policy_id == pmr.policy_id
    # the file name IS the key the audit assembler joins on
    assert path.stem == pmr.policy_id


def test_mapped_intent_policy_id_matches_result(tmp_path: Path) -> None:
    """The action's policy_id (from PolicyMappedIntent) must reference a
    persisted PolicyMappingResult, or /audit can't resolve it."""
    batch = PolicyMapper(context=PolicyContext(kol_id="高盛")).map_batch([_recommendation_intent()])
    result_ids = {m.policy_id for m in batch.mappings}
    for mapped in batch.mapped_intents:
        assert mapped.policy_id in result_ids
