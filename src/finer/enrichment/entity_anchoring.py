"""F2 EntityAnchor L1 producer — deterministic registry alias scan.

L1 (确定层): 精确扫描 `entity_registry` 别名在 block 文本中的出现，构造高置信
EntityAnchor。零 LLM 成本、可审计、可复现。

匹配规则 (解决短码子串误命中):
- 中文别名 ("腾讯"): 直接子串匹配 (CJK 子串误匹配概率低)。
- 英文/数字别名 ("NVDA"/"0700"/"LI"): 词边界匹配 (前后非字母数字)，避免
  "LI" 误命中 "QUALITY"、"0700" 误命中 "070012"。

同一 ticker 的多个别名 / 多次出现合并为单个 envelope 级 EntityAnchor，所有
出现位置记入 `metadata.occurrences`，供 F2 EvidenceSpan (步骤 5) 消费。

L2 (LLM 发现层) 与 registry-gap 路由见
docs/specs/2026-06-14-f2-anchoring-design.md。
"""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Dict, List, NamedTuple, Tuple

from finer.entity_registry import ENTITY_REGISTRY
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.quality import QualityCard

# registry entity_type → schema ENTITY_TYPE_LITERAL
# registry 用 "ticker"/"index"/"crypto"/"sector"；schema literal 无 "ticker"，映射为 "stock"
_TYPE_MAP: Dict[str, str] = {
    "ticker": "stock",
    "index": "index",
    "crypto": "crypto",
    "sector": "sector",
}


def _is_cjk(text: str) -> bool:
    """True if text contains any CJK character."""
    return any("一" <= c <= "鿿" for c in text)


# 预编译: 纯 ASCII (英文/数字) 别名的词边界 pattern；CJK 别名走子串匹配
_ASCII_ALIAS_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (alias, re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"))
    for alias in ENTITY_REGISTRY
    if not _is_cjk(alias)
]
_CJK_ALIASES: List[str] = [alias for alias in ENTITY_REGISTRY if _is_cjk(alias)]


class Hit(NamedTuple):
    """One registry alias occurrence in a text."""

    alias: str
    ticker: str
    market: str
    schema_type: str
    start: int
    end: int


def scan_text(text: str) -> List[Hit]:
    """Scan one text for all registry alias occurrences (L1 exact match)."""
    if not text:
        return []
    hits: List[Hit] = []
    # 中文别名: 子串匹配，记录所有出现位置
    for alias in _CJK_ALIASES:
        ticker, market, etype = ENTITY_REGISTRY[alias]
        schema_type = _TYPE_MAP.get(etype, "unknown")
        start = text.find(alias)
        while start != -1:
            hits.append(Hit(alias, ticker, market, schema_type, start, start + len(alias)))
            start = text.find(alias, start + 1)
    # 英文/数字别名: 词边界匹配，避免短码子串误命中
    for alias, pat in _ASCII_ALIAS_PATTERNS:
        ticker, market, etype = ENTITY_REGISTRY[alias]
        schema_type = _TYPE_MAP.get(etype, "unknown")
        for m in pat.finditer(text):
            hits.append(Hit(alias, ticker, market, schema_type, m.start(), m.end()))
    return hits


def anchor_entities_l1(blocks: List[Tuple[str, str]]) -> List[EntityAnchor]:
    """Build envelope-level EntityAnchors from blocks via L1 registry scan.

    Args:
        blocks: list of ``(block_id, text)`` pairs.

    Returns:
        List of EntityAnchor — one per resolved ticker, with all occurrences
        (block_id + char offsets) recorded in ``metadata.occurrences`` for
        downstream EvidenceSpan construction. confidence is 1.0 (exact match).
    """
    # ticker -> aggregated mentions
    agg: Dict[str, Dict[str, Any]] = {}
    for block_id, text in blocks:
        for h in scan_text(text):
            slot = agg.setdefault(
                h.ticker,
                {"market": h.market, "schema_type": h.schema_type, "aliases": [], "occurrences": []},
            )
            if h.alias not in slot["aliases"]:
                slot["aliases"].append(h.alias)
            slot["occurrences"].append(
                {"block_id": block_id, "alias": h.alias, "char_start": h.start, "char_end": h.end}
            )

    anchors: List[EntityAnchor] = []
    for ticker, slot in agg.items():
        aliases = slot["aliases"]
        # raw_text: 取最长别名 (最具体，如 "腾讯控股" 优先于 "腾讯")
        raw = max(aliases, key=len)
        anchors.append(
            EntityAnchor(
                entity_type=slot["schema_type"],
                raw_text=raw,
                resolved_symbol=ticker,
                resolved_name=None,  # registry 不存规范名；display 回退到 symbol
                market=slot["market"],
                confidence=1.0,  # L1 字面精确匹配 → 确定
                aliases=sorted(aliases),
                metadata={
                    "layer": "L1",
                    "match": "registry_exact",
                    "occurrences": slot["occurrences"],
                    "mention_count": len(slot["occurrences"]),
                },
            )
        )
    anchors.sort(key=lambda a: a.resolved_symbol or "")
    return anchors


