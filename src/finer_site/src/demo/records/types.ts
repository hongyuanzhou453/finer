/**
 * TypeScript mirror of the frozen /records-data snapshot JSON
 * (public/records-data/manifest.json + creator-N.json).
 *
 * The snapshot is a static archive frozen at 2026-08-10 — historical
 * records only, never live data. Shapes here follow the exported files
 * exactly; do not "improve" fields without regenerating the export.
 */

export type SignalClass = "broker_recommendation" | "broker_sector_view";

/**
 * Effect gate emitted by the backend sufficiency engine.
 * UI contract (red line): `count_only` ⇒ render NO ratio anywhere;
 * `show_with_warning` ⇒ ratio allowed but the warning note must ride along.
 */
export type DisplayPolicy = "show" | "show_with_warning" | "count_only";

export type SufficiencyTier = "sufficient" | "provisional" | "insufficient";

export interface PredictiveClaim {
  metric: string;
  /** Always false today — persistence test failed; never imply prediction. */
  permitted: boolean;
  tested_at: string;
  sample_size: number;
  evidence: string;
  summary: string;
  scope_note: string;
}

export interface Sufficiency {
  settled_n: number;
  total_n: number;
  successes: number;
  point_estimate: number;
  wilson_low: number;
  wilson_high: number;
  ci_width: number;
  confidence: number;
  coverage_ratio: number;
  coverage_penalised: boolean;
  tier: SufficiencyTier;
  display_policy: DisplayPolicy;
  /** null on sector cards (metric untested at that granularity). */
  predictive_claim: PredictiveClaim | null;
  notes: string[];
}

export interface RecordCard {
  creator_id: string;
  signal_class: SignalClass;
  n_total: number;
  n_settled: number;
  wins: number;
  /**
   * 全未结算的信源为 null。类型曾写 `number`，而快照里实实在在有 null——
   * `fmtSignedPct(null)` 走 `Math.abs(null)=0` 印出「0.0%」，凭空造了个数字，
   * 编译器一句没报。类型说了实话，tsc 才逼得出全部空值分支。
   */
  mean_return: number | null;
  median_return: number | null;
  expected_win_rate: number | null;
  /** market code → action count, e.g. { US: 130, CN: 101 } */
  market_mix: Record<string, number>;
  first_action_at: string;
  last_action_at: string;
  sufficiency: Sufficiency;
  /** Rows file mixes BOTH signal classes — always filter by signal_class. */
  rows_file: string;
}

export interface RecordsManifest {
  as_of: string;
  note: string;
  total_actions: number;
  settled_actions: number;
  signal_classes: SignalClass[];
  cards: Record<SignalClass, RecordCard[]>;
}

export type RowDirection = "bullish" | "bearish" | "neutral";

export type SettleStatus = "settled" | "pending";

export interface RowSettle {
  status: SettleStatus;
  win?: boolean;
  return_pct?: number;
  holding_days?: number;
  exit_reason?: string;
}

export interface RecordRow {
  id: string;
  intent_id: string;
  signal_class: SignalClass;
  report_date: string;
  published_at: string;
  executable_at: string;
  ticker: string;
  name: string;
  market: string;
  direction: RowDirection;
  rating: string | null;
  rating_prior: string | null;
  target_price: number | null;
  target_price_currency: string | null;
  action_type: string;
  time_horizon: string;
  evidence_span_count: number;
  canonical: boolean;
  settle: RowSettle;
}

export interface CreatorRowsFile {
  as_of: string;
  creator_id: string;
  /** Total rows across both signal classes — NOT the per-class card n_total. */
  n_rows: number;
  rows: RecordRow[];
}
