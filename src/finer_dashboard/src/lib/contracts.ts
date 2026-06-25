// =============================================================================
// API Error Envelope (mirrors src/finer/errors/exceptions.py FinerError.to_payload)
// =============================================================================

/** Structured error details from the backend FinerError.to_payload. */
export interface ApiErrorDetails {
  /** UUID identifying this request in server logs. */
  requestId?: string;
  /** Pipeline stage where the error occurred, e.g. "F0". */
  stage?: string;
  /** Operation that failed, e.g. "wechat_import". */
  operation?: string;
  /** Source channel identifier, e.g. "wechat", "bilibili". */
  sourceChannel?: string;
  /** Whether the operation can be retried. */
  retryable?: boolean;
  /** Actionable fix suggestion for the user. */
  fixHint?: string;
  /** Content ID associated with the error. */
  contentId?: string;
  /** Import run ID associated with the error. */
  importRunId?: string;
  /** External source ID. */
  externalSourceId?: string;
  /** Python exception class name (debugging). */
  exceptionType?: string;
  /** Catch-all for additional error context. */
  [key: string]: unknown;
}

/** Canonical error payload returned by FastAPI error handlers. */
export type ApiErrorEnvelope = {
  ok: false;
  error: {
    /** Stable error code, e.g. "SYS_NTF_001", "F1_PARSE_002". */
    code: string;
    /** Human-readable error message. */
    message: string;
    /** Optional structured details including request_id. */
    details?: {
      /** UUID identifying this request in server logs. */
      request_id?: string;
      /** Pipeline stage where the error occurred. */
      stage?: string;
      /** Operation that failed. */
      operation?: string;
      /** Source channel identifier. */
      source_channel?: string;
      /** Whether the operation can be retried. */
      retryable?: boolean;
      /** Actionable fix suggestion for the user. */
      fix_hint?: string;
      /** Content ID associated with the error. */
      content_id?: string;
      /** Import run ID. */
      import_run_id?: string;
      /** External source ID. */
      external_source_id?: string;
      /** Python exception class name. */
      exception_type?: string;
      /** Catch-all for additional error context. */
      [key: string]: unknown;
    };
  };
};

/**
 * Discriminated union for all API responses.
 * Routes that wrap data in `{ok: true, data: T}` use this directly.
 * Routes that return raw data bypass this — see `parseApiResponse` in api-client.ts.
 */
export type ApiResponse<T> =
  | { ok: true; data: T }
  | ApiErrorEnvelope;

/** Type guard for error responses. */
export function isApiError(response: unknown): response is ApiErrorEnvelope {
  return (
    typeof response === "object" &&
    response !== null &&
    "ok" in response &&
    (response as Record<string, unknown>).ok === false &&
    "error" in response
  );
}

/** Type guard for success envelope responses. */
export function isApiSuccess<T>(
  response: ApiResponse<T>,
): response is { ok: true; data: T } {
  return response.ok === true;
}

// =============================================================================
// Error Code Metadata (client-side lookup, mirrors src/finer/errors/codes.py)
// =============================================================================

/** Subset of error codes most likely to surface in the dashboard UI. */
export const ERROR_CODE_DESCRIPTIONS: Record<
  string,
  { title: string; rootCause: string; fixHint: string }
