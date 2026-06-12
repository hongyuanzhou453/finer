/**
 * Demo fixtures + deterministic RLVR scorer for the annotation walkthrough.
 *
 * ALL passages use the same fabricated personas as data.ts (no real people),
 * and `scoreExtraction` is a transparent rule-based function — NOT a model.
 * It mirrors the reward axes in docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md
 * (structure gate + grounding / calibration / abstention) so the demo shows how
 * a verifiable reward is computed, deterministically and for free.
 */

import type {
  ExtractionDraft,
  F6Case,
  GoldTask,
  PreferencePair,
  RewardBreakdown,
  TradeDirection,
} from "./types";

const COMMITTAL: TradeDirection[] = ["bullish", "bearish"];

const clamp = (v: number) => Math.max(0, Math.min(1, v));

/** ticker core (strip exchange suffix + leading zeros) for loose grounding. */
function tickerCore(ticker: string): string {
  return ticker
    .replace(/\.(SH|SZ|HK|US)$/i, "")
    .replace(/^0+/, "");
}

function tickerGrounded(ticker: string, evidence: string): boolean {
  if (!ticker || ticker === "NONE") return false;
  if (evidence.includes(ticker)) return true;
  const core = tickerCore(ticker);
  return core.length >= 3 && evidence.includes(core);
}

/** Returns whether the draft cites any price, and whether every cited price is in the source. */
function priceCheck(draft: ExtractionDraft, evidence: string): { hasPrice: boolean; ok: boolean } {
  const prices = [draft.target_price_low, draft.target_price_high].filter(
    (v): v is number => v != null,
  );
  if (prices.length === 0) return { hasPrice: false, ok: true };
  const ok = prices.every((p) => evidence.includes(String(p)));
  return { hasPrice: true, ok };
}

/**
 * Deterministic verifier. Structure is a hard gate (fail -> total 0); the
 * remaining axes are weighted grounding 0.5 / calibration 0.4 / abstention 0.1.
 */
export function scoreExtraction(draft: ExtractionDraft, evidence: string): RewardBreakdown {
  const notes: string[] = [];
  const committal = COMMITTAL.includes(draft.direction);

  // --- structure gate ---
  const validDirection = (
    ["bullish", "bearish", "neutral", "watchlist", "risk_warning"] as TradeDirection[]
  ).includes(draft.direction);
  const validConviction = draft.conviction >= 0 && draft.conviction <= 1;
  const hasTicker = committal ? draft.ticker.trim().length > 0 && draft.ticker !== "NONE" : true;
  const priceOrder =
    draft.target_price_low == null ||
    draft.target_price_high == null ||
    draft.target_price_low <= draft.target_price_high;
  const structurePass = validDirection && validConviction && hasTicker && priceOrder;

  if (!structurePass) {
    if (!validDirection) notes.push("direction 非法枚举 → 结构门未过");
    if (!validConviction) notes.push("conviction 越界 [0,1] → 结构门未过");
    if (!hasTicker) notes.push("承诺性输出缺 ticker → 结构门未过");
    if (!priceOrder) notes.push("价格区间 low > high → 结构门未过");
    return { total: 0, structurePass: false, grounding: 0, calibration: 0, abstention: 0, committal, notes };
  }

  // --- grounding ---
  let grounding: number;
  if (!committal) {
    grounding = 1; // 非承诺无需溯源承诺
    notes.push("非承诺输出，无需溯源");
  } else {
    const tg = tickerGrounded(draft.ticker, evidence);
    const { hasPrice, ok: priceOk } = priceCheck(draft, evidence);
    grounding = (tg ? 0.6 : 0) + (priceOk ? 0.4 : 0);
    notes.push(tg ? `标的 ${draft.ticker} 可在原文溯源` : `标的 ${draft.ticker} 未在原文出现（疑似编造）`);
    if (hasPrice) notes.push(priceOk ? "目标价可在原文溯源" : "目标价未在原文出现（疑似编造）");
  }

  // --- calibration: conviction vs evidence strength ---
  let expected: number;
  if (!committal) {
    expected = 0.3; // 弃权类应低信念
  } else if (grounding >= 0.95) {
    expected = 0.8; // 标的+价位皆溯源
  } else if (grounding >= 0.55) {
    expected = 0.6; // 标的溯源、无价位
  } else {
    expected = 0.3; // 硬给买卖但未溯源
  }
  const calibration = clamp(1 - Math.abs(draft.conviction - expected) / 0.5);
  notes.push(`信念 ${draft.conviction.toFixed(2)} vs 证据期望 ${expected.toFixed(2)}`);

  // --- abstention: rewarded when abstaining under weak evidence ---
  const abstention = committal ? 0.4 : 1;
  if (!committal) notes.push("证据不足时观望，abstention +");

  const total = clamp(0.5 * grounding + 0.4 * calibration + 0.1 * abstention);
  return { total, structurePass: true, grounding, calibration, abstention, committal, notes };
}

/** committal share among a set of drafts — the reward-health signal. */
export function committalRate(drafts: ExtractionDraft[]): number {
  if (drafts.length === 0) return 0;
  const n = drafts.filter((d) => COMMITTAL.includes(d.direction)).length;
  return n / drafts.length;
}

