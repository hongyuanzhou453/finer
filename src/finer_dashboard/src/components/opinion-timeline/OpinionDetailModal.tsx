"use client";

import React, { useEffect, useRef } from "react";
import {
  X,
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle,
  XCircle,
  Clock,
  BarChart3,
  Target,
  Star,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import type { TimelineOpinion, OpinionDirection, ActionStep } from "./OpinionTimeline";
import { cn } from "@/lib/utils";

// ============================================
// 类型定义
// ============================================

export interface OpinionDetailModalProps {
  opinion: TimelineOpinion;
  open: boolean;
  onClose: () => void;
}

// ============================================
// 样式常量
// ============================================

const STYLES = {
  overlay: "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm",
  modal: "bg-[#fcfbf9] w-full max-w-3xl max-h-[90vh] rounded-xl shadow-2xl flex flex-col overflow-hidden border border-stone-200",
  header: "flex items-center justify-between p-6 border-b border-stone-200 bg-white",
  headerTitle: "text-lg font-bold text-foreground",
  closeBtn: "p-2 bg-stone-100 hover:bg-red-50 hover:text-red-500 rounded-sm transition-colors",
  body: "flex-1 overflow-y-auto p-6 space-y-6 finer-scrollbar",
  footer: "p-6 border-t border-stone-200 bg-white/80",
  section: "space-y-3",
  sectionTitle: "text-[10px] font-bold uppercase tracking-widest text-foreground/40 flex items-center gap-2",
  card: "rounded-xl border border-[rgba(95,67,40,0.12)] bg-white p-5",
  cardHighlight: "bg-[rgba(255,252,247,0.72)]",
  row: "flex items-center justify-between py-2",
  label: "text-xs font-medium text-foreground/50",
  value: "text-sm font-bold text-foreground",
  quote: "border-l-2 border-morningstar-red pl-4 italic text-sm leading-relaxed text-foreground/70",
  badge: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold",
  actionStep: "flex items-start gap-4 p-4 rounded-lg border border-stone-100 bg-stone-50/50",
} as const;

const DIRECTION_CONFIG: Record<OpinionDirection, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  bullish: {
    label: "看多",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
    icon: <TrendingUp className="w-5 h-5" />,
  },
  bearish: {
    label: "看空",
    color: "text-red-600",
    bg: "bg-red-50 border-red-200",
    icon: <TrendingDown className="w-5 h-5" />,
  },
  neutral: {
    label: "中性",
    color: "text-stone-600",
    bg: "bg-stone-100 border-stone-300",
    icon: <Minus className="w-5 h-5" />,
  },
  watchlist: {
    label: "观察",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
    icon: <Minus className="w-5 h-5" />,
  },
  risk_warning: {
    label: "风险提示",
    color: "text-teal-700",
    bg: "bg-teal-50 border-teal-200",
    icon: <TrendingDown className="w-5 h-5" />,
  },
};

const VERIFICATION_CONFIG = {
  success: { label: "验证成功", icon: <CheckCircle className="w-4 h-4 text-emerald-500" />, color: "text-emerald-600", bg: "bg-emerald-50" },
  failed: { label: "验证失败", icon: <XCircle className="w-4 h-4 text-red-500" />, color: "text-red-600", bg: "bg-red-50" },
  pending: { label: "待验证", icon: <Clock className="w-4 h-4 text-amber-500" />, color: "text-amber-600", bg: "bg-amber-50" },
};

const ACTION_TYPE_LABELS: Record<ActionStep["actionType"], string> = {
  watch: "观望",
  long: "做多",
  short: "做空",
  add: "加仓",
  reduce: "减仓",
  close_long: "平多",
  close_short: "平空",
};

// add/reduce 是仓位增减语义，方向由观点 direction 决定。注意 direction 是
// 跟单符号（follow-trade sign）而非持仓侧：减多仓=卖出信号（bearish），
// 减空仓=买回信号（bullish）。canonical runner 对 reduce_position 恒给
// bearish——那是减多仓，不能标成减空仓。
function actionTypeLabel(
  actionType: ActionStep["actionType"],
  direction: OpinionDirection,
): string {
  if (actionType === "add") {
    return direction === "bearish" || direction === "risk_warning"
      ? "加空仓"
      : "加仓";
  }
  if (actionType === "reduce") {
    return direction === "bullish" ? "减空仓" : "减仓";
  }
  return ACTION_TYPE_LABELS[actionType];
}

// ============================================
// 子组件: 验证结果卡片
// ============================================

interface VerificationResultProps {
  status: "success" | "failed" | "pending";
  priceChange?: number;
  holdingDays?: number;
}

