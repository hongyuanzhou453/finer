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
