"""Tests for ConsensusIntentExtractor (F3 N-run majority vote).

The MiMo endpoint is non-deterministic at temperature=0 (live 2026-07-05:
4 vs 7 intents on the same envelope; a contradictory pair's winner flipped
direction between runs). Consensus keeps only (target, direction) stances a
majority of valid runs agree on — 宁缺毋假.
"""
from __future__ import annotations

from typing import List

import pytest

from finer.extraction.intent_extractor import (
    ConsensusIntentExtractor,
    IntentExtractionResult,
)
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent


def make_intent(**overrides) -> NormalizedInvestmentIntent:
    base = dict(
        envelope_id="env-1",
        block_ids=["b1"],
        creator_id="k1",
        target_type="stock",
        target_name="腾讯",
        target_symbol="0700.HK",
        market="HK",
        direction="bullish",
        actionability="opinion",
        position_delta_hint="none",
        conviction=0.7,
        confidence=0.8,
        time_horizon_hint="unknown",
        evidence_span_ids=[],
        ambiguity_flags=[],
    )
    base.update(overrides)
    return NormalizedInvestmentIntent(**base)


def make_span(sid: str) -> EvidenceSpan:
    return EvidenceSpan.from_dict(
        {
            "schema_version": "1.0",
            "evidence_span_id": sid,
            "block_id": "b1",
            "char_start": 0,
            "char_end": 4,
            "text": "看好腾讯",
            "confidence": 0.8,
            "span_type": "intent_keyword",
        }
    )


def make_result(
    intents: List[NormalizedInvestmentIntent],
    spans: List[EvidenceSpan] | None = None,
    notes: List[str] | None = None,
) -> IntentExtractionResult:
    return IntentExtractionResult(
        envelope_id="env-1",
        intents=intents,
        evidence_spans=spans or [],
        extractor_version="llm_v1",
        processing_notes=notes or [],
    )


class StubExtractor:
    """Base-extractor stub returning queued results (or raising)."""

    def __init__(self, results):
        self._results = list(results)

    def extract(self, envelope):
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class DummyEnvelope:
    envelope_id = "env-1"


