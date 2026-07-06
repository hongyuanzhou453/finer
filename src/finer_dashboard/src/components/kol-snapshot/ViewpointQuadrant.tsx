"use client";

/**
 * 观点象限 — confidence (x) × actual backtest return (y), colored by direction.
 * Visualizes KOL calibration: are high-confidence calls actually paying off?
 *   右上 高信心·兑现 / 左上 低信心·侥幸 / 右下 高信心·打脸 / 左下 低信心·亏损
 */
import React from "react";
import type { SnapshotViewpoint } from "@/lib/fixtures/kol-snapshot";
import { DIRECTION_META, fmtConfidence, fmtPct } from "./primitives";
import { useEchart } from "./useEchart";

const INK = "#181512";
const INK_SOFT = "rgba(24,21,18,0.55)";
const GRID = "rgba(54,38,24,0.12)";

// Concrete hex per direction — canvas can't resolve CSS var()/color-mix().
const DIR_HEX: Record<string, string> = {
  bullish: "#e11b22",
  bearish: "#10b981",
  neutral: "#8a8278",
  watchlist: "#9b7b45",
  risk_warning: "#1f6a67",
};

export function ViewpointQuadrant({
  points,
  avgConfidence,
}: {
  points: SnapshotViewpoint[];
  avgConfidence: number;
}) {
  const ref = useEchart(() => {
    const data = points.map((v) => {
      const meta = DIRECTION_META[v.direction];
      const hex = DIR_HEX[v.direction] ?? "#8a8278";
      const hold = v.holdingDays ?? 0;
      return {
        value: [v.confidence, (v.returnPct ?? 0) * 100],
        name: v.companyName,
        symbolSize: Math.max(14, Math.min(34, 12 + Math.sqrt(hold) * 3)),
        itemStyle: {
          color: hex,
          opacity: 0.82,
          borderColor: hex,
          borderWidth: 1,
        },
        _dir: meta.label,
        _conf: v.confidence,
        _ret: v.returnPct ?? 0,
        _hold: hold,
      };
    });

    const corner = (
      text: string,
      x: "left" | "right",
      y: "top" | "bottom",
    ) => ({
      type: "text" as const,
      [x]: x === "left" ? 52 : 16,
      [y]: y === "top" ? 12 : 40,
      style: {
        text,
        fill: INK_SOFT,
        fontSize: 11,
        fontWeight: 500 as const,
      },
      z: 0,
    });

    return {
      animationDuration: 600,
      grid: { left: 48, right: 18, top: 28, bottom: 44 },
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(255,252,247,0.98)",
        borderColor: GRID,
        borderWidth: 1,
        textStyle: { color: INK, fontSize: 12 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (p: any) =>
          `<b>${p.name}</b> · ${p.data._dir}<br/>置信度 ${fmtConfidence(
            p.data._conf,
          )} ｜ 收益 ${fmtPct(p.data._ret / 100)}<br/>持仓 ${p.data._hold} 天`,
      },
      xAxis: {
        type: "value",
        name: "置信度 →",
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: INK_SOFT, fontSize: 11 },
        min: 0.5,
        max: 0.9,
        interval: 0.1,
        axisLabel: {
          color: INK_SOFT,
          fontSize: 10,
          formatter: (v: number) => `${Math.round(v * 100)}%`,
        },
        axisLine: { lineStyle: { color: GRID } },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      yAxis: {
        type: "value",
        name: "实际收益",
        nameTextStyle: { color: INK_SOFT, fontSize: 11, align: "left" },
        axisLabel: {
          color: INK_SOFT,
          fontSize: 10,
          formatter: (v: number) => `${v > 0 ? "+" : ""}${v}%`,
        },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: GRID, type: "dashed" } },
      },
      graphic: [
        corner("高信心·兑现", "right", "top"),
        corner("低信心·侥幸", "left", "top"),
        corner("高信心·打脸", "right", "bottom"),
        corner("低信心·亏损", "left", "bottom"),
      ],
      series: [
        {
          type: "scatter",
          data,
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: "rgba(24,21,18,0.35)", type: "solid", width: 1 },
            data: [{ yAxis: 0 }, { xAxis: avgConfidence }],
          },
        },
      ],
    };
  }, [points, avgConfidence]);

  return <div ref={ref} className="h-[300px] w-full" />;
}
