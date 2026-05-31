"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  Users,
  GitCompare,
  Plus,
  X,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import type { KOL } from "@/lib/contracts";
import { returnToneClass } from "@/lib/finance-format";

const availableKOLs: KOL[] = [
  { id: "kol-1", name: "投研老王", platform: "wechat", platformId: "xxx123", overallScore: 4.2, dimensionScores: { accuracy: 4.5, timeliness: 4.0, clarity: 3.8, depth: 4.2, consistency: 4.3 }, accuracy: 68, avgReturn: 12.5, totalOpinions: 156, lastActive: "2026-04-23", tags: ["科技", "半导体"], enabled: true },
  { id: "kol-2", name: "价值投资张", platform: "bilibili", platformId: "bili456", overallScore: 3.8, dimensionScores: { accuracy: 3.5, timeliness: 3.8, clarity: 4.0, depth: 3.8, consistency: 3.9 }, accuracy: 55, avgReturn: 8.2, totalOpinions: 89, lastActive: "2026-04-22", tags: ["消费", "医药"], enabled: true },
  { id: "kol-3", name: "量化小李", platform: "feishu", platformId: "feishu789", overallScore: 4.5, dimensionScores: { accuracy: 4.8, timeliness: 4.5, clarity: 4.2, depth: 4.6, consistency: 4.4 }, accuracy: 72, avgReturn: 18.3, totalOpinions: 234, lastActive: "2026-04-24", tags: ["量化", "期货"], enabled: true },
  { id: "kol-4", name: "趋势王", platform: "wechat", platformId: "trend001", overallScore: 4.0, dimensionScores: { accuracy: 4.0, timeliness: 4.2, clarity: 3.9, depth: 3.8, consistency: 4.1 }, accuracy: 62, avgReturn: 15.1, totalOpinions: 120, lastActive: "2026-04-21", tags: ["趋势", "技术分析"], enabled: true },
];

