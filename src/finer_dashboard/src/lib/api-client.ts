/**
 * Unified API client for Finer Dashboard.
 *
 * Handles:
 * - Canonical `{ok, data/error}` envelope parsing
 * - Raw (non-envelope) backend responses (files, stats, etc.)
 * - Typed errors with code, message, request_id
 * - Optional automatic retry with exponential backoff
 *
 * Mirrors backend error format from src/finer/errors/exceptions.py.
 */

import type { ApiErrorDetails, ApiErrorEnvelope, BacktestResult, BacktestSummary, KOLListItemRaw, KOLRatingResponse } from "./contracts";
import { isApiError } from "./contracts";

// =============================================================================
// Error Classes
// =============================================================================

/**
 * Normalize backend snake_case details to camelCase ApiErrorDetails.
 */
function normalizeDetails(
  raw: Record<string, unknown> | undefined,
): ApiErrorDetails | undefined {
  if (!raw) return undefined;
  return {
    requestId: (raw.request_id as string) ?? undefined,
    stage: (raw.stage as string) ?? undefined,
    operation: (raw.operation as string) ?? undefined,
    sourceChannel: (raw.source_channel as string) ?? undefined,
    retryable: (raw.retryable as boolean) ?? undefined,
    fixHint: (raw.fix_hint as string) ?? undefined,
    contentId: (raw.content_id as string) ?? undefined,
    importRunId: (raw.import_run_id as string) ?? undefined,
    externalSourceId: (raw.external_source_id as string) ?? undefined,
    exceptionType: (raw.exception_type as string) ?? undefined,
  };
}

/**
 * Structured API error matching the backend FinerError.to_payload format.
 * Thrown by apiFetch when the backend returns a non-2xx or `{ok: false}` response.
 */
export class ApiError extends Error {
  /** Stable error code, e.g. "SYS_NTF_001". */
  readonly code: string;
  /** HTTP status code (0 if request never reached the server). */
  readonly status: number;
  /** Server-provided request_id for log correlation. */
  readonly requestId: string | undefined;
  /** Structured error details from the server (camelCase). */
  readonly details: ApiErrorDetails | undefined;
  /** Actionable fix suggestion from the server or client-side lookup. */
  readonly fixHint: string | undefined;
  /** Whether the backend indicates this error is retryable. */
  readonly retryable: boolean;

  constructor(
    code: string,
    message: string,
    status: number,
    requestId?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;

    const normalized = normalizeDetails(details);
    this.details = normalized;
    this.requestId = requestId ?? normalized?.requestId;
    this.fixHint = normalized?.fixHint;
    this.retryable = normalized?.retryable ?? isRetryable(status);
  }

  /** Human-readable summary for toast / console display. */
  get displayMessage(): string {
    return `[${this.code}] ${this.message}`;
  }
}

// =============================================================================
// Options
// =============================================================================

export type ApiClientOptions = {
  /** Base URL prefix for relative paths (default: ""). */
  baseUrl?: string;
  /** Maximum retries for transient errors (default: 0 — no retry). */
  maxRetries?: number;
  /** Base delay in ms for exponential backoff (default: 1000). */
  retryBaseDelay?: number;
  /** Request timeout in ms (default: 30000). */
  timeout?: number;
  /** Additional headers merged into every request. */
  headers?: Record<string, string>;
};

const DEFAULT_OPTIONS: Required<ApiClientOptions> = {
  baseUrl: "",
  maxRetries: 0,
  retryBaseDelay: 1000,
  timeout: 30000,
  headers: {},
};

// =============================================================================
// Retry logic
// =============================================================================

