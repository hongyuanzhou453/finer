"use client";

import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle,
  ChevronRight,
  Layers,
  MessageSquare,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
  Target,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AssetFile, ReviewAction, ReviewDirection, ReviewPayload } from "@/lib/contracts";

const DIRECTION_OPTIONS: ReviewDirection[] = [
  "bullish",
  "bearish",
  "neutral",
  "watchlist",
  "risk_warning",
];

const ACTION_OPTIONS = [
  "watch",
  "long",
  "short",
  "close_long",
  "close_short",
  "buy_call",
  "sell_call",
  "buy_put",
  "sell_put",
];

const INSTRUMENT_OPTIONS = ["unspecified", "stock", "etf", "option", "index_future"];
const HORIZON_OPTIONS = ["intraday", "daily", "weekly", "swing", "long_term"];

function buildFallbackPayload(asset: AssetFile | null): ReviewPayload {
  return (
    asset?.reviewPayload ?? {
      ticker: "待确认标的",
      direction: "watchlist",
      timeHorizon: "weekly",
      rationale: "",
      evidenceText:
        asset?.summary ?? "当前资产还没有明确的候选事件，请先补充抽取结果或人工输入字段。",
      confidence: 0.55,
      tags: asset?.tags ?? [],
      ambiguityNotes: [
        "当前缺少结构化候选事件，请人工确认是否值得进入 review。",
        "如果观点只是在描述背景，不应勉强生成交易动作。",
      ],
      actionChain: [
        {
          id: "action-1",
          actionType: "watch",
          instrumentType: "unspecified",
          triggerCondition: "",
          targetPriceLow: "",
          targetPriceHigh: "",
          confidence: 0.55,
          status: "draft",
        },
      ],
    }
  );
}

