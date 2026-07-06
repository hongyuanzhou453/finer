/**
 * "此刻可跟的 call" — 把流水线变成决策的转化面。
 * 跨 KOL 的可执行 call，已按 score 降序（见 deriveActionableCalls）。
 * 取前 6 条渲染为卡片网格；纯展示，无交互态。
 */
import Link from "next/link";
import type { ActionCall } from "@/lib/fixtures/kol-radar";
import {
  ConfidenceMeter,
  DirectionTag,
  DIRECTION_META,
} from "@/components/kol-snapshot/primitives";

export function ActionableCalls({ calls }: { calls: ActionCall[] }) {
  const top = calls.slice(0, 6);

  if (!top.length) {
    return <p className="text-[13px] text-[var(--ink-soft)]">当前无可跟 call。</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {top.map((call) => {
        const dirColor = DIRECTION_META[call.direction].color;
        return (
          <article key={call.id} className="editorial-card rounded-sm p-4">
            {/* 顶行：KOL + 信誉徽标 / 新鲜度 */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Link
                  href={`/demo/kol/${call.kolId}`}
                  className="text-sm font-semibold text-[var(--foreground)] hover:text-[var(--morningstar-red)] hover:underline"
                >
                  {call.kolName}
                </Link>
                <span
                  className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium"
                  style={{
                    color: "var(--accent-gold)",
                    backgroundColor:
                      "color-mix(in srgb, var(--accent-gold) 12%, transparent)",
                    border:
                      "1px solid color-mix(in srgb, var(--accent-gold) 32%, transparent)",
                  }}
                >
                  信誉&nbsp;
                  <span className="tabular-nums">{call.credibility}</span>
                </span>
              </div>
              {call.ageDays <= 1 ? (
                <span
                  className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-semibold"
                  style={{
                    color: "var(--chart-up)",
                    backgroundColor:
                      "color-mix(in srgb, var(--chart-up) 12%, transparent)",
                  }}
                >
                  今日新
                </span>
              ) : (
                <span className="tabular-nums text-[10px] text-[var(--ink-soft)]">
                  {call.ageDays}&nbsp;天前
                </span>
              )}
            </div>

            {/* 主体：方向 + 标的 + 置信度 */}
            <div className="mt-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <DirectionTag direction={call.direction} />
                  <span className="truncate text-base font-bold text-[var(--foreground)]">
                    {call.companyName}
                  </span>
                </div>
                <div className="mt-1 tabular-nums text-[11px] text-[var(--ink-soft)]">
                  {call.ticker}·{call.market}
                </div>
              </div>
              <div className="shrink-0 pt-0.5">
                <ConfidenceMeter value={call.confidence} />
              </div>
            </div>

            {/* 摘要 */}
            <p className="mt-3 text-[13px] leading-snug text-[var(--foreground)]">
              {call.summary}
            </p>

            {/* 证据引文 */}
            <blockquote
              className="mt-3 line-clamp-2 pl-3 text-[12px] leading-snug text-[var(--ink-soft)]"
              style={{
                borderLeft: `2px solid color-mix(in srgb, ${dirColor} 40%, transparent)`,
              }}
            >
              “{call.evidenceText}”
            </blockquote>

            {/* 下钻到 L4 单条证据审计 */}
            <div className="mt-3 border-t border-[var(--grid-line)] pt-2">
              <Link
                href={`/demo/audit/${call.id}`}
                className="text-[11px] text-[var(--accent-teal)] hover:underline"
              >
                查看证据链 →
              </Link>
            </div>
          </article>
        );
      })}
    </div>
  );
}
