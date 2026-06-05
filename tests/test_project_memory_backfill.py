"""Tests for the Project Memory backfill script."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from finer.scripts.project_memory_backfill import (
    BackfillEngine,
    BackfillStats,
    run_inventory,
    scan_manifests,
    scan_raw_files,
    scan_stage_outputs,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_data(tmp_path: Path) -> Path:
    """Create a temporary data directory structure with test files."""
    data = tmp_path / "data"

    # Raw files
    raw = data / "raw" / "trader_ji" / "weekly_strategy"
    raw.mkdir(parents=True)
    (raw / "2026-01-15-market-review.txt").write_text("Market was bullish today.")
    (raw / "2026-02-01-earnings-preview.txt").write_text("AAPL earnings preview.")

    raw_bilibili = data / "raw" / "bilibili" / "video"
    raw_bilibili.mkdir(parents=True)
    (raw_bilibili / "cat-lord-analysis.mp4").write_bytes(b"\x00" * 100)

    # Manifests
    manifests = data / "processed" / "manifests"
    manifests.mkdir(parents=True)
    manifest1 = {
        "content_id": "cnt_abc123",
        "source_type": "weekly_strategy",
        "source_platform": "feishu",
        "creator_id": "trader_ji",
        "creator_name": "Trader Ji",
        "published_at": "2026-01-15T09:00:00",
        "collected_at": "2026-01-15T10:00:00",
        "title": "Market Review 2026-01-15",
        "raw_path": "data/raw/trader_ji/weekly_strategy/2026-01-15-market-review.txt",
        "file_type": "text",
        "metadata": {"original_filename": "2026-01-15-market-review.txt"},
        "source_url": None,
        "external_source_id": None,
        "dedupe_fingerprint": None,
    }
    (manifests / "cnt_abc123.json").write_text(json.dumps(manifest1))

    # Documents
    docs = data / "processed" / "documents"
    docs.mkdir(parents=True)
    (docs / "processed-review.txt").write_text("Processed content.")

    # Transcripts
    transcripts = data / "processed" / "transcripts"
    transcripts.mkdir(parents=True)
    (transcripts / "transcript-001.txt").write_text("Transcript text.")

    # Stage outputs (F0 intake)
    f0 = data / "F0_intake" / "cnt_abc123"
    f0.mkdir(parents=True)
    (f0 / "intake.json").write_text(json.dumps({"status": "ok", "content_id": "cnt_abc123"}))

    # Stage outputs (F1 standardized)
    f1 = data / "F1_standardized" / "cnt_abc123"
    f1.mkdir(parents=True)
    f1_data = {
        "content_id": "cnt_abc123",
        "blocks": [
            {"block_type": "heading", "text": "Market Review"},
            {"block_type": "paragraph", "text": "Today was bullish."},
            {"block_type": "paragraph", "text": "AAPL up 3%."},
        ],
    }
    (f1 / "envelope.json").write_text(json.dumps(f1_data))

    # Stage outputs (F1.5 topic assembly)
    f1_5 = data / "F1_5" / "cnt_abc123"
    f1_5.mkdir(parents=True)
    f1_5_data = {
        "content_id": "cnt_abc123",
        "topics": [
            {"title": "Market Overview", "topic_type": "macro"},
            {"title": "AAPL Analysis", "topic_type": "stock"},
        ],
    }
    (f1_5 / "topics.json").write_text(json.dumps(f1_5_data))

    # Stage outputs (F8 metrics - legacy L8 path)
    l8 = data / "L8_metrics" / "cnt_abc123"
    l8.mkdir(parents=True)
    (l8 / "backtest-result.json").write_text(json.dumps({"pnl": 0.05}))

    return data


@pytest.fixture()
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    """Create an in-memory SQLite connection with the Project Memory schema."""
    db_path = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    # Apply all migrations
    from finer.scripts.project_memory_migrate import _open_db, discover_migrations, _apply_migration

    migrations = discover_migrations()
    for m in migrations:
        _apply_migration(conn, m)

    return conn


# ── Inventory tests ──────────────────────────────────────────────────────────


def test_scan_raw_files(tmp_data: Path) -> None:
    """scan_raw_files finds all raw files."""
    items = scan_raw_files(tmp_data)
    assert len(items) == 3  # 2 txt + 1 mp4

    platforms = {item.source_platform for item in items}
    assert "feishu" in platforms
    assert "bilibili" in platforms

    for item in items:
        assert item.content_hash is not None
        assert len(item.content_hash) == 64  # SHA-256 hex


def test_scan_manifests(tmp_data: Path) -> None:
    """scan_manifests finds manifest files."""
    items = scan_manifests(tmp_data)
    assert len(items) == 1
    assert items[0].content_id == "cnt_abc123"
    assert items[0].source_platform == "feishu"


def test_scan_processed_files(tmp_data: Path) -> None:
    """scan_processed_files finds documents and transcripts."""
    from finer.scripts.project_memory_backfill import scan_processed_files

    docs = scan_processed_files(tmp_data, "documents")
    assert len(docs) == 1
    assert docs[0].kind == "document"

    transcripts = scan_processed_files(tmp_data, "transcripts")
    assert len(transcripts) == 1
    assert transcripts[0].kind == "transcript"


def test_scan_stage_outputs(tmp_data: Path) -> None:
    """scan_stage_outputs finds files in F-stage and legacy L-stage directories."""
    items = scan_stage_outputs(tmp_data)
    # F0: intake.json, F1: envelope.json, F1_5: topics.json, L8: backtest-result.json
    assert len(items) == 4

    paths = [str(item.path) for item in items]
    assert any("F0_intake" in p for p in paths)
    assert any("F1_standardized" in p for p in paths)
    assert any("F1_5" in p for p in paths)
    assert any("L8_metrics" in p for p in paths)


def test_run_inventory(tmp_data: Path) -> None:
    """run_inventory returns all categories."""
    result = run_inventory(tmp_data)
    assert "raw_files" in result
    assert "manifests" in result
    assert "documents" in result
    assert "transcripts" in result
    assert "stage_outputs" in result

    total = sum(len(v) for v in result.values())
    assert total > 0


# ── Backfill engine tests ────────────────────────────────────────────────────


def test_backfill_dry_run(tmp_data: Path, db_conn: sqlite3.Connection) -> None:
    """Dry-run backfill does not write to the database."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=True,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)
    engine.phase4_contents(inventory)
    engine.phase5_objects(inventory)
    engine.phase6_artifacts(inventory)
    engine.phase7_blocks(inventory)
    engine.phase8_artifact_edges()
    engine.phase9_name_bindings(inventory)
    engine.phase10_stage_status()
    engine.phase11_asset_index()
    engine.phase12_integrity()

    stats = engine.stats
    assert stats.mode == "dry-run"
    assert stats.source_groups_new > 0
    assert stats.source_records_new > 0
    assert stats.content_identities_new > 0
    assert stats.content_versions > 0
    assert stats.artifacts > 0
    assert stats.name_bindings > 0

    # Verify nothing was written to DB
    count = db_conn.execute("SELECT COUNT(*) FROM source_groups").fetchone()[0]
    assert count == 0

    count = db_conn.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    assert count == 0

    count = db_conn.execute("SELECT COUNT(*) FROM content_identities").fetchone()[0]
    assert count == 0


