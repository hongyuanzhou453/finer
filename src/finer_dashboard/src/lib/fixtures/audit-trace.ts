/**
 * Audit trace fixtures for the /audit view.
 *
 * 演示数据（sample data only）。所有 persona 为虚构化名，标的、价位、收益、
 * 评分均为示例，不构成投资建议；字段名/类型对齐 src/finer/schemas/ 真实模型。
 *
 * 覆盖三种 canonical_trace_status：
 *   - canonical     完整 F3→F4→F5 链路（贵州茅台 600519）
 *   - partial       缺 F4 Policy（五粮液 000858）
 *   - non_canonical legacy 直提，无 F3/F4/F2 证据链（宁德时代 300750）
 *
 * 每条 EvidenceSpan.text 均为对应 envelope.source_text 的真实子串，
 * 以保证证据高亮可在前端定位（offset 不精确时由组件 indexOf 兜底）。
 */
import type { AuditTraceBundle, TradeActionSummary } from "@/lib/contracts";

// --- source texts ------------------------------------------------------------

const SOURCE_MT =
  "今天聊聊茅台 600519。这波回调到 1480 附近其实是黄金坑，基本面没变，批价企稳，节前旺季还没反映到股价里。我自己已经在 1480-1500 这个区间分批建仓了，仓位三成。如果跌破 1450 我会止损，目标看回 1650。不构成投资建议。";

const SOURCE_WLY =
  "五粮液 000858 现在的估值已经到了历史低位区间，动态市盈率不到 18 倍，分红率也有 3% 多。我长期看好高端白酒的护城河，这个位置可以慢慢收集，拿个两三年问题不大。短期波动不用太在意。";

const SOURCE_CATL =
  "宁德时代 300750 这波冲高有点猛，量能跟不上，MACD 出现顶背离。我先把手里的仓位减一半锁定利润，剩下的设个移动止盈。追高的朋友要小心回踩。";

// --- bundle 1: canonical (贵州茅台 600519) -----------------------------------

