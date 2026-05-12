"use client";

import React from "react";
import { AlertTriangle, Copy, ExternalLink, RefreshCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { ERROR_CODE_DESCRIPTIONS } from "@/lib/contracts";
import type { ApiError } from "@/lib/api-client";

// =============================================================================
// Types
// =============================================================================

export type ErrorPanelProps = {
  /** The ApiError to display. Null hides the panel. */
  error: ApiError | null;
  /** Called when user clicks the retry button. */
  onRetry?: () => void;
  /** Called when user dismisses the panel. */
  onDismiss?: () => void;
  /** Additional CSS classes. */
  className?: string;
  /** Compact mode for inline use (e.g. inside table rows). */
  compact?: boolean;
};

// =============================================================================
// Helpers
// =============================================================================

function getCodeMeta(code: string) {
  return ERROR_CODE_DESCRIPTIONS[code] ?? null;
}

function copyToClipboard(text: string): void {
  navigator.clipboard.writeText(text).catch(() => {
    // Fallback: select + copy
    const el = document.createElement("textarea");
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  });
}

// =============================================================================
// Severity classification
// =============================================================================

type Severity = "error" | "warning" | "info";

function getSeverity(error: ApiError): Severity {
  if (error.status === 0) return "error"; // network failure
  if (error.status >= 500) return "error";
  if (error.status === 429) return "warning";
  if (error.status >= 400) return "info";
  return "error";
}

const SEVERITY_STYLES: Record<Severity, { border: string; bg: string; icon: string; badge: string }> = {
  error: {
    border: "border-red-500/30",
    bg: "bg-red-500/5",
    icon: "text-red-400",
    badge: "bg-red-500/20 text-red-300",
  },
  warning: {
    border: "border-amber-500/30",
    bg: "bg-amber-500/5",
    icon: "text-amber-400",
    badge: "bg-amber-500/20 text-amber-300",
  },
  info: {
    border: "border-blue-500/30",
    bg: "bg-blue-500/5",
    icon: "text-blue-400",
    badge: "bg-blue-500/20 text-blue-300",
  },
};

// =============================================================================
// Component
// =============================================================================

export function ErrorPanel({
  error,
  onRetry,
  onDismiss,
  className,
  compact = false,
}: ErrorPanelProps) {
  if (!error) return null;

  const severity = getSeverity(error);
  const styles = SEVERITY_STYLES[severity];
  const codeMeta = getCodeMeta(error.code);

  const handleCopy = () => {
    const text = [
      `Error Code: ${error.code}`,
      `Message: ${error.message}`,
      error.requestId ? `Request ID: ${error.requestId}` : null,
      error.status ? `HTTP Status: ${error.status}` : null,
      error.details?.stage ? `Stage: ${error.details.stage}` : null,
      error.details?.operation ? `Operation: ${error.details.operation}` : null,
      `Retryable: ${error.retryable ? "Yes" : "No"}`,
      error.fixHint ? `Fix Hint (server): ${error.fixHint}` : null,
      codeMeta ? `Root Cause: ${codeMeta.rootCause}` : null,
      codeMeta ? `Fix Hint (code): ${codeMeta.fixHint}` : null,
    ]
      .filter(Boolean)
      .join("\n");
    copyToClipboard(text);
  };

  if (compact) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-md border px-3 py-2 text-sm",
          styles.border,
          styles.bg,
          className,
        )}
      >
        <AlertTriangle className={cn("h-4 w-4 shrink-0", styles.icon)} />
        <span className="truncate font-mono text-xs">{error.code}</span>
        <span className="truncate text-neutral-300">{error.message}</span>
        {error.retryable !== undefined && (
          <span
            className={cn(
              "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium",
              error.retryable
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-red-500/20 text-red-400",
            )}
          >
            {error.retryable ? "可重试" : "不可重试"}
          </span>
        )}
        {onRetry && (
          <button
            onClick={onRetry}
            className="ml-auto shrink-0 rounded p-1 text-neutral-400 hover:bg-neutral-700 hover:text-neutral-200"
            aria-label="Retry"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border p-4",
        styles.border,
        styles.bg,
        className,
      )}
      role="alert"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <AlertTriangle className={cn("h-5 w-5 shrink-0", styles.icon)} />
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-medium",
                styles.badge,
              )}
            >
              {error.code}
            </span>
            {codeMeta && (
              <span className="text-sm font-medium text-neutral-200">
                {codeMeta.title}
              </span>
            )}
          </div>
        </div>

        {onDismiss && (
          <button
            onClick={onDismiss}
            className="shrink-0 rounded p-1 text-neutral-500 hover:bg-neutral-700 hover:text-neutral-300"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Message */}
      <p className="mt-2.5 text-sm text-neutral-300">{error.message}</p>

      {/* Root cause & fix hint */}
      {codeMeta && (
        <div className="mt-3 space-y-1.5 text-xs text-neutral-400">
          <p>
            <span className="font-medium text-neutral-300">Root cause:</span>{" "}
            {codeMeta.rootCause}
          </p>
          {!error.fixHint && (
            <p>
              <span className="font-medium text-neutral-300">Fix hint:</span>{" "}
              {codeMeta.fixHint}
            </p>
          )}
        </div>
      )}

      {/* Server-provided fix hint */}
      {error.fixHint && (
        <div className="mt-3 rounded-md bg-neutral-800/60 px-3 py-2 text-xs text-neutral-300">
          <span className="mr-1.5">💡</span>
          {error.fixHint}
        </div>
      )}

      {/* Retryable badge + Metadata row */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-neutral-500">
        {error.retryable !== undefined && (
          <span
            className={cn(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium",
              error.retryable
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-red-500/20 text-red-400",
            )}
          >
            {error.retryable ? "Retryable" : "Not retryable"}
          </span>
        )}
        {error.requestId && (
          <span className="flex items-center gap-1.5 font-mono">
            <span className="text-neutral-400">Request ID:</span>
            {error.requestId}
          </span>
        )}
        {error.details?.stage && (
          <span className="flex items-center gap-1.5">
            <span className="text-neutral-400">Stage:</span>
            {error.details.stage}
          </span>
        )}
        {error.details?.operation && (
          <span className="flex items-center gap-1.5">
            <span className="text-neutral-400">Operation:</span>
            {error.details.operation}
          </span>
        )}
        {error.status > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="text-neutral-400">HTTP:</span>
            {error.status}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="mt-3 flex items-center gap-2">
        {onRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md bg-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        )}
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 rounded-md bg-neutral-800 px-3 py-1.5 text-xs font-medium text-neutral-400 hover:bg-neutral-700 hover:text-neutral-300"
        >
          <Copy className="h-3.5 w-3.5" />
          Copy error details
        </button>
        <a
          href={`http://127.0.0.1:8000/api/system/error-codes`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          View error code docs
        </a>
      </div>
    </div>
  );
}
