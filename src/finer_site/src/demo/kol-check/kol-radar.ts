/**
 * Types + pure derivations for the KOL scorecard (信誉分 / 命中率 / 收益榜 / net stance).
 * Ported verbatim from the Finer OS dashboard radar fixtures — only the fabricated
 * multi-persona sample data was removed; every derivation takes a `data: KOLRadarData`
 * argument, so the retail demo passes a FROZEN ANONYMIZED single-KOL snapshot built
 * from real F5 canonical TradeActions (see ./data.json).
 *
 * 信誉分 (0–99): hit rate shrunk toward a 0.5 prior by sample size (see
 *   deriveCredibilityBoard) — a small record can't outrank a long consistent one.
 * return_pct semantics: F8 完全跟单 P&L, already direction-adjusted (正=判断对/盈,
 *   负=判断错/亏). A bearish call that correctly called a drop has positive return_pct.
 */
import type {
  SnapshotViewpoint,
  ViewpointDirection,
} from "./kol-snapshot";

export type { SnapshotViewpoint, ViewpointDirection } from "./kol-snapshot";

export interface RadarKOL {
  kolId: string;
  name: string;
  handle: string;
  style: string;
  platform: string;
  specialties: string[];
  viewpoints: SnapshotViewpoint[]; // time-descending
}

export type ChangeType =
  | "flip" // 翻向
  | "new_high_conviction" // 新高信念 call
  | "new_call" // 新增观点
  | "stop_loss" // 旧 call 触发止损
  | "score_change" // 信誉分变动
  | "consensus_alert"; // 标的出现共识/分歧异动

export interface RadarChangeEvent {
  id: string;
  type: ChangeType;
  kolId?: string;
  kolName?: string;
  ticker?: string;
  companyName?: string;
  fromDirection?: ViewpointDirection;
  toDirection?: ViewpointDirection;
  detail: string;
  timestamp: string;
  value?: number; // signed magnitude (score delta, return, conviction…)
}

/** Server-computed credibility (single source of truth when present). */
export interface CredibilityOverride {
  credibility: number;
  hitRate: number | null;
  settledCount: number;
  lowSample: boolean;
}

export interface KOLRadarData {
  generatedAt: string;
  periodLabel: string;
  kols: RadarKOL[];
  changes: RadarChangeEvent[];
  /** keyed by kolId; live adapter fills this from /stats/summary — fixture
   * pages omit it and fall back to the client-side derivation. */
  credibilityOverrides?: Record<string, CredibilityOverride>;
}

// ===========================================================================
//  Derivations — the data brain. Block components consume these view-models.
// ===========================================================================

const ACTIONABLE: ViewpointDirection[] = ["bullish", "bearish"];

function isSettled(v: SnapshotViewpoint): boolean {
  return v.returnPct !== null && (v.holdingDays ?? 0) > 0;
}

function dirDelta(d: ViewpointDirection): number {
  return d === "bullish" ? 1 : d === "bearish" || d === "risk_warning" ? -1 : 0;
}

function allViewpoints(data: KOLRadarData): SnapshotViewpoint[] {
  return data.kols.flatMap((k) => k.viewpoints);
}

/** Latest viewpoint per (kol, ticker) — a KOL's *current* stance on a name. */
function latestByKolTicker(kol: RadarKOL): Map<string, SnapshotViewpoint> {
  const m = new Map<string, SnapshotViewpoint>();
  for (const v of kol.viewpoints) {
    const prev = m.get(v.ticker);
    if (!prev || v.timestamp > prev.timestamp) m.set(v.ticker, v);
  }
  return m;
}

// ---- A. Market sentiment ----------------------------------------------------

export interface MarketSentimentVM {
  net: number; // 多 − 空/风险 across each KOL's current stances
  bullishKols: number;
  bearishKols: number;
  neutralKols: number;
  breadth: Record<ViewpointDirection, number>; // by current-stance viewpoint count
  kolCount: number;
  totalViewpoints: number;
  dateRange: [string, string] | null;
  allViewpoints: SnapshotViewpoint[]; // feeds the StanceTide chart
}

