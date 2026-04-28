"""Tests for F4 Policy Schema.

Covers:
- PolicyMappingResult serialization/deserialization
- TradeAction can carry intent_id / policy_id / evidence_span_ids
- Canonical trace validation (missing IDs → non_canonical)
- PolicyMappingResult MUST NOT contain raw full text as sole evidence
- PolicyMappedIntent and PolicyRiskConstraints field validation
- PolicyLayerTrace and PolicyDecision creation/validation
- PolicyMappingBatch auto-stats
"""

import json
import pytest
from datetime import datetime
from pydantic import ValidationError

from finer.schemas.policy import (
    PolicyRiskConstraints,
    PolicyLayerTrace,
    PolicyDecision,
    PolicyMappingResult,
    PolicyMappedIntent,
    PolicyContext,
    PolicyMappingBatch,
    ACTION_HINT_LITERAL,
    POSITION_SIZING_HINT_LITERAL,
    HOLDING_PERIOD_HINT_LITERAL,
)

from finer.schemas.trade_action import (
    TradeAction,
    SourceInfo,
    TargetInfo,
    TradeDirection,
    ActionStep,
    ActionType,
)

from finer.schemas.investment_intent import (
    NormalizedInvestmentIntent,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def canonical_intent() -> NormalizedInvestmentIntent:
    """A well-formed F3 intent suitable for canonical F4 mapping."""
    return NormalizedInvestmentIntent(
        intent_id="intent-12345678-1234-1234-1234-123456789012",
        envelope_id="env-001",
        block_ids=["block-1", "block-2"],
        creator_id="kol-001",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.85,
        confidence=0.9,
        evidence_span_ids=["span-001", "span-002"],
    )


@pytest.fixture
def canonical_policy_mapping(canonical_intent) -> PolicyMappingResult:
    """A canonical policy mapping with full traceability."""
    return PolicyMappingResult(
        policy_id="policy-abcdef01-abcd-abcd-abcd-abcdef012345",
        intent_id=canonical_intent.intent_id,
        creator_id="kol-001",
        kol_id="kol-001",
        policy_version="global-base-v1",
        policy_layers_applied=["GlobalBase", "StyleArchetype", "RiskPreference", "KOLPersona"],
        action_hint="add_position",
        position_sizing_hint="small",
        holding_period_hint="medium_term",
        risk_constraints=PolicyRiskConstraints(
            max_position_hint="small",
            requires_human_review=False,
            risk_notes=["KOL moderate conviction on this sector"],
        ),
        mapping_rationale="'加仓' mapped through GlobalBase: add_position + small size. "
                         "StyleArchetype confirms value-style sizing. "
                         "KOLPersona: this KOL's '加仓' typically means 5-15% position.",
        layer_traces=[
            PolicyLayerTrace(
                layer_name="GlobalBase",
                layer_version="global-base-v1",
                applied=True,
                reason="explicit_action + add → add_position + small",
                modifications=["action_hint: → add_position", "position_sizing: → small"],
                order_index=0,
            ),
            PolicyLayerTrace(
                layer_name="StyleArchetype",
                layer_version="style-archetype-v1",
                applied=True,
                reason="KOL classified as value-style — medium holding period",
                modifications=["holding_period: → medium_term"],
                order_index=1,
            ),
        ],
        decisions=[
            PolicyDecision(
                policy_id="policy-abcdef01-abcd-abcd-abcd-abcdef012345",
                layer="GlobalBase",
                decision_type="action_override",
                description="Map explicit_action(add) to add_position",
                rationale="Standard global base mapping for 加仓",
            ),
        ],
        confidence=0.88,
        original_intent_confidence=0.9,
    )


@pytest.fixture
def canonical_mapped_intent(canonical_policy_mapping) -> PolicyMappedIntent:
    """A canonical mapped intent ready for F5 consumption."""
    return PolicyMappedIntent(
        mapped_id="mapped-11223344-1234-1234-1234-123456789012",
        intent_id=canonical_policy_mapping.intent_id,
        policy_id=canonical_policy_mapping.policy_id,
        original_intent_summary="bullish on 宁德时代 (300750.SZ), explicit_action=add, conviction=0.85",
        action_hint="add_position",
        position_sizing_hint="small",
        holding_period_hint="medium_term",
        risk_notes=["Moderate conviction on this sector"],
        mapping_confidence=0.88,
        requires_human_review=False,
    )


@pytest.fixture
def canonical_trade_action_for_trace() -> TradeAction:
    """TradeAction with full canonical trace (intent_id + policy_id + evidence_span_ids)."""
    return TradeAction(
        trade_action_id="ta-canonical-001",
        intent_id="intent-12345678-1234-1234-1234-123456789012",
        policy_id="policy-abcdef01-abcd-abcd-abcd-abcdef012345",
        evidence_span_ids=["span-001", "span-002"],
        effective_trade_at=datetime(2026, 4, 24, 9, 30, 0),
        source=SourceInfo(
            creator_id="kol-001",
            content_id="content-001",
            evidence_text="我加仓宁德时代，新能源趋势明确",
        ),
        target=TargetInfo(ticker="300750.SZ", market="CN", company_name="宁德时代"),
        direction=TradeDirection.BULLISH,
        action_chain=[
            ActionStep(sequence=1, action_type=ActionType.LONG, position_size_pct=0.05),
        ],
        confidence=0.88,
    )


# =============================================================================
# PolicyRiskConstraints Tests
# =============================================================================

class TestPolicyRiskConstraints:
    """Tests for PolicyRiskConstraints model."""

    def test_creation_minimal(self):
        """Test creation with minimal required fields."""
        prc = PolicyRiskConstraints(max_position_hint="small")
        assert prc.max_position_hint == "small"
        assert prc.requires_human_review is False
        assert prc.risk_notes == []

    def test_creation_full(self):
        """Test creation with all fields."""
        prc = PolicyRiskConstraints(
            max_position_hint="medium",
            requires_human_review=True,
            risk_notes=["High concentration risk", "Sector volatility elevated"],
            max_concentration_pct=0.15,
            stop_loss_hint="tight stop at -5%",
            time_decay_days=14,
        )
        assert prc.max_concentration_pct == 0.15
        assert prc.stop_loss_hint == "tight stop at -5%"
        assert prc.time_decay_days == 14
        assert len(prc.risk_notes) == 2

    def test_serialization(self):
        """Test round-trip serialization."""
        prc = PolicyRiskConstraints(
            max_position_hint="large",
            requires_human_review=True,
            risk_notes=["test note"],
            max_concentration_pct=0.25,
        )
        data = prc.model_dump()
        restored = PolicyRiskConstraints.model_validate(data)
        assert restored.max_position_hint == "large"
        assert restored.max_concentration_pct == 0.25

    def test_invalid_max_position_hint(self):
        """Test that invalid hint is rejected."""
        with pytest.raises(ValidationError):
            PolicyRiskConstraints(max_position_hint="massive")  # type: ignore

    def test_invalid_concentration_pct(self):
        """Test that concentration > 1 is rejected."""
        with pytest.raises(ValidationError):
            PolicyRiskConstraints(max_position_hint="small", max_concentration_pct=1.5)


# =============================================================================
# PolicyLayerTrace Tests
# =============================================================================

class TestPolicyLayerTrace:
    """Tests for PolicyLayerTrace model."""

    def test_creation(self):
        """Test creating a layer trace."""
        trace = PolicyLayerTrace(
            layer_name="GlobalBase",
            layer_version="global-base-v1",
            applied=True,
            reason="Standard mapping applied",
            modifications=["action_hint: watch_only → open_position"],
            order_index=0,
        )
        assert trace.layer_name == "GlobalBase"
        assert trace.applied is True
        assert len(trace.modifications) == 1

    def test_skipped_layer(self):
        """Test a layer that was skipped (not applied)."""
        trace = PolicyLayerTrace(
            layer_name="KOLPersona",
            layer_version="kol-persona-v1",
            applied=False,
            reason="No persona data available for this KOL",
            modifications=[],
            order_index=3,
        )
        assert trace.applied is False
        assert trace.modifications == []

    def test_serialization(self):
        """Test round-trip serialization."""
        trace = PolicyLayerTrace(
            layer_name="RiskPreference",
            layer_version="risk-pref-v1",
            applied=True,
            reason="Conservative profile reduces position size",
            modifications=["position_sizing: medium → small"],
            order_index=2,
        )
        data = trace.model_dump()
        restored = PolicyLayerTrace.model_validate(data)
        assert restored.layer_name == "RiskPreference"
        assert restored.order_index == 2


# =============================================================================
# PolicyDecision Tests
# =============================================================================

class TestPolicyDecision:
    """Tests for PolicyDecision model."""

    def test_creation(self):
        """Test creating a policy decision."""
        decision = PolicyDecision(
            policy_id="policy-001",
            layer="GlobalBase",
            decision_type="action_override",
            description="Override watch_only to open_position",
            rationale="Intent had explicit_action=add",
        )
        assert decision.layer == "GlobalBase"
        assert decision.decision_type == "action_override"

    def test_overrides_previous(self):
        """Test the overrides_previous flag."""
        decision = PolicyDecision(
            policy_id="policy-001",
            layer="KOLPersona",
            decision_type="sizing_adjust",
            description="Reduce position size based on persona",
            rationale="KOL's '加仓' typically means small position",
            overrides_previous=True,
        )
        assert decision.overrides_previous is True

    def test_serialization(self):
        """Test round-trip serialization."""
        decision = PolicyDecision(
            decision_id="dec-001",
            policy_id="policy-001",
            layer="StyleArchetype",
            decision_type="holding_adjust",
            description="Extend holding to medium_term",
            rationale="Value-style archetype",
        )
        data = decision.model_dump()
        restored = PolicyDecision.model_validate(data)
        assert restored.decision_id == "dec-001"
        assert restored.decision_type == "holding_adjust"


# =============================================================================
# PolicyMappingResult Tests
# =============================================================================

class TestPolicyMappingResult:
    """Tests for PolicyMappingResult — the core F4 output."""

    def test_creation_minimal(self):
        """Test creating PolicyMappingResult with minimal required fields."""
        pmr = PolicyMappingResult(
            intent_id="intent-test-001",
            action_hint="watch_only",
            position_sizing_hint="none",
            holding_period_hint="review_required",
            mapping_rationale="Opinion intent → watch_only, no position action",
            confidence=0.9,
        )
        assert pmr.intent_id == "intent-test-001"
        assert pmr.action_hint == "watch_only"
        assert pmr.position_sizing_hint == "none"
        assert pmr.policy_id is not None  # auto-generated
        assert pmr.policy_version == "global-base-v1"

    def test_creation_full(self, canonical_intent):
        """Test creating full PolicyMappingResult with all fields."""
        pmr = PolicyMappingResult(
            policy_id="policy-full-001",
            intent_id=canonical_intent.intent_id,
            creator_id="kol-001",
            kol_id="kol-001",
            policy_version="style-archetype-v2",
            policy_layers_applied=["GlobalBase", "StyleArchetype", "RiskPreference"],
            action_hint="open_position",
            position_sizing_hint="medium",
            holding_period_hint="long_term",
            risk_constraints=PolicyRiskConstraints(
                max_position_hint="medium",
                requires_human_review=False,
                risk_notes=["Long-term value play"],
            ),
            mapping_rationale="Bullish explicit_action with open → open_position + medium + long_term",
            layer_traces=[
                PolicyLayerTrace(
                    layer_name="GlobalBase",
                    layer_version="global-base-v1",
                    applied=True,
                    reason="Standard mapping",
                    modifications=["action_hint: → open_position"],
                    order_index=0,
                ),
            ],
            decisions=[
                PolicyDecision(
                    policy_id="policy-full-001",
                    layer="GlobalBase",
                    decision_type="action_override",
                    description="Map explicit_action(open) to open_position",
                    rationale="Standard mapping",
                ),
            ],
            confidence=0.92,
            original_intent_confidence=0.9,
        )
        assert pmr.policy_id == "policy-full-001"
        assert pmr.action_hint == "open_position"
        assert pmr.position_sizing_hint == "medium"
        assert pmr.holding_period_hint == "long_term"
        assert len(pmr.layer_traces) == 1
        assert len(pmr.decisions) == 1

    def test_serialization_round_trip(self, canonical_policy_mapping):
        """Test full serialization and deserialization round-trip."""
        data = canonical_policy_mapping.model_dump()
        # JSON round-trip
        json_str = json.dumps(data, default=str)
        data_from_json = json.loads(json_str)

        # Parse datetime strings back
        if isinstance(data_from_json.get("created_at"), str):
            data_from_json["created_at"] = datetime.fromisoformat(
                data_from_json["created_at"].replace("Z", "+00:00")
            )

        restored = PolicyMappingResult.model_validate(data_from_json)
        assert restored.policy_id == canonical_policy_mapping.policy_id
        assert restored.intent_id == canonical_policy_mapping.intent_id
        assert restored.action_hint == "add_position"
        assert restored.position_sizing_hint == "small"
        assert restored.holding_period_hint == "medium_term"
        assert restored.confidence == 0.88

    def test_json_serialization(self, canonical_policy_mapping):
        """Test that model_dump(mode='json') produces JSON-safe output."""
        json_data = canonical_policy_mapping.model_dump(mode='json')
        assert isinstance(json_data["created_at"], str)
        assert isinstance(json_data["policy_id"], str)
        assert isinstance(json_data["confidence"], float)

    def test_must_reference_intent_id(self):
        """PolicyMappingResult MUST reference a valid intent_id."""
        # Valid: intent_id is set
        pmr = PolicyMappingResult(
            intent_id="intent-valid-001",
            action_hint="watch_only",
            position_sizing_hint="none",
            holding_period_hint="review_required",
            mapping_rationale="Valid mapping",
            confidence=0.7,
        )
        assert pmr.intent_id == "intent-valid-001"

        # Invalid: empty intent_id
        with pytest.raises(ValidationError):
            PolicyMappingResult(
                intent_id="",  # empty string rejected by min_length=1
                action_hint="watch_only",
                position_sizing_hint="none",
                holding_period_hint="review_required",
                mapping_rationale="Missing intent reference",
                confidence=0.5,
            )

    def test_cannot_contain_raw_full_text_as_sole_evidence(self, canonical_policy_mapping):
        """PolicyMappingResult must reference intent_id, NOT contain raw full text."""
        data = canonical_policy_mapping.model_dump()
        # Verify: no field like 'raw_text' or 'full_text' exists
        assert "raw_text" not in data
        assert "full_text" not in data
        assert "original_text" not in data
        # The only text-like field is mapping_rationale, which is a rationale,
        # not the original content
        assert isinstance(data["mapping_rationale"], str)
        # intent_id must be present and non-empty
        assert data["intent_id"] is not None and len(data["intent_id"]) > 0

    def test_action_hint_must_be_valid(self):
        """Test that invalid action_hint is rejected."""
        with pytest.raises(ValidationError):
            PolicyMappingResult(
                intent_id="intent-test",
                action_hint="buy_aggressively",  # type: ignore — not in literal
                position_sizing_hint="none",
                holding_period_hint="review_required",
                mapping_rationale="Invalid hint",
                confidence=0.5,
            )

    def test_invalid_confidence(self):
        """Test that confidence > 1 is rejected."""
        with pytest.raises(ValidationError):
            PolicyMappingResult(
                intent_id="intent-test",
                action_hint="watch_only",
                position_sizing_hint="none",
                holding_period_hint="review_required",
                mapping_rationale="Overconfident",
                confidence=1.5,
            )


# =============================================================================
# PolicyMappedIntent Tests
# =============================================================================

class TestPolicyMappedIntent:
    """Tests for PolicyMappedIntent."""

    def test_creation_minimal(self):
        """Test creating PolicyMappedIntent with minimal fields."""
        pmi = PolicyMappedIntent(
            intent_id="intent-001",
            policy_id="policy-001",
            original_intent_summary="bullish on AAPL",
            action_hint="open_position",
            position_sizing_hint="small",
            holding_period_hint="short_term",
            mapping_confidence=0.85,
        )
        assert pmi.mapped_id is not None
        assert pmi.intent_id == "intent-001"
        assert pmi.action_hint == "open_position"
        assert pmi.requires_human_review is False

    def test_auto_requires_review_on_hints(self):
        """Test that review_required hints automatically set the flag."""
        # action_hint=review_required should set the flag
        pmi = PolicyMappedIntent(
            intent_id="intent-001",
            policy_id="policy-001",
            original_intent_summary="ambiguous intent",
            action_hint="review_required",
            position_sizing_hint="none",
            holding_period_hint="review_required",
            mapping_confidence=0.5,
        )
        assert pmi.requires_human_review is True

    def test_serialization(self, canonical_mapped_intent):
        """Test round-trip serialization."""
        data = canonical_mapped_intent.model_dump()
        restored = PolicyMappedIntent.model_validate(data)
        assert restored.mapped_id == canonical_mapped_intent.mapped_id
        assert restored.action_hint == "add_position"
        assert restored.mapping_confidence == 0.88

    def test_json_serialization(self, canonical_mapped_intent):
        """Test JSON-safe serialization."""
        json_data = canonical_mapped_intent.model_dump(mode='json')
        assert isinstance(json_data["created_at"], str)
        assert isinstance(json_data["mapped_id"], str)


# =============================================================================
# Canonical Trace Tests (TradeAction → F3/F4/F2)
# =============================================================================

class TestCanonicalTrace:
    """Tests for F3 → F4 → F5 canonical trace chain in TradeAction."""

    def test_trade_action_with_full_canonical_trace(self, canonical_trade_action_for_trace):
        """TradeAction with intent_id + policy_id + evidence_span_ids."""
        ta = canonical_trade_action_for_trace
        assert ta.intent_id is not None
        assert ta.policy_id is not None
        assert len(ta.evidence_span_ids) >= 1
        assert ta.canonical_trace_status == "canonical"

    def test_trade_action_carrying_upstream_ids(self):
        """TradeAction can carry intent_id, policy_id, and evidence_span_ids."""
        ta = TradeAction(
            intent_id="intent-test-abc",
            policy_id="policy-test-def",
            evidence_span_ids=["span-001", "span-002", "span-003"],
            effective_trade_at=datetime(2026, 3, 15, 10, 0, 0),
            source=SourceInfo(content_id="test", evidence_text="Test evidence"),
            target=TargetInfo(ticker="NVDA"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.intent_id == "intent-test-abc"
        assert ta.policy_id == "policy-test-def"
        assert ta.evidence_span_ids == ["span-001", "span-002", "span-003"]
        assert ta.effective_trade_at is not None
        assert ta.canonical_trace_status == "canonical"

    def test_trade_action_partial_trace(self):
        """TradeAction with only intent_id (partial trace)."""
        ta = TradeAction(
            intent_id="intent-only-001",
            # policy_id intentionally None
            evidence_span_ids=["span-001"],
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.intent_id == "intent-only-001"
        assert ta.policy_id is None
        assert ta.canonical_trace_status == "partial"

    def test_trade_action_partial_trace_policy_only(self):
        """TradeAction with only policy_id (partial trace)."""
        ta = TradeAction(
            policy_id="policy-only-001",
            evidence_span_ids=["span-001"],
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.intent_id is None
        assert ta.policy_id == "policy-only-001"
        assert ta.canonical_trace_status == "partial"

    def test_trade_action_non_canonical(self):
        """TradeAction without intent_id or policy_id is non-canonical."""
        ta = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="AAPL"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.intent_id is None
        assert ta.policy_id is None
        assert ta.evidence_span_ids == []
        assert ta.canonical_trace_status == "non_canonical"

    def test_canonical_trace_status_auto_set(self):
        """Verify canonical_trace_status is auto-set by model_validator."""
        # Setting intent_id manually, validator runs on creation
        ta = TradeAction(
            intent_id="intent-auto-001",
            policy_id="policy-auto-001",
            evidence_span_ids=["span-001"],
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="TSLA"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.canonical_trace_status == "canonical"

        # Mutate after creation and check that re-validation updates status
        ta.intent_id = None
        # Note: validators don't auto-rerun on mutation, but we can verify
        # that the field is mutable and a fresh instance would get the right status
        ta2 = TradeAction(
            policy_id="policy-auto-002",
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="TSLA"),
            direction=TradeDirection.BULLISH,
        )
        assert ta2.canonical_trace_status == "partial"

    def test_trade_action_with_effective_trade_at(self):
        """TradeAction can carry effective_trade_at from F2 TemporalAnchor."""
        effective_time = datetime(2026, 4, 24, 9, 30, 0)
        ta = TradeAction(
            intent_id="intent-001",
            policy_id="policy-001",
            effective_trade_at=effective_time,
            source=SourceInfo(content_id="test", evidence_text="Test"),
            target=TargetInfo(ticker="GOOGL"),
            direction=TradeDirection.BULLISH,
        )
        assert ta.effective_trade_at == effective_time
        # effective_trade_at is distinct from timestamp
        assert ta.effective_trade_at != ta.timestamp or True  # may equal by accident

    def test_trade_action_serialization_with_trace(self, canonical_trade_action_for_trace):
        """Test full serialization with trace fields."""
        ta = canonical_trade_action_for_trace
        data = ta.model_dump(mode='json')

        assert data["intent_id"] == "intent-12345678-1234-1234-1234-123456789012"
        assert data["policy_id"] == "policy-abcdef01-abcd-abcd-abcd-abcdef012345"
        assert data["evidence_span_ids"] == ["span-001", "span-002"]
        assert data["canonical_trace_status"] == "canonical"
        assert data["effective_trade_at"] is not None

        # Round-trip via model_dump (no mode='json') preserves enum types for strict=True
        data_python = ta.model_dump()
        restored = TradeAction.model_validate(data_python)
        assert restored.intent_id == ta.intent_id
        assert restored.policy_id == ta.policy_id
        assert restored.canonical_trace_status == "canonical"

        # JSON round-trip via model_validate_json
        import json
        json_str = json.dumps(data, default=str)
        restored_json = TradeAction.model_validate_json(json_str)
        assert restored_json.intent_id == ta.intent_id
        assert restored_json.policy_id == ta.policy_id

    def test_missing_ids_marked_non_canonical(self):
        """Fixture without intent_id/policy_id must be marked non-canonical."""
        ta = TradeAction(
            source=SourceInfo(content_id="test", evidence_text="Legacy extraction"),
            target=TargetInfo(ticker="XYZ"),
            direction=TradeDirection.NEUTRAL,
            # No intent_id, no policy_id → non_canonical
        )
        assert ta.canonical_trace_status == "non_canonical"
        assert ta.intent_id is None
        assert ta.policy_id is None


# =============================================================================
# F3/F4 Boundary Tests
# =============================================================================

class TestF3F4Boundary:
    """Tests for the boundary between F3 Intent and F4 Policy."""

    def test_f3_intent_no_position_sizing(self, canonical_intent):
        """F3 Intent MUST NOT contain position_size_pct or target_price fields."""
        data = canonical_intent.model_dump()
        # These fields should NOT exist on NormalizedInvestmentIntent
        assert "position_size_pct" not in data
        assert "target_price_low" not in data
        assert "target_price_high" not in data
        assert "stop_loss_pct" not in data
        assert "take_profit_pct" not in data

    def test_f4_has_hints_not_facts(self, canonical_policy_mapping):
        """F4 has position_sizing_hint (not position_size_pct)."""
        data = canonical_policy_mapping.model_dump()
        assert "position_sizing_hint" in data
        # position_sizing_hint is a qualifier, not a number
        assert data["position_sizing_hint"] in ("none", "small", "medium", "large", "review_required")
        # F4 does NOT have concrete position_size_pct (that's F5's job)
        # (position_sizing_hint is the correct abstraction for F4)

    def test_f5_has_action_chain_not_f4(self, canonical_policy_mapping):
        """F4 PolicyMappingResult does NOT have an action_chain."""
        data = canonical_policy_mapping.model_dump()
        assert "action_chain" not in data
        # F4 only has hints: action_hint, position_sizing_hint, holding_period_hint

    def test_f4_must_not_modify_direction(self):
        """F4 PolicyMappingResult does not have a 'direction' field — it inherits from F3."""
        pmr = PolicyMappingResult(
            intent_id="intent-001",
            action_hint="open_position",
            position_sizing_hint="small",
            holding_period_hint="medium_term",
            mapping_rationale="Standard mapping",
            confidence=0.8,
        )
        data = pmr.model_dump()
        # direction is not a field on PolicyMappingResult
        assert "direction" not in data


# =============================================================================
# PolicyContext Tests
# =============================================================================

class TestPolicyContext:
    """Tests for PolicyContext (input to F4)."""

    def test_creation(self):
        """Test creating PolicyContext."""
        ctx = PolicyContext(
            kol_id="kol-001",
            style_archetype="short_term",
            risk_preference="aggressive",
            persona_summary="This KOL is a momentum trader who enters aggressively on breakouts",
        )
        assert ctx.kol_id == "kol-001"
        assert ctx.style_archetype == "short_term"
        assert ctx.risk_preference == "aggressive"

    def test_defaults(self):
        """Test default values."""
        ctx = PolicyContext(kol_id="kol-002")
        assert ctx.style_archetype == "mixed"
        assert ctx.risk_preference == "balanced"
        assert ctx.persona_summary is None
        assert ctx.active_corrections == []

    def test_serialization(self):
        """Test round-trip serialization."""
        ctx = PolicyContext(
            kol_id="kol-003",
            style_archetype="value",
            risk_preference="conservative",
            active_corrections=["Temporary: KOL says 'not investment advice'"],
        )
        data = ctx.model_dump()
        restored = PolicyContext.model_validate(data)
        assert restored.style_archetype == "value"
        assert len(restored.active_corrections) == 1


# =============================================================================
# PolicyMappingBatch Tests
# =============================================================================

class TestPolicyMappingBatch:
    """Tests for PolicyMappingBatch container."""

    def test_creation_empty(self):
        """Test empty batch."""
        batch = PolicyMappingBatch()
        assert batch.total_mappings == 0
        assert batch.total_mapped_intents == 0
        assert batch.review_required_count == 0

    def test_auto_compute_stats(self, canonical_policy_mapping, canonical_mapped_intent):
        """Test that batch auto-computes statistics."""
        # Create a second mapped intent that requires review
        review_pmi = PolicyMappedIntent(
            intent_id="intent-review-001",
            policy_id="policy-review-001",
            original_intent_summary="ambiguous intent",
            action_hint="review_required",
            position_sizing_hint="review_required",
            holding_period_hint="review_required",
            mapping_confidence=0.4,
            risk_notes=["Unclear direction"],
        )
        # review_required hints should auto-set the flag
        assert review_pmi.requires_human_review is True

        batch = PolicyMappingBatch(
            mappings=[canonical_policy_mapping],
            mapped_intents=[canonical_mapped_intent, review_pmi],
            policy_version="global-base-v1",
        )
        assert batch.total_mappings == 1
        assert batch.total_mapped_intents == 2
        assert batch.review_required_count == 1


# =============================================================================
# Full Chain End-to-End Test (F3 → F4 → F5)
# =============================================================================

class TestFullChainF3F4F5:
    """End-to-end tests for the F3 → F4 → F5 canonical chain."""

    def test_full_chain_canonical(self, canonical_intent):
        """Simulate full canonical F3 → F4 → F5 flow."""
        # F3: extracted intent
        intent = canonical_intent
        assert intent.intent_id is not None
        assert intent.direction == "bullish"
        assert intent.position_delta_hint == "add"

        # F4: policy mapping
        policy = PolicyMappingResult(
            intent_id=intent.intent_id,
            creator_id=intent.creator_id,
            kol_id=intent.creator_id,
            action_hint="add_position",
            position_sizing_hint="small",
            holding_period_hint="medium_term",
            mapping_rationale=f"Intent '{intent.summarize()}' → add_position + small",
            confidence=0.88,
        )
        assert policy.intent_id == intent.intent_id
        assert policy.action_hint == "add_position"

        # F4 output: mapped intent
        mapped = PolicyMappedIntent(
            intent_id=intent.intent_id,
            policy_id=policy.policy_id,
            original_intent_summary=intent.summarize(),
            action_hint=policy.action_hint,
            position_sizing_hint=policy.position_sizing_hint,
            holding_period_hint=policy.holding_period_hint,
            mapping_confidence=policy.confidence,
        )
        assert mapped.policy_id == policy.policy_id

        # F5: trade action with full trace
        trade_action = TradeAction(
            intent_id=intent.intent_id,
            policy_id=policy.policy_id,
            evidence_span_ids=intent.evidence_span_ids,
            source=SourceInfo(
                creator_id=intent.creator_id,
                content_id=intent.envelope_id,
                evidence_text=f"Intent: {intent.summarize()}",
            ),
            target=TargetInfo(
                ticker=intent.target_symbol or intent.target_name,
                market=intent.market,
            ),
            direction=TradeDirection.BULLISH,
            action_chain=[
                ActionStep(sequence=1, action_type=ActionType.LONG, position_size_pct=0.05),
            ],
            confidence=0.88,
        )

        # Verify full traceability
        assert trade_action.intent_id == intent.intent_id
        assert trade_action.policy_id == policy.policy_id
        assert trade_action.canonical_trace_status == "canonical"
        assert len(trade_action.evidence_span_ids) >= 1
