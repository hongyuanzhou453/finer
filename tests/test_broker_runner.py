"""C2 — pipeline.broker_runner: the canonical home of the bri_* F4→F5 drive.

Pins the hoisted executor end-to-end on a tmp data_root:
  * dry-run plans without writing;
  * execute writes bri_{content_id}_actions.json + F4 sidecars + grounded
    F2 evidence sidecars (persist_dir root-cause fix stays wired);
  * rerun is intent-level idempotent (already_actioned skip, no duplicates);
  * unparseable envelopes are counted, never fatal.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple

import pytest

from finer.pipeline.broker_runner import (
    BrokerDriveReport,
    load_pending_by_envelope,
    run_broker_declarative_f5,
)
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.quality import QualityCard

_PUBLISHED_AT = datetime(2026, 3, 12, 15, 36, tzinfo=timezone(timedelta(hours=8)))
CONTENT_ID = "broker_runner_test001"


def _pass_card() -> QualityCard:
    return QualityCard(
        readability_score=0.95,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.95,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.85,
        evidence_traceability_score=0.9,
    )


def _anchor(symbol: str, raw_text: str, span_id: str) -> Tuple[EntityAnchor, EvidenceSpan]:
    span = EvidenceSpan(
        evidence_span_id=span_id,
        block_id="b0",
        char_start=0,
        char_end=max(1, len(raw_text)),
        text=raw_text,
        span_type="entity",
        confidence=1.0,
    )
    anchor = EntityAnchor(
        entity_type="stock",
        raw_text=raw_text,
        resolved_symbol=symbol,
        market="CN",
        confidence=1.0,
        evidence_span_id=span_id,
        metadata={"evidence_span_ids": [span_id]},
    )
    return anchor, span


def _envelope() -> ContentEnvelope:
    a1, s1 = _anchor("300750.SZ", "宁德时代", "f2-span-target")
    block = ContentBlock(
        block_id="b0",
        block_type="paragraph",
        text="宁德时代维持买入评级。",
        order=0,
        quality_card=_pass_card(),
        evidence_spans=[s1],
    )
    return ContentEnvelope(
        envelope_id="env-broker-runner-001",
        source_type="feishu_doc",
        creator_id="高盛",
        published_at=_PUBLISHED_AT,
        quality_card=_pass_card(),
        blocks=[block],
        entity_anchors=[a1],
        temporal_anchors=[],
    )


def _bri_intent() -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id="bri_test0000000000000000001",
        envelope_id="env-broker-runner-001",
        block_ids=["b0"],
        creator_id="高盛",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="recommendation",
        position_delta_hint="none",
        conviction=0.8,
        confidence=0.9,
        evidence_span_ids=["span-f3-self"],  # F3 self-span; F2 grounding re-derives
        ambiguity_flags=[],
    )


class _FakeRepo:
    def __init__(self) -> None:
        self.indexed: List[Tuple[str, str]] = []

    def index_trade_action(self, action, filepath: str) -> None:
        self.indexed.append((action.trade_action_id, filepath))


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    (tmp_path / "F3_intents").mkdir()
    (tmp_path / "F2_anchored").mkdir()
    (tmp_path / "F5_executed").mkdir()
    (tmp_path / "F3_intents" / "bri_test.json").write_text(
        _bri_intent().model_dump_json(indent=2), encoding="utf-8"
    )
    (tmp_path / "F2_anchored" / f"{CONTENT_ID}.json").write_text(
        _envelope().model_dump_json(indent=2), encoding="utf-8"
    )
    return tmp_path


@pytest.mark.asyncio
async def test_dry_run_plans_without_writing(data_root: Path):
    report = await run_broker_declarative_f5(data_root, execute=False)

    assert report.executed is False
    assert report.intents_seen == 1
    assert report.bridged == 1
    assert report.planned == {"env-broker-runner-001": 1}
    assert list((data_root / "F5_executed").iterdir()) == []
    assert not (data_root / "F4_policy_mapped").exists()


@pytest.mark.asyncio
async def test_execute_writes_actions_f4_and_evidence_sidecars(data_root: Path):
    repo = _FakeRepo()
    report = await run_broker_declarative_f5(
        data_root, execute=True, repo=repo, update_stage_status=False
    )

    assert report.executed is True
    assert report.actions_written >= 1
    assert report.f4_written >= 1
    assert repo.indexed, "actions must be indexed"

    out_path = data_root / "F5_executed" / f"bri_{CONTENT_ID}_actions.json"
    assert out_path.is_file()
    actions = json.loads(out_path.read_text(encoding="utf-8"))["actions"]
    assert len(actions) == report.actions_written

    # persist_dir root-cause fix stays wired: every referenced span resolves.
    for action in actions:
        assert action["evidence_span_ids"], "grounded evidence required"
        for span_id in action["evidence_span_ids"]:
            assert (data_root / "F2_evidence" / f"{span_id}.json").is_file()

    # F4 sidecar per policy_id (audit_assembler contract).
    for action in actions:
        assert (
            data_root / "F4_policy_mapped" / f"{action['policy_id']}.json"
        ).is_file()


@pytest.mark.asyncio
async def test_rerun_is_intent_level_idempotent(data_root: Path):
    repo = _FakeRepo()
    first = await run_broker_declarative_f5(
        data_root, execute=True, repo=repo, update_stage_status=False
    )
    second = await run_broker_declarative_f5(
        data_root, execute=True, repo=repo, update_stage_status=False
    )

    assert second.actions_written == 0
    assert second.skips.get("already_actioned") == 1

    out_path = data_root / "F5_executed" / f"bri_{CONTENT_ID}_actions.json"
    actions = json.loads(out_path.read_text(encoding="utf-8"))["actions"]
    assert len(actions) == first.actions_written  # merged, not duplicated


def test_unparseable_envelope_is_counted_not_fatal(data_root: Path):
    (data_root / "F2_anchored" / "broker_bad.json").write_text(
        "{not json", encoding="utf-8"
    )
    per_env, _envs, report = load_pending_by_envelope(data_root)

    assert report.skips.get("envelope_parse_error") == 1
    assert per_env, "the healthy envelope still drives"


def test_content_ids_scope_narrows_without_skip_noise(data_root: Path):
    report = BrokerDriveReport()
    per_env, _envs, report = load_pending_by_envelope(
        data_root, content_ids={"no_such_content"}, report=report
    )

    assert per_env == {}
    # The intent targeting an out-of-scope envelope is not a "skip" — it is
    # simply outside this run's scope (driver routes one content at a time).
    assert "no_envelope" not in report.skips