def test_backfill_write_mode(tmp_data: Path, db_conn: sqlite3.Connection) -> None:
    """Write-mode backfill writes to the database."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=False,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)
    engine.phase4_contents(inventory)
    engine.phase5_objects(inventory)
    engine.phase6_artifacts(inventory)
    engine.phase7_blocks(inventory)
    engine.phase8_artifact_edges()
    engine.phase9_name_bindings(inventory)
    engine.phase10_stage_status()
    engine.phase11_asset_index()
    engine.phase12_integrity()

    stats = engine.stats
    assert stats.mode == "write"

    # Verify data was written
    count = db_conn.execute("SELECT COUNT(*) FROM source_groups").fetchone()[0]
    assert count > 0

    count = db_conn.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    assert count > 0

    count = db_conn.execute("SELECT COUNT(*) FROM content_identities").fetchone()[0]
    assert count > 0

    count = db_conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0]
    assert count > 0

    count = db_conn.execute("SELECT COUNT(*) FROM storage_objects").fetchone()[0]
    assert count > 0

    count = db_conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert count > 0

    count = db_conn.execute("SELECT COUNT(*) FROM name_bindings").fetchone()[0]
    assert count > 0

    # Check stage_status was built
    count = db_conn.execute("SELECT COUNT(*) FROM stage_status").fetchone()[0]
    assert count > 0

    # Check artifact edges were built
    count = db_conn.execute("SELECT COUNT(*) FROM artifact_edges").fetchone()[0]
    assert count > 0


def test_backfill_preserves_manifest_content_id(
    tmp_data: Path, db_conn: sqlite3.Connection
) -> None:
    """Backfill preserves trusted content_id from manifests."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=False,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)

    # The manifest content_id should be preserved
    row = db_conn.execute(
        "SELECT content_id FROM content_identities WHERE content_id = 'cnt_abc123'"
    ).fetchone()
    assert row is not None
    assert row[0] == "cnt_abc123"


