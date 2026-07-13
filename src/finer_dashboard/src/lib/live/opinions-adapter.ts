/**
 * Live adapter: /api/opinions/timeline → cockpit view-models.
 *
 * First real-data path for the 观点雷达 / KOL 问责页. Maps backend
 * TimelineOpinion (5-way direction since the API widening) onto the same
 * view-models the fixture pages use, so KOLRadar/KOLSnapshot render unchanged.
 *
 * HONESTY RULES (what live data genuinely lacks today):
 *  - changes = []            — backend has no snapshot-diff service yet
 *  - narrative = placeholder — no F7/LLM synthesis endpoint yet
 *  - name/style/specialties  — real values come from the KOL registry
 *    (/api/kol/registry); the raw creator_id / "风格未标注" / [] placeholders
 *    remain only as the fallback when the registry is unreachable or the
 *    creator is not registered.
 *  - opinions without a real author are EXCLUDED from KOL grouping (counted,
 *    surfaced in the banner) instead of pooling into a fake "unknown" KOL.
 */
import type {
  CredibilityOverride,
  KOLRadarData,
  RadarChangeEvent,
  RadarKOL,
} from "@/lib/fixtures/kol-radar";
import type {
  KOLSnapshotData,
  SnapshotViewpoint,
  ViewpointDirection,
} from "@/lib/fixtures/kol-snapshot";
import type { CreatorProfile, TradingStyleProfile } from "@/lib/contracts";

/** Backend TimelineOpinion as serialized on the wire (5-way direction). */
interface LiveOpinion {
  id: string;
  timestamp: string; // pipeline extraction moment (batch-collapsed)
  executableAt?: string | null; // canonical execution clock (real signal time)
  ticker: string;
  tickerName?: string | null;
  direction: ViewpointDirection;
  confidence: number;
  conviction?: number | null;
  verificationStatus: "success" | "failed" | "pending";
  priceChange?: number | null;
  holdingDays?: number | null;
  exitReason?: string | null;
  sourceText: string;
  author?: string | null;
  platform?: string | null;
  market?: string | null;
  traceStatus?: string | null;
  instrumentType?: string | null;
  actionChain?:
    | { triggerCondition?: string | null; actionType?: string | null }[]
    | null;
}

/** Real signal time: prefer the canonical execution clock over the extraction moment. */
function clockOf(o: LiveOpinion): string {
  return o.executableAt || o.timestamp;
}

interface LiveTimelineResponse {
  opinions: LiveOpinion[];
  total: number;
}

export interface LiveRadarResult {
  data: KOLRadarData;
  totalOpinions: number;
  unattributedCount: number; // opinions without a real author (excluded)
}

const NON_AUTHORS = new Set(["", "unknown", "none", "null"]);

const VALIDATION_MAP: Record<
  LiveOpinion["verificationStatus"],
  SnapshotViewpoint["validationStatus"]
> = { success: "verified", failed: "failed", pending: "pending" };

const TRACE_VALUES = new Set(["canonical", "partial", "non_canonical"]);

function hasRealAuthor(o: LiveOpinion): o is LiveOpinion & { author: string } {
  return !!o.author && !NON_AUTHORS.has(o.author.trim().toLowerCase());
}

function toViewpoint(o: LiveOpinion): SnapshotViewpoint {
  const trigger = o.actionChain?.[0]?.triggerCondition;
  // Non-tradable concept targets (registry sector placeholders like
  // OPTICAL_MODULE) must not read as real tickers — label the market slot.
  const isConcept = o.instrumentType === "unspecified" || o.instrumentType === "sector_concept";
  return {
    id: o.id,
    timestamp: clockOf(o),
    ticker: o.ticker,
    companyName: o.tickerName || o.ticker,
    market: isConcept ? "概念·不可交易" : o.market || "—",
    direction: o.direction,
    // KOL belief strength when available (the honest ranking signal);
    // falls back to pipeline confidence for legacy actions.
    confidence: Math.max(0, Math.min(1, o.conviction ?? o.confidence)),
    validationStatus: VALIDATION_MAP[o.verificationStatus] ?? "pending",
    // No trigger condition → a direction+target phrase. Slicing sourceText
    // here just duplicated the quote block right below it on every card.
    summary:
      trigger || `${DIRECTION_LABEL[o.direction]} ${o.tickerName || o.ticker}`,
    evidenceText: o.sourceText,
    returnPct: o.priceChange ?? null,
    holdingDays: o.holdingDays ?? null,
    traceStatus: (TRACE_VALUES.has(o.traceStatus ?? "")
      ? o.traceStatus
      : "non_canonical") as SnapshotViewpoint["traceStatus"],
    actionType: o.actionChain?.[0]?.actionType ?? undefined,
  };
}

const PAGE_SIZE = 100; // backend caps limit at le=100; cursor is a stringified offset
const MAX_PAGES = 50; // safety stop (5k opinions)

