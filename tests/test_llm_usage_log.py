"""Tests for LLMClient.chat() usage accounting (FINER_LLM_USAGE_LOG).

Verifies:
- Successful chat() appends one JSONL record with
  {ts, model, base_url_host, prompt_tokens, completion_tokens,
   total_tokens, caller_tag}.
- No message content and no API key ever land in the log.
- caller_tag flows through chat()/chat_prompt()/chat_with_images().
- Write failures are swallowed and never break the call.
- No record is written on non-200 responses.
- Default path resolves under finer.paths.DATA_ROOT.

All HTTP traffic is mocked — no real LLM API is called.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

import finer.llm.client as client_module
from finer.llm.client import (
    LLMClient,
    _extract_usage_tokens,
    get_quota_state,
    get_usage_counter,
    reset_quota_state,
    reset_usage_counter,
)

API_KEY = "dummy-test-api-key-do-not-use"
USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


@pytest.fixture
def clean_telemetry():
    """Reset the process-local usage/quota trackers around a test (C3)."""
    reset_usage_counter()
    reset_quota_state()
    yield
    reset_usage_counter()
    reset_quota_state()


def install_fake_httpx(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int = 200,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Replace httpx.Client with a canned-response fake; returns captured call."""
    captured: Dict[str, Any] = {}
    if payload is None:
        payload = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": dict(USAGE),
        }

    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = status_code
            self.text = json.dumps(payload)

        def json(self) -> Dict[str, Any]:
            return payload

    class FakeHTTPXClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FakeHTTPXClient":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, url: str, headers: Dict, json: Dict) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(client_module.httpx, "Client", FakeHTTPXClient)
    return captured


def make_client() -> LLMClient:
    return LLMClient(
        api_key=API_KEY,
        base_url="https://example.test/v1",
        model="test-model",
    )


def read_records(path: Path) -> list:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_chat_appends_usage_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(monkeypatch)

    result = make_client().chat(
        [{"role": "user", "content": "secret-user-content"}],
        caller_tag="t2_ocr",
    )

    assert result == "ok"
    records = read_records(log_path)
    assert len(records) == 1
    record = records[0]
    assert set(record) == {
        "ts",
        "model",
        "base_url_host",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "caller_tag",
    }
    assert record["model"] == "test-model"
    assert record["base_url_host"] == "example.test"  # host only, no path
    assert record["prompt_tokens"] == 11
    assert record["completion_tokens"] == 7
    assert record["total_tokens"] == 18
    assert record["caller_tag"] == "t2_ocr"
    assert record["ts"]  # ISO timestamp present


def test_log_never_contains_content_or_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(monkeypatch)

    make_client().chat([{"role": "user", "content": "secret-user-content"}])

    raw = log_path.read_text()
    assert "secret-user-content" not in raw
    assert API_KEY not in raw
    assert "ok" != raw  # response content not the record either
    assert '"ok"' not in raw


def test_multiple_calls_append(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(monkeypatch)

    client = make_client()
    client.chat([{"role": "user", "content": "a"}])
    client.chat([{"role": "user", "content": "b"}], caller_tag="second")

    records = read_records(log_path)
    assert len(records) == 2
    assert records[0]["caller_tag"] is None
    assert records[1]["caller_tag"] == "second"


def test_missing_usage_still_logs_with_null_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(
        monkeypatch,
        payload={"choices": [{"message": {"content": "ok"}}]},
    )

    result = make_client().chat([{"role": "user", "content": "x"}])

    assert result == "ok"
    record = read_records(log_path)[0]
    assert record["prompt_tokens"] is None
    assert record["completion_tokens"] is None
    assert record["total_tokens"] is None


def test_write_failure_never_breaks_the_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point the log at a path whose parent is an existing *file* so that
    # mkdir(parents=True) raises.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(blocker / "usage.jsonl"))
    install_fake_httpx(monkeypatch)

    result = make_client().chat([{"role": "user", "content": "x"}])

    assert result == "ok"  # call unaffected by the failed write


def test_no_log_on_http_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(monkeypatch, status_code=500, payload={"error": "boom"})

    result = make_client().chat([{"role": "user", "content": "x"}])

    assert result is None
    assert not log_path.exists()


def test_default_path_resolves_under_data_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FINER_LLM_USAGE_LOG", raising=False)
    monkeypatch.setattr("finer.paths.DATA_ROOT", tmp_path)
    install_fake_httpx(monkeypatch)

    make_client().chat([{"role": "user", "content": "x"}])

    expected = tmp_path / "llm_usage" / "usage.jsonl"
    assert expected.exists()
    assert read_records(expected)[0]["model"] == "test-model"


def test_chat_prompt_forwards_caller_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(monkeypatch)

    make_client().chat_prompt("hello", caller_tag="prompt_tag")

    assert read_records(log_path)[0]["caller_tag"] == "prompt_tag"


def test_chat_with_images_forwards_caller_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(log_path))
    install_fake_httpx(monkeypatch)

    make_client().chat_with_images(
        "describe", image_base64="aGk=", caller_tag="vision_tag"
    )

    record = read_records(log_path)[0]
    assert record["caller_tag"] == "vision_tag"
    raw = log_path.read_text()
    assert "aGk=" not in raw  # image payload never logged


