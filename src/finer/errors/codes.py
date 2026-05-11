"""Canonical Finer error-code catalog.

The catalog is intentionally explicit. Stable error identities are more useful
for root-cause lookup than ad-hoc exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ErrorCode(str, Enum):
    """Stable Finer error codes.

    Format: {DOMAIN}_{CATEGORY}_{SEQUENCE}
    """

    SYS_IN_001 = "SYS_IN_001"
    SYS_IN_002 = "SYS_IN_002"
    SYS_AUTH_001 = "SYS_AUTH_001"
    SYS_AUTH_002 = "SYS_AUTH_002"
    SYS_PERM_001 = "SYS_PERM_001"
    SYS_NTF_001 = "SYS_NTF_001"
    SYS_CNF_001 = "SYS_CNF_001"
    SYS_CFG_001 = "SYS_CFG_001"
    SYS_IO_001 = "SYS_IO_001"
    SYS_STATE_001 = "SYS_STATE_001"
    SYS_TMO_001 = "SYS_TMO_001"
    SYS_INT_001 = "SYS_INT_001"

    API_IN_001 = "API_IN_001"
    API_AUTH_001 = "API_AUTH_001"
    API_PERM_001 = "API_PERM_001"
    API_NTF_001 = "API_NTF_001"
    API_STATE_001 = "API_STATE_001"
    API_EXT_001 = "API_EXT_001"
    API_TMO_001 = "API_TMO_001"
    API_INT_001 = "API_INT_001"

    F0_IN_001 = "F0_IN_001"
    F0_EXT_001 = "F0_EXT_001"
    F0_EXT_002 = "F0_EXT_002"
    F0_AUTH_001 = "F0_AUTH_001"
    F0_TMO_001 = "F0_TMO_001"
    F0_STATE_001 = "F0_STATE_001"
    F0_IO_001 = "F0_IO_001"
    F0_INT_001 = "F0_INT_001"

    F1_IN_001 = "F1_IN_001"
    F1_SCHEMA_001 = "F1_SCHEMA_001"
    F1_PARSE_001 = "F1_PARSE_001"
    F1_PARSE_002 = "F1_PARSE_002"
    F1_EXT_001 = "F1_EXT_001"
    F1_TMO_001 = "F1_TMO_001"
    F1_STATE_001 = "F1_STATE_001"
    F1_INT_001 = "F1_INT_001"

    F15_IN_001 = "F15_IN_001"
    F15_SCHEMA_001 = "F15_SCHEMA_001"
    F15_STATE_001 = "F15_STATE_001"
    F15_EXT_001 = "F15_EXT_001"
    F15_TMO_001 = "F15_TMO_001"
    F15_INT_001 = "F15_INT_001"

    F2_IN_001 = "F2_IN_001"
    F2_NTF_001 = "F2_NTF_001"
    F2_EXT_001 = "F2_EXT_001"
    F2_TMO_001 = "F2_TMO_001"
    F2_SCHEMA_001 = "F2_SCHEMA_001"
    F2_STATE_001 = "F2_STATE_001"
    F2_INT_001 = "F2_INT_001"

    F3_IN_001 = "F3_IN_001"
    F3_SCHEMA_001 = "F3_SCHEMA_001"
    F3_PARSE_001 = "F3_PARSE_001"
    F3_EXT_001 = "F3_EXT_001"
    F3_TMO_001 = "F3_TMO_001"
    F3_STATE_001 = "F3_STATE_001"
    F3_INT_001 = "F3_INT_001"

    F4_IN_001 = "F4_IN_001"
    F4_POLICY_001 = "F4_POLICY_001"
    F4_POLICY_002 = "F4_POLICY_002"
    F4_SCHEMA_001 = "F4_SCHEMA_001"
    F4_STATE_001 = "F4_STATE_001"
    F4_EXT_001 = "F4_EXT_001"
    F4_INT_001 = "F4_INT_001"

    F5_IN_001 = "F5_IN_001"
    F5_SCHEMA_001 = "F5_SCHEMA_001"
    F5_STATE_001 = "F5_STATE_001"
    F5_POLICY_001 = "F5_POLICY_001"
    F5_EXT_001 = "F5_EXT_001"
    F5_TMO_001 = "F5_TMO_001"
    F5_INT_001 = "F5_INT_001"

    F6_IN_001 = "F6_IN_001"
    F6_NTF_001 = "F6_NTF_001"
    F6_SCHEMA_001 = "F6_SCHEMA_001"
    F6_STATE_001 = "F6_STATE_001"
    F6_INT_001 = "F6_INT_001"

    F7_IN_001 = "F7_IN_001"
    F7_NTF_001 = "F7_NTF_001"
    F7_SCHEMA_001 = "F7_SCHEMA_001"
    F7_STATE_001 = "F7_STATE_001"
    F7_INT_001 = "F7_INT_001"

    F8_IN_001 = "F8_IN_001"
    F8_NTF_001 = "F8_NTF_001"
    F8_EXT_001 = "F8_EXT_001"
    F8_TMO_001 = "F8_TMO_001"
    F8_INT_001 = "F8_INT_001"

    LLM_AUTH_001 = "LLM_AUTH_001"
    LLM_CFG_001 = "LLM_CFG_001"
    LLM_EXT_001 = "LLM_EXT_001"
    LLM_EXT_002 = "LLM_EXT_002"
    LLM_TMO_001 = "LLM_TMO_001"
    LLM_SCHEMA_001 = "LLM_SCHEMA_001"
    LLM_INT_001 = "LLM_INT_001"

    WX_AUTH_001 = "WX_AUTH_001"
    WX_EXT_001 = "WX_EXT_001"
    WX_TMO_001 = "WX_TMO_001"
    WX_NTF_001 = "WX_NTF_001"

    BILI_IN_001 = "BILI_IN_001"
    BILI_EXT_001 = "BILI_EXT_001"
    BILI_NTF_001 = "BILI_NTF_001"

    FEISHU_AUTH_001 = "FEISHU_AUTH_001"
    FEISHU_EXT_001 = "FEISHU_EXT_001"
    FEISHU_TMO_001 = "FEISHU_TMO_001"

    NLM_EXT_001 = "NLM_EXT_001"
    NLM_TMO_001 = "NLM_TMO_001"

    F0_INDEX_001 = "F0_INDEX_001"
    F0_INDEX_002 = "F0_INDEX_002"
    F0_INDEX_003 = "F0_INDEX_003"


@dataclass(frozen=True)
class ErrorCodeInfo:
    """Lookup metadata for one error code."""

    code: ErrorCode
    domain: str
    category: str
    sequence: int
    status_code: int
    title: str
    root_cause: str
    fix_hint: str


CATEGORY_STATUS: dict[str, int] = {
    "IN": 400,
    "AUTH": 401,
    "PERM": 403,
    "NTF": 404,
    "CNF": 409,
    "STATE": 409,
    "RLM": 429,
    "SCHEMA": 422,
    "PARSE": 422,
    "POLICY": 422,
    "CFG": 500,
    "IO": 500,
    "INT": 500,
    "EXT": 502,
    "TMO": 504,
}


def parse_error_code(code: ErrorCode | str) -> tuple[str, str, int]:
    """Parse an error code into domain, category, and numeric sequence."""

    value = code.value if isinstance(code, ErrorCode) else code
    parts = value.split("_")
    if len(parts) != 3:
        raise ValueError(f"Invalid error code format: {value}")
    domain, category, sequence_text = parts
    if not domain or not category or not sequence_text.isdigit():
        raise ValueError(f"Invalid error code format: {value}")
    return domain, category, int(sequence_text)


def coerce_error_code(code: ErrorCode | str) -> ErrorCode:
    """Convert a string or enum value to an ErrorCode."""

    if isinstance(code, ErrorCode):
        return code
    return ErrorCode(code)


def _info(
    code: ErrorCode,
    title: str,
    root_cause: str,
    fix_hint: str,
    *,
    status_code: int | None = None,
) -> ErrorCodeInfo:
    domain, category, sequence = parse_error_code(code)
    resolved_status = status_code or CATEGORY_STATUS.get(category, 500)
    return ErrorCodeInfo(
        code=code,
        domain=domain,
        category=category,
        sequence=sequence,
        status_code=resolved_status,
        title=title,
        root_cause=root_cause,
        fix_hint=fix_hint,
    )


ERROR_CODE_DEFINITIONS: dict[ErrorCode, ErrorCodeInfo] = {
    ErrorCode.SYS_IN_001: _info(ErrorCode.SYS_IN_001, "Invalid input", "A caller supplied invalid input.", "Validate request fields and required identifiers before calling the API."),
    ErrorCode.SYS_IN_002: _info(ErrorCode.SYS_IN_002, "Request validation failed", "FastAPI or Pydantic rejected the request payload.", "Inspect details.errors and align the client payload with the route schema.", status_code=422),
    ErrorCode.SYS_AUTH_001: _info(ErrorCode.SYS_AUTH_001, "Authentication failed", "The request did not provide valid credentials.", "Provide a valid X-API-Key or bearer token."),
    ErrorCode.SYS_AUTH_002: _info(ErrorCode.SYS_AUTH_002, "Authentication misconfigured", "Authentication is enabled but no verifier is configured.", "Set API_KEY or JWT_SECRET in the runtime environment.", status_code=500),
    ErrorCode.SYS_PERM_001: _info(ErrorCode.SYS_PERM_001, "Permission denied", "The authenticated request is not allowed to perform this operation.", "Check the operation sensitivity and provide required secondary authentication."),
    ErrorCode.SYS_NTF_001: _info(ErrorCode.SYS_NTF_001, "Resource not found", "The requested resource or route target does not exist.", "Check the identifier, path, and backing store."),
    ErrorCode.SYS_CNF_001: _info(ErrorCode.SYS_CNF_001, "Resource conflict", "The requested operation conflicts with current state.", "Refresh state and retry with a non-conflicting update."),
    ErrorCode.SYS_CFG_001: _info(ErrorCode.SYS_CFG_001, "Configuration error", "Required runtime configuration is missing or invalid.", "Check config.py, configs/*.yaml, and environment variables."),
    ErrorCode.SYS_IO_001: _info(ErrorCode.SYS_IO_001, "Filesystem error", "A filesystem read or write operation failed.", "Check path existence, permissions, and data directory contracts."),
    ErrorCode.SYS_STATE_001: _info(ErrorCode.SYS_STATE_001, "Invalid system state", "The operation was valid but cannot run in the current state.", "Inspect current state and complete the prerequisite transition."),
    ErrorCode.SYS_TMO_001: _info(ErrorCode.SYS_TMO_001, "System timeout", "A local or infrastructure operation exceeded its time budget.", "Retry with a longer timeout or inspect the blocked dependency."),
    ErrorCode.SYS_INT_001: _info(ErrorCode.SYS_INT_001, "Internal server error", "An unexpected server error escaped domain-specific handling.", "Check server logs using the request_id and add a narrower FinerError at the source."),

    ErrorCode.API_IN_001: _info(ErrorCode.API_IN_001, "Invalid API request", "An API route received an unsupported request shape.", "Fix the client request or route request model."),
    ErrorCode.API_AUTH_001: _info(ErrorCode.API_AUTH_001, "API authentication failed", "API credentials failed validation.", "Check request headers and configured credentials."),
    ErrorCode.API_PERM_001: _info(ErrorCode.API_PERM_001, "API permission denied", "The caller is authenticated but lacks permission for the API operation.", "Check route-level authorization and sensitive operation requirements."),
    ErrorCode.API_NTF_001: _info(ErrorCode.API_NTF_001, "API resource not found", "The API route could not find the requested resource.", "Verify the resource id and storage index."),
    ErrorCode.API_STATE_001: _info(ErrorCode.API_STATE_001, "API state conflict", "The API request conflicts with current workflow state.", "Refresh frontend state and retry with the latest resource version."),
    ErrorCode.API_EXT_001: _info(ErrorCode.API_EXT_001, "API upstream failure", "An API route dependency returned an error.", "Inspect dependency health and route logs."),
    ErrorCode.API_TMO_001: _info(ErrorCode.API_TMO_001, "API timeout", "An API request timed out waiting for a dependency.", "Retry or increase the dependency timeout."),
    ErrorCode.API_INT_001: _info(ErrorCode.API_INT_001, "API internal error", "Unexpected API route failure.", "Check route logs and replace broad exceptions with specific FinerError codes."),

    ErrorCode.F0_IN_001: _info(ErrorCode.F0_IN_001, "Invalid F0 intake input", "The intake source payload is missing required fields.", "Validate ContentRecord source metadata before ingestion."),
    ErrorCode.F0_EXT_001: _info(ErrorCode.F0_EXT_001, "F0 source unavailable", "An external intake source could not be reached.", "Check source credentials, network, and adapter health."),
    ErrorCode.F0_EXT_002: _info(ErrorCode.F0_EXT_002, "F0 source returned invalid data", "The intake source responded with malformed or unsupported data.", "Capture the raw response and update the source adapter parser."),
    ErrorCode.F0_AUTH_001: _info(ErrorCode.F0_AUTH_001, "F0 source authentication failed", "The intake adapter has expired or invalid credentials.", "Refresh the source token or login session."),
    ErrorCode.F0_TMO_001: _info(ErrorCode.F0_TMO_001, "F0 intake timeout", "Source ingestion exceeded its timeout.", "Retry with pagination or inspect the external source latency."),
    ErrorCode.F0_STATE_001: _info(ErrorCode.F0_STATE_001, "F0 intake state invalid", "The intake session or cursor is inconsistent.", "Reset or repair the source cursor/session state."),
    ErrorCode.F0_IO_001: _info(ErrorCode.F0_IO_001, "F0 artifact write failed", "The intake artifact could not be persisted.", "Check data/F0_intake permissions and storage paths."),
    ErrorCode.F0_INT_001: _info(ErrorCode.F0_INT_001, "F0 internal error", "Unexpected intake-stage failure.", "Check F0 adapter logs and add a more specific error code."),

    ErrorCode.F1_IN_001: _info(ErrorCode.F1_IN_001, "Invalid F1 input", "F1 received an invalid ContentRecord or source artifact.", "Ensure F0 output satisfies ContentRecord before standardization."),
    ErrorCode.F1_SCHEMA_001: _info(ErrorCode.F1_SCHEMA_001, "F1 envelope schema invalid", "ContentEnvelope or ContentBlock validation failed.", "Fix the standardizer to emit canonical F1 schema fields."),
    ErrorCode.F1_PARSE_001: _info(ErrorCode.F1_PARSE_001, "F1 text parse failed", "The standardizer could not parse source text into canonical blocks.", "Inspect raw text boundaries and parser assumptions."),
    ErrorCode.F1_PARSE_002: _info(ErrorCode.F1_PARSE_002, "F1 media parse failed", "OCR, ASR, or layout extraction produced unusable content.", "Check media artifacts and perception service output."),
    ErrorCode.F1_EXT_001: _info(ErrorCode.F1_EXT_001, "F1 perception service failed", "An OCR, ASR, or vision dependency failed.", "Check perception service health and request payload size."),
    ErrorCode.F1_TMO_001: _info(ErrorCode.F1_TMO_001, "F1 standardization timeout", "Standardization exceeded its time budget.", "Split large inputs or increase the F1 timeout."),
    ErrorCode.F1_STATE_001: _info(ErrorCode.F1_STATE_001, "F1 provenance state invalid", "Block provenance does not match source artifacts.", "Repair source ids and block provenance references."),
    ErrorCode.F1_INT_001: _info(ErrorCode.F1_INT_001, "F1 internal error", "Unexpected F1 standardization failure.", "Check standardizer logs and add a narrower F1 code."),

    ErrorCode.F15_IN_001: _info(ErrorCode.F15_IN_001, "Invalid F1.5 input", "Topic assembly received invalid ContentBlock inputs.", "Pass canonical F1 ContentEnvelope and ContentBlock ids."),
    ErrorCode.F15_SCHEMA_001: _info(ErrorCode.F15_SCHEMA_001, "F1.5 topic schema invalid", "TopicBlock or TopicAssemblyResult validation failed.", "Fix topic assembly output to match schemas/topic_block.py."),
    ErrorCode.F15_STATE_001: _info(ErrorCode.F15_STATE_001, "F1.5 assembly state invalid", "Topic boundaries or source block references are inconsistent.", "Inspect source_block_ids and assembly diagnostics."),
    ErrorCode.F15_EXT_001: _info(ErrorCode.F15_EXT_001, "F1.5 LLM proposal failed", "Constrained topic proposal dependency failed.", "Use deterministic fallback or inspect LLM adapter output."),
    ErrorCode.F15_TMO_001: _info(ErrorCode.F15_TMO_001, "F1.5 assembly timeout", "Topic assembly exceeded its time budget.", "Split input or reduce LLM proposal scope."),
    ErrorCode.F15_INT_001: _info(ErrorCode.F15_INT_001, "F1.5 internal error", "Unexpected topic assembly failure.", "Check topic assembler logs and add a narrower F1.5 code."),

    ErrorCode.F2_IN_001: _info(ErrorCode.F2_IN_001, "Invalid F2 input", "Anchor stage received invalid topic or evidence inputs.", "Ensure F1.5 output satisfies TopicBlock before anchoring."),
    ErrorCode.F2_NTF_001: _info(ErrorCode.F2_NTF_001, "F2 entity not found", "Entity resolution could not locate a required entity.", "Add aliases to the entity registry or relax the resolver query."),
    ErrorCode.F2_EXT_001: _info(ErrorCode.F2_EXT_001, "F2 market data failed", "Finance data or enrichment dependency failed.", "Check finance-skills service health and symbol mapping."),
    ErrorCode.F2_TMO_001: _info(ErrorCode.F2_TMO_001, "F2 enrichment timeout", "Anchor or enrichment work exceeded its time budget.", "Cache finance lookups or reduce batch size."),
    ErrorCode.F2_SCHEMA_001: _info(ErrorCode.F2_SCHEMA_001, "F2 schema invalid", "QualityCard, TemporalAnchor, EntityAnchor, or EvidenceSpan validation failed.", "Fix enrichment output fields and evidence references."),
    ErrorCode.F2_STATE_001: _info(ErrorCode.F2_STATE_001, "F2 anchor state invalid", "Evidence spans or anchors contradict source content.", "Inspect span offsets and source block ids."),
    ErrorCode.F2_INT_001: _info(ErrorCode.F2_INT_001, "F2 internal error", "Unexpected anchor-stage failure.", "Check F2 logs and add a more specific error code."),

    ErrorCode.F3_IN_001: _info(ErrorCode.F3_IN_001, "Invalid F3 input", "Intent extraction received invalid anchored content.", "Pass anchored evidence from F2, not raw text."),
    ErrorCode.F3_SCHEMA_001: _info(ErrorCode.F3_SCHEMA_001, "F3 intent schema invalid", "NormalizedInvestmentIntent validation failed.", "Fix intent extractor output and required ids."),
    ErrorCode.F3_PARSE_001: _info(ErrorCode.F3_PARSE_001, "F3 intent parse failed", "The extractor could not identify a valid investment intent.", "Inspect evidence spans and extraction rules."),
    ErrorCode.F3_EXT_001: _info(ErrorCode.F3_EXT_001, "F3 LLM extraction failed", "Intent extraction LLM dependency failed.", "Check LLM provider health and structured output."),
    ErrorCode.F3_TMO_001: _info(ErrorCode.F3_TMO_001, "F3 extraction timeout", "Intent extraction exceeded its time budget.", "Reduce input size or split extraction batches."),
    ErrorCode.F3_STATE_001: _info(ErrorCode.F3_STATE_001, "F3 trace state invalid", "Intent trace does not align with upstream evidence.", "Ensure intent_id and evidence_span_ids are generated from F2."),
    ErrorCode.F3_INT_001: _info(ErrorCode.F3_INT_001, "F3 internal error", "Unexpected intent-stage failure.", "Check F3 logs and add a narrower code."),

    ErrorCode.F4_IN_001: _info(ErrorCode.F4_IN_001, "Invalid F4 input", "Policy mapping received invalid intent input.", "Pass canonical NormalizedInvestmentIntent from F3."),
    ErrorCode.F4_POLICY_001: _info(ErrorCode.F4_POLICY_001, "F4 policy rejected intent", "The policy layer rejected a non-actionable or unsafe intent.", "Inspect rejection_reason and policy rule metadata."),
    ErrorCode.F4_POLICY_002: _info(ErrorCode.F4_POLICY_002, "F4 no matching policy", "No policy rule could map the intent.", "Add or adjust a policy rule for the intent type."),
    ErrorCode.F4_SCHEMA_001: _info(ErrorCode.F4_SCHEMA_001, "F4 policy schema invalid", "PolicyMappingResult or PolicyMappedIntent validation failed.", "Fix policy mapper output and ids."),
    ErrorCode.F4_STATE_001: _info(ErrorCode.F4_STATE_001, "F4 policy state invalid", "Policy mapping state is inconsistent with the intent trace.", "Check intent_id, policy_id, and mapping diagnostics."),
    ErrorCode.F4_EXT_001: _info(ErrorCode.F4_EXT_001, "F4 policy dependency failed", "A policy lookup dependency failed.", "Check policy data source availability."),
    ErrorCode.F4_INT_001: _info(ErrorCode.F4_INT_001, "F4 internal error", "Unexpected policy-stage failure.", "Check F4 logs and add a narrower code."),

    ErrorCode.F5_IN_001: _info(ErrorCode.F5_IN_001, "Invalid F5 input", "Execution received invalid policy-mapped intent.", "Pass PolicyMappingResult from F4, not raw text."),
    ErrorCode.F5_SCHEMA_001: _info(ErrorCode.F5_SCHEMA_001, "F5 trade action schema invalid", "TradeAction or ExecutionTiming validation failed.", "Include intent_id, policy_id, evidence_span_ids, and four execution clocks."),
    ErrorCode.F5_STATE_001: _info(ErrorCode.F5_STATE_001, "F5 canonical trace invalid", "TradeAction trace is missing canonical upstream ids.", "Build actions through the F3->F4->F5 constructor."),
    ErrorCode.F5_POLICY_001: _info(ErrorCode.F5_POLICY_001, "F5 policy guard failed", "Execution attempted an action forbidden by policy.", "Inspect policy guard result before constructing TradeAction."),
    ErrorCode.F5_EXT_001: _info(ErrorCode.F5_EXT_001, "F5 execution dependency failed", "Execution or market dependency failed.", "Check market data and execution service health."),
    ErrorCode.F5_TMO_001: _info(ErrorCode.F5_TMO_001, "F5 execution timeout", "Trade action construction or execution exceeded timeout.", "Retry with smaller batches or inspect dependency latency."),
    ErrorCode.F5_INT_001: _info(ErrorCode.F5_INT_001, "F5 internal error", "Unexpected execution-stage failure.", "Check F5 logs and add a narrower code."),

    ErrorCode.F6_IN_001: _info(ErrorCode.F6_IN_001, "Invalid F6 review input", "Review or RLHF endpoint received invalid feedback input.", "Validate review payload and required action ids."),
    ErrorCode.F6_NTF_001: _info(ErrorCode.F6_NTF_001, "F6 review item not found", "The requested review item does not exist.", "Check review id and reviewed data directory."),
    ErrorCode.F6_SCHEMA_001: _info(ErrorCode.F6_SCHEMA_001, "F6 feedback schema invalid", "RLHFFeedback validation failed.", "Fix feedback payload fields and labels."),
    ErrorCode.F6_STATE_001: _info(ErrorCode.F6_STATE_001, "F6 review state invalid", "Review state transition is not allowed.", "Inspect current review state before updating."),
    ErrorCode.F6_INT_001: _info(ErrorCode.F6_INT_001, "F6 internal error", "Unexpected review-stage failure.", "Check F6 route and service logs."),

    ErrorCode.F7_IN_001: _info(ErrorCode.F7_IN_001, "Invalid F7 timeline input", "Timeline engine received invalid KOL or action inputs.", "Pass reviewed actions and valid KOL identifiers."),
    ErrorCode.F7_NTF_001: _info(ErrorCode.F7_NTF_001, "F7 timeline not found", "The requested timeline or KOL state does not exist.", "Check KOL id and timeline storage."),
    ErrorCode.F7_SCHEMA_001: _info(ErrorCode.F7_SCHEMA_001, "F7 timeline schema invalid", "KOLTimeline or ViewpointState validation failed.", "Fix timeline schema output."),
    ErrorCode.F7_STATE_001: _info(ErrorCode.F7_STATE_001, "F7 timeline state invalid", "Timeline state cannot be advanced from current inputs.", "Inspect viewpoint transitions and action ordering."),
    ErrorCode.F7_INT_001: _info(ErrorCode.F7_INT_001, "F7 internal error", "Unexpected timeline-stage failure.", "Check F7 logs and add a narrower code."),

    ErrorCode.F8_IN_001: _info(ErrorCode.F8_IN_001, "Invalid F8 backtest input", "Backtest received invalid action, period, or price inputs.", "Validate action list, date range, and symbols."),
    ErrorCode.F8_NTF_001: _info(ErrorCode.F8_NTF_001, "F8 backtest not found", "The requested backtest result does not exist.", "Check backtest id and result storage."),
    ErrorCode.F8_EXT_001: _info(ErrorCode.F8_EXT_001, "F8 price data failed", "Backtest price dependency failed.", "Check data provider health and ticker availability."),
    ErrorCode.F8_TMO_001: _info(ErrorCode.F8_TMO_001, "F8 backtest timeout", "Backtest computation exceeded timeout.", "Reduce date range or cache price data."),
    ErrorCode.F8_INT_001: _info(ErrorCode.F8_INT_001, "F8 internal error", "Unexpected backtest-stage failure.", "Check F8 logs and add a narrower code."),

    ErrorCode.LLM_AUTH_001: _info(ErrorCode.LLM_AUTH_001, "LLM authentication failed", "Provider rejected the configured API credential.", "Refresh provider API key in environment configuration."),
    ErrorCode.LLM_CFG_001: _info(ErrorCode.LLM_CFG_001, "LLM configuration missing", "Required model or provider configuration is missing.", "Check model_config.py and provider environment variables."),
    ErrorCode.LLM_EXT_001: _info(ErrorCode.LLM_EXT_001, "LLM provider unavailable", "The provider returned an unavailable or server error.", "Retry with backoff and inspect provider status."),
    ErrorCode.LLM_EXT_002: _info(ErrorCode.LLM_EXT_002, "LLM provider rate limited", "The provider rejected the request due to quota or rate limits.", "Retry after the provider's retry window or reduce concurrency.", status_code=429),
    ErrorCode.LLM_TMO_001: _info(ErrorCode.LLM_TMO_001, "LLM request timeout", "The provider did not respond before timeout.", "Retry with a longer timeout or smaller prompt."),
    ErrorCode.LLM_SCHEMA_001: _info(ErrorCode.LLM_SCHEMA_001, "LLM structured output invalid", "The provider response did not match the expected Pydantic model.", "Inspect raw completion and tighten constrained decoding or validation."),
    ErrorCode.LLM_INT_001: _info(ErrorCode.LLM_INT_001, "LLM client internal error", "Unexpected failure inside the LLM client wrapper.", "Check client logs and provider response metadata."),

    ErrorCode.WX_AUTH_001: _info(ErrorCode.WX_AUTH_001, "WeChat authentication failed", "WeChat session or cookie is invalid.", "Refresh login session and exporter auth key."),
    ErrorCode.WX_EXT_001: _info(ErrorCode.WX_EXT_001, "WeChat exporter unavailable", "wechat-article-exporter is not reachable or returned an error.", "Start exporter and verify exporter_url."),
    ErrorCode.WX_TMO_001: _info(ErrorCode.WX_TMO_001, "WeChat exporter timeout", "WeChat exporter request exceeded timeout.", "Check exporter health and retry with a longer timeout."),
    ErrorCode.WX_NTF_001: _info(ErrorCode.WX_NTF_001, "WeChat resource not found", "Requested WeChat session, account, or article was not found.", "Check session_id, account_id, or article URL."),

    ErrorCode.BILI_IN_001: _info(ErrorCode.BILI_IN_001, "Invalid Bilibili input", "Bilibili URL or BV id could not be parsed.", "Provide a valid Bilibili URL or BV id."),
    ErrorCode.BILI_EXT_001: _info(ErrorCode.BILI_EXT_001, "Bilibili upstream failed", "Bilibili API, download, or transcription dependency failed.", "Check upstream response and local media tooling."),
    ErrorCode.BILI_NTF_001: _info(ErrorCode.BILI_NTF_001, "Bilibili resource not found", "Requested Bilibili video or generated artifact was not found.", "Verify BV id and artifact path."),

    ErrorCode.FEISHU_AUTH_001: _info(ErrorCode.FEISHU_AUTH_001, "Feishu authentication failed", "Feishu/Lark credentials or tenant access failed.", "Refresh lark-cli auth and app scopes."),
    ErrorCode.FEISHU_EXT_001: _info(ErrorCode.FEISHU_EXT_001, "Feishu upstream failed", "Feishu/Lark API returned an error.", "Inspect lark-cli output and API permissions."),
    ErrorCode.FEISHU_TMO_001: _info(ErrorCode.FEISHU_TMO_001, "Feishu upstream timeout", "Feishu/Lark API request timed out.", "Retry or reduce requested data scope."),

    ErrorCode.NLM_EXT_001: _info(ErrorCode.NLM_EXT_001, "NLM upstream failed", "NLM notebook or document dependency returned an error.", "Check NLM configuration and upstream status."),
    ErrorCode.NLM_TMO_001: _info(ErrorCode.NLM_TMO_001, "NLM upstream timeout", "NLM dependency exceeded timeout.", "Retry with smaller scope or longer timeout."),

    ErrorCode.F0_INDEX_001: _info(ErrorCode.F0_INDEX_001, "F0 index missing or not loaded", "The F0 SQLite index file does not exist or has not been loaded.", "Run POST /api/f0-index/rebuild to create the index.", status_code=503),
    ErrorCode.F0_INDEX_002: _info(ErrorCode.F0_INDEX_002, "F0 index query failed", "A query against the F0 SQLite index failed unexpectedly.", "Check index health via GET /api/f0-index/health. Rebuild if stale.", status_code=500),
    ErrorCode.F0_INDEX_003: _info(ErrorCode.F0_INDEX_003, "F0 index rebuild failed", "The F0 index rebuild process encountered an error.", "Check server logs for details. Ensure manifest files are valid JSON.", status_code=500),
}


def get_error_info(code: ErrorCode | str) -> ErrorCodeInfo:
    """Return catalog metadata for an error code."""

    resolved = coerce_error_code(code)
    return ERROR_CODE_DEFINITIONS[resolved]


def list_error_codes() -> list[ErrorCodeInfo]:
    """Return all error-code definitions in enum order."""

    return [ERROR_CODE_DEFINITIONS[code] for code in ErrorCode]


def lookup_error_codes(
    *,
    domain: str | None = None,
    category: str | None = None,
) -> list[ErrorCodeInfo]:
    """Filter error-code definitions by domain and/or category."""

    domain_value = domain.upper() if domain else None
    category_value = category.upper() if category else None
    return [
        info
        for info in list_error_codes()
        if (domain_value is None or info.domain == domain_value)
        and (category_value is None or info.category == category_value)
    ]


def iter_missing_definitions() -> Iterable[ErrorCode]:
    """Yield enum members that do not have lookup metadata."""

    for code in ErrorCode:
        if code not in ERROR_CODE_DEFINITIONS:
            yield code


__all__ = [
    "CATEGORY_STATUS",
    "ERROR_CODE_DEFINITIONS",
    "ErrorCode",
    "ErrorCodeInfo",
    "coerce_error_code",
    "get_error_info",
    "iter_missing_definitions",
    "list_error_codes",
    "lookup_error_codes",
    "parse_error_code",
]
