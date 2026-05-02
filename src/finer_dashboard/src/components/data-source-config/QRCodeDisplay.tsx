"use client";

import React from "react";
import { QrCode, Loader2, AlertCircle, RefreshCw, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WeChatLoginStatus } from "@/lib/contracts";

interface QRCodeDisplayProps {
  qrDataUri: string | null;
  isLoading: boolean;
  status: WeChatLoginStatus | null;
  expiresIn?: number;
  error?: string | null;
  onRefresh?: () => void;
}

export function QRCodeDisplay({
  qrDataUri,
  isLoading,
  status,
  expiresIn,
  error,
  onRefresh,
}: QRCodeDisplayProps) {
  // Loading state
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-stone-200 bg-white">
        <Loader2 className="w-8 h-8 animate-spin text-stone-400 mb-3" />
        <p className="text-sm text-stone-500">正在生成二维码...</p>
      </div>
    );
  }

  // Error / Exporter unavailable
  if (status === "failed" || error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-stone-200 bg-white">
        <AlertCircle className="w-8 h-8 text-[--finer-red] mb-3" strokeWidth={1.5} />
        <p className="text-sm text-stone-900 font-medium mb-1">获取失败</p>
        <p className="text-xs text-stone-500 mb-4">{error || "请检查导出服务是否运行"}</p>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="px-3 py-1.5 text-xs font-semibold border border-stone-900 text-stone-900 hover:bg-stone-900 hover:text-white transition-all"
          >
            重新获取
          </button>
        )}
      </div>
    );
  }

  // Expired state
  if (status === "expired") {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-stone-200 bg-white">
        <QrCode className="w-8 h-8 text-stone-300 mb-3" strokeWidth={1} />
        <p className="text-sm text-stone-900 font-medium mb-1">二维码已过期</p>
        <p className="text-xs text-stone-500 mb-4">请重新获取登录二维码</p>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold border border-stone-900 text-stone-900 hover:bg-stone-900 hover:text-white transition-all"
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        )}
      </div>
    );
  }

  // Confirmed state
  if (status === "confirmed") {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-stone-200 bg-white">
        <CheckCircle2 className="w-8 h-8 text-stone-900 mb-3" strokeWidth={1.5} />
        <p className="text-sm text-stone-900 font-medium">登录成功</p>
      </div>
    );
  }

  // Scanned state
  if (status === "scanned") {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-stone-200 bg-white">
        <CheckCircle2 className="w-8 h-8 text-stone-600 mb-3" strokeWidth={1.5} />
        <p className="text-sm text-stone-900 font-medium mb-1">已扫码</p>
        <p className="text-xs text-stone-500">请在手机上确认登录</p>
      </div>
    );
  }

  // QR ready — show the QR code
  if (qrDataUri) {
    return (
      <div className="flex flex-col items-center p-6 border border-stone-200 bg-white">
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={qrDataUri}
            alt="微信登录二维码"
            className="w-48 h-48 object-contain"
          />
          {expiresIn !== undefined && expiresIn > 0 && (
            <div className="absolute -top-2 -right-2 bg-stone-900 text-white text-[10px] font-bold px-1.5 py-0.5 tabular-nums">
              {expiresIn}s
            </div>
          )}
        </div>
        <div className="mt-4 text-center">
          <p className="text-sm font-medium text-stone-900">使用微信扫码登录</p>
          <p className="text-xs text-stone-500 mt-1">
            打开微信 → 扫一扫 → 确认登录
          </p>
        </div>
      </div>
    );
  }

  // Initial empty state
  return (
    <div className="flex flex-col items-center justify-center p-8 border border-dashed border-stone-200 bg-stone-50">
      <QrCode className="w-8 h-8 text-stone-300 mb-3" strokeWidth={1} />
      <p className="text-sm text-stone-400">点击「获取二维码」开始登录</p>
    </div>
  );
}
