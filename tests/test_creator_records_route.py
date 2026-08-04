"""GET /api/creator/records 与 /{id}/record —— CRD-1 的只读消费入口。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_scorecard import _action as _make_action

_SEQ = iter(range(10_000))


@pytest.fixture
def client(monkeypatch):
    import finer.api.routes.creator_records as mod

    actions = (
        [_make_action(f"r{next(_SEQ)}", creator="瑞银") for _ in range(35)]
        + [_make_action(f"r{next(_SEQ)}", creator="小社", return_pct=None)
           for _ in range(3)]
    )

    class _FakeRepo:
        def load_all_actions(self):
            return actions

    monkeypatch.setattr(
        "finer.services.repository.TradeActionRepository",
        lambda **kw: _FakeRepo(),
    )
    mod._cards_cache = {}          # 隔离 TTL 缓存
    from finer.api.server import app
    return TestClient(app, raise_server_exceptions=False)


def test_records_list_sorted_by_settled_n_with_gate(client):
    r = client.get("/api/creator/records")
    assert r.status_code == 200
    cards = r.json()["data"]["cards"]
    assert [c["creator_id"] for c in cards] == ["瑞银", "小社"]
    assert cards[0]["sufficiency"]["tier"] == "sufficient"
    # 小社 3 条全未结算 → n_settled=0，只显计数
    assert cards[1]["n_settled"] == 0
    assert cards[1]["sufficiency"]["display_policy"] == "count_only"
    # 预测性主张裁决必须在卡里（broker 口径已登记为不许可）
    assert cards[0]["sufficiency"]["predictive_claim"]["permitted"] is False


def test_single_record_and_canonical_not_found(client):
    ok = client.get("/api/creator/瑞银/record")
    assert ok.status_code == 200
    assert ok.json()["data"]["creator_id"] == "瑞银"

    miss = client.get("/api/creator/不存在的信源/record")
    assert miss.status_code == 404
    details = miss.json()["error"]["details"]
    assert details["retryable"] is False and "fix_hint" in details
