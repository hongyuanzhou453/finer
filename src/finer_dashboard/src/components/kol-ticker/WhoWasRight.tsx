/**
 * L3 签名榜 — 谁对了。Cross-KOL scoreboard on ONE ticker, ranked by each KOL's
 * realized follow-P&L on that name. Rows arrive pre-sorted (returnPct desc, 未结算 last).
 * Compact institutional table: fixed colgroup widths, all names/tags `whitespace-nowrap`,
 * red = 兑现/看多, green = 落空/看空 (China convention via DirectionTag/ReturnChip).
 */
import React from "react";
import Link from "next/link";
import type { WhoWasRightRow } from "@/lib/fixtures/kol-ticker";
import {
  DirectionTag,
  ReturnChip,
  fmtConfidence,
} from "@/components/kol-snapshot/primitives";

function ResultCell({ correct }: { correct: boolean | null }) {
  if (correct === true) {
    return (
      <span className="whitespace-nowrap font-medium" style={{ color: "var(--chart-up)" }}>
        ✓ 兑现
      </span>
    );
  }
  if (correct === false) {
    return (
      <span className="whitespace-nowrap font-medium" style={{ color: "var(--chart-down)" }}>
        ✗ 落空
      </span>
    );
  }
  return (
    <span className="whitespace-nowrap text-[var(--ink-soft)]">待结算</span>
  );
}

export function WhoWasRight({ rows }: { rows: WhoWasRightRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="px-3 py-4 text-[13px] text-[var(--ink-soft)]">
        该标的暂无 KOL 表态记录。
      </div>
    );
  }

  return (
    <div className="finer-scrollbar -mx-1 overflow-x-auto px-1">
      <table className="top-rule-table min-w-[560px]">
        <colgroup>
          <col style={{ width: "34px" }} />
          <col />
          <col style={{ width: "84px" }} />
          <col style={{ width: "74px" }} />
          <col style={{ width: "78px" }} />
          <col style={{ width: "76px" }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">KOL</th>
            <th scope="col">立场</th>
            <th scope="col" className="text-right">置信度</th>
            <th scope="col" className="text-right">兑现</th>
            <th scope="col">结果</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.kolId}>
              <td className="align-top">
                <span className="tabular-nums text-[var(--ink-soft)]">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </td>

              <td className="align-top">
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <Link
                    href={`/demo/kol/${r.kolId}`}
                    className="font-semibold text-[var(--foreground)] hover:text-[var(--morningstar-red)] hover:underline"
                  >
                    {r.kolName}
                  </Link>
                  <span
                    className="rounded-sm px-1.5 py-0.5 text-[10px] font-medium leading-none"
                    style={{
                      color: "var(--accent-gold)",
                      backgroundColor:
                        "color-mix(in srgb, var(--accent-gold) 10%, transparent)",
                      border:
                        "1px solid color-mix(in srgb, var(--accent-gold) 32%, transparent)",
                    }}
                  >
                    信誉 {r.credibility}
                  </span>
                  {r.callCount > 1 ? (
                    <span className="text-[10px] leading-none text-[var(--ink-soft)]">
                      ·此票 {r.callCount} 次
                    </span>
                  ) : null}
                </div>
                {/* 该不该信下一次：KOL 整体战绩，区分一贯准 vs 此票蒙对一次 */}
                <div className="tabular-nums mt-1 flex items-center gap-2 whitespace-nowrap text-[10px] text-[var(--ink-soft)]">
                  <span>
                    总命中{" "}
                    {r.overallHitRate === null ? "—" : fmtConfidence(r.overallHitRate)} ·{" "}
                    {r.overallSettled} 笔
                  </span>
                  {r.lowSample ? (
                    <span style={{ color: "var(--accent-gold)" }}>样本少</span>
                  ) : null}
                </div>
              </td>

              <td className="whitespace-nowrap align-top">
                <DirectionTag direction={r.direction} size="xs" />
              </td>

              <td className="align-top text-right">
                <span className="tabular-nums text-xs text-[var(--foreground)]">
                  {fmtConfidence(r.confidence)}
                </span>
              </td>

              <td className="align-top text-right">
                <ReturnChip value={r.returnPct} muted="待结算" />
              </td>

              <td className="align-top">
                <ResultCell correct={r.correct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
