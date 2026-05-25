import type {
  StageMetrics,
  BottleneckMetric,
  ActiveRun,
  HumanQueueItem,
  AssetFile,
  ReviewPayload,
  TextEvidenceBinding,
  ImageEvidenceBinding,
  AudioVideoEvidenceBinding,
  PdfEvidenceBinding,
  SchemaEvidenceBinding,
} from "@/lib/contracts";

// =============================================================================
// Pipeline Operations Mock (Agent 2)
// =============================================================================

export const MOCK_STAGE_METRICS: StageMetrics[] = [
  { stageId: "F0", queued: 120, running: 15, failed: 2, blocked: 0, throughputToday: 3400 },
  { stageId: "F1", queued: 45, running: 8, failed: 5, blocked: 0, throughputToday: 3200 },
  { stageId: "F1.5", queued: 12, running: 3, failed: 0, blocked: 0, throughputToday: 1500 },
  { stageId: "F2", queued: 8, running: 5, failed: 1, blocked: 0, throughputToday: 1400 },
  { stageId: "F3", queued: 1200, running: 45, failed: 22, blocked: 0, throughputToday: 800 },
  { stageId: "F4", queued: 0, running: 2, failed: 0, blocked: 0, throughputToday: 750 },
  { stageId: "F5", queued: 0, running: 1, failed: 12, blocked: 0, throughputToday: 700 },
  { stageId: "F6", queued: 0, running: 0, failed: 0, blocked: 34, throughputToday: 400 },
  { stageId: "F7", queued: 5, running: 2, failed: 0, blocked: 0, throughputToday: 380 },
  { stageId: "F8", queued: 2, running: 1, failed: 0, blocked: 0, throughputToday: 150 },
];

export const MOCK_BOTTLENECK_METRIC: BottleneckMetric = {
  maxBacklogStage: "F3",
  backlogCount: 1200,
  highestFailureStage: "F5",
  failureRate: 0.15,
  longestWaitP99Ms: 1200000,
};

export const MOCK_ACTIVE_RUNS: ActiveRun[] = [
  {
    jobId: "job-f3-8821a",
    stage: "F3",
    status: "running",
    durationMs: 45000,
    inputAssetId: "asset-1092",
    actions: ["Terminate"],
  },
  {
    jobId: "job-f5-9921b",
    stage: "F5",
    status: "failed",
    durationMs: 2300,
    inputAssetId: "asset-1055",
    error: { code: "F5_POLICY_001", message: "Execution attempted an action forbidden by policy." },
    actions: ["View Logs", "Retry"],
  },
  {
    jobId: "job-f0-7712c",
    stage: "F0",
    status: "queued",
    durationMs: 120000,
    inputAssetId: "source-wechat-x",
    actions: ["Cancel"],
  },
];

export const MOCK_HUMAN_QUEUE: HumanQueueItem[] = [
  {
    taskId: "task-rev-001",
    stage: "F6",
    reason: "Awaiting approval for trade action (Confidence < 0.8)",
    evidenceLinks: ["asset-1022", "asset-1023"],
    requestedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
  },
  {
    taskId: "task-rev-002",
    stage: "F6",
    reason: "Conflict detected in target price extraction",
    evidenceLinks: ["asset-1088"],
    requestedAt: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  },
];

// =============================================================================
// Evidence Binding Mocks (Agent 3/4)
// =============================================================================

export const MOCK_TEXT_EVIDENCE: TextEvidenceBinding = {
  id: "ev-text-001",
  evidenceId: "F3-asset-1092",
  sourceAssetId: "asset-1092",
  provenancePath: "F0/wechat/F1/standardize/F1.5/assemble/F2/anchor/F3",
  confidence: 0.87,
  extractedContent:
    "贵州茅台Q3营收同比增长16.2%，直营占比持续提升至40%以上。管理层在电话会议中明确表态明年不会下调出厂价，批价稳定性预期增强。",
  createdBy: "model",
  modality: "text",
  highlightRange: { start: 0, end: 72 },
};

