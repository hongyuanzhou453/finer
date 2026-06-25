"""Intent Extraction — Rule-based (baseline) + LLM-based extractor.

F3 Intent Extraction layer. Two extractor implementations:

1. RuleBasedIntentExtractor (baseline/fallback):
   Keyword matching against BULLISH/BEARISH/EXPLICIT_ACTION keyword lists.
   Fast, deterministic, no external API dependency. Used as fallback when
   LLM is unavailable.

2. LLMIntentExtractor (primary):
   Uses an LLM callable (any function matching the Callable signature) to
   extract NormalizedInvestmentIntent with rich semantic understanding.
   Supports nuance: opinion vs explicit_action, hold vs add, temporal
   ambiguity, compound signals, sentiment as auxiliary dimension.

Both extractors share the same output type: IntentExtractionResult containing
List[NormalizedInvestmentIntent]. Neither generates TradeAction, position_size,
stop_loss, take_profit, or target_price.
"""

from __future__ import annotations

import json
import re
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.evidence import EvidenceSpan
from finer.entity_registry import ENTITY_REGISTRY, EntityEntry
from finer.llm.router import ModelRouter
from finer.prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)

# Map registry entity_type to intent target_type
_REGISTRY_TYPE_TO_TARGET_TYPE = {
    "ticker": "stock",
    "index": "index",
    "crypto": "crypto",
    "sector": "sector",
}


# =============================================================================
# Shared Result Container
# =============================================================================

class IntentExtractionResult(BaseModel):
    """Result container for intent extraction from a ContentEnvelope.

    Shared by both RuleBasedIntentExtractor and LLMIntentExtractor.
    """

    model_config = ConfigDict(strict=True)

    envelope_id: str = Field(
        ..., description="ID of the source ContentEnvelope"
    )
    intents: List[NormalizedInvestmentIntent] = Field(
        default_factory=list, description="List of extracted intents"
    )
    evidence_spans: List[EvidenceSpan] = Field(
        default_factory=list, description="Evidence spans for traceability"
    )
    extraction_timestamp: datetime = Field(
        default_factory=datetime.now, description="When extraction was performed"
    )
    extractor_version: str = Field(
        "minimal_v1", description="Version identifier for this extractor"
    )
    processing_notes: List[str] = Field(
        default_factory=list, description="Notes or warnings from extraction process"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional extensible metadata"
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode='json')

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntentExtractionResult:
        if isinstance(data.get("extraction_timestamp"), str):
            data["extraction_timestamp"] = datetime.fromisoformat(
                data["extraction_timestamp"].replace("Z", "+00:00")
            )
        return cls.model_validate(data)


# =============================================================================
# Keyword patterns (shared, used by RuleBasedIntentExtractor)
# =============================================================================

BULLISH_KEYWORDS = [
    "看好", "受益", "机会", "加仓", "抄底", "持有", "买入",
    "增持", "推荐", "优质", "低估", "值得", "翻倍", "扭亏为盈",
    "性价比", "入场", "埋伏", "买不了吃亏",
]

BEARISH_KEYWORDS = [
    "看空", "减仓", "退出", "不及预期", "风险", "回避",
    "卖出", "清仓", "减持", "高估", "谨慎", "亏损", "走弱",
    "落后", "透支", "回落", "下跌", "卖就卖",
]

EXPLICIT_ACTION_KEYWORDS = [
    "加仓", "抄底", "买入", "卖出", "减仓", "清仓", "退出",
    "增持", "减持", "建仓", "入场",
]

HOLD_ACTION_KEYWORDS = [
    "持有", "继续拿", "拿着", "不动", "继续持有",
]

OPINION_WATCH_KEYWORDS = [
    "看好", "关注", "观察", "留意", "值得", "埋伏",
]

SKIP_PATTERNS = [
    re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}$'),
    re.compile(r'^猫大人FIRE\s+\d{4}年'),
    re.compile(r'^>\s*\*'),
    re.compile(r'^Q:\s*'),
]


