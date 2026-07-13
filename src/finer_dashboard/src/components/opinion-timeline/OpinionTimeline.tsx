"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Loader2,
  RefreshCw,
  GripHorizontal,
} from "lucide-react";
import { TimelineNode } from "./TimelineNode";
import { TimelineFilter, TimelineFilters } from "./TimelineFilter";
import { OpinionDetailModal } from "./OpinionDetailModal";
import { cn } from "@/lib/utils";

// ============================================
// 类型定义
// ============================================

// Full 5-way TradeDirection — backend no longer collapses
// risk_warning/watchlist into bearish/neutral.
export type OpinionDirection =
  | "bullish"
  | "bearish"
  | "neutral"
  | "watchlist"
  | "risk_warning";
export type VerificationStatus = "success" | "failed" | "pending";

export interface TimelineOpinion {
  id: string;
  timestamp: string;
  ticker: string;
  tickerName?: string;
  direction: OpinionDirection;
  confidence: number;
  conviction?: number; // KOL belief strength from F3 (ranking signal)
  verificationStatus: VerificationStatus;

  // 验证结果
  priceChange?: number;
  holdingDays?: number;
  exitReason?: string; // backtest exit_reason (stop_loss/target_reached/…)

  // 来源信息
  sourceText: string;
  author?: string;
  platform?: string;
  market?: string; // target market, e.g. "CN"
  traceStatus?: string; // canonical_trace_status of the F5 action
  instrumentType?: string; // stock/etf/index_future/…/unspecified (concept downgrade)
  executableAt?: string; // canonical execution clock (real signal time)

  // Action Chain
  actionChain?: ActionStep[];

  // RLHF 状态
  rlhfStatus?: "pending" | "reviewed" | "skipped";
  rlhfRating?: number;
}

export interface ActionStep {
  id: string;
  actionType:
    | "watch"
    | "long"
    | "short"
    | "add"
    | "reduce"
    | "close_long"
    | "close_short";
  triggerCondition?: string;
  targetPriceLow?: string;
  targetPriceHigh?: string;
  /** Signed portfolio-fraction delta: + = increase exposure, - = decrease. */
  positionDeltaPct?: number | null;
}

export interface TimelineData {
  opinions: TimelineOpinion[];
  total: number;
  hasMore: boolean;
  nextCursor?: string;
}

export interface OpinionTimelineProps {
  className?: string;
  initialFilters?: Partial<TimelineFilters>;
  onOpinionClick?: (opinion: TimelineOpinion) => void;
}

// ============================================
// 样式常量
// ============================================

const STYLES = {
  container: "bg-[rgba(255,252,247,0.94)] backdrop-blur-xl",
  header: "border-b border-[rgba(95,67,40,0.12)] px-6 py-4",
  track: "relative overflow-x-auto overflow-y-hidden",
  trackInner: "flex items-center gap-6 py-8 px-8 min-w-max",
  axis: "absolute bottom-0 left-0 right-0 h-px bg-[rgba(95,67,40,0.12)]",
  loading: "flex items-center justify-center py-20 text-foreground/40",
  empty: "flex flex-col items-center justify-center py-20 text-foreground/40",
  controls: "flex items-center gap-2",
  zoomBtn: "p-2 rounded-sm border border-stone-200 hover:border-morningstar-red hover:text-morningstar-red transition-colors",
  scrollBtn: "p-2 rounded-sm bg-white border border-stone-200 hover:border-morningstar-red hover:text-morningstar-red transition-colors shadow-sm",
} as const;

// ============================================
// 主组件
// ============================================

