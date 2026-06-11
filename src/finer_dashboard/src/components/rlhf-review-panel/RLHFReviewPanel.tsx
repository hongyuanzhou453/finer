"use client";

import React from "react";
import { X, ChevronLeft, ChevronRight, AlertTriangle, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { OriginalTextCard } from "./OriginalTextCard";
import { TickerReview } from "./TickerReview";
import { DirectionReview } from "./DirectionReview";
import { ActionChainReview } from "./ActionChainReview";
import { OverallRating } from "./OverallRating";
import { QuickTags } from "./QuickTags";
import { ReviewNotes } from "./ReviewNotes";
import { ReviewActions } from "./ReviewActions";

// ============================================================================
// Types
// ============================================================================

export type ReviewState = "idle" | "reviewing" | "correcting" | "rating" | "ready_to_submit";

export type ReviewField = "ticker" | "direction" | "action_chain" | null;

export interface RLHFReviewItem {
  id: string;
  originalText: string;
  sourceFile: string;
  extractedAt: string;

  // 提取结果
  ticker: string;
  tickerConfidence: number;
  direction: "bullish" | "bearish" | "neutral" | "watchlist" | "risk_warning";
  directionConfidence: number;
  rationale: string;
  timeHorizon: string;
  actionChain: ActionChainItem[];

  // 用户评价
  userRating?: number;
  userTags?: string[];
  userNotes?: string;
  corrections?: ReviewCorrections;
  flaggedAsError?: boolean;
}

export interface ActionChainItem {
  id: string;
  actionType: string;
  instrumentType: string;
  triggerCondition: string;
  targetPriceLow?: string;
  targetPriceHigh?: string;
  confidence: number;
  status: "draft" | "active" | "watch";
  userCorrected?: boolean;
  userCorrection?: Partial<ActionChainItem>;
}

export interface ReviewCorrections {
  ticker?: string;
  direction?: "bullish" | "bearish" | "neutral" | "watchlist" | "risk_warning";
  actionChain?: ActionChainItem[];
}

export interface RLHFReviewPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete?: (reviewedCount: number) => void;
}

// ============================================================================
// Main Component
// ============================================================================

