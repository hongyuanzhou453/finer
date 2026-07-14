"""F4 policy tunable surface — loads ``configs/skills/f3f4-policy.yaml``.

Externalizes the previously-hardcoded F4 risk/exit thresholds
(``global_base.py::compute_risk_constraints``) so they can be tuned without a
code change, and layered per declared trading style. **Defaults mirror the
historical hardcoded values**, so an absent / empty / invalid config is a no-op
(behavior unchanged). This is the "make the surface real" foundation for
P2#8 style-layered exit rules — see ``configs/skills/README.md`` for the
migration protocol and ``docs/specs/2026-06-30-self-evolving-skill-pattern.md``
(M3).

Layering model
--------------
``base`` exit rules apply universally (GlobalBase, Layer 0 — style-independent).
``by_style`` maps a declared ``entry_style`` (left_side / right_side / mixed /
unknown) to a **partial** override; missing fields fall back to base. An empty
``by_style`` (the shipped default) means every style resolves to base, so the
overlay is inert until someone tunes a style.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

from finer.paths import REPO_ROOT

logger = logging.getLogger(__name__)

# Historical hardcoded defaults (global_base.py::compute_risk_constraints).
# Keep these EXACTLY equal to the pre-migration literals — a regression test
# pins config == old value so wiring never silently shifts behavior.
_DEFAULT_STOP_LOSS_PCT: float = -0.10
_DEFAULT_TAKE_PROFIT_PCT: float = 0.20
_DEFAULT_MAX_HOLDING_DAYS: int = 30
_DEFAULT_HUMAN_REVIEW_BELOW: float = 0.3
_DEFAULT_RISK_NOTE_BELOW: float = 0.4
# Conviction thresholds for position sizing bands (global_base _CONVICTION_BANDS).
_DEFAULT_SMALL_AT: float = 0.35
_DEFAULT_MEDIUM_AT: float = 0.70

_CONFIG_PATH = REPO_ROOT / "configs" / "skills" / "f3f4-policy.yaml"


@dataclass(frozen=True)
class ExitRuleHints:
    """Numeric exit-rule hints for downstream (F8 per-action) simulation.

    Sign contract mirrors ``PolicyRiskConstraints``: stop_loss < 0,
    take_profit > 0, max_holding_days > 0.
    """

    stop_loss_pct: float = _DEFAULT_STOP_LOSS_PCT
    take_profit_pct: float = _DEFAULT_TAKE_PROFIT_PCT
    max_holding_days: int = _DEFAULT_MAX_HOLDING_DAYS


@dataclass(frozen=True)
class PolicyTuning:
    """Resolved F4 tunable surface (base + per-style overrides + risk flags)."""

    base_exit: ExitRuleHints = field(default_factory=ExitRuleHints)
    # style_label -> fully-resolved exit hints (base already overlaid).
    by_style: Dict[str, ExitRuleHints] = field(default_factory=dict)
    human_review_below: float = _DEFAULT_HUMAN_REVIEW_BELOW
    risk_note_below: float = _DEFAULT_RISK_NOTE_BELOW
    small_at: float = _DEFAULT_SMALL_AT
    medium_at: float = _DEFAULT_MEDIUM_AT

    def exit_hints_for_style(self, style_label: Optional[str]) -> ExitRuleHints:
        """Return the exit hints for ``style_label``, falling back to base."""
        if style_label and style_label in self.by_style:
            return self.by_style[style_label]
        return self.base_exit

    def conviction_bands(self):
        """Position-sizing bands as ascending (threshold, hint) pairs.

        GlobalBase NEVER outputs 'large' — that requires higher layers — so the
        bands stop at 'medium'. Mirrors the historical _CONVICTION_BANDS.
        """
        return [(0.0, "none"), (self.small_at, "small"), (self.medium_at, "medium")]


def _coerce_exit(base: ExitRuleHints, raw: object, *, where: str) -> ExitRuleHints:
    """Overlay a raw dict onto ``base``, validating the sign contract.

    Any missing or invalid field falls back to ``base`` (with a warning) so a
    malformed config degrades to safe defaults instead of crashing F4.
    """
    if not isinstance(raw, dict):
        return base

    def _num(key: str, base_val, *, want_negative=False, want_positive=False, as_int=False):
        if key not in raw or raw[key] is None:
            return base_val
        try:
            val = int(raw[key]) if as_int else float(raw[key])
        except (TypeError, ValueError):
            logger.warning("f3f4-policy: %s.%s=%r not numeric; using base %r", where, key, raw[key], base_val)
            return base_val
        if want_negative and not val < 0:
            logger.warning("f3f4-policy: %s.%s=%r must be < 0; using base %r", where, key, val, base_val)
            return base_val
        if want_positive and not val > 0:
            logger.warning("f3f4-policy: %s.%s=%r must be > 0; using base %r", where, key, val, base_val)
            return base_val
        return val

    return ExitRuleHints(
        stop_loss_pct=_num("stop_loss_pct", base.stop_loss_pct, want_negative=True),
        take_profit_pct=_num("take_profit_pct", base.take_profit_pct, want_positive=True),
        max_holding_days=_num("max_holding_days", base.max_holding_days, want_positive=True, as_int=True),
    )


def _parse(cfg_path: Path) -> PolicyTuning:
    if not cfg_path.exists():
        return PolicyTuning()
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — a bad config must not break F4
        logger.warning("f3f4-policy: unreadable (%s); using hardcoded defaults", exc)
        return PolicyTuning()

    f4 = raw.get("f4_policy") or {}

    exit_rules = f4.get("exit_rules") or {}
    base = _coerce_exit(ExitRuleHints(), exit_rules.get("base"), where="exit_rules.base")
    by_style_raw = exit_rules.get("by_style") or {}
    by_style: Dict[str, ExitRuleHints] = {}
    if isinstance(by_style_raw, dict):
        for style_label, override in by_style_raw.items():
            by_style[str(style_label)] = _coerce_exit(
                base, override, where=f"exit_rules.by_style.{style_label}"
            )

    risk_flags = f4.get("risk_flags") or {}

    def _flag(key: str, default: float) -> float:
        if key not in risk_flags or risk_flags[key] is None:
            return default
        try:
            return float(risk_flags[key])
        except (TypeError, ValueError):
            logger.warning("f3f4-policy: risk_flags.%s=%r not numeric; using %r", key, risk_flags[key], default)
            return default

    bands = f4.get("position_sizing_bands") or {}

    def _band(key: str, default: float) -> float:
        if key not in bands or bands[key] is None:
            return default
        try:
            val = float(bands[key])
        except (TypeError, ValueError):
            logger.warning("f3f4-policy: position_sizing_bands.%s=%r not numeric; using %r", key, bands[key], default)
            return default
        if not 0.0 <= val <= 1.0:
            logger.warning("f3f4-policy: position_sizing_bands.%s=%r out of [0,1]; using %r", key, val, default)
            return default
        return val

    small_at = _band("small_at", _DEFAULT_SMALL_AT)
    medium_at = _band("medium_at", _DEFAULT_MEDIUM_AT)
    if not small_at < medium_at:
        logger.warning(
            "f3f4-policy: position_sizing_bands small_at=%r must be < medium_at=%r; using defaults",
            small_at, medium_at,
        )
        small_at, medium_at = _DEFAULT_SMALL_AT, _DEFAULT_MEDIUM_AT

    return PolicyTuning(
        base_exit=base,
        by_style=by_style,
        human_review_below=_flag("human_review_below", _DEFAULT_HUMAN_REVIEW_BELOW),
        risk_note_below=_flag("risk_note_below", _DEFAULT_RISK_NOTE_BELOW),
        small_at=small_at,
        medium_at=medium_at,
    )


_cache: Optional[PolicyTuning] = None


def load_policy_tuning(path: Optional[Path] = None, *, use_cache: bool = True) -> PolicyTuning:
    """Load the F4 tunable surface (cached for the default path).

    Args:
        path: override config path (tests). Bypasses the cache when set.
        use_cache: reuse the process-wide parse for the default path.
    """
    global _cache
    if path is not None:
        return _parse(path)
    if use_cache and _cache is not None:
        return _cache
    tuning = _parse(_CONFIG_PATH)
    if use_cache:
        _cache = tuning
    return tuning


def reset_cache() -> None:
    """Drop the cached tuning (tests / after editing the config)."""
    global _cache
    _cache = None
