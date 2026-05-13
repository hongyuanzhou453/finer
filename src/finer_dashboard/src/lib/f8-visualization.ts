import { mean, quantile, standardDeviation } from "simple-statistics";

export type MetricDirection = "higher_is_better" | "lower_is_better";

export type F8ReturnPoint = {
  date: string;
  subject: number;
  benchmark: number;
  peer: number;
  missing?: boolean;
};

export type F8AnnualReturnRow = {
  year: string;
  subject: number;
  benchmark: number;
  peer: number;
  hitRate: number;
  signalCount: number;
  maxDrawdown: number;
};

export type F8PeerPoint = {
  id: string;
  name: string;
  annualizedReturn: number;
  volatility: number;
  hitRate: number;
  maxDrawdown: number;
};

export type F8MetricRow = {
  metric: string;
  direction: MetricDirection;
  subjectValue: number;
  subjectDisplay: string;
  cohortAverage: number;
  cohortDisplay: string;
  percentile: number;
  note: string;
};

export type F8TopCall = {
  id: string;
  ticker: string;
  name: string;
  topic: string;
  direction: "long" | "short";
  evidenceStrength: number;
  weight: number;
  result: number;
  updatedAt: string;
};

export type F8BacktestAssumptions = {
  initialCapital: number;
  positionSize: number;
  commissionPct: number;
  slippagePct: number;
  executionDelay: string;
  holdingRule: string;
  feesIncluded: boolean;
};

export type KOLBacktestViewModel = {
  subject: {
    id: string;
    name: string;
    platform: string;
    biography: string;
    tags: string[];
  };
  benchmark: {
    id: string;
    name: string;
  };
  cohort: {
    id: string;
    name: string;
    definition: string;
    peerCount: number;
  };
  dateRange: {
    start: string;
    end: string;
  };
  dataCutoff: string;
  assumptions: F8BacktestAssumptions;
  keyStats: Array<{
    label: string;
    value: string;
    subLabel: string;
    tone: "positive" | "negative" | "neutral";
  }>;
  returnSeries: F8ReturnPoint[];
  annualRows: F8AnnualReturnRow[];
  subjectRiskReturn: F8PeerPoint;
  peerRiskReturn: F8PeerPoint[];
  cohortMedian: {
    annualizedReturn: number;
    volatility: number;
  };
  metricRows: F8MetricRow[];
  topCalls: F8TopCall[];
};

const monthlyDates = [
  "2025-01",
  "2025-02",
  "2025-03",
  "2025-04",
  "2025-05",
  "2025-06",
  "2025-07",
  "2025-08",
  "2025-09",
  "2025-10",
  "2025-11",
  "2025-12",
  "2026-01",
  "2026-02",
  "2026-03",
  "2026-04",
];

const subjectMonthly = [
  2.4, 3.1, -1.6, 4.8, 5.2, -2.3, 6.4, 2.8,
  3.9, -4.1, 5.7, 6.2, 4.9, 2.6, -3.2, 5.4,
];

const benchmarkMonthly = [
  1.2, 2.3, -2.4, 3.1, 1.8, -1.6, 3.6, 1.2,
  2.2, -3.4, 2.7, 3.1, 2.5, 1.1, -2.1, 2.2,
];

const peerMonthly = [
  1.6, 1.7, -1.8, 2.6, 2.4, -1.3, 3.1, 1.8,
  2.4, -2.5, 3.0, 3.5, 2.7, 1.4, -1.9, 2.8,
];

const peerReturns = [
  6.2, 9.8, 11.4, 14.1, 5.7, 17.8, 21.2, 8.5,
  13.2, 3.9, 18.7, 24.4, 10.6, 15.1, 7.3, 19.4,
  12.8, 16.3, 4.8, 22.1, 9.1, 13.9, 18.0, 11.7,
];

const peerVolatility = [
  13.4, 16.8, 19.2, 21.5, 12.9, 24.1, 28.6, 17.2,
  20.5, 14.6, 26.4, 31.2, 18.0, 22.6, 15.8, 27.3,
  20.1, 23.7, 13.8, 29.8, 17.6, 21.1, 25.8, 18.9,
];

function cumulativeReturn(values: number[]): number[] {
  let current = 1;
  return values.map((value) => {
    current *= 1 + value / 100;
    return Number(((current - 1) * 100).toFixed(2));
  });
}

function percentileRank(
  peerValues: number[],
  subjectValue: number,
  direction: MetricDirection,
): number {
  const betterOrEqual = peerValues.filter((value) =>
    direction === "higher_is_better"
      ? subjectValue >= value
      : subjectValue <= value,
  ).length;

  return Math.round((betterOrEqual / peerValues.length) * 100);
}

