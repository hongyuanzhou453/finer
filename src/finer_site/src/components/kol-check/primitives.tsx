/**
 * kol-check 领域 primitives：共享原子一律来自 components/shared/primitives
 * （唯一真相源），本文件只保留领域专属件（ReturnChip 的回测措辞）与
 * 兼容别名（fmtPct）。
 *
 * 注意：负号已随合并统一为 U+2212「−」（此前本目录走 toFixed 的 ASCII
 * 连字符，与 /records 同数字不同负号）。
 */
import React from "react";
import { fmtSignedPct, returnColor } from "../shared/primitives";

export {
  ConfidenceMeter,
  DIRECTION_META,
  DirectionTag,
  SectionHeader,
  fmtConfidence,
  fmtDate,
} from "../shared/primitives";

/** 兼容别名：历史调用方用 fmtPct 表示带符号收益格式化。 */
export { fmtSignedPct as fmtPct } from "../shared/primitives";

// ---- return chip（回测领域措辞：null=待回测、0=未触发）----------------------

export function ReturnChip({
  value,
  muted,
}: {
  value: number | null;
  muted?: string;
}) {
  if (value === null) {
    return (
      <span className="tabular-nums text-xs text-[var(--ink-soft)]">
        {muted ?? "待回测"}
      </span>
    );
  }
  if (value === 0) {
    return (
      <span className="tabular-nums text-xs text-[var(--ink-soft)]">未触发</span>
    );
  }
  return (
    <span
      className="tabular-nums text-xs font-semibold"
      style={{ color: returnColor(value) }}
    >
      {fmtSignedPct(value)}
    </span>
  );
}
