"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  TrendingUp,
  TrendingDown,
  Users,
  Calendar,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { useAsyncData } from "@/lib/hooks/useAsyncData";
import { listKOLs } from "@/lib/api-client";
import { kolListItemToKOL } from "@/lib/adapters";
import { platformLabel, returnToneClass, scoreToneClass } from "@/lib/finance-format";

export default function KOLListPage() {
  const [sortBy, setSortBy] = useState<"score" | "accuracy" | "return">("score");
  // Project Memory source: "catalog" | "degraded_scan" — set when connected to real API
  const [dataSource] = useState<"catalog" | "degraded_scan">("catalog");

  const {
    data: kols,
    loading,
    error,
    reload,
  } = useAsyncData(
    () => listKOLs().then((items) => items.map(kolListItemToKOL)),
    [],
  );

  const sortedKOLs = [...(kols ?? [])].sort((a, b) => {
    switch (sortBy) {
      case "score":
        return b.overallScore - a.overallScore;
      case "accuracy":
        return b.accuracy - a.accuracy;
      case "return":
        return b.avgReturn - a.avgReturn;
      default:
        return 0;
    }
  });

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">KOL 列表</h1>
        <p className="text-sm text-foreground/60 mt-1">
          跟踪和评估 KOL 的投资观点表现
        </p>
      </div>

      {/* Project Memory degraded scan warning */}
      {dataSource === "degraded_scan" && (
        <div className="mb-6 flex items-center gap-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>Project Memory 不可用 — 显示文件系统扫描结果</span>
        </div>
      )}

      {/* Sort options */}
      <div className="flex items-center gap-4 mb-6">
        <span className="text-sm text-foreground/60">排序方式：</span>
        <div className="flex gap-2">
          {[
            { key: "score", label: "评分" },
            { key: "accuracy", label: "准确率" },
            { key: "return", label: "收益" },
          ].map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSortBy(opt.key as typeof sortBy)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded border transition-colors",
                sortBy === opt.key
                  ? "border-morningstar-red bg-morningstar-red/5 text-morningstar-red"
                  : "border-stone-200 text-foreground/60 hover:border-stone-300"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>加载 KOL 列表失败：{error.message}</span>
          <button
            onClick={reload}
            className="ml-auto shrink-0 underline hover:text-red-900"
          >
            重试
          </button>
        </div>
      )}

      {/* KOL Cards */}
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-foreground/30" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sortedKOLs.map((kol) => (
            <Link
              key={kol.id}
              href={`/kol/${kol.id}`}
              className="editorial-card group block p-5"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-[var(--surface-muted)] rounded-sm flex items-center justify-center">
                    <Users className="w-6 h-6 text-foreground/35" strokeWidth={1.5} />
                  </div>
                  <div>
                    <h3 className="font-bold group-hover:text-morningstar-red transition-colors">
                      {kol.name}
                    </h3>
                    <span className="text-xs text-foreground/50">
                      {platformLabel(kol.platform)}
                    </span>
                  </div>
                </div>
                <div className={cn("text-2xl font-bold tabular-nums", scoreToneClass(kol.overallScore))}>
                  {kol.overallScore.toFixed(1)}
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-3 gap-4 py-4 border-t border-[var(--grid-line)]">
                <div>
                  <div className="text-[10px] text-foreground/45 uppercase tracking-[0.14em] mb-1 font-bold">
                    准确率
                  </div>
                  <div className="text-lg font-bold tabular-nums">{kol.accuracy}%</div>
                </div>
                <div>
                  <div className="text-[10px] text-foreground/45 uppercase tracking-[0.14em] mb-1 font-bold">
                    平均收益
                  </div>
                  <div
                    className={cn(
                      "text-lg font-bold tabular-nums flex items-center gap-1",
                      returnToneClass(kol.avgReturn)
                    )}
                  >
                    {kol.avgReturn >= 0 ? (
                      <TrendingUp className="w-4 h-4" />
                    ) : (
                      <TrendingDown className="w-4 h-4" />
                    )}
                    {kol.avgReturn.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-foreground/45 uppercase tracking-[0.14em] mb-1 font-bold">
                    观点数
                  </div>
                  <div className="text-lg font-bold tabular-nums">{kol.totalOpinions}</div>
                </div>
              </div>

              {/* Tags & Activity */}
              <div className="flex items-center justify-between pt-4 border-t border-[var(--grid-line)]">
                <div className="flex gap-1.5 flex-wrap">
                  {kol.tags.slice(0, 2).map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 text-[10px] font-medium bg-[var(--surface-muted)] text-foreground/60 rounded-sm"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="flex items-center gap-1 text-xs text-foreground/40 tabular-nums">
                  <Calendar className="w-3 h-3" />
                  {kol.lastActive}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
