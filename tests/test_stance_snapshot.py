"""Tests for the F7 stance snapshot + diff service (真快照-diff)."""
from __future__ import annotations

from datetime import date, datetime

from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)
from finer.timeline.stance_snapshot import (
    build_snapshot,
    diff_snapshots,
    load_latest_snapshot_before,
    persist_snapshot,
)


def make_action(
    kol: str,
    ticker: str,
    direction: TradeDirection,
    ts: datetime,
    action_id: str,
) -> TradeAction:
    return TradeAction(
        trade_action_id=action_id,
        timestamp=ts,
        source=SourceInfo(content_id="c-1", evidence_text="e", creator_id=kol),
        target=TargetInfo(ticker=ticker, market="CN", company_name=ticker),
        direction=direction,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                trigger_type=TriggerType.MANUAL,
            )
        ],
    )


T1 = datetime(2026, 3, 2, 9, 30)
T2 = datetime(2026, 3, 10, 9, 30)


class TestBuildSnapshot:
    def test_latest_stance_wins(self):
        actions = [
            make_action("k1", "600519.SH", TradeDirection.BULLISH, T1, "a1"),
            make_action("k1", "600519.SH", TradeDirection.BEARISH, T2, "a2"),
        ]
        snap = build_snapshot(actions, {"k1": 70}, snapshot_date=date(2026, 7, 3))
        stance = snap["kols"]["k1"]["stances"]["600519.SH"]
        assert stance["direction"] == "bearish"
        assert stance["trade_action_id"] == "a2"
        assert snap["kols"]["k1"]["credibility"] == 70

    def test_unattributed_excluded(self):
        actions = [make_action("unknown", "X", TradeDirection.BULLISH, T1, "a1")]
        snap = build_snapshot(actions)
        assert snap["kols"] == {}


class TestDiff:
    def base(self, direction: str = "bullish", cred: int = 70) -> dict:
        return {
            "snapshot_date": "2026-07-02",
            "kols": {
                "k1": {
                    "credibility": cred,
                    "stances": {
                        "600519.SH": {
                            "direction": direction,
                            "clock": "2026-07-02T09:30:00",
                            "trade_action_id": "a1",
                            "company_name": "贵州茅台",
                        }
                    },
                }
            },
        }

    def curr(self, direction: str = "bullish", cred: int = 70, extra=None) -> dict:
        snap = self.base(direction, cred)
        snap["snapshot_date"] = "2026-07-03"
        if extra:
            snap["kols"]["k1"]["stances"].update(extra)
        return snap

    def test_flip_detected(self):
        events = diff_snapshots(self.base("bullish"), self.curr("bearish"))
        flips = [e for e in events if e["type"] == "flip"]
        assert len(flips) == 1
        assert flips[0]["fromDirection"] == "bullish"
        assert flips[0]["toDirection"] == "bearish"

    def test_new_call_detected(self):
        extra = {
            "300750.SZ": {
                "direction": "bullish",
                "clock": "2026-07-03T09:30:00",
                "trade_action_id": "a9",
                "company_name": "宁德时代",
            }
        }
        events = diff_snapshots(self.base(), self.curr(extra=extra))
        news = [e for e in events if e["type"] == "new_call"]
        assert len(news) == 1
        assert news[0]["ticker"] == "300750.SZ"

    def test_score_change_detected(self):
        events = diff_snapshots(self.base(cred=70), self.curr(cred=73))
        scores = [e for e in events if e["type"] == "score_change"]
        assert len(scores) == 1
        assert scores[0]["value"] == 3

    def test_no_change_no_events(self):
        assert diff_snapshots(self.base(), self.curr()) == []

    def test_brand_new_kol_not_spammed_as_new_calls(self):
        """A KOL absent from the previous snapshot doesn't flood new_call."""
        prev = {"snapshot_date": "2026-07-02", "kols": {}}
        events = diff_snapshots(prev, self.curr())
        assert events == []


def make_sector_action(
    kol: str,
    proxy_ticker: str,
    sector_symbol: str,
    direction: TradeDirection,
    ts: datetime,
    action_id: str,
) -> TradeAction:
    """A sector-proxy action: the display ticker is the proxy ETF, but F2
    provenance records which sector it stands in for."""
    action = make_action(kol, proxy_ticker, direction, ts, action_id)
    action.metadata = {
        "sector_proxy": {
            "sector_symbol": sector_symbol,
            "sector_name": sector_symbol.title(),
            "proxy_symbol": proxy_ticker,
            "proxy_name": proxy_ticker,
            "rule": "sector_proxy_v1",
            "config_version": 1,
        }
    }
    return action


