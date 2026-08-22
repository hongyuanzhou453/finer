"use client";

import React from "react";
import { Search, Bell, LayoutGrid, List, Info } from "lucide-react";
import { UploadButton } from "./upload-button";

interface MainBoardProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  tier?: string;
  stageLabel?: string;
  importLabel?: string;
  searchPlaceholder?: string;
  onRefresh?: () => void;
  viewMode?: "grid" | "list";
  onViewModeChange?: (mode: "grid"|"list") => void;
  isInspectorOpen?: boolean;
  onToggleInspector?: () => void;
  filterComponent?: React.ReactNode;
}

export function MainBoard({
  children,
  title = "探索器",
  subtitle = "围绕证据、事件与结果组织你的研究流程。",
  tier = "F1",
  stageLabel = "WORKFLOW",
  importLabel = "Import Asset",
  searchPlaceholder = "搜索资产或事件...",
  onRefresh,
  viewMode = "grid",
  onViewModeChange,
  isInspectorOpen = true,
  onToggleInspector,
  filterComponent,
}: MainBoardProps) {
  return (
    <main className="flex-1 min-w-0 flex flex-col h-full bg-transparent relative overflow-hidden">
      {/* Header */}
      <header className="min-h-20 flex flex-wrap items-center justify-between gap-4 px-8 py-5 bg-[rgba(255,252,247,0.72)] border-b border-[rgba(95,67,40,0.12)] shadow-sm z-10 backdrop-blur-xl">
        <div className="flex flex-1 min-w-[min(100%,34rem)] flex-wrap items-center gap-5">
          <div className="min-w-[16rem] flex-1 space-y-1">
            <div className="flex items-center gap-3">
              <span className="shrink-0 px-2.5 py-1 text-[10px] font-bold tracking-[0.2em] uppercase rounded-full border border-[color-mix(in_srgb,var(--morningstar-red)_18%,transparent)] bg-[color-mix(in_srgb,var(--morningstar-red)_7%,transparent)] text-morningstar-red">
                {stageLabel}
              </span>
              <h2 className="min-w-0 text-[18px] font-bold text-foreground/90 tracking-tight">{title}</h2>
            </div>
            <p className="text-[12px] text-[var(--ink-soft)] max-w-2xl leading-relaxed">{subtitle}</p>
          </div>
          <div className="hidden h-10 w-px bg-[rgba(95,67,40,0.14)] lg:block" />
          <div className="flex min-w-[16rem] max-w-[28rem] flex-1 items-center bg-[rgba(255,255,255,0.6)] border border-[rgba(95,67,40,0.12)] rounded-sm px-4 py-2.5 gap-3 group focus-within:border-morningstar-red/50 focus-within:ring-2 focus-within:ring-morningstar-red/10 transition-all shadow-inner">
            <Search className="w-4 h-4 shrink-0 text-foreground/40 group-focus-within:text-morningstar-red transition-colors" strokeWidth={1.5} />
            <input
              type="text"
              placeholder={searchPlaceholder}
              className="min-w-0 w-full bg-transparent border-none outline-none text-[13px] placeholder:text-foreground/30 font-medium text-foreground"
            />
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-4">
          {!isInspectorOpen && (
            <button
              onClick={onToggleInspector}
              className="p-2.5 hover:bg-red-50 text-stone-400 hover:text-morningstar-red rounded-sm transition-colors border border-transparent hover:border-morningstar-red/20 flex items-center gap-2"
              title="Open Inspector"
            >
              <Info className="w-5 h-5" strokeWidth={1.5} />
              <span className="text-[10px] font-bold uppercase tracking-widest hidden md:inline">Inspect</span>
            </button>
          )}
          <button className="p-2.5 hover:bg-stone-50 rounded-sm transition-colors relative border border-transparent hover:border-stone-200">
            <Bell className="w-5 h-5 text-foreground/50" strokeWidth={1.5} />
            <span className="absolute top-2.5 right-2.5 w-2 h-2 border border-white bg-morningstar-red rounded-full" />
          </button>
          <div className="h-10 w-10 rounded-sm bg-morningstar-red flex items-center justify-center text-white text-xs font-bold shadow-md hover:shadow-lg transition-shadow cursor-pointer">
            ZH
          </div>
        </div>
      </header>

      {/* Toolbar */}
      <div className="min-h-16 flex flex-wrap items-center justify-between gap-3 px-8 py-3 bg-[rgba(255,252,247,0.62)] border-b border-[rgba(95,67,40,0.12)] z-0 backdrop-blur-xl">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {/* Source Filter Component */}
          {filterComponent}

          {filterComponent && <div className="hidden h-6 w-[1px] bg-stone-200 md:block" />}

          <div className="flex shrink-0 items-center bg-[rgba(99,76,55,0.07)] p-1 rounded-sm border border-[rgba(95,67,40,0.12)]">
            <button
              onClick={() => onViewModeChange?.("grid")}
              className={`py-1 px-4 rounded-sm text-xs font-bold flex items-center gap-2 transition-colors ${viewMode === 'grid' ? 'bg-white shadow-sm text-foreground' : 'text-foreground/50 hover:bg-stone-200/50'}`}
            >
              <LayoutGrid className="w-3.5 h-3.5" strokeWidth={1.5} />
              GRID
            </button>
            <button
              onClick={() => onViewModeChange?.("list")}
              className={`py-1 px-4 rounded-sm text-xs font-bold flex items-center gap-2 transition-colors ${viewMode === 'list' ? 'bg-white shadow-sm text-foreground' : 'text-foreground/50 hover:bg-stone-200/50'}`}
            >
              <List className="w-3.5 h-3.5" strokeWidth={1.5} />
              LIST
            </button>
          </div>

          <div className="hidden h-6 w-[1px] bg-stone-200 md:block" />

          <UploadButton
            currentTier={tier}
            label={importLabel}
            onUploadSuccess={onRefresh || (() => {})}
          />
        </div>

        <div className="ml-auto shrink-0 text-[11px] text-foreground/40 font-bold tracking-[0.15em] uppercase flex items-center">
          WORKSPACE <span className="mx-2 text-stone-300">/</span> PIPELINE BADGE <span className="text-morningstar-red font-extrabold px-1.5">{tier}</span>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto finer-scrollbar p-10">
        <div className="max-w-7xl mx-auto">
          {children}
        </div>
      </div>
    </main>
  );
}