# =============================================================================
# C3 — usage extraction hardening + in-process accumulator + quota tracker
# =============================================================================


def test_extract_usage_computes_total_from_parts() -> None:
    """MiMo sometimes omits total_tokens; it must be derived from the parts."""
    tokens = _extract_usage_tokens({"prompt_tokens": 100, "completion_tokens": 250})
    assert tokens == {"prompt_tokens": 100, "completion_tokens": 250, "total_tokens": 350}


def test_extract_usage_folds_reasoning_tokens_when_completion_absent() -> None:
    """Reasoning-model completion budget must not be lost when completion is absent."""
    tokens = _extract_usage_tokens(
        {"prompt_tokens": 10, "completion_tokens_details": {"reasoning_tokens": 40}}
    )
    assert tokens["completion_tokens"] == 40
    assert tokens["total_tokens"] == 50


def test_extract_usage_null_on_empty_or_missing() -> None:
    """An empty/absent usage object yields all-None (the observed null-token case)."""
    for bad in (None, {}, "not-a-dict", {"prompt_tokens": None}):
        tokens = _extract_usage_tokens(bad)
        assert tokens["total_tokens"] is None or tokens["total_tokens"] == 0 or isinstance(
            tokens["total_tokens"], int
        )
    assert _extract_usage_tokens(None) == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_usage_accumulator_tracks_across_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_telemetry
) -> None:
    """Two successful chats accumulate real (non-null) tokens in-process (budget source)."""
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    install_fake_httpx(monkeypatch)  # USAGE = 11/7/18 per call

    client = make_client()
    client.chat([{"role": "user", "content": "a"}])
    client.chat([{"role": "user", "content": "b"}])

    counter = get_usage_counter()
    assert counter["calls"] == 2
    assert counter["prompt_tokens"] == 22
    assert counter["completion_tokens"] == 14
    assert counter["total_tokens"] == 36  # non-null: proves the budget source works


def test_accumulator_computes_total_when_provider_omits_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_telemetry
) -> None:
    """End-to-end: provider omits total_tokens, accumulator still counts it."""
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    install_fake_httpx(
        monkeypatch,
        payload={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 12},  # no total
        },
    )
    make_client().chat([{"role": "user", "content": "x"}])
    assert get_usage_counter()["total_tokens"] == 42


def test_quota_tracker_strikes_then_resets_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_telemetry
) -> None:
    """Consecutive 401/429 increment the strike counter; a 200 clears the streak."""
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    client = make_client()

    install_fake_httpx(monkeypatch, status_code=401, payload={"error": "auth"})
    client.chat([{"role": "user", "content": "x"}])
    assert get_quota_state()["consecutive"] == 1

    install_fake_httpx(monkeypatch, status_code=429, payload={"error": "rate"})
    client.chat([{"role": "user", "content": "x"}])
    assert get_quota_state()["consecutive"] == 2
    assert get_quota_state()["last_status"] == 429

    install_fake_httpx(monkeypatch, status_code=200)
    client.chat([{"role": "user", "content": "x"}])
    state = get_quota_state()
    assert state["consecutive"] == 0  # streak cleared by the success
    assert state["successes"] == 1
    assert state["strikes_recorded"] == 2  # cumulative strikes preserved


def test_non_quota_error_does_not_strike(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_telemetry
) -> None:
    """A 500 is not a quota/auth problem — it must not trip the breaker."""
    monkeypatch.setenv("FINER_LLM_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    install_fake_httpx(monkeypatch, status_code=500, payload={"error": "boom"})
    make_client().chat([{"role": "user", "content": "x"}])
    assert get_quota_state()["consecutive"] == 0
    assert get_quota_state()["strikes_recorded"] == 0
