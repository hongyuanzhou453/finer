/**
 * 站点级共享排版原子（/records · /kol-check 共用）。
 *
 * 此前 kol-check/primitives 与 records/primitives 各有一份 DIRECTION_META
 * 与百分数格式化器，且负号写法不一致（records 用 U+2212「−」，kol-check 用
 * ASCII「-」）——两页若同屏并置，同一个数字会出现两种负号。本模块是唯一
 * 真相源，两个目录的 primitives 只做再导出与领域专属件。
 *
 * Institutional discipline: mono tabular numbers; red = up / win, green =
 * down / loss（全站中国惯例，--chart-up / --chart-down）。
 */
import React from "react";

// ---- direction ---------------------------------------------------------------

/** 全站方向超集；records 的 RowDirection（3 值）是它的子集，可直接传入。 */
export type SiteDirection =
  | "bullish"
  | "bearish"
  | "neutral"
  | "watchlist"
  | "risk_warning";

export const DIRECTION_META: Record<
  SiteDirection,
  { label: string; color: string }
> = {
  bullish: { label: "看多", color: "var(--chart-up)" },
  bearish: { label: "看空", color: "var(--chart-down)" },
  neutral: { label: "中性", color: "#8a8278" },
  watchlist: { label: "观察", color: "var(--accent-gold)" },
  risk_warning: { label: "风险", color: "var(--accent-teal)" },
};

// ---- formatters -------------------------------------------------------------

/** 0.4624 → "46.2%"（无符号，用于比率）。 */
export function fmtRate(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/**
 * 0.0418 → "+4.2%"，-0.0268 → "−2.7%"（带符号，用于收益）。
 * 负号统一 U+2212「−」：与「+」等宽，密排表格里对得齐——这是本次合并
 * 拍板的站点级约定（此前 kol-check 走 toFixed 的 ASCII 连字符）。
 */
export function fmtSignedPct(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${(Math.abs(value) * 100).toFixed(digits)}%`;
}

/** ISO timestamp → "YYYY-MM-DD"。 */
export function fmtDate(iso: string): string {
  return iso.slice(0, 10);
}

export function fmtConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 收益值配色：正=红、负=绿、零=中性墨。 */
export function returnColor(value: number): string {
  if (value > 0) return "var(--chart-up)";
  if (value < 0) return "var(--chart-down)";
  return "var(--ink-soft)";
}

// ---- section header (editorial "01 / TITLE" rule) ---------------------------

/**
 * 编号章节头。flex-wrap + nowrap 标题：窄屏时右注整体换行，
 * 标题不会被拆成两行（与 dashboard crd/primitives 同款修复）。
 */
export function SectionHeader({
  index,
  title,
  en,
  note,
}: {
  index?: string;
  title: string;
  en: string;
  note?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 border-b border-[var(--foreground)] pb-2">
      <div className="flex items-baseline gap-3">
        {index ? (
          <span className="tabular-nums text-sm font-semibold text-[var(--accent-gold)]">
            {index}
          </span>
        ) : null}
        <h2 className="whitespace-nowrap text-lg leading-none text-[var(--foreground)]">
          {title}
        </h2>
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--ink-soft)]">
          {en}
        </span>
      </div>
      {note ? (
        <div className="text-[11px] leading-tight text-[var(--ink-soft)] sm:text-right">
          {note}
        </div>
      ) : null}
    </div>
  );
}

// ---- direction tag ----------------------------------------------------------

export function DirectionTag({
  direction,
  size = "sm",
}: {
  direction: SiteDirection;
  size?: "sm" | "xs";
}) {
  const meta = DIRECTION_META[direction];
  const pad = size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm font-medium ${pad}`}
      style={{
        color: meta.color,
        backgroundColor: `color-mix(in srgb, ${meta.color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${meta.color} 32%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
    </span>
  );
}

// ---- sufficiency tier badge -------------------------------------------------

/** 与 demo/records/types.ts::SufficiencyTier 同值集（结构兼容，无需依赖）。 */
export type SiteSufficiencyTier = "sufficient" | "provisional" | "insufficient";

const TIER_META: Record<SiteSufficiencyTier, { label: string; color: string }> = {
  sufficient: { label: "样本充分", color: "var(--accent-teal)" },
  provisional: { label: "临界样本", color: "var(--accent-gold)" },
  insufficient: { label: "样本不足", color: "#8a8278" },
};

/** 中性配色：档位说的是「能不能读」，不是「好不好」。 */
export function TierBadge({ tier }: { tier: SiteSufficiencyTier }) {
  const meta = TIER_META[tier];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
      style={{
        color: meta.color,
        backgroundColor: `color-mix(in srgb, ${meta.color} 10%, transparent)`,
        border: `1px solid color-mix(in srgb, ${meta.color} 30%, transparent)`,
      }}
    >
      {meta.label}
    </span>
  );
}

// ---- confidence meter -------------------------------------------------------

/** 置信度不是方向——填充固定 accent-gold，不用红绿。 */
export function ConfidenceMeter({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-12 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.round(value * 100)}%`,
            backgroundColor: "var(--accent-gold)",
          }}
        />
      </div>
      <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
        {fmtConfidence(value)}
      </span>
    </div>
  );
}
