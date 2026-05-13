# KOL Backtest MVP — Fixture Contract

> Status: draft
> Created: 2026-05-11
> Scope: Golden fixture standards for end-to-end MVP pipeline verification

## 1. Purpose

This contract defines the canonical test fixtures for verifying the KOL Backtest MVP pipeline (F0 → F1 → F1.5 → F2 → F3 → F4 → F5 → F8). Every fixture is a deterministic, self-contained artifact that enables:

- Per-stage output verification (schema compliance + field-level assertions)
- End-to-end pipeline smoke testing (F0 input → F8 output)
- Regression detection when schemas or extractors change

Fixtures are NOT implementation code. They are the ground truth that implementation tests assert against.

---

## 2. Fixture Directory Structure

Two independent KOL fixtures. Each KOL runs independently through F1→F8. No cross-KOL data flow.

```
tests/fixtures/kol-backtest-mvp/
├── cat_lord/                                # Primary golden: 投研分析型
│   ├── kol_profile.json                     # KOL persona + policy context
│   ├── market_prices.csv                    # Historical prices for backtest
│   ├── content/
│   │   ├── c_001_bullish_csiq.manifest.json
│   │   ├── c_001_bullish_csiq.raw.md
│   │   ├── ... (10 content items)
│   │   └── c_010_multi_intent.raw.md
│   ├── F1/
│   │   └── expected_c_*.envelope.json
│   ├── F1.5/
│   │   └── expected_c_*.assembly.json
│   ├── F2/
│   │   └── expected_c_*.anchors.json
│   ├── F3/
│   │   └── expected_c_*.intents.json
│   ├── F4/
│   │   └── expected_c_*.policy.json
│   ├── F5/
│   │   ├── expected_c_*.actions.json
│   │   └── expected_c_*.rejections.json
│   └── F8/
│       ├── expected_backtest_result.json
│       └── expected_equity_curve.csv
│
└── trader_ji/                               # Secondary golden: 交易信号型
    ├── kol_profile.json
    ├── market_prices.csv
    ├── content/
    │   ├── t_001_*.manifest.json
    │   ├── t_001_*.raw.md
    │   ├── ... (10-15 content items)
    │   └── t_015_*.raw.md
    ├── F1/
    │   └── expected_t_*.envelope.json
    ├── F1.5/
    │   └── expected_t_*.assembly.json
    ├── F2/
    │   └── expected_t_*.anchors.json
    ├── F3/
    │   └── expected_t_*.intents.json
    ├── F4/
    │   └── expected_t_*.policy.json
    ├── F5/
    │   ├── expected_t_*.actions.json
    │   └── expected_t_*.rejections.json
    └── F8/
        ├── expected_backtest_result.json
        └── expected_equity_curve.csv
```

---

## 3. KOL Profile Design

Two real KOLs with distinct styles. Each validates different aspects of the MVP pipeline.

### 3.1 Primary Golden: Cat Lord (猫大人FIRE)

```json
{
  "kol_id": "kol_cat_lord_fire",
  "display_name": "猫大人FIRE",
  "style_archetype": "value",
  "risk_preference": "balanced",
  "persona_summary": "Fundamentals-driven value investor covering A-share and US-listed Chinese equities plus US mega-cap tech. Known for detailed financial modeling (earnings forecasts, PE-based price targets). Tends to express bearish views with specific data points and bullish views with entry conditions. Uses watch/wait-for-dip strategy frequently. Historical win rate ~60%, average hold 2-8 weeks. Concentrated positions in new energy, tech, and consumer sectors.",
  "platform_identities": [
    {
      "platform": "feishu",
      "account_id": "fs_cat_lord_fire_001",
      "account_name": "猫大人FIRE",
      "follower_count": 8500
    },
    {
      "platform": "wechat",
      "account_id": "wx_cat_lord_fire_001",
      "account_name": "猫大人",
      "follower_count": 15000
    }
  ],
  "tags": ["value", "fundamentals", "cn_equity", "us_chinese_adr", "new_energy"],
  "rating": 4.2
}
```

### 3.2 Cat Lord Policy Context (F4 input derived from profile)

```json
{
  "kol_id": "kol_cat_lord_fire",
  "style_archetype": "value",
  "risk_preference": "balanced",
  "persona_summary": "...(same as above)...",
  "active_corrections": []
}
```

### 3.3 Secondary Golden: Trader Ji (9友/trader韭)

```json
{
  "kol_id": "trader_ji",
  "display_name": "9友",
  "style_archetype": "signal_flow",
  "risk_preference": "aggressive",
  "persona_summary": "Short-term signal flow trader. Publishes daily pre-market previews, post-market reviews, and weekly strategy notes via Feishu and Bilibili. Content is structured around specific trade signals with explicit entry/exit levels. Focuses on A-share index plays and sector rotation. Known for time-sensitive calls ('today open', 'before close'). Higher frequency of explicit_action intents, shorter holding periods (days to 1-2 weeks).",
  "platform_identities": [
    {
      "platform": "feishu",
      "account_id": "ou_ba157042c2a9726fb00a9a1018b360af",
      "account_name": "9友",
      "follower_count": 6200
    },
    {
      "platform": "bilibili",
      "account_id": "bili_9you_001",
      "account_name": "trader韭",
      "follower_count": 28000
    }
  ],
  "tags": ["signal_flow", "short_term", "a_share", "index_play", "sector_rotation"],
  "rating": 3.5
}
```

