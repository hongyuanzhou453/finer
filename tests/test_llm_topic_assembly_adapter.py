"""Tests for F1.5 LLMTopicAssemblyAdapter.

These tests use a mock LLM callable only.  They must never call a real
provider or require API keys.
"""

from __future__ import annotations

import json

import httpx
import pytest

from finer.llm import DeepSeekClient
from finer.parsing.llm_topic_assembly_adapter import (
    LLMTopicAssemblyAdapter,
    LLMTopicAssemblyError,
)
from finer.parsing.topic_assembler import TopicAssembler
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.quality import QualityCard


def _quality() -> QualityCard:
    return QualityCard.create_default(overall=0.8)


def _block(block_id: str, order: int, text: str) -> ContentBlock:
    return ContentBlock(
        block_id=block_id,
        block_type="chat_message",
        text=text,
        order=order,
        quality_card=_quality(),
        metadata={"timestamp": f"2026-04-29T09:{order:02d}:00+08:00"},
    )


def _envelope() -> ContentEnvelope:
    return ContentEnvelope(
        envelope_id="env_llm_topic_test",
        source_type="chat",
        blocks=[
            _block("b1", 0, "先说福寿园，现金流很好，但是四月财报不及预期。"),
            _block("b2", 1, "补充一下福寿园的风险，客单价增长开始放缓。"),
            _block("b3", 2, "换个话题，光模块这周资金明显回流。"),
            _block("b4", 3, "中际旭创和新易盛都在光模块链条里，但位置不同。"),
            _block("b5", 4, "今天先聊这些，晚点再看。"),
        ],
        quality_card=_quality(),
    )


def _mock_llm_payload() -> str:
    return json.dumps(
        {
            "topic_blocks": [
                {
                    "topic_title": "福寿园财报与风险补充",
                    "topic_type": "single_stock",
                    "source_block_ids": ["b1", "b2"],
                    "primary_entity_ids": ["福寿园"],
                    "summary": "讨论福寿园现金流、财报不及预期和客单价放缓。",
                    "segmentation_reason": "same entity and continuation marker",
                    "confidence": 0.91,
                    "ambiguity_flags": [],
                },
                {
                    "topic_title": "光模块资金回流与个股讨论",
                    "topic_type": "industry",
                    "source_block_ids": ["b3", "b4"],
                    "primary_entity_ids": ["光模块"],
                    "secondary_entity_ids": ["中际旭创", "新易盛"],
                    "summary": "讨论光模块资金回流及链条内个股。",
                    "segmentation_reason": "industry topic shift followed by related stocks",
                    "confidence": 0.88,
                    "ambiguity_flags": ["mixed_single_stock_and_industry"],
                },
            ],
            "unassigned_block_ids": ["b5"],
            "reasoning_summary": "Grouped by entity and topic shift markers.",
            "confidence": 0.89,
        },
        ensure_ascii=False,
    )


def test_llm_adapter_builds_topic_assembly_result_from_mock_response():
    adapter = LLMTopicAssemblyAdapter(llm_fn=lambda messages: _mock_llm_payload())

    result = adapter.assemble(_envelope())

    assert result.assembly_strategy == "llm_constrained_deepseek_v1"
    assert len(result.topic_blocks) == 2
    assert result.topic_blocks[0].source_block_ids == ["b1", "b2"]
    assert result.topic_blocks[0].raw_text == (
        "先说福寿园，现金流很好，但是四月财报不及预期。\n\n"
        "补充一下福寿园的风险，客单价增长开始放缓。"
    )
    assert result.topic_blocks[1].topic_type == "industry"
    assert result.unassigned_block_ids == ["b5"]


def test_llm_adapter_rejects_fabricated_block_ids():
    payload = json.loads(_mock_llm_payload())
    payload["topic_blocks"][0]["source_block_ids"].append("fabricated")
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: json.dumps(payload, ensure_ascii=False)
    )

    with pytest.raises(LLMTopicAssemblyError, match="fabricated"):
        adapter.assemble(_envelope())


