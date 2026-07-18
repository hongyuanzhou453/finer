"""Tests for model registry failure cooldown and MiMo endpoint resolution.

Covers:
- mark_failed() is cooldown-based (FINER_MODEL_FAIL_COOLDOWN, default 120s),
  not a permanent poison on the module-level registry singletons.
- Direct ``name in registry.failed_models`` membership checks (the
  ingestion/vision_utils.py pattern) also honor the cooldown.
- LLMClient.from_registry() recovers after the cooldown elapses.
- Vision base_url resolution: MIMO_VISION_BASE_URL > MIMO_BASE_URL >
  key-prefix default (tp- keys → token-plan host).
- Text registry warns on the known DeepSeek-key→MiMo-endpoint misroute.

No test sleeps: the time source finer.model_config._monotonic_now is
monkeypatched with a fake clock. No real LLM API is ever called.
"""

from __future__ import annotations

import logging

import pytest

import finer.model_config as model_config
from finer.llm.client import LLMClient
from finer.model_config import (
    BaseModelRegistry,
    ModelConfig,
    ModelProvider,
    TextModelRegistry,
    VisionModelRegistry,
)


class FakeClock:
    """Deterministic replacement for time.monotonic()."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(model_config, "_monotonic_now", fake)
    return fake


def make_registry() -> BaseModelRegistry:
    return BaseModelRegistry(
        models=[
            ModelConfig(
                name="m1",
                provider=ModelProvider.MIMO,
                api_key_env="TEST_COOLDOWN_API_KEY",
                base_url="https://example.test/v1",
            ),
        ]
    )


@pytest.fixture()
def registry(monkeypatch: pytest.MonkeyPatch) -> BaseModelRegistry:
    monkeypatch.setenv("TEST_COOLDOWN_API_KEY", "dummy-value-for-tests")
    monkeypatch.delenv("FINER_MODEL_FAIL_COOLDOWN", raising=False)
    return make_registry()


# ---------------------------------------------------------------------------
# Cooldown semantics
# ---------------------------------------------------------------------------


def test_mark_failed_blocks_within_default_cooldown(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    assert registry.get_available_model() is not None

    registry.mark_failed("m1", "429 rate limited")
    assert registry.get_available_model() is None

    clock.advance(119.0)
    assert registry.get_available_model() is None


def test_failure_expires_after_default_cooldown(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    registry.mark_failed("m1", "429 rate limited")
    clock.advance(120.0)

    model = registry.get_available_model()
    assert model is not None
    assert model.name == "m1"
    # Expired entry is pruned, not just ignored.
    assert "m1" not in registry.failed_models


def test_env_cooldown_shorter_window(
    registry: BaseModelRegistry, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINER_MODEL_FAIL_COOLDOWN", "10")
    registry.mark_failed("m1", "quota exhausted")

    clock.advance(9.0)
    assert registry.get_available_model() is None

    clock.advance(1.0)
    assert registry.get_available_model() is not None


def test_env_cooldown_longer_window(
    registry: BaseModelRegistry, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINER_MODEL_FAIL_COOLDOWN", "1000")
    registry.mark_failed("m1", "quota exhausted")

    clock.advance(130.0)
    assert registry.get_available_model() is None

    clock.advance(870.0)
    assert registry.get_available_model() is not None


def test_invalid_cooldown_env_falls_back_to_default(
    registry: BaseModelRegistry, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINER_MODEL_FAIL_COOLDOWN", "not-a-number")
    registry.mark_failed("m1", "429")

    clock.advance(119.0)
    assert registry.get_available_model() is None

    clock.advance(1.0)
    assert registry.get_available_model() is not None


def test_direct_membership_check_honors_cooldown(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    """ingestion/vision_utils.py checks failed_models membership directly."""
    registry.mark_failed("m1", "429")
    assert "m1" in registry.failed_models

    clock.advance(120.0)
    assert "m1" not in registry.failed_models


def test_error_message_value_semantics_preserved(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    registry.mark_failed("m1", "429 too many requests")
    assert registry.failed_models["m1"] == "429 too many requests"


def test_reset_failures_lifts_mark_immediately(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    registry.mark_failed("m1", "429")
    registry.reset_failures()
    # No time advance needed.
    assert registry.get_available_model() is not None
    assert len(registry.failed_models) == 0


def test_remark_refreshes_cooldown_window(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    registry.mark_failed("m1", "429 first")
    clock.advance(100.0)
    registry.mark_failed("m1", "429 second")

    clock.advance(100.0)  # 200s after first mark, 100s after second
    assert registry.get_available_model() is None

    clock.advance(20.0)
    assert registry.get_available_model() is not None


def test_from_registry_recovers_after_cooldown(
    registry: BaseModelRegistry, clock: FakeClock
) -> None:
    """The batch-OCR poisoning scenario: one 429 must not disable the
    single vision model for the rest of the process lifetime."""
    registry.mark_failed("m1", "429 rate limited")
    assert LLMClient.from_registry(registry) is None

    clock.advance(120.0)
    client = LLMClient.from_registry(registry)
    assert client is not None
    assert client.model == "m1"


# ---------------------------------------------------------------------------
# Vision base_url resolution (MiMo key/host correspondence)
# ---------------------------------------------------------------------------


def test_vision_base_url_prefers_vision_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIMO_VISION_BASE_URL", "https://vision.example.test/v1")
    monkeypatch.setenv("MIMO_BASE_URL", "https://base.example.test/v1")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    registry = VisionModelRegistry()
    assert registry.models[0].base_url == "https://vision.example.test/v1"


def test_vision_base_url_falls_back_to_mimo_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIMO_VISION_BASE_URL", raising=False)
    monkeypatch.setenv("MIMO_BASE_URL", "https://base.example.test/v1")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    registry = VisionModelRegistry()
    assert registry.models[0].base_url == "https://base.example.test/v1"


def test_vision_base_url_tp_key_defaults_to_token_plan_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIMO_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("MIMO_BASE_URL", raising=False)
    monkeypatch.setenv("MIMO_API_KEY", "tp-dummy-test-placeholder")

    registry = VisionModelRegistry()
    assert registry.models[0].base_url == "https://token-plan-cn.xiaomimimo.com/v1"


def test_vision_base_url_standard_key_defaults_to_api_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIMO_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("MIMO_BASE_URL", raising=False)
    monkeypatch.setenv("MIMO_API_KEY", "dummy-test-placeholder")

    registry = VisionModelRegistry()
    assert registry.models[0].base_url == "https://api.xiaomimimo.com/v1"


# ---------------------------------------------------------------------------
# Text registry key/endpoint misroute guard
# ---------------------------------------------------------------------------


def test_text_registry_warns_on_deepseek_key_to_mimo_endpoint(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(
        "FINER_LLM_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"
    )
    monkeypatch.delenv("FINER_LLM_API_KEY_ENV", raising=False)

    with caplog.at_level(logging.WARNING, logger="finer.model_config"):
        TextModelRegistry()

    assert any("MiMo endpoint" in rec.message for rec in caplog.records)


def test_text_registry_no_warning_when_key_env_matches(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(
        "FINER_LLM_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"
    )
    monkeypatch.setenv("FINER_LLM_API_KEY_ENV", "MIMO_API_KEY")

    with caplog.at_level(logging.WARNING, logger="finer.model_config"):
        registry = TextModelRegistry()

    assert not any("MiMo endpoint" in rec.message for rec in caplog.records)
    assert registry.models[0].api_key_env == "MIMO_API_KEY"
