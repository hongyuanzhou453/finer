"""Tests for canonical Finer error codes and API handlers."""

from __future__ import annotations

import re

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from finer.errors import (
    ERROR_CODE_DEFINITIONS,
    ErrorCode,
    FinerExternalServiceError,
    FinerError,
    build_error_details,
    get_error_info,
    list_error_codes,
    lookup_error_codes,
    parse_error_code,
    register_error_handlers,
    sanitize_error_details,
)


CODE_PATTERN = re.compile(r"^[A-Z0-9]+_[A-Z]+_[0-9]{3}$")


def test_error_catalog_is_complete_and_searchable() -> None:
    assert len(ErrorCode) == 107
    assert len(ERROR_CODE_DEFINITIONS) == len(ErrorCode)
    assert len(list_error_codes()) == len(ErrorCode)

    for code in ErrorCode:
        info = get_error_info(code)
        assert info.code == code
        assert CODE_PATTERN.match(code.value)
        assert info.title
        assert info.root_cause
        assert info.fix_hint
        assert 400 <= info.status_code <= 599
        assert not code.value.startswith(("L0_", "L1_", "L2_", "L3_", "L4_", "L5_", "L6_", "L7_", "L8_"))
        assert not code.value.startswith(("V0_", "V1_", "V2_", "V3_", "V4_", "V5_", "V6_"))

    assert parse_error_code(ErrorCode.F15_IN_001) == ("F15", "IN", 1)
    assert [info.code for info in lookup_error_codes(domain="WX")] == [
        ErrorCode.WX_AUTH_001,
        ErrorCode.WX_EXT_001,
        ErrorCode.WX_TMO_001,
        ErrorCode.WX_NTF_001,
    ]


def test_finer_error_payload_uses_catalog_defaults() -> None:
    error = FinerExternalServiceError(
        ErrorCode.LLM_EXT_002,
        "Rate limited",
        service="mimo-api",
        details={"retry_after": 60},
    )

    assert error.status_code == 429
    assert error.error_code_str == "LLM_EXT_002"
    assert str(error) == "[LLM_EXT_002] Rate limited"
    payload = error.to_payload()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LLM_EXT_002"
    assert payload["error"]["message"] == "Rate limited"
    assert payload["error"]["details"]["retry_after"] == 60
    assert payload["error"]["details"]["service"] == "mimo-api"
    assert payload["error"]["details"]["retryable"] is True


def test_fastapi_handlers_serialize_finer_error() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise FinerExternalServiceError(
            ErrorCode.WX_EXT_001,
            "Exporter not responding",
            service="wechat-exporter",
        )

    client = TestClient(app)
    response = client.get("/boom", headers={"X-Request-ID": "req-1"})
    data = response.json()

    assert response.status_code == 502
    assert data["ok"] is False
    assert data["error"]["code"] == "WX_EXT_001"
    assert data["error"]["message"] == "Exporter not responding"
    assert data["error"]["details"]["service"] == "wechat-exporter"
    assert data["error"]["details"]["request_id"] == "req-1"
    assert data["error"]["details"]["fix_hint"] == "Start exporter and verify exporter_url."
    assert data["error"]["details"]["exception_type"] == "FinerExternalServiceError"


def test_fastapi_handlers_wrap_legacy_http_exception() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="Session not found")

    client = TestClient(app)
    response = client.get("/missing", headers={"X-Request-ID": "req-404"})
    data = response.json()

    assert response.status_code == 404
    assert data["ok"] is False
    assert data["error"]["code"] == "SYS_NTF_001"
    assert data["error"]["message"] == "Session not found"
    assert data["error"]["details"]["request_id"] == "req-404"
    assert "fix_hint" in data["error"]["details"]


def test_fastapi_handlers_wrap_request_validation_error() -> None:
    class Payload(BaseModel):
        content_id: str

    app = FastAPI()
    register_error_handlers(app)

    @app.post("/payload")
    def payload(_: Payload) -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/payload", json={}, headers={"X-Request-ID": "req-422"})
    data = response.json()

    assert response.status_code == 422
    assert data["ok"] is False
    assert data["error"]["code"] == "SYS_IN_002"
    assert data["error"]["details"]["request_id"] == "req-422"
    assert data["error"]["details"]["errors"][0]["type"] == "missing"


