"use client";

import React, { useState } from "react";
import { WeChatConfig } from "./WeChatConfig";
import { BilibiliConfig } from "./BilibiliConfig";
import { ImportConsole } from "@/components/import-console";
import { Monitor, MessageCircle, PlayCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type DataSourceTab = "console" | "wechat" | "bilibili";

export function DataSourceConfig() {
  const [activeTab, setActiveTab] = useState<DataSourceTab>("console");

  return (
    <div className="h-full flex flex-col bg-stone-50/50">
      {/* Header */}
      <div className="p-8 border-b bg-white">
        <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-3">
          数据源配置
        </h1>
        <p className="mt-2 text-sm text-[var(--ink-soft)]">
          配置并管理微信公众号和B站等外部数据源，同步内容到系统。
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="px-8 pt-6 bg-white border-b">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab("console")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-bold uppercase tracking-widest border-b-2 transition-colors",
              activeTab === "console"
                ? "border-morningstar-red text-morningstar-red"
                : "border-transparent text-foreground/50 hover:text-foreground/80"
            )}
          >
            <Monitor className="w-4 h-4" />
            导入控制台
          </button>
          <button
            onClick={() => setActiveTab("wechat")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-bold uppercase tracking-widest border-b-2 transition-colors",
              activeTab === "wechat"
                ? "border-morningstar-red text-morningstar-red"
                : "border-transparent text-foreground/50 hover:text-foreground/80"
            )}
          >
            <MessageCircle className="w-4 h-4" />
            微信公众号
          </button>
          <button
            onClick={() => setActiveTab("bilibili")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-bold uppercase tracking-widest border-b-2 transition-colors",
              activeTab === "bilibili"
                ? "border-morningstar-red text-morningstar-red"
                : "border-transparent text-foreground/50 hover:text-foreground/80"
            )}
          >
            <PlayCircle className="w-4 h-4" />
            B站视频
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto finer-scrollbar p-8">
        {activeTab === "console" && <ImportConsole />}
        {activeTab === "wechat" && <WeChatConfig />}
        {activeTab === "bilibili" && <BilibiliConfig />}
      </div>
    </div>
  );
}