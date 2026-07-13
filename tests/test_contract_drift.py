"""Pin the pydantic ↔ contracts.ts enum contract, and prove the guard bites.

A green drift check is only worth anything if it actually fails on drift, so
this file pins BOTH directions: the live contracts are in sync, AND injected
mismatches are detected (parser purity, value diff, unmapped detection).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_contract_drift.py"
_spec = importlib.util.spec_from_file_location("check_contract_drift", _SCRIPT)
cd = importlib.util.module_from_spec(_spec)
sys.modules["check_contract_drift"] = cd
_spec.loader.exec_module(cd)


# ── Live contract is in sync ─────────────────────────────────────────────────


def test_live_contracts_have_no_enum_drift():
    drifts, unmapped = cd.check()
    assert drifts == [], f"pydantic ↔ contracts.ts enum drift: {drifts}"
    assert unmapped == [], (
        f"TS string-enums with no pydantic mapping (register in REGISTRY or "
        f"UI_ONLY_TS_ENUMS): {unmapped}"
    )


def test_every_registry_source_imports_and_yields_values():
    """A stale REGISTRY row (renamed/removed pydantic source) must fail loudly."""
    for ts_name, (module, attr, kind) in cd.REGISTRY.items():
        values = cd.python_enum_values(module, attr, kind)
        assert values, f"{ts_name} → {module}.{attr} produced no values"


# ── TS parser ────────────────────────────────────────────────────────────────


def test_parser_reads_single_and_multiline_unions():
    text = '''
export type Single = "a" | "b" | "c";
export type Multi =
  | "x"
  | "y";
export type LeadingPipe = | "p" | "q";
'''
    enums = cd.parse_ts_enums(text)
    assert enums["Single"] == {"a", "b", "c"}
    assert enums["Multi"] == {"x", "y"}
    assert enums["LeadingPipe"] == {"p", "q"}


def test_parser_skips_object_and_reference_types():
    text = '''
export type Obj = { a: string; b: number };
export type Ref = KOL & { extra: string };
export type Mixed = "a" | SomeType;
export type Pure = "keep" | "me";
'''
    enums = cd.parse_ts_enums(text)
    assert set(enums) == {"Pure"}


# ── Guard bites on drift ─────────────────────────────────────────────────────


def test_value_drift_is_detected(monkeypatch, tmp_path):
    """A TS union missing a pydantic value (and carrying a stray one) must
    surface as value_drift in both directions."""
    ts = tmp_path / "contracts.ts"
    # ValidationStatus pydantic = pending/verified/failed/under_review.
    ts.write_text(
        'export type TradeValidationStatus = "pending" | "verified" | "ghost";\n'
        # keep everything else registered but absent → ts_type_missing, which we
        # filter to isolate the value-drift assertion below.
        'export type TradeDirection = "bullish" | "bearish" | "neutral";\n'
    )
    monkeypatch.setattr(cd, "CONTRACTS_TS", ts)
    monkeypatch.setattr(cd, "REGISTRY", {
        "TradeValidationStatus": ("finer.schemas.trade_action", "ValidationStatus", "enum"),
    })
    drifts, _ = cd.check()
    assert len(drifts) == 1
    d = drifts[0]
    assert d["issue"] == "value_drift"
    assert "failed" in d["missing_in_ts"] and "under_review" in d["missing_in_ts"]
    assert d["extra_in_ts"] == ["ghost"]


def test_missing_ts_type_is_detected(monkeypatch, tmp_path):
    ts = tmp_path / "contracts.ts"
    ts.write_text('export type Unrelated = "x";\n')
    monkeypatch.setattr(cd, "CONTRACTS_TS", ts)
    monkeypatch.setattr(cd, "REGISTRY", {
        "TradeDirection": ("finer.schemas.trade_action", "TradeDirection", "enum"),
    })
    drifts, _ = cd.check()
    assert len(drifts) == 1
    assert drifts[0]["issue"] == "ts_type_missing"


def test_unmapped_ts_enum_is_reported(monkeypatch, tmp_path):
    ts = tmp_path / "contracts.ts"
    ts.write_text('export type BrandNewEnum = "a" | "b";\n')
    monkeypatch.setattr(cd, "CONTRACTS_TS", ts)
    monkeypatch.setattr(cd, "REGISTRY", {})
    monkeypatch.setattr(cd, "UI_ONLY_TS_ENUMS", set())
    drifts, unmapped = cd.check()
    assert drifts == []
    assert unmapped == ["BrandNewEnum"]


def test_stale_registry_source_raises(monkeypatch, tmp_path):
    ts = tmp_path / "contracts.ts"
    ts.write_text('export type X = "a";\n')
    monkeypatch.setattr(cd, "CONTRACTS_TS", ts)
    monkeypatch.setattr(cd, "REGISTRY", {
        "X": ("finer.schemas.trade_action", "NoSuchAttr", "enum"),
    })
    with pytest.raises(cd.DriftError):
        cd.check()
