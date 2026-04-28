"use client";

import React, { useState, useCallback } from "react";
import {
  PlayCircle,
  Loader2,
  Search,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Clock,
  FileText,
  RefreshCw,
} from "lucide-react";
import { SyncStatus, SyncStatusType } from "./SyncStatus";
import { cn } from "@/lib/utils";

type VideoInfo = {
  bvid: string;
  title: string;
  author: string;
  duration: string;
  cover_url: string;
  description: string;
  pub_date: string;
  view_count: number;
};

type TranscribedVideo = {
  id: string;
  bvid: string;
  title: string;
  author: string;
  transcribed_at: string;
  transcript_file: string;
  status: "completed" | "processing" | "failed";
};

export function BilibiliConfig() {
  // Search state
  const [inputValue, setInputValue] = useState("");
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [loadingVideo, setLoadingVideo] = useState(false);
  const [videoError, setVideoError] = useState<string | null>(null);

  // Transcribe state
  const [transcribeStatus, setTranscribeStatus] = useState<SyncStatusType>("idle");
  const [transcribeMessage, setTranscribeMessage] = useState("");
  const [transcribeProgress, setTranscribeProgress] = useState(0);

  // History state
  const [transcribedVideos, setTranscribedVideos] = useState<TranscribedVideo[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Load history on mount
  React.useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      // 后端列表端点是 /api/bilibili/list
      const res = await fetch("/api/bilibili/list");
      const data = await res.json();
      // 映射后端字段到前端期望的字段
      const videos = (data.videos || []).map((v: any) => ({
        id: v.bvid,
        bvid: v.bvid,
        title: v.title,
        author: v.uploader,
        transcribed_at: v.transcribed_at || "",
        transcript_file: "",
        status: "completed" as const,
      }));
      setTranscribedVideos(videos);
    } catch (err) {
      console.error("Failed to load history:", err);
    } finally {
      setLoadingHistory(false);
    }
  };

  // Extract BV ID from input
  const extractBvId = (input: string): string | null => {
    // Direct BV ID
    if (input.startsWith("BV") && input.length === 12) {
      return input;
    }
    // URL pattern: https://www.bilibili.com/video/BVxxx or /BVxxx
    const match = input.match(/BV[a-zA-Z0-9]{10}/);
    return match ? match[0] : null;
  };

  // Fetch video info
  const handleFetchVideo = async () => {
    const bvid = extractBvId(inputValue.trim());
    if (!bvid) {
      setVideoError("请输入有效的BV号或B站视频链接");
      return;
    }

    setLoadingVideo(true);
    setVideoError(null);
    setVideoInfo(null);

    try {
      // 使用路径参数而非查询参数
      const res = await fetch(`/api/bilibili/video/${bvid}`);
      const data = await res.json();

      if (res.status === 400 || res.status === 500) {
        setVideoError(data.detail || "获取视频信息失败");
      } else {
        // 映射后端字段到前端期望的字段
        setVideoInfo({
          bvid: data.bvid,
          title: data.title,
          author: data.uploader, // 后端返回 uploader
          duration: formatDuration(data.duration), // 后端返回秒数
          cover_url: data.cover_url,
          description: data.description,
          pub_date: data.publish_time, // 后端返回 publish_time
          view_count: 0, // 后端不返回播放量
        });
      }
    } catch (err) {
      console.error("Failed to fetch video:", err);
      setVideoError("获取视频信息失败，请重试");
    } finally {
      setLoadingVideo(false);
    }
  };

  // 格式化秒数为时长字符串
  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Start transcription
  const handleTranscribe = async () => {
    if (!videoInfo) return;

    setTranscribeStatus("syncing");
    setTranscribeMessage("正在获取视频信息...");
    setTranscribeProgress(10);

    try {
      // Update progress simulation
      const progressInterval = setInterval(() => {
        setTranscribeProgress((prev) => Math.min(prev + 5, 90));
      }, 500);

      // 使用路径参数而非 body
      const res = await fetch(`/api/bilibili/transcribe/${videoInfo.bvid}?language=zh&save_files=true`, {
        method: "POST",
      });

      clearInterval(progressInterval);
      const data = await res.json();

      if (res.ok) {
        setTranscribeProgress(100);
        setTranscribeStatus("success");
        setTranscribeMessage(`转录完成，已保存到 ${data.transcript_path || "F0"}`);
        // Reload history
        await loadHistory();
      } else {
        setTranscribeStatus("error");
        setTranscribeMessage(data.detail || "转录失败，请重试");
      }
    } catch (err) {
      console.error("Transcribe failed:", err);
      setTranscribeStatus("error");
      setTranscribeMessage("转录失败，请检查网络连接");
    }
  };

  // Clear video info
  const handleClear = () => {
    setInputValue("");
    setVideoInfo(null);
    setVideoError(null);
    setTranscribeStatus("idle");
    setTranscribeMessage("");
    setTranscribeProgress(0);
  };

  return (
    <div className="space-y-8">
      {/* Input Section */}
      <section className="space-y-4">
        <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--ink-soft)]">
          视频转录
        </h2>

        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleFetchVideo()}
              placeholder="输入BV号或粘贴B站视频链接 (如: BV1xx 或 https://bilibili.com/video/BVxxx)"
              className="w-full pl-10 pr-4 py-3 bg-white border border-stone-200 rounded-sm text-sm focus:outline-none focus:ring-2 focus:ring-morningstar-red/20 focus:border-morningstar-red/40 transition-all"
            />
          </div>
          <button
            onClick={handleFetchVideo}
            disabled={loadingVideo || !inputValue.trim()}
            className={cn(
              "flex items-center gap-2 px-6 py-3 text-xs font-bold uppercase tracking-widest text-white rounded-sm transition-all",
              loadingVideo || !inputValue.trim()
                ? "bg-stone-300 cursor-not-allowed"
                : "bg-morningstar-red hover:bg-morningstar-red/90"
            )}
          >
            {loadingVideo ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            查询
          </button>
        </div>

        {/* Error */}
        {videoError && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-sm text-morningstar-red text-sm">
            <AlertCircle className="w-4 h-4" />
            {videoError}
          </div>
        )}
      </section>

      {/* Video Preview */}
      {videoInfo && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--ink-soft)]">
              视频信息
            </h2>
            <button
              onClick={handleClear}
              className="text-xs text-foreground/50 hover:text-foreground/80 transition-colors"
            >
              清除
            </button>
          </div>

          <div className="flex gap-6 p-6 bg-white border border-stone-200 rounded-sm">
            {/* Cover */}
            {videoInfo.cover_url && (
              <div className="w-48 h-28 rounded-sm overflow-hidden flex-shrink-0 bg-stone-100">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={videoInfo.cover_url}
                  alt={videoInfo.title}
                  className="w-full h-full object-cover"
                />
              </div>
            )}

            {/* Info */}
            <div className="flex-1 min-w-0 space-y-3">
              <div>
                <h3 className="text-lg font-bold line-clamp-2">{videoInfo.title}</h3>
                <p className="text-sm text-foreground/60 mt-1">
                  UP主: {videoInfo.author}
                </p>
              </div>

              <div className="flex flex-wrap gap-3 text-xs text-foreground/50">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {videoInfo.duration}
                </span>
                <span className="flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  {videoInfo.pub_date}
                </span>
                <span className="flex items-center gap-1">
                  播放: {videoInfo.view_count.toLocaleString()}
                </span>
                <span className="bg-stone-100 px-2 py-0.5 rounded text-[10px] font-mono">
                  {videoInfo.bvid}
                </span>
              </div>

              {videoInfo.description && (
                <p className="text-xs text-foreground/40 line-clamp-2">
                  {videoInfo.description}
                </p>
              )}

              {/* Actions */}
              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={handleTranscribe}
                  disabled={transcribeStatus === "syncing"}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white rounded-sm transition-all",
                    transcribeStatus === "syncing"
                      ? "bg-stone-300 cursor-not-allowed"
                      : "bg-[var(--accent-teal)] hover:opacity-90"
                  )}
                >
                  {transcribeStatus === "syncing" ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      转录中...
                    </>
                  ) : (
                    <>
                      <PlayCircle className="w-4 h-4" />
                      开始转录
                    </>
                  )}
                </button>

                <a
                  href={`https://www.bilibili.com/video/${videoInfo.bvid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-foreground/60 hover:text-foreground transition-colors"
                >
                  <ExternalLink className="w-3 h-3" />
                  在B站打开
                </a>
              </div>
            </div>
          </div>

          {/* Transcribe Status */}
          {transcribeStatus !== "idle" && (
            <SyncStatus
              status={transcribeStatus}
              message={transcribeMessage}
              progress={transcribeProgress}
            />
          )}
        </section>
      )}

      {/* History Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--ink-soft)]">
            已转录视频 ({transcribedVideos.length})
          </h2>
          <button
            onClick={loadHistory}
            disabled={loadingHistory}
            className="p-2 hover:bg-stone-100 rounded transition-colors"
          >
            <RefreshCw
              className={cn(
                "w-4 h-4",
                loadingHistory && "animate-spin"
              )}
            />
          </button>
        </div>

        {loadingHistory ? (
          <div className="flex items-center justify-center p-8 bg-white border border-stone-200 rounded-sm">
            <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
          </div>
        ) : transcribedVideos.length === 0 ? (
          <div className="p-8 bg-stone-50 border border-dashed border-stone-200 rounded-sm text-center">
            <PlayCircle className="w-12 h-12 text-stone-300 mx-auto mb-3" strokeWidth={1} />
            <p className="text-sm text-foreground/40">暂无转录记录</p>
            <p className="text-xs text-foreground/30 mt-1">
              输入BV号开始转录视频
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {transcribedVideos.map((video) => (
              <div
                key={video.id}
                className="flex items-center gap-4 p-4 bg-white border border-stone-200 rounded-sm hover:border-morningstar-red/20 transition-all"
              >
                {/* Status Icon */}
                <div
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0",
                    video.status === "completed"
                      ? "bg-green-50 text-green-600"
                      : video.status === "processing"
                      ? "bg-blue-50 text-blue-500"
                      : "bg-red-50 text-morningstar-red"
                  )}
                >
                  {video.status === "completed" ? (
                    <CheckCircle2 className="w-5 h-5" />
                  ) : video.status === "processing" ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <AlertCircle className="w-5 h-5" />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold truncate">{video.title}</p>
                  <p className="text-xs text-foreground/50 mt-0.5">
                    {video.author} · {video.transcribed_at}
                  </p>
                </div>

                {/* BV ID */}
                <span className="text-[10px] font-mono text-foreground/40 bg-stone-100 px-2 py-1 rounded">
                  {video.bvid}
                </span>

                {/* File Link */}
                {video.status === "completed" && video.transcript_file && (
                  <span className="text-xs text-foreground/50 flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {video.transcript_file.split("/").pop()}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}