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
 *
 * 第一条红线现在由类型系统执行：本组件只接受 `DisplayCard`，count_only 分支上
 * 比率字段不存在，写出来即编译错误（此前它只是组件内的控制流，被同级的
 * `<dl>` 节点绕过去了——见 ./gate.ts）。
 */
import type { SignalClass } from "@/demo/records/types";
import type { DisplayCard } from "./gate";
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

/**
 * 卡面上**全部**比率的唯一渲染点：命中率、区间、均值收益都在这里。
 * 均值收益此前在同级 `<dl>` 里、门外无条件渲染，是本次事故的直接成因。
 */
function CardRatioBlock({ card }: { card: DisplayCard }) {
  if (!card.ratiosPermitted) {
    // Red line: zero ratios for count_only — counts only.
    const s = card.sufficiency;
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

  // 窄化之后才取 sufficiency：在窄化前取出会得到联合类型，比率字段不可访问。
  const s = card.sufficiency;
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
      <div className="mt-1.5 flex items-baseline justify-between gap-3 text-[11px] leading-4">
        <span className="text-foreground/45">均值收益（历史）</span>
        <span
          className="tabular-nums font-semibold"
          style={{ color: returnColor(card.mean_return) }}
        >
          {fmtSignedPct(card.mean_return)}
        </span>
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
  cards: DisplayCard[];
  signalClass: SignalClass;
  onSelect: (card: DisplayCard) => void;
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

          {/* 事实列：计数、市场构成、记录窗口——不含任何比率，
              比率一律在 CardRatioBlock 内（门的唯一执行点）。 */}
          <dl className="mt-4 space-y-1.5 border-t border-[var(--grid-line)] pt-3 text-[11px] leading-4">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-foreground/45">已结算 / 总数</dt>
              <dd className="tabular-nums text-foreground/80">
                {card.n_settled} / {card.n_total}
              </dd>
            </div>
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
