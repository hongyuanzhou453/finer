"""Unified LLM client with model fallback and proxy compatibility.

Consolidates the three previous implementations:
- llm_client.LLMClient (explicit params, vision support)
- enrichment.LLMClient (registry-based, model fallback)
- services.llm.LLMService (stub, replaced by real implementation)
"""

from __future__ import annotations

import os
import json
import logging
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified HTTP client for LLM APIs with model fallback and curl User-Agent.

    Supports two construction modes:
    1. Explicit: LLMClient(api_key=..., base_url=..., model=...)
    2. Registry-based: LLMClient.from_registry(registry) or LLMClient() with auto-config
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
        registry: Optional[Any] = None,
        api_key_header: str = "Authorization",
        api_key_scheme: Optional[str] = "Bearer",
        max_tokens_field: str = "max_tokens",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") if base_url else None
        self._model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._registry = registry
        self._api_key_header = api_key_header
        self._api_key_scheme = api_key_scheme
        self._max_tokens_field = max_tokens_field
        self.last_error: Optional[str] = None

    # -------------------------------------------------------------------------
    # Factory methods
    # -------------------------------------------------------------------------

    @classmethod
    def from_registry(cls, registry: Any, **kwargs) -> Optional["LLMClient"]:
        """Create a client from a model registry with auto-config."""
        model_config = registry.get_available_model()
        if not model_config:
            return None

        api_key = os.getenv(model_config.api_key_env)
        if not api_key:
            return None

        return cls(
            api_key=api_key,
            base_url=model_config.base_url,
            model=model_config.name,
            max_tokens=getattr(model_config, "max_tokens", 4096),
            registry=registry,
            api_key_header=getattr(model_config, "api_key_header", "Authorization"),
            api_key_scheme=getattr(model_config, "api_key_scheme", "Bearer"),
            max_tokens_field=getattr(model_config, "max_tokens_field", "max_tokens"),
            **kwargs,
        )

    @classmethod
    def auto(cls, **kwargs) -> Optional["LLMClient"]:
        """Create a client using the default text registry."""
        try:
            from finer.model_config import get_text_registry
            return cls.from_registry(get_text_registry(), **kwargs)
        except Exception:
            logger.warning("Failed to create auto-configured LLM client")
            return None

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _resolve_config(self) -> Optional[Dict[str, Any]]:
        """Resolve API key, base_url, model — supports registry fallback."""
        if self._api_key and self._base_url and self._model:
            return {
                "api_key": self._api_key,
                "base_url": self._base_url,
                "model": self._model,
                "api_key_header": self._api_key_header,
                "api_key_scheme": self._api_key_scheme,
                "max_tokens_field": self._max_tokens_field,
            }

        # Registry-based fallback
        if self._registry:
            model_config = self._registry.get_available_model()
            if not model_config:
                logger.error("No available models in registry")
                return None

            api_key = os.getenv(model_config.api_key_env)
            if not api_key:
                self._registry.mark_failed(model_config.name, "No API key")
                return self._resolve_config()  # Retry with next model

            return {
                "api_key": api_key,
                "base_url": model_config.base_url,
                "model": model_config.name,
                "api_key_header": getattr(model_config, "api_key_header", "Authorization"),
                "api_key_scheme": getattr(model_config, "api_key_scheme", "Bearer"),
                "max_tokens_field": getattr(model_config, "max_tokens_field", "max_tokens"),
            }

        logger.error("LLMClient not configured: provide api_key/base_url/model or registry")
        return None

    def _handle_error(self, model: str, error_msg: str) -> None:
        """Mark model as failed in registry if quota/rate-limit error."""
        if self._registry and any(
            x in error_msg.lower() for x in ["quota", "rate", "limit", "exhausted"]
        ):
            self._registry.mark_failed(model, error_msg)

    @staticmethod
    def _auth_header(config: Dict[str, Any]) -> Dict[str, str]:
        """Build provider-specific API key headers."""
        header_name = config.get("api_key_header") or "Authorization"
        scheme = config.get("api_key_scheme")
        api_key = config["api_key"]
        value = f"{scheme} {api_key}" if scheme else api_key
        return {header_name: value}

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Send a chat completion request with full message dicts."""
        config = self._resolve_config()
        if not config:
            return None

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "curl/8.0",
        }
        headers.update(self._auth_header(config))

        data = {
            "model": config["model"],
            "messages": messages,
            "temperature": temperature,
        }
        data[config.get("max_tokens_field", "max_tokens")] = max_tokens or self.max_tokens
        if response_format is not None:
            data["response_format"] = response_format
        if extra_body:
            data.update(extra_body)

        try:
            with httpx.Client(timeout=self.timeout, http2=False) as client:
                response = client.post(
                    f"{config['base_url']}/chat/completions",
                    headers=headers,
                    json=data,
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    if not content or not content.strip():
                        self.last_error = "empty_model_response"
                        logger.warning("LLM returned empty response")
                        return None
                    self.last_error = None
                    return content
                else:
                    error_msg = response.text[:200]
                    status = response.status_code
                    self._handle_error(config["model"], error_msg)
                    if status in (401, 403):
                        self.last_error = f"auth_failed ({status})"
                    elif status == 429:
                        self.last_error = "rate_limited"
                    elif status >= 500:
                        self.last_error = f"server_error ({status})"
                    else:
                        self.last_error = f"http_error ({status})"
                    logger.error(f"LLM API error: {status} - {error_msg}")
                    return None

        except httpx.TimeoutException:
            self.last_error = "timeout"
            logger.error(f"LLM request timed out after {self.timeout}s")
            return None
        except Exception as e:
            self.last_error = f"request_failed ({type(e).__name__})"
            logger.error(f"LLM request failed: {e}")
            return None

    def chat_prompt(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
        system: Optional[str] = None,
    ) -> Optional[str]:
        """Convenience method: send a plain string prompt."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, max_tokens=max_tokens, temperature=temperature)

    def chat_with_images(
        self,
        text: str,
        image_base64: str,
        mime_type: str = "image/png",
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Send a chat completion request with an image (vision)."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}"
                        },
                    },
                ],
            }
        ]
        return self.chat(messages, max_tokens=max_tokens)

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = True,
    ) -> Optional[Any]:
        """Chat completion with optional JSON parsing (replaces LLMService)."""
        raw = self.chat(messages)
        if raw is None:
            return None
        if json_mode:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        return raw
