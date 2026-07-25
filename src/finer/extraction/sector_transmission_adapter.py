"""T9 sector transmission chains → declarative F3 sector intents (D1).

Second declarative adapter after ``broker_recommendation_adapter`` (A3
pattern): pure function, zero LLM, content-derived stable intent ids
(``t9i_`` + sha1[:24] — byte-stable reruns), dry-run-first driving via
``scripts/drive_t9_sector_intents.py``.

Input: one T9 JSONL row (schema_version t9-v0.1, produced by the NAS burn
``t9_sector_deep``): ``extraction.industry_or_theme`` (free text),
``extraction.cycle_view`` (improving/deteriorating/stable/mixed/None),
transmission chains, beneficiaries/losers (companies — NOT consumed here;
they are stock-level signals whose slots belong to the T6/EstimateRevision
design, see the D2 decision record).

Output: at most ONE sector intent per T9 row —
``target_type="sector"``, ``target_symbol=<sector placeholder key>`` (e.g.
``SEMICONDUCTOR``), direction from cycle_view. Downstream it rides the exact
broker declarative path: anchor bridge (the envelope's F2 sector anchors
resolve to the same placeholder keys), F4 policy, canonical F5 with the
sector→proxy-ETF mapping (``configs/sector_proxies.yaml``; unmapped sectors
reject as ``sector_proxy_not_configured`` — an expected funnel that doubles
as the proxies.yaml backlog report).

Honesty rules:
  * mixed / missing cycle_view → no intent (no direction claim to encode);
  * themes explicitly scoped to foreign/global markets (美国/全球/USD/Global…)
    are skipped — the configured proxies are CN ETFs and would misrepresent
    the claim;
  * theme→sector mapping is a deterministic sector_name substring match; no
    fuzzy inference, no LLM.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from finer.schemas.investment_intent import NormalizedInvestmentIntent

__all__ = [
    "CYCLE_VIEW_DIRECTION",
    "FOREIGN_THEME_MARKERS",
    "adapt_t9_record",
    "derive_t9_intent_id",
    "match_theme_to_sector",
]

#: cycle_view → intent direction. mixed/None deliberately absent (no claim).
CYCLE_VIEW_DIRECTION: Dict[str, str] = {
    "improving": "bullish",
    "deteriorating": "bearish",
    "stable": "neutral",
}

#: Theme prefixes/markers that scope the claim to non-CN markets — the
#: configured sector proxies are CN ETFs, so mapping these would fabricate a
#: different trade than the research expressed.
FOREIGN_THEME_MARKERS: Tuple[str, ...] = (
    "美国", "美股", "全球", "海外", "欧洲", "日本", "韩国", "印度",
    "USD", "US ", "Global", "Europe", "Japan",
)

ADAPTER_VERSION = "t9-adapter-v0.1"


def derive_t9_intent_id(filepath: str, sector_key: str, cycle_view: str) -> str:
    """Content-derived stable id: same row → same id, reruns overwrite."""
    digest = hashlib.sha1(
        f"{filepath}|{sector_key}|{cycle_view}".encode("utf-8")
    ).hexdigest()
    return f"t9i_{digest[:24]}"


def match_theme_to_sector(
    theme: Optional[str], sector_names: Mapping[str, str]
) -> Optional[Tuple[str, str]]:
    """Map a free-text theme to a (sector_key, sector_name) pair, or None.

    Deterministic: the sector's Chinese ``sector_name`` (from
    sector_proxies.yaml) must appear verbatim in the theme. Foreign-scoped
    themes are refused before matching. Ties break on the LONGEST matching
    sector_name (most specific claim), then lexicographic key for stability.
    """
    if not theme:
        return None
    stripped = theme.strip()
    for marker in FOREIGN_THEME_MARKERS:
        if marker in stripped:
            return None
    hits = [
        (key, name)
        for key, name in sector_names.items()
        if name and name in stripped
    ]
    if not hits:
        return None
    hits.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    return hits[0]


def adapt_t9_record(
    record: Dict[str, Any],
    f0_record: Dict[str, Any],
    envelope_id: str,
    sector_names: Mapping[str, str],
) -> Tuple[Optional[NormalizedInvestmentIntent], Optional[str]]:
    """Adapt one T9 JSONL row to a sector intent (or a skip reason).

    Returns (intent, None) on success, (None, skip_reason) otherwise.
    Pure: no I/O, no clock beyond created_at stamping, no LLM.
    """
    extraction = record.get("extraction") or {}
    theme = extraction.get("industry_or_theme")
    cycle_view = extraction.get("cycle_view")

    direction = CYCLE_VIEW_DIRECTION.get(cycle_view or "")
    if direction is None:
        return None, "no_direction_claim"  # mixed / missing cycle_view

    matched = match_theme_to_sector(theme, sector_names)
    if matched is None:
        if theme and any(m in theme for m in FOREIGN_THEME_MARKERS):
            return None, "theme_market_foreign"
        return None, "theme_unmapped"
    sector_key, sector_name = matched

    filepath = record.get("filepath") or record.get("filename") or ""
    intent = NormalizedInvestmentIntent(
        intent_id=derive_t9_intent_id(filepath, sector_key, cycle_view),
        envelope_id=envelope_id,
        block_ids=[],
        creator_id=str(
            f0_record.get("creator_id") or record.get("broker") or "unknown"
        ),
        target_type="sector",
        target_name=sector_name,
        target_symbol=sector_key,
        market=None,  # the sector proxy decides the tradable market
        direction=direction,
        actionability="recommendation",
        position_delta_hint="none",
        conviction=0.6,
        confidence=0.85,
        conviction_source="derived_lookup",  # R6: never feeds credibility
        evidence_span_ids=[],  # F2 grounding re-derives via the anchor bridge
        ambiguity_flags=[],
        metadata={
            "adapter_version": ADAPTER_VERSION,
            "t9_schema_version": record.get("schema_version"),
            "t9_theme": theme,
            "t9_cycle_view": cycle_view,
            "t9_theme_window": extraction.get("theme_window"),
            "t9_policy_dependency": extraction.get("policy_dependency"),
            "t9_source_filepath": filepath,
            "signal_class": "broker_recommendation",
        },
        created_at=datetime.now(),
    )
    return intent, None
