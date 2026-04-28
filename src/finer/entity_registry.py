"""Unified entity registry — single source of truth for ticker/entity mappings.

Consolidates:
- aggregation.EntityLinker.KNOWN_ENTITIES
- enrichment.EntityExtractor.known_tickers
- schemas/trade_action.TradeAction.normalize_ticker() name_mappings
"""

from __future__ import annotations

from typing import Dict, Tuple, Optional

# (normalized_ticker, market, entity_type)
EntityEntry = Tuple[str, str, str]

# Canonical registry — alias → (ticker, market, entity_type)
ENTITY_REGISTRY: Dict[str, EntityEntry] = {
    # ── US Stocks ──────────────────────────────────────────────────────────
    "苹果":     ("AAPL",   "US", "ticker"),
    "Apple":   ("AAPL",   "US", "ticker"),
    "APPLE":   ("AAPL",   "US", "ticker"),
    "AAPL":    ("AAPL",   "US", "ticker"),

    "微软":     ("MSFT",   "US", "ticker"),
    "Microsoft":("MSFT",  "US", "ticker"),
    "MICROSOFT":("MSFT",  "US", "ticker"),
    "MSFT":    ("MSFT",   "US", "ticker"),

    "谷歌":     ("GOOGL",  "US", "ticker"),
    "Google":  ("GOOGL",  "US", "ticker"),
    "GOOGLE":  ("GOOGL",  "US", "ticker"),
    "GOOGL":   ("GOOGL",  "US", "ticker"),

    "亚马逊":   ("AMZN",   "US", "ticker"),
    "Amazon":  ("AMZN",   "US", "ticker"),
    "AMAZON":  ("AMZN",   "US", "ticker"),
    "AMZN":    ("AMZN",   "US", "ticker"),

    "特斯拉":   ("TSLA",   "US", "ticker"),
    "Tesla":   ("TSLA",   "US", "ticker"),
    "TESLA":   ("TSLA",   "US", "ticker"),
    "TSLA":    ("TSLA",   "US", "ticker"),

    "英伟达":   ("NVDA",   "US", "ticker"),
    "NVIDIA":  ("NVDA",   "US", "ticker"),
    "NVDA":    ("NVDA",   "US", "ticker"),

    "META":    ("META",   "US", "ticker"),
    "Facebook":("META",   "US", "ticker"),
    "脸书":     ("META",   "US", "ticker"),

    "AMD":     ("AMD",    "US", "ticker"),
    "超微":     ("AMD",    "US", "ticker"),

    "英特尔":   ("INTC",   "US", "ticker"),
    "INTC":    ("INTC",   "US", "ticker"),

    "奈飞":     ("NFLX",   "US", "ticker"),
    "Netflix": ("NFLX",   "US", "ticker"),
    "NFLX":    ("NFLX",   "US", "ticker"),

    "京东":     ("JD",     "US", "ticker"),
    "JD":      ("JD",     "US", "ticker"),

    "拼多多":   ("PDD",    "US", "ticker"),
    "PDD":     ("PDD",    "US", "ticker"),

    "百度":     ("BIDU",   "US", "ticker"),
    "BIDU":    ("BIDU",   "US", "ticker"),

    "网易":     ("NTES",   "US", "ticker"),
    "NTES":    ("NTES",   "US", "ticker"),

    "腾讯音乐": ("TME",    "US", "ticker"),
    "TME":     ("TME",    "US", "ticker"),

    "富途":     ("FUTU",   "US", "ticker"),
    "FUTU":    ("FUTU",   "US", "ticker"),

    "老虎证券": ("TIGR",   "US", "ticker"),
    "TIGR":    ("TIGR",   "US", "ticker"),

    # ── HK Stocks ──────────────────────────────────────────────────────────
    "腾讯":     ("0700.HK", "HK", "ticker"),
    "腾讯控股": ("0700.HK", "HK", "ticker"),
    "TCEHY":   ("0700.HK", "HK", "ticker"),
    "0700":    ("0700.HK", "HK", "ticker"),

    "阿里巴巴": ("9988.HK", "HK", "ticker"),
    "阿里":     ("9988.HK", "HK", "ticker"),
    "BABA":    ("9988.HK", "HK", "ticker"),

    "美团":     ("3690.HK", "HK", "ticker"),
    "3690":    ("3690.HK", "HK", "ticker"),

    "小米":     ("1810.HK", "HK", "ticker"),
    "1810":    ("1810.HK", "HK", "ticker"),

    "比亚迪":   ("1211.HK", "HK", "ticker"),
    "1211":    ("1211.HK", "HK", "ticker"),

    "理想汽车": ("LI",     "US", "ticker"),
    "理想":     ("LI",     "US", "ticker"),
    "LI":      ("LI",     "US", "ticker"),

    "蔚来":     ("NIO",    "US", "ticker"),
    "NIO":     ("NIO",    "US", "ticker"),

    "小鹏":     ("XPEV",   "US", "ticker"),
    "XPEV":    ("XPEV",   "US", "ticker"),

    # ── CN Stocks ──────────────────────────────────────────────────────────
    "茅台":     ("600519.SH", "CN", "ticker"),
    "贵州茅台": ("600519.SH", "CN", "ticker"),

    "宁德时代": ("300750.SZ", "CN", "ticker"),
    "宁德":     ("300750.SZ", "CN", "ticker"),

    "中国平安": ("601318.SH", "CN", "ticker"),
    "平安":     ("601318.SH", "CN", "ticker"),

    "招商银行": ("600036.SH", "CN", "ticker"),

    "海康威视": ("002415.SZ", "CN", "ticker"),
    "隆基绿能": ("601012.SH", "CN", "ticker"),
    "紫金矿业": ("601899.SH", "CN", "ticker"),
    "立讯精密": ("002475.SZ", "CN", "ticker"),
    "寒武纪":   ("688256.SH", "CN", "ticker"),
    "五粮液":   ("000858.SZ", "CN", "ticker"),

    # ── CN Indices ─────────────────────────────────────────────────────────
    "大A":     ("000001.SH", "CN", "index"),
    "A股":     ("000001.SH", "CN", "index"),
    "上证":     ("000001.SH", "CN", "index"),
    "上证指数": ("000001.SH", "CN", "index"),
    "深证":     ("399001.SZ", "CN", "index"),
    "创业板":   ("399006.SZ", "CN", "index"),
    "沪深300": ("000300.SH", "CN", "index"),
    "中证500": ("000905.SH", "CN", "index"),

    # ── Crypto ─────────────────────────────────────────────────────────────
    "比特币":   ("BTC", "CRYPTO", "crypto"),
    "BTC":     ("BTC", "CRYPTO", "crypto"),
    "以太坊":   ("ETH", "CRYPTO", "crypto"),
    "ETH":     ("ETH", "CRYPTO", "crypto"),

    # ── Others (from enrichment, mapped to real tickers) ───────────────────
    "禾赛":     ("HSAI",  "US", "ticker"),
    "泡泡玛特": ("9992.HK", "HK", "ticker"),

    # ── Cat Lord fixture entities (net-new, others updated in-place above) ───
    "宝丰能源": ("600989.SH", "CN", "ticker"),
    "600989":  ("600989.SH", "CN", "ticker"),

    "阿特斯":   ("CSIQ",   "US", "ticker"),
    "阿特斯太阳能": ("CSIQ", "US", "ticker"),
    "CSIQ":    ("CSIQ",   "US", "ticker"),

    # ── Sectors / Themes ────────────────────────────────────────────────────
    "绿电":     ("GREEN_POWER", "CN", "sector"),
    "储能":     ("ENERGY_STORAGE", "CN", "sector"),
    "算电协同": ("COMPUTE_POWER", "CN", "sector"),
    "新能源":   ("NEW_ENERGY", "CN", "sector"),
    "光模块":   ("OPTICAL_MODULE", "CN", "sector"),
}


def resolve(name: str) -> Optional[EntityEntry]:
    """Resolve an entity name/alias to (ticker, market, entity_type)."""
    return ENTITY_REGISTRY.get(name)


def normalize_ticker(name: str) -> str:
    """Normalize a name to its canonical ticker. Returns input if not found."""
    entry = ENTITY_REGISTRY.get(name)
    if entry:
        return entry[0]
    # Try uppercase
    entry = ENTITY_REGISTRY.get(name.upper())
    if entry:
        return entry[0]
    return name


def get_market(name: str) -> Optional[str]:
    """Get the market for an entity name."""
    entry = ENTITY_REGISTRY.get(name)
    return entry[1] if entry else None