/**
 * Server-side change events from /api/opinions/changes — history-derived
 * flips/stop-losses plus true day-over-day snapshot diffs (new coverage,
 * cross-day flips, credibility moves) that only the backend can persist.
 * Failure-tolerant: returns undefined so the client-side derivation stands.
 */
async function fetchServerChanges(): Promise<RadarChangeEvent[] | undefined> {
  try {
    const res = await fetch("/api/opinions/changes", { cache: "no-store" });
    if (!res.ok) return undefined;
    const body = await res.json();
    const events = (body.data ?? body)?.events;
    if (!Array.isArray(events)) return undefined;
    return events as RadarChangeEvent[];
  } catch {
    return undefined;
  }
}

/**
 * Server-side credibility from /stats/summary (the single source of truth —
 * same shrunk-hit-rate formula, now computed in opinions.py). Failure-tolerant:
 * returns undefined so the client-side derivation stands as fallback.
 */
async function fetchCredibilityOverrides(): Promise<
  Record<string, CredibilityOverride> | undefined
> {
  try {
    const res = await fetch("/api/opinions/stats/summary?timeRange=ALL", {
      cache: "no-store",
    });
    if (!res.ok) return undefined;
    const body = await res.json();
    const kols: {
      author?: string;
      credibility?: number;
      hitRate?: number | null;
      settledCount?: number;
      lowSample?: boolean;
    }[] = (body.data ?? body)?.topKols ?? [];
    const out: Record<string, CredibilityOverride> = {};
    for (const k of kols) {
      if (!k.author || typeof k.credibility !== "number") continue;
      out[k.author] = {
        credibility: k.credibility,
        hitRate: k.hitRate ?? null,
        settledCount: k.settledCount ?? 0,
        lowSample: k.lowSample ?? true,
      };
    }
    return Object.keys(out).length ? out : undefined;
  } catch {
    return undefined;
  }
}

/**
 * KOL profile registry from GET /api/kol/registry — the truth source for
 * display_name / style_label / specialties. Failure-tolerant (same pattern as
 * fetchCredibilityOverrides): returns undefined so the raw creator_id
 * placeholders stand as fallback and rendering matches the pre-registry state.
 */
async function fetchRegistry(): Promise<
  Map<string, CreatorProfile> | undefined
> {
  try {
    const res = await fetch("/api/kol/registry", { cache: "no-store" });
    if (!res.ok) return undefined;
    const body = await res.json();
    const creators = (body.data ?? body)?.creators;
    if (!Array.isArray(creators)) return undefined;
    const out = new Map<string, CreatorProfile>();
    for (const c of creators as CreatorProfile[]) {
      if (typeof c?.creator_id !== "string") continue;
      out.set(c.creator_id, c);
    }
    return out.size ? out : undefined;
  } catch {
    return undefined;
  }
}

const DIRECTION_LABEL: Record<ViewpointDirection, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  watchlist: "观察",
  risk_warning: "风险提示",
};

const MAX_CHANGE_EVENTS = 12;

/**
 * Derive REAL change events from the opinion history itself — no snapshot-diff
 * service exists yet, but flips (same KOL + ticker, direction change between
 * consecutive signals) and stop-loss exits are directly observable facts.
 */
function deriveLiveChanges(
  attributed: (LiveOpinion & { author: string })[],
): RadarChangeEvent[] {
  const events: RadarChangeEvent[] = [];

  // Flips: consecutive direction changes per (author, ticker), by signal clock
  const groups = new Map<string, (LiveOpinion & { author: string })[]>();
  for (const o of attributed) {
    const key = `${o.author}::${o.ticker}`;
    const list = groups.get(key) ?? [];
    list.push(o);
    groups.set(key, list);
  }
  for (const list of groups.values()) {
    const sorted = [...list].sort((a, b) => clockOf(a).localeCompare(clockOf(b)));
    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1];
      const cur = sorted[i];
      if (prev.direction !== cur.direction) {
        events.push({
          id: `flip-${cur.id}`,
          type: "flip",
          kolId: cur.author,
          kolName: cur.author,
          ticker: cur.ticker,
          companyName: cur.tickerName || cur.ticker,
          fromDirection: prev.direction,
          toDirection: cur.direction,
          detail: `从${DIRECTION_LABEL[prev.direction]}转为${DIRECTION_LABEL[cur.direction]}`,
          timestamp: clockOf(cur),
        });
      }
    }
  }

  // Stop-loss exits from real backtest results
  for (const o of attributed) {
    if (o.exitReason === "stop_loss") {
      events.push({
        id: `sl-${o.id}`,
        type: "stop_loss",
        kolId: o.author,
        kolName: o.author,
        ticker: o.ticker,
        companyName: o.tickerName || o.ticker,
        detail: "跟单回测触发止损离场",
        timestamp: clockOf(o),
        value: o.priceChange ?? undefined,
      });
    }
  }

  // Latest first; keep the feed scannable
  return events
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
    .slice(0, MAX_CHANGE_EVENTS);
}

