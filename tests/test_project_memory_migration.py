"""Tests for Project Memory migration runner and SQL migrations."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from finer.scripts.project_memory_migrate import (
    MIGRATIONS_DIR,
    MigrationFile,
    _applied_versions,
    _compute_checksum,
    _open_db,
    _table_exists,
    discover_migrations,
    cli,
)
from click.testing import CliRunner


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.project.sqlite3"


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ── Discovery ────────────────────────────────────────────────────────────────


class TestDiscoverMigrations:
    def test_finds_all_migrations(self) -> None:
        migrations = discover_migrations()
        assert len(migrations) == 5
        assert [m.version for m in migrations] == [1, 2, 3, 4, 5]

    def test_versions_are_sequential(self) -> None:
        migrations = discover_migrations()
        for i, m in enumerate(migrations, start=1):
            assert m.version == i

    def test_names_are_nonempty(self) -> None:
        for m in discover_migrations():
            assert m.name
            assert len(m.name) > 0

    def test_checksums_are_hex(self) -> None:
        for m in discover_migrations():
            assert len(m.checksum) == 64
            int(m.checksum, 16)  # should not raise

    def test_checksums_differ_per_file(self) -> None:
        migrations = discover_migrations()
        checksums = [m.checksum for m in migrations]
        assert len(set(checksums)) == len(checksums)

    def test_sql_files_exist(self) -> None:
        for m in discover_migrations():
            assert m.path.exists()
            assert m.path.suffix == ".sql"


# ── Checksum computation ─────────────────────────────────────────────────────


class TestComputeChecksum:
    def test_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.sql"
        f.write_text("-- Version: 1\nSELECT 1;\n")
        assert _compute_checksum(f) == _compute_checksum(f)

    def test_strips_checksum_line(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.sql"
        f1.write_text("-- Version: 1\nSELECT 1;\n")
        f2 = tmp_path / "b.sql"
        f2.write_text("-- Version: 1\n-- Checksum: abcdef\nSELECT 1;\n")
        assert _compute_checksum(f1) == _compute_checksum(f2)


# ── DB operations ────────────────────────────────────────────────────────────


class TestOpenDb:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        db_path = tmp_path / "sub" / "dir" / "test.db"
        conn = _open_db(db_path)
        try:
            assert db_path.exists()
            # WAL mode
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_wal_mode(self, tmp_db: Path) -> None:
        conn = _open_db(tmp_db)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()


class TestAppliedVersions:
    def test_empty_on_fresh_db(self, tmp_db: Path) -> None:
        conn = _open_db(tmp_db)
        try:
            assert _applied_versions(conn) == {}
        finally:
            conn.close()

    def test_returns_recorded_versions(self, tmp_db: Path) -> None:
        conn = _open_db(tmp_db)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  name TEXT NOT NULL,
                  checksum TEXT NOT NULL,
                  applied_at TEXT NOT NULL,
                  applied_by TEXT,
                  execution_ms INTEGER NOT NULL
                )
                """
            )
            conn.commit()
            conn.execute(
                """
                INSERT INTO schema_migrations
                    (version, name, checksum, applied_at, applied_by, execution_ms)
                VALUES (1, 'test', 'abc123', datetime('now'), 'test', 10)
                """
            )
            conn.commit()
            versions = _applied_versions(conn)
            assert 1 in versions
            assert versions[1] == ("test", "abc123")
        finally:
            conn.close()


# ── CLI commands ─────────────────────────────────────────────────────────────


