/**
 * L3-equivalent data brain: the 标的横截面 (ticker cross-section). Groups every KOL's
 * viewpoints on ONE ticker → consensus verdict, a "谁对了" scoreboard ranked by each
 * KOL's realized follow-P&L on that name, and a cross-KOL stance timeline.
 *
 * Reuses the kol-radar fixture (same 5 KOLs). Data-source agnostic via deriveTickerCrossSection.
 * Live seam caveats are identical to kol-radar.ts (credibility/5-way/creator_id).
 *
 * return_pct = F8 完全跟单 P&L, already direction-adjusted (正=判断对/盈, 负=判断错/亏).
 */
import {
  KOL_RADAR_FIXTURE,
  deriveCredibilityBoard,
  type KOLRadarData,
} from "./kol-radar";
import type { SnapshotViewpoint, ViewpointDirection } from "./kol-snapshot";

export type { SnapshotViewpoint, ViewpointDirection } from "./kol-snapshot";

export interface TickerViewpoint extends SnapshotViewpoint {
  kolId: string;
  kolName: string;
  credibility: number;
}

export interface WhoWasRightRow {
  kolId: string;
  kolName: string;
  credibility: number;
  direction: ViewpointDirection; // KOL's current (latest) stance on this ticker
  confidence: number;
  returnPct: number | null; // realized follow-P&L of that stance (null = 未结算)
  correct: boolean | null; // returnPct > 0 ; null if unsettled
  date: string; // latest viewpoint date
  callCount: number; // how many calls this KOL made on the ticker
  overallHitRate: number | null; // KOL's overall hit rate (一贯准 vs 此票蒙对一次)
  overallSettled: number; // overall settled sample size
  lowSample: boolean; // overall sample thin — discount the credibility
}

export type ConsensusNetLabel = "共识看多" | "共识看空" | "分歧" | "观望";

export interface TickerCrossSection {
  ticker: string;
  companyName: string;
  market: string;
  // consensus (distinct KOLs by current stance)
  bull: number;
  bear: number;
  neutral: number;
  watch: number;
  total: number;
  netLabel: ConsensusNetLabel;
  diverging: boolean;
  crowded: boolean;
  crowdReturn: number | null; // avg settled follow-P&L of each KOL's CURRENT stance (reconciles with 谁对了)
  bullReturn: number | null; // avg settled P&L of KOLs whose current stance is bullish
  bearReturn: number | null; // avg settled P&L of KOLs whose current stance is bearish/risk_warning
  soloDirection: ViewpointDirection | null; // set when only 1 KOL covers — avoid "共识" wording
  correctCount: number; // KOLs whose current stance was settled-correct
  settledKolCount: number;
  whoWasRight: WhoWasRightRow[]; // ranked by returnPct desc, unsettled last
  timeline: TickerViewpoint[]; // every viewpoint on the ticker, time-descending
  narrative: string;
}

export interface TickerListItem {
  ticker: string;
  companyName: string;
  market: string;
  total: number; // distinct KOLs covering
}

// ---- helpers (re-implemented locally to keep kol-radar's internals private) ---

function isSettled(v: SnapshotViewpoint): boolean {
  return v.returnPct !== null && (v.holdingDays ?? 0) > 0;
}

// ---- authored per-ticker syntheses (live: F7/LLM-generated) ------------------

const NARRATIVES: Record<string, string> = {
  "002594":
    "三方对垒：老纪看空、趋势猎手K 提示风险，事后股价走弱、两人均兑现（+6.1% / +7.1%）；赛道阿尔法左侧抄底看多，被埋 −7.2%。在比亚迪上，「看空 / 规避」完胜「左侧抄底」。",
  "688256":
    "拥挤的题材龙头：趋势猎手K 与老纪先后追多均亏（−8.0% / 早期 −11.8%），老纪六月及时翻为风险提示并兑现 +4.1%——同一标的上「追高」与「提示风险」的对错一目了然。",
  "688981":
    "罕见的高质量共识：老纪与赛道阿尔法同时看多国产替代主线，双双兑现 +15.6%，是名单里共识与结果最一致的标的。",
  "300059":
    "共识陷阱：老纪与趋势猎手K 同时追券商突破，结果双双 −6.1% 止损——人多的方向未必对，典型的「拥挤打脸」。",
};

// ---- derivations ------------------------------------------------------------

/** Latest viewpoint per KOL on a ticker (a KOL's *current* stance). */
function latestPerKol(vps: TickerViewpoint[]): Map<string, TickerViewpoint> {
  const m = new Map<string, TickerViewpoint>();
  for (const v of vps) {
    const prev = m.get(v.kolId);
    if (!prev || v.timestamp > prev.timestamp) m.set(v.kolId, v);
  }
  return m;
}

