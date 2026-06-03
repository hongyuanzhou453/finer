import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

type Role = "AI" | "人" | "规则";
type Stage = { id: string; name: string; desc: string; role: Role };

const STAGES: Stage[] = [
  { id: "F0", name: "Intake",      desc: "多源接入",       role: "规则" },
  { id: "F1", name: "Standardize", desc: "内容标准化",     role: "AI" },
  { id: "F2", name: "Anchor",      desc: "实体/时间锚定",  role: "规则" },
  { id: "F3", name: "Intent",      desc: "投资意图",       role: "AI" },
  { id: "F4", name: "Policy",      desc: "策略映射",       role: "规则" },
  { id: "F5", name: "Execute",     desc: "TradeAction",    role: "AI" },
  { id: "F6", name: "Review",      desc: "人工复核",       role: "人" },
  { id: "F7", name: "Timeline",    desc: "观点编年史",     role: "规则" },
  { id: "F8", name: "Backtest",    desc: "回测评分",       role: "规则" },
];

const ROLE_STYLE: Record<Role, string> = {
  // China-convention red as AI signal (consistent with brand accent)
  AI: "bg-[rgba(225,27,34,0.08)] text-morningstar-red border border-[rgba(225,27,34,0.18)]",
  // Gold for human — picks up the editorial accent-gold token
  人: "bg-[rgba(155,123,69,0.12)] text-[var(--accent-gold)] border border-[rgba(155,123,69,0.25)]",
  // Muted for deterministic rules
  规则: "bg-[var(--surface-muted)] text-[var(--ink-soft)] border border-[var(--table-border)]",
};

/** Canonical F0-F8 pipeline as a compact editorial strip with role labels. */
export function PipelineStrip() {
  return (
    <div className="overflow-x-auto finer-scrollbar">
      <ol className="flex min-w-[820px] items-stretch">
        {STAGES.map((stage, i) => (
          <li key={stage.id} className="flex flex-1 items-stretch">
            <div className="flex-1 border-t-2 border-[var(--foreground)] bg-[var(--surface-strong)] px-3 py-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold tabular-nums tracking-[0.16em] text-morningstar-red">
                  {stage.id}
                </span>
                <span
                  className={cn(
                    "rounded-sm px-1.5 py-0.5 text-[10px] font-bold tracking-wider",
                    ROLE_STYLE[stage.role],
                  )}
                >
                  {stage.role}
                </span>
              </div>
              <div className="mt-1.5 text-[13px] font-semibold text-foreground">
                {stage.name}
              </div>
              <div className="mt-0.5 text-[11px] leading-snug text-[var(--ink-soft)]">
                {stage.desc}
              </div>
            </div>
            {i < STAGES.length - 1 && (
              <div className="flex items-center px-0.5 text-foreground/25">
                <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-[var(--ink-soft)]">
        <span className="font-bold uppercase tracking-[0.14em] text-foreground/45">
          Role
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("rounded-sm px-1.5 py-0.5 text-[10px] font-bold", ROLE_STYLE.AI)}>AI</span>
          LLM 抽取 / 视觉
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("rounded-sm px-1.5 py-0.5 text-[10px] font-bold", ROLE_STYLE["人"])}>人</span>
          RLHF 复核
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("rounded-sm px-1.5 py-0.5 text-[10px] font-bold", ROLE_STYLE["规则"])}>规则</span>
          确定性策略 / 计算
        </span>
      </div>
    </div>
  );
}
