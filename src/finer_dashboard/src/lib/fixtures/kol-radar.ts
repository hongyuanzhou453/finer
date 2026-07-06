/**
 * Fixture + derivations for the 观点雷达 (viewpoint radar) — the cross-KOL
 * operating-console home (top tier). Retail decision support: 现在什么状况 → 信哪个 → 跟哪条.
 *
 * DATA-SOURCE SEAM — read before wiring to live. This is a fixture (5 KOLs modeled
 * on finer_site demo personas, enriched). The block shapes map onto F7 (KOLTimeline
 * / TradeAction), but the live path is NOT drop-in — several aggregates here run
 * ahead of the backend today:
 *   · 信誉分 (0–99) — derived from hit rate. Backend has only KOLScorer (1–5,
 *     multi-dim); /stats/summary.topKols.avgRating is currently 0.0. Live needs a
 *     credibility aggregation + opinions sliced by creator_id.
 *   · 五向 (含 risk_warning / watchlist) — TradeDirection has 5 values, but the
 *     current /api/opinions/timeline collapses them to 3 (risk_warning→bearish,
 *     watchlist→neutral). Faithful 5-way needs the route to widen direction.
 *   · 今日/近期异动 diff — fixture-authored; backend has no snapshot-diff service yet.
 *   · per-KOL attribution — assumes a clean creator_id; real intake is largely
 *     unknown/None, so live grouping collapses to one bucket until F0 attribution lands.
 *
 * return_pct semantics: F8 完全跟单 P&L, already direction-adjusted (正=判断对/盈,
 * 负=判断错/亏). A bearish call that correctly called a drop has positive return_pct.
 *
 * Cross-KOL overlaps are intentional so consensus/divergence/crowding emerge:
 *   - 中芯国际: 老纪 + 赛道阿尔法 同看多 (共识兑现)
 *   - 比亚迪:   老纪 看空 / 赛道 看多 / 趋势猎手K 风险 (三方分歧)
 *   - 寒武纪/东财: 多人追多且亏 (拥挤打脸)
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

// ---- viewpoint factory (cuts boilerplate; safe defaults) --------------------

type VpInput = Pick<
  SnapshotViewpoint,
  | "id"
  | "timestamp"
  | "ticker"
  | "companyName"
  | "market"
  | "direction"
  | "confidence"
  | "summary"
  | "evidenceText"
> &
  Partial<SnapshotViewpoint>;

const vp = (o: VpInput): SnapshotViewpoint => ({
  validationStatus: "verified",
  returnPct: null,
  holdingDays: null,
  traceStatus: "canonical",
  ...o,
});

// ---- 5 KOLs -----------------------------------------------------------------

const VALUE_LAOZHANG: RadarKOL = {
  kolId: "value_laozhang",
  name: "价值老张",
  handle: "value_laozhang",
  style: "长线价值",
  platform: "雪球",
  specialties: ["银行", "保险", "红利"],
  viewpoints: [
    vp({
      id: "TA-lz-04",
      timestamp: "2026-06-20T09:30:00+08:00",
      ticker: "601088",
      companyName: "中国神华",
      market: "SH",
      direction: "bullish",
      confidence: 0.78,
      summary: "高股息防御，回调加仓",
      evidenceText: "神华这种现金牛，股息率到 7% 就是底，跌出来的都是机会。",
      returnPct: 0.112,
      holdingDays: 55,
    }),
    vp({
      id: "TA-lz-03",
      timestamp: "2026-05-28T09:30:00+08:00",
      ticker: "600900",
      companyName: "长江电力",
      market: "SH",
      direction: "bullish",
      confidence: 0.82,
      summary: "类债资产，长期持有",
      evidenceText: "长电的现金流确定性堪比国债，估值不贵就一直拿。",
      returnPct: 0.068,
      holdingDays: 40,
    }),
    vp({
      // settles 2026-06-22 (timestamp + 41d) — inside the 7d earnings window
      id: "TA-lz-05",
      timestamp: "2026-05-12T09:30:00+08:00",
      ticker: "601288",
      companyName: "农业银行",
      market: "SH",
      direction: "bullish",
      confidence: 0.76,
      summary: "国有大行股息打底，逢低配置",
      evidenceText: "农行股息率还在 5% 以上，这种位置慢慢捡就行，拿着收息不慌。",
      returnPct: 0.058,
      holdingDays: 41,
    }),
    vp({
      id: "TA-lz-02",
      timestamp: "2026-04-02T09:30:00+08:00",
      ticker: "600036",
      companyName: "招商银行",
      market: "SH",
      direction: "bullish",
      confidence: 0.8,
      summary: "破净加仓",
      evidenceText: "银行股里招行最优质，破净就是难得的加仓机会。",
      returnPct: 0.094,
      holdingDays: 36,
    }),
    vp({
      id: "TA-lz-01",
      timestamp: "2026-03-05T09:30:00+08:00",
      ticker: "601318",
      companyName: "中国平安",
      market: "SH",
      direction: "bullish",
      confidence: 0.85,
      summary: "股息率 6% 分批买长持",
      evidenceText: "平安股息率到 6% 就是值得长期拿的位置，估值在底部区域。",
      returnPct: 0.182,
      holdingDays: 64,
    }),
  ],
};

const TRADER_JI: RadarKOL = {
  kolId: "trader_ji",
  name: "老纪",
  handle: "trader_ji",
  style: "个股短线",
  platform: "微信公众号",
  specialties: ["科技成长", "白酒"],
  viewpoints: [
    vp({
      id: "TA-ji-05",
      timestamp: "2026-06-18T14:05:00+08:00",
      ticker: "688256",
      companyName: "寒武纪",
      market: "SH",
      direction: "risk_warning",
      confidence: 0.7,
      summary: "估值透支，高位提示风险",
      evidenceText: "寒武纪这个估值已经透支未来三年业绩了，这个位置不追，拿着的减一点。",
      returnPct: 0.041,
      holdingDays: 12,
    }),
    vp({
      id: "TA-ji-06",
      timestamp: "2026-05-28T10:20:00+08:00",
      ticker: "002594",
      companyName: "比亚迪",
      market: "SZ",
      direction: "bearish",
      confidence: 0.73,
      summary: "价格战压制毛利，趋势走弱看空",
      evidenceText: "价格战打到这个程度，毛利撑不住，趋势也走坏了，先空一波别接刀。",
      returnPct: 0.061,
      holdingDays: 23,
    }),
    vp({
      id: "TA-ji-04",
      timestamp: "2026-05-06T09:50:00+08:00",
      ticker: "300059",
      companyName: "东方财富",
      market: "SZ",
      direction: "bullish",
      confidence: 0.68,
      summary: "券商放量突破，追多",
      evidenceText: "东财放量突破平台，券商行情要来了，破位就走别犹豫。",
      returnPct: -0.061,
      holdingDays: 9,
    }),
    vp({
      id: "TA-ji-03",
      timestamp: "2026-04-10T09:35:00+08:00",
      ticker: "688981",
      companyName: "中芯国际",
      market: "SH",
      direction: "bullish",
      confidence: 0.73,
      summary: "国产替代主线，回调加仓",
      evidenceText: "国产替代是未来三年主线，中芯是核心标的，回调就是加仓机会。",
      returnPct: 0.156,
      holdingDays: 49,
    }),
    vp({
      id: "TA-ji-02",
      timestamp: "2026-03-12T09:35:00+08:00",
      ticker: "600519",
      companyName: "贵州茅台",
      market: "SH",
      direction: "bullish",
      confidence: 0.82,
      summary: "缩量企稳分两批做多",
      evidenceText: "茅台回踩 1580 缩量企稳就是上车点，别一次打满，分两批。",
      returnPct: 0.123,
      holdingDays: 35,
    }),
    vp({
      id: "TA-ji-01",
      timestamp: "2026-02-26T13:20:00+08:00",
      ticker: "688256",
      companyName: "寒武纪",
      market: "SH",
      direction: "bullish",
      confidence: 0.69,
      summary: "题材高位追多",
      evidenceText: "寒武纪是 AI 第一龙头，回调就是上车，趋势没破就拿着。",
      returnPct: -0.118,
      holdingDays: 14,
    }),
  ],
};

const HK_VETERAN: RadarKOL = {
  kolId: "hk_veteran",
  name: "港股老兵",
  handle: "hk_veteran",
  style: "港股龙头",
  platform: "B站",
  specialties: ["互联网", "消费"],
  viewpoints: [
    vp({
      id: "TA-hk-04",
      timestamp: "2026-06-25T11:10:00+08:00",
      ticker: "03690",
      companyName: "美团",
      market: "HK",
      direction: "bullish",
      confidence: 0.74,
      summary: "外卖竞争缓和，估值修复",
      evidenceText: "美团这波杀估值杀过头了，竞争格局在缓和，本地生活还是它的。",
      returnPct: null,
      holdingDays: null,
      validationStatus: "pending",
    }),
    vp({
      // settles 2026-06-22 (timestamp + 15d) — inside the 7d earnings window
      id: "TA-hk-05",
      timestamp: "2026-06-07T10:15:00+08:00",
      ticker: "01024",
      companyName: "快手-W",
      market: "HK",
      direction: "bullish",
      confidence: 0.68,
      summary: "电商货币化提速，短线修复",
      evidenceText: "快手电商货币化率在往上走，估值又是互联网里最便宜的一档，博一段修复。",
      returnPct: 0.047,
      holdingDays: 15,
    }),
    vp({
      id: "TA-hk-03",
      timestamp: "2026-05-12T09:35:00+08:00",
      ticker: "01810",
      companyName: "小米集团",
      market: "HK",
      direction: "bullish",
      confidence: 0.7,
      summary: "汽车放量，追势",
      evidenceText: "小米汽车交付爬坡顺利，硬件 + 生态的故事市场愿意给溢价。",
      returnPct: -0.034,
      holdingDays: 20,
    }),
    vp({
      id: "TA-hk-02",
      timestamp: "2026-04-10T11:20:00+08:00",
      ticker: "09988",
      companyName: "阿里巴巴",
      market: "HK",
      direction: "watchlist",
      confidence: 0.66,
      summary: "等云拆分催化，暂不动",
      evidenceText: "阿里拆分落地才是真正的催化，没落地之前估值修复有限，先观察。",
      returnPct: 0,
      holdingDays: 0,
    }),
    vp({
      id: "TA-hk-01",
      timestamp: "2026-03-09T09:35:00+08:00",
      ticker: "00700",
      companyName: "腾讯控股",
      market: "HK",
      direction: "bullish",
      confidence: 0.79,
      summary: "回购托底，回调分批买",
      evidenceText: "腾讯每天回购就是给股价托底，回调到 380 附近分批买，估值不贵。",
      returnPct: 0.086,
      holdingDays: 48,
    }),
  ],
};

const SECTOR_ALPHA: RadarKOL = {
  kolId: "sector_alpha",
  name: "赛道阿尔法",
  handle: "sector_alpha",
  style: "行业轮动",
  platform: "雪球",
  specialties: ["半导体", "医疗", "新能源"],
  viewpoints: [
    vp({
      id: "TA-sa-05",
      timestamp: "2026-06-12T09:35:00+08:00",
      ticker: "002594",
      companyName: "比亚迪",
      market: "SZ",
      direction: "bullish",
      confidence: 0.67,
      summary: "新能源龙头超跌，左侧布局",
      evidenceText: "比亚迪杀到这个估值，海外放量能托住基本面，赌一个困境反转。",
      returnPct: -0.072,
      holdingDays: 19,
    }),
    vp({
      id: "TA-sa-04",
      timestamp: "2026-05-18T09:35:00+08:00",
      ticker: "601012",
      companyName: "隆基绿能",
      market: "SH",
      direction: "bullish",
      confidence: 0.64,
      summary: "光伏底部，赌反弹",
      evidenceText: "光伏产能出清接近尾声，隆基作为龙头先反弹，仓位别重。",
      returnPct: -0.085,
      holdingDays: 18,
    }),
    vp({
      id: "TA-sa-03",
      timestamp: "2026-04-22T09:30:00+08:00",
      ticker: "300760",
      companyName: "迈瑞医疗",
      market: "SZ",
      direction: "bullish",
      confidence: 0.7,
      summary: "估值切换到买点",
      evidenceText: "医疗器械龙头迈瑞估值切换到了买点，资金会从高位赛道轮过来。",
      returnPct: 0.067,
      holdingDays: 16,
    }),
    vp({
      id: "TA-sa-02",
      timestamp: "2026-04-15T09:35:00+08:00",
      ticker: "300750",
      companyName: "宁德时代",
      market: "SZ",
      direction: "bullish",
      confidence: 0.69,
      summary: "储能拉动，趋势做多",
      evidenceText: "宁德储能订单饱满，第二增长曲线起来了，趋势上就拿着。",
      returnPct: 0.044,
      holdingDays: 21,
    }),
    vp({
      id: "TA-sa-01",
      timestamp: "2026-03-20T09:35:00+08:00",
      ticker: "688981",
      companyName: "中芯国际",
      market: "SH",
      direction: "bullish",
      confidence: 0.73,
      summary: "半导体赛道超配",
      evidenceText: "半导体国产替代是三年主线，中芯是核心，回调加仓。",
      returnPct: 0.156,
      holdingDays: 49,
    }),
  ],
};

const TREND_HUNTER_K: RadarKOL = {
  kolId: "trend_hunter_k",
  name: "趋势猎手K",
  handle: "trend_hunter_k",
  style: "动量趋势",
  platform: "微信公众号",
  specialties: ["题材", "科技"],
  viewpoints: [
    vp({
      id: "TA-k-04",
      timestamp: "2026-06-24T09:45:00+08:00",
      ticker: "300308",
      companyName: "中际旭创",
      market: "SZ",
      direction: "bullish",
      confidence: 0.76,
      summary: "光模块放量突破，追多",
      evidenceText: "中际旭创放量突破前高，AI 算力主升浪还没走完，量在就拿着。",
      returnPct: null,
      holdingDays: null,
      validationStatus: "pending",
    }),
    vp({
      // settles 2026-06-23 (timestamp + 13d) — inside the 7d earnings window
      id: "TA-k-05",
      timestamp: "2026-06-10T09:40:00+08:00",
      ticker: "002230",
      companyName: "科大讯飞",
      market: "SZ",
      direction: "bullish",
      confidence: 0.66,
      summary: "AI 应用轮动补涨，追一把",
      evidenceText: "算力炒完轮到应用，讯飞是应用端旗手，量能起来就跟，破 5 日线就撤。",
      returnPct: -0.028,
      holdingDays: 13,
    }),
    vp({
      id: "TA-k-03",
      timestamp: "2026-06-08T13:05:00+08:00",
      ticker: "002594",
      companyName: "比亚迪",
      market: "SZ",
      direction: "risk_warning",
      confidence: 0.74,
      summary: "跌破年线，趋势走坏规避",
      evidenceText: "比亚迪跌破年线趋势就走坏了，不要抄底，等右侧信号。",
      returnPct: 0.071,
      holdingDays: 23,
    }),
    vp({
      id: "TA-k-02",
      timestamp: "2026-05-20T09:48:00+08:00",
      ticker: "688256",
      companyName: "寒武纪",
      market: "SH",
      direction: "bullish",
      confidence: 0.69,
      summary: "题材龙头追势",
      evidenceText: "寒武纪是这波 AI 总龙头，强者恒强，回调就是上车点。",
      returnPct: -0.08,
      holdingDays: 11,
    }),
    vp({
      id: "TA-k-01",
      timestamp: "2026-05-06T09:50:00+08:00",
      ticker: "300059",
      companyName: "东方财富",
      market: "SZ",
      direction: "bullish",
      confidence: 0.68,
      summary: "券商突破跟风",
      evidenceText: "东财放量了，券商一动牛市就有戏，跟一把。",
      returnPct: -0.061,
      holdingDays: 9,
    }),
  ],
};

const KOLS: RadarKOL[] = [
  VALUE_LAOZHANG,
  TRADER_JI,
  HK_VETERAN,
  SECTOR_ALPHA,
  TREND_HUNTER_K,
];

const CHANGES: RadarChangeEvent[] = [
  {
    id: "chg-1",
    type: "flip",
    kolId: "trader_ji",
    kolName: "老纪",
    ticker: "688256",
    companyName: "寒武纪",
    fromDirection: "bullish",
    toDirection: "risk_warning",
    detail: "从追多转为风险提示——估值透支，建议减仓",
    timestamp: "2026-06-18T14:05:00+08:00",
  },
  {
    id: "chg-2",
    type: "new_high_conviction",
    kolId: "trend_hunter_k",
    kolName: "趋势猎手K",
    ticker: "300308",
    companyName: "中际旭创",
    toDirection: "bullish",
    detail: "放量突破前高，新增高信念做多",
    timestamp: "2026-06-24T09:45:00+08:00",
    value: 0.76,
  },
  {
    id: "chg-3",
    type: "new_call",
    kolId: "hk_veteran",
    kolName: "港股老兵",
    ticker: "03690",
    companyName: "美团",
    toDirection: "bullish",
    detail: "新增做多——外卖竞争缓和，估值修复",
    timestamp: "2026-06-25T11:10:00+08:00",
    value: 0.74,
  },
  {
    id: "chg-4",
    type: "stop_loss",
    kolId: "sector_alpha",
    kolName: "赛道阿尔法",
    ticker: "002594",
    companyName: "比亚迪",
    detail: "左侧抄底比亚迪触发止损",
    timestamp: "2026-06-25T15:00:00+08:00",
    value: -0.072,
  },
  {
    id: "chg-5",
    type: "score_change",
    kolId: "value_laozhang",
    kolName: "价值老张",
    detail: "平安兑现 +18.2%，信誉分上调",
    timestamp: "2026-06-24T16:00:00+08:00",
    value: 2,
  },
  {
    id: "chg-6",
    type: "consensus_alert",
    ticker: "002594",
    companyName: "比亚迪",
    detail: "出现三方分歧：1 看多 / 2 看空·风险",
    timestamp: "2026-06-25T16:00:00+08:00",
  },
];

export const KOL_RADAR_FIXTURE: KOLRadarData = {
  generatedAt: "2026-06-26T06:33:00+08:00",
  periodLabel: "近 4 个月",
  kols: KOLS,
  changes: CHANGES,
};

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
export function deriveEarningsBoard(
  data: KOLRadarData,
  windowDays: 7 | 30,
): EarningsRow[] {
  const end = new Date(data.generatedAt).getTime();
  const start = end - windowDays * 86_400_000;

  const rows: EarningsRow[] = [];
  for (const k of data.kols) {
    const settledInWindow = k.viewpoints.filter((v) => {
      if (!isSettled(v)) return false;
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