### 3.4 Trader Ji Policy Context

```json
{
  "kol_id": "trader_ji",
  "style_archetype": "signal_flow",
  "risk_preference": "aggressive",
  "persona_summary": "...(same as above)...",
  "active_corrections": []
}
```

---

## 4. Content Set Design

Each KOL gets its own content set. Content items follow the pattern `{prefix}_{NNN}_{signal_type}_{ticker}` where prefix is `c_` for cat_lord and `t_` for trader_ji.

### 4.0 Coverage Requirements (Both KOLs)

Each KOL's content set MUST cover:
- At least 3 explicit_action intents (producing canonical TradeActions)
- At least 2 distinct action types (e.g., open + close, or reduce + hold)
- At least 1 non-executable intent (opinion, watch, or review_required)
- At least 1 multi-ticker or multi-intent content item
- At least 2 distinct source types

### 4.1 Cat Lord Content Set

10 content items in Cat Lord's style: fundamentals-driven analysis with financial data, price targets, entry conditions, and risk warnings. Mix of A-share, US-listed Chinese ADRs, and US mega-cap tech.

| content_id | signal_type | ticker | source_type | description |
|---|---|---|---|---|
| c_001_bullish_csiq | bullish opinion | CSIQ | feishu | "阿特斯太阳能CSIQ更值得关注，在手订单充沛，动态远期PE只有8-12倍。2026大概率扭亏为盈。" Bullish with data but no explicit action verb |
| c_002_buy_li | explicit buy | LI | feishu | "理想汽车投资价值弱于其他新能源车企，15元以下都是不错的入场机会。减仓。" Explicit reduce action on LI |
| c_003_bearish_600989 | bearish warning | 600989 | feishu | "宝丰能源目前属于风险高于价值。等跌到27元以下再酌情关注。" Bearish + watch/wait |
| c_004_hold_tme | hold signal | TME | feishu | "腾讯音乐基本到了买不了吃亏买不了上当的阶段。埋伏没问题。" Hold + conviction |
| c_005_ambiguous | ambiguous | NVDA | wechat | "NVDA估值偏高，但AI capex周期刚起步。短期回调风险与长期机会并存。" Ambiguous direction |
| c_006_nonactionable | non-actionable | — | feishu | "市场环境处于震荡调整阶段，主要指数表现分化。" Pure macro commentary, no actionable ticker |
| c_007_mixed | mixed signals | LI+CSIQ | feishu | "理想汽车短期看空，但阿特斯太阳能在15元以下可以建仓。" Multi-ticker, mixed direction |
| c_008_close_li | close position | LI | feishu | "理想汽车套娃策略玩崩了，已全部清仓。等待新款车市场认可。" Explicit close_long |
| c_009_watch_600989 | watch list | 600989 | feishu | "宝丰能源目标价27.5-27.8元，目前定价高估。等跌到27元以下再关注。" Watch + trigger condition |
| c_010_multi_intent | multi-intent | CSIQ+TSLA | wechat | "阿特斯太阳能CSIQ 15元以下建仓，TSLA回调到220也可以加仓。" Two actionable intents in one content |

### 4.2 Signal Coverage Matrix

| Signal Type | Content IDs | F3 actionability | F3 position_delta_hint |
|---|---|---|---|
| Bullish opinion | c_001 | opinion | none |
| Explicit reduce | c_002 | explicit_action | reduce |
| Bearish + watch | c_003 | watch | none |
| Hold | c_004 | explicit_action | hold |
| Ambiguous | c_005 | review_required | none |
| Non-actionable | c_006 | opinion | none |
| Mixed multi-ticker | c_007 | explicit_action | exit (LI) + open (CSIQ) |
| Close position | c_008 | explicit_action | exit |
| Watch + trigger | c_009 | watch | none |
| Multi-intent | c_010 | explicit_action | open (CSIQ) + open (TSLA) |

### 4.3 Required Coverage

- **Actionable intents (explicit_action)**: c_002, c_004, c_007 (2 intents), c_008, c_010 (2 intents) = **8 actionable intents** across 5 content items
- **Non-executable intents**: c_001 (opinion), c_003 (watch), c_005 (review_required), c_006 (opinion), c_009 (watch) = **5 non-executable intents**
- **Action types**: open (c_007/CSIQ, c_010), hold (c_004), close_long (c_002/LI, c_007/LI, c_008/LI), reduce (c_002) = **4 distinct action types** (watch excluded from F5 output)
- **Directions**: bullish (c_001, c_004, c_010), bearish (c_002, c_003, c_008), neutral (c_006), mixed (c_007), unknown (c_005) = **5 directions**
- **Edge cases**: ambiguous content (c_005), non-actionable commentary (c_006), multi-ticker single content (c_007, c_010), A-share ticker (600989)

