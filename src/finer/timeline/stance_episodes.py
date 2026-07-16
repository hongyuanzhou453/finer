"""F7 stance episodes — the persistent-viewpoint projection the scoring path needs.

A KOL restates a standing view across weeks: trader_ji's weekly-strategy template
repeats "减持优质高估值美股（类似苹果/cost）" in 19 of 24 weeks, so F3 emits one
intent per restatement. Those restatements are *truth*, not noise — the
2026-07-03 intent-dedupe spec deliberately reserves cross-envelope repetition as
the place real stance FLIPS live, which is why they must not be suppressed at F3.
What is wrong is the SCORING: counting every restatement as an independent bet
inflated trader_ji's settled record 8x (8 of 12 settled calls were one AAPL view)
and lets a repeated template line single-handedly flip the 言行不一 majority vote.

A stance **episode** is one viewpoint held over time: consecutive same-direction
actions on one stance slot, bounded by a flip. It is scored from its FIRST
statement — the point a follower would actually have acted on it; later
restatements are reaffirmations, not new entry points. A flip opens a new
episode, so genuine changes of mind still count as separate calls.

Identity reuses :func:`finer.timeline.stance_snapshot.stance_key_of` — the
battle-tested slot key that already encodes the non-obvious rule that two sectors
proxying to the SAME ETF must stay distinct viewpoints. Never re-derive identity
from (kol, ticker): that reintroduces the proxy-collapse bug that key documents.

This is a read-side projection: it reads F5 actions and writes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from finer.schemas.trade_action import TradeAction
from finer.timeline.stance_snapshot import signal_clock_of, stance_key_of

_BEIJING = timezone(timedelta(hours=8))


def _clock_dt(action: TradeAction) -> datetime:
    """Chronological sort key for the canonical signal clock.

    Real F5 slots mix UTC offsets (US actions carry -05:00/-04:00 across the
    DST boundary, CN actions +08:00), so comparing the raw ISO strings is NOT
    chronological — "T09:00+08:00" sorts after "T08:00-04:00" despite being 11
    hours earlier. Parse to aware datetimes; naive stamps get the repo's
    Beijing convention.
    """
    dt = datetime.fromisoformat(signal_clock_of(action))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_BEIJING)
    return dt


@dataclass(frozen=True)
class StanceEpisode:
    """One viewpoint held over time (same stance slot, same direction, until a flip)."""

    creator_id: str
    stance_key: str
    ticker: str
    direction: str
    first_stated_at: str
    last_stated_at: str
    anchor: TradeAction
    actions: Tuple[TradeAction, ...]

    @property
    def restatement_count(self) -> int:
        """How many times the view was stated (1 = said once, never repeated)."""
        return len(self.actions)

    @property
    def is_standing_view(self) -> bool:
        """True when the view was restated at least once after first stating it."""
        return len(self.actions) > 1

    @property
    def backtest_result(self):
        """Outcome of the FIRST statement — a follower's real entry point."""
        return self.anchor.backtest_result

    @property
    def validation_status(self):
        return self.anchor.validation_status


def _attributable(action: TradeAction) -> Optional[Tuple[str, str]]:
    """(creator_id, ticker) when the action can carry a stance, else None."""
    creator = (action.source.creator_id or "").strip()
    if not creator or creator.lower() in ("unknown", "none", ""):
        return None
    ticker = action.target.ticker_normalized or action.target.ticker
    if not ticker:
        return None
    return creator, ticker


def build_stance_episodes(actions: Iterable[TradeAction]) -> List[StanceEpisode]:
    """Project F5 actions into stance episodes (one persistent viewpoint each).

    Actions are grouped by (creator, ``stance_key_of``), ordered by the canonical
    signal clock (ties broken by trade_action_id, matching ``build_snapshot``),
    then split into episodes wherever the direction changes.

    Returns episodes ordered by (creator, stance_key, first_stated_at).
    """
    groups: Dict[Tuple[str, str], List[TradeAction]] = {}
    for action in actions:
        attributed = _attributable(action)
        if attributed is None:
            continue
        creator, ticker = attributed
        groups.setdefault((creator, stance_key_of(action, ticker)), []).append(action)

    episodes: List[StanceEpisode] = []
    for (creator, key), group in groups.items():
        group.sort(key=lambda a: (_clock_dt(a), a.trade_action_id))

        run: List[TradeAction] = []
        run_direction: Optional[str] = None

        def _flush() -> None:
            if not run:
                return
            first = run[0]
            episodes.append(
                StanceEpisode(
                    creator_id=creator,
                    stance_key=key,
                    ticker=first.target.ticker_normalized or first.target.ticker,
                    direction=run_direction or "",
                    first_stated_at=signal_clock_of(first),
                    last_stated_at=signal_clock_of(run[-1]),
                    anchor=first,
                    actions=tuple(run),
                )
            )

        for action in group:
            direction = action.direction.value if hasattr(action.direction, "value") else str(action.direction)
            if run_direction is not None and direction != run_direction:
                _flush()  # a flip ends the episode and opens a new call
                run = []
            run_direction = direction
            run.append(action)
        _flush()

    episodes.sort(key=lambda e: (e.creator_id, e.stance_key, _clock_dt(e.anchor)))
    return episodes


def episodes_by_creator(
    episodes: Iterable[StanceEpisode],
) -> Dict[str, List[StanceEpisode]]:
    """Group episodes by creator_id (convenience for per-KOL scorers)."""
    out: Dict[str, List[StanceEpisode]] = {}
    for e in episodes:
        out.setdefault(e.creator_id, []).append(e)
    return out
