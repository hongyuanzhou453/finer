"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { KOL } from "@/lib/contracts";
import { AlertTriangle, Loader2, RefreshCw, Search, Users } from "lucide-react";
import { platformLabel, scoreToneClass } from "./format";

type SortKey = "score" | "accuracy" | "return";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "score", label: "评分" },
  { key: "accuracy", label: "准确率" },
  { key: "return", label: "收益" },
];

export function KolObjectRail({
  kols,
  loading,
  error,
  reload,
  selectedId,
  onSelect,
}: {
  kols: KOL[];
  loading: boolean;
  error: Error | null;
  reload: () => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("score");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? kols.filter(
          (k) =>
            k.name.toLowerCase().includes(q) ||
            k.tags.some((t) => t.toLowerCase().includes(q)),
        )
      : kols;
    return [...filtered].sort((a, b) => {
      switch (sortBy) {
        case "accuracy":
          return b.accuracy - a.accuracy;
        case "return":
          return b.avgReturn - a.avgReturn;
        default:
          return b.overallScore - a.overallScore;
      }
    });
  }, [kols, query, sortBy]);

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-r border-[var(--table-border)] bg-[var(--surface-strong)]">
      {/* Rail header */}
      <div className="border-b border-[var(--table-border)] px-5 pt-5 pb-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--ink-soft)]">
            KOL Universe
          </span>
          <span className="tabular-nums text-[11px] font-bold text-foreground/50">
            {loading ? "—" : `${visible.length}/${kols.length}`}
          </span>
        </div>

        {/* Search */}
        <div className="mt-3 flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-2.5 py-1.5">
          <Search className="h-3.5 w-3.5 text-foreground/40" strokeWidth={1.8} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索 KOL 或标签"
            className="w-full bg-transparent text-[13px] text-foreground outline-none placeholder:text-foreground/35"
          />
        </div>

        {/* Sort segmented control */}
        <div className="segmented-control mt-3 w-full" role="tablist" aria-label="KOL 排序方式">
          {SORTS.map((s) => (
            <button
              key={s.key}
              role="tab"
              aria-selected={sortBy === s.key}
              onClick={() => setSortBy(s.key)}
              className="flex-1"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="finer-scrollbar flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex h-40 items-center justify-center text-foreground/30">
            <Loader2 className="h-6 w-6 animate-spin" strokeWidth={1.5} />
          </div>
        ) : error ? (
          <div className="m-4 rounded-sm border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>加载 KOL 列表失败</span>
            </div>
            <p className="mt-1 text-[11px] text-red-600">{error.message}</p>
            <button
              onClick={reload}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold underline hover:text-red-900"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 px-6 text-center text-foreground/35">
            <Users className="h-8 w-8 opacity-40" strokeWidth={1.2} />
            <span className="text-xs">
              {kols.length === 0 ? "暂无 KOL 数据" : "没有匹配的 KOL"}
            </span>
          </div>
        ) : (
          <ul>
            {visible.map((kol) => {
              const active = kol.id === selectedId;
              return (
                <li key={kol.id}>
                  <button
                    onClick={() => onSelect(kol.id)}
                    className={cn(
                      "relative w-full border-b border-[var(--grid-line)] px-5 py-3.5 text-left transition-colors",
                      active
                        ? "bg-[rgba(159,29,34,0.05)]"
                        : "hover:bg-[rgba(99,76,55,0.04)]",
                    )}
                  >
                    {active && (
                      <span className="absolute inset-y-0 left-0 w-[3px] bg-morningstar-red" />
                    )}
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div
                          className={cn(
                            "truncate text-[14px] font-bold leading-tight",
                            active ? "text-morningstar-red" : "text-foreground",
                          )}
                        >
                          {kol.name}
                        </div>
                        <div className="mt-1 text-[11px] text-foreground/45">
                          {platformLabel(kol.platform)} · {kol.totalOpinions} 观点
                        </div>
                      </div>
                      <div
                        className={cn(
                          "shrink-0 tabular-nums text-[17px] font-bold leading-none",
                          scoreToneClass(kol.overallScore),
                        )}
                      >
                        {kol.overallScore.toFixed(1)}
                      </div>
                    </div>

                    {kol.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {kol.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-sm bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-medium text-foreground/55"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
