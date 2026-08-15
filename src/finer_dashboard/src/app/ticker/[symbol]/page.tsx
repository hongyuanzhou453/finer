"use client";

/**
 * /ticker/[symbol] — 个股共识记录（UI-3，CRD-3 的消费面）。
 *
 * 定位纪律（2026-08-02 转向）：本页描述「谁说过什么」，不判断「谁说得对」。
 * notes 里的口径声明必须逐条展示，不得折叠——这是 CRD-2 的前端义务。
 * 陈旧度是页面的**状态**（置页头），不是脚注里的免责声明。
 *
 * 版式（2026-08-13）：机构研报排版——报头横规、编号章节、booktabs 密排表、
 * 立场构成条、目标价离散度条。所有字段与口径不变，图形只是已显示数字的再编码。
 */

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ScrollText } from "lucide-react";
import type {
  ConsensusDirection,
  Staleness,
  TickerConsensusView,
} from "@/lib/contracts";
import { apiFetch } from "@/lib/api-client";
import {
  BlankCell,
  CONSENSUS_DIRECTION_META,
  CompositionRibbon,
  DirectionTag,
  ErrorPanel,
  LoadingRow,
  Masthead,
  MetricTile,
  NoteList,
  SectionHeader,
  SpreadBar,
  StatusBanner,
  fmtPct,
  type RibbonSegment,
} from "@/components/crd/primitives";

const STALENESS_LABEL: Record<Staleness, string> = {
  current: "近期记录",
  aging: "已有一段时间未更新",
  stale: "记录较旧",
  archival: "档案级记录",
};

/** 构成条的固定读序：多 → 中性 → 空 → 混合，跨标的保持一致好比较形状。 */
const DIRECTION_ORDER: ConsensusDirection[] = [
  "bullish",
  "neutral",
  "bearish",
  "mixed",
];

function fmtPrice(v?: number | null, cur?: string | null): string {
  if (v == null) return "—";
  return `${v.toLocaleString()} ${cur ?? ""}`.trim();
}

