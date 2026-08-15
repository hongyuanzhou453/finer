/**
 * CRD 消费面共享排版原子（/discover · /ticker · 后续 /records）。
 *
 * 机构研报的版面纪律：硬墨线、等宽数字、编号章节、报头横规、密排表格。
 * 借的是版式，不是信息模型——本模块刻意**不提供**方向箭头、涨跌 delta、
 * 排名徽章、强弱评分条这类器件：它们把历史计数读成趋势外推，撞 2026-08-02
 * 定位红线（CLAUDE.md「定位前提」§1/§3）。
 *
 * 色彩沿用中国惯例：红=看多/上涨，绿=看空/下跌（globals.css --chart-up/-down）。
 * 但**效力类图形（WilsonBar / TierBadge）一律中性墨色**——命中率不是方向，
 * 给它上红绿就是在说「这家更好」，而跨期持续性检验并不支持这个读法。
 */

import React from "react";
import type { ConsensusDirection, SampleTier } from "@/lib/contracts";

// ---- formatters -------------------------------------------------------------

/** 比率 → 百分数；null 一律渲染为破折号，**不得填 0**（缺失必须留白）。 */
export function fmtPct(value?: number | null, digits = 1): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

/** 带符号的收益率，供收益列使用。 */
export function fmtSignedPct(value?: number | null, digits = 2): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

export function fmtDate(iso?: string | null): string {
  return iso ? iso.slice(0, 10) : "—";
}

// ---- masthead（报头横规）-----------------------------------------------------

/**
 * 页头：眉标 + 主标题 + 元信息行 + 2px 墨线。
 * meta 行承载口径、快照时间、样本量这类「这一页是什么」的事实。
 */
export function Masthead({
  eyebrow,
  title,
  suffix,
  meta,
  lede,
}: {
  eyebrow: string;
  title: React.ReactNode;
  suffix?: React.ReactNode;
  meta?: React.ReactNode[];
  lede?: React.ReactNode;
}) {
  return (
    <header className="border-b-2 border-[var(--foreground)] pb-3">
      <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-[var(--accent-gold)]">
        {eyebrow}
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-[26px] leading-none sm:text-[30px]">{title}</h1>
        {suffix ? (
          <span className="text-sm text-[var(--ink-soft)]">{suffix}</span>
        ) : null}
      </div>
      {meta && meta.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-[var(--ink-soft)]">
          {meta.map((m, i) => (
            <React.Fragment key={i}>
              {i > 0 ? <span aria-hidden>·</span> : null}
              <span className="tabular-nums">{m}</span>
            </React.Fragment>
          ))}
        </div>
      ) : null}
      {lede ? (
        <p className="mt-2.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--ink-soft)]">
          {lede}
        </p>
      ) : null}
    </header>
  );
}

// ---- section header（编号章节 01 / 中文 / EN kicker）--------------------------

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
    // flex-wrap + nowrap 标题：窄屏时右侧注记整体换行，标题不会被拆成「口径概/览」。
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

// ---- metric tile -------------------------------------------------------------

/**
 * 指标磁贴。**只有绝对值，没有 delta、没有趋势箭头**——这是有意的，不是遗漏：
 * 底座是冻结的静态档案，任何环比符号都会被读成「还在往这个方向走」。
 */
export function MetricTile({
  value,
  label,
  sub,
  tone,
}: {
  value: React.ReactNode;
  label: string;
  sub?: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="editorial-panel rounded-sm px-3.5 py-3">
      <div
        className="tabular-nums text-2xl font-semibold leading-none"
        style={{ color: tone ?? "var(--foreground)" }}
      >
        {value}
      </div>
      <div className="mt-1.5 text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
        {label}
      </div>
      {sub ? (
        <div className="mt-0.5 tabular-nums text-[11px] text-[var(--ink-soft)]">
          {sub}
        </div>
      ) : null}
    </div>
  );
}

// ---- Wilson 区间条（把 CRD-2 纪律画出来）-------------------------------------

/**
 * 点估计 + 95% Wilson 区间的水平区间条。
 *
 * CLAUDE.md §3：「超额列保留但强制并排 95% 区间」。此前区间只以文字并排，
 * 画成区间条后，「区间有多宽 / 是否覆盖参照线」变成一眼可读的事实——
 * 这正是本产品要传达的东西：样本不足以区分。
 *
 * 刻意中性墨色，不用红绿：命中率不是方向，上色就是在暗示优劣。
 * 调用方必须先判 display_policy !== "count_only"，本组件不自行放行。
 */
