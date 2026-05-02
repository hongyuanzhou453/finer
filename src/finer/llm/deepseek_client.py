"""DeepSeek official API client.

This client follows DeepSeek's OpenAI-compatible API contract:

- base URL: https://api.deepseek.com
- endpoint: /chat/completions
- model: deepseek-v4-pro by default
- JSON output: response_format={"type": "json_object"}
- thinking mode: sent via extra body {"thinking": {"type": "enabled"}}

The client intentionally raises typed errors instead of returning ``None`` so
callers can distinguish provider outage, bad credentials, empty content, and
invalid JSON.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class DeepSeekClientError(RuntimeError):
    """Base error for DeepSeek client failures."""


class DeepSeekConfigurationError(DeepSeekClientError):
    """Raised when no usable DeepSeek credential/configuration exists."""


class DeepSeekAPIError(DeepSeekClientError):
    """Raised when DeepSeek returns a non-200 response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"DeepSeek API error {status_code}: {message}")


class DeepSeekEmptyResponseError(DeepSeekClientError):
    """Raised when DeepSeek returns an empty assistant content."""


class DeepSeekJSONError(DeepSeekClientError):
    """Raised when DeepSeek output cannot be parsed as JSON."""


@dataclass(frozen=True)
class DeepSeekChatResult:
    """Raw DeepSeek chat result with useful usage metadata."""

    content: str
    model: str
    usage: Dict[str, Any]
    reasoning_content: Optional[str] = None


class DeepSeekClient:
    """Small HTTP client for DeepSeek's official OpenAI-compatible API."""

    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-v4-pro"
    RETRYABLE_STATUS_CODES = {429, 500, 503}

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 180.0,
        max_retries: int = 2,
        retry_base_delay: float = 1.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (
            base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("FINER_LLM_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = model or os.getenv("FINER_LLM_MODEL") or self.DEFAULT_MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.transport = transport

        if not self.api_key:
            raise DeepSeekConfigurationError("DEEPSEEK_API_KEY is not configured")

    @classmethod
    def from_env(cls, **kwargs: Any) -> "DeepSeekClient":
        """Build a client from environment variables."""
        return cls(**kwargs)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 8192,
        response_format: Optional[Dict[str, str]] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = "high",
        temperature: Optional[float] = None,
        stream: bool = False,
    ) -> DeepSeekChatResult:
        """Call DeepSeek chat completions and return assistant content."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if thinking is not None:
            payload["thinking"] = thinking
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if temperature is not None:
            payload["temperature"] = temperature

        response_data = self._post_with_retries(payload)
        choice = response_data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        if not content.strip():
            raise DeepSeekEmptyResponseError("DeepSeek returned empty content")

        return DeepSeekChatResult(
            content=content,
            model=response_data.get("model", self.model),
            usage=response_data.get("usage", {}),
            reasoning_content=message.get("reasoning_content"),
        )

    def chat_json(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 8192,
        thinking_enabled: bool = True,
        reasoning_effort: str = "high",
    ) -> Dict[str, Any]:
        """Call DeepSeek JSON Output mode and parse the returned object."""
        result = self.chat(
            messages,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            thinking={"type": "enabled" if thinking_enabled else "disabled"},
            reasoning_effort=reasoning_effort if thinking_enabled else None,
            temperature=None if thinking_enabled else 0.1,
            stream=False,
        )
        return self._loads_json(result.content)

    def _post_with_retries(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "finer/DeepSeekClient",
        }
        endpoint = f"{self.base_url}/chat/completions"
        last_error: Optional[DeepSeekClientError] = None

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    http2=False,
                    transport=self.transport,
                ) as client:
                    response = client.post(endpoint, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_error = DeepSeekClientError(f"DeepSeek request failed: {exc}")
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise last_error from exc

            if response.status_code == 200:
                return response.json()

            message = self._safe_error_message(response)
            error = DeepSeekAPIError(response.status_code, message)
            last_error = error
            if (
                response.status_code in self.RETRYABLE_STATUS_CODES
                and attempt < self.max_retries
            ):
                self._sleep_before_retry(attempt)
                continue
            raise error

        if last_error is not None:
            raise last_error
        raise DeepSeekClientError("DeepSeek request failed without response")

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.2)
        logger.info("Retrying DeepSeek request after %.2fs", delay)
        time.sleep(delay)

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                error = data.get("error")
                if isinstance(error, dict):
                    return str(error.get("message") or error)[:300]
                return str(data)[:300]
        except Exception:
            pass
        return response.text[:300]

    @staticmethod
    def _loads_json(raw: str) -> Dict[str, Any]:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DeepSeekJSONError(f"DeepSeek output is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise DeepSeekJSONError("DeepSeek JSON output must be an object")
        return data
