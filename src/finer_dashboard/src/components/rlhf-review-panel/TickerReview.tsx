"use client";

import React from "react";
import { Badge, Check, X, Edit3 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TickerReviewProps {
  ticker: string;
  /** F5 只有整条抽取的把握，缺失时留白——0 会被读成「毫无把握」。 */
  confidence?: number | null;
  correction?: string;
  isCorrecting: boolean;
  onCorrect: (highlightedText?: string) => void;
  onCorrectionSubmit: (value: string) => void;
  onCancel: () => void;
}

export function TickerReview({
  ticker,
  confidence,
  correction,
  isCorrecting,
  onCorrect,
  onCorrectionSubmit,
  onCancel
}: TickerReviewProps) {
  const [inputValue, setInputValue] = React.useState(correction || ticker);

  React.useEffect(() => {
    setInputValue(correction || ticker);
  }, [ticker, correction]);

  const displayTicker = correction || ticker;
  const hasCorrection = Boolean(correction);
  const confidenceColor =
    confidence == null
      ? "text-foreground/35"
      : confidence >= 0.8
        ? "text-green-600"
        : confidence >= 0.5
          ? "text-amber-600"
          : "text-red-600";

  const handleSubmit = () => {
    if (inputValue.trim() && inputValue !== ticker) {
      onCorrectionSubmit(inputValue.trim().toUpperCase());
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
          <Badge className="w-4 h-4 text-morningstar-red" strokeWidth={1.5} />
          <h3 className="text-xs font-bold uppercase tracking-widest text-foreground/70">
            股票代码
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
      <div className="p-4">
        {!isCorrecting ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-xl font-bold text-foreground font-mono">
                {displayTicker}
              </span>
              <span className={cn("text-xs font-medium", confidenceColor)}>
                {confidence == null ? "—" : `${(confidence * 100).toFixed(0)}%`}
              </span>
            </div>

            <button
              onClick={() => onCorrect(displayTicker)}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-foreground/60 hover:text-morningstar-red hover:bg-red-50 border border-stone-200 hover:border-red-200 rounded-sm transition-all"
            >
              <Edit3 className="w-3 h-3" />
              修正
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value.toUpperCase())}
                placeholder="输入正确的股票代码"
                className="flex-1 px-3 py-2 text-sm font-mono bg-white border border-stone-300 focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 rounded-sm outline-none transition-all"
                autoFocus
              />
            </div>

            <div className="flex items-center justify-end gap-2">
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