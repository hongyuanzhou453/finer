"use client";

/**
 * 04 观点时间线 — the drill-down. One card per viewpoint (TradeAction),
 * time-descending, with the KOL's own words as the evidence quote.
 */
import React from "react";
import Link from "next/link";
import type { SnapshotViewpoint } from "@/lib/fixtures/kol-snapshot";
import {
  ConfidenceMeter,
  DIRECTION_META,
  DirectionTag,
  ReturnChip,
  fmtDate,
} from "./primitives";

const VALIDATION_LABEL: Record<string, string> = {
  verified: "已验证",
  pending: "待验证",
  failed: "未通过",
  under_review: "复核中",
};

function ViewpointRow({ v }: { v: SnapshotViewpoint }) {
  const accent = DIRECTION_META[v.direction].color;
  return (
    <li className="relative pl-5">
      {/* timeline rail dot */}
      <span
        aria-hidden
        className="absolute left-0 top-1.5 h-2 w-2 -translate-x-1/2 rounded-full"
        style={{ backgroundColor: accent, boxShadow: "0 0 0 3px var(--background)" }}
      />
      <Link
        href={`/demo/audit/${v.id}`}
        className="block editorial-card rounded-sm p-3"
        style={{ borderTopColor: accent }}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="tabular-nums text-xs text-[var(--ink-soft)]">
            {fmtDate(v.timestamp)}
          </span>
          <DirectionTag direction={v.direction} />
          <span className="text-sm font-semibold text-[var(--foreground)]">
            {v.companyName}
          </span>
          <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
            {v.ticker}·{v.market}
          </span>
          <span className="ml-auto flex items-center gap-3">
            <span className="text-[10px] uppercase tracking-wider text-[var(--ink-soft)]">
              {VALIDATION_LABEL[v.validationStatus] ?? v.validationStatus}
            </span>
            <ReturnChip value={v.returnPct} />
          </span>
        </div>

        <p className="mt-1.5 text-[13px] leading-snug text-[var(--foreground)]">
          {v.summary}
        </p>

        <blockquote
          className="mt-2 border-l-2 pl-2.5 text-[12px] leading-relaxed text-[var(--ink-soft)]"
          style={{ borderColor: `color-mix(in srgb, ${accent} 40%, transparent)` }}
        >
          “{v.evidenceText}”
        </blockquote>

        <div className="mt-2 flex items-center justify-between">
          <ConfidenceMeter value={v.confidence} />
          <span className="flex items-center gap-3">
            {v.holdingDays && v.holdingDays > 0 ? (
              <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                持仓 {v.holdingDays} 天
              </span>
            ) : null}
            <span className="text-[11px] text-[var(--accent-teal)]">证据链 →</span>
          </span>
        </div>
      </Link>
    </li>
  );
}

export function ViewpointTimeline({
  viewpoints,
}: {
  viewpoints: SnapshotViewpoint[];
}) {
  return (
    <ol className="relative space-y-3 before:absolute before:left-0 before:top-1 before:h-full before:w-px before:bg-[var(--grid-line)]">
      {viewpoints.map((v) => (
        <ViewpointRow key={v.id} v={v} />
      ))}
    </ol>
  );
}
