/**
 * 标的横截面 (ticker cross-section) — the per-ticker counterpart to the KOL
 * accountability page. For one name: 众 KOL 怎么看（共识裁决）→ 谁对了（本票兑现榜）
 * → 立场如何演变（跨 KOL 时间线）. Data-source agnostic via TickerCrossSection.
 */
import Link from "next/link";
import { SectionHeader } from "@/components/kol-snapshot/primitives";
import type { TickerCrossSection } from "@/lib/fixtures/kol-ticker";
import { TickerVerdict } from "./TickerVerdict";
import { WhoWasRight } from "./WhoWasRight";
import { TickerStanceTimeline } from "./TickerStanceTimeline";

export function KOLTickerCrossSection({ data }: { data: TickerCrossSection }) {
  return (
    <div className="mx-auto max-w-[1180px] px-6 py-8">
      <header className="border-b border-[var(--foreground)] pb-4">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] text-[var(--ink-soft)]">
          <span>FINER OS · 标的横截面 · TICKER CROSS-SECTION</span>
          <Link
            href="/demo/kol-radar"
            className="normal-case tracking-normal text-[var(--accent-teal)] hover:underline"
          >
            ← 返回观点雷达
          </Link>
        </div>
        <div className="mt-3 flex flex-wrap items-baseline gap-3">
          <h1 className="text-[32px] leading-none text-[var(--foreground)]">
            {data.companyName}
          </h1>
          <span className="tabular-nums text-sm text-[var(--ink-soft)]">
            {data.ticker} · {data.market}
          </span>
          <span className="text-[11px] text-[var(--ink-soft)]">众 KOL 视角 · 谁对了</span>
        </div>
      </header>

      {/* ── Hero: consensus verdict ───────────────────────────── */}
      <div className="mt-5">
        <TickerVerdict data={data} />
      </div>

      {/* ── 01 谁对了 ─────────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="01"
          title="谁对了"
          en="WHO WAS RIGHT"
          note={`${data.settledKolCount} 位已结算 · 按本票兑现排名`}
        />
        <div className="editorial-panel mt-3 rounded-sm p-4">
          <WhoWasRight rows={data.whoWasRight} />
        </div>
      </section>

      {/* ── 02 立场时间线 ─────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="02"
          title="立场时间线"
          en="STANCE TIMELINE"
          note={`${data.timeline.length} 条 · 倒序`}
        />
        <div className="mt-4">
          <TickerStanceTimeline timeline={data.timeline} />
        </div>
      </section>

      <footer className="mt-10 border-t border-[var(--table-border)] pt-4 text-[11px] leading-relaxed text-[var(--ink-soft)]">
        数据为示例 fixture。兑现为 F8 完全跟单回测（已按方向结算，正=判断对/盈）。规划中：每条观点可下钻至单条证据审计。本页仅展示模型隐含立场，非投资建议。
      </footer>
    </div>
  );
}
