"""Tests for F3 extractor injection + LLM→rule fallback in canonical_runner."""
from __future__ import annotations

from finer.extraction.intent_extractor import (
    IntentExtractionResult,
    RuleBasedIntentExtractor,
)
from finer.pipeline.canonical_runner import (
    _extract_with_fallback,
    _resolve_intent_extractor,
)
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.quality import QualityCard


def make_quality_card() -> QualityCard:
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.8,
        financial_relevance_score=0.9,
        entity_resolution_score=0.8,
        temporal_resolution_score=0.7,
        evidence_traceability_score=0.8,
    )


def make_envelope(text: str = "贵州茅台基本面扎实，建议买入，看多后市。") -> ContentEnvelope:
    return ContentEnvelope(
        envelope_id="env-inject-test",
        source_type="feishu_doc",
        source_title="t",
        quality_card=make_quality_card(),
        blocks=[
            ContentBlock(
                block_type="paragraph",
                text=text,
                order=0,
                quality_card=make_quality_card(),
            )
        ],
    )


class FakeExtractor:
    """Stands in for LLMIntentExtractor (non-rule-based type)."""

    def __init__(self, result=None, raises: bool = False):
        self._result = result
        self._raises = raises
        self.calls = 0

    def extract(self, envelope):
        self.calls += 1
        if self._raises:
            raise RuntimeError("simulated LLM failure")
        return self._result


class TestResolve:
    def test_explicit_injection_wins(self, monkeypatch):
        monkeypatch.setenv("FINER_F3_EXTRACTOR", "llm")
        fake = FakeExtractor()
        extractor, note = _resolve_intent_extractor(fake)
        assert extractor is fake and note is None

    def test_default_is_rule_based(self, monkeypatch):
        monkeypatch.delenv("FINER_F3_EXTRACTOR", raising=False)
        extractor, note = _resolve_intent_extractor()
        assert isinstance(extractor, RuleBasedIntentExtractor)
        assert note is None

    def test_llm_env_with_broken_construction_falls_back(self, monkeypatch):
        monkeypatch.setenv("FINER_F3_EXTRACTOR", "llm")

        # break LLM construction deterministically
        import finer.llm.router as router_mod

        def boom(*a, **k):
            raise RuntimeError("no api key")

        monkeypatch.setattr(router_mod, "ModelRouter", boom)
        extractor, note = _resolve_intent_extractor()
        assert isinstance(extractor, RuleBasedIntentExtractor)
        assert note and "fell back to rule-based" in note


class TestFallback:
    def test_primary_exception_degrades_to_rule_based(self):
        env = make_envelope()
        result = _extract_with_fallback(FakeExtractor(raises=True), env)
        assert result is not None
        assert any("fell back from FakeExtractor" in n for n in result.processing_notes)
        # the rule-based baseline actually finds the茅台 intent
        assert any(i.target_symbol == "600519.SH" for i in result.intents)

    def test_non_rule_empty_result_degrades(self):
        env = make_envelope()
        empty = IntentExtractionResult(
            envelope_id=env.envelope_id,
            intents=[],
            evidence_spans=[],
            extractor_version="llm_v1",
            processing_notes=["LLM returned None"],
        )
        result = _extract_with_fallback(FakeExtractor(result=empty), env)
        assert any(i.target_symbol == "600519.SH" for i in result.intents)

    def test_rule_based_empty_stays_empty(self):
        """A signal-free document is legitimately empty — no fallback loop."""
        env = make_envelope(text="今天天气不错，聊聊生活。")
        result = _extract_with_fallback(RuleBasedIntentExtractor(), env)
        assert result is not None
        assert result.intents == []

    def test_successful_primary_used_as_is(self):
        env = make_envelope()
        canned = RuleBasedIntentExtractor().extract(env)
        fake = FakeExtractor(result=canned)
        result = _extract_with_fallback(fake, env)
        assert result is canned
        assert fake.calls == 1
