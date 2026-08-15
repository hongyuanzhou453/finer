"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus, Clock, CheckCircle2, XCircle, ExternalLink, ChevronRight } from "lucide-react";
import type { RecentOpinion } from "./KOLRatingCard";

export interface RecentOpinionsProps {
  opinions: RecentOpinion[];
  compact?: boolean;
  maxItems?: number;
  className?: string;
}

// Direction style
function getDirectionStyle(direction: "bullish" | "bearish" | "neutral") {
  switch (direction) {
    case "bullish":
      return {
        icon: <TrendingUp className="w-3.5 h-3.5" />,
        bg: "bg-emerald-50",
        text: "text-emerald-600",
        border: "border-emerald-200",
        label: "看涨",
      };
    case "bearish":
      return {
        icon: <TrendingDown className="w-3.5 h-3.5" />,
        bg: "bg-red-50",
        text: "text-red-600",
        border: "border-red-200",
        label: "看跌",
      };
    case "neutral":
      return {
        icon: <Minus className="w-3.5 h-3.5" />,
        bg: "bg-stone-50",
        text: "text-stone-600",
        border: "border-stone-200",
        label: "中性",
      };
  }
}

// Status style
function getStatusStyle(status: "pending" | "correct" | "incorrect") {
  switch (status) {
    case "correct":
      return {
        icon: <CheckCircle2 className="w-3.5 h-3.5" />,
        bg: "bg-emerald-50",
        text: "text-emerald-600",
        border: "border-emerald-200",
        label: "正确",
      };
    case "incorrect":
      return {
        icon: <XCircle className="w-3.5 h-3.5" />,
        bg: "bg-red-50",
        text: "text-red-600",
        border: "border-red-200",
        label: "错误",
      };
    case "pending":
      return {
        icon: <Clock className="w-3.5 h-3.5" />,
        bg: "bg-amber-50",
        text: "text-amber-600",
        border: "border-amber-200",
        label: "待验证",
      };
  }
}

