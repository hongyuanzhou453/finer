"""Single-constructor guard: TradeAction() may only be called in three places.

The F5 truth-source collar (docs/specs/2026-07-11-architecture-priorities.md
P0-1) requires every production TradeAction to be assembled by
``extraction/action_composer.compose_trade_action``. Hand-rolled construction
sites drifted from the canonical contract twice before (ADD/REDUCE collapse,
dropped style/exit metadata). This AST test fails loudly when a new
``TradeAction(...)`` call appears outside the allowlist.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "finer"

# The only files allowed to CALL TradeAction(...):
#  - action_composer.py: the single canonical constructor
#  - trade_action_extractor.py: quarantined legacy path (see
#    test_legacy_quarantine.py; must not gain new importers)
ALLOWED_CALLERS = {
    SRC_DIR / "extraction" / "action_composer.py",
    SRC_DIR / "extraction" / "trade_action_extractor.py",
}


def _trade_action_calls(path: Path) -> list[int]:
    """Return line numbers of TradeAction(...) call sites in a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover — broken file fails elsewhere
        return []
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name == "TradeAction":
            lines.append(node.lineno)
    return lines


def test_trade_action_constructed_only_in_composer():
    violations: dict[str, list[int]] = {}
    for path in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        if path in ALLOWED_CALLERS:
            continue
        # The schema module defines the class; a Call node for the class name
        # cannot appear in its own definition, but guard anyway for clarity.
        if path == SRC_DIR / "schemas" / "trade_action.py":
            continue
        lines = _trade_action_calls(path)
        if lines:
            violations[str(path.relative_to(SRC_DIR))] = lines
    assert violations == {}, (
        "TradeAction() constructed outside the canonical composer — delegate "
        f"to extraction/action_composer.compose_trade_action instead: {violations}"
    )


def test_allowed_callers_exist():
    """Allowlist entries must stay real files (catch renames silently widening the net)."""
    for path in ALLOWED_CALLERS:
        assert path.exists(), f"single-constructor allowlist entry vanished: {path}"
