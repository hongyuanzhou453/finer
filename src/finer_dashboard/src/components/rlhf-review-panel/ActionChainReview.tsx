"use client";

import React from "react";
import { Zap, Check, X, Edit3, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ActionChainItem } from "./RLHFReviewPanel";

export interface ActionChainReviewProps {
  actions: ActionChainItem[];
  corrections?: ActionChainItem[];
  isCorrecting: boolean;
  onCorrect: () => void;
  onCorrectionSubmit: (actions: ActionChainItem[]) => void;
  onCancel: () => void;
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  hold: "持有",
  short: "做空",
  cover: "平仓",
  reduce: "减仓",
  add: "加仓",
  stop_loss: "止损",
  take_profit: "止盈"
};

const INSTRUMENT_LABELS: Record<string, string> = {
  stock: "股票",
  option: "期权",
  future: "期货",
  bond: "债券",
  etf: "ETF",
  index: "指数"
};

export function ActionChainReview({
  actions,
  corrections,
  isCorrecting,
  onCorrect,
  onCorrectionSubmit,
  onCancel
}: ActionChainReviewProps) {
  const [editActions, setEditActions] = React.useState<ActionChainItem[]>([]);

  React.useEffect(() => {
    setEditActions(corrections || actions);
  }, [actions, corrections]);

  const displayActions = corrections || actions;
  const hasCorrection = Boolean(corrections);
  const hasUserCorrections = displayActions.some(a => a.userCorrected);

  const updateAction = (index: number, field: keyof ActionChainItem, value: string | number) => {
    setEditActions(prev => prev.map((a, i) =>
      i === index ? { ...a, [field]: value, userCorrected: true } : a
    ));
  };

  const addAction = () => {
    const newAction: ActionChainItem = {
      id: `action-${Date.now()}`,
      actionType: "buy",
      instrumentType: "stock",
      triggerCondition: "",
      targetPriceLow: "",
      targetPriceHigh: "",
      confidence: 0.5,
      status: "draft",
      userCorrected: true
    };
    setEditActions(prev => [...prev, newAction]);
  };

  const removeAction = (index: number) => {
    setEditActions(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = () => {
    const changed = JSON.stringify(editActions) !== JSON.stringify(actions);
    if (changed) {
      onCorrectionSubmit(editActions);
    } else {
      onCancel();
    }
  };

  return (
    <div className={cn(
      "rounded-xl border overflow-hidden transition-all",
      hasCorrection || hasUserCorrections
        ? "border-green-300 bg-green-50/30"
        : "border-[rgba(95,67,40,0.12)] bg-white/80"
    )}>
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-[rgba(95,67,40,0.08)] bg-[rgba(99,76,55,0.02)] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-morningstar-red" strokeWidth={1.5} />
          <h3 className="text-xs font-bold uppercase tracking-widest text-foreground/70">
            操作链
          </h3>
          <span className="text-[10px] font-medium text-foreground/40 bg-stone-100 px-2 py-0.5 rounded-full">
            {displayActions.length} 项
          </span>
        </div>

        <div className="flex items-center gap-2">
          {(hasCorrection || hasUserCorrections) && (
            <div className="flex items-center gap-1 text-[10px] text-green-700 bg-green-100 px-2 py-0.5 rounded-full">
              <Check className="w-3 h-3" />
              <span className="font-medium">已修正</span>
            </div>
          )}

          {!isCorrecting && (
            <button
              onClick={onCorrect}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-foreground/60 hover:text-morningstar-red hover:bg-red-50 border border-stone-200 hover:border-red-200 rounded-sm transition-all"
            >
              <Edit3 className="w-3 h-3" />
              修正
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {!isCorrecting ? (
          <div className="space-y-3">
            {displayActions.length === 0 ? (
              <div className="text-center py-4 text-foreground/40 text-sm">
                暂无操作链数据
              </div>
            ) : (
              displayActions.map((action) => (
                <div
                  key={action.id}
                  className={cn(
                    "p-3 rounded-lg border transition-all",
                    action.userCorrected
                      ? "border-green-200 bg-green-50/50"
                      : "border-[rgba(95,67,40,0.08)] bg-[rgba(99,76,55,0.02)]"
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-xs font-bold px-2 py-0.5 rounded",
                        action.actionType === "buy" || action.actionType === "add"
                          ? "bg-green-100 text-green-700"
                          : action.actionType === "sell" || action.actionType === "short"
                            ? "bg-red-100 text-red-700"
                            : "bg-stone-100 text-stone-700"
                      )}>
                        {ACTION_TYPE_LABELS[action.actionType] || action.actionType}
                      </span>

                      <span className="text-xs text-foreground/60">
                        {INSTRUMENT_LABELS[action.instrumentType] || action.instrumentType}
                      </span>

                      <span className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded",
                        action.status === "active"
                          ? "bg-green-100 text-green-700"
                          : action.status === "watch"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-stone-100 text-stone-600"
                      )}>
                        {action.status === "active" ? "生效" : action.status === "watch" ? "观察" : action.status === "draft" ? "草稿" : "未标注"}
                      </span>
                    </div>

                    <span className={cn(
                      "text-[10px] font-medium",
                      action.confidence == null ? "text-foreground/35"
                        : action.confidence >= 0.8 ? "text-green-600"
                        : action.confidence >= 0.5 ? "text-amber-600"
                          : "text-red-600"
                    )}>
                      {action.confidence == null ? "—" : `${(action.confidence * 100).toFixed(0)}%`}
                    </span>
                  </div>

                  {action.triggerCondition && (
                    <div className="text-xs text-foreground/70 mb-1">
                      触发条件: {action.triggerCondition}
                    </div>
                  )}

                  {(action.targetPriceLow || action.targetPriceHigh) && (
                    <div className="text-xs text-foreground/60">
                      目标价格: {action.targetPriceLow || "-"} ~ {action.targetPriceHigh || "-"}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {editActions.map((action, index) => (
              <div
                key={action.id}
                className={cn(
                  "p-4 rounded-lg border",
                  action.userCorrected
                    ? "border-green-300 bg-green-50/50"
                    : "border-stone-200 bg-white"
                )}
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-foreground/60">操作 #{index + 1}</span>
                  <button
                    onClick={() => removeAction(index)}
                    className="p-1 text-foreground/40 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      操作类型
                    </label>
                    <select
                      value={action.actionType}
                      onChange={(e) => updateAction(index, "actionType", e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-stone-300 rounded-sm focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none"
                    >
                      {Object.entries(ACTION_TYPE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      工具类型
                    </label>
                    <select
                      value={action.instrumentType}
                      onChange={(e) => updateAction(index, "instrumentType", e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-stone-300 rounded-sm focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none"
                    >
                      {Object.entries(INSTRUMENT_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="col-span-2">
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      触发条件
                    </label>
                    <input
                      type="text"
                      value={action.triggerCondition}
                      onChange={(e) => updateAction(index, "triggerCondition", e.target.value)}
                      placeholder="如: 股价突破 50 日均线"
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-stone-300 rounded-sm focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      目标价格 (低)
                    </label>
                    <input
                      type="text"
                      value={action.targetPriceLow || ""}
                      onChange={(e) => updateAction(index, "targetPriceLow", e.target.value)}
                      placeholder="最低目标价"
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-stone-300 rounded-sm focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      目标价格 (高)
                    </label>
                    <input
                      type="text"
                      value={action.targetPriceHigh || ""}
                      onChange={(e) => updateAction(index, "targetPriceHigh", e.target.value)}
                      placeholder="最高目标价"
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-stone-300 rounded-sm focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      置信度: {action.confidence == null ? "—" : `${(action.confidence * 100).toFixed(0)}%`}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={(action.confidence ?? 0.5) * 100}
                      onChange={(e) => updateAction(index, "confidence", parseInt(e.target.value) / 100)}
                      className="w-full accent-morningstar-red"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-medium text-foreground/50 mb-1">
                      状态
                    </label>
                    <select
                      value={action.status ?? "draft"}
                      onChange={(e) => updateAction(index, "status", e.target.value as "draft" | "active" | "watch")}
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-stone-300 rounded-sm focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none"
                    >
                      <option value="draft">草稿</option>
                      <option value="active">生效</option>
                      <option value="watch">观察</option>
                    </select>
                  </div>
                </div>
              </div>
            ))}

            <button
              onClick={addAction}
              className="w-full flex items-center justify-center gap-2 p-3 border-2 border-dashed border-stone-300 hover:border-morningstar-red text-foreground/50 hover:text-morningstar-red rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span className="text-sm font-medium">添加操作</span>
            </button>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-stone-200">
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
                确认修改
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}