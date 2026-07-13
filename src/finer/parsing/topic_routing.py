"""F1.5 canonical-pipeline routing — when and how to assemble TopicBlocks.

canonical runner 在质量门与 F3 之间调用本模块：长内容（直播转写、长聊天、
长文档）按 TopicBlock 切分后逐 topic 提取，替代整文进 F3；短内容旁路，
保持原整文路径。F1.5 契约不变：只做语义 topic assembly，不产 direction /
actionability / TradeAction，不丢任何 block。

路由（env 可覆盖）：
- ``FINER_F15_MODE``      auto（默认，按长度阈值路由）| off | force
- ``FINER_F15_ASSEMBLER`` rule（默认，确定性）| llm（constrained proposal，
  失败自动回退规则版）
- ``FINER_F15_MIN_BLOCKS`` / ``FINER_F15_MIN_CHARS`` auto 模式阈值

规则版 ``TOPIC_RULES`` 是 golden fixture 词表，真实语料几乎不命中——
所以 rule fast-path 的主力是 **锚点驱动动态规则**：envelope 的 F2
entity_anchors（含 aliases 与出现位置）就是最可靠的 topic 种子，
``build_anchor_topic_rules`` 把它们转成 TopicRule，零 LLM 成本、可复现。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from finer.parsing.topic_assembler import TopicAssembler, TopicRule
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.topic_block import TopicAssemblyResult, TopicType

logger = logging.getLogger(__name__)

_DEFAULT_MIN_BLOCKS = 8
_DEFAULT_MIN_CHARS = 2400
# 每 envelope 的 F3 调用量 = 身份组数（llm 模式再乘共识投票数）。硬顶防
# 实体极多的长聊天把提取成本放大到不可控；溢出组按块数取大者保留，小组
# 并入「未分组」兜底提取，不丢内容。
_DEFAULT_MAX_GROUPS = 12

# registry entity_type / schema entity_type → TopicBlock 分类与规则置信度
_ANCHOR_TYPE_TO_TOPIC: Dict[str, Tuple[TopicType, float]] = {
    "stock": (TopicType.SINGLE_STOCK, 0.95),
    "etf": (TopicType.SINGLE_STOCK, 0.95),
    "crypto": (TopicType.SINGLE_STOCK, 0.95),
    "index": (TopicType.MARKET_COMMENTARY, 0.8),
    "sector": (TopicType.INDUSTRY, 0.72),
}


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or default).strip().lower()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _anchor_field(anchor: Any, key: str) -> Any:
    if isinstance(anchor, dict):
        return anchor.get(key)
    return getattr(anchor, key, None)


def build_anchor_topic_rules(envelope: ContentEnvelope) -> List[TopicRule]:
    """Derive deterministic TopicRules from the envelope's F2 entity anchors.

    每个 resolved anchor 生成一条规则：keywords = anchor aliases（含
    raw_text），topic 键 = ``anchor:{symbol}``。置信度按实体类型分级，
    保证具体标的（0.95）压过板块泛称（0.72）赢得 block 归属。
    """
    rules: List[TopicRule] = []
    seen_symbols: set = set()
    for anchor in getattr(envelope, "entity_anchors", None) or []:
        symbol = _anchor_field(anchor, "resolved_symbol")
        if not symbol or symbol in seen_symbols:
            continue
        entity_type = str(_anchor_field(anchor, "entity_type") or "stock")
        topic_type, confidence = _ANCHOR_TYPE_TO_TOPIC.get(
            entity_type, (TopicType.SINGLE_STOCK, 0.9)
        )
        raw_text = _anchor_field(anchor, "raw_text")
        aliases = list(_anchor_field(anchor, "aliases") or [])
        keywords = [
            kw
            for kw in dict.fromkeys([*(aliases), raw_text, str(symbol)])
            if kw and len(str(kw)) >= 2
        ]
        if not keywords:
            continue
        seen_symbols.add(symbol)
        rules.append(
            TopicRule(
                topic_key=f"anchor:{symbol}",
                topic_title=str(raw_text or symbol),
                topic_type=topic_type,
                keywords=[str(kw) for kw in keywords],
                primary_entity_ids=[str(symbol)],
                confidence=confidence,
            )
        )
    return rules


def _is_long_content(envelope: ContentEnvelope) -> bool:
    blocks = [
        b for b in (getattr(envelope, "blocks", None) or [])
        if (getattr(b, "text", "") or "").strip()
    ]
    if len(blocks) >= _env_int("FINER_F15_MIN_BLOCKS", _DEFAULT_MIN_BLOCKS):
        return True
    total_chars = sum(len(getattr(b, "text", "") or "") for b in blocks)
    return total_chars >= _env_int("FINER_F15_MIN_CHARS", _DEFAULT_MIN_CHARS)


def assemble_topics_for_extraction(
    envelope: ContentEnvelope,
) -> Optional[TopicAssemblyResult]:
    """Route an envelope through F1.5; None means "extract whole-envelope".

    None 的三种情形：mode=off、auto 模式下内容不够长、装配结果不足 2 个
    topic（单话题内容按 topic 切分没有增益，整文路径反而保留更多上下文）。
    """
    mode = _env("FINER_F15_MODE", "auto")
    if mode == "off":
        return None
    if mode != "force" and not _is_long_content(envelope):
        return None

    extra_rules = build_anchor_topic_rules(envelope)

    result: Optional[TopicAssemblyResult] = None
    if _env("FINER_F15_ASSEMBLER", "rule") == "llm":
        try:
            result = TopicAssembler(use_llm=True).assemble(envelope)
        except Exception as exc:  # noqa: BLE001 - LLM assembly degrades to rule path
            logger.warning(
                "F1.5 LLM assembly failed for %s (%s); falling back to rule assembler",
                getattr(envelope, "envelope_id", "?"), exc,
            )
    if result is None:
        result = TopicAssembler(extra_rules=extra_rules).assemble(envelope)

    if len(result.topic_blocks) < 2:
        return None
    return result


def topic_subenvelopes(
    envelope: ContentEnvelope,
    assembly: TopicAssemblyResult,
) -> List[Tuple[str, ContentEnvelope]]:
    """Split an envelope into per-topic sub-envelopes for F3 extraction.

    - ``envelope_id`` 不变：intents 的 provenance 指向真实 envelope。
    - entity_anchors 按 ``metadata.occurrences[].block_id`` 过滤到本 topic；
      没有出现位置信息的 anchor 保守地保留在所有子 envelope。
    - temporal_anchors 同理按 ``metadata.block_id`` 过滤；envelope 级锚
      （published_at，无 block_id）全部保留。
    - unassigned blocks 兜底成一个「未分组」子 envelope——F1.5 契约不丢块，
      整文路径今天能看到的内容，按 topic 路径也必须看到。
    """
    blocks_by_id = {
        getattr(b, "block_id", None): b
        for b in (getattr(envelope, "blocks", None) or [])
    }

    # 聊天体裁同一实体常散布出现，assembler 的连续块合并会拆成多个位置性
    # TopicBlock（实测 18 块聊天 → 14 topics / 9 实体）。位置切分是 F1.5
    # 的装配语义；对 F3 提取而言按 topic 身份聚合才是正确粒度——一个实体
    # 一次聚焦提取，也避免 LLM 提取调用量随位置碎片放大。
    grouped: Dict[str, Tuple[str, List[str]]] = {}
    for idx, tb in enumerate(assembly.topic_blocks):
        key = (
            tb.primary_entity_ids[0]
            if tb.primary_entity_ids
            else (tb.topic_title or f"topic-{idx}")
        )
        label = tb.topic_title or key
        if key in grouped:
            grouped[key][1].extend(tb.source_block_ids)
        else:
            grouped[key] = (label, list(tb.source_block_ids))
    groups: List[Tuple[str, List[str]]] = list(grouped.values())

    # Cost cap: keep the largest identity groups, merge the tail into the
    # fallback group (extraction still sees every block — no silent drop).
    max_groups = _env_int("FINER_F15_MAX_TOPICS", _DEFAULT_MAX_GROUPS)
    unassigned_ids = list(assembly.unassigned_block_ids)
    if max_groups > 0 and len(groups) > max_groups:
        ranked = sorted(
            enumerate(groups), key=lambda ig: (-len(ig[1][1]), ig[0])
        )
        keep_indices = {i for i, _ in ranked[:max_groups]}
        overflow = [g for i, g in enumerate(groups) if i not in keep_indices]
        groups = [g for i, g in enumerate(groups) if i in keep_indices]
        overflow_blocks = [bid for _, bids in overflow for bid in bids]
        unassigned_ids.extend(overflow_blocks)
        logger.warning(
            "F1.5: %d identity groups capped to %d for %s; %d blocks from %d "
            "overflow groups merged into the fallback group",
            len(groups) + len(overflow),
            max_groups,
            getattr(envelope, "envelope_id", "?"),
            len(overflow_blocks),
            len(overflow),
        )
    if unassigned_ids:
        groups.append(("未分组", unassigned_ids))

    def _anchor_block_ids(anchor: Any) -> set:
        meta = _anchor_field(anchor, "metadata") or {}
        occurrences = meta.get("occurrences") if isinstance(meta, dict) else None
        ids = {
            occ.get("block_id")
            for occ in (occurrences or [])
            if isinstance(occ, dict) and occ.get("block_id")
        }
        return ids

    def _temporal_block_id(anchor: Any) -> Optional[str]:
        meta = _anchor_field(anchor, "metadata") or {}
        if isinstance(meta, dict):
            return meta.get("block_id")
        return None

    subenvelopes: List[Tuple[str, ContentEnvelope]] = []
    for label, block_ids in groups:
        member_ids = {bid for bid in block_ids if bid in blocks_by_id}
        if not member_ids:
            continue
        sub_blocks = sorted(
            (blocks_by_id[bid] for bid in member_ids),
            key=lambda b: getattr(b, "order", 0),
        )
        sub_entities = [
            a
            for a in (getattr(envelope, "entity_anchors", None) or [])
            if not _anchor_block_ids(a) or (_anchor_block_ids(a) & member_ids)
        ]
        sub_temporals = [
            a
            for a in (getattr(envelope, "temporal_anchors", None) or [])
            if _temporal_block_id(a) is None or _temporal_block_id(a) in member_ids
        ]
        subenvelopes.append(
            (
                label,
                envelope.model_copy(
                    update={
                        "blocks": sub_blocks,
                        "entity_anchors": sub_entities,
                        "temporal_anchors": sub_temporals,
                    }
                ),
            )
        )
    return subenvelopes
