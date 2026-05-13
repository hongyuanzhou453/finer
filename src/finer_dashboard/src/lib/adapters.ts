/**
 * Adapters to convert backend BacktestResult into frontend view models.
 */

import type {
  BacktestResult,
  BacktestSummary,
  BacktestTask,
  KOL,
  KOLDetail,
  KOLListItemRaw,
  KOLRatingResponse,
  KOLTimelineEvent,
  PortfolioSnapshot,
} from "./contracts";
import type {
  KOLBacktestViewModel,
  F8ReturnPoint,
  F8AnnualReturnRow,
  F8PeerPoint,
  F8MetricRow,
  F8TopCall,
  MetricDirection,
} from "./f8-visualization";

// =============================================================================
// Helpers
// =============================================================================

function formatPercent(value: number, digits = 1): string {
  const pct = value * 100;
  const prefix = pct > 0 ? "+" : "";
  return `${prefix}${pct.toFixed(digits)}%`;
}

function formatSignedDrawdown(value: number): string {
  return `-${(Math.abs(value) * 100).toFixed(1)}%`;
}

function percentileRank(
  values: number[],
  subject: number,
  direction: MetricDirection,
): number {
  const better = values.filter((v) =>
    direction === "higher_is_better" ? subject >= v : subject <= v,
  ).length;
  return Math.round((better / Math.max(values.length, 1)) * 100);
}

function makeMetricRow(params: {
  metric: string;
  direction: MetricDirection;
  subjectValue: number;
  subjectDisplay: string;
  note: string;
}): F8MetricRow {
  return {
    metric: params.metric,
    direction: params.direction,
    subjectValue: params.subjectValue,
    subjectDisplay: params.subjectDisplay,
    cohortAverage: 0,
    cohortDisplay: "—",
    percentile: 0,
    note: params.note,
  };
}

// =============================================================================
// BacktestSummary → BacktestTask (for list page)
// =============================================================================

/**
 * Convert a backend BacktestSummary into the BacktestTask shape
 * used by the /backtest list page.
 */
export function backtestSummaryToTask(summary: BacktestSummary): BacktestTask {
  const kolIds = summary.kol_id ? [summary.kol_id] : [];
  return {
    id: summary.backtest_id,
    name: `回测 ${summary.backtest_id.slice(0, 8)}`,
    kolIds,
    kolNames: kolIds.length > 0 ? kolIds : ["未指定"],
    status: "completed",
    startDate: summary.start_date?.slice(0, 10) ?? "",
    endDate: summary.end_date?.slice(0, 10) ?? "",
    createdAt: summary.created_at?.slice(0, 10) ?? "",
    completedAt: summary.created_at?.slice(0, 10),
    config: {
      initialCapital: 0,
      positionSize: 0.1,
    },
    metrics: {
      totalReturn: summary.total_return * 100,
      annualizedReturn: 0,
      sharpeRatio: summary.sharpe_ratio,
      maxDrawdown: summary.max_drawdown * 100,
      winRate: summary.win_rate * 100,
      totalTrades: summary.total_trades,
    },
  };
}

// =============================================================================
// BacktestResult → KOLBacktestViewModel (for detail page)
// =============================================================================

/**
 * Convert a backend BacktestResult into the KOLBacktestViewModel
 * consumed by f8-charts components.
 *
 * @param result - BacktestResult from GET /api/backtest/results/{id}
 * @param kolId  - KOL identifier from route params
 */