// Opinion row
function OpinionRow({
  opinion,
  onClick,
}: {
  opinion: RecentOpinion;
  onClick?: () => void;
}) {
  const dirStyle = getDirectionStyle(opinion.direction);
  const statusStyle = getStatusStyle(opinion.status);

  return (
    <div
      className={cn(
        "flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer",
        "bg-white border-[rgba(95,67,40,0.08)]",
        "hover:border-[rgba(159,29,34,0.2)] hover:shadow-sm"
      )}
      onClick={onClick}
    >
      {/* Ticker + Direction */}
      <div className="flex items-center gap-2 min-w-[100px]">
        <span className="text-sm font-bold text-foreground">{opinion.ticker}</span>
        <span className={cn(
          "flex items-center gap-0.5 text-[9px] font-medium px-1.5 py-0.5 rounded border",
          dirStyle.bg,
          dirStyle.text,
          dirStyle.border
        )}>
          {dirStyle.icon}
          {dirStyle.label}
        </span>
      </div>

      {/* Title */}
      <div className="flex-1 min-w-0">
        <p className="text-xs text-foreground/80 line-clamp-1">{opinion.title}</p>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2">
        <span className={cn(
          "flex items-center gap-1 text-[9px] font-medium px-1.5 py-0.5 rounded border",
          statusStyle.bg,
          statusStyle.text,
          statusStyle.border
        )}>
          {statusStyle.icon}
          {statusStyle.label}
        </span>

        {/* Return rate if verified */}
        {opinion.verified && opinion.returnRate !== undefined && (
          <span className={cn(
            "text-xs font-bold tabular-nums",
            opinion.returnRate >= 0 ? "text-emerald-600" : "text-red-600"
          )}>
            {opinion.returnRate >= 0 ? "+" : ""}{opinion.returnRate.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Date & Arrow */}
      <div className="flex items-center gap-2 min-w-[80px] justify-end">
        <span className="text-[10px] text-foreground/40 tabular-nums">{opinion.date}</span>
        <ChevronRight className="w-4 h-4 text-foreground/20" />
      </div>
    </div>
  );
}

// Compact opinion chip
function OpinionChip({ opinion }: { opinion: RecentOpinion }) {
  const dirStyle = getDirectionStyle(opinion.direction);
  const statusStyle = getStatusStyle(opinion.status);

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-white border border-[rgba(95,67,40,0.08)] rounded-lg">
      <span className="text-xs font-bold text-foreground">{opinion.ticker}</span>
      <span className={cn("text-[9px]", dirStyle.text)}>{dirStyle.icon}</span>
      <div className="w-px h-3 bg-stone-200" />
      <span className={cn("text-[9px] font-medium", statusStyle.text)}>
        {statusStyle.label}
      </span>
      {opinion.verified && opinion.returnRate !== undefined && (
        <>
          <div className="w-px h-3 bg-stone-200" />
          <span className={cn(
            "text-[10px] font-bold tabular-nums",
            opinion.returnRate >= 0 ? "text-emerald-600" : "text-red-600"
          )}>
            {opinion.returnRate >= 0 ? "+" : ""}{opinion.returnRate.toFixed(0)}%
          </span>
        </>
      )}
    </div>
  );
}

export function RecentOpinions({
  opinions,
  compact = false,
  maxItems = 5,
  className,
}: RecentOpinionsProps) {
  const displayOpinions = compact ? opinions.slice(0, 3) : opinions.slice(0, maxItems);

  // Calculate summary stats
  const stats = React.useMemo(() => {
    const verified = opinions.filter(o => o.verified);
    const correct = verified.filter(o => o.status === "correct").length;
    const pending = opinions.filter(o => o.status === "pending").length;

    return {
      total: opinions.length,
      verified: verified.length,
      correct,
      // null（不是 0）：无已裁决样本时比率不存在——0% 是一个会被当真的数字
      accuracy: verified.length > 0 ? (correct / verified.length) * 100 : null,
      pending,
    };
  }, [opinions]);

  // Compact: horizontal scroll chips
  if (compact) {
    return (
      <div className={cn("flex items-center gap-2 overflow-x-auto pb-2", className)}>
        {displayOpinions.map((opinion) => (
          <OpinionChip key={opinion.id} opinion={opinion} />
        ))}
        {opinions.length > displayOpinions.length && (
          <span className="text-[10px] text-foreground/40 flex-shrink-0">
            +{opinions.length - displayOpinions.length}
          </span>
        )}
      </div>
    );
  }

  // Full: vertical list with stats header
  return (
    <div className={cn("space-y-3", className)}>
      {/* Stats summary */}
      <div className="flex items-center gap-4 p-3 bg-[rgba(95,67,40,0.04)] rounded-lg">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-foreground/50">总计</span>
          <span className="text-sm font-bold text-foreground tabular-nums">{stats.total}</span>
        </div>
        <div className="w-px h-4 bg-stone-200" />
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-foreground/50">已验证</span>
          <span className="text-sm font-bold text-foreground tabular-nums">{stats.verified}</span>
        </div>
        <div className="w-px h-4 bg-stone-200" />
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-foreground/50">准确率</span>
          <span className={cn(
            "text-sm font-bold tabular-nums",
            stats.accuracy == null
              ? "text-foreground/30"
              : stats.accuracy >= 60 ? "text-emerald-600" : stats.accuracy >= 40 ? "text-yellow-600" : "text-red-600"
          )}>
            {stats.accuracy == null ? "—" : `${stats.accuracy.toFixed(0)}%`}
          </span>
        </div>
        {stats.pending > 0 && (
          <>
            <div className="w-px h-4 bg-stone-200" />
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-foreground/50">待验证</span>
              <span className="text-sm font-bold text-amber-600 tabular-nums">{stats.pending}</span>
            </div>
          </>
        )}
      </div>

      {/* Opinion list */}
      <div className="space-y-2">
        {displayOpinions.map((opinion) => (
          <OpinionRow
            key={opinion.id}
            opinion={opinion}
            onClick={() => {
              if (opinion.detailPath) {
                window.open(opinion.detailPath, "_blank");
              }
            }}
          />
        ))}
      </div>

      {/* Load more */}
      {opinions.length > maxItems && (
        <button className="w-full flex items-center justify-center gap-2 text-xs text-foreground/50 hover:text-morningstar-red py-2 transition-colors">
          查看全部 {opinions.length} 条观点
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

export default RecentOpinions;