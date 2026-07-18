"""Model Config — model configuration with registry-based selection.

Text tasks may use fallback registries. Vision/OCR is intentionally pinned to
MiMo-V2.5 so F1 image/PDF standardization has a single auditable provider.

Text tasks: GLM-5.1 via SVIPS proxy (primary)
Vision tasks: MiMo-V2.5 via Xiaomi MiMo API Open Platform
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)

_MIMO_OPENAI_EXTRA_BODY = {"stream": False, "thinking": {"type": "disabled"}}

#: Default failure cooldown in seconds (override via FINER_MODEL_FAIL_COOLDOWN).
_DEFAULT_FAIL_COOLDOWN_SECONDS = 120.0


def _monotonic_now() -> float:
    """Injectable time source for failure cooldowns (monkeypatch in tests)."""
    return time.monotonic()


def _fail_cooldown_seconds() -> float:
    """Cooldown window for failed models.

    Read from FINER_MODEL_FAIL_COOLDOWN on every check so long-running batch
    processes pick up changes without re-creating the registry singletons.
    A value of 0 disables failure marking entirely (entries expire at once).
    """
    raw = os.getenv("FINER_MODEL_FAIL_COOLDOWN")
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            logger.warning(
                "Ignoring invalid FINER_MODEL_FAIL_COOLDOWN=%r; using default %.0fs",
                raw,
                _DEFAULT_FAIL_COOLDOWN_SECONDS,
            )
    return _DEFAULT_FAIL_COOLDOWN_SECONDS


class _FailureCooldownDict(Dict[str, str]):
    """``failed_models`` mapping whose entries auto-expire after a cooldown.

    The registries are module-level singletons, so a permanent
    ``failed_models`` entry used to poison a model for the whole process
    lifetime (``reset_failures()`` has no callers): after one transient 429
    on the single vision model, every subsequent ``LLMClient.from_registry()``
    returned None and batch OCR silently degraded to its failure fallback.

    Membership checks (``name in failed_models``) return False — and prune
    the entry — once FINER_MODEL_FAIL_COOLDOWN seconds (default 120) have
    elapsed since the failure was recorded, so the model automatically gets
    another chance. Values keep their error-string semantics for callers
    that read ``failed_models[name]``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._failed_at: Dict[str, float] = {key: _monotonic_now() for key in self}

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key, value)
        self._failed_at[key] = _monotonic_now()

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._failed_at.pop(key, None)

    def clear(self) -> None:
        super().clear()
        self._failed_at.clear()

    def __contains__(self, key: object) -> bool:
        if not super().__contains__(key):
            return False
        failed_at = self._failed_at.get(key)  # type: ignore[arg-type]
        if failed_at is None:
            # Entry recorded without a timestamp (e.g. injected directly);
            # start its cooldown now so it still expires eventually.
            self._failed_at[key] = _monotonic_now()  # type: ignore[index]
            return True
        if _monotonic_now() - failed_at >= _fail_cooldown_seconds():
            super().__delitem__(key)  # type: ignore[arg-type]
            self._failed_at.pop(key, None)  # type: ignore[arg-type]
            return False
        return True


def _text_extra_body_from_env() -> Dict[str, Any]:
    raw = os.getenv("FINER_LLM_EXTRA_BODY_JSON")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.warning("Ignoring invalid FINER_LLM_EXTRA_BODY_JSON")
    model_name = os.getenv("FINER_LLM_MODEL", "")
    if model_name.startswith("mimo-"):
        return dict(_MIMO_OPENAI_EXTRA_BODY)
    return {}


