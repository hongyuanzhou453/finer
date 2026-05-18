"""Tests for ModelRouter — task-type-based LLM routing with fallback."""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from finer.model_config import (
    BaseModelRegistry,
    ModelConfig,
    ModelProvider,
    ReasoningModelRegistry,
    TextModelRegistry,
    VisionModelRegistry,
    get_reasoning_registry,
)
from finer.llm.router import ModelRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_text_registry() -> BaseModelRegistry:
    """A text registry with one fake model."""
    return TextModelRegistry(
        models=[
            ModelConfig(
                name="test-text-model",
                provider=ModelProvider.DEEPSEEK,
                api_key_env="TEST_TEXT_API_KEY",
                base_url="https://test.example.com/v1",
                max_tokens=4096,
                priority=0,
            ),
        ]
    )


@pytest.fixture()
def mock_reasoning_registry() -> BaseModelRegistry:
    """A reasoning registry with one fake model."""
    return ReasoningModelRegistry(
        models=[
            ModelConfig(
                name="test-reasoning-model",
                provider=ModelProvider.MIMO,
                api_key_env="TEST_REASONING_API_KEY",
                base_url="https://test-reasoning.example.com/v1",
                max_tokens=8192,
                priority=0,
                api_key_header="api-key",
                api_key_scheme=None,
                max_tokens_field="max_completion_tokens",
            ),
        ]
    )


@pytest.fixture()
def router(
    mock_text_registry: BaseModelRegistry,
    mock_reasoning_registry: BaseModelRegistry,
) -> ModelRouter:
    """A ModelRouter with mocked registries."""
    return ModelRouter(
        text_registry=mock_text_registry,
        reasoning_registry=mock_reasoning_registry,
    )


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestModelRouterInit:
    def test_init_with_explicit_registries(self, mock_text_registry):
        router = ModelRouter(text_registry=mock_text_registry)
        assert "text" in router._registries

    def test_init_empty_uses_lazy_registries(self):
        router = ModelRouter()
        # Should not raise on init — registries are lazy
        assert len(router._registries) == 0

    def test_unknown_task_type_raises(self):
        router = ModelRouter()
        with pytest.raises(ValueError, match="Unknown task_type"):
            router._get_registry("unknown_type")


# ---------------------------------------------------------------------------
# call() tests
# ---------------------------------------------------------------------------


class TestModelRouterCall:
    @patch("finer.llm.router.LLMClient")
    def test_call_text_returns_response(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = "Hello from model"
        MockLLMClient.from_registry.return_value = mock_client

        result = router.call("test prompt", task_type="text")
        assert result == "Hello from model"
        mock_client.chat.assert_called_once()

    @patch("finer.llm.router.LLMClient")
    def test_call_with_system_prompt(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = "response"
        MockLLMClient.from_registry.return_value = mock_client

        router.call("test", task_type="text", system_prompt="You are helpful")
        call_args = mock_client.chat.call_args
        messages = call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful"
        assert messages[1]["role"] == "user"

    @patch("finer.llm.router.LLMClient")
    def test_call_no_system_prompt(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = "response"
        MockLLMClient.from_registry.return_value = mock_client

        router.call("test", task_type="text")
        call_args = mock_client.chat.call_args
        messages = call_args[0][0]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @patch("finer.llm.router.LLMClient")
    def test_call_returns_none_when_no_client(self, MockLLMClient, router):
        MockLLMClient.from_registry.return_value = None
        result = router.call("test", task_type="text")
        assert result is None

    @patch("finer.llm.router.LLMClient")
    def test_call_reasoning_uses_reasoning_registry(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = "reasoning result"
        MockLLMClient.from_registry.return_value = mock_client

        result = router.call("complex task", task_type="reasoning")
        assert result == "reasoning result"
        # Verify from_registry was called with the reasoning registry
        MockLLMClient.from_registry.assert_called_once()
        registry_arg = MockLLMClient.from_registry.call_args[0][0]
        assert isinstance(registry_arg, ReasoningModelRegistry)


# ---------------------------------------------------------------------------
# call_json() tests
# ---------------------------------------------------------------------------


class TestModelRouterCallJson:
    @patch("finer.llm.router.LLMClient")
    def test_call_json_parses_valid_json(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = '{"key": "value"}'
        MockLLMClient.from_registry.return_value = mock_client

        result = router.call_json("extract data", task_type="text")
        assert result == {"key": "value"}

    @patch("finer.llm.router.LLMClient")
    def test_call_json_strips_markdown_fences(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = '```json\n{"key": "value"}\n```'
        MockLLMClient.from_registry.return_value = mock_client

        result = router.call_json("extract data", task_type="text")
        assert result == {"key": "value"}

    @patch("finer.llm.router.LLMClient")
    def test_call_json_returns_none_on_invalid_json(self, MockLLMClient, router):
        mock_client = MagicMock()
        mock_client.chat.return_value = "not json at all"
        MockLLMClient.from_registry.return_value = mock_client

        result = router.call_json("extract data", task_type="text")
        assert result is None

    @patch("finer.llm.router.LLMClient")
    def test_call_json_with_response_model(self, MockLLMClient, router):
        from pydantic import BaseModel

        class MyModel(BaseModel):
            name: str
            value: int

        mock_client = MagicMock()
        mock_client.chat.return_value = '{"name": "test", "value": 42}'
        MockLLMClient.from_registry.return_value = mock_client

        result = router.call_json("extract", response_model=MyModel, task_type="text")
        assert result == {"name": "test", "value": 42}

    @patch("finer.llm.router.LLMClient")
    def test_call_json_returns_none_when_no_response(self, MockLLMClient, router):
        MockLLMClient.from_registry.return_value = None
        result = router.call_json("test", task_type="text")
        assert result is None


# ---------------------------------------------------------------------------
# ReasoningModelRegistry tests
# ---------------------------------------------------------------------------


class TestReasoningModelRegistry:
    def test_default_model_is_mimo_v25_pro(self):
        registry = ReasoningModelRegistry()
        assert len(registry.models) == 1
        assert registry.models[0].name == "mimo-v2.5-pro"

    def test_default_base_url(self):
        registry = ReasoningModelRegistry()
        assert registry.models[0].base_url == "https://token-plan-cn.xiaomimimo.com/v1"

    def test_auth_header_is_api_key(self):
        registry = ReasoningModelRegistry()
        assert registry.models[0].api_key_header == "api-key"
        assert registry.models[0].api_key_scheme is None

    def test_max_tokens_field(self):
        registry = ReasoningModelRegistry()
        assert registry.models[0].max_tokens_field == "max_completion_tokens"

    def test_get_reasoning_registry_singleton(self):
        r1 = get_reasoning_registry()
        r2 = get_reasoning_registry()
        assert r1 is r2
