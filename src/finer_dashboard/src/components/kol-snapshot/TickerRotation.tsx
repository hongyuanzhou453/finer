"use client";

/**
 * 标的兑现榜 — per-ticker stance + realized performance, ranked by avg return.
 * The KOL analogue of the reference report's sector-rotation / net-inflow board.
 */
import React from "react";
import type { TickerRotationRow } from "@/lib/fixtures/kol-snapshot";
import { DirectionTag, ReturnChip } from "./primitives";

/** Diverging bar centered at zero: positive grows red-right, negative green-left. */
function RotationBar({ value, maxAbs }: { value: number; maxAbs: number }) {
  const pct = maxAbs > 0 ? Math.min(1, Math.abs(value) / maxAbs) : 0;
  const half = pct * 50;
  const positive = value >= 0;
  return (
    <div className="relative h-2 w-16 rounded-[2px] bg-[var(--surface-muted)]">
      <span
        aria-hidden
        className="absolute top-0 h-full w-px bg-[var(--grid-line)]"
        style={{ left: "50%" }}
      />
      <span
        aria-hidden
        className="absolute top-0 h-full rounded-[2px]"
        style={{
          left: positive ? "50%" : `${50 - half}%`,
          width: `${half}%`,
          backgroundColor: positive ? "var(--chart-up)" : "var(--chart-down)",
        }}
      />
    </div>
  );
}

export function TickerRotation({ rows }: { rows: TickerRotationRow[] }) {
  const maxAbs = Math.max(
    0.01,
    ...rows.map((r) => Math.abs(r.avgReturn ?? 0)),
  );

  return (
    <table className="top-rule-table">
      <thead>
        <tr>
          <th>标的</th>
          <th>最新立场</th>
          <th className="text-right">观点数</th>
          <th className="text-right">平均兑现</th>
          <th aria-label="兑现强度" />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.ticker}>
            <td>
              <span className="font-medium text-[var(--foreground)]">
                {r.companyName}
              </span>{" "}
              <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                {r.ticker}·{r.market}
              </span>
            </td>
            <td>
              <DirectionTag direction={r.latestDirection} size="xs" />
            </td>
            <td className="tabular-nums">{r.count}</td>
            <td className="tabular-nums">
              {r.avgReturn === null ? (
                <span className="text-xs text-[var(--ink-soft)]">待回测</span>
              ) : (
                <ReturnChip value={r.avgReturn} />
              )}
            </td>
            <td>
              {r.avgReturn === null ? null : (
                <RotationBar value={r.avgReturn} maxAbs={maxAbs} />
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
