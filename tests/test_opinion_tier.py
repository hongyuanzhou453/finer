"""Tests for the F5 opinion tier (watch_only materializes instead of rejecting).

Product decision (2026-07-05): the viewpoint products present opinions, but F5
used to drop every watch_only mapping as non_executable_action_hint — an honest
F3 extractor (most KOL speech IS opinion) would starve the dashboard. Opinions
now materialize as non-executable WATCH actions passing the same gates.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from finer.pipeline.canonical_runner import run_canonical_from_envelope
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.quality import QualityCard
from finer.schemas.trade_action import ActionType


def make_quality_card() -> QualityCard:
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.8,
        financial_relevance_score=0.9,
        entity_resolution_score=0.8,
        temporal_resolution_score=0.7,
        evidence_traceability_score=0.8,
    )


def make_envelope(text: str) -> ContentEnvelope:
    return ContentEnvelope(
        envelope_id="env-opinion-tier",
        source_type="feishu_doc",
        source_title="t",
        quality_card=make_quality_card(),
        creator_id="k1",
        published_at=datetime(2026, 3, 2, 9, 0),
        blocks=[
            ContentBlock(
                block_type="paragraph",
                text=text,
                order=0,
                quality_card=make_quality_card(),
            )
        ],
    )


class TestOpinionTier:
    def test_pure_opinion_materializes_as_watch(self):
        """看好但无交易动作 → WATCH action（原先被 non_executable 拒掉）。"""
        env = make_envelope("我长期看好贵州茅台，基本面扎实，护城河深。")
        actions = asyncio.run(run_canonical_from_envelope(env, {}))
        watch = [
            a
            for a in actions
            if a.action_chain and a.action_chain[0].action_type == ActionType.WATCH
        ]
        assert watch, [
            (a.target.ticker, a.action_chain[0].action_type) for a in actions
        ]
        ta = watch[0]
        assert ta.target.ticker == "600519.SH"
        # opinion keeps the KOL's sentiment for the radar breadth/consensus
        assert ta.direction.value == "bullish"
        # non-executable: no position size
        assert ta.action_chain[0].position_size_pct is None
        assert ta.metadata.get("tier") == "opinion"
        assert ta.metadata.get("action_hint_original") in (
            "watch_only",
            "watch_or_no_trade",
        )
        # canonical trace intact
        assert ta.intent_id and ta.policy_id

    def test_explicit_action_still_trade_tier(self):
        env = make_envelope("贵州茅台我今天加仓了，回调就是机会，建议买入。")
        actions = asyncio.run(run_canonical_from_envelope(env, {}))
        assert actions
        trade = [a for a in actions if a.metadata.get("tier") == "trade"]
        assert trade, [(a.metadata, a.action_chain[0].action_type) for a in actions]
        assert trade[0].action_chain[0].action_type != ActionType.WATCH

    def test_sector_opinion_still_rejected(self):
        """opinion tier 不放宽 sector gate——板块观点仍不产 action。"""
        env = make_envelope("我看好光模块这个板块的长期逻辑。")
        actions = asyncio.run(run_canonical_from_envelope(env, {}))
        assert all(
            (a.target.ticker or "") != "OPTICAL_MODULE" for a in actions
        ), [a.target.ticker for a in actions]

    def test_bearish_opinion_materializes_as_watch(self):
        """看空但无交易动作 → F4 avoid_or_watch_risk → WATCH action，方向保真。

        live regen 2026-07-05：4 条全票 bearish 观点在 F5 被
        non_executable_action_hint 整层滤掉，时间线被漏斗（而非内容）推成偏多。
        """
        env = make_envelope("我看空贵州茅台，估值太贵，建议回避，风险很大。")
        actions = asyncio.run(run_canonical_from_envelope(env, {}))
        watch = [
            a
            for a in actions
            if a.action_chain and a.action_chain[0].action_type == ActionType.WATCH
        ]
        assert watch, [
            (a.target.ticker, a.direction, a.metadata) for a in actions
        ]
        ta = watch[0]
        assert ta.direction.value == "bearish"
        assert ta.metadata.get("tier") == "opinion"
        assert ta.action_chain[0].position_size_pct is None

    def test_mixed_direction_resolves_neutral_not_bullish(self):
        """mixed/unknown 无对应 TradeDirection 成员 → NEUTRAL。旧兜底默认
        BULLISH 会凭空捏造立场（live：共识 mixed 变 bullish action）。"""
        from types import SimpleNamespace

        from finer.pipeline.canonical_runner import _resolve_direction

        for d in ("mixed", "unknown"):
            intent = SimpleNamespace(direction=d)
            mapped = SimpleNamespace(action_hint="watch_only")
            assert _resolve_direction(intent, mapped).value == "neutral", d
