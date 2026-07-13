"use client";

/**
 * 交易风格画像卡 — declared（自述/人工标注）vs observed（实际行为统计）对照。
 * 数据来自 GET /api/kol/style/{creator_id}（TradingStyleProfile, contracts.ts）。
 * 任一层缺失时渲染对应降级态，不阻塞整卡。
 */
import React from "react";
import type {
  DeclaredTradingStyle,
  EntryStyle,
  ObservedTradingStyle,
  TradingStyleProfile,
} from "@/lib/contracts";

const ENTRY_STYLE_LABEL: Record<EntryStyle, string> = {
  left_side: "左侧（逢低布局）",
  right_side: "右侧（趋势确认）",
  mixed: "混合",
  unknown: "未标注",
};

type Verdict = "match" | "conflict" | "insufficient";

// 一致性判定不用行情涨跌色（红涨绿跌语义会把「冲突」渲染成正面色）：
// 一致 = 沉稳确认色，冲突 = 警示红。
const VERDICT_META: Record<Verdict, { label: string; className: string }> = {
  match: { label: "✓ 一致", className: "text-[var(--accent-teal)]" },
  conflict: { label: "⚠ 冲突", className: "font-semibold text-[var(--morningstar-red)]" },
  insufficient: { label: "— 数据不足", className: "text-[var(--ink-soft)]" },
};

function fmtDeclaredBool(value: boolean | null): string {
  if (value === null) return "未标注";
  return value ? "使用" : "不使用";
}

function fmtRatio(ratio: number): string {
  return `${(ratio * 100).toFixed(0)}%`;
}

interface DimensionRow {
  key: string;
  label: string;
  declaredText: string;
  observedText: string;
  verdict: Verdict;
}

function boolDimension(
  label: string,
  declared: boolean | null,
  mentionCount: number | null,
  sampleSize: number | null,
  mentionVerb: string,
): DimensionRow {
  const declaredText = fmtDeclaredBool(declared);
  let observedText = "暂无行为数据";
  let verdict: Verdict = "insufficient";

  if (mentionCount !== null && sampleSize !== null) {
    observedText =
      mentionCount > 0
        ? `${mentionVerb} ${mentionCount} 次 · n=${sampleSize}`
        : `未观测到 · n=${sampleSize}`;
    if (declared === false && mentionCount > 0) {
      verdict = "conflict";
    } else if (declared !== null && (declared === mentionCount > 0)) {
      verdict = "match";
    }
    // declared=true 但未观测到：语料未覆盖 ≠ 冲突，保持 insufficient
  }

  return { key: label, label, declaredText, observedText, verdict };
}

function buildRows(
  declared: DeclaredTradingStyle | null,
  observed: ObservedTradingStyle | null,
): DimensionRow[] {
  const n = observed?.sample_size ?? null;

  const margin = boolDimension(
    "融资",
    declared?.uses_margin ?? null,
    observed?.margin_mention_count ?? null,
    n,
    "提及融资",
  );
  const leverage = boolDimension(
    "杠杆",
    declared?.uses_leverage ?? null,
    observed?.leverage_mention_count ?? null,
    n,
    "提及杠杆",
  );

  // 做空：observed 证据是方向性 action 中的空头侧占比
  const declaredShort = declared?.does_short ?? null;
  let shortObserved = "暂无行为数据";
  let shortVerdict: Verdict = "insufficient";
  if (observed && observed.short_ratio !== null) {
    shortObserved = `做空 ${fmtRatio(observed.short_ratio)} · n=${observed.directional_sample_size}`;
    if (declaredShort === false && observed.short_side_count > 0) {
      shortVerdict = "conflict";
    } else if (
      declaredShort !== null &&
      declaredShort === observed.short_side_count > 0
    ) {
      shortVerdict = "match";
    }
  } else if (observed) {
    shortObserved = "无方向性样本";
  }

  // 入场风格：declared entry_style vs observed 多数决
  const declaredEntry = declared?.entry_style ?? "unknown";
  const observedEntry = observed?.entry_style_observed ?? "unknown";
  let entryObserved = "暂无行为数据";
  let entryVerdict: Verdict = "insufficient";
  if (observed) {
    if (observedEntry !== "unknown") {
      entryObserved = `${ENTRY_STYLE_LABEL[observedEntry]} · 左${observed.left_side_count}/右${observed.right_side_count}`;
    } else {
      entryObserved = `信号不足 · 左${observed.left_side_count}/右${observed.right_side_count}`;
    }
    if (declaredEntry !== "unknown" && observedEntry !== "unknown") {
      entryVerdict = declaredEntry === observedEntry ? "match" : "conflict";
    }
  }

  return [
    margin,
    leverage,
    {
      key: "做空",
      label: "做空",
      declaredText: declaredShort === null ? "未标注" : declaredShort ? "做空" : "不做空",
      observedText: shortObserved,
      verdict: shortVerdict,
    },
    {
      key: "入场风格",
      label: "入场风格",
      declaredText: ENTRY_STYLE_LABEL[declaredEntry],
      observedText: entryObserved,
      verdict: entryVerdict,
    },
  ];
}

export function TradingStyleCard({
  profile,
}: {
  profile?: TradingStyleProfile | null;
}) {
  if (!profile || (!profile.declared && !profile.observed)) {
    return (
      <div className="editorial-panel rounded-sm p-4 text-[12px] text-[var(--ink-soft)]">
        暂无交易风格画像 — declared 层待人工标注（configs/creators），observed
        层待该 KOL 归属 action 数据积累。
      </div>
    );
  }

  const rows = buildRows(profile.declared, profile.observed);
  const lowSample = profile.observed?.low_sample ?? true;

  return (
    <div className="editorial-panel rounded-sm p-4">
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-[var(--table-border)] text-left text-[10px] uppercase tracking-[0.16em] text-[var(--ink-soft)]">
            <th className="py-2 pr-3 font-normal">维度</th>
            <th className="py-2 pr-3 font-normal">自述 · DECLARED</th>
            <th className="py-2 pr-3 font-normal">
              实际行为 · OBSERVED
              {profile.observed && lowSample ? (
                <span className="ml-2 rounded-sm border border-[var(--table-border)] px-1 py-0.5 normal-case tracking-normal">
                  样本不足
                </span>
              ) : null}
            </th>
            <th className="py-2 font-normal">一致性</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const meta = VERDICT_META[row.verdict];
            return (
              <tr key={row.key} className="border-b border-[var(--grid-line)]">
                <td className="py-2.5 pr-3 font-medium text-[var(--foreground)]">
                  {row.label}
                </td>
                <td className="py-2.5 pr-3 text-[var(--foreground)]">
                  {row.declaredText}
                </td>
                <td className="tabular-nums py-2.5 pr-3 text-[var(--foreground)]">
                  {row.observedText}
                </td>
                <td className={`py-2.5 ${meta.className}`}>{meta.label}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {profile.declared?.evidence_notes?.length ? (
        <div className="mt-3 text-[11px] leading-relaxed text-[var(--ink-soft)]">
          <span className="uppercase tracking-[0.16em]">标注依据</span>
          <ul className="mt-1 list-inside list-disc">
            {profile.declared.evidence_notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-3 border-t border-[var(--grid-line)] pt-2 text-[11px] text-[var(--ink-soft)]">
        自述来自人工标注；实际行为由 F5 归属 action 统计（融资/杠杆/左右侧信号自
        F3 提取，做空自操作链）。冲突行提示「言行不一」，供审阅参考。
      </div>
    </div>
  );
}
