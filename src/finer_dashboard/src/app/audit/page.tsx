"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Search, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  AuditTraceBundle,
  CanonicalTraceStatus,
  TradeActionSummary,
} from "@/lib/contracts";
import {
  AUDIT_USE_FIXTURES,
  getAuditActions,
  getAuditTrace,
} from "@/lib/audit-api";
import { ActionList } from "@/components/audit/action-list";
import { TraceTimeline } from "@/components/audit/trace-timeline";
import { EvidenceSource } from "@/components/audit/evidence-source";
import { ExecutionClocks } from "@/components/audit/execution-clocks";
import { TraceStatusBadge } from "@/components/audit/trace-status-badge";

const STATUS_OPTIONS: { value: CanonicalTraceStatus | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "canonical", label: "Canonical" },
  { value: "partial", label: "Partial" },
  { value: "non_canonical", label: "Legacy" },
];

export default function AuditPage() {
  const [actions, setActions] = useState<TradeActionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [bundle, setBundle] = useState<AuditTraceBundle | null>(null);
  const [activeSpanId, setActiveSpanId] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingTrace, setLoadingTrace] = useState(false);

  const [statusFilter, setStatusFilter] = useState<CanonicalTraceStatus | "all">("all");
  const [kolFilter, setKolFilter] = useState<string>("all");
  const [tickerQuery, setTickerQuery] = useState("");

  // load the full action list once
  useEffect(() => {
    let alive = true;
    setLoadingList(true);
    getAuditActions()
      .then((data) => {
        if (!alive) return;
        setActions(data);
        // honor ?kol= deep-link when it matches loaded data, else show all
        const urlKol =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("kol")
            : null;
        const kolMatch = !!urlKol && data.some((a) => a.kol_id === urlKol);
        if (kolMatch) setKolFilter(urlKol);
        const first = kolMatch
          ? data.find((a) => a.kol_id === urlKol)?.trade_action_id
          : data[0]?.trade_action_id;
        setActiveId((prev) => prev ?? first ?? null);
      })
      .finally(() => {
        if (alive) setLoadingList(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  // load trace bundle when the selected action changes
  useEffect(() => {
    if (!activeId) {
      setBundle(null);
      return;
    }
    let alive = true;
    setLoadingTrace(true);
    setActiveSpanId(null);
    getAuditTrace(activeId)
      .then((b) => {
        if (alive) setBundle(b);
      })
      .finally(() => {
        if (alive) setLoadingTrace(false);
      });
    return () => {
      alive = false;
    };
  }, [activeId]);

  const kolOptions = useMemo(() => {
    const set = new Set<string>();
    actions.forEach((a) => a.kol_id && set.add(a.kol_id));
    return Array.from(set);
  }, [actions]);

  const filtered = useMemo(
    () =>
      actions.filter((a) => {
        if (statusFilter !== "all" && a.canonical_trace_status !== statusFilter) return false;
        if (kolFilter !== "all" && a.kol_id !== kolFilter) return false;
        if (tickerQuery && !a.ticker.includes(tickerQuery)) return false;
        return true;
      }),
    [actions, statusFilter, kolFilter, tickerQuery],
  );

  const activeSummary = actions.find((a) => a.trade_action_id === activeId) ?? null;

  return (
    <div className="flex h-[100dvh] w-full flex-col">
      {/* top bar */}
      <header className="z-30 flex h-14 shrink-0 items-center justify-between border-b border-[var(--table-border)] bg-[rgba(243,239,231,0.92)] px-4 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-morningstar-red">
            <ShieldCheck className="h-4 w-4 text-white" strokeWidth={1.8} />
          </div>
          <span className="text-[14px] font-bold tracking-tight text-foreground">
            Finer OS
            <span className="ml-2 font-mono text-[11px] font-normal text-foreground/45">
              / audit trace
            </span>
          </span>
          {AUDIT_USE_FIXTURES && (
            <span className="ml-2 hidden rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--ink-soft)] sm:inline">
              演示数据 · Sample data
            </span>
          )}
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-foreground/70 transition-colors hover:text-morningstar-red"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={2} />
          返回工作台
        </Link>
      </header>

      {/* body */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        {/* left: filters + action list */}
        <aside className="flex shrink-0 flex-col border-b border-[var(--table-border)] bg-[var(--surface-strong)] lg:w-72 lg:border-b-0 lg:border-r">
          <div className="border-b border-[var(--table-border)] px-3 py-3">
            <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/45">
              TradeAction · 证据链清单
            </div>
            {/* status segmented */}
            <div className="flex flex-wrap gap-1">
              {STATUS_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setStatusFilter(o.value)}
                  className={cn(
                    "rounded-sm border px-2 py-1 text-[11px] font-semibold transition-colors",
                    statusFilter === o.value
                      ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.06)] text-morningstar-red"
                      : "border-[var(--table-border)] bg-white text-foreground/55 hover:border-foreground/25",
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {/* kol + ticker */}
            <div className="mt-2 flex gap-1.5">
              <select
                value={kolFilter}
                onChange={(e) => setKolFilter(e.target.value)}
                className="min-w-0 flex-1 rounded-sm border border-[var(--table-border)] bg-white px-2 py-1 text-[11px] text-foreground/70"
              >
                <option value="all">全部 KOL</option>
                {kolOptions.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
              <div className="flex min-w-0 flex-1 items-center gap-1 rounded-sm border border-[var(--table-border)] bg-white px-2">
                <Search className="h-3 w-3 shrink-0 text-foreground/40" strokeWidth={2} />
                <input
                  value={tickerQuery}
                  onChange={(e) => setTickerQuery(e.target.value)}
                  placeholder="标的"
                  className="min-w-0 flex-1 bg-transparent py-1 text-[11px] text-foreground/80 outline-none placeholder:text-foreground/30"
                />
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto finer-scrollbar">
            {loadingList ? (
              <div className="flex h-40 items-center justify-center text-foreground/30">
                <Loader2 className="h-6 w-6 animate-spin" strokeWidth={1.5} />
              </div>
            ) : (
              <ActionList actions={filtered} activeId={activeId} onSelect={setActiveId} />
            )}
          </div>
        </aside>

        {/* center: trace timeline */}
        <main className="min-w-0 flex-1 overflow-y-auto finer-scrollbar">
          <div className="mx-auto max-w-[760px] px-5 py-5">
            {loadingTrace ? (
              <div className="flex h-64 items-center justify-center text-foreground/30">
                <Loader2 className="h-7 w-7 animate-spin" strokeWidth={1.5} />
              </div>
            ) : bundle ? (
              <>
                <div className="mb-5 flex flex-wrap items-end justify-between gap-3 border-b border-[var(--table-border)] pb-4">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <h1 className="font-mono text-[22px] font-bold tracking-tight text-foreground">
                        {bundle.trade_action.target.ticker}
                      </h1>
                      <span className="text-[14px] text-foreground/55">
                        {bundle.trade_action.target.company_name}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-foreground/40">
                      {bundle.trade_action.trade_action_id}
                    </p>
                  </div>
                  <TraceStatusBadge status={bundle.trade_action.canonical_trace_status} />
                </div>
                <TraceTimeline
                  bundle={bundle}
                  activeSpanId={activeSpanId}
                  onHoverSpan={setActiveSpanId}
                />
              </>
            ) : (
              <div className="flex h-64 flex-col items-center justify-center gap-3 text-foreground/30">
                <ShieldCheck className="h-10 w-10 opacity-30" strokeWidth={1} />
                <span className="text-[12px] uppercase tracking-[0.16em]">
                  选择左侧一条 TradeAction 查看证据链
                </span>
              </div>
            )}
          </div>
        </main>

        {/* right: evidence + clocks */}
        <aside className="shrink-0 overflow-y-auto border-t border-[var(--table-border)] bg-[var(--surface-strong)] finer-scrollbar lg:w-96 lg:border-l lg:border-t-0">
          {bundle ? (
            <>
              <EvidenceSource
                sourceText={bundle.envelope.source_text}
                spans={bundle.evidence_spans}
                fallbackText={bundle.trade_action.source.evidence_text}
                activeSpanId={activeSpanId}
                onHoverSpan={setActiveSpanId}
              />
              <div className="border-t border-[var(--table-border)] px-4 py-3">
                <ExecutionClocks timing={bundle.trade_action.execution_timing} />
              </div>
            </>
          ) : (
            <div className="flex h-40 items-center justify-center px-6 text-center text-[11px] text-foreground/35">
              {activeSummary ? "" : "证据与执行时钟将在此显示"}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
