export type WorkflowStage =
  | "intake"
  | "enrichment"
  | "library"
  | "parsing"
  | "extraction"
  | "review"
  | "backtest";

export type ReviewDirection =
  | "bullish"
  | "bearish"
  | "neutral"
  | "watchlist"
  | "risk_warning";

export type SourceType = "feishu" | "notebooklm" | "local" | "unknown";

export type ReviewAction = {
  id: string;
  actionType: string;
  instrumentType: string;
  triggerCondition: string;
  targetPriceLow: string;
  targetPriceHigh: string;
  confidence: number;
  status: "draft" | "active" | "watch";
};

export type ReviewPayload = {
  ticker: string;
  direction: ReviewDirection;
  timeHorizon: string;
  rationale: string;
  evidenceText: string;
  confidence: number;
  tags: string[];
  ambiguityNotes: string[];
  actionChain: ReviewAction[];
};

export type AssetFile = {
  id: string;
  name: string;
  size: string;
  date: string;
  type: string;
  status: string;
  workflowStage: WorkflowStage;
  stageBadge: string;
  creatorName: string;
  sourcePlatform: string;
  contentType: string;
  contentId: string;
  sourcePath?: string;
  manifestPath?: string;
  evidencePath?: string;
  candidateEventPath?: string;
  approvedEventPath?: string;
  summary: string;
  tags: string[];
  reviewPayload?: ReviewPayload;
  // Source classification fields
  sourceType: SourceType;
  sourceGroupId?: string;
  sourceGroupName?: string;
  fileTimestamp?: string;
  // Semantic display fields (LLM-enhanced)
  fileType?: string; // Display-friendly: 聊天记录/图片/PDF/文档
  sourceName?: string; // Human-readable source name (e.g. feishu chat name)
  semanticTitle?: string; // LLM-generated short title summarizing content
};

export type KOL = {
  id: string;
  name: string;
  platform: "feishu" | "wechat" | "bilibili";
  platformId: string;
  avatar?: string;
  overallScore: number;
  dimensionScores: {
    accuracy: number;
    timeliness: number;
    clarity: number;
    depth: number;
    consistency: number;
  };
  accuracy: number;
  avgReturn: number;
  totalOpinions: number;
  lastActive: string;
  tags: string[];
  enabled: boolean;
};

export type KOLTimelineEvent = {
  id: string;
  kolId: string;
  date: string;
  ticker: string;
  direction: "bullish" | "bearish" | "neutral";
  summary: string;
  return?: number;
  evidenceText?: string;
};

export type BacktestTask = {
  id: string;
  name: string;
  kolIds: string[];
  kolNames: string[];
  status: "pending" | "running" | "completed" | "failed";
  startDate: string;
  endDate: string;
  createdAt: string;
  completedAt?: string;
  config: {
    initialCapital: number;
    positionSize: number;
  };
  metrics?: {
    totalReturn: number;
    annualizedReturn: number;
    sharpeRatio: number;
    maxDrawdown: number;
    winRate: number;
    totalTrades: number;
  };
  trades?: Array<{
    id: string;
    ticker: string;
    direction: "long" | "short";
    entryDate: string;
    exitDate: string;
    entryPrice: number;
    exitPrice: number;
    return: number;
    opinionId: string;
  }>;
};

export type SourceGroup = {
  id: string;
  name: string;
  type: "feishu" | "notebooklm";
  fileCount: number;
  lastSync?: string;
};

// =============================================================================
// Lineage & Version Control
// =============================================================================

export type DataLineage = {
  original_content_id: string;
  original_source?: string;
  enrichment_content_ids: string[];
  segment_ids: string[];
  event_ids: string[];
  extraction_id?: string;
  pipeline_run_id?: string;
  created_at: string;
};

export type VersionInfo = {
  schema_version: string;
  extraction_config_hash?: string;
  model_version?: string;
  model_provider?: string;
  prompt_version?: string;
  prompt_hash?: string;
  created_at: string;
  modified_at?: string;
  modified_by?: string;
  temperature?: number;
  additional_params: Record<string, unknown>;
};

