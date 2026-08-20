"use client";

import React from "react";
import { TrendingUp, TrendingDown, Minus, Eye, AlertTriangle, Check, X, Edit3 } from "lucide-react";
import { cn } from "@/lib/utils";

export type Direction = "bullish" | "bearish" | "neutral" | "watchlist" | "risk_warning";

export interface DirectionReviewProps {
  direction: Direction;
  /** F5 只有整条抽取的把握，缺失时留白——0 会被读成「毫无把握」。 */
  confidence?: number | null;
  rationale: string;
  timeHorizon: string;
  correction?: Direction;
  isCorrecting: boolean;
  onCorrect: (highlightedText?: string) => void;
  onCorrectionSubmit: (value: Direction) => void;
  onCancel: () => void;
}

const DIRECTION_CONFIG: Record<Direction, {
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  colorClass: string;
  bgClass: string;
}> = {
  bullish: {
    label: "看涨",
    icon: TrendingUp,
    colorClass: "text-green-600",
    bgClass: "bg-green-50 border-green-200"
  },
  bearish: {
    label: "看跌",
    icon: TrendingDown,
    colorClass: "text-red-600",
    bgClass: "bg-red-50 border-red-200"
  },
  neutral: {
    label: "中性",
    icon: Minus,
    colorClass: "text-stone-600",
    bgClass: "bg-stone-50 border-stone-200"
  },
  watchlist: {
    label: "观察",
    icon: Eye,
    colorClass: "text-blue-600",
    bgClass: "bg-blue-50 border-blue-200"
  },
  risk_warning: {
    label: "风险警示",
    icon: AlertTriangle,
    colorClass: "text-amber-600",
    bgClass: "bg-amber-50 border-amber-200"
  }
};

export function DirectionReview({
  direction,
  confidence,
  rationale,
  timeHorizon,
  correction,
  isCorrecting,
  onCorrect,
  onCorrectionSubmit,
  onCancel
}: DirectionReviewProps) {
  const [selectedDirection, setSelectedDirection] = React.useState<Direction>(correction || direction);

  React.useEffect(() => {
    setSelectedDirection(correction || direction);
  }, [direction, correction]);

  const displayDirection = correction || direction;
  const hasCorrection = Boolean(correction);
  const config = DIRECTION_CONFIG[displayDirection];
  const Icon = config.icon;
  const confidenceColor =
    confidence == null
      ? "text-foreground/35"
      : confidence >= 0.8
        ? "text-green-600"
        : confidence >= 0.5
          ? "text-amber-600"
          : "text-red-600";

  const handleSubmit = () => {
    if (selectedDirection !== direction) {
      onCorrectionSubmit(selectedDirection);
    } else {
      onCancel();
    }
  };

  return (
    <div className={cn(
      "rounded-xl border overflow-hidden transition-all",
      hasCorrection
        ? "border-green-300 bg-green-50/30"
        : "border-[rgba(95,67,40,0.12)] bg-white/80"
    )}>
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-[rgba(95,67,40,0.08)] bg-[rgba(99,76,55,0.02)] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={cn("w-4 h-4", config.colorClass)} strokeWidth={1.5} />
          <h3 className="text-xs font-bold uppercase tracking-widest text-foreground/70">
            投资方向
          </h3>
        </div>

        {hasCorrection && (
          <div className="flex items-center gap-1 text-[10px] text-green-700 bg-green-100 px-2 py-0.5 rounded-full">
            <Check className="w-3 h-3" />
            <span className="font-medium">已修正</span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {!isCorrecting ? (
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-full border", config.bgClass)}>
                  <Icon className={cn("w-4 h-4", config.colorClass)} />
                  <span className={cn("text-sm font-bold", config.colorClass)}>
                    {config.label}
                  </span>
                </div>
                <span className={cn("text-xs font-medium", confidenceColor)}>
                  {confidence == null ? "—" : `${(confidence * 100).toFixed(0)}%`}
                </span>
              </div>

              <button
                onClick={() => onCorrect()}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-foreground/60 hover:text-morningstar-red hover:bg-red-50 border border-stone-200 hover:border-red-200 rounded-sm transition-all"
              >
                <Edit3 className="w-3 h-3" />
                修正
              </button>
            </div>

            <div className="text-xs text-foreground/60 space-y-1">
              <div className="flex items-start gap-2">
                <span className="font-medium text-foreground/40 shrink-0">时间范围:</span>
                <span>{timeHorizon}</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-medium text-foreground/40 shrink-0">理由:</span>
                <span className="leading-relaxed">{rationale}</span>
              </div>
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(DIRECTION_CONFIG) as Direction[]).map((dir) => {
                const cfg = DIRECTION_CONFIG[dir];
                const DirIcon = cfg.icon;
                const isSelected = selectedDirection === dir;

                return (
                  <button
                    key={dir}
                    onClick={() => setSelectedDirection(dir)}
                    className={cn(
                      "flex items-center gap-2 px-3 py-2 rounded-sm border transition-all",
                      isSelected
                        ? cn(cfg.bgClass, "ring-2 ring-offset-1")
                        : "border-stone-200 bg-white hover:border-stone-300"
                    )}
                  >
                    <DirIcon className={cn("w-4 h-4", cfg.colorClass)} />
                    <span className={cn("text-sm font-medium", isSelected ? cfg.colorClass : "text-foreground/70")}>
                      {cfg.label}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={onCancel}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-foreground/60 hover:text-foreground border border-stone-200 rounded-sm transition-colors"
              >
                <X className="w-3 h-3" />
                取消
              </button>
              <button
                onClick={handleSubmit}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-morningstar-red hover:bg-red-700 rounded-sm transition-colors"
              >
                <Check className="w-3 h-3" />
                确认
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}