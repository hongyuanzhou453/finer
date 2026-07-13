"""Tests for F1.5 canonical-pipeline wiring (parsing.topic_routing + runner).

Pins:
  1. Anchor-driven TopicRules — F2 entity anchors become deterministic topic
     seeds (the rule fast-path that works on real corpus, not just fixtures).
  2. Routing — off/auto/force envs, length thresholds, and the <2-topics
     bail-out that keeps single-topic content on the whole-envelope path.
  3. Sub-envelope construction — envelope_id preserved, anchors filtered by
     occurrence block_ids, unassigned blocks kept via the fallback group
     (F1.5 contract: no block is ever discarded).
  4. Runner integration — long multi-topic envelopes extract per topic with
     f15_* provenance on each intent and narrowed block_ids; short content
     bypasses F1.5 entirely.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from finer.parsing.topic_routing import (
    assemble_topics_for_extraction,
    build_anchor_topic_rules,
    topic_subenvelopes,
)
from finer.pipeline.canonical_runner import run_canonical_from_envelope
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.quality import QualityCard
from finer.schemas.temporal import TemporalAnchor
from finer.schemas.topic_block import TopicType

_PUBLISHED_AT = datetime(2026, 3, 12, 15, 36, tzinfo=timezone(timedelta(hours=8)))


def _card() -> QualityCard:
    return QualityCard(
        readability_score=0.95,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.95,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.85,
        evidence_traceability_score=0.9,
    )


def _anchor(symbol: str, raw: str, etype: str, block_ids: list) -> EntityAnchor:
    span_ids = [f"span-{symbol}-{i}" for i in range(len(block_ids))]
    return EntityAnchor(
        entity_type=etype,
        raw_text=raw,
        resolved_symbol=symbol,
        market="CN",
        confidence=1.0,
        aliases=[raw],
        evidence_span_id=span_ids[0] if span_ids else None,
        metadata={
            "occurrences": [
                {"block_id": bid, "alias": raw, "char_start": 0, "char_end": len(raw)}
                for bid in block_ids
            ],
            "evidence_span_ids": span_ids,
        },
    )


def _block(i: int, text: str, spans: list | None = None) -> ContentBlock:
    return ContentBlock(
        block_id=f"b{i}",
        block_type="paragraph",
        text=text,
        order=i,
        quality_card=_card(),
        evidence_spans=spans or [],
    )


def _span(sid: str, bid: str, text: str) -> EvidenceSpan:
    return EvidenceSpan(
        evidence_span_id=sid,
        block_id=bid,
        char_start=0,
        char_end=len(text),
        text=text,
        span_type="entity",
        confidence=1.0,
    )


def _two_topic_envelope() -> ContentEnvelope:
    """8 blocks: b0-b3 discuss 腾讯 (0700.HK), b4-b7 discuss 泡泡玛特 (9992.HK).

    Each run carries the F2 shape: anchors with per-block occurrences and
    matching block-level evidence spans.
    """
    tencent_blocks = [
        _block(0, "腾讯今天的表现值得关注，游戏业务恢复明显。",
               [_span("span-0700.HK-0", "b0", "腾讯")]),
        _block(1, "腾讯的广告收入也在回升，基本面扎实。",
               [_span("span-0700.HK-1", "b1", "腾讯")]),
        _block(2, "我看好腾讯，建议逢低买入。",
               [_span("span-0700.HK-2", "b2", "腾讯")]),
        _block(3, "腾讯视频号的商业化空间还很大。",
               [_span("span-0700.HK-3", "b3", "腾讯")]),
    ]
    popmart_blocks = [
        _block(4, "泡泡玛特的海外扩张超预期。",
               [_span("span-9992.HK-0", "b4", "泡泡玛特")]),
        _block(5, "泡泡玛特新品发售火爆，看好后续表现。",
               [_span("span-9992.HK-1", "b5", "泡泡玛特")]),
        _block(6, "泡泡玛特估值不便宜但成长性支撑，建议买入。",
               [_span("span-9992.HK-2", "b6", "泡泡玛特")]),
        _block(7, "泡泡玛特的 IP 矩阵是护城河。",
               [_span("span-9992.HK-3", "b7", "泡泡玛特")]),
    ]
    return ContentEnvelope(
        envelope_id="env-topic-test",
        source_type="video_transcript",
        creator_id="kol-test-001",
        published_at=_PUBLISHED_AT,
        quality_card=_card(),
        blocks=tencent_blocks + popmart_blocks,
        entity_anchors=[
            _anchor("0700.HK", "腾讯", "stock", ["b0", "b1", "b2", "b3"]),
            _anchor("9992.HK", "泡泡玛特", "stock", ["b4", "b5", "b6", "b7"]),
        ],
        temporal_anchors=[
            TemporalAnchor(
                anchor_type="published_at",
                raw_text="published_at",
                resolved_time=_PUBLISHED_AT,
                confidence=1.0,
                resolution_strategy="explicit_date",
                metadata={},
            ),
            TemporalAnchor(
                anchor_type="mentioned_at",
                raw_text="今天",
                resolved_time=_PUBLISHED_AT,
                confidence=0.85,
                resolution_strategy="relative_date",
                metadata={"block_id": "b0"},
            ),
        ],
    )


# ── 1. Anchor-driven TopicRules ──────────────────────────────────────────────


class TestAnchorTopicRules:
    def test_rules_from_anchors(self):
        env = _two_topic_envelope()
        rules = build_anchor_topic_rules(env)
        by_key = {r.topic_key: r for r in rules}
        assert set(by_key) == {"anchor:0700.HK", "anchor:9992.HK"}
        tencent = by_key["anchor:0700.HK"]
        assert "腾讯" in tencent.keywords
        assert tencent.topic_type == TopicType.SINGLE_STOCK
        assert tencent.confidence == 0.95
        assert tencent.primary_entity_ids == ["0700.HK"]

    def test_sector_anchor_gets_industry_type_and_lower_confidence(self):
        env = _two_topic_envelope().model_copy(
            update={"entity_anchors": [_anchor("ENERGY_STORAGE", "储能", "sector", ["b0"])]}
        )
        rules = build_anchor_topic_rules(env)
        assert len(rules) == 1
        assert rules[0].topic_type == TopicType.INDUSTRY
        assert rules[0].confidence < 0.95

    def test_duplicate_symbols_and_missing_symbols_skipped(self):
        env = _two_topic_envelope().model_copy(
            update={
                "entity_anchors": [
                    _anchor("0700.HK", "腾讯", "stock", ["b0"]),
                    _anchor("0700.HK", "腾讯控股", "stock", ["b1"]),
                ]
            }
        )
        assert len(build_anchor_topic_rules(env)) == 1


# ── 2. Routing ───────────────────────────────────────────────────────────────


class TestRouting:
    def test_long_multi_topic_assembles(self, monkeypatch):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        result = assemble_topics_for_extraction(_two_topic_envelope())
        assert result is not None
        assert len(result.topic_blocks) == 2
        titles = {tb.topic_title for tb in result.topic_blocks}
        assert titles == {"腾讯", "泡泡玛特"}

    def test_mode_off_bypasses(self, monkeypatch):
        monkeypatch.setenv("FINER_F15_MODE", "off")
        assert assemble_topics_for_extraction(_two_topic_envelope()) is None

    def test_short_content_bypasses_in_auto(self, monkeypatch):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        short = env.model_copy(update={"blocks": list(env.blocks[:2])})
        assert assemble_topics_for_extraction(short) is None

    def test_force_ignores_thresholds(self, monkeypatch):
        monkeypatch.setenv("FINER_F15_MODE", "force")
        env = _two_topic_envelope()
        short = env.model_copy(update={"blocks": [env.blocks[0], env.blocks[4]]})
        result = assemble_topics_for_extraction(short)
        assert result is not None and len(result.topic_blocks) == 2

    def test_single_topic_returns_none(self, monkeypatch):
        """<2 topics → whole-envelope path retains more context."""
        monkeypatch.setenv("FINER_F15_MODE", "force")
        env = _two_topic_envelope()
        only_tencent = env.model_copy(
            update={
                "blocks": list(env.blocks[:4]),
                "entity_anchors": [env.entity_anchors[0]],
            }
        )
        assert assemble_topics_for_extraction(only_tencent) is None


# ── 3. Sub-envelope construction ─────────────────────────────────────────────


class TestSubEnvelopes:
    def test_split_preserves_id_and_filters_anchors(self, monkeypatch):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        assembly = assemble_topics_for_extraction(env)
        subs = topic_subenvelopes(env, assembly)
        assert len(subs) == 2
        for label, sub in subs:
            assert sub.envelope_id == "env-topic-test"
            symbols = {a.resolved_symbol for a in sub.entity_anchors}
            if label == "腾讯":
                assert symbols == {"0700.HK"}
                assert [b.block_id for b in sub.blocks] == ["b0", "b1", "b2", "b3"]
                # block-level temporal anchor (b0) rides with this topic
                assert {t.anchor_type for t in sub.temporal_anchors} == {
                    "published_at", "mentioned_at",
                }
            else:
                assert symbols == {"9992.HK"}
                # published_at (no block_id) is kept everywhere
                assert {t.anchor_type for t in sub.temporal_anchors} == {"published_at"}

    def test_unassigned_blocks_get_fallback_group(self, monkeypatch):
        monkeypatch.setenv("FINER_F15_MODE", "force")
        env = _two_topic_envelope()
        noise = _block(8, "今天天气不错，先聊到这里，谢谢大家收看。")
        env = env.model_copy(update={"blocks": [*env.blocks, noise]})
        assembly = assemble_topics_for_extraction(env)
        assert "b8" in assembly.unassigned_block_ids
        subs = topic_subenvelopes(env, assembly)
        labels = [label for label, _ in subs]
        assert labels[-1] == "未分组"
        assert [b.block_id for b in subs[-1][1].blocks] == ["b8"]

    def test_scattered_same_entity_topics_merge_into_one_group(self, monkeypatch):
        """聊天里同一实体分散出现 → assembler 产多个位置性 TopicBlock，
        提取路由按 topic 身份聚合成一个子 envelope。"""
        monkeypatch.setenv("FINER_F15_MODE", "force")
        env = _two_topic_envelope()
        # interleave: 腾讯 b0-b1, 泡泡玛特 b4-b5, 腾讯 b2-b3 again (reordered)
        reordered = [
            env.blocks[0], env.blocks[1],
            env.blocks[4], env.blocks[5],
            env.blocks[2], env.blocks[3],
            env.blocks[6], env.blocks[7],
        ]
        for new_order, b in enumerate(reordered):
            object.__setattr__(b, "order", new_order)
        env = env.model_copy(update={"blocks": reordered})
        assembly = assemble_topics_for_extraction(env)
        # positional topics: 腾讯/泡泡玛特/腾讯/泡泡玛特 = 4
        assert len(assembly.topic_blocks) == 4
        subs = topic_subenvelopes(env, assembly)
        # identity groups: 腾讯 + 泡泡玛特 = 2
        assert len(subs) == 2
        by_label = {label: sub for label, sub in subs}
        assert {b.block_id for b in by_label["腾讯"].blocks} == {"b0", "b1", "b2", "b3"}
        assert {b.block_id for b in by_label["泡泡玛特"].blocks} == {"b4", "b5", "b6", "b7"}

    def test_anchor_without_occurrences_kept_everywhere(self, monkeypatch):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        bare = EntityAnchor(
            entity_type="index",
            raw_text="A股",
            resolved_symbol="000001.SH",
            market="CN",
            confidence=1.0,
            metadata={},
        )
        env = env.model_copy(update={"entity_anchors": [*env.entity_anchors, bare]})
        assembly = assemble_topics_for_extraction(env)
        subs = topic_subenvelopes(env, assembly)
        for _label, sub in subs:
            assert "000001.SH" in {a.resolved_symbol for a in sub.entity_anchors}


# ── 4. Runner integration ────────────────────────────────────────────────────


class TestRunnerIntegration:
    def test_long_envelope_extracts_per_topic(self, monkeypatch):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        actions = asyncio.run(run_canonical_from_envelope(env, {}))
        assert actions, "expected actions from the two bullish topics"
        tickers = {a.target.ticker for a in actions}
        assert {"0700.HK", "9992.HK"} <= tickers

    def test_intents_carry_f15_provenance_and_narrow_block_ids(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        actions = asyncio.run(
            run_canonical_from_envelope(env, {}, persist_dir=tmp_path)
        )
        assert actions
        # persisted F3 intents carry topic provenance + topic-scoped block_ids
        import json

        intent_files = list((tmp_path / "F3_intents").glob("*.json"))
        intents = [json.loads(p.read_text()) for p in intent_files]
        by_symbol = {
            i["target_symbol"]: i for i in intents if i.get("target_symbol")
        }
        assert "0700.HK" in by_symbol and "9992.HK" in by_symbol
        tencent = by_symbol["0700.HK"]
        assert tencent["metadata"]["f15_topic_title"] == "腾讯"
        assert set(tencent["block_ids"]) <= {"b0", "b1", "b2", "b3"}
        popmart = by_symbol["9992.HK"]
        assert popmart["metadata"]["f15_topic_title"] == "泡泡玛特"
        assert set(popmart["block_ids"]) <= {"b4", "b5", "b6", "b7"}
        # the assembly itself is persisted for audit
        assert list((tmp_path / "F1_5_topics").glob("*.json"))

    def test_short_envelope_bypasses_f15(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        short = env.model_copy(
            update={
                "blocks": [env.blocks[2]],
                "entity_anchors": [env.entity_anchors[0]],
            }
        )
        actions = asyncio.run(
            run_canonical_from_envelope(short, {}, persist_dir=tmp_path)
        )
        assert actions
        import json

        intents = [
            json.loads(p.read_text())
            for p in (tmp_path / "F3_intents").glob("*.json")
        ]
        assert all("f15_topic_title" not in (i.get("metadata") or {}) for i in intents)
        assert not (tmp_path / "F1_5_topics").exists()

    def test_mode_off_keeps_whole_envelope_path(self, monkeypatch):
        monkeypatch.setenv("FINER_F15_MODE", "off")
        env = _two_topic_envelope()
        actions = asyncio.run(run_canonical_from_envelope(env, {}))
        # same targets still extracted — F1.5 is a precision upgrade, not a
        # recall dependency
        tickers = {a.target.ticker for a in actions}
        assert {"0700.HK", "9992.HK"} <= tickers

    def test_assembly_persisted_even_without_actions(self, monkeypatch, tmp_path):
        """F1_5_topics sidecar is an F1.5-stage artifact — persisted when
        assembly engages, not gated on F5 emitting actions (review finding)."""
        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        neutral = [
            b.model_copy(update={"text": f"{name}公布了季度运营数据，披露了用户规模。"})
            for b, name in zip(
                env.blocks,
                ["腾讯", "腾讯", "腾讯", "腾讯", "泡泡玛特", "泡泡玛特", "泡泡玛特", "泡泡玛特"],
            )
        ]
        env = env.model_copy(update={"blocks": neutral})
        actions = asyncio.run(
            run_canonical_from_envelope(env, {}, persist_dir=tmp_path)
        )
        assert actions == []
        assert list((tmp_path / "F1_5_topics").glob("*.json"))


# ── 5. Per-topic fallback semantics (2026-07-12 review fixes) ────────────────


class _ScriptedExtractor:
    """Non-rule extractor stub: behavior keyed on which entity the
    sub-envelope carries. 'intents' → one bullish intent; 'empty' → genuine
    no-stance result; 'fail_marker' → empty result with an LLM failure note;
    'raise' → exception."""

    VERSION = "llm_consensus_v1"

    def __init__(self, script: dict):
        self.script = script

    def extract(self, envelope):
        from uuid import uuid4

        from finer.extraction.intent_extractor import IntentExtractionResult
        from finer.schemas.investment_intent import NormalizedInvestmentIntent

        symbols = {a.resolved_symbol for a in envelope.entity_anchors}
        mode = next(
            (m for sym, m in self.script.items() if sym in symbols), "empty"
        )
        if mode == "raise":
            raise RuntimeError("simulated LLM outage")
        if mode == "fail_marker":
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                intents=[],
                processing_notes=["run 1: LLM call exception: timeout"],
                extractor_version=self.VERSION,
            )
        if mode == "empty":
            return IntentExtractionResult(
                envelope_id=envelope.envelope_id,
                intents=[],
                processing_notes=["consensus: 0 stances survived"],
                extractor_version=self.VERSION,
            )
        sym = mode  # 'intents' mode stores the symbol itself
        block_ids = [b.block_id for b in envelope.blocks]
        intent = NormalizedInvestmentIntent(
            intent_id=str(uuid4()),
            envelope_id=envelope.envelope_id,
            block_ids=block_ids,
            creator_id="kol-test-001",
            target_type="stock",
            target_name=sym,
            target_symbol=sym,
            market="CN",
            direction="bullish",
            actionability="explicit_action",
            position_delta_hint="add",
            conviction=0.8,
            confidence=0.8,
            evidence_span_ids=[f"span-{sym}-0"],
            ambiguity_flags=[],
        )
        return IntentExtractionResult(
            envelope_id=envelope.envelope_id,
            intents=[intent],
            processing_notes=[],
            extractor_version=self.VERSION,
        )


class TestPerTopicFallbackSemantics:
    def _run_per_topic(self, script, monkeypatch):
        from finer.parsing.topic_routing import assemble_topics_for_extraction
        from finer.pipeline.canonical_runner import _extract_intents_per_topic

        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        assembly = assemble_topics_for_extraction(env)
        assert assembly is not None
        return _extract_intents_per_topic(_ScriptedExtractor(script), env, assembly)

    def test_genuine_empty_topic_is_not_resurrected_by_rule_fallback(
        self, monkeypatch
    ):
        """LLM 判定某 topic 无立场（空结果、无失败标记）→ 不得用规则提取器
        重跑复活假阳性（high finding）。泡泡玛特块带 看好/买入 关键词，规则
        提取器一旦重跑必产 9992.HK intent。"""
        result = self._run_per_topic(
            {"0700.HK": "0700.HK", "9992.HK": "empty"}, monkeypatch
        )
        symbols = {i.target_symbol for i in result.intents}
        assert symbols == {"0700.HK"}
        assert not any("fell back" in n for n in result.processing_notes)
        assert result.extractor_version == "llm_consensus_v1"

    def test_explicit_llm_failure_marker_still_falls_back(self, monkeypatch):
        result = self._run_per_topic(
            {"0700.HK": "0700.HK", "9992.HK": "fail_marker"}, monkeypatch
        )
        symbols = {i.target_symbol for i in result.intents}
        assert "9992.HK" in symbols  # rule fallback re-extracted the topic
        assert any("fell back" in n for n in result.processing_notes)

    def test_exception_falls_back_and_version_is_honest_mixed(self, monkeypatch):
        """单 topic LLM 异常 → 该 topic 规则回退；合并版本打 mixed 章，
        每条 intent 的 metadata 记录本 topic 实际 extractor 版本。"""
        result = self._run_per_topic(
            {"0700.HK": "0700.HK", "9992.HK": "raise"}, monkeypatch
        )
        by_symbol = {i.target_symbol: i for i in result.intents}
        assert "0700.HK" in by_symbol and "9992.HK" in by_symbol
        assert result.extractor_version == "mixed(llm_consensus_v1+rule_based_v1)"
        assert (
            by_symbol["0700.HK"].metadata["f15_extractor_version"]
            == "llm_consensus_v1"
        )
        assert (
            by_symbol["9992.HK"].metadata["f15_extractor_version"]
            == "rule_based_v1"
        )

    def test_cross_topic_duplicate_gets_merged_topics_annotation(self, monkeypatch):
        """dedupe 把跨 topic 的同 (target, direction, hint) intent 合并进首见
        条目并 union block_ids；block_ids 跨组的幸存者必须标注
        f15_merged_topics，避免单一 f15_topic_title 错误指向部分证据。"""
        from finer.parsing.topic_routing import assemble_topics_for_extraction
        from finer.pipeline.canonical_runner import _extract_intents_per_topic

        monkeypatch.delenv("FINER_F15_MODE", raising=False)
        env = _two_topic_envelope()
        # bare anchor（无 occurrences）保守保留在所有子 envelope；scripted
        # extractor 对两个 topic 都命中它 → 两条同 stance intent → dedupe 合并
        bare = EntityAnchor(
            entity_type="index",
            raw_text="A股",
            resolved_symbol="000001.SH",
            market="CN",
            confidence=1.0,
            metadata={},
        )
        env = env.model_copy(update={"entity_anchors": [*env.entity_anchors, bare]})
        assembly = assemble_topics_for_extraction(env)
        result = _extract_intents_per_topic(
            _ScriptedExtractor({"000001.SH": "000001.SH"}), env, assembly
        )
        assert len(result.intents) == 1
        merged = result.intents[0]
        assert sorted(merged.metadata["f15_merged_topics"]) == ["泡泡玛特", "腾讯"]

    def test_group_cap_merges_overflow_into_fallback(self, monkeypatch):
        from finer.parsing.topic_routing import (
            assemble_topics_for_extraction,
            topic_subenvelopes,
        )

        monkeypatch.setenv("FINER_F15_MODE", "force")
        monkeypatch.setenv("FINER_F15_MAX_TOPICS", "1")
        env = _two_topic_envelope()
        assembly = assemble_topics_for_extraction(env)
        subs = topic_subenvelopes(env, assembly)
        labels = [label for label, _ in subs]
        assert len(subs) == 2  # 1 kept group + fallback
        assert labels[-1] == "未分组"
        kept_blocks = {b.block_id for _, sub in subs for b in sub.blocks}
        assert len(kept_blocks) == 8  # no block dropped
