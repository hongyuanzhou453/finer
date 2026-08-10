"use client";

/**
 * /records — interactive frozen-snapshot explorer.
 *
 * Static-export friendly: all data comes from runtime fetch of
 * /records-data/*.json (2.9MB split across files; creator files load lazily
 * on first click and are cached in-memory). No backend, no realtime data —
 * everything on screen is a historical record frozen at manifest.as_of.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CreatorRowsFile,
  RecordCard,
  RecordRow,
  RecordsManifest,
  SignalClass,
} from "@/demo/records/types";
import { RecordCardWall } from "./RecordCardWall";
import { CreatorRecordView } from "./CreatorRecordView";
import { SIGNAL_CLASS_LABEL } from "./primitives";

type Selection = { card: RecordCard; rows: RecordRow[] } | null;

/** Persistence-test banner content, rendered FROM the data (not hardcoded). */
function usePersistenceStatement(manifest: RecordsManifest | null) {
  return useMemo(() => {
    if (!manifest) return null;
    for (const cls of manifest.signal_classes) {
      for (const card of manifest.cards[cls] ?? []) {
        const s = card.sufficiency;
        if (s.predictive_claim) {
          const note =
            s.notes.find((n) => n.includes("持续性")) ?? s.notes[0] ?? "";
          return { summary: s.predictive_claim.summary, note };
        }
      }
    }
    return null;
  }, [manifest]);
}

export function RecordsExplorer() {
  const [manifest, setManifest] = useState<RecordsManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signalClass, setSignalClass] = useState<SignalClass>(
    "broker_recommendation",
  );
  const [selection, setSelection] = useState<Selection>(null);
  const [loadingRows, setLoadingRows] = useState(false);
  const rowsCache = useRef(new Map<string, RecordRow[]>());

  useEffect(() => {
    let cancelled = false;
    fetch("/records-data/manifest.json")
      .then((r) => {
        if (!r.ok) throw new Error(`manifest HTTP ${r.status}`);
        return r.json() as Promise<RecordsManifest>;
      })
      .then((m) => {
        if (!cancelled) setManifest(m);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const statement = usePersistenceStatement(manifest);
  const cards = manifest?.cards[signalClass] ?? [];

  async function openCard(card: RecordCard) {
    const cached = rowsCache.current.get(card.rows_file);
    if (cached) {
      setSelection({ card, rows: cached });
      return;
    }
    setLoadingRows(true);
    try {
      const r = await fetch(`/records-data/${card.rows_file}`);
      if (!r.ok) throw new Error(`rows HTTP ${r.status}`);
      const file = (await r.json()) as CreatorRowsFile;
      rowsCache.current.set(card.rows_file, file.rows);
      setSelection({ card, rows: file.rows });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingRows(false);
    }
  }

  return (
    <main className="mx-auto max-w-[1200px] px-6 py-12 lg:py-16">
      {/* page header */}
      <div className="max-w-3xl">
        <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
          SOURCE RECORDS · FROZEN SNAPSHOT
        </div>
        <h1 className="mt-4 text-[30px] font-bold leading-tight tracking-tight text-foreground lg:text-[36px]">
          信源记录 · 谁说过什么，后来发生了什么
        </h1>
        <p className="mt-3 text-[14px] leading-6 text-[var(--ink-soft)]">
          数据冻结于{" "}
          <span className="tabular-nums font-semibold text-foreground/80">
            {manifest?.as_of ?? "2026-08-10"}
          </span>{" "}
          · 真实语料 · 每张卡是一份历史记录，不是推荐
          {manifest ? (
            <span className="tabular-nums">
              {" "}· 共 {manifest.total_actions} 条记录 / {manifest.settled_actions}{" "}
              条已结算
            </span>
          ) : null}
        </p>
      </div>

      {/* persistence-test banner — rendered from snapshot data */}
      {statement ? (
        <div
          className="mt-6 border-t-2 border-morningstar-red bg-white p-5 shadow-[var(--shadow-soft)]"
          data-testid="persistence-banner"
        >
          <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-morningstar-red">
            持续性检验 · 先于结果预声明
          </div>
          <p className="mt-2 max-w-3xl text-[13px] leading-6 text-[var(--ink-soft)]">
            {statement.summary}
          </p>
          <p className="mt-1.5 max-w-3xl text-[12px] leading-5 text-foreground/70">
            {statement.note}
          </p>
        </div>
      ) : null}

      {error ? (
        <div className="mt-6 rounded-sm border border-morningstar-red/40 bg-white p-4 text-[13px] text-morningstar-red">
          快照数据加载失败（{error}）。请刷新重试。
        </div>
      ) : null}

      {!manifest && !error ? (
        <div className="mt-10 text-[13px] text-[var(--ink-soft)]">
          正在加载冻结快照…
        </div>
      ) : null}

      {manifest && !selection ? (
        <>
          {/* signal-class toggle */}
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <div
              className="segmented-control"
              role="tablist"
              aria-label="口径切换"
              data-testid="class-toggle"
            >
              {manifest.signal_classes.map((cls) => (
                <button
                  key={cls}
                  type="button"
                  aria-selected={signalClass === cls}
                  onClick={() => setSignalClass(cls)}
                >
                  {SIGNAL_CLASS_LABEL[cls]}
                </button>
              ))}
            </div>
            <span className="text-[12px] text-[var(--ink-soft)]">
              两种口径基准率不同，不可跨口径比较
            </span>
            <span className="ml-auto text-[12px] text-foreground/45">
              按已结算样本量的稳定输出序，不是排名
            </span>
          </div>

          <div className="mt-5">
            <RecordCardWall
              cards={cards}
              signalClass={signalClass}
              onSelect={openCard}
            />
          </div>

          {loadingRows ? (
            <div className="mt-4 text-[13px] text-[var(--ink-soft)]">
              正在加载该信源的记录…
            </div>
          ) : null}

          <p className="mt-8 text-[12px] leading-5 text-foreground/45">
            快照冻结于 {manifest.as_of} · 语料为静态档案，记录截至哪一天就标注到哪一天，本页不含实时数据。
          </p>
        </>
      ) : null}

      {manifest && selection ? (
        <div className="mt-8">
          <CreatorRecordView
            card={selection.card}
            rows={selection.rows}
            asOf={manifest.as_of}
            onBack={() => setSelection(null)}
          />
        </div>
      ) : null}
    </main>
  );
}
