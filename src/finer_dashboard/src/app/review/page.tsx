"use client";

/**
 * /review — F6 人工复核入口（RLHF 偏好对采集）。
 *
 * 为什么需要这个路由：`RLHFReviewPanel`（1,743 行、9 个组件）自 2026-06-11
 * 建成后**从未被任何页面挂载**，而 `docs/specs/2026-07-13-next-optimization-
 * directions.md` 的 P2#8 把「用该面板对已结算 action 做人工审核积累偏好对」
 * 列为 DPO 实训的前置条件——环 B 反馈飞轮 100% 卡在 `data/rlhf/feedbacks/`
 * 为空。面板是抽屉形态（fixed inset-0），所以这里做成落地页 + 打开抽屉，
 * 而不是把抽屉硬塞进页面壳。
 */

import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, Play } from "lucide-react";
import { RLHFReviewPanel } from "@/components/rlhf-review-panel";
import { Masthead, MetricTile, SectionHeader, Disclosure, NoteList } from "@/components/crd/primitives";

type RLHFStats = {
  total_feedbacks: number;
  average_rating: number;
  pending_reviews: number;
  dpo_ready_count: number;
};

type PendingResponse = { total: number };

export default function ReviewPage() {
  const [open, setOpen] = useState(false);
  const [stats, setStats] = useState<RLHFStats | null>(null);
  const [pendingTotal, setPendingTotal] = useState<number | null>(null);

  const refresh = useCallback(() => {
    fetch("/api/rlhf/stats")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setStats(d))
      .catch(() => setStats(null));
    fetch("/api/rlhf/pending?limit=1")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: PendingResponse | null) => setPendingTotal(d?.total ?? null))
      .catch(() => setPendingTotal(null));
  }, []);

  useEffect(refresh, [refresh]);

  const reviewed = stats?.total_feedbacks ?? 0;
  // DPO 实训的经验门槛：路线图写「上百条前不启动实训」。
  const DPO_THRESHOLD = 100;

  return (
    <div className="finer-scrollbar h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-9">
        <Masthead
          eyebrow="FINER OS · 人工复核"
          title="复核台"
          suffix="F6 · RLHF 偏好对采集"
          meta={[
            pendingTotal != null ? `${pendingTotal.toLocaleString()} 条待复核` : "待复核 —",
            `${reviewed} 条已复核`,
            `DPO 就绪 ${stats?.dpo_ready_count ?? 0}`,
          ]}
          lede="对已结算的 TradeAction 逐条判断抽取质量。每条复核产生一个偏好对，累积到上百条后才启动 DPO 实训——这是反馈飞轮的入口，不是评分页面。"
        />

        <div className="mt-4">
          <Disclosure title="口径说明">
            {"待复核队列 = 已结算的 canonical F5 action（有回测结果才谈得上判断对错）。复核的是「我们把这条抽取得对不对」，不是「信源说得准不准」——前者是管道质量，后者是信源记录，两者不可混为一谈。"}
          </Disclosure>
        </div>

        <section className="mt-7">
          <SectionHeader
            index="01"
            title="飞轮状态"
            en="FEEDBACK LOOP"
            note={<>DPO 实训门槛 {DPO_THRESHOLD} 条</>}
          />
          <div className="mt-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
            <MetricTile
              value={pendingTotal != null ? pendingTotal.toLocaleString() : "—"}
              label="待复核"
              sub="已结算 F5 action"
            />
            <MetricTile value={reviewed} label="已复核" sub="累计偏好对" />
            <MetricTile
              value={stats?.dpo_ready_count ?? 0}
              label="DPO 就绪"
              sub="可导出为训练对"
            />
            <MetricTile
              value={`${reviewed} / ${DPO_THRESHOLD}`}
              label="距实训门槛"
              sub={
                reviewed >= DPO_THRESHOLD ? "已达门槛" : `还差 ${DPO_THRESHOLD - reviewed} 条`
              }
            />
          </div>
        </section>

        <section className="mt-8 pb-12">
          <SectionHeader index="02" title="开始复核" en="START REVIEW" />
          <div className="editorial-panel mt-3 rounded-sm px-5 py-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <ClipboardCheck
                  className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent-gold)]"
                  strokeWidth={1.6}
                />
                <div className="text-[13px] leading-relaxed text-[var(--ink-soft)]">
                  逐条查看原文、抽取结果与操作链，可就地纠正标的/方向/操作链，
                  给 1–5 分并打标签。
                  <br />
                  快捷键：<span className="font-mono">1–5</span> 评分 ·
                  <span className="font-mono"> S</span> 跳过 ·
                  <span className="font-mono"> F</span> 标记错误 ·
                  <span className="font-mono"> Enter</span> 提交
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(true)}
                disabled={pendingTotal === 0}
                className="inline-flex shrink-0 items-center gap-2 rounded-sm bg-[var(--foreground)] px-5 py-2.5 text-[13px] text-[var(--surface-strong)] transition-colors hover:bg-[var(--morningstar-red)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Play className="h-4 w-4" strokeWidth={2} />
                打开复核面板
              </button>
            </div>
          </div>

          <div className="mt-3">
            <NoteList
              notes={[
                "复核结果写入 data/rlhf/feedbacks/，经 GET /api/rlhf/export 导出为 DPO 训练数据。",
                "F5 只记录整条抽取的 confidence，没有分字段置信度——标的/方向两处显示的是同一个整体把握值，不是各自的准确度。",
                "跳过不产生偏好对；标记为错误的条目会进入负样本。",
              ]}
            />
          </div>
        </section>
      </div>

      <RLHFReviewPanel
        isOpen={open}
        onClose={() => {
          setOpen(false);
          refresh();
        }}
        onComplete={() => refresh()}
      />
    </div>
  );
}
