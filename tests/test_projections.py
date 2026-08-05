"""PROJ-1 物化器：写入原子性、读侧往返、缺库回退语义。"""

from __future__ import annotations

import json

import pytest

from finer.projections.materializer import (
    materialize_projections,
    projection_path,
    read_consensus,
    read_record_cards,
)
from tests.test_scorecard import _action as _make_action

_SEQ = iter(range(10_000))


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    (tmp_path / "F3_intents").mkdir()
    (tmp_path / "F5_executed").mkdir()
    (tmp_path / "cache").mkdir()
    for i, broker in enumerate(["高盛", "瑞银"]):
        (tmp_path / "F3_intents" / f"bri_p{i}.json").write_text(json.dumps({
            "intent_id": f"bri_p{i}", "creator_id": broker,
            "target_symbol": "NVDA", "target_name": "Nvidia",
            "direction": "bullish",
            "target_price": {"value": 200.0 + i, "currency": "USD"},
            "metadata": {"rating_current": "Buy", "report_date": f"2026-0{i+1}-10"},
        }), encoding="utf-8")

    actions = [_make_action(f"p{next(_SEQ)}", creator="高盛") for _ in range(35)]

    class _FakeRepo:
        def load_all_actions(self):
            return actions

    monkeypatch.setattr(
        "finer.services.repository.TradeActionRepository",
        lambda **kw: _FakeRepo(),
    )
    return tmp_path


def test_materialize_and_read_back(data_root):
    counts = materialize_projections(data_root)
    assert counts["ticker_consensus"] == 1
    assert counts["creator_record_cards"] == 1
    assert projection_path(data_root).exists()

    view = read_consensus(data_root, "NVDA")
    assert view is not None and view.n_sources == 2
    # 物化前后语义等价：每源最新一篇、下钻 id 保留
    assert {r.intent_id for r in view.latest_by_source} == {"bri_p0", "bri_p1"}

    cards = read_record_cards(data_root, "broker_recommendation")
    assert cards is not None and cards[0].creator_id == "高盛"
    assert cards[0].sufficiency.tier == "sufficient"


def test_missing_projection_returns_none_not_error(tmp_path):
    assert read_consensus(tmp_path, "NVDA") is None
    assert read_record_cards(tmp_path, "broker_recommendation") is None


def test_rematerialize_replaces_atomically(data_root):
    materialize_projections(data_root)
    first = projection_path(data_root).stat().st_mtime_ns
    materialize_projections(data_root)          # 全量重建覆盖，无残留 tmp
    assert projection_path(data_root).exists()
    assert projection_path(data_root).stat().st_mtime_ns >= first
    assert not projection_path(data_root).with_suffix(".sqlite3.tmp").exists()


def test_unknown_signal_class_returns_none(data_root):
    materialize_projections(data_root)
    assert read_record_cards(data_root, "kol_statement") is None


def test_stale_schema_version_falls_back_instead_of_serving_old_payload(data_root):
    """投影 schema 版本落后时必须回退活算，不能静默供缺字段的旧 payload。

    2026-08-05 实测踩到：加了 latest_report_date 后忘记重跑物化，
    /ticker 的陈旧度横幅一直不出现——而 API 与前端都「正常」，
    因为缺失字段的 None 是合法值。宁可慢也不能供错。
    """
    import sqlite3

    materialize_projections(data_root)
    assert read_consensus(data_root, "NVDA") is not None

    conn = sqlite3.connect(projection_path(data_root))
    conn.execute("UPDATE projection_meta SET value='0' WHERE key='schema_version'")
    conn.commit()
    conn.close()

    assert read_consensus(data_root, "NVDA") is None
    assert read_record_cards(data_root, "broker_recommendation") is None