export function WilsonBar({
  point,
  low,
  high,
  reference,
  referenceLabel = "市场预期",
}: {
  point?: number | null;
  low?: number | null;
  high?: number | null;
  reference?: number | null;
  referenceLabel?: string;
}) {
  if (point == null) return null;
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const lo = clamp(low ?? point);
  const hi = clamp(high ?? point);
  const p = clamp(point);

  return (
    <div className="mt-2.5">
      <div className="relative h-5">
        {/* 轨道 0–100% */}
        <div className="absolute inset-x-0 top-2 h-1 rounded-sm bg-[var(--surface-muted)]" />
        {/* 95% 区间带 */}
        <div
          className="absolute top-2 h-1 rounded-sm"
          style={{
            left: `${lo * 100}%`,
            width: `${Math.max(hi - lo, 0.004) * 100}%`,
            backgroundColor:
              "color-mix(in srgb, var(--accent-gold) 55%, transparent)",
          }}
        />
        {/* 区间端点须 */}
        {[lo, hi].map((v, i) => (
          <div
            key={i}
            className="absolute top-[3px] h-[14px] w-px"
            style={{
              left: `${v * 100}%`,
              backgroundColor:
                "color-mix(in srgb, var(--accent-gold) 80%, transparent)",
            }}
          />
        ))}
        {/* 参照线：市场预期基准率 */}
        {reference != null ? (
          <div
            className="absolute top-0 h-5 border-l border-dashed border-[var(--ink-soft)]"
            style={{ left: `${clamp(reference) * 100}%` }}
            title={`${referenceLabel} ${fmtPct(reference)}`}
          />
        ) : null}
        {/* 点估计 */}
        <div
          className="absolute top-[1px] h-[18px] w-[2px] bg-[var(--foreground)]"
          style={{ left: `${p * 100}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] tabular-nums text-[var(--ink-soft)]">
        <span>0%</span>
        <span>
          95% 区间 {fmtPct(low, 0)}–{fmtPct(high, 0)}
          {reference != null
            ? ` · ${referenceLabel} ${fmtPct(reference, 0)}`
            : ""}
        </span>
        <span>100%</span>
      </div>
    </div>
  );
}

// ---- 构成条（100% 堆叠，只编码计数）------------------------------------------

export interface RibbonSegment {
  key: string;
  label: string;
  count: number;
  color: string;
}

/**
 * 计数构成条：方向票、市场分布这类「由什么组成」的事实。
 * 图例只标**计数**不标百分比——几何形状已经表达了份额，再写一个比率
 * 会让它看起来像一个受效力门约束的统计量。
 */
export function CompositionRibbon({
  segments,
  emptyHint = "无记录",
}: {
  segments: RibbonSegment[];
  emptyHint?: string;
}) {
  const total = segments.reduce((s, x) => s + x.count, 0);
  if (total <= 0) {
    return (
      <div className="mt-1 text-[11px] text-[var(--ink-soft)]">{emptyHint}</div>
    );
  }
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-sm">
        {segments
          .filter((s) => s.count > 0)
          .map((s, i, arr) => (
            <div
              key={s.key}
              style={{
                width: `${(s.count / total) * 100}%`,
                backgroundColor: s.color,
                // 相邻墨阶靠得太近会糊成一条；发丝分隔线让分段边界始终可数。
                boxShadow:
                  i < arr.length - 1
                    ? "inset -1px 0 0 var(--surface-strong)"
                    : undefined,
              }}
              title={`${s.label} ${s.count}`}
            />
          ))}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {segments
          .filter((s) => s.count > 0)
          .map((s) => (
            <span
              key={s.key}
              className="flex items-center gap-1 text-[11px] text-[var(--ink-soft)]"
            >
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-[1px]"
                style={{ backgroundColor: s.color }}
              />
              {s.label}
              <span className="tabular-nums text-[var(--foreground)]">
                {s.count}
              </span>
            </span>
          ))}
      </div>
    </div>
  );
}

// ---- 区间条（目标价 min / median / max）--------------------------------------

/** 目标价离散度：min–max 轨道 + 中位刻度。纯粹是已显示数字的再编码。 */
export function SpreadBar({
  min,
  median,
  max,
}: {
  min: number;
  median: number;
  max: number;
}) {
  const span = max - min;
  const at = (v: number) => (span > 0 ? ((v - min) / span) * 100 : 50);
  return (
    <div className="mt-2 h-4">
      <div className="relative h-4">
        <div className="absolute inset-x-0 top-[7px] h-[2px] bg-[color-mix(in_srgb,var(--foreground)_28%,transparent)]" />
        {[min, max].map((v, i) => (
          <div
            key={i}
            className="absolute top-[2px] h-[12px] w-px bg-[var(--foreground)]"
            style={{ left: `calc(${at(v)}% - ${i === 0 ? 0 : 1}px)` }}
          />
        ))}
        <div
          className="absolute top-0 h-4 w-[2px] bg-[var(--accent-gold)]"
          style={{ left: `calc(${at(median)}% - 1px)` }}
          title={`中位 ${median.toLocaleString()}`}
        />
      </div>
    </div>
  );
}

// ---- 方向标签（共识口径，四值）----------------------------------------------

export const CONSENSUS_DIRECTION_META: Record<
  ConsensusDirection,
  { label: string; color: string }
> = {
  bullish: { label: "看多", color: "var(--chart-up)" },
  bearish: { label: "看空", color: "var(--chart-down)" },
  neutral: { label: "中性", color: "#8a8278" },
  mixed: { label: "混合", color: "var(--accent-gold)" },
};

export function DirectionTag({
  direction,
  size = "sm",
}: {
  direction: ConsensusDirection;
  size?: "sm" | "xs";
}) {
  const meta =
    CONSENSUS_DIRECTION_META[direction] ?? CONSENSUS_DIRECTION_META.mixed;
  const pad =
    size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]";
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

// ---- 样本档位徽章 ------------------------------------------------------------

const TIER_META: Record<SampleTier, { label: string; color: string }> = {
  sufficient: { label: "样本充分", color: "var(--accent-teal)" },
  provisional: { label: "样本有限", color: "var(--accent-gold)" },
  insufficient: { label: "样本不足", color: "#8a8278" },
};

/** 中性配色：档位说的是「能不能读」，不是「好不好」。 */
export function TierBadge({ tier }: { tier: SampleTier }) {
  const meta = TIER_META[tier] ?? TIER_META.insufficient;
  return (
    <span
      className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium tracking-wide"
      style={{
        color: meta.color,
        border: `1px solid color-mix(in srgb, ${meta.color} 34%, transparent)`,
        backgroundColor: `color-mix(in srgb, ${meta.color} 10%, transparent)`,
      }}
    >
      {meta.label}
    </span>
  );
}

// ---- 声明块 ------------------------------------------------------------------

/**
 * 口径声明 / 边界声明。**默认渲染**，只在后端明确许可时由调用方撤下——
 * 声明消失是最坏的失效方向（significance.py 事故判例）。
 */
export function Disclosure({
  title,
  children,
  tone = "neutral",
}: {
  title: string;
  children: React.ReactNode;
  tone?: "neutral" | "warn";
}) {
  const accent = tone === "warn" ? "var(--accent-gold)" : "var(--foreground)";
  return (
    <div
      className="rounded-sm border border-[var(--table-border)] border-l-[3px] bg-[var(--surface-muted)] px-3 py-2 text-[11px] leading-relaxed text-[var(--foreground)]"
      style={{ borderLeftColor: accent }}
    >
      <span className="font-semibold">{title}</span>
      <span className="text-[var(--ink-soft)]"> {children}</span>
    </div>
  );
}

/** 逐条口径 note——CRD-2 要求逐条展示，不折叠。 */
export function NoteList({ notes }: { notes: string[] }) {
  if (!notes.length) return null;
  return (
    <ul className="space-y-1">
      {notes.map((n) => (
        <li
          key={n}
          className="flex gap-1.5 text-[11px] leading-5 text-[var(--ink-soft)]"
        >
          <span aria-hidden className="text-[var(--accent-gold)]">
            ·
          </span>
          <span>{n}</span>
        </li>
      ))}
    </ul>
  );
}

// ---- 留白格 ------------------------------------------------------------------

/**
 * 样本不足时的显式留白。**不得填 0、不得填占位数字**——一个系统主动说
 * 「我不知道」是这个产品最强的差异化，不是需要藏起来的缺陷。
 */
export function BlankCell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2.5 rounded-sm border border-dashed border-[var(--table-border)] px-3 py-2.5 text-[11px] leading-relaxed text-[var(--ink-soft)]">
      {children}
    </div>
  );
}

// ---- 状态条（陈旧度等页面级状态）--------------------------------------------

export function StatusBanner({
  tone,
  children,
}: {
  tone: "current" | "aging" | "stale" | "archival";
  children: React.ReactNode;
}) {
  const color =
    tone === "current"
      ? "var(--accent-teal)"
      : tone === "aging"
        ? "var(--accent-gold)"
        : tone === "stale"
          ? "var(--morningstar-red)"
          : "#8a8278";
  return (
    <div
      className="rounded-sm border-l-[3px] bg-[var(--surface-muted)] px-3 py-2 text-[12px] leading-relaxed"
      style={{ borderLeftColor: color }}
    >
      {children}
    </div>
  );
}

// ---- 加载 / 错误 -------------------------------------------------------------

export function LoadingRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-10 flex items-center gap-2 text-[13px] text-[var(--ink-soft)]">
      <span
        aria-hidden
        className="inline-block h-3 w-3 animate-spin rounded-full border border-[var(--ink-soft)] border-t-transparent"
      />
      {children}
    </div>
  );
}

export function ErrorPanel({
  title,
  hint,
}: {
  title: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <div className="mt-6 rounded-sm border border-[var(--table-border)] border-l-[3px] border-l-[var(--morningstar-red)] bg-[var(--surface-muted)] px-3.5 py-3 text-[13px] text-[var(--foreground)]">
      {title}
      {hint ? (
        <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
          {hint}
        </div>
      ) : null}
    </div>
  );
}