# =============================================================================
# Helper functions
# =============================================================================

def _is_skip_block(text: str) -> bool:
    """Check if a block should be skipped (metadata/timestamp, not analysis)."""
    text = text.strip()
    if not text or len(text) < 4:
        return True
    if re.match(r'^Q[:：]\s*', text) and "\n" not in text:
        return True
    for pattern in SKIP_PATTERNS:
        if pattern.pattern == r'^Q:\s*':
            continue
        if pattern.match(text):
            return True
    return False


# Prefer concrete tradeable instruments over broad index/sector/macro references
# when several known entities co-occur, so a specific stock pick is not shadowed
# by a market index ("上证") or theme ("光模块") that was only mentioned as backdrop.
_ENTITY_TYPE_PRIORITY = {
    "ticker": 0,
    "etf": 0,
    "crypto": 1,
    "commodity": 1,
    "sector": 2,
    "index": 3,
    "macro": 4,
}


def _find_entities_in_text(text: str) -> List[Tuple[str, EntityEntry]]:
    """Find all known entity names present in text.

    Ordered by (type priority, name length) so callers taking ``found[0]`` get
    the most specific tradeable entity rather than whichever index/theme happened
    to match. Longer names still win within the same type (more specific match).
    """
    found = []
    for name, entry in ENTITY_REGISTRY.items():
        if name in text:
            found.append((name, entry))
    found.sort(key=lambda x: (_ENTITY_TYPE_PRIORITY.get(x[1][2], 5), -len(x[0])))
    return found


def _extract_entity_from_heading(heading_text: str) -> Optional[Tuple[str, EntityEntry]]:
    """Extract entity from a section heading like '## 理想汽车分析'."""
    cleaned = re.sub(r'^#{1,6}\s+', '', heading_text).strip()
    entry = ENTITY_REGISTRY.get(cleaned)
    if entry:
        return cleaned, entry
    found = _find_entities_in_text(cleaned)
    if found:
        return found[0]
    return None


def _detect_direction(text: str) -> Optional[str]:
    """Detect sentiment direction from text."""
    bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    if bullish_count > bearish_count:
        return "bullish"
    elif bearish_count > bullish_count:
        return "bearish"
    elif bullish_count > 0 and bullish_count == bearish_count:
        return "mixed"
    return None


def _detect_actionability(text: str) -> Tuple[str, str]:
    """Detect actionability and position delta hint from text."""
    for kw in EXPLICIT_ACTION_KEYWORDS:
        if kw in text:
            if kw in ["加仓", "抄底", "买入", "增持", "建仓", "入场"]:
                return "explicit_action", "add"
            elif kw in ["卖出", "减仓", "清仓", "退出", "减持"]:
                return "explicit_action", "reduce"

    for kw in HOLD_ACTION_KEYWORDS:
        if kw in text:
            return "explicit_action", "hold"

    for kw in OPINION_WATCH_KEYWORDS:
        if kw in text:
            if kw == "看好":
                return "opinion", "none"
            else:
                return "watch", "none"

    if "卖就卖" in text or "该卖" in text:
        return "opinion", "exit"

    return "opinion", "none"


def _create_evidence_span(
    block_id: str,
    text: str,
    start: int,
    end: int,
    span_type: str,
    confidence: float = 0.8,
) -> EvidenceSpan:
    """Create an EvidenceSpan from text position."""
    return EvidenceSpan(
        block_id=block_id,
        char_start=start,
        char_end=end,
        text=text[start:end],
        confidence=confidence,
        span_type=span_type,
    )


def _find_keyword_evidence(
    text: str, block_id: str, span_type: str = "intent_keyword"
) -> List[EvidenceSpan]:
    """Find keyword occurrences in text and create evidence spans."""
    spans = []
    all_keywords = BULLISH_KEYWORDS + BEARISH_KEYWORDS
    seen_positions = set()

    for keyword in sorted(all_keywords, key=len, reverse=True):
        start = 0
        while True:
            pos = text.find(keyword, start)
            if pos == -1:
                break
            if (pos, pos + len(keyword)) not in seen_positions:
                spans.append(_create_evidence_span(
                    block_id, text, pos, pos + len(keyword), span_type
                ))
                seen_positions.add((pos, pos + len(keyword)))
            start = pos + 1

    return spans