export function AnnotationWorkbench({
  asset,
  onClose,
  onSaved,
}: {
  asset: AssetFile | null;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [payload, setPayload] = useState<ReviewPayload>(buildFallbackPayload(asset));
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving_draft" | "saving_approved" | "saved" | "error">("idle");
  const [saveMessage, setSaveMessage] = useState("");
  const [focusedValue, setFocusedValue] = useState<string>("");

  useEffect(() => {
    setPayload(buildFallbackPayload(asset));
    setReviewerNotes("");
    setSaveState("idle");
    setSaveMessage("");
    setFocusedValue("");
  }, [asset]);

  const updateField = <K extends keyof ReviewPayload>(field: K, value: ReviewPayload[K]) => {
    setPayload((current) => ({ ...current, [field]: value }));
    if (typeof value === "string") {
      setFocusedValue(value);
    }
  };

  const updateAction = (actionId: string, patch: Partial<ReviewAction>) => {
    setPayload((current) => ({
      ...current,
      actionChain: current.actionChain.map((action) =>
        action.id === actionId ? { ...action, ...patch } : action,
      ),
    }));
    const textVal = Object.values(patch).find(v => typeof v === "string");
    if (textVal) setFocusedValue(textVal as string);
  };

  const addAction = () => {
    setPayload((current) => ({
      ...current,
      actionChain: [
        ...current.actionChain,
        {
          id: `action-${current.actionChain.length + 1}`,
          actionType: "watch",
          instrumentType: "unspecified",
          triggerCondition: "",
          targetPriceLow: "",
          targetPriceHigh: "",
          confidence: 0.5,
          status: "draft",
        },
      ],
    }));
  };

  const removeAction = (actionId: string) => {
    setPayload((current) => ({
      ...current,
      actionChain:
        current.actionChain.length === 1
          ? current.actionChain
          : current.actionChain.filter((action) => action.id !== actionId),
    }));
  };

  const title = asset?.name ?? "未命名资产";
  const stageBadge = asset?.stageBadge ?? "F6";

  const saveReview = async (status: "pending" | "approved" | "rejected") => {
    if (!asset) return;

    setSaveState(status === "approved" ? "saving_approved" : "saving_draft");
    setSaveMessage("");

    try {
      const response = await fetch("/api/review", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          assetId: asset.id,
          contentId: asset.contentId,
          assetName: asset.name,
          status: status,
          reviewerNotes,
          payload,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to save review");
      }

      const result = await response.json();
      setSaveState("saved");
      setSaveMessage(
        result.approvedPath
          ? "Approved! Written to canonical store."
          : "Draft saved successfully."
      );
      
      onSaved?.();
      
      if (status === "approved") {
        setTimeout(() => onClose(), 800);
      }
    } catch (error) {
      console.error(error);
      setSaveState("error");
      setSaveMessage("Failed to save review. Please retry.");
    }
  };

  const renderEvidenceText = (text: string) => {
    if (!focusedValue || focusedValue.trim().length <= 1) return text;
    
    // safe regex split
    const safeFocus = focusedValue.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${safeFocus})`, 'gi'));
    return parts.map((part, i) => 
      part.toLowerCase() === focusedValue.toLowerCase() 
        ? <span key={i} className="bg-morningstar-red/20 text-morningstar-red font-bold rounded-sm px-1 border-b-[2px] border-morningstar-red/30 transition-all animate-in fade-in">{part}</span> 
        : part
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-[rgba(243,239,231,0.94)] flex flex-col animate-in fade-in slide-in-from-bottom-2 duration-300 backdrop-blur-md">
      <header className="h-20 bg-[rgba(255,252,247,0.88)] border-b border-[rgba(95,67,40,0.12)] flex items-center justify-between px-10 shadow-sm">
        <div className="flex items-center gap-6">
          <button
            onClick={onClose}
            className="p-2.5 hover:bg-stone-50 border border-transparent hover:border-stone-200 rounded-sm transition-all group"
          >
            <ArrowLeft className="w-5 h-5 text-foreground/50 group-hover:text-morningstar-red" strokeWidth={1.5} />
          </button>
          <div className="flex flex-col">
            <h2 className="text-[16px] font-bold tracking-tight">Review Workstation / 标注车间</h2>
            <div className="text-[11px] text-foreground/40 uppercase tracking-widest flex items-center gap-2 mt-1">
              <span className="text-morningstar-red font-extrabold flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-morningstar-red animate-pulse" /> {stageBadge}
              </span>
              <span className="text-stone-300">|</span>
              <span className="truncate max-w-[32rem]">{title}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 py-2">
          <button className="flex items-center gap-2 px-4 py-2 text-foreground/60 text-xs font-bold uppercase hover:bg-stone-100 transition-all rounded-sm border border-transparent hover:border-stone-200">
            <MessageSquare className="w-4 h-4" strokeWidth={1.5} />
            reviewer notes
          </button>
          <button
            onClick={() => saveReview("pending")}
            disabled={saveState.startsWith("saving")}
            className="flex items-center gap-2 px-6 py-2.5 rounded-sm bg-stone-100/80 text-foreground/80 border border-stone-200 text-xs font-bold uppercase hover:bg-stone-200 transition-all text-shadow-none"
          >
            <Save className="w-3.5 h-3.5 text-stone-500" strokeWidth={2} />
            {saveState === "saving_draft" ? "saving..." : "Save Draft"}
          </button>
          <button
            onClick={() => saveReview("approved")}
            disabled={saveState.startsWith("saving")}
            className="flex items-center gap-2 px-8 py-2.5 rounded-sm bg-stone-800 text-white text-xs font-bold uppercase shadow-sm hover:shadow-md hover:bg-stone-900 transition-all group border border-stone-900"
          >
            <CheckCircle className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" strokeWidth={2} />
            {saveState === "saving_approved" ? "Approving..." : "Approve & Close"}
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden max-w-[1720px] mx-auto w-full border-x border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.84)] shadow-2xl my-6 rounded-sm">
        <div className="w-[48%] border-r border-[rgba(95,67,40,0.12)] flex flex-col bg-[rgba(255,252,247,0.55)]">
          <div className="h-12 px-10 flex items-center bg-[rgba(99,76,55,0.06)] text-[11px] font-bold uppercase tracking-[0.15em] text-foreground/50 border-b border-[rgba(95,67,40,0.12)]">
            Source Evidence
          </div>
          <div className="flex-1 overflow-y-auto p-12 space-y-8 select-text finer-scrollbar">
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-[11px] text-foreground/40 font-bold uppercase tracking-widest flex items-center gap-2">
                  <Target className="w-3.5 h-3.5" strokeWidth={1.5} />
                  Content Identity
                </div>
                <div className="text-[11px] font-mono text-stone-600 font-bold px-2 py-0.5 bg-stone-100 border border-stone-200 rounded-sm shadow-sm">
                  {asset?.contentId ?? "unknown"}
                </div>
              </div>

              <div className="p-8 bg-white border border-[rgba(95,67,40,0.12)] rounded-sm shadow-sm relative transition-all">
                <div className="absolute top-0 flex w-full justify-center -mt-3">
                  <div className="bg-white border border-[rgba(95,67,40,0.12)] px-3 py-1 text-[10px] font-bold text-foreground/50 uppercase tracking-widest rounded-sm">
                    Evidence Text
                  </div>
                </div>
                <p className="text-[16px] leading-[1.9] text-foreground/80 font-medium mt-4 whitespace-pre-wrap transition-all">
                  {renderEvidenceText(payload.evidenceText)}
                </p>
              </div>
            </section>

            <section className="bg-white border border-[rgba(95,67,40,0.12)] rounded-sm p-8 shadow-sm">
              <div className="flex items-center gap-2 text-xs font-bold text-foreground uppercase tracking-widest mb-6 pb-4 border-b border-stone-100">
                <BrainCircuit className="w-4 h-4 text-morningstar-red" strokeWidth={2} />
                Provenance & Machine Clues
              </div>

              <div className="space-y-4 text-sm text-foreground/75 leading-relaxed">
                <div>
                  <span className="font-bold text-foreground">Summary:</span> {asset?.summary ?? "No machine summary available."}
                </div>
                <div className="flex items-center gap-3 text-xs font-bold text-foreground/60 uppercase tracking-widest flex-wrap mt-2">
                  <span className="px-3 py-1.5 bg-stone-100 rounded-sm border border-stone-200 text-stone-600 shadow-sm">
                    {asset?.creatorName ?? "unknown creator"}
                  </span>
                  <ChevronRight className="w-3.5 h-3.5 text-stone-300" />
                  <span className="px-3 py-1.5 bg-stone-100 rounded-sm border border-stone-200 text-stone-600 shadow-sm">
                    {asset?.sourcePlatform ?? "unknown source"}
                  </span>
                  <ChevronRight className="w-3.5 h-3.5 text-stone-300" />
                  <span className="px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-sm border border-emerald-200 shadow-sm">
                    {asset?.contentType ?? "candidate_event"}
                  </span>
                </div>
              </div>
            </section>

            <section className="bg-white border border-[rgba(95,67,40,0.12)] rounded-sm p-8 shadow-sm">
              <div className="text-xs font-bold text-foreground uppercase tracking-widest mb-5">
                Ambiguity Guardrails
              </div>
              <div className="space-y-3">
                {payload.ambiguityNotes.map((note) => (
                  <div
                    key={note}
                    className="rounded-sm border border-[rgba(159,29,34,0.08)] bg-[rgba(159,29,34,0.04)] px-4 py-3 text-[13px] leading-relaxed text-foreground/75"
                  >
                    {note}
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>

        <div className="w-[52%] flex flex-col bg-white">
          <div className="h-12 px-10 flex items-center justify-between bg-[rgba(99,76,55,0.06)] border-b border-[rgba(95,67,40,0.12)]">
            <span className="text-[11px] font-bold uppercase tracking-[0.15em] text-foreground/50">Field Correction & Intent Calibration</span>
            <button className="text-foreground/40 hover:text-foreground/80 transition-colors">
              <Settings2 className="w-4 h-4" strokeWidth={1.5} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-12 space-y-10 finer-scrollbar">
            <section className="grid grid-cols-2 gap-6">
              <div className="space-y-4">
                <label className="text-xs font-bold text-foreground/50 uppercase tracking-[0.1em] flex items-center gap-2">
                  <Target className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                  Ticker Identity
                </label>
                <input
                  type="text"
                  value={payload.ticker}
                  onChange={(event) => updateField("ticker", event.target.value)}
                  onFocus={() => { if(payload.ticker !== "待确认标的") setFocusedValue(payload.ticker); }}
                  onBlur={() => setFocusedValue("")}
                  className="w-full bg-stone-50 border border-stone-200 rounded-sm px-5 py-4 text-[13px] font-bold focus:bg-white focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none transition-all text-foreground"
                />
              </div>

              <div className="space-y-4">
                <label className="text-xs font-bold text-foreground/50 uppercase tracking-[0.1em] flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                  Time Horizon
                </label>
                <select
                  value={payload.timeHorizon}
                  onChange={(event) => updateField("timeHorizon", event.target.value)}
                  className="w-full bg-stone-50 border border-stone-200 rounded-sm px-5 py-4 text-[13px] font-bold focus:bg-white focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none transition-all text-foreground"
                >
                  {HORIZON_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </section>

            <section className="space-y-4">
              <label className="text-xs font-bold text-foreground/50 uppercase tracking-[0.1em] flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                Sentiment Bias
              </label>
              <div className="grid grid-cols-5 gap-2 rounded-sm p-1 bg-stone-100 border border-stone-200">
                {DIRECTION_OPTIONS.map((direction) => (
                  <button
                    key={direction}
                    onClick={() => updateField("direction", direction)}
                    className={cn(
                      "py-3 text-[11px] font-bold transition-all uppercase tracking-[0.12em] rounded-sm",
                      payload.direction === direction
                        ? "bg-white text-morningstar-red shadow-sm border border-stone-200/50"
                        : "text-foreground/50 hover:text-foreground/80 hover:bg-stone-50/50",
                    )}
                  >
                    {direction}
                  </button>
                ))}
              </div>
            </section>

            <section className="space-y-4">
              <label className="text-xs font-bold text-foreground/50 uppercase tracking-[0.1em] flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                Rationale Correction
              </label>
              <textarea
                value={payload.rationale}
                onChange={(event) => updateField("rationale", event.target.value)}
                onFocus={() => { if(payload.rationale.length > 3) setFocusedValue(payload.rationale); }}
                onBlur={() => setFocusedValue("")}
                rows={4}
                className="w-full bg-stone-50 border border-stone-200 rounded-sm px-5 py-4 text-[13px] font-medium focus:bg-white focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none transition-all text-foreground resize-none"
                placeholder="补充为什么这个观点成立、条件成立在哪里、哪里仍然存在歧义。"
              />
            </section>

            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-foreground/50 uppercase tracking-[0.1em] flex items-center gap-2">
                  <Layers className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
                  Action Chain Editor
                </label>
                <button
                  onClick={addAction}
                  className="inline-flex items-center gap-2 rounded-sm border border-[rgba(95,67,40,0.12)] bg-stone-50 px-3 py-2 text-[11px] font-bold uppercase tracking-[0.12em] text-foreground/70 hover:text-morningstar-red"
                >
                  <Plus className="w-3.5 h-3.5" strokeWidth={2} />
                  add action
                </button>
              </div>

              <div className="space-y-4">
                {payload.actionChain.map((action, index) => (
                  <div
                    key={action.id}
                    className="rounded-sm border border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.72)] p-5 shadow-sm"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/50">
                        Step {index + 1}
                      </div>
                      <button
                        onClick={() => removeAction(action.id)}
                        disabled={payload.actionChain.length === 1}
                        className="rounded-sm border border-transparent p-2 text-foreground/30 hover:text-red-500 hover:border-red-200 disabled:opacity-30"
                      >
                        <Trash2 className="w-4 h-4" strokeWidth={1.6} />
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <select
                        value={action.actionType}
                        onChange={(event) => updateAction(action.id, { actionType: event.target.value })}
                        className="bg-white border border-stone-200 rounded-sm px-4 py-3 text-[12px] font-bold text-foreground outline-none focus:border-morningstar-red"
                      >
                        {ACTION_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>

                      <select
                        value={action.instrumentType}
                        onChange={(event) => updateAction(action.id, { instrumentType: event.target.value })}
                        className="bg-white border border-stone-200 rounded-sm px-4 py-3 text-[12px] font-bold text-foreground outline-none focus:border-morningstar-red"
                      >
                        {INSTRUMENT_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>

                      <input
                        type="text"
                        value={action.triggerCondition}
                        onChange={(event) => updateAction(action.id, { triggerCondition: event.target.value })}
                        onFocus={() => { if(action.triggerCondition) setFocusedValue(action.triggerCondition); }}
                        onBlur={() => setFocusedValue("")}
                        className="bg-white border border-stone-200 rounded-sm px-4 py-3 text-[12px] font-medium text-foreground outline-none focus:border-morningstar-red col-span-2"
                        placeholder="Trigger condition (e.g. Breakout above 500)"
                      />

                      <input
                        type="text"
                        value={action.targetPriceLow}
                        onChange={(event) => updateAction(action.id, { targetPriceLow: event.target.value })}
                        onFocus={() => { if(action.targetPriceLow) setFocusedValue(action.targetPriceLow); }}
                        onBlur={() => setFocusedValue("")}
                        className="bg-white border border-stone-200 rounded-sm px-4 py-3 text-[12px] font-medium text-foreground outline-none focus:border-morningstar-red"
                        placeholder="Target low"
                      />

                      <input
                        type="text"
                        value={action.targetPriceHigh}
                        onChange={(event) => updateAction(action.id, { targetPriceHigh: event.target.value })}
                        onFocus={() => { if(action.targetPriceHigh) setFocusedValue(action.targetPriceHigh); }}
                        onBlur={() => setFocusedValue("")}
                        className="bg-white border border-stone-200 rounded-sm px-4 py-3 text-[12px] font-medium text-foreground outline-none focus:border-morningstar-red"
                        placeholder="Target high"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="grid grid-cols-[1.2fr,0.8fr] gap-6">
              <div className="space-y-4">
                <label className="text-xs font-bold text-foreground/50 uppercase tracking-[0.1em]">
                  Reviewer Notes
                </label>
                <textarea
                  value={reviewerNotes}
                  onChange={(event) => setReviewerNotes(event.target.value)}
                  rows={4}
                  className="w-full bg-stone-50 border border-stone-200 rounded-sm px-5 py-4 text-[13px] font-medium focus:bg-white focus:border-morningstar-red focus:ring-1 focus:ring-morningstar-red/20 outline-none transition-all text-foreground resize-none"
                  placeholder="记录你修改了什么、为什么改、哪些地方仍需二次确认。"
                />
                <div className="min-h-10">
                {saveMessage ? (
                  <div
                    className={cn(
                      "rounded-sm border px-4 py-3 text-[12px] font-bold shadow-sm animate-in zoom-in-95 duration-200",
                      saveState === "error"
                        ? "border-red-200 bg-red-50 text-red-600"
                        : "border-emerald-200 bg-emerald-50 text-emerald-700",
                    )}
                  >
                    {saveMessage}
                  </div>
                ) : null}
                </div>
              </div>

              <div className="rounded-sm border border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.74)] p-5 flex flex-col justify-start">
                <div className="flex items-center gap-4">
                  <ShieldCheck className="w-6 h-6 text-emerald-600" strokeWidth={1.5} />
                  <div className="flex flex-col">
                    <span className="text-[10px] text-foreground/40 font-bold uppercase tracking-widest">SYSTEM CONFIDENCE</span>
                    <span className="text-lg font-black text-foreground tabular-nums tracking-tighter">
                      {(payload.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-[rgba(95,67,40,0.12)] text-[12px] font-medium text-foreground/40 leading-relaxed">
                  The model extracted this logic payload from contextual evidence automatically. Review before marking as terminal Approved.
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
