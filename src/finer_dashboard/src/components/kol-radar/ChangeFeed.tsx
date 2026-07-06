/**
 * 今日异动流 — compact, scannable feed of cross-KOL stance changes.
 * One card per event; type drives the marker color + Chinese label.
 * Red = bullish/long basis (China convention), green = loss/downside.
 */
import {
  DirectionTag,
  ReturnChip,
  fmtConfidence,
} from "@/components/kol-snapshot/primitives";
import type {
  RadarChangeEvent,
  ChangeFeedItem,
  ChangeType,
} from "@/lib/fixtures/kol-radar";

// ---- type → label / color mapping (single source) ---------------------------

interface ChangeMeta {
  label: string;
  color: string;
}

const CHANGE_META: Record<ChangeType, ChangeMeta> = {
  flip: { label: "翻向", color: "var(--accent-teal)" },
  new_high_conviction: { label: "新高信念", color: "var(--chart-up)" },
  new_call: { label: "新增", color: "var(--chart-up)" },
  stop_loss: { label: "触发止损", color: "var(--chart-down)" },
  score_change: { label: "信誉变动", color: "var(--accent-gold)" },
  consensus_alert: { label: "共识异动", color: "var(--accent-teal)" },
};

// ---- per-event value rendering ----------------------------------------------

function EventValue({ ev }: { ev: RadarChangeEvent }) {
  if (ev.value === undefined || ev.value === null) return null;

  if (ev.type === "score_change") {
    const sign = ev.value > 0 ? "+" : "";
    return (
      <span
        className="tabular-nums text-[11px] font-semibold"
        style={{ color: "var(--accent-gold)" }}
      >
        信誉 {sign}
        {ev.value}
      </span>
    );
  }

  if (ev.type === "stop_loss") {
    return <ReturnChip value={ev.value} />;
  }

  if (ev.type === "new_high_conviction") {
    return (
      <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
        信念 {fmtConfidence(ev.value)}
      </span>
    );
  }

  return null;
}

// ---- card -------------------------------------------------------------------

function ChangeCard({ ev }: { ev: ChangeFeedItem }) {
  const meta = CHANGE_META[ev.type];
  const hasFlip = Boolean(ev.fromDirection && ev.toDirection);

  return (
    <article className="editorial-card rounded-sm p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: meta.color }}
          />
          <span
            className="text-[11px] font-semibold"
            style={{ color: meta.color }}
          >
            {meta.label}
          </span>
        </div>
        <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
          {ev.ageLabel}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {ev.kolName ? (
          <span className="text-[13px] font-medium text-[var(--foreground)]">
            {ev.kolName}
          </span>
        ) : null}
        {ev.companyName ? (
          <span className="flex items-baseline gap-1">
            <span className="text-[13px] text-[var(--foreground)]">
              {ev.companyName}
            </span>
            {ev.ticker ? (
              <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                {ev.ticker}
              </span>
            ) : null}
          </span>
        ) : null}
      </div>

      {hasFlip ? (
        <div className="mt-2 flex items-center gap-1.5">
          <DirectionTag direction={ev.fromDirection!} size="xs" />
          <span className="text-[11px] text-[var(--ink-soft)]">→</span>
          <DirectionTag direction={ev.toDirection!} size="xs" />
        </div>
      ) : null}

      <p className="mt-2 text-[13px] leading-snug text-[var(--ink-soft)]">
        {ev.detail}
      </p>

      <div className="mt-2 min-h-[16px]">
        <EventValue ev={ev} />
      </div>
    </article>
  );
}

// ---- feed -------------------------------------------------------------------

export function ChangeFeed({ events }: { events: ChangeFeedItem[] }) {
  if (!events.length) {
    return (
      <p className="text-[13px] text-[var(--ink-soft)]">近期暂无异动。</p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {events.map((ev) => (
        <ChangeCard key={ev.id} ev={ev} />
      ))}
    </div>
  );
}
