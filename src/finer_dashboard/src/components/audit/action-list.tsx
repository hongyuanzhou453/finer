"use client";

import { cn } from "@/lib/utils";
import type { TradeActionSummary, TradeDirection } from "@/lib/contracts";
import { TraceStatusBadge } from "./trace-status-badge";
import { Pill, type Tone } from "./primitives";

const DIRECTION: Record<TradeDirection, { label: string; tone: Tone }> = {
  bullish: { label: "看多", tone: "red" },
  bearish: { label: "看空", tone: "green" },
  neutral: { label: "中性", tone: "neutral" },
  watchlist: { label: "观察", tone: "gold" },
  risk_warning: { label: "风险提示", tone: "green" },
};

function pct(v: number) {
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

export function ActionList({
  actions,
  activeId,
  onSelect,
}: {
  actions: TradeActionSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  if (actions.length === 0) {
    return (
      <div className="px-4 py-10 text-center text-[12px] text-foreground/40">
        无匹配的交易动作
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 p-3">
      {actions.map((a) => {
        const on = a.trade_action_id === activeId;
        const dir = DIRECTION[a.direction];
        return (
          <button
            key={a.trade_action_id}
            type="button"
            onClick={() => onSelect(a.trade_action_id)}
            className={cn(
              "rounded-sm border px-3 py-2.5 text-left transition-colors",
              on
                ? "border-l-2 border-morningstar-red bg-white shadow-[var(--shadow-soft)]"
                : "border-[var(--table-border)] bg-[var(--surface-strong)] hover:bg-white",
            )}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-[13px] font-bold text-foreground">{a.ticker}</span>
              <span className="min-w-0 truncate text-[11px] text-foreground/45">
                {a.company_name}
              </span>
              <span className="grow" />
              <Pill tone={dir.tone}>{dir.label}</Pill>
            </div>

            <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-[var(--ink-soft)]">
              {a.summary}
            </p>

            <div className="mt-1.5 flex items-center justify-between gap-2">
              <TraceStatusBadge status={a.canonical_trace_status} size="sm" />
              {typeof a.backtest_return_pct === "number" && (
                <span
                  className={cn(
                    "tabular-nums text-[12px] font-bold",
                    a.backtest_return_pct >= 0 ? "text-morningstar-red" : "text-[#0f9b6c]",
                  )}
                >
                  {pct(a.backtest_return_pct)}
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
