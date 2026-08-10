"use client";

/**
 * 单个真实（匿名化）KOL 的「晨星式体检报告」— 散户向自助单页。
 * 数据 = 冻结的真实 F5 canonical TradeActions（见 @/demo/kol-check/data.json）：
 * 真实标的/时序/原话/回测保真，KOL 身份匿名化。全前端、不连后端。
 */
import React from "react";
import { RADAR, TRADING_STYLE, AUDIT_BY_ID, KOL_ID } from "@/demo/kol-check/fixtures";
import {
  deriveCredibilityBoard,
  deriveEarningsBoard,
} from "@/demo/kol-check/kol-radar";
import { deriveKolSnapshot } from "@/demo/kol-check/kol-l2";
import {
  deriveHighlights,
  deriveSummary,
  deriveTickerRotation,
  type SnapshotViewpoint,
} from "@/demo/kol-check/kol-snapshot";
import { ViewpointTimeline } from "./ViewpointTimeline";
import { TradingStyleCard } from "./TradingStyleCard";
import { DirectionTag, ReturnChip, SectionHeader, fmtPct } from "./primitives";

function isSettled(v: SnapshotViewpoint): boolean {
  return v.returnPct !== null && (v.holdingDays ?? 0) > 0;
}

function MetricTile({
  value,
  label,
  sub,
  tone,
}: {
  value: React.ReactNode;
  label: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="editorial-panel rounded-sm px-4 py-3">
      <div
        className="tabular-nums text-2xl font-semibold leading-none"
        style={{ color: tone ?? "var(--foreground)" }}
      >
        {value}
      </div>
      <div className="mt-1.5 text-[11px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
        {label}
      </div>
      {sub ? (
        <div className="mt-0.5 tabular-nums text-[11px] text-[var(--ink-soft)]">{sub}</div>
      ) : null}
    </div>
  );
}

