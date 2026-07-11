"""Tests for the F8 settle service (validation_status lifecycle owner)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from finer.backtest.settle import SettleReport, settle_actions
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    BacktestResult,
    ExitReason,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
    ValidationStatus,
)
from finer.services.repository import TradeActionRepository

ENTRY = datetime(2026, 3, 2, 9, 30)
D0 = date(2026, 3, 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_action(
    action_id: str,
    *,
    direction: TradeDirection = TradeDirection.BULLISH,
    ts: datetime = ENTRY,
    ticker: str = "TEST",
    validation_status: ValidationStatus = ValidationStatus.PENDING,
    backtest_result: Optional[BacktestResult] = None,
) -> TradeAction:
    return TradeAction(
        trade_action_id=action_id,
        timestamp=ts,
        source=SourceInfo(content_id="c-1", evidence_text="test", creator_id="k1"),
        target=TargetInfo(ticker=ticker, market="CN"),
        direction=direction,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                trigger_type=TriggerType.MANUAL,
                trigger_condition="test",
            )
        ],
        validation_status=validation_status,
        backtest_result=backtest_result,
    )


def make_result(
    exit_reason: ExitReason,
    return_pct: Optional[float],
    holding_days: int = 5,
) -> BacktestResult:
    return BacktestResult(
        return_pct=return_pct,
        holding_days=holding_days,
        exit_reason=exit_reason,
        exit_price=100.0,
        backtest_timestamp=datetime(2026, 3, 10, 12, 0),
        backtest_period="2026-03-02 — 2026-03-07",
    )


def series(start: date, closes: List[float]) -> List[Tuple[date, float]]:
    return [(start + timedelta(days=i), c) for i, c in enumerate(closes)]


def fake_fetcher(prices_by_ticker: Dict[str, List[Tuple[date, float]]]):
    def fetch(ticker: str) -> List[Tuple[date, float]]:
        return prices_by_ticker.get(ticker, [])

    return fetch


def snapshot_files(action_dir: Path) -> Dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(action_dir.rglob("*.json"))}


@pytest.fixture
def repo(tmp_path: Path) -> TradeActionRepository:
    return TradeActionRepository(
        db_path=tmp_path / "db" / "trade_actions.db",
        action_dir=tmp_path / "F5_executed",
    )


def reload(repo: TradeActionRepository, action_id: str) -> TradeAction:
    """Reload from file truth (bypasses any in-memory object)."""
    for action in repo.load_all_actions():
        if action.trade_action_id == action_id:
            return action
    raise AssertionError(f"action {action_id} not found in files")


# ---------------------------------------------------------------------------
# 1-2. Terminal results flip PENDING -> VERIFIED / FAILED
# ---------------------------------------------------------------------------

def test_terminal_profit_flips_to_verified(repo):
    repo.save(make_action(
        "ta-win",
        backtest_result=make_result(ExitReason.TARGET_REACHED, 0.207),
    ))

    report = settle_actions(repo=repo, fetch_closes=fake_fetcher({}), dry_run=False)

    assert report.verified == 1 and report.failed == 0
    assert reload(repo, "ta-win").validation_status == ValidationStatus.VERIFIED


def test_terminal_loss_and_zero_flip_to_failed(repo):
    repo.save(make_action(
        "ta-loss",
        backtest_result=make_result(ExitReason.STOP_LOSS, -0.113),
    ))
    repo.save(make_action(
        "ta-zero",
        ts=ENTRY + timedelta(hours=1),
        backtest_result=make_result(ExitReason.TIME_EXIT, 0.0),
    ))

    report = settle_actions(repo=repo, fetch_closes=fake_fetcher({}), dry_run=False)

    assert report.failed == 2 and report.verified == 0
    assert reload(repo, "ta-loss").validation_status == ValidationStatus.FAILED
    assert reload(repo, "ta-zero").validation_status == ValidationStatus.FAILED


# ---------------------------------------------------------------------------
# 3-4. END_OF_PERIOD results are re-evaluated with fresh prices
# ---------------------------------------------------------------------------

def test_end_of_period_reevaluates_and_flips_when_target_hit(repo):
    repo.save(make_action(
        "ta-eop-win",
        backtest_result=make_result(ExitReason.END_OF_PERIOD, 0.05),
    ))
    fetch = fake_fetcher({"TEST": series(D0, [100, 105, 112, 121, 130])})

    report = settle_actions(repo=repo, fetch_closes=fetch, dry_run=False)

    assert report.reevaluated == 1 and report.verified == 1
    action = reload(repo, "ta-eop-win")
    assert action.validation_status == ValidationStatus.VERIFIED
    assert action.backtest_result.exit_reason == ExitReason.TARGET_REACHED
    assert action.backtest_result.return_pct > 0.05  # refreshed, not the old stub


def test_end_of_period_still_open_refreshes_and_stays_pending(repo):
    repo.save(make_action(
        "ta-eop-open",
        backtest_result=make_result(ExitReason.END_OF_PERIOD, 0.01),
    ))
    fetch = fake_fetcher({"TEST": series(D0, [100, 103, 105])})  # no threshold hit

    report = settle_actions(repo=repo, fetch_closes=fetch, dry_run=False)

    assert report.reevaluated == 1
    assert report.refreshed_still_open == 1
    assert report.verified == 0 and report.failed == 0
    action = reload(repo, "ta-eop-open")
    assert action.validation_status == ValidationStatus.PENDING
    assert action.backtest_result.exit_reason == ExitReason.END_OF_PERIOD
    assert action.backtest_result.return_pct == round(0.05 - 0.003, 4)  # refreshed


# ---------------------------------------------------------------------------
# 5-6. Missing backtest_result: evaluator skips keep PENDING, write nothing
# ---------------------------------------------------------------------------

def test_non_directional_skipped_and_never_written(repo):
    repo.save(make_action("ta-neutral", direction=TradeDirection.NEUTRAL))
    before = snapshot_files(repo.action_dir)
    fetch = fake_fetcher({"TEST": series(D0, [100, 105])})

    report = settle_actions(repo=repo, fetch_closes=fetch, dry_run=False)

    assert report.skipped_non_directional == 1
    assert report.reevaluated == 0
    assert snapshot_files(repo.action_dir) == before
    assert reload(repo, "ta-neutral").validation_status == ValidationStatus.PENDING


def test_no_price_data_skipped_stays_pending(repo):
    repo.save(make_action("ta-nodata"))
    fetch = fake_fetcher({})  # empty series for every ticker

    report = settle_actions(repo=repo, fetch_closes=fetch, dry_run=False)

    assert report.skipped_no_data == 1
    assert report.errors == []
    action = reload(repo, "ta-nodata")
    assert action.validation_status == ValidationStatus.PENDING
    assert action.backtest_result is None


# ---------------------------------------------------------------------------
# 7-8. UNDER_REVIEW and already-terminal statuses are untouchable
# ---------------------------------------------------------------------------

def test_under_review_untouched(repo):
    repo.save(make_action(
        "ta-review",
        validation_status=ValidationStatus.UNDER_REVIEW,
        backtest_result=make_result(ExitReason.TARGET_REACHED, 0.30),
    ))
    before = snapshot_files(repo.action_dir)

    report = settle_actions(repo=repo, fetch_closes=fake_fetcher({}), dry_run=False)

    assert report.skipped_under_review == 1
    assert report.verified == 0 and report.failed == 0
    assert snapshot_files(repo.action_dir) == before


def test_verified_never_flips_back(repo):
    repo.save(make_action(
        "ta-done",
        validation_status=ValidationStatus.VERIFIED,
        backtest_result=make_result(ExitReason.STOP_LOSS, -0.15),  # losing result
    ))
    before = snapshot_files(repo.action_dir)

    report = settle_actions(repo=repo, fetch_closes=fake_fetcher({}), dry_run=False)

    assert report.skipped_terminal == 1
    assert report.failed == 0
    assert snapshot_files(repo.action_dir) == before
    assert reload(repo, "ta-done").validation_status == ValidationStatus.VERIFIED


# ---------------------------------------------------------------------------
# 9. dry_run reports every transition but writes nothing
# ---------------------------------------------------------------------------

def test_dry_run_counts_transitions_without_writing(repo):
    repo.save(make_action(
        "ta-dry-win",
        backtest_result=make_result(ExitReason.TARGET_REACHED, 0.21),
    ))
    repo.save(make_action(
        "ta-dry-eop",
        ts=ENTRY + timedelta(hours=1),
        backtest_result=make_result(ExitReason.END_OF_PERIOD, 0.02),
    ))
    before = snapshot_files(repo.action_dir)
    mtimes_before = {p: p.stat().st_mtime_ns for p in before}
    fetch = fake_fetcher({"TEST": series(D0, [100, 105, 112, 121, 130])})

    report = settle_actions(repo=repo, fetch_closes=fetch)  # dry_run defaults True

    assert report.dry_run is True
    assert report.verified == 2  # terminal flip + reevaluated-to-terminal flip
    assert report.reevaluated == 1
    assert snapshot_files(repo.action_dir) == before
    assert {p: p.stat().st_mtime_ns for p in before} == mtimes_before
    assert reload(repo, "ta-dry-win").validation_status == ValidationStatus.PENDING
    assert reload(repo, "ta-dry-eop").validation_status == ValidationStatus.PENDING


# ---------------------------------------------------------------------------
# 10. limit caps how many PENDING actions are processed
# ---------------------------------------------------------------------------

def test_limit_caps_pending_processing(repo):
    for i in range(3):
        repo.save(make_action(
            f"ta-lim-{i}",
            ts=ENTRY + timedelta(hours=i),
            backtest_result=make_result(ExitReason.TARGET_REACHED, 0.10),
        ))

    report = settle_actions(
        repo=repo, fetch_closes=fake_fetcher({}), dry_run=False, limit=1
    )

    assert report.verified == 1
    statuses = [reload(repo, f"ta-lim-{i}").validation_status for i in range(3)]
    assert statuses.count(ValidationStatus.VERIFIED) == 1
    assert statuses.count(ValidationStatus.PENDING) == 2


# ---------------------------------------------------------------------------
# 11. Manual-semantics exits are never overwritten by automation
# ---------------------------------------------------------------------------

def test_signal_reversal_and_manual_exits_skipped(repo):
    repo.save(make_action(
        "ta-reversal",
        backtest_result=make_result(ExitReason.SIGNAL_REVERSAL, 0.08),
    ))
    repo.save(make_action(
        "ta-manual",
        ts=ENTRY + timedelta(hours=1),
        backtest_result=make_result(ExitReason.MANUAL, -0.04),
    ))
    before = snapshot_files(repo.action_dir)

    report = settle_actions(repo=repo, fetch_closes=fake_fetcher({}), dry_run=False)

    assert report.skipped_manual_semantics == 2
    assert report.verified == 0 and report.failed == 0
    assert snapshot_files(repo.action_dir) == before


# ---------------------------------------------------------------------------
# Report shape / error isolation
# ---------------------------------------------------------------------------

def test_report_to_dict_roundtrip():
    report = SettleReport(scanned=3, verified=1, dry_run=False)
    d = report.to_dict()
    assert d["scanned"] == 3 and d["verified"] == 1
    assert d["dry_run"] is False
    assert d["errors"] == []


def test_fetch_error_is_isolated_per_action(repo):
    repo.save(make_action("ta-boom"))  # needs re-evaluation -> triggers fetch
    repo.save(make_action(
        "ta-fine",
        ts=ENTRY + timedelta(hours=1),
        backtest_result=make_result(ExitReason.TARGET_REACHED, 0.12),
    ))

    def exploding_fetch(ticker: str):
        raise ConnectionError("network down")

    report = settle_actions(repo=repo, fetch_closes=exploding_fetch, dry_run=False)

    assert len(report.errors) == 1
    assert report.errors[0]["trade_action_id"] == "ta-boom"
    assert "network down" in report.errors[0]["error"]
    # The healthy sibling still settled.
    assert report.verified == 1
    assert reload(repo, "ta-fine").validation_status == ValidationStatus.VERIFIED
    assert reload(repo, "ta-boom").validation_status == ValidationStatus.PENDING
