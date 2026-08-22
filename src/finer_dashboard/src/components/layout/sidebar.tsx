"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRightLeft,
  Binary,
  BookMarked,
  Bot,
  CheckCircle2,
  Gauge,
  LineChart,
  Network,
  Radar,
  Settings,
  Database,
  ShieldCheck,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

type WorkflowItem = {
  tier: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  badge: string;
};

const workflowItems: WorkflowItem[] = [
  {
    tier: "F0",
    label: "Intake",
    description: "多源内容接入与原始归档",
    icon: ArrowRightLeft,
    badge: "F0",
  },
  {
    tier: "F1",
    label: "Standardize",
    description: "内容标准化与 Block 拆分",
    icon: BookMarked,
    badge: "F1",
  },
  {
    tier: "F2",
    label: "Anchor",
    description: "质量评估与实体/时间锚定",
    icon: Network,
    badge: "F2",
  },
  {
    tier: "F5",
    label: "Execute",
    description: "投资意图提取与交易执行",
    icon: Bot,
    badge: "F5",
  },
  {
    tier: "F6",
    label: "Review",
    description: "人工复核与歧义裁决",
    icon: CheckCircle2,
    badge: "F6",
  },
  {
    tier: "F8",
    label: "Backtest",
    description: "策略回测与 KOL 评估",
    icon: Gauge,
    badge: "F8",
  },
];

const integrationItems = [
  {
    tier: "Integrations",
    label: "Sync Hub",
    description: "飞书与 NotebookLM 外部源",
    icon: Activity,
    badge: "EXT",
  },
  {
    tier: "DataSource",
    label: "Data Sources",
    description: "微信公众号与 B站数据源",
    icon: Database,
    badge: "SRC",
  }
];