function formatPercent(value: number, digits = 1): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}%`;
}

function formatSignedDrawdown(value: number): string {
  return `-${Math.abs(value).toFixed(1)}%`;
}

function makeMetricRow(params: {
  metric: string;
  direction: MetricDirection;
  subjectValue: number;
  subjectDisplay: string;
  cohortAverage: number;
  cohortDisplay: string;
  peers: number[];
  note: string;
}): F8MetricRow {
  return {
    metric: params.metric,
    direction: params.direction,
    subjectValue: params.subjectValue,
    subjectDisplay: params.subjectDisplay,
    cohortAverage: params.cohortAverage,
    cohortDisplay: params.cohortDisplay,
    percentile: percentileRank(
      params.peers,
      params.subjectValue,
      params.direction,
    ),
    note: params.note,
  };
}

/**
 * @deprecated Use `backtestResultToViewModel` from `./adapters` instead.
 * This function returns hard-coded mock data and will be removed in a future cleanup.
 */
export function createMockKOLBacktestViewModel(
  kolId: string,
): KOLBacktestViewModel {
  const subjectCumulative = cumulativeReturn(subjectMonthly);
  const benchmarkCumulative = cumulativeReturn(benchmarkMonthly);
  const peerCumulative = cumulativeReturn(peerMonthly);

  const returnSeries = monthlyDates.map((date, index) => ({
    date,
    subject: subjectCumulative[index],
    benchmark: benchmarkCumulative[index],
    peer: peerCumulative[index],
    missing: index === 9,
  }));

  const peerRiskReturn = peerReturns.map((annualizedReturn, index) => ({
    id: `peer-${index + 1}`,
    name: `同类 KOL ${index + 1}`,
    annualizedReturn,
    volatility: peerVolatility[index],
    hitRate: 45 + ((index * 7) % 31),
    maxDrawdown: 8 + ((index * 5) % 24),
  }));

  const annualizedReturn = 32.5;
  const volatility = Number(standardDeviation(subjectMonthly).toFixed(2)) * Math.sqrt(12);
  const subjectRiskReturn = {
    id: kolId,
    name: "投研老王",
    annualizedReturn,
    volatility: Number(volatility.toFixed(1)),
    hitRate: 68,
    maxDrawdown: 12.3,
  };

  const medianReturn = Number(quantile(peerReturns, 0.5).toFixed(1));
  const medianVolatility = Number(quantile(peerVolatility, 0.5).toFixed(1));
  const peerMeanReturn = Number(mean(peerReturns).toFixed(1));
  const peerMeanVolatility = Number(mean(peerVolatility).toFixed(1));

  const metricRows = [
    makeMetricRow({
      metric: "观点命中率",
      direction: "higher_is_better",
      subjectValue: 68,
      subjectDisplay: "68.0%",
      cohortAverage: 54,
      cohortDisplay: "54.0%",
      peers: peerRiskReturn.map((point) => point.hitRate),
      note: "按观点有效期结束后的方向正确率计算。",
    }),
    makeMetricRow({
      metric: "Alpha",
      direction: "higher_is_better",
      subjectValue: 12.4,
      subjectDisplay: "+12.4%",
      cohortAverage: 4.1,
      cohortDisplay: "+4.1%",
      peers: peerReturns.map((value) => value - 8),
      note: "相对沪深 300 与主题 beta 的残差收益。",
    }),
    makeMetricRow({
      metric: "最大回撤",
      direction: "lower_is_better",
      subjectValue: 12.3,
      subjectDisplay: formatSignedDrawdown(12.3),
      cohortAverage: 18.7,
      cohortDisplay: formatSignedDrawdown(18.7),
      peers: peerRiskReturn.map((point) => point.maxDrawdown),
      note: "越低越好，按组合净值峰谷回撤计算。",
    }),
    makeMetricRow({
      metric: "兑现速度",
      direction: "lower_is_better",
      subjectValue: 8.6,
      subjectDisplay: "8.6 天",
      cohortAverage: 14.2,
      cohortDisplay: "14.2 天",
      peers: [9, 18, 11, 13, 21, 16, 7, 24, 14, 12, 19, 10],
      note: "观点发布后达到主要收益贡献的中位天数。",
    }),
    makeMetricRow({
      metric: "证据质量",
      direction: "higher_is_better",
      subjectValue: 82,
      subjectDisplay: "82 / 100",
      cohortAverage: 67,
      cohortDisplay: "67 / 100",
      peers: [52, 61, 66, 70, 74, 58, 81, 63, 69, 77, 73, 56],
      note: "基于证据跨度、实体锚定和可审计来源质量。",
    }),
    makeMetricRow({
      metric: "时效性",
      direction: "higher_is_better",
      subjectValue: 74,
      subjectDisplay: "74 / 100",
      cohortAverage: 61,
      cohortDisplay: "61 / 100",
      peers: [45, 58, 64, 71, 55, 67, 63, 49, 76, 59, 52, 69],
      note: "观点发布时间相对可执行价格窗口的有效性。",
    }),
    makeMetricRow({
      metric: "观点波动",
      direction: "lower_is_better",
      subjectValue: subjectRiskReturn.volatility,
      subjectDisplay: `${subjectRiskReturn.volatility.toFixed(1)}%`,
      cohortAverage: peerMeanVolatility,
      cohortDisplay: `${peerMeanVolatility.toFixed(1)}%`,
      peers: peerVolatility,
      note: "越低越好，反映观点组合净值波动。",
    }),
    makeMetricRow({
      metric: "观点一致性",
      direction: "higher_is_better",
      subjectValue: 71,
      subjectDisplay: "71 / 100",
      cohortAverage: 58,
      cohortDisplay: "58 / 100",
      peers: [44, 51, 62, 57, 66, 73, 48, 59, 61, 53, 69, 56],
      note: "同主题连续观点是否自洽，反向更新会降低分数。",
    }),
  ];

  return {
    subject: {
      id: kolId,
      name: "投研老王",
      platform: "微信公众号",
      biography:
        "偏科技与半导体周期跟踪，观点多围绕产业链景气、订单变化与估值切换。当前样例为 F8 可视化演示数据。",
      tags: ["科技成长", "半导体", "事件驱动", "中高频"],
    },
    benchmark: {
      id: "CSI300",
      name: "沪深 300",
    },
    cohort: {
      id: "tech-growth-kol",
      name: "科技成长 KOL 同类组",
      definition: "近 18 个月至少 40 条科技/半导体观点，且具备可执行时间锚的 KOL。",
      peerCount: peerRiskReturn.length,
    },
    dateRange: {
      start: "2025-01-01",
      end: "2026-04-30",
    },
    dataCutoff: "2026-04-30",
    assumptions: {
      initialCapital: 100000,
      positionSize: 0.1,
      commissionPct: 0.001,
      slippagePct: 0.0005,
      executionDelay: "T+1 开盘成交",
      holdingRule: "默认 30 天，到期或反向信号退出",
      feesIncluded: true,
    },
    keyStats: [
      {
        label: "累计收益",
        value: formatPercent(subjectCumulative.at(-1) ?? 0),
        subLabel: `同类均值 ${formatPercent(peerCumulative.at(-1) ?? 0)}`,
        tone: "positive",
      },
      {
        label: "年化收益",
        value: formatPercent(annualizedReturn),
        subLabel: `同类均值 ${formatPercent(peerMeanReturn)}`,
        tone: "positive",
      },
      {
        label: "夏普比率",
        value: "1.85",
        subLabel: "风险调整后优于同类",
        tone: "positive",
      },
      {
        label: "最大回撤",
        value: formatSignedDrawdown(12.3),
        subLabel: `同类均值 ${formatSignedDrawdown(18.7)}`,
        tone: "negative",
      },
      {
        label: "观点命中率",
        value: "68.0%",
        subLabel: "已验证观点 106 / 156",
        tone: "neutral",
      },
      {
        label: "信号数量",
        value: "156",
        subLabel: "覆盖 23 个标的",
        tone: "neutral",
      },
    ],
    returnSeries,
    annualRows: [
      {
        year: "2025",
        subject: 38.7,
        benchmark: 15.1,
        peer: 20.4,
        hitRate: 66,
        signalCount: 112,
        maxDrawdown: -10.8,
      },
      {
        year: "2026 YTD",
        subject: 9.5,
        benchmark: 3.6,
        peer: 5.1,
        hitRate: 71,
        signalCount: 44,
        maxDrawdown: -6.2,
      },
    ],
    subjectRiskReturn,
    peerRiskReturn,
    cohortMedian: {
      annualizedReturn: medianReturn,
      volatility: medianVolatility,
    },
    metricRows,
    topCalls: [
      {
        id: "call-nvda",
        ticker: "NVDA",
        name: "英伟达",
        topic: "AI 算力链",
        direction: "long",
        evidenceStrength: 88,
        weight: 12.5,
        result: 15.5,
        updatedAt: "2026-02-20",
      },
      {
        id: "call-tsla",
        ticker: "TSLA",
        name: "特斯拉",
        topic: "竞争格局",
        direction: "short",
        evidenceStrength: 76,
        weight: 8.0,
        result: 7.1,
        updatedAt: "2026-03-15",
      },
      {
        id: "call-aapl",
        ticker: "AAPL",
        name: "苹果",
        topic: "服务收入",
        direction: "long",
        evidenceStrength: 64,
        weight: 7.5,
        result: -2.8,
        updatedAt: "2026-03-10",
      },
      {
        id: "call-amd",
        ticker: "AMD",
        name: "超威半导体",
        topic: "GPU 份额",
        direction: "long",
        evidenceStrength: 71,
        weight: 6.5,
        result: 5.6,
        updatedAt: "2026-04-18",
      },
    ],
  };
}