class ModelProvider(Enum):
    """Supported model providers."""
    GLM_SVIPS = "glm_svips"  # GLM via SVIPS proxy (text only)
    DASHSCOPE = "dashscope"  # Alibaba Cloud (Qwen) - vision + text fallback
    OPENAI = "openai"
    ZHIPU = "zhipu"  # GLM native
    DEEPSEEK = "deepseek"
    MIMO = "mimo"  # Xiaomi MiMo API Open Platform


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    name: str
    provider: ModelProvider
    api_key_env: str  # Environment variable name for API key
    base_url: Optional[str] = None
    max_tokens: int = 1024
    enabled: bool = True
    priority: int = 0  # Lower = higher priority
    api_key_header: str = "Authorization"
    api_key_scheme: Optional[str] = "Bearer"
    max_tokens_field: str = "max_tokens"
    extra_body: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaseModelRegistry:
    """Base registry with shared fallback logic.

    Failure marking is cooldown-based: entries in ``failed_models`` expire
    automatically after FINER_MODEL_FAIL_COOLDOWN seconds (default 120), so
    a transient quota/rate-limit error never permanently disables a model
    on the module-level registry singletons.
    """

    models: List[ModelConfig] = field(default_factory=list)
    failed_models: Dict[str, str] = field(default_factory=_FailureCooldownDict)

    def get_available_model(self) -> Optional[ModelConfig]:
        """Get the highest priority available model."""
        for model in sorted(self.models, key=lambda m: m.priority):
            if not model.enabled:
                continue
            if model.name in self.failed_models:
                continue
            api_key = os.getenv(model.api_key_env)
            if api_key:
                return model
        return None

    def mark_failed(self, model_name: str, error: str):
        """Mark a model as failed for the cooldown window, trigger fallback.

        The mark expires automatically after FINER_MODEL_FAIL_COOLDOWN
        seconds (default 120); call reset_failures() to lift it early.
        """
        self.failed_models[model_name] = error
        logger.warning(f"Model {model_name} failed: {error}. Trying fallback...")

    def reset_failures(self):
        """Reset failed models immediately (e.g., after quota refresh)."""
        self.failed_models.clear()
        logger.info("Reset all model failures")


def _mimo_vision_base_url() -> str:
    """Resolve the MiMo vision endpoint.

    Precedence: MIMO_VISION_BASE_URL > MIMO_BASE_URL > key-prefix default.

    MiMo issues keys bound to different hosts:
    - token-plan quota keys (prefix ``tp-``) are only valid on
      https://token-plan-cn.xiaomimimo.com/v1
    - standard open-platform keys are valid on https://api.xiaomimimo.com/v1

    Sending a ``tp-`` key to api.xiaomimimo.com returns 401, so when neither
    env override is set the default host is chosen from the key prefix
    (prefix check only — the key value itself is never logged or stored).
    """
    explicit = os.getenv("MIMO_VISION_BASE_URL") or os.getenv("MIMO_BASE_URL")
    if explicit:
        return explicit
    if (os.getenv("MIMO_API_KEY") or "").startswith("tp-"):
        return "https://token-plan-cn.xiaomimimo.com/v1"
    return "https://api.xiaomimimo.com/v1"


@dataclass
class VisionModelRegistry(BaseModelRegistry):
    """Registry of vision/OCR models.

    The user has chosen MiMo-V2.5 as the only vision model. Do not add
    provider fallback here unless the F1 OCR architecture is explicitly reset.
    """

    models: List[ModelConfig] = field(default_factory=lambda: [
        ModelConfig(
            name="mimo-v2.5",
            provider=ModelProvider.MIMO,
            api_key_env="MIMO_API_KEY",
            base_url=_mimo_vision_base_url(),
            max_tokens=4096,
            priority=0,
            api_key_header="api-key",
            api_key_scheme=None,
            max_tokens_field="max_completion_tokens",
            extra_body=dict(_MIMO_OPENAI_EXTRA_BODY),
        ),
    ])


