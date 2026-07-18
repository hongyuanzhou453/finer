"""F2 EntityAnchor deterministic producer — registry alias scan.

确定性层: 精确扫描 `entity_registry` 别名在 block 文本中的出现，构造高置信
EntityAnchor。零 LLM 成本、可审计、可复现。

匹配规则 (解决短码子串误命中):
- 中文别名 ("腾讯"): 直接子串匹配 (CJK 子串误匹配概率低)。
- 英文/数字别名 ("NVDA"/"0700"/"LI"): 词边界匹配 (前后非字母数字)，避免
  "LI" 误命中 "QUALITY"、"0700" 误命中 "070012"。
- 纯数字别名 ("0700"/"2498"/"600989"): 词边界之外还要过数字上下文门——
  电话/传真号码模式一律拒绝 (UBS "+61-2-9324 2498" 曾被锚成 2498.HK)，
  且必须带 ticker 上下文 (紧邻括号、交易所后缀、行情/代码类词)。
- 歧义裸别名 (broker 层的 KEY/SE/ET/SI/IQ/Target/Block/Stone 类常见词):
  与数字门同等待遇——必须带显式 ticker 上下文 (紧邻括号 "(KEY)"、交易所
  后缀 "KEY.N"、Ticker:/代码 前导词、Bloomberg "KEY US Equity") 才锚定。
  歧义集合来自 broker registry 的 `requires_context` 标记 ∪ 加载期
  `entity_stoplist.is_ambiguous_broker_alias` 分类器；策展 KOL 别名不受影响。

Registry 分层: 策展 KOL registry (`finer.entity_registry.ENTITY_REGISTRY`)
为主层；broker 语料生成的 `configs/entity_registry_broker.yaml`
(`enrichment.broker_entity_registry`) 作为追加来源，alias 冲突时策展条目优先。

同一 ticker 的多个别名 / 多次出现合并为单个 envelope 级 EntityAnchor，所有
出现位置记入 `metadata.occurrences`，供 F2 EvidenceSpan (步骤 5) 消费。

LLM 发现层与 registry-gap 路由见
docs/specs/2026-06-14-f2-anchoring-design.md。
"""

from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, NamedTuple, Tuple

from finer.entity_registry import EntityEntry
from finer.enrichment.broker_entity_registry import (
    load_context_required_aliases,
    load_generic_ticker_context_patterns,
    merged_registry,
)
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.quality import QualityCard
from finer.schemas.temporal import TemporalAnchor

# registry entity_type → schema ENTITY_TYPE_LITERAL
# registry 用 "ticker"/"index"/"crypto"/"sector"；schema literal 无 "ticker"，映射为 "stock"
_TYPE_MAP: Dict[str, str] = {
    "ticker": "stock",
    "etf": "etf",
    "index": "index",
    "crypto": "crypto",
    "commodity": "commodity",
    "sector": "sector",
}


def _is_cjk(text: str) -> bool:
    """True if text contains any CJK character."""
    return any("一" <= c <= "鿿" for c in text)


class _AliasTables(NamedTuple):
    """Precompiled scan tables for one merged-registry snapshot."""

    registry: Dict[str, EntityEntry]
    ascii_patterns: List[Tuple[str, "re.Pattern[str]"]]
    cjk_aliases: List[str]
    context_required: frozenset[str]


# 预编译缓存: 按 merged registry 的 alias 集合失效 (broker YAML 重生成 →
# broker_entity_registry 的 mtime 缓存换新 dict → alias 集合变化 → 重编译)。
_alias_tables_cache: _AliasTables | None = None