def _group_into_sections(blocks: List[ContentBlock]) -> List[Dict[str, Any]]:
    """Group blocks into sections based on H2+ headings."""
    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None

    for block in blocks:
        if block.block_type == "heading":
            text = block.text.strip()
            if re.match(r'^#{2,}\s+', text):
                current_section = {
                    "heading": text,
                    "heading_block": block,
                    "blocks": [],
                    "entity": _extract_entity_from_heading(text),
                }
                sections.append(current_section)
                continue

        if current_section is not None:
            current_section["blocks"].append(block)

    return sections


# ── Entity resolution (LLM output → NormalizedInvestmentIntent helper) ──

def _resolve_entity_from_llm_output(
    target_name: str,
    target_symbol: Optional[str],
    llm_target_type: str,
    market: Optional[str],
    combined_text: str,
    entity_anchors: Optional[List[Any]] = None,
) -> Tuple[str, Optional[str], str, Optional[str]]:
    """Resolve entity info: prefer LLM output, fall back to registry + anchors.

    Returns (target_name, target_symbol, target_type, market).
    """
    final_name = target_name or "unknown"
    final_symbol = target_symbol
    final_type = llm_target_type
    final_market = market

    # If LLM gave a name, try to look it up in registry for symbol/market
    if final_name != "unknown" and not final_symbol:
        entry = ENTITY_REGISTRY.get(final_name)
        if entry:
            final_symbol = entry[0]
            final_market = final_market or entry[1]
            final_type = _REGISTRY_TYPE_TO_TARGET_TYPE.get(entry[2], final_type or "stock")

    # Fallback to text search in registry
    if final_name == "unknown" or not final_symbol:
        found = _find_entities_in_text(combined_text)
        if found:
            name, (ticker, mkt, etype) = found[0]
            final_name = name
            final_symbol = ticker
            final_type = _REGISTRY_TYPE_TO_TARGET_TYPE.get(etype, "stock")
            final_market = final_market or mkt

    # Fallback to entity_anchors
    if final_name == "unknown" and entity_anchors:
        anchor = entity_anchors[0]
        final_name = anchor.resolved_name or anchor.raw_text or "unknown"
        final_symbol = final_symbol or anchor.resolved_symbol
        final_market = final_market or getattr(anchor, 'market', None)

    # Normalize target_type
    if final_type not in ("stock", "sector", "index", "crypto", "commodity", "macro", "unknown"):
        final_type = "stock"

    return final_name, final_symbol, final_type, final_market


# =============================================================================
# RuleBasedIntentExtractor (Baseline / Fallback)
# =============================================================================

class RuleBasedIntentExtractor:
    """Rule-based intent extractor using keyword matching.

    This is the BASELINE extractor. It uses hardcoded keyword lists
    (BULLISH_KEYWORDS, BEARISH_KEYWORDS, etc.) and simple heuristics.
    No LLM calls. Fast, deterministic, zero external API dependency.

    Used as fallback when LLM is unavailable. For production-quality
    extraction with semantic nuance (opinion vs action, hold vs add,
    compound signals), use LLMIntentExtractor.
    """

    VERSION = "rule_based_v1"

    def extract(self, envelope: ContentEnvelope) -> IntentExtractionResult:
        """Extract intents using rule-based keyword matching.

        Groups blocks by section headings, identifies entities via
        entity_registry, and creates one intent per section that has
        investment signals.
        """
        return _rule_based_extract_impl(envelope, self.VERSION)


