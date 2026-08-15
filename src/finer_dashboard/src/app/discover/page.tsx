"use client";

/**
 * /discover — 信源历史记录卡片墙（UI-1，CRD-1 的消费面）。
 *
 * 口径纪律（2026-08-03 UI-1 拍板）：
 * - 默认序 = 已结算样本量降序（后端 read_record_cards 已排好，前端不得重排）。
 *   这是稳定输出序，**不是排名**——跨期持续性检验未获支持，任何按超额的
 *   默认排序都是在宣称一件数据不支持的事。
 * - display_policy 强制消费：count_only 的卡不渲染任何比率，改为显式留白。
 * - 胜率必须与 95% 区间并排；预测性声明置顶且**默认展示**。
 *
 * 版式（2026-08-13）：改用机构研报排版——报头横规、页头三栏声明带、
 * 编号章节、等宽数字、Wilson 区间条。所有数字口径不变，新增的只有
 * 「同口径计数合计」这一类聚合（计数不是比率，不受 CRD-2 效力门约束）。
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ScrollText } from "lucide-react";
import type {
  CorpusRatioSlices,
  CreatorRecordCard,
  RatioSlice,
  RecordCorpusAggregates,
} from "@/lib/contracts";
import { apiFetch } from "@/lib/api-client";
import {
  BlankCell,
  CompositionRibbon,
  Disclosure,
  ErrorPanel,
  LoadingRow,
  Masthead,
  MetricTile,
  NoteList,
  SectionHeader,
  TierBadge,
  WilsonBar,
  fmtDate,
  fmtPct,
  fmtSignedPct,
  type RibbonSegment,
} from "@/components/crd/primitives";

/** 口径切换：券商对个股的评级与对板块的看法基准率不同，不得混算（R6）。 */
const SCOPES = [
  { key: "broker_recommendation", label: "个股评级" },
  { key: "broker_sector_view", label: "板块观点" },
] as const;

/** 市场构成用中性墨阶——市场不是方向，上红绿会被读成优劣。 */
const MARKET_RAMP = [
  "color-mix(in srgb, var(--foreground) 72%, transparent)",
  "color-mix(in srgb, var(--foreground) 52%, transparent)",
  "color-mix(in srgb, var(--foreground) 36%, transparent)",
  "color-mix(in srgb, var(--foreground) 24%, transparent)",
  "color-mix(in srgb, var(--foreground) 14%, transparent)",
];

/** 方向计数带的固定读序与配色（红多绿空，中国惯例；观察/风险为辅助色）。 */
const DIRECTION_SEGMENT_META: Array<{ key: string; label: string; color: string }> = [
  { key: "bullish", label: "看多", color: "var(--chart-up)" },
  { key: "neutral", label: "中性", color: "#8a8278" },
  { key: "bearish", label: "看空", color: "var(--chart-down)" },
  { key: "watchlist", label: "观察", color: "var(--accent-gold)" },
  { key: "risk_warning", label: "风险", color: "var(--accent-teal)" },
];

const EXIT_REASON_LABEL: Record<string, string> = {
  stop_loss: "止损离场",
  time_exit: "到期离场",
  target_reached: "到达目标价",
  end_of_period: "期末结算",
};

const TIME_HORIZON_LABEL: Record<string, string> = {
  short_term: "短线",
  medium_term: "中线",
  long_term: "长线",
  review_required: "需复核",
};

/** 计数字典 → 构成带分段；未知取值保留原名（不静默丢票）。 */
function countSegments(
  counts: Record<string, number>,
  labels: Record<string, string>,
  ramp: string[],
): RibbonSegment[] {
  return Object.entries(counts).map(([k, n], i) => ({
    key: k,
    label: labels[k] ?? k,
    count: n,
    color: ramp[Math.min(i, ramp.length - 1)],
  }));
}

/**
 * 月度活动条（纯计数）。淡条 = 当月全部条数，深条 = 其中已结算。
 * 高度编码的是计数不是比率——两根条并排呈现，不合成「结算率」。
 */
