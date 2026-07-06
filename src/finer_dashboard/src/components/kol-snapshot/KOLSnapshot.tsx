"use client";

/**
 * KOL 观点潮汐快照 (viewpoint tide snapshot) — editorial financial-report layout
 * for a single KOL's F7 timeline. Data-source agnostic: feed it a KOLSnapshotData
 * view-model (fixture today, GET /api/opinions/timeline once F7 data matures).
 */
import React, { useMemo, useState } from "react";
import {
  deriveHighlights,
  deriveSummary,
  deriveTickerRotation,
  netStance,
  type KOLSnapshotData,
  type SnapshotSummary,
  type SnapshotViewpoint,
  type ViewpointDirection,
} from "@/lib/fixtures/kol-snapshot";
import {
  DIRECTION_META,
  DirectionLegend,
  DirectionTag,
  SectionHeader,
  fmtConfidence,
  fmtDate,
  fmtPct,
} from "./primitives";
import { ViewpointQuadrant } from "./ViewpointQuadrant";
import { StanceTide } from "./StanceTide";
import { ViewpointTimeline } from "./ViewpointTimeline";
import { TickerRotation } from "./TickerRotation";
import { TradingStyleCard } from "./TradingStyleCard";

const ALL_DIRECTIONS: ViewpointDirection[] = [
  "bullish",
  "bearish",
  "neutral",
  "watchlist",
  "risk_warning",
];

type Period = "1m" | "3m" | "all";
const PERIOD_DAYS: Record<Period, number | null> = { "1m": 31, "3m": 92, all: null };
const PERIOD_LABEL: Record<Period, string> = { "1m": "近1月", "3m": "近3月", all: "全部" };
const BREADTH_ORDER: ViewpointDirection[] = [
  "bullish",
  "bearish",
  "neutral",
  "watchlist",
  "risk_warning",
];

function filterByPeriod(
  viewpoints: SnapshotViewpoint[],
  generatedAt: string,
  period: Period,
): SnapshotViewpoint[] {
  const days = PERIOD_DAYS[period];
  if (days === null) return viewpoints;
  const cutoff = new Date(generatedAt).getTime() - days * 86_400_000;
  return viewpoints.filter((v) => new Date(v.timestamp).getTime() >= cutoff);
}

// ---- small inline pieces ----------------------------------------------------

function StatBlock({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] text-[var(--ink-soft)]">
        {label}
      </div>
      <div className="tabular-nums text-[22px] font-semibold leading-tight text-[var(--foreground)]">
        {value}
      </div>
      {sub ? <div className="text-[11px] text-[var(--ink-soft)]">{sub}</div> : null}
    </div>
  );
}

