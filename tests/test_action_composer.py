"""Tests for the single canonical TradeAction constructor (action_composer)."""
from __future__ import annotations

from datetime import datetime

import pytest

from finer.extraction.action_composer import (
    EmptyEvidenceSpanIdsError,
    MissingIntentIdError,
    MissingPolicyIdError,
    compose_trade_action,
)
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    ExecutionTiming,
    SourceInfo,
    TargetInfo,
    TradeDirection,
    TriggerType,
    ValidationStatus,
)


def _intent(intent_id: str = "intent-1") -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id=intent_id,
        envelope_id="env-1",
        block_ids=["b-1"],
        creator_id="k1",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.8,
        confidence=0.9,
    )


def _mapped(intent_id: str = "intent-1", policy_id: str = "pol-1") -> PolicyMappedIntent:
    return PolicyMappedIntent(
        intent_id=intent_id,
        policy_id=policy_id,
        original_intent_summary="test",
        action_hint="add_position",
        position_sizing_hint="small",
        holding_period_hint="medium_term",
        mapping_confidence=0.7,
        created_at=datetime(2026, 7, 1),
    )


def _timing() -> ExecutionTiming:
    now = datetime(2026, 7, 1, 10, 0)
    return ExecutionTiming(
        intent_published_at=now,
        action_decision_at=now,
        action_executable_at=now,
        market="CN",
        timezone="Asia/Shanghai",
        timing_policy_id="test-policy",
    )


def _compose(**overrides):
    kwargs = dict(
        intent=_intent(),
        policy_mapped_intent=_mapped(),
        evidence_span_ids=["span-1"],
        execution_timing=_timing(),
        source=SourceInfo(content_id="env-1", evidence_text="ev", creator_id="k1"),
        target=TargetInfo(ticker="300750.SZ", market="CN"),
        direction=TradeDirection.BULLISH,
        action_chain=[
            ActionStep(sequence=1, action_type=ActionType.ADD, trigger_type=TriggerType.MANUAL)
        ],
        rationale="看多 300750.SZ · add_position",
    )
    kwargs.update(overrides)
    return compose_trade_action(**kwargs)


class TestInvariants:
    def test_missing_intent_id_rejected(self):
        with pytest.raises(MissingIntentIdError):
            _compose(intent=_intent(intent_id=""))

    def test_missing_policy_id_rejected(self):
        # Pydantic already rejects policy_id="" at model construction, so use
        # model_construct to simulate a malformed object reaching the composer
        # — its own guard must still hold.
        broken = _mapped().model_construct(**{**_mapped().model_dump(), "policy_id": ""})
        with pytest.raises(MissingPolicyIdError):
            _compose(policy_mapped_intent=broken)

    def test_empty_evidence_rejected_by_default(self):
        with pytest.raises(EmptyEvidenceSpanIdsError):
            _compose(evidence_span_ids=[])

    def test_raw_text_rejected(self):
        with pytest.raises(TypeError):
            _compose(intent="我看多宁德时代")

    def test_canonical_status_with_evidence(self):
        ta = _compose()
        assert ta.canonical_trace_status == "canonical"


class TestAllowEmptyEvidence:
    def test_empty_evidence_allowed_is_partial(self):
        """Runner path: F2 gate ran upstream, no-F2 envelopes stay honest."""
        ta = _compose(evidence_span_ids=[], allow_empty_evidence=True)
        assert ta.canonical_trace_status == "partial"
        assert ta.evidence_span_ids == []

    def test_allow_empty_does_not_weaken_other_invariants(self):
        with pytest.raises(MissingIntentIdError):
            _compose(
                intent=_intent(intent_id=""),
                evidence_span_ids=[],
                allow_empty_evidence=True,
            )


class TestDefaults:
    def test_confidence_defaults_to_min_of_f3_f4(self):
        ta = _compose()
        assert ta.confidence == 0.7  # min(0.9 intent, 0.7 mapping)

    def test_conviction_defaults_to_intent(self):
        ta = _compose()
        assert ta.conviction == 0.8

    def test_explicit_confidence_wins(self):
        ta = _compose(confidence=0.55)
        assert ta.confidence == 0.55

    def test_validation_status_defaults_to_pending(self):
        ta = _compose()
        assert ta.validation_status == ValidationStatus.PENDING

    def test_metadata_contract_plus_extra(self):
        ta = _compose(extra_metadata={"tier": "trade"})
        assert ta.metadata["action_hint_original"] == "add_position"
        assert ta.metadata["tier"] == "trade"


class TestVersionStamp:
    def test_unstamped_keeps_schema_default(self):
        ta = _compose()
        assert ta.model_version == "v1.0"
        assert ta.version_info is not None
        assert ta.version_info.model_version == "unassigned"

    def test_extractor_version_stamps_action(self):
        ta = _compose(extractor_version="llm_consensus_v1", f5_strategy="programmatic")
        assert ta.model_version == "llm_consensus_v1"
        assert ta.version_info is not None
        assert ta.version_info.schema_version == "1.0"
        assert ta.version_info.model_version == "llm_consensus_v1"

    def test_extraction_method_recorded(self):
        ta = _compose(extraction_method="rule_based")
        assert ta.extraction_method == "rule_based"


# =============================================================================
# C7 — signal_class classification at the single construction point
# =============================================================================


def test_signal_class_kol_statement_for_non_recommendation():
    """A KOL's own action (actionability != recommendation) → kol_statement."""
    ta = _compose()  # _intent() uses actionability="explicit_action"
    assert ta.signal_class == "kol_statement"
    assert ta.metadata["signal_class"] == "kol_statement"


def test_signal_class_broker_recommendation_for_recommendation():
    """A declarative institutional rating (actionability=recommendation) →
    broker_recommendation, set on the field AND surfaced in metadata."""
    intent = _intent()
    intent.actionability = "recommendation"
    ta = _compose(intent=intent)
    assert ta.signal_class == "broker_recommendation"
    assert ta.metadata["signal_class"] == "broker_recommendation"


def test_signal_class_field_defaults_to_none_for_legacy():
    """Actions written before the field existed load as None (honest, not
    mislabeled kol_statement)."""
    from finer.schemas.trade_action import TradeAction

    assert TradeAction.model_fields["signal_class"].default is None
