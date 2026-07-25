"""F2 anchor grounding bridge — intent.target_symbol → envelope anchor form.

Hoisted from ``scripts/drive_broker_recommendations.py`` (C1): the three-tier
strict→loose bridging rule is business logic shared by the broker declarative
driver and the re-anchor measurement tooling, and the hand-copied variant in
``reanchor_broker_f2_dryrun.py`` had already drifted (it mirrored only two of
the three tiers). This module is the single home; scripts import from here.

The bridge never fabricates: every tier is confined to THIS envelope's anchor
set, and the loose tier only fires on an unambiguous single-anchor match.
"""

from __future__ import annotations

from typing import List, Optional

from finer.enrichment.ticker_normalization import (
    bridge_symbol_equivalent,
    normalize_broker_ticker,
)
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.investment_intent import NormalizedInvestmentIntent

__all__ = ["anchor_resolved_symbols", "bridge_target_symbol"]


def anchor_resolved_symbols(env: ContentEnvelope) -> List[str]:
    """The envelope's F2 entity-anchor resolved_symbols (order-preserving)."""
    symbols = [
        getattr(a, "resolved_symbol", None)
        for a in (env.entity_anchors or [])
    ]
    return [s for s in symbols if s]


def bridge_target_symbol(
    intent: NormalizedInvestmentIntent, env: ContentEnvelope
) -> Optional[str]:
    """Normalize intent.target_symbol to match one of the envelope's F2
    anchor resolved_symbols. Returns the matched symbol or None (no fabrication).

    Three tiers, strict → loose, each confined to THIS envelope's anchor set so
    no cross-corpus symbol can leak in:
      1. exact string match on the raw target_symbol
      2. canonical ``normalize_broker_ticker`` match (US/CN/HK/intl suffix table)
      3. within-envelope loose base bridging — recovers broker dialects the
         canonical resolver rejects in isolation (bare ``8309`` ↔ ``8309.T``,
         ``EQNR`` ↔ ``EQNR.OL``, ``VARB.NS`` ↔ ``VARB.BO``) because the anchor
         disambiguates. The matched anchor's resolved_symbol is what F2 grounding
         is keyed on, so target_symbol is rewritten to the anchor form.

    B1: a successful tier-2/tier-3 bridge also refreshes ``intent.market``
    from the bridged symbol — the intent otherwise keeps its stale F3-era
    market (often a wrong "US"), which would put the action on the wrong
    trading calendar. When normalization cannot name a market (tier-3 anchor
    with a suffix outside the canonical tables), the market is left unchanged
    — no fabrication.

    Only mutates the in-memory intent; pipeline code untouched.
    """
    anchor_symbols = anchor_resolved_symbols(env)
    anchor_set = set(anchor_symbols)

    raw = intent.target_symbol
    if raw in anchor_set:
        return raw

    normalized = normalize_broker_ticker(raw) if raw else None
    if normalized and normalized.symbol in anchor_set:
        intent.target_symbol = normalized.symbol
        if normalized.market is not None:
            intent.market = normalized.market
        return normalized.symbol

    if raw:
        loose_hits = [
            s for s in anchor_symbols if bridge_symbol_equivalent(raw, s)
        ]
        # Only bridge on an unambiguous single-anchor match — a base that maps to
        # two different anchors in one envelope would be fabrication, so skip it.
        if len(set(loose_hits)) == 1:
            matched = loose_hits[0]
            intent.target_symbol = matched
            # The anchor form decides the market too (e.g. EQNR → EQNR.OL is
            # not a US instrument). None → keep the intent's market as-is.
            anchor_normalized = normalize_broker_ticker(matched)
            if anchor_normalized is not None:
                intent.market = anchor_normalized.market
            return matched
    return None