const BUNDLE_CANONICAL: AuditTraceBundle = {
  trade_action: {
    trade_action_id: "ta-mt-600519-01",
    timestamp: "2026-05-20T21:34:00+08:00",
    source: {
      creator_id: "trader_ji",
      content_id: "fs-doc-mt-0520",
      evidence_text: "我自己已经在 1480-1500 这个区间分批建仓了，仓位三成",
      evidence_start_idx: 50,
      evidence_end_idx: 75,
    },
    target: {
      ticker: "600519",
      ticker_normalized: "600519",
      market: "CN",
      instrument_type: "stock",
      company_name: "贵州茅台",
    },
    direction: "bullish",
    action_chain: [
      {
        sequence: 1,
        action_type: "long",
        trigger_condition: "回调至 1480-1500 区间分批建仓",
        trigger_type: "price_threshold",
        target_price_low: 1480,
        target_price_high: 1500,
        position_size_pct: 0.3,
        notes: "分批建仓，合计约三成仓位",
      },
      {
        sequence: 2,
        action_type: "close_long",
        trigger_condition: "跌破 1450 止损",
        trigger_type: "price_threshold",
        target_price_high: 1450,
        notes: "破位止损，保护本金",
      },
    ],
    intent_id: "int-mt-600519-01",
    policy_id: "pol-mt-600519-01",
    evidence_span_ids: ["es-mt-1", "es-mt-2", "es-mt-3"],
    effective_trade_at: "2026-05-21T09:30:00+08:00",
    canonical_trace_status: "canonical",
    execution_timing: {
      intent_published_at: "2026-05-20T21:30:00+08:00",
      intent_effective_at: "2026-05-21T09:30:00+08:00",
      action_decision_at: "2026-05-20T21:34:00+08:00",
      action_executable_at: "2026-05-21T09:30:00+08:00",
      market: "CN",
      timezone: "Asia/Shanghai",
      market_session_at_publish: "after_close",
      execution_delay_reason: "发布于收盘后，按次日开盘价成交以避免前视偏差",
      timing_policy_id: "next_open_fill_v1",
    },
    confidence: 0.85,
    model_version: "canonical-programmatic",
    extraction_method: "f3f4f5_canonical",
    validation_status: "verified",
    time_horizon: "short_term",
    rationale: "回调黄金坑 + 节前旺季预期，自带止损，风险可控。",
    tags: ["白酒", "消费", "短线"],
  },
  intent: {
    intent_id: "int-mt-600519-01",
    schema_version: "1.0",
    envelope_id: "env-mt-600519",
    block_ids: ["blk-mt-001", "blk-mt-002"],
    creator_id: "trader_ji",
    target_type: "stock",
    target_name: "贵州茅台",
    target_symbol: "600519",
    market: "CN",
    direction: "bullish",
    actionability: "explicit_action",
    position_delta_hint: "open",
    conviction: 0.82,
    sentiment_score: 0.6,
    risk_preference_hint: "balanced",
    time_horizon_hint: "short_term",
    temporal_anchor_ids: ["ta-mt-01"],
    evidence_span_ids: ["es-mt-1", "es-mt-2", "es-mt-3"],
    ambiguity_flags: [],
    confidence: 0.85,
    metadata: {},
    created_at: "2026-05-20T21:32:00+08:00",
  },
  policy: {
    policy_id: "pol-mt-600519-01",
    intent_id: "int-mt-600519-01",
    creator_id: "trader_ji",
    kol_id: "trader_ji",
    policy_version: "1.0",
    policy_layers_applied: ["global_base"],
    action_hint: "open_position",
    position_sizing_hint: "medium",
    holding_period_hint: "short_term",
    risk_constraints: {
      max_position_hint: "medium",
      requires_human_review: false,
      risk_notes: ["单一标的集中度建议 ≤ 30%", "已设止损位 1450"],
      max_concentration_pct: 30,
      stop_loss_hint: "1450",
      metadata: {},
    },
    mapping_rationale: "明确看多且自带止损 → 映射为 open_position，中等仓位，短线持有。",
    layer_traces: [
      {
        layer_name: "GlobalBasePolicy",
        layer_version: "1.0",
        applied: true,
        reason: "默认基础策略，对所有 Intent 生效。",
        modifications: ["将仓位提示按基础风险上限收敛为 medium"],
        order_index: 0,
        metadata: {},
      },
      {
        layer_name: "StyleArchetypePolicy",
        layer_version: "0.0",
        applied: false,
        reason: "KOL 风格层尚未实现，跳过。",
        modifications: [],
        order_index: 1,
        metadata: {},
      },
    ],
    decisions: [
      {
        decision_id: "dec-mt-01",
        policy_id: "pol-mt-600519-01",
        layer: "global_base",
        decision_type: "sizing_adjust",
        description: "仓位「三成」映射为 medium",
        rationale: "缺少 KOL 风格层时，基础策略将单一标的仓位上限设为 medium。",
        overrides_previous: false,
        metadata: {},
      },
      {
        decision_id: "dec-mt-02",
        policy_id: "pol-mt-600519-01",
        layer: "global_base",
        decision_type: "risk_bound",
        description: "采纳原文止损位 1450 作为风险下界",
        rationale: "原文显式给出止损条件，策略保留并作为 risk_constraint。",
        overrides_previous: false,
        metadata: {},
      },
    ],
    confidence: 0.83,
    original_intent_confidence: 0.85,
    created_at: "2026-05-20T21:33:00+08:00",
    metadata: {},
  },
  evidence_spans: [
    {
      schema_version: "1.0",
      evidence_span_id: "es-mt-1",
      block_id: "blk-mt-001",
      char_start: 14,
      char_end: 31,
      text: "这波回调到 1480 附近其实是黄金坑",
      confidence: 0.88,
      span_type: "rationale",
      metadata: {},
    },
    {
      schema_version: "1.0",
      evidence_span_id: "es-mt-2",
      block_id: "blk-mt-002",
      char_start: 50,
      char_end: 75,
      text: "我自己已经在 1480-1500 这个区间分批建仓了，仓位三成",
      confidence: 0.92,
      span_type: "action",
      metadata: {},
    },
    {
      schema_version: "1.0",
      evidence_span_id: "es-mt-3",
      block_id: "blk-mt-002",
      char_start: 76,
      char_end: 95,
      text: "如果跌破 1450 我会止损，目标看回 1650",
      confidence: 0.9,
      span_type: "risk_management",
      metadata: {},
    },
  ],
  envelope: {
    envelope_id: "env-mt-600519",
    source_text: SOURCE_MT,
    source_published_at: "2026-05-20T21:30:00+08:00",
    creator_id: "trader_ji",
    kol_id: "trader_ji",
  },
};

