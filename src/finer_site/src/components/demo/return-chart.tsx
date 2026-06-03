"use client";

import { useEffect, useState } from "react";
import type { SeriesPoint } from "@/demo/types";

/**
 * Lightweight hand-drawn SVG cumulative-return chart with a draw-in animation.
 * No charting library — pure SVG geometry. Replays when `seriesKey` changes.
 * China convention: gains in red (var(--chart-up)).
 */
export function ReturnChart({
  series,
  seriesKey,
}: {
  series: SeriesPoint[];
  seriesKey: string;
}) {
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    setDrawn(false);
    const t = setTimeout(() => setDrawn(true), 50);
    return () => clearTimeout(t);
  }, [seriesKey]);

  const W = 720;
  const H = 260;
  const padL = 42;
  const padR = 16;
  const padT = 18;
  const padB = 26;
  const n = series.length;

  const vals = series.flatMap((p) => [p.value, p.benchmark]);
  const rawMax = Math.max(...vals);
  const rawMin = Math.min(...vals, 0);
  const maxV = Math.ceil(rawMax / 5) * 5 || 5;
  const minV = Math.floor(rawMin / 5) * 5;

  const xFor = (i: number) =>
    padL + (n <= 1 ? 0 : (i / (n - 1)) * (W - padL - padR));
  const yFor = (v: number) =>
    padT + (1 - (v - minV) / (maxV - minV || 1)) * (H - padT - padB);

  const line = series
    .map((p, i) => `${i ? "L" : "M"}${xFor(i).toFixed(1)},${yFor(p.value).toFixed(1)}`)
    .join(" ");
  const bench = series
    .map((p, i) => `${i ? "L" : "M"}${xFor(i).toFixed(1)},${yFor(p.benchmark).toFixed(1)}`)
    .join(" ");
  const area = `${line} L${xFor(n - 1).toFixed(1)},${yFor(0).toFixed(1)} L${xFor(0).toFixed(1)},${yFor(0).toFixed(1)} Z`;

  const ticks = 4;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => minV + ((maxV - minV) / ticks) * i);
  const last = series[n - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="累计收益曲线（演示数据）">
      <defs>
        <linearGradient id="rc-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--chart-up)" stopOpacity="0.16" />
          <stop offset="100%" stopColor="var(--chart-up)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* y grid + labels */}
      {yTicks.map((t) => (
        <g key={t}>
          <line
            x1={padL}
            y1={yFor(t)}
            x2={W - padR}
            y2={yFor(t)}
            stroke="var(--grid-line)"
            strokeWidth={1}
          />
          <text
            x={padL - 7}
            y={yFor(t) + 3}
            textAnchor="end"
            fill="var(--ink-soft)"
            fontSize={10}
            fontFamily="var(--font-ui-mono)"
          >
            {t}%
          </text>
        </g>
      ))}

      {/* x labels (every other point) */}
      {series.map((p, i) =>
        i % 2 === 0 ? (
          <text
            key={p.date}
            x={xFor(i)}
            y={H - 8}
            textAnchor="middle"
            fill="var(--ink-soft)"
            fontSize={10}
            fontFamily="var(--font-ui-mono)"
          >
            {p.date}
          </text>
        ) : null,
      )}

      {/* area under return line */}
      <path
        d={area}
        fill="url(#rc-fill)"
        opacity={drawn ? 1 : 0}
        style={{ transition: "opacity 0.8s ease 0.3s" }}
      />

      {/* benchmark (peer / dashed) */}
      <path
        d={bench}
        fill="none"
        stroke="var(--chart-peer)"
        strokeWidth={1.4}
        strokeDasharray="4 3"
        opacity={drawn ? 0.9 : 0}
        style={{ transition: "opacity 0.6s ease 0.2s" }}
      />

      {/* cumulative return line with draw-in */}
      <path
        d={line}
        fill="none"
        stroke="var(--chart-up)"
        strokeWidth={2.2}
        strokeLinejoin="round"
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={100}
        strokeDashoffset={drawn ? 0 : 100}
        style={{ transition: "stroke-dashoffset 1.1s ease" }}
      />

      {/* last point marker */}
      <circle
        cx={xFor(n - 1)}
        cy={yFor(last.value)}
        r={3.6}
        fill="var(--chart-up)"
        opacity={drawn ? 1 : 0}
        style={{ transition: "opacity 0.3s ease 1s" }}
      />
    </svg>
  );
}
