"""GET /api/ticker/{symbol}/consensus —— CRD-3 的只读消费入口。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import finer.api.routes.ticker as mod

    (tmp_path / "F3_intents").mkdir(parents=True)
    (tmp_path / "F3_intents" / "bri_t1.json").write_text(json.dumps({
        "intent_id": "bri_t1", "creator_id": "高盛", "target_symbol": "NVDA",
        "target_name": "Nvidia", "direction": "bullish",
        "target_price": {"value": 300.0, "currency": "USD"},
        "metadata": {"rating_current": "Buy", "report_date": "2026-05-20"},
    }), encoding="utf-8")
    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    mod._cache = None          # 隔离 TTL 缓存，防跨测试污染
    from finer.api.server import app
    return TestClient(app, raise_server_exceptions=False)


def test_consensus_ok(client):
    r = client.get("/api/ticker/NVDA/consensus")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ticker"] == "NVDA" and data["n_sources"] == 1
    assert data["latest_by_source"][0]["intent_id"] == "bri_t1"
    assert any("不构成对未来的预测" in n for n in data["notes"])


def test_unknown_symbol_is_canonical_error(client):
    r = client.get("/api/ticker/NO.SUCH.ZZZ/consensus")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["details"]["retryable"] is False
    assert "fix_hint" in err["details"] and "request_id" in err["details"]
