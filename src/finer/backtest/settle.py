"""Settlement lifecycle owner for F5 TradeActions (F8 settle service).

Flips ``validation_status`` from PENDING to VERIFIED/FAILED once a per-action
backtest reaches a terminal exit, and incrementally re-evaluates PENDING
actions whose backtest is missing or still open. This is the missing owner of
the validation lifecycle: canonical F5 output only ever produces PENDING /
UNDER_REVIEW, and ``TradeActionRepository.update_validation_status`` (the
atomic file+index writer) previously had zero callers, so no action ever
settled.

Canonical "settled" definition
------------------------------
    settled := validation_status in {VERIFIED, FAILED}

VERIFIED means the KOL call closed with a direction-adjusted net profit
(``backtest_result.return_pct > 0``); FAILED means it closed flat or at a loss
(``return_pct <= 0``, zero counts as FAILED). Reputation/credibility code that
still uses "``backtest_result`` exists" as its settled proxy is a transitional
compatibility reading; this module's definition is the target semantics.

State machine (one pass per action)
-----------------------------------
========== ============================================ =============================
status     backtest_result condition                    action -> outcome
========== ============================================ =============================
PENDING    exit in TERMINAL, return_pct > 0             flip -> VERIFIED
PENDING    exit in TERMINAL, return_pct <= 0            flip -> FAILED
PENDING    exit == END_OF_PERIOD or UNKNOWN             re-evaluate; write new result;
                                                        flip only if now terminal
PENDING    backtest_result is None                      re-evaluate (skips: see below)
PENDING    exit in {SIGNAL_REVERSAL, MANUAL}            skip (manual semantics — a
                                                        human/upstream signal owns it)
UNDER_-    any                                          skip (human review outranks
REVIEW                                                  automation)
VERIFIED/  any                                          skip (terminal states never
FAILED                                                  flip back)
========== ============================================ =============================

Re-evaluation skips keep the action PENDING and write nothing:
``non_directional`` (neutral/watchlist views are not follow-tradable) and the
no-data family (``no_price_data`` / ``no_entry_bar`` / ``insufficient_bars``),
which will naturally retry on the next settle run once prices exist.

Design note: no ``incremental`` parameter
-----------------------------------------
The approved plan sketched an ``incremental: bool`` flag whose two readings
contradicted each other (daily mode vs. first-run backfill both need to flip
already-terminal PENDING results). Settlement is *inherently* incremental —
terminal states never flip back, UNDER_REVIEW is never touched, and no-data
actions are retried next run — so a full/incremental split adds a mode switch
without adding behavior. The flag is therefore dropped and the full state
machine always runs; ``limit`` and ``dry_run`` remain the operational knobs.

Safety: ``dry_run=True`` (the default) computes and reports every transition
without performing any write. All writes go through the repository's atomic
methods (``update_backtest_result`` / ``update_validation_status``: tmp file +
fsync + os.replace + reindex). Per-action failures are recorded in
``SettleReport.errors`` and never abort the run.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from finer.backtest.per_action import evaluate_action
from finer.backtest.yahoo_prices import fetch_daily_closes
from finer.schemas.trade_action import (
    ExitReason,
    TradeAction,
    ValidationStatus,
)
from finer.services.repository import TradeActionRepository, get_repository

logger = logging.getLogger(__name__)

#: Exit reasons that settle a simulated follow-trade: the position closed on
#: its own rules, so the call's outcome is final and the status may flip.
TERMINAL_EXIT_REASONS = {
    ExitReason.STOP_LOSS,
    ExitReason.TARGET_REACHED,
    ExitReason.TIME_EXIT,
}

#: Exit reasons owned by a human or an upstream signal — automation must not
#: overwrite or re-simulate them.
MANUAL_SEMANTICS_EXIT_REASONS = {
    ExitReason.SIGNAL_REVERSAL,
    ExitReason.MANUAL,
}

#: Evaluator skip reasons that mean "no usable price series yet" — the action
#: stays PENDING and is retried on the next run.
NO_DATA_SKIP_REASONS = {"no_price_data", "no_entry_bar", "insufficient_bars"}

#: Price fetcher contract: ticker -> ascending (date, close) series.
PriceFetcher = Callable[[str], Sequence[Tuple[date, float]]]


@dataclass
class SettleReport:
    """Aggregate outcome of one settle pass (all counters are per-action)."""

    scanned: int = 0
    verified: int = 0
    failed: int = 0
    reevaluated: int = 0
    refreshed_still_open: int = 0
    skipped_under_review: int = 0
    skipped_non_directional: int = 0
    skipped_no_data: int = 0
    skipped_terminal: int = 0  # already VERIFIED/FAILED — never re-flipped
    skipped_manual_semantics: int = 0  # SIGNAL_REVERSAL / MANUAL exits
    errors: List[Dict[str, str]] = field(default_factory=list)
    dry_run: bool = True

    def to_dict(self) -> dict:
        """Plain-dict view for CLI/JSON reporting."""
        return asdict(self)


def settle_actions(
    *,
    repo: Optional[TradeActionRepository] = None,
    fetch_closes: Optional[PriceFetcher] = None,
    dry_run: bool = True,
    limit: Optional[int] = None,
) -> SettleReport:
    """Run one settle pass over every F5 action and return the report.

    Args:
        repo: TradeAction repository; defaults to the process singleton.
        fetch_closes: Daily-close source, ``ticker -> [(date, close), ...]``.
            Defaults to the Yahoo chart source; tests inject fake series.
            Fetched at most once per ticker per pass (in-memory cache).
        dry_run: When True (default), count every transition that *would*
            happen but perform no write.
        limit: Cap on the number of PENDING actions fed into the state
            machine (scanning stops once reached). Terminal/UNDER_REVIEW
            skips do not consume the budget.

    Returns:
        SettleReport with per-transition counters and per-action errors.
    """
    repo = repo if repo is not None else get_repository()
    fetch = fetch_closes if fetch_closes is not None else fetch_daily_closes
    report = SettleReport(dry_run=dry_run)

    # Per-pass price cache: ticker -> series, or the exception the first
    # fetch raised (so sibling actions fail fast instead of refetching).
    price_cache: Dict[str, Union[Sequence[Tuple[date, float]], Exception]] = {}

    def closes_for(ticker: str) -> Sequence[Tuple[date, float]]:
        cached = price_cache.get(ticker)
        if isinstance(cached, Exception):
            raise RuntimeError(
                f"price fetch already failed for {ticker}: {cached}"
            ) from cached
        if cached is not None:
            return cached
        try:
            closes = list(fetch(ticker))
        except Exception as e:
            price_cache[ticker] = e
            raise
        price_cache[ticker] = closes
        return closes

    def apply_flip(trade_action_id: str, return_pct: float) -> None:
        new_status = (
            ValidationStatus.VERIFIED
            if return_pct > 0
            else ValidationStatus.FAILED
        )
        if not dry_run:
            if not repo.update_validation_status(trade_action_id, new_status):
                raise RuntimeError(
                    "update_validation_status returned False "
                    "(action missing from index?)"
                )
        if new_status is ValidationStatus.VERIFIED:
            report.verified += 1
        else:
            report.failed += 1

    def settle_one(action: TradeAction) -> None:
        br = action.backtest_result

        if br is not None and br.exit_reason in MANUAL_SEMANTICS_EXIT_REASONS:
            report.skipped_manual_semantics += 1
            return

        if (
            br is not None
            and br.exit_reason in TERMINAL_EXIT_REASONS
            and br.return_pct is not None
        ):
            apply_flip(action.trade_action_id, br.return_pct)
            return

        # Re-evaluation path: no result yet, still-open result
        # (END_OF_PERIOD), UNKNOWN, or a terminal result missing return_pct.
        ticker = action.target.ticker_normalized or action.target.ticker
        closes = closes_for(ticker)
        result, skip = evaluate_action(action, closes)

        if skip is not None:
            if skip.reason == "non_directional":
                report.skipped_non_directional += 1
            else:  # NO_DATA_SKIP_REASONS — retry naturally on the next pass
                report.skipped_no_data += 1
            return

        report.reevaluated += 1
        if not dry_run:
            if not repo.update_backtest_result(action.trade_action_id, result):
                raise RuntimeError(
                    "update_backtest_result returned False "
                    "(action missing from index?)"
                )
        if (
            result.exit_reason in TERMINAL_EXIT_REASONS
            and result.return_pct is not None
        ):
            apply_flip(action.trade_action_id, result.return_pct)
        else:
            report.refreshed_still_open += 1

    # File truth, deterministic order. isoformat keys sidestep naive/aware
    # datetime comparison errors present in real mixed-timezone F5 data.
    actions = sorted(
        repo.load_all_actions(),
        key=lambda a: (a.timestamp.isoformat(), a.trade_action_id),
    )

    pending_processed = 0
    for action in actions:
        if limit is not None and pending_processed >= limit:
            break
        report.scanned += 1

        status = action.validation_status
        if status in (ValidationStatus.VERIFIED, ValidationStatus.FAILED):
            report.skipped_terminal += 1
            continue
        if status == ValidationStatus.UNDER_REVIEW:
            report.skipped_under_review += 1
            continue

        pending_processed += 1
        try:
            settle_one(action)
        except Exception as e:  # per-action isolation: record, keep going
            logger.warning(
                "settle failed for %s", action.trade_action_id, exc_info=True
            )
            report.errors.append(
                {
                    "trade_action_id": action.trade_action_id,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    return report