def _primary_text_model_config() -> ModelConfig:
    """Build the env-overridable primary text model.

    Guards against the known key/endpoint misroute: pointing
    FINER_LLM_BASE_URL at a MiMo host while the key still comes from
    DEEPSEEK_API_KEY (FINER_LLM_API_KEY_ENV unset) sends the DeepSeek key
    to MiMo and fails with 401.
    """
    base_url = os.getenv("FINER_LLM_BASE_URL", "https://api.deepseek.com")
    api_key_env = os.getenv("FINER_LLM_API_KEY_ENV", "DEEPSEEK_API_KEY")
    if "xiaomimimo" in base_url and api_key_env == "DEEPSEEK_API_KEY":
        logger.warning(
            "FINER_LLM_BASE_URL points at a MiMo endpoint but the API key env "
            "is still DEEPSEEK_API_KEY (FINER_LLM_API_KEY_ENV not set). The "
            "DeepSeek key will be sent to MiMo and rejected with 401. Set "
            "FINER_LLM_API_KEY_ENV=MIMO_API_KEY to match the endpoint."
        )
    return ModelConfig(
        name=os.getenv("FINER_LLM_MODEL", "deepseek-v4-pro"),
        provider=ModelProvider.DEEPSEEK,
        api_key_env=api_key_env,
        base_url=base_url,
        max_tokens=int(os.getenv("FINER_LLM_MAX_TOKENS", "8192")),
        priority=0,
        api_key_header=os.getenv("FINER_LLM_API_KEY_HEADER", "Authorization"),
        api_key_scheme=(
            None
            if os.getenv("FINER_LLM_API_KEY_SCHEME", "Bearer") == ""
            else os.getenv("FINER_LLM_API_KEY_SCHEME", "Bearer")
        ),
        max_tokens_field=os.getenv("FINER_LLM_MAX_TOKENS_FIELD", "max_tokens"),
        extra_body=_text_extra_body_from_env(),
    )


@dataclass
class TextModelRegistry(BaseModelRegistry):
    """Registry of text/chat models for F1/F2 enrichment."""

    models: List[ModelConfig] = field(default_factory=lambda: [
        _primary_text_model_config(),
        ModelConfig(
            name="qwen-plus",
            provider=ModelProvider.DASHSCOPE,
            api_key_env="DASHSCOPE_API_KEY",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_tokens=4096,
            priority=1,
        ),
        ModelConfig(
            name="GLM-5.1",
            provider=ModelProvider.GLM_SVIPS,
            api_key_env="GLM_API_KEY",
            base_url="https://api.svips.org/v1",
            max_tokens=4096,
            priority=2,
        ),
    ])


@dataclass
class ReasoningModelRegistry(BaseModelRegistry):
    """Registry of reasoning/thinking models (MiMo-V2.5-Pro, etc.).

    These models support extended reasoning and are used for tasks that
    require deeper analysis (e.g., F3 intent extraction on complex content).
    """

    models: List[ModelConfig] = field(default_factory=lambda: [
        ModelConfig(
            name="mimo-v2.5-pro",
            provider=ModelProvider.MIMO,
            api_key_env="MIMO_API_KEY",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            max_tokens=8192,
            priority=0,
            api_key_header="api-key",
            api_key_scheme=None,
            max_tokens_field="max_completion_tokens",
            extra_body=dict(_MIMO_OPENAI_EXTRA_BODY),
        ),
    ])


# Global registry instances
_vision_registry: Optional[VisionModelRegistry] = None
_text_registry: Optional[TextModelRegistry] = None
_reasoning_registry: Optional[ReasoningModelRegistry] = None


def get_vision_registry() -> VisionModelRegistry:
    """Get or create the global vision model registry."""
    global _vision_registry
    if _vision_registry is None:
        _vision_registry = VisionModelRegistry()
    return _vision_registry


def get_text_registry() -> TextModelRegistry:
    """Get or create the global text model registry."""
    global _text_registry
    if _text_registry is None:
        _text_registry = TextModelRegistry()
    return _text_registry


def get_reasoning_registry() -> ReasoningModelRegistry:
    """Get or create the global reasoning model registry."""
    global _reasoning_registry
    if _reasoning_registry is None:
        _reasoning_registry = ReasoningModelRegistry()
    return _reasoning_registry
