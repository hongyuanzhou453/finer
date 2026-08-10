/**
 * Shared presentational atoms + formatters for the /records snapshot page.
 * Institutional discipline: mono tabular numbers; red = up / win, green =
 * down / loss (site-wide China market convention, --chart-up / --chart-down).
 */
import type {
  RowDirection,
  RowSettle,
  SignalClass,
  SufficiencyTier,
} from "@/demo/records/types";

// ---- labels -----------------------------------------------------------------

export const SIGNAL_CLASS_LABEL: Record<SignalClass, string> = {
  broker_recommendation: "个股评级",
  broker_sector_view: "板块观点",
};

export const DIRECTION_META: Record<
  RowDirection,
  { label: string; color: string }
> = {
  bullish: { label: "看多", color: "var(--chart-up)" },
  bearish: { label: "看空", color: "var(--chart-down)" },
  neutral: { label: "中性", color: "#8a8278" },
};

const TIME_HORIZON_LABEL: Record<string, string> = {
  short_term: "短线",
  medium_term: "中线",
  long_term: "长线",
  review_required: "需复核",
};

const ACTION_TYPE_LABEL: Record<string, string> = {
  long: "做多",
  reduce: "减仓",
  watch: "观察",
};

const EXIT_REASON_LABEL: Record<string, string> = {
  time_exit: "到期离场",
  stop_loss: "止损离场",
  target_reached: "到达目标价",
  end_of_period: "期末结算",
};

export function horizonLabel(v: string): string {
  return TIME_HORIZON_LABEL[v] ?? v;
}

export function actionTypeLabel(v: string): string {
  return ACTION_TYPE_LABEL[v] ?? v;
}

export function exitReasonLabel(v: string | undefined): string {
  if (!v) return "—";
  return EXIT_REASON_LABEL[v] ?? v;
}

// ---- formatters -------------------------------------------------------------

/** 0.4624 → "46.2%" (unsigned, for rates). */
export function fmtRate(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** 0.0418 → "+4.2%" (signed, for returns). */
export function fmtSignedPct(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${(Math.abs(value) * 100).toFixed(digits)}%`;
}

/** ISO timestamp → "YYYY-MM-DD". */
export function fmtDate(iso: string): string {
  return iso.slice(0, 10);
}

/** Return-value color per site convention: red positive, green negative. */
export function returnColor(value: number): string {
  if (value > 0) return "var(--chart-up)";
  if (value < 0) return "var(--chart-down)";
  return "var(--ink-soft)";
}

// ---- tier badge -------------------------------------------------------------

const TIER_META: Record<SufficiencyTier, { label: string; color: string }> = {
  sufficient: { label: "样本充分", color: "var(--accent-teal)" },
  provisional: { label: "临界样本", color: "var(--accent-gold)" },
  insufficient: { label: "样本不足", color: "#8a8278" },
};

export function TierBadge({ tier }: { tier: SufficiencyTier }) {
  const meta = TIER_META[tier];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
      style={{
        color: meta.color,
        backgroundColor: `color-mix(in srgb, ${meta.color} 10%, transparent)`,
        border: `1px solid color-mix(in srgb, ${meta.color} 30%, transparent)`,
      }}
    >
      {meta.label}
    </span>
  );
}

// ---- direction chip ---------------------------------------------------------

export function DirectionChip({ direction }: { direction: RowDirection }) {
  const meta = DIRECTION_META[direction];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium"
      style={{
        color: meta.color,
        backgroundColor: `color-mix(in srgb, ${meta.color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${meta.color} 32%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
    </span>
  );
}

// ---- settle chip (red win / green loss / grey pending) ----------------------

export function SettleChip({ settle }: { settle: RowSettle }) {
  if (settle.status === "pending") {
    return (
      <span className="inline-flex items-center rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] text-[var(--ink-soft)]">
        待结算
      </span>
    );
  }
  const win = settle.win === true;
  const color = win ? "var(--chart-up)" : "var(--chart-down)";
  const pct =
    typeof settle.return_pct === "number"
      ? fmtSignedPct(settle.return_pct)
      : "—";
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      <span
        className="tabular-nums text-[12px] font-semibold"
        style={{ color }}
      >
        {win ? "验证" : "未验证"} {pct}
      </span>
      {typeof settle.holding_days === "number" ? (
        <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
          持有 {settle.holding_days} 天
        </span>
      ) : null}
    </span>
  );
}