export function deriveMarketSentiment(data: KOLRadarData): MarketSentimentVM {
  const all = allViewpoints(data);
  const breadth: Record<ViewpointDirection, number> = {
    bullish: 0,
    bearish: 0,
    neutral: 0,
    watchlist: 0,
    risk_warning: 0,
  };
  let bullishKols = 0;
  let bearishKols = 0;
  let neutralKols = 0;

  for (const k of data.kols) {
    const latest = [...latestByKolTicker(k).values()];
    for (const v of latest) breadth[v.direction] += 1;
    const kolNet = latest.reduce((n, v) => n + dirDelta(v.direction), 0);
    if (kolNet > 0) bullishKols += 1;
    else if (kolNet < 0) bearishKols += 1;
    else neutralKols += 1;
  }

  const net = bullishKols - bearishKols;
  const times = all.map((v) => v.timestamp).sort();

  return {
    net,
    bullishKols,
    bearishKols,
    neutralKols,
    breadth,
    kolCount: data.kols.length,
    totalViewpoints: all.length,
    dateRange: times.length ? [times[0], times[times.length - 1]] : null,
    allViewpoints: all,
  };
}

// ---- B. Change feed ---------------------------------------------------------

export interface ChangeFeedItem extends RadarChangeEvent {
  ageLabel: string; // relative time vs generatedAt, e.g. "今天" / "1 天前" / "8 天前"
}

function relativeAge(fromIso: string, toIso: string): string {
  const days = Math.round(
    (new Date(toIso).getTime() - new Date(fromIso).getTime()) / 86_400_000,
  );
  if (days <= 0) return "今天";
  if (days === 1) return "1 天前";
  return `${days} 天前`;
}

/**
 * Recent changes, newest first, each stamped with a relative age. Fixture supplies
 * the raw events; a live build needs a backend snapshot-diff service (none today).
 */
export function deriveChangeFeed(data: KOLRadarData): ChangeFeedItem[] {
  return [...data.changes]
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
    .map((ev) => ({ ...ev, ageLabel: relativeAge(ev.timestamp, data.generatedAt) }));
}

// ---- C. Credibility board (the spine) --------------------------------------

export interface CredibilityRow {
  kolId: string;
  name: string;
  handle: string;
  style: string;
  specialties: string[];
  credibility: number; // 0–99, sample-size-shrunk hit rate (see deriveCredibilityBoard)
  hitRate: number | null;
  settledCount: number;
  lowSample: boolean; // settled < LOW_SAMPLE_N — score is statistically thin, flag it
  trend: "up" | "flat" | "down";
  netStance: number;
  stanceLabel: "偏多" | "偏空" | "分歧";
  topCall: { companyName: string; direction: ViewpointDirection; confidence: number } | null;
  lastActive: string;
  totalViewpoints: number;
}

/** Hit = positive follow-P&L. return_pct is already direction-adjusted (see header). */
function hitRateOf(vps: SnapshotViewpoint[]): {
  rate: number | null;
  settled: number;
  wins: number;
} {
  const settled = vps.filter(isSettled);
  if (!settled.length) return { rate: null, settled: 0, wins: 0 };
  const wins = settled.filter((v) => (v.returnPct ?? 0) > 0).length;
  return { rate: wins / settled.length, settled: settled.length, wins };
}

function trendOf(vps: SnapshotViewpoint[], generatedAt: string): "up" | "flat" | "down" {
  const cutoff = new Date(generatedAt).getTime() - 45 * 86_400_000;
  const recent = vps.filter(
    (v) => isSettled(v) && new Date(v.timestamp).getTime() >= cutoff,
  );
  if (!recent.length) return "flat";
  const mean = recent.reduce((s, v) => s + (v.returnPct ?? 0), 0) / recent.length;
  return mean > 0.02 ? "up" : mean < -0.02 ? "down" : "flat";
}

