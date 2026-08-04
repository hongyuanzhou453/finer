#!/usr/bin/env python3
"""重建读模型投影（PROJ-1 薄壳 CLI）。

    python scripts/materialize_projections.py

投影 = data/projections.sqlite3，可随时重建，删掉不丢任何真值。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.projections.materializer import materialize_projections  # noqa: E402


def main() -> int:
    counts = materialize_projections(REPO_ROOT / "data")
    for key, value in counts.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
