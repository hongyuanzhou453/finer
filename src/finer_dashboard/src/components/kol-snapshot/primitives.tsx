/**
 * Shared presentational atoms for the KOL viewpoint-tide snapshot.
 * Institutional-finance discipline: hard rules, mono tabular numbers,
 * red = up/bullish, green = down/bearish (China market convention).
 */
import React from "react";
import type { ViewpointDirection } from "@/lib/fixtures/kol-snapshot";

export interface DirectionMeta {
  label: string; // short Chinese label
  glyph: string; // single-char tag glyph
  color: string; // semantic color token value
}

export const DIRECTION_META: Record<ViewpointDirection, DirectionMeta> = {
  bullish: { label: "看多", glyph: "多", color: "var(--chart-up)" },
  bearish: { label: "看空", glyph: "空", color: "var(--chart-down)" },
  neutral: { label: "中性", glyph: "中", color: "#8a8278" },
  watchlist: { label: "观察", glyph: "察", color: "var(--accent-gold)" },
  risk_warning: { label: "风险", glyph: "险", color: "var(--accent-teal)" },
};

// ---- formatters -------------------------------------------------------------

export function fmtPct(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

export function fmtConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function fmtDate(iso: string): string {
  // YYYY-MM-DD from an ISO string without pulling in a date lib
  return iso.slice(0, 10);
}

export function fmtMonthDay(iso: string): string {
  return iso.slice(5, 10);
}

// ---- section header (editorial "01 / TITLE" rule) ---------------------------

export function SectionHeader({
  index,
  title,
  en,
  note,
}: {
  index: string;
  title: string;
  en: string;
  note?: React.ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-4 border-b border-[var(--foreground)] pb-2">
      <div className="flex items-baseline gap-3">
        {index ? (
          <span className="tabular-nums text-sm font-semibold text-[var(--accent-gold)]">
            {index}
          </span>
        ) : null}
        <h2 className="text-lg leading-none text-[var(--foreground)]">{title}</h2>
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--ink-soft)]">
          {en}
        </span>
      </div>
      {note ? (
        <div className="text-[11px] leading-tight text-[var(--ink-soft)]">{note}</div>
      ) : null}
    </div>
  );
}

// ---- direction tag ----------------------------------------------------------

export function DirectionTag({
  direction,
  size = "sm",
}: {
  direction: ViewpointDirection;
  size?: "sm" | "xs";
}) {
  const meta = DIRECTION_META[direction];
  const pad = size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm font-medium ${pad}`}
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

// ---- return chip (red up / green down) --------------------------------------

export function ReturnChip({
  value,
  muted,
}: {
  value: number | null;
  muted?: string;
}) {
  if (value === null) {
    return (
      <span className="tabular-nums text-xs text-[var(--ink-soft)]">
        {muted ?? "待回测"}
      </span>
    );
  }
  if (value === 0) {
    return (
      <span className="tabular-nums text-xs text-[var(--ink-soft)]">未触发</span>
    );
  }
  const color = value > 0 ? "var(--chart-up)" : "var(--chart-down)";
  return (
    <span className="tabular-nums text-xs font-semibold" style={{ color }}>
      {fmtPct(value)}
    </span>
  );
}

// ---- direction legend -------------------------------------------------------

export function DirectionLegend({
  directions,
  className = "",
}: {
  directions: ViewpointDirection[];
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 ${className}`}>
      {directions.map((d) => (
        <span key={d} className="flex items-center gap-1 text-[11px]">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: DIRECTION_META[d].color }}
          />
          <span className="text-[var(--ink-soft)]">{DIRECTION_META[d].label}</span>
        </span>
      ))}
    </div>
  );
}

// ---- confidence meter -------------------------------------------------------

export function ConfidenceMeter({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-12 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.round(value * 100)}%`,
            backgroundColor: "var(--accent-gold)",
          }}
        />
      </div>
      <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
        {fmtConfidence(value)}
      </span>
    </div>
  );
}
