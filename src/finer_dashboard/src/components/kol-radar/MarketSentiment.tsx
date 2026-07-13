/**
 * 英雄区 · 全 KOL 今日情绪 (MARKET SENTIMENT).
 * Cross-KOL aggregate stance hero — the radar's "市场方向" headline.
 * Pure props render; StanceTide (right column) carries its own "use client".
 */
import {
  DIRECTION_META,
  fmtDate,
} from "@/components/kol-snapshot/primitives";
import { StanceTide } from "@/components/kol-snapshot/StanceTide";
import {
  stanceVerdict,
  type MarketSentimentVM,
  type ViewpointDirection,
} from "@/lib/fixtures/kol-radar";

// breadth segments rendered in this fixed order
const BREADTH_ORDER: ViewpointDirection[] = [
  "bullish",
  "bearish",
  "neutral",
  "watchlist",
  "risk_warning",
];

function StatBlock({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] leading-none text-[var(--ink-soft)]">
        {label}
      </span>
      <span
        className="tabular-nums text-2xl font-semibold leading-none"
        style={{ color: color ?? "var(--foreground)" }}
      >
        {value}
      </span>
    </div>
  );
}

export function MarketSentiment({ data }: { data: MarketSentimentVM }) {
  const verdict = stanceVerdict(data.net);
  const netLabel =
    data.net >= 0
      ? `净多 +${data.net} 家`
      : `净空 ${Math.abs(data.net)} 家`;

  const segments = BREADTH_ORDER.filter((dir) => data.breadth[dir] > 0).map(
    (dir) => ({
      dir,
      count: data.breadth[dir],
      meta: DIRECTION_META[dir],
    }),
  );
  const breadthTotal = segments.reduce((sum, s) => sum + s.count, 0);

  return (
    <section className="editorial-panel rounded-sm p-5">
      <div className="grid gap-6 lg:grid-cols-[1.05fr_1fr]">
        {/* ---- Left: verdict + stats + breadth bar ---- */}
        <div className="flex flex-col gap-4">
          <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--ink-soft)]">
            今日 KOL 情绪 · MARKET SENTIMENT
          </span>

          <div className="flex items-center gap-4">
            <h2
              className="leading-none tabular-nums"
              style={{ fontSize: "52px", color: verdict.color }}
            >
              {verdict.arrow} {verdict.label}
            </h2>
            <span
              className="inline-flex items-center rounded-sm px-2.5 py-1 text-xs font-medium tabular-nums"
              style={{
                color: verdict.color,
                backgroundColor: `color-mix(in srgb, ${verdict.color} 12%, transparent)`,
                border: `1px solid color-mix(in srgb, ${verdict.color} 32%, transparent)`,
              }}
            >
              {netLabel}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-4 border-t border-[var(--grid-line)] pt-4">
            <StatBlock label="跟踪 KOL" value={data.kolCount} />
            <StatBlock
              label="看多家数"
              value={data.bullishKols}
              color="var(--chart-up)"
            />
            <StatBlock
              label="看空家数"
              value={data.bearishKols}
              color="var(--chart-down)"
            />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex h-2 w-full overflow-hidden rounded-sm bg-[var(--surface-muted)]">
              {segments.map((s) => (
                <div
                  key={s.dir}
                  style={{
                    width: `${(s.count / breadthTotal) * 100}%`,
                    backgroundColor: s.meta.color,
                  }}
                />
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              {segments.map((s) => (
                <span key={s.dir} className="flex items-center gap-1.5 text-[11px]">
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: s.meta.color }}
                  />
                  <span className="text-[var(--ink-soft)]">{s.meta.label}</span>
                  <span className="tabular-nums font-medium text-[var(--foreground)]">
                    {s.count}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ---- Right: cumulative net-long stance tide ---- */}
        <div className="flex flex-col gap-3 lg:border-l lg:border-[var(--table-border)] lg:pl-6">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-sm leading-none text-[var(--foreground)]">
              观点流向潮汐
            </h3>
            {data.dateRange ? (
              <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                {fmtDate(data.dateRange[0])} — {fmtDate(data.dateRange[1])}
              </span>
            ) : null}
          </div>

          <StanceTide viewpoints={data.allViewpoints} />

          <p className="text-[11px] leading-tight text-[var(--ink-soft)]">
            逐月观点方向累计（非仓位/涨跌）· 跟踪 {data.totalViewpoints} 条观点 · 非投资建议
          </p>
        </div>
      </div>
    </section>
  );
}