export function backtestResultToViewModel(
  result: BacktestResult,
  kolId: string,
): KOLBacktestViewModel {
  const snapshots = result.portfolio_snapshots ?? [];

  // --- returnSeries from portfolio_snapshots ---
  const returnSeries: F8ReturnPoint[] = snapshots.map(
    (s: PortfolioSnapshot) => ({
      date: s.date.slice(0, 7), // YYYY-MM
      subject: Number((s.cumulative_return * 100).toFixed(2)),
      benchmark: 0,
      peer: 0,
    }),
  );

  // Deduplicate by month (keep last snapshot per month)
  const monthMap = new Map<string, F8ReturnPoint>();
  for (const point of returnSeries) {
    monthMap.set(point.date, point);
  }
  const dedupedReturnSeries = Array.from(monthMap.values()).sort((a, b) =>
    a.date.localeCompare(b.date),
  );

  // --- annualRows: group snapshots by year ---
  const yearMap = new Map<
    string,
    { snapshots: PortfolioSnapshot[]; trades: typeof result.trades }
  >();
  for (const s of snapshots) {
    const year = s.date.slice(0, 4);
    if (!yearMap.has(year)) {
      yearMap.set(year, { snapshots: [], trades: [] });
    }
    yearMap.get(year)!.snapshots.push(s);
  }
  for (const t of result.trades ?? []) {
    const year = t.exit_date?.slice(0, 4);
    if (year && yearMap.has(year)) {
      yearMap.get(year)!.trades.push(t);
    }
  }

  const annualRows: F8AnnualReturnRow[] = Array.from(yearMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, data]) => {
      const lastSnap = data.snapshots[data.snapshots.length - 1];
      const yearReturn = lastSnap ? lastSnap.cumulative_return * 100 : 0;
      const wins = data.trades.filter((t) => t.net_pnl > 0).length;
      const total = data.trades.length;
      const drawdowns = data.snapshots.map((s) => s.current_drawdown);
      const maxDD = drawdowns.length > 0 ? Math.max(...drawdowns) * 100 : 0;

      return {
        year,
        subject: Number(yearReturn.toFixed(1)),
        benchmark: 0,
        peer: 0,
        hitRate: total > 0 ? Math.round((wins / total) * 100) : 0,
        signalCount: total,
        maxDrawdown: -Number(maxDD.toFixed(1)),
      };
    });

  // --- keyStats ---
  const totalReturnPct = result.total_return * 100;
  const keyStats: KOLBacktestViewModel["keyStats"] = [
    {
      label: "累计收益",
      value: formatPercent(result.total_return),
      subLabel: "",
      tone: totalReturnPct >= 0 ? "positive" : "negative",
    },
    {
      label: "年化收益",
      value: formatPercent(result.annualized_return),
      subLabel: "",
      tone: result.annualized_return >= 0 ? "positive" : "negative",
    },
    {
      label: "夏普比率",
      value: result.sharpe_ratio.toFixed(2),
      subLabel: "",
      tone: result.sharpe_ratio >= 1 ? "positive" : "neutral",
    },
    {
      label: "最大回撤",
      value: formatSignedDrawdown(result.max_drawdown),
      subLabel: "",
      tone: "negative",
    },
    {
      label: "胜率",
      value: `${(result.win_rate * 100).toFixed(1)}%`,
      subLabel: `${result.winning_trades}/${result.total_trades}`,
      tone: "neutral",
    },
    {
      label: "信号数量",
      value: String(result.total_trades),
      subLabel: "",
      tone: "neutral",
    },
  ];

  // --- subjectRiskReturn ---
  const volatilityPct = result.volatility * 100;
  const subjectRiskReturn: F8PeerPoint = {
    id: kolId,
    name: kolId,
    annualizedReturn: Number((result.annualized_return * 100).toFixed(1)),
    volatility: Number(volatilityPct.toFixed(1)),
    hitRate: Math.round(result.win_rate * 100),
    maxDrawdown: Number((result.max_drawdown * 100).toFixed(1)),
  };

  // --- metricRows ---
  const metricRows: F8MetricRow[] = [
    makeMetricRow({
      metric: "夏普比率",
      direction: "higher_is_better",
      subjectValue: result.sharpe_ratio,
      subjectDisplay: result.sharpe_ratio.toFixed(2),
      note: "风险调整后收益，越高越好。",
    }),
    makeMetricRow({
      metric: "最大回撤",
      direction: "lower_is_better",
      subjectValue: result.max_drawdown * 100,
      subjectDisplay: formatSignedDrawdown(result.max_drawdown),
      note: "组合净值峰谷最大跌幅。",
    }),
    makeMetricRow({
      metric: "胜率",
      direction: "higher_is_better",
      subjectValue: result.win_rate * 100,
      subjectDisplay: `${(result.win_rate * 100).toFixed(1)}%`,
      note: "盈利交易占总交易比例。",
    }),
    makeMetricRow({
      metric: "盈亏比",
      direction: "higher_is_better",
      subjectValue: result.profit_factor,
      subjectDisplay: result.profit_factor.toFixed(2),
      note: "总盈利 / 总亏损。",
    }),
    makeMetricRow({
      metric: "平均持仓天数",
      direction: "lower_is_better",
      subjectValue: result.avg_holding_days,
      subjectDisplay: `${result.avg_holding_days.toFixed(1)} 天`,
      note: "所有交易平均持仓周期。",
    }),
    makeMetricRow({
      metric: "Sortino 比率",
      direction: "higher_is_better",
      subjectValue: result.sortino_ratio,
      subjectDisplay: result.sortino_ratio.toFixed(2),
      note: "下行风险调整后收益。",
    }),
  ];

  // --- topCalls: top trades by net_pnl ---
  const sortedTrades = [...(result.trades ?? [])].sort(
    (a, b) => b.net_pnl - a.net_pnl,
  );
  const topCalls: F8TopCall[] = sortedTrades.slice(0, 10).map((t, i) => ({
    id: t.trade_id ?? `trade-${i}`,
    ticker: t.ticker,
    name: t.ticker,
    topic: t.exit_reason ?? "",
    direction: t.side === "short" ? "short" : "long",
    evidenceStrength: 0,
    weight: 0,
    result: Number((t.return_pct * 100).toFixed(1)),
    updatedAt: t.exit_date?.slice(0, 10) ?? "",
  }));

  // --- assumptions ---
  const assumptions: KOLBacktestViewModel["assumptions"] = {
    initialCapital: result.initial_capital,
    positionSize:
      (result.config?.default_position_pct as number) ?? 0.1,
    commissionPct:
      (result.config?.commission_pct as number) ?? 0.001,
    slippagePct: (result.config?.slippage_pct as number) ?? 0.0005,
    executionDelay: "T+0",
    holdingRule: `默认 ${result.config?.max_holding_days ?? 30} 天`,
    feesIncluded: true,
  };

  return {
    subject: {
      id: kolId,
      name: kolId,
      platform: "",
      biography: "",
      tags: [],
    },
    benchmark: { id: "N/A", name: "基准（暂无）" },
    cohort: {
      id: "single",
      name: "单 KOL 回测",
      definition: "",
      peerCount: 0,
    },
    dateRange: {
      start: result.start_date.slice(0, 10),
      end: result.end_date.slice(0, 10),
    },
    dataCutoff: result.end_date.slice(0, 10),
    assumptions,
    keyStats,
    returnSeries: dedupedReturnSeries,
    annualRows,
    subjectRiskReturn,
    peerRiskReturn: [],
    cohortMedian: { annualizedReturn: 0, volatility: 0 },
    metricRows,
    topCalls,
  };
}

