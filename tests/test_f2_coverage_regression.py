"""F2 coverage regression gate against local dry-run artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_f2_coverage_regression import check_scopes


def test_f2_backfill_coverage_does_not_regress_on_local_data():
    data_root = Path("data")
    if not (data_root / "F1_standardized").exists():
        pytest.skip("local F1 standardized data is not available")

    results = check_scopes(data_root, ["curated-pdf", "all-local"])
    failures = {
        result.scope: result.failures
        for result in results
        if result.failures
    }

    assert failures == {}