function BreadthBar({ summary }: { summary: SnapshotSummary }) {
  const counts: Record<ViewpointDirection, number> = {
    bullish: summary.bullishCount,
    bearish: summary.bearishCount,
    neutral: summary.neutralCount,
    watchlist: summary.watchlistCount,
    risk_warning: summary.riskWarningCount,
  };
  const total = summary.totalActions || 1;
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-sm">
        {BREADTH_ORDER.map((d) =>
          counts[d] > 0 ? (
            <div
              key={d}
              style={{
                width: `${(counts[d] / total) * 100}%`,
                backgroundColor: DIRECTION_META[d].color,
              }}
              title={`${DIRECTION_META[d].label} ${counts[d]}`}
            />
          ) : null,
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {BREADTH_ORDER.map((d) => (
          <span key={d} className="flex items-center gap-1 text-[11px]">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-[2px]"
              style={{ backgroundColor: DIRECTION_META[d].color }}
            />
            <span className="text-[var(--ink-soft)]">{DIRECTION_META[d].label}</span>
            <span className="tabular-nums font-medium text-[var(--foreground)]">
              {counts[d]}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function HighlightCard({
  label,
  primary,
  secondary,
  accent,
  tag,
}: {
  label: string;
  primary: string;
  secondary?: string;
  accent?: string;
  tag?: React.ReactNode;
}) {
  return (
    <div className="editorial-card rounded-sm p-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[var(--ink-soft)]">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-[var(--foreground)]">{primary}</span>
        {tag}
      </div>
      {secondary ? (
        <div
          className="tabular-nums mt-0.5 text-lg font-semibold leading-none"
          style={{ color: accent ?? "var(--foreground)" }}
        >
          {secondary}
        </div>
      ) : null}
    </div>
  );
}

// ---- main -------------------------------------------------------------------

export function KOLSnapshot({ data }: { data: KOLSnapshotData }) {
  const [period, setPeriod] = useState<Period>("all");

  const viewpoints = useMemo(
    () => filterByPeriod(data.viewpoints, data.generatedAt, period),
    [data.viewpoints, data.generatedAt, period],
  );
  const summary = useMemo(() => deriveSummary(viewpoints), [viewpoints]);
  const highlights = useMemo(() => deriveHighlights(viewpoints), [viewpoints]);
  const net = netStance(summary);

  const quadrantPoints = useMemo(
    () => viewpoints.filter((v) => v.returnPct !== null && (v.holdingDays ?? 0) > 0),
    [viewpoints],
  );
  const tickerRotation = useMemo(() => deriveTickerRotation(viewpoints), [viewpoints]);

  const verdict =
    net >= 2
      ? { label: "偏多", color: "var(--chart-up)", arrow: "▲" }
      : net <= -2
        ? { label: "偏空", color: "var(--chart-down)", arrow: "▼" }
        : { label: "分歧", color: "#8a8278", arrow: "◆" };

  const verifiedRate = summary.totalActions
    ? summary.verifiedCount / summary.totalActions
    : 0;

  return (
    <div className="mx-auto max-w-[1180px] px-6 py-8">
      {/* ── Masthead ──────────────────────────────────────────── */}
      <header className="border-b border-[var(--foreground)] pb-4">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] text-[var(--ink-soft)]">
          <span>FINER OS · 观点潮汐 · KOL VIEWPOINT TIDE</span>
          <span className="tabular-nums normal-case tracking-normal">
            生成 {data.generatedAt.slice(0, 16).replace("T", " ")}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <h1 className="text-[34px] leading-none text-[var(--foreground)]">
              {data.kolName}
            </h1>
            <span className="tabular-nums text-sm text-[var(--ink-soft)]">
              @{data.handle}
            </span>
            <span className="rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] text-[var(--foreground)]">
              {data.style}
            </span>
            <span className="text-[11px] text-[var(--ink-soft)]">{data.platform}</span>
          </div>
          <div className="segmented-control" role="tablist" aria-label="时间范围">
            {(Object.keys(PERIOD_LABEL) as Period[]).map((p) => (
              <button
                key={p}
                role="tab"
                aria-selected={period === p}
                onClick={() => setPeriod(p)}
              >
                {PERIOD_LABEL[p]}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* ── Hero: stance verdict + tide ───────────────────────── */}
      <section className="editorial-panel mt-5 grid grid-cols-1 gap-6 rounded-sm p-5 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-soft)]">
            当前立场 · STANCE
          </div>
          <div className="mt-1 flex items-end gap-3">
            <span
              className="text-[52px] font-semibold leading-none"
              style={{ color: verdict.color, fontFamily: "var(--font-display-serif)" }}
            >
              {verdict.arrow} {verdict.label}
            </span>
            <span
              className="tabular-nums mb-1 rounded-sm px-2 py-0.5 text-sm font-semibold"
              style={{
                color: verdict.color,
                backgroundColor: `color-mix(in srgb, ${verdict.color} 12%, transparent)`,
              }}
            >
              {net >= 0 ? `净多 +${net}` : `净空 ${net}`}
            </span>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-4">
            <StatBlock label="总观点" value={String(summary.totalActions)} sub="期内明确观点" />
            <StatBlock
              label="平均置信度"
              value={fmtConfidence(summary.avgConfidence)}
              sub="模型提取置信"
            />
            <StatBlock
              label="验证率"
              value={fmtConfidence(verifiedRate)}
              sub={`${summary.verifiedCount}/${summary.totalActions} 已验证`}
            />
          </div>

          <div className="mt-5">
            <BreadthBar summary={summary} />
          </div>
        </div>

        <div className="lg:border-l lg:border-[var(--table-border)] lg:pl-6">
          <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-[var(--ink-soft)]">
            <span>立场潮汐 · 累计净多空</span>
            <span className="tabular-nums normal-case tracking-normal">
              {summary.dateRange
                ? `${fmtDate(summary.dateRange[0])} — ${fmtDate(summary.dateRange[1])}`
                : "—"}
            </span>
          </div>
          <StanceTide viewpoints={viewpoints} />
          <div className="mt-1 flex justify-between text-[11px] text-[var(--ink-soft)]">
            <span>
              覆盖标的{" "}
              <span className="tabular-nums font-medium text-[var(--foreground)]">
                {summary.tickersCovered.length}
              </span>{" "}
              个
            </span>
            <span>立场为模型隐含 · 收益来自完全跟单回测 · 非投资建议</span>
          </div>
        </div>
      </section>

      {/* ── 本期研判 ──────────────────────────────────────────── */}
      <section className="mt-6">
        <SectionHeader index="" title="本期研判" en="VIEWPOINT FOCUS" />
        <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[1.5fr_1fr]">
          <p className="text-[14px] leading-relaxed text-[var(--foreground)]">
            {data.narrative}
          </p>
          <div className="grid grid-cols-2 gap-3">
            {highlights.topConfidence ? (
              <HighlightCard
                label="最高信心"
                primary={highlights.topConfidence.companyName}
                secondary={fmtConfidence(highlights.topConfidence.confidence)}
                accent="var(--accent-gold)"
                tag={<DirectionTag direction={highlights.topConfidence.direction} size="xs" />}
              />
            ) : null}
            {highlights.bestReturn ? (
              <HighlightCard
                label="最佳兑现"
                primary={highlights.bestReturn.companyName}
                secondary={fmtPct(highlights.bestReturn.returnPct ?? 0)}
                accent={
                  (highlights.bestReturn.returnPct ?? 0) >= 0
                    ? "var(--chart-up)"
                    : "var(--chart-down)"
                }
              />
            ) : null}
            {highlights.worstReturn ? (
              <HighlightCard
                label={
                  (highlights.worstReturn.returnPct ?? 0) < 0 ? "最大教训" : "最弱兑现"
                }
                primary={highlights.worstReturn.companyName}
                secondary={fmtPct(highlights.worstReturn.returnPct ?? 0)}
                accent={
                  (highlights.worstReturn.returnPct ?? 0) < 0
                    ? "var(--chart-down)"
                    : "var(--chart-up)"
                }
              />
            ) : null}
            {highlights.hitRate !== null ? (
              <HighlightCard
                label="兑现命中率"
                primary={`${highlights.settledCount} 笔已结算`}
                secondary={fmtConfidence(highlights.hitRate)}
                accent="var(--foreground)"
              />
            ) : null}
          </div>
        </div>
      </section>

      {/* ── 交易风格画像（自述 vs 实际行为） ────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index=""
          title="交易风格画像"
          en="TRADING STYLE"
          note="自述（人工标注）对照实际行为（F5 归属 action 统计）"
        />
        <div className="mt-3">
          <TradingStyleCard profile={data.tradingStyle} />
        </div>
      </section>

      {/* ── 01 立场总览 ───────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="01"
          title="标的兑现榜"
          en="TICKER SCOREBOARD"
          note={`${summary.tickersCovered.length} 标的 · 按平均兑现排名`}
        />
        <div className="editorial-panel mt-3 rounded-sm p-4">
          <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-[var(--grid-line)] pb-3 text-[12px] text-[var(--ink-soft)]">
            <span>
              覆盖标的{" "}
              <b className="tabular-nums text-[var(--foreground)]">
                {summary.tickersCovered.length}
              </b>
            </span>
            <span>
              看多占比{" "}
              <b className="tabular-nums text-[var(--foreground)]">
                {fmtConfidence(summary.bullishCount / (summary.totalActions || 1))}
              </b>
            </span>
            <span>
              已结算{" "}
              <b className="tabular-nums text-[var(--foreground)]">
                {highlights.settledCount}
              </b>
            </span>
            <span>
              待验证{" "}
              <b className="tabular-nums text-[var(--foreground)]">
                {summary.pendingCount}
              </b>
            </span>
          </div>
          <TickerRotation rows={tickerRotation} />
        </div>
      </section>

      {/* ── 02 观点象限 ───────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="02"
          title="观点象限"
          en="VIEWPOINT QUADRANT"
          note="横轴 置信度 · 纵轴 实际收益 · 颜色代表方向 · 点大小代表持仓"
        />
        <div className="editorial-panel mt-3 grid grid-cols-1 gap-4 rounded-sm p-4 lg:grid-cols-[1.6fr_1fr]">
          <ViewpointQuadrant points={quadrantPoints} avgConfidence={summary.avgConfidence} />
          <div className="flex flex-col justify-center gap-3 text-[12px] leading-relaxed text-[var(--ink-soft)] lg:border-l lg:border-[var(--table-border)] lg:pl-5">
            <span className="text-[11px] uppercase tracking-[0.16em]">如何读 · 四象限</span>
            <div className="grid grid-cols-2 overflow-hidden rounded-sm border border-[var(--table-border)] text-[11px] leading-snug">
              <div className="border-b border-r border-[var(--grid-line)] p-2">
                <b className="text-[var(--foreground)]">左上 低信心·侥幸</b>
                <div>蒙对的，别当本事</div>
              </div>
              <div className="border-b border-[var(--grid-line)] p-2">
                <b className="text-[var(--foreground)]">右上 高信心·兑现</b>
                <div>真本事，可信</div>
              </div>
              <div className="border-r border-[var(--grid-line)] p-2">
                <b className="text-[var(--foreground)]">左下 低信心·亏损</b>
                <div>小错，认知一致</div>
              </div>
              <div className="p-2">
                <b className="text-[var(--foreground)]">右下 高信心·打脸</b>
                <div>系统性偏差，警惕</div>
              </div>
            </div>
            <p>
              竖线 = 平均置信度 {fmtConfidence(summary.avgConfidence)}，横线 = 盈亏分界；
              理想分布集中在右上与左下。
            </p>
            <div className="flex items-center justify-between gap-2 border-t border-[var(--grid-line)] pt-2">
              <DirectionLegend directions={ALL_DIRECTIONS} />
              <span className="tabular-nums text-[var(--foreground)]">
                已结算 {quadrantPoints.length} · 命中{" "}
                {highlights.hitRate !== null ? fmtConfidence(highlights.hitRate) : "—"}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── 03 观点时间线 ─────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="03"
          title="观点时间线"
          en="VIEWPOINT TIMELINE"
          note={`${viewpoints.length} 条 · 倒序`}
        />
        <div className="mt-4">
          <ViewpointTimeline viewpoints={viewpoints} />
        </div>
      </section>

      <footer className="mt-10 border-t border-[var(--table-border)] pt-4 text-[11px] leading-relaxed text-[var(--ink-soft)]">
        数据为示例 fixture，建模于真实 KOL 画像（老纪 / trader_ji）。每条观点可回溯至 F0
        原文与 F2 证据片段；收益来自 F8 完全跟单回测。本页仅展示模型隐含立场，非投资建议。
      </footer>
    </div>
  );
}
