"""Tests for F2 LLMEntityProposalAdapter.

These tests use a mock LLM callable only. They must never call a real provider
or require API keys. The deterministic validator is the unit under test: given a
mocked LLM payload, only proposals that pass every hard check become candidates.
"""

from __future__ import annotations

import json

import httpx
import pytest

from finer.enrichment.llm_entity_proposal import (
    CANDIDATE_TYPE,
    LLMEntityProposalAdapter,
    LLMEntityProposalError,
)
from finer.entity_registry import resolve
from finer.llm import DeepSeekClient

# Block text containing verbatim occurrences of: a fictional tradable entity
# (云图机器人), a registered entity (苹果), and a metric token (EPS). The
# hallucinated proposal's evidence quote is deliberately NOT present here.
_BLOCK_TEXT = (
    "今天聊几个标的。云图机器人这家公司订单饱满，EPS 也在改善，估值不算贵。"
    "另外苹果的服务业务继续增长，我还是长期看好。"
)


def _mixed_payload() -> str:
    """One real entity + one hallucination + one existing + one metric noise."""
    return json.dumps(
        {
            "proposals": [
                {
                    "alias": "云图机器人",
                    "suggested_ticker": "300666.SZ",
                    "market": "CN",
                    "entity_type": "ticker",
                    "confidence": 0.82,
                    "evidence_quote": "云图机器人这家公司订单饱满",
                },
                {
                    "alias": "幻影动力",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 0.7,
                    "evidence_quote": "幻影动力宣布上市",  # not in block text
                },
                {
                    "alias": "苹果",
                    "suggested_ticker": "AAPL",
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.9,
                    "evidence_quote": "苹果的服务业务继续增长",  # already registered
                },
                {
                    "alias": "EPS",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 0.6,
                    "evidence_quote": "EPS 也在改善",  # stoplisted metric token
                },
            ],
            "reasoning_summary": "Mixed batch for validator gates.",
        },
        ensure_ascii=False,
    )


def _propose(payload_str: str):
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload_str)
    return adapter.propose_for_block(
        text=_BLOCK_TEXT,
        block_id="block_001",
        source_record_id="local_test",
        raw_path="data/raw/test/x.png",
        reason="zero_anchor",
    )


def test_validator_passes_only_the_real_entity():
    # Precondition: the fictional entity is not (yet) in the registry, the
    # registered one is. If 云图机器人 is ever added to ENTITY_REGISTRY, rename it
    # here (see task card §6 fixture-coupling trap).
    assert resolve("云图机器人") is None
    assert resolve("苹果") is not None

    candidates = _propose(_mixed_payload())

    assert len(candidates) == 1
    only = candidates[0]
    assert only["alias_candidate"] == "云图机器人"
    assert only["candidate_type"] == CANDIDATE_TYPE
    assert only["suggested_ticker"] == "300666.SZ"
    assert only["suggested_market"] == "CN"
    assert only["score"] == 0.82


def test_candidate_aligns_gap_review_contract():
    candidates = _propose(_mixed_payload())
    row = candidates[0]
    # First 8 fields of GAP_CANDIDATE_REVIEW_FIELDS must be present and typed.
    for field in (
        "alias_candidate",
        "source_record_id",
        "block_id",
        "raw_path",
        "context_snippet",
        "reason",
        "candidate_type",
        "score",
    ):
        assert field in row
    assert row["source_record_id"] == "local_test"
    assert row["block_id"] == "block_001"
    assert row["reason"] == "zero_anchor"
    assert "云图机器人" in row["context_snippet"]
    assert isinstance(row["score"], float)


def test_rejects_hallucinated_alias_not_in_text():
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "幻影动力",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 0.9,
                    "evidence_quote": "幻影动力宣布上市",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    assert _propose(payload) == []


def test_rejects_alias_not_inside_its_own_evidence():
    # Alias is in the block text, but the evidence quote does not contain it.
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "云图机器人",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 0.9,
                    "evidence_quote": "估值不算贵",  # in text but lacks the alias
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    assert _propose(payload) == []


def test_rejects_existing_registry_entity():
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "苹果",
                    "suggested_ticker": "AAPL",
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.95,
                    "evidence_quote": "苹果的服务业务继续增长",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    assert _propose(payload) == []


def test_rejects_stoplisted_metric_token():
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "EPS",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 0.8,
                    "evidence_quote": "EPS 也在改善",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    assert _propose(payload) == []


def test_blanks_malformed_ticker_but_keeps_alias():
    text = "蓝海科技这家公司值得关注，基本面扎实。"
    assert resolve("蓝海科技") is None
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "蓝海科技",
                    "suggested_ticker": "ABCDEFG",  # >5 letters, malformed
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.75,
                    "evidence_quote": "蓝海科技这家公司值得关注",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload)
    candidates = adapter.propose_for_block(text=text, block_id="b1")
    assert len(candidates) == 1
    assert candidates[0]["alias_candidate"] == "蓝海科技"
    assert candidates[0]["suggested_ticker"] == ""  # blanked, manual fill


def test_ticker_suffix_overrides_mismatched_market():
    text = "飞驰动力今天大涨，港股表现强势。"
    assert resolve("飞驰动力") is None
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "飞驰动力",
                    "suggested_ticker": "1810.HK",
                    "market": "US",  # wrong; suffix says HK
                    "entity_type": "ticker",
                    "confidence": 0.8,
                    "evidence_quote": "飞驰动力今天大涨",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload)
    candidates = adapter.propose_for_block(text=text, block_id="b1")
    assert candidates[0]["suggested_ticker"] == "1810.HK"
    assert candidates[0]["suggested_market"] == "HK"


