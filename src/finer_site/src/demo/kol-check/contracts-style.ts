/**
 * Trading-style contract slice — mirrors the Pydantic schema
 * `src/finer/schemas/kol_profile.py` (DeclaredTradingStyle / ObservedTradingStyle /
 * TradingStyleProfile). Copied here so the static demo doesn't drag the dashboard's
 * full contracts.ts. Field names/optionality match the backend + ./data.json.
 */

export type EntryStyle = "left_side" | "right_side" | "mixed" | "unknown";

export interface DeclaredTradingStyle {
  uses_margin: boolean | null;
  uses_leverage: boolean | null;
  does_short: boolean | null;
  entry_style: EntryStyle;
  evidence_notes: string[];
}

export interface ObservedTradingStyle {
  sample_size: number;
  directional_sample_size: number;
  short_side_count: number;
  short_ratio: number | null;
  margin_mention_count: number;
  leverage_mention_count: number;
  left_side_count: number;
  right_side_count: number;
  entry_style_observed: EntryStyle;
  entry_style_sample_size: number;
  low_sample: boolean;
  computed_at: string;
  window_label: string;
}

export interface TradingStyleProfile {
  creator_id: string;
  display_name: string;
  declared: DeclaredTradingStyle | null;
  observed: ObservedTradingStyle | null;
}