const PRIOR_K = 4; // pseudo-observations for the 0.5 prior (sample-size shrinkage)
const LOW_SAMPLE_N = 5; // below this, the score is statistically thin

export function deriveCredibilityBoard(data: KOLRadarData): CredibilityRow[] {
  const rows = data.kols.map((k): CredibilityRow => {
    const { rate, settled, wins } = hitRateOf(k.viewpoints);
    // Shrink the raw hit rate toward a 0.5 prior by sample size, so a tiny 4/4
    // record can't outrank a long, consistently-good one (4/4 → 0.75, not 1.0).
    const adjRate = settled === 0 ? 0.5 : (wins + PRIOR_K * 0.5) / (settled + PRIOR_K);
    let credibility = Math.max(0, Math.min(99, Math.round(40 + 55 * adjRate)));
    let hitRate = rate;
    let settledCount = settled;
    let lowSample = settled < LOW_SAMPLE_N;

    // Server-computed credibility is the source of truth when provided
    // (live adapter fills it from /stats/summary; fixtures don't).
    const override = data.credibilityOverrides?.[k.kolId];
    if (override) {
      credibility = override.credibility;
      hitRate = override.hitRate;
      settledCount = override.settledCount;
      lowSample = override.lowSample;
    }

    const latest = [...latestByKolTicker(k).values()];
    const netStance = latest.reduce((n, v) => n + dirDelta(v.direction), 0);
    const stanceLabel = netStance >= 2 ? "偏多" : netStance <= -2 ? "偏空" : "分歧";

    const actionable = k.viewpoints
      .filter((v) => ACTIONABLE.includes(v.direction))
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0];

    const lastActive = k.viewpoints
      .map((v) => v.timestamp)
      .sort()
      .slice(-1)[0];

    return {
      kolId: k.kolId,
      name: k.name,
      handle: k.handle,
      style: k.style,
      specialties: k.specialties,
      credibility,
      hitRate,
      settledCount,
      lowSample,
      trend: trendOf(k.viewpoints, data.generatedAt),
      netStance,
      stanceLabel,
      topCall: actionable
        ? {
            companyName: actionable.companyName,
            direction: actionable.direction,
            confidence: actionable.confidence,
          }
        : null,
      lastActive,
      totalViewpoints: k.viewpoints.length,
    };
  });

  return rows.sort(
    (a, b) => b.credibility - a.credibility || (b.hitRate ?? 0) - (a.hitRate ?? 0),
  );
}

// ---- D. Actionable calls ----------------------------------------------------

export interface ActionCall {
  id: string;
  kolId: string;
  kolName: string;
  credibility: number;
  ticker: string;
  companyName: string;
  market: string;
  direction: ViewpointDirection;
  confidence: number;
  summary: string;
  evidenceText: string;
  ageDays: number;
  isFresh: boolean; // pending / not yet settled
  score: number; // credibility × confidence × freshness
}

/** Active, actionable calls across all KOLs, ranked credibility × conviction × freshness. */
export function deriveActionableCalls(
  data: KOLRadarData,
  maxAgeDays = 24,
): ActionCall[] {
  const credById = new Map(
    deriveCredibilityBoard(data).map((r) => [r.kolId, r.credibility]),
  );
  const now = new Date(data.generatedAt).getTime();
  const calls: ActionCall[] = [];

  for (const k of data.kols) {
    const latest = latestByKolTicker(k);
    for (const v of latest.values()) {
      if (!ACTIONABLE.includes(v.direction)) continue;
      // opinion tier (watch actions) stays on timelines/consensus but is not
      // presented as a followable call
      if (v.actionType === "watch") continue;
      const ageDays = Math.round((now - new Date(v.timestamp).getTime()) / 86_400_000);
      if (ageDays > maxAgeDays) continue;
      const credibility = credById.get(k.kolId) ?? 50;
      const freshness = Math.max(0.2, 1 - ageDays / 30);
      calls.push({
        id: v.id,
        kolId: k.kolId,
        kolName: k.name,
        credibility,
        ticker: v.ticker,
        companyName: v.companyName,
        market: v.market,
        direction: v.direction,
        confidence: v.confidence,
        summary: v.summary,
        evidenceText: v.evidenceText,
        ageDays,
        isFresh: v.validationStatus === "pending",
        score: (credibility / 100) * v.confidence * freshness,
      });
    }
  }

  return calls.sort((a, b) => b.score - a.score);
}

