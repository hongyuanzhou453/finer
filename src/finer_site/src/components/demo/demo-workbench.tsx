"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronRight,
  Clock,
  Search,
  Star,
  UserCheck,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { KOLS, STAGE_DETAILS } from "@/demo/data";
import { DemoHeader, type DemoView } from "./demo-header";
import type {
  EvidenceSpan,
  Kol,
  TradeAction,
  TradeDirection,
  ValidationStatus,
} from "@/demo/types";
import { ReturnChart } from "./return-chart";
import { PipelineRail } from "./pipeline-rail";

// ---- formatting helpers -----------------------------------------------------

const pct = (v: number, sign = true) =>
  `${sign && v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

export const DIRECTION_META: Record<TradeDirection, { label: string; cls: string }> = {
  bullish: { label: "看多", cls: "bg-[rgba(225,27,34,0.1)] text-morningstar-red" },
  bearish: { label: "看空", cls: "bg-[rgba(16,185,129,0.12)] text-[#0f9b6c]" },
  neutral: { label: "中性", cls: "bg-[var(--surface-muted)] text-[var(--ink-soft)]" },
  watchlist: { label: "观察", cls: "bg-[rgba(155,123,69,0.14)] text-[var(--accent-gold)]" },
  risk_warning: { label: "风险提示", cls: "bg-[rgba(16,185,129,0.12)] text-[#0f9b6c]" },
};

const VALIDATION_META: Record<ValidationStatus, { label: string; cls: string }> = {
  verified: { label: "已验证", cls: "text-[#0f9b6c]" },
  under_review: { label: "待复核", cls: "text-[var(--accent-gold)]" },
  pending: { label: "待定", cls: "text-[var(--ink-soft)]" },
  failed: { label: "未通过", cls: "text-morningstar-red" },
};

// ---- small pieces -----------------------------------------------------------

export function Stars({
  value,
  onSelect,
}: {
  value: number | null;
  onSelect?: (n: number) => void;
}) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => {
        const filled = value != null && n <= value;
        const star = (
          <Star
            className={cn("h-4 w-4", filled ? "text-morningstar-red" : "text-foreground/25")}
            fill={filled ? "currentColor" : "none"}
            strokeWidth={1.6}
          />
        );
        return onSelect ? (
          <button
            key={n}
            type="button"
            onClick={() => onSelect(n)}
            className="transition-transform hover:scale-110"
            aria-label={`评 ${n} 星`}
          >
            {star}
          </button>
        ) : (
          <span key={n}>{star}</span>
        );
      })}
    </div>
  );
}

export function HighlightedSource({
  text,
  spans,
  activeSpanId,
}: {
  text: string;
  spans: EvidenceSpan[];
  activeSpanId: string | null;
}) {
  const parts = useMemo(() => {
    const marks = spans
      .map((s) => ({ id: s.evidence_span_id, text: s.text, idx: text.indexOf(s.text) }))
      .filter((m) => m.idx >= 0)
      .sort((a, b) => a.idx - b.idx);
    const out: { t: string; id: string | null }[] = [];
    let cursor = 0;
    for (const m of marks) {
      if (m.idx < cursor) continue;
      if (m.idx > cursor) out.push({ t: text.slice(cursor, m.idx), id: null });
      out.push({ t: text.slice(m.idx, m.idx + m.text.length), id: m.id });
      cursor = m.idx + m.text.length;
    }
    if (cursor < text.length) out.push({ t: text.slice(cursor), id: null });
    return out;
  }, [text, spans]);

  return (
    <p className="text-[13px] leading-7 text-foreground/90">
      {parts.map((p, i) =>
        p.id ? (
          <mark
            key={i}
            className={cn(
              "rounded-sm px-0.5 transition-colors",
              activeSpanId === p.id
                ? "bg-[rgba(225,27,34,0.3)]"
                : "bg-[rgba(225,27,34,0.12)]",
            )}
          >
            {p.t}
          </mark>
        ) : (
          <span key={i}>{p.t}</span>
        ),
      )}
    </p>
  );
}

// ---- left rail: KOL roster --------------------------------------------------

function KolList({
  kols,
  activeId,
  onSelect,
}: {
  kols: Kol[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto p-3 finer-scrollbar lg:flex-col lg:overflow-x-visible lg:overflow-y-auto">
      <div className="hidden px-1 pb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/40 lg:block">
        KOL Universe
      </div>
      {kols.map((k) => {
        const on = k.id === activeId;
        return (
          <button
            key={k.id}
            type="button"
            onClick={() => onSelect(k.id)}
            className={cn(
              "min-w-[150px] shrink-0 rounded-sm border px-3 py-2.5 text-left transition-colors lg:min-w-0",
              on
                ? "border-l-2 border-morningstar-red bg-white shadow-[var(--shadow-soft)]"
                : "border-[var(--table-border)] bg-[var(--surface-strong)] hover:bg-white",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-bold text-foreground">{k.name}</span>
              <span className="tabular-nums text-[13px] font-bold text-morningstar-red">
                {k.rating.toFixed(1)}
              </span>
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-foreground/45">{k.handle}</div>
            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-[var(--ink-soft)]">
              <span>{k.style}</span>
              <span className="h-0.5 w-0.5 rounded-full bg-foreground/30" />
              <span className="tabular-nums">{k.backtest_count} 回测</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ---- right rail: evidence + RLHF -------------------------------------------

function EvidencePanel({
  ta,
  activeSpanId,
  onHoverSpan,
}: {
  ta: TradeAction;
  activeSpanId: string | null;
  onHoverSpan: (id: string | null) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-4 py-2.5">
        <Search className="h-3.5 w-3.5 text-foreground/50" strokeWidth={1.8} />
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/55">
          Evidence &amp; Provenance
        </span>
      </div>

      <div className="px-4 py-3">
        {/* source with highlights */}
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          原文 · source
        </div>
        <div className="mt-1.5 rounded-sm border border-[var(--grid-line)] bg-[var(--surface-strong)] p-3">
          <HighlightedSource text={ta.source_text} spans={ta.evidence} activeSpanId={activeSpanId} />
        </div>

        {/* evidence spans */}
        <div className="mt-4 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          证据片段 · EvidenceSpan
        </div>
        <ul className="mt-1.5 space-y-1.5">
          {ta.evidence.map((e) => (
            <li
              key={e.evidence_span_id}
              onMouseEnter={() => onHoverSpan(e.evidence_span_id)}
              onMouseLeave={() => onHoverSpan(null)}
              className={cn(
                "cursor-default rounded-sm border px-2.5 py-2 transition-colors",
                activeSpanId === e.evidence_span_id
                  ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.05)]"
                  : "border-[var(--table-border)] bg-white",
              )}
            >
              <div className="flex items-center justify-between font-mono text-[10px] text-foreground/45">
                <span>{e.evidence_span_id}</span>
                <span>
                  [{e.char_start}, {e.char_end}] · {e.span_type}
                </span>
              </div>
              <div className="mt-0.5 text-[12px] text-foreground/85">「{e.text}」</div>
            </li>
          ))}
        </ul>

        {/* trace chain */}
        <div className="mt-4 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          证据链 · canonical trace
        </div>
        <dl className="mt-1.5 divide-y divide-[var(--grid-line)] rounded-sm border border-[var(--table-border)] bg-white font-mono text-[11px]">
          {[
            ["intent_id", ta.intent_id],
            ["policy_id", ta.policy_id],
            ["evidence_span_ids", ta.evidence_span_ids.join(", ")],
            ["trace_status", ta.canonical_trace_status],
          ].map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-2 px-3 py-1.5">
              <dt className="w-28 shrink-0 text-foreground/50">{k}</dt>
              <dd
                className={cn(
                  "min-w-0 break-words",
                  k === "trace_status" ? "font-bold text-[#0f9b6c]" : "text-foreground/85",
                )}
              >
                {v}
              </dd>
            </div>
          ))}
        </dl>

        {/* execution timing — four clocks */}
        <div className="mt-4 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          <Clock className="h-3 w-3" strokeWidth={2} />
          四时钟 · ExecutionTiming
        </div>
        <dl className="mt-1.5 divide-y divide-[var(--grid-line)] rounded-sm border border-[var(--table-border)] bg-white font-mono text-[11px]">
          {[
            ["intent_published_at", ta.execution_timing.intent_published_at],
            ["intent_effective_at", ta.execution_timing.intent_effective_at],
            ["action_decision_at", ta.execution_timing.action_decision_at],
            ["action_executable_at", ta.execution_timing.action_executable_at],
          ].map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-2 px-3 py-1.5">
              <dt className="w-40 shrink-0 text-foreground/50">{k}</dt>
              <dd className="min-w-0 break-words text-foreground/85">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-1.5 font-mono text-[10px] text-foreground/40">
          session @ publish: {ta.execution_timing.market_session_at_publish} ·{" "}
          {ta.execution_timing.timezone}
        </div>
      </div>
    </div>
  );
}

function RlhfPanel({ ta }: { ta: TradeAction }) {
  const [rating, setRating] = useState<number | null>(null);
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    setRating(null);
    setIsCorrect(null);
    setSubmitted(false);
  }, [ta.trade_action_id]);

  return (
    <div className="border-t border-[var(--table-border)]">
      <div className="flex items-center gap-2 border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-4 py-2.5">
        <UserCheck className="h-3.5 w-3.5 text-[var(--accent-gold)]" strokeWidth={1.8} />
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/55">
          F6 · RLHF 复核
        </span>
      </div>

      <div className="px-4 py-3">
        {/* existing reviewer verdict */}
        <div className="rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-foreground/55">已有裁决</span>
            <Stars value={ta.rlhf.rating} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-foreground/55">
            <span>
              is_correct:{" "}
              <span className={ta.rlhf.is_correct ? "text-[#0f9b6c]" : "text-morningstar-red"}>
                {String(ta.rlhf.is_correct)}
              </span>
            </span>
            <span>reviewer: {ta.rlhf.reviewer_id}</span>
          </div>
          {ta.rlhf.review_notes && (
            <p className="mt-1.5 text-[12px] leading-5 text-[var(--ink-soft)]">
              「{ta.rlhf.review_notes}」
            </p>
          )}
          {ta.rlhf.corrections.length > 0 && (
            <ul className="mt-1.5 space-y-0.5">
              {ta.rlhf.corrections.map((c) => (
                <li key={c} className="text-[11px] text-[var(--ink-soft)]">
                  · {c}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* your turn */}
        {!submitted ? (
          <div className="mt-3">
            <div className="text-[11px] font-bold text-foreground/70">轮到你复核（演示）</div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[12px] text-[var(--ink-soft)]">整体评分</span>
              <Stars value={rating} onSelect={setRating} />
            </div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[12px] text-[var(--ink-soft)]">方向是否正确</span>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setIsCorrect(true)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-[12px] transition-colors",
                    isCorrect === true
                      ? "border-[#0f9b6c]/40 bg-[rgba(16,185,129,0.1)] text-[#0f9b6c]"
                      : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                  )}
                >
                  <Check className="h-3.5 w-3.5" strokeWidth={2} /> 正确
                </button>
                <button
                  type="button"
                  onClick={() => setIsCorrect(false)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-[12px] transition-colors",
                    isCorrect === false
                      ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.08)] text-morningstar-red"
                      : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                  )}
                >
                  <X className="h-3.5 w-3.5" strokeWidth={2} /> 有误
                </button>
              </div>
            </div>
            <button
              type="button"
              disabled={rating == null || isCorrect == null}
              onClick={() => setSubmitted(true)}
              className="mt-3 w-full rounded-sm bg-morningstar-red px-3 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-morningstar-red/90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              提交反馈
            </button>
          </div>
        ) : (
          <div className="mt-3 rounded-sm border border-[#0f9b6c]/30 bg-[rgba(16,185,129,0.06)] p-3">
            <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[#0f9b6c]">
              <Check className="h-4 w-4" strokeWidth={2} />
              已记录为 RLHFFeedback（演示，未落库）
            </div>
            <pre className="mt-2 overflow-x-auto rounded-sm bg-white/70 p-2 font-mono text-[10px] leading-5 text-foreground/75">
{`{
  "trade_action_id": "${ta.trade_action_id}",
  "rating": ${rating},
  "is_correct": ${isCorrect},
  "reviewer_id": "you_demo",
  "reviewed_at": "2026-06-03T..."
}`}
            </pre>
            <div className="mt-1.5 font-mono text-[10px] text-foreground/45">
              → POST /api/rlhf/submit （演示中不会真正发送）
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---- main workbench ---------------------------------------------------------

export function DemoWorkbench({
  view,
  onViewChange,
}: {
  view: DemoView;
  onViewChange: (v: DemoView) => void;
}) {
  const [kolId, setKolId] = useState(KOLS[0].id);
  const kol = KOLS.find((k) => k.id === kolId) ?? KOLS[0];

  const [taId, setTaId] = useState(kol.trade_actions[0].trade_action_id);
  const ta = kol.trade_actions.find((t) => t.trade_action_id === taId) ?? kol.trade_actions[0];

  const [stageId, setStageId] = useState(STAGE_DETAILS[0].id);
  const [activeSpanId, setActiveSpanId] = useState<string | null>(null);

  function selectKol(id: string) {
    const k = KOLS.find((x) => x.id === id) ?? KOLS[0];
    setKolId(id);
    setTaId(k.trade_actions[0].trade_action_id);
    setActiveSpanId(null);
  }

  function selectTa(id: string) {
    setTaId(id);
    setActiveSpanId(null);
  }

  const m = kol.metrics;

  return (
    <div className="flex h-[100dvh] flex-col">
      {/* top bar */}
      <DemoHeader view={view} onViewChange={onViewChange} />

      {/* body: three panes */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        {/* left: KOL roster */}
        <aside className="shrink-0 border-b border-[var(--table-border)] bg-[var(--surface-strong)] lg:w-60 lg:border-b-0 lg:border-r">
          <KolList kols={KOLS} activeId={kolId} onSelect={selectKol} />
        </aside>

        {/* center: research view */}
        <main className="min-w-0 flex-1 overflow-y-auto finer-scrollbar">
          <div className="mx-auto max-w-[860px] px-5 py-5">
            {/* KOL header */}
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="flex items-center gap-2.5">
                  <h1 className="text-[24px] font-bold tracking-tight text-foreground">
                    {kol.name}
                  </h1>
                  <span className="font-mono text-[12px] text-foreground/45">{kol.handle}</span>
                </div>
                <p className="mt-1 text-[13px] text-[var(--ink-soft)]">{kol.blurb}</p>
              </div>
              <div className="text-right">
                <div className="text-[11px] text-foreground/45">综合回测评分</div>
                <div className="tabular-nums text-[30px] font-bold leading-none text-morningstar-red">
                  {kol.rating.toFixed(1)}
                </div>
              </div>
            </div>

            {/* metrics row */}
            <div className="mt-4 grid grid-cols-3 overflow-hidden rounded-sm border border-[var(--table-border)] sm:grid-cols-6">
              {[
                { k: "累计收益", v: pct(m.cum_return), red: true },
                { k: "年化", v: pct(m.annualized), red: true },
                { k: "夏普", v: m.sharpe.toFixed(2) },
                { k: "最大回撤", v: pct(m.max_drawdown), green: true },
                { k: "胜率", v: `${(m.win_rate * 100).toFixed(1)}%` },
                { k: "信号数", v: String(m.signal_count) },
              ].map((cell) => (
                <div
                  key={cell.k}
                  className="border-r border-[var(--grid-line)] bg-white px-3 py-2.5 last:border-r-0"
                >
                  <div className="text-[10px] text-foreground/45">{cell.k}</div>
                  <div
                    className={cn(
                      "mt-0.5 tabular-nums text-[15px] font-bold",
                      cell.red && "text-morningstar-red",
                      cell.green && "text-[#0f9b6c]",
                      !cell.red && !cell.green && "text-foreground",
                    )}
                  >
                    {cell.v}
                  </div>
                </div>
              ))}
            </div>

            {/* cumulative return chart */}
            <div className="mt-4 rounded-sm border border-[var(--table-border)] bg-white p-4">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[12px] font-bold text-foreground">
                  Cumulative Return · 累计收益
                </span>
                <div className="flex items-center gap-3 text-[10px] text-[var(--ink-soft)]">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-0.5 w-3 bg-[var(--chart-up)]" /> 跟单收益
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-0.5 w-3 bg-[var(--chart-peer)]" /> 沪深300
                  </span>
                </div>
              </div>
              <ReturnChart series={kol.series} seriesKey={kol.id} />
              <div className="mt-1 text-[10px] text-foreground/40">
                次开盘成交 · 含费用与滑点假设 · {kol.period}
              </div>
            </div>

            {/* trade action list */}
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/45">
                  交易动作 · TradeAction
                </span>
                <span className="text-[10px] text-foreground/40">点一条 → 右侧证据溯源</span>
              </div>
              <div className="space-y-1.5">
                {kol.trade_actions.map((t) => {
                  const on = t.trade_action_id === taId;
                  const dir = DIRECTION_META[t.direction];
                  const val = VALIDATION_META[t.validation_status];
                  return (
                    <button
                      key={t.trade_action_id}
                      type="button"
                      onClick={() => selectTa(t.trade_action_id)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-sm border px-3 py-2.5 text-left transition-colors",
                        on
                          ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.04)]"
                          : "border-[var(--table-border)] bg-white hover:border-foreground/20",
                      )}
                    >
                      <div className="flex w-16 shrink-0 flex-col">
                        <span className="font-mono text-[12px] font-bold text-foreground">
                          {t.ticker}
                        </span>
                        <span className="text-[10px] text-foreground/45">{t.company_name}</span>
                      </div>
                      <span className={cn("rounded-sm px-1.5 py-0.5 text-[10px] font-bold", dir.cls)}>
                        {dir.label}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--ink-soft)]">
                        {t.summary}
                      </span>
                      <span className="hidden shrink-0 text-right sm:block">
                        <span
                          className={cn(
                            "tabular-nums text-[12px] font-bold",
                            t.backtest.return_pct >= 0 ? "text-morningstar-red" : "text-[#0f9b6c]",
                          )}
                        >
                          {pct(t.backtest.return_pct)}
                        </span>
                        <span className={cn("block text-[9px]", val.cls)}>{val.label}</span>
                      </span>
                      <ChevronRight className="h-4 w-4 shrink-0 text-foreground/25" strokeWidth={2} />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* pipeline walk-through */}
            <div className="mt-6 border-t border-[var(--table-border)] pt-5">
              <PipelineRail stages={STAGE_DETAILS} activeId={stageId} onSelect={setStageId} />
            </div>
          </div>
        </main>

        {/* right: evidence + RLHF */}
        <aside className="shrink-0 overflow-y-auto border-t border-[var(--table-border)] bg-[var(--surface-strong)] finer-scrollbar lg:w-80 lg:border-l lg:border-t-0">
          <EvidencePanel ta={ta} activeSpanId={activeSpanId} onHoverSpan={setActiveSpanId} />
          <RlhfPanel ta={ta} />
        </aside>
      </div>
    </div>
  );
}
