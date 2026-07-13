"use client";

import React, { useState } from "react";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle,
  XCircle,
  Clock,
} from "lucide-react";
import type { TimelineOpinion, OpinionDirection, VerificationStatus } from "./OpinionTimeline";
import { cn } from "@/lib/utils";

// ============================================
// 类型定义
// ============================================

export interface TimelineNodeProps {
  opinion: TimelineOpinion;
  onClick: () => void;
  zoom?: number;
  showConnector?: boolean;
}

// ============================================
// 样式常量
// ============================================

const NODE_WIDTH = 180;

const DIRECTION_STYLES: Record<OpinionDirection, { bg: string; border: string; text: string; icon: React.ReactNode }> = {
  bullish: {
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-600",
    icon: <TrendingUp className="w-4 h-4" strokeWidth={2} />,
  },
  bearish: {
    bg: "bg-red-50",
    border: "border-red-200",
    text: "text-red-600",
    icon: <TrendingDown className="w-4 h-4" strokeWidth={2} />,
  },
  neutral: {
    bg: "bg-stone-100",
    border: "border-stone-300",
    text: "text-stone-500",
    icon: <Minus className="w-4 h-4" strokeWidth={2} />,
  },
  watchlist: {
    bg: "bg-amber-50",
    border: "border-amber-200",
    text: "text-amber-600",
    icon: <Minus className="w-4 h-4" strokeWidth={2} />,
  },
  risk_warning: {
    bg: "bg-teal-50",
    border: "border-teal-200",
    text: "text-teal-700",
    icon: <TrendingDown className="w-4 h-4" strokeWidth={2} />,
  },
};

const DIRECTION_LABELS: Record<OpinionDirection, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  watchlist: "观察",
  risk_warning: "风险",
};

const VERIFICATION_ICONS: Record<VerificationStatus, React.ReactNode> = {
  success: <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-500" />,
  pending: <Clock className="w-3.5 h-3.5 text-amber-500" />,
};

// ============================================
// 辅助函数
// ============================================

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  } else if (diffDays < 7) {
    return `${diffDays}天前`;
  } else {
    return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  }
}

function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "bg-emerald-500";
  if (confidence >= 0.6) return "bg-amber-500";
  return "bg-stone-400";
}

// ============================================
// 主组件
// ============================================

export function TimelineNode({
  opinion,
  onClick,
  zoom = 1,
  showConnector: _showConnector = true, // eslint-disable-line @typescript-eslint/no-unused-vars
}: TimelineNodeProps) {
  const [isHovered, setIsHovered] = useState(false);

  const dirStyle = DIRECTION_STYLES[opinion.direction];
  const verificationIcon = VERIFICATION_ICONS[opinion.verificationStatus];

  // 计算节点尺寸
  const nodeWidth = Math.round(NODE_WIDTH * zoom);
  const nodeScale = Math.min(zoom, 1.2);

  return (
    <div
      className="flex-shrink-0 flex items-center"
      style={{ width: `${nodeWidth}px` }}
    >
      {/* 节点卡片 */}
      <button
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={cn(
          "w-full rounded-xl border-2 bg-white p-4 text-left transition-all",
          "hover:shadow-lg hover:-translate-y-1",
          "focus:outline-none focus:ring-2 focus:ring-morningstar-red/30",
          dirStyle.border,
          isHovered && "shadow-md -translate-y-0.5"
        )}
        style={{ transform: `scale(${nodeScale})` }}
      >
        {/* 头部: 时间 + 验证状态 */}
        <div className="flex items-center justify-between mb-3">
          <span className="text-[10px] font-bold uppercase tracking-widest text-foreground/40">
            {formatTimestamp(opinion.timestamp)}
          </span>
          <div className="flex items-center gap-1">
            {verificationIcon}
          </div>
        </div>

        {/* 标的 */}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-bold text-foreground truncate">
            {opinion.ticker}
          </span>
          {opinion.tickerName && (
            <span className="text-[10px] text-foreground/40 truncate">
              {opinion.tickerName}
            </span>
          )}
        </div>

        {/* 方向 + 置信度 */}
        <div className="flex items-center gap-2 mb-3">
          <div className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full",
            dirStyle.bg,
            dirStyle.text
          )}>
            {dirStyle.icon}
            <span className="text-[11px] font-bold uppercase tracking-wide">
              {DIRECTION_LABELS[opinion.direction]}
            </span>
          </div>
        </div>

        {/* 置信度进度条 */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-widest text-foreground/40">
              置信度
            </span>
            <span className="text-[10px] font-medium text-foreground/60">
              {formatConfidence(opinion.confidence)}
            </span>
          </div>
          <div className="h-1.5 bg-stone-100 rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all", getConfidenceColor(opinion.confidence))}
              style={{ width: `${opinion.confidence * 100}%` }}
            />
          </div>
        </div>

        {/* 悬停提示 */}
        {isHovered && (
          <div className="mt-3 pt-3 border-t border-stone-100">
            <p className="text-[10px] text-foreground/50 leading-relaxed line-clamp-2">
              {opinion.sourceText.slice(0, 60)}...
            </p>
            {opinion.author && (
              <p className="text-[9px] text-foreground/30 mt-1">
                — {opinion.author}
              </p>
            )}
          </div>
        )}
      </button>
    </div>
  );
}

export default TimelineNode;
