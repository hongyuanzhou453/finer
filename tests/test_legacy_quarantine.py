"""Quarantine test: ensure deprecated/legacy modules are not imported by active code."""
import ast
import os
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src" / "finer"

DEPRECATED_MODULES = {
    "finer.parsing.content_standardizer",
    "finer.parsing.vision_extractor",
    "finer.parsing.audio_extractor",
    "finer.parsing.sentiment_enricher",
    "finer.parsing.slang",
    "finer.parsing.context_summarizer",
    "finer.schemas.segment",
    "finer.extraction.trade_action_extractor",
}

# Map deprecated module names to their source file paths (relative to src/finer)
DEPRECATED_MODULE_PATHS = {
    "finer.parsing.content_standardizer": "parsing/content_standardizer.py",
    "finer.parsing.vision_extractor": "parsing/vision_extractor.py",
    "finer.parsing.audio_extractor": "parsing/audio_extractor.py",
    "finer.parsing.sentiment_enricher": "parsing/sentiment_enricher.py",
    "finer.parsing.slang": "parsing/slang.py",
    "finer.parsing.context_summarizer": "parsing/context_summarizer.py",
    "finer.schemas.segment": "schemas/segment.py",
    "finer.extraction.trade_action_extractor": "extraction/trade_action_extractor.py",
}

# Files allowed to import deprecated modules:
#   1. Deprecated modules themselves (self-imports)
#   2. Known legacy consumers that have not yet been migrated
#   3. Test files (handled separately via path check)
ALLOWED_IMPORTERS: set[str] = set()
for _rel_path in DEPRECATED_MODULE_PATHS.values():
    ALLOWED_IMPORTERS.add(str(SRC_DIR / _rel_path))

# Known legacy consumers that haven't been migrated yet.
# 2026-07-11 tightening: services.lineage and api.routes.extraction no longer
# import any deprecated module — do not re-add them without a migration
# reason. action_interpreter (schemas.segment) and services.perception
# (parsing.slang) still consume non-extractor deprecated modules.
ALLOWED_IMPORTERS.add(str(SRC_DIR / "extraction" / "action_interpreter.py"))
ALLOWED_IMPORTERS.add(str(SRC_DIR / "services" / "perception.py"))
ALLOWED_IMPORTERS.add(str(SRC_DIR / "pipeline" / "orchestrator.py"))
ALLOWED_IMPORTERS.add(str(SRC_DIR / "parsing" / "__init__.py"))


def _is_test_file(filepath: Path) -> bool:
    """Check if a file lives under a tests/ directory."""
    parts = filepath.parts
    return "tests" in parts


def _collect_python_files(root: Path) -> list[Path]:
    """Collect all .py files under src/finer, excluding __pycache__."""
    return [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]


def _get_imports(filepath: Path) -> list[str]:
    """Parse a Python file and extract imported module names."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


@pytest.mark.parametrize("deprecated_mod", sorted(DEPRECATED_MODULES))
def test_no_new_imports_of_deprecated_modules(deprecated_mod: str) -> None:
    """Verify that deprecated modules are only imported by other deprecated/allowed code."""
    violations: list[str] = []

    for pyfile in _collect_python_files(SRC_DIR):
        # Skip files that are explicitly allowed
        if str(pyfile) in ALLOWED_IMPORTERS:
            continue
        # Skip test files anywhere in the tree
        if _is_test_file(pyfile):
            continue

        imports = _get_imports(pyfile)
        if deprecated_mod in imports:
            violations.append(str(pyfile.relative_to(SRC_DIR.parent.parent)))

    if violations:
        pytest.fail(
            f"Deprecated module '{deprecated_mod}' is imported by non-deprecated code:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