export const MOCK_IMAGE_EVIDENCE: ImageEvidenceBinding = {
  id: "ev-img-001",
  evidenceId: "F3-asset-1093",
  sourceAssetId: "asset-1093",
  provenancePath: "F0/bilibili/F1/perceive/F1.5/assemble/F2/anchor/F3",
  confidence: 0.72,
  extractedContent: "K线图显示茅台日线在1700附近形成双底结构，MACD金叉确认。",
  createdBy: "model",
  modality: "image",
  boundingBox: { x: 120, y: 80, w: 640, h: 360 },
};

export const MOCK_AV_EVIDENCE: AudioVideoEvidenceBinding = {
  id: "ev-av-001",
  evidenceId: "F3-asset-1094",
  sourceAssetId: "asset-1094",
  provenancePath: "F0/bilibili/F1/perceive/F1.5/assemble/F2/anchor/F3",
  confidence: 0.65,
  extractedContent:
    "[01:23-02:15] 博主提到：'茅台直营比例如果继续提高，对经销商体系的冲击是不可逆的，但利润端会更好看。'",
  createdBy: "model",
  modality: "audio",
  timestampRange: { startMs: 83000, endMs: 135000 },
};

export const MOCK_PDF_EVIDENCE: PdfEvidenceBinding = {
  id: "ev-pdf-001",
  evidenceId: "F3-asset-1095",
  sourceAssetId: "asset-1095",
  provenancePath: "F0/feishu/F1/standardize/F1.5/assemble/F2/anchor/F3",
  confidence: 0.91,
  extractedContent: "券商研报第12页：目标价上调至2100元，维持'买入'评级。核心逻辑：直营放量+批价企稳。",
  createdBy: "model",
  modality: "pdf",
  pageRange: { start: 11, end: 13 },
  boundingBox: { x: 60, y: 200, w: 480, h: 120, page: 12 },
};

export const MOCK_SCHEMA_EVIDENCE: SchemaEvidenceBinding = {
  id: "ev-schema-001",
  evidenceId: "F3-asset-1096",
  sourceAssetId: "asset-1096",
  provenancePath: "F0/feishu/F1/standardize/F1.5/assemble/F2/anchor/F3",
  confidence: 0.95,
  extractedContent: '{"ticker": "600519.SH", "direction": "bullish", "target_price": 2100}',
  createdBy: "model",
  modality: "schema",
  jsonPath: "$.investment_intent.target_price",
};

// =============================================================================
// Review Payload Mock (Agent 3)
// =============================================================================

export const MOCK_REVIEW_PAYLOAD: ReviewPayload = {
  ticker: "600519.SH",
  direction: "bullish",
  timeHorizon: "weekly",
  rationale:
    "茅台直营占比持续提升带来利润率改善预期，叠加批价企稳信号明确。多源证据方向一致，置信度较高。",
  evidenceBindings: [
    MOCK_TEXT_EVIDENCE,
    MOCK_IMAGE_EVIDENCE,
    MOCK_AV_EVIDENCE,
    MOCK_PDF_EVIDENCE,
    MOCK_SCHEMA_EVIDENCE,
  ],
  decisionStatus: "draft",
  confidence: 0.82,
  tags: ["白酒", "消费", "核心资产", "直营放量"],
  ambiguityNotes: [
    "研报目标价2100与当前价差约24%，但研报发布日期距今已3周，需确认时效性。",
    "视频KOL的持仓信息未知，无法判断是否存在利益冲突。",
  ],
  actionChain: [
    {
      id: "action-mock-1",
      actionType: "long",
      instrumentType: "stock",
      triggerCondition: "股价回踩1680支撑位且放量企稳",
      targetPriceLow: "1680",
      targetPriceHigh: "2100",
      confidence: 0.82,
      status: "active",
    },
    {
      id: "action-mock-2",
      actionType: "watch",
      instrumentType: "stock",
      triggerCondition: "若跌破1600则观望等待二次确认",
      targetPriceLow: "1550",
      targetPriceHigh: "1600",
      confidence: 0.45,
      status: "draft",
    },
  ],
};

// =============================================================================
// Asset File Mocks (shared by Agent 2/3/4)
// =============================================================================

