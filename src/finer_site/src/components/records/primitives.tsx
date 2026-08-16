/**
 * records 领域 primitives：共享原子一律来自 components/shared/primitives
 * （唯一真相源），本文件只保留 /records 快照页的领域词表（signal class、
 * 期限、动作、离场原因）与 SettleChip。
 */
import type { RowSettle, SignalClass } from "@/demo/records/types";
import { fmtSignedPct } from "../shared/primitives";

export {
  DIRECTION_META,
  TierBadge,
  fmtDate,
  fmtRate,
  fmtSignedPct,
  returnColor,
} from "../shared/primitives";

/** 兼容别名：records 侧历史上叫 DirectionChip（默认 sm 尺寸，签名不变）。 */
export { DirectionTag as DirectionChip } from "../shared/primitives";

// ---- domain labels ----------------------------------------------------------

export const SIGNAL_CLASS_LABEL: Record<SignalClass, string> = {
  broker_recommendation: "个股评级",
  broker_sector_view: "板块观点",
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