def test_fastapi_handlers_wrap_unexpected_errors() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/unexpected")
    def unexpected() -> None:
        raise RuntimeError("database password should not leak")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/unexpected", headers={"X-Request-ID": "req-500"})
    data = response.json()

    assert response.status_code == 500
    assert data["ok"] is False
    assert data["error"]["code"] == "SYS_INT_001"
    assert data["error"]["details"]["exception_type"] == "RuntimeError"
    assert data["error"]["details"]["request_id"] == "req-500"
    assert "exception_message" not in data["error"]["details"]


def test_server_create_app_registers_finer_error_handler() -> None:
    from finer.api.server import create_app

    app = create_app()
    assert FinerError in app.exception_handlers


# ---------------------------------------------------------------------------
# New tests for enhanced error envelope (request_id, context, fix_hint, etc.)
# ---------------------------------------------------------------------------


def test_error_details_include_request_id() -> None:
    """Handler auto-injects request_id into error details."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/ctx")
    def ctx() -> None:
        raise FinerError(ErrorCode.F0_EXT_001, "source down")

    client = TestClient(app)
    # With explicit header
    resp = client.get("/ctx", headers={"X-Request-ID": "req-abc123"})
    assert resp.json()["error"]["details"]["request_id"] == "req-abc123"

    # Auto-generated
    resp2 = client.get("/ctx")
    rid = resp2.json()["error"]["details"]["request_id"]
    assert rid.startswith("req-")
    assert len(rid) == 12  # "req-" + 8 hex chars


def test_error_details_include_stage_operation() -> None:
    """stage/operation context fields propagate into error details."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/stage")
    def stage_route() -> None:
        raise FinerError(
            ErrorCode.F0_EXT_001,
            "wechat unreachable",
            stage="F0",
            operation="wechat_import",
            source_channel="wechat",
            content_id="c-001",
        )

    client = TestClient(app)
    data = client.get("/stage", headers={"X-Request-ID": "req-s1"}).json()
    details = data["error"]["details"]
    assert details["stage"] == "F0"
    assert details["operation"] == "wechat_import"
    assert details["source_channel"] == "wechat"
    assert details["content_id"] == "c-001"
    assert details["request_id"] == "req-s1"


def test_error_details_include_fix_hint() -> None:
    """fix_hint is injected from the error catalog."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/hint")
    def hint() -> None:
        raise FinerError(ErrorCode.F0_EXT_001, "source down")

    client = TestClient(app)
    data = client.get("/hint", headers={"X-Request-ID": "req-hint"}).json()
    expected_hint = get_error_info(ErrorCode.F0_EXT_001).fix_hint
    assert data["error"]["details"]["fix_hint"] == expected_hint


def test_sensitive_fields_filtered() -> None:
    """token/secret/password fields are redacted in error details."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/leak")
    def leak() -> None:
        raise FinerError(
            ErrorCode.SYS_INT_001,
            "config error",
            details={
                "token": "sk-secret-123",
                "password": "hunter2",
                "api_key": "AKIA12345",
                "authorization": "Bearer xyz",
                "safe_field": "visible",
            },
        )

    client = TestClient(app)
    data = client.get("/leak", headers={"X-Request-ID": "req-leak"}).json()
    details = data["error"]["details"]
    assert details["token"] == "***REDACTED***"
    assert details["password"] == "***REDACTED***"
    assert details["api_key"] == "***REDACTED***"
    assert details["authorization"] == "***REDACTED***"
    assert details["safe_field"] == "visible"
    assert details["request_id"] == "req-leak"


def test_finerr_to_payload_with_context() -> None:
    """FinerError.to_payload() includes context fields in details."""
    error = FinerError(
        ErrorCode.F0_EXT_001,
        "wechat unreachable",
        stage="F0",
        operation="wechat_import",
        source_channel="wechat",
        content_id="c-001",
        import_run_id="run-42",
        external_source_id="ext-7",
        retryable=False,
    )
    payload = error.to_payload()
    details = payload["error"]["details"]
    assert details["stage"] == "F0"
    assert details["operation"] == "wechat_import"
    assert details["source_channel"] == "wechat"
    assert details["content_id"] == "c-001"
    assert details["import_run_id"] == "run-42"
    assert details["external_source_id"] == "ext-7"
    assert details["retryable"] is False
    assert payload["ok"] is False
    assert payload["error"]["code"] == "F0_EXT_001"
