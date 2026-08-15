"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus, Clock, CheckCircle2, XCircle, ChevronRight } from "lucide-react";
import type { TimelineEvent } from "./KOLRatingCard";

export interface PerformanceTimelineProps {
  events: TimelineEvent[];
  compact?: boolean;
  maxItems?: number;
  className?: string;
}

/**
 * 方向/盈亏配色（中国惯例）：红=看涨/盈利，绿=看跌/亏损，走 --chart-up/-down。
 * 此前用的是西方口径（涨绿跌红），与全仓其余组件反色——密排并置会自相矛盾。
 */
function getDirectionStyle(direction: "bullish" | "bearish" | "neutral") {
  switch (direction) {
    case "bullish":
      return {
        icon: <TrendingUp className="w-3.5 h-3.5" />,
        bg: "bg-[color-mix(in_srgb,var(--chart-up)_8%,transparent)]",
        text: "text-[color:var(--chart-up)]",
        border: "border-[color-mix(in_srgb,var(--chart-up)_28%,transparent)]",
        label: "看涨",
      };
    case "bearish":
      return {
        icon: <TrendingDown className="w-3.5 h-3.5" />,
        bg: "bg-[color-mix(in_srgb,var(--chart-down)_10%,transparent)]",
        text: "text-[color:var(--chart-down)]",
        border: "border-[color-mix(in_srgb,var(--chart-down)_28%,transparent)]",
        label: "看跌",
      };
    case "neutral":
      return {
        icon: <Minus className="w-3.5 h-3.5" />,
        bg: "bg-[var(--surface-muted)]",
        text: "text-[var(--ink-soft)]",
        border: "border-[var(--table-border)]",
        label: "中性",
      };
  }
}

// Result badge
function ResultBadge({ result, returnRate }: { result?: "profit" | "loss" | "neutral"; returnRate?: number }) {
  if (!result || !returnRate) return null;

  const styles = {
    profit: {
      bg: "bg-[color-mix(in_srgb,var(--chart-up)_12%,transparent)]",
      text: "text-[color:var(--chart-up)]",
      prefix: "+",
    },
    loss: {
      bg: "bg-[color-mix(in_srgb,var(--chart-down)_14%,transparent)]",
      text: "text-[color:var(--chart-down)]",
      prefix: "",
    },
    neutral: { bg: "bg-[var(--surface-muted)]", text: "text-[var(--ink-soft)]", prefix: "" },
  };

  const style = styles[result];

  return (
    <span className={cn(
      "text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded",
      style.bg,
      style.text
    )}>
      {style.prefix}{returnRate.toFixed(1)}%
    </span>
  );
}