> = {
  SYS_IN_001: {
    title: "Invalid input",
    rootCause: "A caller supplied invalid input.",
    fixHint: "Validate request fields and required identifiers before calling the API.",
  },
  SYS_IN_002: {
    title: "Request validation failed",
    rootCause: "FastAPI or Pydantic rejected the request payload.",
    fixHint: "Inspect details.errors and align the client payload with the route schema.",
  },
  SYS_AUTH_001: {
    title: "Authentication failed",
    rootCause: "The request did not provide valid credentials.",
    fixHint: "Provide a valid X-API-Key or bearer token.",
  },
  SYS_PERM_001: {
    title: "Permission denied",
    rootCause: "The authenticated request is not allowed to perform this operation.",
    fixHint: "Check the operation sensitivity and provide required secondary authentication.",
  },
  SYS_NTF_001: {
    title: "Resource not found",
    rootCause: "The requested resource or route target does not exist.",
    fixHint: "Check the identifier, path, and backing store.",
  },
  SYS_CNF_001: {
    title: "Resource conflict",
    rootCause: "The requested operation conflicts with current state.",
    fixHint: "Refresh state and retry with a non-conflicting update.",
  },
  SYS_TMO_001: {
    title: "System timeout",
    rootCause: "A local or infrastructure operation exceeded its time budget.",
    fixHint: "Retry with a longer timeout or inspect the blocked dependency.",
  },
  SYS_INT_001: {
    title: "Internal server error",
    rootCause: "An unexpected server error escaped domain-specific handling.",
    fixHint: "Check server logs using the request_id and add a narrower FinerError at the source.",
  },
  API_NTF_001: {
    title: "API resource not found",
    rootCause: "The API route could not find the requested resource.",
    fixHint: "Verify the resource id and storage index.",
  },
  API_STATE_001: {
    title: "API state conflict",
    rootCause: "The API request conflicts with current workflow state.",
    fixHint: "Refresh frontend state and retry with the latest resource version.",
  },
  API_EXT_001: {
    title: "API upstream failure",
    rootCause: "An API route dependency returned an error.",
    fixHint: "Inspect dependency health and route logs.",
  },
  API_TMO_001: {
    title: "API timeout",
    rootCause: "An API request timed out waiting for a dependency.",
    fixHint: "Retry or increase the dependency timeout.",
  },
  // F0 Intake
  F0_IN_001: {
    title: "Invalid F0 intake input",
    rootCause: "The intake source payload is missing required fields.",
    fixHint: "Validate ContentRecord source metadata before ingestion.",
  },
  F0_EXT_001: {
    title: "F0 source unavailable",
    rootCause: "An external intake source could not be reached.",
    fixHint: "Check source credentials, network, and adapter health.",
  },
  F0_AUTH_001: {
    title: "F0 source authentication failed",
    rootCause: "The intake adapter has expired or invalid credentials.",
    fixHint: "Refresh the source token or login session.",
  },
  F0_TMO_001: {
    title: "F0 intake timeout",
    rootCause: "Source ingestion exceeded its timeout.",
    fixHint: "Retry with pagination or inspect the external source latency.",
  },
  F0_INDEX_001: {
    title: "F0 index unavailable",
    rootCause: "The F0 SQLite index file does not exist or has not been loaded.",
    fixHint: "Run POST /api/f0-index/rebuild to create the index.",
  },
  F0_INDEX_002: {
    title: "F0 index query failed",
    rootCause: "A query against the F0 SQLite index failed unexpectedly.",
    fixHint: "Check index health via GET /api/f0-index/health. Rebuild if stale.",
  },
  F0_INDEX_003: {
    title: "F0 index rebuild failed",
    rootCause: "The F0 index rebuild process encountered an error.",
    fixHint: "Check server logs for details. Ensure manifest files are valid JSON.",
  },
  // F1 Standardize
  F1_IN_001: {
    title: "Invalid F1 input",
    rootCause: "F1 received an invalid ContentRecord or source artifact.",
    fixHint: "Ensure F0 output satisfies ContentRecord before standardization.",
  },
  F1_SCHEMA_001: {
    title: "F1 envelope schema invalid",
    rootCause: "ContentEnvelope or ContentBlock validation failed.",
    fixHint: "Fix the standardizer to emit canonical F1 schema fields.",
  },
  F1_PARSE_001: {
    title: "F1 text parse failed",
    rootCause: "The standardizer could not parse source text into canonical blocks.",
    fixHint: "Inspect raw text boundaries and parser assumptions.",
  },
  F1_PARSE_002: {
    title: "F1 media parse failed",
    rootCause: "OCR, ASR, or layout extraction produced unusable content.",
    fixHint: "Check media artifacts and perception service output.",
  },
  F1_TMO_001: {
    title: "F1 standardization timeout",
    rootCause: "Standardization exceeded its time budget.",
    fixHint: "Split large inputs or increase the F1 timeout.",
  },
  // F1.5 Topic Assembly
  F15_IN_001: {
    title: "Invalid F1.5 input",
    rootCause: "Topic assembly received invalid ContentBlock inputs.",
    fixHint: "Pass canonical F1 ContentEnvelope and ContentBlock ids.",
  },
  F15_SCHEMA_001: {
    title: "F1.5 topic schema invalid",
    rootCause: "TopicBlock or TopicAssemblyResult validation failed.",
    fixHint: "Fix topic assembly output to match schemas/topic_block.py.",
  },
  F15_TMO_001: {
    title: "F1.5 assembly timeout",
    rootCause: "Topic assembly exceeded its time budget.",
    fixHint: "Split input or reduce LLM proposal scope.",
  },
  // F2 Anchor
  F2_IN_001: {
    title: "Invalid F2 input",
    rootCause: "Anchor stage received invalid topic or evidence inputs.",
    fixHint: "Ensure F1.5 output satisfies TopicBlock before anchoring.",
  },
  F2_NTF_001: {
    title: "F2 entity not found",
    rootCause: "Entity resolution could not locate a required entity.",
    fixHint: "Add aliases to the entity registry or relax the resolver query.",
  },
  F2_EXT_001: {
    title: "F2 market data failed",
    rootCause: "Finance data or enrichment dependency failed.",
    fixHint: "Check finance-skills service health and symbol mapping.",
  },
  F2_TMO_001: {
    title: "F2 enrichment timeout",
    rootCause: "Anchor or enrichment work exceeded its time budget.",
    fixHint: "Cache finance lookups or reduce batch size.",
  },
  // F3 Intent
  F3_IN_001: {
    title: "Invalid F3 input",
    rootCause: "Intent extraction received invalid anchored content.",
    fixHint: "Pass anchored evidence from F2, not raw text.",
  },
  F3_SCHEMA_001: {
    title: "F3 intent schema invalid",
    rootCause: "NormalizedInvestmentIntent validation failed.",
    fixHint: "Fix intent extractor output and required ids.",
  },
  F3_PARSE_001: {
    title: "F3 intent parse failed",
    rootCause: "The extractor could not identify a valid investment intent.",
    fixHint: "Inspect evidence spans and extraction rules.",
  },
  F3_EXT_001: {
    title: "F3 LLM extraction failed",
    rootCause: "Intent extraction LLM dependency failed.",
    fixHint: "Check LLM provider health and structured output.",
  },
  F3_TMO_001: {
    title: "F3 extraction timeout",
    rootCause: "Intent extraction exceeded its time budget.",
    fixHint: "Reduce input size or split extraction batches.",
  },
  // F4 Policy
  F4_IN_001: {
    title: "Invalid F4 input",
    rootCause: "Policy mapping received invalid intent input.",
    fixHint: "Pass canonical NormalizedInvestmentIntent from F3.",
  },
  F4_POLICY_001: {
    title: "F4 policy rejected intent",
    rootCause: "The policy layer rejected a non-actionable or unsafe intent.",
    fixHint: "Inspect rejection_reason and policy rule metadata.",
  },
  F4_POLICY_002: {
    title: "F4 no matching policy",
    rootCause: "No policy rule could map the intent.",
    fixHint: "Add or adjust a policy rule for the intent type.",
  },
  F4_SCHEMA_001: {
    title: "F4 policy schema invalid",
    rootCause: "PolicyMappingResult or PolicyMappedIntent validation failed.",
    fixHint: "Fix policy mapper output and ids.",
  },
  // F5 Execute
  F5_IN_001: {
    title: "Invalid F5 input",
    rootCause: "Execution received invalid policy-mapped intent.",
    fixHint: "Pass PolicyMappingResult from F4, not raw text.",
  },
  F5_SCHEMA_001: {
    title: "F5 trade action schema invalid",
    rootCause: "TradeAction or ExecutionTiming validation failed.",
    fixHint: "Include intent_id, policy_id, evidence_span_ids, and four execution clocks.",
  },
  F5_POLICY_001: {
    title: "F5 policy guard failed",
    rootCause: "Execution attempted an action forbidden by policy.",
    fixHint: "Inspect policy guard result before constructing TradeAction.",
  },
  F5_TMO_001: {
    title: "F5 execution timeout",
    rootCause: "Trade action construction or execution exceeded timeout.",
    fixHint: "Retry with smaller batches or inspect dependency latency.",
  },
  // F6 Review
  F6_IN_001: {
    title: "Invalid F6 review input",
    rootCause: "Review or RLHF endpoint received invalid feedback input.",
    fixHint: "Validate review payload and required action ids.",
  },
  F6_NTF_001: {
    title: "F6 review item not found",
    rootCause: "The requested review item does not exist.",
    fixHint: "Check review id and reviewed data directory.",
  },
  F6_SCHEMA_001: {
    title: "F6 feedback schema invalid",
    rootCause: "RLHFFeedback validation failed.",
    fixHint: "Fix feedback payload fields and labels.",
  },
  // F7 Timeline
  F7_IN_001: {
    title: "Invalid F7 timeline input",
    rootCause: "Timeline engine received invalid KOL or action inputs.",
    fixHint: "Pass reviewed actions and valid KOL identifiers.",
  },
  F7_NTF_001: {
    title: "F7 timeline not found",
    rootCause: "The requested timeline or KOL state does not exist.",
    fixHint: "Check KOL id and timeline storage.",
  },
  F7_SCHEMA_001: {
    title: "F7 timeline schema invalid",
    rootCause: "KOLTimeline or ViewpointState validation failed.",
    fixHint: "Fix timeline schema output.",
  },
  // F8 Backtest
  F8_IN_001: {
    title: "Invalid F8 backtest input",
    rootCause: "Backtest received invalid action, period, or price inputs.",
    fixHint: "Validate action list, date range, and symbols.",
  },
  F8_NTF_001: {
    title: "F8 backtest not found",
    rootCause: "The requested backtest result does not exist.",
    fixHint: "Check backtest id and result storage.",
  },
  F8_EXT_001: {
    title: "F8 price data failed",
    rootCause: "Backtest price dependency failed.",
    fixHint: "Check data provider health and ticker availability.",
  },
  F8_TMO_001: {
    title: "F8 backtest timeout",
    rootCause: "Backtest computation exceeded timeout.",
    fixHint: "Reduce date range or cache price data.",
  },
  // LLM
  LLM_AUTH_001: {
    title: "LLM authentication failed",
    rootCause: "Provider rejected the configured API credential.",
    fixHint: "Refresh provider API key in environment configuration.",
  },
  LLM_EXT_001: {
    title: "LLM provider unavailable",
    rootCause: "The provider returned an unavailable or server error.",
    fixHint: "Retry with backoff and inspect provider status.",
  },
  LLM_EXT_002: {
    title: "LLM provider rate limited",
    rootCause: "The provider rejected the request due to quota or rate limits.",
    fixHint: "Retry after the provider's retry window or reduce concurrency.",
  },
  LLM_TMO_001: {
    title: "LLM request timeout",
    rootCause: "The provider did not respond before timeout.",
    fixHint: "Retry with a longer timeout or smaller prompt.",
  },
  LLM_SCHEMA_001: {
    title: "LLM structured output invalid",
    rootCause: "The provider response did not match the expected Pydantic model.",
    fixHint: "Inspect raw completion and tighten constrained decoding or validation.",
  },
  // WeChat
  WX_AUTH_001: {
    title: "WeChat authentication failed",
    rootCause: "WeChat session or cookie is invalid.",
    fixHint: "Refresh login session and exporter auth key.",
  },
  WX_EXT_001: {
    title: "WeChat exporter unavailable",
    rootCause: "wechat-article-exporter is not reachable or returned an error.",
    fixHint: "Start exporter and verify exporter_url.",
  },
  WX_TMO_001: {
    title: "WeChat exporter timeout",
    rootCause: "WeChat exporter request exceeded timeout.",
    fixHint: "Check exporter health and retry with a longer timeout.",
  },
  WX_NTF_001: {
    title: "WeChat resource not found",
    rootCause: "Requested WeChat session, account, or article was not found.",
    fixHint: "Check session_id, account_id, or article URL.",
  },
  // Bilibili
  BILI_IN_001: {
    title: "Invalid Bilibili input",
    rootCause: "Bilibili URL or BV id could not be parsed.",
    fixHint: "Provide a valid Bilibili URL or BV id.",
  },
  BILI_EXT_001: {
    title: "Bilibili upstream failed",
    rootCause: "Bilibili API, download, or transcription dependency failed.",
    fixHint: "Check upstream response and local media tooling.",
  },
  BILI_NTF_001: {
    title: "Bilibili resource not found",
    rootCause: "Requested Bilibili video or generated artifact was not found.",
    fixHint: "Verify BV id and artifact path.",
  },
  // Feishu
  FEISHU_AUTH_001: {
    title: "Feishu authentication failed",
    rootCause: "Feishu/Lark credentials or tenant access failed.",
    fixHint: "Refresh lark-cli auth and app scopes.",
  },
  FEISHU_EXT_001: {
    title: "Feishu upstream failed",
    rootCause: "Feishu/Lark API returned an error.",
    fixHint: "Inspect lark-cli output and API permissions.",
  },
  FEISHU_TMO_001: {
    title: "Feishu upstream timeout",
    rootCause: "Feishu/Lark API request timed out.",
    fixHint: "Retry or reduce requested data scope.",
  },
  // NLM
  NLM_EXT_001: {
    title: "NLM upstream failed",
    rootCause: "NLM notebook or document dependency returned an error.",
    fixHint: "Check NLM configuration and upstream status.",
  },
  NLM_TMO_001: {
    title: "NLM upstream timeout",
    rootCause: "NLM dependency exceeded timeout.",
    fixHint: "Retry with smaller scope or longer timeout.",
  },
};

