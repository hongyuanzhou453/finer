"""Topic Assembler — F1.5 Deterministic Topic Grouping.

Groups ContentBlocks into TopicBlocks using keyword/entity matching rules.
No LLM calls — pure rule-based assembly.

Algorithm:
1. Scan each ContentBlock text for topic keywords
2. Assign each block to its highest-confidence matching topic
3. Merge consecutive blocks with the same topic into one TopicBlock
4. Unmatched blocks go to unassigned_block_ids

Confidence levels:
- 1.0  — exact ticker/stock code match (e.g. 9992.HK)
- 0.95 — unambiguous company name (e.g. 泡泡玛特, 宁德时代)
- 0.85 — unambiguous person/institution name (e.g. 巴菲特, 伯克希尔)
- 0.75 — shorter keyword that could be substring (e.g. 卫星, 老铺)
- 0.7  — generic category keyword (e.g. 新能源, NEV, 价值投资)

F1.5 Contract:
- Does NOT produce direction, actionability, position_delta_hint, or TradeAction
- Does NOT discard any original ContentBlock
- Preserves source_block_ids for traceability
- raw_text is assembled from source block text, never fabricated
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from finer.schemas.content_envelope import ContentEnvelope, ContentBlock
from finer.schemas.topic_block import TopicAssemblyResult, TopicBlock, TopicType


# =============================================================================
# Topic Rule Definitions
# =============================================================================

@dataclass(frozen=True)
class TopicRule:
    """A keyword-based rule for matching blocks to a topic.

    Attributes:
        topic_key: Canonical topic identifier (used for grouping).
        topic_title: Human-readable topic name.
        topic_type: TopicBlock classification.
        keywords: List of keywords/patterns to match (case-insensitive).
        primary_entity_ids: Entity IDs to attach to the TopicBlock.
        secondary_entity_ids: Secondary entity IDs for the TopicBlock.
        confidence: Base confidence when this rule matches.
        ambiguity_flags: Default ambiguity flags when matched.
    """

    topic_key: str
    topic_title: str
    topic_type: TopicType
    keywords: List[str]
    primary_entity_ids: List[str]
    confidence: float
    secondary_entity_ids: List[str] = field(default_factory=list)
    ambiguity_flags: List[str] = field(default_factory=list)


# The rule set — order matters for tie-breaking (first match wins)
TOPIC_RULES: List[TopicRule] = [
    # ── 泡泡玛特 ──────────────────────────────────────────────────
    TopicRule(
        topic_key="popmart",
        topic_title="泡泡玛特",
        topic_type=TopicType.SINGLE_STOCK,
        keywords=["泡泡玛特", "POP MART", "POP MART", "9992.HK", "9992HK"],
        primary_entity_ids=["泡泡玛特", "9992.HK"],
        confidence=0.95,
    ),
    # ── 巴菲特 ──────────────────────────────────────────────────
    TopicRule(
        topic_key="buffett",
        topic_title="巴菲特/价值投资",
        topic_type=TopicType.INVESTMENT_PHILOSOPHY,
        keywords=["巴菲特", "Buffett", "伯克希尔", "股东信", "价值投资"],
        primary_entity_ids=["巴菲特", "伯克希尔"],
        confidence=0.85,
        ambiguity_flags=["generic_keywords_only"] if False else [],
    ),
    # ── 老铺黄金 ──────────────────────────────────────────────────
    TopicRule(
        topic_key="laopu_gold",
        topic_title="老铺黄金",
        topic_type=TopicType.SINGLE_STOCK,
        keywords=["老铺黄金", "老铺"],
        primary_entity_ids=["老铺黄金"],
        confidence=0.75,
        ambiguity_flags=["short_keyword"],
    ),
    # ── 卫星化学 ──────────────────────────────────────────────────
    TopicRule(
        topic_key="satellite_chem",
        topic_title="卫星化学",
        topic_type=TopicType.SINGLE_STOCK,
        keywords=["卫星化学", "卫星"],
        primary_entity_ids=["卫星化学"],
        confidence=0.75,
        ambiguity_flags=["short_keyword"],
    ),
    # ── 新能源 (broad industry — must come after specific stocks) ──
    TopicRule(
        topic_key="nev",
        topic_title="新能源",
        topic_type=TopicType.INDUSTRY,
        keywords=[
            "新能源", "NEV", "蔚来", "小鹏", "理想", "理想汽车",
            "比亚迪", "CATL", "宁德时代",
        ],
        primary_entity_ids=["新能源行业"],
        secondary_entity_ids=["蔚来", "小鹏", "理想", "比亚迪", "宁德时代"],
        confidence=0.90,
    ),
]


# =============================================================================
# Keyword Matching
# =============================================================================

def _build_keyword_pattern(keywords: List[str]) -> re.Pattern[str]:
    """Build a compiled regex that matches any of the given keywords.

    Uses ASCII letter boundaries for Latin keywords: a match must not be
    preceded or followed by an ASCII letter. This prevents false positives
    inside other Latin words (e.g. "POP" inside "POPCORN") while correctly
    matching at ASCII/CJK transitions where Python's \\b fails.

    For CJK keywords, uses simple substring matching.
    """
    parts: List[str] = []
    for kw in keywords:
        escaped = re.escape(kw)
        if kw.isascii():
            # Use ASCII letter lookaround instead of \b to handle CJK context
            parts.append(rf'(?<![a-zA-Z]){escaped}(?![a-zA-Z])')
        else:
            # CJK: substring match is sufficient and more reliable
            parts.append(escaped)
    return re.compile("|".join(parts), re.IGNORECASE)


# =============================================================================
# Consecutive Block Merging
# =============================================================================

@dataclass
class _GroupRun:
    """Tracks a run of consecutive blocks assigned to the same topic."""
    topic_key: str
    rule: TopicRule
    block_indices: List[int] = field(default_factory=list)
    block_ids: List[str] = field(default_factory=list)
    texts: List[str] = field(default_factory=list)


def _merge_consecutive(
    assignments: List[Optional[TopicRule]],
    blocks: List[ContentBlock],
) -> List[_GroupRun]:
    """Merge consecutive blocks with the same topic_key into GroupRuns.

    Non-consecutive blocks with the same topic produce separate GroupRuns.
    """
    runs: List[_GroupRun] = []
    current: Optional[_GroupRun] = None

    for idx, (assignment, block) in enumerate(zip(assignments, blocks)):
        key = assignment.topic_key if assignment is not None else None

        if key is not None and current is not None and current.topic_key == key:
            # Extend current run
            current.block_indices.append(idx)
            current.block_ids.append(block.block_id)
            current.texts.append(block.text)
        elif key is not None:
            # Start new run
            current = _GroupRun(
                topic_key=key,
                rule=assignment,
                block_indices=[idx],
                block_ids=[block.block_id],
                texts=[block.text],
            )
            runs.append(current)
        else:
            # Unmatched — break current run
            current = None

    return runs


# =============================================================================
# TopicAssembler
# =============================================================================

class TopicAssembler:
    """Deterministic keyword-based topic assembler for F1.5.

    Groups ContentBlocks into TopicBlocks by scanning text for topic
    keywords. Consecutive blocks with the same topic are merged into
    a single TopicBlock.

    Usage:
        assembler = TopicAssembler()
        result = assembler.assemble(envelope)
    """

    def __init__(
        self,
        extra_rules: Optional[List[TopicRule]] = None,
        use_llm: bool = False,
        llm_adapter: Optional[object] = None,
    ) -> None:
        """Initialize the assembler.

        Args:
            extra_rules: Additional topic rules to append to the defaults.
            use_llm: Route assembly through the constrained F1.5 LLM adapter.
            llm_adapter: Optional adapter with an assemble(ContentEnvelope) method.
        """
        self.use_llm = use_llm
        self.llm_adapter = llm_adapter

        rules = list(TOPIC_RULES)
        if extra_rules:
            rules.extend(extra_rules)

        # Build compiled patterns indexed by topic_key
        self._rule_index: Dict[str, Tuple[TopicRule, re.Pattern[str]]] = {}
        for rule in rules:
            pattern = _build_keyword_pattern(rule.keywords)
            self._rule_index[rule.topic_key] = (rule, pattern)

    def _assign_block(self, text: str) -> Optional[TopicRule]:
        """Return the best-matching TopicRule for a block's text, or None."""
        best_rule: Optional[TopicRule] = None
        best_conf: float = 0.0

        for topic_key, (rule, pattern) in self._rule_index.items():
            if pattern.search(text):
                if rule.confidence > best_conf:
                    best_conf = rule.confidence
                    best_rule = rule

        return best_rule

    def assemble(self, envelope: ContentEnvelope) -> TopicAssemblyResult:
        """Assemble ContentBlocks into TopicBlocks.

        Args:
            envelope: The F1 ContentEnvelope containing ordered ContentBlocks.

        Returns:
            TopicAssemblyResult with topic_blocks and unassigned_block_ids.
        """
        if self.use_llm:
            adapter = self.llm_adapter
            if adapter is None:
                from finer.parsing.llm_topic_assembly_adapter import (
                    LLMTopicAssemblyAdapter,
                )
                adapter = LLMTopicAssemblyAdapter()
            return adapter.assemble(envelope)

        blocks = sorted(envelope.blocks, key=lambda b: b.order)

        # Step 1: Assign each block to a topic (or None)
        assignments: List[Optional[TopicRule]] = [
            self._assign_block(block.text) for block in blocks
        ]

        # Step 2: Merge consecutive blocks with same topic
        runs = _merge_consecutive(assignments, blocks)

        # Step 3: Build TopicBlocks from runs
        topic_blocks: List[TopicBlock] = []
        assigned_indices: set = set()

        for run in runs:
            assigned_indices.update(run.block_indices)

            start_idx = run.block_indices[0]
            end_idx = run.block_indices[-1]

            # Compute time range from source blocks
            start_time = None
            end_time = None
            for idx in run.block_indices:
                block = blocks[idx]
                # Use block metadata timestamps if available
                block_start = block.metadata.get("start_time")
                block_end = block.metadata.get("end_time")
                if block_start and (start_time is None or block_start < start_time):
                    start_time = block_start
                if block_end and (end_time is None or block_end > end_time):
                    end_time = block_end

            raw_text = "\n\n".join(run.texts)

            # Determine ambiguity flags
            ambiguity = list(run.rule.ambiguity_flags)
            if len(run.block_indices) == 1:
                ambiguity.append("single_block_topic")

            topic_block = TopicBlock(
                envelope_id=envelope.envelope_id,
                source_block_ids=run.block_ids,
                topic_title=run.rule.topic_title,
                topic_type=run.rule.topic_type,
                primary_entity_ids=list(run.rule.primary_entity_ids),
                secondary_entity_ids=list(run.rule.secondary_entity_ids),
                start_block_index=start_idx,
                end_block_index=end_idx,
                start_time=start_time,
                end_time=end_time,
                summary="",
                raw_text=raw_text,
                segmentation_reason=(
                    f"Keyword match: {run.rule.topic_key} "
                    f"({len(run.block_ids)} blocks)"
                ),
                confidence=run.rule.confidence,
                ambiguity_flags=ambiguity,
            )
            topic_blocks.append(topic_block)

        # Step 4: Collect unassigned block IDs
        unassigned_block_ids: List[str] = [
            blocks[idx].block_id
            for idx in range(len(blocks))
            if idx not in assigned_indices
        ]

        return TopicAssemblyResult(
            envelope_id=envelope.envelope_id,
            topic_blocks=topic_blocks,
            unassigned_block_ids=unassigned_block_ids,
            assembly_strategy="deterministic_keyword_v1",
        )