function MonthlyActivityBars({
  aggregates,
}: {
  aggregates: RecordCorpusAggregates;
}) {
  const buckets = aggregates.monthly;
  if (buckets.length === 0) {
    return <BlankCell>该口径下无带时钟的记录，无法按月归置。</BlankCell>;
  }
  const peak = Math.max(...buckets.map((b) => b.n_total), 1);
  return (
    <div>
      <div className="flex h-28 items-end gap-1">
        {buckets.map((b) => (
          <div
            key={b.month}
            // h-full 必须显式给出：子条的百分比高度要有确定的解析基准
            className="group relative flex h-full min-w-0 flex-1 items-end justify-center gap-px"
            title={`${b.month} · 共 ${b.n_total} 条 · 已结算 ${b.n_settled} 条`}
          >
            <div
              className="w-full max-w-[18px] rounded-t-[2px]"
              style={{
                height: `${Math.max((b.n_total / peak) * 100, 2)}%`,
                backgroundColor:
                  "color-mix(in srgb, var(--foreground) 18%, transparent)",
              }}
            />
            <div
              className="w-full max-w-[18px] rounded-t-[2px]"
              style={{
                height: `${Math.max((b.n_settled / peak) * 100, b.n_settled > 0 ? 2 : 0)}%`,
                backgroundColor:
                  "color-mix(in srgb, var(--foreground) 62%, transparent)",
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1 border-t border-[var(--grid-line)] pt-1">
        {buckets.map((b) => (
          <div
            key={b.month}
            className="min-w-0 flex-1 text-center text-[9px] tabular-nums leading-tight text-[var(--ink-soft)]"
          >
            {b.month.slice(2).replace("-", "")}
            <br />
            <span className="text-[var(--foreground)]">{b.n_total}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--ink-soft)]">
        <span className="flex items-center gap-1">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-[1px]"
            style={{ backgroundColor: "color-mix(in srgb, var(--foreground) 18%, transparent)" }}
          />
          当月条数
        </span>
        <span className="flex items-center gap-1">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-[1px]"
            style={{ backgroundColor: "color-mix(in srgb, var(--foreground) 62%, transparent)" }}
          />
          其中已结算
        </span>
      </div>
    </div>
  );
}

const MARKET_LABEL: Record<string, string> = {
  US: "美股",
  CN: "A股",
  HK: "港股",
  JP: "日股",
  UK: "英股",
  TW: "台股",
  KR: "韩股",
};

/**
 * 一行胜率切片。CRD-2 前端义务的执行点：
 * - count_only → 只报计数，比率/区间/收益一概不渲染；
 * - 过门 → WilsonBar（点估计 + 95% 区间 + 全口径参照线）与收益并排。
 */
function SliceRow({
  slice,
  label,
  reference,
}: {
  slice: RatioSlice;
  label: string;
  reference: number | null;
}) {
  const s = slice.sufficiency;
  const countOnly = s.display_policy === "count_only";
  return (
    <div className="border-b border-[var(--grid-line)] py-2.5 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-[72px] font-medium">
          {label}
          <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-soft)]">
            {slice.key.startsWith("__") ? "" : slice.key}
          </span>
        </span>
        <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
          已结算 {slice.n_settled} / {slice.n_total}
        </span>
        {countOnly ? (
          <span className="text-[11px] text-[var(--ink-soft)]">
            样本不足 · 仅计数
          </span>
        ) : (
          <span className="tabular-nums text-[13px] font-semibold">
            {fmtPct(s.point_estimate)}
            <span className="ml-2 font-normal text-[11px] text-[var(--ink-soft)]">
              均值收益 {fmtSignedPct(slice.mean_return)}
            </span>
          </span>
        )}
      </div>
      {!countOnly && (
        <WilsonBar
          point={s.point_estimate}
          low={s.wilson_low}
          high={s.wilson_high}
          reference={reference}
          referenceLabel="全口径合并"
        />
      )}
      {!countOnly && s.display_policy === "show_with_warning" && (
        <p className="mt-1 border-l-2 border-[var(--accent-gold)] pl-2 text-[10px] leading-relaxed text-[var(--ink-soft)]">
          样本偏少，请按区间宽度阅读。
        </p>
      )}
    </div>
  );
}

function SlicePanel({
  title,
  slices,
  labelOf,
}: {
  title: string;
  slices: CorpusRatioSlices;
  labelOf: (key: string) => string;
}) {
  // 参照线 = 全口径合并命中率；合并片自己没过门就不画参照线
  const overallPermitted =
    slices.overall.sufficiency.display_policy !== "count_only";
  const reference = overallPermitted
    ? (slices.overall.sufficiency.point_estimate ?? null)
    : null;
  return (
    <div className="editorial-panel rounded-sm px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
          {title}
        </div>
        <div className="tabular-nums text-[10px] text-[var(--ink-soft)]">
          {overallPermitted
            ? `全口径合并 ${fmtPct(slices.overall.sufficiency.point_estimate)}（n=${slices.overall.n_settled}）`
            : `全口径合并样本不足（n=${slices.overall.n_settled}），无参照线`}
        </div>
      </div>
      <div className="mt-1.5">
        {slices.slices.map((s) => (
          <SliceRow
            key={s.key}
            slice={s}
            label={labelOf(s.key)}
            reference={reference}
          />
        ))}
      </div>
    </div>
  );
}

function marketSegments(mix: Record<string, number>): RibbonSegment[] {
  const sorted = Object.entries(mix).sort((a, b) => b[1] - a[1]);
  const head = sorted.slice(0, 4);
  const tailCount = sorted.slice(4).reduce((s, [, n]) => s + n, 0);
  const segments: RibbonSegment[] = head.map(([m, n], i) => ({
    key: m,
    label: m,
    count: n,
    color: MARKET_RAMP[i],
  }));
  if (tailCount > 0) {
    segments.push({
      key: "__rest",
      label: `其他 ${sorted.length - head.length} 个市场`,
      count: tailCount,
      color: MARKET_RAMP[4],
    });
  }
  return segments;
}

function RecordCard({ card }: { card: CreatorRecordCard }) {
  const s = card.sufficiency;
  const countOnly = s.display_policy === "count_only";

  return (
    <article className="editorial-panel flex flex-col rounded-sm px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[15px] font-semibold leading-tight text-[var(--foreground)]">
          {card.creator_id}
        </span>
        <TierBadge tier={s.tier} />
      </div>

      {countOnly ? (
        <BlankCell>
          已结算{" "}
          <span className="tabular-nums text-[var(--foreground)]">
            {card.n_settled}
          </span>{" "}
          / 共{" "}
          <span className="tabular-nums text-[var(--foreground)]">
            {card.n_total}
          </span>{" "}
          条 —— 样本不足以支撑任何比率，此处刻意留白而非填零。
        </BlankCell>
      ) : (
        <>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="tabular-nums text-[26px] font-semibold leading-none">
              {fmtPct(s.point_estimate)}
            </span>
            <span className="text-[11px] text-[var(--ink-soft)]">
              结算命中率
            </span>
          </div>
          <WilsonBar
            point={s.point_estimate}
            low={s.wilson_low}
            high={s.wilson_high}
            reference={card.expected_win_rate}
          />
          <dl className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--ink-soft)]">已结算</dt>
              <dd className="tabular-nums">
                {card.n_settled} / {card.n_total}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--ink-soft)]">均值收益</dt>
              <dd className="tabular-nums">{fmtSignedPct(card.mean_return)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--ink-soft)]">中位收益</dt>
              <dd className="tabular-nums">
                {fmtSignedPct(card.median_return)}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--ink-soft)]">市场预期</dt>
              <dd className="tabular-nums">{fmtPct(card.expected_win_rate)}</dd>
            </div>
          </dl>
          {s.display_policy === "show_with_warning" && (
            <p className="mt-2 border-l-2 border-[var(--accent-gold)] pl-2 text-[10px] leading-relaxed text-[var(--ink-soft)]">
              样本偏少，请按区间宽度阅读，不要按点估计阅读。
            </p>
          )}
        </>
      )}

      {/* mt-auto：把构成条与页脚压到卡底，同一行的卡片基线才对得齐。 */}
      <div className="mt-auto pt-3">
        <div className="border-t border-[var(--grid-line)] pt-2.5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
            市场构成 · 按条数
          </div>
          <div className="mt-1.5">
            <CompositionRibbon segments={marketSegments(card.market_mix)} />
          </div>
        </div>

        <div className="mt-3 flex items-end justify-between gap-2 border-t border-[var(--grid-line)] pt-2.5">
          <span className="tabular-nums text-[10px] leading-tight text-[var(--ink-soft)]">
            记录窗口
            <br />
            {fmtDate(card.first_action_at)} — {fmtDate(card.last_action_at)}
          </span>
          <Link
            href={`/audit?kol=${encodeURIComponent(card.creator_id)}`}
            className="inline-flex items-center gap-1 border-b border-[var(--accent-gold)] pb-px text-[11px] text-[var(--foreground)] transition-colors hover:text-[var(--morningstar-red)]"
          >
            <ScrollText className="h-3 w-3" /> 逐条审计
          </Link>
        </div>
      </div>
    </article>
  );
}