### 4.4 Trader Ji Content Set

10-15 content items in Trader Ji's style: short-form signal flow with explicit entry/exit levels, time-sensitive calls, daily pre/post market notes. Mix of A-share index plays and sector rotation signals.

| content_id | signal_type | ticker | source_type | description |
|---|---|---|---|---|
| t_001_buy_510300 | explicit buy | 510300 | daily_pre | "今天开盘买入沪深300ETF，目标前高。止损设在昨日低点。" Explicit buy with time anchor "today open" |
| t_002_sell_159915 | explicit sell | 159915 | daily_post | "创业板ETF尾盘已全部清仓，明天观望。" Explicit close + next-day watch |
| t_003_hold_600519 | hold signal | 600519 | weekly_strategy | "茅台本周继续持有，不加不减。等待周五消费数据。" Hold with time anchor |
| t_004_bullish_000858 | bullish opinion | 000858 | daily_pre | "五粮液估值合理，但短期无催化剂。观察。" Opinion + watch |
| t_005_bearish_601318 | bearish warning | 601318 | wechat | "中国平安短期承压，地产风险未出清。暂时回避。" Bearish + avoid |
| t_006_nonactionable | non-actionable | — | daily_post | "今日大盘缩量震荡，市场情绪偏谨慎。" Pure market commentary |
| t_007_mixed | mixed signals | 510300+159915 | weekly_strategy | "沪深300看多，但创业板短期需减仓。" Multi-ticker mixed |
| t_008_add_510300 | explicit add | 510300 | daily_pre | "沪深300ETF今天回调到位，加仓10%。" Explicit add with timing |
| t_009_watch_000001 | watch list | 000001 | daily_post | "平安银行接近支撑位，明天如果放量可以进场。" Watch + trigger |
| t_010_multi_intent | multi-intent | 510300+600519 | weekly_strategy | "本周策略：沪深300继续加仓，茅台择机减仓锁定利润。" Two actionable intents |
| t_011_ambiguous | ambiguous | 601012 | wechat | "隆基绿能消息面复杂，多空分歧大。暂时不动。" Ambiguous |
| t_012_close_510300 | close position | 510300 | daily_post | "沪深300ETF已全部止盈，落袋为安。" Explicit close_long |
| t_013_bullish_399006 | bullish opinion | 399006 | daily_pre | "创业板指今天大概率反弹，但不确定幅度。" Opinion, no action verb |
| t_014_reduce_600519 | explicit reduce | 600519 | daily_post | "茅台减仓一半，锁定部分利润。" Explicit reduce |
| t_015_ambiguous_multi | ambiguous multi | 000858+601318 | wechat | "白酒和保险都不确定，再观察一周。" Multi-ticker ambiguous |

### 4.5 Trader Ji Signal Coverage Matrix

| Signal Type | Content IDs | F3 actionability | F3 position_delta_hint |
|---|---|---|---|
| Explicit buy | t_001 | explicit_action | open |
| Explicit sell/close | t_002 | explicit_action | exit |
| Hold | t_003 | explicit_action | hold |
| Bullish + watch | t_004 | watch | none |
| Bearish + avoid | t_005 | watch | none |
| Non-actionable | t_006 | opinion | none |
| Mixed multi-ticker | t_007 | explicit_action | open (510300) + reduce (159915) |
| Explicit add | t_008 | explicit_action | add |
| Watch + trigger | t_009 | watch | none |
| Multi-intent | t_010 | explicit_action | add (510300) + reduce (600519) |
| Ambiguous | t_011 | review_required | none |
| Close position | t_012 | explicit_action | exit |
| Bullish opinion | t_013 | opinion | none |
| Explicit reduce | t_014 | explicit_action | reduce |
| Ambiguous multi | t_015 | review_required | none |

### 4.6 Trader Ji Required Coverage

- **Actionable intents (explicit_action)**: t_001, t_002, t_003, t_007 (2), t_008, t_010 (2), t_012, t_014 = **10 actionable intents** across 8 content items
- **Non-executable intents**: t_004 (watch), t_005 (watch), t_006 (opinion), t_009 (watch), t_011 (review_required), t_013 (opinion), t_015 (review_required) = **7 non-executable intents**
- **Action types**: open (t_001, t_007/510300), add (t_008, t_010/510300), close_long (t_002, t_012), reduce (t_007/159915, t_010/600519, t_014), hold (t_003) = **5 distinct action types**
- **Directions**: bullish (t_001, t_004, t_008, t_013), bearish (t_002, t_005, t_014), neutral (t_003, t_006), mixed (t_007), unknown (t_011, t_015) = **5 directions**
- **Edge cases**: time-sensitive calls (t_001 "today open"), multi-index content (t_007, t_010), A-share index ETFs (510300, 159915), ambiguous multi-ticker (t_015)
- **Trader Ji tests**: time anchor resolution ("today open", "before close", "this week"), execution timing, explicit_action frequency

---

## 5. Market Price Data

