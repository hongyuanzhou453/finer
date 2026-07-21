"""C9 follow-up — ``run_canonical_from_artifacts(persist_dir=...)`` writes the F2
evidence sidecars the emitted actions reference.

Root cause this pins: the broker driver called ``run_canonical_from_artifacts``
without ``persist_dir``, so it wrote F5 (+ F4) but never the per-id
``F2_evidence/{span_id}.json`` sidecars — the three-way trace audit then found
every broker action's evidence leg unresolvable (6.6%, C8). These tests assert:

  * persist_dir writes exactly the grounded spans the actions reference
    (symbol-first resolution — NOT the whole envelope's span set);
  * upstream F3/F4 artifacts are the caller's concern and are NOT written here;
  * without persist_dir the runner stays read-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from finer.pipeline.canonical_runner import run_canonical_from_artifacts
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent, PolicyMappingBatch
from finer.schemas.quality import QualityCard

_PUBLISHED_AT = datetime(2026, 3, 12, 15, 36, tzinfo=timezone(timedelta(hours=8)))


def _pass_card() -> QualityCard:
    return QualityCard(
        readability_score=0.95,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.95,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.85,
        evidence_traceability_score=0.9,
    )


def _anchor(symbol: str, raw_text: str, span_id: str) -> tuple[EntityAnchor, EvidenceSpan]:
    span = EvidenceSpan(
        evidence_span_id=span_id,
        block_id="b0",
        char_start=0,
        char_end=max(1, len(raw_text)),
        text=raw_text,
        span_type="entity",
        confidence=1.0,
    )
    anchor = EntityAnchor(
        entity_type="stock",
        raw_text=raw_text,
        resolved_symbol=symbol,
        market="CN",
        confidence=1.0,
        evidence_span_id=span_id,
        metadata={"evidence_span_ids": [span_id]},
    )
    return anchor, span


def _two_symbol_envelope() -> tuple[ContentEnvelope, str, str]:
    """F2 envelope anchoring two tickers on one block, each with its own span."""
    a1, s1 = _anchor("300750.SZ", "宁德时代", "f2-span-target")
    a2, s2 = _anchor("600519.SH", "贵州茅台", "f2-span-other")
    block = ContentBlock(
        block_id="b0",
        block_type="paragraph",
        text="宁德时代继续走强，建议加仓；贵州茅台只是顺带一提。",
        order=0,
        quality_card=_pass_card(),
        evidence_spans=[s1, s2],
    )
    env = ContentEnvelope(
        envelope_id="env-artifacts-001",
        source_type="feishu_doc",
        creator_id="kol-test-001",
        published_at=_PUBLISHED_AT,
        quality_card=_pass_card(),
        blocks=[block],
        entity_anchors=[a1, a2],
        temporal_anchors=[],
    )
    return env, s1.evidence_span_id, s2.evidence_span_id


def _intent_and_batch() -> tuple[NormalizedInvestmentIntent, PolicyMappingBatch]:
    intent = NormalizedInvestmentIntent(
        intent_id="bri-test-intent",
        envelope_id="env-artifacts-001",
        block_ids=["b0"],
        creator_id="kol-test-001",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.8,
        confidence=0.8,
        evidence_span_ids=["span-f3-uuid"],  # F3 self-span; never matches F2
        ambiguity_flags=[],
    )
    mapped = PolicyMappedIntent(
        mapped_id="mapped-001",
        intent_id=intent.intent_id,
        policy_id="policy-test-001",
        original_intent_summary="bullish 宁德时代",
        action_hint="open_position",
        position_sizing_hint="small",
        holding_period_hint="short_term",
        risk_notes=[],
        mapping_confidence=0.9,
        requires_human_review=False,
    )
    return intent, PolicyMappingBatch(mapped_intents=[mapped])


@pytest.mark.asyncio
async def test_persist_dir_writes_grounded_evidence_sidecars(tmp_path):
    env, target_span, other_span = _two_symbol_envelope()
    intent, batch = _intent_and_batch()

    result = await run_canonical_from_artifacts(
        intents=[intent],
        policy_batch=batch,
        evidence_spans=[],
        envelope=env,
        strategy="programmatic",
        persist_dir=tmp_path,
    )

    assert result.trade_actions, "the grounded intent should produce an action"
    action = result.trade_actions[0]
    assert action.evidence_span_ids, "action must carry F2-grounded evidence"

    # Every span the action references is persisted as a sidecar the audit resolves.
    for span_id in action.evidence_span_ids:
        assert (tmp_path / "F2_evidence" / f"{span_id}.json").is_file()

    # Grounded, not over-broad: the target symbol's span is written, the
    # unrelated second symbol's span is NOT (symbol-first F2 resolution).
    assert (tmp_path / "F2_evidence" / f"{target_span}.json").is_file()
    assert not (tmp_path / "F2_evidence" / f"{other_span}.json").exists()

    # F3/F4 are upstream inputs the caller owns; the artifacts path does not
    # write them (unlike the envelope path, which generates and persists them).
    assert not (tmp_path / "F3_intents").exists()
    assert not (tmp_path / "F4_policy_mapped").exists()


@pytest.mark.asyncio
async def test_no_persist_dir_stays_read_only(tmp_path):
    env, _, _ = _two_symbol_envelope()
    intent, batch = _intent_and_batch()

    result = await run_canonical_from_artifacts(
        intents=[intent],
        policy_batch=batch,
        evidence_spans=[],
        envelope=env,
        strategy="programmatic",
    )
    assert result.trade_actions
    assert not (tmp_path / "F2_evidence").exists()
