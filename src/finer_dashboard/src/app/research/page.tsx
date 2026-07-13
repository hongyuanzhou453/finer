"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Activity, LayoutGrid, ListFilter, ShieldCheck } from "lucide-react";
import type {
  BacktestSummary,
  KOL,
  KOLRatingResponse,
} from "@/lib/contracts";
import type { KOLBacktestViewModel } from "@/lib/f8-visualization";
import {
  getBacktestResult,
  getKOLRating,
  listBacktestResults,
  listKOLs,
} from "@/lib/api-client";
import {
  backtestResultToViewModel,
  kolListItemToKOL,
  kolRatingToDetail,
} from "@/lib/adapters";
import { useAsyncData } from "@/lib/hooks/useAsyncData";
import { KolObjectRail, ProvenanceRail, ResearchCanvas } from "@/components/research";

type KolResearch = {
  rating: KOLRatingResponse;
  backtest: KOLBacktestViewModel | null;
  backtestId: string | null;
};

/**
 * Build the researchable KOL universe from real endpoints.
 *
 * The enriched KOL list (/api/kol/list/enriched) may be empty even when rating
 * and backtest data exist keyed by kol_id. We therefore union the enriched list
 * with KOLs that have backtests, hydrating the latter from their rating endpoint.
 * No synthetic placeholders — every entry is backed by a real rating or backtest.
 */
async function loadKolUniverse(): Promise<KOL[]> {
  const [enriched, summaries] = await Promise.all([
    listKOLs()
      .then((items) => items.map(kolListItemToKOL))
      .catch(() => [] as KOL[]),
    listBacktestResults({ limit: 100 }).catch(() => [] as BacktestSummary[]),
  ]);

  const byId = new Map<string, KOL>();
  for (const k of enriched) byId.set(k.id, k);

  const missingIds = [
    ...new Set(summaries.map((s) => s.kol_id).filter((id): id is string => !!id)),
  ].filter((id) => !byId.has(id));

  const derived = await Promise.all(
    missingIds.map(async (id) => {
      try {
        return kolRatingToDetail(await getKOLRating(id), id) as KOL;
      } catch {
        return null;
      }
    }),
  );
  for (const k of derived) if (k) byId.set(k.id, k);

  return [...byId.values()];
}

/** Load rating + latest backtest for one KOL. Binds entirely to real endpoints. */
async function loadResearch(kolId: string): Promise<KolResearch> {
  const [rating, summaries] = await Promise.all([
    getKOLRating(kolId),
    listBacktestResults({ kol_id: kolId, limit: 1 }).catch(
      () => [] as BacktestSummary[],
    ),
  ]);

  let backtest: KOLBacktestViewModel | null = null;
  let backtestId: string | null = null;
  if (summaries.length > 0) {
    backtestId = summaries[0].backtest_id;
    backtest = await getBacktestResult(backtestId)
      .then((r) => backtestResultToViewModel(r, kolId))
      .catch(() => null);
  }

  return { rating, backtest, backtestId };
}

export default function ResearchPage() {
  const {
    data: kolsRaw,
    loading: kolsLoading,
    error: kolsError,
    reload: reloadKols,
  } = useAsyncData(() => loadKolUniverse(), []);

  const kols: KOL[] = useMemo(
    () => [...(kolsRaw ?? [])].sort((a, b) => b.overallScore - a.overallScore),
    [kolsRaw],
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Initialize selection from ?kol= URL param, else first KOL.
  useEffect(() => {
    if (selectedId || kols.length === 0) return;
    const urlKol =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("kol")
        : null;
    if (urlKol && kols.some((k) => k.id === urlKol)) {
      setSelectedId(urlKol);
    } else {
      setSelectedId(kols[0].id);
    }
  }, [kols, selectedId]);

  const selectedKol = kols.find((k) => k.id === selectedId);

  const {
    data: research,
    loading: researchLoading,
    error: researchError,
    reload: reloadResearch,
  } = useAsyncData<KolResearch | null>(
    () => (selectedId ? loadResearch(selectedId) : Promise.resolve(null)),
    [selectedId],
  );

  function handleSelect(id: string) {
    setSelectedId(id);
    if (typeof window !== "undefined") {
      window.history.pushState(null, "", `/research?kol=${id}`);
    }
  }

  return (
    <div className="flex h-full w-full flex-col bg-background">
      {/* Top context bar */}
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--table-border)] bg-[var(--surface-strong)] px-4 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-morningstar-red">
            <Activity className="h-4 w-4 text-white" strokeWidth={1.8} />
          </div>
          <div className="flex min-w-0 items-baseline gap-2">
            <span className="shrink-0 whitespace-nowrap text-[15px] font-bold tracking-tight text-foreground">
              Finer OS
            </span>
            <span className="hidden items-baseline gap-2 md:flex">
              <span className="text-foreground/30">/</span>
              <span className="whitespace-nowrap text-[13px] font-semibold text-foreground/70">
                KOL 研究
              </span>
              {selectedKol && (
                <>
                  <span className="text-foreground/30">/</span>
                  <span className="max-w-[28vw] truncate text-[13px] text-morningstar-red">
                    {selectedKol.name}
                  </span>
                </>
              )}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {/* Mobile KOL selector (rail hidden below lg) */}
          <div className="lg:hidden">
            <label className="sr-only" htmlFor="kol-mobile-select">
              选择 KOL
            </label>
            <select
              id="kol-mobile-select"
              value={selectedId ?? ""}
              onChange={(e) => handleSelect(e.target.value)}
              className="max-w-[40vw] truncate rounded-sm border border-[var(--table-border)] bg-white px-2 py-1.5 text-[12px] text-foreground outline-none"
            >
              {kols.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
          </div>

          <Link
            href={selectedId ? `/audit?kol=${selectedId}` : "/audit"}
            className="hidden items-center gap-1.5 rounded-sm border border-[var(--table-border)] bg-white px-3 py-1.5 text-[12px] font-semibold text-foreground/70 transition-colors hover:border-foreground/30 sm:inline-flex"
          >
            <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.8} />
            审计台
          </Link>
          <Link
            href="/kol"
            className="hidden items-center gap-1.5 rounded-sm border border-[var(--table-border)] bg-white px-3 py-1.5 text-[12px] font-semibold text-foreground/70 transition-colors hover:border-foreground/30 sm:inline-flex"
          >
            <ListFilter className="h-3.5 w-3.5" strokeWidth={1.8} />
            KOL 列表
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-sm border border-[var(--table-border)] bg-white px-3 py-1.5 text-[12px] font-semibold text-foreground/70 transition-colors hover:border-foreground/30"
          >
            <LayoutGrid className="h-3.5 w-3.5" strokeWidth={1.8} />
            工作台
          </Link>
        </div>
      </header>

      {/* Three-column body */}
      <div className="flex min-h-0 flex-1">
        <div className="hidden lg:flex">
          <KolObjectRail
            kols={kols}
            loading={kolsLoading}
            error={kolsError}
            reload={reloadKols}
            selectedId={selectedId}
            onSelect={handleSelect}
          />
        </div>

        <ResearchCanvas
          kol={selectedKol}
          rating={research?.rating}
          backtest={research?.backtest ?? null}
          loading={researchLoading}
          error={researchError}
          reload={reloadResearch}
        />

        <div className="hidden xl:flex">
          <ProvenanceRail
            kolId={selectedId}
            rating={research?.rating}
            backtest={research?.backtest ?? null}
            backtestId={research?.backtestId ?? null}
            loading={researchLoading}
          />
        </div>
      </div>
    </div>
  );
}