Each KOL has its own `market_prices.csv`. Tickers may overlap between KOLs but each file is independent.

### 5.1 Tickers

**Cat Lord tickers** (in `cat_lord/market_prices.csv`):

| Ticker | Market | Coverage |
|---|---|---|
| CSIQ | US | Full date range |
| LI | US | Full date range |
| TME | US | Full date range |
| TSLA | US | Full date range |
| 600989 | CN (A-share) | Full date range |
| NVDA | US | Full date range |

**Trader Ji tickers** (in `trader_ji/market_prices.csv`):

| Ticker | Market | Coverage |
|---|---|---|
| 510300 | CN (ETF) | Full date range |
| 159915 | CN (ETF) | Full date range |
| 600519 | CN (A-share) | Full date range |
| 000858 | CN (A-share) | Full date range |
| 601318 | CN (A-share) | Full date range |
| 000001 | CN (A-share) | Full date range |
| 601012 | CN (A-share) | Full date range |
| 399006 | CN (Index) | Full date range |

### 5.2 Date Range

**2026-03-01 to 2026-05-09** (50 trading days). All content `published_at` dates fall within this window. The backtest evaluation window extends to 2026-05-09 to capture post-signal price movements.

### 5.3 CSV Schema

```csv
date,ticker,open,high,low,close,volume,adj_close
2026-03-02,CSIQ,12.50,13.20,12.30,13.00,5000000,13.00
2026-03-02,LI,28.00,28.50,27.50,28.20,8000000,28.20
2026-03-02,TME,11.50,11.80,11.30,11.60,12000000,11.60
2026-03-02,TSLA,265.00,268.50,262.30,267.80,32000000,267.80
2026-03-02,600989,29.50,30.20,29.30,30.00,25000000,30.00
2026-03-02,NVDA,140.50,143.20,139.80,142.90,45000000,142.90
...
```

### 5.4 Price Behavior Design

The price data must produce **deterministic, verifiable** backtest results. The design:

| Ticker | Pattern | Rationale |
|---|---|---|
| CSIQ | Uptrend 12→18 (Mar-Apr), pullback 18→15 (late Apr), recovery 15→17 (May) | Validates: buy-at-12 (c_001 opinion, no action), open-at-15 (c_007/c_010 at entry condition) |
| LI | Decline 28→22 (Mar-Apr), sideways 22-24 (May) | Validates: bearish-reduce (c_002), close-at-28 (c_008 profit taking), mixed signal (c_007) |
| TME | Stable 11-13 range, slight uptrend | Validates: hold signal (c_004) — no dramatic moves, "buy and hold" thesis |
| TSLA | Dip 265→220 (Mar), recovery 220→275 (Apr-May) | Validates: buy-at-220 (c_010 on dip), hold through recovery |
| 600989 | Range-bound 28-32, brief dip to 26.5 in late Apr | Validates: watch-with-trigger (c_003/c_009) — 27 entry condition test |
| NVDA | Range-bound 130-155, volatile | Validates: ambiguous signal (c_005) — no clear direction |

---

## 6. Trader Ji (9友/trader韭) — Secondary Golden Fixture

### 6.1 Profile: Trader Ji

```json
{
  "kol_id": "trader_ji",
  "display_name": "9友/trader韭",
  "style_archetype": "short_term",
  "risk_preference": "aggressive",
  "persona_summary": "Short-term trader focused on A-share and US tech. Publishes daily pre-market notes, post-market reviews, and weekly strategy summaries. Content is signal-dense with explicit entry/exit levels, time-sensitive calls, and position updates. Style: direct, action-oriented, minimal analysis depth.",
  "content_sources": [
    {"type": "daily_pre", "description": "盘前笔记：当日关注标的 + 操作计划"},
    {"type": "daily_post", "description": "盘后复盘：当日操作记录 + 明日计划"},
    {"type": "weekly_strategy", "description": "周策略：本周重点标的 + 仓位调整"},
    {"type": "bilibili_video", "description": "B站视频：投研分析或操作讲解"},
    {"type": "wechat", "description": "微信文章：深度分析或策略观点"}
  ],
  "default_market": "CN",
  "tags": ["short_term", "momentum", "a_share", "us_tech", "signal_dense"]
}
```

### 6.2 Trader Ji Content Set

10-15 content items from `data/raw/trader_ji/` and `data/raw/9you/`, frozen as test fixtures. Content types:

| Content Type | Source | Expected F3 Signals | Tests |
|---|---|---|---|
| 盘前笔记 (daily_pre) | `data/raw/trader_ji/daily_pre/` | explicit_action: open/add on specific tickers with price levels | Time anchor: "今日开盘", F5 execution timing |
| 盘后复盘 (daily_post) | `data/raw/trader_ji/daily_post/` | explicit_action: close/reduce, hold confirmation | Time anchor: "今日已操作", evidence trace |
| 周策略 (weekly_strategy) | `data/raw/trader_ji/weekly_strategy/` | explicit_action: weekly position adjustments | Time anchor: "本周", holding_period=short_term |
| B站视频 (bilibili_video) | `data/raw/trader_ji/bilibili_video/` | opinion + explicit_action mix | F1 video transcript handling |
| 微信文章 (wechat) | `data/raw/trader_ji/wechat/` | Longer analysis, multi-ticker | F1.5 topic assembly |

