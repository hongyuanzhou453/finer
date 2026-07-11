"""Tests for RLHF pipeline-version anchoring (Batch D1).

Covers rlhf_assembler.build_pipeline_snapshot / action_to_extraction_dict and
the server-side enrichment in POST /api/rlhf/submit.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    ExecutionTiming,
    SourceInfo,
    TargetInfo,
    TradeDirection,
    TriggerType,
)
from finer.extraction.action_composer import compose_trade_action
from finer.services.rlhf_assembler import (
    action_to_extraction_dict,
    build_pipeline_snapshot,
)
from finer.services.versioning import CURRENT_PROMPT_VERSION, CURRENT_SCHEMA_VERSION


def _stamped_action(extractor_version: str | None = "llm_consensus_v1"):
    intent = NormalizedInvestmentIntent(
        intent_id="intent-1",
        envelope_id="env-1",
        block_ids=["b-1"],
        creator_id="k1",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.8,
        confidence=0.9,
    )
    mapped = PolicyMappedIntent(
        intent_id="intent-1",
        policy_id="pol-1",
        original_intent_summary="test",
        action_hint="add_position",
        position_sizing_hint="small",
        holding_period_hint="medium_term",
        mapping_confidence=0.7,
        created_at=datetime(2026, 7, 1),
    )
    now = datetime(2026, 7, 1, 10, 0)
    timing = ExecutionTiming(
        intent_published_at=now,
        action_decision_at=now,
        action_executable_at=now,
        market="CN",
        timezone="Asia/Shanghai",
        timing_policy_id="test-policy",
    )
    return compose_trade_action(
        intent=intent,
        policy_mapped_intent=mapped,
        evidence_span_ids=["span-1"],
        execution_timing=timing,
        source=SourceInfo(content_id="env-1", evidence_text="回调就是上车机会", creator_id="k1"),
        target=TargetInfo(ticker="300750.SZ", market="CN"),
        direction=TradeDirection.BULLISH,
        action_chain=[
            ActionStep(sequence=1, action_type=ActionType.ADD, trigger_type=TriggerType.MANUAL)
        ],
        rationale="看多 300750.SZ · add_position",
        extractor_version=extractor_version,
        f5_strategy="programmatic",
    )


class TestActionToExtractionDict:
    def test_includes_evidence_text(self):
        """DPO export requires evidence_text — the bootstrap must carry it."""
        d = action_to_extraction_dict(_stamped_action())
        assert d["evidence_text"] == "回调就是上车机会"
        assert d["ticker"] == "300750.SZ"
        assert d["direction"] == "bullish"
        assert d["action_chain"][0]["action_type"] == "add"


class TestBuildPipelineSnapshot:
    def test_stamped_action_full_anchor(self, tmp_path):
        wrapper = tmp_path / "c1_actions.json"
        wrapper.write_text(
            json.dumps({"model": "canonical-f2-envelope", "actions": []}),
            encoding="utf-8",
        )
        snap = build_pipeline_snapshot(_stamped_action(), str(wrapper))
        assert snap.f5_model == "canonical-f2-envelope"
        assert snap.extractor_version == "llm_consensus_v1"
        assert snap.schema_version == "1.0"
        assert snap.config_hash  # composer stamped version_info
        assert snap.trade_action_source_file == str(wrapper)
        assert snap.action_snapshot["evidence_text"] == "回调就是上车机会"

    def test_unstamped_action_falls_back_to_current_constants(self):
        action = _stamped_action(extractor_version=None)
        action.version_info = None  # simulate legacy unstamped action
        snap = build_pipeline_snapshot(action, None)
        assert snap.extractor_version == "v1.0"  # honest unstamped marker
        assert snap.prompt_version == CURRENT_PROMPT_VERSION
        assert snap.schema_version == CURRENT_SCHEMA_VERSION
        assert snap.config_hash is None
        assert snap.f5_model is None

    def test_unreadable_wrapper_never_raises(self, tmp_path):
        snap = build_pipeline_snapshot(_stamped_action(), str(tmp_path / "missing.json"))
        assert snap.f5_model is None  # best-effort, submit must not block


class TestSubmitEnrichment:
    @pytest.fixture()
    def rlhf_env(self, tmp_path, monkeypatch):
        """Redirect the rlhf route's storage and repository to tmp."""
        import finer.api.routes.rlhf as rlhf_route

        rlhf_dir = tmp_path / "rlhf"
        monkeypatch.setattr(rlhf_route, "RLHF_DIR", rlhf_dir)
        monkeypatch.setattr(rlhf_route, "FEEDBACKS_DIR", rlhf_dir / "feedbacks")
        monkeypatch.setattr(rlhf_route, "INDEX_PATH", rlhf_dir / "index.json")

        action = _stamped_action()
        wrapper_file = tmp_path / "F5" / "c1_actions.json"
        wrapper_file.parent.mkdir(parents=True)
        wrapper_file.write_text(
            json.dumps(
                {"model": "canonical-f2-envelope", "actions": [action.model_dump(mode="json")]},
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

        class FakeDB:
            def get_by_id(self, trade_action_id):
                if trade_action_id == action.trade_action_id:
                    return {"file_path": str(wrapper_file)}
                return None

        class FakeRepo:
            db = FakeDB()

            def load(self, trade_action_id):
                return action if trade_action_id == action.trade_action_id else None

        import finer.services.repository as repository_module

        monkeypatch.setattr(repository_module, "TradeActionRepository", lambda: FakeRepo())
        return rlhf_route, action

    @pytest.mark.asyncio
    async def test_submit_backfills_snapshot_and_original(self, rlhf_env):
        rlhf_route, action = rlhf_env
        body = rlhf_route.RLHFFeedbackCreate(
            trade_action_id=action.trade_action_id,
            rating=2,
            flagged_as_error=True,
        )
        result = await rlhf_route.submit_feedback(body)
        saved = json.loads(
            (rlhf_route.FEEDBACKS_DIR / f"{result['feedback_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        snap = saved["pipeline_snapshot"]
        assert snap["f5_model"] == "canonical-f2-envelope"
        assert snap["extractor_version"] == "llm_consensus_v1"
        # original_extraction bootstrapped server-side, with evidence_text.
        assert saved["original_extraction"]["evidence_text"] == "回调就是上车机会"
        # flagged_as_error + bootstrap => trainable preference pair.
        assert saved["preference"]["is_original_correct"] is False

    @pytest.mark.asyncio
    async def test_submit_survives_unknown_action(self, rlhf_env):
        rlhf_route, _action = rlhf_env
        body = rlhf_route.RLHFFeedbackCreate(trade_action_id="ta-ghost", rating=4)
        result = await rlhf_route.submit_feedback(body)
        saved = json.loads(
            (rlhf_route.FEEDBACKS_DIR / f"{result['feedback_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        assert saved["pipeline_snapshot"] is None  # degraded, not blocked
