"use client";

import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  IntentActionability,
  IntentDirection,
  IntentRiskPreference,
  IntentTargetType,
  IntentTimeHorizon,
  NormalizedInvestmentIntent,
  PositionDeltaHint,
} from "@/lib/contracts";
import { FieldRow, Meter, Pill, SectionLabel, type Tone } from "./primitives";

const DIRECTION: Record<IntentDirection, { label: string; tone: Tone }> = {
  bullish: { label: "看多", tone: "red" },
  bearish: { label: "看空", tone: "green" },
  neutral: { label: "中性", tone: "neutral" },
  mixed: { label: "分歧", tone: "gold" },
  unknown: { label: "未知", tone: "neutral" },
};

const ACTIONABILITY: Record<IntentActionability, { label: string; tone: Tone }> = {
  opinion: { label: "纯观点", tone: "neutral" },
  watch: { label: "观察", tone: "gold" },
  explicit_action: { label: "明确行动", tone: "red" },
  review_required: { label: "待审核", tone: "gold" },
};

const POSITION_DELTA: Record<PositionDeltaHint, string> = {
  open: "开仓",
  add: "加仓",
  reduce: "减仓",
  hold: "持有",
  exit: "清仓",
  none: "无变动",
  unknown: "未知",
};

const TIME_HORIZON: Record<IntentTimeHorizon, string> = {
  intraday: "日内",
  short_term: "短线",
  medium_term: "中线",
  long_term: "长线",
  unknown: "未知",
};

const RISK_PREF: Record<IntentRiskPreference, string> = {
  aggressive: "激进",
  balanced: "均衡",
  conservative: "保守",
  unknown: "未知",
};

const TARGET_TYPE: Record<IntentTargetType, string> = {
  stock: "个股",
  sector: "板块",
  index: "指数",
  macro: "宏观",
  commodity: "商品",
  crypto: "加密",
  unknown: "未知",
};

export function IntentCard({
  intent,
  activeSpanId,
  onHoverSpan,
}: {
  intent: NormalizedInvestmentIntent;
  activeSpanId?: string | null;
  onHoverSpan?: (id: string | null) => void;
}) {
  const dir = DIRECTION[intent.direction];
  const act = ACTIONABILITY[intent.actionability];

  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-white p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-bold text-foreground">{intent.target_name}</span>
        {intent.target_symbol && (
          <span className="font-mono text-[12px] text-foreground/45">{intent.target_symbol}</span>
        )}
        <Pill>{TARGET_TYPE[intent.target_type]}</Pill>
        <span className="grow" />
        <Pill tone={dir.tone}>{dir.label}</Pill>
        <Pill tone={act.tone}>{act.label}</Pill>
      </div>

      <div className="mt-2.5 divide-y divide-[var(--grid-line)]">
        <FieldRow label="仓位动作 · position_delta">
          {POSITION_DELTA[intent.position_delta_hint]}
        </FieldRow>
        <FieldRow label="信念 · conviction">
          <Meter value={intent.conviction} />
        </FieldRow>
        {typeof intent.sentiment_score === "number" && (
          <FieldRow label="情绪 · sentiment">
            <span className="tabular-nums">{intent.sentiment_score.toFixed(2)}</span>
          </FieldRow>
        )}
        <FieldRow label="周期 · time_horizon">{TIME_HORIZON[intent.time_horizon_hint]}</FieldRow>
        <FieldRow label="风险偏好 · risk_pref">{RISK_PREF[intent.risk_preference_hint]}</FieldRow>
        <FieldRow label="置信度 · confidence">
          <Meter value={intent.confidence} />
        </FieldRow>
      </div>

      {intent.ambiguity_flags.length > 0 && (
        <div className="mt-2.5 flex items-start gap-1.5 rounded-sm border border-[var(--accent-gold)]/30 bg-[rgba(155,123,69,0.08)] px-2.5 py-1.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--accent-gold)]" strokeWidth={1.8} />
          <div className="text-[11px] leading-5 text-[var(--ink-soft)]">
            {intent.ambiguity_flags.map((f) => (
              <div key={f}>{f}</div>
            ))}
          </div>
        </div>
      )}

      {intent.evidence_span_ids.length > 0 && (
        <div className="mt-2.5">
          <SectionLabel>支撑证据 · evidence_span_ids</SectionLabel>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {intent.evidence_span_ids.map((id) => (
              <button
                key={id}
                type="button"
                onMouseEnter={() => onHoverSpan?.(id)}
                onMouseLeave={() => onHoverSpan?.(null)}
                className={cn(
                  "rounded-sm border px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                  activeSpanId === id
                    ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.06)] text-morningstar-red"
                    : "border-[var(--table-border)] bg-[var(--surface-strong)] text-foreground/55 hover:border-foreground/25",
                )}
              >
                {id}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