function isRetryable(status: number): boolean {
  return status === 429 || status >= 500;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// =============================================================================
// Response parsing
// =============================================================================

/**
 * Parse a Response object into a typed result.
 *
 * Strategy:
 * 1. Try to parse JSON body.
 * 2. If body matches `{ok: false, error: {...}}` -> throw ApiError.
 * 3. If body matches `{ok: true, data: ...}` -> return data.
 * 4. Otherwise -> return raw body (for non-envelope routes like files, stats).
 * 5. On non-2xx without envelope -> throw generic ApiError.
 */
async function parseResponse<T>(response: Response): Promise<T> {
  let body: unknown;

  try {
    body = await response.json();
  } catch {
    // Non-JSON response (e.g. streams/download returns binary)
    if (!response.ok) {
      throw new ApiError(
        "SYS_INT_001",
        `Non-JSON response with status ${response.status}`,
        response.status,
      );
    }
    // Non-JSON success — return as-is (caller must expect non-JSON)
    return undefined as T;
  }

  // Canonical error envelope
  if (isApiError(body)) {
    const envelope = body as ApiErrorEnvelope;
    throw new ApiError(
      envelope.error.code,
      envelope.error.message,
      response.status,
      envelope.error.details?.request_id as string | undefined,
      envelope.error.details,
    );
  }

  // Canonical success envelope
  if (
    typeof body === "object" &&
    body !== null &&
    "ok" in body &&
    (body as Record<string, unknown>).ok === true &&
    "data" in body
  ) {
    return (body as { ok: true; data: T }).data;
  }

  // Non-2xx without envelope (shouldn't happen if backend error handlers are registered)
  if (!response.ok) {
    throw new ApiError(
      "SYS_INT_001",
      `HTTP ${response.status}`,
      response.status,
    );
  }

  // Non-envelope success (raw data from legacy routes like /api/files, /api/stats)
  return body as T;
}

// =============================================================================
// Core fetch wrapper
// =============================================================================

/**
 * Typed fetch wrapper that handles the canonical error envelope.
 *
 * @example
 * // Envelope route (returns unwrapped data)
 * const files = await apiFetch<AssetFile[]>("/api/files?tier=F1");
 *
 * @example
 * // POST with body
 * const result = await apiFetch<{ success: boolean }>("/api/review", {
 *   method: "POST",
 *   body: reviewPayload,
 * });
 */
export async function apiFetch<T>(
  path: string,
  init: {
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
    signal?: AbortSignal;
    /** Override per-request options. */
    clientOptions?: Partial<ApiClientOptions>;
  } = {},
): Promise<T> {
  const opts = { ...DEFAULT_OPTIONS, ...init.clientOptions };
  const url = path.startsWith("http") ? path : `${opts.baseUrl}${path}`;

  const fetchHeaders: Record<string, string> = {
    ...opts.headers,
    ...init.headers,
  };

  if (init.body !== undefined && !(init.body instanceof FormData)) {
    fetchHeaders["Content-Type"] = fetchHeaders["Content-Type"] ?? "application/json";
  }

  const fetchBody =
    init.body === undefined
      ? undefined
      : init.body instanceof FormData
        ? init.body
        : JSON.stringify(init.body);

  let lastError: ApiError | undefined;

  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    if (attempt > 0) {
      const delay = opts.retryBaseDelay * Math.pow(2, attempt - 1);
      await sleep(delay);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), opts.timeout);

    // Combine external signal with timeout
    if (init.signal) {
      init.signal.addEventListener("abort", () => controller.abort());
    }

    try {
      const response = await fetch(url, {
        method: init.method ?? "GET",
        headers: fetchHeaders,
        body: fetchBody,
        signal: controller.signal,
        cache: "no-store",
      });

      clearTimeout(timeoutId);

      // Retry on transient errors
      if (isRetryable(response.status) && attempt < opts.maxRetries) {
        lastError = new ApiError(
          "SYS_TMO_001",
          `Transient error (attempt ${attempt + 1}/${opts.maxRetries + 1})`,
          response.status,
        );
        continue;
      }

      return await parseResponse<T>(response);
    } catch (err) {
      clearTimeout(timeoutId);

      if (err instanceof ApiError) {
        lastError = err;
        // Retry transient errors
        if (isRetryable(err.status) && attempt < opts.maxRetries) {
          continue;
        }
        throw err;
      }

      // Network / timeout errors
      const message =
        err instanceof DOMException && err.name === "AbortError"
          ? "Request timed out"
          : err instanceof TypeError
            ? "Network error — backend may be unreachable"
            : `Request failed: ${String(err)}`;

      lastError = new ApiError("SYS_TMO_001", message, 0);

      if (attempt < opts.maxRetries) {
        continue;
      }

      throw lastError;
    }
  }

  // Should not reach here, but just in case
  throw lastError ?? new ApiError("SYS_INT_001", "Unknown error", 0);
}

// =============================================================================
// Convenience methods
// =============================================================================

/** GET request. Returns unwrapped data. */
export function apiGet<T>(
  path: string,
  options?: Partial<ApiClientOptions>,
): Promise<T> {
  return apiFetch<T>(path, { clientOptions: options });
}

/** POST request with JSON body. Returns unwrapped data. */
export function apiPost<T>(
  path: string,
  body: unknown,
  options?: Partial<ApiClientOptions>,
): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body, clientOptions: options });
}

/** PUT request with JSON body. Returns unwrapped data. */
export function apiPut<T>(
  path: string,
  body: unknown,
  options?: Partial<ApiClientOptions>,
): Promise<T> {
  return apiFetch<T>(path, { method: "PUT", body, clientOptions: options });
}

/** DELETE request. Returns unwrapped data. */
export function apiDelete<T>(
  path: string,
  options?: Partial<ApiClientOptions>,
): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE", clientOptions: options });
}

// =============================================================================
// F8 Backtest API
// =============================================================================

/** Run a new backtest. */
export async function runBacktest(params: {
  trade_actions: Array<Record<string, unknown>>;
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  kol_id?: string;
  backtest_name?: string;
}): Promise<{ backtest_id: string; result: BacktestResult }> {
  return apiFetch("/api/backtest/run", {
    method: "POST",
    body: params,
  });
}

/** Get a specific backtest result by ID. */
export async function getBacktestResult(
  backtestId: string,
): Promise<BacktestResult> {
  return apiFetch(`/api/backtest/results/${backtestId}`);
}

/** List all backtest results (summaries). */
export async function listBacktestResults(params?: {
  kol_id?: string;
  limit?: number;
}): Promise<BacktestSummary[]> {
  const query = new URLSearchParams();
  if (params?.kol_id) query.set("kol_id", params.kol_id);
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  const raw = await apiFetch<{ results: BacktestSummary[] }>(
    `/api/backtest/results${qs ? `?${qs}` : ""}`,
  );
  return raw.results ?? [];
}

/** Delete a backtest result. */
export async function deleteBacktestResult(
  backtestId: string,
): Promise<{ deleted: boolean }> {
  return apiFetch(`/api/backtest/results/${backtestId}`, {
    method: "DELETE",
  });
}

// =============================================================================
// KOL API
// =============================================================================

/** List all KOLs with enriched rating data. Returns raw backend shape — use kolListItemToKOL adapter. */
export async function listKOLs(): Promise<KOLListItemRaw[]> {
  return apiFetch("/api/kol/list/enriched");
}

/** Get detailed rating for a specific KOL. */
export async function getKOLRating(
  kolId: string,
): Promise<KOLRatingResponse> {
  return apiFetch(`/api/kol/rating/${kolId}`);
}