export const MOCK_REVIEW_ASSETS: AssetFile[] = [
  {
    id: "asset-1092",
    name: "茅台Q3财报分析-微信长文",
    size: "24KB",
    date: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    type: "article",
    status: "processed",
    pipelineStage: "F6",
    stageBadge: "F6",
    creatorName: "白酒研究所",
    sourcePlatform: "wechat",
    contentType: "long_article",
    contentId: "content-1092",
    summary: "贵州茅台Q3营收同比+16.2%，直营占比突破40%。",
    tags: ["白酒", "茅台", "Q3财报"],
    sourceType: "wechat",
    sourceGroupId: "group-wechat-baijiu",
    sourceGroupName: "白酒研究所公众号",
    fileType: "长文",
    sourceName: "白酒研究所",
    semanticTitle: "茅台Q3：直营放量驱动利润率上行",
    reviewPayload: MOCK_REVIEW_PAYLOAD,
  },
  {
    id: "asset-1093",
    name: "茅台技术面分析-B站视频",
    size: "156MB",
    date: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
    type: "video",
    status: "processed",
    pipelineStage: "F6",
    stageBadge: "F6",
    creatorName: "缠论小王子",
    sourcePlatform: "bilibili",
    contentType: "video_analysis",
    contentId: "content-1093",
    summary: "B站UP主从技术面分析茅台日线形态，1700附近双底结构。",
    tags: ["茅台", "技术分析", "缠论"],
    sourceType: "bilibili",
    fileType: "视频",
    sourceName: "bilibili/缠论小王子",
    semanticTitle: "茅台日线双底确认，目标2000+",
    reviewPayload: {
      ticker: "600519.SH",
      direction: "bullish",
      timeHorizon: "daily",
      rationale: "技术面双底结构+MACD金叉，短线看多至2000。",
      evidenceBindings: [MOCK_IMAGE_EVIDENCE, MOCK_AV_EVIDENCE],
      decisionStatus: "draft",
      confidence: 0.65,
      tags: ["技术分析", "短线"],
      ambiguityNotes: ["纯技术面分析，未考虑基本面变化。"],
      actionChain: [
        {
          id: "action-mock-3",
          actionType: "long",
          instrumentType: "stock",
          triggerCondition: "突破1750颈线位",
          targetPriceLow: "1700",
          targetPriceHigh: "2000",
          confidence: 0.65,
          status: "draft",
        },
      ],
    },
  },
  {
    id: "asset-1094",
    name: "茅台渠道调研纪要-飞书文档",
    size: "180KB",
    date: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(),
    type: "document",
    status: "processed",
    pipelineStage: "F6",
    stageBadge: "F6",
    creatorName: "渠道调研组",
    sourcePlatform: "feishu",
    contentType: "research_note",
    contentId: "content-1094",
    summary: "经销商反馈批价稳定在1680-1700区间，直营店配额增加20%。",
    tags: ["茅台", "渠道调研", "纪要"],
    sourceType: "feishu",
    fileType: "文档",
    sourceName: "飞书/投研群",
    semanticTitle: "茅台渠道纪要：批价稳、直营量增",
    reviewPayload: {
      ticker: "600519.SH",
      direction: "bullish",
      timeHorizon: "medium_term",
      rationale: "渠道调研确认批价企稳+直营放量，与财报数据交叉验证。",
      evidenceBindings: [MOCK_TEXT_EVIDENCE, MOCK_PDF_EVIDENCE, MOCK_SCHEMA_EVIDENCE],
      decisionStatus: "draft",
      confidence: 0.9,
      tags: ["渠道调研", "一手信息"],
      ambiguityNotes: ["调研样本有限（3家经销商），需扩大验证范围。"],
      actionChain: [
        {
          id: "action-mock-4",
          actionType: "add_position",
          instrumentType: "stock",
          triggerCondition: "当前价位附近直接建仓",
          targetPriceLow: "1680",
          targetPriceHigh: "1750",
          confidence: 0.9,
          status: "active",
        },
      ],
    },
  },
];