export function KolCheckReport() {
  const snap = deriveKolSnapshot(RADAR, KOL_ID)!;
  const cred = deriveCredibilityBoard(RADAR)[0];
  const summary = deriveSummary(snap.viewpoints);
  const hl = deriveHighlights(snap.viewpoints);
  const rotation = deriveTickerRotation(snap.viewpoints);
  const earn = deriveEarningsBoard(RADAR, "all")[0];

  const settled = snap.viewpoints.filter(isSettled);
  const wins = settled.filter((v) => (v.returnPct ?? 0) > 0).length;
  const losses = settled.length - wins;
  const avgReturn = earn?.avgReturn ?? 0;

  const credTone =
    cred.credibility >= 70
      ? "var(--chart-up)"
      : cred.credibility >= 55
        ? "var(--accent-gold)"
        : "var(--morningstar-red)";

  const styleConflict =
    TRADING_STYLE.declared?.entry_style &&
    TRADING_STYLE.observed?.entry_style_observed &&
    TRADING_STYLE.declared.entry_style !== "unknown" &&
    TRADING_STYLE.observed.entry_style_observed !== "unknown" &&
    TRADING_STYLE.declared.entry_style !== TRADING_STYLE.observed.entry_style_observed;

  const settledRotation = rotation.filter((r) => r.avgReturn !== null);

  return (
    <div className="mx-auto w-full max-w-[880px] px-5 py-10 sm:py-14">
      {/* sample-data banner */}
      <div className="mb-6 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-3 py-2 text-[11px] text-[var(--ink-soft)]">
        <span className="font-semibold text-[var(--foreground)]">真实结果快照 · 已匿名化</span>
        <span>
          数据为 Finer OS 对一位真实 KOL 内容跑出的真实 canonical 结果（标的/时序/原话/回测保真），身份已匿名。演示用途，非实时行情、非投资建议。
        </span>
      </div>

      {/* hero */}
      <header className="mb-8">
        <div className="flex items-baseline gap-3">
          <span className="text-[11px] uppercase tracking-[0.2em] text-[var(--accent-gold)]">
            KOL 晨星 · 体检报告
          </span>
        </div>
        <h1 className="mt-2 text-[28px] leading-tight sm:text-[34px]">
          {snap.kolName}
        </h1>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--ink-soft)]">
          <span>{snap.style}</span>
          <span aria-hidden>·</span>
          <span>{snap.platform}</span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">{RADAR.periodLabel}</span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">回测截至结算日</span>
        </div>

        {/* verdict banner */}
        <div
          className="mt-5 rounded-sm border-l-4 bg-[var(--surface-muted)] px-4 py-3 text-[13px] leading-relaxed text-[var(--foreground)]"
          style={{ borderColor: credTone }}
        >
          <span className="font-semibold">体检结论：</span>
          信誉分 {cred.credibility}/99，{settled.length} 笔已结算跟单命中{" "}
          {Math.round((hl.hitRate ?? 0) * 100)}%、等权每笔均值 {fmtPct(avgReturn)}
          {styleConflict ? "，且自述入场风格与实盘行为存在冲突" : ""}。
          {cred.credibility < 55
            ? "历史跟单为负，参考其观点需自行验证，不建议无脑跟单。"
            : "跟单前建议结合下方逐条证据链自行判断。"}
        </div>

        {/* metric tiles */}
        <div className="mt-4 grid grid-cols-2 gap-2.5 md:grid-cols-4">
          <MetricTile
            value={`${cred.credibility}`}
            label="信誉分 / 99"
            sub={`样本收缩后 · ${cred.lowSample ? "样本偏少" : `${settled.length} 笔结算`}`}
            tone={credTone}
          />
          <MetricTile
            value={`${Math.round((hl.hitRate ?? 0) * 100)}%`}
            label="结算命中率"
            sub={`${wins} 胜 / ${losses} 负`}
          />
          <MetricTile
            value={<span style={{ color: avgReturn > 0 ? "var(--chart-up)" : "var(--chart-down)" }}>{fmtPct(avgReturn)}</span>}
            label="平均每笔跟单"
            sub="等权 · 方向已校正"
          />
          <MetricTile
            value={`${summary.totalActions}`}
            label="明确观点数"
            sub={`覆盖 ${summary.tickersCovered.length} 标的`}
          />
        </div>

        <p className="mt-4 text-[13px] leading-relaxed text-[var(--ink-soft)]">
          {snap.narrative}
        </p>
      </header>

      {/* 01 言行不一 */}
      <section className="mb-9">
        <SectionHeader
          index="01"
          title="言行不一 · 自述 vs 实盘"
          en="DECLARED VS OBSERVED"
          note={styleConflict ? <span className="text-[var(--morningstar-red)]">检出冲突</span> : null}
        />
        <p className="mb-3 mt-3 text-[13px] leading-relaxed text-[var(--foreground)]">
          KOL 自我定位<strong>右侧交易</strong>（突破确认再上车），但系统统计其带风格标注的实盘信号为{" "}
          <strong className="text-[var(--morningstar-red)]">
            左侧 {TRADING_STYLE.observed?.left_side_count} 次 / 右侧 {TRADING_STYLE.observed?.right_side_count} 次
          </strong>
          ——多数是逢低抄底。自述与行为的差距，正是散户最难自查、也最该被问责的地方。
        </p>
        <TradingStyleCard profile={TRADING_STYLE} />
      </section>

      {/* 02 标的兑现榜 */}
      <section className="mb-9">
        <SectionHeader
          index="02"
          title="标的兑现榜"
          en="PER-TICKER REALIZED"
          note={<span>已结算按均值跟单收益排序</span>}
        />
        <div className="finer-scrollbar mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-[var(--table-border)] text-left text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                <th className="py-2 pr-3 font-normal">标的</th>
                <th className="py-2 pr-3 font-normal">最新立场</th>
                <th className="py-2 pr-3 font-normal">观点数</th>
                <th className="py-2 pr-3 font-normal">已结算</th>
                <th className="py-2 pr-3 text-right font-normal">均值跟单收益</th>
              </tr>
            </thead>
            <tbody>
              {settledRotation.map((r) => (
                <tr key={r.ticker} className="border-b border-[var(--grid-line)]">
                  <td className="py-2.5 pr-3">
                    <span className="font-medium text-[var(--foreground)]">{r.companyName}</span>
                    <span className="ml-2 tabular-nums text-[11px] text-[var(--ink-soft)]">
                      {r.ticker}·{r.market}
                    </span>
                  </td>
                  <td className="py-2.5 pr-3">
                    <DirectionTag direction={r.latestDirection} size="xs" />
                  </td>
                  <td className="tabular-nums py-2.5 pr-3 text-[var(--foreground)]">{r.count}</td>
                  <td className="tabular-nums py-2.5 pr-3 text-[var(--ink-soft)]">{r.settledCount}</td>
                  <td className="py-2.5 pr-3 text-right">
                    <ReturnChip value={r.avgReturn} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-[var(--ink-soft)]">
          仅列出至少一笔已结算的标的；未触发/观望类不计入收益排序。
        </p>
      </section>

      {/* 03 观点时间线 + 逐条证据链 */}
      <section className="mb-9">
        <SectionHeader
          index="03"
          title="真实战绩时间线"
          en="EVIDENCE · AUDIT TRAIL"
          note={<span>每条可展开 F3→F4→F5→F8 溯源</span>}
        />
        <p className="mb-4 mt-3 text-[13px] leading-relaxed text-[var(--ink-soft)]">
          每条观点保留 KOL 原话、方向、置信度与真实回测盈亏；点「证据链 · 溯源」展开该条从投资意图（F3）
          到策略映射（F4）、四时钟执行（F5）、完全跟单回测（F8）的 canonical 全链，携带真实 trace id。
        </p>
        <ViewpointTimeline viewpoints={snap.viewpoints} auditById={AUDIT_BY_ID} />
      </section>

      {/* footer honesty */}
      <footer className="mt-10 border-t border-[var(--grid-line)] pt-4 text-[11px] leading-relaxed text-[var(--ink-soft)]">
        <p>
          <span className="font-semibold text-[var(--foreground)]">口径与边界。</span>{" "}
          信誉分 = 结算命中率按样本量向 0.5 先验收缩（4 笔伪观测），单一 KOL、
          {settled.length} 笔已结算，非行业横评。跟单收益为完全跟单、方向已校正的
          F8 回测（含止损/止盈/最长持有），不含手续费滑点以外的资金管理。观点原话来自
          内容转写，可能含口语噪声。全部为演示快照，不构成投资建议。
        </p>
      </footer>
    </div>
  );
}