// ---- E. Ticker consensus ----------------------------------------------------

export interface ConsensusRow {
  ticker: string;
  companyName: string;
  market: string;
  bull: number;
  bear: number;
  neutral: number;
  watch: number;
  total: number; // distinct KOLs
  netLabel: "共识看多" | "共识看空" | "分歧" | "观望";
  diverging: boolean;
  crowded: boolean; // ≥2 KOLs piled in
  avgReturn: number | null;
  kolNames: string[];
}

export function deriveTickerConsensus(data: KOLRadarData): ConsensusRow[] {
  // distinct KOL current-stance per ticker
  const byTicker = new Map<
    string,
    { company: string; market: string; stances: { kol: string; v: SnapshotViewpoint }[] }
  >();

  for (const k of data.kols) {
    for (const v of latestByKolTicker(k).values()) {
      const entry =
        byTicker.get(v.ticker) ??
        { company: v.companyName, market: v.market, stances: [] };
      entry.stances.push({ kol: k.name, v });
      byTicker.set(v.ticker, entry);
    }
  }

  const rows: ConsensusRow[] = [];
  for (const [ticker, e] of byTicker) {
    let bull = 0;
    let bear = 0;
    let neutral = 0;
    let watch = 0;
    const settledReturns: number[] = [];
    for (const { v } of e.stances) {
      if (v.direction === "bullish") bull += 1;
      else if (v.direction === "bearish" || v.direction === "risk_warning") bear += 1;
      else if (v.direction === "neutral") neutral += 1;
      else watch += 1;
      if (isSettled(v)) settledReturns.push(v.returnPct ?? 0);
    }
    const total = e.stances.length;
    const diverging = bull > 0 && bear > 0;
    const directional = bull + bear;
    const netLabel: ConsensusRow["netLabel"] = diverging
      ? "分歧"
      : bull > bear
        ? "共识看多"
        : bear > bull
          ? "共识看空"
          : directional === 0
            ? "观望"
            : "分歧";
    const avgReturn = settledReturns.length
      ? settledReturns.reduce((s, r) => s + r, 0) / settledReturns.length
      : null;

    rows.push({
      ticker,
      companyName: e.company,
      market: e.market,
      bull,
      bear,
      neutral,
      watch,
      total,
      netLabel,
      diverging,
      crowded: total >= 2,
      avgReturn,
      kolNames: e.stances.map((s) => s.kol),
    });
  }

  // multi-KOL coverage first, then by divergence/crowding interest
  return rows.sort(
    (a, b) => b.total - a.total || Number(b.diverging) - Number(a.diverging),
  );
}

// ---- F. Earnings board (收益榜 · TOP EARNERS) --------------------------------

export interface EarningsRow {
  kolId: string;
  name: string;
  handle: string;
  style: string;
  cumReturn: number; // 窗口内已结算观点 returnPct 等权累计
  avgReturn: number;
  sampleCount: number;
  lowSample: boolean; // sampleCount < 3
  bestCall: { companyName: string; returnPct: number } | null;
}

const EARNINGS_LOW_SAMPLE_N = 3;

