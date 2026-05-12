"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { DataSourceConfig } from "@/components/data-source-config/DataSourceConfig";
import {
  Settings,
  Database,
  Users,
} from "lucide-react";

type KOLConfig = {
  id: string;
  name: string;
  platform: string;
  platformId: string;
  enabled: boolean;
};

const mockKOLConfigs: KOLConfig[] = [
  { id: "kol-1", name: "投研老王", platform: "wechat", platformId: "xxx123", enabled: true },
  { id: "kol-2", name: "价值投资张", platform: "bilibili", platformId: "bili456", enabled: true },
  { id: "kol-3", name: "量化小李", platform: "feishu", platformId: "feishu789", enabled: true },
];

function getTypeLabel(type: string) {
  const labels: Record<string, string> = {
    feishu: "飞书",
    wechat: "微信公众号",
    bilibili: "B站",
  };
  return labels[type] ?? type;
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"datasources" | "kols" | "system">(
    "datasources"
  );
  const [kolConfigs, setKOLConfigs] = useState(mockKOLConfigs);

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">系统设置</h1>
        <p className="text-sm text-foreground/60 mt-1">
          配置数据源、管理 KOL 和系统参数
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-stone-200 mb-6">
        {[
          { key: "datasources", label: "数据源配置", icon: Database },
          { key: "kols", label: "KOL 管理", icon: Users },
          { key: "system", label: "系统设置", icon: Settings },
        ].map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as typeof activeTab)}
              className={cn(
                "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors",
                activeTab === tab.key
                  ? "border-morningstar-red text-foreground"
                  : "border-transparent text-foreground/60 hover:text-foreground"
              )}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === "datasources" && <DataSourceConfig />}

      {activeTab === "kols" && (
        <div>
          <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-stone-50 border-b border-stone-200">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-foreground/60">
                    KOL
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-foreground/60">
                    平台
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-foreground/60">
                    平台 ID
                  </th>
                  <th className="px-4 py-3 text-center font-medium text-foreground/60">
                    启用
                  </th>
                  <th className="px-4 py-3 text-right font-medium text-foreground/60">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {kolConfigs.map((kol) => (
                  <tr key={kol.id} className="border-b border-stone-100 last:border-0">
                    <td className="px-4 py-3 font-medium">{kol.name}</td>
                    <td className="px-4 py-3 text-foreground/60">
                      {getTypeLabel(kol.platform)}
                    </td>
                    <td className="px-4 py-3 text-foreground/60 font-mono text-xs">
                      {kol.platformId}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() =>
                          setKOLConfigs(
                            kolConfigs.map((k) =>
                              k.id === kol.id ? { ...k, enabled: !k.enabled } : k
                            )
                          )
                        }
                        className={cn(
                          "w-10 h-5 rounded-full transition-colors relative",
                          kol.enabled ? "bg-green-500" : "bg-stone-300"
                        )}
                      >
                        <span
                          className={cn(
                            "absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform shadow",
                            kol.enabled ? "translate-x-5" : "translate-x-0.5"
                          )}
                        />
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button className="px-2 py-1 text-xs text-foreground/60 hover:text-foreground transition-colors">
                        编辑
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "system" && (
        <div className="bg-white border border-stone-200 rounded-lg p-6">
          <h3 className="font-bold mb-4">系统配置</h3>
          <div className="h-48 flex items-center justify-center text-foreground/40 border border-dashed border-stone-300 rounded">
            <div className="text-center">
              <Settings className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">系统配置表单（待实现）</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
