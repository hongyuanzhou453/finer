"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Calendar,
  ChevronDown,
  Check,
  X,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ============================================
// 类型定义
// ============================================

export type TimeRange = "1W" | "1M" | "3M" | "1Y" | "ALL";

export type OpinionDirection = "bullish" | "bearish" | "neutral";

export interface TimelineFilters {
  timeRange: TimeRange;
  tickers: string[];
  directions: OpinionDirection[];
  kols: string[];
}

export interface TimelineFilterProps {
  filters: TimelineFilters;
  onChange: (filters: TimelineFilters) => void;
}

// ============================================
// 配置
// ============================================

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "1W", label: "1 周" },
  { value: "1M", label: "1 月" },
  { value: "3M", label: "3 月" },
  { value: "1Y", label: "1 年" },
  { value: "ALL", label: "全部" },
];

const DIRECTION_OPTIONS: { value: OpinionDirection; label: string; icon: React.ReactNode }[] = [
  { value: "bullish", label: "看多", icon: <TrendingUp className="w-3 h-3" /> },
  { value: "bearish", label: "看空", icon: <TrendingDown className="w-3 h-3" /> },
  { value: "neutral", label: "中性", icon: <Minus className="w-3 h-3" /> },
];

// ============================================
// 样式常量
// ============================================

const STYLES = {
  container: "flex items-center gap-4",
  dropdown: "relative",
  dropdownBtn: "flex items-center gap-2 px-3 py-2 rounded-sm bg-white border border-stone-200 hover:border-morningstar-red transition-colors text-xs font-medium",
  dropdownMenu: "absolute top-full left-0 mt-2 bg-white rounded-lg border border-stone-200 shadow-lg z-50 min-w-[160px] overflow-hidden",
  dropdownItem: "flex items-center gap-2 px-3 py-2 text-xs hover:bg-stone-50 cursor-pointer transition-colors",
  dropdownItemSelected: "bg-morningstar-red/5 text-morningstar-red",
  checkbox: "w-4 h-4 rounded border border-stone-300 flex items-center justify-center",
  checkboxChecked: "bg-morningstar-red border-morningstar-red text-white",
  tag: "inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide",
  tagRemove: "ml-1 hover:bg-white/20 rounded-full p-0.5 cursor-pointer",
} as const;

// ============================================
// 子组件: 时间范围选择器
// ============================================

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
}

