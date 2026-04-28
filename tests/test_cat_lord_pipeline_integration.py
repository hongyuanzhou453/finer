"""Integration test: cat lord fixture full pipeline.

Runs standardize_markdown_source → extract_intents_from_envelope on the
cat lord fixture and validates structural expectations.
"""

import pytest
from datetime import datetime
from pathlib import Path

from finer.parsing.content_standardizer import standardize_markdown_source
from finer.extraction.intent_extractor import extract_intents_from_envelope


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kol"
MARKDOWN_PATH = FIXTURE_DIR / "cat_lord_strategy_2026_03_12.md"


@pytest.fixture
def envelope():
    """Run standardizer on cat lord fixture."""
    markdown = MARKDOWN_PATH.read_text(encoding="utf-8")
    return standardize_markdown_source(
        markdown=markdown,
        source_type="feishu_doc",
        creator_id="cat_lord_fire",
        creator_name="猫大人FIRE",
        published_at=datetime(2026, 3, 12),
    )


@pytest.fixture
def result(envelope):
    """Run intent extractor on cat lord fixture."""
    return extract_intents_from_envelope(envelope)


class TestCatLordPipeline:
    """Full pipeline integration tests."""

    def test_envelope_has_blocks(self, envelope):
        """Standardizer produces blocks."""
        assert len(envelope.blocks) >= 20, f"Expected >= 20 blocks, got {len(envelope.blocks)}"

    def test_envelope_has_multiple_block_types(self, envelope):
        """Standardizer detects heading, list, paragraph types."""
        types = {b.block_type for b in envelope.blocks}
        assert "heading" in types
        assert "paragraph" in types
        assert "list" in types

    def test_envelope_no_section_separators(self, envelope):
        """Markdown --- separators are filtered out."""
        for block in envelope.blocks:
            assert block.block_type != "section_separator"
            assert block.block_type != "table", \
                f"Block should not be table: {block.text[:50]}"

    def test_extracts_minimum_intents(self, result):
        """At least 5 intents extracted (one per section)."""
        assert len(result.intents) >= 5, \
            f"Expected >= 5 intents, got {len(result.intents)}"

    def test_all_intents_have_evidence(self, result):
        """Every intent has at least one evidence span."""
        for intent in result.intents:
            assert len(intent.evidence_span_ids) >= 1, \
                f"Intent {intent.target_name} has no evidence spans"

    def test_evidence_spans_reference_blocks(self, result, envelope):
        """Evidence span IDs map to real blocks."""
        block_ids = {b.block_id for b in envelope.blocks}
        for span in result.evidence_spans:
            assert span.block_id in block_ids, \
                f"Evidence span {span.evidence_span_id} references unknown block {span.block_id}"

    def test_no_position_ratio_in_metadata(self, result):
        """No intent should generate position percentage."""
        for intent in result.intents:
            assert "position_ratio" not in intent.metadata
            assert "position_size_pct" not in intent.metadata

    def test_direction_values_valid(self, result):
        """All intents have valid direction values."""
        valid = {"bullish", "bearish", "neutral", "mixed", "unknown"}
        for intent in result.intents:
            assert intent.direction in valid, \
                f"Invalid direction: {intent.direction}"

    def test_actionability_values_valid(self, result):
        """All intents have valid actionability values."""
        valid = {"opinion", "watch", "explicit_action", "review_required"}
        for intent in result.intents:
            assert intent.actionability in valid, \
                f"Invalid actionability: {intent.actionability}"


class TestCatLordEntityCoverage:
    """Entity-specific coverage tests."""

    def test_covers_li_auto(self, result):
        """理想汽车 is covered."""
        li_intents = [i for i in result.intents
                      if i.target_symbol == "LI" or "理想" in i.target_name]
        assert len(li_intents) >= 1, "理想汽车 not found in intents"

    def test_covers_baofeng_energy(self, result):
        """宝丰能源 is covered."""
        bf_intents = [i for i in result.intents
                      if "600989" in str(i.target_symbol) or "宝丰" in i.target_name]
        assert len(bf_intents) >= 1, "宝丰能源 not found in intents"

    def test_covers_green_power_or_compute(self, result):
        """绿电 or 算电协同 sector is covered."""
        sector_intents = [i for i in result.intents
                          if i.target_type == "sector"]
        assert len(sector_intents) >= 1, \
            f"Expected >= 1 sector intent, got {len(sector_intents)}"

    def test_covers_csiq(self, result):
        """阿特斯/CSIQ is covered."""
        csiq_intents = [i for i in result.intents
                        if i.target_symbol == "CSIQ" or "阿特斯" in i.target_name or "CSIQ" in i.target_name]
        assert len(csiq_intents) >= 1, "CSIQ not found in intents"

    def test_covers_tme(self, result):
        """腾讯音乐 is covered."""
        tme_intents = [i for i in result.intents
                       if i.target_symbol == "TME" or "腾讯音乐" in i.target_name]
        assert len(tme_intents) >= 1, "TME not found in intents"

    def test_stock_intent_count(self, result):
        """At least 4 stock intents (LI, 600989, CSIQ, TME)."""
        stock_intents = [i for i in result.intents if i.target_type == "stock"]
        assert len(stock_intents) >= 4, \
            f"Expected >= 4 stock intents, got {len(stock_intents)}"

    def test_has_risk_flags(self, result):
        """At least one intent has risk-related flags."""
        intents_with_risk = [i for i in result.intents
                             if "risk_warning" in i.ambiguity_flags]
        assert len(intents_with_risk) >= 1, \
            "No intents with risk_warning flag"


class TestCatLordResultStructure:
    """Structural validation of extraction result."""

    def test_result_has_envelope_id(self, result, envelope):
        """Result references the correct envelope."""
        assert result.envelope_id == envelope.envelope_id

    def test_result_extractor_version(self, result):
        """Extractor version is set."""
        assert result.extractor_version == "minimal_v1"

    def test_result_timestamp(self, result):
        """Extraction timestamp is set."""
        assert isinstance(result.extraction_timestamp, datetime)

    def test_intent_conviction_in_range(self, result):
        """Conviction scores are in [0, 1]."""
        for intent in result.intents:
            assert 0.0 <= intent.conviction <= 1.0, \
                f"Conviction out of range: {intent.conviction}"

    def test_intent_confidence_in_range(self, result):
        """Confidence scores are in [0, 1]."""
        for intent in result.intents:
            assert 0.0 <= intent.confidence <= 1.0, \
                f"Confidence out of range: {intent.confidence}"

    def test_result_json_serializable(self, result):
        """Result can be serialized to JSON."""
        data = result.to_dict()
        assert isinstance(data, dict)
        assert "intents" in data
        assert "evidence_spans" in data