### 6.3 Trader Ji Tickers

| Ticker | Market | Coverage |
|---|---|---|
| (A-share tickers from content) | CN | Full date range |
| (US tech tickers from content) | US | Full date range |

Specific tickers determined by frozen content selection. Each KOL's market_prices.csv is independent.

### 6.4 Trader Ji Validates

- **Time anchor resolution**: "今日开盘" → specific date, "本周" → date range
- **Execution timing**: Pre-market content → action_executable_at = same day open
- **Signal-dense content**: Multiple explicit_actions per content item
- **Short-term holding**: holding_period_hint = short_term/intraday
- **F1 source types**: daily_pre, daily_post, weekly_strategy (not just feishu/wechat)

### 6.5 Dual-KOL Independence Rule

- Each KOL has its own `kol_profile.json`, `market_prices.csv`, and content set
- Each KOL runs independently through F1→F8
- No cross-KOL data flow, no shared fixtures
- Both must independently pass all acceptance assertions
- No multi-KOL ranking, no portfolio comparison, no style attribution

---

## 7. Per-Stage Expected Output Contracts

### 7.1 F0 — ContentRecord (manifest.json)

Each `content/{content_id}.manifest.json` is a serialized `ContentRecord`.

**Strict assertions:**
- `content_id` — exact match
- `source_type` — exact match ("wechat" or "feishu" or "daily_pre" etc.)
- `file_type` — exact match ("markdown")
- `creator_id` — exact match (KOL-specific: "kol_cat_lord_fire" or "trader_ji")

**Existence-only assertions:**
- `raw_path` — must exist, value unchecked (path depends on runtime)
- `published_at` — must exist as ISO 8601 string
- `collected_at` — must exist as ISO 8601 string

### 7.2 F1 — ContentEnvelope (expected_*.envelope.json)

**Strict assertions:**
- `envelope_id` — deterministic from content_id (format: `env_{content_id}`)
- `schema_version` — "1.0"
- `source_content_id` — matches content_id
- `blocks[].block_type` — exact match per content (e.g., "text")
- `blocks[].quality.readability` — not null, within [0,1]

**Approximate assertions (tolerance):**
- `blocks[].quality.extraction_confidence` — +/- 0.1
- `blocks[].quality.structural_confidence` — +/- 0.1
- `blocks[].quality.completeness` — +/- 0.1

**Existence-only assertions:**
- `blocks[].block_id` — must be a non-empty string
- `blocks[].text` — must be non-empty
- `created_at` — must exist

### 7.3 F1.5 — TopicAssemblyResult (expected_*.assembly.json)

**Strict assertions:**
- `envelope_id` — matches F1 envelope_id
- `topic_blocks[].topic_type` — exact match (e.g., "single_stock", "market_commentary")
- `topic_blocks[].source_block_ids` — non-empty list, each ID references a valid F1 block

**Approximate assertions:**
- `topic_blocks[].summary` — semantically equivalent (not exact string match; assert key entities and direction present)

**Existence-only assertions:**
- `topic_blocks[].topic_block_id` — non-empty string
- `topic_blocks[].raw_text` — non-empty string

**Special cases:**
- c_006 (non-actionable): `topic_type` must be "market_commentary" or "other"
- c_007, c_010 (multi-ticker): may produce 1 or 2 topic blocks; if 2, each references distinct source blocks

### 7.4 F2 — Anchors (expected_*.anchors.json)

Container for EvidenceSpan[], EntityAnchor[], TemporalAnchor[] extracted from one content item.

**Strict assertions:**
- `evidence_spans[].schema_version` — "v0.5"
- `entity_anchors[].entity_type` — exact match ("stock", "sector", etc.)
- `entity_anchors[].resolved_symbol` — exact match (e.g., "NVDA", "TSLA")
- `entity_anchors[].market` — exact match (KOL-specific: "US"/"CN" per ticker; see Section 5.1)
- `temporal_anchors[].anchor_type` — exact match

**Approximate assertions:**
- `evidence_spans[].confidence` — +/- 0.15

**Existence-only assertions:**
- `evidence_spans[].evidence_span_id` — non-empty string (format: `span_{hex12}`)
- `evidence_spans[].block_id` — references a valid F1 block_id
- `evidence_spans[].char_start`, `char_end` — integers, char_start < char_end
- `evidence_spans[].text` — non-empty substring of block text
- `temporal_anchors[].resolved_time` — ISO 8601 string if resolved

**Special cases:**
- c_006 (non-actionable): `entity_anchors` may be empty
- c_007, c_010 (multi-ticker): must have entity_anchors for each ticker mentioned

### 7.5 F3 — NormalizedInvestmentIntent (expected_*.intents.json)

Each file contains a list of intents (usually 1, sometimes 2 for c_007/c_010).