// =============================================================================
// Workflow & Review Types
// =============================================================================

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

export type SourceType = "feishu" | "notebooklm" | "local" | "wechat" | "bilibili" | "unknown";

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

/** Backend KOL list item from GET /api/kol/list/enriched (snake_case). */
export type KOLListItemRaw = {
  id: string;
  name: string;
  platform: string;
  platform_id: string;
  overall_score: number;
  dimension_scores: Record<string, number>;
  accuracy: number;
  avg_return: number;
  total_opinions: number;
  last_active: string;
  tags: string[];
  enabled: boolean;
};

/** Backend KOL rating response (mirrors kol.py KOLRatingResponse). */
export type KOLRatingResponse = {
  rating: {
    kolId: string;
    name: string;
    platform: string;
    overallRating: number;
    avgReturn: number;
    successRate: number;
    totalOpinions: number;
  };
  dimensions: Array<{
    dimension: string;
    score: number;
    label: string;
  }>;
  timeline: Array<{
    date: string;
    rating: number;
    return_pct?: number;
  }>;
  focusAreas: string[];
  recentOpinions: Array<{
    id: string;
    ticker: string;
    ticker_name?: string;
    direction: string;
    timestamp: string;
    result?: string;
  }>;
};

/** KOL detail view type used by kol/[id]/page.tsx. */
export type KOLDetail = KOL & {
  stats: {
    totalOpinions: number;
    correctCount: number;
    avgReturn: number;
    maxReturn: number;
    minReturn: number;
    avgHoldingDays: number;
  };
  timeline: KOLTimelineEvent[];
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
  contentVersionId?: string;
  nameLineage?: NameLineage;
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

// =============================================================================
// F8 Backtest Result (mirrors src/finer/backtest/engine.py BacktestResult)
// =============================================================================

/** Daily portfolio state snapshot. */
export type PortfolioSnapshot = {
  date: string;
  cash: number;
  positions_value: number;
  total_value: number;
  daily_pnl: number;
  cumulative_pnl: number;
  cumulative_return: number;
  peak_value: number;
  current_drawdown: number;
  num_positions: number;
  long_exposure: number;
  short_exposure: number;
};

/** Completed trade record from backtest engine. */
export type TradeRecord = {
  trade_id: string;
  ticker: string;
  side: "long" | "short" | "flat";
  quantity: number;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  gross_pnl: number;
  commission: number;
  slippage: number;
  borrowing_cost: number;
  net_pnl: number;
  return_pct: number;
  exit_reason: string;
  holding_days: number;
  trade_action_id?: string;
  kol_id?: string;
};

/** Per-KOL performance attribution. */
export type KolMetrics = {
  total_trades: number;
  total_pnl: number;
  win_rate: number;
  avg_return: number;
};

/** Summary returned by GET /api/backtest/results (list endpoint). */
export type BacktestSummary = {
  backtest_id: string;
  kol_id: string | null;
  start_date: string;
  end_date: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  created_at: string;
  filepath?: string;
};

/** Complete backtest result from F8 engine. */
export type BacktestResult = {
  backtest_id: string;
  start_date: string;
  end_date: string;
  run_timestamp: string;
  initial_capital: number;
  config: Record<string, unknown>;

  // Performance metrics
  total_return: number;
  annualized_return: number;
  volatility: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown: number;
  max_drawdown_duration: number;

  // Trade statistics
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  avg_holding_days: number;

  // Risk metrics
  value_at_risk_95: number;
  expected_shortfall: number;
  max_consecutive_losses: number;

  // Time series data
  portfolio_snapshots: PortfolioSnapshot[];
  trades: TradeRecord[];

  // KOL attribution
  kol_metrics: Record<string, KolMetrics>;
};

export type SourceGroup = {
  id: string;
  name: string;
  type: "feishu" | "notebooklm" | "wechat" | "bilibili" | "local";
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

// =============================================================================
// WeChat Integration Types
// =============================================================================

export type WeChatLoginStatus =
  | "created"
  | "qr_ready"
  | "waiting_scan"
  | "scanned"
  | "confirmed"
  | "expired"
  | "failed";

export type WeChatLoginSession = {
  session_id: string;
  qr_data_uri: string;
  status: WeChatLoginStatus;
  expires_in: number;
};

export type WeChatAccount = {
  account_id: string;
  account_name: string;
  avatar_url?: string;
  last_sync?: string;
  article_count: number;
  is_valid: boolean;
};

export type WeChatArticle = {
  article_id: string;
  title: string;
  author?: string;
  digest?: string;
  publish_time?: string;
  content_url?: string;
  cover_url?: string;
  read_count: number;
  like_count: number;
  status: "pending" | "syncing" | "completed" | "failed";
};

export type WeChatSyncResult = {
  account_id: string;
  synced_count: number;
  failed_count: number;
  articles: string[];
  content_record_ids: string[];
  errors: string[];
  f0_triggered: boolean;
};

export type ExporterHealth = {
  available: boolean;
  url: string;
  latency_ms?: number;
  error?: string;
};

// =============================================================================
// Project Memory Storage v1 — Types (mirrors docs/specs/project-memory-storage-v1.md §10)
// =============================================================================

/** Project Memory metadata returned by /api/files and /api/system/diagnostics. */
export interface ProjectMemoryMeta {
  projectId: string;
  schemaVersion: string;
  dbPath: string;
  assetIndexUpdatedAt: string | null;
  degraded: boolean;
}

/** Structured name lineage for a content item across pipeline stages. */
export interface NameLineage {
  originalFilename?: string;
  f0DisplayName?: string;
  f1EnvelopeTitle?: string;
  splitFilename?: string;
  materializedFilename?: string;
}

/** Asset file with Project Memory lineage fields. */
export interface AssetFileWithLineage {
  id: string;
  contentId: string;
  contentVersionId: string;
  stage: string;
  name: string;
  sourceRecordId: string;
  sourceGroupId: string;
  latestArtifactId: string;
  manifestId: string;
  nameLineage: NameLineage;
}

/** Response shape for GET /api/files with Project Memory metadata. */
export interface FilesApiResponse {
  source: "catalog" | "degraded_scan";
  projectMemory?: ProjectMemoryMeta;
  files: AssetFileWithLineage[];
}

/** Response shape for GET /api/system/diagnostics. */
export interface SystemDiagnostics {
  projectMemory: {
    status: "healthy" | "degraded" | "missing" | "corrupt" | "schema_mismatch";
    projectId: string;
    schemaVersion: string;
    dbPath: string;
    contentCount: number;
    contentVersionCount: number;
    blockCount: number;
    topicBlockCount: number;
    objectCount: number;
    artifactCount: number;
    assetIndexCount: number;
    assetFtsCount: number;
    lastRebuildAt: string | null;
  };
}

// =============================================================================
// F0 Project Memory — Index Health & Query (mirrors src/finer/schemas/f0_index.py)
// =============================================================================

/** F0 index health status for Import Console display. */
export interface F0IndexHealth {
  status: "healthy" | "stale" | "missing" | "rebuilding";
  record_count: number;
  last_rebuild_at: string | null;
  last_rebuild_duration_ms: number | null;
  manifest_count_on_disk: number;
  drift: number;
  db_path: string;
  db_size_bytes: number;
  needs_rebuild: boolean;
}

/** F0 index query result. */
export interface F0IndexResult {
  records: F0ContentRecord[];
  total_count: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

/** Single content record from F0 index. */
export interface F0ContentRecord {
  content_id: string;
  source_type: string;
  source_platform: string;
  creator_id: string | null;
  creator_name: string | null;
  title: string | null;
  raw_path: string;
  file_type: string;
  published_at: string | null;
  collected_at: string;
  source_url: string | null;
  external_source_id: string | null;
  manifest_path: string | null;
  import_run_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Import run record (mirrors src/finer/schemas/f0_index.py import_runs table). */
export interface ImportRun {
  run_id: string;
  source_channel: string;
  started_at: string;
  finished_at: string | null;
  status: "pending" | "running" | "completed" | "failed";
  records_created: number;
  records_skipped: number;
  error_code: string | null;
  error_message: string | null;
  request_id: string | null;
  retryable: boolean;
  fix_hint: string | null;
}

// =============================================================================
// Annotation Workbench (mirrors src/finer/schemas/annotation.py)
// =============================================================================

/** Annotation task identifier. */
export type AnnotationTaskId = "eval_gold" | "pairs_review";
export type AnnotationExportMode = "formal" | "draft";
export type AnnotationItemStatus = "pending" | "annotated" | "excluded";
export type EvalSampleVerdict = "gold" | "exclude";

/** Single step in a gold action chain (mirrors GoldActionStep). */
export interface GoldActionStep {
  action_type: string;
  trigger_condition?: string | null;
  target_price_low?: number | null;
  target_price_high?: number | null;
}

/** Gold extraction answer for eval set (mirrors GoldExtraction). */
export interface GoldExtraction {
  ticker: string;
  direction: "bullish" | "bearish" | "neutral" | "watchlist" | "risk_warning";
  action_chain: GoldActionStep[];
  conviction?: number | null;
  rationale?: string | null;
}

/** Neighboring source message merged into evidence (mirrors ContextBlock). */
export interface ContextBlock {
  offset: number;
  timestamp?: string | null;
  content: string;
}

/** One eval-set annotation (mirrors EvalGoldAnnotation). */
export interface EvalGoldAnnotation {
  id: string;
  reviewer_id: string;
  annotation_schema_version: string;
  sample_verdict: EvalSampleVerdict;
  exclude_reason?: "image_placeholder" | "insufficient_context" | "non_investment" | "duplicate" | "other" | null;
  expected_abstain: boolean;
  gold?: GoldExtraction | null;
  alt_golds?: GoldExtraction[];
  context_blocks?: ContextBlock[];
  notes?: string | null;
  duration_ms?: number | null;
  annotated_at?: string;
}

/** One DPO pair review verdict (mirrors PairReviewAnnotation). */
export interface PairReviewAnnotation {
  pair_id: string;
  reviewer_id: string;
  annotation_schema_version: string;
  verdict: "accept" | "edit" | "reject";
  edited_chosen?: string | null;
  notes?: string | null;
  duration_ms?: number | null;
  annotated_at?: string;
}

export interface AnnotationQualityStatus {
  bad_source_lines: number;
  bad_annotation_lines: number;
  dangling_annotations: number;
  legacy_missing_reviewer: number;
  invalid_annotations: number;
  train_eval_overlap_ids: string[];
  image_placeholder_items: number;
  weak_signal_items: number;
  unexcluded_image_placeholder_items: number;
  unexcluded_weak_signal_items: number;
  incomplete_items: number;
  excluded_items: number;
  effective_gold_items: number;
  pair_sample_size?: number | null;
  pair_sample_reviewed?: number | null;
  manifest_path?: string | null;
  manifest?: Record<string, unknown> | null;
  formal_blocking_reasons: string[];
}

/** Task summary from GET /api/annotation/tasks (mirrors AnnotationTaskSummary). */
export interface AnnotationTaskSummary {
  task_id: AnnotationTaskId;
  title: string;
  source_path: string;
  annotations_path: string;
  export_path: string;
  ready: boolean;
  total: number;
  annotated: number;
  fix_hint?: string | null;
  quality: AnnotationQualityStatus;
}

/** Eval item from GET /api/annotation/items?task_id=eval_gold. */
export interface EvalAnnotationItem {
  id: string;
  evidence_text: string;
  creator?: string | null;
  source_file?: string | null;
  timestamp?: string | null;
  signals?: {
    has_direction?: boolean;
    has_price?: boolean;
    has_ticker?: boolean;
    horizon_hint?: string;
    signal_score?: number;
  } | null;
  char_len?: number | null;
  status: AnnotationItemStatus;
  annotation?: EvalGoldAnnotation | null;
  /** 模型初稿（run_inference 对 passages 的输出 JSON 串），仅标注辅助。 */
  draft?: string | null;
}

/** Pair item from GET /api/annotation/items?task_id=pairs_review. */
export interface PairReviewItem {
  pair_id: string;
  evidence_text: string;
  chosen: string;
  rejected: string;
  creator?: string | null;
  source_file?: string | null;
  status: AnnotationItemStatus;
  annotation?: PairReviewAnnotation | null;
}

/** Result of POST /api/annotation/export. */
export interface AnnotationExportResult {
  export_path: string;
  exported: number;
  excluded?: number;
  mode?: AnnotationExportMode;
  sample_size?: number;
  expected_abstain_count?: number;
  train_eval_overlap_ids?: string[];
  accept?: number;
  edit?: number;
  reject?: number;
  unreviewed?: number;
}

export interface AnnotationEnums {
  annotation_schema_version: string;
  directions: GoldExtraction["direction"][];
  action_types: string[];
  eval_exclude_reasons: NonNullable<EvalGoldAnnotation["exclude_reason"]>[];
  pair_sample_size: number;
  pair_sample_seed: number;
  entity_aliases: Record<string, { ticker: string; market: string }>;
}

/** One block from GET /api/annotation/context. */
export interface ContextResponseBlock {
  position: "before" | "self" | "after";
  offset: number;
  timestamp?: string | null;
  content: string;
}

/** Response data of GET /api/annotation/context. */
export interface ContextResponse {
  item_id: string;
  source_file: string;
  block_index: number;
  total_blocks: number;
  blocks: ContextResponseBlock[];
}

/** One daily bar in the market window. */
export interface MarketBar {
  trade_date: string;
  close: number;
  pct_chg?: number | null;
}

/** Response data of GET /api/annotation/market. */
export interface MarketWindowResult {
  ticker: string;
  ts_code?: string;
  name?: string | null;
  coverage: "local" | "unsupported_market" | "unknown_ticker" | "no_local_data";
  market?: string | null;
  hint?: string;
  anchor_date?: string;
  anchor_close?: number;
  anchor_pct_chg?: number | null;
  window?: MarketBar[];
}

// =============================================================================
// F3 Intent Schema Types (mirrors src/finer/schemas/investment_intent.py)
// =============================================================================

export type IntentTargetType =
  | "stock"
  | "sector"
  | "index"
  | "macro"
  | "commodity"
  | "crypto"
  | "unknown";

export type IntentDirection = "bullish" | "bearish" | "neutral" | "mixed" | "unknown";

export type IntentActionability =
  | "opinion" //          纯观点，无行动意图
  | "watch" //            观察名单，待机
  | "explicit_action" //  明确的行动指令
  | "review_required"; // 需人工审核

export type PositionDeltaHint =
  | "open"
  | "add"
  | "reduce"
  | "hold"
  | "exit"
  | "none"
  | "unknown";

export type IntentRiskPreference =
  | "aggressive"
  | "balanced"
  | "conservative"
  | "unknown";

export type IntentTimeHorizon =
  | "intraday"
  | "short_term"
  | "medium_term"
  | "long_term"
  | "unknown";

/** F3 normalized investment intent (mirrors NormalizedInvestmentIntent). */
export type NormalizedInvestmentIntent = {
  intent_id: string;
  schema_version: string;
  envelope_id: string;
  block_ids: string[];
  creator_id?: string;
  target_type: IntentTargetType;
  target_name: string;
  target_symbol?: string;
  market?: string;
  direction: IntentDirection;
  actionability: IntentActionability;
  position_delta_hint: PositionDeltaHint;
  conviction: number; //       0..1
  sentiment_score?: number; // -1..1
  risk_preference_hint: IntentRiskPreference;
  time_horizon_hint: IntentTimeHorizon;
  temporal_anchor_ids: string[];
  evidence_span_ids: string[];
  ambiguity_flags: string[];
  confidence: number; //       0..1
  metadata: Record<string, unknown>;
  created_at: string;
};

// =============================================================================
// F2 Evidence Schema Types (mirrors src/finer/schemas/evidence.py)
// =============================================================================

/** F2 evidence span anchoring a claim to source text. */
export type EvidenceSpan = {
  schema_version: string;
  evidence_span_id: string;
  block_id: string;
  char_start: number;
  char_end: number;
  text: string;
  confidence: number; // 0..1
  span_type?: string;
  metadata: Record<string, unknown>;
};

// =============================================================================
// F5 TradeAction Schema Types (mirrors src/finer/schemas/trade_action.py)
// Subset relevant to the audit view; the full Pydantic model also carries
// enrichment / backtest_result / rlhf_feedback / lineage / version_info.
// =============================================================================

export type TradeDirection =
  | "bullish"
  | "bearish"
  | "neutral"
  | "watchlist"
  | "risk_warning";

export type ActionType =
  | "long"
  | "short"
  | "close_long"
  | "close_short"
  | "buy_call"
  | "sell_call"
  | "buy_put"
  | "sell_put"
  | "hold"
  | "watch"
  | "buy_and_hold";

export type TriggerType =
  | "price_threshold"
  | "breakout"
  | "support_resistance"
  | "indicator_signal"
  | "time_based"
  | "news_event"
  | "manual";

export type TradeValidationStatus = "pending" | "verified" | "failed" | "under_review";

export type ExitReason =
  | "target_reached"
  | "stop_loss"
  | "time_exit"
  | "signal_reversal"
  | "manual"
  | "unknown";

export type MarketSession =
  | "pre_market"
  | "regular"
  | "after_close"
  | "non_trading_day"
  | "unknown";

export type InstrumentType =
  | "stock"
  | "option"
  | "etf"
  | "index_future"
  | "crypto"
  | "unspecified";

export type SourceInfo = {
  creator_id?: string;
  content_id: string;
  evidence_text: string;
  evidence_start_idx?: number;
  evidence_end_idx?: number;
  content_url?: string;
};

export type TargetInfo = {
  ticker: string;
  ticker_normalized?: string;
  market?: string;
  instrument_type: InstrumentType;
  company_name?: string;
};

export type ActionStep = {
  sequence: number;
  action_type: ActionType;
  trigger_condition?: string;
  trigger_type: TriggerType;
  target_price_low?: number | null;
  target_price_high?: number | null;
  position_size_pct?: number | null;
  notes?: string;
};

/** F5 four-clock execution timing (mirrors ExecutionTiming). */
export type ExecutionTiming = {
  intent_published_at: string;
  intent_effective_at?: string;
  action_decision_at: string;
  action_executable_at: string;
  market: string;
  timezone: string;
  market_session_at_publish: MarketSession;
  execution_delay_reason?: string;
  timing_policy_id: string;
};

/** F5 trade action (audit subset of the full Pydantic TradeAction). */
export type TradeAction = {
  trade_action_id: string;
  timestamp: string;
  source: SourceInfo;
  target: TargetInfo;
  direction: TradeDirection;
  action_chain: ActionStep[];
  intent_id?: string;
  policy_id?: string;
  evidence_span_ids: string[];
  effective_trade_at?: string;
  canonical_trace_status: CanonicalTraceStatus;
  execution_timing?: ExecutionTiming;
  confidence: number; // 0..1
  model_version: string;
  extraction_method: string;
  validation_status: TradeValidationStatus;
  time_horizon?: string;
  rationale?: string;
  tags: string[];
};

// =============================================================================
// Audit Trace Bundle — frontend aggregate for /audit
// See docs/specs/2026-06-04-dashboard-audit-trace-frontend.md §6
// =============================================================================

/** Minimal F1/F0 source context needed for audit highlighting. */
export type EnvelopeContext = {
  envelope_id: string;
  source_text: string;
  source_published_at?: string;
  creator_id?: string;
  kol_id?: string;
};

/** Compact TradeAction row for the audit list (left rail). */
export type TradeActionSummary = {
  trade_action_id: string;
  ticker: string;
  company_name?: string;
  direction: TradeDirection;
  summary: string;
  canonical_trace_status: CanonicalTraceStatus;
  validation_status: TradeValidationStatus;
  kol_id?: string;
  created_at: string;
  backtest_return_pct?: number;
};

/** Full F0→F5 chain for one TradeAction, returned by the audit trace API. */
export type AuditTraceBundle = {
  trade_action: TradeAction;
  intent: NormalizedInvestmentIntent | null; //  null = chain broken at F3
  policy: PolicyMappingResult | null; //         null = chain broken at F4
  evidence_spans: EvidenceSpan[]; //             F2
  envelope: EnvelopeContext; //                  F1/F0 source
};
