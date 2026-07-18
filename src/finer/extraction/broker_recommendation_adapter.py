"""F3 declarative adapter: T3 structured broker JSONL -> NormalizedInvestmentIntent.

Broker research ratings are *declared*, not inferred. This adapter is a pure
keyword-table parser (spec 2026-07-15 key decision 3): no LLM involvement.

Input (per unit of work):
    - one T3 JSONL line (schema_version=t3-v0.2, produced by
      rag_system/structured_extract.py burn)
    - the matching F0 ``ContentRecord`` dict (join key:
      t3.filepath <-> f0.metadata.source_filepath)
    - the matching F1 ``ContentEnvelope`` dict (for the real envelope_id)
    - optionally the F2 anchored envelope dict (for evidence lineage)

Output: ``AdaptResult`` — either a canonical ``NormalizedInvestmentIntent``
or an explicit skip with a reason (no silent drops).

Slot mapping (A2 schema wave, spec §3): ``actionability="recommendation"``,
``target_price`` (schema ``IntentTargetPrice``), ``prior_direction``,
``rating_action`` and ``conviction_source`` are first-class intent fields.
Only sidecar facts without a slot (``key_thesis``, ``horizon_months``,
``analysts``, raw rating words, currency-inference flag) live in metadata.

R6 warning: ``conviction`` here is a *lookup constant* derived from the rating
word class (``conviction_source="derived_lookup"``). It MUST NOT feed any
credibility / KOL scoring computation.

CLI (dry-run by default, mirrors ingestion/broker_research_intake.py):

    python -m finer.extraction.broker_recommendation_adapter \
        --t3-jsonl /path/to/burn_all.jsonl --data-root data [--limit N] [--execute]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from finer.schemas.investment_intent import (
    IntentTargetPrice,
    NormalizedInvestmentIntent,
)

ADAPTER_VERSION = "broker_recommendation_adapter_v1"
T3_SCHEMA_VERSION = "t3-v0.2"

# =============================================================================
# Rating keyword tables (module-level constants; extend here, not inline)
# =============================================================================
# Normalization before lookup: casefold, "-"/"_" -> space, collapse whitespace.

_BULLISH_TOKENS = frozenset({
    "buy", "overweight", "ow", "outperform", "add", "positive", "accumulate",
    "买入", "增持", "surperformance",
})
_NEUTRAL_TOKENS = frozenset({
    "neutral", "hold", "equal weight", "ew", "market perform",
    "sector perform", "in line", "持有", "中性",
})
_BEARISH_TOKENS = frozenset({
    "sell", "underweight", "underperform", "reduce", "卖出", "减持",
})

RATING_DIRECTION_TABLE: Dict[str, str] = {
    **{tok: "bullish" for tok in _BULLISH_TOKENS},
    **{tok: "neutral" for tok in _NEUTRAL_TOKENS},
    **{tok: "bearish" for tok in _BEARISH_TOKENS},
}

# Explicit "no rating" declarations -> skip(not_rated), distinct from unmapped.
NOT_RATED_TOKENS = frozenset({"not rated", "nr", "no rating", "unrated"})

# Conviction lookup (R6: derived constant, NEVER a credibility input).
# strong = outright buy/sell class, tilt = over-/under-weight class,
# neutral class = 0.4.
_CONVICTION_STRONG = frozenset({
    "buy", "sell", "outperform", "underperform", "surperformance",
    "买入", "卖出",
})
_CONVICTION_TILT = frozenset({
    "overweight", "underweight", "ow", "add", "reduce", "positive",
    "accumulate", "增持", "减持",
})
CONVICTION_TABLE: Dict[str, float] = {
    **{tok: 0.7 for tok in _CONVICTION_STRONG},
    **{tok: 0.6 for tok in _CONVICTION_TILT},
    **{tok: 0.4 for tok in _NEUTRAL_TOKENS},
}

CONVICTION_SOURCE = "derived_lookup"

# Declarative parse of a declared rating: fixed, conservative model confidence.
DEFAULT_CONFIDENCE = 0.9


# =============================================================================
# Small result / value models
# =============================================================================

SkipReason = Literal[
    "no_rating",        # rating_current empty / null
    "not_rated",        # explicit Not Rated / NR
    "unmapped_rating",  # non-empty rating outside the keyword table
    "no_ticker",        # neither stock_code nor extraction.ticker usable
    "no_f0",            # CLI-level: no F0 record for t3.filepath
    "no_envelope",      # CLI-level: F0 exists but no F1 envelope
]


@dataclass
class AdaptResult:
    """Either a canonical intent or an explicit, reasoned skip."""

    intent: Optional[NormalizedInvestmentIntent] = None
    skip_reason: Optional[SkipReason] = None
    raw_rating: Optional[str] = None  # original word for unmapped long-tail

    @property
    def skipped(self) -> bool:
        return self.intent is None


# =============================================================================
# Pure helpers
# =============================================================================

def normalize_rating_token(raw: Optional[str]) -> Optional[str]:
    """Casefold, hyphen/underscore -> space, collapse whitespace."""
    if raw is None:
        return None
    token = raw.replace("-", " ").replace("_", " ").casefold()
    token = " ".join(token.split())
    return token or None


def map_rating_to_direction(raw: Optional[str]) -> Optional[str]:
    """Rating word -> bullish/neutral/bearish via table; None if unmapped."""
    token = normalize_rating_token(raw)
    if token is None:
        return None
    return RATING_DIRECTION_TABLE.get(token)


def lookup_conviction(raw: Optional[str]) -> Optional[float]:
    token = normalize_rating_token(raw)
    if token is None:
        return None
    return CONVICTION_TABLE.get(token)


def map_horizon_months(horizon_months: Optional[float]) -> str:
    """T3 horizon_months -> time_horizon_hint.

    None -> long_term: sell-side target prices default to a 12M convention,
    consistent with resolve_horizon_tier's unknown->long default.
    """
    if horizon_months is None:
        return "long_term"
    if horizon_months <= 2:
        return "short_term"
    if horizon_months <= 6:
        return "medium_term"
    return "long_term"


def _normalize_symbol(symbol: str) -> str:
    """Minimal normalization only (upper + strip).

    Deep ticker normalization is deliberately NOT done here — it belongs to
    the F2 wave (enrichment/ is off-limits to this adapter).
    """
    return symbol.strip().upper()


def ticker_segments(t3: Dict[str, Any]) -> List[str]:
    """All symbol spellings for this report: stock_code + '/'-split ticker."""
    segments: List[str] = []
    stock_code = (t3.get("stock_code") or "").strip()
    if stock_code:
        segments.append(_normalize_symbol(stock_code))
    raw_ticker = ((t3.get("extraction") or {}).get("ticker") or "").strip()
    for part in raw_ticker.split("/"):
        part = _normalize_symbol(part)
        if part and part not in segments:
            segments.append(part)
    return segments


def select_target_symbol(t3: Dict[str, Any]) -> Optional[str]:
    """Top-level stock_code first; else last '/'-segment with an exchange
    suffix (contains '.'); else first segment."""
    stock_code = (t3.get("stock_code") or "").strip()
    if stock_code:
        return _normalize_symbol(stock_code)
    raw_ticker = ((t3.get("extraction") or {}).get("ticker") or "").strip()
    if not raw_ticker:
        return None
    parts = [_normalize_symbol(p) for p in raw_ticker.split("/") if p.strip()]
    if not parts:
        return None
    suffixed = [p for p in parts if "." in p]
    return suffixed[-1] if suffixed else parts[0]


def infer_market(symbol: Optional[str]) -> Optional[str]:
    """Heuristic market from ticker suffix (.HK -> HK, .SZ/.SS/6-digit -> CN,
    otherwise US). Documented heuristic, not authoritative."""
    if not symbol:
        return None
    upper = symbol.upper()
    if upper.endswith(".HK"):
        return "HK"
    if upper.endswith((".SZ", ".SS")):
        return "CN"
    if upper.isdigit() and len(upper) == 6:
        return "CN"
    return "US"


def infer_currency(symbol: Optional[str]) -> str:
    """Heuristic currency from ticker suffix when the report declared none:
    .HK -> HKD, .SZ/.SS/6-digit -> CNY, else USD."""
    if symbol:
        upper = symbol.upper()
        if upper.endswith(".HK"):
            return "HKD"
        if upper.endswith((".SZ", ".SS")):
            return "CNY"
        if upper.isdigit() and len(upper) == 6:
            return "CNY"
    return "USD"


def build_target_price(
    t3: Dict[str, Any], target_symbol: Optional[str]
) -> Tuple[Optional[IntentTargetPrice], bool]:
    """Build the schema IntentTargetPrice; second value flags a currency that
    was heuristically inferred from the ticker suffix (the schema model only
    carries declared facts, so the flag goes to intent.metadata)."""
    tp = (t3.get("extraction") or {}).get("target_price") or {}
    value = tp.get("value")
    if value is None:
        return None, False
    currency = tp.get("currency")
    inferred = currency is None
    if inferred:
        currency = infer_currency(target_symbol)
    return IntentTargetPrice(
        value=float(value),
        currency=str(currency),
        prior_value=(
            float(tp["prior_value"]) if tp.get("prior_value") is not None else None
        ),
    ), inferred


def derive_intent_id(
    content_id: str, target_symbol: str, rating_current: str, date: str
) -> str:
    """Content-derived stable id: same report+target+rating+date -> same id,
    so re-runs overwrite the same F3 file instead of doubling."""
    digest = hashlib.sha1(
        "|".join([content_id, target_symbol, rating_current, date]).encode("utf-8")
    ).hexdigest()
    return f"bri_{digest[:24]}"


def match_f2_lineage(
    f2_anchored: Optional[Dict[str, Any]],
    target_symbol: Optional[str],
    segments: List[str],
) -> Tuple[List[str], List[str]]:
    """Find F2 entity anchors whose resolved_symbol matches the target.

    Match rule: exact equality, or both symbols appear in the report's
    '/'-segment spelling set. Returns (block_ids, evidence_span_ids); empty
    lists when nothing matches — honest lineage, the F5 hard gate will block,
    we do not fabricate evidence.
    """
    if not f2_anchored or not target_symbol:
        return [], []
    segment_set = set(segments)
    block_ids: List[str] = []
    span_ids: List[str] = []
    anchors = f2_anchored.get("entity_anchors") or f2_anchored.get("anchors") or []
    for anchor in anchors:
        resolved = anchor.get("resolved_symbol")
        if not resolved:
            continue
        resolved_norm = _normalize_symbol(str(resolved))
        matched = resolved_norm == target_symbol or (
            resolved_norm in segment_set and target_symbol in segment_set
        )
        if not matched:
            continue
        meta = anchor.get("metadata") or {}
        occurrences = meta.get("occurrences") or []
        for occ in occurrences:
            bid = occ.get("block_id")
            sid = occ.get("evidence_span_id")
            if bid and bid not in block_ids:
                block_ids.append(bid)
            if sid and sid not in span_ids:
                span_ids.append(sid)
        top_span = anchor.get("evidence_span_id")
        if top_span and top_span not in span_ids:
            span_ids.append(top_span)
    return block_ids, span_ids


# =============================================================================
# Core pure function
# =============================================================================

def adapt_t3_line(
    t3: Dict[str, Any],
    f0_record: Dict[str, Any],
    envelope: Dict[str, Any],
    f2_anchored: Optional[Dict[str, Any]] = None,
) -> AdaptResult:
    """Merge one T3 structured line with finer lineage into one canonical
    NormalizedInvestmentIntent (or a reasoned skip). Pure function."""
    extraction = t3.get("extraction") or {}

    # --- rating -> direction -----------------------------------------------
    rating_current = extraction.get("rating_current")
    token = normalize_rating_token(rating_current)
    if token is None:
        return AdaptResult(skip_reason="no_rating")
    if token in NOT_RATED_TOKENS:
        return AdaptResult(skip_reason="not_rated", raw_rating=rating_current)
    direction = RATING_DIRECTION_TABLE.get(token)
    if direction is None:
        return AdaptResult(skip_reason="unmapped_rating", raw_rating=rating_current)

    # --- target --------------------------------------------------------------
    target_symbol = select_target_symbol(t3)
    if target_symbol is None:
        return AdaptResult(skip_reason="no_ticker")
    segments = ticker_segments(t3)
    company_name = (t3.get("company_name") or "").strip()
    target_name = company_name or target_symbol
    market = infer_market(target_symbol)

    # --- declarative attributes ----------------------------------------------
    conviction = CONVICTION_TABLE.get(token, 0.4)
    rating_action = extraction.get("rating_action") or "unknown"
    prior_direction = map_rating_to_direction(extraction.get("rating_prior"))
    target_price, currency_inferred = build_target_price(t3, target_symbol)
    time_horizon = map_horizon_months(extraction.get("horizon_months"))

    # --- lineage ---------------------------------------------------------------
    envelope_id = envelope["envelope_id"]
    creator_id = f0_record.get("creator_id")
    content_id = f0_record.get("content_id") or t3.get("report_id") or ""
    block_ids, evidence_span_ids = match_f2_lineage(
        f2_anchored, target_symbol, segments
    )

    intent_id = derive_intent_id(
        content_id, target_symbol, str(rating_current), str(t3.get("date") or "")
    )

    metadata: Dict[str, Any] = {
        "source": ADAPTER_VERSION,
        "t3_schema_version": t3.get("schema_version") or T3_SCHEMA_VERSION,
        "report_id": t3.get("report_id"),
        "broker": t3.get("broker"),
        "report_date": t3.get("date"),
        # Raw rating words as printed in the report; the mapped values live in
        # the direction / prior_direction / rating_action slots.
        "rating_current": rating_current,
        "rating_prior": extraction.get("rating_prior"),
        "horizon_months": extraction.get("horizon_months"),
        "analysts": extraction.get("analysts") or [],
        # True when target_price.currency came from the ticker-suffix
        # heuristic rather than the report itself (slot carries stated facts).
        "target_price_currency_inferred": currency_inferred,
        "ticker_segments": segments,
    }
    key_thesis = extraction.get("key_thesis")
    if key_thesis:
        # No text slot on the intent schema — kept in metadata.
        metadata["key_thesis"] = key_thesis

    intent = NormalizedInvestmentIntent(
        intent_id=intent_id,
        envelope_id=envelope_id,
        block_ids=block_ids,
        creator_id=creator_id,
        target_type="stock",
        target_name=target_name,
        target_symbol=target_symbol,
        market=market,
        direction=direction,  # type: ignore[arg-type]
        # Zero-position-commitment institutional recommendation (spec R2).
        actionability="recommendation",
        # Broker advice != the broker's own trades.
        position_delta_hint="none",
        conviction=conviction,
        # R6: lookup constant — MUST NOT feed credibility scoring.
        conviction_source=CONVICTION_SOURCE,
        rating_action=rating_action,  # type: ignore[arg-type]
        prior_direction=prior_direction,  # type: ignore[arg-type]
        target_price=target_price,
        sentiment_score=None,
        time_horizon_hint=time_horizon,  # type: ignore[arg-type]
        evidence_span_ids=evidence_span_ids,
        confidence=DEFAULT_CONFIDENCE,
        metadata=metadata,
    )
    return AdaptResult(intent=intent, raw_rating=rating_current)


# =============================================================================
# Thin CLI (dry-run by default)
# =============================================================================

@dataclass
class RunStats:
    total: int = 0
    adapted: int = 0
    written: int = 0
    skips: Counter = field(default_factory=Counter)
    unmapped_ratings: Counter = field(default_factory=Counter)


def _iter_jsonl(path: Path, limit: Optional[int] = None) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        count = 0
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
            count += 1
            if limit is not None and count >= limit:
                return


def _build_f0_index(data_root: Path) -> Dict[str, Dict[str, Any]]:
    """source_filepath -> F0 record, from data_root/F0_intake/broker/*.json."""
    index: Dict[str, Dict[str, Any]] = {}
    broker_dir = data_root / "F0_intake" / "broker"
    if not broker_dir.is_dir():
        return index
    for record_path in sorted(broker_dir.glob("*.json")):
        if record_path.name.endswith(".receipt.json"):
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_filepath = (record.get("metadata") or {}).get("source_filepath")
        if source_filepath:
            index[source_filepath] = record
    return index


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run(
    t3_jsonl: Path,
    data_root: Path,
    limit: Optional[int] = None,
    execute: bool = False,
) -> RunStats:
    stats = RunStats()
    f0_index = _build_f0_index(data_root)
    intents_dir = data_root / "F3_intents"

    for t3 in _iter_jsonl(t3_jsonl, limit=limit):
        stats.total += 1
        f0_record = f0_index.get(t3.get("filepath") or "")
        if f0_record is None:
            stats.skips["no_f0"] += 1
            continue
        content_id = f0_record.get("content_id") or ""
        envelope = _load_json(
            data_root / "F1_standardized" / content_id / "content_envelope.json"
        )
        if envelope is None:
            stats.skips["no_envelope"] += 1
            continue
        f2_anchored = _load_json(data_root / "F2_anchored" / f"{content_id}.json")

        result = adapt_t3_line(t3, f0_record, envelope, f2_anchored)
        if result.skipped:
            stats.skips[result.skip_reason or "unknown"] += 1
            if result.skip_reason == "unmapped_rating" and result.raw_rating:
                stats.unmapped_ratings[result.raw_rating] += 1
            continue

        stats.adapted += 1
        if execute:
            intents_dir.mkdir(parents=True, exist_ok=True)
            out_path = intents_dir / f"{result.intent.intent_id}.json"
            # Idempotent: stable content-derived intent_id -> overwrite in place.
            payload = result.intent.to_dict()
            # Keep the original created_at on re-runs so unchanged intents
            # stay byte-stable (created_at is a schema default_factory).
            existing = _load_json(out_path)
            if existing and existing.get("created_at"):
                payload["created_at"] = existing["created_at"]
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            stats.written += 1
    return stats


def _print_stats(stats: RunStats, execute: bool) -> None:
    header = "[execute]" if execute else "[dry-run]"
    print(f"{header} t3 lines: {stats.total}")
    print(f"  adapted:  {stats.adapted}")
    if execute:
        print(f"  written:  {stats.written}")
    print(f"  skipped:  {sum(stats.skips.values())}")
    for reason, count in stats.skips.most_common():
        print(f"    {reason}: {count}")
    if stats.unmapped_ratings:
        print("  unmapped rating long-tail:")
        for word, count in stats.unmapped_ratings.most_common():
            print(f"    {word!r}: {count}")
    if not execute:
        print("dry-run: nothing written. Re-run with --execute to persist.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m finer.extraction.broker_recommendation_adapter",
        description=(
            "F3 declarative adapter: T3 broker JSONL -> NormalizedInvestmentIntent "
            "(dry-run by default)."
        ),
    )
    parser.add_argument(
        "--t3-jsonl", type=Path, required=True,
        help="T3 structured JSONL path (one report per line)",
    )
    parser.add_argument(
        "--data-root", type=Path, required=True,
        help="finer data root containing F0_intake/ F1_standardized/ F2_anchored/",
    )
    parser.add_argument("--limit", type=int, default=None, help="max T3 lines")
    parser.add_argument(
        "--execute", action="store_true",
        help="actually write intents to <data-root>/F3_intents/",
    )
    args = parser.parse_args(argv)

    stats = run(
        t3_jsonl=args.t3_jsonl,
        data_root=args.data_root,
        limit=args.limit,
        execute=args.execute,
    )
    _print_stats(stats, execute=args.execute)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
