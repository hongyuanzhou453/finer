"""KOL trading-style profile service (declared + observed).

Builds the two-layer :class:`TradingStyleProfile`:

- declared: hand-annotated ``trading_style:`` block in
  ``configs/creators/{creator_id}.yaml`` (loaded via
  :func:`finer.config.load_creator_config`).
- observed: aggregate statistics over the KOL's attributed F5 TradeActions —
  short-side ratio from the action chain itself, margin/leverage mentions and
  left/right entry-timing signals from the F3 style flags that the canonical
  builder writes into ``TradeAction.metadata``.

The two layers stay independent: a missing YAML block yields ``declared=None``,
a KOL with no attributed actions yields ``observed=None``, and the profile is
still returned so the frontend can render the corresponding empty states.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from finer.config import load_creator_config
from finer.paths import REPO_ROOT
from finer.schemas.kol_profile import (
    DeclaredTradingStyle,
    ObservedTradingStyle,
    TradingStyleProfile,
)
from finer.schemas.trade_action import ActionType, TradeAction
from finer.services.repository import TradeActionRepository

logger = logging.getLogger(__name__)

# Actions whose primary step operates on the short side.
_SHORT_SIDE_TYPES = {
    ActionType.SHORT,
    ActionType.CLOSE_SHORT,
    ActionType.BUY_PUT,
    ActionType.SELL_CALL,
}

# Non-directional primary steps excluded from the directional sample.
_NON_DIRECTIONAL_TYPES = {ActionType.HOLD, ActionType.WATCH}

# Majority-vote thresholds for the observed entry style.
_ENTRY_STYLE_MIN_SAMPLE = 5
_ENTRY_STYLE_MAJORITY = 0.6

# Directional sample below this is flagged low_sample.
_LOW_SAMPLE_THRESHOLD = 5


def load_declared_style(
    creator_id: str,
    root: Path = REPO_ROOT,
) -> Optional[DeclaredTradingStyle]:
    """Load the hand-annotated trading style from the creator registry.

    Returns None when the creator profile or its ``trading_style`` block is
    missing/invalid — "not annotated" is a first-class state, not an error.
    Delegates to KOLRegistry (the file-truth reader over configs/creators/),
    which owns the block-isolation semantics; signature kept for existing
    callers.
    """
    from finer.services.kol_registry import get_registry

    return get_registry(root).declared_style(creator_id)


def compute_observed_style(
    actions: Sequence[TradeAction],
    computed_at: Optional[datetime] = None,
) -> Optional[ObservedTradingStyle]:
    """Aggregate observed style statistics from a KOL's TradeActions.

    Returns None for an empty action list (no data ≠ zero counts).

    Votes are cast once per **stance episode** (a standing view held over time),
    not once per TradeAction. A KOL whose weekly template restates the same view
    would otherwise stuff the ballot — 19 identical votes in a ~24 denominator can
    single-handedly flip ``entry_style_observed`` and manufacture a 自述-vs-实测
    contradiction that says more about their template than their trading. Each
    episode votes with its first statement; a flip opens a new episode, so real
    changes of stance still get their own vote. See timeline/stance_episodes.py.
    """
    if not actions:
        return None

    from finer.timeline.stance_episodes import build_stance_episodes

    episodes = build_stance_episodes(actions)
    # Fall back to raw actions only when nothing can be attributed to a stance
    # slot (keeps "no data ≠ zero counts" rather than reporting a degenerate 0).
    voters = [ep.anchor for ep in episodes] or list(actions)

    directional = 0
    short_side = 0
    margin_mentions = 0
    leverage_mentions = 0
    left_side = 0
    right_side = 0

    for action in voters:
        primary = action.action_chain[0] if action.action_chain else None
        if primary is not None and primary.action_type not in _NON_DIRECTIONAL_TYPES:
            directional += 1
            if primary.action_type in _SHORT_SIDE_TYPES:
                short_side += 1

        meta = action.metadata or {}
        if meta.get("margin_flag") is True:
            margin_mentions += 1
        if meta.get("leverage_flag") is True:
            leverage_mentions += 1
        entry_style = meta.get("entry_timing_style")
        if entry_style == "left_side":
            left_side += 1
        elif entry_style == "right_side":
            right_side += 1

    entry_sample = left_side + right_side
    entry_style_observed = "unknown"
    if entry_sample >= _ENTRY_STYLE_MIN_SAMPLE:
        left_ratio = left_side / entry_sample
        right_ratio = right_side / entry_sample
        if left_ratio >= _ENTRY_STYLE_MAJORITY:
            entry_style_observed = "left_side"
        elif right_ratio >= _ENTRY_STYLE_MAJORITY:
            entry_style_observed = "right_side"
        else:
            entry_style_observed = "mixed"

    return ObservedTradingStyle(
        sample_size=len(voters),  # distinct stance episodes, not restatements
        directional_sample_size=directional,
        short_side_count=short_side,
        short_ratio=(short_side / directional) if directional > 0 else None,
        margin_mention_count=margin_mentions,
        leverage_mention_count=leverage_mentions,
        left_side_count=left_side,
        right_side_count=right_side,
        entry_style_observed=entry_style_observed,
        entry_style_sample_size=entry_sample,
        low_sample=directional < _LOW_SAMPLE_THRESHOLD,
        computed_at=computed_at or datetime.now(),
        window_label="ALL",
    )


def build_style_profile(
    creator_id: str,
    repository: Optional[TradeActionRepository] = None,
    root: Path = REPO_ROOT,
) -> TradingStyleProfile:
    """Build the full two-layer style profile for one creator."""
    declared = load_declared_style(creator_id, root=root)

    repo = repository if repository is not None else TradeActionRepository()
    attributed: List[TradeAction] = [
        action
        for action in repo.load_all_actions()
        if action.source is not None and action.source.creator_id == creator_id
    ]
    observed = compute_observed_style(attributed)

    from finer.services.kol_registry import get_registry

    profile = get_registry(root).get(creator_id)
    display_name: Optional[str] = profile.display_name if profile else None

    return TradingStyleProfile(
        creator_id=creator_id,
        display_name=display_name,
        declared=declared,
        observed=observed,
    )
