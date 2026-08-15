import { ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CanonicalTraceStatus } from "@/lib/contracts";

const META: Record<
  CanonicalTraceStatus,
  { label: string; cls: string; Icon: typeof ShieldCheck }
> = {
  // canonical=链路完整是「成功」语义，不是行情方向——走 --color-success，
  // 别与 --chart-down 的「下跌绿」混用同一字面量。
  canonical: {
    label: "Canonical",
    cls: "border-success/30 bg-success/10 text-success",
    Icon: ShieldCheck,
  },
  partial: {
    label: "Partial",
    cls: "border-[var(--accent-gold)]/40 bg-[rgba(155,123,69,0.14)] text-[var(--accent-gold)]",
    Icon: ShieldAlert,
  },
  non_canonical: {
    label: "Non-canonical",
    cls: "border-[var(--table-border)] bg-[var(--surface-muted)] text-[var(--ink-soft)]",
    Icon: ShieldX,
  },
};

export function TraceStatusBadge({
  status,
  size = "md",
}: {
  status: CanonicalTraceStatus;
  size?: "sm" | "md";
}) {
  const m = META[status];
  const Icon = m.Icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border font-bold uppercase tracking-[0.1em]",
        m.cls,
        size === "sm" ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]",
      )}
    >
      <Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} strokeWidth={1.8} />
      {m.label}
    </span>
  );
}
