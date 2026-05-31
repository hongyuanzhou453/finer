"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  LineChart,
  Plus,
  Play,
  Pause,
  Trash2,
  Loader2,
  Calendar,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  Clock,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import type { BacktestTask } from "@/lib/contracts";
import { useAsyncData } from "@/lib/hooks/useAsyncData";
import { listBacktestResults, deleteBacktestResult, ApiError } from "@/lib/api-client";
import { backtestSummaryToTask } from "@/lib/adapters";
import { returnToneClass } from "@/lib/finance-format";

function getStatusIcon(status: BacktestTask["status"]) {
  switch (status) {
    case "completed":
      return <CheckCircle className="w-4 h-4 text-green-600" />;
    case "running":
      return <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />;
    case "pending":
      return <Clock className="w-4 h-4 text-amber-600" />;
    case "failed":
      return <XCircle className="w-4 h-4 text-red-600" />;
  }
}

function getStatusLabel(status: BacktestTask["status"]) {
  const labels = {
    completed: "已完成",
    running: "运行中",
    pending: "等待中",
    failed: "失败",
  };
  return labels[status];
}

function getStatusColor(status: BacktestTask["status"]) {
  const colors = {
    completed: "text-green-600 bg-green-50",
    running: "text-blue-600 bg-blue-50",
    pending: "text-amber-600 bg-amber-50",
    failed: "text-red-600 bg-red-50",
  };
  return colors[status];
}

export default function BacktestManagePage() {
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const {
    data: tasks,
    loading,
    error,
    reload,
  } = useAsyncData(
    () =>
      listBacktestResults().then((results) =>
        results.map(backtestSummaryToTask),
      ),
    [],
  );

  async function handleDelete(id: string) {
    setDeleting(id);
    try {
      await deleteBacktestResult(id);
      reload();
    } catch {
      // error is surfaced via reload
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">回测管理</h1>
          <p className="text-sm text-foreground/60 mt-1">
            创建和管理回测任务
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 bg-morningstar-red text-white rounded-md hover:bg-morningstar-red/90 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          新建回测
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>加载回测列表失败：{error.message}</span>
            <button
              onClick={reload}
              className="ml-auto shrink-0 underline hover:text-red-900"
            >
              重试
            </button>
          </div>
          {error instanceof ApiError && (
            <div className="mt-2 space-y-1 text-xs text-red-600">
              {error.code && <div>错误码：{error.code}</div>}
              {error.requestId && <div>请求 ID：{error.requestId}</div>}
              {error.fixHint && <div>修复建议：{error.fixHint}</div>}
            </div>
          )}
        </div>
      )}

      {/* Create Form Placeholder */}
      {showCreate && (
        <div className="bg-white border border-stone-200 rounded-lg p-6 mb-8">
          <h2 className="text-lg font-bold mb-4">新建回测任务</h2>
          <div className="h-32 flex items-center justify-center text-foreground/40 border border-dashed border-stone-300 rounded">
            <div className="text-center">
              <Plus className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">回测配置表单（待实现）</p>
            </div>
          </div>
        </div>
      )}

      {/* Task List */}
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-foreground/30" />
        </div>
      ) : !tasks || tasks.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-foreground/40">
          <div className="text-center">
            <LineChart className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>暂无回测任务</p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {tasks.map((task) => {
            const firstKolId = task.kolIds[0] ?? "";
            return (
              <div
                key={task.id}
                className="editorial-card p-4"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {/* Header */}
                    <div className="flex items-center gap-3 mb-2">
                      {getStatusIcon(task.status)}
                      <Link
                        href={`/kol/${firstKolId}/backtest/${task.id}`}
                        className="font-bold hover:underline"
                      >
                        {task.name}
                      </Link>
                      <span
                        className={cn(
                          "px-2 py-0.5 text-xs font-medium rounded",
                          getStatusColor(task.status),
                        )}
                      >
                        {getStatusLabel(task.status)}
                      </span>
                    </div>

                    {/* Info */}
                    <div className="flex flex-wrap items-center gap-4 text-sm text-foreground/60">
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {task.startDate} ~ {task.endDate}
                      </div>
                      <div className="flex items-center gap-1">
                        {task.kolNames.slice(0, 2).join(", ")}
                        {task.kolNames.length > 2 &&
                          ` +${task.kolNames.length - 2}`}
                      </div>
                      <div>创建于 {task.createdAt}</div>
                    </div>

                    {/* Metrics */}
                    {task.metrics && (
                      <div className="flex items-center gap-6 mt-3 pt-3 border-t border-[var(--grid-line)]">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-foreground/50">
                            总收益
                          </span>
                          <span
                            className={cn(
                              "text-sm font-bold tabular-nums flex items-center gap-1",
                              returnToneClass(task.metrics.totalReturn),
                            )}
                          >
                            {task.metrics.totalReturn >= 0 ? (
                              <TrendingUp className="w-3 h-3" />
                            ) : (
                              <TrendingDown className="w-3 h-3" />
                            )}
                            {task.metrics.totalReturn.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-foreground/50">
                            夏普
                          </span>
                          <span className="text-sm font-bold tabular-nums">
                            {task.metrics.sharpeRatio.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-foreground/50">
                            最大回撤
                          </span>
                          <span className="text-sm font-bold tabular-nums text-[color:var(--chart-down)]">
                            -{Math.abs(task.metrics.maxDrawdown).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 ml-4">
                    {task.status === "pending" && (
                      <button className="p-2 hover:bg-stone-100 rounded transition-colors">
                        <Play className="w-4 h-4 text-green-600" />
                      </button>
                    )}
                    {task.status === "running" && (
                      <button className="p-2 hover:bg-stone-100 rounded transition-colors">
                        <Pause className="w-4 h-4 text-amber-600" />
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(task.id)}
                      disabled={deleting === task.id}
                      className="p-2 hover:bg-stone-100 rounded transition-colors disabled:opacity-50"
                    >
                      {deleting === task.id ? (
                        <Loader2 className="w-4 h-4 animate-spin text-foreground/40" />
                      ) : (
                        <Trash2 className="w-4 h-4 text-foreground/40" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
