"use client";

/**
 * Per-source record list for the /records snapshot.
 *
 * ⚠️ Rows files mix BOTH signal classes; this view filters rows by the
 * selected card's signal_class so row counts reconcile with the card face
 * (e.g. UBS: 670 stock-rating rows out of a 736-row file).
 *
 * Detail panel = inline row expansion (keeps the static-export layout simple).
 */
import { useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { RecordCard, RecordRow, RowDirection } from "@/demo/records/types";
import {
  DirectionChip,
  SIGNAL_CLASS_LABEL,
  SettleChip,
  TierBadge,
  actionTypeLabel,
  exitReasonLabel,
  fmtDate,
  fmtRate,
  fmtSignedPct,
  horizonLabel,
  returnColor,
} from "./primitives";

const PAGE_SIZE = 50;
const COL_COUNT = 8;

function HeaderRatio({ card }: { card: RecordCard }) {
  const s = card.sufficiency;
  if (s.display_policy === "count_only") {
    // Red line: count_only ⇒ no ratio in the header restatement either.
    return (
      <span className="tabular-nums">
        已结算 {s.settled_n} / 总数 {s.total_n}（样本不足，只报计数）
      </span>
    );
  }
  return (
    <span className="tabular-nums">
      结算命中率（历史）{fmtRate(s.point_estimate)} · 95% 区间{" "}
      {fmtRate(s.wilson_low)}–{fmtRate(s.wilson_high)} · 已结算 {s.settled_n} 条
      {/* show_with_warning 契约：比率可渲染，但后端告警注必须随行（types.ts） */}
      {s.display_policy === "show_with_warning" && s.notes[0] ? (
        <span className="ml-2 text-[var(--accent-gold)]">{s.notes[0]}</span>
      ) : null}
    </span>
  );
}

function RowDetail({ row, asOf }: { row: RecordRow; asOf: string }) {
  const fields: { k: string; v: React.ReactNode }[] = [
    { k: "published_at（发布）", v: row.published_at },
    { k: "executable_at（可执行）", v: row.executable_at },
    { k: "action_type", v: `${actionTypeLabel(row.action_type)} (${row.action_type})` },
    { k: "time_horizon", v: `${horizonLabel(row.time_horizon)} (${row.time_horizon})` },
    { k: "市场", v: row.market },
    {
      k: "评级",
      v: row.rating
        ? row.rating_prior
          ? `${row.rating_prior} → ${row.rating}`
          : row.rating
        : "—",
    },
    {
      k: "目标价",
      v:
        row.target_price !== null
          ? `${row.target_price} ${row.target_price_currency ?? ""}`.trim()
          : "—",
    },
    { k: "evidence span", v: `${row.evidence_span_count} 个证据片段` },
    {
      k: "结算",
      v:
        row.settle.status === "settled" ? (
          <span>
            <span
              className="tabular-nums font-semibold"
              style={{
                color: returnColor(row.settle.return_pct ?? 0),
              }}
            >
              {typeof row.settle.return_pct === "number"
                ? fmtSignedPct(row.settle.return_pct)
                : "—"}
            </span>
            {" · "}
            {exitReasonLabel(row.settle.exit_reason)}
            {typeof row.settle.holding_days === "number"
              ? ` · 持有 ${row.settle.holding_days} 天`
              : ""}
          </span>
        ) : (
          "待结算（截至快照日尚未离场）"
        ),
    },
  ];
  return (
    <div className="bg-[var(--surface-muted)] px-4 py-4" data-testid="row-detail">
      <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((f) => (
          <div key={f.k} className="flex items-baseline gap-2 text-[12px]">
            <span className="shrink-0 text-foreground/45">{f.k}</span>
            <span className="min-w-0 text-foreground/85">{f.v}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[var(--grid-line)] pt-2.5">
        {row.canonical ? (
          <span className="rounded-sm border border-[rgba(31,106,103,0.3)] bg-[rgba(31,106,103,0.08)] px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-[var(--accent-teal)]">
            CANONICAL
          </span>
        ) : null}
        <span className="font-mono text-[11px] text-foreground/50">
          intent_id: {row.intent_id}
        </span>
        <span className="font-mono text-[11px] text-foreground/50">
          trade_action_id: {row.id}
        </span>
        <span className="tabular-nums text-[11px] text-foreground/40">
          快照 {asOf}
        </span>
      </div>
      <p className="mt-2.5 text-[11px] leading-5 text-[var(--ink-soft)]">
        完整证据链（研报原文片段级下钻）在产品 /audit 内提供；公开快照只含结构化事实，不含研报原文。
      </p>
    </div>
  );
}

export function CreatorRecordView({
  card,
  rows,
  asOf,
  onBack,
}: {
  card: RecordCard;
  /** Full rows file content — filtered here by card.signal_class. */
  rows: RecordRow[];
  asOf: string;
  onBack: () => void;
}) {
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const [dirFilter, setDirFilter] = useState<"all" | RowDirection>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Red line: filter to the card's signal class — rows files mix both.
  const classRows = useMemo(
    () => rows.filter((r) => r.signal_class === card.signal_class),
    [rows, card.signal_class],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return classRows.filter((r) => {
      if (dirFilter !== "all" && r.direction !== dirFilter) return false;
      if (
        q &&
        !r.ticker.toLowerCase().includes(q) &&
        !r.name.toLowerCase().includes(q)
      )
        return false;
      return true;
    });
  }, [classRows, query, dirFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(
    safePage * PAGE_SIZE,
    (safePage + 1) * PAGE_SIZE,
  );

  return (
    <div data-testid="creator-record-view">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-foreground/70 transition-colors hover:text-morningstar-red"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={2} />
        返回全部信源
      </button>

      {/* source header: card-face restatement + window + declaration */}
      <div className="mt-4 border-t-2 border-morningstar-red bg-white p-5 shadow-[var(--shadow-soft)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[22px] font-bold tracking-tight text-foreground">
              {card.creator_id}
            </h2>
            <div className="mt-1 text-[12px] text-foreground/50">
              {SIGNAL_CLASS_LABEL[card.signal_class]} · 记录窗口{" "}
              <span className="tabular-nums">
                {fmtDate(card.first_action_at)} – {fmtDate(card.last_action_at)}
              </span>{" "}
              · 快照冻结于 <span className="tabular-nums">{asOf}</span>
            </div>
          </div>
          <TierBadge tier={card.sufficiency.tier} />
        </div>
        <div className="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[13px] text-foreground/80">
          <HeaderRatio card={card} />
          <span className="tabular-nums">
            均值收益（历史）{" "}
            <span
              className="font-semibold"
              style={{ color: returnColor(card.mean_return) }}
            >
              {fmtSignedPct(card.mean_return)}
            </span>
          </span>
          <span className="tabular-nums">
            记录 {card.n_settled} / {card.n_total} 已结算
          </span>
        </div>
        <p className="mt-2.5 text-[12px] leading-5 text-[var(--ink-soft)]">
          这是一份历史记录，不是排名，也不是推荐；本平台未观测到该指标的跨期持续性，数字不构成对未来的预测。
        </p>
      </div>

      {/* filters */}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          placeholder="搜索 ticker / 名称"
          className="w-52 rounded-sm border border-[var(--table-border)] bg-white px-3 py-1.5 text-[13px] text-foreground placeholder:text-foreground/35 focus:border-foreground/40 focus:outline-none"
        />
        <div className="segmented-control" role="tablist" aria-label="方向筛选">
          {(
            [
              ["all", "全部"],
              ["bullish", "看多"],
              ["bearish", "看空"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-selected={dirFilter === key}
              onClick={() => {
                setDirFilter(key);
                setPage(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="tabular-nums text-[12px] text-foreground/45">
          {filtered.length} 条（{SIGNAL_CLASS_LABEL[card.signal_class]}口径）
        </span>
      </div>

      {/* table */}
      {/* max-height 让纵向滚动发生在容器内——否则 sticky 相对页面滚动是 no-op */}
      <div className="mt-3 max-h-[70vh] overflow-auto rounded-sm border border-[var(--table-border)] bg-white finer-scrollbar">
        <table className="top-rule-table min-w-[860px]">
          <thead className="sticky top-0 z-10 bg-[var(--table-header-bg)]">
            <tr>
              <th>报告日</th>
              <th>标的</th>
              <th>市场</th>
              <th>评级</th>
              <th className="text-right">目标价</th>
              <th>方向</th>
              <th>期限</th>
              <th>结算（历史）</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row) => (
              <RowPair
                key={row.id}
                row={row}
                asOf={asOf}
                expanded={expandedId === row.id}
                onToggle={() =>
                  setExpandedId((cur) => (cur === row.id ? null : row.id))
                }
              />
            ))}
            {pageRows.length === 0 ? (
              <tr>
                <td
                  colSpan={COL_COUNT}
                  className="py-8 text-center text-[13px] text-[var(--ink-soft)]"
                >
                  当前筛选条件下没有记录
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {/* pagination */}
      {pageCount > 1 ? (
        <div className="mt-3 flex items-center gap-3 text-[13px]">
          <button
            type="button"
            disabled={safePage === 0}
            onClick={() => setPage(safePage - 1)}
            className="rounded-sm border border-[var(--table-border)] bg-white px-3 py-1 font-semibold text-foreground/70 transition-colors enabled:hover:border-foreground/30 disabled:opacity-40"
          >
            上一页
          </button>
          <span className="tabular-nums text-foreground/60">
            第 {safePage + 1} / {pageCount} 页
          </span>
          <button
            type="button"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(safePage + 1)}
            className="rounded-sm border border-[var(--table-border)] bg-white px-3 py-1 font-semibold text-foreground/70 transition-colors enabled:hover:border-foreground/30 disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      ) : null}

      <p className="mt-4 max-w-3xl text-[12px] leading-5 text-[var(--ink-soft)]">
        结算口径：次开盘成交、固定持有窗口与止损参数的机器结算；数字依赖参数选择，为历史记录，不构成对未来的预测。
      </p>
    </div>
  );
}

function RowPair({
  row,
  asOf,
  expanded,
  onToggle,
}: {
  row: RecordRow;
  asOf: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        data-testid="record-row"
        aria-expanded={expanded}
        className={`cursor-pointer transition-colors hover:bg-[var(--surface-muted)] ${
          expanded ? "bg-[var(--surface-muted)]" : ""
        }`}
      >
        <td className="tabular-nums whitespace-nowrap !text-left">
          {row.report_date}
        </td>
        <td>
          <span className="font-mono text-[12px] text-foreground/85">
            {row.ticker}
          </span>
          <span className="ml-1.5 text-[12px] text-foreground/60">
            {row.name}
          </span>
        </td>
        <td className="text-[12px]">{row.market}</td>
        <td className="text-[12px]">
          {row.rating ? (
            row.rating_prior ? (
              <span>
                <span className="text-foreground/45">{row.rating_prior}</span>
                <span className="text-foreground/45"> → </span>
                {row.rating}
              </span>
            ) : (
              row.rating
            )
          ) : (
            "—"
          )}
        </td>
        <td className="tabular-nums whitespace-nowrap">
          {row.target_price !== null
            ? `${row.target_price} ${row.target_price_currency ?? ""}`.trim()
            : "—"}
        </td>
        <td>
          <DirectionChip direction={row.direction} />
        </td>
        <td className="text-[12px]">{horizonLabel(row.time_horizon)}</td>
        <td>
          <SettleChip settle={row.settle} />
        </td>
      </tr>
      {expanded ? (
        <tr>
          <td colSpan={COL_COUNT} className="!p-0">
            <RowDetail row={row} asOf={asOf} />
          </td>
        </tr>
      ) : null}
    </>
  );
}
