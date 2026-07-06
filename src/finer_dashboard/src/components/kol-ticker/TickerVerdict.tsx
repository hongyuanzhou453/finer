/**
 * L3 标的横截面 · 英雄区 — 众 KOL 裁决。
 * 左列给共识研判（大号 netLabel + 多空广度 + 信号徽标 + 三个 stat），
 * 右列给横截面叙事。红=涨/看多/盈，绿=跌/看空/亏（中国惯例）。
 */
import React from "react";
import type {
  ConsensusNetLabel,
  TickerCrossSection,
} from "@/lib/fixtures/kol-ticker";
import { DIRECTION_META, ReturnChip } from "@/components/kol-snapshot/primitives";

// 共识标签语义色：看多红 / 看空绿 / 分歧 teal / 观望 ink
const CONSENSUS_COLOR: Record<ConsensusNetLabel, string> = {
  共识看多: "var(--chart-up)",
  共识看空: "var(--chart-down)",
  分歧: "var(--accent-teal)",
  观望: "#8a8278",
};

function SignalBadge({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] font-medium"
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 32%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

function Stat({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--ink-soft)]">
        {label}
      </span>
      <span className="tabular-nums text-xl font-semibold text-[var(--foreground)]">
        {children}
      </span>
    </div>
  );
}

export function TickerVerdict({ data }: { data: TickerCrossSection }) {
  // One KOL isn't a "共识" — show its lone direction; else the consensus verdict.
  const verdictLabel = data.soloDirection
    ? DIRECTION_META[data.soloDirection].label
    : data.netLabel;
  const verdictColor = data.soloDirection
    ? DIRECTION_META[data.soloDirection].color
    : CONSENSUS_COLOR[data.netLabel];

  const badges: { key: string; label: string; color: string }[] = [];
  if (data.diverging) {
    badges.push({ key: "diverging", label: "分歧", color: "var(--accent-teal)" });
  }
  if (data.crowded && data.crowdReturn !== null && data.crowdReturn < 0) {
    badges.push({
      key: "crowd-slap",
      label: "拥挤打脸",
      color: "var(--chart-down)",
    });
  } else if (data.crowded) {
    badges.push({ key: "crowded", label: "拥挤", color: "var(--accent-gold)" });
  }

  return (
    <section className="editorial-panel rounded-sm p-5">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.05fr_1fr]">
        {/* 左列 — 共识研判 */}
        <div className="flex flex-col gap-4">
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--accent-gold)]">
            众 KOL 裁决 · CONSENSUS
          </span>

          <h2
            className="text-[52px] leading-none"
            style={{ color: verdictColor }}
          >
            {verdictLabel}
          </h2>

          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
            <span
              className="tabular-nums font-semibold"
              style={{ color: "var(--chart-up)" }}
            >
              {data.bull} 多
            </span>
            <span className="text-[var(--ink-soft)]">/</span>
            <span
              className="tabular-nums font-semibold"
              style={{ color: "var(--chart-down)" }}
            >
              {data.bear} 空
            </span>
            {data.neutral > 0 ? (
              <span className="tabular-nums text-[var(--ink-soft)]">
                / {data.neutral} 中性
              </span>
            ) : null}
            {data.watch > 0 ? (
              <span className="tabular-nums text-[var(--ink-soft)]">
                / {data.watch} 观望
              </span>
            ) : null}
          </div>

          {badges.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              {badges.map((b) => (
                <SignalBadge key={b.key} label={b.label} color={b.color} />
              ))}
            </div>
          ) : null}

          <div className="mt-1 grid grid-cols-3 gap-4 border-t border-[var(--grid-line)] pt-4">
            <Stat label="覆盖 KOL">{data.total}</Stat>
            {data.diverging ? (
              <Stat label="分方向兑现">
                <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-base">
                  <span className="flex items-baseline gap-1">
                    <span className="text-[10px] text-[var(--ink-soft)]">多</span>
                    <ReturnChip value={data.bullReturn} muted="—" />
                  </span>
                  <span className="flex items-baseline gap-1">
                    <span className="text-[10px] text-[var(--ink-soft)]">空</span>
                    <ReturnChip value={data.bearReturn} muted="—" />
                  </span>
                </span>
              </Stat>
            ) : (
              <Stat label="群体兑现">
                <ReturnChip value={data.crowdReturn} muted="待回测" />
              </Stat>
            )}
            <Stat label="命中">
              {data.correctCount}/{data.settledKolCount}
            </Stat>
          </div>
        </div>

        {/* 右列 — 横截面研判 */}
        <div className="lg:border-l lg:border-[var(--grid-line)] lg:pl-6">
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--ink-soft)]">
            横截面研判
          </span>
          <p className="mt-3 text-[14px] leading-relaxed text-[var(--foreground)]">
            {data.narrative}
          </p>
        </div>
      </div>
    </section>
  );
}