// Individual timeline node
function TimelineNode({
  event,
  isLast,
  expanded,
  onToggle,
}: {
  event: TimelineEvent;
  isLast: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const dirStyle = getDirectionStyle(event.direction);

  return (
    <div className="relative">
      {/* Connector line */}
      {!isLast && (
        <div className="absolute left-[19px] top-10 bottom-0 w-px bg-[rgba(95,67,40,0.12)]" />
      )}

      <div
        className={cn(
          "flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all",
          "hover:bg-[rgba(95,67,40,0.04)]",
          expanded && "bg-[rgba(95,67,40,0.04)]"
        )}
        onClick={onToggle}
      >
        {/* Date & Status Icon */}
        <div className="flex flex-col items-center">
          <div className={cn(
            "w-[38px] h-[38px] rounded-full flex items-center justify-center border-2",
            event.verified
              ? event.result === "profit"
                ? "bg-[color-mix(in_srgb,var(--chart-up)_8%,transparent)] border-[color-mix(in_srgb,var(--chart-up)_28%,transparent)]"
                : event.result === "loss"
                  ? "bg-[color-mix(in_srgb,var(--chart-down)_10%,transparent)] border-[color-mix(in_srgb,var(--chart-down)_28%,transparent)]"
                  : "bg-[var(--surface-muted)] border-[var(--table-border)]"
              : "bg-[color-mix(in_srgb,var(--accent-gold)_12%,transparent)] border-[color-mix(in_srgb,var(--accent-gold)_32%,transparent)]"
          )}>
            {event.verified ? (
              event.result === "profit" ? (
                <CheckCircle2 className="w-5 h-5 text-[color:var(--chart-up)]" />
              ) : event.result === "loss" ? (
                <XCircle className="w-5 h-5 text-[color:var(--chart-down)]" />
              ) : (
                <Minus className="w-5 h-5 text-[var(--ink-soft)]" />
              )
            ) : (
              <Clock className="w-5 h-5 text-[var(--accent-gold)]" />
            )}
          </div>
          <span className="text-[9px] text-foreground/50 mt-1 tabular-nums">
            {event.date.slice(5)}
          </span>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-bold text-foreground">{event.ticker}</span>
            <span className={cn(
              "flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border",
              dirStyle.bg,
              dirStyle.text,
              dirStyle.border
            )}>
              {dirStyle.icon}
              {dirStyle.label}
            </span>
            {event.verified && <ResultBadge result={event.result} returnRate={event.returnRate} />}
            {!event.verified && (
              <span className="text-[9px] text-[var(--accent-gold)] bg-[color-mix(in_srgb,var(--accent-gold)_12%,transparent)] px-1.5 py-0.5 rounded border border-[color-mix(in_srgb,var(--accent-gold)_32%,transparent)]">
                待验证
              </span>
            )}
          </div>
          <p className="text-xs text-foreground/60 line-clamp-1">{event.summary}</p>

          {/* Expanded details */}
          {expanded && (
            <div className="mt-2 pt-2 border-t border-[rgba(95,67,40,0.08)]">
              <div className="text-[11px] text-foreground/50 leading-relaxed">
                {event.summary}
              </div>
              {event.verified && event.returnRate !== undefined && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-[10px] text-foreground/40">验证收益:</span>
                  <ResultBadge result={event.result} returnRate={event.returnRate} />
                </div>
              )}
            </div>
          )}
        </div>

        <ChevronRight
          className={cn(
            "w-4 h-4 text-foreground/30 transition-transform",
            expanded && "rotate-90"
          )}
        />
      </div>
    </div>
  );
}

export function PerformanceTimeline({
  events,
  compact = false,
  maxItems = 5,
  className,
}: PerformanceTimelineProps) {
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const displayEvents = compact ? events.slice(0, 3) : events.slice(0, maxItems);

  // Compact horizontal timeline
  if (compact) {
    return (
      <div className={cn("flex items-center gap-2 overflow-x-auto pb-2", className)}>
        {displayEvents.map((event) => {
          const dirStyle = getDirectionStyle(event.direction);
          return (
            <div
              key={event.id}
              className="flex-shrink-0 flex items-center gap-1.5 px-2 py-1.5 bg-white border border-[rgba(95,67,40,0.12)] rounded-lg"
            >
              <span className="text-xs font-bold text-foreground">{event.ticker}</span>
              <span className={cn("text-[10px] font-medium", dirStyle.text)}>
                {dirStyle.icon}
              </span>
              {event.verified && event.returnRate !== undefined && (
                <span className={cn(
                  "text-[9px] font-bold tabular-nums",
                  event.result === "profit"
                    ? "text-[color:var(--chart-up)]"
                    : event.result === "loss"
                      ? "text-[color:var(--chart-down)]"
                      : "text-[var(--ink-soft)]"
                )}>
                  {event.returnRate >= 0 ? "+" : ""}{event.returnRate.toFixed(0)}%
                </span>
              )}
            </div>
          );
        })}
        {events.length > displayEvents.length && (
          <span className="text-[10px] text-foreground/40 flex-shrink-0">
            +{events.length - displayEvents.length}
          </span>
        )}
      </div>
    );
  }

  // Full vertical timeline
  return (
    <div className={cn("space-y-1", className)}>
      {displayEvents.map((event, index) => (
        <TimelineNode
          key={event.id}
          event={event}
          isLast={index === displayEvents.length - 1}
          expanded={expandedId === event.id}
          onToggle={() => setExpandedId(expandedId === event.id ? null : event.id)}
        />
      ))}

      {events.length > maxItems && (
        <button className="w-full text-center text-xs text-foreground/50 hover:text-morningstar-red py-2 transition-colors">
          查看全部 {events.length} 条记录
        </button>
      )}
    </div>
  );
}

export default PerformanceTimeline;