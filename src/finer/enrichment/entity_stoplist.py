"""F2 entity-candidate stoplists — shared single source of truth.

These negative lexicons are used to reject non-entity tokens during F2 gap
candidate generation. They are consumed by two paths that must stay in sync:

- ``scripts/backfill_f2_anchor.py`` — the deterministic upper-token / cn-cue
  rule paths.
- ``finer.enrichment.llm_entity_proposal`` — the deterministic validator that
  hard-checks constrained-LLM entity proposals.

Keeping the lexicons here (rather than inside the script) lets both the rule
path and the LLM validator import one canonical copy instead of drifting two.

``NOISY_UPPER_TOKENS``
    Upper-case tokens that look like tickers but are not investable entities:
    acronyms, financial metrics/ratios, time/date tokens, currency codes,
    Pop Mart IP product lines, and generic English words.

``CN_GENERIC_CANDIDATE_TERMS``
    Chinese substrings that, if contained in a candidate alias, mark it as a
    generic phrase rather than a tradable entity name.

``CN_SECTOR_THEME_TERMS``
    Sector / theme / concept names that name a *basket* of stocks, not a single
    tradable instrument (券商, 保险, 创新药...). Matched **exactly** (alias ==
    term), never as a substring, so real names containing the word survive
    (e.g. 新华保险 != 保险, 招商银行 != 银行). Used by the F2 LLM proposal
    validator to reject the sector-泛称 the LLM tends to over-propose on
    conversational text.

``AMBIGUOUS_BARE_UPPER_TOKENS`` / ``AMBIGUOUS_TITLECASE_WORDS`` /
``is_ambiguous_broker_alias``
    Broker-registry aliases that collide with common English words,
    abbreviations, legal-entity suffixes, or timezones (KEY, SE, ET, SI, IQ,
    Target, Block, Stone...). These are NOT dropped — the company reference is
    real — but a bare occurrence in broker-report text is far more often the
    common word ("KEY DEFINITIONS", "UBS Europe SE", "Price Target",
    "Block B-6"). The F2 deterministic scan therefore requires an explicit
    ticker context ("(KEY)", "KEY.N", "Ticker: KEY") before anchoring them —
    the same treatment digit-only aliases already get. Consumed by:

    - ``scripts/build_broker_entity_registry.py`` — marks matching aliases
      with ``requires_context: true`` in the generated YAML.
    - ``finer.enrichment.broker_entity_registry`` — defense-in-depth: applies
      the classifier at load time so stale YAMLs are still gated.
"""

from __future__ import annotations

from typing import Tuple

# Upper-case tokens that resemble tickers but are never investable entities.
NOISY_UPPER_TOKENS: frozenset[str] = frozenset(
    {
        "AI",
        "ADAS",
        "AND",
        "API",
        "APP",
        "ASR",
        "BBG",
        "BPS",
        "BRN0W",
        "CIPS",
        "CAGR",
        "CCL",
        "CEO",
        "CFO",
        "CNBC",
        "CUDA",
        "DDTL",
        "DJT",
        "CPI",
        "CTA",
        "DRAM",
        "ETF",
        "FIFO",
        "FINRA",
        "FILA",
        "FIRE",
        "FSD",
        "GAAP",
        "GDP",
        "GPU",
        "GTC",
        "HBM",
        "HSD",
        "IEA",
        "IDEF",
        "IFRS",
        "IPO",
        "IRR",
        "IP",
        "LABUBU",
        "LTCM",
        "LLM",
        "MOLLY",
        "MORE",
        "NAND",
        "NEW",
        "NOA",
        "OCR",
        "PCB",
        "PDF",
        "PE",
        "PEG",
        "PCE",
        "PROHIBITED",
        "PPI",
        "PSG",
        "PO",
        "PS",
        "PPT",
        "REASONABLE",
        "REGIME",
        "ROE",
        "ROI",
        "RSI",
        "SOFR",
        "SP",
        "TACO",
        "TRUMP",
        "TPU",
        "TV",
        "CN",
        "HK",
        "US",
        "USA",
        "USD",
        "WATCH",
        "I",
        "II",
        "III",
        "IV",
        "V",
        # --- Financial metrics / ratios (a measure, never an investable entity) ---
        "EPS",
        "AUM",
        "ASP",
        "NP",
        "NPM",
        "ER",
        "PB",
        "PIK",
        # --- Time / date tokens (timestamps in KOL screenshots, not entities) ---
        "AM",
        "PM",
        "GMT",
        "UTC",
        # --- Currency codes (consistent with USD above) ---
        "RMB",
        "CNY",
        "HKD",
        "JPY",
        "EUR",
        "GBP",
        # --- Career / desk abbreviations ---
        "IBD",
        # --- Pop Mart IP product lines (consistent with LABUBU / MOLLY) ---
        "DIMOO",
        "PUCKY",
        "YOKI",
        "JELLY",
        "PINO",
        # --- Generic English words / interjections ---
        "JUST",
        "OK",
    }
)

