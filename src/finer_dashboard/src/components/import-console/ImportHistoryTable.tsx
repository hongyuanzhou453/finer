"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { FileText, Inbox, ChevronDown, ChevronRight } from "lucide-react";
import type { ImportRun } from "@/lib/contracts";

interface ImportHistoryTableProps {
  records: ImportRun[];
  loading: boolean;
}

const STATUS_BADGE: Record<
  string,
  { label: string; color: string; bgColor: string }
> = {
  completed: {
    label: "完成",
    color: "text-green-700",
    bgColor: "bg-green-50 border-green-200",
  },
  running: {
    label: "运行中",
    color: "text-blue-700",
    bgColor: "bg-blue-50 border-blue-200",
  },
  failed: {
    label: "失败",
    color: "text-red-700",
    bgColor: "bg-red-50 border-red-200",
  },
  pending: {
    label: "等待中",
    color: "text-stone-600",
    bgColor: "bg-stone-50 border-stone-200",
  },
};

const CHANNEL_LABELS: Record<string, string> = {
  feishu: "飞书",
  wechat: "微信",
  bilibili: "B站",
  notebooklm: "NLM",
  local: "本地",
};

function renderStatusBadge(status: string) {
  const cfg = STATUS_BADGE[status] ?? {
    label: status,
    color: "text-stone-600",
    bgColor: "bg-stone-50 border-stone-200",
  };
  return (
    <span
      className={cn(
        "inline-block px-2 py-0.5 text-xs font-medium rounded-full border",
        cfg.bgColor,
        cfg.color
      )}
    >
      {cfg.label}
    </span>
  );
}

function renderChannel(channel: string) {
  return CHANNEL_LABELS[channel] ?? channel;
}

function formatTime(value: string | null): string {
  if (value) {
    return new Date(value).toLocaleString("zh-CN");
  }
  return "--";
}

/** Expandable error details row for failed imports. */
function ErrorDetailsRow({ record }: { record: ImportRun }) {
  return (
    <tr>
      <td colSpan={6} className="px-4 py-3 bg-red-50/50">
        <div className="space-y-2 text-xs">
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {record.error_code && (
              <div>
                <span className="text-foreground/50">错误码: </span>
                <span className="font-mono font-medium text-red-700">
                  {record.error_code}
                </span>
              </div>
            )}
            {record.error_message && (
              <div>
                <span className="text-foreground/50">错误信息: </span>
                <span className="text-red-600">{record.error_message}</span>
              </div>
            )}
            {record.request_id && (
              <div>
                <span className="text-foreground/50">Request ID: </span>
                <span className="font-mono text-foreground/70">{record.request_id}</span>
              </div>
            )}
            <div>
              <span className="text-foreground/50">可重试: </span>
              <span className={record.retryable ? "text-green-700" : "text-red-600"}>
                {record.retryable ? "是" : "否"}
              </span>
            </div>
            {record.fix_hint && (
              <div className="w-full mt-1 p-2 bg-amber-50 border border-amber-200 rounded text-amber-800">
                {record.fix_hint}
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

export function ImportHistoryTable({
  records,
  loading,
}: ImportHistoryTableProps) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (runId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <div className="p-6 space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-10 bg-stone-50 rounded animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-12">
        <div className="flex flex-col items-center justify-center text-foreground/40">
          <Inbox className="w-10 h-10 mb-3 opacity-50" />
          <p className="text-sm font-medium">暂无导入记录</p>
          <p className="text-xs mt-1">
            通过数据源渠道导入内容后，记录将显示在此处
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-6 py-4 border-b border-stone-100">
        <FileText className="w-4 h-4 text-foreground/50" />
        <h3 className="font-bold text-foreground">导入历史</h3>
        <span className="text-xs text-foreground/40">
          ({records.length} 条)
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 border-b border-stone-200">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-foreground/60 w-8" />
              <th className="px-4 py-3 text-left font-medium text-foreground/60">
                来源渠道
              </th>
              <th className="px-4 py-3 text-left font-medium text-foreground/60">
                导入时间
              </th>
              <th className="px-4 py-3 text-left font-medium text-foreground/60">
                状态
              </th>
              <th className="px-4 py-3 text-right font-medium text-foreground/60">
                创建记录数
              </th>
              <th className="px-4 py-3 text-right font-medium text-foreground/60">
                跳过记录数
              </th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => {
              const isFailed = record.status === "failed";
              const isExpanded = expandedRows.has(record.run_id);

              return (
                <React.Fragment key={record.run_id}>
                  <tr
                    className={cn(
                      "border-b border-stone-100 last:border-0 hover:bg-stone-50/50 transition-colors",
                      isFailed && "cursor-pointer"
                    )}
                    onClick={isFailed ? () => toggleRow(record.run_id) : undefined}
                  >
                    <td className="px-4 py-3 w-8">
                      {isFailed && (
                        isExpanded
                          ? <ChevronDown className="w-3.5 h-3.5 text-foreground/40" />
                          : <ChevronRight className="w-3.5 h-3.5 text-foreground/40" />
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {renderChannel(record.source_channel)}
                    </td>
                    <td className="px-4 py-3 text-foreground/60 text-xs">
                      {formatTime(record.started_at)}
                    </td>
                    <td className="px-4 py-3">
                      {renderStatusBadge(record.status)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {record.records_created}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {record.records_skipped}
                    </td>
                  </tr>
                  {isFailed && isExpanded && (
                    <ErrorDetailsRow record={record} />
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
