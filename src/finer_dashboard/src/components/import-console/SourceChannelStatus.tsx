"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface ChannelInfo {
  id: string;
  emoji: string;
  name: string;
  description: string;
}

const CHANNELS: ChannelInfo[] = [
  {
    id: "feishu",
    emoji: "📍",
    name: "飞书",
    description: "从飞书群聊和文档导入投研内容",
  },
  {
    id: "wechat",
    emoji: "💬",
    name: "微信公众号",
    description: "同步微信公众号文章和推送",
  },
  {
    id: "bilibili",
    emoji: "🎥",
    name: "B站",
    description: "下载B站视频并转录为文本",
  },
  {
    id: "notebooklm",
    emoji: "📓",
    name: "NotebookLM",
    description: "从 Google NotebookLM 导入研究笔记",
  },
];

export function SourceChannelStatus() {
  return (
    <div className="bg-white border border-stone-200 rounded-lg p-6">
      <h3 className="font-bold text-foreground mb-4">数据源渠道</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {CHANNELS.map((channel) => (
          <div
            key={channel.id}
            className={cn(
              "p-4 rounded-lg border border-stone-200 bg-stone-50/50",
              "hover:border-stone-300 transition-colors"
            )}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">{channel.emoji}</span>
              <span className="font-medium text-sm text-foreground">
                {channel.name}
              </span>
            </div>
            <p className="text-xs text-foreground/50 leading-relaxed">
              {channel.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