**Strict assertions:**
- `schema_version` — "1.0"
- `target_symbol` — exact match (e.g., "NVDA", "TSLA")
- `target_type` — exact match ("stock" for all MVP content)
- `direction` — exact match ("bullish", "bearish", "neutral", "mixed", "unknown")
- `actionability` — exact match ("opinion", "watch", "explicit_action", "review_required")
- `position_delta_hint` — exact match
- `market` — exact match (KOL-specific: "US" or "CN" per ticker)

**Approximate assertions:**
- `conviction` — +/- 0.15
- `confidence` — +/- 0.15

**Existence-only assertions:**
- `intent_id` — non-empty string (UUID format)
- `envelope_id` — references F1 envelope_id
- `block_ids` — non-empty list
- `evidence_span_ids` — non-empty list for actionable intents, references valid F2 spans
- `created_at` — ISO 8601

**Per-content intent expectations:**

| content_id | expected intents | direction | actionability | position_delta_hint | target_symbol |
|---|---|---|---|---|---|
| c_001 | 1 | bullish | opinion | none | CSIQ |
| c_002 | 1 | bearish | explicit_action | reduce | LI |
| c_003 | 1 | bearish | watch | none | 600989 |
| c_004 | 1 | bullish | explicit_action | hold | TME |
| c_005 | 1 | mixed | review_required | none | NVDA |
| c_006 | 1 | neutral | opinion | none | — (no symbol) |
| c_007 | 2 | bearish + bullish | explicit_action | exit + open | LI + CSIQ |
| c_008 | 1 | bearish | explicit_action | exit | LI |
| c_009 | 1 | bearish | watch | none | 600989 |
| c_010 | 2 | bullish + bullish | explicit_action | open + open | CSIQ + TSLA |

### 7.6 F4 — PolicyMappingResult (expected_*.policy.json)

Each file contains a list of PolicyMappingResult objects, one per F3 intent.

**Strict assertions:**
- `intent_id` — references a valid F3 intent_id
- `policy_version` — "global-base-v1"
- `action_hint` — exact match
- `position_sizing_hint` — exact match
- `holding_period_hint` — exact match
- `risk_constraints.max_position_hint` — exact match

**Approximate assertions:**
- `confidence` — +/- 0.15
- `original_intent_confidence` — +/- 0.15

**Existence-only assertions:**
- `policy_id` — non-empty string (UUID format)
- `mapping_rationale` — non-empty string
- `created_at` — ISO 8601
- `layer_traces` — list (may be empty for MVP baseline)

**Per-intent policy expectations:**

| content_id | F3 actionability | expected action_hint | expected position_sizing_hint | expected holding_period_hint |
|---|---|---|---|---|
| c_001 | opinion | watch_only | none | review_required |
| c_002 | explicit_action + reduce | reduce_position | small | short_term |
| c_003 | watch | watch_only | none | review_required |
| c_004 | explicit_action + hold | hold_position | none | medium_term |
| c_005 | review_required | review_required | review_required | review_required |
| c_006 | opinion | watch_only | none | review_required |
| c_007a (LI) | explicit_action + exit | close_position | none | short_term |
| c_007b (CSIQ) | explicit_action + open | open_position | medium | short_term |
| c_008 | explicit_action + exit | close_position | none | short_term |
| c_009 | watch | watch_only | none | review_required |
| c_010a (CSIQ) | explicit_action + open | open_position | medium | short_term |
| c_010b (TSLA) | explicit_action + open | open_position | medium | short_term |

### 7.7 F5 — TradeAction (expected_*.actions.json)

Each file contains a list of TradeAction objects. **Only canonical TradeActions are included** — watch, opinion, and review_required intents do NOT produce TradeActions. See `expected_*.rejections.json` (Section 6.7.1) for skipped/rejected intents.

**Strict assertions:**
- `direction` — exact match (must not contradict F3 direction)
- `action_chain[0].action_type` — exact match
- `canonical_trace_status` — "canonical" (every action in this file)
- `target.ticker_normalized` — exact match
- `target.market` — exact match (KOL-specific: "US"/"CN" per ticker; see Section 5.1)
- `intent_id` — references F3 intent_id
- `policy_id` — references F4 policy_id
- `evidence_span_ids` — non-empty

**Approximate assertions:**
- `confidence` — +/- 0.15
- `enrichment.market_price_at_time` — +/- 1.0 (price at time of signal)

**Existence-only assertions:**
- `trade_action_id` — non-empty string (UUID format)
- `timestamp` — ISO 8601
- `execution_timing.intent_published_at` — ISO 8601
- `execution_timing.action_decision_at` — ISO 8601
- `execution_timing.action_executable_at` — ISO 8601
- `execution_timing.market` — KOL-specific ("US" for cat_lord US tickers, "CN" for cat_lord 600989 and all trader_ji tickers)
- `execution_timing.timezone` — KOL-specific ("America/New_York" for US tickers, "Asia/Shanghai" for CN tickers)
- `execution_timing.timing_policy_id` — non-empty string
- `source.content_id` — references content_id
- `source.evidence_text` — non-empty substring of raw content

