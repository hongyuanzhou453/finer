"use client";

import React from "react";
import {
  Database,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2,
  HardDrive,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { F0IndexHealth } from "@/lib/contracts";
import { apiPost } from "@/lib/api-client";

interface IndexHealthCardProps {
  health: F0IndexHealth | null;
  loading: boolean;
}

const STATUS_CONFIG: Record<
  F0IndexHealth["status"],
  { label: string; color: string; bgColor: string; icon: React.ElementType }
> = {
  healthy: {
    label: "健康",
    color: "text-green-700",
    bgColor: "bg-green-50 border-green-200",
    icon: CheckCircle,
  },
  stale: {
    label: "过期",
    color: "text-yellow-700",
    bgColor: "bg-yellow-50 border-yellow-200",
    icon: AlertTriangle,
  },
  missing: {
    label: "缺失",
    color: "text-red-700",
    bgColor: "bg-red-50 border-red-200",
    icon: XCircle,
  },
  rebuilding: {
    label: "重建中",
    color: "text-blue-700",
    bgColor: "bg-blue-50 border-blue-200",
    icon: Loader2,
  },
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString("zh-CN");
}

export function IndexHealthCard({ health, loading }: IndexHealthCardProps) {
  const [rebuilding, setRebuilding] = React.useState(false);
  const [rebuildError, setRebuildError] = React.useState<string | null>(null);

  const handleRebuild = async () => {
    setRebuilding(true);
    setRebuildError(null);
    try {
      await apiPost("/api/f0-index/rebuild", {});
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "重建请求失败";
      setRebuildError(message);
    } finally {
      setRebuilding(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-stone-100 rounded-lg animate-pulse" />
          <div className="space-y-2">
            <div className="h-4 w-24 bg-stone-100 rounded animate-pulse" />
            <div className="h-3 w-32 bg-stone-100 rounded animate-pulse" />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-stone-50 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-6">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-stone-100 rounded-lg">
            <Database className="w-5 h-5 text-stone-400" />
          </div>
          <div>
            <h3 className="font-bold text-foreground">索引健康状态</h3>
            <p className="text-sm text-foreground/50">索引服务未就绪</p>
          </div>
        </div>
      </div>
    );
  }

  const statusCfg = STATUS_CONFIG[health.status];
  const StatusIcon = statusCfg.icon;

  return (
    <div className="bg-white border border-stone-200 rounded-lg p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-stone-100 rounded-lg">
            <Database className="w-5 h-5 text-foreground/70" />
          </div>
          <div>
            <h3 className="font-bold text-foreground">索引健康状态</h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span
                className={cn(
                  "inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border",
                  statusCfg.bgColor,
                  statusCfg.color
                )}
              >
                <StatusIcon
                  className={cn(
                    "w-3 h-3",
                    health.status === "rebuilding" && "animate-spin"
                  )}
                />
                {statusCfg.label}
              </span>
              {health.needs_rebuild && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-yellow-50 border border-yellow-200 text-yellow-700">
                  <AlertTriangle className="w-3 h-3" />
                  需要重建
                </span>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={handleRebuild}
          disabled={rebuilding}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-stone-200 rounded hover:bg-stone-50 transition-colors",
            rebuilding && "opacity-50 cursor-not-allowed"
          )}
        >
          <RefreshCw
            className={cn("w-3 h-3", rebuilding && "animate-spin")}
          />
          {rebuilding ? "重建中..." : "重建索引"}
        </button>
      </div>

      {rebuildError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {rebuildError}
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-3 bg-stone-50 rounded-lg">
          <p className="text-xs text-foreground/50 mb-1">记录数</p>
          <p className="text-lg font-bold text-foreground">
            {health.record_count.toLocaleString()}
          </p>
        </div>
        <div className="p-3 bg-stone-50 rounded-lg">
          <p className="text-xs text-foreground/50 mb-1">漂移量</p>
          <p
            className={cn(
              "text-lg font-bold",
              health.drift > 0 ? "text-yellow-600" : "text-foreground"
            )}
          >
            {health.drift}
          </p>
        </div>
        <div className="p-3 bg-stone-50 rounded-lg">
          <p className="text-xs text-foreground/50 mb-1">上次重建</p>
          <p className="text-sm font-medium text-foreground">
            {formatTime(health.last_rebuild_at)}
          </p>
          {health.last_rebuild_duration_ms !== null && (
            <p className="text-xs text-foreground/40 mt-0.5">
              耗时 {formatDuration(health.last_rebuild_duration_ms)}
            </p>
          )}
        </div>
        <div className="p-3 bg-stone-50 rounded-lg">
          <p className="text-xs text-foreground/50 mb-1 flex items-center gap-1">
            <HardDrive className="w-3 h-3" />
            数据库大小
          </p>
          <p className="text-lg font-bold text-foreground">
            {formatBytes(health.db_size_bytes)}
          </p>
        </div>
      </div>

      {/* Manifest info */}
      <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between text-xs text-foreground/40">
        <span>
          磁盘 Manifest: {health.manifest_count_on_disk} 个
        </span>
        <span className="font-mono">{health.db_path}</span>
      </div>
    </div>
  );
}
