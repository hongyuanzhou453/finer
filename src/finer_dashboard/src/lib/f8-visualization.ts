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
