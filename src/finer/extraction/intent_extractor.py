"""Intent Extraction — Minimal V1 rule-based extractor.

Extracts NormalizedInvestmentIntent from ContentEnvelope using keyword
matching and entity registry lookups. Groups blocks by section headings
to produce one intent per topic section.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.evidence import EvidenceSpan
from finer.entity_registry import ENTITY_REGISTRY, EntityEntry

# Map registry entity_type to intent target_type
_REGISTRY_TYPE_TO_TARGET_TYPE = {
    "ticker": "stock",
    "index": "index",
    "crypto": "crypto",
    "sector": "sector",
}


class IntentExtractionResult(BaseModel):
    """Result container for intent extraction from a ContentEnvelope."""

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
# Keyword patterns
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

# Blocks that don't contain investment analysis (metadata, timestamps, Q messages)
SKIP_PATTERNS = [
    re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}$'),  # timestamp line
    re.compile(r'^猫大人FIRE\s+\d{4}年'),  # chat metadata
    re.compile(r'^>\s*\*'),  # markdown metadata lines
    re.compile(r'^Q:\s*'),  # pure question lines (not answers)
]


def _is_skip_block(text: str) -> bool:
    """Check if a block should be skipped (metadata/timestamp, not analysis)."""
    text = text.strip()
    if not text or len(text) < 4:
        return True
    for pattern in SKIP_PATTERNS:
        if pattern.match(text):
            return True
    return False


# =============================================================================
# Entity resolution
# =============================================================================

def _find_entities_in_text(text: str) -> List[Tuple[str, EntityEntry]]:
    """Find all known entity names present in text.

    Returns list of (matched_name, (ticker, market, entity_type)) sorted by
    name length descending (longest match first — more specific).
    """
    found = []
    for name, entry in ENTITY_REGISTRY.items():
        if name in text:
            found.append((name, entry))
    # Sort by match length descending (longer = more specific)
    found.sort(key=lambda x: len(x[0]), reverse=True)
    return found


def _extract_entity_from_heading(heading_text: str) -> Optional[Tuple[str, EntityEntry]]:
    """Extract entity from a section heading like '## 理想汽车分析'.

    Strips markdown heading markers and common suffixes, then looks up
    in entity registry.
    """
    # Strip heading markers
    cleaned = re.sub(r'^#{1,6}\s+', '', heading_text).strip()

    # Try direct lookup first
    entry = ENTITY_REGISTRY.get(cleaned)
    if entry:
        return cleaned, entry

    # Find known entity names within the heading
    found = _find_entities_in_text(cleaned)
    if found:
        return found[0]  # (name, entry) for longest match

    return None


# =============================================================================
# Direction and actionability detection
# =============================================================================

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

    # Check for "卖就卖" (exit signal within bullish context)
    if "卖就卖" in text or "该卖" in text:
        return "opinion", "exit"

    return "opinion", "none"


# =============================================================================
# Evidence span helpers
# =============================================================================

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


# =============================================================================
# Section grouping
# =============================================================================

def _group_into_sections(blocks: List[ContentBlock]) -> List[Dict[str, Any]]:
    """Group blocks into sections based on H2+ headings.

    Returns list of dicts with keys: heading, heading_block, blocks, entity.
    The first section (before any H2) uses the H1 title as context.
    """
    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None

    for block in blocks:
        if block.block_type == "heading":
            text = block.text.strip()
            # H2+ creates a new section; H1 is a title
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


# =============================================================================
# Main extraction
# =============================================================================

def extract_intents_from_envelope(
    envelope: ContentEnvelope,
) -> IntentExtractionResult:
    """Extract investment intents from a ContentEnvelope.

    Groups blocks by section headings, identifies entities via entity_registry,
    and creates one intent per section that has investment signals.

    Constraints:
        - Each intent has at least one evidence span
        - Does not generate position ratio or target price
        - Uses entity_registry for ticker/type/market resolution
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
        # Filter out timestamp/metadata blocks
        content_blocks = [b for b in section["blocks"] if not _is_skip_block(b.text)]

        if not content_blocks:
            continue

        # Determine entity: from heading → body text → entity_anchors
        target_name = "unknown"
        target_symbol = None
        target_type = "unknown"
        market = None

        if section["entity"]:
            name, (ticker, mkt, etype) = section["entity"]
            target_name = name
            target_symbol = ticker
            target_type = _REGISTRY_TYPE_TO_TARGET_TYPE.get(etype, "stock")
            market = mkt
        else:
            # Search body text for known entities
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

        # Combine text for direction/actionability analysis
        combined_text = " ".join(b.text for b in content_blocks)

        direction = _detect_direction(combined_text)
        if not direction:
            processing_notes.append(
                f"Section '{section['heading']}': no clear direction"
            )
            continue

        actionability, position_hint = _detect_actionability(combined_text)

        # Build evidence spans from content blocks
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

        # Build ambiguity flags
        ambiguity_flags: List[str] = []
        if target_name == "unknown":
            ambiguity_flags.append("unknown_target")

        # Detect risk warnings
        if any(kw in combined_text for kw in ["风险高于价值", "回落的风险", "透支"]):
            ambiguity_flags.append("risk_warning")
        if "等跌到" in combined_text or "以下再" in combined_text:
            ambiguity_flags.append("wait_for_better_entry")
        if "修复空间" in combined_text and "有限" in combined_text:
            ambiguity_flags.append("limited_upside")

        # Estimate conviction from keyword density and specificity
        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in combined_text)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in combined_text)
        total_signals = bullish_count + bearish_count

        if total_signals >= 5:
            conviction = 0.75
        elif total_signals >= 3:
            conviction = 0.65
        else:
            conviction = 0.55

        # Confidence based on entity resolution and evidence
        confidence = 0.7
        if target_symbol:
            confidence = 0.85
        elif target_type in ("sector", "index"):
            confidence = 0.75
        if ambiguity_flags:
            confidence -= 0.05 * len(ambiguity_flags)
        confidence = max(0.35, min(0.95, confidence))

        # Time horizon hints
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
            target_type=target_type,
            target_name=target_name,
            target_symbol=target_symbol,
            market=market,
            direction=direction,
            actionability=actionability,
            position_delta_hint=position_hint,
            conviction=conviction,
            confidence=confidence,
            time_horizon_hint=time_horizon,
            evidence_span_ids=[span.evidence_span_id for span in section_evidence],
            ambiguity_flags=ambiguity_flags,
        )

        intents.append(intent)
        all_evidence_spans.extend(section_evidence)

    result = IntentExtractionResult(
        envelope_id=envelope.envelope_id,
        intents=intents,
        evidence_spans=all_evidence_spans,
        processing_notes=processing_notes,
    )

    return result