def anchor_envelope_l1(envelope: Dict[str, Any]) -> List[EntityAnchor]:
    """Convenience: run L1 anchoring over an envelope dict's blocks."""
    blocks = [
        (b.get("block_id", ""), b.get("text", "") or "")
        for b in envelope.get("blocks", [])
    ]
    return anchor_entities_l1(blocks)


def _stable_id(prefix: str, *parts: Any) -> str:
    """Build a deterministic stage-local ID from immutable source coordinates."""
    payload = "\x1f".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _envelope_to_dict(envelope: ContentEnvelope | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(envelope, ContentEnvelope):
        return envelope.model_dump(mode="json")
    return copy.deepcopy(envelope)


def _f0_metadata(f0_record: ContentRecord | Dict[str, Any] | None) -> Dict[str, Any]:
    if f0_record is None:
        return {}
    if isinstance(f0_record, ContentRecord):
        return f0_record.model_dump(mode="json")
    return copy.deepcopy(f0_record)


def _bbox_json(block: Dict[str, Any]) -> Dict[str, Any] | None:
    bbox = block.get("bbox")
    if not bbox:
        return None
    if isinstance(bbox, dict):
        return copy.deepcopy(bbox)
    if hasattr(bbox, "model_dump"):
        return bbox.model_dump(mode="json")
    return None


def _span_provenance_metadata(
    block: Dict[str, Any],
    hit: Hit,
    *,
    source_record_id: str,
    raw_path: str,
) -> Dict[str, Any]:
    """Build provenance metadata for an F2 evidence span."""
    bbox = _bbox_json(block)
    page_index = block.get("page_index")
    if bbox:
        granularity = "bbox"
    elif page_index is not None:
        granularity = "page"
    else:
        granularity = "file"

    metadata: Dict[str, Any] = {
        "stage": "F2",
        "layer": "L1",
        "match": "registry_exact",
        "alias": hit.alias,
        "resolved_symbol": hit.ticker,
        "market": hit.market,
        "source_record_id": source_record_id,
        "raw_path": raw_path,
        "provenance_granularity": granularity,
    }
    if page_index is not None:
        metadata["page_index"] = page_index
    if bbox:
        metadata["bbox"] = bbox
    return metadata


def _evidence_span_for_hit(
    block: Dict[str, Any],
    hit: Hit,
    *,
    source_record_id: str,
    raw_path: str,
) -> EvidenceSpan:
    block_id = block.get("block_id") or ""
    span_id = _stable_id(
        "span",
        source_record_id,
        block_id,
        hit.ticker,
        hit.alias,
        hit.start,
        hit.end,
    )
    text = block.get("text") or ""
    return EvidenceSpan(
        evidence_span_id=span_id,
        block_id=block_id,
        char_start=hit.start,
        char_end=hit.end,
        text=text[hit.start:hit.end],
        confidence=1.0,
        span_type="entity",
        metadata=_span_provenance_metadata(
            block,
            hit,
            source_record_id=source_record_id,
            raw_path=raw_path,
        ),
    )


def _entity_anchor_from_slot(
    ticker: str,
    slot: Dict[str, Any],
    *,
    source_record_id: str,
) -> EntityAnchor:
    aliases = slot["aliases"]
    span_ids = slot["evidence_span_ids"]
    return EntityAnchor(
        entity_anchor_id=_stable_id("entity", source_record_id, ticker),
        entity_type=slot["schema_type"],
        raw_text=max(aliases, key=len),
        resolved_symbol=ticker,
        resolved_name=None,
        market=slot["market"],
        confidence=1.0,
        evidence_span_id=span_ids[0] if span_ids else None,
        aliases=sorted(aliases),
        metadata={
            "layer": "L1",
            "match": "registry_exact",
            "occurrences": slot["occurrences"],
            "mention_count": len(slot["occurrences"]),
            "evidence_span_ids": span_ids,
        },
    )


def build_l1_entity_anchors_with_spans(
    envelope: ContentEnvelope | Dict[str, Any],
) -> Tuple[List[EntityAnchor], Dict[str, List[EvidenceSpan]]]:
    """Build deterministic L1 EntityAnchors plus per-block EvidenceSpans.

    This is the F2 production helper. Unlike ``anchor_entities_l1`` it assigns
    stable IDs and materializes one ``EvidenceSpan`` per alias occurrence.
    """
    data = _envelope_to_dict(envelope)
    source_record_id = data.get("source_record_id") or data.get("envelope_id") or "unknown"
    raw_path = data.get("raw_path") or data.get("source_uri") or ""
    spans_by_block: Dict[str, List[EvidenceSpan]] = {}
    agg: Dict[str, Dict[str, Any]] = {}

    for block in data.get("blocks", []):
        block_id = block.get("block_id") or ""
        text = block.get("text") or ""
        hits = sorted(
            scan_text(text),
            key=lambda h: (h.start, h.end, h.ticker, h.alias),
        )
        for hit in hits:
            span = _evidence_span_for_hit(
                block,
                hit,
                source_record_id=source_record_id,
                raw_path=raw_path,
            )
            spans_by_block.setdefault(block_id, []).append(span)
            slot = agg.setdefault(
                hit.ticker,
                {
                    "market": hit.market,
                    "schema_type": hit.schema_type,
                    "aliases": [],
                    "occurrences": [],
                    "evidence_span_ids": [],
                },
            )
            if hit.alias not in slot["aliases"]:
                slot["aliases"].append(hit.alias)
            slot["occurrences"].append(
                {
                    "block_id": block_id,
                    "alias": hit.alias,
                    "char_start": hit.start,
                    "char_end": hit.end,
                    "evidence_span_id": span.evidence_span_id,
                }
            )
            slot["evidence_span_ids"].append(span.evidence_span_id)

    anchors = [
        _entity_anchor_from_slot(ticker, slot, source_record_id=source_record_id)
        for ticker, slot in agg.items()
    ]
    anchors.sort(key=lambda a: a.resolved_symbol or "")
    for spans in spans_by_block.values():
        spans.sort(key=lambda s: (s.char_start, s.char_end, s.text, s.evidence_span_id))
    return anchors, spans_by_block


def _update_f2_quality(
    quality_card: Dict[str, Any],
    *,
    hit_block_count: int,
    total_block_count: int,
) -> Dict[str, Any]:
    score = round(hit_block_count / total_block_count, 4) if total_block_count else 0.0
    card = QualityCard.model_validate(quality_card)
    updated = card.model_dump()
    updated["entity_resolution_score"] = score
    updated["evidence_traceability_score"] = max(card.evidence_traceability_score, score)
    return QualityCard.model_validate(updated).model_dump(mode="json")


def build_f2_l1_envelope(
    envelope: ContentEnvelope | Dict[str, Any],
    *,
    f0_record: ContentRecord | Dict[str, Any] | None = None,
) -> ContentEnvelope:
    """Copy a F1 envelope and attach deterministic F2 L1 anchors/spans.

    The media-level F1 ``source_type`` is preserved (e.g. ``pdf``). Original F0
    taxonomy is copied into envelope metadata for downstream filtering.
    """
    data = _envelope_to_dict(envelope)
    f0 = _f0_metadata(f0_record)
    anchors, spans_by_block = build_l1_entity_anchors_with_spans(data)

    hit_blocks = 0
    for block in data.get("blocks", []):
        block_id = block.get("block_id") or ""
        spans = spans_by_block.get(block_id, [])
        block["evidence_spans"] = [s.model_dump(mode="json") for s in spans]
        if spans:
            hit_blocks += 1

    data["entity_anchors"] = [a.model_dump(mode="json") for a in anchors]
    data["quality_card"] = _update_f2_quality(
        data["quality_card"],
        hit_block_count=hit_blocks,
        total_block_count=len(data.get("blocks", [])),
    )

    metadata = copy.deepcopy(data.get("metadata") or {})
    source_type = f0.get("source_type")
    if source_type:
        metadata["f0_source_type"] = source_type
    if f0.get("source_platform"):
        metadata["f0_source_platform"] = f0["source_platform"]
    metadata["f2_anchor"] = {
        "stage": "F2",
        "layer": "L1",
        "method": "registry_exact",
        "entity_anchor_count": len(anchors),
        "evidence_span_count": sum(len(v) for v in spans_by_block.values()),
        "hit_block_count": hit_blocks,
        "total_block_count": len(data.get("blocks", [])),
    }
    data["metadata"] = metadata
    return ContentEnvelope.model_validate(data)
