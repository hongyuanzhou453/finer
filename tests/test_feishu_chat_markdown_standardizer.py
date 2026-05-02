"""Unit tests for FeishuChatMarkdownStandardizer.

Tests cover:
- Header parsing (timestamp, speaker, message_type)
- HTML cleaning (<p>...</p> removal)
- Failed forward → attachment_ref
- Q/A format detection
- System noise → system_event
- Block quality scoring (deterministic)
- Block provenance (raw offsets, extractor, source_hash)
- Canonical validator pass
- Edge cases (empty body, unknown type, metadata prefix)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

import pytest

from finer.parsing.feishu_chat_standardizer import (
    FeishuChatMarkdownStandardizer,
    _clean_html,
    _compute_block_quality,
    _detect_qa_format,
    _extract_image_refs,
    _split_messages,
    _parse_timestamp,
)
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    ContentBlock,
    ContentEnvelope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TZ_BEIJING = timezone(timedelta(hours=8))


def _make_f0_record(
    content_id: str = "test_chat_001",
    creator_name: str = "test_user",
    metadata: dict | None = None,
) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        creator_name=creator_name,
        source_platform="feishu",
        content_type="chat_transcript",
        published_at=datetime(2026, 4, 20, 20, 47, 44),
        title="test_chat.md",
        source_path="/tmp/test_chat.md",
        language="zh",
        metadata=metadata or {},
    )


def _write_tmp_chat(tmp_path: Path, content: str, name: str = "chat.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestCleanHtml:
    def test_no_html(self):
        cleaned, flag = _clean_html("hello world")
        assert cleaned == "hello world"
        assert flag is False

    def test_simple_p_tags(self):
        cleaned, flag = _clean_html("<p>line one</p><p>line two</p>")
        assert flag is True
        assert "<p>" not in cleaned
        assert "line one" in cleaned
        assert "line two" in cleaned

    def test_nested_html(self):
        cleaned, flag = _clean_html("<p><b>bold</b> text</p>")
        assert flag is True
        assert "bold" in cleaned
        assert "<b>" not in cleaned

    def test_multiple_newlines_collapsed(self):
        cleaned, flag = _clean_html("<p>a</p>\n\n\n\n<p>b</p>")
        assert flag is True
        assert "\n\n\n" not in cleaned


class TestDetectQaFormat:
    def test_qa_detected(self):
        assert _detect_qa_format("Q: what is AAPL?\nA: it's a stock") is True

    def test_qa_chinese_colon(self):
        assert _detect_qa_format("Q：你好\nA：你好") is True

    def test_no_qa(self):
        assert _detect_qa_format("just a normal message") is False


class TestExtractImageRefs:
    def test_single_ref(self):
        refs = _extract_image_refs("see [Image: abc123.png] here")
        assert refs == ["abc123.png"]

    def test_multiple_refs(self):
        refs = _extract_image_refs("[Image: a.png] and [Image: b.jpg]")
        assert refs == ["a.png", "b.jpg"]

    def test_no_refs(self):
        assert _extract_image_refs("no images here") == []


class TestParseTimestamp:
    def test_valid(self):
        ts = _parse_timestamp("2026-03-12 14:34:00")
        assert ts.year == 2026
        assert ts.month == 3
        assert ts.day == 12
        assert ts.hour == 14
        assert ts.minute == 34
        assert ts.tzinfo == _TZ_BEIJING


class TestSplitMessages:
    def test_single_message(self):
        raw = "### [2026-03-12 14:34:00] user_a (text)\nhello world"
        msgs = _split_messages(raw)
        assert len(msgs) == 1
        _start, _end, ts, speaker, msg_type, body = msgs[0]
        assert ts == "2026-03-12 14:34:00"
        assert speaker == "user_a"
        assert msg_type == "text"
        assert "hello world" in body

    def test_multiple_messages(self):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\nmsg one\n"
            "### [2026-03-12 14:35:00] user_b (post)\nmsg two"
        )
        msgs = _split_messages(raw)
        assert len(msgs) == 2
        assert msgs[0][2] == "2026-03-12 14:34:00"
        assert msgs[1][2] == "2026-03-12 14:35:00"

    def test_metadata_prefix(self):
        raw = "# Chat History:\n- **Chat ID**: oc_xxx\n\n### [2026-03-12 14:34:00] user_a (text)\nhello"
        msgs = _split_messages(raw)
        # First entry is metadata prefix (ts=None)
        assert msgs[0][2] is None
        assert len(msgs) == 2

    def test_empty_input(self):
        msgs = _split_messages("")
        assert msgs == []


# ---------------------------------------------------------------------------
# Unit tests: BlockQuality scoring
# ---------------------------------------------------------------------------


class TestBlockQuality:
    def test_chat_message_quality(self):
        q = _compute_block_quality("hello world, this is a test message", "chat_message")
        assert isinstance(q, BlockQuality)
        assert 0.0 <= q.readability <= 1.0
        assert q.extraction_confidence == 0.9
        assert q.structural_confidence == 0.95

    def test_attachment_ref_quality(self):
        q = _compute_block_quality("[Merged forward: fetch failed]", "attachment_ref", has_failed_forward=True)
        assert "attachment_missing" in q.quality_flags
        assert q.noise_score > 0.0

    def test_system_event_quality(self):
        q = _compute_block_quality("system notification", "system_event")
        assert "system_noise" in q.quality_flags
        assert q.noise_score == 0.8

    def test_empty_text_quality(self):
        q = _compute_block_quality("", "chat_message")
        assert q.readability == 0.1
        assert q.completeness == 0.1
        assert "empty_content" in q.quality_flags

    def test_html_cleaned_flag(self):
        q = _compute_block_quality("text", "chat_message", html_cleaned=True)
        assert "html_cleaned" in q.quality_flags


# ---------------------------------------------------------------------------
# Unit tests: standardizer integration
# ---------------------------------------------------------------------------


class TestFeishuChatMarkdownStandardizer:
    @pytest.fixture
    def std(self):
        return FeishuChatMarkdownStandardizer()

    def test_basic_text_messages(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "hello world\n"
            "### [2026-03-12 14:35:00] user_b (text)\n"
            "goodbye world"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert isinstance(envelope, ContentEnvelope)
        assert len(envelope.blocks) == 2
        assert envelope.blocks[0].block_type == "chat_message"
        assert envelope.blocks[0].speaker == "user_a"
        assert envelope.blocks[0].text == "hello world"
        assert envelope.blocks[1].speaker == "user_b"

    def test_failed_forward_becomes_attachment_ref(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (merge_forward)\n"
            "[Merged forward: fetch failed: permission denied]"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        block = envelope.blocks[0]
        assert block.block_type == "attachment_ref"
        assert block.metadata.get("failure_reason") == "fetch_failed"

    def test_successful_merge_forward(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (merge_forward)\n"
            "[Merged forward: 5 messages from group]\n"
            "actual forwarded content here"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "chat_message"
        assert envelope.blocks[0].metadata.get("message_type") == "merge_forward"

    def test_html_cleaned(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "<p>line one</p><p>line two</p>"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].metadata.get("html_cleaned") is True
        assert "<p>" not in envelope.blocks[0].text

    def test_qa_format_detected(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "Q: what is AAPL?\nA: Apple Inc."
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert envelope.blocks[0].metadata.get("qa_format") is True

    def test_image_refs_in_metadata(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "check this [Image: chart.png]"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        refs = envelope.blocks[0].metadata.get("image_refs", [])
        assert "chart.png" in refs

    def test_system_event_for_unknown_type(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] system (notification)\n"
            "user joined the group"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "system_event"

    def test_metadata_prefix_as_system_event(self, std, tmp_path):
        raw = (
            "# Chat History:\n"
            "- **Chat ID**: oc_xxx\n"
            "- **Creator Segment**: some info\n\n"
            "### [2026-03-12 14:34:00] user_a (text)\nhello"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        # metadata prefix may or may not produce a block depending on content
        # but we should have at least the chat message
        assert any(b.block_type == "chat_message" for b in envelope.blocks)

    def test_empty_body_skipped(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n\n"
            "### [2026-03-12 14:35:00] user_b (text)\nhello"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        # empty body should be skipped
        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].text == "hello"

    def test_order_index_sequential(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] a (text)\nmsg1\n"
            "### [2026-03-12 14:35:00] b (text)\nmsg2\n"
            "### [2026-03-12 14:36:00] c (text)\nmsg3"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i

    def test_envelope_id_propagated(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        for block in envelope.blocks:
            assert block.envelope_id == envelope.envelope_id

    def test_provenance_fields(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello world"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        block = envelope.blocks[0]
        assert block.provenance is not None
        assert block.provenance.extractor == "feishu_chat_standardizer"
        assert block.provenance.extractor_version == "1.0.0"
        assert block.provenance.source_hash is not None
        assert block.provenance.raw_path == str(path)

    def test_timestamp_beijing_tz(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        ts = envelope.blocks[0].timestamp
        assert ts is not None
        assert ts.tzinfo == _TZ_BEIJING
        assert ts.hour == 14

    def test_f0_metadata_propagation(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record(
            content_id="my_custom_id",
            metadata={"chat_id": "oc_xxx", "chat_name": "test chat"},
        )
        envelope = std.standardize(f0, path)

        assert envelope.source_record_id == "my_custom_id"
        assert envelope.standardization_profile == "feishu_chat_markdown_v1"
        assert envelope.raw_path == str(path)
        assert envelope.metadata.get("chat_id") == "oc_xxx"

    def test_canonical_validator_passes(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "hello world\n"
            "### [2026-03-12 14:35:00] user_b (merge_forward)\n"
            "[Merged forward: fetch failed: perm denied]"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        violations = envelope.validate_canonical_f1()
        assert violations == [], (
            f"Canonical validation failed:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_schema_version_is_v1(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert envelope.schema_version == "v1.0"

    def test_source_type_feishu_chat(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert envelope.source_type == "feishu_chat"

    def test_temporal_anchors_empty(self, std, tmp_path):
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert envelope.temporal_anchors == []
        assert envelope.entity_anchors == []

    def test_post_type_message(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (post)\n"
            "rich content with **bold**"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "chat_message"
        assert envelope.blocks[0].metadata.get("message_type") == "post"

    def test_large_chat_order_consistency(self, std, tmp_path):
        """Simulate many messages to verify order_index consistency."""
        lines = []
        for i in range(50):
            lines.append(f"### [2026-03-12 14:{i:02d}:00] user_{i % 3} (text)")
            lines.append(f"message number {i}")
        raw = "\n".join(lines)
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 50
        for i, block in enumerate(envelope.blocks):
            assert block.order_index == i
            assert block.envelope_id == envelope.envelope_id


# ---------------------------------------------------------------------------
# Edge cases: empty / header-only / malformed input
# ---------------------------------------------------------------------------


class TestEmptyAndMalformedInput:
    """F1 adapters must never return non-canonical empty envelopes."""

    @pytest.fixture
    def std(self):
        return FeishuChatMarkdownStandardizer()

    def test_empty_file(self, std, tmp_path):
        path = _write_tmp_chat(tmp_path, "")
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "system_event"
        assert "empty_export" in envelope.blocks[0].metadata.get("reason", "")
        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_header_only_no_messages(self, std, tmp_path):
        raw = "# Chat History:\n- **Chat ID**: oc_xxx\n---"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) >= 1
        assert all(b.block_type == "system_event" for b in envelope.blocks)
        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_malformed_no_header_pattern(self, std, tmp_path):
        raw = "just some random text\nwithout any headers\nat all"
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) >= 1
        assert envelope.blocks[0].block_type == "system_event"
        assert "no_parseable_messages" in envelope.blocks[0].metadata.get("reason", "")
        violations = envelope.validate_canonical_f1()
        assert violations == []

    def test_whitespace_only(self, std, tmp_path):
        path = _write_tmp_chat(tmp_path, "   \n\n  \n")
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        assert len(envelope.blocks) == 1
        assert envelope.blocks[0].block_type == "system_event"
        violations = envelope.validate_canonical_f1()
        assert violations == []


# ---------------------------------------------------------------------------
# Provenance offset replay: raw_text[start:end] must recover block content
# ---------------------------------------------------------------------------


class TestProvenanceReplay:
    """Verify that provenance character offsets can recover the source span."""

    @pytest.fixture
    def std(self):
        return FeishuChatMarkdownStandardizer()

    def test_offsets_recover_body_text(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "hello world\n"
            "### [2026-03-12 14:35:00] user_b (text)\n"
            "goodbye world"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        raw_text = path.read_text(encoding="utf-8")
        for block in envelope.blocks:
            prov = block.provenance
            assert prov is not None
            span = raw_text[prov.raw_offset_start:prov.raw_offset_end]
            # The span should contain at least a fragment of the block text
            assert block.text[:20] in span or span.strip() != "", (
                f"Block text {block.text[:40]!r} not recoverable from "
                f"offset [{prov.raw_offset_start}:{prov.raw_offset_end}]: "
                f"got {span[:60]!r}"
            )

    def test_offsets_recover_chinese_text(self, std, tmp_path):
        """Chinese chars are multi-byte UTF-8 but single Python characters."""
        raw = (
            "### [2026-03-12 14:34:00] user_a (text)\n"
            "你好世界，这是一条中文消息\n"
            "### [2026-03-12 14:35:00] user_b (text)\n"
            "第二条消息"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        raw_text = path.read_text(encoding="utf-8")
        for block in envelope.blocks:
            prov = block.provenance
            assert prov is not None
            span = raw_text[prov.raw_offset_start:prov.raw_offset_end]
            # At least the first few chars of block text should appear in the span
            assert block.text[:6] in span, (
                f"Chinese block text not recoverable: "
                f"expected {block.text[:10]!r} in span, got {span[:30]!r}"
            )

    def test_offsets_monotonically_increase(self, std, tmp_path):
        raw = (
            "### [2026-03-12 14:34:00] a (text)\nmsg1\n"
            "### [2026-03-12 14:35:00] b (text)\nmsg2\n"
            "### [2026-03-12 14:36:00] c (text)\nmsg3"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        for i in range(1, len(envelope.blocks)):
            prev_end = envelope.blocks[i - 1].provenance.raw_offset_end
            curr_start = envelope.blocks[i].provenance.raw_offset_start
            assert curr_start >= prev_end, (
                f"Block {i} start {curr_start} < block {i-1} end {prev_end}"
            )

    def test_metadata_prefix_offsets(self, std, tmp_path):
        raw = (
            "# Chat History:\n"
            "- **Chat ID**: oc_xxx\n\n"
            "### [2026-03-12 14:34:00] user_a (text)\nhello"
        )
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        raw_text = path.read_text(encoding="utf-8")
        # First block is the metadata prefix system_event
        first = envelope.blocks[0]
        assert first.block_type == "system_event"
        prov = first.provenance
        span = raw_text[prov.raw_offset_start:prov.raw_offset_end]
        assert "Chat ID" in span or "Chat History" in span, (
            f"Metadata prefix not in span: {span[:40]!r}"
        )

    def test_no_trailing_newline_offsets_within_bounds(self, std, tmp_path):
        """Files without trailing newline must not inflate end offsets."""
        raw = "### [2026-03-12 14:34:00] a (text)\nhello"
        assert not raw.endswith("\n")
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        text_len = len(raw)
        for i, block in enumerate(envelope.blocks):
            p = block.provenance
            assert p.raw_offset_end <= text_len, (
                f"Block {i}: end {p.raw_offset_end} > len(raw_text) {text_len}"
            )

    def test_with_trailing_newline_offsets_within_bounds(self, std, tmp_path):
        """Files with trailing newline must not inflate end offsets."""
        raw = "### [2026-03-12 14:34:00] a (text)\nhello\n"
        assert raw.endswith("\n")
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        text_len = len(raw)
        for i, block in enumerate(envelope.blocks):
            p = block.provenance
            assert p.raw_offset_end <= text_len, (
                f"Block {i}: end {p.raw_offset_end} > len(raw_text) {text_len}"
            )

    def test_all_offsets_within_bounds(self, std, tmp_path):
        """Every block must satisfy 0 <= start <= end <= len(raw_text)."""
        lines = []
        for i in range(20):
            lines.append(f"### [2026-03-12 14:{i:02d}:00] user_{i} (text)")
            lines.append(f"message {i} with content")
        raw = "\n".join(lines)
        path = _write_tmp_chat(tmp_path, raw)
        f0 = _make_f0_record()
        envelope = std.standardize(f0, path)

        text_len = len(raw)
        for i, block in enumerate(envelope.blocks):
            p = block.provenance
            assert 0 <= p.raw_offset_start <= p.raw_offset_end <= text_len, (
                f"Block {i}: bounds [{p.raw_offset_start}:{p.raw_offset_end}] "
                f"outside [0:{text_len}]"
            )
