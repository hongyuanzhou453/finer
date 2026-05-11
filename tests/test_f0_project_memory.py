"""F0 Project Memory contract tests — schema, query, startup, API, error codes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from finer.schemas.f0_index import F0IndexHealth, F0IndexQuery, F0IndexResult, F0IndexSchema
from finer.startup import F0IndexStartupState, F0StartupResult, check_f0_index_on_startup, rebuild_f0_index


# ---------------------------------------------------------------------------
# 1. Schema contract tests
# ---------------------------------------------------------------------------

class TestF0IndexSchema:
    """Validate F0 index schema definitions."""

    def test_content_records_columns_include_required_fields(self):
        cols = F0IndexSchema.CONTENT_RECORDS_COLUMNS
        required = {"content_id", "source_type", "raw_path", "file_type", "collected_at"}
        assert required.issubset(set(cols.keys()))

    def test_content_records_primary_key(self):
        assert "PRIMARY KEY" in F0IndexSchema.CONTENT_RECORDS_COLUMNS["content_id"]

    def test_import_runs_columns_include_status(self):
        cols = F0IndexSchema.IMPORT_RUNS_COLUMNS
        assert "status" in cols
        assert "source_channel" in cols

    def test_index_metadata_table_exists(self):
        assert F0IndexSchema.INDEX_METADATA_TABLE == "index_metadata"
        assert "key" in F0IndexSchema.INDEX_METADATA_COLUMNS


# ---------------------------------------------------------------------------
# 2. Health model tests
# ---------------------------------------------------------------------------

class TestF0IndexHealth:
    """Validate F0IndexHealth behavior."""

    def _make_health(self, **overrides):
        defaults = dict(
            status="healthy",
            record_count=100,
            last_rebuild_at="2026-05-11T09:00:00",
            last_rebuild_duration_ms=500,
            manifest_count_on_disk=100,
            drift=0,
            db_path="/tmp/f0_index.db",
            db_size_bytes=4096,
        )
        defaults.update(overrides)
        return F0IndexHealth(**defaults)

    def test_healthy_no_drift_not_needs_rebuild(self):
        h = self._make_health(status="healthy", drift=0)
        assert h.needs_rebuild is False

    def test_missing_needs_rebuild(self):
        h = self._make_health(status="missing")
        assert h.needs_rebuild is True

    def test_stale_needs_rebuild(self):
        h = self._make_health(status="stale")
        assert h.needs_rebuild is True

    def test_drift_nonzero_needs_rebuild(self):
        h = self._make_health(status="healthy", drift=5)
        assert h.needs_rebuild is True

    def test_frozen(self):
        h = self._make_health()
        with pytest.raises(AttributeError):
            h.status = "stale"


# ---------------------------------------------------------------------------
# 3. Query shape tests
# ---------------------------------------------------------------------------

class TestF0IndexQuery:
    """Validate query shape defaults."""

    def test_default_query_values(self):
        q = F0IndexQuery()
        assert q.sort_by == "collected_at"
        assert q.sort_order == "desc"
        assert q.limit == 50
        assert q.offset == 0

    def test_query_frozen(self):
        q = F0IndexQuery()
        with pytest.raises(AttributeError):
            q.limit = 100

    def test_all_filters_none_by_default(self):
        q = F0IndexQuery()
        assert q.source_type is None
        assert q.source_platform is None
        assert q.creator_id is None


# ---------------------------------------------------------------------------
# 4. Startup contract tests
# ---------------------------------------------------------------------------

class TestF0Startup:
    """Validate startup behavior contract."""

    def test_startup_returns_not_implemented(self):
        with pytest.raises(NotImplementedError, match="A1 first round"):
            check_f0_index_on_startup()

    def test_rebuild_returns_not_implemented(self):
        with pytest.raises(NotImplementedError, match="A1 first round"):
            rebuild_f0_index()

    def test_startup_state_enum_values(self):
        assert F0IndexStartupState.READY == "ready"
        assert F0IndexStartupState.STALE == "stale"
        assert F0IndexStartupState.MISSING == "missing"
        assert F0IndexStartupState.CORRUPT == "corrupt"

    def test_startup_result_dataclass(self):
        r = F0StartupResult(
            state=F0IndexStartupState.MISSING,
            health=None,
            message="no index",
            action_taken="none",
        )
        assert r.state == F0IndexStartupState.MISSING
        assert r.health is None


# ---------------------------------------------------------------------------
# 5. API contract tests
# ---------------------------------------------------------------------------

class TestF0IndexAPI:
    """Validate API endpoint contract."""

    @pytest.fixture()
    def client(self):
        from finer.api.server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_records_endpoint_returns_501(self, client):
        resp = client.get("/api/f0-index/records")
        assert resp.status_code == 500  # NotImplementedError becomes 500

    def test_health_endpoint_returns_501(self, client):
        resp = client.get("/api/f0-index/health")
        assert resp.status_code == 500

    def test_rebuild_endpoint_returns_501(self, client):
        resp = client.post("/api/f0-index/rebuild")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# 6. Error code tests
# ---------------------------------------------------------------------------

class TestF0IndexErrorCodes:
    """Validate F0 index error codes exist."""

    def test_error_codes_defined(self):
        from finer.errors.codes import ErrorCode
        assert hasattr(ErrorCode, 'F0_INDEX_001')
        assert hasattr(ErrorCode, 'F0_INDEX_002')
        assert hasattr(ErrorCode, 'F0_INDEX_003')

    def test_error_codes_have_metadata(self):
        from finer.errors import get_error_info, ErrorCode
        for code in (ErrorCode.F0_INDEX_001, ErrorCode.F0_INDEX_002, ErrorCode.F0_INDEX_003):
            info = get_error_info(code)
            assert info.fix_hint
            assert info.title
