/**
 * L3 跨 KOL 立场时间线 — 同一标的，多个 KOL 在何时怎么看、演变与分歧。
 * 竖向 editorial 时间线（左 rail + 方向着色圆点），每条卡突出「是哪个 KOL」。
 * timeline 已按时间倒序，逐条渲染即可。纯 props，无 "use client"。
 */
import React from "react";
import Link from "next/link";
import type { TickerViewpoint } from "@/lib/fixtures/kol-ticker";
import {
  ConfidenceMeter,
  DIRECTION_META,
  DirectionTag,
  ReturnChip,
  fmtDate,
} from "@/components/kol-snapshot/primitives";

const VALIDATION_LABEL: Record<string, string> = {
  verified: "已验证",
  pending: "待验证",
  failed: "未通过",
  under_review: "复核中",
};

function StanceRow({ v }: { v: TickerViewpoint }) {
  const accent = DIRECTION_META[v.direction].color;
  return (
    <li className="relative pl-5">
      {/* timeline rail dot — direction-colored */}
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
            {v.kolName}
          </span>
          <span
            className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium tabular-nums"
            style={{
              color: "var(--accent-gold)",
              backgroundColor: "color-mix(in srgb, var(--accent-gold) 12%, transparent)",
              border: "1px solid color-mix(in srgb, var(--accent-gold) 32%, transparent)",
            }}
          >
            信誉 {v.credibility}
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

export function TickerStanceTimeline({ timeline }: { timeline: TickerViewpoint[] }) {
  return (
    <ol className="relative space-y-3 before:absolute before:left-0 before:top-1 before:h-full before:w-px before:bg-[var(--grid-line)]">
      {timeline.map((v) => (
        <StanceRow key={v.id} v={v} />
      ))}
    </ol>
  );
}
