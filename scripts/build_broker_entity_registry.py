"""Build configs/entity_registry_broker.yaml from the broker research corpus.

Sources (both read-only):

1. reports.db (mode=ro) — distinct (company_name, stock_code) pairs mined from
   the broker research intake corpus.
2. The research repo's curated entities.yaml — positive rules
   (ticker_company_aliases, company_alias_canonical) and negative rules
   (ambiguous_text_tickers, non_company_tickers, company_noise_prefixes,
   generic_ticker_context_patterns).

Output: an AUTO-GENERATED, committable YAML consumed by
``finer.enrichment.broker_entity_registry`` as the append-only broker layer of
the F2 deterministic registry. Curated KOL registry aliases always win; the
generator therefore skips any alias already present in
``finer.entity_registry.ENTITY_REGISTRY``.

Cleaning rules applied at build time (precision over recall):

- stock_code dirt (PRC/China style non-tickers, currency/region codes,
  ambiguous 1-2 letter codes, NOISY_UPPER_TOKENS) is rejected.
- codes are normalized through the explicit suffix tables in
  ``finer.enrichment.ticker_normalization`` (RIC .N/.OQ → US bare,
  .SS → .SH, bare 6-digit by CN segment, bare letters → US).
- bare 6-digit codes whose company name looks Korean (三星/海力士/Samsung…)
  are rejected — zero-padded KOSPI codes collide with SZSE 00x codes.
- bare alpha codes (no exchange suffix) are accepted only with ≥2 distinct
  clean company names, or corroboration from a suffixed twin (ARM + ARM.US);
  this kills report-shorthand dirt like WFE/HDD/TAM/ESS/CCFI.
- company names are cleaned (broker prefix noise, share-class suffixes,
  underscore artifacts) and rejected when they look like report titles or
  generic sector phrases instead of company names.
- bare-digit aliases in the year range 1900-2099 are never emitted (the
  suffixed form, e.g. 2018.HK, still is) — year mentions are the dominant
  false-positive class for numeric aliases.
- ambiguous bare aliases (common English words / abbreviations / legal-entity
  suffixes / timezones: KEY, SE, ET, SI, IQ, Target, Block, Stone...) are kept
  but marked ``requires_context: true`` — the F2 deterministic scan
  (``entity_anchoring.bare_alias_context_ok``) then requires an explicit
  ticker context ("(KEY)", "KEY.N", "Ticker: KEY") before anchoring. The
  classifier is ``entity_stoplist.is_ambiguous_broker_alias``.

Idempotent: same inputs → byte-identical output (no timestamps).

Usage:
    .venv/bin/python scripts/build_broker_entity_registry.py \
        --db /Volumes/NAMEZY/外资研报/rag_data/reports.db \
        --entities-yaml /Volumes/NAMEZY/外资研报/config/entities.yaml \
        --out configs/entity_registry_broker.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.entity_registry import ENTITY_REGISTRY  # noqa: E402
from finer.enrichment.entity_stoplist import (  # noqa: E402
    CN_GENERIC_CANDIDATE_TERMS,
    CN_SECTOR_THEME_TERMS,
    NOISY_UPPER_TOKENS,
    is_ambiguous_broker_alias,
)
from finer.enrichment.ticker_normalization import (  # noqa: E402
    NormalizedTicker,
    normalize_broker_ticker,
)

DEFAULT_DB = Path("/Volumes/NAMEZY/外资研报/rag_data/reports.db")
DEFAULT_ENTITIES_YAML = Path("/Volumes/NAMEZY/外资研报/config/entities.yaml")
DEFAULT_OUT = REPO_ROOT / "configs" / "entity_registry_broker.yaml"

# stock_code dirt that is a region/market label, never a ticker.
DIRTY_CODES: frozenset = frozenset(
    {"PRC", "CHINA", "CN", "HK", "US", "USA", "EU", "UK", "GLOBAL", "ASIA", "APAC", "NA", "N/A"}
)

# Company-name patterns that mark a bare 6-digit code as Korean (KOSPI codes
# are zero-padded 6-digit and collide with SZSE 00x segments).
KR_NAME_MARKERS: Tuple[str, ...] = (
    "三星",
    "海力士",
    "Samsung",
    "Hynix",
    "现代",
    "Hyundai",
    "起亚",
    "Kia",
    "LG",
)

# CJK company-name substrings that mark a report-title / sector phrase.
CJK_NAME_NOISE_TERMS: Tuple[str, ...] = (
    "指数",
    "设备",
    "市场",
    "板块",
    "概念",
    "行业",
    "消费者",
    "运价",
    "中小盘",
    "基准",
    "会议",
    "要点",
    "展望",
    "解读",
    "重申",
    "预计",
    "结合",
    "优化",
    "打造",
    "发布",
    "如何",
    "追踪",
    "学会",
    "协会",
    "渗透率",
    "出货量",
    "研报",
    "策略",
    "晨报",
    "周报",
)

# ASCII company-name keywords that mark a report title, not a company.
ASCII_NAME_NOISE_WORDS: frozenset = frozenset(
    {
        "weekly",
        "monthly",
        "daily",
        "tracker",
        "benchmark",
        "rates",
        "rate",
        "strategy",
        "morning",
        "notes",
        "note",
        "update",
        "preview",
        "review",
        "outlook",
        "transcript",
        "summit",
        "index",
        "attribution",
        "attributions",
        "movers",
        "pulse",
        "spot",
    }
)

_ASCII_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9&.,'()\- ]*$")
_CJK_RE = re.compile(r"[一-鿿]")
_TRAILING_SHARE_CLASS_RE = re.compile(r"[\s\-–—]+[AH]$")
_ASCII_CORP_SUFFIX_RE = re.compile(
    r"[\s,]+(Inc|Inc\.|Corp|Corp\.|Corporation|Co|Co\.|Ltd|Ltd\.|Limited|PLC|Plc|Holdings?|Group)\.?$"
)
_CJK_CORP_SUFFIX_RE = re.compile(r"(股份有限公司|有限公司|控股有限|股份|控股|集团|公司)$")

_YEAR_LIKE_RE = re.compile(r"^(19|20)\d{2}$")

_MAX_NAME_LEN = 40
_MAX_ASCII_NAME_WORDS = 6


@dataclass
class BuildStats:
    """Counters for one generation run (surfaced in the YAML header)."""

    pairs_in: int = 0
    pairs_code_rejected: int = 0
    pairs_kr_guard_rejected: int = 0
    bare_alpha_rejected: int = 0
    alias_conflicts_dropped: int = 0
    aliases_skipped_kol_priority: int = 0
    aliases_context_gated: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "pairs_in": self.pairs_in,
            "pairs_code_rejected": self.pairs_code_rejected,
            "pairs_kr_guard_rejected": self.pairs_kr_guard_rejected,
            "bare_alpha_rejected": self.bare_alpha_rejected,
            "alias_conflicts_dropped": self.alias_conflicts_dropped,
            "aliases_skipped_kol_priority": self.aliases_skipped_kol_priority,
            "aliases_context_gated": self.aliases_context_gated,
        }


@dataclass
class EntitiesConfig:
    """Relevant slices of the research repo's curated entities.yaml."""

    ambiguous_text_tickers: List[str] = field(default_factory=list)
    non_company_tickers: List[str] = field(default_factory=list)
    company_noise_prefixes: List[str] = field(default_factory=list)
    generic_ticker_context_patterns: List[str] = field(default_factory=list)
    ticker_company_aliases: Dict[str, str] = field(default_factory=dict)
    company_alias_canonical: Dict[str, str] = field(default_factory=dict)


