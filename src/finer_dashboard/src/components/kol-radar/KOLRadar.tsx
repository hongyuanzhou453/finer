/**
 * 观点雷达 — cross-KOL operating-console home (top tier). Retail decision support:
 * 现在什么状况（市场情绪 + 近期异动）→ 信哪个（可信度榜）→ 跟哪条（可跟 call）+ 标的共识.
 *
 * Data-source agnostic: derives all block view-models from a KOLRadarData prop.
 * Live wiring is NOT drop-in — see the data-source seam notes in lib/fixtures/kol-radar.ts.
 */
import {
  KOL_RADAR_FIXTURE,
  deriveActionableCalls,
  deriveChangeFeed,
  deriveCredibilityBoard,
  deriveMarketSentiment,
  deriveTickerConsensus,
  type KOLRadarData,
} from "@/lib/fixtures/kol-radar";
import { SectionHeader } from "@/components/kol-snapshot/primitives";
import { MarketSentiment } from "./MarketSentiment";
import { EarningsRace } from "./EarningsRace";
import { ChangeFeed } from "./ChangeFeed";
import { CredibilityBoard } from "./CredibilityBoard";
import { ActionableCalls } from "./ActionableCalls";
import { TickerConsensus } from "./TickerConsensus";

export function KOLRadar({ data = KOL_RADAR_FIXTURE }: { data?: KOLRadarData }) {
  const sentiment = deriveMarketSentiment(data);
  const changes = deriveChangeFeed(data);
  const board = deriveCredibilityBoard(data);
  const calls = deriveActionableCalls(data);
  const consensus = deriveTickerConsensus(data);

  return (
    <div className="mx-auto max-w-[1180px] px-6 py-8">
      {/* ── Masthead ──────────────────────────────────────────── */}
      <header className="border-b border-[var(--foreground)] pb-4">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] text-[var(--ink-soft)]">
          <span>FINER OS · 观点雷达 · KOL VIEWPOINT RADAR</span>
          <span className="tabular-nums normal-case tracking-normal">
            生成 {data.generatedAt.slice(0, 16).replace("T", " ")}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div className="flex items-baseline gap-3">
            <h1 className="text-[32px] leading-none text-[var(--foreground)]">观点雷达</h1>
            <span className="tabular-nums text-sm text-[var(--ink-soft)]">
              {data.kols.length} 位 KOL · {data.periodLabel}
            </span>
          </div>
          <span className="text-[11px] text-[var(--ink-soft)]">
            散户决策台 · 信哪个 / 跟哪条 / 什么状况
          </span>
        </div>
      </header>

      {/* ── Hero: market sentiment ────────────────────────────── */}
      <div className="mt-5">
        <MarketSentiment data={sentiment} />
      </div>

      {/* ── 收益榜 ────────────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index=""
          title="收益榜"
          en="TOP EARNERS"
          note="按窗口内已结算跟单收益 · 等权累计"
        />
        <div className="editorial-panel mt-3 rounded-sm p-4">
          <EarningsRace data={data} />
        </div>
      </section>

      {/* ── 近期异动 ──────────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index=""
          title="近期异动"
          en="RECENT CHANGES"
          note={`${changes.length} 条 · 倒序`}
        />
        <div className="mt-3">
          <ChangeFeed events={changes} />
        </div>
      </section>

      {/* ── 01 可信度榜 ───────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="01"
          title="可信度榜"
          en="CREDIBILITY BOARD"
          note="按信誉分排名（含样本量校正）· 点击 KOL 进问责页"
        />
        <div className="editorial-panel mt-3 rounded-sm p-4">
          <CredibilityBoard rows={board} />
        </div>
      </section>

      {/* ── 02 此刻可跟 ───────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="02"
          title="此刻可跟"
          en="ACTIONABLE CALLS"
          note="可信度 × 信念 × 新鲜度排序 · 模型聚合，非荐股"
        />
        <div className="mt-3">
          <ActionableCalls calls={calls} />
        </div>
      </section>

      {/* ── 03 标的共识 ───────────────────────────────────────── */}
      <section className="mt-7">
        <SectionHeader
          index="03"
          title="标的共识"
          en="TICKER CONSENSUS"
          note="多 KOL 覆盖优先 · 分歧 / 拥挤预警"
        />
        <div className="mt-3">
          <TickerConsensus rows={consensus} />
        </div>
      </section>

      <footer className="mt-10 border-t border-[var(--table-border)] pt-4 text-[11px] leading-relaxed text-[var(--ink-soft)]">
        数据为示例 fixture，建模于真实 KOL 画像。信誉分由历史命中率派生并按样本量校正（非后端真值）。
        规划中：KOL 行与数字可下钻至 KOL 问责页、标的横截面与单条证据审计。本页仅展示模型隐含立场，非投资建议。
      </footer>
    </div>
  );
}