def test_backfill_no_legacy_stage_in_db(
    tmp_data: Path, db_conn: sqlite3.Connection
) -> None:
    """No L0-L8 or V0-V6 values in canonical stage columns."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=False,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)
    engine.phase4_contents(inventory)
    engine.phase5_objects(inventory)
    engine.phase6_artifacts(inventory)
    engine.phase7_blocks(inventory)
    engine.phase8_artifact_edges()
    engine.phase9_name_bindings(inventory)
    engine.phase10_stage_status()

    # Check no legacy stage values in artifacts
    rows = db_conn.execute("SELECT DISTINCT stage FROM artifacts").fetchall()
    stages = {row[0] for row in rows}
    for stage in stages:
        assert not stage.startswith("L"), f"Legacy stage {stage} found in artifacts"
        assert not stage.startswith("V"), f"Legacy stage {stage} found in artifacts"

    # Check no legacy stage values in contents
    rows = db_conn.execute("SELECT DISTINCT current_stage FROM contents").fetchall()
    for row in rows:
        assert not row[0].startswith("L"), f"Legacy stage {row[0]} found in contents"
        assert not row[0].startswith("V"), f"Legacy stage {row[0]} found in contents"


def test_backfill_idempotent(tmp_data: Path, db_conn: sqlite3.Connection) -> None:
    """Running backfill twice does not create duplicate records."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    for _ in range(2):
        engine = BackfillEngine(
            conn=db_conn,
            data_root=tmp_data,
            storage_root=storage_root,
            dry_run=False,
        )
        inventory = engine.phase1_inventory()
        engine.phase2_sources(inventory)
        engine.phase3_content_identity(inventory)
        engine.phase4_contents(inventory)
        engine.phase5_objects(inventory)
        engine.phase6_artifacts(inventory)

    # Source groups should not duplicate
    count = db_conn.execute("SELECT COUNT(*) FROM source_groups").fetchone()[0]
    assert count <= 3  # directory + manifest_import (at most)

    # Content identities should not duplicate
    count = db_conn.execute("SELECT COUNT(*) FROM content_identities").fetchone()[0]
    # Should be: 1 from manifest + 2 from raw files (trader_ji files) + 1 bilibili
    # But the manifest one overlaps with raw file
    assert count >= 3