# Chinese substrings that mark a candidate alias as a generic phrase.
CN_GENERIC_CANDIDATE_TERMS: Tuple[str, ...] = (
    "目标",
    "图片",
    "价值",
    "区间",
    "情绪",
    "以上",
    "以下",
    "背景",
    "关键",
    "数据",
    "收入",
    "百万元",
    "占比",
    "提升",
    "提升至",
    "提升到了",
    "去年",
    "方面",
    "一方面",
    "品牌",
    "截止",
    "基于",
    "公开",
    "信息",
    "参考",
    "分析",
    "订单",
    "毛利",
    "产能",
    "业务",
    "公司",
    "策略",
    "操作",
    "风险",
    "来自",
    "分钟",
    "前",
    "转发",
    "评论",
    "保守",
    "止盈",
    "波段",
    "位置",
    "流通",
    "相关股",
    "也继续",
    "产业链",
    "产业的",
    "投资机",
    "总销量",
    "销量",
    "交付量",
    "商店",
    "研究院",
    "金融科技",
    "资产证券",
    "资产证券化",
    "非存款",
    "抵押品",
    "信贷",
    "权重",
    "盘面",
    "补跌",
    "奢侈品",
    "煤炭",
    "主管",
    "报业",
    "活跃",
    "一如既往",
    "企业服",
    "本集团",
    "激光雷达产",
    "非常",
    "点赞",
    "收藏",
    "回复",
    "讨论",
    "最热",
    "最新",
    "最早",
    "下午",
    "猫大人",
    "出货量",
)

# Sector / theme / concept names (a basket of stocks, not one instrument).
# Matched EXACTLY against the alias, never as a substring.
CN_SECTOR_THEME_TERMS: frozenset[str] = frozenset(
    {
        # --- observed in F2 LLM proposal eval (2026-06-26) ---
        "券商",
        "保险",
        "机器人",
        "创新药",
        "中概",
        "新消费",
        "标普消费",
        # --- common A-share / market sector & theme 泛称 ---
        "科技",
        "医药",
        "半导体",
        "光伏",
        "新能源",
        "白酒",
        "煤炭",
        "有色",
        "军工",
        "消费",
        "金融",
        "地产",
        "银行",
        "证券",
        "芯片",
        "算力",
        "赛道",
        "题材",
        "概念",
        "板块",
        "大盘",
        "蓝筹",
        "成长股",
        "价值股",
        "权重股",
    }
)

