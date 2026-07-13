/**
 * L4 per-viewpoint evidence audit — the drill target for every viewpoint / call.
 * Shows the layers the demo actually carries (F2 evidence → F5 action → F8 backtest)
 * and honestly flags F3 intent / F4 policy as not-materialized-in-demo. Full canonical
 * F0→F5 examples live at /audit. Reuses the audit TraceStatusBadge + the snapshot kit.
 */
import React from "react";
import Link from "next/link";
import { TraceStatusBadge } from "@/components/audit/trace-status-badge";
import type { ViewpointLocator } from "@/lib/fixtures/kol-audit";
import {
  ConfidenceMeter,
  DIRECTION_META,
  DirectionTag,
  ReturnChip,
  fmtConfidence,
  fmtDate,
} from "@/components/kol-snapshot/primitives";

const VALIDATION_LABEL: Record<string, string> = {
  verified: "已验证",
  pending: "待验证",
  failed: "未通过",
  under_review: "复核中",
};

function Stage({
  index,
  title,
  en,
  children,
}: {
  index: string;
  title: string;
  en: string;
  children: React.ReactNode;
}) {
  return (
    <section className="editorial-panel rounded-sm p-4">
      <div className="mb-2.5 flex items-baseline gap-3 border-b border-[var(--grid-line)] pb-2">
        <span className="tabular-nums text-sm font-semibold text-[var(--accent-gold)]">
          {index}
        </span>
        <h2 className="text-base leading-none text-[var(--foreground)]">{title}</h2>
        <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--ink-soft)]">
          {en}
        </span>
      </div>
      {children}
    </section>
  );
}

export function ViewpointAudit({ data }: { data: ViewpointLocator }) {
  const { viewpoint: v, kolId, kolName, kolStyle } = data;
  const accent = DIRECTION_META[v.direction].color;
  const settled = v.returnPct !== null && (v.holdingDays ?? 0) > 0;

  return (
    <div className="mx-auto max-w-[860px] px-6 py-8">
      {/* ── Masthead ──────────────────────────────────────────── */}
      <header className="border-b border-[var(--foreground)] pb-4">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] text-[var(--ink-soft)]">
          <span>FINER OS · 证据审计 · EVIDENCE AUDIT</span>
          <Link
            href={`/demo/kol/${kolId}`}
            className="normal-case tracking-normal text-[var(--accent-teal)] hover:underline"
          >
            ← 返回 {kolName} 问责页
          </Link>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-[26px] leading-none text-[var(--foreground)]">
            {v.companyName}
          </h1>
          <span className="tabular-nums text-sm text-[var(--ink-soft)]">
            {v.ticker} · {v.market}
          </span>
          <DirectionTag direction={v.direction} />
          <TraceStatusBadge status={v.traceStatus} />
        </div>
        <div className="mt-1.5 text-[12px] text-[var(--ink-soft)]">
          来自{" "}
          <Link
            href={`/demo/kol/${kolId}`}
            className="text-[var(--foreground)] hover:underline"
          >
            {kolName}
          </Link>
          （{kolStyle}）· {fmtDate(v.timestamp)}
        </div>
      </header>

      {/* ── Honest scope note ─────────────────────────────────── */}
      <p className="mt-4 rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] p-3 text-[12px] leading-relaxed text-[var(--ink-soft)]">
        本页展示该观点在 demo 数据中携带的层：
        <b className="text-[var(--foreground)]">F2 证据 → F5 动作 → F8 回测</b>
        。F3 投资意图 / F4 策略映射层未在 demo 物化；完整 F0→F5 canonical 结构示例见{" "}
        <Link href="/audit" className="text-[var(--accent-teal)] hover:underline">
          证据审计台 /audit →
        </Link>
        。
      </p>

      {/* ── Staged trace ──────────────────────────────────────── */}
      <div className="mt-6 space-y-4">
        <Stage index="F2" title="证据" en="EVIDENCE">
          <blockquote
            className="border-l-2 pl-3 text-[14px] leading-relaxed text-[var(--foreground)]"
            style={{ borderColor: `color-mix(in srgb, ${accent} 50%, transparent)` }}
          >
            “{v.evidenceText}”
          </blockquote>
          <div className="mt-2 text-[11px] text-[var(--ink-soft)]">
            KOL 原话 · 抽取置信度 {fmtConfidence(v.confidence)}
          </div>
        </Stage>

        <div className="rounded-sm border border-dashed border-[var(--table-border)] p-3 text-[12px] leading-relaxed text-[var(--ink-soft)]">
          <span className="font-medium text-[var(--foreground)]">F3 意图 · F4 策略</span>
          {" "}—— 本 demo 观点未物化该两层明细。canonical 示例（含 F3 投资意图 + F4 策略层追溯）见{" "}
          <Link href="/audit" className="text-[var(--accent-teal)] hover:underline">
            /audit →
          </Link>
        </div>

        <Stage index="F5" title="动作" en="ACTION">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <DirectionTag direction={v.direction} />
            <ConfidenceMeter value={v.confidence} />
            <span className="text-[11px] text-[var(--ink-soft)]">
              {VALIDATION_LABEL[v.validationStatus] ?? v.validationStatus}
            </span>
          </div>
          <p className="mt-2 text-[13px] text-[var(--foreground)]">{v.summary}</p>
          <div className="tabular-nums mt-1 text-[11px] text-[var(--ink-soft)]">
            观点时刻 {v.timestamp.slice(0, 16).replace("T", " ")}
          </div>
        </Stage>

        <Stage index="F8" title="回测结果" en="BACKTEST">
          {settled ? (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
              <span className="flex items-baseline gap-1.5">
                <span className="text-[11px] text-[var(--ink-soft)]">跟单兑现</span>
                <ReturnChip value={v.returnPct} />
              </span>
              <span className="tabular-nums text-[12px] text-[var(--ink-soft)]">
                持仓 {v.holdingDays} 天
              </span>
            </div>
          ) : (
            <div className="text-[12px] text-[var(--ink-soft)]">
              {v.returnPct === 0 ? "未触发建仓" : "待回测"}
            </div>
          )}
        </Stage>
      </div>

      <footer className="mt-10 border-t border-[var(--table-border)] pt-4 text-[11px] leading-relaxed text-[var(--ink-soft)]">
        数据为示例 fixture。兑现为 F8 完全跟单回测（已按方向结算）。本页仅展示模型隐含立场，非投资建议。
      </footer>
    </div>
  );
}
