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

/**
 * 方向配色。**中国惯例：红=看多/上涨，绿=看空/下跌**（--chart-up/-down）。
 * 此前这里是西方口径（bullish 绿 / bearish 红），与全仓其余组件正相反——
 * 与 PerformanceTimeline 2026-08-14 修过的是同一个错。
 */
const DIRECTION_STYLES: Record<OpinionDirection, { bg: string; border: string; text: string; icon: React.ReactNode }> = {
  bullish: {
    bg: "bg-[color-mix(in_srgb,var(--chart-up)_8%,transparent)]",
    border: "border-[color-mix(in_srgb,var(--chart-up)_28%,transparent)]",
    text: "text-[color:var(--chart-up)]",
    icon: <TrendingUp className="w-4 h-4" strokeWidth={2} />,
  },
  bearish: {
    bg: "bg-[color-mix(in_srgb,var(--chart-down)_10%,transparent)]",
    border: "border-[color-mix(in_srgb,var(--chart-down)_28%,transparent)]",
    text: "text-[color:var(--chart-down)]",
    icon: <TrendingDown className="w-4 h-4" strokeWidth={2} />,
  },
  neutral: {
    bg: "bg-[var(--surface-muted)]",
    border: "border-[var(--table-border)]",
    text: "text-[var(--ink-soft)]",
    icon: <Minus className="w-4 h-4" strokeWidth={2} />,
  },
  watchlist: {
    bg: "bg-[color-mix(in_srgb,var(--accent-gold)_10%,transparent)]",
    border: "border-[color-mix(in_srgb,var(--accent-gold)_30%,transparent)]",
    text: "text-[var(--accent-gold)]",
    icon: <Minus className="w-4 h-4" strokeWidth={2} />,
  },
  risk_warning: {
    bg: "bg-[color-mix(in_srgb,var(--accent-teal)_10%,transparent)]",
    border: "border-[color-mix(in_srgb,var(--accent-teal)_30%,transparent)]",
    text: "text-[var(--accent-teal)]",
    icon: <TrendingDown className="w-4 h-4" strokeWidth={2} />,
  },
};

/** 口径标签与配色。券商=金（口径标注，不是方向），KOL=墨。 */
const SIGNAL_CLASS_META: Record<string, { label: string; color: string }> = {
  broker_recommendation: { label: "券商 · 个股评级", color: "var(--accent-gold)" },
  broker_sector_view: { label: "券商 · 板块观点", color: "var(--accent-gold)" },
  kol_statement: { label: "KOL 自述", color: "var(--ink-soft)" },
};

const DIRECTION_LABELS: Record<OpinionDirection, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  watchlist: "观察",
  risk_warning: "风险",
};

const VERIFICATION_ICONS: Record<VerificationStatus, React.ReactNode> = {
  success: <CheckCircle className="w-3.5 h-3.5 text-success" />,
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

/**
 * 置信度进度条配色。**置信度不是方向**——用中性墨阶而非红绿，
 * 否则同一张卡上「高置信度=绿」会与「看空=绿」撞在一起读不出区别。
 */
function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "bg-[color-mix(in_srgb,var(--foreground)_62%,transparent)]";
  if (confidence >= 0.6) return "bg-[color-mix(in_srgb,var(--foreground)_38%,transparent)]";
  return "bg-[color-mix(in_srgb,var(--foreground)_20%,transparent)]";
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

  // 契约外取值兜底：后端新增方向/状态时页面降级而不是白屏
  const dirStyle = DIRECTION_STYLES[opinion.direction] ?? DIRECTION_STYLES.neutral;
  const verificationIcon =
    VERIFICATION_ICONS[opinion.verificationStatus] ?? VERIFICATION_ICONS.pending;

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

        {/* 标的 + 口径 */}
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
        {/* R6 口径隔离：券商研报与 KOL 自述基准率不同，必须可分辨。
            现役语料 4,919 条里绝大多数是券商研报——不标注会被整体读成 KOL 观点。 */}
        {opinion.signalClass && SIGNAL_CLASS_META[opinion.signalClass] ? (
          <div className="mb-2">
            <span
              className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[9px] font-bold tracking-wider"
              style={{
                color: SIGNAL_CLASS_META[opinion.signalClass].color,
                border: `1px solid color-mix(in srgb, ${SIGNAL_CLASS_META[opinion.signalClass].color} 32%, transparent)`,
                backgroundColor: `color-mix(in srgb, ${SIGNAL_CLASS_META[opinion.signalClass].color} 10%, transparent)`,
              }}
            >
              {SIGNAL_CLASS_META[opinion.signalClass].label}
            </span>
          </div>
        ) : null}

        {/* 方向 + 置信度 */}
        <div className="flex items-center gap-2 mb-3">
          <div className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full",
            dirStyle.bg,
            dirStyle.text
          )}>
            {dirStyle.icon}
            <span className="text-[11px] font-bold uppercase tracking-wide">
              {DIRECTION_LABELS[opinion.direction] ?? opinion.direction}
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