export type PipelineRunInfo = {
  run_id: string;
  started_at: string;
  completed_at?: string;
  config_snapshot: Record<string, unknown>;
  items_processed: number;
  items_failed: number;
  status: "running" | "completed" | "failed";
  error_message?: string;
};

export type LineageResponse = {
  ok: boolean;
  data?: {
    trade_action_id?: string;
    lineage?: DataLineage;
    summary?: string;
    original_content_id?: string;
    original_source?: string;
    segment_ids?: string[];
    event_ids?: string[];
    content_id?: string;
    action_count?: number;
    action_ids?: string[];
    segment_id?: string;
    event_id?: string;
  };
  error?: {
    code: string;
    message: string;
  };
};

export type LineageStatsResponse = {
  total_actions_tracked: number;
  total_contents: number;
  total_segments: number;
  total_events: number;
  active_pipeline_runs: number;
  completed_pipeline_runs: number;
};

// =============================================================================
// F4 Policy Schema Types
// =============================================================================

export type PolicyRiskConstraints = {
  max_position_hint: "none" | "small" | "medium" | "large";
  requires_human_review: boolean;
  risk_notes: string[];
  max_concentration_pct?: number;
  stop_loss_hint?: string;
  time_decay_days?: number;
  metadata: Record<string, unknown>;
};

export type PolicyLayerTrace = {
  layer_name: string;
  layer_version: string;
  applied: boolean;
  reason: string;
  modifications: string[];
  order_index: number;
  metadata: Record<string, unknown>;
};

export type PolicyDecision = {
  decision_id: string;
  policy_id: string;
  layer: string;
  decision_type:
    | "action_override"
    | "sizing_adjust"
    | "holding_adjust"
    | "risk_bound"
    | "confidence_adjust"
    | "human_escalation"
    | "no_op";
  description: string;
  rationale: string;
  overrides_previous: boolean;
  metadata: Record<string, unknown>;
};

export type PolicyMappingResult = {
  policy_id: string;
  intent_id: string;
  creator_id?: string;
  kol_id?: string;
  policy_version: string;
  policy_layers_applied: string[];
  action_hint:
    | "watch_only"
    | "watch_or_no_trade"
    | "avoid_or_watch_risk"
    | "open_position"
    | "add_position"
    | "reduce_position"
    | "hold_position"
    | "close_position"
    | "review_required";
  position_sizing_hint:
    | "none"
    | "small"
    | "medium"
    | "large"
    | "review_required";
  holding_period_hint:
    | "intraday"
    | "short_term"
    | "medium_term"
    | "long_term"
    | "review_required";
  risk_constraints: PolicyRiskConstraints;
  mapping_rationale: string;
  layer_traces: PolicyLayerTrace[];
  decisions: PolicyDecision[];
  confidence: number;
  original_intent_confidence?: number;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type PolicyMappedIntent = {
  mapped_id: string;
  intent_id: string;
  policy_id: string;
  original_intent_summary: string;
  action_hint:
    | "watch_only"
    | "watch_or_no_trade"
    | "avoid_or_watch_risk"
    | "open_position"
    | "add_position"
    | "reduce_position"
    | "hold_position"
    | "close_position"
    | "review_required";
  position_sizing_hint:
    | "none"
    | "small"
    | "medium"
    | "large"
    | "review_required";
  holding_period_hint:
    | "intraday"
    | "short_term"
    | "medium_term"
    | "long_term"
    | "review_required";
  risk_notes: string[];
  mapping_confidence: number;
  requires_human_review: boolean;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type PolicyContext = {
  kol_id: string;
  style_archetype: string;
  risk_preference: string;
  persona_summary?: string;
  active_corrections: string[];
  metadata: Record<string, unknown>;
};

// =============================================================================
// F5 TradeAction Upstream Trace Fields (partial — mirrors Python schema)
// =============================================================================

/** Canonical trace status for TradeAction F3→F4→F5 chain completeness. */
export type CanonicalTraceStatus = "canonical" | "partial" | "non_canonical";

/** Upstream trace fields on TradeAction (subset relevant to frontend). */
export type TradeActionTrace = {
  intent_id?: string;
  policy_id?: string;
  evidence_span_ids: string[];
  effective_trade_at?: string;
  canonical_trace_status: CanonicalTraceStatus;
};
