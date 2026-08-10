/**
 * Types + pure derivations for the single-KOL 观点潮汐快照 (viewpoint tide snapshot).
 * Ported verbatim from the Finer OS dashboard fixtures; the derivation logic is the
 * contract (TimelineSummary / hit-rate / ticker rotation) and is data-source-agnostic.
 *
 * The retail demo feeds these functions a FROZEN, ANONYMIZED snapshot of real F5
 * canonical TradeActions (see ./data.json). No fabricated personas here.
 *   - SnapshotViewpoint ← one F5 TradeAction wrapped with its real signal timestamp
 *   - SnapshotSummary   ← timeline/models.py::TimelineSummary
 *   - KOLSnapshotData    ← timeline/models.py::KOLTimeline + KOL meta
 * return_pct is F8 完全跟单 P&L, already direction-adjusted (正=判断对/盈, 负=判断错/亏).
 */

import type { TradingStyleProfile } from "./contracts-style";

export type ViewpointDirection =
  | "bullish"
  | "bearish"
  | "neutral"
  | "watchlist"
  | "risk_warning";

export type ValidationStatus =
  | "verified"
  | "pending"
  | "failed"
  | "under_review";

export type CanonicalTraceStatus = "canonical" | "partial" | "non_canonical";

/** One viewpoint = one F5 TradeAction wrapped with its timeline timestamp. */
export interface SnapshotViewpoint {
  id: string; // TradeAction.trade_action_id
  timestamp: string; // ISO; TimelineEntry.timestamp
  ticker: string; // target.ticker_normalized
  companyName: string; // target.company_name
  market: string; // target.market
  direction: ViewpointDirection; // TradeAction.direction
  confidence: number; // 0-1; TradeAction.confidence
  validationStatus: ValidationStatus; // TimelineEntry.validation_status
  summary: string; // short headline derived from intent/rationale
  evidenceText: string; // source.evidence_text (KOL 原话)
  returnPct: number | null; // backtest_result.return_pct (null = 未回测/未触发)
  holdingDays: number | null; // backtest_result.holding_days
  traceStatus: CanonicalTraceStatus; // TradeAction.canonical_trace_status
  actionType?: string; // action_chain[0].action_type; "watch" = opinion tier (非可执行)
}

/** Mirrors timeline/models.py::TimelineSummary. */
export interface SnapshotSummary {
  totalActions: number;
  bullishCount: number;
  bearishCount: number;
  neutralCount: number;
  watchlistCount: number;
  riskWarningCount: number;
  tickersCovered: string[];
  dateRange: [string, string] | null;
  avgConfidence: number;
  verifiedCount: number;
  pendingCount: number;
}

export interface KOLSnapshotData {
  kolId: string;
  kolName: string;
  handle: string;
  style: string; // trading style label
  platform: string;
  generatedAt: string; // report generation timestamp
  /** AI synthesis of the KOL's recent stance — in prod this is F7/LLM-derived. */
  narrative: string;
  viewpoints: SnapshotViewpoint[]; // time-descending, like KOLTimeline.entries
  /** 交易风格画像（declared+observed 双层）；live 来自 GET /api/kol/style/{id}。 */
  tradingStyle?: TradingStyleProfile | null;
}


// ---- derivations (mirror backend TimelineSummary computation) ---------------

/** Compute the summary block from a (possibly filtered) viewpoint list. */
export function deriveSummary(viewpoints: SnapshotViewpoint[]): SnapshotSummary {
  const count = (d: ViewpointDirection) =>
    viewpoints.filter((v) => v.direction === d).length;

  const tickers = Array.from(new Set(viewpoints.map((v) => v.ticker))).sort();
  const times = viewpoints.map((v) => v.timestamp).sort();
  const avg =
    viewpoints.length === 0
      ? 0
      : viewpoints.reduce((s, v) => s + v.confidence, 0) / viewpoints.length;

  return {
    totalActions: viewpoints.length,
    bullishCount: count("bullish"),
    bearishCount: count("bearish"),
    neutralCount: count("neutral"),
    watchlistCount: count("watchlist"),
    riskWarningCount: count("risk_warning"),
    tickersCovered: tickers,
    dateRange: times.length ? [times[0], times[times.length - 1]] : null,
    avgConfidence: avg,
    verifiedCount: viewpoints.filter((v) => v.validationStatus === "verified")
      .length,
    pendingCount: viewpoints.filter((v) => v.validationStatus === "pending")
      .length,
  };
}

