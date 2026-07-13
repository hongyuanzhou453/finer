"""Tests for the registry-merged creator tag map (ingestion/classifier.py)."""
from __future__ import annotations

import pytest

from finer.ingestion.classifier import (
    _TAG_TO_CREATOR,
    _extract_tags,
    _merged_creator_tags,
)


def test_merged_map_is_superset_of_static():
    """The static baseline (incl. pseudo-creator routing) must survive the merge."""
    merged = _merged_creator_tags()
    for tag, creator in _TAG_TO_CREATOR.items():
        assert merged.get(tag) == creator, tag
    assert merged["研报"] == "_research"  # pseudo-creator stays static-routed


def test_registry_alias_extends_static_map():
    """九友 exists only as a registry alias (9you.yaml) — proof of收编 value."""
    merged = _merged_creator_tags()
    assert "九友" not in _TAG_TO_CREATOR
    assert merged.get("九友") == "9you"


def test_extract_tags_with_merged_map():
    merged = _merged_creator_tags()
    creator, source = _extract_tags("#九友 #chat 今天的群聊记录", merged)
    assert creator == "9you"
    assert source == "chat_export"


def test_extract_tags_default_map_unchanged():
    """Direct callers without a tag_map keep the legacy static behaviour."""
    creator, _ = _extract_tags("#九友 记录")
    assert creator is None  # static map has no 九友 — pinned legacy semantics


def test_registry_failure_falls_back_to_static(monkeypatch):
    import finer.services.kol_registry as registry_module

    def boom(*args, **kwargs):
        raise RuntimeError("registry down")

    monkeypatch.setattr(registry_module, "get_registry", boom)
    merged = _merged_creator_tags()
    assert merged == _TAG_TO_CREATOR
