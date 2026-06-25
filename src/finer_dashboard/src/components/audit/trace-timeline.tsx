"use client";

import Link from "next/link";
import { ArrowUpRight, GitBranch, Unlink } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  ActionStep,
  ActionType,
  AuditTraceBundle,
  TradeDirection,
} from "@/lib/contracts";
import { IntentCard } from "./intent-card";
import { PolicyTraceCard } from "./policy-trace-card";
import { TraceStatusBadge } from "./trace-status-badge";
import { Pill, SectionLabel, type Tone } from "./primitives";

const ACTION_TYPE: Record<ActionType, string> = {
  long: "做多",
  short: "做空",
  close_long: "平多",
  close_short: "平空",
  buy_call: "买入看涨",
  sell_call: "卖出看涨",
  buy_put: "买入看跌",
  sell_put: "卖出看跌",
  hold: "持有",
  watch: "观察",
  buy_and_hold: "买入持有",
};

const DIRECTION: Record<TradeDirection, { label: string; tone: Tone }> = {
  bullish: { label: "看多", tone: "red" },
  bearish: { label: "看空", tone: "green" },
  neutral: { label: "中性", tone: "neutral" },
  watchlist: { label: "观察", tone: "gold" },
  risk_warning: { label: "风险提示", tone: "green" },
};

function StageNode({
  stage,
  role,
  broken = false,
  isLast = false,
  children,
}: {
  stage: string;
  role: string;
  broken?: boolean;
  isLast?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      {/* rail */}
      <div className="flex flex-col items-center">
        <div
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold",
            broken
              ? "border-[var(--table-border)] bg-[var(--surface-muted)] text-foreground/30"
              : "border-morningstar-red/25 bg-[rgba(225,27,34,0.08)] text-morningstar-red",
          )}
        >
          {stage.replace("F", "")}
        </div>
        {!isLast && <div className="mt-1 w-px flex-1 bg-[var(--table-border)]" />}
      </div>

      {/* content */}
      <div className="min-w-0 flex-1 pb-5">
        <div className="mb-1.5 flex items-center gap-2">
          <span
            className={cn(
              "text-[12px] font-bold tracking-tight",
              broken ? "text-foreground/40" : "text-foreground",
            )}
          >
            {stage}
          </span>
          <span className="rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.12em] text-[var(--ink-soft)]">
            {role}
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}

function BrokenStage({ what }: { what: string }) {
  return (
    <div className="flex items-start gap-2 rounded-sm border border-dashed border-[var(--table-border)] bg-[var(--surface-muted)]/60 px-3 py-2.5">
      <Unlink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-foreground/30" strokeWidth={1.8} />
      <p className="text-[11px] leading-5 text-[var(--ink-soft)]">{what}</p>
    </div>
  );
}

function ActionChainStep({ step }: { step: ActionStep }) {
  const price =
    step.target_price_low != null || step.target_price_high != null
      ? `${step.target_price_low ?? "—"} ~ ${step.target_price_high ?? "—"}`
      : null;
  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-white px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] font-bold text-foreground/50">#{step.sequence}</span>
        <Pill tone="red">{ACTION_TYPE[step.action_type] ?? step.action_type}</Pill>
        {step.trigger_condition && (
          <span className="text-[12px] text-foreground/80">{step.trigger_condition}</span>
        )}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-foreground/45">
        <span>trigger: {step.trigger_type}</span>
        {price && <span>price: {price}</span>}
        {step.position_size_pct != null && (
          <span>size: {Math.round(step.position_size_pct * 100)}%</span>
        )}
      </div>
      {step.notes && <p className="mt-1 text-[11px] text-[var(--ink-soft)]">{step.notes}</p>}
    </div>
  );
}

export function TraceTimeline({
  bundle,
  activeSpanId,
  onHoverSpan,
}: {
  bundle: AuditTraceBundle;
  activeSpanId: string | null;
  onHoverSpan: (id: string | null) => void;
}) {
  const { trade_action: ta, intent, policy, envelope } = bundle;
  const dir = DIRECTION[ta.direction];

  return (
    <div>
      {/* F3 Intent */}
      <StageNode stage="F3" role="AI · Intent">
        {intent ? (
          <IntentCard intent={intent} activeSpanId={activeSpanId} onHoverSpan={onHoverSpan} />
        ) : (
          <BrokenStage what="无 F3 Intent。该动作未经投资意图归一化，缺少 direction / actionability / 仓位动作等结构化语义，无法核验“观点是否被正确理解”。" />
        )}
      </StageNode>

      {/* F4 Policy */}
      <StageNode stage="F4" role="规则 · Policy">
        {policy ? (
          <PolicyTraceCard policy={policy} />
        ) : (
          <BrokenStage what="无 F4 Policy。Intent 未经策略映射，仓位、持有期与风险约束均未确定，无法解释“为什么这条意图变成了这个动作”。" />
        )}
      </StageNode>

      {/* F5 TradeAction */}
      <StageNode stage="F5" role="AI · TradeAction" isLast>
        <div className="rounded-sm border border-[var(--table-border)] bg-white p-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[13px] font-bold text-foreground">
              {ta.target.ticker}
            </span>
            <span className="text-[12px] text-foreground/55">{ta.target.company_name}</span>
            <Pill tone={dir.tone}>{dir.label}</Pill>
            <span className="grow" />
            <TraceStatusBadge status={ta.canonical_trace_status} size="sm" />
          </div>

          {ta.rationale && (
            <p className="mt-2 text-[12px] leading-6 text-foreground/80">{ta.rationale}</p>
          )}

          <div className="mt-3">
            <SectionLabel>执行链 · action_chain</SectionLabel>
            <div className="mt-1.5 space-y-1.5">
              {ta.action_chain.map((s) => (
                <ActionChainStep key={s.sequence} step={s} />
              ))}
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between border-t border-[var(--grid-line)] pt-2.5 font-mono text-[10px] text-foreground/45">
            <span>{ta.extraction_method}</span>
            <span>{ta.model_version}</span>
          </div>

          {envelope.kol_id && (
            <Link
              href={`/kol/${envelope.kol_id}/backtest`}
              className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-semibold text-morningstar-red transition-colors hover:text-morningstar-red/80"
            >
              <GitBranch className="h-3.5 w-3.5" strokeWidth={1.8} />
              查看该 KOL 完整回测审计
              <ArrowUpRight className="h-3 w-3" strokeWidth={2} />
            </Link>
          )}
        </div>
      </StageNode>
    </div>
  );
}
