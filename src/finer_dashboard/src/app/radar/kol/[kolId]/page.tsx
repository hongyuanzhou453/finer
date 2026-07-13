"use client";

/**
 * KOL 问责页 · LIVE — real-data counterpart of /demo/kol/[kolId], fed by the
 * same fetch + adapter as /radar. Renders the unchanged KOLSnapshot component.
 */
import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import { KOLSnapshot } from "@/components/kol-snapshot";
import type { KOLSnapshotData } from "@/lib/fixtures/kol-snapshot";
import {
  fetchLiveRadarData,
  fetchTradingStyle,
  toSnapshotData,
} from "@/lib/live/opinions-adapter";

export default function LiveKolSnapshotPage({
  params,
}: {
  params: Promise<{ kolId: string }>;
}) {
  const { kolId } = use(params);
  const [data, setData] = useState<KOLSnapshotData | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "missing" | "error">(
    "loading",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const decodedId = decodeURIComponent(kolId);
    // Style profile is failure-tolerant (undefined → empty-state card), so it
    // must not block or fail the snapshot itself.
    Promise.all([fetchLiveRadarData(), fetchTradingStyle(decodedId)])
      .then(([r, tradingStyle]) => {
        if (cancelled) return;
        const snap = toSnapshotData(r.data, decodedId);
        if (snap) {
          setData({ ...snap, tradingStyle });
          setState("ok");
        } else {
          setState("missing");
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [kolId]);

  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      {state === "loading" ? (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center text-sm text-[var(--ink-soft)]">
          正在加载真实观点数据…
        </div>
      ) : state === "error" ? (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">无法连接真实数据源</p>
          <p className="tabular-nums mt-2 text-sm text-[var(--ink-soft)]">{error}</p>
        </div>
      ) : state === "missing" || !data ? (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">
            未找到 KOL {decodeURIComponent(kolId)}
          </p>
          <p className="mt-2 text-sm">
            <Link href="/radar" className="text-[var(--accent-teal)] hover:underline">
              返回观点雷达（LIVE）→
            </Link>
          </p>
        </div>
      ) : (
        <>
          <div className="border-b border-[var(--accent-gold)] bg-[color-mix(in_srgb,var(--accent-gold)_8%,transparent)] px-6 py-2 text-center text-[12px] text-[var(--foreground)]">
            <b>LIVE</b> · 真实数据源 /api/opinions ·{" "}
            <Link href="/radar" className="text-[var(--accent-teal)] hover:underline">
              返回观点雷达 →
            </Link>
          </div>
          <KOLSnapshot data={data} />
        </>
      )}
    </main>
  );
}
