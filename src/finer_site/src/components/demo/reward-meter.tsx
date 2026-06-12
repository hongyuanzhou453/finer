"use client";

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RewardBreakdown } from "@/demo/types";

type Tone = "chosen" | "rejected" | "neutral";

const TONE_ACCENT: Record<Tone, string> = {
  chosen: "var(--chart-up, #0f9b6c)",
  rejected: "var(--morningstar-red)",
  neutral: "var(--accent-gold)",
};

function AxisBar({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 text-[10px] text-foreground/50">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.round(value * 100)}%`, backgroundColor: accent }}
        />
      </div>
      <span className="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-foreground/70">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function RewardCard({
  label,
  tone,
  reward,
}: {
  label: string;
  tone: Tone;
  reward: RewardBreakdown;
}) {
  const accent = TONE_ACCENT[tone];
  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-white p-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold text-foreground/70">{label}</span>
        <div className="flex items-center gap-1.5">
          {reward.structurePass ? (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-[#0f9b6c]">
              <Check className="h-3 w-3" strokeWidth={2.5} /> 结构门
            </span>
          ) : (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-morningstar-red">
              <X className="h-3 w-3" strokeWidth={2.5} /> 结构门
            </span>
          )}
        </div>
      </div>

      <div className="mt-1.5 flex items-baseline gap-1.5">
        <span className="font-mono text-[24px] font-bold leading-none tabular-nums" style={{ color: accent }}>
          {reward.total.toFixed(2)}
        </span>
        <span className="text-[10px] text-foreground/40">total reward</span>
      </div>

      <div className="mt-2.5 space-y-1.5">
        <AxisBar label="grounding" value={reward.grounding} accent={accent} />
        <AxisBar label="calibration" value={reward.calibration} accent={accent} />
        <AxisBar label="abstention" value={reward.abstention} accent={accent} />
      </div>

      <ul className="mt-2.5 space-y-0.5 border-t border-[var(--grid-line)] pt-2">
        {reward.notes.map((n, i) => (
          <li key={i} className="flex items-start gap-1.5 text-[10px] leading-4 text-foreground/55">
            <span className="mt-[5px] h-0.5 w-0.5 shrink-0 rounded-full bg-foreground/30" />
            {n}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * RLVR verifier panel. Renders 1-2 candidate reward breakdowns side by side
 * (e.g. chosen vs rejected), with the deterministic axes and the margin between
 * them. The scores come from scoreExtraction() — rule-based, free, reproducible.
 */
export function RewardMeter({
  items,
  caption,
}: {
  items: { label: string; tone: Tone; reward: RewardBreakdown }[];
  caption?: string;
}) {
  const margin =
    items.length === 2 ? Math.abs(items[0].reward.total - items[1].reward.total) : null;

  return (
    <div>
      <div className="space-y-2.5">
        {items.map((it) => (
          <RewardCard key={it.label} label={it.label} tone={it.tone} reward={it.reward} />
        ))}
      </div>

      {margin != null && (
        <div className="mt-2.5 flex items-center justify-between rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] px-3 py-2">
          <span className="text-[11px] text-foreground/55">reward margin</span>
          <span
            className={cn(
              "font-mono text-[13px] font-bold tabular-nums",
              margin >= 0.2 ? "text-[#0f9b6c]" : "text-[var(--accent-gold)]",
            )}
          >
            {margin.toFixed(2)} {margin >= 0.2 ? "· 偏好信号充分" : "· 近似平手，转人工"}
          </span>
        </div>
      )}

      {caption && <p className="mt-2 text-[10px] leading-4 text-foreground/45">{caption}</p>}
    </div>
  );
}
