import { Clock } from "lucide-react";
import type { ExecutionTiming, MarketSession } from "@/lib/contracts";

const CLOCKS: { key: keyof ExecutionTiming; label: string; hint: string }[] = [
  { key: "intent_published_at", label: "intent_published_at", hint: "KOL 发布观点时刻" },
  { key: "intent_effective_at", label: "intent_effective_at", hint: "意图生效时刻" },
  { key: "action_decision_at", label: "action_decision_at", hint: "系统决策时刻" },
  { key: "action_executable_at", label: "action_executable_at", hint: "可成交时刻（防前视）" },
];

const SESSION_LABEL: Record<MarketSession, string> = {
  pre_market: "盘前",
  regular: "盘中",
  after_close: "收盘后",
  non_trading_day: "非交易日",
  unknown: "未知",
};

export function ExecutionClocks({ timing }: { timing?: ExecutionTiming }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
        <Clock className="h-3 w-3" strokeWidth={2} />
        四时钟 · ExecutionTiming（F5）
      </div>

      {!timing ? (
        <div className="mt-1.5 rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-3 py-2.5 text-[11px] leading-5 text-[var(--ink-soft)]">
          legacy 直提，无执行时钟。无法区分发布 / 生效 / 决策 / 可成交四个时点，
          回测存在前视偏差风险。
        </div>
      ) : (
        <>
          <dl className="mt-1.5 divide-y divide-[var(--grid-line)] rounded-sm border border-[var(--table-border)] bg-white font-mono text-[11px]">
            {CLOCKS.map(({ key, label, hint }) => {
              const v = timing[key];
              return (
                <div key={key} className="flex items-baseline gap-2 px-3 py-1.5">
                  <dt className="w-40 shrink-0 text-foreground/50" title={hint}>
                    {label}
                  </dt>
                  <dd className="min-w-0 break-words text-foreground/85">
                    {typeof v === "string" && v ? v : <span className="text-foreground/30">—</span>}
                  </dd>
                </div>
              );
            })}
          </dl>
          <div className="mt-1.5 font-mono text-[10px] text-foreground/40">
            session @ publish: {SESSION_LABEL[timing.market_session_at_publish]} · {timing.market} ·{" "}
            {timing.timezone}
          </div>
          {timing.execution_delay_reason && (
            <div className="mt-1 text-[10px] leading-4 text-[var(--ink-soft)]">
              延迟原因：{timing.execution_delay_reason}
            </div>
          )}
        </>
      )}
    </div>
  );
}
