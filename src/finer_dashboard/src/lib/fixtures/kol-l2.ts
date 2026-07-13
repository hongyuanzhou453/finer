/**
 * L2 bridge: derive a per-KOL 观点潮汐快照 (KOLSnapshotData) from the radar fixture,
 * so the credibility board / actionable cards can drill into a KOL accountability page.
 * Same data source as the radar (KOL_RADAR_FIXTURE) → the board's 信誉/命中 numbers
 * reconcile with the KOL page. The 本期研判 narrative is data-derived (live: F7/LLM).
 */
import type { KOLRadarData, RadarKOL } from "./kol-radar";
import {
  deriveHighlights,
  deriveSummary,
  netStance,
  type KOLSnapshotData,
} from "./kol-snapshot";

function fmtPctSigned(x: number): string {
  return `${x > 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
}

function narrativeFor(kol: RadarKOL): string {
  const summary = deriveSummary(kol.viewpoints);
  const highlights = deriveHighlights(kol.viewpoints);
  const net = netStance(summary);
  const lean = net >= 2 ? "立场偏多" : net <= -2 ? "立场偏空" : "立场分歧";

  const parts: string[] = [
    `${kol.name}（${kol.style}）近期共 ${summary.totalActions} 次明确观点，${lean}（${summary.bullishCount} 多 / ${summary.bearishCount} 空）`,
  ];
  if (highlights.hitRate !== null) {
    parts.push(
      `结算命中率 ${Math.round(highlights.hitRate * 100)}%（${highlights.settledCount} 笔）`,
    );
  }
  if (highlights.bestReturn && highlights.bestReturn.returnPct != null) {
    parts.push(
      `最佳兑现 ${highlights.bestReturn.companyName} ${fmtPctSigned(highlights.bestReturn.returnPct)}`,
    );
  }
  // Only call it a 教训 when there's an actual loss — an all-winning KOL has none.
  if (highlights.worstReturn && (highlights.worstReturn.returnPct ?? 0) < 0) {
    parts.push(
      `最大教训 ${highlights.worstReturn.companyName} ${fmtPctSigned(highlights.worstReturn.returnPct ?? 0)}`,
    );
  }
  return `${parts.join("；")}。`;
}

export function deriveKolSnapshot(
  data: KOLRadarData,
  kolId: string,
): KOLSnapshotData | null {
  const kol = data.kols.find((k) => k.kolId === kolId);
  if (!kol) return null;
  return {
    kolId: kol.kolId,
    kolName: kol.name,
    handle: kol.handle,
    style: kol.style,
    platform: kol.platform,
    generatedAt: data.generatedAt,
    narrative: narrativeFor(kol),
    viewpoints: kol.viewpoints,
  };
}