/** Fetch all opinions (paged) and group them into the radar view-model. */
export async function fetchLiveRadarData(): Promise<LiveRadarResult> {
  const opinions: LiveOpinion[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const cursor = page * PAGE_SIZE;
    const res = await fetch(
      `/api/opinions/timeline?limit=${PAGE_SIZE}${cursor ? `&cursor=${cursor}` : ""}`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      throw new Error(`opinions API ${res.status}`);
    }
    const body = (await res.json()) as LiveTimelineResponse;
    const batch = body.opinions ?? [];
    opinions.push(...batch);
    if (opinions.length >= (body.total ?? 0) || batch.length === 0) break;
  }

  const attributed = opinions.filter(hasRealAuthor);
  const unattributedCount = opinions.length - attributed.length;

  const byAuthor = new Map<string, SnapshotViewpoint[]>();
  const platformByAuthor = new Map<string, string>();
  for (const o of attributed) {
    const list = byAuthor.get(o.author) ?? [];
    list.push(toViewpoint(o));
    byAuthor.set(o.author, list);
    if (o.platform && !platformByAuthor.get(o.author)) {
      platformByAuthor.set(o.author, o.platform);
    }
  }

  const allTs = attributed.map(clockOf).sort();
  const periodLabel = allTs.length
    ? `${allTs[0].slice(0, 10)} — ${allTs[allTs.length - 1].slice(0, 10)}`
    : "—";

  const [credibilityOverrides, serverChanges, registry] = await Promise.all([
    fetchCredibilityOverrides(),
    fetchServerChanges(),
    fetchRegistry(),
  ]);

  // Registry-backed KOL metadata. Every fallback is byte-identical to the
  // pre-registry placeholders, so a failed registry fetch renders unchanged.
  const kols: RadarKOL[] = [...byAuthor.entries()].map(([author, vps]) => {
    const p = registry?.get(author);
    return {
      kolId: author, // never remapped — keys credibilityOverrides/toSnapshotData
      name: p?.display_name ?? author,
      handle: p?.handle ?? p?.display_name ?? author,
      style: p?.style_label ?? "风格未标注",
      // Observed platform wins; registry declaration is only the fallback.
      platform: platformByAuthor.get(author) ?? p?.platforms?.[0] ?? "—",
      specialties: p?.specialties ?? [],
      viewpoints: vps.sort((a, b) => b.timestamp.localeCompare(a.timestamp)),
    };
  });

  return {
    data: {
      generatedAt: new Date().toISOString(),
      periodLabel,
      kols,
      // Server snapshot-diff service is the primary source (persists daily
      // stance snapshots + credibility moves; display names decorated
      // server-side); the client history derivation is only an offline
      // fallback, so decorate its raw kolIds with registry names here.
      changes: (serverChanges ?? deriveLiveChanges(attributed)).map((ev) =>
        ev.kolId
          ? { ...ev, kolName: registry?.get(ev.kolId)?.display_name ?? ev.kolName }
          : ev,
      ),
      credibilityOverrides,
    },
    totalOpinions: opinions.length,
    unattributedCount,
  };
}

/** Build the per-KOL accountability view-model from an already-fetched radar result. */
export function toSnapshotData(
  radar: KOLRadarData,
  kolId: string,
): KOLSnapshotData | null {
  const kol = radar.kols.find((k) => k.kolId === kolId);
  if (!kol) return null;
  return {
    kolId: kol.kolId,
    kolName: kol.name,
    handle: kol.handle,
    style: kol.style,
    platform: kol.platform,
    generatedAt: radar.generatedAt,
    narrative:
      "自动研判尚未接入（F7/LLM 综合叙事为规划能力）。以下立场、象限与时间线均由该 KOL 的真实观点与 F8 回测派生。",
    viewpoints: kol.viewpoints,
  };
}

/**
 * Trading-style profile from GET /api/kol/style/{creator_id}. Failure-tolerant
 * (same pattern as fetchCredibilityOverrides): returns undefined so the
 * snapshot renders its "暂无风格画像" empty state instead of breaking.
 */
export async function fetchTradingStyle(
  kolId: string,
): Promise<TradingStyleProfile | undefined> {
  try {
    const res = await fetch(`/api/kol/style/${encodeURIComponent(kolId)}`, {
      cache: "no-store",
    });
    if (!res.ok) return undefined;
    const body = await res.json();
    const profile = (body.data ?? body) as TradingStyleProfile | undefined;
    if (!profile || typeof profile.creator_id !== "string") return undefined;
    return profile;
  } catch {
    return undefined;
  }
}
