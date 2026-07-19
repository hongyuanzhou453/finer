"""C8 — three-way trace-integrity audit.

Two layers:
  * logic tests on a tmp fixture (CI-safe) — the audit detects each break type
    and computes rates correctly;
  * a threshold guard on the real data root (skipped when the data isn't present,
    e.g. a fresh CI checkout) — intent/policy MUST stay 100% (regression guard);
    evidence has a documented floor that C9's F2 re-anchor raises to 100%.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.audit_trace_integrity as ati
from finer.paths import DATA_ROOT

# Thresholds — set to the post-C7 reality. C9 (F2 re-anchor + re-drive) raises
# EVIDENCE_MIN to 1.0 once every action's evidence spans resolve.
INTENT_MIN = 1.0
POLICY_MIN = 1.0
EVIDENCE_MIN = 0.05  # current ~6.6%; C9 → 1.0


# ---------------------------------------------------------------------------
# Logic tests (tmp fixture)
# ---------------------------------------------------------------------------


def _build_fixture(root: Path) -> None:
    for sub in ("F3_intents", "F4_policy_mapped", "F2_evidence", "F5_executed"):
        (root / sub).mkdir(parents=True)
    (root / "F3_intents" / "i_ok.json").write_text("{}", encoding="utf-8")
    (root / "F4_policy_mapped" / "p_ok.json").write_text("{}", encoding="utf-8")
    (root / "F2_evidence" / "s_ok.json").write_text("{}", encoding="utf-8")

    actions = [
        {"trade_action_id": "a_intact", "intent_id": "i_ok", "policy_id": "p_ok", "evidence_span_ids": ["s_ok"]},
        {"trade_action_id": "a_f3missing", "intent_id": "i_missing", "policy_id": "p_ok", "evidence_span_ids": ["s_ok"]},
        {"trade_action_id": "a_f4missing", "intent_id": "i_ok", "policy_id": "p_missing", "evidence_span_ids": ["s_ok"]},
        {"trade_action_id": "a_evmissing", "intent_id": "i_ok", "policy_id": "p_ok", "evidence_span_ids": ["s_ok", "s_missing"]},
        {"trade_action_id": "a_noids", "evidence_span_ids": []},
    ]
    (root / "F5_executed" / "batch_actions.json").write_text(
        json.dumps({"actions": actions}, ensure_ascii=False), encoding="utf-8"
    )


def test_audit_detects_each_break_type(tmp_path: Path) -> None:
    _build_fixture(tmp_path)
    r = ati.audit_trace_integrity(tmp_path)

    assert r.total_actions == 5
    assert r.fully_intact == 1  # only a_intact
    assert r.intent_resolved == 3  # intact, f4missing, evmissing
    assert r.policy_resolved == 3  # intact, f3missing, evmissing
    assert r.evidence_all_resolved == 3  # intact, f3missing, f4missing (all have [s_ok])

    assert r.break_counts[ati.BREAK_F3_MISSING] == 1
    assert r.break_counts[ati.BREAK_F4_MISSING] == 1
    assert r.break_counts[ati.BREAK_F2_EVIDENCE_MISSING] == 1
    assert r.break_counts[ati.BREAK_MISSING_INTENT_ID] == 1
    assert r.break_counts[ati.BREAK_MISSING_POLICY_ID] == 1
    assert r.break_counts[ati.BREAK_MISSING_EVIDENCE_IDS] == 1

    broken = {b.action_id: b for b in r.broken}
    assert set(broken) == {"a_f3missing", "a_f4missing", "a_evmissing", "a_noids"}
    assert broken["a_evmissing"].detail["evidence_missing"] == 1
    assert broken["a_evmissing"].detail["evidence_total"] == 2


def test_audit_rates_and_json_roundtrip(tmp_path: Path) -> None:
    _build_fixture(tmp_path)
    r = ati.audit_trace_integrity(tmp_path)
    assert r.intent_rate == pytest.approx(3 / 5)
    assert r.policy_rate == pytest.approx(3 / 5)
    assert r.evidence_rate == pytest.approx(3 / 5)
    assert r.evidence_span_rate == pytest.approx(4 / 5)  # s_ok×4 resolve, s_missing×1 not

    d = r.to_dict()
    assert d["total_actions"] == 5 and d["fully_intact"] == 1
    assert d["rates"]["intent_resolve"] == pytest.approx(0.6)
    assert len(d["broken"]) == 4


def test_audit_missing_f5_dir_is_empty_report(tmp_path: Path) -> None:
    r = ati.audit_trace_integrity(tmp_path / "nope")
    assert r.total_actions == 0 and r.broken == []


def test_audit_skips_backup_dirs(tmp_path: Path) -> None:
    _build_fixture(tmp_path)
    # a stray backup dir must not be walked
    bak = tmp_path / "F5_executed" / "old.bak-20260101"
    bak.mkdir()
    (bak / "x_actions.json").write_text(json.dumps({"actions": [{"trade_action_id": "z"}]}), encoding="utf-8")
    r = ati.audit_trace_integrity(tmp_path)
    assert r.total_actions == 5  # backup dir's action not counted


# ---------------------------------------------------------------------------
# Threshold guard on real data (skips when data is absent)
# ---------------------------------------------------------------------------


def test_real_data_trace_completeness_thresholds() -> None:
    r = ati.audit_trace_integrity(DATA_ROOT)
    if r.total_actions == 0:
        pytest.skip("no F5 actions on disk (fresh checkout / CI without data)")
    # intent + policy must be fully resolvable — C7 guaranteed policy; a drop
    # here is a real regression (a new action with a missing F3/F4 artifact).
    assert r.intent_rate >= INTENT_MIN, f"intent resolve {r.intent_rate:.3f} < {INTENT_MIN}"
    assert r.policy_rate >= POLICY_MIN, f"policy resolve {r.policy_rate:.3f} < {POLICY_MIN}"
    # evidence has a known gap (broker F2 spans lack sidecars) — floor only until
    # C9 re-anchors and this tightens to 1.0.
    assert r.evidence_rate >= EVIDENCE_MIN, f"evidence resolve {r.evidence_rate:.3f} < {EVIDENCE_MIN}"
