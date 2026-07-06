/**
 * Fixture for the KOL "观点潮汐快照" (viewpoint tide snapshot) benchmark page.
 *
 * ⚠️ Illustrative data. The persona 老纪 (trader_ji) and his viewpoints mirror
 * the schema-faithful demo in `finer_site/src/demo/data.ts`, expanded to a fuller
 * timeline so the snapshot layout can be evaluated against realistic density.
 *
 * The view-model below is shaped to F7 (so wiring to live is a small adapter, not
 * a redesign), but it is NOT a drop-in 1:1 — note the gap before binding:
 *   - SnapshotViewpoint  ← TimelineEntry { timestamp, action: TradeAction, validation_status }
 *   - SnapshotSummary    ← timeline/models.py::TimelineSummary
 *   - KOLSnapshotData     ← timeline/models.py::KOLTimeline + KOL meta
 * Live source: GET /api/opinions/timeline?kols=<id> (+ /stats/summary). Caveat: that
 * route currently collapses TradeDirection 5→3 (risk_warning→bearish, watchlist→neutral),
 * so risk_warning/watchlist here need the route widened to survive a live swap.
 */

import type { TradingStyleProfile } from "@/lib/contracts";

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

// ---- 老纪 / trader_ji — A 股个股短线 -----------------------------------------

const VIEWPOINTS: SnapshotViewpoint[] = [
  {
    id: "TA-trader_ji-013",
    timestamp: "2026-06-24T09:38:00+08:00",
    ticker: "300308",
    companyName: "中际旭创",
    market: "SZ",
    direction: "bullish",
    confidence: 0.76,
    validationStatus: "pending",
    summary: "光模块景气延续，回调分批做多",
    evidenceText: "AI 算力需求没见顶，光模块龙头这波回调就是上车机会，分两批。",
    returnPct: null,
    holdingDays: null,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-012",
    timestamp: "2026-06-18T14:05:00+08:00",
    ticker: "688256",
    companyName: "寒武纪",
    market: "SH",
    direction: "risk_warning",
    confidence: 0.7,
    validationStatus: "verified",
    summary: "估值透支，高位提示风险规避",
    evidenceText: "寒武纪这个估值已经透支未来三年业绩了，这个位置不追，拿着的减一点。",
    returnPct: 0.041,
    holdingDays: 12,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-011",
    timestamp: "2026-06-10T09:35:00+08:00",
    ticker: "002371",
    companyName: "北方华创",
    market: "SZ",
    direction: "bullish",
    confidence: 0.81,
    validationStatus: "verified",
    summary: "设备国产化加速，逢低做多",
    evidenceText: "半导体设备国产化订单饱满，北方华创回调就是机会，基本面是硬的。",
    returnPct: 0.092,
    holdingDays: 28,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-010",
    timestamp: "2026-05-28T10:20:00+08:00",
    ticker: "002594",
    companyName: "比亚迪",
    market: "SZ",
    direction: "bearish",
    confidence: 0.73,
    validationStatus: "verified",
    summary: "价格战压制毛利，趋势走弱看空",
    evidenceText: "价格战打到这个程度，毛利撑不住，趋势也走坏了，先空一波别接刀。",
    returnPct: 0.061,
    holdingDays: 23,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-009",
    timestamp: "2026-05-15T09:42:00+08:00",
    ticker: "601012",
    companyName: "隆基绿能",
    market: "SH",
    direction: "bullish",
    confidence: 0.64,
    validationStatus: "verified",
    summary: "光伏超跌反弹，左侧抄底",
    evidenceText: "光伏跌到这里有估值修复空间，赌一把超跌反弹，仓位小一点。",
    returnPct: -0.085,
    holdingDays: 18,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-008",
    timestamp: "2026-05-06T09:50:00+08:00",
    ticker: "300059",
    companyName: "东方财富",
    market: "SZ",
    direction: "bullish",
    confidence: 0.68,
    validationStatus: "verified",
    summary: "券商放量突破，追多",
    evidenceText: "东财放量突破平台，券商行情要来了，量能不退就拿着，破位就走。",
    returnPct: -0.061,
    holdingDays: 9,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-007",
    timestamp: "2026-04-22T09:35:00+08:00",
    ticker: "002475",
    companyName: "立讯精密",
    market: "SZ",
    direction: "bullish",
    confidence: 0.79,
    validationStatus: "verified",
    summary: "果链旺季催化，做多",
    evidenceText: "果链旺季订单确定性高，立讯估值不贵，这种确定性的我重仓。",
    returnPct: 0.118,
    holdingDays: 31,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-006",
    timestamp: "2026-04-10T09:35:00+08:00",
    ticker: "688981",
    companyName: "中芯国际",
    market: "SH",
    direction: "bullish",
    confidence: 0.73,
    validationStatus: "verified",
    summary: "国产替代主线，赛道超配",
    evidenceText: "国产替代是未来三年主线，中芯是核心标的，回调就是加仓机会。",
    returnPct: 0.156,
    holdingDays: 49,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-005",
    timestamp: "2026-03-25T15:10:00+08:00",
    ticker: "300750",
    companyName: "宁德时代",
    market: "SZ",
    direction: "watchlist",
    confidence: 0.71,
    validationStatus: "verified",
    summary: "等回调，未触发建仓",
    evidenceText: "宁德现在追高不划算，跌到 180 下方再看，没到价格不动。",
    returnPct: 0,
    holdingDays: 0,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-004",
    timestamp: "2026-03-18T09:48:00+08:00",
    ticker: "000858",
    companyName: "五粮液",
    market: "SZ",
    direction: "bullish",
    confidence: 0.66,
    validationStatus: "verified",
    summary: "白酒修复补涨，跟随做多",
    evidenceText: "白酒情绪在修复，五粮液跟着茅台补涨，性价比比茅台高。",
    returnPct: 0.043,
    holdingDays: 22,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-001",
    timestamp: "2026-03-12T09:35:00+08:00",
    ticker: "600519",
    companyName: "贵州茅台",
    market: "SH",
    direction: "bullish",
    confidence: 0.82,
    validationStatus: "verified",
    summary: "缩量企稳分两批做多",
    evidenceText: "茅台回踩 1580 一带我觉得是中线机会，缩量企稳就是上车点，别一次打满。",
    returnPct: 0.123,
    holdingDays: 35,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-003",
    timestamp: "2026-03-05T09:40:00+08:00",
    ticker: "000300",
    companyName: "沪深300",
    market: "SH",
    direction: "neutral",
    confidence: 0.6,
    validationStatus: "verified",
    summary: "大盘震荡，观望为主",
    evidenceText: "大盘上有压力下有支撑，震荡为主，这种行情别乱动，等方向。",
    returnPct: 0.01,
    holdingDays: 30,
    traceStatus: "canonical",
  },
  {
    id: "TA-trader_ji-002",
    timestamp: "2026-02-26T13:20:00+08:00",
    ticker: "688256",
    companyName: "寒武纪",
    market: "SH",
    direction: "bullish",
    confidence: 0.69,
    validationStatus: "verified",
    summary: "题材高位追多",
    evidenceText: "寒武纪是 AI 第一龙头，回调就是上车，趋势没破就拿着。",
    returnPct: -0.118,
    holdingDays: 14,
    traceStatus: "canonical",
  },
];

