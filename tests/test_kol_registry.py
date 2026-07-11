"""Tests for the KOL Profile Registry (services/kol_registry.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from finer.services.kol_registry import KOLRegistry, get_registry


def _write_yaml(root: Path, stem: str, config: dict) -> Path:
    creators = root / "configs" / "creators"
    creators.mkdir(parents=True, exist_ok=True)
    path = creators / f"{stem}.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def _registry(root: Path, ttl: float = 60.0) -> KOLRegistry:
    return KOLRegistry(root=root, ttl_seconds=ttl)


class TestRealRepoRoot:
    def test_loads_trader_ji_from_repo(self):
        reg = get_registry()
        profile = reg.get("trader_ji")
        assert profile is not None
        assert profile.display_name == "trader韭"
        assert profile.trading_style is not None
        assert profile.trading_style.entry_style == "right_side"


class TestLoading:
    def test_list_and_get(self, tmp_path):
        _write_yaml(tmp_path, "k1", {"creator_id": "k1", "display_name": "老K"})
        _write_yaml(tmp_path, "k2", {"creator_id": "k2"})
        reg = _registry(tmp_path)
        assert {p.creator_id for p in reg.list_profiles()} == {"k1", "k2"}
        assert reg.get("k1").display_name == "老K"
        assert reg.get("k2").display_name is None  # optional (test_trading_style k2 语义)
        assert reg.get("nobody") is None

    def test_enabled_filter(self, tmp_path):
        _write_yaml(tmp_path, "on", {"creator_id": "on"})
        _write_yaml(tmp_path, "off", {"creator_id": "off", "enabled": False})
        reg = _registry(tmp_path)
        assert {p.creator_id for p in reg.list_profiles()} == {"on"}
        assert {p.creator_id for p in reg.list_profiles(include_disabled=True)} == {"on", "off"}
        assert reg.get("off") is not None  # get 不受 enabled 影响

    def test_underscore_stems_skipped(self, tmp_path):
        _write_yaml(tmp_path, "_template", {"creator_id": "example_kol"})
        _write_yaml(tmp_path, "real", {"creator_id": "real"})
        reg = _registry(tmp_path)
        assert {p.creator_id for p in reg.list_profiles()} == {"real"}

    def test_broken_yaml_isolated(self, tmp_path):
        creators = tmp_path / "configs" / "creators"
        creators.mkdir(parents=True)
        (creators / "broken.yaml").write_text("{{ not yaml :::", encoding="utf-8")
        _write_yaml(tmp_path, "good", {"creator_id": "good"})
        reg = _registry(tmp_path)
        assert {p.creator_id for p in reg.list_profiles()} == {"good"}

    def test_stem_wins_over_yaml_creator_id(self, tmp_path):
        _write_yaml(tmp_path, "stem_name", {"creator_id": "different_id"})
        reg = _registry(tmp_path)
        assert reg.get("stem_name") is not None
        assert reg.get("different_id") is None

    def test_invalid_trading_style_block_isolated(self, tmp_path):
        """块无效 → declared None，但 display_name 等其余字段必须保住。"""
        _write_yaml(tmp_path, "k3", {
            "creator_id": "k3",
            "display_name": "老三",
            "trading_style": {"entry_style": "not_a_valid_style"},
        })
        reg = _registry(tmp_path)
        profile = reg.get("k3")
        assert profile is not None
        assert profile.display_name == "老三"
        assert profile.trading_style is None

    def test_missing_dir_gives_empty_registry(self, tmp_path):
        reg = _registry(tmp_path)
        assert reg.list_profiles() == []
        assert reg.get("anyone") is None


class TestResolve:
    @pytest.fixture()
    def reg(self, tmp_path):
        _write_yaml(tmp_path, "maodaren", {
            "creator_id": "maodaren",
            "display_name": "猫大人",
            "handle": "猫掌柜",
            "aliases": ["猫", "kol_cat_lord_fire"],
            "platform_identities": [
                {"platform": "feishu", "account_id": "oc_ABC123"}
            ],
        })
        return _registry(tmp_path)

    def test_resolve_alias(self, reg):
        assert reg.resolve("猫") == "maodaren"
        assert reg.resolve("kol_cat_lord_fire") == "maodaren"

    def test_resolve_display_name_and_handle(self, reg):
        assert reg.resolve("猫大人") == "maodaren"
        assert reg.resolve("猫掌柜") == "maodaren"

    def test_resolve_platform_identity_case_insensitive(self, reg):
        assert reg.resolve("feishu:oc_abc123") == "maodaren"
        assert reg.resolve("FEISHU:OC_ABC123") == "maodaren"

    def test_resolve_miss(self, reg):
        assert reg.resolve("无名氏") is None
        assert reg.resolve("") is None

    def test_get_resolved(self, reg):
        assert reg.get_resolved("maodaren").creator_id == "maodaren"  # 精确
        assert reg.get_resolved("kol_cat_lord_fire").creator_id == "maodaren"  # alias
        assert reg.get_resolved("无名氏") is None


class TestHelpers:
    def test_display_name_fallback(self, tmp_path):
        _write_yaml(tmp_path, "named", {"creator_id": "named", "display_name": "有名"})
        _write_yaml(tmp_path, "anon", {"creator_id": "anon"})
        reg = _registry(tmp_path)
        assert reg.display_name("named") == "有名"
        assert reg.display_name("anon") == "anon"       # 无 display_name 回退
        assert reg.display_name("missing") == "missing"  # 无档案回退

    def test_declared_style(self, tmp_path):
        _write_yaml(tmp_path, "k", {
            "creator_id": "k",
            "trading_style": {"does_short": False, "entry_style": "left_side"},
        })
        reg = _registry(tmp_path)
        style = reg.declared_style("k")
        assert style is not None and style.entry_style == "left_side"
        assert reg.declared_style("missing") is None


class TestTTL:
    def test_clear_cache_picks_up_new_files(self, tmp_path):
        _write_yaml(tmp_path, "k1", {"creator_id": "k1"})
        reg = _registry(tmp_path, ttl=3600)
        assert len(reg.list_profiles()) == 1
        _write_yaml(tmp_path, "k2", {"creator_id": "k2"})
        assert len(reg.list_profiles()) == 1  # TTL 内不重读
        reg.clear_cache()
        assert len(reg.list_profiles()) == 2

    def test_ttl_expiry_rebuilds(self, tmp_path):
        _write_yaml(tmp_path, "k1", {"creator_id": "k1"})
        reg = _registry(tmp_path, ttl=0.0)  # 立即过期
        assert len(reg.list_profiles()) == 1
        _write_yaml(tmp_path, "k2", {"creator_id": "k2"})
        assert len(reg.list_profiles()) == 2

    def test_get_registry_per_root_instances(self, tmp_path):
        a = get_registry(tmp_path)
        b = get_registry(tmp_path)
        assert a is b
