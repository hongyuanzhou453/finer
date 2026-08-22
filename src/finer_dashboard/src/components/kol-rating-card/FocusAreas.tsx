"use client";

import React from "react";
import { cn } from "@/lib/utils";
import type { FocusArea } from "./KOLRatingCard";

export interface FocusAreasProps {
  areas: FocusArea[];
  compact?: boolean;
  className?: string;
}

// Color based on accuracy
function getAccuracyColor(accuracy: number) {
  if (accuracy >= 70) return { bg: "bg-emerald-500", text: "text-emerald-600", light: "bg-emerald-100" };
  if (accuracy >= 55) return { bg: "bg-yellow-500", text: "text-yellow-600", light: "bg-yellow-100" };
  return { bg: "bg-red-500", text: "text-red-600", light: "bg-red-100" };
}

// Heatmap cell
function HeatmapCell({ area, maxCount }: { area: FocusArea; maxCount: number }) {
  const color = getAccuracyColor(area.accuracy);
  const intensity = area.count / maxCount;

  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center p-3 rounded-lg border transition-all cursor-pointer group",
        "hover:scale-105 hover:shadow-md",
        color.light,
        "border-transparent hover:border-current"
      )}
      style={{
        opacity: 0.3 + intensity * 0.7,
      }}
    >
      {/* Area name */}
      <span className="text-xs font-bold text-foreground/80 text-center leading-tight">
        {area.name}
      </span>

      {/* Stats on hover */}
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/95 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity p-2">
        <span className="text-sm font-bold text-foreground">{area.name}</span>
        <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
          <span className="text-foreground/50">观点数:</span>
          <span className="font-bold text-foreground tabular-nums text-right">{area.count}</span>
          <span className="text-foreground/50">准确率:</span>
          <span className={cn("font-bold tabular-nums text-right", color.text)}>
            {area.accuracy.toFixed(0)}%
          </span>
          <span className="text-foreground/50">平均收益:</span>
          <span className={cn(
            "font-bold tabular-nums text-right",
            area.avgReturn >= 0 ? "text-emerald-600" : "text-red-600"
          )}>
            {area.avgReturn >= 0 ? "+" : ""}{area.avgReturn.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}

// Horizontal bar
function AreaBar({ area, maxCount }: { area: FocusArea; maxCount: number }) {
  const color = getAccuracyColor(area.accuracy);
  const width = (area.count / maxCount) * 100;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium text-foreground/70 w-20 text-right truncate">
        {area.name}
      </span>
      <div className="flex-1 h-6 bg-stone-100 rounded overflow-hidden relative">
        <div
          className={cn("h-full transition-all duration-300", color.bg)}
          style={{ width: `${width}%` }}
        />
        {/* Stats overlay */}
        <div className="absolute inset-0 flex items-center justify-between px-2">
          <span className="text-[10px] font-bold text-white/90 tabular-nums">
            {area.count}
          </span>
          <span className={cn("text-[10px] font-bold tabular-nums", color.text)}>
            {area.accuracy.toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
}

export function FocusAreas({
  areas,
  compact = false,
  className,
}: FocusAreasProps) {
  const maxCount = Math.max(...areas.map(a => a.count));
  const totalOpinions = areas.reduce((sum, a) => sum + a.count, 0);

  // Compact: simple tag list
  if (compact) {
    return (
      <div className={cn("flex flex-wrap gap-2", className)}>
        {areas.slice(0, 5).map((area, index) => {
          const color = getAccuracyColor(area.accuracy);
          return (
            <div
              key={index}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold border",
                color.light,
                color.text,
                "border-transparent"
              )}
            >
              <span>{area.name}</span>
              <span className="opacity-60">({area.count})</span>
            </div>
          );
        })}
      </div>
    );
  }

  // Full view: grid + bars
  return (
    <div className={cn("space-y-5", className)}>
      {/* Heatmap grid */}
      <div className="grid grid-cols-5 gap-2">
        {areas.map((area, index) => (
          <HeatmapCell key={index} area={area} maxCount={maxCount} />
        ))}
      </div>

      {/* Summary bar chart */}
      <div className="space-y-2">
        <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/40 mb-3">
          观点分布 ({totalOpinions} 条)
        </div>
        {areas.map((area, index) => (
          <AreaBar key={index} area={area} maxCount={maxCount} />
        ))}
      </div>
    </div>
  );
}

// Radar chart variant (optional, for visual variety)
export function FocusRadar({
  areas,
  className,
}: {
  areas: FocusArea[];
  className?: string;
}) {
  const centerX = 100;
  const centerY = 100;
  const radius = 80;
  const numPoints = areas.length;

  // Calculate polygon points
  const points = areas.map((area, i) => {
    const angle = (2 * Math.PI * i) / numPoints - Math.PI / 2;
    const r = (area.accuracy / 100) * radius;
    return {
      x: centerX + r * Math.cos(angle),
      y: centerY + r * Math.sin(angle),
    };
  });

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ") + " Z";

  return (
    <div className={cn("relative", className)}>
      <svg width="200" height="200" viewBox="0 0 200 200">
        {/* Background circles */}
        {[0.25, 0.5, 0.75, 1].map((scale) => (
          <circle
            key={scale}
            cx={centerX}
            cy={centerY}
            r={radius * scale}
            fill="none"
            stroke="rgba(95,67,40,0.12)"
            strokeWidth={1}
          />
        ))}

        {/* Axis lines */}
        {areas.map((_, i) => {
          const angle = (2 * Math.PI * i) / numPoints - Math.PI / 2;
          return (
            <line
              key={i}
              x1={centerX}
              y1={centerY}
              x2={centerX + radius * Math.cos(angle)}
              y2={centerY + radius * Math.sin(angle)}
              stroke="rgba(95,67,40,0.08)"
              strokeWidth={1}
            />
          );
        })}

        {/* Data polygon */}
        <path
          d={pathD}
          fill="color-mix(in srgb, var(--morningstar-red) 15%, transparent)"
          stroke="color-mix(in srgb, var(--morningstar-red) 60%, transparent)"
          strokeWidth={2}
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={3} fill="var(--morningstar-red)" />
        ))}
      </svg>

      {/* Labels */}
      {areas.map((area, i) => {
        const angle = (2 * Math.PI * i) / numPoints - Math.PI / 2;
        const labelRadius = radius + 20;
        const x = centerX + labelRadius * Math.cos(angle);
        const y = centerY + labelRadius * Math.sin(angle);
        return (
          <div
            key={i}
            className="absolute text-[9px] font-medium text-foreground/60"
            style={{
              left: x,
              top: y,
              transform: "translate(-50%, -50%)",
            }}
          >
            {area.name}
          </div>
        );
      })}
    </div>
  );
}

export default FocusAreas;