def test_llm_adapter_rejects_missing_block_coverage():
    payload = json.loads(_mock_llm_payload())
    payload["unassigned_block_ids"] = []
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: json.dumps(payload, ensure_ascii=False)
    )

    with pytest.raises(LLMTopicAssemblyError, match="omitted"):
        adapter.assemble(_envelope())


def test_llm_adapter_rejects_duplicate_block_assignment():
    payload = json.loads(_mock_llm_payload())
    payload["unassigned_block_ids"] = ["b4", "b5"]
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: json.dumps(payload, ensure_ascii=False)
    )

    with pytest.raises(LLMTopicAssemblyError, match="duplicated"):
        adapter.assemble(_envelope())


def test_llm_adapter_rejects_forbidden_f3_or_f5_fields():
    payload = json.loads(_mock_llm_payload())
    payload["topic_blocks"][0]["direction"] = "bullish"
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: json.dumps(payload, ensure_ascii=False)
    )

    with pytest.raises(LLMTopicAssemblyError, match="Forbidden F1.5 field"):
        adapter.assemble(_envelope())


def test_topic_assembler_can_route_to_llm_adapter():
    adapter = LLMTopicAssemblyAdapter(llm_fn=lambda messages: _mock_llm_payload())
    assembler = TopicAssembler(use_llm=True, llm_adapter=adapter)

    result = assembler.assemble(_envelope())

    assert result.assembly_strategy == "llm_constrained_deepseek_v1"
    assert [tb.topic_title for tb in result.topic_blocks] == [
        "福寿园财报与风险补充",
        "光模块资金回流与个股讨论",
    ]


def test_llm_messages_include_deepseek_constrained_contract():
    captured = {}

    def mock_llm(messages):
        captured["messages"] = messages
        return _mock_llm_payload()

    LLMTopicAssemblyAdapter(llm_fn=mock_llm).assemble(_envelope())

    system = captured["messages"][0]["content"]
    user = json.loads(captured["messages"][1]["content"])
    assert "Do not infer investment intent" in system
    assert "TradeAction" in system
    assert user["task"] == "F1.5 topic assembly"
    assert {b["block_id"] for b in user["blocks"]} == {"b1", "b2", "b3", "b4", "b5"}


def test_adapter_detects_deepseek_env(monkeypatch):
    """DeepSeek env vars are accepted without exposing values."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-token")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    assert LLMTopicAssemblyAdapter().is_configured() is True


def test_adapter_requires_deepseek_env_when_no_mock(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    assert LLMTopicAssemblyAdapter().is_configured() is False


def test_adapter_requests_deepseek_json_mode_from_client():
    """F1.5 must use DeepSeek JSON Output through DeepSeekClient."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "message": {
                            "content": _mock_llm_payload(),
                            "reasoning_content": "hidden",
                        }
                    }
                ],
                "usage": {"total_tokens": 123},
            },
        )

    client = DeepSeekClient(
        api_key="test-token",
        transport=httpx.MockTransport(handler),
        retry_base_delay=0,
    )
    adapter = LLMTopicAssemblyAdapter(deepseek_client=client)
    result = adapter.assemble(_envelope())

    assert result.topic_blocks
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["max_tokens"] == 8192
    assert captured["payload"]["thinking"] == {"type": "enabled"}
    assert captured["payload"]["reasoning_effort"] == "high"
    assert "temperature" not in captured["payload"]


def test_deepseek_client_retries_retryable_errors():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-pro",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {},
            },
        )

    client = DeepSeekClient(
        api_key="test-token",
        transport=httpx.MockTransport(handler),
        retry_base_delay=0,
    )

    assert client.chat_json([{"role": "user", "content": "json"}]) == {"ok": True}
    assert calls["count"] == 2
