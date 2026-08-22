"use client";

/**
 * /timeline — 观点时间线（F7 消费面）。
 *
 * `components/opinion-timeline/`（1,818 行、6 个文件）自建成起从未被任何
 * 页面挂载——它的 `index.ts` 里那段「使用示例」写的正是这个页面，两个月
 * 无人建。2026-07-02 还专门为它做过一次前后端契约同步
 * （`OpinionDirection` 3→5、补 market/traceStatus，见
 * docs/specs/2026-07-02-opinions-5way-live-adapter.md），说明它不是弃码，
 * 是「已建好没接上」。
 *
 * 与 `/discover` 的分工：/discover 按**信源**聚合（谁的记录如何），
 * 本页按**时间**平铺（这段时间里发生了什么），可按标的/方向/信源筛选并
 * 下钻单条证据。两者共用同一批 F5 action，不是同一个视角。
 */

import { useState } from "react";
import type { TimelineOpinion } from "@/components/opinion-timeline";
import { OpinionTimeline, OpinionDetailModal } from "@/components/opinion-timeline";
import { Disclosure, Masthead } from "@/components/crd/primitives";

export default function TimelinePage() {
  const [selected, setSelected] = useState<TimelineOpinion | null>(null);

  return (
    <div className="finer-scrollbar h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-6 py-9">
        <Masthead
          eyebrow="FINER OS · 观点时间线"
          title="观点时间线"
          suffix="按时间平铺 · 可筛选下钻"
          lede="这段时间里谁说过什么，按发布时间横向铺开。点开任意一条可查看原文、操作链与回测结果。按信源聚合的视图在「信源记录」。"
        />

        <div className="mt-4">
          <Disclosure title="口径说明">
            {"每条都标注了口径：券商研报（个股评级 / 板块观点）与 KOL 自述的基准率不同，不可放在一起比较。时间轴用的是 canonical 执行时钟（真实信号时间），不是抽取时刻——后者会把整批导入压在同一瞬间。"}
          </Disclosure>
        </div>

        <div className="mt-6">
          <OpinionTimeline
            initialFilters={{ timeRange: "1M" }}
            onOpinionClick={setSelected}
          />
        </div>
      </div>

      {/* Modal 的 opinion prop 是必填的，用条件渲染而不是传 null */}
      {selected !== null && (
        <OpinionDetailModal
          opinion={selected}
          open
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
