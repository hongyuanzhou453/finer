"""D1 — T9 sector transmission adapter (second declarative adapter, A3 pattern)."""

from __future__ import annotations

from finer.extraction.sector_transmission_adapter import (
    adapt_t9_record,
    derive_t9_intent_id,
    match_theme_to_sector,
)

SECTOR_NAMES = {
    "SEMICONDUCTOR": "半导体",
    "ENERGY_STORAGE": "储能",
    "GOLD": "黄金",
    "ROBOTICS": "机器人",
}


def _t9_row(theme: str, cycle_view: str | None) -> dict:
    return {
        "schema_version": "t9-v0.1",
        "filepath": "/Volumes/NAMEZY/外资研报/2026年/5月/x.pdf",
        "broker": "高盛",
        "extraction": {
            "industry_or_theme": theme,
            "cycle_view": cycle_view,
            "theme_window": "未来12个月",
            "policy_dependency": None,
        },
        "validation": {"json_ok": True},
    }


F0 = {"content_id": "broker_t9test01", "creator_id": "高盛"}
ENV_ID = "env-t9-test-001"


# ── theme mapping ────────────────────────────────────────────────────────────


def test_theme_maps_on_sector_name_substring():
    assert match_theme_to_sector("中国半导体行业", SECTOR_NAMES) == (
        "SEMICONDUCTOR", "半导体",
    )


def test_theme_longest_name_wins():
    names = {**SECTOR_NAMES, "ROBOT_ARM": "机器人手臂"}
    assert match_theme_to_sector("机器人手臂产业链", names) == (
        "ROBOT_ARM", "机器人手臂",
    )


def test_foreign_scoped_theme_refused():
    assert match_theme_to_sector("美国半导体及设备行业", SECTOR_NAMES) is None
    assert match_theme_to_sector("全球能源存储与电池行业", SECTOR_NAMES) is None


def test_unmapped_theme_returns_none():
    assert match_theme_to_sector("中美关系与贸易谈判", SECTOR_NAMES) is None
    assert match_theme_to_sector(None, SECTOR_NAMES) is None


# ── adapt ────────────────────────────────────────────────────────────────────


def test_improving_cycle_becomes_bullish_sector_intent():
    intent, skip = adapt_t9_record(
        _t9_row("中国半导体行业", "improving"), F0, ENV_ID, SECTOR_NAMES
    )
    assert skip is None and intent is not None
    assert intent.target_type == "sector"
    assert intent.target_symbol == "SEMICONDUCTOR"
    assert intent.target_name == "半导体"
    assert intent.direction == "bullish"
    assert intent.actionability == "recommendation"
    assert intent.conviction_source == "derived_lookup"  # R6: no credibility feed
    assert intent.envelope_id == ENV_ID
    assert intent.creator_id == "高盛"
    assert intent.intent_id.startswith("t9i_")
    assert intent.metadata["signal_class"] == "broker_recommendation"


def test_deteriorating_becomes_bearish_and_stable_neutral():
    bear, _ = adapt_t9_record(
        _t9_row("储能产业链", "deteriorating"), F0, ENV_ID, SECTOR_NAMES
    )
    neut, _ = adapt_t9_record(
        _t9_row("黄金市场", "stable"), F0, ENV_ID, SECTOR_NAMES
    )
    assert bear is not None and bear.direction == "bearish"
    assert neut is not None and neut.direction == "neutral"


def test_mixed_or_missing_cycle_view_is_no_claim():
    for cv in ("mixed", None):
        intent, skip = adapt_t9_record(
            _t9_row("中国半导体行业", cv), F0, ENV_ID, SECTOR_NAMES
        )
        assert intent is None and skip == "no_direction_claim"


def test_foreign_theme_skip_reason():
    intent, skip = adapt_t9_record(
        _t9_row("美国半导体及设备行业", "improving"), F0, ENV_ID, SECTOR_NAMES
    )
    assert intent is None and skip == "theme_market_foreign"


def test_unmapped_theme_skip_reason():
    intent, skip = adapt_t9_record(
        _t9_row("中美关系与贸易谈判", "improving"), F0, ENV_ID, SECTOR_NAMES
    )
    assert intent is None and skip == "theme_unmapped"


def test_intent_id_is_content_derived_and_stable():
    a, _ = adapt_t9_record(_t9_row("黄金市场", "improving"), F0, ENV_ID, SECTOR_NAMES)
    b, _ = adapt_t9_record(_t9_row("黄金市场", "improving"), F0, ENV_ID, SECTOR_NAMES)
    assert a is not None and b is not None
    assert a.intent_id == b.intent_id  # rerun-stable (created_at may differ)
    assert a.intent_id == derive_t9_intent_id(
        "/Volumes/NAMEZY/外资研报/2026年/5月/x.pdf", "GOLD", "improving"
    )


def test_direction_changes_id():
    a = derive_t9_intent_id("f.pdf", "GOLD", "improving")
    b = derive_t9_intent_id("f.pdf", "GOLD", "deteriorating")
    assert a != b
