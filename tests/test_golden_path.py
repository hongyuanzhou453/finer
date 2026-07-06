"""Golden Path pipeline tests.

Tests run_golden_path(envelope) -> GoldenPathResult with mocked LLM router.
Most tests read ``.primary_action`` (the representative TradeAction).
Verifies F3→F4→F5 canonical chain, artifact writing, and error handling.

Run: pytest tests/test_golden_path.py -v
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock, BlockQuality, BlockProvenance
from finer.schemas.quality import QualityCard


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_block_quality() -> BlockQuality:
    return BlockQuality(
        readability=0.9,
        extraction_confidence=0.9,
        structural_confidence=0.9,
        completeness=0.9,
        noise_score=0.1,
    )


def _make_block_provenance() -> BlockProvenance:
    return BlockProvenance(
        extractor="test_standardizer",
        extractor_version="v1",
    )


def _make_quality_card() -> QualityCard:
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.9,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.9,
        evidence_traceability_score=0.9,
    )


def _make_envelope(**overrides) -> ContentEnvelope:
    defaults = dict(
        envelope_id="env_golden_001",
        source_type="feishu_chat",
        creator_id="test_kol",
        creator_name="Test KOL",
        published_at=datetime(2026, 5, 10, 9, 0, 0, tzinfo=timezone.utc),
        quality_card=_make_quality_card(),
        blocks=[
            ContentBlock(
                block_id="blk_001",
                block_type="paragraph",
                text="看好苹果 AAPL，准备加仓",
                order_index=0,
                quality=_make_block_quality(),
                provenance=_make_block_provenance(),
            ),
            # second block so multi-intent mocks can quote verbatim evidence
            # (the F3 validator rejects intents whose quote isn't in any block)
            ContentBlock(
                block_id="blk_002",
                block_type="paragraph",
                text="看好微软 MSFT，准备买入",
                order_index=1,
                quality=_make_block_quality(),
                provenance=_make_block_provenance(),
            ),
        ],
    )
    defaults.update(overrides)
    return ContentEnvelope(**defaults)


_MOCK_LLM_OUTPUT = {
    "intents": [
        {
            "target_name": "Apple Inc.",
            "target_symbol": "AAPL",
            "target_type": "stock",
            "direction": "bullish",
            "actionability": "explicit_action",
            "position_delta_hint": "add",
            "conviction": 0.85,
            "confidence": 0.9,
            "market": "US",
            "evidence_text": "看好苹果 AAPL，准备加仓",
        },
    ],
}


@pytest.fixture(autouse=True)
def _patch_model_router():
    """Mock ModelRouter so no real LLM calls are made."""
    mock_router = MagicMock()
    mock_router.call_json.return_value = _MOCK_LLM_OUTPUT

    with patch(
        "finer.pipeline.golden_path.ModelRouter",
        return_value=mock_router,
    ), patch(
        "finer.extraction.intent_extractor.ModelRouter",
        return_value=mock_router,
    ):
        yield mock_router


# ── Tests ────────────────────────────────────────────────────────────────────


class TestRunGoldenPath:
    """Test the run_golden_path function."""

    def test_returns_golden_path_result(self, tmp_path):
        from finer.pipeline.golden_path import GoldenPathResult, run_golden_path

        result = run_golden_path(_make_envelope(), data_root=tmp_path)
        assert isinstance(result, GoldenPathResult)
        assert result.intent_count == 1
        assert result.policy_mapping_count == 1
        assert result.action_count == 1
        assert result.primary_action.__class__.__name__ == "TradeAction"

    def test_returns_all_trade_actions_for_multi_intent_envelope(
        self,
        tmp_path,
        _patch_model_router,
    ):
        from finer.pipeline.golden_path import run_golden_path

        _patch_model_router.call_json.return_value = {
            "intents": [
                _MOCK_LLM_OUTPUT["intents"][0],
                {
                    "target_name": "Microsoft Corp.",
                    "target_symbol": "MSFT",
                    "target_type": "stock",
                    "direction": "bullish",
                    "actionability": "explicit_action",
                    "position_delta_hint": "open",
                    "conviction": 0.8,
                    "confidence": 0.88,
                    "market": "US",
                    "evidence_text": "看好微软 MSFT，准备买入",
                },
            ],
        }

        result = run_golden_path(_make_envelope(), data_root=tmp_path)

        assert result.intent_count == 2
        assert result.policy_mapping_count == 2
        assert result.action_count == 2
        assert {ta.target.ticker for ta in result.trade_actions} == {"AAPL", "MSFT"}
        assert len(list((tmp_path / "F5_executed").glob("*.json"))) == 2

    def test_canonical_trace_status(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert ta.canonical_trace_status == "canonical"

    def test_has_intent_id_and_policy_id(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert ta.intent_id is not None
        assert ta.policy_id is not None

    def test_has_evidence_span_ids(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert len(ta.evidence_span_ids) > 0

    def test_has_execution_timing(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert ta.execution_timing is not None

    def test_target_ticker(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert ta.target.ticker == "AAPL"

    def test_direction_bullish(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert ta.direction.value == "bullish"

    def test_source_creator_id(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        assert ta.source.creator_id == "test_kol"


class TestArtifactWriting:
    """Test that intermediate artifacts are written to disk."""

    def test_f3_intents_written(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        run_golden_path(_make_envelope(), data_root=tmp_path)
        f3_dir = tmp_path / "F3_intents"
        assert f3_dir.exists()
        files = list(f3_dir.glob("*.json"))
        assert len(files) >= 1

    def test_f4_policy_written(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        run_golden_path(_make_envelope(), data_root=tmp_path)
        f4_dir = tmp_path / "F4_policy_mapped"
        assert f4_dir.exists()
        batch_files = list(f4_dir.glob("*.batch.json"))
        assert len(batch_files) == 1

    def test_f5_executed_written(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        run_golden_path(_make_envelope(), data_root=tmp_path)
        f5_dir = tmp_path / "F5_executed"
        assert f5_dir.exists()
        files = list(f5_dir.glob("*.json"))
        assert len(files) >= 1

    def test_f3_intent_contains_direction(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        run_golden_path(_make_envelope(), data_root=tmp_path)
        f3_files = list((tmp_path / "F3_intents").glob("*.json"))
        data = json.loads(f3_files[0].read_text())
        assert data["direction"] == "bullish"

    def test_f5_action_is_canonical(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        run_golden_path(_make_envelope(), data_root=tmp_path)
        f5_files = list((tmp_path / "F5_executed").glob("*.json"))
        data = json.loads(f5_files[0].read_text())
        assert data["canonical_trace_status"] == "canonical"


class TestErrorHandling:
    """Test error cases."""

    def test_no_intents_raises(self, tmp_path, _patch_model_router):
        from finer.pipeline.golden_path import run_golden_path

        _patch_model_router.call_json.return_value = {"intents": []}
        with pytest.raises(ValueError, match="No intents extracted"):
            run_golden_path(_make_envelope(), data_root=tmp_path)


class TestCanonicalChain:
    """Test the full F3→F4→F5 canonical chain."""

    def test_intent_id_in_chain(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action

        # F3 artifact should have matching intent_id
        f3_files = list((tmp_path / "F3_intents").glob("*.json"))
        f3_data = json.loads(f3_files[0].read_text())
        assert f3_data["intent_id"] == ta.intent_id

    def test_policy_id_in_chain(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action

        # F4 artifact should have matching policy_id
        f4_dir = tmp_path / "F4_policy_mapped"
        policy_files = [f for f in f4_dir.glob("*.json") if not f.name.endswith(".batch.json")]
        f4_data = json.loads(policy_files[0].read_text())
        assert f4_data["policy_id"] == ta.policy_id

    def test_evidence_span_ids_from_intent(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        envelope = _make_envelope()
        ta = run_golden_path(envelope, data_root=tmp_path).primary_action

        # TradeAction evidence_span_ids should come from F3 intent
        f3_files = list((tmp_path / "F3_intents").glob("*.json"))
        f3_data = json.loads(f3_files[0].read_text())
        assert ta.evidence_span_ids == f3_data["evidence_span_ids"]

    def test_f5_action_serializable(self, tmp_path):
        from finer.pipeline.golden_path import run_golden_path

        ta = run_golden_path(_make_envelope(), data_root=tmp_path).primary_action
        dumped = ta.model_dump()
        assert dumped["canonical_trace_status"] == "canonical"
        assert dumped["intent_id"] is not None
        assert dumped["policy_id"] is not None
