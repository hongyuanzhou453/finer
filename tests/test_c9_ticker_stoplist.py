"""C9 phase ① — ticker international suffixes + MSCI rating stoplist.

Covers the ticker_normalization additions (NSDQ + international exchange
suffixes, vendor-variant merge, base-kind guard) and the entity_stoplist
context-gating of MSCI/broker rating abbreviations.
"""

from __future__ import annotations

import pytest

from finer.enrichment.entity_stoplist import is_ambiguous_broker_alias
from finer.enrichment.ticker_normalization import normalize_broker_ticker


# ---------------------------------------------------------------------------
# ticker normalization — new suffixes
# ---------------------------------------------------------------------------


def test_nasdaq_vendor_suffix_is_us_bare():
    assert normalize_broker_ticker("AAPL.NSDQ") == ("AAPL", "US")


@pytest.mark.parametrize(
    "raw,expected_symbol,expected_market",
    [
        ("BP.L", "BP.L", "UK"),
        ("MC.PA", "MC.PA", "FR"),
        ("SAP.DE", "SAP.DE", "DE"),
        ("NESN.SW", "NESN.SW", "CH"),
        ("BHP.AX", "BHP.AX", "AU"),
        ("ABI.AS", "ABI.AS", "NL"),
        ("RACE.MI", "RACE.MI", "IT"),
        ("BMW.DE", "BMW.DE", "DE"),
    ],
)
def test_international_alpha_exchanges(raw, expected_symbol, expected_market):
    assert normalize_broker_ticker(raw) == (expected_symbol, expected_market)


@pytest.mark.parametrize(
    "raw,expected_symbol,expected_market",
    [
        ("005930.KS", "005930.KS", "KR"),   # Samsung KOSPI (numeric)
        ("D05.SI", "D05.SI", "SG"),          # DBS Singapore (alphanumeric)
        ("7203.KL", "7203.KL", "MY"),        # numeric Malaysia
        ("RELIANCE.NS", "RELIANCE.NS", "IN"),
    ],
)
def test_international_alnum_exchanges(raw, expected_symbol, expected_market):
    assert normalize_broker_ticker(raw) == (expected_symbol, expected_market)


def test_bloomberg_variant_merges_to_reuters_canonical():
    # Reuters .PA and Bloomberg .FP both collapse to the Paris canonical.
    assert normalize_broker_ticker("MC.FP") == normalize_broker_ticker("MC.PA") == ("MC.PA", "FR")
    # Reuters .L and Bloomberg .LN both collapse to London .L.
    assert normalize_broker_ticker("BP.LN") == normalize_broker_ticker("BP.L") == ("BP.L", "UK")


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Bloomberg-dialect tail merging into an existing Reuters canonical.
        ("5802.JP", ("5802.T", "JP")),      # Tokyo → .T
        ("2454.TT", ("2454.TW", "TW")),     # Taiwan main board → .TW
        ("ALK.TSX", ("ALK.TO", "CA")),      # Toronto → .TO
        ("GXI.GR", ("GXI.DE", "DE")),       # Germany → XETRA .DE
        ("HEI.GY", ("HEI.DE", "DE")),       # Germany (alt) → .DE
        ("RAND.NA", ("RAND.AS", "NL")),     # Amsterdam → .AS
        ("SAN.SM", ("SAN.MC", "ES")),       # Madrid → .MC
        ("SPM.IM", ("SPM.MI", "IT")),       # Milan → .MI
        ("IEL.AU", ("IEL.AX", "AU")),       # ASX → .AX
        ("PINELABS.IN", ("PINELABS.NS", "IN")),  # Bloomberg India → NSE
        ("ARGX.BB", ("ARGX.BR", "BE")),     # Brussels (alt) → .BR
        ("EQNR.NO", ("EQNR.OL", "NO")),     # Oslo (alt) → .OL
        ("DANSKE.DC", ("DANSKE.CO", "DK")), # Copenhagen (alt) → .CO
        # New exchanges (own canonical, exchange inferred from the issuer).
        ("ITUB3.SA", ("ITUB3.SA", "BR")),   # B3 São Paulo (alnum base)
        ("GRUMAB.MX", ("GRUMAB.MX", "MX")), # BMV Mexico
        ("6488.TWO", ("6488.TWO", "TW")),   # Taipei OTC
        ("UCB.BR", ("UCB.BR", "BE")),       # Brussels
        ("TEL.OL", ("TEL.OL", "NO")),       # Oslo
        ("NOVOB.CO", ("NOVOB.CO", "DK")),   # Copenhagen
        ("MAPI.JK", ("MAPI.JK", "ID")),     # Jakarta
        ("KGH.WA", ("KGH.WA", "PL")),       # Warsaw
        ("TRUE.BK", ("TRUE.BK", "TH")),     # Bangkok
        ("NOS.LS", ("NOS.LS", "PT")),       # Lisbon
        ("KMD.NZ", ("KMD.NZ", "NZ")),       # New Zealand
    ],
)
def test_bloomberg_tail_exchanges(raw, expected):
    assert normalize_broker_ticker(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "SECARE.SS",  # .SS = Swedish here but already means Shanghai → collision, omitted
        "SOBO.CN",    # .CN = Canada CSE vs China → collision, omitted
        "2280.SE",    # .SE = Saudi but corpus mislabels (1211.SE=BYD) → omitted
        "6FHAY.F",    # .F Frankfurt but derivative-code dirt → omitted
        "RIEN.S",     # .S Swiss conflicts with .SW canonical → omitted
        "TECK.B",     # share-class suffix, not an exchange → omitted
    ],
)
def test_ambiguous_or_dirty_suffixes_stay_unmapped(raw):
    # Intentionally NOT added — see ticker_normalization tail comment. Mapping
    # these blind would fabricate wrong exchanges.
    assert normalize_broker_ticker(raw) is None


def test_numeric_base_rejected_for_alpha_exchange():
    # a Shanghai code with a London/Swiss suffix is a mismatched code+exchange.
    assert normalize_broker_ticker("600519.L") is None
    assert normalize_broker_ticker("600519.SW") is None


def test_unknown_or_malformed_international_rejected():
    assert normalize_broker_ticker("XYZ.BOGUS") is None      # unknown exchange
    assert normalize_broker_ticker("TOOLONGBASE.PA") is None  # base > 8 chars
    assert normalize_broker_ticker("MC PA") is None           # space, not a code


def test_existing_us_cn_hk_unchanged():
    assert normalize_broker_ticker("AAPL") == ("AAPL", "US")
    assert normalize_broker_ticker("600519.SS") == ("600519.SH", "CN")
    assert normalize_broker_ticker("700.HK") == ("0700.HK", "HK")


# ---------------------------------------------------------------------------
# entity stoplist — MSCI / broker rating abbreviations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rating", ["OW", "EW", "UW", "MP"])
def test_rating_abbreviations_are_context_gated(rating):
    # bare rating abbreviations must require ticker context (not silently anchor).
    assert is_ambiguous_broker_alias(rating) is True


def test_real_tickers_not_gated():
    for real in ["AAPL", "MSFT", "TSLA", "NVDA"]:
        assert is_ambiguous_broker_alias(real) is False
