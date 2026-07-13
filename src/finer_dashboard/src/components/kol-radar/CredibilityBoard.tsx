/**
 * 01 可信度榜 — the product spine. KOL leaderboard ranked by derived 信誉分.
 * Compact 6-column institutional table: 趋势 merged into 信誉分, 擅长 into the
 * KOL cell, everything `whitespace-nowrap` so Chinese never wraps one-char-per-line.
 * (Panel chrome is supplied by the parent section, so no inner editorial-panel.)
 */
import React from "react";
import Link from "next/link";
import type { CredibilityRow } from "@/lib/fixtures/kol-radar";
import { DirectionTag, fmtConfidence } from "@/components/kol-snapshot/primitives";
import { DEMO_RADAR_LINKS, kolHref, type RadarLinks } from "./links";

const TREND_META: Record<CredibilityRow["trend"], { glyph: string; color: string; label: string }> = {
  up: { glyph: "↑", color: "var(--chart-up)", label: "上升" },
  down: { glyph: "↓", color: "var(--chart-down)", label: "下降" },
  flat: { glyph: "→", color: "#8a8278", label: "持平" },
};

function stanceColor(label: CredibilityRow["stanceLabel"]): string {
  return label === "偏多"
    ? "var(--chart-up)"
    : label === "偏空"
      ? "var(--chart-down)"
      : "#8a8278";
}

export function CredibilityBoard({
  rows,
  links = DEMO_RADAR_LINKS,
}: {
  rows: CredibilityRow[];
  links?: RadarLinks;
}) {
  return (
    <div className="finer-scrollbar -mx-1 overflow-x-auto px-1">
      <table className="top-rule-table min-w-[600px]">
        <colgroup>
        <col style={{ width: "34px" }} />
        <col />
        <col style={{ width: "104px" }} />
        <col style={{ width: "82px" }} />
        <col style={{ width: "80px" }} />
        <col style={{ width: "158px" }} />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">KOL</th>
          <th scope="col" className="text-right">信誉分</th>
          <th scope="col" className="text-right">命中率</th>
          <th scope="col">当前立场</th>
          <th scope="col">当前主推</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const trend = TREND_META[r.trend];
          return (
            <tr key={r.kolId}>
              <td className="tabular-nums align-top text-[var(--ink-soft)]">
                {String(i + 1).padStart(2, "0")}
              </td>

              <td className="align-top">
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <Link
                    href={kolHref(links, r.kolId)}
                    className="font-semibold text-[var(--foreground)] hover:text-[var(--morningstar-red)] hover:underline"
                  >
                    {r.name}
                  </Link>
                  <span className="rounded-sm bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--ink-soft)]">
                    {r.style}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.specialties.map((s) => (
                    <span
                      key={s}
                      className="whitespace-nowrap rounded-sm border border-[var(--grid-line)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--ink-soft)]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </td>

              <td className="align-top">
                <div className="flex items-baseline justify-end gap-1.5">
                  <span className="tabular-nums text-xl font-semibold leading-none text-[var(--foreground)]">
                    {r.credibility}
                  </span>
                  <span
                    className="text-sm font-semibold leading-none"
                    style={{ color: trend.color }}
                    title={`趋势 ${trend.label}`}
                  >
                    {trend.glyph}
                  </span>
                </div>
                <div className="ml-auto mt-1.5 h-1 w-16 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${r.credibility}%`, backgroundColor: "var(--accent-gold)" }}
                  />
                </div>
              </td>

              <td className="align-top text-right">
                <div className="tabular-nums font-medium text-[var(--foreground)]">
                  {r.hitRate === null ? "—" : fmtConfidence(r.hitRate)}
                </div>
                <div className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                  {r.settledCount} 笔
                </div>
                {r.lowSample ? (
                  <div className="text-[10px] text-[var(--accent-gold)]" title="结算样本不足，信誉分已按样本量打折">
                    样本少
                  </div>
                ) : null}
              </td>

              <td className="whitespace-nowrap align-top">
                <span className="font-medium" style={{ color: stanceColor(r.stanceLabel) }}>
                  {r.stanceLabel}
                </span>{" "}
                <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                  {r.netStance >= 0 ? `+${r.netStance}` : r.netStance}
                </span>
              </td>

              <td className="align-top">
                {r.topCall ? (
                  <div className="flex items-center gap-1.5 whitespace-nowrap">
                    <span className="font-medium text-[var(--foreground)]">
                      {r.topCall.companyName}
                    </span>
                    <DirectionTag direction={r.topCall.direction} size="xs" />
                    <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                      {fmtConfidence(r.topCall.confidence)}
                    </span>
                  </div>
                ) : (
                  <span className="text-[var(--ink-soft)]">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
      </table>
    </div>
  );
}
