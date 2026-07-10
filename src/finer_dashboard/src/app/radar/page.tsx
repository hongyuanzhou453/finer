"use client";

/**
 * 观点雷达 · LIVE — first real-data path. Same KOLRadar component as the
 * /demo benchmark, fed by /api/opinions/timeline via the live adapter.
 * States: loading / backend-down / empty / data (with an honest banner).
 */
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { KOLRadar, LIVE_RADAR_LINKS } from "@/components/kol-radar";
import {
  fetchLiveRadarData,
  type LiveRadarResult,
} from "@/lib/live/opinions-adapter";

export default function LiveRadarPage() {
  const [result, setResult] = useState<LiveRadarResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchLiveRadarData()
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      {error ? (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">无法连接真实数据源</p>
          <p className="tabular-nums mt-2 text-sm text-[var(--ink-soft)]">{error}</p>
          <p className="mt-4 text-sm text-[var(--ink-soft)]">
            请确认后端已启动：
            <code className="mx-1 rounded-sm bg-[var(--surface-muted)] px-1.5 py-0.5 text-[12px]">
              uvicorn finer.api.server:app --port 8000
            </code>
          </p>
          <p className="mt-3 text-sm">
            <Link href="/demo/kol-radar" className="text-[var(--accent-teal)] hover:underline">
              查看设计标杆（fixture）→
            </Link>
          </p>
        </div>
      ) : !result ? (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center text-sm text-[var(--ink-soft)]">
          正在加载真实观点数据…
        </div>
      ) : result.data.kols.length === 0 ? (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">暂无可归属的真实观点</p>
          <p className="mt-2 text-sm text-[var(--ink-soft)]">
            共 {result.totalOpinions} 条观点，其中 {result.unattributedCount} 条缺少
            KOL 归属（creator_id）。先跑 F5 提取或补齐归属后再来。
          </p>
        </div>
      ) : (
        <>
          <div className="border-b border-[var(--accent-gold)] bg-[color-mix(in_srgb,var(--accent-gold)_8%,transparent)] px-6 py-2 text-center text-[12px] text-[var(--foreground)]">
            <b>LIVE</b> · 真实数据源 /api/opinions · {result.totalOpinions} 条观点 ·{" "}
            {result.data.kols.length} 个 KOL
            {result.unattributedCount > 0
              ? ` · ${result.unattributedCount} 条未归属已排除`
              : ""}{" "}
            · 异动：每日快照对比 + 历史派生 · 信誉分为服务端真值 ·{" "}
            <Link href="/demo/kol-radar" className="text-[var(--accent-teal)] hover:underline">
              对照设计标杆 →
            </Link>
          </div>
          <KOLRadar data={result.data} links={LIVE_RADAR_LINKS} />
        </>
      )}
    </main>
  );
}