def test_finance_skills_validator_blanks_fake_ticker():
    text = "新潮能源被点名，资金关注度上升。"
    assert resolve("新潮能源") is None
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "新潮能源",
                    "suggested_ticker": "XY",  # well-formed but (per stub) fake
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.7,
                    "evidence_quote": "新潮能源被点名",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(
        llm_fn=lambda messages: payload,
        finance_skills_validator=lambda ticker, market: False,
    )
    candidates = adapter.propose_for_block(text=text, block_id="b1")
    assert len(candidates) == 1
    assert candidates[0]["alias_candidate"] == "新潮能源"
    assert candidates[0]["suggested_ticker"] == ""


def test_accepts_integer_confidence():
    """schema is extra=forbid but NOT strict, so int confidence is coerced."""
    text = "晨曦半导体获得新订单。"
    assert resolve("晨曦半导体") is None
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "晨曦半导体",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 1,  # int, not float
                    "evidence_quote": "晨曦半导体获得新订单",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload)
    candidates = adapter.propose_for_block(text=text, block_id="b1")
    assert len(candidates) == 1
    assert candidates[0]["score"] == 0.95  # capped


def test_rejects_extra_fields_in_proposal():
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "云图机器人",
                    "suggested_ticker": "",
                    "market": "",
                    "entity_type": "ticker",
                    "confidence": 0.8,
                    "evidence_quote": "云图机器人这家公司订单饱满",
                    "direction": "bullish",  # forbidden extra field
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    with pytest.raises(LLMEntityProposalError):
        _propose(payload)


def test_empty_text_returns_empty_without_llm_call():
    called = {"n": 0}

    def mock_llm(messages):
        called["n"] += 1
        return "{}"

    adapter = LLMEntityProposalAdapter(llm_fn=mock_llm)
    assert adapter.propose_for_block(text="   ", block_id="b1") == []
    assert called["n"] == 0


def test_messages_include_constrained_contract():
    captured = {}

    def mock_llm(messages):
        captured["messages"] = messages
        return _mixed_payload()

    LLMEntityProposalAdapter(llm_fn=mock_llm).propose_for_block(
        text=_BLOCK_TEXT, block_id="b1"
    )

    system = captured["messages"][0]["content"]
    user = json.loads(captured["messages"][1]["content"])
    assert "tradable" in system
    assert "Return JSON only" in system
    assert user["task"] == "F2 entity candidate proposal"
    assert user["block_text"] == _BLOCK_TEXT
    assert "US" in user["allowed_markets"]


def test_invalid_json_raises():
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: "not json at all")
    with pytest.raises(LLMEntityProposalError):
        adapter.propose_for_block(text=_BLOCK_TEXT, block_id="b1")


def test_adapter_detects_deepseek_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-token")
    assert LLMEntityProposalAdapter().is_configured() is True


def test_adapter_requires_deepseek_env_when_no_mock(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert LLMEntityProposalAdapter().is_configured() is False


def test_adapter_requests_deepseek_json_mode_from_client():
    """F2 must use DeepSeek JSON Output through DeepSeekClient."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-pro",
                "choices": [{"message": {"content": _mixed_payload()}}],
                "usage": {"total_tokens": 42},
            },
        )

    client = DeepSeekClient(
        api_key="test-token",
        transport=httpx.MockTransport(handler),
        retry_base_delay=0,
    )
    adapter = LLMEntityProposalAdapter(deepseek_client=client)
    candidates = adapter.propose_for_block(text=_BLOCK_TEXT, block_id="b1")

    assert [c["alias_candidate"] for c in candidates] == ["云图机器人"]
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["max_tokens"] == 8192
    assert captured["payload"]["thinking"] == {"type": "enabled"}
    assert captured["payload"]["reasoning_effort"] == "high"


def test_rejects_sector_theme_term():
    """Sector/theme 泛称 (a basket, not one instrument) is rejected."""
    text = "今天券商板块大涨，资金明显涌入。"
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "券商",
                    "suggested_ticker": "",
                    "market": "CN",
                    "entity_type": "sector",
                    "confidence": 0.7,
                    "evidence_quote": "今天券商板块大涨",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload)
    assert adapter.propose_for_block(text=text, block_id="b1") == []


def test_dedups_case_insensitive_registry():
    """Case variants of registered tickers (Nvidia/tsla) are de-duped."""
    assert resolve("NVIDIA") is not None and resolve("TSLA") is not None
    text = "Nvidia 和 tsla 今天都涨了。"
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "Nvidia",
                    "suggested_ticker": "NVDA",
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.95,
                    "evidence_quote": "Nvidia 和 tsla 今天都涨了",
                },
                {
                    "alias": "tsla",
                    "suggested_ticker": "TSLA",
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.9,
                    "evidence_quote": "Nvidia 和 tsla 今天都涨了",
                },
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload)
    assert adapter.propose_for_block(text=text, block_id="b1") == []


def test_real_name_containing_sector_word_survives():
    """Exact-match sector stoplist must not kill names containing the word
    (云图证券 != 证券). Fictional alias to avoid the registry fixture trap."""
    text = "云图证券今天放量上涨，资金关注度上升。"
    assert resolve("云图证券") is None
    payload = json.dumps(
        {
            "proposals": [
                {
                    "alias": "云图证券",
                    "suggested_ticker": "6178.HK",
                    "market": "HK",
                    "entity_type": "ticker",
                    "confidence": 0.85,
                    "evidence_quote": "云图证券今天放量上涨",
                }
            ],
            "reasoning_summary": "",
        },
        ensure_ascii=False,
    )
    adapter = LLMEntityProposalAdapter(llm_fn=lambda messages: payload)
    cands = adapter.propose_for_block(text=text, block_id="b1")
    assert [c["alias_candidate"] for c in cands] == ["云图证券"]
