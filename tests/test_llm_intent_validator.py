"""Tests for the F3 deterministic LLM-intent validator (constrained proposal).

Each check maps to a failure mode from the 2026-07-05 regen acceptance:
fabricated quotes, direction contradicting its own evidence, hallucinated /
off-anchor targets.
"""
from __future__ import annotations

from types import SimpleNamespace

from finer.extraction.intent_extractor import _validate_llm_intents
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent


def make_intent(**overrides) -> NormalizedInvestmentIntent:
    base = dict(
        envelope_id="env-1",
        block_ids=["b1"],
        creator_id="k1",
        target_type="stock",
        target_name="谷歌",
        target_symbol="GOOGL",
        market="US",
        direction="bullish",
        actionability="opinion",
        position_delta_hint="none",
        conviction=0.6,
        confidence=0.8,
        time_horizon_hint="unknown",
        evidence_span_ids=["s1"],
        ambiguity_flags=[],
    )
    base.update(overrides)
    return NormalizedInvestmentIntent(**base)


def make_span(sid: str, text: str, span_type: str = "intent_keyword") -> EvidenceSpan:
    return EvidenceSpan.from_dict(
        {
            "schema_version": "1.0",
            "evidence_span_id": sid,
            "block_id": "b1",
            "char_start": 0,
            "char_end": len(text),
            "text": text,
            "confidence": 0.8,
            "span_type": span_type,
        }
    )


ANCHORS = [
    {"resolved_symbol": "GOOGL", "raw_text": "谷歌", "resolved_name": "谷歌", "market": "US", "entity_type": "ticker"},
    {"resolved_symbol": "600519.SH", "raw_text": "贵州茅台", "resolved_name": "贵州茅台", "market": "CN", "entity_type": "ticker"},
]


def env_with_anchors(anchors=ANCHORS):
    return SimpleNamespace(entity_anchors=anchors)


class TestVerbatimGate:
    def test_block_level_fallback_span_rejected(self):
        """Fabricated quote → only block_level fallback span → rejected."""
        notes: list[str] = []
        intents = [make_intent(evidence_span_ids=["s1"])]
        spans = [make_span("s1", "整个 block 文本", span_type="block_level")]
        kept, _ = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert kept == []
        assert any("evidence_not_verbatim" in n for n in notes)

    def test_verbatim_span_passes(self):
        notes: list[str] = []
        intents = [make_intent()]
        spans = [make_span("s1", "谷歌基本面看好，值得关注")]
        kept, kept_spans = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert len(kept) == 1 and len(kept_spans) == 1


class TestDirectionConsistency:
    def test_bullish_with_bearish_evidence_rejected(self):
        """The live GOOGL case: bullish intent, quote says 走弱."""
        notes: list[str] = []
        intents = [make_intent(direction="bullish")]
        spans = [make_span("s1", "Google：右走弱了，有点不对劲")]
        kept, _ = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert kept == []
        assert any("direction_conflicts_evidence" in n for n in notes)

    def test_bearish_with_bearish_evidence_passes(self):
        notes: list[str] = []
        intents = [make_intent(direction="bearish")]
        spans = [make_span("s1", "Google：右走弱了，有点不对劲")]
        kept, _ = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert len(kept) == 1

    def test_mixed_direction_exempt(self):
        notes: list[str] = []
        intents = [make_intent(direction="mixed")]
        spans = [make_span("s1", "短期走弱但长期看好")]
        kept, _ = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert len(kept) == 1


class TestAnchorGrounding:
    def test_off_anchor_target_rejected(self):
        """Hallucinated target (not in F2 anchors) → rejected."""
        notes: list[str] = []
        intents = [make_intent(target_name="日经指数", target_symbol="NI225")]
        spans = [make_span("s1", "看好这个机会")]
        kept, _ = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert kept == []
        assert any("target_not_anchored" in n for n in notes)

    def test_name_match_normalizes_symbol(self):
        """LLM invented a symbol but the NAME matches an anchor → symbol fixed."""
        notes: list[str] = []
        intents = [make_intent(target_name="贵州茅台", target_symbol="000510.SZ")]
        spans = [make_span("s1", "贵州茅台值得买入")]
        kept, _ = _validate_llm_intents(intents, spans, env_with_anchors(), notes)
        assert len(kept) == 1
        assert kept[0].target_symbol == "600519.SH"  # normalized to the anchor

    def test_no_anchors_skips_grounding(self):
        """Raw-text path (no F2 anchors) — grounding check is skipped."""
        notes: list[str] = []
        intents = [make_intent(target_name="日经指数", target_symbol="NI225")]
        spans = [make_span("s1", "看好这个机会")]
        kept, _ = _validate_llm_intents(
            intents, spans, SimpleNamespace(entity_anchors=[]), notes
        )
        assert len(kept) == 1
