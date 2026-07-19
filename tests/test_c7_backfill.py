"""Tests for the bri signal_class + F4 backfill (C7 plan A).

Exercises the execute path on a tmp corpus: backup, signal_class set (ids
preserved), F4 artifact written under the action's existing policy_id, idempotent
re-run. No real data touched — module dir constants are monkeypatched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.backfill_bri_signal_class_f4 as bf
from finer.schemas.investment_intent import NormalizedInvestmentIntent


def _write_corpus(root: Path) -> tuple[str, str]:
    (root / "F3_intents").mkdir(parents=True)
    (root / "F5_executed").mkdir(parents=True)
    intent = NormalizedInvestmentIntent(
        intent_id="bri_test01",
        envelope_id="broker_env",
        block_ids=["b1"],
        creator_id="高盛",
        target_type="stock",
        target_name="宁德时代",
        target_symbol="300750.SZ",
        market="CN",
        direction="bullish",
        actionability="recommendation",
        position_delta_hint="add",
        conviction=0.6,
        confidence=0.75,
    )
    (root / "F3_intents" / "bri_test01.json").write_text(
        intent.model_dump_json(indent=2), encoding="utf-8"
    )
    policy_id = "11111111-2222-3333-4444-555555555555"
    action = {"trade_action_id": "ta_1", "intent_id": "bri_test01", "policy_id": policy_id}
    (root / "F5_executed" / "bri_broker_env_actions.json").write_text(
        json.dumps({"model": "canonical-programmatic-bri", "actions": [action]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return "bri_test01", policy_id


@pytest.fixture()
def tmp_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(bf, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(bf, "F3_DIR", tmp_path / "F3_intents")
    monkeypatch.setattr(bf, "F4_DIR", tmp_path / "F4_policy_mapped")
    monkeypatch.setattr(bf, "F5_DIR", tmp_path / "F5_executed")
    intent_id, policy_id = _write_corpus(tmp_path)
    return tmp_path, intent_id, policy_id


def test_dry_run_writes_nothing(tmp_corpus) -> None:
    root, _, policy_id = tmp_corpus
    r = bf.backfill(execute=False)
    assert r.actions_scanned == 1 and r.signal_class_set == 1 and r.f4_written == 1
    assert r.signal_class_dist["broker_recommendation"] == 1
    # nothing on disk changed
    assert not (root / "F4_policy_mapped").exists()
    action = json.loads((root / "F5_executed" / "bri_broker_env_actions.json").read_text())["actions"][0]
    assert "signal_class" not in action


def test_execute_backfills_and_preserves_ids(tmp_corpus) -> None:
    root, _, policy_id = tmp_corpus
    r = bf.backfill(execute=True)
    assert r.backup_path and Path(r.backup_path).is_dir()  # F5 backed up first
    assert r.signal_class_set == 1 and r.f4_written == 1 and r.failed == 0

    doc = json.loads((root / "F5_executed" / "bri_broker_env_actions.json").read_text())
    action = doc["actions"][0]
    assert action["signal_class"] == "broker_recommendation"
    assert action["policy_id"] == policy_id  # id preserved
    assert action["trade_action_id"] == "ta_1"  # id preserved

    # F4 artifact written under the action's existing policy_id (audit join key)
    f4 = root / "F4_policy_mapped" / f"{policy_id}.json"
    assert f4.exists()
    from finer.schemas.policy import PolicyMappingResult

    pmr = PolicyMappingResult.model_validate_json(f4.read_text())
    assert pmr.policy_id == policy_id


def test_execute_is_idempotent(tmp_corpus) -> None:
    bf.backfill(execute=True)
    r2 = bf.backfill(execute=True)
    assert r2.signal_class_already == 1 and r2.signal_class_set == 0 and r2.failed == 0
