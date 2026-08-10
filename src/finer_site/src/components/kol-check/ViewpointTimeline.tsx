"use client";

/**
 * 观点时间线 — one card per viewpoint (a real F5 TradeAction), time-descending,
 * with the KOL's own words as the evidence quote. Each card expands inline to a
 * canonical F3→F4→F5→F8 audit drawer carrying the REAL trace ids (intent / policy /
 * evidence spans / four execution clocks / backtest outcome). Single-URL, no routing.
 */
import React, { useState } from "react";
import type { SnapshotViewpoint } from "@/demo/kol-check/kol-snapshot";
import type { AuditRecord } from "@/demo/kol-check/fixtures";
import {
  ConfidenceMeter,
  DIRECTION_META,
  DirectionTag,
  ReturnChip,
  fmtDate,
  fmtPct,
} from "./primitives";

const VALIDATION_LABEL: Record<string, string> = {
  verified: "已验证",
  pending: "待验证",
  failed: "未通过",
  under_review: "复核中",
};

const SESSION_LABEL: Record<string, string> = {
  non_trading_day: "非交易时段",
  regular: "盘中",
  pre_market: "盘前",
  after_close: "盘后",
  unknown: "未知",
};

const EXIT_LABEL: Record<string, string> = {
  target_reached: "触及目标",
  stop_loss: "触发止损",
  time_exit: "到期平仓",
  signal_reversal: "信号反转",
  manual: "手动",
  end_of_period: "区间结束",
  unknown: "未知",
};

function shortId(id: string | null): string {
  if (!id) return "—";
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

function clk(iso: string | null): string {
  if (!iso) return "—";
  // trim to minute, drop the timezone tail for compactness
  return iso.slice(0, 16).replace("T", " ");
}

function TraceStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
        {label}
      </span>
      <span className="tabular-nums text-[11px] text-[var(--foreground)]">{value}</span>
    </div>
  );
}

function StageBlock({
  tag,
  title,
  children,
}: {
  tag: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-sm border border-[var(--grid-line)] bg-[var(--surface-muted)] p-2.5">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="rounded-sm bg-[var(--foreground)] px-1 py-0.5 font-mono text-[9px] font-semibold text-[var(--background)]">
          {tag}
        </span>
        <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--ink-soft)]">
          {title}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">{children}</div>
    </div>
  );
}

function AuditDrawer({ audit }: { audit: AuditRecord }) {
  const et = audit.executionTiming;
  const bt = audit.backtest;
  return (
    <div className="mt-2.5 space-y-2 border-t border-dashed border-[var(--grid-line)] pt-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--accent-teal)]">
          Canonical trace · F3 → F4 → F5 → F8
        </span>
        <span
          className="rounded-sm border px-1.5 py-0.5 text-[9px] font-medium"
          style={{
            color: "var(--accent-teal)",
            borderColor: "color-mix(in srgb, var(--accent-teal) 40%, transparent)",
          }}
        >
          {audit.traceStatus ?? "—"}
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <StageBlock tag="F3" title="Intent · 投资意图">
          <TraceStat label="intent_id" value={<span className="font-mono">{shortId(audit.intentId)}</span>} />
          <TraceStat label="信念 conviction" value={audit.conviction != null ? audit.conviction.toFixed(2) : "—"} />
          <TraceStat label="意图动作" value={audit.actionHint ?? "—"} />
          <TraceStat label="层级 tier" value={audit.tier ?? "—"} />
        </StageBlock>

        <StageBlock tag="F4" title="Policy · 策略映射">
          <TraceStat label="policy_id" value={<span className="font-mono">{shortId(audit.policyId)}</span>} />
          <TraceStat label="择时策略" value={et.timingPolicyId ?? "—"} />
          <TraceStat label="提取方式" value={audit.extractionMethod ?? "—"} />
          <TraceStat label="模型" value={audit.modelVersion ?? "—"} />
        </StageBlock>

        <StageBlock tag="F5" title="Execution · 四时钟">
          <TraceStat label="观点发布 (信号)" value={clk(et.intentPublishedAt)} />
          <TraceStat label="决策时刻" value={clk(et.actionDecisionAt)} />
          <TraceStat label="可执行时刻" value={clk(et.actionExecutableAt)} />
          <TraceStat
            label="市场 · 时段"
            value={`${et.market ?? "—"} · ${SESSION_LABEL[et.session ?? "unknown"] ?? et.session}`}
          />
        </StageBlock>

        <StageBlock tag="F8" title="Backtest · 完全跟单回测">
          {bt ? (
            <>
              <TraceStat
                label="跟单收益"
                value={
                  bt.returnPct != null ? (
                    <span
                      className="font-semibold"
                      style={{ color: bt.returnPct > 0 ? "var(--chart-up)" : "var(--chart-down)" }}
                    >
                      {fmtPct(bt.returnPct)}
                    </span>
                  ) : (
                    "—"
                  )
                }
              />
              <TraceStat label="持仓天数" value={bt.holdingDays ?? "—"} />
              <TraceStat label="平仓原因" value={EXIT_LABEL[bt.exitReason ?? "unknown"] ?? bt.exitReason} />
              <TraceStat
                label="最大回撤"
                value={bt.maxDrawdownPct != null ? fmtPct(bt.maxDrawdownPct) : "—"}
              />
            </>
          ) : (
            <div className="col-span-2 text-[11px] text-[var(--ink-soft)]">
              未结算（观点/观望类，无跟单回测）
            </div>
          )}
        </StageBlock>
      </div>

      <div className="text-[10px] leading-relaxed text-[var(--ink-soft)]">
        证据锚点 {audit.evidenceSpanIds.length} 条 F2 span
        {audit.evidenceSpanIds.length ? (
          <span className="ml-1 font-mono">
            （{audit.evidenceSpanIds.slice(0, 2).map(shortId).join(", ")}
            {audit.evidenceSpanIds.length > 2 ? " …" : ""}）
          </span>
        ) : null}
        。回测口径：完全跟单、方向已校正、止损/止盈/最长持有由 F4 策略给定。
      </div>
    </div>
  );
}