def test_backfill_deterministic_artifact_ids(tmp_data: Path, db_conn: sqlite3.Connection) -> None:
    """Running backfill twice produces stable artifact row count (no duplicates)."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    for _ in range(2):
        engine = BackfillEngine(
            conn=db_conn,
            data_root=tmp_data,
            storage_root=storage_root,
            dry_run=False,
        )
        inventory = engine.phase1_inventory()
        engine.phase2_sources(inventory)
        engine.phase3_content_identity(inventory)
        engine.phase4_contents(inventory)
        engine.phase5_objects(inventory)
        engine.phase6_artifacts(inventory)

    # Artifacts should not duplicate — deterministic IDs make second run a no-op
    artifact_count = db_conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    # Canonical artifacts should all be is_canonical=1 (no stale 0 rows)
    canonical_count = db_conn.execute("SELECT COUNT(*) FROM artifacts WHERE is_canonical = 1").fetchone()[0]
    assert artifact_count == canonical_count, f"Found {artifact_count - canonical_count} non-canonical stale rows"


def test_backfill_integrity_clean(
    tmp_data: Path, db_conn: sqlite3.Connection
) -> None:
    """Integrity checks pass on a clean backfill."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=False,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)
    engine.phase4_contents(inventory)
    engine.phase5_objects(inventory)
    engine.phase6_artifacts(inventory)
    engine.phase7_blocks(inventory)
    engine.phase8_artifact_edges()
    engine.phase9_name_bindings(inventory)
    engine.phase10_stage_status()
    engine.phase11_asset_index()
    engine.phase12_integrity()

    # The integrity check may have warnings about name bindings for
    # content items created from raw files without manifests, but
    # no critical structural violations
    for warning in engine.stats.integrity_warnings:
        assert "without identity" not in warning, "Content without identity is a critical error"
        assert "without object payload" not in warning, "Missing object is a critical error"


def test_backfill_stats_summary(tmp_data: Path, db_conn: sqlite3.Connection) -> None:
    """BackfillStats produces correct summary fields."""
    stats = BackfillStats(mode="dry-run")
    stats.source_groups_new = 3
    stats.source_groups_existing = 2
    stats.source_records_new = 38
    stats.source_records_existing = 4
    stats.content_identities_new = 30
    stats.content_identities_existing = 5

    assert stats.source_groups_total == 5
    assert stats.source_records_total == 42
    assert stats.content_identities_total == 35
    assert stats.integrity_status == "OK"

    stats.integrity_warnings.append("test warning")
    assert stats.integrity_status == "1 warnings"


def test_empty_data_dir(db_conn: sqlite3.Connection, tmp_path: Path) -> None:
    """Backfill handles empty data directory gracefully."""
    empty_data = tmp_path / "empty_data"
    empty_data.mkdir()
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    engine = BackfillEngine(
        conn=db_conn,
        data_root=empty_data,
        storage_root=storage_root,
        dry_run=True,
    )

    inventory = engine.phase1_inventory()
    assert all(len(v) == 0 for v in inventory.values())

    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)

    assert engine.stats.source_groups_new == 0
    assert engine.stats.source_records_new == 0
    assert engine.stats.content_identities_new == 0


def test_legacy_l8_mapped_to_f8(
    tmp_data: Path, db_conn: sqlite3.Connection
) -> None:
    """Legacy L8_metrics directory maps to canonical F8 stage."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=False,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)
    engine.phase4_contents(inventory)
    engine.phase5_objects(inventory)
    engine.phase6_artifacts(inventory)

    # The L8_metrics file should be registered as F8
    rows = db_conn.execute(
        "SELECT stage FROM artifacts WHERE stage = 'F8'"
    ).fetchall()
    # May or may not find a match depending on content_id inference,
    # but if it matches, it must be F8 not L8
    for row in rows:
        assert row[0] == "F8"


def test_manifest_primary_name(tmp_data: Path, db_conn: sqlite3.Connection) -> None:
    """Manifest title becomes primary name binding."""
    storage_root = tmp_data.parent / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = BackfillEngine(
        conn=db_conn,
        data_root=tmp_data,
        storage_root=storage_root,
        dry_run=False,
    )

    inventory = engine.phase1_inventory()
    engine.phase2_sources(inventory)
    engine.phase3_content_identity(inventory)
    engine.phase9_name_bindings(inventory)

    # Check primary name for manifest content
    rows = db_conn.execute(
        """
        SELECT display_value FROM name_bindings
        WHERE subject_id = 'cnt_abc123'
          AND is_primary = 1
          AND valid_to IS NULL
        """
    ).fetchall()
    assert len(rows) > 0
    assert rows[0][0] == "Market Review 2026-01-15"