# ── Ambiguous bare broker aliases (context-gated, never silently anchored) ──
#
# Upper-case tokens (matched when the alias is ALL-CAPS and ≤4 chars) that are
# common English words, finance/legal abbreviations, legal-entity suffixes, or
# timezones. A bare hit is presumed NOT to be the ticker unless an explicit
# ticker context is adjacent. Confirmed false-positive cases from the broker
# F2 acceptance run (2026-07-17): KEY ("KEY DEFINITIONS"), SE ("UBS Europe
# SE"), ET ("4:00 PM ET"), SI ("SI 2017/1064"), IQ ("S&P Capital IQ").
AMBIGUOUS_BARE_UPPER_TOKENS: frozenset[str] = frozenset(
    {
        # --- confirmed false-positive tickers (2026-07-17 acceptance) ---
        "KEY",
        "SE",
        "ET",
        "SI",
        "IQ",
        # --- English function / ultra-common words (ALL-CAPS headings,
        #     disclaimers, boilerplate) ---
        "AN",
        "AND",
        "ANY",
        "ALL",
        "ARE",
        "AS",
        "AT",
        "BE",
        "BEST",
        "BUT",
        "BUY",
        "CAN",
        "DID",
        "DO",
        "EACH",
        "END",
        "ETC",
        "FOR",
        "FREE",
        "FROM",
        "FULL",
        "GO",
        "HAD",
        "HAS",
        "HAVE",
        "HE",
        "HER",
        "HIGH",
        "HIS",
        "HOLD",
        "HOW",
        "IF",
        "IN",
        "IS",
        "IT",
        "ITS",
        "LOW",
        "MAY",
        "ME",
        "MORE",
        "MOST",
        "MY",
        "NEXT",
        "NO",
        "NON",
        "NOR",
        "NOT",
        "NOW",
        "OF",
        "OFF",
        "ON",
        "ONE",
        "ONLY",
        "OR",
        "OUR",
        "OUT",
        "OVER",
        "OWN",
        "PAGE",
        "PART",
        "PAST",
        "PER",
        "PLAN",
        "RISK",
        "SAME",
        "SEE",
        "SELL",
        "SHE",
        "SO",
        "SOME",
        "SUCH",
        "THAN",
        "THAT",
        "THE",
        "THEY",
        "THIS",
        "TIME",
        "TO",
        "TOP",
        "TWO",
        "UP",
        "UPON",
        "USE",
        "VERY",
        "VIEW",
        "WAS",
        "WAY",
        "WE",
        "WELL",
        "WERE",
        "WHAT",
        "WHEN",
        "WHO",
        "WHY",
        "WILL",
        "WITH",
        "YEAR",
        "YET",
        "YOU",
        # --- officer / desk abbreviations common in report prose ---
        "COO",
        "BOE",  # Bank of England in macro text, not BOE Varitronix
        # --- legal-entity suffixes ("UBS Europe SE", "Adyen NV") ---
        "AG",
        "AB",
        "ASA",
        "BV",
        "CO",
        "GMBH",
        "INC",
        "KK",
        "LLC",
        "LLP",
        "LP",
        "LTD",
        "NV",
        "OYJ",
        "PLC",
        "SA",
        "SPA",
        # --- timezones ("4:00 PM ET") ---
        "PT",
        "CT",
        "MT",
        "EST",
        "EDT",
        "CST",
        "CDT",
        "MST",
        "MDT",
        "PST",
        "PDT",
        "BST",
        "CET",
        "CEST",
        "HKT",
        "JST",
        "SGT",
        "IST",
        # --- misc abbreviations ---
        "ID",
        "IE",
        "EG",
        "EX",
        "VS",
        "VIA",
        "QTR",
        "YTD",
        "QOQ",
        "YOY",
        "FY",
        # --- broker rating abbreviations (MSCI OW/EW/UW, Market-Perform). These
        #     collide with real tickers (MP Materials, EW Edwards Lifesciences),
        #     so CONTEXT-GATE — don't drop — them: bare "Equal-weight: EW" /
        #     "Market Perform (MP)" prose must not silently anchor as a ticker,
        #     but "EW.N" / "(MP)" with ticker context still does. Fixes the C9
        #     broker false positives (裸 EW 撞 MSCI 评级术语). ---
        "OW",
        "EW",
        "UW",
        "MP",
    }
)

# Title-case single common English words used as bare broker aliases
# (lower-case forms; matched when the alias is one Title-case word). Confirmed
# false-positive cases (2026-07-17): Target ("Price Target"), Block (Mumbai
# address "Block B-6"), Stone (analyst surname). Full company names such as
# "Block Inc" are multi-word and never match.
AMBIGUOUS_TITLECASE_WORDS: frozenset[str] = frozenset(
    {
        "target",
        "block",
        "stone",
        "key",
        "array",
    }
)


def is_ambiguous_broker_alias(alias: str) -> bool:
    """True when a broker-registry alias needs an explicit ticker context.

    Two deterministic layers (see module docstring):

    - short ALL-CAPS alias (≤4 chars) that is a common English word /
      abbreviation / legal suffix / timezone (``AMBIGUOUS_BARE_UPPER_TOKENS``);
    - single Title-case common English word (``AMBIGUOUS_TITLECASE_WORDS``).

    Multi-word aliases ("Block Inc") and non-alpha aliases (digit codes have
    their own numeric context gate) never match.
    """
    if not alias or not alias.isascii() or not alias.isalpha():
        return False
    if len(alias) <= 4 and alias.isupper() and alias in AMBIGUOUS_BARE_UPPER_TOKENS:
        return True
    if alias.istitle() and alias.lower() in AMBIGUOUS_TITLECASE_WORDS:
        return True
    return False