// --- bundle 2: partial — 缺 F4 Policy (五粮液 000858) -------------------------

const BUNDLE_PARTIAL: AuditTraceBundle = {
  trade_action: {
    trade_action_id: "ta-wly-000858-01",
    timestamp: "2026-05-22T10:06:00+08:00",
    source: {
      creator_id: "value_laozhang",
      content_id: "fs-doc-wly-0522",
      evidence_text: "这个位置可以慢慢收集，拿个两三年问题不大",
    },
    target: {
      ticker: "000858",
      ticker_normalized: "000858",
      market: "CN",
      instrument_type: "stock",
      company_name: "五粮液",
    },
    direction: "bullish",
    action_chain: [
      {
        sequence: 1,
        action_type: "buy_and_hold",
        trigger_condition: "估值处于历史低位区间",
        trigger_type: "indicator_signal",
        notes: "分批慢慢收集，长期持有",
      },
    ],
    intent_id: "int-wly-000858-01",
    evidence_span_ids: ["es-wly-1", "es-wly-2"],
    canonical_trace_status: "partial",
    execution_timing: {
      intent_published_at: "2026-05-22T10:00:00+08:00",
      action_decision_at: "2026-05-22T10:06:00+08:00",
      action_executable_at: "2026-05-22T13:00:00+08:00",
      market: "CN",
      timezone: "Asia/Shanghai",
      market_session_at_publish: "regular",
      timing_policy_id: "next_session_fill_v1",
    },
    confidence: 0.74,
    model_version: "canonical-programmatic",
    extraction_method: "f3f5_no_policy",
    validation_status: "under_review",
    time_horizon: "long_term",
    rationale: "低估值 + 长期护城河逻辑；缺少 F4 Policy 层，仓位与风险约束未确定。",
    tags: ["白酒", "价值", "长线"],
  },
  intent: {
    intent_id: "int-wly-000858-01",
    schema_version: "1.0",
    envelope_id: "env-wly-000858",
    block_ids: ["blk-wly-001"],
    creator_id: "value_laozhang",
    target_type: "stock",
    target_name: "五粮液",
    target_symbol: "000858",
    market: "CN",
    direction: "bullish",
    actionability: "explicit_action",
    position_delta_hint: "open",
    conviction: 0.7,
    sentiment_score: 0.5,
    risk_preference_hint: "conservative",
    time_horizon_hint: "long_term",
    temporal_anchor_ids: [],
    evidence_span_ids: ["es-wly-1", "es-wly-2"],
    ambiguity_flags: ["未给出明确建仓价位区间"],
    confidence: 0.78,
    metadata: {},
    created_at: "2026-05-22T10:05:00+08:00",
  },
  policy: null,
  evidence_spans: [
    {
      schema_version: "1.0",
      evidence_span_id: "es-wly-1",
      block_id: "blk-wly-001",
      char_start: 14,
      char_end: 36,
      text: "估值已经到了历史低位区间，动态市盈率不到 18 倍",
      confidence: 0.85,
      span_type: "rationale",
      metadata: {},
    },
    {
      schema_version: "1.0",
      evidence_span_id: "es-wly-2",
      block_id: "blk-wly-001",
      char_start: 60,
      char_end: 79,
      text: "这个位置可以慢慢收集，拿个两三年问题不大",
      confidence: 0.8,
      span_type: "action",
      metadata: {},
    },
  ],
  envelope: {
    envelope_id: "env-wly-000858",
    source_text: SOURCE_WLY,
    source_published_at: "2026-05-22T10:00:00+08:00",
    creator_id: "value_laozhang",
    kol_id: "value_laozhang",
  },
};

