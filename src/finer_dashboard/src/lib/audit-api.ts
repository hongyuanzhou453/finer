/**
 * Data layer for the /audit view.
 *
 * Toggles between local fixtures (default this round) and the live backend
 * canonical-trace API via the NEXT_PUBLIC_AUDIT_USE_FIXTURES env var.
 *
 * Backend contract (NOT yet implemented — see
 * docs/specs/2026-06-04-dashboard-audit-trace-frontend.md §7):
 *   GET /api/audit/actions               -> { actions: TradeActionSummary[], total }
 *   GET /api/audit/actions/{id}/trace    -> AuditTraceBundle
 */
import { apiFetch } from "@/lib/api-client";
import type {
  AuditTraceBundle,
  CanonicalTraceStatus,
  TradeActionSummary,
} from "@/lib/contracts";
import { AUDIT_BUNDLES, AUDIT_SUMMARIES } from "@/lib/fixtures/audit-trace";

/** True when the view is backed by local fixtures rather than the live backend. */
export const AUDIT_USE_FIXTURES =
  process.env.NEXT_PUBLIC_AUDIT_USE_FIXTURES !== "false";

export type AuditActionFilters = {
  traceStatus?: CanonicalTraceStatus | "all";
  kolId?: string | "all";
  ticker?: string;
};

/** Fetch the TradeAction list for the left rail. */
export async function getAuditActions(
  filters?: AuditActionFilters,
): Promise<TradeActionSummary[]> {
  if (AUDIT_USE_FIXTURES) {
    return AUDIT_SUMMARIES.filter((s) => matchesFilters(s, filters));
  }
  const params = new URLSearchParams();
  if (filters?.traceStatus && filters.traceStatus !== "all") {
    params.set("trace_status", filters.traceStatus);
  }
  if (filters?.kolId && filters.kolId !== "all") {
    params.set("kol_id", filters.kolId);
  }
  if (filters?.ticker) params.set("ticker", filters.ticker);
  const qs = params.toString();
  const res = await apiFetch<{ actions: TradeActionSummary[]; total: number }>(
    `/api/audit/actions${qs ? `?${qs}` : ""}`,
  );
  return res.actions ?? [];
}

/** Fetch the full F0→F5 trace bundle for one TradeAction. */
export async function getAuditTrace(
  tradeActionId: string,
): Promise<AuditTraceBundle | null> {
  if (AUDIT_USE_FIXTURES) {
    return AUDIT_BUNDLES[tradeActionId] ?? null;
  }
  return apiFetch<AuditTraceBundle>(
    `/api/audit/actions/${encodeURIComponent(tradeActionId)}/trace`,
  );
}

function matchesFilters(
  s: TradeActionSummary,
  f?: AuditActionFilters,
): boolean {
  if (!f) return true;
  if (
    f.traceStatus &&
    f.traceStatus !== "all" &&
    s.canonical_trace_status !== f.traceStatus
  ) {
    return false;
  }
  if (f.kolId && f.kolId !== "all" && s.kol_id !== f.kolId) return false;
  if (f.ticker && !s.ticker.includes(f.ticker)) return false;
  return true;
}