function ViewpointRow({
  v,
  audit,
}: {
  v: SnapshotViewpoint;
  audit?: AuditRecord;
}) {
  const [open, setOpen] = useState(false);
  const accent = DIRECTION_META[v.direction].color;
  return (
    <li className="relative pl-5">
      <span
        aria-hidden
        className="absolute left-0 top-1.5 h-2 w-2 -translate-x-1/2 rounded-full"
        style={{ backgroundColor: accent, boxShadow: "0 0 0 3px var(--background)" }}
      />
      <div
        className="editorial-card rounded-sm p-3"
        style={{ borderTopColor: accent }}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="tabular-nums text-xs text-[var(--ink-soft)]">
            {fmtDate(v.timestamp)}
          </span>
          <DirectionTag direction={v.direction} />
          <span className="text-sm font-semibold text-[var(--foreground)]">
            {v.companyName}
          </span>
          <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
            {v.ticker}·{v.market}
          </span>
          <span className="ml-auto flex items-center gap-3">
            <span className="text-[10px] uppercase tracking-wider text-[var(--ink-soft)]">
              {VALIDATION_LABEL[v.validationStatus] ?? v.validationStatus}
            </span>
            <ReturnChip value={v.returnPct} />
          </span>
        </div>

        <p className="mt-1.5 text-[13px] leading-snug text-[var(--foreground)]">
          {v.summary}
        </p>

        <blockquote
          className="mt-2 border-l-2 pl-2.5 text-[12px] leading-relaxed text-[var(--ink-soft)]"
          style={{ borderColor: `color-mix(in srgb, ${accent} 40%, transparent)` }}
        >
          “{v.evidenceText}”
        </blockquote>

        <div className="mt-2 flex items-center justify-between">
          <ConfidenceMeter value={v.confidence} />
          <span className="flex items-center gap-3">
            {v.holdingDays && v.holdingDays > 0 ? (
              <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                持仓 {v.holdingDays} 天
              </span>
            ) : null}
            {audit ? (
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="text-[11px] text-[var(--accent-teal)] transition-opacity hover:opacity-70"
                aria-expanded={open}
              >
                {open ? "收起证据链 ▴" : "证据链 · 溯源 ▾"}
              </button>
            ) : null}
          </span>
        </div>

        {open && audit ? <AuditDrawer audit={audit} /> : null}
      </div>
    </li>
  );
}

export function ViewpointTimeline({
  viewpoints,
  auditById,
}: {
  viewpoints: SnapshotViewpoint[];
  auditById: Record<string, AuditRecord>;
}) {
  return (
    <ol className="relative space-y-3 before:absolute before:left-0 before:top-1 before:h-full before:w-px before:bg-[var(--grid-line)]">
      {viewpoints.map((v) => (
        <ViewpointRow key={v.id} v={v} audit={auditById[v.id]} />
      ))}
    </ol>
  );
}