export const KOL_SNAPSHOT_FIXTURE: KOLSnapshotData = {
  kolId: "trader_ji",
  kolName: "老纪",
  handle: "trader_ji",
  style: "A股个股短线",
  platform: "微信公众号",
  generatedAt: "2026-06-26T06:33:00+08:00",
  narrative:
    "近四个月内，老纪共发出 13 次明确观点，立场显著偏多（9 多 / 1 空 / 1 风险提示），集中在 A 股科技成长与白酒龙头两条主线。高信心观点兑现质量好——茅台 +12.3%、中芯 +15.6%、立讯 +11.8% 均验证为正；但在题材股追高上反复吃亏——隆基超跌抄底 −8.5%、东财假突破 −6.1%、早期追多寒武纪 −11.8%，且其六月对寒武纪的风险提示与二月的追多形成自我修正。整体置信度与实际收益正相关，高信心区命中率明显高于低信心区，说明老纪的择时与仓位纪律强于趋势持续性判断。",
  viewpoints: VIEWPOINTS,
  // 交易风格画像示例：declared 与 observed 在「入场风格」上冲突（自述右侧、
  // 行为偏左侧抄底），冻结「言行不一」高亮态的设计。
  tradingStyle: {
    creator_id: "trader_ji",
    display_name: "老纪",
    declared: {
      uses_margin: false,
      uses_leverage: null,
      does_short: false,
      entry_style: "right_side",
      evidence_notes: [
        "直播中自述“从不融资，满仓也只用自有资金”",
        "多次强调“突破确认再上车”，自我定位右侧交易",
      ],
    },
    observed: {
      sample_size: 13,
      directional_sample_size: 11,
      short_side_count: 0,
      short_ratio: 0.0,
      margin_mention_count: 0,
      leverage_mention_count: 0,
      left_side_count: 5,
      right_side_count: 2,
      entry_style_observed: "left_side",
      entry_style_sample_size: 7,
      low_sample: false,
      computed_at: "2026-06-26T06:33:00+08:00",
      window_label: "ALL",
    },
  },
};

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