export default function TickerConsensusPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const [view, setView] = useState<TickerConsensusView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<TickerConsensusView>(
      `/api/ticker/${encodeURIComponent(symbol)}/consensus`,
    )
      .then((data) => {
        if (alive) setView(data);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  const directionSegments = useMemo<RibbonSegment[]>(() => {
    if (!view) return [];
    const counts = view.direction_counts ?? {};
    const known = DIRECTION_ORDER.map((d) => ({
      key: d,
      label: CONSENSUS_DIRECTION_META[d].label,
      count: counts[d] ?? 0,
      color: CONSENSUS_DIRECTION_META[d].color,
    }));
    // 契约外的取值不静默丢弃——宁可显示一个陌生标签，也不要悄悄少算票数。
    const extras = Object.entries(counts)
      .filter(([k]) => !DIRECTION_ORDER.includes(k as ConsensusDirection))
      .map(([k, n]) => ({
        key: k,
        label: k,
        count: n,
        color: "color-mix(in srgb, var(--foreground) 30%, transparent)",
      }));
    return [...known, ...extras];
  }, [view]);

  const tp = view?.target_prices ?? null;

  return (
    <div className="finer-scrollbar h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-9">
        <Link
          href="/"
          className="mb-5 inline-flex items-center gap-1 text-[11px] text-[var(--ink-soft)] transition-colors hover:text-[var(--foreground)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> 返回
        </Link>

        <Masthead
          eyebrow="FINER OS · 个股共识记录"
          title={
            <span className="tabular-nums">{decodeURIComponent(symbol)}</span>
          }
          suffix="共识记录 · 谁说过什么"
          meta={
            view
              ? [
                  `${view.n_sources} 家信源`,
                  `最新报告 ${view.latest_report_date ?? "—"}`,
                  view.directional_agreement != null
                    ? `方向一致度 ${fmtPct(view.directional_agreement, 0)}`
                    : "方向一致度 —",
                  view.target_names.length > 0
                    ? view.target_names.slice(0, 2).join(" / ")
                    : "无名称记录",
                ]
              : undefined
          }
          lede="本页只回答「谁、在哪天、说了什么」。每一行都可下钻到原文证据，不对未来做任何判断。"
        />

        {view?.staleness && view.latest_report_date && (
          <div className="mt-4">
            <StatusBanner tone={view.staleness}>
              <span className="font-semibold">
                本页记录截至{" "}
                <span className="tabular-nums">{view.latest_report_date}</span>
                {view.as_of_days != null && (
                  <span className="tabular-nums">
                    （距今 {view.as_of_days} 天）
                  </span>
                )}
                {" · "}
                {STALENESS_LABEL[view.staleness]}
              </span>
              <div className="mt-0.5 text-[11px] text-[var(--ink-soft)]">
                语料为静态档案，不代表此刻的市场共识。
              </div>
            </StatusBanner>
          </div>
        )}

        {loading && <LoadingRow>加载中…</LoadingRow>}

        {error && !loading && (
          <ErrorPanel
            title={<>未找到该标的的立场记录：{error}</>}
            hint="确认代码写法（如 0700.HK / NVDA / AZN.L），或该标的未被已接入信源覆盖。"
          />
        )}

        {view && !loading && (
          <>
            {/* 口径声明 —— CRD-2 纪律：逐条展示，不折叠 */}
            {view.notes.length > 0 && (
              <section className="mt-6">
                <SectionHeader
                  index=""
                  title="口径声明"
                  en="METHODOLOGY NOTES"
                  note={<>逐条展示 · 不折叠</>}
                />
                <div className="mt-2.5">
                  <NoteList notes={view.notes} />
                </div>
              </section>
            )}

            {/* 01 立场构成 */}
            <section className="mt-7">
              <SectionHeader
                index="01"
                title="立场构成"
                en="STATED POSITIONS"
                note={<>每家信源只计最新一篇</>}
              />
              <div className="mt-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                <MetricTile
                  value={view.n_sources}
                  label="信源家数"
                  sub="每源计最新一篇"
                />
                <MetricTile
                  value={view.latest_by_source.reduce(
                    (s, r) => s + (r.n_reports ?? 0),
                    0,
                  )}
                  label="累计篇数"
                  sub="含同源多篇"
                />
                <MetricTile
                  value={
                    view.directional_agreement != null
                      ? fmtPct(view.directional_agreement, 0)
                      : "—"
                  }
                  label="方向一致度"
                  sub="口径见上方声明"
                />
                <MetricTile
                  value={view.latest_report_date ?? "—"}
                  label="最新报告日"
                  sub={
                    view.as_of_days != null
                      ? `距今 ${view.as_of_days} 天`
                      : undefined
                  }
                />
              </div>
              <div className="editorial-panel mt-2.5 rounded-sm px-4 py-3">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                  方向票构成 · 按家数
                </div>
                <div className="mt-2">
                  <CompositionRibbon
                    segments={directionSegments}
                    emptyHint="该标的无方向票记录。"
                  />
                </div>
              </div>
            </section>

            {/* 02 目标价分布 */}
            <section className="mt-8">
              <SectionHeader
                index="02"
                title="目标价分布"
                en="TARGET PRICE SPREAD"
                note={<>排除计数必须可见</>}
              />
              {tp ? (
                <div className="editorial-panel mt-3 rounded-sm px-4 py-3.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-[11px] text-[var(--ink-soft)]">
                      币种 <span className="tabular-nums">{tp.currency}</span> ·
                      纳入
                      <span className="tabular-nums"> n={tp.n}</span>
                    </span>
                    <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                      最低 / 中位 / 最高
                    </span>
                  </div>
                  <div className="mt-1.5 tabular-nums text-[22px] font-semibold leading-none">
                    {tp.min_value.toLocaleString()}
                    <span className="mx-2 text-[var(--ink-soft)]">/</span>
                    <span className="text-[var(--accent-gold)]">
                      {tp.median_value.toLocaleString()}
                    </span>
                    <span className="mx-2 text-[var(--ink-soft)]">/</span>
                    {tp.max_value.toLocaleString()}
                  </div>
                  <SpreadBar
                    min={tp.min_value}
                    median={tp.median_value}
                    max={tp.max_value}
                  />
                  {(tp.excluded_unit_ambiguous > 0 ||
                    tp.excluded_currency_mismatch > 0) && (
                    <p className="mt-2 border-l-2 border-[var(--accent-gold)] pl-2 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                      已排除：单位可疑{" "}
                      <span className="tabular-nums text-[var(--foreground)]">
                        {tp.excluded_unit_ambiguous}
                      </span>{" "}
                      条 · 币种不一{" "}
                      <span className="tabular-nums text-[var(--foreground)]">
                        {tp.excluded_currency_mismatch}
                      </span>{" "}
                      条。排除比一个错误的中位数诚实。
                    </p>
                  )}
                </div>
              ) : (
                <BlankCell>
                  {
                    "目标价未聚合——无数据，或单位可疑被整体排除。这里留白，不给一个看起来像数字的猜测。"
                  }
                </BlankCell>
              )}
            </section>

            {/* 03 各信源最新立场 */}
            <section className="mt-8 pb-12">
              <SectionHeader
                index="03"
                title="各信源最新立场"
                en="LATEST BY SOURCE"
                note={<>每行可下钻至 F3 意图与 F2 证据原文</>}
              />
              <div className="finer-scrollbar mt-3 overflow-x-auto">
                <table className="top-rule-table min-w-[720px]">
                  <thead>
                    <tr>
                      <th>信源</th>
                      <th>方向</th>
                      <th>评级</th>
                      <th className="text-right">目标价</th>
                      <th className="text-right">报告日</th>
                      <th className="text-right">篇数</th>
                      <th>下钻</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.latest_by_source.map((row) => (
                      <tr key={row.intent_id || row.creator_id}>
                        <td className="font-medium">{row.creator_id}</td>
                        <td>
                          <DirectionTag direction={row.direction} size="xs" />
                        </td>
                        <td className="text-[var(--ink-soft)]">
                          {row.rating ?? "—"}
                        </td>
                        <td className="tabular-nums">
                          {fmtPrice(
                            row.target_price_value,
                            row.target_price_currency,
                          )}
                        </td>
                        <td className="tabular-nums">
                          {row.report_date ?? "—"}
                        </td>
                        <td className="tabular-nums">{row.n_reports}</td>
                        <td>
                          <Link
                            href={`/audit?ticker=${encodeURIComponent(view.ticker)}`}
                            className="inline-flex items-center gap-1 border-b border-[var(--accent-gold)] pb-px font-mono text-[10px] text-[var(--foreground)] transition-colors hover:text-[var(--morningstar-red)]"
                            title={row.intent_id}
                          >
                            <ScrollText className="h-3 w-3" />
                            {row.intent_id.slice(0, 14)}…
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                {"表内为每家信源的"}
                <strong className="font-semibold text-[var(--foreground)]">
                  最新一篇
                </strong>
                {
                  "立场；同源历史立场与完整证据链在审计页逐条可查。目标价按原文币种呈现，跨币种不做换算。"
                }
              </p>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