def _alias_tables() -> _AliasTables:
    """Build (and cache) word-boundary patterns over the merged registry.

    ASCII (英文/数字) 别名预编译词边界 pattern；CJK 别名走子串匹配。
    """
    global _alias_tables_cache
    registry = merged_registry()
    context_required = load_context_required_aliases()
    cached = _alias_tables_cache
    if (
        cached is not None
        and cached.registry.keys() == registry.keys()
        and cached.context_required == context_required
    ):
        return cached
    ascii_patterns = [
        (alias, re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"))
        for alias in registry
        if not _is_cjk(alias)
    ]
    cjk_aliases = [alias for alias in registry if _is_cjk(alias)]
    tables = _AliasTables(registry, ascii_patterns, cjk_aliases, context_required)
    _alias_tables_cache = tables
    return tables


def clear_alias_table_cache() -> None:
    """Drop the compiled alias tables (test hook)."""
    global _alias_tables_cache
    _alias_tables_cache = None


class Hit(NamedTuple):
    """One registry alias occurrence in a text."""

    alias: str
    ticker: str
    market: str
    schema_type: str
    start: int
    end: int


class TemporalHit(NamedTuple):
    """One deterministic temporal expression occurrence in a block."""

    raw_text: str
    resolved_time: datetime
    confidence: float
    resolution_strategy: str
    rule: str
    start: int
    end: int
    resolved_end_time: datetime | None = None
    temporal_granularity: str = "day"


_FULL_DATE_PATTERN = re.compile(
    r"(?<!\d)(20\d{2})(?:年\s*|[-/.])"
    r"(0?[1-9]|1[0-2])(?:月\s*|[-/.])"
    r"(0?[1-9]|[12]\d|3[01])日?(?!\d)"
)
_CN_MONTH_DAY_PATTERN = re.compile(
    r"(?<![\d年月])"
    r"(0?[1-9]|1[0-2])月"
    r"(0?[1-9]|[12]\d|3[01])日"
    r"(?!\d)"
)
_EVENT_MONTH_DAY_PATTERN = re.compile(
    r"(?<![\d./-])"
    r"(0?[1-9]|1[0-2])[./](0?[1-9]|[12]\d|3[01])"
    r"(?![\d./-])"
)
_RELATIVE_WEEKDAY_PATTERN = re.compile(r"(上周|本周|这周|下周)([一二三四五六日天])")
_RELATIVE_EVENT_CUES = (
    "非农",
    "CPI",
    "PPI",
    "FOMC",
    "议息",
    "财报",
    "业绩",
    "会议",
)
_RELATIVE_DAY_TERMS = {
    "今天": 0,
    "今日": 0,
    "明天": 1,
    "明日": 1,
    "昨天": -1,
    "昨日": -1,
}
_RELATIVE_WEEK_TERMS = {
    "上周": -1,
    "本周": 0,
    "这周": 0,
    "下周": 1,
}
_RELATIVE_MONTH_TERMS = {
    "上月": -1,
    "本月": 0,
    "这个月": 0,
    "下月": 1,
}
_CN_WEEKDAY_INDEX = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


# ── 纯数字别名上下文门 (F2 numeric-alias context gate) ───────────────────────
# 负规则: 命中电话/传真号码模式一律拒绝。实锤案例: UBS 落款
# "+61-2-9324 2498" 中的 "2498" 曾被锚成 2498.HK (速腾聚创)。
# 紧邻前缀是「数字+分隔符」→ 电话号码分组 (如 "9324 2498")
_NUMERIC_PHONE_PREFIX_RE = re.compile(r"\d[\s\-–—.]$")
# 前向窗口内出现「+国家码-」拨号前缀 (如 "+61-2-…" / "＋86 10 …")
_NUMERIC_PHONE_PLUS_RE = re.compile(r"[+＋]\(?\d{1,4}\)?[\s\-–—.]")
# 紧邻后缀是「分隔符+4位以上数字」→ 电话号码延续分组
_NUMERIC_PHONE_SUFFIX_RE = re.compile(r"^[\s\-–—.]\d{4}")
_NUMERIC_TEL_WORDS = ("tel", "fax", "phone", "电话", "传真", "转分机")
_NUMERIC_TEL_WINDOW = 24
_NUMERIC_PHONE_PLUS_WINDOW = 16

# 正规则: 纯数字别名必须带 ticker 上下文之一才算命中。
_NUMERIC_OPEN_BRACKETS = "（([【"
_NUMERIC_CLOSE_BRACKETS = "）)]】"
# 交易所后缀紧跟其后 ("2498.HK" / "600519.SS")
_NUMERIC_EXCHANGE_SUFFIX_RE = re.compile(
    r"^\.(HK|SH|SZ|SS|TW|T|US|N|O|OQ)(?![A-Za-z0-9])", re.IGNORECASE
)
# Bloomberg 风格交易所码紧跟其后 ("700 HK Equity" / "2330 TT")
_NUMERIC_BLOOMBERG_RE = re.compile(r"^ (HK|CH|US|TT|JP|KS)(?![A-Za-z0-9])")
# 「股份」「代码」类词 + 行情动词, 在 ±12 字窗口内即视为 ticker 上下文
_NUMERIC_CONTEXT_TERMS = (
    "代码",
    "股",
    "证券",
    "收盘",
    "开盘",
    "涨",
    "跌",
    "买入",
    "卖出",
    "增持",
    "减持",
    "持有",
    "评级",
    "目标价",
    "上市",
    "公司",
)
_NUMERIC_CONTEXT_WINDOW = 12
_NUMERIC_TITLE_PATTERN_WINDOW = 40


def numeric_alias_context_ok(text: str, start: int, end: int) -> bool:
    """Gate one digit-only alias hit on its surrounding context.

    Reject phone/fax number patterns outright; otherwise require an explicit
    ticker context (adjacent bracket, exchange suffix, Bloomberg exchange code,
    or a 股份/代码/行情 term nearby). Report-title patterns from the broker
    negative rules (``generic_ticker_context_patterns``) also reject.
    """
    before = text[max(0, start - _NUMERIC_TEL_WINDOW):start]
    after = text[end:end + _NUMERIC_TEL_WINDOW]

    # ── 负规则: 电话/传真模式 ──
    if _NUMERIC_PHONE_PREFIX_RE.search(before):
        return False
    if _NUMERIC_PHONE_PLUS_RE.search(text[max(0, start - _NUMERIC_PHONE_PLUS_WINDOW):start]):
        return False
    if _NUMERIC_PHONE_SUFFIX_RE.match(after):
        return False
    window_folded = (before + after).casefold()
    if any(term in window_folded for term in _NUMERIC_TEL_WORDS):
        return False

    # ── 负规则: 研报标题类噪声上下文 (来源: entities.yaml 负规则) ──
    title_window = (
        text[max(0, start - _NUMERIC_TITLE_PATTERN_WINDOW):start]
        + text[end:end + _NUMERIC_TITLE_PATTERN_WINDOW]
    )
    for pattern in load_generic_ticker_context_patterns():
        if pattern in title_window:
            return False

    # ── 正规则: 必须带 ticker 上下文 ──
    if start > 0 and text[start - 1] in _NUMERIC_OPEN_BRACKETS:
        return True
    if end < len(text) and text[end] in _NUMERIC_CLOSE_BRACKETS:
        return True
    if _NUMERIC_EXCHANGE_SUFFIX_RE.match(text[end:end + 6]):
        return True
    if _NUMERIC_BLOOMBERG_RE.match(text[end:end + 8]):
        return True
    context = (
        text[max(0, start - _NUMERIC_CONTEXT_WINDOW):start]
        + text[end:end + _NUMERIC_CONTEXT_WINDOW]
    )
    return any(term in context for term in _NUMERIC_CONTEXT_TERMS)


# ── 歧义裸别名上下文门 (F2 ambiguous bare-alias context gate) ─────────────────
# broker registry 的 KEY/SE/ET/SI/IQ/Target/Block/Stone 类别名与常见英文词、
# 法律实体后缀、时区缩写同形。裸出现默认拒绝，必须命中显式 ticker 上下文:
#   1. 双侧紧邻括号:            "KeyCorp (KEY)" / "速腾聚创（KEY）"
#   2. 括号 + Bloomberg 交易所:  "Sea Ltd (SE US)"
#   3. 交易所后缀紧跟其后:       "KEY.N" / "SE.OQ"
#   4. Ticker:/代码 前导词:      "Ticker: KEY" / "股票代码 KEY"
#   5. Bloomberg Equity 全形式:  "KEY US Equity"
# 实锤假阳性 (2026-07-17 验收): "KEY DEFINITIONS"、"UBS Europe SE"、
# "Price Target"、"Block B-6" (孟买地址)、"4:00 PM ET"、"SI 2017/1064"、
# 分析师人名 "Stone"、"S&P Capital IQ"。
_BARE_TICKER_LEAD_RE = re.compile(
    r"(?:ticker|symbol|股票代码|代码)\s*[:：]?\s*$", re.IGNORECASE
)
_BARE_TICKER_LEAD_WINDOW = 12
_BARE_BRACKET_EXCHANGE_RE = re.compile(
    r"^\s+(?:US|UN|UW|HK|CH|TT|JP|GR|LN|SS|SZ)\s*[）)\]】]"
)
_BARE_BLOOMBERG_EQUITY_RE = re.compile(
    r"^ (?:US|UN|UW|HK|CH|TT|JP|GR|LN) Equity(?![A-Za-z0-9])"
)


def bare_alias_context_ok(text: str, start: int, end: int) -> bool:
    """Gate one ambiguous bare-alias hit on its surrounding context.

    Same posture as ``numeric_alias_context_ok``: default-reject, anchor only
    with an explicit ticker context. Applied to broker-layer aliases flagged
    ``requires_context`` (common English words / legal suffixes / timezones);
    full-name aliases like "Block Inc" or "iQIYI" are separate registry
    entries and are never gated here.
    """
    prev_open = start > 0 and text[start - 1] in _NUMERIC_OPEN_BRACKETS
    after = text[end:end + 16]

    # 1/2. 双侧紧邻括号 (可含 Bloomberg 交易所码): "(KEY)" / "(SE US)"
    if prev_open:
        if end < len(text) and text[end] in _NUMERIC_CLOSE_BRACKETS:
            return True
        if _BARE_BRACKET_EXCHANGE_RE.match(after):
            return True

    # 3. 交易所后缀紧跟其后: "KEY.N"
    if _NUMERIC_EXCHANGE_SUFFIX_RE.match(text[end:end + 6]):
        return True

    # 4. Ticker:/代码 前导词
    before = text[max(0, start - _BARE_TICKER_LEAD_WINDOW):start]
    if _BARE_TICKER_LEAD_RE.search(before):
        return True

    # 5. Bloomberg Equity 全形式: "KEY US Equity"
    if _BARE_BLOOMBERG_EQUITY_RE.match(after):
        return True

    return False


def scan_text(text: str) -> List[Hit]:
    """Scan one text for all registry alias occurrences."""
    if not text:
        return []
    tables = _alias_tables()
    registry = tables.registry
    hits: List[Hit] = []
    # 中文别名: 子串匹配，记录所有出现位置
    for alias in tables.cjk_aliases:
        ticker, market, etype = registry[alias]
        schema_type = _TYPE_MAP.get(etype, "unknown")
        start = text.find(alias)
        while start != -1:
            hits.append(Hit(alias, ticker, market, schema_type, start, start + len(alias)))
            start = text.find(alias, start + 1)
    # 英文/数字别名: 词边界匹配，避免短码子串误命中
    for alias, pat in tables.ascii_patterns:
        ticker, market, etype = registry[alias]
        schema_type = _TYPE_MAP.get(etype, "unknown")
        digit_only = alias.isascii() and alias.isdigit()
        needs_context = alias in tables.context_required
        for m in pat.finditer(text):
            if digit_only and not numeric_alias_context_ok(text, m.start(), m.end()):
                continue
            if needs_context and not bare_alias_context_ok(text, m.start(), m.end()):
                continue
            hits.append(Hit(alias, ticker, market, schema_type, m.start(), m.end()))
    return hits


def anchor_entities_deterministic(blocks: List[Tuple[str, str]]) -> List[EntityAnchor]:
    """Build envelope-level EntityAnchors from blocks via deterministic registry scan.

    Args:
        blocks: list of ``(block_id, text)`` pairs.

    Returns:
        List of EntityAnchor — one per resolved ticker, with all occurrences
        (block_id + char offsets) recorded in ``metadata.occurrences`` for
        downstream EvidenceSpan construction. confidence is 1.0 (exact match).
    """
    # ticker -> aggregated mentions
    agg: Dict[str, Dict[str, Any]] = {}
    for block_id, text in blocks:
        for h in scan_text(text):
            slot = agg.setdefault(
                h.ticker,
                {"market": h.market, "schema_type": h.schema_type, "aliases": [], "occurrences": []},
            )
            if h.alias not in slot["aliases"]:
                slot["aliases"].append(h.alias)
            slot["occurrences"].append(
                {"block_id": block_id, "alias": h.alias, "char_start": h.start, "char_end": h.end}
            )

    anchors: List[EntityAnchor] = []
    for ticker, slot in agg.items():
        aliases = slot["aliases"]
        # raw_text: 取最长别名 (最具体，如 "腾讯控股" 优先于 "腾讯")
        raw = max(aliases, key=len)
        anchors.append(
            EntityAnchor(
                entity_type=slot["schema_type"],
                raw_text=raw,
                resolved_symbol=ticker,
                resolved_name=None,  # registry 不存规范名；display 回退到 symbol
                market=slot["market"],
                confidence=1.0,
                aliases=sorted(aliases),
                metadata={
                    "layer": "deterministic_registry",
                    "match": "registry_exact",
                    "occurrences": slot["occurrences"],
                    "mention_count": len(slot["occurrences"]),
                },
            )
        )
    anchors.sort(key=lambda a: a.resolved_symbol or "")
    return anchors


def anchor_envelope_deterministic(envelope: Dict[str, Any]) -> List[EntityAnchor]:
    """Convenience: run deterministic anchoring over an envelope dict's blocks."""
    blocks = [
        (b.get("block_id", ""), b.get("text", "") or "")
        for b in envelope.get("blocks", [])
    ]
    return anchor_entities_deterministic(blocks)


def _stable_id(prefix: str, *parts: Any) -> str:
    """Build a deterministic stage-local ID from immutable source coordinates."""
    payload = "\x1f".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _envelope_to_dict(envelope: ContentEnvelope | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(envelope, ContentEnvelope):
        return envelope.model_dump(mode="json")
    return copy.deepcopy(envelope)


def _f0_metadata(f0_record: ContentRecord | Dict[str, Any] | None) -> Dict[str, Any]:
    if f0_record is None:
        return {}
    if isinstance(f0_record, ContentRecord):
        return f0_record.model_dump(mode="json")
    return copy.deepcopy(f0_record)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _timezone_name(dt: datetime) -> str | None:
    if dt.tzinfo is None:
        return None
    return dt.tzinfo.tzname(dt)


def _with_reference_timezone(value: datetime, reference: datetime | None) -> datetime:
    if value.tzinfo is not None or reference is None or reference.tzinfo is None:
        return value
    return value.replace(tzinfo=reference.tzinfo)


def _date_at_midnight(
    year: int,
    month: int,
    day: int,
    *,
    reference: datetime | None,
) -> datetime | None:
    try:
        return _with_reference_timezone(
            datetime.combine(datetime(year, month, day).date(), time.min),
            reference,
        )
    except ValueError:
        return None


def _period_end_exclusive(start: datetime, *, days: int) -> datetime:
    return start + timedelta(days=days)


def _month_start(reference: datetime, *, offset: int = 0) -> datetime:
    month_index = reference.year * 12 + reference.month - 1 + offset
    year = month_index // 12
    month = month_index % 12 + 1
    return _with_reference_timezone(datetime.combine(datetime(year, month, 1).date(), time.min), reference)


def _week_start(reference: datetime, *, offset_weeks: int = 0) -> datetime:
    ref_day = _with_reference_timezone(
        datetime.combine(reference.date(), time.min),
        reference,
    )
    return ref_day - timedelta(days=ref_day.weekday()) + timedelta(days=offset_weeks * 7)


def _same_day(reference: datetime, *, offset_days: int = 0) -> datetime:
    return _with_reference_timezone(
        datetime.combine(reference.date(), time.min),
        reference,
    ) + timedelta(days=offset_days)


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(start < used_end and used_start < end for used_start, used_end in occupied)


def _event_cue_near(text: str, *, start: int, end: int) -> bool:
    window = text[end: min(len(text), end + 10)]
    return any(cue in window for cue in _RELATIVE_EVENT_CUES)


def build_published_at_temporal_anchor(
    published_at: Any,
    *,
    source_record_id: str,
) -> TemporalAnchor | None:
    """Build a stable F2 ``published_at`` TemporalAnchor when time is explicit."""
    resolved = _parse_datetime(published_at)
    if resolved is None:
        return None
    resolved_iso = resolved.isoformat()
    return TemporalAnchor(
        anchor_id=_stable_id("time", source_record_id, "published_at", resolved_iso),
        anchor_type="published_at",
        raw_text="published_at",
        resolved_time=resolved,
        confidence=1.0,
        resolution_strategy="explicit_date",
        timezone=_timezone_name(resolved),
        metadata={
            "stage": "F2",
            "layer": "deterministic_temporal",
            "source_field": "published_at",
            "source_record_id": source_record_id,
        },
    )


def scan_explicit_temporal_expressions(
    text: str,
    *,
    published_at: Any = None,
) -> List[TemporalHit]:
    """Scan block text for high-precision explicit date expressions.

    Deliberately avoids numeric-only month/day forms like ``4.1`` or ``10/15``
    because local F1 blocks contain many prices, ratios, and hit-rate strings
    with the same shape.
    """
    if not text:
        return []
    reference = _parse_datetime(published_at)
    hits: list[TemporalHit] = []
    occupied: list[tuple[int, int]] = []

    for match in _FULL_DATE_PATTERN.finditer(text):
        resolved = _date_at_midnight(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            reference=reference,
        )
        if resolved is None:
            continue
        hits.append(
            TemporalHit(
                raw_text=match.group(0),
                resolved_time=resolved,
                confidence=1.0,
                resolution_strategy="explicit_date",
                rule="full_date",
                start=match.start(),
                end=match.end(),
            )
        )
        occupied.append((match.start(), match.end()))

    if reference is None:
        return sorted(hits, key=lambda hit: (hit.start, hit.end, hit.raw_text))

    for match in _CN_MONTH_DAY_PATTERN.finditer(text):
        if any(match.start() < end and start < match.end() for start, end in occupied):
            continue
        resolved = _date_at_midnight(
            reference.year,
            int(match.group(1)),
            int(match.group(2)),
            reference=reference,
        )
        if resolved is None:
            continue
        hits.append(
            TemporalHit(
                raw_text=match.group(0),
                resolved_time=resolved,
                confidence=0.9,
                resolution_strategy="rule_based",
                rule="month_day_from_published_year",
                start=match.start(),
                end=match.end(),
            )
        )

    return sorted(hits, key=lambda hit: (hit.start, hit.end, hit.raw_text))


def scan_relative_temporal_expressions(
    text: str,
    *,
    published_at: Any = None,
) -> List[TemporalHit]:
    """Scan block text for deterministic relative date expressions.

    Rules intentionally require an explicit ``published_at`` reference. F2 does
    not infer relative dates from ingestion time or wall-clock time.
    """
    if not text:
        return []
    reference = _parse_datetime(published_at)
    if reference is None:
        return []

    hits: list[TemporalHit] = []
    occupied: list[tuple[int, int]] = []

    for match in _RELATIVE_WEEKDAY_PATTERN.finditer(text):
        week_offset = _RELATIVE_WEEK_TERMS[match.group(1)]
        weekday = _CN_WEEKDAY_INDEX[match.group(2)]
        resolved = _week_start(reference, offset_weeks=week_offset) + timedelta(days=weekday)
        hits.append(
            TemporalHit(
                raw_text=match.group(0),
                resolved_time=resolved,
                confidence=0.85,
                resolution_strategy="relative_date",
                rule="relative_weekday_from_published_at",
                start=match.start(),
                end=match.end(),
            )
        )
        occupied.append((match.start(), match.end()))

    for term, offset in _RELATIVE_DAY_TERMS.items():
        start = text.find(term)
        while start != -1:
            end = start + len(term)
            if not _overlaps(start, end, occupied):
                hits.append(
                    TemporalHit(
                        raw_text=term,
                        resolved_time=_same_day(reference, offset_days=offset),
                        confidence=0.85,
                        resolution_strategy="relative_date",
                        rule="relative_day_from_published_at",
                        start=start,
                        end=end,
                    )
                )
                occupied.append((start, end))
            start = text.find(term, start + 1)

    for term, offset in _RELATIVE_WEEK_TERMS.items():
        start = text.find(term)
        while start != -1:
            end = start + len(term)
            if not _overlaps(start, end, occupied):
                resolved = _week_start(reference, offset_weeks=offset)
                hits.append(
                    TemporalHit(
                        raw_text=term,
                        resolved_time=resolved,
                        confidence=0.8,
                        resolution_strategy="relative_date",
                        rule="relative_week_from_published_at",
                        start=start,
                        end=end,
                        resolved_end_time=_period_end_exclusive(resolved, days=7),
                        temporal_granularity="week",
                    )
                )
                occupied.append((start, end))
            start = text.find(term, start + 1)

    for term, offset in _RELATIVE_MONTH_TERMS.items():
        start = text.find(term)
        while start != -1:
            end = start + len(term)
            if not _overlaps(start, end, occupied):
                resolved = _month_start(reference, offset=offset)
                resolved_end = _month_start(reference, offset=offset + 1)
                hits.append(
                    TemporalHit(
                        raw_text=term,
                        resolved_time=resolved,
                        confidence=0.8,
                        resolution_strategy="relative_date",
                        rule="relative_month_from_published_at",
                        start=start,
                        end=end,
                        resolved_end_time=resolved_end,
                        temporal_granularity="month",
                    )
                )
                occupied.append((start, end))
            start = text.find(term, start + 1)

    for match in _EVENT_MONTH_DAY_PATTERN.finditer(text):
        if _overlaps(match.start(), match.end(), occupied):
            continue
        if not _event_cue_near(text, start=match.start(), end=match.end()):
            continue
        resolved = _date_at_midnight(
            reference.year,
            int(match.group(1)),
            int(match.group(2)),
            reference=reference,
        )
        if resolved is None:
            continue
        hits.append(
            TemporalHit(
                raw_text=match.group(0),
                resolved_time=resolved,
                confidence=0.75,
                resolution_strategy="rule_based",
                rule="numeric_month_day_with_event_cue",
                start=match.start(),
                end=match.end(),
            )
        )
        occupied.append((match.start(), match.end()))

    return sorted(hits, key=lambda hit: (hit.start, hit.end, hit.raw_text))


def scan_deterministic_temporal_expressions(
    text: str,
    *,
    published_at: Any = None,
) -> List[TemporalHit]:
    """Scan block text for all deterministic F2 temporal expressions."""
    hits = scan_explicit_temporal_expressions(text, published_at=published_at)
    occupied = [(hit.start, hit.end) for hit in hits]
    for hit in scan_relative_temporal_expressions(text, published_at=published_at):
        if _overlaps(hit.start, hit.end, occupied):
            continue
        hits.append(hit)
        occupied.append((hit.start, hit.end))
    return sorted(hits, key=lambda hit: (hit.start, hit.end, hit.raw_text))


def _temporal_span_metadata(
    block: Dict[str, Any],
    hit: TemporalHit,
    *,
    source_record_id: str,
    raw_path: str,
) -> Dict[str, Any]:
    metadata = _span_provenance_metadata(
        block,
        Hit(
            alias=hit.raw_text,
            ticker="",
            market="",
            schema_type="",
            start=hit.start,
            end=hit.end,
        ),
        source_record_id=source_record_id,
        raw_path=raw_path,
    )
    metadata.update(
        {
            "layer": "deterministic_temporal",
            "match": hit.rule,
            "resolved_time": hit.resolved_time.isoformat(),
            "resolution_strategy": hit.resolution_strategy,
            "temporal_granularity": hit.temporal_granularity,
        }
    )
    if hit.resolved_end_time is not None:
        metadata["resolved_end_time_exclusive"] = hit.resolved_end_time.isoformat()
    metadata.pop("resolved_symbol", None)
    metadata.pop("market", None)
    return metadata


def _temporal_evidence_span_for_hit(
    block: Dict[str, Any],
    hit: TemporalHit,
    *,
    source_record_id: str,
    raw_path: str,
) -> EvidenceSpan:
    block_id = block.get("block_id") or ""
    span_id = _stable_id(
        "span",
        source_record_id,
        block_id,
        "temporal",
        hit.raw_text,
        hit.start,
        hit.end,
        hit.resolved_time.isoformat(),
    )
    text = block.get("text") or ""
    return EvidenceSpan(
        evidence_span_id=span_id,
        block_id=block_id,
        char_start=hit.start,
        char_end=hit.end,
        text=text[hit.start:hit.end],
        confidence=hit.confidence,
        span_type="temporal",
        metadata=_temporal_span_metadata(
            block,
            hit,
            source_record_id=source_record_id,
            raw_path=raw_path,
        ),
    )


def build_deterministic_temporal_anchors_with_spans(
    envelope: ContentEnvelope | Dict[str, Any],
    *,
    published_at: Any = None,
) -> Tuple[List[TemporalAnchor], Dict[str, List[EvidenceSpan]]]:
    """Build deterministic block-level TemporalAnchors and EvidenceSpans."""
    data = _envelope_to_dict(envelope)
    source_record_id = data.get("source_record_id") or data.get("envelope_id") or "unknown"
    raw_path = data.get("raw_path") or data.get("source_uri") or ""
    anchors: list[TemporalAnchor] = []
    spans_by_block: dict[str, list[EvidenceSpan]] = {}

    for block in data.get("blocks", []):
        block_id = block.get("block_id") or ""
        text = block.get("text") or ""
        for hit in scan_deterministic_temporal_expressions(text, published_at=published_at):
            span = _temporal_evidence_span_for_hit(
                block,
                hit,
                source_record_id=source_record_id,
                raw_path=raw_path,
            )
            anchor = TemporalAnchor(
                anchor_id=_stable_id(
                    "time",
                    source_record_id,
                    block_id,
                    hit.raw_text,
                    hit.start,
                    hit.end,
                    hit.resolved_time.isoformat(),
                ),
                anchor_type="mentioned_at",
                raw_text=hit.raw_text,
                resolved_time=hit.resolved_time,
                confidence=hit.confidence,
                resolution_strategy=hit.resolution_strategy,
                evidence_span_id=span.evidence_span_id,
                timezone=_timezone_name(hit.resolved_time),
                metadata={
                    "stage": "F2",
                    "layer": "deterministic_temporal",
                    "source_field": "block.text",
                    "rule": hit.rule,
                    "block_id": block_id,
                    "char_start": hit.start,
                    "char_end": hit.end,
                    "source_record_id": source_record_id,
                    "temporal_granularity": hit.temporal_granularity,
                },
            )
            if hit.resolved_end_time is not None:
                anchor.metadata["resolved_end_time_exclusive"] = hit.resolved_end_time.isoformat()
            anchors.append(anchor)
            spans_by_block.setdefault(block_id, []).append(span)

    anchors.sort(
        key=lambda a: (
            a.resolved_time.isoformat() if a.resolved_time else "",
            a.raw_text,
            a.anchor_id,
        )
    )
    for spans in spans_by_block.values():
        spans.sort(key=lambda s: (s.char_start, s.char_end, s.text, s.evidence_span_id))
    return anchors, spans_by_block


def build_explicit_temporal_anchors_with_spans(
    envelope: ContentEnvelope | Dict[str, Any],
    *,
    published_at: Any = None,
) -> Tuple[List[TemporalAnchor], Dict[str, List[EvidenceSpan]]]:
    """Backward-compatible wrapper for deterministic temporal anchoring."""
    return build_deterministic_temporal_anchors_with_spans(envelope, published_at=published_at)


def _bbox_json(block: Dict[str, Any]) -> Dict[str, Any] | None:
    bbox = block.get("bbox")
    if not bbox:
        return None
    if isinstance(bbox, dict):
        return copy.deepcopy(bbox)
    if hasattr(bbox, "model_dump"):
        return bbox.model_dump(mode="json")
    return None


def _span_provenance_metadata(
    block: Dict[str, Any],
    hit: Hit,
    *,
    source_record_id: str,
    raw_path: str,
) -> Dict[str, Any]:
    """Build provenance metadata for an F2 evidence span."""
    bbox = _bbox_json(block)
    page_index = block.get("page_index")
    if bbox:
        granularity = "bbox"
    elif page_index is not None:
        granularity = "page"
    else:
        granularity = "file"

    metadata: Dict[str, Any] = {
        "stage": "F2",
        "layer": "deterministic_registry",
        "match": "registry_exact",
        "alias": hit.alias,
        "resolved_symbol": hit.ticker,
        "market": hit.market,
        "source_record_id": source_record_id,
        "raw_path": raw_path,
        "provenance_granularity": granularity,
    }
    if page_index is not None:
        metadata["page_index"] = page_index
    if bbox:
        metadata["bbox"] = bbox
    return metadata


def _evidence_span_for_hit(
    block: Dict[str, Any],
    hit: Hit,
    *,
    source_record_id: str,
    raw_path: str,
) -> EvidenceSpan:
    block_id = block.get("block_id") or ""
    span_id = _stable_id(
        "span",
        source_record_id,
        block_id,
        hit.ticker,
        hit.alias,
        hit.start,
        hit.end,
    )
    text = block.get("text") or ""
    return EvidenceSpan(
        evidence_span_id=span_id,
        block_id=block_id,
        char_start=hit.start,
        char_end=hit.end,
        text=text[hit.start:hit.end],
        confidence=1.0,
        span_type="entity",
        metadata=_span_provenance_metadata(
            block,
            hit,
            source_record_id=source_record_id,
            raw_path=raw_path,
        ),
    )


def _entity_anchor_from_slot(
    ticker: str,
    slot: Dict[str, Any],
    *,
    source_record_id: str,
) -> EntityAnchor:
    aliases = slot["aliases"]
    span_ids = slot["evidence_span_ids"]
    return EntityAnchor(
        entity_anchor_id=_stable_id("entity", source_record_id, ticker),
        entity_type=slot["schema_type"],
        raw_text=max(aliases, key=len),
        resolved_symbol=ticker,
        resolved_name=None,
        market=slot["market"],
        confidence=1.0,
        evidence_span_id=span_ids[0] if span_ids else None,
        aliases=sorted(aliases),
        metadata={
            "layer": "deterministic_registry",
            "match": "registry_exact",
            "occurrences": slot["occurrences"],
            "mention_count": len(slot["occurrences"]),
            "evidence_span_ids": span_ids,
        },
    )


def build_deterministic_entity_anchors_with_spans(
    envelope: ContentEnvelope | Dict[str, Any],
) -> Tuple[List[EntityAnchor], Dict[str, List[EvidenceSpan]]]:
    """Build deterministic EntityAnchors plus per-block EvidenceSpans.

    This is the F2 production helper. Unlike ``anchor_entities_deterministic``
    it assigns stable IDs and materializes one ``EvidenceSpan`` per alias
    occurrence.
    """
    data = _envelope_to_dict(envelope)
    source_record_id = data.get("source_record_id") or data.get("envelope_id") or "unknown"
    raw_path = data.get("raw_path") or data.get("source_uri") or ""
    spans_by_block: Dict[str, List[EvidenceSpan]] = {}
    agg: Dict[str, Dict[str, Any]] = {}

    for block in data.get("blocks", []):
        block_id = block.get("block_id") or ""
        text = block.get("text") or ""
        hits = sorted(
            scan_text(text),
            key=lambda h: (h.start, h.end, h.ticker, h.alias),
        )
        for hit in hits:
            span = _evidence_span_for_hit(
                block,
                hit,
                source_record_id=source_record_id,
                raw_path=raw_path,
            )
            spans_by_block.setdefault(block_id, []).append(span)
            slot = agg.setdefault(
                hit.ticker,
                {
                    "market": hit.market,
                    "schema_type": hit.schema_type,
                    "aliases": [],
                    "occurrences": [],
                    "evidence_span_ids": [],
                },
            )
            if hit.alias not in slot["aliases"]:
                slot["aliases"].append(hit.alias)
            slot["occurrences"].append(
                {
                    "block_id": block_id,
                    "alias": hit.alias,
                    "char_start": hit.start,
                    "char_end": hit.end,
                    "evidence_span_id": span.evidence_span_id,
                }
            )
            slot["evidence_span_ids"].append(span.evidence_span_id)

    anchors = [
        _entity_anchor_from_slot(ticker, slot, source_record_id=source_record_id)
        for ticker, slot in agg.items()
    ]
    anchors.sort(key=lambda a: a.resolved_symbol or "")
    for spans in spans_by_block.values():
        spans.sort(key=lambda s: (s.char_start, s.char_end, s.text, s.evidence_span_id))
    return anchors, spans_by_block


def _update_f2_quality(
    quality_card: Dict[str, Any],
    *,
    hit_block_count: int,
    total_block_count: int,
    temporal_anchor_count: int,
) -> Dict[str, Any]:
    score = round(hit_block_count / total_block_count, 4) if total_block_count else 0.0
    card = QualityCard.model_validate(quality_card)
    updated = card.model_dump()
    updated["entity_resolution_score"] = score
    if temporal_anchor_count:
        updated["temporal_resolution_score"] = max(card.temporal_resolution_score, 1.0)
    updated["evidence_traceability_score"] = max(card.evidence_traceability_score, score)
    return QualityCard.model_validate(updated).model_dump(mode="json")


def build_f2_deterministic_envelope(
    envelope: ContentEnvelope | Dict[str, Any],
    *,
    f0_record: ContentRecord | Dict[str, Any] | None = None,
) -> ContentEnvelope:
    """Copy a F1 envelope and attach deterministic F2 anchors/spans.

    The media-level F1 ``source_type`` is preserved (e.g. ``pdf``). Original F0
    taxonomy is copied into envelope metadata for downstream filtering.
    """
    data = _envelope_to_dict(envelope)
    f0 = _f0_metadata(f0_record)
    source_record_id = data.get("source_record_id") or data.get("envelope_id") or "unknown"
    anchors, spans_by_block = build_deterministic_entity_anchors_with_spans(data)
    published_at = data.get("published_at") or f0.get("published_at")
    temporal_anchor = build_published_at_temporal_anchor(
        published_at,
        source_record_id=source_record_id,
    )
    block_temporal_anchors, temporal_spans_by_block = build_deterministic_temporal_anchors_with_spans(
        data,
        published_at=published_at,
    )
    temporal_anchors = ([temporal_anchor] if temporal_anchor else []) + block_temporal_anchors

    hit_blocks = 0
    for block in data.get("blocks", []):
        block_id = block.get("block_id") or ""
        spans = spans_by_block.get(block_id, []) + temporal_spans_by_block.get(block_id, [])
        spans.sort(key=lambda s: (s.char_start, s.char_end, s.text, s.evidence_span_id))
        block["evidence_spans"] = [s.model_dump(mode="json") for s in spans]
        if spans_by_block.get(block_id):
            hit_blocks += 1

    data["entity_anchors"] = [a.model_dump(mode="json") for a in anchors]
    data["temporal_anchors"] = [a.model_dump(mode="json") for a in temporal_anchors]
    data["quality_card"] = _update_f2_quality(
        data["quality_card"],
        hit_block_count=hit_blocks,
        total_block_count=len(data.get("blocks", [])),
        temporal_anchor_count=len(temporal_anchors),
    )

    metadata = copy.deepcopy(data.get("metadata") or {})
    source_type = f0.get("source_type")
    if source_type:
        metadata["f0_source_type"] = source_type
    if f0.get("source_platform"):
        metadata["f0_source_platform"] = f0["source_platform"]
    metadata["f2_anchor"] = {
        "stage": "F2",
        "layer": "deterministic_registry",
        "method": "registry_exact",
        "entity_anchor_count": len(anchors),
        "temporal_anchor_count": len(temporal_anchors),
        "entity_evidence_span_count": sum(len(v) for v in spans_by_block.values()),
        "temporal_evidence_span_count": sum(len(v) for v in temporal_spans_by_block.values()),
        "evidence_span_count": (
            sum(len(v) for v in spans_by_block.values())
            + sum(len(v) for v in temporal_spans_by_block.values())
        ),
        "hit_block_count": hit_blocks,
        "total_block_count": len(data.get("blocks", [])),
    }
    data["metadata"] = metadata
    return ContentEnvelope.model_validate(data)
