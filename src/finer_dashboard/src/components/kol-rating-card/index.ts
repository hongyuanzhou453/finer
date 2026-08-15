// KOL Rating Card Components
// 参考晨星网基金经理评价风格设计

export { KOLRatingCard, default } from "./KOLRatingCard";
// KOLRating 本地类型已删除：响应契约以 @/lib/contracts 的 KOLRatingResponse 为准
export type {
  DimensionScore,
  TimelineEvent,
  FocusArea,
  RecentOpinion,
  KOLRatingCardProps,
} from "./KOLRatingCard";

export { StarRating, MedalBadge, getRatingMedalStyle } from "./StarRating";
export type { StarRatingProps } from "./StarRating";

export { DimensionScores, DimensionMiniChart } from "./DimensionScores";
export type { DimensionScoresProps } from "./DimensionScores";

export { PerformanceTimeline } from "./PerformanceTimeline";
export type { PerformanceTimelineProps } from "./PerformanceTimeline";

export { FocusAreas, FocusRadar } from "./FocusAreas";
export type { FocusAreasProps } from "./FocusAreas";

export { RecentOpinions } from "./RecentOpinions";
export type { RecentOpinionsProps } from "./RecentOpinions";