export default function DiscoverPage() {
  const [cards, setCards] = useState<CreatorRecordCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<string>(SCOPES[0].key);
  // 语料构成聚合独立加载：失败只影响对应区块，不拖垮卡墙
  const [aggregates, setAggregates] = useState<RecordCorpusAggregates | null>(null);
  const [marketSlices, setMarketSlices] = useState<CorpusRatioSlices | null>(null);
  const [monthSlices, setMonthSlices] = useState<CorpusRatioSlices | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<{ cards: CreatorRecordCard[] }>(
      `/api/creator/records?signal_class=${encodeURIComponent(scope)}`,
    )
      .then((data) => {
        if (alive) setCards(data.cards);
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
  }, [scope]);

  useEffect(() => {
    let alive = true;
    setAggregates(null);
    setMarketSlices(null);
    setMonthSlices(null);
    apiFetch<{ aggregates: RecordCorpusAggregates }>(
      `/api/creator/records/aggregates?signal_class=${encodeURIComponent(scope)}`,
    )
      .then((data) => {
        if (alive) setAggregates(data.aggregates);
      })
      .catch(() => {
        // 静默降级：聚合区块渲染为缺失提示，不阻塞主内容
        if (alive) setAggregates(null);
      });
    for (const [dimension, set] of [
      ["market", setMarketSlices],
      ["month", setMonthSlices],
    ] as const) {
      apiFetch<{ slices: CorpusRatioSlices }>(
        `/api/creator/records/slices?signal_class=${encodeURIComponent(scope)}&dimension=${dimension}`,
      )
        .then((data) => {
          if (alive) set(data.slices);
        })
        .catch(() => {
          if (alive) set(null);
        });
    }
    return () => {
      alive = false;
    };
  }, [scope]);

  const scopeLabel = SCOPES.find((s) => s.key === scope)?.label ?? scope;

  /** 同口径内的计数合计。计数不是比率，不受效力门约束；跨口径永不相加。 */
  const totals = useMemo(() => {
    const nTotal = cards.reduce((s, c) => s + c.n_total, 0);
    const nSettled = cards.reduce((s, c) => s + c.n_settled, 0);
    const readable = cards.filter(
      (c) => c.sufficiency.display_policy !== "count_only",
    ).length;
    return { nTotal, nSettled, readable };
  }, [cards]);

  const claim = cards[0]?.sufficiency.predictive_claim;
  /**
   * 声明**默认渲染**，只有后端明确许可（permitted === true）时才撤下。
   * 曾经的写法是 `claim && !claim.permitted`——claim 为 null 时整块消失，
   * 而 null 恰恰意味着「该指标从没被检验过」，是最该出声明的情形。
   */
  const showPredictiveDisclosure = claim?.permitted !== true;

  return (
    <div className="finer-scrollbar h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-9">
        <Masthead
          eyebrow="FINER OS · 信源记录"
          title="信源记录"
          suffix="谁说过什么 · 后来怎么结算的"
          meta={[
            `口径 ${scopeLabel}`,
            `${cards.length} 个信源`,
            `${totals.nTotal.toLocaleString()} 条记录`,
            `${totals.nSettled.toLocaleString()} 条已结算`,
          ]}
          lede="每张卡是一份历史记录，不是推荐。默认按已结算样本量排列——这是稳定输出序，不是排名。"
        />

        {/* 页头三栏声明带：口径、排序、预测边界。默认可见，不折叠。 */}
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          <Disclosure title="口径隔离">
            个股评级与板块观点基准率不同，不可跨口径比较，也不可合并计数。
          </Disclosure>
          <Disclosure title="排序口径">
            默认序 = 已结算样本量降序。不按收益、不按胜率、不产出「Top 信源」。
          </Disclosure>
          {showPredictiveDisclosure ? (
            <Disclosure title="预测边界" tone="warn">
              本页数字描述已发生的事实，不构成对未来的预测。
              {claim?.summary
                ? ` 跨期持续性检验：${claim.summary}`
                : " 该指标未经跨期持续性检验。"}
              {claim?.evidence ? (
                <span className="ml-1 font-mono text-[10px]">
                  {claim.evidence}
                </span>
              ) : null}
            </Disclosure>
          ) : (
            <Disclosure title="预测边界">
              该指标已通过预声明持续性判据，许可范围以后端 predictive_claim
              为准。
            </Disclosure>
          )}
        </div>

        {/* 口径开关 */}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          {/* tablist/tab：aria-selected 是 .segmented-control 的样式钩子，
              而 role=button 不支持该属性——用 tab 角色才既合法又保留样式。 */}
          <div
            className="segmented-control"
            role="tablist"
            aria-label="信号口径"
          >
            {SCOPES.map((s) => (
              <button
                key={s.key}
                type="button"
                role="tab"
                aria-selected={scope === s.key}
                aria-controls="scope-panel"
                onClick={() => setScope(s.key)}
              >
                {s.label}
              </button>
            ))}
          </div>
          <span className="text-[11px] text-[var(--ink-soft)]">
            切换口径会整页换一套基准率，两侧数字不可对比。
          </span>
        </div>

        <div id="scope-panel" role="tabpanel" aria-live="polite">
          {loading && (
            <LoadingRow>加载中…（首次扫描全量 action，约数秒）</LoadingRow>
          )}

          {error && !loading && (
            <ErrorPanel
              title={<>记录卡加载失败：{error}</>}
              hint="确认后端 /api/creator/records 可达；若投影未物化，接口会回退到全量扫描，首次响应较慢。"
            />
          )}

          {!loading && !error && (
            <section className="mt-7">
              <SectionHeader
                index="01"
                title="口径概览"
                en="SCOPE OVERVIEW"
                note={<>计数合计仅在当前口径内有效</>}
              />
              <div className="mt-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                <MetricTile
                  value={cards.length}
                  label="信源数"
                  sub={`口径 ${scopeLabel}`}
                />
                <MetricTile
                  value={totals.nTotal.toLocaleString()}
                  label="记录条数"
                  sub="含未结算"
                />
                <MetricTile
                  value={totals.nSettled.toLocaleString()}
                  label="已结算条数"
                  sub="进入比率计算的样本"
                />
                <MetricTile
                  value={`${totals.readable} / ${cards.length}`}
                  label="可读比率的信源"
                  sub={`其余 ${cards.length - totals.readable} 个只报计数`}
                />
              </div>
            </section>
          )}

          {!loading && !error && aggregates && (
            <section className="mt-8">
              <SectionHeader
                index="02"
                title="语料构成"
                en="CORPUS COMPOSITION"
                note={
                  <>
                    全部为计数 · 无比率
                    <br />
                    月度形状 = 入库节奏，非信源行为节奏
                  </>
                }
              />
              <div className="mt-3 grid gap-2.5 lg:grid-cols-2">
                <div className="editorial-panel rounded-sm px-4 py-3.5 lg:col-span-2">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    月度活动 · 按 canonical signal clock 归月
                  </div>
                  <div className="mt-2.5">
                    <MonthlyActivityBars aggregates={aggregates} />
                  </div>
                </div>
                <div className="editorial-panel rounded-sm px-4 py-3.5">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    方向构成 · 按条数
                  </div>
                  <div className="mt-2">
                    <CompositionRibbon
                      segments={DIRECTION_SEGMENT_META.map((d) => ({
                        key: d.key,
                        label: d.label,
                        count: aggregates.directions[d.key] ?? 0,
                        color: d.color,
                      }))}
                    />
                  </div>
                  <div className="mt-3 border-t border-[var(--grid-line)] pt-2.5 text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    期限档构成 · 按条数
                  </div>
                  <div className="mt-2">
                    <CompositionRibbon
                      segments={countSegments(
                        aggregates.time_horizons,
                        TIME_HORIZON_LABEL,
                        MARKET_RAMP,
                      )}
                    />
                  </div>
                </div>
                <div className="editorial-panel rounded-sm px-4 py-3.5">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    离场原因 · 仅已结算行
                  </div>
                  <div className="mt-2">
                    <CompositionRibbon
                      segments={countSegments(
                        aggregates.exit_reasons,
                        EXIT_REASON_LABEL,
                        MARKET_RAMP,
                      )}
                      emptyHint="该口径下暂无已结算行。"
                    />
                  </div>
                  <div className="mt-3 border-t border-[var(--grid-line)] pt-2.5 text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    市场构成 · 按条数
                  </div>
                  <div className="mt-2">
                    <CompositionRibbon
                      segments={marketSegments(aggregates.markets)}
                    />
                  </div>
                </div>
              </div>
              {aggregates.notes.length > 0 && (
                <div className="mt-2.5">
                  <NoteList notes={aggregates.notes} />
                </div>
              )}
            </section>
          )}

          {!loading && !error && (marketSlices || monthSlices) && (
            <section className="mt-8">
              <SectionHeader
                index="03"
                title="胜率切片"
                en="WIN-RATE SLICES"
                note={
                  <>
                    每片独立过效力门 · 样本不足只报计数
                    <br />
                    切片间差异不构成对未来的预测
                  </>
                }
              />
              <div className="mt-3 grid gap-2.5 lg:grid-cols-2">
                {marketSlices && (
                  <SlicePanel
                    title="按市场 · ticker 推导的真实市场"
                    slices={marketSlices}
                    labelOf={(k) =>
                      k === "unknown" ? "未归属" : (MARKET_LABEL[k] ?? k)
                    }
                  />
                )}
                {monthSlices && (
                  <SlicePanel
                    title="按月 · signal clock 归月"
                    slices={monthSlices}
                    labelOf={(k) => k}
                  />
                )}
              </div>
              {(marketSlices ?? monthSlices) && (
                <div className="mt-2.5">
                  <NoteList notes={(marketSlices ?? monthSlices)!.notes} />
                </div>
              )}
            </section>
          )}

          {!loading && !error && (
            <section className="mt-8 pb-12">
              <SectionHeader
                index="04"
                title="信源记录卡"
                en="RECORD CARDS"
                note={
                  <>
                    按已结算样本量降序 · 非排名
                    <br />
                    样本不足者留白，不填零
                  </>
                }
              />
              {cards.length === 0 ? (
                <BlankCell>该口径下暂无记录卡。</BlankCell>
              ) : (
                <div className="mt-3.5 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                  {cards.map((card) => (
                    <RecordCard key={card.creator_id} card={card} />
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
