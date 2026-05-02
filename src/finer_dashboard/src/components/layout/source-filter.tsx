"use client";

import React from "react";
import { ChevronDown, RefreshCw, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SourceGroup, SourceType } from "@/lib/contracts";

type SourceFilterProps = {
  sourceType: SourceType | "all";
  groups: SourceGroup[];
  selectedGroupId: string | null;
  onSourceTypeChange: (type: SourceType | "all") => void;
  onGroupChange: (groupId: string | null) => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
};

const SOURCE_TYPE_LABELS: Record<SourceType | "all", string> = {
  all: "全部来源",
  feishu: "飞书",
  notebooklm: "NotebookLM",
  local: "本地导入",
  wechat: "微信",
  bilibili: "B站",
  unknown: "未知",
};

export function SourceFilter({
  sourceType,
  groups,
  selectedGroupId,
  onSourceTypeChange,
  onGroupChange,
  onRefresh,
  isRefreshing = false,
}: SourceFilterProps) {
  const [showSourceDropdown, setShowSourceDropdown] = React.useState(false);
  const [showGroupDropdown, setShowGroupDropdown] = React.useState(false);

  // Filter groups by current source type
  const filteredGroups = sourceType === "all"
    ? groups
    : groups.filter((g) => g.type === sourceType);

  const selectedGroup = groups.find((g) => g.id === selectedGroupId);

  return (
    <div className="flex items-center gap-3">
      {/* Source Type Dropdown */}
      <div className="relative">
        <button
          onClick={() => setShowSourceDropdown(!showSourceDropdown)}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-bold uppercase tracking-wider border border-stone-200 bg-white rounded-sm hover:border-stone-300 transition-colors"
        >
          <span>{SOURCE_TYPE_LABELS[sourceType]}</span>
          <ChevronDown className="w-3 h-3" />
        </button>

        {showSourceDropdown && (
          <div className="absolute top-full left-0 mt-1 w-40 bg-white border border-stone-200 rounded-sm shadow-lg z-50">
            {(["all", "feishu", "notebooklm", "local"] as const).map((type) => (
              <button
                key={type}
                onClick={() => {
                  onSourceTypeChange(type);
                  onGroupChange(null); // Reset group when source type changes
                  setShowSourceDropdown(false);
                }}
                className={cn(
                  "w-full flex items-center justify-between px-3 py-2 text-xs font-medium hover:bg-stone-50 transition-colors",
                  sourceType === type ? "text-morningstar-red" : "text-foreground"
                )}
              >
                <span>{SOURCE_TYPE_LABELS[type]}</span>
                {sourceType === type && <Check className="w-3 h-3" />}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Group Dropdown (only show if there are groups for this source type) */}
      {filteredGroups.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setShowGroupDropdown(!showGroupDropdown)}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-bold uppercase tracking-wider border border-stone-200 bg-white rounded-sm hover:border-stone-300 transition-colors"
          >
            <span className="max-w-[120px] truncate">
              {selectedGroup ? selectedGroup.name : "全部群组"}
            </span>
            <ChevronDown className="w-3 h-3" />
          </button>

          {showGroupDropdown && (
            <div className="absolute top-full left-0 mt-1 w-56 bg-white border border-stone-200 rounded-sm shadow-lg z-50 max-h-64 overflow-y-auto finer-scrollbar">
              <button
                onClick={() => {
                  onGroupChange(null);
                  setShowGroupDropdown(false);
                }}
                className={cn(
                  "w-full flex items-center justify-between px-3 py-2 text-xs font-medium hover:bg-stone-50 transition-colors",
                  !selectedGroupId ? "text-morningstar-red" : "text-foreground"
                )}
              >
                <span>全部群组</span>
                {!selectedGroupId && <Check className="w-3 h-3" />}
              </button>

              {filteredGroups.map((group) => (
                <button
                  key={group.id}
                  onClick={() => {
                    onGroupChange(group.id);
                    setShowGroupDropdown(false);
                  }}
                  className={cn(
                    "w-full flex items-center justify-between px-3 py-2 text-xs font-medium hover:bg-stone-50 transition-colors",
                    selectedGroupId === group.id ? "text-morningstar-red" : "text-foreground"
                  )}
                >
                  <div className="flex flex-col items-start">
                    <span className="truncate max-w-[180px]">{group.name}</span>
                    <span className="text-[10px] text-stone-400">
                      {group.fileCount} 文件
                      {group.lastSync && ` · 最后同步 ${new Date(group.lastSync).toLocaleDateString()}`}
                    </span>
                  </div>
                  {selectedGroupId === group.id && <Check className="w-3 h-3 flex-shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Refresh Button */}
      {onRefresh && sourceType !== "all" && sourceType !== "local" && (
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold uppercase tracking-wider border rounded-sm transition-all",
            isRefreshing
              ? "border-stone-200 text-stone-400 bg-stone-50"
              : "border-morningstar-red/20 text-morningstar-red bg-morningstar-red/5 hover:bg-morningstar-red/10"
          )}
        >
          <RefreshCw className={cn("w-3 h-3", isRefreshing && "animate-spin")} />
          <span>{isRefreshing ? "刷新中..." : "刷新"}</span>
        </button>
      )}
    </div>
  );
}
