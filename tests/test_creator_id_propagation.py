"""Regression: F1 standardizers must propagate creator_id from F0, not just creator_name.

Guards the 地基-A P0 fix. The F1 layer historically copied `creator_name` while
dropping `creator_id`, which collapsed all downstream per-KOL grouping (opinions
timeline, credibility board, market sentiment) into a single 'unknown' bucket.
See docs/specs/2026-07-01-dashboard-live-graduation-plan.md 卡 2.
"""
from pathlib import Path

import pytest

from finer.schemas.content import ContentRecord
from finer.parsing.manual_text_standardizer import ManualTextStandardizer
from finer.parsing.placeholder_adapters import create_unsupported_envelope


def _f0_record(**overrides) -> ContentRecord:
    base = dict(
        content_id="cid-creator-001",
        source_type="manual_upload",
        source_platform="local",
        raw_path="data/raw/_inbox/x.txt",
        file_type="text",
        title="creator id propagation test",
        creator_id="trader_ji",
        creator_name="trader_ji",
    )
    base.update(overrides)
    return ContentRecord(**base)


def test_manual_text_standardizer_propagates_creator_id(tmp_path: Path) -> None:
    src = tmp_path / "post.txt"
    src.write_text("茅台回踩 1580 是黄金坑，缩量企稳就是上车点。", encoding="utf-8")
    rec = _f0_record(raw_path=str(src))

    env = ManualTextStandardizer().standardize(rec, src)

    # creator_id was None before the F1 pass-through fix
    assert env.creator_id == "trader_ji"
    assert env.creator_name == "trader_ji"


def test_placeholder_envelope_propagates_creator_id() -> None:
    rec = _f0_record()
    env = create_unsupported_envelope(
        rec, Path("x.txt"), "manual_text", reason="unsupported source type"
    )
    assert env.creator_id == "trader_ji"


def test_creator_id_none_is_not_fabricated(tmp_path: Path) -> None:
    """When F0 has no creator_id, F1 must not invent one."""
    src = tmp_path / "post.txt"
    src.write_text("some content", encoding="utf-8")
    rec = _f0_record(raw_path=str(src), creator_id=None, creator_name=None)

    env = ManualTextStandardizer().standardize(rec, src)

    assert env.creator_id is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