// =============================================================================
// KOLListItemRaw → KOL (for kol list page)
// =============================================================================

/** Convert a backend KOLListItem (snake_case) into the frontend KOL type. */
export function kolListItemToKOL(raw: KOLListItemRaw): KOL {
  const dimScores = raw.dimension_scores;
  return {
    id: raw.id,
    name: raw.name,
    platform: (raw.platform || "wechat") as KOL["platform"],
    platformId: raw.platform_id,
    overallScore: raw.overall_score,
    dimensionScores: {
      accuracy: dimScores.accuracy ?? 0,
      timeliness: dimScores.timeliness ?? 0,
      clarity: dimScores.clarity ?? 0,
      depth: dimScores.depth ?? 0,
      consistency: dimScores.consistency ?? 0,
    },
    accuracy: raw.accuracy,
    avgReturn: raw.avg_return,
    totalOpinions: raw.total_opinions,
    lastActive: raw.last_active,
    tags: raw.tags,
    enabled: raw.enabled,
  };
}

// =============================================================================
// KOLRatingResponse → KOLDetail (for kol detail page)
// =============================================================================

/** Convert a backend KOLRatingResponse into the KOLDetail view model. */
export function kolRatingToDetail(
  resp: KOLRatingResponse,
  kolId: string,
): KOLDetail {
  const r = resp.rating;
  const dimScores: KOLDetail["dimensionScores"] = {
    accuracy: 0,
    timeliness: 0,
    clarity: 0,
    depth: 0,
    consistency: 0,
  };
  for (const d of resp.dimensions) {
    if (d.dimension in dimScores) {
      dimScores[d.dimension as keyof typeof dimScores] = d.score;
    }
  }

  const totalOpinions = r.totalOpinions;
  const correctCount = Math.round(r.successRate * totalOpinions);

  const timeline: KOLTimelineEvent[] = resp.recentOpinions.map((o) => ({
    id: o.id,
    kolId,
    date: o.timestamp.slice(0, 10),
    ticker: o.ticker,
    direction: o.direction as KOLTimelineEvent["direction"],
    summary: o.ticker_name ? `${o.ticker_name} — ${o.direction}` : o.direction,
    return: undefined,
  }));

  const avgReturn = r.avgReturn;

  return {
    id: kolId,
    name: r.name,
    platform: (r.platform || "wechat") as KOL["platform"],
    platformId: "",
    overallScore: r.overallRating,
    dimensionScores: dimScores,
    accuracy: Math.round(r.successRate * 100),
    avgReturn,
    totalOpinions,
    lastActive: resp.timeline[0]?.date ?? "",
    tags: resp.focusAreas.slice(0, 3),
    enabled: true,
    stats: {
      totalOpinions,
      correctCount,
      avgReturn,
      maxReturn: 0,
      minReturn: 0,
      avgHoldingDays: 0,
    },
    timeline,
  };
}
