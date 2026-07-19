"""F2 broker ticker suffix normalization — explicit mapping tables, no regex magic.

Broker research PDFs carry stock codes in many vendor dialects (Reuters RIC,
Bloomberg, bare exchange-local codes). F2 needs one canonical
``resolved_symbol`` shape per market so anchors from broker corpora merge with
the curated KOL registry instead of forking a second symbol universe.

Canonical output shapes (kept consistent with ``finer.entity_registry``):

- US equities:      bare uppercase letters (``AAPL``), market ``US``
- CN A-shares:      ``600519.SH`` / ``300750.SZ``, market ``CN``
- HK equities:      4-digit zero-padded ``0700.HK`` (5-digit kept as-is), market ``HK``
- TW equities:      ``2330.TW``, market ``TW``
- JP equities:      ``9202.T``, market ``JP``

Normalization happens where ``resolved_symbol`` is produced; the original raw
form must be preserved by callers in ``raw_text`` / aliases.

All rules are explicit table rows below — add a row, don't widen a regex.
"""

from __future__ import annotations

from typing import Dict, NamedTuple, Optional, Tuple


class NormalizedTicker(NamedTuple):
    """Canonical (symbol, market) for one broker-dialect stock code."""

    symbol: str
    market: str


# ── Suffix mapping table ─────────────────────────────────────────────────────
# raw suffix (uppercased, without dot) → (canonical suffix or "" for bare, market)
# "" means the base code alone is canonical (US convention: bare letters).
SUFFIX_NORMALIZATION_TABLE: Dict[str, Tuple[str, str]] = {
    # US venues — RIC and vendor dialects all collapse to bare US semantics
    "US": ("", "US"),
    "N": ("", "US"),        # RIC: NYSE
    "NYSE": ("", "US"),
    "O": ("", "US"),        # RIC: NASDAQ
    "OQ": ("", "US"),       # RIC: NASDAQ
    "NSDQ": ("", "US"),     # vendor: NASDAQ (C9)
    # Mainland China — RIC ".SS" means Shanghai, canonical is ".SH"
    "SS": ("SH", "CN"),
    "SH": ("SH", "CN"),
    "SZ": ("SZ", "CN"),
    # Hong Kong
    "HK": ("HK", "HK"),
    # Taiwan
    "TW": ("TW", "TW"),
    # Tokyo (explicit suffix only; bare 4-digit codes stay ambiguous → rejected)
    "T": ("T", "JP"),
}

# ── International exchange suffixes ──────────────────────────────────────────
# raw suffix (uppercased, without dot) → (canonical suffix, market, base_kind).
# Non-US/CN/HK venues the broker corpus references (Reuters RIC / Bloomberg
# dialects). The curated KOL registry is US/CN/HK-centric, so these are a
# broker-only universe — they need only normalize CONSISTENTLY so a broker
# intent's target_symbol and its F2 anchor collapse to the same resolved_symbol
# (the driver bridge). Vendor variants for one exchange map to a single canonical
# suffix (e.g. Reuters .PA and Bloomberg FP both → PA). ``base_kind`` guards the
# base shape so a mismatched code+exchange (e.g. a Shanghai code "600519.L") stays
# unmappable: European venues use ALPHA tickers, Asian venues numeric/alphanumeric
# codes. Extend by adding a row — never widen a regex. (C9)
_ALPHA, _ALNUM = "alpha", "alnum"
INTERNATIONAL_SUFFIX_TABLE: Dict[str, Tuple[str, str, str]] = {
    "L": ("L", "UK", _ALPHA), "LN": ("L", "UK", _ALPHA),   # London LSE
    "PA": ("PA", "FR", _ALPHA), "FP": ("PA", "FR", _ALPHA),  # Euronext Paris
    "AS": ("AS", "NL", _ALPHA),                              # Euronext Amsterdam
    "DE": ("DE", "DE", _ALPHA),                              # XETRA Germany
    "SW": ("SW", "CH", _ALPHA),                              # SIX Swiss
    "MI": ("MI", "IT", _ALPHA),                              # Borsa Italiana
    "MC": ("MC", "ES", _ALPHA),                              # BME Madrid
    "ST": ("ST", "SE", _ALPHA),                              # Nasdaq Stockholm
    "HE": ("HE", "FI", _ALPHA),                              # Nasdaq Helsinki
    "AX": ("AX", "AU", _ALPHA),                              # ASX Australia
    "TO": ("TO", "CA", _ALPHA),                              # Toronto TSX
    "KS": ("KS", "KR", _ALNUM), "KQ": ("KQ", "KR", _ALNUM), # Korea KOSPI / KOSDAQ
    "SI": ("SI", "SG", _ALNUM),                              # Singapore SGX
    "KL": ("KL", "MY", _ALNUM),                              # Bursa Malaysia
    "NS": ("NS", "IN", _ALNUM), "BO": ("BO", "IN", _ALNUM), # India NSE / BSE
}


