"""Script-level tests for scripts/drive_broker_recommendations.bridge_target_symbol.

B1: a successful tier-2/tier-3 bridge must also refresh ``intent.market``
from the bridged symbol — otherwise the intent keeps its stale F3-era market
(often a wrong "US") and the action lands on the wrong trading calendar.

The driver script is import-safe (module-level code is sys.path setup,
imports and constants only; the drive itself runs under ``main()``), so it is
loaded here via importlib and the pure bridge function is exercised against
real ``NormalizedInvestmentIntent`` instances.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Optional

from finer.schemas.investment_intent import NormalizedInvestmentIntent

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "drive_broker_recommendations.py"
)


def _load_driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "drive_broker_recommendations_under_test", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver = _load_driver()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_intent(
    target_symbol: str, market: Optional[str] = "US"
) -> NormalizedInvestmentIntent:
    """Real schema intent carrying a (deliberately) stale F3-era market."""
    return NormalizedInvestmentIntent(
        envelope_id="env_bridge_test",
        target_type="stock",
        target_name=target_symbol,
        target_symbol=target_symbol,
        market=market,
        direction="bullish",
        actionability="recommendation",
        position_delta_hint="none",
        conviction=0.7,
        confidence=0.9,
    )


def make_env(*resolved_symbols: str) -> SimpleNamespace:
    """bridge_target_symbol only reads env.entity_anchors[].resolved_symbol."""
    return SimpleNamespace(
        entity_anchors=[SimpleNamespace(resolved_symbol=s) for s in resolved_symbols]
    )


# ---------------------------------------------------------------------------
# Tier 1 — exact match: no rewrite of symbol or market
# ---------------------------------------------------------------------------

def test_l1_exact_match_leaves_intent_untouched() -> None:
    intent = make_intent("600519.SH", market="CN")
    matched = driver.bridge_target_symbol(intent, make_env("600519.SH"))
    assert matched == "600519.SH"
    assert intent.target_symbol == "600519.SH"
    assert intent.market == "CN"


# ---------------------------------------------------------------------------
# Tier 2 — canonical normalization match: market refreshed from the table
# ---------------------------------------------------------------------------

def test_l2_rewrites_market_for_cn_dialect() -> None:
    """.SS dialect bridges to the .SH anchor and drops the stale US market."""
    intent = make_intent("600519.SS", market="US")  # stale F3-era market
    matched = driver.bridge_target_symbol(intent, make_env("600519.SH"))
    assert matched == "600519.SH"
    assert intent.target_symbol == "600519.SH"
    assert intent.market == "CN"


def test_l2_rewrites_market_for_international_dialect() -> None:
    """Bloomberg .FP dialect → canonical MC.PA anchor → market FR."""
    intent = make_intent("MC.FP", market="US")
    matched = driver.bridge_target_symbol(intent, make_env("MC.PA"))
    assert matched == "MC.PA"
    assert intent.target_symbol == "MC.PA"
    assert intent.market == "FR"


# ---------------------------------------------------------------------------
# Tier 3 — loose within-envelope bridge: anchor form decides the market
# ---------------------------------------------------------------------------

def test_l3_rewrites_market_from_normalizable_anchor() -> None:
    """Bare 8309 bridges to the Tokyo anchor; market becomes JP, not US."""
    intent = make_intent("8309", market="US")
    matched = driver.bridge_target_symbol(intent, make_env("8309.T"))
    assert matched == "8309.T"
    assert intent.target_symbol == "8309.T"
    assert intent.market == "JP"


def test_l3_adopts_market_when_anchor_normalizes() -> None:
    """EQNR ↔ EQNR.OL: post international-unlock merge .OL is canonical (NO).

    The L3 bridge normalizes the matched anchor and adopts its market — the
    stale F3-era "US" must be corrected, not preserved.
    """
    intent = make_intent("EQNR", market="US")
    matched = driver.bridge_target_symbol(intent, make_env("EQNR.OL"))
    assert matched == "EQNR.OL"
    assert intent.target_symbol == "EQNR.OL"
    assert intent.market == "NO"


def test_l3_keeps_market_when_anchor_not_normalizable() -> None:
    """EQNR ↔ EQNR.QQ: unknown suffix → normalize returns None → market unchanged.

    The bridge must not fabricate a market — the stale value stays as-is.
    """
    intent = make_intent("EQNR", market="US")
    matched = driver.bridge_target_symbol(intent, make_env("EQNR.QQ"))
    assert matched == "EQNR.QQ"
    assert intent.target_symbol == "EQNR.QQ"
    assert intent.market == "US"  # untouched, honest no-op


def test_l3_ambiguous_anchors_no_bridge_no_rewrite() -> None:
    """Two conflicting anchors for one base → no bridge, nothing mutated."""
    intent = make_intent("8309", market="US")
    matched = driver.bridge_target_symbol(intent, make_env("8309.T", "8309.HK"))
    assert matched is None
    assert intent.target_symbol == "8309"
    assert intent.market == "US"


# ---------------------------------------------------------------------------
# No match — intent untouched
# ---------------------------------------------------------------------------

def test_no_match_leaves_intent_untouched() -> None:
    intent = make_intent("TSLA", market="US")
    matched = driver.bridge_target_symbol(intent, make_env("AAPL"))
    assert matched is None
    assert intent.target_symbol == "TSLA"
    assert intent.market == "US"
