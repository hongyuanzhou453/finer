/**
 * Demo-only TypeScript types for the Finer OS interactive demo.
 *
 * Field names mirror the real Pydantic schemas under src/finer/schemas/
 * (trade_action.py, investment_intent.py, evidence.py) so the demo reads
 * like the real product — but ALL values are fabricated sample data and the
 * demo never touches a backend.
 */

export type TradeDirection =
  | "bullish"
  | "bearish"
  | "neutral"
  | "watchlist"
  | "risk_warning";

export type ActionType =
  | "long"
  | "short"
  | "close_long"
  | "close_short"
  | "buy_and_hold"
  | "hold"
  | "watch";

export type TriggerType =
  | "price_threshold"
  | "breakout"
  | "support_resistance"
  | "indicator_signal"
  | "time_based"
  | "news_event"
  | "manual";

export type ValidationStatus = "pending" | "verified" | "failed" | "under_review";

export type MarketSession =
  | "pre_market"
  | "regular"
  | "after_close"
  | "non_trading_day"
  | "unknown";

export type ExitReason =
  | "target_reached"
  | "stop_loss"
  | "time_exit"
  | "signal_reversal"
  | "manual"
  | "unknown";

export interface EvidenceSpan {
  evidence_span_id: string;
  char_start: number;
  char_end: number;
  text: string;
  confidence: number;
  span_type: string;
}

export interface IntentLite {
  intent_id: string;
  target_name: string;
  target_symbol: string;
  direction: string;
  conviction: number;
  sentiment_score: number;
  time_horizon_hint: string;
  actionability: string;
}

export interface ExecutionTiming {
  intent_published_at: string;
  intent_effective_at: string;
  action_decision_at: string;
  action_executable_at: string;
  market: string;
  timezone: string;
  market_session_at_publish: MarketSession;
}

export interface ActionStep {
  sequence: number;
  action_type: ActionType;
  trigger_type: TriggerType;
  trigger_condition: string;
  target_price_low: number | null;
  target_price_high: number | null;
  position_size_pct: number | null;
  notes: string;
}

export interface BacktestLite {
  return_pct: number;
  holding_days: number;
  exit_reason: ExitReason;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  backtest_period: string;
}

export interface RlhfLite {
  rating: number | null;
  is_correct: boolean | null;
  corrected_direction: TradeDirection | null;
  corrections: string[];
  reviewer_id: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
}

export interface TradeAction {
  trade_action_id: string;
  timestamp: string;
  ticker: string;
  company_name: string;
  market: string;
  direction: TradeDirection;
  summary: string;
  action_chain: ActionStep[];
  intent_id: string;
  policy_id: string;
  evidence_span_ids: string[];
  canonical_trace_status: "canonical" | "non_canonical" | "partial";
  confidence: number;
  validation_status: ValidationStatus;
  model_version: string;
  extraction_method: string;
  execution_timing: ExecutionTiming;
  intent: IntentLite;
  evidence: EvidenceSpan[];
  source_text: string;
  source_published_at: string;
  backtest: BacktestLite;
  rlhf: RlhfLite;
}

export interface SeriesPoint {
  date: string;
  value: number;
  benchmark: number;
}

export interface KolMetrics {
  cum_return: number;
  annualized: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  signal_count: number;
}

export interface CapabilityScore {
  label: string;
  value: number;
}

export interface Kol {
  id: string;
  handle: string;
  name: string;
  style: string;
  rating: number;
  backtest_count: number;
  tickers: string[];
  period: string;
  blurb: string;
  metrics: KolMetrics;
  capability: CapabilityScore[];
  series: SeriesPoint[];
  trade_actions: TradeAction[];
}

export type StageRole = "AI" | "人" | "规则";

export interface StageDetail {
  id: string;
  name: string;
  role: StageRole;
  headline: string;
  what: string;
  output: { k: string; v: string }[];
  schema_ref: string;
}

// ---- annotation demo (标注全流程) -------------------------------------------
// Demo-only types for the interactive annotation walkthrough. Field names echo
// the real pipeline (eval_set.jsonl gold, DPO pairs, RLHFFeedback) and the RLVR
// reward axes from docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md — but ALL
// values are fabricated and scored by a deterministic demo function, never a
// real model or backend.

export type AnnotationTaskId = "gold" | "preference" | "f6";

/** One model extraction candidate — shape mirrors the simplified extraction JSON. */
export interface ExtractionDraft {
  ticker: string;
  direction: TradeDirection;
  conviction: number; // 0-1
  action: ActionType;
  target_price_low: number | null;
  target_price_high: number | null;
  rationale: string;
}

/**
 * RLVR verifier score for one ExtractionDraft against its source evidence.
 * Axes align with the planned src/finer/ml/rewards.py (structure gate +
 * grounding / calibration / abstention). Computed deterministically in the demo.
 */
export interface RewardBreakdown {
  total: number; // [0,1]; structure fail -> 0
  structurePass: boolean; // gate
  grounding: number; // [0,1]
  calibration: number; // [0,1]
  abstention: number; // [0,1]
  committal: boolean; // direction ∈ {bullish, bearish}
  notes: string[]; // human-readable reasons
}

/** Task 1 — held-out eval gold annotation (human verification set). */
export interface GoldTask {
  id: string;
  persona: string;
  passage: string;
  expected_abstain: boolean;
  reference_gold: {
    direction: TradeDirection;
    ticker: string;
    conviction: number;
    note: string;
  };
}

/** Task 2 — DPO preference pair review (chosen ≻ rejected). */
export interface PreferencePair {
  id: string;
  persona: string;
  prompt: string; // source evidence text
  chosen: ExtractionDraft;
  rejected: ExtractionDraft;
  rationale: string; // why chosen beats rejected
}

/** Task 3 — F6 field-level correction → preference (environment B flywheel). */
export interface F6Case {
  id: string;
  trade_action_id: string;
  persona: string;
  passage: string;
  model_output: ExtractionDraft; // the rejected (model's original error)
  flagged: string; // what's wrong
}

export interface AnnotationProgress {
  gold: number;
  pairs: number;
  f6: number;
}