class TestMajorityVote:
    def test_two_of_three_kept_one_of_three_vetoed(self):
        stable = lambda: make_intent()  # 0700.HK bullish in runs 1+2
        noise = make_intent(target_name="小米", target_symbol="1810.HK", direction="bearish")
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([stable()]),
                make_result([stable(), noise]),
                make_result([]),
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        keys = {(i.target_symbol, i.direction) for i in result.intents}
        assert keys == {("0700.HK", "bullish")}
        assert any("consensus vetoed: 1810.HK bearish (1/3" in n for n in result.processing_notes)
        assert any("consensus kept: 0700.HK bullish (2/3" in n for n in result.processing_notes)

    def test_direction_split_vetoes_whole_target(self):
        """GOOGL-style flip: one direction per run, no majority → target gone."""
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent(target_symbol="GOOGL", direction="bullish")]),
                make_result([make_intent(target_symbol="GOOGL", direction="bearish")]),
                make_result([make_intent(target_symbol="GOOGL", direction="neutral")]),
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        assert result.intents == []

    def test_contested_direction_2_to_1_vetoed(self):
        """bullish and bearish BOTH drew votes → a 2:1 majority is a sampling
        coin-flip (live: GOOGL flipped bearish 2/3 → bullish 2/3 between
        consensus rounds). Contested directions need unanimity — both die."""
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent(target_symbol="GOOGL", direction="bearish", conviction=0.6)]),
                make_result([make_intent(target_symbol="GOOGL", direction="bullish", conviction=0.6)]),
                make_result([make_intent(target_symbol="GOOGL", direction="bearish", conviction=0.7)]),
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        assert result.intents == []
        assert any(
            "GOOGL bearish (2/3 runs, contested direction" in n
            for n in result.processing_notes
        )

    def test_contested_unanimous_side_survives(self):
        """Narrated reversal: every run lands bearish, one run also keeps the
        pre-reversal bullish (stance_change). Bearish is unanimous → kept;
        the 1/3 bullish is vetoed."""
        reversal_run = make_result([
            make_intent(target_symbol="GOOGL", direction="bullish", conviction=0.5,
                        ambiguity_flags=["stance_change"]),
            make_intent(target_symbol="GOOGL", direction="bearish", conviction=0.7),
        ])
        ext = ConsensusIntentExtractor(
            StubExtractor([
                reversal_run,
                make_result([make_intent(target_symbol="GOOGL", direction="bearish", conviction=0.7)]),
                make_result([make_intent(target_symbol="GOOGL", direction="bearish", conviction=0.6)]),
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        assert len(result.intents) == 1
        assert result.intents[0].direction == "bearish"

    def test_neutral_vs_bullish_not_contested(self):
        """neutral×bullish isn't a product-breaking contradiction — plain
        majority applies (only strict bullish×bearish triggers unanimity)."""
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent(direction="bullish", conviction=0.7)]),
                make_result([make_intent(direction="bullish", conviction=0.7)]),
                make_result([make_intent(direction="neutral", conviction=0.4)]),
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        assert len(result.intents) == 1
        assert result.intents[0].direction == "bullish"

    def test_winner_is_best_supporter_with_its_spans(self):
        """Representative = highest (confidence, conviction); its evidence
        spans travel with it so the audit chain stays self-consistent."""
        weak = make_intent(conviction=0.6, confidence=0.7, evidence_span_ids=["s-weak"])
        strong = make_intent(conviction=0.7, confidence=0.9, evidence_span_ids=["s-strong"])
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([weak], spans=[make_span("s-weak")]),
                make_result([strong], spans=[make_span("s-strong")]),
            ]),
            runs=2,
        )
        result = ext.extract(DummyEnvelope())
        assert len(result.intents) == 1
        assert result.intents[0].evidence_span_ids == ["s-strong"]
        assert [s.evidence_span_id for s in result.evidence_spans] == ["s-strong"]

    def test_two_valid_runs_require_unanimity(self):
        """threshold = majority of valid runs: with 2 valid runs, 2/2."""
        only_once = make_intent(target_symbol="MU", direction="bullish")
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent(), only_once]),
                make_result([make_intent()]),
            ]),
            runs=2,
        )
        result = ext.extract(DummyEnvelope())
        keys = {(i.target_symbol, i.direction) for i in result.intents}
        assert keys == {("0700.HK", "bullish")}


    def test_one_run_compound_pair_is_one_vote(self):
        """A sanctioned hold+add compound (two intents, same target+direction,
        different hints) inside ONE run must not cast two votes: with no other
        run supporting the stance, 1/3 run-votes < majority → vetoed."""
        compound_run = make_result([
            make_intent(position_delta_hint="hold"),
            make_intent(position_delta_hint="add"),
        ])
        ext = ConsensusIntentExtractor(
            StubExtractor([compound_run, make_result([]), make_result([])]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        assert result.intents == []
        assert any("consensus vetoed: 0700.HK bullish (1/3" in n for n in result.processing_notes)


class TestVoteBase:
    def test_failed_run_retried_to_fill_vote_base(self):
        """A failed LLM call is retried so one dead run doesn't turn 3-run
        majority into 2-run unanimity (live smoke 2026-07-05)."""
        failed = make_result([], notes=["LLM call exception: timeout"])
        mu = make_intent(target_symbol="MU", direction="bullish")
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent(), mu]),
                failed,
                make_result([make_intent()]),
                make_result([make_intent(), mu]),  # retry restores base to 3
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        keys = {(i.target_symbol, i.direction) for i in result.intents}
        # MU has 2/3 run-votes — kept only because the retry restored the base
        assert keys == {("0700.HK", "bullish"), ("MU", "bullish")}

    def test_collapsed_vote_base_raises(self):
        """<2 valid runs → raise so the caller's rule-based fallback engages."""
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent()]),
                make_result([], notes=["LLM returned None (likely API key missing)"]),
                RuntimeError("boom"),
            ]),
            runs=3,
        )
        with pytest.raises(RuntimeError, match="vote base collapsed"):
            ext.extract(DummyEnvelope())

    def test_genuinely_empty_run_is_a_valid_vote(self):
        """An empty result WITHOUT failure markers is a real 'nothing here'
        vote and stays in the base (raising the bar for the others)."""
        ext = ConsensusIntentExtractor(
            StubExtractor([
                make_result([make_intent()]),
                make_result([]),  # honest empty — counts
                make_result([]),
            ]),
            runs=3,
        )
        result = ext.extract(DummyEnvelope())
        assert result.intents == []  # 1/3 < majority(2)

    def test_runs_below_two_rejected(self):
        with pytest.raises(ValueError):
            ConsensusIntentExtractor(StubExtractor([]), runs=1)


class TestResolverWiring:
    def test_llm_mode_defaults_to_consensus(self, monkeypatch):
        from finer.pipeline.canonical_runner import _resolve_intent_extractor

        monkeypatch.setenv("FINER_F3_EXTRACTOR", "llm")
        monkeypatch.delenv("FINER_F3_CONSENSUS_RUNS", raising=False)
        extractor, note = _resolve_intent_extractor()
        assert type(extractor).__name__ == "ConsensusIntentExtractor"
        assert note is None

    def test_consensus_runs_1_opts_out(self, monkeypatch):
        from finer.pipeline.canonical_runner import _resolve_intent_extractor

        monkeypatch.setenv("FINER_F3_EXTRACTOR", "llm")
        monkeypatch.setenv("FINER_F3_CONSENSUS_RUNS", "1")
        extractor, _ = _resolve_intent_extractor()
        assert type(extractor).__name__ == "LLMIntentExtractor"

    def test_garbage_consensus_runs_does_not_kill_llm_mode(self, monkeypatch):
        """int('abc') must not trip the broad except into rule-based."""
        from finer.pipeline.canonical_runner import _resolve_intent_extractor

        monkeypatch.setenv("FINER_F3_EXTRACTOR", "llm")
        monkeypatch.setenv("FINER_F3_CONSENSUS_RUNS", "abc")
        extractor, note = _resolve_intent_extractor()
        assert type(extractor).__name__ == "ConsensusIntentExtractor"
        assert note is None
