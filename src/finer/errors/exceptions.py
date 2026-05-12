"""Finer exception hierarchy backed by canonical error codes."""

from __future__ import annotations

from typing import Any

from finer.errors.codes import ErrorCode, coerce_error_code, get_error_info


class FinerError(Exception):
    """Base exception for all expected Finer failures."""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        cause: BaseException | None = None,
        stage: str | None = None,
        operation: str | None = None,
        source_channel: str | None = None,
        content_id: str | None = None,
        import_run_id: str | None = None,
        external_source_id: str | None = None,
        retryable: bool = True,
        request_id: str | None = None,
        **context: Any,
    ) -> None:
        self.code = coerce_error_code(code)
        self.info = get_error_info(self.code)
        self.message = message or self.info.title
        self.status_code = status_code or self.info.status_code
        self.cause = cause
        self.stage = stage
        self.operation = operation
        self.source_channel = source_channel
        self.content_id = content_id
        self.import_run_id = import_run_id
        self.external_source_id = external_source_id
        self.retryable = retryable
        self.request_id = request_id
        self.details: dict[str, Any] = dict(details or {})
        self.details.update({key: value for key, value in context.items() if value is not None})
        super().__init__(self.message)

    @property
    def error_code_str(self) -> str:
        """Return the string value used in API responses and logs."""

        return self.code.value

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the canonical API error payload."""

        ctx_details: dict[str, Any] = {}
        if self.request_id is not None:
            ctx_details["request_id"] = self.request_id
        if self.stage is not None:
            ctx_details["stage"] = self.stage
        if self.operation is not None:
            ctx_details["operation"] = self.operation
        if self.source_channel is not None:
            ctx_details["source_channel"] = self.source_channel
        if self.content_id is not None:
            ctx_details["content_id"] = self.content_id
        if self.import_run_id is not None:
            ctx_details["import_run_id"] = self.import_run_id
        if self.external_source_id is not None:
            ctx_details["external_source_id"] = self.external_source_id
        ctx_details["retryable"] = self.retryable
        # merge: explicit details override context defaults, context fields fill in
        merged = {**ctx_details, **self.details}
        # re-add context fields that were overwritten by details only if they
        # are not already present from self.details
        for key, value in ctx_details.items():
            merged.setdefault(key, value)

        return {
            "ok": False,
            "error": {
                "code": self.error_code_str,
                "message": self.message,
                "details": merged,
            },
        }

    def __str__(self) -> str:
        return f"[{self.error_code_str}] {self.message}"


class FinerValidationError(FinerError):
    """Caller input failed validation."""


class FinerAuthenticationError(FinerError):
    """Authentication failed."""


class FinerAuthorizationError(FinerError):
    """Authenticated caller is not allowed to perform the operation."""


class FinerNotFoundError(FinerError):
    """Requested resource was not found."""


class FinerConflictError(FinerError):
    """Requested operation conflicts with current state."""


class FinerConfigurationError(FinerError):
    """Runtime configuration is invalid or missing."""


class FinerStateError(FinerError):
    """Pipeline or resource state is invalid for the requested operation."""


class FinerSchemaError(FinerError):
    """Canonical schema validation failed."""


class FinerExternalServiceError(FinerError):
    """External service or upstream dependency failed."""


class FinerTimeoutError(FinerError):
    """Operation exceeded its timeout."""


class FinerInternalError(FinerError):
    """Unexpected internal failure that should be narrowed later."""


__all__ = [
    "FinerAuthenticationError",
    "FinerAuthorizationError",
    "FinerConfigurationError",
    "FinerConflictError",
    "FinerError",
    "FinerExternalServiceError",
    "FinerInternalError",
    "FinerNotFoundError",
    "FinerSchemaError",
    "FinerStateError",
    "FinerTimeoutError",
    "FinerValidationError",
]