// ---- Task 1: held-out eval gold ---------------------------------------------

export const GOLD_TASKS: GoldTask[] = [
  {
    id: "gold-001",
    persona: "老纪 · trader_ji",
    passage:
      "白酒龙头估值已经回到历史低位，600519 贵州茅台基本面没问题，我自己加到了三成仓，目标看 1900 附近，再跌就是机会。",
    expected_abstain: false,
    reference_gold: {
      direction: "bullish",
      ticker: "600519.SH",
      conviction: 0.8,
      note: "标的 600519 与目标价 1900 均可溯，方向明确——可给高信念 bullish。",
    },
  },
  {
    id: "gold-002",
    persona: "港股老兵 · hk_veteran",
    passage:
      "最近大盘怎么走我也看不清，外围扰动太多，大家自己注意风险，我先空仓观望，不给具体方向和标的。",
    expected_abstain: true,
    reference_gold: {
      direction: "watchlist",
      ticker: "NONE",
      conviction: 0.2,
      note: "无明确标的与方向，证据不足——应弃权 watchlist、低信念。",
    },
  },
];

// ---- Task 2: DPO preference pairs -------------------------------------------

export const PREFERENCE_PAIRS: PreferencePair[] = [
  {
    id: "pair-001",
    persona: "老纪 · trader_ji",
    prompt:
      "白酒龙头估值已经回到历史低位，600519 贵州茅台基本面没问题，我自己加到了三成仓，目标看 1900 附近，再跌就是机会。",
    chosen: {
      ticker: "600519.SH",
      direction: "bullish",
      conviction: 0.8,
      action: "long",
      target_price_low: 1900,
      target_price_high: null,
      rationale: "加仓三成、目标 1900，标的与价位均来自原文。",
    },
    rejected: {
      ticker: "600519.SH",
      direction: "bullish",
      conviction: 0.96,
      action: "long",
      target_price_low: 2500,
      target_price_high: 2800,
      rationale: "强烈看多，目标价 2500-2800。",
    },
    rationale: "chosen 的目标价 1900 来自原文、信念与证据匹配；rejected 编造 2500-2800 目标价且信念虚高。",
  },
  {
    id: "pair-002",
    persona: "趋势猎手K · trend_hunter_k",
    prompt: "东方财富 300059 放量突破，我先跟一个底仓，站稳 20 日线再加。",
    chosen: {
      ticker: "300059.SZ",
      direction: "bullish",
      conviction: 0.6,
      action: "long",
      target_price_low: null,
      target_price_high: null,
      rationale: "突破跟底仓、未给目标价，标的来自原文。",
    },
    rejected: {
      ticker: "002460.SZ",
      direction: "bullish",
      conviction: 0.7,
      action: "long",
      target_price_low: null,
      target_price_high: null,
      rationale: "看多赣锋锂业。",
    },
    rationale: "chosen 标的 300059 可溯；rejected 编造了原文根本没有的 002460。",
  },
  {
    id: "pair-003",
    persona: "港股老兵 · hk_veteran",
    prompt: "港股这波反弹我觉得就是超跌修复，没什么基本面支撑，不建议追，我自己空仓看着。",
    chosen: {
      ticker: "NONE",
      direction: "watchlist",
      conviction: 0.3,
      action: "watch",
      target_price_low: null,
      target_price_high: null,
      rationale: "超跌修复无基本面支撑，空仓观望。",
    },
    rejected: {
      ticker: "00700.HK",
      direction: "bullish",
      conviction: 0.55,
      action: "long",
      target_price_low: null,
      target_price_high: null,
      rationale: "反弹看多腾讯。",
    },
    rationale: "原文明确不建议追、空仓观望；chosen 正确弃权，rejected 编造标的且方向相反。",
  },
];

// ---- Task 3: F6 field-level corrections -------------------------------------

export const F6_CASES: F6Case[] = [
  {
    id: "f6-001",
    trade_action_id: "TA-value_laozhang-001",
    persona: "价值老张 · value_laozhang",
    passage: "中国平安 601318 我觉得短期还有压力，先减一部分仓位，等回踩再看。",
    model_output: {
      ticker: "601318.SH",
      direction: "bullish",
      conviction: 0.7,
      action: "long",
      target_price_low: null,
      target_price_high: null,
      rationale: "看多中国平安。",
    },
    flagged: "方向判反：原文是「减仓、还有压力」，模型却输出 bullish / long。",
  },
  {
    id: "f6-002",
    trade_action_id: "TA-trend_hunter_k-001",
    persona: "趋势猎手K · trend_hunter_k",
    passage: "东方财富 300059 突破了，先跟一手，没说具体目标价，看着走。",
    model_output: {
      ticker: "300059.SZ",
      direction: "bullish",
      conviction: 0.85,
      action: "long",
      target_price_low: 25,
      target_price_high: 32,
      rationale: "突破跟进，目标 25-32。",
    },
    flagged: "编造目标价：原文未给目标价，模型臆造 25-32，且信念偏高。",
  },
];