def load_entities_config(path: Path) -> EntitiesConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return EntitiesConfig(
        ambiguous_text_tickers=[str(x) for x in data.get("ambiguous_text_tickers", [])],
        non_company_tickers=[str(x) for x in data.get("non_company_tickers", [])],
        company_noise_prefixes=[str(x) for x in data.get("company_noise_prefixes", [])],
        generic_ticker_context_patterns=[
            str(x) for x in data.get("generic_ticker_context_patterns", [])
        ],
        ticker_company_aliases={
            str(k): str(v) for k, v in (data.get("ticker_company_aliases") or {}).items()
        },
        company_alias_canonical={
            str(k): str(v) for k, v in (data.get("company_alias_canonical") or {}).items()
        },
    )


def load_pairs_from_db(db_path: Path, *, busy_timeout_ms: int = 60000) -> List[Tuple[str, str]]:
    """Distinct (company_name, stock_code) pairs, read-only with busy timeout."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        rows = conn.execute(
            "SELECT DISTINCT company_name, stock_code FROM reports "
            "WHERE company_name IS NOT NULL AND company_name != '' "
            "AND stock_code IS NOT NULL AND stock_code != ''"
        ).fetchall()
    finally:
        conn.close()
    return [(str(name), str(code)) for name, code in rows]


def _negative_code_set(cfg: EntitiesConfig) -> Set[str]:
    negative: Set[str] = set(DIRTY_CODES)
    negative.update(t.upper() for t in cfg.ambiguous_text_tickers)
    negative.update(t.upper() for t in cfg.non_company_tickers)
    negative.update(NOISY_UPPER_TOKENS)
    return negative


def clean_company_name(name: str, *, noise_prefixes: Iterable[str]) -> Optional[str]:
    """Clean one company name; return None when it is not a usable alias."""
    cleaned = name.replace("_", " ").replace("~", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.lstrip("&-—·. ").strip()
    if not cleaned:
        return None
    # Broker prefix noise (from entities.yaml company_noise_prefixes)
    for prefix in noise_prefixes:
        if cleaned.startswith(prefix + " "):
            cleaned = cleaned[len(prefix) + 1:].strip()
            break
    # Trailing share-class markers after underscore cleanup ("BYD A", "CITIC Securities A")
    cleaned = _TRAILING_SHARE_CLASS_RE.sub("", cleaned).strip()
    if len(cleaned) < 2 or len(cleaned) > _MAX_NAME_LEN:
        return None
    if cleaned[0].isdigit():
        return None
    if any(ch in cleaned for ch in "％%；;。！？!?|:\n\t"):
        return None

    if _CJK_RE.search(cleaned):
        # CJK-ish name: reject report-title / sector-phrase noise
        if any(term in cleaned for term in CJK_NAME_NOISE_TERMS):
            return None
        if any(term in cleaned for term in CN_GENERIC_CANDIDATE_TERMS):
            return None
        if cleaned in CN_SECTOR_THEME_TERMS:
            return None
        # Hyphenated CJK strings are report-title fragments, not names
        if "-" in cleaned or "—" in cleaned:
            return None
        return cleaned

    # Pure ASCII name
    if not _ASCII_NAME_RE.match(cleaned):
        return None
    words = cleaned.split(" ")
    if len(words) > _MAX_ASCII_NAME_WORDS:
        return None
    if any(w.lower().strip(".,") in ASCII_NAME_NOISE_WORDS for w in words):
        return None
    return cleaned


def _corp_suffix_stripped(name: str) -> Optional[str]:
    """Secondary alias with the corporate suffix removed, when it stays specific."""
    if _CJK_RE.search(name):
        stripped = _CJK_CORP_SUFFIX_RE.sub("", name)
        if stripped != name and len(stripped) >= 2:
            return stripped
        return None
    stripped = _ASCII_CORP_SUFFIX_RE.sub("", name).strip()
    if stripped != name and len(stripped) >= 3:
        return stripped
    return None


def _looks_kr(name: str) -> bool:
    return any(marker in name for marker in KR_NAME_MARKERS)


def _digit_alias_ok(digits: str) -> bool:
    """Bare-digit aliases: never emit year-like values (1900-2099)."""
    return not _YEAR_LIKE_RE.match(digits)


def build_registry(
    pairs: List[Tuple[str, str]],
    cfg: EntitiesConfig,
) -> Tuple[Dict[str, Dict[str, str]], BuildStats]:
    """Build alias → {symbol, market} entries from mined pairs + curated rules."""
    stats = BuildStats(pairs_in=len(pairs))
    negative_codes = _negative_code_set(cfg)

    # ── pass 1: normalize codes, group names per symbol ──────────────────────
    # symbol → {"market": str, "raw_codes": set, "clean_names": set,
    #           "bare_alpha_only": bool, "suffix_corroborated": bool, "curated": bool}
    symbols: Dict[str, Dict[str, object]] = {}

    def _ingest(name: str, code: str, *, curated: bool) -> None:
        code_stripped = code.strip()
        if not code_stripped or code_stripped.upper() in negative_codes:
            stats.pairs_code_rejected += 1
            return
        bare_alpha = "." not in code_stripped and code_stripped.isascii() and code_stripped.isalpha()
        if bare_alpha and len(code_stripped) < 2:
            stats.pairs_code_rejected += 1
            return
        normalized = normalize_broker_ticker(code_stripped)
        if normalized is None:
            stats.pairs_code_rejected += 1
            return
        # KR guard: zero-padded KOSPI codes collide with SZSE 00x segments
        bare_six_digit = "." not in code_stripped and code_stripped.isdigit() and len(code_stripped) == 6
        if bare_six_digit and _looks_kr(name):
            stats.pairs_kr_guard_rejected += 1
            return
        slot = symbols.setdefault(
            normalized.symbol,
            {
                "market": normalized.market,
                "raw_codes": set(),
                "clean_names": set(),
                "bare_alpha_only": True,
                "suffix_corroborated": False,
                "curated": False,
            },
        )
        slot["raw_codes"].add(code_stripped.upper())
        if not bare_alpha:
            slot["bare_alpha_only"] = False
        if "." in code_stripped:
            slot["suffix_corroborated"] = True
        if curated:
            slot["curated"] = True
        cleaned = clean_company_name(name, noise_prefixes=cfg.company_noise_prefixes)
        if cleaned:
            slot["clean_names"].add(cleaned)

    for name, code in pairs:
        _ingest(name, code, curated=False)
    # entities.yaml ticker_company_aliases is human-curated: code → company name
    for code, name in cfg.ticker_company_aliases.items():
        _ingest(name, code, curated=True)

    # ── pass 2: bare-alpha acceptance gate ────────────────────────────────────
    accepted: Dict[str, Dict[str, object]] = {}
    for symbol, slot in symbols.items():
        if slot["bare_alpha_only"] and not slot["curated"]:
            # Accept only with ≥2 distinct clean names, or a suffixed twin.
            if len(slot["clean_names"]) < 2 and not slot["suffix_corroborated"]:
                stats.bare_alpha_rejected += 1
                continue
        accepted[symbol] = slot

    # ── pass 3: assemble aliases ──────────────────────────────────────────────
    # alias → set of symbols (to detect conflicts)
    alias_candidates: Dict[str, Set[str]] = {}
    alias_market: Dict[Tuple[str, str], str] = {}

    def _propose(alias: str, symbol: str, market: str) -> None:
        alias = alias.strip()
        if not alias or len(alias) < 2:
            return
        if alias.isascii() and not _CJK_RE.search(alias):
            upper = alias.upper()
            if upper in negative_codes:
                return
            if alias.isdigit() and not _digit_alias_ok(alias):
                return
            if alias.isdigit() and len(alias) < 4:
                return
        alias_candidates.setdefault(alias, set()).add(symbol)
        alias_market[(alias, symbol)] = market

    for symbol, slot in accepted.items():
        market = str(slot["market"])
        _propose(symbol, symbol, market)
        for raw in slot["raw_codes"]:
            if raw != symbol:
                _propose(raw, symbol, market)
        # bare digit alias for suffixed digit symbols (0700.HK → 0700)
        base, _, suffix = symbol.rpartition(".")
        if suffix and base.isdigit():
            _propose(base, symbol, market)
        for name in slot["clean_names"]:
            _propose(name, symbol, market)
            stripped = _corp_suffix_stripped(name)
            if stripped:
                _propose(stripped, symbol, market)

    # company_alias_canonical: alias → canonical company name → symbol
    canonical_name_to_symbol: Dict[str, str] = {}
    for symbol, slot in accepted.items():
        for name in slot["clean_names"]:
            canonical_name_to_symbol.setdefault(name, symbol)
    for alias, (ticker, market, etype) in ENTITY_REGISTRY.items():
        if etype == "ticker":
            canonical_name_to_symbol.setdefault(alias, ticker)
    for alias, canonical in cfg.company_alias_canonical.items():
        symbol = canonical_name_to_symbol.get(canonical)
        if symbol is None:
            continue
        if symbol in accepted:
            market = str(accepted[symbol]["market"])
        else:
            entry = ENTITY_REGISTRY.get(canonical)
            if entry is None or entry[2] != "ticker":
                continue
            market = entry[1]
        _propose(alias, symbol, market)

    # ── pass 4: conflict + KOL priority resolution ────────────────────────────
    entries: Dict[str, Dict[str, object]] = {}
    for alias, symbol_set in alias_candidates.items():
        if len(symbol_set) > 1:
            stats.alias_conflicts_dropped += 1
            continue
        if alias in ENTITY_REGISTRY:
            stats.aliases_skipped_kol_priority += 1
            continue
        symbol = next(iter(symbol_set))
        entry: Dict[str, object] = {
            "symbol": symbol,
            "market": alias_market[(alias, symbol)],
        }
        # Ambiguous bare aliases (common English words / abbreviations /
        # legal-entity suffixes / timezones: KEY, SE, ET, Target, Block...)
        # are kept but flagged: the F2 deterministic scan must see an explicit
        # ticker context ("(KEY)", "KEY.N", "Ticker: KEY") before anchoring.
        if is_ambiguous_broker_alias(alias):
            entry["requires_context"] = True
            stats.aliases_context_gated += 1
        entries[alias] = entry
    return entries, stats


def render_yaml(
    entries: Dict[str, Dict[str, object]],
    cfg: EntitiesConfig,
    stats: BuildStats,
    *,
    db_path: Path,
    entities_yaml_path: Path,
) -> str:
    """Render the committable AUTO-GENERATED registry YAML (idempotent)."""
    header = (
        "# AUTO-GENERATED — DO NOT EDIT BY HAND\n"
        "# Generated by scripts/build_broker_entity_registry.py\n"
        "#\n"
        "# Sources (read-only):\n"
        f"#   - reports.db (mode=ro): {db_path}\n"
        f"#   - curated entities.yaml: {entities_yaml_path}\n"
        "#\n"
        "# Consumed by finer.enrichment.broker_entity_registry as the append-only\n"
        "# broker layer of the F2 deterministic entity registry. Curated KOL\n"
        "# registry aliases (finer.entity_registry.ENTITY_REGISTRY) always win on\n"
        "# alias conflicts. Regenerate with:\n"
        "#   .venv/bin/python scripts/build_broker_entity_registry.py\n"
        "#\n"
        f"# build_stats: {json.dumps(stats.as_dict(), sort_keys=True)}\n"
    )
    payload = {
        "version": 1,
        "entry_count": len(entries),
        "negative_rules": {
            "ambiguous_text_tickers": sorted(cfg.ambiguous_text_tickers),
            "non_company_tickers": sorted(cfg.non_company_tickers),
            "company_noise_prefixes": sorted(cfg.company_noise_prefixes),
            "generic_ticker_context_patterns": sorted(cfg.generic_ticker_context_patterns),
        },
        "entries": {
            alias: dict(sorted(spec.items())) for alias, spec in sorted(entries.items())
        },
    }
    body = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
        width=120,
    )
    return header + body


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--entities-yaml", type=Path, default=DEFAULT_ENTITIES_YAML)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--busy-timeout-ms", type=int, default=60000)
    args = parser.parse_args(argv)

    cfg = load_entities_config(args.entities_yaml)
    pairs = load_pairs_from_db(args.db, busy_timeout_ms=args.busy_timeout_ms)
    entries, stats = build_registry(pairs, cfg)
    text = render_yaml(
        entries,
        cfg,
        stats,
        db_path=args.db,
        entities_yaml_path=args.entities_yaml,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(entries)} aliases)")
    print(f"stats: {json.dumps(stats.as_dict(), sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
