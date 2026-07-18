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
            return None
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
