"use client";

import React, { useState, useEffect } from "react";
import { RefreshCw, Trash2, Loader2, ExternalLink, AlertCircle } from "lucide-react";
import { QRCodeDisplay } from "./QRCodeDisplay";
import { SyncStatus, SyncStatusType } from "./SyncStatus";
import { cn } from "@/lib/utils";
import { apiFetch, ApiError } from "@/lib/api-client";
import { ErrorPanel } from "@/components/error-panel/ErrorPanel";
import type { WeChatAccount, WeChatArticle, WeChatLoginStatus } from "@/lib/contracts";

type Tab = "login" | "accounts" | "articles";

export function WeChatConfig() {
  const [activeTab, setActiveTab] = useState<Tab>("login");

  // Login state
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [qrDataUri, setQrDataUri] = useState<string | null>(null);
  const [loginStatus, setLoginStatus] = useState<WeChatLoginStatus | null>(null);
  const [expiresIn, setExpiresIn] = useState<number>(0);
  const [loginSessionId, setLoginSessionId] = useState<string | null>(null);
  const [pollingLogin, setPollingLogin] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Accounts state
  const [accounts, setAccounts] = useState<WeChatAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);

  // Articles state
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [articles, setArticles] = useState<WeChatArticle[]>([]);
  const [loadingArticles, setLoadingArticles] = useState(false);

  // Sync state
  const [syncStatus, setSyncStatus] = useState<SyncStatusType>("idle");
  const [syncMessage, setSyncMessage] = useState<string>("");
  const [syncProgress, setSyncProgress] = useState<number>(0);

  // Exporter health
  const [exporterAvailable, setExporterAvailable] = useState<boolean | null>(null);

  // Fetch error state
  const [fetchError, setFetchError] = useState<ApiError | null>(null);

  // Load accounts on mount
  useEffect(() => {
    loadAccounts();
    checkExporterHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkExporterHealth = async () => {
    try {
      const res = await fetch("/api/wechat/exporter/health");
      const data = await res.json();
      setExporterAvailable(data.available);
    } catch {
      setExporterAvailable(false);
    }
  };

  const loadAccounts = async () => {
    setLoadingAccounts(true);
    setFetchError(null);
    try {
      const data = await apiFetch<WeChatAccount[]>("/api/wechat/accounts");
      setAccounts(Array.isArray(data) ? data : []);
      if (data.length > 0 && !selectedAccountId) {
        setSelectedAccountId(data[0].account_id);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFetchError(err);
      }
      console.error("Failed to load accounts:", err);
    } finally {
      setLoadingAccounts(false);
    }
  };

  const handleStartLogin = async () => {
    setIsLoggingIn(true);
    setQrDataUri(null);
    setLoginError(null);
    setLoginStatus(null);
    setFetchError(null);
    try {
      const data = await apiFetch<{
        qr_data_uri?: string;
        qr_url?: string;
        expires_in?: number;
        session_id?: string;
        status?: WeChatLoginStatus;
      }>("/api/wechat/login", { method: "POST" });

      setQrDataUri(data.qr_data_uri || data.qr_url || null);
      setExpiresIn(data.expires_in || 300);
      setLoginSessionId(data.session_id ?? null);
      setLoginStatus(data.status || "qr_ready");
      setPollingLogin(true);
    } catch (err) {
      if (err instanceof ApiError) {
        const hint = err.fixHint
          ? `${err.message} — ${err.fixHint}`
          : err.message;
        setLoginError(hint);
        setFetchError(err);
      } else {
        setLoginError("请求失败，请检查导出服务是否运行");
      }
      setLoginStatus("failed");
    } finally {
      setIsLoggingIn(false);
    }
  };

  // Poll login status
  useEffect(() => {
    if (!pollingLogin || !loginSessionId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/wechat/login/${loginSessionId}/status`);
        const data = await res.json();
        setLoginStatus(data.status);

        if (data.status === "confirmed") {
          setPollingLogin(false);
          setQrDataUri(null);
          setLoginSessionId(null);
          setSyncMessage("登录成功");
          setActiveTab("accounts");
          await loadAccounts();
        } else if (data.status === "expired") {
          setPollingLogin(false);
          setLoginError("二维码已过期，请重新获取");
        } else if (data.status === "failed") {
          setPollingLogin(false);
          setLoginError(data.error_msg || "登录失败");
        }
      } catch (err) {
        console.error("Failed to poll login status:", err);
      }
    }, 2500);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollingLogin, loginSessionId]);

  // Countdown timer
  useEffect(() => {
    if (!pollingLogin || expiresIn <= 0) return;
    const timer = setTimeout(() => setExpiresIn((prev) => prev - 1), 1000);
    return () => clearTimeout(timer);
  }, [pollingLogin, expiresIn]);

  // Load articles when account is selected
  useEffect(() => {
    if (selectedAccountId) loadArticles(selectedAccountId);
  }, [selectedAccountId]);

  const loadArticles = async (accountId: string) => {
    setLoadingArticles(true);
    try {
      const res = await fetch(`/api/wechat/articles/${accountId}`);
      const data = await res.json();
      setArticles(data.articles || []);
    } catch (err) {
      console.error("Failed to load articles:", err);
    } finally {
      setLoadingArticles(false);
    }
  };

  const handleSyncAll = async () => {
    if (!selectedAccountId) return;
    setSyncStatus("syncing");
    setSyncProgress(0);
    setSyncMessage("正在同步文章...");
    setFetchError(null);

    try {
      const data = await apiFetch<{
        synced_count: number;
        failed_count: number;
      }>(`/api/wechat/sync/${selectedAccountId}`, { method: "POST" });

      setSyncStatus("success");
      setSyncMessage(
        `同步完成：${data.synced_count} 篇成功` +
        (data.failed_count > 0 ? `，${data.failed_count} 篇失败` : "")
      );
      setSyncProgress(100);
      await loadArticles(selectedAccountId);
    } catch (err) {
      if (err instanceof ApiError) {
        const hint = err.fixHint
          ? `${err.message} — ${err.fixHint}`
          : err.message;
        setSyncMessage(hint);
        setFetchError(err);
      } else {
        setSyncMessage("同步失败，请重试");
      }
      setSyncStatus("error");
    }
  };

  const handleRemoveAccount = async (accountId: string) => {
    try {
      await fetch(`/api/wechat/accounts/${accountId}`, { method: "DELETE" });
      await loadAccounts();
      if (selectedAccountId === accountId) setSelectedAccountId(null);
    } catch (err) {
      console.error("Failed to remove account:", err);
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "login", label: "扫码登录" },
    { key: "accounts", label: "账号管理" },
    { key: "articles", label: "文章列表" },
  ];

  return (
    <div className="space-y-6">
      {/* Exporter Status */}
      {exporterAvailable === false && (
        <div className="flex items-center gap-2 px-4 py-3 bg-stone-50 border border-stone-200 text-sm text-stone-600">
          <AlertCircle className="w-4 h-4 text-stone-400 flex-shrink-0" />
          <span>导出服务不可用 — 请确认 wechat-article-exporter 已启动</span>
          <button
            onClick={checkExporterHealth}
            className="ml-auto text-xs underline text-stone-500 hover:text-stone-800"
          >
            重试
          </button>
        </div>
      )}

      {/* Fetch Error Panel */}
      {fetchError && (
        <ErrorPanel
          error={fetchError}
          onRetry={() => {
            setFetchError(null);
            loadAccounts();
          }}
          onDismiss={() => setFetchError(null)}
        />
      )}

      {/* Metric Grid */}
      <div className="grid grid-cols-4 border-b border-stone-200 pb-4">
        <MetricCell label="已登录账号" value={String(accounts.length)} />
        <MetricCell
          label="文章总数"
          value={String(accounts.reduce((sum, a) => sum + a.article_count, 0))}
        />
        <MetricCell
          label="最近同步"
          value={
            accounts
              .filter((a) => a.last_sync)
              .sort((a, b) => (b.last_sync || "").localeCompare(a.last_sync || ""))[0]
              ?.last_sync?.slice(0, 10) || "—"
          }
        />
        <MetricCell
          label="导出服务"
          value={exporterAvailable ? "在线" : "离线"}
          valueColor={exporterAvailable ? "text-stone-900" : "text-[--finer-red]"}
        />
      </div>

      {/* Underline Tabs */}
      <div className="border-b border-stone-200">
        <nav className="flex gap-8">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "relative pb-3 text-sm transition-colors",
                activeTab === tab.key
                  ? "text-stone-900 font-semibold"
                  : "text-stone-500 hover:text-stone-700"
              )}
            >
              {tab.label}
              {activeTab === tab.key && (
                <span className="absolute bottom-0 left-0 right-0 h-[3px] bg-stone-900" />
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === "login" && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-stone-900">微信扫码登录</h3>
            <button
              onClick={handleStartLogin}
              disabled={isLoggingIn || pollingLogin}
              className={cn(
                "px-4 py-2 text-xs font-semibold border transition-all",
                isLoggingIn || pollingLogin
                  ? "border-stone-200 text-stone-400 cursor-not-allowed"
                  : "border-stone-900 text-stone-900 hover:bg-stone-900 hover:text-white"
              )}
            >
              {isLoggingIn ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  生成中...
                </span>
              ) : pollingLogin ? (
                "等待扫码..."
              ) : (
                "获取二维码"
              )}
            </button>
          </div>

          <QRCodeDisplay
            qrDataUri={qrDataUri}
            isLoading={isLoggingIn}
            status={loginStatus}
            expiresIn={expiresIn}
            error={loginError}
            onRefresh={handleStartLogin}
          />
        </section>
      )}

      {activeTab === "accounts" && (
        <section className="space-y-4">
          {loadingAccounts ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="w-5 h-5 animate-spin text-stone-400" />
            </div>
          ) : accounts.length === 0 ? (
            <div className="p-8 text-center text-sm text-stone-400 border border-dashed border-stone-200">
              暂无已登录账号
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-200 text-left">
                  <th className="pb-2 font-semibold text-stone-900">账号</th>
                  <th className="pb-2 font-semibold text-stone-900">文章数</th>
                  <th className="pb-2 font-semibold text-stone-900">最近同步</th>
                  <th className="pb-2 font-semibold text-stone-900">状态</th>
                  <th className="pb-2 w-12"></th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((acc) => (
                  <tr
                    key={acc.account_id}
                    onClick={() => {
                      setSelectedAccountId(acc.account_id);
                      setActiveTab("articles");
                    }}
                    className={cn(
                      "border-b border-stone-100 cursor-pointer hover:bg-stone-50 transition-colors",
                      selectedAccountId === acc.account_id && "bg-stone-50"
                    )}
                  >
                    <td className="py-3 font-medium text-stone-900">
                      {acc.account_name}
                    </td>
                    <td className="py-3 text-stone-600 tabular-nums">
                      {acc.article_count}
                    </td>
                    <td className="py-3 text-stone-500">
                      {acc.last_sync?.slice(0, 10) || "—"}
                    </td>
                    <td className="py-3">
                      {acc.is_valid ? (
                        <span className="text-xs text-stone-600">活跃</span>
                      ) : (
                        <span className="text-xs text-[--finer-red]">失效</span>
                      )}
                    </td>
                    <td className="py-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveAccount(acc.account_id);
                        }}
                        className="p-1 text-stone-400 hover:text-[--finer-red] transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {activeTab === "articles" && (
        <section className="space-y-4">
          {!selectedAccountId ? (
            <div className="p-8 text-center text-sm text-stone-400 border border-dashed border-stone-200">
              请先选择账号
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-stone-900">
                  {accounts.find((a) => a.account_id === selectedAccountId)?.account_name || "文章"}
                  <span className="ml-2 text-stone-400 font-normal">({articles.length})</span>
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadArticles(selectedAccountId)}
                    disabled={loadingArticles}
                    className="p-1.5 text-stone-500 hover:text-stone-800 transition-colors"
                  >
                    <RefreshCw className={cn("w-4 h-4", loadingArticles && "animate-spin")} />
                  </button>
                  <button
                    onClick={handleSyncAll}
                    disabled={syncStatus === "syncing"}
                    className={cn(
                      "px-3 py-1.5 text-xs font-semibold border transition-all",
                      syncStatus === "syncing"
                        ? "border-stone-200 text-stone-400 cursor-not-allowed"
                        : "border-stone-900 text-stone-900 hover:bg-stone-900 hover:text-white"
                    )}
                  >
                    {syncStatus === "syncing" ? "同步中..." : "同步全部"}
                  </button>
                </div>
              </div>

              {syncStatus !== "idle" && (
                <SyncStatus
                  status={syncStatus}
                  message={syncMessage}
                  progress={syncProgress}
                />
              )}

              {loadingArticles ? (
                <div className="flex items-center justify-center p-8">
                  <Loader2 className="w-5 h-5 animate-spin text-stone-400" />
                </div>
              ) : articles.length === 0 ? (
                <div className="p-8 text-center text-sm text-stone-400 border border-dashed border-stone-200">
                  暂无文章
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-stone-200 text-left">
                      <th className="pb-2 font-semibold text-stone-900">标题</th>
                      <th className="pb-2 font-semibold text-stone-900">作者</th>
                      <th className="pb-2 font-semibold text-stone-900">发布时间</th>
                      <th className="pb-2 font-semibold text-stone-900">状态</th>
                      <th className="pb-2 w-12"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {articles.map((art) => (
                      <tr
                        key={art.article_id}
                        className="border-b border-stone-100 hover:bg-stone-50 transition-colors"
                      >
                        <td className="py-3 max-w-xs truncate text-stone-900">
                          {art.title}
                        </td>
                        <td className="py-3 text-stone-500">
                          {art.author || "—"}
                        </td>
                        <td className="py-3 text-stone-500 tabular-nums">
                          {art.publish_time?.slice(0, 10) || "—"}
                        </td>
                        <td className="py-3">
                          <ArticleStatusBadge status={art.status} />
                        </td>
                        <td className="py-3">
                          {art.content_url && (
                            <a
                              href={art.content_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1 text-stone-400 hover:text-stone-700 transition-colors"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

function MetricCell({
  label,
  value,
  valueColor = "text-stone-900",
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div className="px-4 py-2">
      <p className="text-xs text-stone-500 mb-1">{label}</p>
      <p className={cn("text-lg font-semibold tabular-nums", valueColor)}>{value}</p>
    </div>
  );
}

function ArticleStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    completed: "text-stone-700",
    pending: "text-stone-400",
    syncing: "text-stone-500",
    failed: "text-[--finer-red]",
  };
  const labels: Record<string, string> = {
    completed: "已同步",
    pending: "待同步",
    syncing: "同步中",
    failed: "失败",
  };
  return (
    <span className={cn("text-xs", styles[status] || "text-stone-400")}>
      {labels[status] || status}
    </span>
  );
}
