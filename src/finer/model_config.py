"""Model Config — model configuration with registry-based selection.

Text tasks may use fallback registries. Vision/OCR is intentionally pinned to
MiMo-V2.5 so F1 image/PDF standardization has a single auditable provider.

Text tasks: GLM-5.1 via SVIPS proxy (primary)
Vision tasks: MiMo-V2.5 via Xiaomi MiMo API Open Platform
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


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


@dataclass
class BaseModelRegistry:
    """Base registry with shared fallback logic."""

    models: List[ModelConfig] = field(default_factory=list)
    failed_models: Dict[str, str] = field(default_factory=dict)

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
        """Mark a model as failed, trigger fallback."""
        self.failed_models[model_name] = error
        logger.warning(f"Model {model_name} failed: {error}. Trying fallback...")

    def reset_failures(self):
        """Reset failed models (e.g., after quota refresh)."""
        self.failed_models.clear()
        logger.info("Reset all model failures")


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
            base_url=(
                os.getenv("MIMO_VISION_BASE_URL")
                or os.getenv("MIMO_BASE_URL")
                or "https://api.xiaomimimo.com/v1"
            ),
            max_tokens=4096,
            priority=0,
            api_key_header="api-key",
            api_key_scheme=None,
            max_tokens_field="max_completion_tokens",
        ),
    ])


@dataclass
class TextModelRegistry(BaseModelRegistry):
    """Registry of text/chat models for F1/F2 enrichment."""

    models: List[ModelConfig] = field(default_factory=lambda: [
        ModelConfig(
            name=os.getenv("FINER_LLM_MODEL", "deepseek-v4-pro"),
            provider=ModelProvider.DEEPSEEK,
            api_key_env=os.getenv("FINER_LLM_API_KEY_ENV", "DEEPSEEK_API_KEY"),
            base_url=os.getenv("FINER_LLM_BASE_URL", "https://api.deepseek.com"),
            max_tokens=8192,
            priority=0,
        ),
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
