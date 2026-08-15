"use client";

import React from "react";
import { StarRating } from "./StarRating";
import { DimensionScores } from "./DimensionScores";
import { PerformanceTimeline } from "./PerformanceTimeline";
import { RecentOpinions } from "./RecentOpinions";
import { TrendingUp, TrendingDown, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { KOLRatingResponse } from "@/lib/contracts";

/**
 * 契约根治（2026-08-15）：本组件曾自带一套与后端不符的响应类型
 * （badges/rank/accuracyRate 从未存在于任何后端响应；dimensions/focusAreas/
 * timeline 的形状也各自漂移）。现在 fetch 直接吃 canonical
 * ``KOLRatingResponse``（contracts.ts 镜像 kol.py），再经本文件底部的
 * 显式 adapter 转成展示用视图模型——漂移只可能发生在一处、且有类型检查。
 *
 * 效力门：ratio 字段（successRate/avgReturn/overallRating）在
 * display_policy == count_only 时为 null，渲染一律留白（—），不回填 0。
 */

export interface DimensionScore {
  name: string;
  score: number; // 0-100
  weight: number; // 0-1
  description?: string;
}

export interface TimelineEvent {
  id: string;
  date: string;
  ticker: string;
  direction: "bullish" | "bearish" | "neutral";
  verified: boolean;
  result?: "profit" | "loss" | "neutral";
  returnRate?: number;
  summary: string;
}

export interface FocusArea {
  name: string;
  count: number;
  accuracy: number; // 0-100
  avgReturn: number;
}

export interface RecentOpinion {
  id: string;
  date: string;
  ticker: string;
  direction: "bullish" | "bearish" | "neutral";
  title: string;
  verified: boolean;
  status: "pending" | "correct" | "incorrect";
  returnRate?: number;
  detailPath?: string;
}

export interface KOLRatingCardProps {
  kolId: string;
  className?: string;
  compact?: boolean;
  showTimeline?: boolean;
  showOpinions?: boolean;
}

// ---------------------------------------------------------------------------
// canonical 响应 → 展示视图模型（唯一的形状转换点）
// ---------------------------------------------------------------------------

function toDimensionScores(resp: KOLRatingResponse): DimensionScore[] {
  // 后端 0-5 → 环形图 0-100；weight 后端不提供，不编造
  return resp.dimensions.map((d) => ({
    name: d.label,
    score: Math.round(d.score * 20),
    weight: 0,
  }));
}

function toTimelineEvents(resp: KOLRatingResponse): TimelineEvent[] {
  // 业绩时间线的事件源 = recentOpinions（有 ticker/方向/结果的真实字段）；
  // resp.timeline 是净值采样点（无 ticker），不能拼成事件——此前把它硬塞
  // 进来渲染的是 undefined。
  return resp.recentOpinions.map((o) => ({
    id: o.id,
    date: o.timestamp.slice(0, 10),
    ticker: o.ticker,
    direction: (["bullish", "bearish", "neutral"].includes(o.direction)
      ? o.direction
      : "neutral") as TimelineEvent["direction"],
    verified: o.result === "success" || o.result === "failed" || o.result === "verified",
    result:
      o.result === "success" || o.result === "verified"
        ? "profit"
        : o.result === "failed"
          ? "loss"
          : undefined,
    summary: o.ticker_name ?? o.ticker,
  }));
}

function toRecentOpinions(resp: KOLRatingResponse): RecentOpinion[] {
  return resp.recentOpinions.map((o) => ({
    id: o.id,
    date: o.timestamp.slice(0, 10),
    ticker: o.ticker,
    direction: (["bullish", "bearish", "neutral"].includes(o.direction)
      ? o.direction
      : "neutral") as RecentOpinion["direction"],
    title: o.ticker_name ?? o.ticker,
    verified: o.result === "success" || o.result === "failed" || o.result === "verified",
    status:
      o.result === "success" || o.result === "verified"
        ? "correct"
        : o.result === "failed"
          ? "incorrect"
          : "pending",
  }));
}

export function KOLRatingCard({
  kolId,
  className,
  compact = false,
  showTimeline = true,
  showOpinions = true,
}: KOLRatingCardProps) {
  const [data, setData] = React.useState<KOLRatingResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/kol/rating/${kolId}`);
        if (!res.ok) {
          throw new Error(`API error: ${res.status}`);
        }
        const json = await res.json();
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [kolId]);

  if (loading) {
    return (
      <div className={cn("research-panel p-8", className)}>
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-6 h-6 animate-spin text-[var(--chart-up)]" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={cn("research-panel p-8", className)}>
        <div className="flex items-center justify-center h-48 text-foreground/50">
          <AlertCircle className="w-5 h-5 mr-2" />
          <span className="text-sm">加载失败</span>
        </div>
      </div>
    );
  }

  const { rating } = data;
  const dimensions = toDimensionScores(data);
  const timeline = toTimelineEvents(data);
  const focusAreas = data.focusAreas;
  const recentOpinions = toRecentOpinions(data);
  const countOnly = rating.sufficiency.display_policy === "count_only";
  const directionIcon =
    rating.avgReturn != null && rating.avgReturn >= 0 ? (
      <TrendingUp className="w-4 h-4" />
    ) : (
      <TrendingDown className="w-4 h-4" />
    );

  return (
    <div className={cn("research-panel", className)}>
      {/* Header: Core Rating + Key Metrics */}
      <div className="research-panel-header p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            {/* Avatar */}
            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-[rgba(159,29,34,0.1)] to-[rgba(31,106,103,0.1)] flex items-center justify-center text-lg font-bold text-foreground/80 border border-[rgba(95,67,40,0.12)]">
              {rating.name.charAt(0)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-foreground">{rating.name}</h3>
                <span className="text-[10px] font-bold uppercase tracking-widest text-foreground/50 bg-stone-100 px-2 py-0.5 rounded">
                  {rating.platform}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1">
                {rating.overallRating != null ? (
                  <StarRating rating={rating.overallRating} size="lg" showLabel />
                ) : (
                  <span className="text-xs text-foreground/50">
                    样本不足，仅显示计数
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Key Metrics */}
          <div className="flex items-center gap-6">
            <MetricBlock
              label="观点数"
              value={rating.totalOpinions.toString()}
              subLabel={`${rating.settledOpinions} 已结算`}
            />
            {/* 效力门 count_only 时为 null → 留白（—），不得回填 0 */}
            <MetricBlock
              label="结算命中率"
              value={
                rating.successRate != null
                  ? `${(rating.successRate * 100).toFixed(1)}%`
                  : "—"
              }
            />
            <MetricBlock
              label="平均收益"
              value={
                rating.avgReturn != null
                  ? `${rating.avgReturn >= 0 ? "+" : ""}${rating.avgReturn.toFixed(1)}%`
                  : "—"
              }
              trend={
                rating.avgReturn == null
                  ? undefined
                  : rating.avgReturn >= 0
                    ? "up"
                    : "down"
              }
              icon={rating.avgReturn != null ? directionIcon : undefined}
            />
          </div>
        </div>
      </div>

      {/* 效力门横幅：比率被撤下时说明原因，而不是让空位无声出现 */}
      {countOnly && (
        <div className="px-6 py-3 border-b border-[rgba(95,67,40,0.08)] text-[11px] leading-relaxed text-foreground/60">
          已结算样本不足（{rating.settledOpinions} 条），本卡只显示计数；
          比率、评分与维度分在样本达标前不呈现——留白比一个不可靠的数字诚实。
        </div>
      )}

      {/* Body: Dimension Scores（空 = 无数据依据或门未过，整节隐藏） */}
      {dimensions.length > 0 && (
        <div className="p-6 border-b border-[rgba(95,67,40,0.08)]">
          <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/40 mb-4">
            维度评分
          </div>
          <DimensionScores dimensions={dimensions} compact={compact} />
        </div>
      )}

      {/* Focus Areas：后端只给标的代码列表（无每域统计），只渲染标签，
          不给 FocusAreas 组件喂零值编造出「0% 准确率」 */}
      {focusAreas.length > 0 && (
        <div className="p-6 border-b border-[rgba(95,67,40,0.08)]">
          <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/40 mb-4">
            高频标的
          </div>
          <div className="flex flex-wrap gap-1.5">
            {focusAreas.map((t) => (
              <span
                key={t}
                className="rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-2 py-0.5 font-mono text-[11px] tabular-nums text-foreground/70"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Timeline */}
      {showTimeline && (
        <div className="p-6 border-b border-[rgba(95,67,40,0.08)]">
          <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/40 mb-4">
            业绩时间线
          </div>
          <PerformanceTimeline events={timeline} compact={compact} />
        </div>
      )}

      {/* Recent Opinions */}
      {showOpinions && (
        <div className="p-6">
          <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/40 mb-4">
            最近观点
          </div>
          <RecentOpinions opinions={recentOpinions} compact={compact} />
        </div>
      )}
    </div>
  );
}

// Helper component for metric blocks
function MetricBlock({
  label,
  value,
  subLabel,
  trend,
  icon
}: {
  label: string;
  value: string;
  subLabel?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
}) {
  const trendColors = {
    up: "text-[var(--chart-up)]",
    down: "text-[var(--chart-down)]",
    neutral: "text-foreground/70",
  };

  return (
    <div className="text-center">
      <div className="text-[9px] font-bold uppercase tracking-widest text-foreground/40 mb-1">
        {label}
      </div>
      <div className={cn(
        "text-xl font-bold tabular-nums flex items-center justify-center gap-1",
        trend ? trendColors[trend] : "text-foreground"
      )}>
        {icon}
        {value}
      </div>
      {subLabel && (
        <div className="text-[10px] text-foreground/50 mt-0.5">
          {subLabel}
        </div>
      )}
    </div>
  );
}

export default KOLRatingCard;