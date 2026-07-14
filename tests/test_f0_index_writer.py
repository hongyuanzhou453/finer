"""Contract tests for F0IndexWriter (GATE freeze).

Verifies the single-record PM write path:
- lands a ContentRecord into contents + source_record + asset_index (+ FK chain)
- is idempotent (second call adds no duplicate rows)
- the written asset is visible via AssetIndexService (frontend projection)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finer.ingestion.f0_index_writer import F0IndexWriter
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.services.project_memory.asset_index import AssetIndexService


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    """A real, fully-migrated Project Memory DB (same helper the backfill tests use)."""
    from finer.scripts.project_memory_migrate import discover_migrations, _apply_migration

    db_path = tmp_path / "pm.sqlite3"
    connection = sqlite3.connect(str(db_path))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    for migration in discover_migrations():
        _apply_migration(connection, migration)
    return connection


@pytest.fixture(autouse=True)
def _durable_record_file(tmp_path: Path, monkeypatch):
    """Make the ContentRecord durable at the receipt's default record_path.

    F0IndexWriter now refuses to register a record as F0-ready unless its
    ContentRecord file exists (write-atomicity guard). These unit tests call the
    writer directly with a synthetic receipt, so materialize the file under a
    tmp cwd (all default receipts point at the same relative record_path).
    """
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "F0_intake" / "wechat" / "cnt_w001.json"
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text("{}", encoding="utf-8")  # content not validated by the writer
    yield


def _record(content_id: str = "cnt_w001", **overrides) -> ContentRecord:
    defaults = dict(
        content_id=content_id,
        source_type="wechat_channels_video",
        source_platform="wechat",
        raw_path="data/raw/wechat/cnt_w001/video.mp4",
        file_type="video",
        title="Cat Lord weekly review",
        creator_id="cat_lord",
        external_source_id="export_xyz",
        dedupe_fingerprint="fp_w001",
        collected_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ContentRecord(**defaults)


def _receipt(content_id: str = "cnt_w001", **overrides) -> ImportReceipt:
    defaults = dict(
        run_id="run_w001",
        request_id="req_w001",
        source_channel="wechat_channels",
        source_kind="wechat_channels_video",
        status="completed",
        content_id=content_id,
        external_source_id="export_xyz",
        dedupe_fingerprint="fp_w001",
        record_path="data/F0_intake/wechat/cnt_w001.json",
        records_created=1,
    )
    defaults.update(overrides)
    return ImportReceipt(**defaults)


def _count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sql, params).fetchone()[0]


class TestRecordImported:
    def test_writes_full_chain(self, conn: sqlite3.Connection) -> None:
        F0IndexWriter(conn).record_imported(_record(), _receipt())

        assert _count(conn, "content_identities", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "source_groups") == 1
        assert _count(conn, "source_records") == 1
        assert _count(conn, "contents", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "source_content_links", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "stage_status", "content_id = ? AND stage = 'F0'", ("cnt_w001",)) == 1
        assert _count(conn, "asset_index", "content_id = ? AND stage = 'F0'", ("cnt_w001",)) == 1

    def test_contents_row_is_f0_active(self, conn: sqlite3.Connection) -> None:
        F0IndexWriter(conn).record_imported(_record(), _receipt())
        row = conn.execute(
            "SELECT current_stage, status, content_type, canonical_title, primary_source_record_id "
            "FROM contents WHERE content_id = ?",
            ("cnt_w001",),
        ).fetchone()
        assert row["current_stage"] == "F0"
        assert row["status"] == "active"
        assert row["content_type"] == "wechat_channels_video"
        assert row["canonical_title"] == "Cat Lord weekly review"
        assert row["primary_source_record_id"] is not None

    def test_asset_visible_via_service(self, conn: sqlite3.Connection) -> None:
        F0IndexWriter(conn).record_imported(_record(), _receipt())
        svc = AssetIndexService(conn)
        asset = svc.get_asset("F0:cnt_w001")
        assert asset is not None
        assert asset["display_name"] == "Cat Lord weekly review"
        assert asset["source_platform"] == "wechat"
        assert asset["source_type"] == "wechat_channels_video"
        assert asset["status"] == "ready"
        # Listed under F0 stage
        listed = svc.list_assets(stage="F0")
        assert any(a["content_id"] == "cnt_w001" for a in listed)

    def test_idempotent_second_call_no_duplicates(self, conn: sqlite3.Connection) -> None:
        writer = F0IndexWriter(conn)
        writer.record_imported(_record(), _receipt())
        writer.record_imported(_record(), _receipt())

        assert _count(conn, "content_identities", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "source_groups") == 1
        assert _count(conn, "source_records") == 1
        assert _count(conn, "contents", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "source_content_links", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "stage_status", "content_id = ?", ("cnt_w001",)) == 1
        assert _count(conn, "asset_index", "content_id = ?", ("cnt_w001",)) == 1

    def test_two_distinct_records_two_assets(self, conn: sqlite3.Connection) -> None:
        writer = F0IndexWriter(conn)
        writer.record_imported(_record("cnt_a"), _receipt("cnt_a"))
        writer.record_imported(
            _record("cnt_b", raw_path="data/raw/bilibili/cnt_b/v.mp4", source_platform="bilibili",
                    source_type="bilibili_video", dedupe_fingerprint="fp_b"),
            _receipt("cnt_b", source_channel="bilibili", source_kind="bilibili_video"),
        )
        assert _count(conn, "asset_index", "stage = 'F0'") == 2
        # distinct platforms => distinct source groups
        assert _count(conn, "source_groups") == 2

    def test_foreign_keys_enforced_and_satisfied(self, conn: sqlite3.Connection) -> None:
        # With PRAGMA foreign_keys=ON, a successful commit proves the FK chain
        # (asset_index.content_id -> contents.content_id, etc.) is satisfied.
        conn.execute("PRAGMA foreign_keys=ON")
        F0IndexWriter(conn).record_imported(_record(), _receipt())
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert violations == []


class TestArtifactRegistration:
    def test_record_imported_writes_artifacts(self, conn: sqlite3.Connection) -> None:
        """raw_sha256 on receipt triggers storage_object + artifact writes."""
        receipt = _receipt(raw_sha256={"video": "aabbccdd" * 8}, raw_paths={"video": "data/raw/wechat/cnt_w001/video.mp4"})
        F0IndexWriter(conn).record_imported(_record(), receipt)

        assert _count(conn, "storage_objects") == 1
        assert _count(conn, "artifacts", "content_id = ? AND role = 'video'", ("cnt_w001",)) == 1
        row = conn.execute("SELECT is_canonical FROM artifacts WHERE content_id = 'cnt_w001'").fetchone()
        assert row["is_canonical"] == 1

    def test_artifacts_idempotent(self, conn: sqlite3.Connection) -> None:
        """Calling record_imported twice with same raw_sha256 produces stable artifact count."""
        receipt = _receipt(raw_sha256={"video": "aabbccdd" * 8}, raw_paths={"video": "data/raw/wechat/cnt_w001/video.mp4"})
        writer = F0IndexWriter(conn)
        writer.record_imported(_record(), receipt)
        writer.record_imported(_record(), receipt)

        assert _count(conn, "storage_objects") == 1
        assert _count(conn, "artifacts", "content_id = ?", ("cnt_w001",)) == 1

    def test_no_raw_sha256_skips_artifacts(self, conn: sqlite3.Connection) -> None:
        """Empty raw_sha256 produces no artifact rows (backward compat)."""
        F0IndexWriter(conn).record_imported(_record(), _receipt())

        assert _count(conn, "storage_objects") == 0
        assert _count(conn, "artifacts") == 0

    def test_two_roles_two_artifacts(self, conn: sqlite3.Connection) -> None:
        """Multiple roles produce multiple artifact rows."""
        receipt = _receipt(
            raw_sha256={"video": "aabbccdd" * 8, "document": "11223344" * 8},
            raw_paths={"video": "data/raw/wechat/cnt_w001/video.mp4", "document": "data/raw/wechat/cnt_w001/doc.pdf"},
        )
        F0IndexWriter(conn).record_imported(_record(), receipt)

        assert _count(conn, "storage_objects") == 2
        assert _count(conn, "artifacts", "content_id = ?", ("cnt_w001",)) == 2


class TestWriteAtomicityGuard:
    """F0 write-atomicity: never register a non-durable record as F0-ready."""

    def test_missing_record_file_raises(self, conn: sqlite3.Connection) -> None:
        receipt = _receipt(record_path="data/F0_intake/wechat/does_not_exist.json")
        with pytest.raises(FileNotFoundError, match="not durable"):
            F0IndexWriter(conn).record_imported(_record(), receipt)

    def test_missing_record_file_writes_no_rows(self, conn: sqlite3.Connection) -> None:
        # The guard runs before any insert → no partial/orphan rows leak.
        receipt = _receipt(record_path="data/F0_intake/wechat/does_not_exist.json")
        with pytest.raises(FileNotFoundError):
            F0IndexWriter(conn).record_imported(_record(), receipt)
        assert _count(conn, "contents", "content_id = ?", ("cnt_w001",)) == 0
        assert _count(conn, "stage_status", "content_id = ?", ("cnt_w001",)) == 0

    def test_no_record_path_is_permitted(self, conn: sqlite3.Connection) -> None:
        # record_path is Optional — when absent the guard can't verify, so it
        # proceeds (unchanged legacy behavior).
        receipt = _receipt(record_path=None)
        F0IndexWriter(conn).record_imported(_record(), receipt)
        assert _count(conn, "stage_status", "content_id = ? AND stage = 'F0'", ("cnt_w001",)) == 1