**Per-content action expectations (only explicit_action intents that pass F4 executable gate):**

Cat Lord:

| content_id | action_type | direction | canonical_trace_status | target |
|---|---|---|---|---|
| c_002 | close_long | bearish | canonical | LI |
| c_004 | hold | bullish | canonical | TME |
| c_007a | close_long | bearish | canonical | LI |
| c_007b | long | bullish | canonical | CSIQ |
| c_008 | close_long | bearish | canonical | LI |
| c_010a | long | bullish | canonical | CSIQ |
| c_010b | long | bullish | canonical | TSLA |

**Cat Lord canonical TradeActions**: 7

Trader Ji:

| content_id | action_type | direction | canonical_trace_status | target |
|---|---|---|---|---|
| t_001 | long | bullish | canonical | 510300 |
| t_002 | close_long | bearish | canonical | 159915 |
| t_003 | hold | neutral | canonical | 600519 |
| t_007a | long | bullish | canonical | 510300 |
| t_007b | close_long | bearish | canonical | 159915 |
| t_008 | long (add) | bullish | canonical | 510300 |
| t_010a | long (add) | bullish | canonical | 510300 |
| t_010b | close_long | bearish | canonical | 600519 |
| t_012 | close_long | bearish | canonical | 510300 |
| t_014 | close_long | bearish | canonical | 600519 |

**Trader Ji canonical TradeActions**: 10

#### 7.7.1 Rejections — expected_*.rejections.json

Each file lists intents that were rejected or skipped during F4/F5 processing, with structured reasons. These files are written alongside `expected_*.actions.json` for audit trail completeness.

**Schema per rejection record:**

| Field | Type | Description |
|---|---|---|
| `intent_id` | `str` | F3 intent that was rejected |
| `policy_id` | `str` | F4 policy result (if intent reached F4), null otherwise |
| `rejection_stage` | `str` | `"F4"` (filtered by executable gate) or `"F5"` (rejected during TradeAction generation) |
| `rejection_reason` | `str` | Structured reason code |
| `description` | `str` | Human-readable explanation |

**Expected rejections — Cat Lord:**

| content_id | intent target | rejection_stage | rejection_reason | description |
|---|---|---|---|---|
| c_001 | CSIQ | F4 | `non_executable_action_hint` | opinion-only intent → `watch_only`, excluded at executable gate |
| c_003 | 600989 | F4 | `non_executable_action_hint` | watch intent → `watch_only`, excluded at executable gate |
| c_005 | NVDA | F4 | `non_executable_action_hint` | review_required intent → `review_required`, excluded at executable gate |
| c_006 | — | F4 | `non_executable_action_hint` | opinion-only, no ticker → `watch_only`, excluded at executable gate |
| c_009 | 600989 | F4 | `non_executable_action_hint` | watch intent → `watch_only`, excluded at executable gate |

**Expected rejections — Trader Ji:**

| content_id | intent target | rejection_stage | rejection_reason | description |
|---|---|---|---|---|
| t_004 | 000858 | F4 | `non_executable_action_hint` | watch intent → `watch_only`, excluded at executable gate |
| t_005 | 601318 | F4 | `non_executable_action_hint` | watch intent → `watch_only`, excluded at executable gate |
| t_006 | — | F4 | `non_executable_action_hint` | opinion-only, no ticker → `watch_only`, excluded at executable gate |
| t_009 | 000001 | F4 | `non_executable_action_hint` | watch intent → `watch_only`, excluded at executable gate |
| t_011 | 601012 | F4 | `non_executable_action_hint` | review_required → `review_required`, excluded at executable gate |
| t_013 | 399006 | F4 | `non_executable_action_hint` | opinion-only → `watch_only`, excluded at executable gate |
| t_015 | 000858+601318 | F4 | `non_executable_action_hint` | review_required → `review_required`, excluded at executable gate |

### 7.8 F8 — BacktestResult (expected_backtest_result.json + expected_equity_curve.csv)

**Scope**: Only canonical TradeActions (canonical_trace_status = "canonical") participate in the backtest. Watch and non-canonical actions are excluded.

**expected_backtest_result.json — Cat Lord:**

```json
{
  "total_trades": 7,
  "return_pct": "<computed from market_prices.csv>",
  "max_drawdown_pct": "<computed>",
  "sharpe_ratio": "<computed>",
  "win_rate": "<computed>",
  "backtest_period": "2026-03-01 to 2026-05-09",
  "initial_capital": 100000,
  "trading_days": 50,
  "commission_pct": 0,
  "slippage_pct": 0,
  "max_holding_days": 30
}
```

**expected_backtest_result.json — Trader Ji:**

```json
{
  "total_trades": 10,
  "return_pct": "<computed from market_prices.csv>",
  "max_drawdown_pct": "<computed>",
  "sharpe_ratio": "<computed>",
  "win_rate": "<computed>",
  "backtest_period": "2026-03-01 to 2026-05-09",
  "initial_capital": 100000,
  "trading_days": 50,
  "commission_pct": 0,
  "slippage_pct": 0,
  "max_holding_days": 30
}
```