/**
 * 收益榜口径（冻结为契约，live 路径同一函数零改动复用）：
 *
 * 1. 结算判定复用 `isSettled`（returnPct 非 null 且 holdingDays > 0）。
 * 2. 窗口按**结算时点**归入，而非信号发布时点：
 *    `settleTs = timestamp + holdingDays * 86400_000`，
 *    落在 `[generatedAt − windowDays 天, generatedAt]` 闭区间内计入。
 *    理由：持有期最长可达 30 天，按信号时点算周榜恒空；语义 = 本窗口
 *    「落袋」的跟单盈亏。live 路径 generatedAt 即当前时刻，语义不变。
 * 3. `cumReturn = Σ returnPct`（等权跟单一单位，returnPct 已按方向调整，
 *    见文件头 return_pct semantics）；排序按 cumReturn 降序。
 * 4. `sampleCount === 0` 的 KOL 不上榜；`< 3` 标 lowSample 但仍上榜。
 * 5. `bestCall` = 窗口内 returnPct 最高的一笔。
 */
/** Earnings-board window: rolling 7d / 30d, or "all" (every settled viewpoint,
 * no time bound — the live surface uses this so historical settles still show). */
export type EarningsWindow = 7 | 30 | "all";

export function deriveEarningsBoard(
  data: KOLRadarData,
  windowDays: EarningsWindow,
): EarningsRow[] {
  const end = new Date(data.generatedAt).getTime();
  const start = windowDays === "all" ? -Infinity : end - windowDays * 86_400_000;

  const rows: EarningsRow[] = [];
  for (const k of data.kols) {
    const settledInWindow = k.viewpoints.filter((v) => {
      if (!isSettled(v)) return false;
      if (windowDays === "all") return true;
      const settleTs =
        new Date(v.timestamp).getTime() + (v.holdingDays ?? 0) * 86_400_000;
      return settleTs >= start && settleTs <= end;
    });
    if (!settledInWindow.length) continue;

    const cumReturn = settledInWindow.reduce((s, v) => s + (v.returnPct ?? 0), 0);
    const best = settledInWindow.reduce((b, v) =>
      (v.returnPct ?? -Infinity) > (b.returnPct ?? -Infinity) ? v : b,
    );

    rows.push({
      kolId: k.kolId,
      name: k.name,
      handle: k.handle,
      style: k.style,
      cumReturn,
      avgReturn: cumReturn / settledInWindow.length,
      sampleCount: settledInWindow.length,
      lowSample: settledInWindow.length < EARNINGS_LOW_SAMPLE_N,
      bestCall: { companyName: best.companyName, returnPct: best.returnPct ?? 0 },
    });
  }

  return rows.sort((a, b) => b.cumReturn - a.cumReturn);
}

/**
 * 全量数据中最近一笔结算的日期（YYYY-MM-DD），无已结算观点时为 null。
 * 供收益榜空态解释「为什么窗口是空的」——历史批次语料的结算时点可能
 * 远早于当前窗口。口径与 deriveEarningsBoard 一致（settle = timestamp +
 * holdingDays）。
 */
export function deriveLatestSettleDate(data: KOLRadarData): string | null {
  let latest = -Infinity;
  for (const k of data.kols) {
    for (const v of k.viewpoints) {
      if (!isSettled(v)) continue;
      const settleTs =
        new Date(v.timestamp).getTime() + (v.holdingDays ?? 0) * 86_400_000;
      if (settleTs > latest) latest = settleTs;
    }
  }
  return Number.isFinite(latest)
    ? new Date(latest).toISOString().slice(0, 10)
    : null;
}

/** Shared hero verdict mapping, reused by the market-sentiment block. */
export function stanceVerdict(net: number): {
  label: string;
  color: string;
  arrow: string;
} {
  if (net >= 2) return { label: "偏多", color: "var(--chart-up)", arrow: "▲" };
  if (net <= -2) return { label: "偏空", color: "var(--chart-down)", arrow: "▼" };
  return { label: "分歧", color: "#8a8278", arrow: "◆" };
}