export function Sidebar({
  activeTier,
  onTierChange,
}: {
  activeTier: string;
  onTierChange: (tier: string) => void;
}) {
  const [stats, setStats] = useState({ intake: 0, library: 0, review: 0 });

  useEffect(() => {
    fetch('/api/stats')
      .then(res => res.json())
      .then(data => {
        if (data?.pulse) {
          setStats(data.pulse);
        }
      })
      .catch(console.error);
  }, [activeTier]);

  const activeItem =
    workflowItems.find((item) => item.tier === activeTier) ?? workflowItems[1];

  const pulseItems = [
    { label: "F0 Intake", value: stats.intake.toString(), tone: "text-[var(--accent-teal)]" },
    { label: "F1 Std", value: stats.library.toString(), tone: "text-[var(--accent-gold)]" },
    { label: "F6 Review", value: stats.review.toString(), tone: "text-morningstar-red" },
  ];

  return (
    <aside className="w-72 editorial-panel h-full flex flex-col z-20 transition-all duration-300">
      <div className="px-6 pt-6 pb-5 border-b border-[rgba(95,67,40,0.12)]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-sm bg-morningstar-red flex items-center justify-center shadow-md">
            <Activity className="text-white w-5 h-5" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              Finer OS
            </h1>
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-soft)] mt-1">
              Evidence-first research ops
            </p>
          </div>
        </div>
      </div>

      <div className="px-6 pt-6">
        <div className="rounded-sm border border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.74)] px-4 py-3 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-bold text-[var(--ink-soft)] uppercase tracking-[0.18em]">
              Current workflow
            </div>
            <span className="rounded-full bg-[color-mix(in_srgb,var(--morningstar-red)_8%,transparent)] px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-morningstar-red">
              {activeItem.badge}
            </span>
          </div>
          <div className="mt-4">
            <div className="text-lg font-bold text-foreground">{activeItem.label}</div>
            <p className="mt-1 text-[12px] leading-relaxed text-[var(--ink-soft)]">
              {activeItem.description}
            </p>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto finer-scrollbar px-4 py-5 space-y-6">
        <div className="space-y-2">
          <div className="px-3 text-[10px] font-bold text-[var(--ink-soft)] uppercase tracking-[0.16em]">
            Workflow
          </div>

          <div className="space-y-1.5">
            {workflowItems.map((item) => {
              const isActive = item.tier === activeTier;

              return (
                <button
                  key={item.tier}
                  onClick={() => onTierChange(item.tier)}
                  className={cn(
                    "w-full rounded-sm border px-3 py-2.5 text-left transition-all duration-150",
                    isActive
                      ? "border-[color-mix(in_srgb,var(--morningstar-red)_20%,transparent)] bg-[color-mix(in_srgb,var(--morningstar-red)_6%,transparent)] shadow-sm"
                      : "border-transparent bg-transparent hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "mt-0.5 rounded-sm border p-2",
                        isActive
                          ? "border-[color-mix(in_srgb,var(--morningstar-red)_16%,transparent)] bg-white text-morningstar-red"
                          : "border-[rgba(95,67,40,0.1)] bg-[rgba(99,76,55,0.04)] text-[var(--ink-soft)]"
                      )}
                    >
                      <item.icon className="w-4 h-4" strokeWidth={1.6} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <span
                          className={cn(
                            "text-[13px] font-bold",
                            isActive ? "text-morningstar-red" : "text-foreground"
                          )}
                        >
                          {item.label}
                        </span>
                        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                          {item.badge}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                        {item.description}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <div className="px-3 text-[10px] font-bold text-[var(--ink-soft)] uppercase tracking-[0.16em]">
            Integrations
          </div>

          <div className="space-y-1.5">
            {integrationItems.map((item) => {
              const isActive = item.tier === activeTier;

              return (
                <button
                  key={item.tier}
                  onClick={() => onTierChange(item.tier)}
                  className={cn(
                    "w-full rounded-sm border px-3 py-2.5 text-left transition-all duration-150",
                    isActive
                      ? "border-[color-mix(in_srgb,var(--morningstar-red)_20%,transparent)] bg-[color-mix(in_srgb,var(--morningstar-red)_6%,transparent)] shadow-sm"
                      : "border-transparent bg-transparent hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "mt-0.5 rounded-sm border p-2",
                        isActive
                          ? "border-[color-mix(in_srgb,var(--morningstar-red)_16%,transparent)] bg-white text-morningstar-red"
                          : "border-[rgba(95,67,40,0.1)] bg-[rgba(99,76,55,0.04)] text-[var(--ink-soft)]"
                      )}
                    >
                      <item.icon className="w-4 h-4" strokeWidth={1.6} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <span
                          className={cn(
                            "text-[13px] font-bold",
                            isActive ? "text-morningstar-red" : "text-foreground"
                          )}
                        >
                          {item.label}
                        </span>
                        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                          {item.badge}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                        {item.description}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <div className="px-3 text-[10px] font-bold text-[var(--ink-soft)] uppercase tracking-[0.16em]">
            Analysis
          </div>
          <div className="space-y-1.5">
            {/* 新定位（「不告诉你谁更准，让你查得清谁说过什么」）的两个主入口。
                此前 /discover 与 /ticker 在全仓**零入站链接**——为新定位建的页面
                没有任何路径能走到，而宣传站落地页却拿 /discover 的截图当主推图。 */}
            <Link
              href="/discover"
              className="block w-full rounded-sm border border-transparent px-3 py-2.5 text-left transition-all duration-150 hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-sm border border-[rgba(95,67,40,0.1)] bg-[rgba(99,76,55,0.04)] p-2 text-[var(--ink-soft)]">
                  <Users className="w-4 h-4" strokeWidth={1.6} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[13px] font-bold text-foreground">信源记录 Discover</span>
                    <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--accent-teal)]">
                      LIVE
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                    谁说过什么 · 按已结算样本量排列，不是排名
                  </div>
                </div>
              </div>
            </Link>
            <Link
              href="/ticker"
              className="block w-full rounded-sm border border-transparent px-3 py-2.5 text-left transition-all duration-150 hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-sm border border-[rgba(95,67,40,0.1)] bg-[rgba(99,76,55,0.04)] p-2 text-[var(--ink-soft)]">
                  <LineChart className="w-4 h-4" strokeWidth={1.6} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[13px] font-bold text-foreground">个股共识 Ticker</span>
                    <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--accent-teal)]">
                      LIVE
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                    这只票谁说过什么 · 含陈旧度标注
                  </div>
                </div>
              </div>
            </Link>
            <Link
              href="/audit"
              className="block w-full rounded-sm border border-transparent px-3 py-2.5 text-left transition-all duration-150 hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-sm border border-[rgba(95,67,40,0.1)] bg-[rgba(99,76,55,0.04)] p-2 text-[var(--ink-soft)]">
                  <ShieldCheck className="w-4 h-4" strokeWidth={1.6} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[13px] font-bold text-foreground">审计台 Audit</span>
                    <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                      TRACE
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                    证据链与 F3→F4→F5 溯源
                  </div>
                </div>
              </div>
            </Link>
            {/* /radar 按「信誉分」降序排名、无 sufficiency、无 95% 区间、无
                「不构成对未来的预测」声明——正是 2026-08-02 定位转向拍板要禁的形态
                （UI-1：默认序 = 已结算样本量；禁止「Top 券商/最佳信源」式呈现）。
                它吃的是真实数据，所以曾挂 LIVE 徽标，位置还在两个合规页之上。
                这里先降级：移到末位、去掉 LIVE、文案如实说明它不合口径。
                **页面本身尚未按 UI-1 改造**——改造还是删除是产品决策，未定。 */}
            <Link
              href="/radar"
              className="block w-full rounded-sm border border-transparent px-3 py-2.5 text-left opacity-70 transition-all duration-150 hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)] hover:opacity-100"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-sm border border-[rgba(95,67,40,0.1)] bg-[rgba(99,76,55,0.04)] p-2 text-[var(--ink-soft)]">
                  <Radar className="w-4 h-4" strokeWidth={1.6} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[13px] font-bold text-foreground/70">观点雷达 Radar</span>
                    <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                      旧口径
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed text-[var(--ink-soft)]">
                    按信誉分排名，不带样本量门与区间——待按新口径改造
                  </div>
                </div>
              </div>
            </Link>
          </div>
        </div>

        <div className="space-y-2">
          <div className="px-3 text-[10px] font-bold text-[var(--ink-soft)] uppercase tracking-[0.16em]">
            Pipeline Pulse
          </div>

          <div className="rounded-sm border border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.6)] p-4">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/70">
              <Radar className="w-4 h-4 text-morningstar-red" strokeWidth={1.6} />
              Active Asset Surface
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2">
              {pulseItems.map((item) => (
                <div
                  key={item.label}
                  className="rounded-sm border border-[rgba(95,67,40,0.1)] bg-white/80 px-2.5 py-2"
                >
                  <div className={cn("text-lg font-bold tabular-nums", item.tone)}>
                    {item.value}
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    {item.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="px-3 text-[10px] font-bold text-[var(--ink-soft)] uppercase tracking-[0.16em]">
            Provenance
          </div>
          <div className="rounded-sm border border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.6)] p-4">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/70">
              <Binary className="w-4 h-4 text-[var(--accent-gold)]" strokeWidth={1.6} />
              Pipeline badges remain visible
            </div>
            <p className="mt-3 text-[12px] leading-relaxed text-[var(--ink-soft)]">
              F0-F8 作为证据链和运行状态的标识，对应 canonical pipeline 各阶段。
            </p>
          </div>
        </div>
      </nav>

      <div className="p-6 mt-auto border-t border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.5)]">
        <a href="/settings" className="w-full flex items-center gap-3 px-3 py-2 text-foreground/60 hover:text-morningstar-red transition-colors text-xs font-bold">
          <Settings className="w-4 h-4" strokeWidth={1.5} />
          <span>系统设置 / SYSTEM</span>
        </a>
      </div>
    </aside>
  );
}