export function OpinionTimeline({
  className,
  initialFilters,
  onOpinionClick,
}: OpinionTimelineProps) {
  // 状态
  const [opinions, setOpinions] = useState<TimelineOpinion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [cursor, setCursor] = useState<string | undefined>();

  // 筛选
  const [filters, setFilters] = useState<TimelineFilters>({
    timeRange: "1M",
    tickers: [],
    directions: [],
    kols: [],
    ...initialFilters,
  });

  // 缩放级别 (1 = 100%)
  const [zoom, setZoom] = useState(1);

  // 选中观点
  const [selectedOpinion, setSelectedOpinion] = useState<TimelineOpinion | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // 拖拽滚动
  const trackRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, scrollLeft: 0 });

  // 加载数据
  const loadTimeline = useCallback(async (reset = false) => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      params.set("timeRange", filters.timeRange);
      if (filters.tickers.length > 0) params.set("tickers", filters.tickers.join(","));
      if (filters.directions.length > 0) params.set("directions", filters.directions.join(","));
      if (filters.kols.length > 0) params.set("kols", filters.kols.join(","));
      if (!reset && cursor) params.set("cursor", cursor);

      const response = await fetch(`/api/opinions/timeline?${params.toString()}`);

      if (!response.ok) {
        throw new Error(`Failed to load timeline: ${response.statusText}`);
      }

      const data: TimelineData = await response.json();

      if (reset) {
        setOpinions(data.opinions);
      } else {
        setOpinions(prev => [...prev, ...data.opinions]);
      }

      setHasMore(data.hasMore);
      setCursor(data.nextCursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [filters, cursor]);

  // 初始加载和筛选变化时重新加载
  useEffect(() => {
    setCursor(undefined);
    setOpinions([]);
    loadTimeline(true);
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // 处理节点点击
  const handleNodeClick = useCallback((opinion: TimelineOpinion) => {
    setSelectedOpinion(opinion);
    setModalOpen(true);
    onOpinionClick?.(opinion);
  }, [onOpinionClick]);

  // 缩放控制
  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.25, 2));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.25, 0.5));

  // 滚动控制
  const handleScroll = (direction: "left" | "right") => {
    if (trackRef.current) {
      const scrollAmount = 300 * zoom;
      trackRef.current.scrollBy({
        left: direction === "left" ? -scrollAmount : scrollAmount,
        behavior: "smooth",
      });
    }
  };

  // 拖拽滚动
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!trackRef.current) return;
    setIsDragging(true);
    setDragStart({
      x: e.pageX,
      scrollLeft: trackRef.current.scrollLeft,
    });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !trackRef.current) return;
    e.preventDefault();
    const x = e.pageX;
    const walk = (x - dragStart.x) * 1.5;
    trackRef.current.scrollLeft = dragStart.scrollLeft - walk;
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // 加载更多
  const handleLoadMore = () => {
    if (!loading && hasMore) {
      loadTimeline();
    }
  };

  // 计算节点间距
  const nodeGap = Math.round(24 * zoom);

  return (
    <div className={cn(STYLES.container, "rounded-2xl border border-[rgba(95,67,40,0.12)] shadow-sm", className)}>
      {/* 头部: 筛选与控制 */}
      <div className={STYLES.header}>
        <div className="flex items-center justify-between gap-4">
          <TimelineFilter
            filters={filters}
            onChange={setFilters}
          />

          <div className="flex items-center gap-4">
            {/* 缩放控制 */}
            <div className={STYLES.controls}>
              <button
                onClick={handleZoomOut}
                disabled={zoom <= 0.5}
                className={cn(STYLES.zoomBtn, "disabled:opacity-40 disabled:cursor-not-allowed")}
                title="缩小"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="text-xs font-medium text-foreground/60 w-12 text-center">
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={handleZoomIn}
                disabled={zoom >= 2}
                className={cn(STYLES.zoomBtn, "disabled:opacity-40 disabled:cursor-not-allowed")}
                title="放大"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
            </div>

            {/* 滚动控制 */}
            <div className={STYLES.controls}>
              <button
                onClick={() => handleScroll("left")}
                className={STYLES.scrollBtn}
                title="向左滚动"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleScroll("right")}
                className={STYLES.scrollBtn}
                title="向右滚动"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* 刷新 */}
            <button
              onClick={() => loadTimeline(true)}
              disabled={loading}
              className={cn(STYLES.zoomBtn, loading && "animate-spin")}
              title="刷新"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* 时间线轨道 */}
      <div
        ref={trackRef}
        className={cn(STYLES.track, isDragging && "cursor-grabbing")}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {loading && opinions.length === 0 ? (
          <div className={STYLES.loading}>
            <Loader2 className="w-6 h-6 animate-spin mr-3" />
            <span className="text-sm">加载观点时间线...</span>
          </div>
        ) : error ? (
          <div className={STYLES.empty}>
            <p className="text-sm text-red-500">{error}</p>
            <button
              onClick={() => loadTimeline(true)}
              className="mt-4 text-xs text-morningstar-red hover:underline"
            >
              重试
            </button>
          </div>
        ) : opinions.length === 0 ? (
          <div className={STYLES.empty}>
            <GripHorizontal className="w-8 h-8 mb-3 opacity-30" />
            <p className="text-sm">暂无观点数据</p>
            <p className="text-xs text-foreground/40 mt-1">调整筛选条件查看更多</p>
          </div>
        ) : (
          <>
            <div
              className={STYLES.trackInner}
              style={{ gap: `${nodeGap}px` }}
            >
              {opinions.map((opinion, index) => (
                <TimelineNode
                  key={opinion.id}
                  opinion={opinion}
                  onClick={() => handleNodeClick(opinion)}
                  zoom={zoom}
                  showConnector={index < opinions.length - 1}
                />
              ))}

              {/* 加载更多按钮 */}
              {hasMore && (
                <button
                  onClick={handleLoadMore}
                  disabled={loading}
                  className="flex-shrink-0 flex items-center gap-2 px-6 py-4 rounded-xl border-2 border-dashed border-stone-300 hover:border-morningstar-red hover:bg-morningstar-red/5 transition-all text-sm text-foreground/50 hover:text-morningstar-red"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      加载中...
                    </>
                  ) : (
                    <>
                      <ChevronRight className="w-4 h-4" />
                      加载更多
                    </>
                  )}
                </button>
              )}
            </div>

            {/* 时间轴基线 */}
            <div className={STYLES.axis} />
          </>
        )}
      </div>

      {/* 详情弹窗 */}
      {selectedOpinion && (
        <OpinionDetailModal
          opinion={selectedOpinion}
          open={modalOpen}
          onClose={() => {
            setModalOpen(false);
            setSelectedOpinion(null);
          }}
        />
      )}
    </div>
  );
}

export default OpinionTimeline;
