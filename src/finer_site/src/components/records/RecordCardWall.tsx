"use client";

/**
 * Card wall for the /records snapshot: one card per source × signal class.
 *
 * Red lines enforced here:
 * - display_policy === "count_only" ⇒ NO ratio rendered anywhere on the card
 *   (counts only). All 24 sector cards are count_only by design.
 * - Every rendered ratio sits next to its settled sample count AND its 95%
 *   Wilson interval.
 * - "show_with_warning" renders the ratio plus the backend warning note.
 */
import type { RecordCard, SignalClass } from "@/demo/records/types";
import {
  SIGNAL_CLASS_LABEL,
  TierBadge,
  fmtDate,
  fmtRate,
  fmtSignedPct,
  returnColor,
} from "./primitives";

function topMarkets(mix: Record<string, number>, k = 3): string {
  const entries = Object.entries(mix).sort((a, b) => b[1] - a[1]).slice(0, k);
  if (entries.length === 0) return "—";
  return entries.map(([m, n]) => `${m} ${n}`).join(" · ");
}

function CardRatioBlock({ card }: { card: RecordCard }) {
  const s = card.sufficiency;

  if (s.display_policy === "count_only") {
    // Red line: zero ratios for count_only — counts only.
    return (
      <div className="mt-3">
        <div className="tabular-nums text-[24px] font-bold leading-none tracking-tight text-foreground">
          {s.settled_n}
          <span className="text-[14px] font-semibold text-foreground/50">
            {" "}/ {s.total_n}
          </span>
        </div>
        <div className="mt-1.5 text-[11px] leading-4 text-[var(--ink-soft)]">
          已结算 {s.settled_n} / 总数 {s.total_n}（样本不足，只报计数）
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <div className="flex items-baseline gap-2">
        <span className="tabular-nums text-[28px] font-bold leading-none tracking-tight text-foreground">
          {fmtRate(s.point_estimate)}
        </span>
        <span className="tabular-nums text-[11px] leading-4 text-[var(--ink-soft)]">
          95% 区间 {fmtRate(s.wilson_low)}–{fmtRate(s.wilson_high)}
        </span>
      </div>
      <div className="mt-1 text-[11px] leading-4 text-[var(--ink-soft)]">
        结算命中率（历史）· 已结算 {s.settled_n} 条
      </div>
      {s.display_policy === "show_with_warning" && s.notes[0] ? (
        <div className="mt-1.5 border-l-2 border-[var(--accent-gold)] pl-2 text-[11px] leading-4 text-[var(--accent-gold)]">
          {s.notes[0]}
        </div>
      ) : null}
    </div>
  );
}

export function RecordCardWall({
  cards,
  signalClass,
  onSelect,
}: {
  cards: RecordCard[];
  signalClass: SignalClass;
  onSelect: (card: RecordCard) => void;
}) {
  return (
    <div
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      data-testid="record-card-wall"
    >
      {cards.map((card) => (
        <button
          key={`${card.signal_class}:${card.creator_id}`}
          type="button"
          onClick={() => onSelect(card)}
          data-testid="record-card"
          className="editorial-card group flex flex-col rounded-sm p-5 text-left transition-shadow hover:shadow-[var(--shadow-soft)]"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[16px] font-bold tracking-tight text-foreground group-hover:text-morningstar-red">
                {card.creator_id}
              </div>
              <div className="mt-0.5 text-[11px] text-foreground/45">
                {SIGNAL_CLASS_LABEL[signalClass]} · 历史记录
              </div>
            </div>
            <TierBadge tier={card.sufficiency.tier} />
          </div>

          <CardRatioBlock card={card} />

          <dl className="mt-4 space-y-1.5 border-t border-[var(--grid-line)] pt-3 text-[11px] leading-4">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-foreground/45">已结算 / 总数</dt>
              <dd className="tabular-nums text-foreground/80">
                {card.n_settled} / {card.n_total}
              </dd>
            </div>
            {/* 均值收益**也是比率**，必须与命中率同样受 count_only 门约束。
                此前它在 `CardRatioBlock` 的门**外面**无条件渲染：34 张 count_only
                卡里 24 张照样印出均值收益（KeyBanc n_settled=1 印 +58.0%），
                另外 10 张 mean_return 是 null 却被印成「0.0%」。
                门写对了，只是开在了门外。 */}
            {card.sufficiency.display_policy !== "count_only" && (
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-foreground/45">均值收益（历史）</dt>
                <dd
                  className="tabular-nums font-semibold"
                  style={{ color: returnColor(card.mean_return) }}
                >
                  {fmtSignedPct(card.mean_return)}
                </dd>
              </div>
            )}
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-foreground/45">主要市场</dt>
              <dd className="tabular-nums text-foreground/80">
                {topMarkets(card.market_mix)}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-foreground/45">记录窗口</dt>
              <dd className="tabular-nums text-foreground/80">
                {fmtDate(card.first_action_at)} – {fmtDate(card.last_action_at)}
              </dd>
            </div>
          </dl>

          <div className="mt-3 text-[11px] font-semibold text-morningstar-red opacity-0 transition-opacity group-hover:opacity-100">
            点开完整记录 →
          </div>
        </button>
      ))}
    </div>
  );
}