def _rule_based_extract_impl(
    envelope: ContentEnvelope,
    extractor_version: str = "rule_based_v1",
) -> IntentExtractionResult:
    """Internal implementation of rule-based extraction.

    Extracted as a separate function so it can be called both by
    the class and the backward-compatible module-level function.
    """
    intents: List[NormalizedInvestmentIntent] = []
    all_evidence_spans: List[EvidenceSpan] = []
    processing_notes: List[str] = []

    sections = _group_into_sections(envelope.blocks)

    # Fallback: if no H2 sections found, process blocks individually
    if not sections:
        sections = [
            {
                "heading": f"block_{block.block_id[:8]}",
                "heading_block": None,
                "blocks": [block],
                "entity": None,
            }
            for block in envelope.blocks
        ]

    for section in sections:
        content_blocks = [b for b in section["blocks"] if not _is_skip_block(b.text)]
        if not content_blocks:
            continue

        # Determine entity
        target_name = "unknown"
        target_symbol = None
        target_type: str = "unknown"
        market = None

        if section["entity"]:
            name, (ticker, mkt, etype) = section["entity"]
            target_name = name
            target_symbol = ticker
            target_type = _REGISTRY_TYPE_TO_TARGET_TYPE.get(etype, "stock")
            market = mkt
        else:
            combined = " ".join(b.text for b in content_blocks)
            found = _find_entities_in_text(combined)
            if found:
                name, (ticker, mkt, etype) = found[0]
                target_name = name
                target_symbol = ticker
                target_type = _REGISTRY_TYPE_TO_TARGET_TYPE.get(etype, "stock")
                market = mkt
            elif hasattr(envelope, 'entity_anchors') and envelope.entity_anchors:
                anchor = envelope.entity_anchors[0]
                target_name = anchor.resolved_name or anchor.raw_text or "unknown"
                target_symbol = anchor.resolved_symbol
                target_type = anchor.entity_type if hasattr(anchor, 'entity_type') else "stock"
                market = getattr(anchor, 'market', None)

        combined_text = " ".join(b.text for b in content_blocks)

        direction = _detect_direction(combined_text)
        if not direction:
            processing_notes.append(
                f"Section '{section['heading']}': no clear direction"
            )
            continue

        actionability, position_hint = _detect_actionability(combined_text)

        # Build evidence spans
        section_evidence: List[EvidenceSpan] = []
        block_ids: List[str] = []

        for block in content_blocks:
            spans = _find_keyword_evidence(block.text, block.block_id)
            if spans:
                section_evidence.extend(spans)
                if block.block_id not in block_ids:
                    block_ids.append(block.block_id)

        if not section_evidence:
            processing_notes.append(
                f"Section '{section['heading']}': direction detected but no keyword evidence"
            )
            continue

        # Ambiguity flags
        ambiguity_flags: List[str] = []
        if target_name == "unknown":
            ambiguity_flags.append("unknown_target")
        if any(kw in combined_text for kw in ["风险高于价值", "回落的风险", "透支"]):
            ambiguity_flags.append("risk_warning")
        if "等跌到" in combined_text or "以下再" in combined_text:
            ambiguity_flags.append("wait_for_better_entry")
        if "修复空间" in combined_text and "有限" in combined_text:
            ambiguity_flags.append("limited_upside")
        # Hold + add compound detection (rule-based approximation)
        has_hold = any(kw in combined_text for kw in HOLD_ACTION_KEYWORDS)
        has_add = any(kw in combined_text for kw in ["加仓", "买入", "增持", "入场"])
        if has_hold and has_add:
            ambiguity_flags.append("hold_and_add_compound")
        # Relative time detection
        if any(kw in combined_text for kw in ["上周", "这周", "下周", "上个月", "下个月", "短期"]):
            if "relative_time_unresolved" not in ambiguity_flags:
                ambiguity_flags.append("relative_time_unresolved")

        # Conviction
        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in combined_text)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in combined_text)
        total_signals = bullish_count + bearish_count

        if total_signals >= 5:
            conviction = 0.75
        elif total_signals >= 3:
            conviction = 0.65
        else:
            conviction = 0.55

        # Confidence
        confidence = 0.7
        if target_symbol:
            confidence = 0.85
        elif target_type in ("sector", "index"):
            confidence = 0.75
        if ambiguity_flags:
            confidence -= 0.05 * len(ambiguity_flags)
        confidence = max(0.35, min(0.95, confidence))

        # Time horizon
        time_horizon = "unknown"
        if any(kw in combined_text for kw in ["短期", "日内", "短线"]):
            time_horizon = "short_term"
        elif any(kw in combined_text for kw in ["长期", "年度"]):
            time_horizon = "long_term"
        elif any(kw in combined_text for kw in ["2026年", "全年", "季度"]):
            time_horizon = "medium_term"

        intent = NormalizedInvestmentIntent(
            envelope_id=envelope.envelope_id,
            block_ids=block_ids,
            creator_id=envelope.creator_id,
            target_type=target_type,  # type: ignore[arg-type]
            target_name=target_name,
            target_symbol=target_symbol,
            market=market,
            direction=direction,  # type: ignore[arg-type]
            actionability=actionability,  # type: ignore[arg-type]
            position_delta_hint=position_hint,  # type: ignore[arg-type]
            conviction=conviction,
            confidence=confidence,
            time_horizon_hint=time_horizon,  # type: ignore[arg-type]
            evidence_span_ids=[span.evidence_span_id for span in section_evidence],
            ambiguity_flags=ambiguity_flags,
        )

        intents.append(intent)
        all_evidence_spans.extend(section_evidence)

    result = IntentExtractionResult(
        envelope_id=envelope.envelope_id,
        intents=intents,
        evidence_spans=all_evidence_spans,
        extractor_version=extractor_version,
        processing_notes=processing_notes,
    )

    return result