export function deriveTickerCrossSection(
  data: KOLRadarData,
  ticker: string,
): TickerCrossSection | null {
  const boardById = new Map(deriveCredibilityBoard(data).map((r) => [r.kolId, r]));

  const all: TickerViewpoint[] = [];
  for (const k of data.kols) {
    for (const v of k.viewpoints) {
      if (v.ticker !== ticker) continue;
      all.push({
        ...v,
        kolId: k.kolId,
        kolName: k.name,
        credibility: boardById.get(k.kolId)?.credibility ?? 50,
      });
    }
  }
  if (!all.length) return null;

  const timeline = [...all].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const companyName = timeline[0].companyName;
  const market = timeline[0].market;

  // consensus by distinct KOL current stance
  const latest = latestPerKol(all);
  let bull = 0;
  let bear = 0;
  let neutral = 0;
  let watch = 0;
  for (const v of latest.values()) {
    if (v.direction === "bullish") bull += 1;
    else if (v.direction === "bearish" || v.direction === "risk_warning") bear += 1;
    else if (v.direction === "neutral") neutral += 1;
    else watch += 1;
  }
  const total = latest.size;
  const diverging = bull > 0 && bear > 0;
  const directional = bull + bear;
  const netLabel: ConsensusNetLabel = diverging
    ? "分歧"
    : bull > bear
      ? "共识看多"
      : bear > bull
        ? "共识看空"
        : directional === 0
          ? "观望"
          : "分歧";

  // Crowd / side returns use each KOL's CURRENT stance only — same population as
  // 谁对了/命中 below — so the hero numbers reconcile with the scoreboard. A KOL's
  // superseded older calls stay in the timeline, not in these aggregates.
  const latestStances = [...latest.values()];
  const latestSettled = latestStances.filter(isSettled);
  const avg = (xs: number[]): number | null =>
    xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null;
  const crowdReturn = avg(latestSettled.map((v) => v.returnPct ?? 0));
  const bullReturn = avg(
    latestSettled.filter((v) => v.direction === "bullish").map((v) => v.returnPct ?? 0),
  );
  const bearReturn = avg(
    latestSettled
      .filter((v) => v.direction === "bearish" || v.direction === "risk_warning")
      .map((v) => v.returnPct ?? 0),
  );
  const soloDirection = latestStances.length === 1 ? latestStances[0].direction : null;

  // who-was-right: one row per KOL by their CURRENT stance (旧立场已被取代，不回退到
  // 更早的已结算观点；当前立场未结算即记「待结算」). Ranked by realized P&L.
  const whoWasRight: WhoWasRightRow[] = [...latest.values()]
    .map((v): WhoWasRightRow => {
      const settled = isSettled(v);
      const callCount = all.filter((x) => x.kolId === v.kolId).length;
      const board = boardById.get(v.kolId);
      return {
        kolId: v.kolId,
        kolName: v.kolName,
        credibility: v.credibility,
        direction: v.direction,
        confidence: v.confidence,
        returnPct: settled ? v.returnPct : null,
        correct: settled ? (v.returnPct ?? 0) > 0 : null,
        date: v.timestamp,
        callCount,
        overallHitRate: board?.hitRate ?? null,
        overallSettled: board?.settledCount ?? 0,
        lowSample: board?.lowSample ?? false,
      };
    })
    .sort((a, b) => {
      if (a.returnPct === null && b.returnPct === null) return 0;
      if (a.returnPct === null) return 1;
      if (b.returnPct === null) return -1;
      return b.returnPct - a.returnPct;
    });

  const correctCount = whoWasRight.filter((r) => r.correct === true).length;
  const settledKolCount = whoWasRight.filter((r) => r.correct !== null).length;

  // Solo coverage isn't a "共识" — phrase the fallback narrative by the lone direction.
  const SOLO_WORD: Record<ViewpointDirection, string> = {
    bullish: "看多",
    bearish: "看空",
    neutral: "中性观望",
    watchlist: "观望",
    risk_warning: "提示风险",
  };
  const verdictWord = soloDirection ? SOLO_WORD[soloDirection] : netLabel;
  const narrative =
    NARRATIVES[ticker] ??
    `${total} 位 KOL 覆盖${companyName}，当前${verdictWord}${
      crowdReturn !== null
        ? `，群体跟单兑现 ${crowdReturn >= 0 ? "+" : ""}${(crowdReturn * 100).toFixed(1)}%`
        : ""
    }。`;

  return {
    ticker,
    companyName,
    market,
    bull,
    bear,
    neutral,
    watch,
    total,
    netLabel,
    diverging,
    crowded: total >= 2,
    crowdReturn,
    bullReturn,
    bearReturn,
    soloDirection,
    correctCount,
    settledKolCount,
    whoWasRight,
    timeline,
    narrative,
  };
}

/** Tickers present in the fixture, multi-KOL first — for route validation / index. */
export function listTickers(data: KOLRadarData = KOL_RADAR_FIXTURE): TickerListItem[] {
  const map = new Map<string, TickerListItem & { kols: Set<string> }>();
  for (const k of data.kols) {
    for (const v of k.viewpoints) {
      const e =
        map.get(v.ticker) ??
        {
          ticker: v.ticker,
          companyName: v.companyName,
          market: v.market,
          total: 0,
          kols: new Set<string>(),
        };
      e.kols.add(k.kolId);
      map.set(v.ticker, e);
    }
  }
  return [...map.values()]
    .map((e) => ({
      ticker: e.ticker,
      companyName: e.companyName,
      market: e.market,
      total: e.kols.size,
    }))
    .sort((a, b) => b.total - a.total);
}

/** Default showcase ticker for the demo route (the 3-way 比亚迪 divergence). */
export const DEFAULT_TICKER = "002594";
