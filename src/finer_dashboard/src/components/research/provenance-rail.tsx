"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { KOLRatingResponse } from "@/lib/contracts";
import type { KOLBacktestViewModel } from "@/lib/f8-visualization";
import { ArrowUpRight, FileSearch, Loader2, ShieldCheck } from "lucide-react";

function RailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-[var(--table-border)] px-5 py-4">
      <div className="mb-3 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--ink-soft)]">
        {title}
      </div>
      {children}
    </section>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="shrink-0 text-[11px] text-foreground/45">{label}</span>
      <span
        className={cn(
          "min-w-0 truncate text-right text-[12px] text-foreground/75",
          mono && "font-mono text-[11px] text-foreground/55",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function ProvenanceRail({
  kolId,
  rating,
  backtest,
  backtestId,
  loading,
}: {
  kolId: string | null;
  rating?: KOLRatingResponse | null;
  backtest: KOLBacktestViewModel | null;
  backtestId: string | null;
  loading: boolean;
}) {
  const dimensions = rating?.dimensions ?? [];

  return (
    <aside className="flex h-full w-[360px] shrink-0 flex-col border-l border-[var(--table-border)] bg-[var(--surface-strong)]">
      <div className="border-b border-[var(--table-border)] px-5 pt-5 pb-4">
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--ink-soft)]">
          <ShieldCheck className="h-3.5 w-3.5 text-morningstar-red" strokeWidth={1.8} />
          Evidence &amp; Provenance
        </div>
      </div>

      <div className="finer-scrollbar flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex h-40 items-center justify-center text-foreground/30">
            <Loader2 className="h-6 w-6 animate-spin" strokeWidth={1.5} />
          </div>
        ) : (
          <>
            {/* Capability dimensions */}
            <RailSection title="能力维度">
              {dimensions.length === 0 ? (
                <div className="py-2 text-[12px] text-foreground/40">暂无维度评分</div>
              ) : (
                <div className="space-y-2.5">
                  {dimensions.map((d) => (
                    <div key={d.dimension}>
                      <div className="flex items-center justify-between">
                        <span className="text-[12px] text-foreground/70">{d.label}</span>
                        <span className="tabular-nums text-[12px] font-bold text-foreground">
                          {d.score.toFixed(1)}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                        <div
                          className="h-full rounded-full bg-morningstar-red"
                          style={{ width: `${Math.min(100, (d.score / 5) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </RailSection>

            {/* Backtest provenance */}
            <RailSection title="回测溯源">
              {backtest ? (
                <div className="space-y-0.5">
                  <MetaRow
                    label="回测区间"
                    value={`${backtest.dateRange.start} → ${backtest.dateRange.end}`}
                  />
                  <MetaRow label="数据截止" value={backtest.dataCutoff} />
                  <MetaRow
                    label="初始资金"
                    value={`$${backtest.assumptions.initialCapital.toLocaleString()}`}
                  />
                  <MetaRow
                    label="单笔仓位"
                    value={`${(backtest.assumptions.positionSize * 100).toFixed(0)}%`}
                  />
                  <MetaRow label="持仓规则" value={backtest.assumptions.holdingRule} />
                  <MetaRow
                    label="费用滑点"
                    value={backtest.assumptions.feesIncluded ? "已计入" : "未计入"}
                  />
                  {backtestId && (
                    <MetaRow label="回测 ID" value={backtestId} mono />
                  )}
                </div>
              ) : (
                <div className="py-2 text-[12px] text-foreground/40">
                  暂无回测溯源信息
                </div>
              )}
            </RailSection>

            {/* Action */}
            {kolId && backtestId && (
              <div className="px-5 py-5">
                <Link
                  href={`/kol/${kolId}/backtest/${backtestId}`}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-sm bg-morningstar-red px-4 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
                >
                  <FileSearch className="h-4 w-4" strokeWidth={1.8} />
                  查看完整回测审计
                  <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={2} />
                </Link>
                <p className="mt-2 text-center text-[10px] text-foreground/40">
                  含逐笔交易、风险指标与方法论
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
