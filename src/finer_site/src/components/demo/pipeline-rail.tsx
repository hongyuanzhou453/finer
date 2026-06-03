"use client";

import { cn } from "@/lib/utils";
import type { StageDetail, StageRole } from "@/demo/types";

const ROLE_STYLE: Record<StageRole, string> = {
  AI: "bg-[rgba(225,27,34,0.08)] text-morningstar-red border border-[rgba(225,27,34,0.18)]",
  人: "bg-[rgba(155,123,69,0.12)] text-[var(--accent-gold)] border border-[rgba(155,123,69,0.25)]",
  规则: "bg-[var(--surface-muted)] text-[var(--ink-soft)] border border-[var(--table-border)]",
};

/**
 * Interaction #1 — walk the canonical F0-F8 pipeline.
 * Click a stage to see what that stage produced for the sample content.
 * Controlled component: parent owns `activeId`.
 */
export function PipelineRail({
  stages,
  activeId,
  onSelect,
}: {
  stages: StageDetail[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const active = stages.find((s) => s.id === activeId) ?? stages[0];

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/45">
          F0 → F8 流水线走查
        </span>
        <span className="font-mono text-[10px] text-foreground/40">
          样本：老纪 · 600519 贵州茅台
        </span>
      </div>

      {/* clickable rail */}
      <div className="flex items-stretch gap-0.5 overflow-x-auto finer-scrollbar">
        {stages.map((s) => {
          const on = s.id === active.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelect(s.id)}
              aria-pressed={on}
              className={cn(
                "flex min-w-[56px] flex-1 flex-col items-center gap-1 border-t-2 px-1.5 py-2 transition-colors",
                on
                  ? "border-morningstar-red bg-white"
                  : "border-[var(--table-border)] bg-[var(--surface-strong)] hover:bg-white",
              )}
            >
              <span
                className={cn(
                  "text-[11px] font-bold tabular-nums",
                  on ? "text-morningstar-red" : "text-foreground/70",
                )}
              >
                {s.id}
              </span>
              <span className="whitespace-nowrap text-[10px] text-[var(--ink-soft)]">
                {s.headline}
              </span>
            </button>
          );
        })}
      </div>

      {/* stage detail */}
      <div className="mt-3 rounded-sm border border-[var(--table-border)] bg-white p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-bold tabular-nums text-morningstar-red">
            {active.id}
          </span>
          <span className="text-[14px] font-bold text-foreground">{active.name}</span>
          <span
            className={cn(
              "rounded-sm px-1.5 py-0.5 text-[10px] font-bold tracking-wider",
              ROLE_STYLE[active.role],
            )}
          >
            {active.role}
          </span>
          <span className="ml-auto font-mono text-[10px] text-foreground/40">
            {active.schema_ref}
          </span>
        </div>
        <p className="mt-2 text-[13px] leading-6 text-[var(--ink-soft)]">{active.what}</p>
        <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
          {active.output.map((o) => (
            <div
              key={o.k}
              className="flex items-baseline gap-2 border-b border-[var(--grid-line)] pb-1 font-mono text-[11px]"
            >
              <span className="w-36 shrink-0 text-foreground/50">{o.k}</span>
              <span className="min-w-0 break-words text-foreground/90">{o.v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
