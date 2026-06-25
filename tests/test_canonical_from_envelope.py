"""Tests for run_canonical_from_envelope and the F5 route's F2-envelope path.

Background: the F5 extraction route used to read only the top-level ``text`` field
of each input JSON and feed it to the deprecated ``run_canonical_extraction``.
F2-anchored envelopes have **no** top-level text (their content lives in
``blocks``), so the route silently skipped them and discarded every
``entity_anchor`` / ``temporal_anchor`` the F2 stage produced.

These tests pin the canonical F2 → F3 → F4 → F5 path:
  1. run_canonical_from_envelope consumes a real F2 envelope so F3 resolves the
     target symbol from ``envelope.entity_anchors``.
  2. The runner feeds the *real* envelope (not a fabricated one) to F3.
  3. The quality gate still rejects low-quality envelopes on the new path.
  4. The F5 route selects the envelope path for serialized ContentEnvelopes.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Fixed publish time so canonical ExecutionTiming never falls back to runtime now().
_PUBLISHED_AT = datetime(2026, 3, 12, 15, 36, tzinfo=timezone(timedelta(hours=8)))

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.quality import QualityCard
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent, PolicyMappingBatch
from finer.pipeline.canonical_runner import run_canonical_from_envelope


# ── Helpers ──────────────────────────────────────────────────────────────────


def _pass_card() -> QualityCard:
    return QualityCard(
        readability_score=0.95,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.95,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.85,
        evidence_traceability_score=0.9,
    )


def _reject_card() -> QualityCard:
    return QualityCard(
        readability_score=0.2,
        semantic_completeness_score=0.2,
        financial_relevance_score=0.1,
        entity_resolution_score=0.2,
        temporal_resolution_score=0.15,
        evidence_traceability_score=0.1,
    )


def _f2_envelope(blocks_text, anchors=None, card=None) -> ContentEnvelope:
    """A serialized-shaped F2 envelope: content in blocks, anchors at top level."""
    blocks = [
        ContentBlock(
            block_type="paragraph",
            text=text,
            order=i,
            quality_card=_pass_card(),
        )
        for i, text in enumerate(blocks_text)
    ]
    return ContentEnvelope(
        envelope_id="f2-env-001",
        source_type="feishu_doc",
        source_title="Test F2 Envelope",
        creator_id="test-kol",
        published_at=_PUBLISHED_AT,
        quality_card=card or _pass_card(),
        blocks=blocks,
        entity_anchors=anchors or [],
        temporal_anchors=[],
    )


def _ndt_anchor() -> EntityAnchor:
    return EntityAnchor(
        raw_text="宁德时代",
        resolved_name="宁德时代",
        resolved_symbol="300750.SZ",
        entity_type="stock",
        confidence=0.95,
    )


def _action_symbol(action) -> str:
    """TradeAction symbol accessor that tolerates schema field naming."""
    target = getattr(action, "target", None)
    return (
        getattr(target, "symbol", None)
        or getattr(target, "ticker", None)
        or getattr(action, "target_symbol", None)
    )


# ── 1. Real chain: anchor drives symbol resolution ───────────────────────────


@pytest.mark.asyncio
async def test_from_envelope_resolves_symbol_from_entity_anchor():
    """A bullish block + entity anchor yields a canonical action on the anchor symbol."""
    envelope = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])

    actions = await run_canonical_from_envelope(envelope, {"author": "test-kol"})

    assert actions, "expected at least one canonical TradeAction from the F2 envelope"
    action = actions[0]
    assert action.canonical_trace_status == "canonical"
    assert _action_symbol(action) == "300750.SZ"


# ── 2. Wiring: the REAL envelope (with anchors) is fed to F3 ──────────────────


@pytest.mark.asyncio
async def test_from_envelope_feeds_real_envelope_to_f3():
    """Deterministic proof the runner passes our anchored envelope into F3 (not a
    text-fabricated one) and emits canonical actions."""
    envelope = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])

    intent = NormalizedInvestmentIntent(
        intent_id="intent-001",
        envelope_id=envelope.envelope_id,
        block_ids=["b0"],
        creator_id="test-kol",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="open",
        conviction=0.85,
        confidence=0.85,
        evidence_span_ids=["span-001"],
    )
    span = EvidenceSpan(
        evidence_span_id="span-001",
        block_id="b0",
        char_start=0,
        char_end=4,
        text="准备加仓",
        span_type="intent_keyword",
        confidence=0.85,
    )
    mock_result = MagicMock()
    mock_result.intents = [intent]
    mock_result.evidence_spans = [span]

    mapped = PolicyMappedIntent(
        intent_id="intent-001",
        policy_id="policy-001",
        original_intent_summary="bullish explicit action",
        action_hint="open_position",
        position_sizing_hint="small",
        holding_period_hint="medium_term",
        mapping_confidence=0.8,
        requires_human_review=False,
    )
    mock_batch = PolicyMappingBatch(mapped_intents=[mapped], mappings=[])

    with (
        patch("finer.extraction.intent_extractor.RuleBasedIntentExtractor") as MockExtractor,
        patch("finer.policy.policy_mapper.PolicyMapper") as MockMapper,
    ):
        MockExtractor.return_value.extract.return_value = mock_result
        MockMapper.return_value.map_batch.return_value = mock_batch

        actions = await run_canonical_from_envelope(envelope, {"author": "test-kol"})

    # The real F2 envelope (carrying entity_anchors) must be what F3 receives.
    MockExtractor.return_value.extract.assert_called_once_with(envelope)
    assert actions
    assert actions[0].canonical_trace_status == "canonical"
    assert _action_symbol(actions[0]) == "300750.SZ"


# ── 3. Quality gate still rejects on the new path ────────────────────────────


@pytest.mark.asyncio
async def test_from_envelope_rejects_low_quality_before_f3():
    envelope = _f2_envelope(
        ["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()], card=_reject_card()
    )

    with patch("finer.extraction.intent_extractor.RuleBasedIntentExtractor") as MockExtractor:
        actions = await run_canonical_from_envelope(envelope, {"author": "test-kol"})

    assert actions == []
    MockExtractor.return_value.extract.assert_not_called()


# ── 4. F5 route selects the envelope path for serialized ContentEnvelopes ─────


@pytest.mark.asyncio
async def test_route_uses_envelope_path_for_f2_json(tmp_path):
    """An F2 envelope file (no top-level text) must go through the envelope path,
    not the legacy raw-text path that would skip it."""
    from finer.api.routes import extraction as ext_route

    envelope = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])
    in_dir = tmp_path / "F2_anchored"
    out_dir = tmp_path / "F5_executed"
    in_dir.mkdir()
    out_dir.mkdir()
    (in_dir / "env1.json").write_text(envelope.model_dump_json(), encoding="utf-8")

    fake_action = MagicMock()
    fake_action.model_dump.return_value = {
        "action_id": "a1",
        "canonical_trace_status": "canonical",
    }

    with (
        patch(
            "finer.pipeline.canonical_runner.run_canonical_from_envelope",
            new=AsyncMock(return_value=[fake_action]),
        ) as m_env,
        patch(
            "finer.pipeline.canonical_runner.run_canonical_extraction",
            new=AsyncMock(return_value=[]),
        ) as m_text,
    ):
        await ext_route._run_extraction_pipeline_async(in_dir, out_dir, limit=10)

    m_env.assert_called_once()
    m_text.assert_not_called()

    out_files = list(out_dir.glob("*_actions.json"))
    assert len(out_files) == 1
    payload = json.loads(out_files[0].read_text(encoding="utf-8"))
    assert payload["model"] == "canonical-f2-envelope"
    assert payload["actions"] == [{"action_id": "a1", "canonical_trace_status": "canonical"}]
    # Actions must serialize via mode="json" so datetime fields (the four
    # execution-timing clocks) become ISO strings, not unserializable datetimes.
    fake_action.model_dump.assert_called_once_with(mode="json")


# ── 5. JSON round-trip: anchors arrive as dicts but still resolve ────────────


@pytest.mark.asyncio
async def test_from_envelope_handles_json_roundtrip_anchor_dicts():
    """ContentEnvelope types anchors as List[Any], so model_validate() on a
    serialized F2 envelope yields dict anchors. The runner must coerce them so
    the real F5-route file path resolves symbols (regression guard)."""
    from finer.schemas.temporal import TemporalAnchor

    built = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])
    # Strict TemporalAnchor with a datetime that survives JSON only as a string.
    built.temporal_anchors = [
        TemporalAnchor.create_published_at(
            raw_text="2026-03-12", resolved_time=_PUBLISHED_AT, confidence=1.0
        )
    ]
    reloaded = ContentEnvelope.model_validate(json.loads(built.model_dump_json()))
    assert isinstance(reloaded.entity_anchors[0], dict)  # documents the root cause
    assert isinstance(reloaded.temporal_anchors[0], dict)  # incl. strict temporal anchor

    actions = await run_canonical_from_envelope(reloaded, {"author": "test-kol"})

    assert actions, "expected canonical actions from a JSON-reloaded F2 envelope"
    assert actions[0].canonical_trace_status == "canonical"
    assert _action_symbol(actions[0]) == "300750.SZ"


# ── 5. F3/F4/evidence persistence lights up the audit Intent/Policy/Evidence ──


@pytest.mark.asyncio
async def test_persist_dir_writes_f3_f4_evidence_sidecars(tmp_path):
    """persist_dir writes per-id F3/F4/F2-evidence sidecars the assembler resolves."""
    from finer.services.audit_assembler import AuditAssembler

    envelope = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])
    actions = await run_canonical_from_envelope(
        envelope, {"author": "test-kol"}, persist_dir=tmp_path
    )
    assert actions
    action = actions[0]

    intent_file = tmp_path / "F3_intents" / f"{action.intent_id}.json"
    policy_file = tmp_path / "F4_policy_mapped" / f"{action.policy_id}.json"
    assert intent_file.is_file(), "F3 intent sidecar should be written"
    assert policy_file.is_file(), "F4 policy sidecar should be written"

    # Only action-referenced intents/policies are persisted — no orphan sidecars
    # for rejected intents / unmapped policies.
    persisted_intents = {p.stem for p in (tmp_path / "F3_intents").glob("*.json")}
    persisted_policies = {p.stem for p in (tmp_path / "F4_policy_mapped").glob("*.json")}
    assert persisted_intents == {a.intent_id for a in actions}
    assert persisted_policies == {a.policy_id for a in actions}

    # Every evidence span the action references is persisted.
    assert action.evidence_span_ids, "action should carry evidence spans"
    for span_id in action.evidence_span_ids:
        assert (tmp_path / "F2_evidence" / f"{span_id}.json").is_file()

    # The assembler now populates Intent + Policy + Evidence panels.
    f5_dir = tmp_path / "F5_executed"
    f5_dir.mkdir(parents=True, exist_ok=True)
    (f5_dir / f"{envelope.envelope_id}_actions.json").write_text(
        json.dumps(
            {
                "source_file": "x",
                "model": "canonical-f2-envelope",
                "actions": [action.model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )
    bundle = AuditAssembler(data_root=tmp_path, ttl_seconds=0).get_trace_bundle(
        action.trade_action_id
    )
    assert bundle is not None
    assert bundle["intent"] is not None
    assert bundle["intent"]["intent_id"] == action.intent_id
    assert bundle["policy"] is not None
    assert bundle["policy"]["policy_id"] == action.policy_id
    # Evidence panel is no longer a stub.
    assert len(bundle["evidence_spans"]) == len(action.evidence_span_ids)
    served_ids = {s["evidence_span_id"] for s in bundle["evidence_spans"]}
    assert served_ids == set(action.evidence_span_ids)
    assert all(s.get("text") for s in bundle["evidence_spans"])


@pytest.mark.asyncio
async def test_no_persist_dir_writes_nothing(tmp_path):
    """Without persist_dir the runner stays read-only (no sidecars)."""
    envelope = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])
    actions = await run_canonical_from_envelope(envelope, {"author": "test-kol"})
    assert actions
    assert not (tmp_path / "F3_intents").exists()
    assert not (tmp_path / "F4_policy_mapped").exists()
    assert not (tmp_path / "F2_evidence").exists()


@pytest.mark.asyncio
async def test_action_rationale_is_human_readable():
    """Rationale is grounded in target/direction/evidence, not '<action> via <uuid>'."""
    envelope = _f2_envelope(["看好这只股票，准备加仓。"], anchors=[_ndt_anchor()])
    actions = await run_canonical_from_envelope(envelope, {"author": "test-kol"})
    assert actions
    rationale = actions[0].rationale or ""

    assert "Canonical F3→F4→F5" not in rationale  # old placeholder gone
    assert " via " not in rationale  # old "<action_hint> via <policy_id>" gone
    assert "宁德时代" in rationale or "300750" in rationale  # carries the target
    assert "·" in rationale  # new structured format