/** Net directional lean: 多 minus 空/风险. Drives the hero verdict. */
export function netStance(s: SnapshotSummary): number {
  return s.bullishCount - s.bearishCount - s.riskWarningCount;
}

export interface SnapshotHighlights {
  topConfidence: SnapshotViewpoint | null;
  bestReturn: SnapshotViewpoint | null;
  worstReturn: SnapshotViewpoint | null;
  hitRate: number | null; // positive-return share among settled trades
  settledCount: number;
}

/** Settled = backtested with a real holding period (excludes pending/untriggered). */
function isSettled(v: SnapshotViewpoint): boolean {
  return v.returnPct !== null && (v.holdingDays ?? 0) > 0;
}

export function deriveHighlights(
  viewpoints: SnapshotViewpoint[],
): SnapshotHighlights {
  const settled = viewpoints.filter(isSettled);
  const byReturn = [...settled].sort(
    (a, b) => (b.returnPct ?? 0) - (a.returnPct ?? 0),
  );
  const topConfidence = [...viewpoints].sort(
    (a, b) => b.confidence - a.confidence,
  )[0];
  const positives = settled.filter((v) => (v.returnPct ?? 0) > 0).length;

  return {
    topConfidence: topConfidence ?? null,
    bestReturn: byReturn[0] ?? null,
    worstReturn: byReturn[byReturn.length - 1] ?? null,
    hitRate: settled.length ? positives / settled.length : null,
    settledCount: settled.length,
  };
}

export interface TickerRotationRow {
  ticker: string;
  companyName: string;
  market: string;
  count: number;
  net: number; // 多 minus 空/风险 for this ticker
  latestDirection: ViewpointDirection;
  avgReturn: number | null; // mean return across settled trades, null if none settled
  settledCount: number;
}

/**
 * Per-ticker stance + realized performance ("标的兑现榜"), the KOL analogue of
 * the reference report's sector rotation / net-inflow ranking. Settled tickers
 * rank by avg realized return (winners first); unsettled tickers sink to the end.
 */
export function deriveTickerRotation(
  viewpoints: SnapshotViewpoint[],
): TickerRotationRow[] {
  const groups = new Map<string, SnapshotViewpoint[]>();
  for (const v of viewpoints) {
    const arr = groups.get(v.ticker) ?? [];
    arr.push(v);
    groups.set(v.ticker, arr);
  }

  const rows: TickerRotationRow[] = [];
  for (const [ticker, vps] of groups) {
    const sorted = [...vps].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    const settled = vps.filter(isSettled);
    const net = vps.reduce(
      (n, v) =>
        n +
        (v.direction === "bullish"
          ? 1
          : v.direction === "bearish" || v.direction === "risk_warning"
            ? -1
            : 0),
      0,
    );
    rows.push({
      ticker,
      companyName: sorted[0].companyName,
      market: sorted[0].market,
      count: vps.length,
      net,
      latestDirection: sorted[0].direction,
      avgReturn: settled.length
        ? settled.reduce((s, v) => s + (v.returnPct ?? 0), 0) / settled.length
        : null,
      settledCount: settled.length,
    });
  }

  return rows.sort((a, b) => {
    // settled first, ranked by avg return desc; unsettled last by count desc
    if (a.avgReturn === null && b.avgReturn === null) return b.count - a.count;
    if (a.avgReturn === null) return 1;
    if (b.avgReturn === null) return -1;
    return b.avgReturn - a.avgReturn;
  });
}
