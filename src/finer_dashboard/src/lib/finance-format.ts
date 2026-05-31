/**
 * Shared finance formatting + color helpers (app-wide).
 *
 * Color convention follows the design tokens in globals.css and the
 * finer-financial-frontend-design skill: China market convention where
 * positive/up = red (--chart-up), negative/down = green (--chart-down).
 * Used by both the KOL Research View and the legacy /kol pages so the
 * convention stays consistent across surfaces.
 */

/** Tailwind text color class for a signed numeric value (gain=red, loss=green). */
export function returnToneClass(value: number): string {
  if (value > 0) return "text-[color:var(--chart-up)]";
  if (value < 0) return "text-[color:var(--chart-down)]";
  return "text-foreground/50";
}

/** Map an adapter keyStat tone to a China-convention text color class. */
export function keyStatToneClass(tone: "positive" | "negative" | "neutral"): string {
  if (tone === "positive") return "text-[color:var(--chart-up)]";
  if (tone === "negative") return "text-[color:var(--chart-down)]";
  return "text-foreground";
}

/** Format a percentage value with explicit sign. */
export function formatPct(value: number, digits = 1): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}%`;
}

/** Human-readable platform label. */
export function platformLabel(platform: string): string {
  const labels: Record<string, string> = {
    wechat: "微信公众号",
    bilibili: "B站",
    feishu: "飞书",
  };
  return labels[platform] || platform;
}

/** Investment direction display style (China convention: 看多=红, 看空=绿). */
export function directionStyle(direction: string): { label: string; cls: string } {
  switch (direction) {
    case "bullish":
      return { label: "看多", cls: "text-[color:var(--chart-up)] bg-[rgba(225,27,34,0.08)]" };
    case "bearish":
      return { label: "看空", cls: "text-[color:var(--chart-down)] bg-[rgba(16,185,129,0.12)]" };
    default:
      return { label: "中性", cls: "text-amber-700 bg-amber-50" };
  }
}

/** Text color class for a 0-5 KOL score. */
export function scoreToneClass(score: number): string {
  if (score >= 4.5) return "text-[color:var(--chart-up)]";
  if (score >= 4.0) return "text-[var(--accent-gold)]";
  if (score >= 3.5) return "text-amber-600";
  return "text-foreground/50";
}