class TestSectorProxyStanceKey:
    """F7 fix: two sectors proxying to the SAME ETF must not collapse into one
    stance slot (sector spec Open Issue #2)."""

    def test_two_sectors_same_proxy_stay_distinct(self):
        # COMPUTE_POWER and AI_COMPUTING both proxy to 159819 with opposite calls.
        actions = [
            make_sector_action(
                "k1", "159819", "COMPUTE_POWER", TradeDirection.BULLISH, T1, "a1"
            ),
            make_sector_action(
                "k1", "159819", "AI_COMPUTING", TradeDirection.BEARISH, T2, "a2"
            ),
        ]
        snap = build_snapshot(actions, snapshot_date=date(2026, 7, 3))
        stances = snap["kols"]["k1"]["stances"]
        # keyed by sector, NOT collapsed under the shared proxy ticker
        assert set(stances) == {"sector:COMPUTE_POWER", "sector:AI_COMPUTING"}
        assert stances["sector:COMPUTE_POWER"]["direction"] == "bullish"
        assert stances["sector:AI_COMPUTING"]["direction"] == "bearish"
        # display ticker is still the proxy ETF the reader recognizes
        assert stances["sector:COMPUTE_POWER"]["ticker"] == "159819"
        assert stances["sector:AI_COMPUTING"]["ticker"] == "159819"

    def test_direct_ticker_still_keys_by_ticker(self):
        actions = [
            make_action("k1", "600519.SH", TradeDirection.BULLISH, T1, "a1"),
        ]
        snap = build_snapshot(actions, snapshot_date=date(2026, 7, 3))
        stances = snap["kols"]["k1"]["stances"]
        assert set(stances) == {"600519.SH"}
        assert stances["600519.SH"]["ticker"] == "600519.SH"

    def test_diff_does_not_fabricate_flip_across_shared_proxy(self):
        prev = build_snapshot(
            [
                make_sector_action(
                    "k1", "159819", "COMPUTE_POWER", TradeDirection.BULLISH, T1, "a1"
                )
            ],
            snapshot_date=date(2026, 7, 2),
        )
        curr = build_snapshot(
            [
                make_sector_action(
                    "k1", "159819", "COMPUTE_POWER", TradeDirection.BULLISH, T1, "a1"
                ),
                make_sector_action(
                    "k1", "159819", "AI_COMPUTING", TradeDirection.BEARISH, T2, "a2"
                ),
            ],
            snapshot_date=date(2026, 7, 3),
        )
        events = diff_snapshots(prev, curr)
        # the second sector is a NEW coverage slot, not a flip of the first
        assert [e["type"] for e in events] == ["new_call"]
        assert events[0]["ticker"] == "159819"


class TestPersistence:
    def test_roundtrip_and_latest_before(self, tmp_path):
        s1 = build_snapshot(
            [make_action("k1", "X", TradeDirection.BULLISH, T1, "a1")],
            snapshot_date=date(2026, 7, 1),
        )
        s2 = build_snapshot(
            [make_action("k1", "X", TradeDirection.BEARISH, T2, "a2")],
            snapshot_date=date(2026, 7, 2),
        )
        persist_snapshot(s1, snapshot_dir=tmp_path)
        persist_snapshot(s2, snapshot_dir=tmp_path)

        got = load_latest_snapshot_before(date(2026, 7, 3), snapshot_dir=tmp_path)
        assert got is not None
        d, snap = got
        assert d == date(2026, 7, 2)
        assert snap["kols"]["k1"]["stances"]["X"]["direction"] == "bearish"

        # strictly-before semantics: same-day snapshot is not "previous"
        got2 = load_latest_snapshot_before(date(2026, 7, 2), snapshot_dir=tmp_path)
        assert got2 is not None and got2[0] == date(2026, 7, 1)

        assert load_latest_snapshot_before(date(2026, 7, 1), snapshot_dir=tmp_path) is None


class TestOldFormatMigration:
    def test_diff_falls_back_to_ticker_key_for_pre_sector_snapshots(self):
        """Snapshots persisted before sector-aware keys hold sector stances
        under the raw proxy ticker; the first post-deploy diff must not
        fabricate a new_call (and must keep fromDirection on real flips)."""
        prev = {
            "snapshot_date": "2026-07-10",
            "kols": {
                "k1": {
                    "credibility": 70,
                    "stances": {
                        # old format: keyed by proxy ticker directly
                        "159819": {
                            "direction": "bullish",
                            "clock": "2026-07-10T09:30:00",
                            "trade_action_id": "a-old",
                            "company_name": "AI ETF",
                        }
                    },
                }
            },
        }
        curr = {
            "snapshot_date": "2026-07-11",
            "kols": {
                "k1": {
                    "credibility": 70,
                    "stances": {
                        # new format: sector-aware key, ticker rides in the value
                        "sector:AI_COMPUTING": {
                            "direction": "bearish",
                            "clock": "2026-07-11T09:30:00",
                            "trade_action_id": "a-new",
                            "ticker": "159819",
                            "company_name": "AI ETF",
                        }
                    },
                }
            },
        }
        events = diff_snapshots(prev, curr)
        # migration fallback: recognized as a FLIP of the old ticker-keyed
        # stance, not fabricated as brand-new coverage
        assert [e["type"] for e in events] == ["flip"]
        assert events[0]["fromDirection"] == "bullish"
        assert events[0]["toDirection"] == "bearish"
        assert events[0]["ticker"] == "159819"
