"""API tests for GET /api/kol/registry (routes/kol_registry.py)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from finer.api.server import create_app

client = TestClient(create_app(), raise_server_exceptions=False)


def test_registry_list_contains_real_creators():
    res = client.get("/api/kol/registry")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["data"]["total"] >= 3
    ids = {c["creator_id"] for c in body["data"]["creators"]}
    assert {"trader_ji", "maodaren", "9you"} <= ids


def test_registry_single_profile_with_trading_style():
    res = client.get("/api/kol/registry/trader_ji")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["display_name"] == "trader韭"
    assert data["style_label"] == "板块与主题轮动"
    assert data["trading_style"]["entry_style"] == "right_side"


def test_registry_resolves_alias_to_profile():
    # 中文别名与历史 canonical id 都归并到 maodaren
    for key in ("猫大人", "kol_cat_lord_fire"):
        res = client.get(f"/api/kol/registry/{key}")
        assert res.status_code == 200, key
        assert res.json()["data"]["creator_id"] == "maodaren"


def test_registry_miss_returns_canonical_404_envelope():
    res = client.get("/api/kol/registry/no_such_creator")
    assert res.status_code == 404
    body = res.json()
    assert body["ok"] is False
    err = body["error"]
    assert err["code"]
    details = err["details"]
    assert details["retryable"] is False
    assert "fix_hint" in details
    assert "request_id" in details