// --- bundle 3: non_canonical — legacy 直提 (宁德时代 300750) ------------------

const BUNDLE_NON_CANONICAL: AuditTraceBundle = {
  trade_action: {
    trade_action_id: "ta-catl-300750-01",
    timestamp: "2026-05-19T14:20:00+08:00",
    source: {
      creator_id: "trend_hunter_k",
      content_id: "bili-vid-catl-0519",
      evidence_text: "我先把手里的仓位减一半锁定利润，剩下的设个移动止盈",
    },
    target: {
      ticker: "300750",
      ticker_normalized: "300750",
      market: "CN",
      instrument_type: "stock",
      company_name: "宁德时代",
    },
    direction: "bearish",
    action_chain: [
      {
        sequence: 1,
        action_type: "close_long",
        trigger_condition: "MACD 顶背离 + 量能不足",
        trigger_type: "indicator_signal",
        position_size_pct: 0.5,
        notes: "减仓一半，锁定利润",
      },
    ],
    evidence_span_ids: [],
    canonical_trace_status: "non_canonical",
    confidence: 0.6,
    model_version: "legacy-extractor-v2",
    extraction_method: "legacy_direct",
    validation_status: "pending",
    time_horizon: "short_term",
    rationale: "技术面顶背离，减仓锁利（legacy 直提，未经 F3/F4，无独立证据链与执行时钟）。",
    tags: ["新能源", "电池"],
  },
  intent: null,
  policy: null,
  evidence_spans: [],
  envelope: {
    envelope_id: "env-catl-300750",
    source_text: SOURCE_CATL,
    source_published_at: "2026-05-19T14:15:00+08:00",
    creator_id: "trend_hunter_k",
    kol_id: "trend_hunter_k",
  },
};

// --- exports -----------------------------------------------------------------

export const AUDIT_BUNDLES: Record<string, AuditTraceBundle> = {
  [BUNDLE_CANONICAL.trade_action.trade_action_id]: BUNDLE_CANONICAL,
  [BUNDLE_PARTIAL.trade_action.trade_action_id]: BUNDLE_PARTIAL,
  [BUNDLE_NON_CANONICAL.trade_action.trade_action_id]: BUNDLE_NON_CANONICAL,
};

export const AUDIT_SUMMARIES: TradeActionSummary[] = [
  {
    trade_action_id: "ta-mt-600519-01",
    ticker: "600519",
    company_name: "贵州茅台",
    direction: "bullish",
    summary: "回调黄金坑，1480-1500 分批建仓三成，破 1450 止损",
    canonical_trace_status: "canonical",
    validation_status: "verified",
    kol_id: "trader_ji",
    created_at: "2026-05-20T21:34:00+08:00",
    backtest_return_pct: 0.112,
  },
  {
    trade_action_id: "ta-wly-000858-01",
    ticker: "000858",
    company_name: "五粮液",
    direction: "bullish",
    summary: "估值历史低位，长期慢慢收集（缺 F4 Policy）",
    canonical_trace_status: "partial",
    validation_status: "under_review",
    kol_id: "value_laozhang",
    created_at: "2026-05-22T10:06:00+08:00",
  },
  {
    trade_action_id: "ta-catl-300750-01",
    ticker: "300750",
    company_name: "宁德时代",
    direction: "bearish",
    summary: "顶背离减仓一半锁利（legacy 直提，无证据链）",
    canonical_trace_status: "non_canonical",
    validation_status: "pending",
    kol_id: "trend_hunter_k",
    created_at: "2026-05-19T14:20:00+08:00",
  },
];
