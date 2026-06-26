"""Tests for the F2 constrained-LLM proposal wiring in backfill_f2_anchor.

These tests inject a fake adapter via ``set_llm_proposal_adapter`` and never call
a real LLM. They verify the opt-in switch, per-block caching, the block cap, and
clean-skip behaviour — i.e. that the wiring cannot silently burn tokens.
"""

from __future__ import annotations

import pytest

from scripts.backfill_f2_anchor import (
    LLMEntityProposalError,
    _gap_candidates_for_block,
    set_llm_proposal_adapter,
)

# Neutral text: the rule paths (upper-token / cn-cue) find nothing here, so any
# candidate that appears must have come from the LLM path.
_NEUTRAL_TEXT = "今天先随便聊聊，没什么特别的。"


class _Item:
    content_id = "local_x"
    raw_path = "data/raw/x.png"


def _llm_candidate(alias: str = "云图机器人") -> dict:
    return {
        "alias_candidate": alias,
        "source_record_id": "local_x",
        "block_id": "b1",
        "raw_path": "data/raw/x.png",
        "context_snippet": alias,
        "reason": "zero_anchor",
        "candidate_type": "llm_entity_proposal",
        "score": 0.82,
        "suggested_ticker": "300666.SZ",
        "suggested_market": "CN",
    }


class _FakeAdapter:
    def __init__(self, candidates: list[dict], *, configured: bool = True) -> None:
        self._candidates = candidates
        self._configured = configured
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def propose_for_block(self, **kwargs) -> list[dict]:
        self.calls += 1
        return [dict(c) for c in self._candidates]


@pytest.fixture(autouse=True)
def _reset_adapter():
    yield
    set_llm_proposal_adapter(None)


def _block(block_id: str = "b1") -> dict:
    return {"block_id": block_id, "text": _NEUTRAL_TEXT}


def test_llm_path_off_by_default_keeps_diagnostics_rule_only():
    fake = _FakeAdapter([_llm_candidate()])
    set_llm_proposal_adapter(fake)
    # include_llm defaults False (the diagnostic call site) -> no LLM, no call.
    out = _gap_candidates_for_block(_Item(), _block(), reason="zero_anchor")
    assert out == []
    assert fake.calls == 0


def test_llm_path_adds_candidates_when_enabled():
    fake = _FakeAdapter([_llm_candidate()])
    set_llm_proposal_adapter(fake)
    out = _gap_candidates_for_block(
        _Item(), _block(), reason="zero_anchor", include_llm=True
    )
    assert [c["alias_candidate"] for c in out] == ["云图机器人"]
    assert out[0]["candidate_type"] == "llm_entity_proposal"
    assert fake.calls == 1


def test_llm_results_cached_per_block():
    fake = _FakeAdapter([_llm_candidate()])
    set_llm_proposal_adapter(fake)
    item, block = _Item(), _block()
    _gap_candidates_for_block(item, block, reason="zero_anchor", include_llm=True)
    _gap_candidates_for_block(item, block, reason="zero_anchor", include_llm=True)
    assert fake.calls == 1  # second pass hits the cache (build_gap_report runs twice)


def test_llm_max_blocks_cap_stops_spending():
    fake = _FakeAdapter([_llm_candidate()])
    set_llm_proposal_adapter(fake, max_blocks=1)
    _gap_candidates_for_block(
        _Item(), _block("b1"), reason="zero_anchor", include_llm=True
    )
    over_cap = _gap_candidates_for_block(
        _Item(), _block("b2"), reason="zero_anchor", include_llm=True
    )
    assert fake.calls == 1
    assert over_cap == []


def test_llm_skipped_when_adapter_not_configured():
    fake = _FakeAdapter([_llm_candidate()], configured=False)
    set_llm_proposal_adapter(fake)
    out = _gap_candidates_for_block(
        _Item(), _block(), reason="zero_anchor", include_llm=True
    )
    assert out == []
    assert fake.calls == 0


def test_set_none_disables_path():
    set_llm_proposal_adapter(None)
    out = _gap_candidates_for_block(
        _Item(), _block(), reason="zero_anchor", include_llm=True
    )
    assert out == []


def test_llm_error_is_swallowed_per_block():
    class _BoomAdapter:
        def is_configured(self) -> bool:
            return True

        def propose_for_block(self, **kwargs):
            raise LLMEntityProposalError("boom")

    set_llm_proposal_adapter(_BoomAdapter())
    out = _gap_candidates_for_block(
        _Item(), _block(), reason="zero_anchor", include_llm=True
    )
    assert out == []  # error swallowed; backfill does not crash on one bad block


def test_llm_candidate_deduped_against_rule_alias():
    # If the LLM proposes an alias the rule path already produced, it is not
    # duplicated. 云图出行 is fictional (cue 出行, not in registry) per the
    # fixture-decoupling convention.
    text = "云图出行值得关注。"
    block = {"block_id": "b1", "text": text}
    # Precondition: the cn-cue rule path already yields 云图出行 on its own.
    set_llm_proposal_adapter(None)
    rule_only = _gap_candidates_for_block(_Item(), block, reason="zero_anchor")
    assert "云图出行" in [c["alias_candidate"] for c in rule_only]
    # With the LLM proposing the same alias, it is not duplicated.
    set_llm_proposal_adapter(_FakeAdapter([_llm_candidate(alias="云图出行")]))
    out = _gap_candidates_for_block(
        _Item(), block, reason="zero_anchor", include_llm=True
    )
    assert [c["alias_candidate"] for c in out].count("云图出行") == 1
