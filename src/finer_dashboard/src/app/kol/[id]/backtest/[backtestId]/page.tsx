"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, SlidersHorizontal, Loader2, AlertTriangle, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import {
  CumulativeReturnResearch,
  KOLOverviewPanel,
  MethodologyStrip,
  MetricPercentileTable,
  RiskReturnResearch,
  TopCallsTable,
} from "@/components/f8-charts";
import { useAsyncData } from "@/lib/hooks/useAsyncData";
import { getBacktestResult } from "@/lib/api-client";
import { backtestResultToViewModel } from "@/lib/adapters";

export default function KOLBacktestDetailPage() {
  const params = useParams<{ id: string; backtestId: string }>();

  const {
    data: model,
    loading,
    error,
    reload,
  } = useAsyncData(
    () =>
      getBacktestResult(params.backtestId).then((r) =>
        backtestResultToViewModel(r, params.id),
      ),
    [params.backtestId, params.id],
  );

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--background)]">
        <div className="container py-8 flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-foreground/30" />
        </div>
      </main>
    );
  }

  if (error || !model) {
    const isApiErr = error instanceof ApiError;
    return (
      <main className="min-h-screen bg-[var(--background)]">
        <div className="container py-8">
          <Link
            href={`/kol/${params.id}`}
            className="mb-6 inline-flex items-center gap-2 text-sm text-foreground/60 hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            返回 KOL 详情
          </Link>
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>加载回测结果失败：{error?.message ?? "未找到数据"}</span>
            </div>
            {isApiErr && (
              <div className="mt-2 space-y-1 text-xs text-red-600">
                {error.code && <div>错误码：{error.code}</div>}
                {error.requestId && <div>请求 ID：{error.requestId}</div>}
                {error.fixHint && <div>修复建议：{error.fixHint}</div>}
                {error.retryable && (
                  <button
                    onClick={reload}
                    className="mt-1 inline-flex items-center gap-1 underline hover:text-red-800"
                  >
                    <RefreshCw className="h-3 w-3" />
                    重试
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[var(--background)]">
      <div className="container py-8">
        <Link
          href={`/kol/${params.id}`}
          className="mb-6 inline-flex items-center gap-2 text-sm text-foreground/60 hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          返回 KOL 详情
        </Link>

        <header className="mb-8 border-t-2 border-[var(--foreground)] bg-white px-6 py-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-morningstar-red">
                F8 BACKTEST / KOL SIGNAL PERFORMANCE
              </div>
              <h1 className="text-2xl font-semibold tracking-normal text-[var(--foreground)]">
                {model.subject.name} 的 KOL 收益结果审计
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--ink-soft)]">
                以 {model.benchmark.name} 为基准，比较 {model.cohort.name}，
                覆盖 {model.dateRange.start} 至 {model.dateRange.end}。
                每个图表必须同时展示主体、对照组、时间范围、指标方向和回测假设。
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button className="inline-flex items-center gap-2 border border-[var(--table-border)] bg-white px-3 py-2 text-xs font-semibold text-[var(--foreground)] hover:border-[var(--foreground)]">
                <SlidersHorizontal className="h-4 w-4" />
                基准 / 同类组
              </button>
              <button className="inline-flex items-center gap-2 border border-[var(--foreground)] bg-[var(--foreground)] px-3 py-2 text-xs font-semibold text-white hover:bg-foreground/90">
                <Download className="h-4 w-4" />
                导出报告
              </button>
            </div>
          </div>
        </header>

        <div className="space-y-6">
          <KOLOverviewPanel model={model} />
          <CumulativeReturnResearch model={model} />

          <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.82fr)]">
            <div className="min-w-0">
              <RiskReturnResearch model={model} />
            </div>
            <div className="min-w-0">
              <MetricPercentileTable rows={model.metricRows} />
            </div>
          </div>

          <TopCallsTable model={model} />
          <MethodologyStrip model={model} />

          <footer className="border-t border-[var(--table-border)] py-4 text-[11px] leading-5 text-[var(--ink-soft)]">
            数据截止：{model.dataCutoff}。基准：{model.benchmark.name}。
            同类组：{model.cohort.name}。假设：初始资金 $
            {model.assumptions.initialCapital.toLocaleString()}，单笔仓位
            {(model.assumptions.positionSize * 100).toFixed(0)}%，
            {model.assumptions.executionDelay}，{model.assumptions.holdingRule}。
            费用/滑点：{model.assumptions.feesIncluded ? "已计入" : "未计入"}。
          </footer>
        </div>
      </div>
    </main>
  );
}
