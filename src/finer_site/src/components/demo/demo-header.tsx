"use client";

import Link from "next/link";
import { ArrowLeft, ClipboardCheck, LineChart, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

export type DemoView = "research" | "annotation";

const TABS: { id: DemoView; label: string; icon: typeof LineChart }[] = [
  { id: "research", label: "研究 · 回测", icon: LineChart },
  { id: "annotation", label: "标注全流程", icon: ClipboardCheck },
];

/**
 * Shared demo top bar with a segmented view switch. Both the research/backtest
 * workbench and the annotation workbench render it, so switching is one control.
 */
export function DemoHeader({
  view,
  onViewChange,
}: {
  view: DemoView;
  onViewChange: (v: DemoView) => void;
}) {
  return (
    <header className="z-30 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--table-border)] bg-[rgba(243,239,231,0.92)] px-4 backdrop-blur">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-morningstar-red">
          <ShieldCheck className="h-4 w-4 text-white" strokeWidth={1.8} />
        </div>
        <span className="hidden truncate text-[14px] font-bold tracking-tight text-foreground sm:inline">
          Finer OS
          <span className="ml-2 font-mono text-[11px] font-normal text-foreground/45">/ demo</span>
        </span>
        <span className="ml-1 hidden rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--ink-soft)] lg:inline">
          演示数据 · Sample data only
        </span>
      </div>

      {/* segmented view switch */}
      <div className="flex shrink-0 items-center gap-0.5 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-0.5">
        {TABS.map((t) => {
          const Icon = t.icon;
          const on = t.id === view;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onViewChange(t.id)}
              aria-pressed={on}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 text-[12px] font-semibold transition-colors",
                on
                  ? "bg-morningstar-red text-white shadow-[var(--shadow-soft)]"
                  : "text-foreground/60 hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" strokeWidth={2} />
              <span className="hidden sm:inline">{t.label}</span>
            </button>
          );
        })}
      </div>

      <Link
        href="/"
        className="inline-flex shrink-0 items-center gap-1.5 text-[13px] font-semibold text-foreground/70 transition-colors hover:text-morningstar-red"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={2} />
        <span className="hidden sm:inline">返回首页</span>
      </Link>
    </header>
  );
}
