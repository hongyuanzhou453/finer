"use client";

/**
 * 立场潮汐 — cumulative net-long stance over time (multi-month).
 * The KOL analogue of the reference report's "20 日净流向水位" water-level line.
 */
import React from "react";
import type { SnapshotViewpoint } from "@/lib/fixtures/kol-snapshot";
import { useEchart } from "./useEchart";

const INK_SOFT = "rgba(24,21,18,0.55)";
const GRID = "rgba(54,38,24,0.12)";
const RED = "#e11b22";

function monthlyCumulativeNet(viewpoints: SnapshotViewpoint[]) {
  const buckets = new Map<string, number>();
  for (const v of viewpoints) {
    const month = v.timestamp.slice(0, 7); // YYYY-MM
    const delta =
      v.direction === "bullish"
        ? 1
        : v.direction === "bearish" || v.direction === "risk_warning"
          ? -1
          : 0;
    buckets.set(month, (buckets.get(month) ?? 0) + delta);
  }
  const months = Array.from(buckets.keys()).sort();
  let acc = 0;
  return months.map((m) => {
    acc += buckets.get(m) ?? 0;
    return { month: m.slice(5), value: acc };
  });
}

export function StanceTide({ viewpoints }: { viewpoints: SnapshotViewpoint[] }) {
  const ref = useEchart(() => {
    const series = monthlyCumulativeNet(viewpoints);
    return {
      animationDuration: 600,
      grid: { left: 26, right: 12, top: 14, bottom: 22 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,252,247,0.98)",
        borderColor: GRID,
        borderWidth: 1,
        textStyle: { color: "#181512", fontSize: 12 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (ps: any) =>
          `${ps[0].axisValue} 月<br/>累计净多 <b>${ps[0].data > 0 ? "+" : ""}${ps[0].data}</b>`,
      },
      xAxis: {
        type: "category",
        data: series.map((d) => d.month),
        boundaryGap: false,
        axisLabel: { color: INK_SOFT, fontSize: 10 },
        axisLine: { lineStyle: { color: GRID } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: INK_SOFT, fontSize: 10 },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      series: [
        {
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: series.map((d) => d.value),
          lineStyle: { color: RED, width: 2 },
          itemStyle: { color: RED },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(225,27,34,0.18)" },
                { offset: 1, color: "rgba(225,27,34,0.01)" },
              ],
            },
          },
        },
      ],
    };
  }, [viewpoints]);

  return <div ref={ref} className="h-[120px] w-full" />;
}
