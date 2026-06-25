"use client";

import { useMemo } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EvidenceSpan } from "@/lib/contracts";

/**
 * Resolve a span's character range against the source text.
 * Prefers the schema offsets (char_start/char_end) when they actually match,
 * falls back to indexOf for fixtures / imperfect offsets, null if not found.
 */
function resolveOffset(
  source: string,
  span: Pick<EvidenceSpan, "char_start" | "char_end" | "text">,
): { start: number; end: number } | null {
  const { char_start, char_end, text } = span;
  if (
    Number.isInteger(char_start) &&
    Number.isInteger(char_end) &&
    char_start >= 0 &&
    char_end <= source.length &&
    source.slice(char_start, char_end) === text
  ) {
    return { start: char_start, end: char_end };
  }
  if (text) {
    const idx = source.indexOf(text);
    if (idx >= 0) return { start: idx, end: idx + text.length };
  }
  return null;
}

function HighlightedText({
  source,
  marks,
  activeSpanId,
}: {
  source: string;
  marks: { id: string; start: number; end: number }[];
  activeSpanId: string | null;
}) {
  const parts = useMemo(() => {
    const sorted = [...marks].sort((a, b) => a.start - b.start);
    const out: { t: string; id: string | null }[] = [];
    let cursor = 0;
    for (const m of sorted) {
      if (m.start < cursor) continue; // skip overlaps
      if (m.start > cursor) out.push({ t: source.slice(cursor, m.start), id: null });
      out.push({ t: source.slice(m.start, m.end), id: m.id });
      cursor = m.end;
    }
    if (cursor < source.length) out.push({ t: source.slice(cursor), id: null });
    return out;
  }, [source, marks]);

  return (
    <p className="text-[13px] leading-7 text-foreground/90">
      {parts.map((p, i) =>
        p.id ? (
          <mark
            key={i}
            className={cn(
              "rounded-sm px-0.5 transition-colors",
              activeSpanId === p.id
                ? "bg-[rgba(225,27,34,0.3)]"
                : "bg-[rgba(225,27,34,0.12)]",
            )}
          >
            {p.t}
          </mark>
        ) : (
          <span key={i}>{p.t}</span>
        ),
      )}
    </p>
  );
}

export function EvidenceSource({
  sourceText,
  spans,
  fallbackText,
  activeSpanId,
  onHoverSpan,
}: {
  sourceText: string;
  spans: EvidenceSpan[];
  fallbackText?: string;
  activeSpanId: string | null;
  onHoverSpan: (id: string | null) => void;
}) {
  const resolved = useMemo(
    () =>
      spans
        .map((s) => {
          const r = resolveOffset(sourceText, s);
          return r ? { span: s, ...r } : null;
        })
        .filter((x): x is { span: EvidenceSpan; start: number; end: number } => x !== null),
    [sourceText, spans],
  );

  const marks = resolved.map((r) => ({ id: r.span.evidence_span_id, start: r.start, end: r.end }));

  // non_canonical fallback: highlight the legacy evidence_text (no F2 anchoring)
  const legacyMark = useMemo(() => {
    if (spans.length > 0 || !fallbackText) return null;
    const idx = sourceText.indexOf(fallbackText);
    return idx >= 0 ? [{ id: "__legacy__", start: idx, end: idx + fallbackText.length }] : null;
  }, [spans.length, fallbackText, sourceText]);

  return (
    <div>
      <div className="flex items-center gap-2 border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-4 py-2.5">
        <Search className="h-3.5 w-3.5 text-foreground/50" strokeWidth={1.8} />
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/55">
          Evidence &amp; Provenance
        </span>
      </div>

      <div className="px-4 py-3">
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          原文 · source
        </div>
        <div className="mt-1.5 rounded-sm border border-[var(--grid-line)] bg-[var(--surface-strong)] p-3">
          <HighlightedText
            source={sourceText}
            marks={legacyMark ?? marks}
            activeSpanId={activeSpanId}
          />
        </div>

        {spans.length > 0 ? (
          <>
            <div className="mt-4 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
              证据片段 · EvidenceSpan（F2）
            </div>
            <ul className="mt-1.5 space-y-1.5">
              {spans.map((e) => {
                const found = resolved.some((r) => r.span.evidence_span_id === e.evidence_span_id);
                return (
                  <li
                    key={e.evidence_span_id}
                    onMouseEnter={() => onHoverSpan(e.evidence_span_id)}
                    onMouseLeave={() => onHoverSpan(null)}
                    className={cn(
                      "cursor-default rounded-sm border px-2.5 py-2 transition-colors",
                      activeSpanId === e.evidence_span_id
                        ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.05)]"
                        : "border-[var(--table-border)] bg-white",
                    )}
                  >
                    <div className="flex items-center justify-between font-mono text-[10px] text-foreground/45">
                      <span>{e.evidence_span_id}</span>
                      <span>
                        [{e.char_start}, {e.char_end}]
                        {e.span_type ? ` · ${e.span_type}` : ""}
                        {!found && <span className="text-morningstar-red"> · 偏移未匹配</span>}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[12px] text-foreground/85">「{e.text}」</div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                      <div
                        className="h-full rounded-full bg-morningstar-red/70"
                        style={{ width: `${Math.round(e.confidence * 100)}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <div className="mt-4 rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-3 py-2.5 text-[11px] leading-5 text-[var(--ink-soft)]">
            无 F2 锚定证据。该动作为 legacy 直提，证据仅以原文片段
            {fallbackText ? "（上方高亮）" : ""}保留，未经独立证据锚定。
          </div>
        )}
      </div>
    </div>
  );
}
