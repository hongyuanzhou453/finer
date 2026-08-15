import { cn } from "@/lib/utils";

export type Tone = "red" | "green" | "gold" | "teal" | "neutral";

/**
 * 方向语义配色：红=看多/上涨、绿=看空/下跌（中国惯例）、teal=风险提示
 * （与 kol-snapshot/crd 的 DIRECTION_META 同词表）。值一律走 token——
 * 此前 green 硬编码 #0f9b6c，与 --chart-down(#10b981) 同屏打架。
 */
const TONE_CLS: Record<Tone, string> = {
  red: "bg-[color-mix(in_srgb,var(--chart-up)_10%,transparent)] text-[color:var(--chart-up)]",
  green:
    "bg-[color-mix(in_srgb,var(--chart-down)_12%,transparent)] text-[color:var(--chart-down)]",
  gold: "bg-[color-mix(in_srgb,var(--accent-gold)_14%,transparent)] text-[var(--accent-gold)]",
  teal: "bg-[color-mix(in_srgb,var(--accent-teal)_12%,transparent)] text-[var(--accent-teal)]",
  neutral: "bg-[var(--surface-muted)] text-[var(--ink-soft)]",
};

export function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: Tone;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-bold",
        TONE_CLS[tone],
      )}
    >
      {children}
    </span>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
      {children}
    </div>
  );
}

export function FieldRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="shrink-0 text-[11px] text-foreground/45">{label}</span>
      <span className="min-w-0 text-right text-[12px] text-foreground/80">{children}</span>
    </div>
  );
}

/**
 * Horizontal 0..1 meter (conviction / confidence).
 * 置信度不是方向，填充用中性 accent-gold——红色填充会被读成警报或
 * 上涨语义（与 crd/kol-check 的 ConfidenceMeter 同口径）。
 */
export function Meter({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <span
          className="block h-full rounded-full bg-[var(--accent-gold)]"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="tabular-nums text-[11px] text-foreground/70">{pct}%</span>
    </span>
  );
}
