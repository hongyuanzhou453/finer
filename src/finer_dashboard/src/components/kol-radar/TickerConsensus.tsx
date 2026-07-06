/**
 * 标的共识 / 拥挤 (ticker consensus & crowding) — an aggregate-only signal:
 * how many distinct KOLs currently lean long vs. short on the same name, where
 * they diverge, and where the crowd has piled in. Mirrors the reference page's
 * "板块轮动 + 拥挤预警" panel. Pure props render, no client state.
 */
import Link from "next/link";
import {
  DIRECTION_META,
  ReturnChip,
} from "@/components/kol-snapshot/primitives";
import type { ConsensusRow } from "@/lib/fixtures/kol-radar";

const BULL_COLOR = DIRECTION_META.bullish.color; // 红 = 看多 (China convention)
const BEAR_COLOR = DIRECTION_META.bearish.color; // 绿 = 看空

/** netLabel → chip color. 共识看多=红, 共识看空=绿, 分歧=teal, 观望=灰.
 *  (teal owns "分歧" so the chip and the SignalTag below agree; gold is reserved for 拥挤.) */
function netLabelColor(label: ConsensusRow["netLabel"]): string {
  switch (label) {
    case "共识看多":
      return "var(--chart-up)";
    case "共识看空":
      return "var(--chart-down)";
    case "分歧":
      return "var(--accent-teal)";
    default:
      return "#8a8278"; // 观望
  }
}

/** Emphasis rule: divergence shades the top rule teal, crowding gold. */
function topRuleColor(row: ConsensusRow): string {
  if (row.diverging) return "var(--accent-teal)";
  if (row.crowded) return "var(--accent-gold)";
  return "transparent";
}

function NetLabelChip({ label }: { label: ConsensusRow["netLabel"] }) {
  const color = netLabelColor(label);
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium"
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 32%, transparent)`,
      }}
    >
      {label}
    </span>
  );
}

function SignalTag({ text, color }: { text: string; color: string }) {
  return (
    <span
      className="inline-flex items-center rounded-sm px-1 py-px text-[10px] font-medium tracking-wide"
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)`,
      }}
    >
      {text}
    </span>
  );
}

/** Bull/bear split bar — left red segment ∝ bull, right green segment ∝ bear. */
function BullBearBar({ bull, bear }: { bull: number; bear: number }) {
  const total = bull + bear;
  const bullPct = total > 0 ? (bull / total) * 100 : 0;
  const bearPct = total > 0 ? (bear / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-1.5 flex-1 overflow-hidden rounded-sm bg-[var(--surface-muted)]">
        <div style={{ width: `${bullPct}%`, backgroundColor: BULL_COLOR }} />
        <div style={{ width: `${bearPct}%`, backgroundColor: BEAR_COLOR }} />
      </div>
      <span className="tabular-nums shrink-0 text-[10px] text-[var(--ink-soft)]">
        <span style={{ color: BULL_COLOR }}>{bull} 多</span>
        {" / "}
        <span style={{ color: BEAR_COLOR }}>{bear} 空</span>
      </span>
    </div>
  );
}

function ConsensusCard({ row }: { row: ConsensusRow }) {
  return (
    <div
      className="editorial-card rounded-sm p-3"
      style={{ borderTopColor: topRuleColor(row), borderTopWidth: "3px" }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--foreground)]">
            {row.companyName}
          </div>
          <div className="tabular-nums mt-0.5 text-[10px] text-[var(--ink-soft)]">
            {row.ticker}
            <span className="mx-1 text-[var(--grid-line)]">·</span>
            {row.market}
          </div>
        </div>
        <NetLabelChip label={row.netLabel} />
      </div>

      <div className="mt-2.5">
        <BullBearBar bull={row.bull} bear={row.bear} />
      </div>

      <div className="mt-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {row.diverging ? (
            <SignalTag text="分歧" color="var(--accent-teal)" />
          ) : null}
          {row.crowded ? (
            row.avgReturn !== null && row.avgReturn < 0 ? (
              <SignalTag text="拥挤打脸" color="var(--chart-down)" />
            ) : (
              <SignalTag text="拥挤" color="var(--accent-gold)" />
            )
          ) : null}
        </div>
        <div className="flex shrink-0 items-baseline gap-1">
          <span className="text-[10px] text-[var(--ink-soft)]">平均兑现</span>
          <ReturnChip value={row.avgReturn} />
        </div>
      </div>

      <div className="tabular-nums mt-2 truncate border-t border-[var(--grid-line)] pt-1.5 text-[10px] text-[var(--ink-soft)]">
        {row.kolNames.join(" · ")}
      </div>
    </div>
  );
}

export function TickerConsensus({ rows }: { rows: ConsensusRow[] }) {
  const visible = rows.slice(0, 8);
  if (!visible.length) {
    return (
      <p className="text-[13px] text-[var(--ink-soft)]">暂无多 KOL 覆盖标的。</p>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {visible.map((row) => (
        <Link
          key={row.ticker}
          href={`/demo/ticker/${row.ticker}`}
          className="block transition-opacity hover:opacity-90"
          aria-label={`${row.companyName} 标的横截面`}
        >
          <ConsensusCard row={row} />
        </Link>
      ))}
    </div>
  );
}
