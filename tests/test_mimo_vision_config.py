"""Tests for MiMo-V2.5 as the canonical F1 vision/OCR provider."""

from __future__ import annotations

from finer.llm.client import LLMClient
from finer.model_config import ModelProvider, VisionModelRegistry, get_vision_registry


def test_vision_registry_only_uses_mimo_v25():
    registry = get_vision_registry()

    assert len(registry.models) == 1
    model = registry.models[0]
    assert model.name == "mimo-v2.5"
    assert model.provider == ModelProvider.MIMO
    assert model.api_key_env == "MIMO_API_KEY"
    assert model.base_url == "https://api.xiaomimimo.com/v1"
    assert model.api_key_header == "api-key"
    assert model.api_key_scheme is None
    assert model.max_tokens_field == "max_completion_tokens"


def test_mimo_base_url_can_use_token_plan_endpoint(monkeypatch):
    monkeypatch.setenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")

    registry = VisionModelRegistry()

    assert registry.models[0].base_url == "https://token-plan-cn.xiaomimimo.com/v1"


def test_llm_client_uses_mimo_headers_and_token_field(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "test-mimo-key")
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "OCR text"}}]}

    class FakeHTTPXClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("finer.llm.client.httpx.Client", FakeHTTPXClient)

    client = LLMClient.from_registry(get_vision_registry())
    assert client is not None

    result = client.chat_with_images(
        text="extract text",
        image_base64="ZmFrZQ==",
        mime_type="image/png",
    )

    assert result == "OCR text"
    assert captured["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert captured["headers"]["api-key"] == "test-mimo-key"
    assert "Authorization" not in captured["headers"]
    assert captured["json"]["model"] == "mimo-v2.5"
    assert captured["json"]["max_completion_tokens"] == 4096
    assert "max_tokens" not in captured["json"]
    content = captured["json"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