class TestCliStatus:
    def test_status_on_missing_db(self, runner: CliRunner, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.sqlite3"
        result = runner.invoke(cli, ["--db-path", str(db), "status"])
        assert result.exit_code == 0
        assert "pending" in result.output.lower()

    def test_status_on_fresh_db(self, runner: CliRunner, tmp_db: Path) -> None:
        result = runner.invoke(cli, ["--db-path", str(tmp_db), "status"])
        assert result.exit_code == 0
        assert "pending" in result.output.lower()


class TestCliUpgrade:
    def test_upgrade_applies_all(self, runner: CliRunner, tmp_db: Path) -> None:
        result = runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])
        assert result.exit_code == 0
        assert "Applied 5 migration(s)" in result.output

        # Verify tables exist
        conn = sqlite3.connect(str(tmp_db))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            expected = {
                "projects",
                "project_memory_meta",
                "schema_migrations",
                "source_groups",
                "source_records",
                "content_identities",
                "content_versions",
                "source_content_links",
                "contents",
                "storage_objects",
                "manifests",
                "artifacts",
                "artifact_edges",
                "content_blocks",
                "topic_blocks",
                "topic_block_members",
                "name_bindings",
                "pipeline_runs",
                "stage_status",
                "asset_index",
            }
            assert expected.issubset(tables)
        finally:
            conn.close()

    def test_upgrade_idempotent(self, runner: CliRunner, tmp_db: Path) -> None:
        runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])
        result = runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])
        assert result.exit_code == 0
        assert "already applied" in result.output.lower()

    def test_upgrade_records_checksums(self, runner: CliRunner, tmp_db: Path) -> None:
        runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])

        conn = sqlite3.connect(str(tmp_db))
        try:
            rows = conn.execute(
                "SELECT version, checksum, execution_ms FROM schema_migrations ORDER BY version"
            ).fetchall()
            assert len(rows) == 5
            for row in rows:
                assert len(row[1]) == 64  # sha256 hex
                assert row[2] >= 0  # execution_ms
        finally:
            conn.close()

    def test_upgrade_fts_virtual_table(self, runner: CliRunner, tmp_db: Path) -> None:
        runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])

        conn = sqlite3.connect(str(tmp_db))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "asset_index_fts" in tables
        finally:
            conn.close()


class TestCliVerify:
    def test_verify_ok_after_upgrade(self, runner: CliRunner, tmp_db: Path) -> None:
        runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])
        result = runner.invoke(cli, ["--db-path", str(tmp_db), "verify"])
        assert result.exit_code == 0
        assert "verified OK" in result.output

    def test_verify_on_missing_db(self, runner: CliRunner, tmp_path: Path) -> None:
        db = tmp_path / "nope.sqlite3"
        result = runner.invoke(cli, ["--db-path", str(db), "verify"])
        assert result.exit_code != 0

    def test_verify_detects_no_migrations(self, runner: CliRunner, tmp_db: Path) -> None:
        # Create the DB but don't run upgrade
        conn = sqlite3.connect(str(tmp_db))
        conn.close()
        result = runner.invoke(cli, ["--db-path", str(tmp_db), "verify"])
        assert result.exit_code == 0
        assert "no migrations applied" in result.output.lower()


class TestIndexes:
    def test_expected_indexes_created(self, runner: CliRunner, tmp_db: Path) -> None:
        runner.invoke(cli, ["--db-path", str(tmp_db), "upgrade"])

        conn = sqlite3.connect(str(tmp_db))
        try:
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
            expected_indexes = {
                "idx_source_records_group",
                "idx_source_records_hash",
                "idx_content_versions_content",
                "idx_source_content_links_content",
                "idx_contents_primary_source",
                "idx_contents_current_stage",
                "idx_manifests_subject",
                "idx_artifacts_content_stage",
                "idx_artifacts_stage_type",
                "idx_content_blocks_content_order",
                "idx_content_blocks_version",
                "idx_topic_blocks_content",
                "idx_name_bindings_subject",
                "idx_name_bindings_primary",
                "idx_stage_status_stage",
                "idx_pipeline_runs_status",
                "idx_asset_index_stage",
                "idx_asset_index_content",
                "idx_asset_index_source_group",
            }
            assert expected_indexes.issubset(indexes)
        finally:
            conn.close()
