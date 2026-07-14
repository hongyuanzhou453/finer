"""Tests for the F4 tunable surface loader (policy/policy_config.py)."""
from __future__ import annotations

import textwrap
from pathlib import Path

from finer.policy.policy_config import (
    ExitRuleHints,
    PolicyTuning,
    load_policy_tuning,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "f3f4-policy.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# --- defaults / regression ---------------------------------------------------

def test_defaults_when_file_absent(tmp_path):
    tuning = load_policy_tuning(path=tmp_path / "nope.yaml")
    assert tuning.base_exit == ExitRuleHints(-0.10, 0.20, 30)
    assert tuning.human_review_below == 0.3
    assert tuning.risk_note_below == 0.4
    assert tuning.by_style == {}


def test_shipped_config_base_equals_hardcoded():
    """Regression: the shipped YAML must mirror the pre-migration constants."""
    tuning = load_policy_tuning(use_cache=False)
    assert tuning.base_exit == ExitRuleHints(-0.10, 0.20, 30)
    assert tuning.human_review_below == 0.3
    assert tuning.risk_note_below == 0.4
    # Shipped default ships NO style overrides → overlay inert.
    assert tuning.by_style == {}


# --- base overrides ----------------------------------------------------------

def test_base_override(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          exit_rules:
            base:
              stop_loss_pct: -0.15
              take_profit_pct: 0.25
              max_holding_days: 45
    """)
    tuning = load_policy_tuning(path=p)
    assert tuning.base_exit == ExitRuleHints(-0.15, 0.25, 45)


def test_risk_flags_override(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          risk_flags:
            human_review_below: 0.25
            risk_note_below: 0.5
    """)
    tuning = load_policy_tuning(path=p)
    assert tuning.human_review_below == 0.25
    assert tuning.risk_note_below == 0.5


# --- by_style partial overlay ------------------------------------------------

def test_by_style_partial_override_falls_back_to_base(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          exit_rules:
            base:
              stop_loss_pct: -0.10
              take_profit_pct: 0.20
              max_holding_days: 30
            by_style:
              right_side:
                take_profit_pct: 0.30
                max_holding_days: 20
    """)
    tuning = load_policy_tuning(path=p)
    right = tuning.exit_hints_for_style("right_side")
    assert right.take_profit_pct == 0.30      # overridden
    assert right.max_holding_days == 20        # overridden
    assert right.stop_loss_pct == -0.10        # fell back to base
    # Unknown style → base
    assert tuning.exit_hints_for_style("left_side") == tuning.base_exit
    assert tuning.exit_hints_for_style(None) == tuning.base_exit


# --- robustness: invalid values degrade to base ------------------------------

def test_invalid_values_fall_back_to_base(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          exit_rules:
            base:
              stop_loss_pct: 0.05      # invalid: must be < 0
              take_profit_pct: -0.20   # invalid: must be > 0
              max_holding_days: -5     # invalid: must be > 0
    """)
    tuning = load_policy_tuning(path=p)
    # All three fall back to the ExitRuleHints defaults (the historical values).
    assert tuning.base_exit == ExitRuleHints(-0.10, 0.20, 30)


def test_malformed_yaml_degrades_to_defaults(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("f4_policy: [not, a, mapping", encoding="utf-8")
    tuning = load_policy_tuning(path=p)
    assert tuning == PolicyTuning()


# --- position sizing bands ---------------------------------------------------

def test_position_bands_default_equals_hardcoded(tmp_path):
    tuning = load_policy_tuning(path=tmp_path / "nope.yaml")
    assert tuning.small_at == 0.35
    assert tuning.medium_at == 0.70
    assert tuning.conviction_bands() == [(0.0, "none"), (0.35, "small"), (0.70, "medium")]


def test_shipped_position_bands_equal_hardcoded():
    """Regression: shipped YAML bands mirror the pre-migration _CONVICTION_BANDS."""
    tuning = load_policy_tuning(use_cache=False)
    assert tuning.conviction_bands() == [(0.0, "none"), (0.35, "small"), (0.70, "medium")]


def test_position_bands_override(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          position_sizing_bands:
            small_at: 0.30
            medium_at: 0.60
    """)
    tuning = load_policy_tuning(path=p)
    assert tuning.conviction_bands() == [(0.0, "none"), (0.30, "small"), (0.60, "medium")]


def test_position_bands_invalid_order_falls_back(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          position_sizing_bands:
            small_at: 0.8
            medium_at: 0.4
    """)
    tuning = load_policy_tuning(path=p)
    # small_at !< medium_at → both revert to defaults
    assert tuning.small_at == 0.35 and tuning.medium_at == 0.70


def test_position_bands_out_of_range_falls_back(tmp_path):
    p = _write(tmp_path, """
        f4_policy:
          position_sizing_bands:
            small_at: 1.5
    """)
    tuning = load_policy_tuning(path=p)
    assert tuning.small_at == 0.35
