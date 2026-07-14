"""F3 extraction guardrail regression tests.

Built from the REAL OCR text of trader_ji weekly-strategy images that the naive
keyword extractor mis-scored as bearish (2026-07-14 over-extraction
investigation, when the first real activation produced an 80%-bearish skew that
was an artifact, not his stance).

Guarded failure modes:
  1. technical watchlist / monitoring tables ("左侧/破位/SP风险") — a right-side
     trader's "左侧为主" means "not buying yet", not "short it";
  2. portfolio-allocation frameworks ("60进攻+20防守+20现金") — position
     structure, not a directional call;
  3. pure risk-caution ("注意回调风险") — risk awareness, not a short.
Positive controls ensure genuine directional calls are NOT suppressed.
"""
from finer.extraction.intent_extractor import (
    RuleBasedIntentExtractor,
    _classify_nondirectional_section,
    _detect_direction,
)
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.quality import QualityCard

# --- real OCR snippets from the activation run (verbatim) ---
SEMI_MONITOR = (
    "• [] 全球芯片* (观察溢价何时转折价) | • [] 中国半导体 (还是左侧为主) | "
    "• [] 半导体 (芯片设计&生产-费城半导体全部左侧，有轻微破位，SP风险变高)"
)
ALLOC_FRAMEWORK = (
    "大A账户【创业板主线，科创板支线，来回搓就行】60进攻+20防守+20现金 "
    "-1最重要是选好板块"
)
PURE_CAUTION = "半导体估值不低，注意回调风险。"

# genuine directional (positive controls — must NOT be suppressed)
AVOID_CALL = "风险比较大，建议回避这只股票。"
REDUCE_CALL = "减持这只票，逐步卖出。"
BULLISH_CALL = "看好半导体，逢低加仓。"


class TestSectionClassifier:
    def test_semiconductor_monitoring_table_is_nondirectional(self):
        assert _classify_nondirectional_section(SEMI_MONITOR) == "monitoring"

    def test_allocation_framework_is_nondirectional(self):
        assert _classify_nondirectional_section(ALLOC_FRAMEWORK) == "allocation"

    def test_strong_action_overrides_monitoring_framing(self):
        # a concrete "加仓" inside a tracking table is still a real trade
        assert _classify_nondirectional_section(SEMI_MONITOR + " 半导体加仓。") is None

    def test_plain_directional_text_is_not_classified(self):
        assert _classify_nondirectional_section(REDUCE_CALL) is None
        assert _classify_nondirectional_section(AVOID_CALL) is None


class TestDirectionLexicon:
    def test_pure_risk_caution_is_neutral_not_bearish(self):
        assert _detect_direction(PURE_CAUTION) == "neutral"

    def test_avoid_call_stays_bearish(self):
        assert _detect_direction(AVOID_CALL) == "bearish"

    def test_reduce_call_stays_bearish(self):
        assert _detect_direction(REDUCE_CALL) == "bearish"

    def test_bullish_stays_bullish(self):
        assert _detect_direction(BULLISH_CALL) == "bullish"


def _env(text: str) -> ContentEnvelope:
    qc = QualityCard(
        readability_score=0.9, semantic_completeness_score=0.8,
        financial_relevance_score=0.9, entity_resolution_score=0.8,
        temporal_resolution_score=0.7, evidence_traceability_score=0.8,
    )
    return ContentEnvelope(
        envelope_id="f3_guard", source_type="feishu_doc", quality_card=qc,
        blocks=[ContentBlock(block_type="paragraph", text=text, order=0, quality_card=qc)],
    )


class TestExtractorEndToEnd:
    def test_monitoring_table_never_extracted_as_bearish(self):
        res = RuleBasedIntentExtractor().extract(_env(SEMI_MONITOR))
        for i in res.intents:
            assert i.direction != "bearish", (i.target_name, i.direction)
            # a resolved-entity intent from a tracking table is neutral/watch
            if i.target_name != "unknown":
                assert i.direction == "neutral"
                assert i.actionability == "watch"
                assert "nondirectional_monitoring" in i.ambiguity_flags

    def test_allocation_framework_never_extracted_as_bearish(self):
        res = RuleBasedIntentExtractor().extract(_env(ALLOC_FRAMEWORK))
        for i in res.intents:
            assert i.direction != "bearish", (i.target_name, i.direction)

    def test_genuine_reduce_still_produces_bearish(self):
        res = RuleBasedIntentExtractor().extract(_env("半导体 " + REDUCE_CALL))
        dirs = {i.direction for i in res.intents}
        assert "bearish" in dirs, dirs