export default function KOLComparePage() {
  const [selectedKOLs, setSelectedKOLs] = useState<KOL[]>([availableKOLs[0], availableKOLs[1]]);
  const [showSelector, setShowSelector] = useState(false);

  const handleAddKOL = (kol: KOL) => {
    if (!selectedKOLs.find((k) => k.id === kol.id)) {
      setSelectedKOLs([...selectedKOLs, kol]);
    }
    setShowSelector(false);
  };

  const handleRemoveKOL = (kolId: string) => {
    setSelectedKOLs(selectedKOLs.filter((k) => k.id !== kolId));
  };

  const unselectedKOLs = availableKOLs.filter(
    (k) => !selectedKOLs.find((sk) => sk.id === k.id)
  );

  // Comparison metrics
  const metrics = ["overallScore", "accuracy", "avgReturn"] as const;
  const metricLabels = {
    overallScore: "综合评分",
    accuracy: "准确率 (%)",
    avgReturn: "平均收益 (%)",
  };

  const getBestKOL = (metric: typeof metrics[number]) => {
    return selectedKOLs.reduce((best, kol) =>
      kol[metric] > best[metric] ? kol : best
    );
  };

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">KOL 对比</h1>
        <p className="text-sm text-foreground/60 mt-1">
          选择多个 KOL 进行对比分析
        </p>
      </div>

      {/* KOL Selector */}
      <div className="mb-8">
        <div className="flex flex-wrap items-center gap-3">
          {selectedKOLs.map((kol) => (
            <div
              key={kol.id}
              className="flex items-center gap-2 px-3 py-2 bg-white border border-stone-200 rounded-lg"
            >
              <Link
                href={`/kol/${kol.id}`}
                className="font-medium hover:text-morningstar-red transition-colors"
              >
                {kol.name}
              </Link>
              <button
                onClick={() => handleRemoveKOL(kol.id)}
                className="p-0.5 hover:bg-stone-100 rounded transition-colors"
              >
                <X className="w-4 h-4 text-foreground/40" />
              </button>
            </div>
          ))}

          {selectedKOLs.length < 4 && (
            <button
              onClick={() => setShowSelector(!showSelector)}
              className="flex items-center gap-2 px-3 py-2 border border-dashed border-stone-300 rounded-lg text-foreground/60 hover:border-stone-400 hover:text-foreground transition-colors"
            >
              <Plus className="w-4 h-4" />
              添加 KOL
            </button>
          )}
        </div>

        {showSelector && unselectedKOLs.length > 0 && (
          <div className="mt-3 p-3 bg-white border border-stone-200 rounded-lg shadow-sm">
            <div className="text-xs text-foreground/50 mb-2">选择要添加的 KOL：</div>
            <div className="flex flex-wrap gap-2">
              {unselectedKOLs.map((kol) => (
                <button
                  key={kol.id}
                  onClick={() => handleAddKOL(kol)}
                  className="px-3 py-1.5 text-sm bg-stone-50 hover:bg-stone-100 rounded border border-stone-200 transition-colors"
                >
                  {kol.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {selectedKOLs.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-foreground/40">
          <div className="text-center">
            <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>请选择至少一个 KOL 进行对比</p>
          </div>
        </div>
      ) : (
        <>
          {/* Comparison Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {selectedKOLs.map((kol) => (
              <Link
                key={kol.id}
                href={`/kol/${kol.id}`}
                className="editorial-card block p-4"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 bg-[var(--surface-muted)] rounded-sm flex items-center justify-center">
                    <Users className="w-5 h-5 text-foreground/35" strokeWidth={1.5} />
                  </div>
                  <div className="font-bold">{kol.name}</div>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-foreground/60">评分</span>
                    <span className="font-bold tabular-nums">{kol.overallScore.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-foreground/60">准确率</span>
                    <span className="font-bold tabular-nums">{kol.accuracy}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-foreground/60">平均收益</span>
                    <span
                      className={cn(
                        "font-bold tabular-nums flex items-center gap-1",
                        returnToneClass(kol.avgReturn)
                      )}
                    >
                      {kol.avgReturn >= 0 ? (
                        <TrendingUp className="w-3 h-3" />
                      ) : (
                        <TrendingDown className="w-3 h-3" />
                      )}
                      {kol.avgReturn.toFixed(1)}%
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>

          {/* Comparison Table */}
          <div className="bg-white border border-[var(--table-border)] rounded-sm overflow-hidden mb-8">
            <table className="w-full text-sm">
              <thead className="bg-[var(--table-header-bg)] border-b border-[var(--table-border)]">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-foreground/60">
                    指标
                  </th>
                  {selectedKOLs.map((kol) => (
                    <th key={kol.id} className="px-4 py-3 text-center font-medium">
                      {kol.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric) => {
                  const best = getBestKOL(metric);
                  return (
                    <tr key={metric} className="border-b border-[var(--grid-line)] last:border-0">
                      <td className="px-4 py-3 text-foreground/60">
                        {metricLabels[metric]}
                      </td>
                      {selectedKOLs.map((kol) => (
                        <td
                          key={kol.id}
                          className={cn(
                            "px-4 py-3 text-center font-bold tabular-nums",
                            kol.id === best.id && "text-morningstar-red"
                          )}
                        >
                          {metric === "overallScore"
                            ? kol[metric].toFixed(1)
                            : metric === "accuracy"
                            ? `${kol[metric]}%`
                            : `${kol[metric].toFixed(1)}%`}
                          {kol.id === best.id && (
                            <span className="ml-1 text-xs">★</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Radar Chart Placeholder */}
          <div className="bg-white border border-stone-200 rounded-lg p-8">
            <div className="h-64 flex items-center justify-center text-foreground/40">
              <div className="text-center">
                <GitCompare className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>雷达图对比</p>
                <p className="text-xs mt-1">（待实现）</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
