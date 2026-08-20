"""R6 signal isolation on the opinions routes.

data/F5_executed mixes KOL statements with broker declarative recommendations
(bri_*_actions.json, signal_class == "broker_recommendation") and carries
dedup markers (metadata.superseded_by). Rule R6: broker recommendations must
NOT feed KOL credibility scoring, the settled record, or the leaderboard;
superseded duplicates must not double-count in any aggregation. Both stay
visible in timeline/detail, brokers badged via signalClass passthrough.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, get_args

import pytest
from fastapi.testclient import TestClient

from finer.api.routes import opinions
from finer.api.server import create_app
from finer.schemas.trade_action import (
    SIGNAL_CLASS_LITERAL,
    ActionStep,
    ActionType,
    BacktestResult,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
)
from finer.services.repository import TradeActionRepository

client = TestClient(create_app(), raise_server_exceptions=False)


def make_action(
    action_id: str,
    kol: str,
    ticker: str,
    ts: datetime,
    direction: TradeDirection = TradeDirection.BULLISH,
    signal_class: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    return_pct: Optional[float] = None,
    holding_days: int = 10,
) -> TradeAction:
    """Fixture action in the shape of real F5 output (see test_stance_episodes)."""
    return TradeAction(
        trade_action_id=action_id,
        timestamp=ts,
        source=SourceInfo(content_id=f"c-{action_id}", evidence_text="e", creator_id=kol),
        target=TargetInfo(ticker=ticker, market="CN", company_name=ticker),
        direction=direction,
        action_chain=[
            ActionStep(sequence=1, action_type=ActionType.LONG, trigger_type=TriggerType.MANUAL)
        ],
        signal_class=signal_class,
        metadata=metadata or {},
        backtest_result=(
            BacktestResult(return_pct=return_pct, holding_days=holding_days)
            if return_pct is not None
            else None
        ),
    )


NOW = datetime.now()


def _mixed_fixture_actions() -> Dict[str, TradeAction]:
    """2 KOL actions (one settled win), 1 settled broker, 1 superseded KOL."""
    return {
        "kol_win": make_action(
            "ta-kol-win", "kol_alpha", "AAPL", NOW - timedelta(days=3),
            signal_class="kol_statement", return_pct=0.10,
        ),
        "kol_open": make_action(
            "ta-kol-open", "kol_alpha", "0700.HK", NOW - timedelta(days=2),
            direction=TradeDirection.BEARISH,  # legacy: signal_class None = kol
        ),
        "broker": make_action(
            "ta-broker", "gs_research", "AAPL", NOW - timedelta(days=1),
            signal_class="broker_recommendation", return_pct=0.20,
        ),
        "superseded": make_action(
            "ta-superseded", "kol_beta", "TSLA", NOW - timedelta(days=1),
            return_pct=0.30, metadata={"superseded_by": "ta-somewhere-else"},
        ),
    }


@pytest.fixture
def mixed_action_dir(tmp_path: Path, monkeypatch) -> Dict[str, TradeAction]:
    """Point the opinions route at a tmp F5 dir with the mixed population.

    KOL/superseded actions use the single ``*.action.json`` layout; the broker
    action lands in a ``bri_*_actions.json`` batch wrapper — the two real
    persisted layouts that _load_actions_from_dir globs.
    """
    data_root = tmp_path / "data"
    f5_dir = data_root / "F5_executed"
    f5_dir.mkdir(parents=True)

    actions = _mixed_fixture_actions()
    for key in ("kol_win", "kol_open", "superseded"):
        a = actions[key]
        (f5_dir / f"{a.trade_action_id}.action.json").write_text(
            json.dumps(a.to_dict()), encoding="utf-8"
        )
    (f5_dir / "bri_gs_research_actions.json").write_text(
        json.dumps({"actions": [actions["broker"].to_dict()]}), encoding="utf-8"
    )

    repo = TradeActionRepository(
        db_path=data_root / "cache" / "trade_actions.db",
        action_dir=f5_dir,
    )
    monkeypatch.setattr(opinions, "_repository", repo)
    # F6_reviewed scan resolves under the patched root (empty in this fixture)
    monkeypatch.setattr(opinions, "DATA_ROOT", data_root)
    return actions


# ---------------------------------------------------------------------------
# Classification unit behaviour (top-level field, metadata fallback, dedup)
# ---------------------------------------------------------------------------

class TestClassification:
    def test_top_level_broker_signal_class(self):
        a = make_action("a1", "k", "AAPL", NOW, signal_class="broker_recommendation")
        assert opinions._is_broker_signal(a) is True
        assert opinions._is_credibility_scoreable(a) is False

    def test_metadata_fallback_broker_signal_class(self):
        a = make_action(
            "a2", "k", "AAPL", NOW,
            metadata={"signal_class": "broker_recommendation"},
        )
        assert opinions._is_broker_signal(a) is True

    def test_none_signal_class_means_kol(self):
        a = make_action("a3", "k", "AAPL", NOW)  # legacy action
        assert opinions._is_broker_signal(a) is False
        assert opinions._is_credibility_scoreable(a) is True

    def test_kol_statement_is_not_broker(self):
        a = make_action("a4", "k", "AAPL", NOW, signal_class="kol_statement")
        assert opinions._is_broker_signal(a) is False

    def test_sector_view_is_broker_too(self):
        """板块观点也是券商信号——不是 KOL。

        回归：此前 ``_is_broker_signal`` 用 ``== "broker_recommendation"``
        单值比较，现役 400 条 ``broker_sector_view`` 因此全部落进「未知 = KOL」
        的默认分支，进了 KOL 记分卡与榜单。整个测试类当时是绿的，因为没有一条
        用例喂过第二个 broker 取值。
        """
        a = make_action("a8", "k", "AAPL", NOW, signal_class="broker_sector_view")
        assert opinions._is_broker_signal(a) is True
        assert opinions._is_credibility_scoreable(a) is False

    def test_sector_view_via_metadata_fallback(self):
        a = make_action(
            "a9", "k", "AAPL", NOW,
            metadata={"signal_class": "broker_sector_view"},
        )
        assert opinions._is_broker_signal(a) is True
        assert opinions._is_credibility_scoreable(a) is False

    def test_every_contract_value_is_classified(self):
        """钉内容而非钉行为：契约里的每个取值都必须被显式归类。

        逐个喂 ``SIGNAL_CLASS_LITERAL`` 的取值，而不是喂几个手挑的常量——
        新增第四个取值时这条会失败，不会像上一次那样静默漏进 KOL 侧。
        """
        contract_values = set(get_args(SIGNAL_CLASS_LITERAL))
        assert contract_values, "SIGNAL_CLASS_LITERAL 必须是非空 Literal"
        for value in contract_values:
            a = make_action(f"a-{value}", "k", "AAPL", NOW, signal_class=value)
            is_broker = opinions._is_broker_signal(a)
            assert is_broker is (value in opinions._BROKER_SIGNAL_CLASSES), (
                f"{value} 未被显式归类；不得依赖「未知 = KOL」的默认分支"
            )
        # 归类表本身必须完整覆盖契约，不多不少。
        assert (
            opinions._BROKER_SIGNAL_CLASSES | opinions._KOL_SIGNAL_CLASSES
        ) == contract_values

    def test_passthrough_preserves_sector_view(self):
        """对外透传不得把板块观点抹成 None（None 在前端读作 KOL）。"""
        a = make_action("a10", "k", "AAPL", NOW, signal_class="broker_sector_view")
        assert opinions.trade_action_to_opinion(a).signalClass == "broker_sector_view"

    def test_passthrough_drops_junk_signal_class(self):
        a = make_action("a11", "k", "AAPL", NOW, metadata={"signal_class": "garbage"})
        assert opinions.trade_action_to_opinion(a).signalClass is None

    def test_superseded_marker_blocks_scoring(self):
        a = make_action("a5", "k", "AAPL", NOW, metadata={"superseded_by": "a6"})
        assert opinions._is_superseded(a) is True
        assert opinions._is_credibility_scoreable(a) is False

    def test_falsy_superseded_marker_is_ignored(self):
        a = make_action("a7", "k", "AAPL", NOW, metadata={"superseded_by": ""})
        assert opinions._is_superseded(a) is False


# ---------------------------------------------------------------------------
# Credibility / settled record / leaderboard exclusion (R6)
# ---------------------------------------------------------------------------

class TestCredibilityIsolation:
    def test_settled_record_counts_only_scoreable_kol_actions(self, mixed_action_dir):
        all_actions = opinions._load_all_actions()
        assert len(all_actions) == 4  # everything is loaded; scoring filters

        record = opinions._kol_settled_record(all_actions)
        # Only kol_alpha remains: 1 settled call, 1 win. The broker's settled
        # win and the superseded win must not create records — not even
        # zero-record leaderboard entries.
        assert record == {"kol_alpha": (1, 1)}

    def test_credibility_map_has_no_broker_or_superseded_entries(self, mixed_action_dir):
        cred = opinions._kol_credibility_map(opinions._load_all_actions())
        assert set(cred) == {"kol_alpha"}
        assert cred["kol_alpha"] == opinions._credibility_score(1, 1)

    def test_attributed_actions_exclude_broker_and_superseded(self, mixed_action_dir):
        ids = {a.trade_action_id for a in opinions._attributed_actions()}
        assert ids == {"ta-kol-win", "ta-kol-open"}

    def test_settled_record_universe_is_filtered_too(self, mixed_action_dir):
        # A broker/superseded action in the universe must not anchor episodes.
        all_actions = opinions._load_all_actions()
        scoreable = [a for a in all_actions if opinions._is_credibility_scoreable(a)]
        record = opinions._kol_settled_record(scoreable, universe=all_actions)
        assert record == {"kol_alpha": (1, 1)}


class TestLeaderboard:
    def test_top_kols_only_counts_non_superseded_kol_actions(self, mixed_action_dir):
        res = client.get("/api/opinions/stats/summary?timeRange=1M")
        assert res.status_code == 200
        data = res.json()["data"]

        authors = {k["author"] for k in data["topKols"]}
        assert authors == {"kol_alpha"}, (
            "leaderboard must list only real KOLs — no broker "
            "(gs_research) and no superseded-only creator (kol_beta)"
        )

        (entry,) = data["topKols"]
        assert entry["count"] == 2  # both non-superseded KOL actions
        assert entry["settledCount"] == 1
        assert entry["wins"] == 1

        # CRD-2 效力门（2026-08-17）：settled=1 远低于 canonical 门槛，
        # 比率不得离开后端——此前这里发 hitRate=1.0 与信誉分 95，
        # 一条 1/1 的记录就能占榜首。
        assert entry["hitRate"] is None, "样本不足时不得发出比率"
        assert entry["sufficiency"]["display_policy"] == "count_only"
        assert entry["sufficiency"]["settled_n"] == 1

        # 0-99 信誉分与私有 lowSample 已下线，不得再出现在响应里
        assert "credibility" not in entry
        assert "lowSample" not in entry
        assert "avgRating" not in entry

    def test_superseded_action_absent_from_stats(self, mixed_action_dir):
        res = client.get("/api/opinions/stats/summary?timeRange=1M")
        data = res.json()["data"]
        # 2 KOL + 1 broker; the superseded duplicate is out of every bucket.
        assert data["total"] == 3
        assert data["byDirection"]["bullish"] == 2  # kol win + broker
        assert data["byDirection"]["bearish"] == 1  # kol open
        # TSLA (the superseded action's ticker) appears in no top-ticker slot
        assert all(t["ticker"] != "TSLA" for t in data["topTickers"])


# ---------------------------------------------------------------------------
# Timeline / detail keep everything, with signalClass passthrough
# ---------------------------------------------------------------------------

class TestTimelinePassthrough:
    def test_timeline_keeps_broker_and_superseded_with_signal_class(self, mixed_action_dir):
        res = client.get("/api/opinions/timeline?timeRange=1M&limit=50")
        assert res.status_code == 200
        body = res.json()
        by_id = {o["id"]: o for o in body["opinions"]}

        # nothing is hidden from the timeline
        assert set(by_id) == {
            "ta-kol-win", "ta-kol-open", "ta-broker", "ta-superseded",
        }
        assert body["total"] == 4

        # passthrough lets the frontend badge broker recommendations
        assert by_id["ta-broker"]["signalClass"] == "broker_recommendation"
        assert by_id["ta-kol-win"]["signalClass"] == "kol_statement"
        assert by_id["ta-kol-open"]["signalClass"] is None  # legacy = unclassified
        assert by_id["ta-superseded"]["signalClass"] is None

    def test_detail_view_passes_signal_class_through(self, mixed_action_dir):
        res = client.get("/api/opinions/ta-broker")
        assert res.status_code == 200
        assert res.json()["signalClass"] == "broker_recommendation"