function VerificationResult({ status, priceChange, holdingDays }: VerificationResultProps) {
  const config = VERIFICATION_CONFIG[status];

  return (
    <div className={cn(STYLES.card, status === "success" && "border-emerald-200", status === "failed" && "border-red-200")}>
      <div className="flex items-center gap-3 mb-4">
        {config.icon}
        <span className={cn("text-sm font-bold", config.color)}>{config.label}</span>
      </div>

      {status !== "pending" && priceChange !== undefined && (
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-4 rounded-lg bg-stone-50">
            <div className={cn(
              "text-2xl font-bold",
              priceChange >= 0 ? "text-emerald-600" : "text-red-600"
            )}>
              {priceChange >= 0 ? "+" : ""}{priceChange.toFixed(2)}%
            </div>
            <div className="text-[10px] uppercase tracking-widest text-foreground/40 mt-1">
              涨跌幅
            </div>
          </div>
          <div className="text-center p-4 rounded-lg bg-stone-50">
            <div className="text-2xl font-bold text-foreground">
              {holdingDays ?? "-"}
            </div>
            <div className="text-[10px] uppercase tracking-widest text-foreground/40 mt-1">
              持有天数
            </div>
          </div>
        </div>
      )}

      {status === "pending" && (
        <p className="text-sm text-foreground/50">
          该观点尚未到达验证时间，系统将在持有期结束后自动计算涨跌幅。
        </p>
      )}
    </div>
  );
}

// ============================================
// 子组件: Action Chain 显示
// ============================================

interface ActionChainDisplayProps {
  steps: ActionStep[];
  direction: OpinionDirection;
}

