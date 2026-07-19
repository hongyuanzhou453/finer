"""Tests for the F2 broker entity registry layer.

Covers:
- ticker suffix normalization tables (enrichment/ticker_normalization.py)
- the numeric-alias context gate incl. the UBS phone-number regression
  (entity_anchoring.numeric_alias_context_ok / scan_text)
- the ambiguous bare-alias context gate incl. the 8 confirmed false-positive
  words from the 2026-07-17 acceptance run (KEY/SE/ET/SI/IQ/Target/Block/Stone)
  (entity_anchoring.bare_alias_context_ok / scan_text)
- generator negative rules + requires_context flagging
  (scripts/build_broker_entity_registry.py)
- KOL-priority layering (enrichment/broker_entity_registry.py)
- generator idempotence

See docs/specs/2026-07-15-broker-research-source-integration.md.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

from finer.entity_registry import ENTITY_REGISTRY
from finer.enrichment import broker_entity_registry as breg
from finer.enrichment.entity_anchoring import (
    bare_alias_context_ok,
    clear_alias_table_cache,
    numeric_alias_context_ok,
    scan_text,
)
from finer.enrichment.entity_stoplist import is_ambiguous_broker_alias
from finer.enrichment.ticker_normalization import (
    NormalizedTicker,
    normalize_broker_ticker,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    """Import scripts/build_broker_entity_registry.py as a module."""
    path = REPO_ROOT / "scripts" / "build_broker_entity_registry.py"
    spec = importlib.util.spec_from_file_location("build_broker_entity_registry", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


# ── 1. suffix normalization table ────────────────────────────────────────────


class TestTickerNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # RIC US venues → bare US semantics
            ("AAPL.N", NormalizedTicker("AAPL", "US")),
            ("AAPL.NYSE", NormalizedTicker("AAPL", "US")),
            ("MSFT.O", NormalizedTicker("MSFT", "US")),
            ("NVDA.OQ", NormalizedTicker("NVDA", "US")),
            ("amkr.us", NormalizedTicker("AMKR", "US")),
            # RIC .SS means Shanghai → canonical .SH
            ("600519.SS", NormalizedTicker("600519.SH", "CN")),
            ("600519.SH", NormalizedTicker("600519.SH", "CN")),
            ("300750.SZ", NormalizedTicker("300750.SZ", "CN")),
            # HK zero-padding
            ("700.HK", NormalizedTicker("0700.HK", "HK")),
            ("0700.HK", NormalizedTicker("0700.HK", "HK")),
            ("9988.HK", NormalizedTicker("9988.HK", "HK")),
            # TW / JP explicit suffixes
            ("2330.TW", NormalizedTicker("2330.TW", "TW")),
            ("9202.T", NormalizedTicker("9202.T", "JP")),
            # bare 6-digit → CN segment table
            ("600754", NormalizedTicker("600754.SH", "CN")),
            ("688012", NormalizedTicker("688012.SH", "CN")),
            ("000333", NormalizedTicker("000333.SZ", "CN")),
            ("300059", NormalizedTicker("300059.SZ", "CN")),
            # bare letters → US
            ("IQ", NormalizedTicker("IQ", "US")),
            ("AMKR", NormalizedTicker("AMKR", "US")),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_broker_ticker(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",  # empty
            "PRC",  # too long? no — 3 letters IS valid US shape; PRC filtered upstream
            "8570",  # bare 4-digit: HK vs JP ambiguous
            "79360",  # bare 5-digit
            "400001",  # BSE-ish segment not in table
            "830799",  # BSE segment
            "920116",  # BSE 92x segment
            "600519.XX",  # unknown suffix
            "ABC DEF",  # embedded space
            "TOOLONGTICKER",  # >5 letters
            "600519.L",  # LSE is alpha-only; a numeric base stays unmappable (C9)
            "600519.SW",  # Swiss is alpha-only; numeric base unmappable (C9)
        ],
    )
    def test_rejects_unmappable(self, raw):
        if raw == "PRC":
            # PRC is shape-valid; the generator's DIRTY_CODES rejects it instead.
            assert normalize_broker_ticker(raw) == NormalizedTicker("PRC", "US")
            assert "PRC" in builder.DIRTY_CODES
        else:
            assert normalize_broker_ticker(raw) is None


# ── 2. numeric-alias context gate ────────────────────────────────────────────


class TestNumericContextGate:
    def test_ubs_phone_number_regression(self):
        # Real text from broker_0ddc49c2b4964416aca54bb2 that anchored 2498.HK.
        text = "gayathri.chandrasekaran@ubs.com\n+61-2-9324 2498\nline with FY25."
        hits = scan_text(text)
        assert all(h.ticker != "2498.HK" for h in hits)

    @pytest.mark.parametrize(
        "text",
        [
            "+61-2-9324 2498",  # phone grouping: digit+space prefix
            "call +852 2498 1234 now",  # phone continuation suffix
            "Tel: 2498",  # tel keyword in window
            "传真 2498",  # fax keyword in window
            "电话：2498",  # phone keyword in window
        ],
    )
    def test_phone_fax_patterns_rejected(self, text):
        start = text.index("2498")
        assert numeric_alias_context_ok(text, start, start + 4) is False

    @pytest.mark.parametrize(
        "text",
        [
            "速腾聚创（2498）发布公告",  # adjacent bracket
            "RoboSense (2498) results",
            "2498.HK 收盘上涨",  # exchange suffix
            "2498 HK Equity",  # Bloomberg style
            "股票代码2498",  # 代码 context term
            "买入2498，目标价上调",  # trade verb context
        ],
    )
    def test_ticker_context_accepted(self, text):
        start = text.index("2498")
        assert numeric_alias_context_ok(text, start, start + 4) is True

    def test_bare_number_without_context_rejected(self):
        text = "样本共有 2498 条记录参与统计"
        start = text.index("2498")
        assert numeric_alias_context_ok(text, start, start + 4) is False

    def test_scan_text_still_anchors_contextual_numeric(self):
        hits = scan_text("速腾聚创（2498）目标价上调")
        assert any(h.ticker == "2498.HK" and h.alias == "2498" for h in hits)

    def test_generic_title_pattern_rejects(self, tmp_path, monkeypatch):
        yaml_path = tmp_path / "broker.yaml"
        yaml_path.write_text(
            yaml.safe_dump(
                {
                    "entries": {},
                    "negative_rules": {
                        "generic_ticker_context_patterns": ["TSX Composite Attributions"]
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(breg, "DEFAULT_BROKER_REGISTRY_PATH", yaml_path)
        breg.clear_cache()
        clear_alias_table_cache()
        try:
            text = "TSX Composite Attributions 股票代码2498"
            start = text.index("2498")
            assert numeric_alias_context_ok(text, start, start + 4) is False
        finally:
            breg.clear_cache()
            clear_alias_table_cache()


# ── 2b. ambiguous bare-alias context gate ────────────────────────────────────


# Broker fixture registry mirroring the 8 confirmed false-positive aliases
# from the 2026-07-17 acceptance run, plus their full-name siblings which must
# NEVER be gated.
_POISON_FIXTURE_ENTRIES = {
    "KEY": {"symbol": "KEY", "market": "US"},
    "KeyCorp": {"symbol": "KEY", "market": "US"},
    "SE": {"symbol": "SE", "market": "US"},
    "Sea Ltd": {"symbol": "SE", "market": "US"},
    "ET": {"symbol": "ET", "market": "US"},
    "SI": {"symbol": "SI", "market": "US"},
    "IQ": {"symbol": "IQ", "market": "US"},
    "iQIYI": {"symbol": "IQ", "market": "US"},
    "Target": {"symbol": "TGT", "market": "US"},
    "Block": {"symbol": "XYZ", "market": "US"},
    "Block Inc": {"symbol": "XYZ", "market": "US"},
    "Stone": {"symbol": "STNE", "market": "US"},
    "StoneCo": {"symbol": "STNE", "market": "US"},
}


@pytest.fixture()
def poison_registry(tmp_path, monkeypatch):
    """Point the broker layer at the poison-word fixture registry."""
    path = tmp_path / "broker.yaml"
    path.write_text(
        yaml.safe_dump(
            {"entries": _POISON_FIXTURE_ENTRIES, "negative_rules": {}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(breg, "DEFAULT_BROKER_REGISTRY_PATH", path)
    breg.clear_cache()
    clear_alias_table_cache()
    yield path
    breg.clear_cache()
    clear_alias_table_cache()


class TestBareAliasContextGate:
    """The 8 poison words from the acceptance run must not anchor bare."""

    @pytest.mark.parametrize(
        ("text", "symbol"),
        [
            # 2026-07-17 acceptance-run false positives, verbatim shapes:
            ("KEY DEFINITIONS\nThis report was produced by UBS.", "KEY"),
            ("UBS Europe SE is a subsidiary of UBS Group AG.", "SE"),
            ("Price Target: US$25.00 (from US$22.00)", "TGT"),
            ("Nirlon Knowledge Park, Block B-6, Goregaon (East), Mumbai", "XYZ"),
            ("The call will begin at 4:00 PM ET on Thursday.", "ET"),
            ("as defined by SI 2017/1064 under UK regulations", "SI"),
            ("Analyst: Jamie Stone, CFA +1-212-000-0000", "STNE"),
            ("Source: S&P Capital IQ, company filings", "IQ"),
        ],
    )
    def test_poison_words_do_not_anchor_bare(self, poison_registry, text, symbol):
        assert all(h.ticker != symbol for h in scan_text(text))

    @pytest.mark.parametrize(
        ("text", "symbol", "alias"),
        [
            # explicit ticker contexts keep working:
            ("KeyCorp (KEY) reported Q2 earnings", "KEY", "KEY"),
            ("Shopee parent (SE US) beat estimates", "SE", "SE"),
            ("We upgrade KEY.N to Buy", "KEY", "KEY"),
            ("Ticker: KEY — regional bank coverage", "KEY", "KEY"),
            ("股票代码: SE 东南亚电商", "SE", "SE"),
            ("KEY US Equity screened positive", "KEY", "KEY"),
        ],
    )
    def test_ticker_context_still_anchors(self, poison_registry, text, symbol, alias):
        assert any(
            h.ticker == symbol and h.alias == alias for h in scan_text(text)
        )

    @pytest.mark.parametrize(
        ("text", "symbol", "alias"),
        [
            # full-name aliases are separate entries and are never gated:
            ("Block Inc reported strong GPV growth", "XYZ", "Block Inc"),
            ("iQIYI subscriber numbers improved", "IQ", "iQIYI"),
            ("KeyCorp reported Q2 earnings", "KEY", "KeyCorp"),
            ("Sea Ltd gaming revenue rebounded", "SE", "Sea Ltd"),
            ("StoneCo payment volumes grew", "STNE", "StoneCo"),
        ],
    )
    def test_full_name_aliases_not_gated(self, poison_registry, text, symbol, alias):
        assert any(
            h.ticker == symbol and h.alias == alias for h in scan_text(text)
        )

    def test_bare_gate_default_rejects(self):
        text = "KEY DEFINITIONS"
        start = text.index("KEY")
        assert bare_alias_context_ok(text, start, start + 3) is False

    @pytest.mark.parametrize(
        "text",
        [
            "KeyCorp (KEY) rallied",
            "upgrade KEY.N to Buy",
            "Ticker: KEY",
            "KEY US Equity",
        ],
    )
    def test_bare_gate_positive_contexts(self, text):
        start = text.index("KEY", text.find("KeyCorp") + 1 if "KeyCorp" in text else 0)
        assert bare_alias_context_ok(text, start, start + 3) is True


class TestAmbiguousAliasClassifier:
    @pytest.mark.parametrize(
        "alias",
        ["KEY", "SE", "ET", "SI", "IQ", "Target", "Block", "Stone", "AG", "PLC", "PST"],
    )
    def test_flags_ambiguous(self, alias):
        assert is_ambiguous_broker_alias(alias) is True

    @pytest.mark.parametrize(
        "alias",
        [
            "CATL",  # 4-char caps but not a common word
            "NVDA",
            "iQIYI",  # not Title-case, full brand name
            "Block Inc",  # multi-word full name
            "KeyCorp",
            "600519",  # digits: numeric gate owns these
            "3750.HK",
            "美的集团",
        ],
    )
    def test_passes_specific(self, alias):
        assert is_ambiguous_broker_alias(alias) is False


# ── 3. generator negative rules ──────────────────────────────────────────────


def _cfg(**overrides):
    base = dict(
        ambiguous_text_tickers=["A", "AI", "US"],
        non_company_tickers=["USD", "EM", "EU"],
        company_noise_prefixes=["ADV", "PLC"],
        generic_ticker_context_patterns=["Morning Notes"],
        ticker_company_aliases={},
        company_alias_canonical={},
    )
    base.update(overrides)
    return builder.EntitiesConfig(**base)


class TestGeneratorNegativeRules:
    def test_dirty_and_negative_codes_rejected(self):
        pairs = [
            ("中国宏观", "PRC"),
            ("China Strategy", "CHINA"),
            ("美元观察", "USD"),
            ("新兴市场", "EM"),
            ("AI 主题", "AI"),
            ("贵州茅台", "600519.SS"),
        ]
        entries, stats = builder.build_registry(pairs, _cfg())
        symbols = {spec["symbol"] for spec in entries.values()}
        assert symbols == {"600519.SH"}
        assert stats.pairs_code_rejected == 5

    def test_company_noise_prefix_stripped(self):
        pairs = [("ADV 美的集团", "000333.SZ")]
        entries, _ = builder.build_registry(pairs, _cfg())
        assert "美的集团" in entries
        assert entries["美的集团"]["symbol"] == "000333.SZ"
        assert "ADV 美的集团" not in entries

    def test_year_like_bare_digit_alias_never_emitted(self):
        pairs = [("某港股公司", "2018.HK")]
        entries, _ = builder.build_registry(pairs, _cfg())
        assert "2018.HK" in entries  # suffixed form survives
        assert "2018" not in entries  # bare year-like digits do not

    def test_kr_zero_padded_code_guard(self):
        pairs = [("三星电子", "005930")]
        entries, stats = builder.build_registry(pairs, _cfg())
        assert not entries
        assert stats.pairs_kr_guard_rejected == 1

    def test_bare_alpha_needs_corroboration(self):
        # single name, no suffixed twin → rejected
        entries, stats = builder.build_registry([("Wafer Fab Equipment", "WFE")], _cfg())
        assert "WFE" not in entries
        assert stats.bare_alpha_rejected == 1
        # suffixed twin corroborates
        entries, _ = builder.build_registry(
            [("Arm Holdings", "ARM"), ("Arm Holdings", "ARM.US")], _cfg()
        )
        assert entries["ARM"]["symbol"] == "ARM"

    def test_report_title_company_names_rejected(self):
        pairs = [
            ("半导体设备行业周报", "600519.SS"),
            ("Global Rates Weekly", "600519.SS"),
        ]
        entries, _ = builder.build_registry(pairs, _cfg())
        aliases = set(entries)
        assert "半导体设备行业周报" not in aliases
        assert "Global Rates Weekly" not in aliases

    def test_alias_conflict_dropped(self):
        pairs = [("Acme Robotics", "600519.SS"), ("Acme Robotics", "000333.SZ")]
        entries, stats = builder.build_registry(pairs, _cfg())
        assert "Acme Robotics" not in entries
        assert stats.alias_conflicts_dropped == 1

    def test_ambiguous_bare_alias_flagged_requires_context(self):
        # "SE" (Sea Ltd) is a corroborated real ticker but a legal-entity
        # suffix in text — kept, flagged; the full name is NOT flagged.
        pairs = [("Sea Ltd", "SE.N"), ("Sea Limited", "SE")]
        entries, stats = builder.build_registry(pairs, _cfg())
        assert entries["SE"]["requires_context"] is True
        assert "requires_context" not in entries["Sea Ltd"]
        assert stats.aliases_context_gated >= 1

    def test_unambiguous_alias_not_flagged(self):
        pairs = [("Amkor Technology", "AMKR.OQ")]
        entries, _ = builder.build_registry(pairs, _cfg())
        assert "requires_context" not in entries["AMKR"]


# ── 4. KOL-priority layering ─────────────────────────────────────────────────


class TestKolPriority:
    def _write_yaml(self, tmp_path: Path, entries: dict) -> Path:
        path = tmp_path / "broker.yaml"
        path.write_text(
            yaml.safe_dump({"entries": entries, "negative_rules": {}}, allow_unicode=True),
            encoding="utf-8",
        )
        return path

    def test_kol_alias_never_overridden(self, tmp_path):
        # "苹果" is a curated KOL alias (AAPL); a broker collision must be dropped.
        path = self._write_yaml(
            tmp_path,
            {
                "苹果": {"symbol": "0700.HK", "market": "HK"},
                "美的集团": {"symbol": "000333.SZ", "market": "CN"},
            },
        )
        breg.clear_cache()
        loaded = breg.load_broker_entries(path)
        assert "苹果" not in loaded
        assert loaded["美的集团"] == ("000333.SZ", "CN", "ticker")
        merged = breg.merged_registry(path)
        assert merged["苹果"] == ENTITY_REGISTRY["苹果"]
        assert merged["美的集团"][0] == "000333.SZ"
        breg.clear_cache()

    def test_generator_skips_kol_aliases(self):
        pairs = [("苹果", "AAPL.O"), ("Apple Inc", "AAPL.O")]
        entries, stats = builder.build_registry(pairs, _cfg())
        assert "苹果" not in entries
        assert stats.aliases_skipped_kol_priority >= 1

    def test_context_required_union_flag_and_classifier(self, tmp_path):
        # requires_context: true flags load; the load-time classifier also
        # gates known-ambiguous aliases in stale YAMLs missing the flag.
        path = self._write_yaml(
            tmp_path,
            {
                "Foobarbaz": {"symbol": "FBB", "market": "US", "requires_context": True},
                "ET": {"symbol": "ET", "market": "US"},  # stale: no flag
                "美的集团": {"symbol": "000333.SZ", "market": "CN"},
            },
        )
        breg.clear_cache()
        gated = breg.load_context_required_aliases(path)
        assert "Foobarbaz" in gated  # explicit flag
        assert "ET" in gated  # defense-in-depth classifier
        assert "美的集团" not in gated
        breg.clear_cache()

    def test_missing_yaml_degrades_to_kol_only(self, tmp_path):
        breg.clear_cache()
        missing = tmp_path / "nope.yaml"
        assert breg.load_broker_entries(missing) == {}
        assert breg.merged_registry(missing) == dict(ENTITY_REGISTRY)
        breg.clear_cache()

    def test_scan_uses_broker_entries(self, tmp_path, monkeypatch):
        path = self._write_yaml(
            tmp_path, {"美的集团": {"symbol": "000333.SZ", "market": "CN"}}
        )
        monkeypatch.setattr(breg, "DEFAULT_BROKER_REGISTRY_PATH", path)
        breg.clear_cache()
        clear_alias_table_cache()
        try:
            hits = scan_text("美的集团发布中报，苹果同日发新品")
            tickers = {h.ticker for h in hits}
            assert "000333.SZ" in tickers  # broker layer
            assert "AAPL" in tickers  # curated KOL layer intact
        finally:
            breg.clear_cache()
            clear_alias_table_cache()


# ── 5. generator idempotence ─────────────────────────────────────────────────


class TestIdempotence:
    def _fixture_db(self, tmp_path: Path) -> Path:
        db = tmp_path / "reports.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE reports (company_name TEXT, stock_code TEXT)"
        )
        conn.executemany(
            "INSERT INTO reports VALUES (?, ?)",
            [
                ("贵州茅台", "600519.SS"),
                ("美的集团", "000333"),
                ("Tencent Holdings", "700.HK"),
                ("中国宏观", "PRC"),
                ("Gayathri Chandrasekaran", "2498"),
            ],
        )
        conn.commit()
        conn.close()
        return db

    def _fixture_entities_yaml(self, tmp_path: Path) -> Path:
        path = tmp_path / "entities.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "ambiguous_text_tickers": ["AI", "US"],
                    "non_company_tickers": ["USD", "EM"],
                    "company_noise_prefixes": ["ADV"],
                    "generic_ticker_context_patterns": ["Morning Notes"],
                    "ticker_company_aliases": {"000333": "美的集团"},
                    "company_alias_canonical": {},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return path

    def test_main_is_idempotent(self, tmp_path):
        db = self._fixture_db(tmp_path)
        entities = self._fixture_entities_yaml(tmp_path)
        out = tmp_path / "out.yaml"
        argv = ["--db", str(db), "--entities-yaml", str(entities), "--out", str(out)]
        assert builder.main(argv) == 0
        first = out.read_bytes()
        assert builder.main(argv) == 0
        assert out.read_bytes() == first

    def test_output_parses_and_layers(self, tmp_path):
        db = self._fixture_db(tmp_path)
        entities = self._fixture_entities_yaml(tmp_path)
        out = tmp_path / "out.yaml"
        builder.main(["--db", str(db), "--entities-yaml", str(entities), "--out", str(out)])
        breg.clear_cache()
        loaded = breg.load_broker_entries(out)
        assert loaded["美的集团"] == ("000333.SZ", "CN", "ticker")
        assert loaded["600519.SH"] == ("600519.SH", "CN", "ticker")
        assert loaded["0700.HK"] == ("0700.HK", "HK", "ticker")
        # bare "2498" pair is a phone-book artifact; alias may only appear
        # in suffixed form and never a bare 4-digit code (ambiguous HK/JP).
        assert "2498" not in loaded
        assert "PRC" not in loaded
        patterns = breg.load_generic_ticker_context_patterns(out)
        assert "Morning Notes" in patterns
        breg.clear_cache()

    def test_committed_registry_parses_clean(self):
        """The committed AUTO-GENERATED YAML loads and respects KOL priority."""
        path = breg.DEFAULT_BROKER_REGISTRY_PATH
        if not path.exists():
            pytest.skip("configs/entity_registry_broker.yaml not generated")
        breg.clear_cache()
        loaded = breg.load_broker_entries(path)
        assert loaded, "committed broker registry must not be empty"
        for alias in loaded:
            assert alias not in ENTITY_REGISTRY
        for alias, (symbol, market, etype) in loaded.items():
            assert etype == "ticker"
            assert market in {"US", "CN", "HK", "TW", "JP"}
        # The 8 confirmed acceptance-run poison words must be context-gated
        # if present in the committed registry.
        gated = breg.load_context_required_aliases(path)
        for alias in ("KEY", "SE", "ET", "SI", "IQ", "Target", "Block", "Stone"):
            if alias in loaded:
                assert alias in gated, f"poison alias {alias!r} must be context-gated"
        # Full-name siblings must never be gated.
        for alias in ("Block Inc", "iQIYI", "KeyCorp", "Sea Ltd"):
            assert alias not in gated
        breg.clear_cache()