export function RLHFReviewPanel({ isOpen, onClose, onComplete }: RLHFReviewPanelProps) {
  // State
  const [currentIndex, setCurrentIndex] = React.useState(0);
  const [items, setItems] = React.useState<RLHFReviewItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [reviewState, setReviewState] = React.useState<ReviewState>("idle");
  const [activeCorrectionField, setActiveCorrectionField] = React.useState<ReviewField>(null);
  const [highlightedText, setHighlightedText] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  // Current item state
  const [rating, setRating] = React.useState(0);
  const [selectedTags, setSelectedTags] = React.useState<string[]>([]);
  const [notes, setNotes] = React.useState("");
  const [corrections, setCorrections] = React.useState<ReviewCorrections>({});
  const [flaggedAsError, setFlaggedAsError] = React.useState(false);

  const currentItem = items[currentIndex];
  const totalItems = items.length;
  const reviewedCount = items.filter(item => item.userRating !== undefined).length;

  // Fetch pending items
  React.useEffect(() => {
    if (isOpen && items.length === 0) {
      fetchPendingItems();
    }
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard shortcuts
  React.useEffect(() => {
    if (!isOpen || !currentItem) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Number keys 1-5 for rating
      if (e.key >= "1" && e.key <= "5" && reviewState !== "correcting") {
        const num = parseInt(e.key);
        setRating(num);
        setReviewState("rating");
      }

      // S for skip
      if (e.key.toLowerCase() === "s" && !e.metaKey && !e.ctrlKey) {
        handleSkip();
      }

      // F for flag
      if (e.key.toLowerCase() === "f" && !e.metaKey && !e.ctrlKey) {
        handleFlag();
      }

      // Enter for submit
      if (e.key === "Enter" && reviewState === "ready_to_submit") {
        handleSubmit();
      }

      // Escape to cancel correction
      if (e.key === "Escape" && reviewState === "correcting") {
        setActiveCorrectionField(null);
        setReviewState("reviewing");
        setHighlightedText(null);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, currentItem, reviewState, rating]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset state when moving to next item
  React.useEffect(() => {
    if (currentItem) {
      setRating(currentItem.userRating || 0);
      setSelectedTags(currentItem.userTags || []);
      setNotes(currentItem.userNotes || "");
      setCorrections(currentItem.corrections || {});
      setFlaggedAsError(currentItem.flaggedAsError || false);
      setReviewState("reviewing");
      setActiveCorrectionField(null);
      setHighlightedText(null);
    }
  }, [currentIndex, currentItem?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update ready state
  React.useEffect(() => {
    if (rating > 0 && reviewState !== "correcting") {
      setReviewState("ready_to_submit");
    }
  }, [rating, reviewState]);

  const fetchPendingItems = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/rlhf/pending");
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch pending items:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCorrectField = (field: ReviewField, highlightedText?: string) => {
    setActiveCorrectionField(field);
    setHighlightedText(highlightedText || null);
    setReviewState("correcting");
  };

  const handleCorrectionSubmit = (field: ReviewField, value: string | ActionChainItem[]) => {
    const key = field === "action_chain" ? "actionChain" : field as keyof ReviewCorrections;
    setCorrections(prev => ({
      ...prev,
      [key]: value
    }));
    setActiveCorrectionField(null);
    setHighlightedText(null);
    setReviewState("rating");
  };

  const handleSkip = () => {
    if (currentIndex < totalItems - 1) {
      setCurrentIndex(prev => prev + 1);
    } else {
      onClose();
    }
  };

  const handleFlag = () => {
    setFlaggedAsError(prev => !prev);
  };

  const handleSubmit = async () => {
    if (!currentItem || submitting) return;

    setSubmitting(true);
    try {
      // 映射前端 camelCase action chain → 后端 snake_case 抽取格式
      const mapChain = (chain?: ActionChainItem[]) =>
        (chain ?? []).map((a) => ({
          action_type: a.actionType,
          instrument_type: a.instrumentType,
          trigger_condition: a.triggerCondition,
          target_price_low: a.targetPriceLow ? Number(a.targetPriceLow) : undefined,
          target_price_high: a.targetPriceHigh ? Number(a.targetPriceHigh) : undefined,
        }));

      // 与后端 RLHFFeedbackCreate 对齐：trade_action_id / quick_tags / original_extraction / corrections / flagged_as_error
      // 后端 build_preference 用 original_extraction + corrections 组装 DPO preference（环 B 桥）
      const res = await fetch("/api/rlhf/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trade_action_id: currentItem.id,
          rating,
          quick_tags: selectedTags,
          notes,
          original_extraction: {
            ticker: currentItem.ticker,
            direction: currentItem.direction,
            action_chain: mapChain(currentItem.actionChain),
            time_horizon: currentItem.timeHorizon,
            rationale: currentItem.rationale,
            evidence_text: currentItem.originalText,
          },
          corrections: {
            ticker: corrections.ticker,
            direction: corrections.direction,
            action_chain: corrections.actionChain ? mapChain(corrections.actionChain) : undefined,
          },
          flagged_as_error: flaggedAsError,
        })
      });

      if (res.ok) {
        // Update local state
        setItems(prev => prev.map((item, idx) =>
          idx === currentIndex
            ? { ...item, userRating: rating, userTags: selectedTags, userNotes: notes, corrections, flaggedAsError }
            : item
        ));

        // Move to next or close
        if (currentIndex < totalItems - 1) {
          setCurrentIndex(prev => prev + 1);
        } else {
          onComplete?.(reviewedCount + 1);
          onClose();
        }
      }
    } catch (err) {
      console.error("Failed to submit review:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative ml-auto w-full max-w-4xl h-full bg-[rgba(255,252,247,0.98)] border-l border-[rgba(95,67,40,0.12)] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <header className="flex-shrink-0 h-16 px-6 flex items-center justify-between border-b border-[rgba(95,67,40,0.12)] bg-white/50">
          <div className="flex items-center gap-4">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-widest">
              RLHF 评价面板
            </h2>
            <span className="text-[10px] font-medium text-foreground/50 uppercase tracking-wider">
              {reviewedCount}/{totalItems} 已评价
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Keyboard hints */}
            <div className="hidden md:flex items-center gap-2 text-[9px] font-medium text-foreground/40 uppercase tracking-wider">
              <kbd className="px-1.5 py-0.5 bg-stone-100 border border-stone-200 rounded">1-5</kbd>
              <span>评分</span>
              <kbd className="px-1.5 py-0.5 bg-stone-100 border border-stone-200 rounded ml-2">S</kbd>
              <span>跳过</span>
              <kbd className="px-1.5 py-0.5 bg-stone-100 border border-stone-200 rounded ml-2">F</kbd>
              <span>标记异常</span>
            </div>

            <button
              onClick={onClose}
              className="p-2 text-foreground/40 hover:text-morningstar-red hover:bg-red-50 rounded-sm transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-sm text-foreground/40">加载中...</div>
            </div>
          ) : !currentItem ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <Check className="w-12 h-12 text-green-500 mx-auto mb-4" />
                <p className="text-sm font-medium text-foreground/60">暂无待评价内容</p>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col overflow-hidden">
              {/* Progress bar */}
              <div className="flex-shrink-0 h-1 bg-stone-100">
                <div
                  className="h-full bg-morningstar-red transition-all duration-300"
                  style={{ width: `${((currentIndex + 1) / totalItems) * 100}%` }}
                />
              </div>

              {/* Main content area */}
              <div className="flex-1 overflow-y-auto finer-scrollbar p-6 space-y-6">
                {/* Original text */}
                <OriginalTextCard
                  text={currentItem.originalText}
                  sourceFile={currentItem.sourceFile}
                  extractedAt={currentItem.extractedAt}
                  highlightedText={highlightedText}
                />

                {/* Field reviews */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <TickerReview
                    ticker={currentItem.ticker}
                    confidence={currentItem.tickerConfidence}
                    correction={corrections.ticker}
                    isCorrecting={activeCorrectionField === "ticker"}
                    onCorrect={(highlightedText) => handleCorrectField("ticker", highlightedText)}
                    onCorrectionSubmit={(value) => handleCorrectionSubmit("ticker", value)}
                    onCancel={() => {
                      setActiveCorrectionField(null);
                      setHighlightedText(null);
                      setReviewState("reviewing");
                    }}
                  />

                  <DirectionReview
                    direction={currentItem.direction}
                    confidence={currentItem.directionConfidence}
                    rationale={currentItem.rationale}
                    timeHorizon={currentItem.timeHorizon}
                    correction={corrections.direction}
                    isCorrecting={activeCorrectionField === "direction"}
                    onCorrect={(highlightedText) => handleCorrectField("direction", highlightedText)}
                    onCorrectionSubmit={(value) => handleCorrectionSubmit("direction", value)}
                    onCancel={() => {
                      setActiveCorrectionField(null);
                      setHighlightedText(null);
                      setReviewState("reviewing");
                    }}
                  />
                </div>

                {/* Action chain review */}
                <ActionChainReview
                  actions={currentItem.actionChain}
                  corrections={corrections.actionChain}
                  isCorrecting={activeCorrectionField === "action_chain"}
                  onCorrect={() => handleCorrectField("action_chain")}
                  onCorrectionSubmit={(actions) => handleCorrectionSubmit("action_chain", actions)}
                  onCancel={() => {
                    setActiveCorrectionField(null);
                    setReviewState("reviewing");
                  }}
                />

                {/* Rating and tags */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <OverallRating
                    value={rating}
                    onChange={setRating}
                    disabled={reviewState === "correcting"}
                  />

                  <QuickTags
                    selected={selectedTags}
                    onChange={setSelectedTags}
                  />
                </div>

                {/* Notes */}
                <ReviewNotes
                  value={notes}
                  onChange={setNotes}
                  placeholder="补充说明、修正理由、特殊情况备注..."
                />

                {/* Flag indicator */}
                {flaggedAsError && (
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700">
                    <AlertTriangle className="w-4 h-4" />
                    <span className="text-sm font-medium">已标记为异常数据</span>
                  </div>
                )}
              </div>

              {/* Actions footer */}
              <div className="flex-shrink-0 border-t border-[rgba(95,67,40,0.12)] bg-white/50 p-4">
                <ReviewActions
                  onSubmit={handleSubmit}
                  onSkip={handleSkip}
                  onFlag={handleFlag}
                  onPrevious={handlePrevious}
                  canSubmit={reviewState === "ready_to_submit" || reviewState === "rating"}
                  canGoBack={currentIndex > 0}
                  isSubmitting={submitting}
                  isFlagged={flaggedAsError}
                  hasCorrections={Object.keys(corrections).length > 0}
                />

                {/* Navigation */}
                <div className="flex items-center justify-center gap-2 mt-3 text-[10px] text-foreground/40">
                  <button
                    onClick={handlePrevious}
                    disabled={currentIndex === 0}
                    className={cn(
                      "flex items-center gap-1 px-2 py-1 rounded transition-colors",
                      currentIndex > 0
                        ? "hover:bg-stone-100 text-foreground/60"
                        : "opacity-40 cursor-not-allowed"
                    )}
                  >
                    <ChevronLeft className="w-3 h-3" />
                    上一条
                  </button>

                  <span className="px-3 py-1 bg-stone-100 rounded text-foreground/60 font-medium">
                    {currentIndex + 1} / {totalItems}
                  </span>

                  <button
                    onClick={handleSkip}
                    className="flex items-center gap-1 px-2 py-1 rounded hover:bg-stone-100 text-foreground/60 transition-colors"
                  >
                    下一条
                    <ChevronRight className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}