"""F1.5 Cat Lord golden fixture tests for LLM topic assembly.

Default tests use a mock LLM response built from the golden fixture, so the
suite does not spend tokens.  The real DeepSeek smoke test is opt-in via:

    FINER_RUN_DEEPSEEK_TESTS=1 pytest tests/test_cat_lord_topic_assembly_llm.py -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from finer.parsing import LLMTopicAssemblyAdapter, LLMTopicAssemblyError, TopicAssembler
from finer.schemas.content_envelope import ContentEnvelope


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kol"
INPUT_PATH = FIXTURE_DIR / "cat_lord_topic_assembly_input.json"
EXPECTED_PATH = FIXTURE_DIR / "cat_lord_topic_assembly_expected.json"

EXPECTED_TOPIC_BLOCK_IDS = [
    ["cl_ta_002", "cl_ta_003", "cl_ta_004"],
    ["cl_ta_005", "cl_ta_006", "cl_ta_007"],
    ["cl_ta_008", "cl_ta_009", "cl_ta_010"],
    ["cl_ta_012", "cl_ta_013", "cl_ta_014"],
    ["cl_ta_016", "cl_ta_017", "cl_ta_019"],
]

EXPECTED_UNASSIGNED_IDS = [
    "cl_ta_001",
    "cl_ta_011",
    "cl_ta_015",
    "cl_ta_018",
    "cl_ta_020",
    "cl_ta_021",
    "cl_ta_022",
]


def _load_envelope() -> ContentEnvelope:
    return ContentEnvelope.model_validate_json(INPUT_PATH.read_text(encoding="utf-8"))


def _load_expected() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def _mock_llm_response_from_expected() -> str:
    """Convert expected TopicAssemblyResult fixture into LLM adapter payload."""
    expected = _load_expected()
    payload = {
        "topic_blocks": [
            {
                "topic_title": tb["topic_title"],
                "topic_type": tb["topic_type"],
                "source_block_ids": tb["source_block_ids"],
                "primary_entity_ids": tb.get("primary_entity_ids", []),
                "secondary_entity_ids": tb.get("secondary_entity_ids", []),
                "summary": tb.get("summary", ""),
                "segmentation_reason": tb.get("segmentation_reason", ""),
                "confidence": tb.get("confidence", 0.8),
                "ambiguity_flags": tb.get("ambiguity_flags", []),
            }
            for tb in expected["topic_blocks"]
        ],
        "unassigned_block_ids": expected["unassigned_block_ids"],
        "reasoning_summary": "Golden fixture replay for F1.5 LLM assembly.",
        "confidence": 0.9,
    }
    return json.dumps(payload, ensure_ascii=False)


def _assert_cat_lord_golden_result(result) -> None:
    """Strictly verify the F1.5 golden topic boundaries."""
    assert len(result.topic_blocks) == 5
    assert [tb.source_block_ids for tb in result.topic_blocks] == EXPECTED_TOPIC_BLOCK_IDS
    assert result.unassigned_block_ids == EXPECTED_UNASSIGNED_IDS

    assigned = []
    for tb in result.topic_blocks:
        assigned.extend(tb.source_block_ids)
        assert tb.raw_text
        assert "direction" not in tb.model_dump()
        assert "trade_action" not in tb.model_dump()

    all_input_ids = {block.block_id for block in _load_envelope().blocks}
    all_output_ids = set(assigned) | set(result.unassigned_block_ids)
    assert all_output_ids == all_input_ids
    assert len(assigned) + len(result.unassigned_block_ids) == len(all_input_ids)


def test_cat_lord_golden_fixture_with_llm_topic_assembler_mock():
    """TopicAssembler(use_llm=True) must validate against the Cat Lord fixture."""
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: _mock_llm_response_from_expected()
    )
    assembler = TopicAssembler(use_llm=True, llm_adapter=adapter)

    result = assembler.assemble(_load_envelope())

    assert result.assembly_strategy == "llm_constrained_deepseek_v1"
    _assert_cat_lord_golden_result(result)


def test_cat_lord_golden_fixture_rejects_missing_block_from_mock_llm():
    """The validator must fail when the LLM omits a Cat Lord block."""
    payload = json.loads(_mock_llm_response_from_expected())
    payload["unassigned_block_ids"].remove("cl_ta_022")
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: json.dumps(payload, ensure_ascii=False)
    )
    assembler = TopicAssembler(use_llm=True, llm_adapter=adapter)

    with pytest.raises(LLMTopicAssemblyError, match="omitted"):
        assembler.assemble(_load_envelope())


def test_cat_lord_golden_fixture_rejects_fabricated_block_from_mock_llm():
    """The validator must fail when the LLM invents a block id."""
    payload = json.loads(_mock_llm_response_from_expected())
    payload["topic_blocks"][0]["source_block_ids"].append("fake_block_999")
    adapter = LLMTopicAssemblyAdapter(
        llm_fn=lambda messages: json.dumps(payload, ensure_ascii=False)
    )
    assembler = TopicAssembler(use_llm=True, llm_adapter=adapter)

    with pytest.raises(LLMTopicAssemblyError, match="fabricated"):
        assembler.assemble(_load_envelope())


@pytest.mark.skipif(
    os.getenv("FINER_RUN_DEEPSEEK_TESTS") != "1",
    reason="Real DeepSeek test is opt-in to avoid token usage",
)
def test_cat_lord_deepseek_integration_smoke():
    """Optional real DeepSeek smoke test for F1.5 topic assembly.

    This intentionally uses broad assertions because LLM wording can vary.
    Boundary-exact behavior is covered by the mock golden test above.
    """
    assembler = TopicAssembler(use_llm=True)
    try:
        result = assembler.assemble(_load_envelope())
    except LLMTopicAssemblyError as exc:
        if os.getenv("FINER_DEEPSEEK_STRICT") == "1":
            raise
        pytest.skip(f"DeepSeek provider unavailable or returned invalid output: {exc}")

    assert result.assembly_strategy == "llm_constrained_deepseek_v1"
    assert len(result.topic_blocks) >= 5

    assigned = []
    for tb in result.topic_blocks:
        assigned.extend(tb.source_block_ids)
        assert tb.source_block_ids
        assert tb.raw_text

    all_input_ids = {block.block_id for block in _load_envelope().blocks}
    all_output_ids = set(assigned) | set(result.unassigned_block_ids)
    assert all_output_ids == all_input_ids