function ActionChainDisplay({ steps, direction }: ActionChainDisplayProps) {
  if (!steps || steps.length === 0) {
    return (
      <div className="text-sm text-foreground/40 italic">
        无操作链信息
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {steps.map((step, index) => (
        <div key={step.id} className={STYLES.actionStep}>
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white border border-stone-200 flex items-center justify-center text-xs font-bold text-foreground/60">
            {index + 1}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className={cn(
                "px-2 py-0.5 rounded text-xs font-bold",
                (step.actionType === "long" || step.actionType === "add") && "bg-emerald-100 text-emerald-700",
                step.actionType === "short" && "bg-red-100 text-red-700",
                step.actionType === "reduce" && "bg-orange-100 text-orange-700",
                step.actionType === "watch" && "bg-blue-100 text-blue-700",
                (step.actionType === "close_long" || step.actionType === "close_short") && "bg-purple-100 text-purple-700"
              )}>
                {actionTypeLabel(step.actionType, direction)}
              </span>
              {step.actionType === "add" && (
                <span className="text-[10px] uppercase tracking-widest text-foreground/40">
                  增持现有仓位
                </span>
              )}
              {step.actionType === "reduce" && (
                <span className="text-[10px] uppercase tracking-widest text-foreground/40">
                  部分减持 · 非清仓
                </span>
              )}
            </div>
            <div className="space-y-1">
              {step.triggerCondition && (
                <div className="text-xs text-foreground/60">
                  <span className="font-medium">触发条件:</span> {step.triggerCondition}
                </div>
              )}
              {(step.targetPriceLow || step.targetPriceHigh) && (
                <div className="text-xs text-foreground/60">
                  <span className="font-medium">目标价:</span>{" "}
                  {step.targetPriceLow && step.targetPriceHigh
                    ? `${step.targetPriceLow} - ${step.targetPriceHigh}`
                    : step.targetPriceLow || step.targetPriceHigh}
                </div>
              )}
              {step.positionDeltaPct != null && (
                <div className="text-xs text-foreground/60">
                  <span className="font-medium">仓位变动:</span>{" "}
                  {step.positionDeltaPct > 0 ? "+" : ""}
                  {(step.positionDeltaPct * 100).toFixed(0)}%
                </div>
              )}
            </div>
          </div>
          {index < steps.length - 1 && (
            <ChevronRight className="w-4 h-4 text-foreground/20" />
          )}
        </div>
      ))}
    </div>
  );
}

// ============================================
// 子组件: RLHF 状态
// ============================================

interface RLHFStatusProps {
  status?: "pending" | "reviewed" | "skipped";
  rating?: number;
}

function RLHFStatus({ status = "pending", rating }: RLHFStatusProps) {
  const statusConfig = {
    pending: { label: "待评价", color: "text-amber-600", bg: "bg-amber-50" },
    reviewed: { label: "已评价", color: "text-emerald-600", bg: "bg-emerald-50" },
    skipped: { label: "已跳过", color: "text-stone-500", bg: "bg-stone-100" },
  };

  const config = statusConfig[status];

  return (
    <div className={cn(STYLES.card, config.bg)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Star className={cn("w-4 h-4", config.color)} />
          <span className={cn("text-sm font-bold", config.color)}>
            {config.label}
          </span>
        </div>
        {status === "reviewed" && rating && (
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map(i => (
              <Star
                key={i}
                className={cn(
                  "w-4 h-4",
                  i <= rating ? "fill-amber-400 text-amber-400" : "text-stone-300"
                )}
              />
            ))}
          </div>
        )}
      </div>
      {status === "pending" && (
        <p className="mt-3 text-xs text-foreground/50">
          该观点需要人工评价以改进模型。点击下方按钮进入评价工作台。
        </p>
      )}
    </div>
  );
}

// ============================================
// 主组件
// ============================================

export function OpinionDetailModal({ opinion, open, onClose }: OpinionDetailModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  // ESC 关闭
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  const dirConfig = DIRECTION_CONFIG[opinion.direction];

  return (
    <div
      className={STYLES.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={modalRef} className={STYLES.modal}>
        {/* 头部 */}
        <div className={STYLES.header}>
          <div className="flex items-center gap-4">
            <div className={cn(
              "p-2.5 rounded-lg",
              dirConfig.bg
            )}>
              <span className={dirConfig.color}>{dirConfig.icon}</span>
            </div>
            <div>
              <h2 className={STYLES.headerTitle}>
                {opinion.ticker} {opinion.tickerName && `· ${opinion.tickerName}`}
              </h2>
              <p className="text-xs text-foreground/40 mt-0.5">
                观点详情
              </p>
            </div>
          </div>
          <button onClick={onClose} className={STYLES.closeBtn}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 内容 */}
        <div className={STYLES.body}>
          {/* 基本信息 */}
          <div className={STYLES.section}>
            <div className={STYLES.sectionTitle}>
              <Target className="w-3.5 h-3.5" />
              基本信息
            </div>
            <div className={cn(STYLES.card, "grid grid-cols-2 gap-4")}>
              <div className={STYLES.row}>
                <span className={STYLES.label}>方向</span>
                <span className={cn(STYLES.badge, dirConfig.bg, dirConfig.color)}>
                  {dirConfig.icon}
                  {dirConfig.label}
                </span>
              </div>
              <div className={STYLES.row}>
                <span className={STYLES.label}>置信度</span>
                <span className={STYLES.value}>{Math.round(opinion.confidence * 100)}%</span>
              </div>
              <div className={STYLES.row}>
                <span className={STYLES.label}>发布时间</span>
                <span className={STYLES.value}>
                  {new Date(opinion.timestamp).toLocaleString("zh-CN")}
                </span>
              </div>
              {opinion.author && (
                <div className={STYLES.row}>
                  <span className={STYLES.label}>作者</span>
                  <span className={STYLES.value}>{opinion.author}</span>
                </div>
              )}
              {opinion.platform && (
                <div className={STYLES.row}>
                  <span className={STYLES.label}>来源</span>
                  <span className={STYLES.value}>{opinion.platform}</span>
                </div>
              )}
            </div>
          </div>

          {/* 原文引用 */}
          <div className={STYLES.section}>
            <div className={STYLES.sectionTitle}>
              <MessageSquare className="w-3.5 h-3.5" />
              原文引用
            </div>
            <div className={cn(STYLES.card, STYLES.cardHighlight)}>
              <blockquote className={STYLES.quote}>
                &ldquo;{opinion.sourceText}&rdquo;
              </blockquote>
            </div>
          </div>

          {/* Action Chain */}
          {opinion.actionChain && opinion.actionChain.length > 0 && (
            <div className={STYLES.section}>
              <div className={STYLES.sectionTitle}>
                <BarChart3 className="w-3.5 h-3.5" />
                操作链
              </div>
              <div className={STYLES.card}>
                <ActionChainDisplay steps={opinion.actionChain} direction={opinion.direction} />
              </div>
            </div>
          )}

          {/* 验证结果 */}
          <div className={STYLES.section}>
            <div className={STYLES.sectionTitle}>
              <Target className="w-3.5 h-3.5" />
              验证结果
            </div>
            <VerificationResult
              status={opinion.verificationStatus}
              priceChange={opinion.priceChange}
              holdingDays={opinion.holdingDays}
            />
          </div>

          {/* RLHF 状态 */}
          <div className={STYLES.section}>
            <div className={STYLES.sectionTitle}>
              <Star className="w-3.5 h-3.5" />
              RLHF 评价状态
            </div>
            <RLHFStatus
              status={opinion.rlhfStatus}
              rating={opinion.rlhfRating}
            />
          </div>
        </div>

        {/* 底部操作 */}
        <div className={STYLES.footer}>
          <div className="flex items-center justify-between">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-foreground/60 hover:text-foreground transition-colors"
            >
              关闭
            </button>
            <div className="flex items-center gap-3">
              {opinion.rlhfStatus === "pending" && (
                <button
                  className="px-4 py-2 text-sm font-medium text-morningstar-red hover:bg-morningstar-red/10 rounded-sm transition-colors"
                >
                  进入评价工作台
                </button>
              )}
              <button
                className="px-6 py-2.5 bg-morningstar-red hover:bg-red-700 text-white text-sm font-bold rounded-sm shadow-sm transition-colors"
              >
                查看完整历史
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default OpinionDetailModal;
