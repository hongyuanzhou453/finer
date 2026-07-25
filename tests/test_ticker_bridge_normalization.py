"""Within-envelope loose bridging helpers (F2 international-suffix recovery).

These guard ``bridge_base_key`` / ``bridge_symbol_equivalent`` — the loose
matchers the broker driver uses to bridge a broker intent's ``target_symbol`` to
one F2 ``EntityAnchor.resolved_symbol`` in the SAME envelope, recovering broker
dialects (bare 4-digit, vendor tags, alt exchange suffixes) that the canonical
``normalize_broker_ticker`` intentionally rejects in isolation.
"""

from __future__ import annotations

import pytest

from finer.enrichment.ticker_normalization import (
    bridge_base_key,
    bridge_symbol_equivalent,
    normalize_broker_ticker,
)


# ── canonical resolver must stay strict (bridging must NOT relax it) ──────────

def test_canonical_resolver_still_rejects_bare_four_digit():
    # Ambiguous in isolation (HK vs JP vs KR) — canonical stays None.
    assert normalize_broker_ticker("8309") is None
    assert normalize_broker_ticker("0700") is None


# ── loose bridging bridges what canonical rejects, within an envelope ─────────

@pytest.mark.parametrize(
    "intent_symbol,anchor_symbol",
    [
        ("8309", "8309.T"),        # bare Tokyo code ↔ .T anchor
        ("3690", "3690.HK"),       # bare HK code ↔ .HK anchor
        ("0700", "0700.HK"),       # zero-padded HK
        ("066570", "066570.KS"),   # bare Korea code ↔ .KS anchor
        ("EQNR", "EQNR.OL"),       # bare US-form ↔ Oslo suffix
        ("GNC", "GNC.AX"),         # bare ↔ ASX
        ("IMO", "IMO.TO"),         # bare ↔ Toronto
        ("VARB.NS", "VARB.BO"),    # NSE ↔ BSE (same India instrument)
        ("ABBN.S", "ABBN.SW"),     # Reuters .S ↔ SIX .SW
        ("ASML.AS", "ASML"),       # Amsterdam suffix ↔ bare
        ("EL.FP", "EL"),           # Bloomberg Paris ↔ bare
        ("SPGI.MSCI", "SPGI"),     # vendor index tag ↔ bare
        ("GILD.BIC", "GILD"),      # vendor tag ↔ bare
        ("VIPS.UN", "VIPS"),       # units tag ↔ bare
    ],
)
def test_bridge_matches_within_envelope(intent_symbol, anchor_symbol):
    assert bridge_symbol_equivalent(intent_symbol, anchor_symbol)
    # symmetric
    assert bridge_symbol_equivalent(anchor_symbol, intent_symbol)


# ── loose bridging must NOT fabricate cross-instrument matches ────────────────

@pytest.mark.parametrize(
    "a,b",
    [
        ("SN", "SPX"),           # different bases
        ("603236.SS", "000100.SZ"),  # different A-share stocks
        ("METC", "MP"),          # different US tickers
        ("8309", "8306.T"),      # adjacent Tokyo codes, different base
        ("600519.SH", "600519.TW"),  # same base, two explicit conflicting markets
    ],
)
def test_bridge_rejects_non_equivalent(a, b):
    assert not bridge_symbol_equivalent(a, b)


def test_bridge_base_key_wildcard_market_for_bare_inputs():
    # Bare input → market hint None (anchor disambiguates).
    assert bridge_base_key("8309") == ("8309", None)
    assert bridge_base_key("EQNR") == ("EQNR", None)
    # Input with a KNOWN canonical suffix → carries a concrete market hint.
    assert bridge_base_key("RIO.L") == ("RIO", "UK")
    assert bridge_base_key("600519.SS") == ("600519", "CN")
    # Post international-unlock merge: .OL is now a canonical suffix (Oslo),
    # so it resolves with a concrete market instead of the L3 wildcard strip.
    assert bridge_base_key("EQNR.OL") == ("EQNR", "NO")
    # Input with an UNKNOWN dotted alpha tag → base stripped, market wildcard.
    assert bridge_base_key("EQNR.QQ") == ("EQNR", None)


def test_bridge_base_key_rejects_garbage():
    assert bridge_base_key("") is None
    assert bridge_base_key("MC PA") is None       # space, not a code
    assert bridge_base_key("...") is None
    assert bridge_base_key(None) is None  # type: ignore[arg-type]


def test_market_incompatible_same_base_not_bridged():
    # A concrete US ticker and a concrete non-US suffix with the same base
    # must not bridge (both carry explicit, conflicting markets).
    assert bridge_base_key("AAPL")[1] is None      # bare → wildcard, OK
    # But two explicitly-suffixed conflicting markets do not match:
    assert not bridge_symbol_equivalent("600519.SH", "600519.TW")
