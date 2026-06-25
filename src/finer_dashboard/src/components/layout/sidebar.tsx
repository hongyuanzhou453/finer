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
  Network,
  Radar,
  Settings,
  Database,
  ShieldCheck,
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
            <span className="rounded-full bg-[rgba(159,29,34,0.08)] px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-morningstar-red">
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
                      ? "border-[rgba(159,29,34,0.2)] bg-[rgba(159,29,34,0.06)] shadow-sm"
                      : "border-transparent bg-transparent hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "mt-0.5 rounded-sm border p-2",
                        isActive
                          ? "border-[rgba(159,29,34,0.16)] bg-white text-morningstar-red"
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
                      ? "border-[rgba(159,29,34,0.2)] bg-[rgba(159,29,34,0.06)] shadow-sm"
                      : "border-transparent bg-transparent hover:border-[rgba(95,67,40,0.1)] hover:bg-[rgba(255,252,247,0.62)]"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "mt-0.5 rounded-sm border p-2",
                        isActive
                          ? "border-[rgba(159,29,34,0.16)] bg-white text-morningstar-red"
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
