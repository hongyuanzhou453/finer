"""FastAPI integration for canonical Finer errors."""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from finer.errors.codes import ErrorCode, get_error_info
from finer.errors.exceptions import FinerError

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
})


def register_error_handlers(app: FastAPI) -> None:
    """Register canonical exception handlers on a FastAPI app."""

    app.add_exception_handler(FinerError, finer_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)


def error_response(
    code: ErrorCode,
    message: str | None = None,
    *,
    details: dict[str, Any] | None = None,
    status_code: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a canonical JSON error response outside exception handlers."""

    error = FinerError(code, message, details=details, status_code=status_code)
    return JSONResponse(
        status_code=error.status_code,
        content=jsonable_encoder(error.to_payload()),
        headers=headers,
    )


def build_error_details(error: FinerError, request_id: str) -> dict[str, Any]:
    """Build canonical error details, auto-injecting *request_id* and *fix_hint*.

    Context fields from the error (stage, operation, etc.) are merged into
    details.  ``request_id`` and ``fix_hint`` are injected last so they always
    appear in the output even if the caller omitted them.
    """

    details = error.to_payload()["error"]["details"]
    details["request_id"] = request_id
    details["fix_hint"] = details.get("fix_hint") or error.info.fix_hint
    details["exception_type"] = details.get("exception_type") or type(error).__name__
    return details


def sanitize_error_details(details: dict[str, Any]) -> dict[str, Any]:
    """Filter sensitive fields (token, secret, password, etc.) from error details."""

    return {
        key: ("***REDACTED***" if key.lower() in _SENSITIVE_KEYS else value)
        for key, value in details.items()
    }


async def finer_error_handler(request: Request, exc: FinerError) -> JSONResponse:
    """Serialize expected Finer failures."""

    request_id = _resolve_request_id(request)
    details = build_error_details(exc, request_id)
    details = sanitize_error_details(details)
    payload = {
        "ok": False,
        "error": {
            "code": exc.error_code_str,
            "message": exc.message,
            "details": details,
        },
    }
    _log_error(request, exc.error_code_str, exc.status_code, exc.message, details)
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(payload))


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert legacy HTTPException usage to canonical error payload."""

    code = _code_for_status(exc.status_code)
    message = _message_from_http_exception(exc)
    base_details = _details_from_http_exception(exc)
    request_id = _resolve_request_id(request)
    base_details["request_id"] = request_id
    info = get_error_info(code)
    base_details["fix_hint"] = base_details.get("fix_hint") or info.fix_hint
    base_details = sanitize_error_details(base_details)
    response = error_response(
        code,
        message,
        details=base_details,
        status_code=exc.status_code,
        headers=exc.headers,
    )
    _log_error(request, code.value, exc.status_code, message, base_details)
    return response


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Serialize request model validation errors."""

    request_id = _resolve_request_id(request)
    details: dict[str, Any] = {"errors": exc.errors(), "request_id": request_id}
    info = get_error_info(ErrorCode.SYS_IN_002)
    details["fix_hint"] = info.fix_hint
    details = sanitize_error_details(details)
    response = error_response(
        ErrorCode.SYS_IN_002,
        "Request validation failed",
        details=details,
    )
    _log_error(request, ErrorCode.SYS_IN_002.value, 422, "Request validation failed", details)
    return response


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Serialize unexpected failures without leaking details by default."""

    request_id = _resolve_request_id(request)
    details: dict[str, Any] = {"exception_type": type(exc).__name__, "request_id": request_id}
    if _debug_errors_enabled():
        details["exception_message"] = str(exc)
    info = get_error_info(ErrorCode.SYS_INT_001)
    details["fix_hint"] = info.fix_hint
    details = sanitize_error_details(details)
    response = error_response(
        ErrorCode.SYS_INT_001,
        "Internal server error",
        details=details,
    )
    logger.exception(
        "Unhandled Finer API error",
        extra={
            "error_code": ErrorCode.SYS_INT_001.value,
            "path": request.url.path,
            "method": request.method,
            "details": details,
        },
    )
    return response


def _resolve_request_id(request: Request) -> str:
    """Return ``X-Request-ID`` header value or generate ``req-{uuid[:8]}``."""

    header_val = request.headers.get("X-Request-ID")
    if header_val:
        return header_val
    return f"req-{uuid4().hex[:8]}"


def _code_for_status(status_code: int) -> ErrorCode:
    if status_code == 400:
        return ErrorCode.SYS_IN_001
    if status_code == 401:
        return ErrorCode.SYS_AUTH_001
    if status_code == 403:
        return ErrorCode.SYS_PERM_001
    if status_code == 404:
        return ErrorCode.SYS_NTF_001
    if status_code == 409:
        return ErrorCode.SYS_CNF_001
    if status_code == 422:
        return ErrorCode.SYS_IN_002
    if status_code == 502:
        return ErrorCode.API_EXT_001
    if status_code == 504:
        return ErrorCode.SYS_TMO_001
    return ErrorCode.SYS_INT_001 if status_code >= 500 else ErrorCode.API_IN_001


def _message_from_http_exception(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message") or exc.detail.get("detail")
        if isinstance(message, str):
            return message
    if isinstance(exc.detail, str):
        return exc.detail
    return "HTTP error"


def _details_from_http_exception(exc: HTTPException) -> dict[str, Any]:
    if isinstance(exc.detail, dict):
        details = dict(exc.detail.get("details") or {})
        original_code = exc.detail.get("code")
        if original_code:
            details["original_code"] = original_code
        return details
    return {}


def _debug_errors_enabled() -> bool:
    return os.environ.get("FINER_ERROR_DEBUG", "false").lower() == "true"


def _log_error(
    request: Request,
    code: str,
    status_code: int,
    message: str,
    details: dict[str, Any],
) -> None:
    logger.warning(
        "Finer API error",
        extra={
            "error_code": code,
            "status_code": status_code,
            "error_message": message,
            "path": request.url.path,
            "method": request.method,
            "details": details,
        },
    )


__all__ = [
    "build_error_details",
    "error_response",
    "finer_error_handler",
    "http_exception_handler",
    "register_error_handlers",
    "sanitize_error_details",
    "unhandled_error_handler",
    "validation_error_handler",
]