function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = TIME_RANGE_OPTIONS.find(o => o.value === value);

  return (
    <div ref={ref} className={STYLES.dropdown}>
      <button
        onClick={() => setOpen(!open)}
        className={STYLES.dropdownBtn}
      >
        <Calendar className="w-3.5 h-3.5 text-foreground/50" />
        <span>{selected?.label}</span>
        <ChevronDown className="w-3 h-3 text-foreground/40" />
      </button>

      {open && (
        <div className={STYLES.dropdownMenu}>
          {TIME_RANGE_OPTIONS.map(option => (
            <button
              key={option.value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={cn(
                STYLES.dropdownItem,
                value === option.value && STYLES.dropdownItemSelected
              )}
            >
              {value === option.value && <Check className="w-3 h-3" />}
              <span className={value === option.value ? "" : "ml-5"}>
                {option.label}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================
// 子组件: 多选筛选器
// ============================================

interface MultiSelectProps {
  label: string;
  icon: React.ReactNode;
  options: { value: string; label: string; icon?: React.ReactNode }[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
}

function MultiSelect({ label, icon, options, value, onChange, placeholder }: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const toggle = (item: string) => {
    if (value.includes(item)) {
      onChange(value.filter(v => v !== item));
    } else {
      onChange([...value, item]);
    }
  };

  const displayText = value.length === 0
    ? placeholder || label
    : value.length === 1
      ? options.find(o => o.value === value[0])?.label
      : `${value.length} 项已选`;

  return (
    <div ref={ref} className={STYLES.dropdown}>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          STYLES.dropdownBtn,
          value.length > 0 && "border-morningstar-red/30 bg-morningstar-red/5"
        )}
      >
        {icon}
        <span>{displayText}</span>
        {value.length > 0 && (
          <span className="ml-1 rounded-full bg-morningstar-red text-white px-1.5 text-[9px]">
            {value.length}
          </span>
        )}
        <ChevronDown className="w-3 h-3 text-foreground/40" />
      </button>

      {open && (
        <div className={STYLES.dropdownMenu}>
          {options.map(option => {
            const isSelected = value.includes(option.value);
            return (
              <button
                key={option.value}
                onClick={() => toggle(option.value)}
                className={cn(
                  STYLES.dropdownItem,
                  isSelected && STYLES.dropdownItemSelected
                )}
              >
                <div className={cn(
                  STYLES.checkbox,
                  isSelected && STYLES.checkboxChecked
                )}>
                  {isSelected && <Check className="w-2.5 h-2.5" />}
                </div>
                {option.icon && <span className="text-foreground/50">{option.icon}</span>}
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================
// 子组件: 活动筛选标签
// ============================================

interface ActiveFilterTagsProps {
  filters: TimelineFilters;
  onRemoveTimeRange: () => void;
  onRemoveTicker: (ticker: string) => void;
  onRemoveDirection: (direction: OpinionDirection) => void;
  onRemoveKol: (kol: string) => void;
  onClearAll: () => void;
}

function ActiveFilterTags({
  filters,
  onRemoveTimeRange,
  onRemoveTicker,
  onRemoveDirection,
  onRemoveKol,
  onClearAll,
}: ActiveFilterTagsProps) {
  const hasFilters = filters.timeRange !== "1M" || filters.tickers.length > 0 || filters.directions.length > 0 || filters.kols.length > 0;

  if (!hasFilters) return null;

  return (
    <div className="flex items-center gap-2 pl-4 border-l border-stone-200">
      <div className="flex items-center gap-1.5 flex-wrap">
        {filters.timeRange !== "1M" && (
          <span className={cn(STYLES.tag, "bg-blue-50 text-blue-600 border border-blue-200")}>
            {TIME_RANGE_OPTIONS.find(o => o.value === filters.timeRange)?.label}
            <button onClick={onRemoveTimeRange} className={STYLES.tagRemove}>
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        )}

        {filters.tickers.map(ticker => (
          <span key={ticker} className={cn(STYLES.tag, "bg-purple-50 text-purple-600 border border-purple-200")}>
            {ticker}
            <button onClick={() => onRemoveTicker(ticker)} className={STYLES.tagRemove}>
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}

        {filters.directions.map(dir => (
          <span key={dir} className={cn(
            STYLES.tag,
            dir === "bullish" && "bg-[color-mix(in_srgb,var(--chart-up)_8%,transparent)] text-[color:var(--chart-up)] border border-[color-mix(in_srgb,var(--chart-up)_28%,transparent)]",
            dir === "bearish" && "bg-[color-mix(in_srgb,var(--chart-down)_10%,transparent)] text-[color:var(--chart-down)] border border-[color-mix(in_srgb,var(--chart-down)_28%,transparent)]",
            dir === "neutral" && "bg-stone-100 text-stone-600 border border-stone-300"
          )}>
            {DIRECTION_OPTIONS.find(o => o.value === dir)?.label}
            <button onClick={() => onRemoveDirection(dir)} className={STYLES.tagRemove}>
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}

        {filters.kols.map(kol => (
          <span key={kol} className={cn(STYLES.tag, "bg-amber-50 text-amber-600 border border-amber-200")}>
            {kol}
            <button onClick={() => onRemoveKol(kol)} className={STYLES.tagRemove}>
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}
      </div>

      <button
        onClick={onClearAll}
        className="text-[10px] text-foreground/40 hover:text-morningstar-red underline"
      >
        清除全部
      </button>
    </div>
  );
}

// ============================================
// 主组件
// ============================================

export function TimelineFilter({ filters, onChange }: TimelineFilterProps) {
  // 模拟数据 - 实际应从 API 获取
  const [availableTickers, setAvailableTickers] = useState<string[]>([]);
  const [availableKols, setAvailableKols] = useState<string[]>([]);
  // 加载可用选项
  useEffect(() => {
    fetch("/api/opinions/meta")
      .then(res => res.json())
      .then(data => {
        setAvailableTickers(data.tickers || []);
        setAvailableKols(data.kols || []);
      })
      .catch(err => {
        console.error("Failed to load meta:", err);
        // 使用模拟数据
        setAvailableTickers(["NVDA", "AAPL", "TSLA", "AMD", "MSFT"]);
        setAvailableKols(["分析师张三", "李四", "王五", "财通证券"]);
      });
  }, []);

  // 更新器
  const updateTimeRange = (timeRange: TimeRange) => {
    onChange({ ...filters, timeRange });
  };

  const updateTickers = (tickers: string[]) => {
    onChange({ ...filters, tickers: tickers as string[] });
  };

  const updateDirections = (directions: string[]) => {
    onChange({ ...filters, directions: directions as OpinionDirection[] });
  };

  const updateKols = (kols: string[]) => {
    onChange({ ...filters, kols });
  };

  // 移除器
  const removeTimeRange = () => onChange({ ...filters, timeRange: "1M" });
  const removeTicker = (ticker: string) => onChange({ ...filters, tickers: filters.tickers.filter(t => t !== ticker) });
  const removeDirection = (dir: OpinionDirection) => onChange({ ...filters, directions: filters.directions.filter(d => d !== dir) });
  const removeKol = (kol: string) => onChange({ ...filters, kols: filters.kols.filter(k => k !== kol) });
  const clearAll = () => onChange({ timeRange: "1M", tickers: [], directions: [], kols: [] });

  return (
    <div className={STYLES.container}>
      {/* 时间范围 */}
      <TimeRangeSelector
        value={filters.timeRange}
        onChange={updateTimeRange}
      />

      {/* 标的筛选 */}
      <MultiSelect
        label="标的"
        icon={<span className="text-xs font-bold text-foreground/50">T</span>}
        options={availableTickers.map(t => ({ value: t, label: t }))}
        value={filters.tickers}
        onChange={updateTickers}
        placeholder="全部标的"
      />

      {/* 方向筛选 */}
      <MultiSelect
        label="方向"
        icon={<span className="text-xs font-bold text-foreground/50">D</span>}
        options={DIRECTION_OPTIONS.map(d => ({ value: d.value, label: d.label, icon: d.icon }))}
        value={filters.directions}
        onChange={updateDirections}
        placeholder="全部方向"
      />

      {/* KOL 筛选 */}
      <MultiSelect
        label="KOL"
        icon={<span className="text-xs font-bold text-foreground/50">K</span>}
        options={availableKols.map(k => ({ value: k, label: k }))}
        value={filters.kols}
        onChange={updateKols}
        placeholder="全部来源"
      />

      {/* 活动筛选标签 */}
      <ActiveFilterTags
        filters={filters}
        onRemoveTimeRange={removeTimeRange}
        onRemoveTicker={removeTicker}
        onRemoveDirection={removeDirection}
        onRemoveKol={removeKol}
        onClearAll={clearAll}
      />
    </div>
  );
}

export default TimelineFilter;
