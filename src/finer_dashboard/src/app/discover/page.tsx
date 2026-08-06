"use client";

/**
 * /discover — 信源历史记录卡片墙（UI-1，CRD-1 的消费面）。
 *
 * 口径纪律（2026-08-03 UI-1 拍板）：
 * - 默认序 = 已结算样本量降序。这是稳定输出序，**不是排名**——跨期持续性
 *   检验未获支持，任何按超额的默认排序都是在宣称一件数据不支持的事。
 * - display_policy 强制消费：count_only 的卡不渲染任何比率。
 * - 胜率必须与 95% 区间并排；预测性声明置顶展示。
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CreatorRecordCard } from "@/lib/contracts";
import { apiFetch } from "@/lib/api-client";

function pct(v?: number | null, digits = 1): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

function CardBody({ card }: { card: CreatorRecordCard }) {
  const s = card.sufficiency;

  if (s.display_policy === "count_only") {
    return (
      <div className="mt-3 text-sm text-zinc-500">
        已结算 {card.n_settled} / 共 {card.n_total} 条
        <div className="mt-1 text-xs text-zinc-400">样本不足，仅显示计数</div>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-2xl">{pct(s.point_estimate)}</span>
        <span className="text-xs text-zinc-500">
          命中率 · 95% 区间 {pct(s.wilson_low, 0)}–{pct(s.wilson_high, 0)}
        </span>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-x-4 text-xs text-zinc-500">
        <span>已结算 {card.n_settled} / {card.n_total}</span>
        <span>均值收益 {pct(card.mean_return, 2)}</span>
        <span>市场预期 {pct(card.expected_win_rate)}</span>
        <span>
          主要市场{" "}
          {Object.entries(card.market_mix)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([m, n]) => `${m}:${n}`)
            .join(" ")}
        </span>
      </div>
      {s.display_policy === "show_with_warning" && (
        <div className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
          样本偏少，数字仅供参考，请结合区间宽度阅读
        </div>
      )}
    </div>
  );
}

/** 口径切换：券商对个股的评级与对板块的看法基准率不同，不得混算（R6）。 */
const SCOPES = [
  { key: "broker_recommendation", label: "个股评级" },
  { key: "broker_sector_view", label: "板块观点" },
] as const;

export default function DiscoverPage() {
  const [cards, setCards] = useState<CreatorRecordCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<string>(SCOPES[0].key);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<{ cards: CreatorRecordCard[] }>(
      `/api/creator/records?signal_class=${encodeURIComponent(scope)}`,
    )
      .then((data) => {
        if (alive) setCards(data.cards);
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
  }, [scope]);

  const claim = cards[0]?.sufficiency.predictive_claim;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">信源记录</h1>
      <p className="mt-2 text-sm text-zinc-500">
        每张卡是一份历史记录，不是推荐。默认按已结算样本量排列——不是排名。
      </p>

      <div className="mt-4 flex gap-2">
        {SCOPES.map((s) => (
          <button
            key={s.key}
            onClick={() => setScope(s.key)}
            className={cn(
              "rounded border px-3 py-1 text-sm",
              scope === s.key
                ? "border-zinc-800 bg-zinc-900 text-white"
                : "border-zinc-300 text-zinc-600 hover:bg-zinc-50",
            )}
          >
            {s.label}
          </button>
        ))}
        <span className="self-center text-xs text-zinc-400">
          两种口径基准率不同，不可跨口径比较
        </span>
      </div>

      {claim && !claim.permitted && (
        <div className="mt-4 rounded border border-zinc-200 bg-zinc-50 p-3 text-xs leading-5 text-zinc-600">
          🚫 本页数字描述已发生的事实，不构成对未来的预测。
          {claim.summary && <> 跨期持续性检验：{claim.summary}</>}
          {claim.evidence && (
            <span className="ml-1 font-mono text-zinc-400">{claim.evidence}</span>
          )}
        </div>
      )}

      {loading && (
        <div className="mt-12 flex items-center gap-2 text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…（首次扫描全量
          action，约数秒）
        </div>
      )}
      {error && !loading && (
        <div className="mt-8 rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          加载失败：{error}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <div
            key={card.creator_id}
            className={cn(
              "rounded-lg border border-zinc-200 p-4",
              card.sufficiency.display_policy === "count_only" && "opacity-70",
            )}
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">{card.creator_id}</span>
              <Link
                href={`/audit?kol=${encodeURIComponent(card.creator_id)}`}
                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
              >
                <ScrollText className="h-3 w-3" /> 审计
              </Link>
            </div>
            <CardBody card={card} />
            {(card.first_action_at || card.last_action_at) && (
              <div className="mt-2 text-[11px] text-zinc-400">
                记录窗口 {card.first_action_at?.slice(0, 10)} —{" "}
                {card.last_action_at?.slice(0, 10)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