# ── Bare 6-digit A-share segment table ───────────────────────────────────────
# first two digits → (canonical suffix, market). Codes outside these segments
# (BSE 4xx/8xx/92x, KR 0-padded KOSPI codes…) are NOT confidently mappable and
# must be rejected by returning None.
CN_SIX_DIGIT_SEGMENT_TABLE: Dict[str, Tuple[str, str]] = {
    "60": ("SH", "CN"),  # SSE main board
    "68": ("SH", "CN"),  # SSE STAR market
    "00": ("SZ", "CN"),  # SZSE main board
    "30": ("SZ", "CN"),  # SZSE ChiNext
}

_MAX_US_TICKER_LEN = 5


def _is_all_digits(text: str) -> bool:
    return text.isascii() and text.isdigit()


def _is_all_alpha(text: str) -> bool:
    return text.isascii() and text.isalpha()


def _normalize_hk_base(base: str) -> Optional[str]:
    if not _is_all_digits(base) or not 1 <= len(base) <= 5:
        return None
    # HK convention in the curated registry: 4-digit zero-padded (0700.HK).
    return base if len(base) == 5 else base.zfill(4)


def _normalize_international(base: str, suffix: str) -> Optional[NormalizedTicker]:
    """Non-US/CN/HK exchange suffixes → canonical ``{base}.{suffix}`` (C9).

    Base is validated as a plain alphanumeric code (1-8 chars); anything else
    (spaces, punctuation, over-long) is rejected as unmappable.
    """
    mapping = INTERNATIONAL_SUFFIX_TABLE.get(suffix)
    if mapping is None:
        return None
    canonical_suffix, market, base_kind = mapping
    if not (base.isascii() and 1 <= len(base) <= 8):
        return None
    ok = _is_all_alpha(base) if base_kind == _ALPHA else base.isalnum()
    if ok:
        return NormalizedTicker(f"{base}.{canonical_suffix}", market)
    return None


def normalize_broker_ticker(raw_code: str) -> Optional[NormalizedTicker]:
    """Normalize one broker-dialect stock code to canonical (symbol, market).

    Returns ``None`` when the code cannot be confidently mapped — ambiguous
    bare 4-digit codes (HK vs JP), unknown exchange suffixes, malformed input.
    Callers must keep the raw form for audit; this function only decides the
    canonical ``resolved_symbol``.
    """
    if not raw_code:
        return None
    code = raw_code.strip().upper()
    if not code or " " in code:
        return None

    if "." in code:
        base, _, suffix = code.rpartition(".")
        if not base or not suffix:
            return None
        mapping = SUFFIX_NORMALIZATION_TABLE.get(suffix)
        if mapping is None:
            return _normalize_international(base, suffix)
        canonical_suffix, market = mapping
        if canonical_suffix == "":  # US bare-letter convention
            if _is_all_alpha(base) and 1 <= len(base) <= _MAX_US_TICKER_LEN:
                return NormalizedTicker(base, market)
            return None
        if canonical_suffix == "HK":
            hk_base = _normalize_hk_base(base)
            if hk_base is None:
                return None
            return NormalizedTicker(f"{hk_base}.HK", market)
        if canonical_suffix in ("SH", "SZ"):
            if _is_all_digits(base) and len(base) == 6:
                return NormalizedTicker(f"{base}.{canonical_suffix}", market)
            return None
        if canonical_suffix == "TW":
            if _is_all_digits(base) and 4 <= len(base) <= 6:
                return NormalizedTicker(f"{base}.TW", market)
            return None
        if canonical_suffix == "T":
            if _is_all_digits(base) and len(base) == 4:
                return NormalizedTicker(f"{base}.T", market)
            return None
        return None

    # Bare 6-digit → A-share segment table
    if _is_all_digits(code) and len(code) == 6:
        mapping = CN_SIX_DIGIT_SEGMENT_TABLE.get(code[:2])
        if mapping is None:
            return None
        canonical_suffix, market = mapping
        return NormalizedTicker(f"{code}.{canonical_suffix}", market)

    # Bare 4/5-digit numeric: ambiguous (HK vs JP vs KR) → reject
    if _is_all_digits(code):
        return None

    # Bare letters → US semantics
    if _is_all_alpha(code) and 1 <= len(code) <= _MAX_US_TICKER_LEN:
        return NormalizedTicker(code, "US")

    return None
