"use client";

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  PolicyDecision,
  PolicyLayerTrace,
  PolicyMappingResult,
} from "@/lib/contracts";
import { FieldRow, Meter, Pill, SectionLabel } from "./primitives";

const ACTION_HINT: Record<string, string> = {
  watch_only: "仅观察",
  watch_or_no_trade: "观察/不交易",
  avoid_or_watch_risk: "规避/风险观察",
  open_position: "开仓",
  add_position: "加仓",
  reduce_position: "减仓",
  hold_position: "持有",
  close_position: "平仓",
  review_required: "待审核",
};

const SIZING_HINT: Record<string, string> = {
  none: "无",
  small: "小",
  medium: "中",
  large: "大",
  review_required: "待审核",
};

const HOLDING_HINT: Record<string, string> = {
  intraday: "日内",
  short_term: "短线",
  medium_term: "中线",
  long_term: "长线",
  review_required: "待审核",
};

const DECISION_TYPE: Record<string, string> = {
  action_override: "动作覆盖",
  sizing_adjust: "仓位调整",
  holding_adjust: "持有期调整",
  risk_bound: "风险约束",
  confidence_adjust: "置信度调整",
  human_escalation: "人工升级",
  no_op: "无操作",
};

const MAX_POSITION: Record<string, string> = {
  none: "无",
  small: "小",
  medium: "中",
  large: "大",
};

function LayerTrace({ layer }: { layer: PolicyLayerTrace }) {
  return (
    <div
      className={cn(
        "rounded-sm border px-2.5 py-2",
        layer.applied
          ? "border-[var(--table-border)] bg-white"
          : "border-dashed border-[var(--table-border)] bg-[var(--surface-muted)]/50",
      )}
    >
      <div className="flex items-center gap-2">
        {layer.applied ? (
          <Check className="h-3.5 w-3.5 shrink-0 text-[#0f9b6c]" strokeWidth={2.2} />
        ) : (
          <X className="h-3.5 w-3.5 shrink-0 text-foreground/30" strokeWidth={2.2} />
        )}
        <span
          className={cn(
            "text-[12px] font-bold",
            layer.applied ? "text-foreground" : "text-foreground/40",
          )}
        >
          {layer.layer_name}
        </span>
        <span className="font-mono text-[10px] text-foreground/40">v{layer.layer_version}</span>
      </div>
      <p className="mt-1 text-[11px] leading-5 text-[var(--ink-soft)]">{layer.reason}</p>
      {layer.modifications.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {layer.modifications.map((m, i) => (
            <li key={i} className="text-[11px] text-foreground/70">
              · {m}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Decision({ decision }: { decision: PolicyDecision }) {
  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-white px-2.5 py-2">
      <div className="flex items-center gap-2">
        <Pill tone="gold">{DECISION_TYPE[decision.decision_type] ?? decision.decision_type}</Pill>
        <span className="text-[12px] text-foreground/85">{decision.description}</span>
        {decision.overrides_previous && (
          <span className="font-mono text-[9px] uppercase tracking-wide text-morningstar-red">
            override
          </span>
        )}
      </div>
      <p className="mt-1 text-[11px] leading-5 text-[var(--ink-soft)]">{decision.rationale}</p>
    </div>
  );
}

export function PolicyTraceCard({ policy }: { policy: PolicyMappingResult }) {
  const rc = policy.risk_constraints;
  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-white p-3.5">
      {/* hints */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone="red">{ACTION_HINT[policy.action_hint] ?? policy.action_hint}</Pill>
        <span className="text-[11px] text-foreground/45">仓位</span>
        <Pill>{SIZING_HINT[policy.position_sizing_hint] ?? policy.position_sizing_hint}</Pill>
        <span className="text-[11px] text-foreground/45">持有</span>
        <Pill>{HOLDING_HINT[policy.holding_period_hint] ?? policy.holding_period_hint}</Pill>
      </div>

      <p className="mt-2.5 text-[12px] leading-6 text-foreground/80">{policy.mapping_rationale}</p>

      {/* layer traces — 核心：逐层是否生效 + 原因 */}
      <div className="mt-3">
        <SectionLabel>策略分层 · layer_traces</SectionLabel>
        <div className="mt-1.5 space-y-1.5">
          {policy.layer_traces.map((l) => (
            <LayerTrace key={`${l.layer_name}-${l.order_index}`} layer={l} />
          ))}
        </div>
      </div>

      {/* decisions */}
      {policy.decisions.length > 0 && (
        <div className="mt-3">
          <SectionLabel>策略决策 · decisions</SectionLabel>
          <div className="mt-1.5 space-y-1.5">
            {policy.decisions.map((d) => (
              <Decision key={d.decision_id} decision={d} />
            ))}
          </div>
        </div>
      )}

      {/* risk constraints */}
      <div className="mt-3">
        <SectionLabel>风险约束 · risk_constraints</SectionLabel>
        <div className="mt-1.5 divide-y divide-[var(--grid-line)] rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] px-2.5">
          <FieldRow label="最大仓位">{MAX_POSITION[rc.max_position_hint] ?? rc.max_position_hint}</FieldRow>
          <FieldRow label="需人工复核">
            {rc.requires_human_review ? (
              <span className="text-[var(--accent-gold)]">是</span>
            ) : (
              <span className="text-[#0f9b6c]">否</span>
            )}
          </FieldRow>
          {typeof rc.max_concentration_pct === "number" && (
            <FieldRow label="集中度上限">{rc.max_concentration_pct}%</FieldRow>
          )}
          {rc.stop_loss_hint && <FieldRow label="止损提示">{rc.stop_loss_hint}</FieldRow>}
          {typeof rc.time_decay_days === "number" && (
            <FieldRow label="时间衰减">{rc.time_decay_days} 天</FieldRow>
          )}
        </div>
        {rc.risk_notes.length > 0 && (
          <ul className="mt-1.5 space-y-0.5">
            {rc.risk_notes.map((n, i) => (
              <li key={i} className="text-[11px] text-[var(--ink-soft)]">
                · {n}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-3 border-t border-[var(--grid-line)] pt-2">
        <FieldRow label="映射置信度 · confidence">
          <Meter value={policy.confidence} />
        </FieldRow>
      </div>
    </div>
  );
}