# =============================================================================
# LLMIntentExtractor
# =============================================================================

class LLMIntentExtractor:
    """LLM-based intent extractor using ModelRouter + PromptRegistry.

    Uses dependency-injected ModelRouter for LLM calls and PromptRegistry
    for Jinja2-based prompt rendering.

    The LLM is prompted to output:
    - direction: bullish/bearish/neutral/mixed/unknown
    - actionability: opinion/watch/explicit_action/review_required
    - position_delta_hint: open/add/reduce/hold/exit/none/unknown
    - conviction: 0.0-1.0 float

    The LLM MUST NOT output:
    - position_size_pct, stop_loss, take_profit, target_price (F4 territory)
    - TradeAction (F5 territory)

    Args:
        router: ModelRouter instance for LLM calls with automatic fallback.
        prompt_registry: PromptRegistry for Jinja2 template rendering.
        extractor_version: Version string for traceability.
    """

    VERSION = "llm_v1"

    def __init__(
        self,
        router: ModelRouter,
        prompt_registry: PromptRegistry,
        extractor_version: str = "llm_v1",
        temperature: float = 0.3,
    ):
        self._router = router
        self._prompt_registry = prompt_registry
        self._version = extractor_version
        self._temperature = temperature

    def extract(self, envelope: ContentEnvelope) -> IntentExtractionResult:
        """Extract intents from a ContentEnvelope using the LLM.

        Args:
            envelope: F2-anchored ContentEnvelope with blocks.

        Returns:
            IntentExtractionResult containing NormalizedInvestmentIntent list.
            Returns empty result on LLM failure.
        """
        # Build combined text from non-skip blocks
        content_blocks = [
            b for b in envelope.blocks if not _is_skip_block(b.text)
        ]
        combined_text = "\n\n".join(b.text for b in content_blocks)

        if not combined_text.strip():
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                extractor_version=self._version,
                processing_notes=["No meaningful content text found in envelope"],
            )

        # Find known entities for context
        known_entities = [name for name, _ in _find_entities_in_text(combined_text)]

        # Build prompt via PromptRegistry (Jinja2 templates)
        known_entities_str = "\n".join(f"  - {e}" for e in known_entities) or "  (none detected)"

        system_prompt = self._prompt_registry.render("f3_intent_extraction/system")
        user_prompt = self._prompt_registry.render(
            "f3_intent_extraction/user",
            content_text=combined_text,
            creator_name=envelope.creator_name or "unknown",
            creator_id=envelope.creator_id or "unknown",
            source_type=envelope.source_type or "unknown",
            published_at=envelope.published_at.isoformat() if envelope.published_at else "unknown",
            known_entities=known_entities_str,
        )

        # Call LLM via ModelRouter
        try:
            llm_output = self._router.call_json(
                user_prompt,
                system_prompt=system_prompt,
                task_type="text",
                temperature=self._temperature,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                extractor_version=self._version,
                processing_notes=[f"LLM call exception: {e}"],
            )

        if llm_output is None:
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                extractor_version=self._version,
                processing_notes=["LLM returned None (likely API key missing or quota exhausted)"],
            )

        # Parse LLM output
        return self._parse_llm_output(
            llm_output, envelope, combined_text, content_blocks
        )

    def _parse_llm_output(
        self,
        llm_output: dict,
        envelope: ContentEnvelope,
        combined_text: str,
        content_blocks: List[ContentBlock],
    ) -> IntentExtractionResult:
        """Parse LLM dict output into IntentExtractionResult.

        Validates each intent against the Pydantic schema. Rejects intents
        that contain forbidden fields (position_size, stop_loss, take_profit,
        target_price). JSON parsing and code fence stripping are handled by
        ModelRouter.call_json() upstream.
        """
        processing_notes: List[str] = []
        intents: List[NormalizedInvestmentIntent] = []
        evidence_spans: List[EvidenceSpan] = []

        # Collect overall notes
        if isinstance(llm_output.get("overall_notes"), list):
            processing_notes.extend(llm_output["overall_notes"])

        raw_intents = llm_output.get("intents", [])
        if not isinstance(raw_intents, list):
            processing_notes.append("LLM output 'intents' is not a list")
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                extractor_version=self._version,
                processing_notes=processing_notes,
            )

        if len(raw_intents) == 0:
            processing_notes.append("LLM found no investment intents in content")
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                extractor_version=self._version,
                processing_notes=processing_notes,
            )

        # Block IDs for evidence tracing
        block_ids = [b.block_id for b in content_blocks]

        for i, raw in enumerate(raw_intents):
            if not isinstance(raw, dict):
                processing_notes.append(f"Intent {i}: not a dict, skipping")
                continue

            # Reject if forbidden fields are present
            forbidden_fields = ["position_size_pct", "position_size", "stop_loss",
                                "take_profit", "target_price", "target_price_low",
                                "target_price_high", "trigger_condition"]
            has_forbidden = any(f in raw for f in forbidden_fields)
            if has_forbidden:
                found = [f for f in forbidden_fields if f in raw]
                processing_notes.append(
                    f"Intent {i}: rejected — contains forbidden fields: {found}"
                )
                continue

            try:
                target_name = str(raw.get("target_name", "unknown"))
                target_symbol = raw.get("target_symbol")
                llm_target_type = raw.get("target_type", "unknown")
                llm_market = raw.get("market")

                # Resolve entity with registry fallback
                final_name, final_symbol, final_type, final_market = \
                    _resolve_entity_from_llm_output(
                        target_name, target_symbol, llm_target_type, llm_market,
                        combined_text,
                        entity_anchors=getattr(envelope, 'entity_anchors', None),
                    )

                direction = str(raw.get("direction", "unknown"))
                actionability = str(raw.get("actionability", "opinion"))
                position_hint = str(raw.get("position_delta_hint", "none"))
                conviction = float(raw.get("conviction", 0.5))
                confidence = float(raw.get("confidence", 0.6))
                sentiment_score = raw.get("sentiment_score")
                time_horizon = str(raw.get("time_horizon", "unknown"))
                ambiguity_notes = raw.get("ambiguity_notes", [])
                if isinstance(ambiguity_notes, list):
                    ambiguity_notes = [str(n) for n in ambiguity_notes]
                else:
                    ambiguity_notes = []

                intent_processing = raw.get("processing_notes", [])
                if isinstance(intent_processing, list):
                    intent_processing = [str(n) for n in intent_processing]
                else:
                    intent_processing = []

                # Evidence text from LLM (fallback: first block text snippet)
                evidence_text = str(raw.get("evidence_text", ""))

                # Build evidence spans from LLM-provided evidence text
                intent_evidence_spans: List[EvidenceSpan] = []
                if evidence_text:
                    for block in content_blocks:
                        pos = block.text.find(evidence_text)
                        if pos >= 0:
                            span = _create_evidence_span(
                                block.block_id, block.text, pos,
                                pos + len(evidence_text),
                                span_type="intent_keyword",
                                confidence=confidence,
                            )
                            intent_evidence_spans.append(span)
                            break

                # Fallback: if no exact match, use block-level evidence
                # from blocks that were selected by the LLM (block_ids)
                if not intent_evidence_spans and block_ids:
                    for block in content_blocks:
                        if block.block_id in block_ids:
                            span = _create_evidence_span(
                                block.block_id, block.text, 0,
                                len(block.text),
                                span_type="block_level",
                                confidence=confidence * 0.7,  # lower confidence for fallback
                            )
                            intent_evidence_spans.append(span)

                # Clamp values
                conviction = max(0.0, min(1.0, conviction))
                confidence = max(0.0, min(1.0, confidence))

                if sentiment_score is not None:
                    sentiment_score = float(sentiment_score)
                    sentiment_score = max(-1.0, min(1.0, sentiment_score))

                # Validate enum values
                valid_directions = {"bullish", "bearish", "neutral", "mixed", "unknown"}
                valid_actionability = {"opinion", "watch", "explicit_action", "review_required"}
                valid_position_hints = {"open", "add", "reduce", "hold", "exit", "none", "unknown"}
                valid_time_horizons = {"intraday", "short_term", "medium_term", "long_term", "unknown"}

                if direction not in valid_directions:
                    direction = "unknown"
                if actionability not in valid_actionability:
                    actionability = "review_required"
                if position_hint not in valid_position_hints:
                    position_hint = "unknown"
                if time_horizon not in valid_time_horizons:
                    time_horizon = "unknown"

                intent = NormalizedInvestmentIntent(
                    envelope_id=envelope.envelope_id,
                    block_ids=block_ids,
                    creator_id=envelope.creator_id,
                    target_type=final_type,  # type: ignore[arg-type]
                    target_name=final_name,
                    target_symbol=final_symbol,
                    market=final_market,
                    direction=direction,  # type: ignore[arg-type]
                    actionability=actionability,  # type: ignore[arg-type]
                    position_delta_hint=position_hint,  # type: ignore[arg-type]
                    conviction=conviction,
                    confidence=confidence,
                    sentiment_score=sentiment_score,
                    time_horizon_hint=time_horizon,  # type: ignore[arg-type]
                    evidence_span_ids=[s.evidence_span_id for s in intent_evidence_spans],
                    ambiguity_flags=ambiguity_notes,
                )

                intents.append(intent)
                evidence_spans.extend(intent_evidence_spans)

            except Exception as e:
                processing_notes.append(f"Intent {i}: failed to construct — {e}")
                continue

        return IntentExtractionResult(
            envelope_id=envelope.envelope_id,
            intents=intents,
            evidence_spans=evidence_spans,
            extractor_version=self._version,
            processing_notes=processing_notes,
        )


# =============================================================================
# Backward-compatible module-level function
# =============================================================================

def extract_intents_from_envelope(
    envelope: ContentEnvelope,
) -> IntentExtractionResult:
    """Extract investment intents from a ContentEnvelope.

    Uses the rule-based baseline extractor. For LLM-based extraction,
    use LLMIntentExtractor directly.

    This function is maintained for backward compatibility with existing
    callers that import ``extract_intents_from_envelope`` from this module.
    """
    extractor = RuleBasedIntentExtractor()
    return extractor.extract(envelope)
