import { cn } from "@/lib/utils";

export type Tone = "red" | "green" | "gold" | "neutral";

const TONE_CLS: Record<Tone, string> = {
  red: "bg-[rgba(225,27,34,0.1)] text-morningstar-red",
  green: "bg-[rgba(16,185,129,0.12)] text-[#0f9b6c]",
  gold: "bg-[rgba(155,123,69,0.14)] text-[var(--accent-gold)]",
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

/** Horizontal 0..1 meter (conviction / confidence). */
export function Meter({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <span
          className="block h-full rounded-full bg-morningstar-red"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="tabular-nums text-[11px] text-foreground/70">{pct}%</span>
    </span>
  );
}
