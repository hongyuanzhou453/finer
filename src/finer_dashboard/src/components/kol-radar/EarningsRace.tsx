"use client";

/**
 * 收益榜 · TOP EARNERS — 最近一周 / 最近一月已结算跟单收益排名，带排名重排动画。
 *
 * One component, isomorphic across /demo/kol-radar (fixture) and /radar (live):
 * takes the whole KOLRadarData and runs deriveEarningsBoard internally, so tab
 * switching re-derives client-side with zero backend involvement. 口径 (frozen)
 * lives in deriveEarningsBoard's docstring: settled viewpoints bucketed by
 * *settle time* (timestamp + holdingDays), equal-weight Σ returnPct.
 *
 * Animation discipline (financial product — restrained, no bounce): rows are
 * framer-motion `layout` items keyed by kolId; tab switches spring-reorder
 * (stiffness 300 / damping 30), enter/exit fade + small vertical shift,
 * mount staggers ~0.05s per rank.
 */

import React, { useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  deriveEarningsBoard,
  deriveLatestSettleDate,
  type KOLRadarData,
} from "@/lib/fixtures/kol-radar";
import { fmtPct } from "@/components/kol-snapshot/primitives";
import { DEMO_RADAR_LINKS, kolHref, type RadarLinks } from "./links";

const SPRING = { type: "spring", stiffness: 300, damping: 30 } as const;

const WINDOWS: { days: 7 | 30; label: string }[] = [
  { days: 7, label: "近一周" },
  { days: 30, label: "近一月" },
];

function returnColor(value: number): string {
  return value >= 0 ? "var(--chart-up)" : "var(--chart-down)";
}

export function EarningsRace({
  data,
  links = DEMO_RADAR_LINKS,
}: {
  data: KOLRadarData;
  links?: RadarLinks;
}) {
  const [windowDays, setWindowDays] = useState<7 | 30>(7);
  const rows = deriveEarningsBoard(data, windowDays);
  const maxAbs = rows.reduce((m, r) => Math.max(m, Math.abs(r.cumReturn)), 0);

  return (
    <div>
      {/* ---- window tabs + meta ---- */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="结算窗口"
          className="flex overflow-hidden rounded-sm border border-[var(--table-border)]"
        >
          {WINDOWS.map((w) => {
            const active = windowDays === w.days;
            return (
              <button
                key={w.days}
                role="tab"
                aria-selected={active}
                onClick={() => setWindowDays(w.days)}
                className={`px-3 py-1.5 text-[11px] leading-none transition-colors ${
                  active
                    ? "bg-[var(--foreground)] font-medium text-[var(--background)]"
                    : "text-[var(--ink-soft)] hover:text-[var(--foreground)]"
                }`}
              >
                {w.label}
              </button>
            );
          })}
        </div>
        <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
          {rows.length} 位 KOL 上榜 · 窗口截至 {data.generatedAt.slice(0, 10)}
        </span>
      </div>

      {/* ---- ranked rows ---- */}
      <div className="finer-scrollbar -mx-1 mt-3 overflow-x-auto px-1">
        <div className="min-w-[560px] border-t border-[var(--foreground)]">
          {rows.length === 0 ? (
            <div className="py-8 text-center text-xs text-[var(--ink-soft)]">
              该窗口内暂无已结算观点
              {(() => {
                const latest = deriveLatestSettleDate(data);
                return latest ? (
                  <span className="tabular-nums"> · 最近一笔结算 {latest}</span>
                ) : null;
              })()}
            </div>
          ) : (
            <AnimatePresence initial={false} mode="popLayout">
              {rows.map((r, i) => {
                const barPct = maxAbs === 0 ? 0 : (Math.abs(r.cumReturn) / maxAbs) * 100;
                const color = returnColor(r.cumReturn);
                return (
                  <motion.div
                    key={r.kolId}
                    layout
                    layoutId={r.kolId}
                    initial={{ opacity: 0, y: 14 }}
                    animate={{
                      opacity: 1,
                      y: 0,
                      transition: { ...SPRING, delay: i * 0.05 },
                    }}
                    exit={{ opacity: 0, y: -10, transition: { duration: 0.16 } }}
                    transition={SPRING}
                    className="grid grid-cols-[34px_minmax(170px,1fr)_minmax(200px,1.5fr)_170px] items-center gap-3 border-b border-[var(--grid-line)] py-2.5"
                  >
                    {/* rank */}
                    <span
                      className="tabular-nums text-sm font-semibold"
                      style={{ color: i === 0 ? "var(--accent-gold)" : "var(--ink-soft)" }}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>

                    {/* KOL identity */}
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
                      {r.lowSample ? (
                        <span
                          className="rounded-sm px-1 py-0.5 text-[10px] leading-none text-[var(--accent-gold)]"
                          style={{
                            border:
                              "1px solid color-mix(in srgb, var(--accent-gold) 45%, transparent)",
                          }}
                          title="窗口内结算笔数少于 3，收益统计意义有限"
                        >
                          样本不足
                        </span>
                      ) : null}
                    </div>

                    {/* return bar + cumulative pct */}
                    <div className="flex items-center gap-2.5">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                        <motion.div
                          className="h-full rounded-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${barPct}%` }}
                          transition={SPRING}
                          style={{ backgroundColor: color }}
                        />
                      </div>
                      <span
                        className="w-[76px] text-right tabular-nums text-sm font-semibold"
                        style={{ color }}
                      >
                        {fmtPct(r.cumReturn, 2)}
                      </span>
                    </div>

                    {/* sample count + best call */}
                    <div className="whitespace-nowrap text-right">
                      <div className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                        n={r.sampleCount}
                      </div>
                      {r.bestCall ? (
                        <div className="text-[11px]">
                          <span className="text-[var(--ink-soft)]">最佳: </span>
                          <span className="font-medium text-[var(--foreground)]">
                            {r.bestCall.companyName}
                          </span>{" "}
                          <span
                            className="tabular-nums font-semibold"
                            style={{ color: returnColor(r.bestCall.returnPct) }}
                          >
                            {fmtPct(r.bestCall.returnPct)}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          )}
        </div>
      </div>

      <p className="mt-2 text-[11px] leading-tight text-[var(--ink-soft)]">
        按结算时点归入窗口 · 收益为方向调整后的完全跟单口径 · 无结算样本的 KOL 不上榜 · 非投资建议
      </p>
    </div>
  );
}
