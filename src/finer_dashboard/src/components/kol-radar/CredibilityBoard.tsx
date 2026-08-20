/**
 * 01 信源记录板 —— 谁说过什么、结算了多少，**不是排名**。
 *
 * 2026-08-17 改造：此前是「可信度榜 · 按 0-99 信誉分降序」，那个分数由
 * `opinions.py` 的私有阈值（n<5 判低样本，canonical 门是 30/15）收缩得出，
 * 且分数 + 名次正是定位转向明令禁止的形态。现在：默认序 = 已结算样本量降序
 * （稳定输出序），命中率过 CRD-2 效力门才呈现且必与 95% 区间并排。
 *
 * Compact institutional table：趋势并入样本量列，擅长并入 KOL 单元格，
 * 全部 `whitespace-nowrap` 以免中文逐字换行。
 */
import React from "react";
import Link from "next/link";
import type { CredibilityRow } from "@/lib/fixtures/kol-radar";
import { DirectionTag, fmtConfidence } from "@/components/kol-snapshot/primitives";
import { DEMO_RADAR_LINKS, kolHref, type RadarLinks } from "./links";

const TREND_META: Record<CredibilityRow["trend"], { glyph: string; color: string; label: string }> = {
  up: { glyph: "↑", color: "var(--chart-up)", label: "上升" },
  down: { glyph: "↓", color: "var(--chart-down)", label: "下降" },
  flat: { glyph: "→", color: "#8a8278", label: "持平" },
};

function stanceColor(label: CredibilityRow["stanceLabel"]): string {
  return label === "偏多"
    ? "var(--chart-up)"
    : label === "偏空"
      ? "var(--chart-down)"
      : "#8a8278";
}

export function CredibilityBoard({
  rows,
  links = DEMO_RADAR_LINKS,
}: {
  rows: CredibilityRow[];
  links?: RadarLinks;
}) {
  return (
    <div className="finer-scrollbar -mx-1 overflow-x-auto px-1">
      <table className="top-rule-table min-w-[600px]">
        <colgroup>
        <col style={{ width: "34px" }} />
        <col />
        <col style={{ width: "104px" }} />
        <col style={{ width: "82px" }} />
        <col style={{ width: "80px" }} />
        <col style={{ width: "158px" }} />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">序</th>
          <th scope="col">KOL</th>
          <th scope="col" className="text-right">已结算</th>
          <th scope="col" className="text-right">命中率</th>
          <th scope="col">当前立场</th>
          <th scope="col">当前主推</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const trend = TREND_META[r.trend];
          return (
            <tr key={r.kolId}>
              <td className="tabular-nums align-top text-[var(--ink-soft)]">
                {String(i + 1).padStart(2, "0")}
              </td>

              <td className="align-top">
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <Link
                    href={kolHref(links, r.kolId)}
                    className="font-semibold text-[var(--foreground)] hover:text-[var(--morningstar-red)] hover:underline"
                  >
                    {r.name}
                  </Link>
                  <span className="rounded-sm bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--ink-soft)]">
                    {r.style}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.specialties.map((s) => (
                    <span
                      key={s}
                      className="whitespace-nowrap rounded-sm border border-[var(--grid-line)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--ink-soft)]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </td>

              <td className="align-top">
                {/* 已结算样本量：默认序所依据的事实。此前这里是 0-99 信誉分
                    + 金色进度条，那是私有阈值下的收缩分，已于 2026-08-17 下线。 */}
                <div className="flex items-baseline justify-end gap-1.5">
                  <span className="tabular-nums text-xl font-semibold leading-none text-[var(--foreground)]">
                    {r.settledCount}
                  </span>
                  <span
                    className="text-sm font-semibold leading-none"
                    style={{ color: trend.color }}
                    title={`近 45 天已结算收益趋势 ${trend.label}`}
                  >
                    {trend.glyph}
                  </span>
                </div>
                <div className="mt-1 text-right text-[10px] text-[var(--ink-soft)]">
                  笔已结算
                </div>
              </td>

              <td className="align-top text-right">
                {/* CRD-2：门未过一律不渲染比率；过门则必须与 95% 区间并排。 */}
                {r.ratiosPermitted && r.hitRate !== null ? (
                  <>
                    <div className="tabular-nums font-medium text-[var(--foreground)]">
                      {fmtConfidence(r.hitRate)}
                    </div>
                    <div className="tabular-nums text-[10px] text-[var(--ink-soft)]">
                      {r.wilsonLow !== null && r.wilsonHigh !== null
                        ? `95% ${fmtConfidence(r.wilsonLow)}–${fmtConfidence(r.wilsonHigh)}`
                        : "区间未提供"}
                    </div>
                  </>
                ) : (
                  <div
                    className="text-[11px] text-[var(--ink-soft)]"
                    title="已结算样本不足，不呈现比率——留白比一个不可靠的数字诚实"
                  >
                    样本不足 · 仅计数
                  </div>
                )}
              </td>

              <td className="whitespace-nowrap align-top">
                <span className="font-medium" style={{ color: stanceColor(r.stanceLabel) }}>
                  {r.stanceLabel}
                </span>{" "}
                <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                  {r.netStance >= 0 ? `+${r.netStance}` : r.netStance}
                </span>
              </td>

              <td className="align-top">
                {r.topCall ? (
                  <div className="flex items-center gap-1.5 whitespace-nowrap">
                    <span className="font-medium text-[var(--foreground)]">
                      {r.topCall.companyName}
                    </span>
                    <DirectionTag direction={r.topCall.direction} size="xs" />
                    <span className="tabular-nums text-[11px] text-[var(--ink-soft)]">
                      {fmtConfidence(r.topCall.confidence)}
                    </span>
                  </div>
                ) : (
                  <span className="text-[var(--ink-soft)]">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
      </table>
    </div>
  );
}
