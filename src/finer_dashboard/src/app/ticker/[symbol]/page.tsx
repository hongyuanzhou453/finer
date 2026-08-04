"use client";

/**
 * /ticker/[symbol] — 个股共识记录（UI-3，CRD-3 的消费面）。
 *
 * 定位纪律（2026-08-02 转向）：本页描述「谁说过什么」，不判断「谁说得对」。
 * notes 里的口径声明必须逐条展示，不得折叠——这是 CRD-2 的前端义务。
 */

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConsensusDirection, TickerConsensusView } from "@/lib/contracts";
import { apiFetch } from "@/lib/api-client";

const DIRECTION_LABEL: Record<ConsensusDirection, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
  mixed: "混合",
};

const DIRECTION_STYLE: Record<ConsensusDirection, string> = {
  bullish: "bg-red-50 text-red-700 border-red-200",
  bearish: "bg-green-50 text-green-700 border-green-200",
  neutral: "bg-zinc-100 text-zinc-600 border-zinc-200",
  mixed: "bg-amber-50 text-amber-700 border-amber-200",
};

function fmtPrice(v?: number | null, cur?: string | null): string {
  if (v == null) return "—";
  return `${v.toLocaleString()} ${cur ?? ""}`.trim();
}

export default function TickerConsensusPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const [view, setView] = useState<TickerConsensusView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<TickerConsensusView>(
      `/api/ticker/${encodeURIComponent(symbol)}/consensus`,
    )
      .then((data) => {
        if (alive) setView(data);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-800"
      >
        <ArrowLeft className="h-4 w-4" /> 返回
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">
        {decodeURIComponent(symbol)}
        <span className="ml-3 text-base font-normal text-zinc-500">
          共识记录 · 谁说过什么
        </span>
      </h1>

      {loading && (
        <div className="mt-12 flex items-center gap-2 text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </div>
      )}

      {error && !loading && (
        <div className="mt-8 rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          未找到该标的的立场记录：{error}
          <div className="mt-1 text-xs text-amber-700">
            确认代码写法（如 0700.HK / NVDA / AZN.L），或该标的未被已接入信源覆盖。
          </div>
        </div>
      )}

      {view && !loading && (
        <>
          {/* 口径声明 —— CRD-2 纪律：逐条展示，不折叠 */}
          <div className="mt-4 space-y-1">
            {view.notes.map((note) => (
              <p key={note} className="text-xs leading-5 text-zinc-500">
                · {note}
              </p>
            ))}
          </div>

          {/* 方向分布 */}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            {Object.entries(view.direction_counts).map(([dir, count]) => (
              <span
                key={dir}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm",
                  DIRECTION_STYLE[dir as ConsensusDirection] ??
                    DIRECTION_STYLE.mixed,
                )}
              >
                {DIRECTION_LABEL[dir as ConsensusDirection] ?? dir} {count}
              </span>
            ))}
            <span className="text-sm text-zinc-500">
              共 {view.n_sources} 家信源（每源只计最新一篇）
              {view.directional_agreement != null &&
                ` · 方向一致度 ${(view.directional_agreement * 100).toFixed(0)}%`}
            </span>
          </div>

          {/* 目标价分布 —— 排除计数必须可见 */}
          {view.target_prices ? (
            <div className="mt-4 rounded border border-zinc-200 p-4">
              <div className="text-sm text-zinc-500">
                目标价分布（{view.target_prices.currency}，n=
                {view.target_prices.n}）
              </div>
              <div className="mt-1 font-mono text-lg">
                {view.target_prices.min_value.toLocaleString()} /{" "}
                {view.target_prices.median_value.toLocaleString()} /{" "}
                {view.target_prices.max_value.toLocaleString()}
                <span className="ml-2 text-xs text-zinc-400">
                  最低 / 中位 / 最高
                </span>
              </div>
              {(view.target_prices.excluded_unit_ambiguous > 0 ||
                view.target_prices.excluded_currency_mismatch > 0) && (
                <div className="mt-1 text-xs text-amber-700">
                  已排除：单位可疑 {view.target_prices.excluded_unit_ambiguous}{" "}
                  条 · 币种不一 {view.target_prices.excluded_currency_mismatch} 条
                </div>
              )}
            </div>
          ) : (
            <div className="mt-4 rounded border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500">
              目标价未聚合（无数据或单位可疑——排除比错误的中位数诚实）。
            </div>
          )}

          {/* 各信源最新立场 */}
          <div className="mt-8 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-xs text-zinc-500">
                  <th className="py-2 pr-4">信源</th>
                  <th className="py-2 pr-4">方向</th>
                  <th className="py-2 pr-4">评级</th>
                  <th className="py-2 pr-4">目标价</th>
                  <th className="py-2 pr-4">报告日</th>
                  <th className="py-2 pr-4">篇数</th>
                  <th className="py-2">下钻</th>
                </tr>
              </thead>
              <tbody>
                {view.latest_by_source.map((row) => (
                  <tr
                    key={row.intent_id || row.creator_id}
                    className="border-b border-zinc-100"
                  >
                    <td className="py-2 pr-4 font-medium">{row.creator_id}</td>
                    <td className="py-2 pr-4">
                      <span
                        className={cn(
                          "rounded border px-2 py-0.5 text-xs",
                          DIRECTION_STYLE[row.direction],
                        )}
                      >
                        {DIRECTION_LABEL[row.direction]}
                      </span>
                    </td>
                    <td className="py-2 pr-4">{row.rating ?? "—"}</td>
                    <td className="py-2 pr-4 font-mono">
                      {fmtPrice(row.target_price_value, row.target_price_currency)}
                    </td>
                    <td className="py-2 pr-4 text-zinc-500">
                      {row.report_date ?? "—"}
                    </td>
                    <td className="py-2 pr-4 text-zinc-500">{row.n_reports}</td>
                    <td className="py-2">
                      <Link
                        href={`/audit?ticker=${encodeURIComponent(view.ticker)}`}
                        className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
                        title={row.intent_id}
                      >
                        <ScrollText className="h-3 w-3" />
                        {row.intent_id.slice(0, 14)}…
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
