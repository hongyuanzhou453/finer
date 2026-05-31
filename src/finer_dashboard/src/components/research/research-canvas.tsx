"use client";

import { cn } from "@/lib/utils";
import type { KOL, KOLRatingResponse } from "@/lib/contracts";
import type { KOLBacktestViewModel } from "@/lib/f8-visualization";
import { CumulativeReturnResearch } from "@/components/f8-charts";
import {
  AlertTriangle,
  LineChart,
  Loader2,
  RefreshCw,
  Users,
} from "lucide-react";
import { directionStyle, keyStatToneClass, platformLabel } from "./format";

export function ResearchCanvas({
  kol,
  rating,
  backtest,
  loading,
  error,
  reload,
}: {
  kol?: KOL;
  rating?: KOLRatingResponse | null;
  backtest: KOLBacktestViewModel | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}) {
  if (!kol) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-foreground/30">
        <Users className="h-12 w-12 opacity-30" strokeWidth={1} />
        <span className="text-sm">从左侧选择一位 KOL 开始研究</span>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-foreground/30">
        <Loader2 className="h-8 w-8 animate-spin" strokeWidth={1.4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-start justify-center p-8">
        <div className="w-full max-w-md rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>加载 {kol.name} 的研究数据失败</span>
          </div>
          <p className="mt-1 text-xs text-red-600">{error.message}</p>
          <button
            onClick={reload}
            className="mt-2 inline-flex items-center gap-1 text-xs font-semibold underline hover:text-red-900"
          >
            <RefreshCw className="h-3 w-3" />
            重试
          </button>
        </div>
      </div>
    );
  }

  const r = rating?.rating;
  const focusAreas = rating?.focusAreas ?? kol.tags;
  const opinions = rating?.recentOpinions ?? [];

  return (
    <div className="finer-scrollbar flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[960px] px-8 py-7">
        {/* Subject header */}
        <header className="border-t-2 border-foreground bg-[var(--surface-strong)] px-6 py-5">
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0">
              <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-morningstar-red">
                KOL RESEARCH / 观点回测审计
              </div>
              <h1 className="mt-1.5 truncate text-2xl font-bold tracking-tight text-foreground">
                {r?.name ?? kol.name}
              </h1>
              <p className="mt-1 text-[13px] text-foreground/55">
                {platformLabel(r?.platform ?? kol.platform)} · {r?.totalOpinions ?? kol.totalOpinions} 条观点
              </p>
              {focusAreas.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {focusAreas.slice(0, 5).map((tag) => (
                    <span
                      key={tag}
                      className="rounded-sm border border-[var(--table-border)] bg-white px-2 py-0.5 text-[11px] font-medium text-foreground/65"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="shrink-0 text-right">
              <div className="tabular-nums text-4xl font-bold leading-none text-foreground">
                {(r?.overallRating ?? kol.overallScore).toFixed(1)}
              </div>
              <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.16em] text-foreground/45">
                综合评分
              </div>
            </div>
          </div>
        </header>

        {/* Outcome strip: key stats from backtest */}
        {backtest ? (
          <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-[var(--table-border)] bg-[var(--table-border)] sm:grid-cols-3 lg:grid-cols-6">
            {backtest.keyStats.map((stat) => (
              <div key={stat.label} className="bg-white px-4 py-3.5">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-foreground/45">
                  {stat.label}
                </div>
                <div
                  className={cn(
                    "mt-1.5 tabular-nums text-xl font-bold leading-none",
                    keyStatToneClass(stat.tone),
                  )}
                >
                  {stat.value}
                </div>
                {stat.subLabel && (
                  <div className="mt-1 tabular-nums text-[10px] text-foreground/40">
                    {stat.subLabel}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-5 flex items-center gap-3 rounded-sm border border-dashed border-[var(--table-border)] bg-[var(--surface-muted)] px-5 py-4 text-[13px] text-foreground/55">
            <LineChart className="h-5 w-5 shrink-0 text-foreground/35" strokeWidth={1.5} />
            <span>
              该 KOL 暂无回测结果。运行回测后，这里展示累计收益、夏普、回撤等绩效指标。
            </span>
          </div>
        )}

        {/* Money shot: cumulative return curve */}
        <div className="mt-6">
          {backtest ? (
            <CumulativeReturnResearch model={backtest} />
          ) : (
            <div className="research-panel">
              <div className="research-panel-header flex items-center justify-between">
                <span>累计收益曲线</span>
                <span className="text-[11px] font-normal text-foreground/40">F8 BACKTEST</span>
              </div>
              <div className="research-panel-body">
                <div className="flex h-56 flex-col items-center justify-center gap-3 text-foreground/35">
                  <LineChart className="h-10 w-10 opacity-40" strokeWidth={1.1} />
                  <span className="text-xs">暂无回测净值序列</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Recent opinions */}
        <div className="mt-6">
          <div className="research-panel">
            <div className="research-panel-header flex items-center justify-between">
              <span>近期观点</span>
              <span className="tabular-nums text-[11px] font-normal text-foreground/40">
                {opinions.length} 条
              </span>
            </div>
            <div className="research-panel-body p-0">
              {opinions.length === 0 ? (
                <div className="flex h-28 items-center justify-center text-xs text-foreground/35">
                  暂无结构化观点
                </div>
              ) : (
                <ul>
                  {opinions.map((op) => {
                    const dir = directionStyle(op.direction);
                    return (
                      <li
                        key={op.id}
                        className="flex items-center justify-between gap-4 border-b border-[var(--grid-line)] px-4 py-3 last:border-b-0"
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <span className="tabular-nums text-[13px] font-bold text-foreground">
                            {op.ticker}
                          </span>
                          <span
                            className={cn(
                              "rounded-sm px-1.5 py-0.5 text-[11px] font-semibold",
                              dir.cls,
                            )}
                          >
                            {dir.label}
                          </span>
                          {op.ticker_name && (
                            <span className="truncate text-[12px] text-foreground/55">
                              {op.ticker_name}
                            </span>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-3">
                          {op.result && (
                            <span className="text-[11px] text-foreground/50">{op.result}</span>
                          )}
                          <span className="tabular-nums text-[11px] text-foreground/40">
                            {op.timestamp.slice(0, 10)}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