**Strict assertions (both KOLs):**
- `total_trades` — exact count of canonical actions (7 for cat_lord, 10 for trader_ji)
- `backtest_period` — exact match "2026-03-01 to 2026-05-09"
- `initial_capital` — 100000
- `commission_pct` — 0 (no commissions for MVP)
- `slippage_pct` — 0 (no slippage for MVP)
- `max_holding_days` — 30

**Approximate assertions (tolerance):**
- `return_pct` — +/- 0.5% (depends on exact execution timing resolution)
- `max_drawdown_pct` — +/- 1.0%
- `sharpe_ratio` — +/- 0.1

**expected_equity_curve.csv:**

```csv
date,equity,benchmark,cash,positions_value
2026-03-01,100000.00,100000.00,100000.00,0.00
2026-03-02,100000.00,100150.00,100000.00,0.00
...
```

**Strict assertions:**
- First row: `equity` = 100000.00, `cash` = 100000.00, `positions_value` = 0.00
- Row count = trading days in range (50 business days)
- `date` column is monotonically increasing, no gaps on trading days

**Approximate assertions:**
- `equity` — +/- 0.5% per row
- `benchmark` — +/- 0.5% (buy-and-hold equal-weight portfolio of traded tickers)

---

## 8. Assertion Classification Summary

| Level | Rule | Examples |
|---|---|---|
| **Strict** | Value must match exactly. Test failure = bug. | IDs, schema_version, direction, action_type, canonical_trace_status, market, ticker |
| **Approximate** | Value within tolerance. Test failure = regression or drift. | confidence, conviction, quality scores, price, return_pct, sharpe_ratio |
| **Existence-only** | Field must be present and non-null. Value unchecked. | timestamps, UUIDs, text content, file paths |

### 8.1 Tolerance Table

| Field Category | Tolerance | Rationale |
|---|---|---|
| Confidence / conviction | +/- 0.15 | LLM non-determinism across runs |
| Quality scores | +/- 0.1 | Parser heuristics may vary |
| Market prices (enrichment) | +/- 1.0 | API rounding, timing jitter |
| Backtest return_pct | +/- 0.5% | Execution timing resolution |
| Backtest max_drawdown | +/- 1.0% | Intraday price granularity |
| Backtest sharpe_ratio | +/- 0.1 | Statistical estimation variance |

---

## 9. Minimum Counts

| Metric | Cat Lord | Trader Ji | Rationale |
|---|---|---|---|
| Content items | 10 | 15 | Covers all signal types + edge cases |
| Actionable intents (F3) | 8 | 11 | From content items producing explicit_action |
| Canonical TradeActions (F5) | 7 | 10 | Only from explicit_action intents passing F4 executable gate |
| Rejected/skipped intents | 5 | 7 | opinion, review_required, and watch intents excluded at F4/F5 |
| Distinct tickers | 6 | 8 | Mixed CN + US for cat_lord; CN-only for trader_ji |
| Distinct action types | 4 | 5 | long, hold, close_long, reduce (+ add for trader_ji) |
| Distinct source types | 2 | 4 | wechat, feishu for cat_lord; + daily_pre, daily_post, weekly_strategy, bilibili for trader_ji |

---

## 10. Determinism Guarantees

### 10.1 ID Generation

- `envelope_id`: deterministic from content_id — `env_{content_id}`
- `topic_block_id`: deterministic from content_id + index — `tb_{content_id}_{idx}`
- `evidence_span_id`: deterministic from content_id + block + span index — `span_{content_id}_{block_idx}_{span_idx}`
- `intent_id`: deterministic from content_id + intent index — `intent_{content_id}_{idx}`
- `policy_id`: deterministic from intent_id — `policy_{intent_id}`
- `trade_action_id`: deterministic from content_id + action index — `action_{content_id}_{idx}`

All deterministic IDs use a fixed prefix scheme (not UUID) so tests can assert exact values. Fixture JSON files use these deterministic IDs. Runtime implementations may use UUIDs, but must map back to deterministic IDs for test comparison.

### 10.2 Timestamps

Fixture timestamps use fixed dates, not `datetime.now()`. The pipeline processing timestamp (`action_decision_at`) is fixed at `2026-05-10T12:00:00+00:00` for all fixtures.

### 10.3 Market Prices

`market_prices.csv` is a static file, not fetched from an API. Backtest results are computed deterministically from this file.

---

## 11. Fixture Maintenance Rules

1. **Additive only**: New content items can be added; existing fixtures must not be modified without updating this contract.
2. **Schema version bump**: If a schema changes, fixtures must be regenerated and this contract updated with the new schema_version.
3. **One fixture per content item**: Each content item has exactly one expected output per stage, even if the output contains multiple intents/actions.
4. **Cross-reference integrity**: Every ID reference in a downstream stage must resolve to an upstream fixture. Broken references = contract violation.
5. **No runtime dependencies**: Fixtures must be fully deterministic and self-contained. No API calls, no LLM calls, no filesystem state outside the fixture directory.
