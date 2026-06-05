"""F0IndexWriter — the single PM write path for successful channel imports.

After a channel adapter (feishu / local upload / NotebookLM / wechat /
wechat_channels / bilibili) successfully imports one content item, it calls
``F0IndexWriter.record_imported(record, receipt)`` to register that item in
Project Memory so it shows up in the Import Console catalog / asset index.

Scope (IDP-01 decision)
-----------------------
This writer persists the minimal idempotent chain required for an F0 record to
appear in the frontend ``asset_index``:

    source_groups
      └─ source_records
    content_identities
      └─ contents              (FK: content_id -> content_identities)
           ├─ source_content_links  (links source_record <-> content)
           ├─ stage_status (F0, 'ready')   (asset_index rebuild reads this)
           ├─ asset_index (F0)             (the hot frontend index)
           ├─ storage_objects              (one per raw_sha256 role)
           └─ artifacts                    (one canonical per role, F0 stage)

It **also** writes ``artifacts`` / ``storage_objects`` for every raw payload
entry in the receipt (``raw_sha256`` keys), using deterministic
``sha256-derived`` ids so repeated calls are idempotent. The receipt's
``raw_sha256`` / ``raw_paths`` carry the provenance; each role gets one
``storage_object`` + one canonical ``artifact`` row.

All identity keys are deterministic (sha256-derived), and all inserts use
``INSERT OR IGNORE`` / ``ON CONFLICT``, so calling ``record_imported`` twice for
the same ContentRecord is a no-op on the second call (no duplicate rows).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.services.project_memory.asset_index import AssetIndexService
from finer.services.project_memory.connection import get_connection
from finer.utils.time import now_utc


def _det_id(prefix: str, *parts: str) -> str:
    """Deterministic, collision-resistant id from prefix + parts (sha256/16)."""
    raw = ":".join((prefix, *parts))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class F0IndexWriter:
    """Idempotent single-record writer into Project Memory for F0 imports."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None, *, db_path: Optional[Path] = None) -> None:
        """Bind to an explicit connection, or resolve one from the PM pool.

        Tests pass an explicit ``conn`` (a migrated in-memory/temp DB). Channel
        adapters can call ``F0IndexWriter()`` to use the active project DB.
        """
        self._conn = conn if conn is not None else get_connection(db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_imported(self, record: ContentRecord, receipt: ImportReceipt) -> None:
        """Register one successfully imported ContentRecord in Project Memory.

        Writes the minimal contents + source_record + asset_index chain (see
        module docstring), plus storage_objects + artifacts for every
        ``receipt.raw_sha256`` entry (deterministic ids, idempotent).
        """
        conn = self._conn
        now = now_utc().isoformat()
        content_id = record.content_id

        # 1. content identity (FK target for contents + source_content_links)
        stable_key = record.dedupe_fingerprint or content_id
        conn.execute(
            """
            INSERT OR IGNORE INTO content_identities
                (content_id, identity_scheme, stable_key, created_at)
            VALUES (?, 'f0_import', ?, ?)
            """,
            (content_id, stable_key, now),
        )

        # 2. source group (deterministic per platform+channel) and source record
        source_group_id = _det_id(
            "sg", record.source_platform, receipt.source_channel
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO source_groups
                (source_group_id, source_type, source_name, source_platform,
                 importer, imported_at)
            VALUES (?, ?, ?, ?, 'f0_index_writer', ?)
            """,
            (
                source_group_id,
                receipt.source_kind,
                f"{record.source_platform}:{receipt.source_channel}",
                record.source_platform,
                now,
            ),
        )

        # source record is keyed deterministically off content_id so re-imports
        # of the same content reuse the same row.
        source_record_id = _det_id("sr", content_id)
        external_id = record.external_source_id or receipt.external_source_id
        conn.execute(
            """
            INSERT OR IGNORE INTO source_records
                (source_record_id, source_group_id, external_id, source_uri,
                 original_filename, original_title, source_platform,
                 content_hash, imported_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported')
            """,
            (
                source_record_id,
                source_group_id,
                external_id,
                record.source_url or (receipt.record_path or record.raw_path),
                Path(record.raw_path).name,
                record.title or Path(record.raw_path).stem,
                record.source_platform,
                record.dedupe_fingerprint,
                now,
            ),
        )

        # 3. contents current-state row (FK: content_id, primary_source_record_id)
        title = record.title or Path(record.raw_path).stem
        existing = conn.execute(
            "SELECT content_id FROM contents WHERE content_id = ?",
            (content_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO contents
                    (content_id, primary_source_record_id, content_type,
                     current_stage, canonical_title, frontend_display_name,
                     created_at, updated_at, status)
                VALUES (?, ?, ?, 'F0', ?, ?, ?, ?, 'active')
                """,
                (
                    content_id,
                    source_record_id,
                    record.source_type,
                    title,
                    title,
                    now,
                    now,
                ),
            )
        else:
            # Keep current-state fresh without clobbering downstream stage moves.
            conn.execute(
                """
                UPDATE contents SET
                    primary_source_record_id = COALESCE(primary_source_record_id, ?),
                    content_type = COALESCE(content_type, ?),
                    canonical_title = COALESCE(canonical_title, ?),
                    frontend_display_name = COALESCE(frontend_display_name, ?),
                    updated_at = ?
                WHERE content_id = ?
                """,
                (source_record_id, record.source_type, title, title, now, content_id),
            )

        # 4. link source record <-> content
        conn.execute(
            """
            INSERT OR IGNORE INTO source_content_links
                (source_record_id, content_id, link_reason, confidence, created_at)
            VALUES (?, ?, 'f0_import', 1.0, ?)
            """,
            (source_record_id, content_id, now),
        )

        # 5. F0 stage status — asset_index rebuild only projects ready/partial rows
        conn.execute(
            """
            INSERT INTO stage_status (content_id, stage, status, updated_at)
            VALUES (?, 'F0', 'ready', ?)
            ON CONFLICT(content_id, stage) DO UPDATE SET
                status = 'ready',
                updated_at = excluded.updated_at
            """,
            (content_id, now),
        )

        conn.commit()

        # 6. asset_index hot row (idempotent upsert keyed by asset_id = F0:content_id)
        AssetIndexService(conn).upsert_asset(
            asset_id=f"F0:{content_id}",
            content_id=content_id,
            stage="F0",
            display_name=title,
            source_platform=record.source_platform,
            source_type=record.source_type,
            content_type=record.source_type,
            source_group_id=source_group_id,
            status="ready",
            sort_key=record.collected_at.isoformat(),
        )

        # 7. raw artifact + storage_object registration (idempotent)
        for role, sha256_hex in receipt.raw_sha256.items():
            raw_path = receipt.raw_paths.get(role, "")
            object_id = _det_id("obj", content_id, role, sha256_hex)
            artifact_id = _det_id("art", content_id, role, sha256_hex)

            conn.execute(
                """INSERT OR IGNORE INTO storage_objects
                       (object_id, sha256, storage_uri, byte_size, created_at)
                   VALUES (?, ?, ?, 0, ?)""",
                (object_id, sha256_hex, raw_path, now),
            )
            conn.execute(
                """INSERT OR IGNORE INTO artifacts
                       (artifact_id, content_id, stage, artifact_type, role,
                        object_id, artifact_version, is_canonical, created_at)
                   VALUES (?, ?, 'F0', 'raw_payload', ?, ?, 1, 1, ?)""",
                (artifact_id, content_id, role, object_id, now),
            )

        conn.commit()
