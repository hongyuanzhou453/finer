"""CLI backfill script for importing existing disk data into Project Memory.

Commands:
    inventory — scan legacy directories and report what would be imported
    backfill  — run the full backfill pipeline (dry-run by default)

Usage:
    python -m finer.scripts.project_memory_backfill inventory
    python -m finer.scripts.project_memory_backfill backfill
    python -m finer.scripts.project_memory_backfill backfill --write
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click

from finer.paths import DATA_ROOT, PROJECT_MEMORY_DB, STORAGE_ROOT


# ── Constants ────────────────────────────────────────────────────────────────

# F-stage directory mapping (legacy L* paths map to canonical F* names)
_LEGACY_STAGE_MAP: dict[str, str] = {
    "L0_intake": "F0",
    "L0": "F0",
    "F0_intake": "F0",
    "L1_standardized": "F1",
    "L1": "F1",
    "F1_standardized": "F1",
    "F1_5": "F1_5",
    "F1_5_topic_assembly": "F1_5",
    "L2_anchored": "F2",
    "L2": "F2",
    "F2_anchored": "F2",
    "L3_intents": "F3",
    "L3": "F3",
    "F3_intents": "F3",
    "L4_policy_mapped": "F4",
    "L4": "F4",
    "F4_policy_mapped": "F4",
    "L5_executed": "F5",
    "L5": "F5",
    "F5_executed": "F5",
    "L6_reviewed": "F6",
    "L6": "F6",
    "F6_reviewed": "F6",
    "L7_timeline": "F7",
    "L7": "F7",
    "F7_timeline": "F7",
    "L8_metrics": "F8",
    "L8": "F8",
    "F8_metrics": "F8",
}

_CANONICAL_STAGES = frozenset(
    {"F0", "F1", "F1_5", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F_PLUS"}
)

_MIME_MAP: dict[str, str] = {
    ".json": "application/json",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
}


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class InventoryItem:
    """One scannable file found during inventory."""

    path: Path
    kind: str  # "raw_file", "manifest", "document", "transcript", "stage_output"
    source_platform: str
    creator_id: Optional[str] = None
    content_id: Optional[str] = None
    content_hash: Optional[str] = None


@dataclass
class BackfillStats:
    """Counters for backfill summary."""

    mode: str = "dry-run"
    source_groups_new: int = 0
    source_groups_existing: int = 0
    source_records_new: int = 0
    source_records_existing: int = 0
    content_identities_new: int = 0
    content_identities_existing: int = 0
    content_versions: int = 0
    artifacts: int = 0
    name_bindings: int = 0
    asset_index_entries: int = 0
    integrity_warnings: list[str] = field(default_factory=list)

    @property
    def source_groups_total(self) -> int:
        return self.source_groups_new + self.source_groups_existing

    @property
    def source_records_total(self) -> int:
        return self.source_records_new + self.source_records_existing

    @property
    def content_identities_total(self) -> int:
        return self.content_identities_new + self.content_identities_existing

    @property
    def integrity_status(self) -> str:
        if not self.integrity_warnings:
            return "OK"
        return f"{len(self.integrity_warnings)} warnings"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_hash(path: Path) -> str:
    """SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _deterministic_source_group_id(source_type: str, source_name: str) -> str:
    """Deterministic source_group_id from type + name."""
    raw = f"sg:{source_type}:{source_name}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"sg_{h}"


def _deterministic_source_record_id(
    source_type: str, external_id: str, content_hash: str
) -> str:
    """Deterministic source_record_id."""
    raw = f"sr:{source_type}:{external_id}:{content_hash}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"sr_{h}"


def _deterministic_content_id(identity_scheme: str, stable_key: str) -> str:
    """Deterministic content_id from identity scheme + stable key."""
    raw = f"{identity_scheme}:{stable_key}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"cnt_{h}"


def _random_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _det_id(prefix: str, *parts: str) -> str:
    """Deterministic, collision-resistant id from prefix + parts (sha256/16)."""
    raw = ":".join((prefix, *parts))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _mime_for_path(path: Path) -> str:
    return _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")


def _infer_source_type_from_path(path: Path, root: Path) -> str:
    """Infer source_type from the relative path under raw/."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return "unclassified"
    parts = rel.parts
    if len(parts) >= 2:
        return parts[1]  # e.g. raw/trader_ji/weekly_strategy/file.txt -> weekly_strategy
    return "unclassified"


def _infer_platform_from_creator(creator_id: str) -> str:
    """Infer platform from creator directory name."""
    platform_hints = {
        "trader_ji": "feishu",
        "_inbox": "feishu",
        "_research": "local",
        "wechat": "wechat",
        "bilibili": "bilibili",
    }
    return platform_hints.get(creator_id, "local")


# ── Inventory ────────────────────────────────────────────────────────────────


def scan_raw_files(data_root: Path) -> list[InventoryItem]:
    """Scan data/raw/ for source files."""
    items: list[InventoryItem] = []
    raw_root = data_root / "raw"
    if not raw_root.exists():
        return items

    for creator_dir in raw_root.iterdir():
        if not creator_dir.is_dir():
            continue
        creator_id = creator_dir.name
        platform = _infer_platform_from_creator(creator_id)

        for file_path in creator_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                items.append(
                    InventoryItem(
                        path=file_path,
                        kind="raw_file",
                        source_platform=platform,
                        creator_id=creator_id,
                        content_hash=_file_hash(file_path),
                    )
                )
    return items


def scan_manifests(data_root: Path) -> list[InventoryItem]:
    """Scan data/processed/manifests/ for ContentManifest JSON files."""
    items: list[InventoryItem] = []
    manifest_dir = data_root / "processed" / "manifests"
    if not manifest_dir.exists():
        return items

    for manifest_path in manifest_dir.glob("*.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            content_id = data.get("content_id")
            platform = data.get("source_platform", "local")
            items.append(
                InventoryItem(
                    path=manifest_path,
                    kind="manifest",
                    source_platform=platform,
                    content_id=content_id,
                    content_hash=_file_hash(manifest_path),
                )
            )
        except (json.JSONDecodeError, OSError):
            continue
    return items


def scan_processed_files(data_root: Path, subdir: str) -> list[InventoryItem]:
    """Scan data/processed/{subdir}/ for files."""
    items: list[InventoryItem] = []
    target_dir = data_root / "processed" / subdir
    if not target_dir.exists():
        return items

    for file_path in target_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            items.append(
                InventoryItem(
                    path=file_path,
                    kind=subdir.rstrip("s"),  # documents -> document, transcripts -> transcript
                    source_platform="local",
                    content_hash=_file_hash(file_path),
                )
            )
    return items


def scan_stage_outputs(data_root: Path) -> list[InventoryItem]:
    """Scan F0-F8 (and legacy L0-L8) stage output directories."""
    items: list[InventoryItem] = []
    if not data_root.exists():
        return items

    for child in data_root.iterdir():
        if not child.is_dir():
            continue
        stage = _LEGACY_STAGE_MAP.get(child.name)
        if stage is None:
            # Check if it's a canonical stage directory (F0, F1, F2, etc.)
            if child.name in _CANONICAL_STAGES:
                stage = child.name
            else:
                continue

        for file_path in child.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                items.append(
                    InventoryItem(
                        path=file_path,
                        kind="stage_output",
                        source_platform="local",
                        content_hash=_file_hash(file_path),
                    )
                )
    return items


def run_inventory(data_root: Path) -> dict[str, list[InventoryItem]]:
    """Full inventory scan. Returns categorized items."""
    return {
        "raw_files": scan_raw_files(data_root),
        "manifests": scan_manifests(data_root),
        "documents": scan_processed_files(data_root, "documents"),
        "transcripts": scan_processed_files(data_root, "transcripts"),
        "stage_outputs": scan_stage_outputs(data_root),
    }


# ── Manifest loader ─────────────────────────────────────────────────────────


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load a ContentManifest JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


# ── Backfill engine ──────────────────────────────────────────────────────────


class BackfillEngine:
    """Orchestrates the 12-phase backfill from legacy disk data into Project Memory."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        data_root: Path,
        storage_root: Path,
        dry_run: bool = True,
    ) -> None:
        self._conn = conn
        self._data_root = data_root
        self._storage_root = storage_root
        self._dry_run = dry_run
        self.stats = BackfillStats(mode="dry-run" if dry_run else "write")

        # In-memory registries for idempotency
        self._source_group_ids: dict[str, str] = {}  # key -> source_group_id
        self._source_record_ids: dict[str, str] = {}  # key -> source_record_id
        self._content_ids: dict[str, str] = {}  # stable_key -> content_id
        self._object_ids: dict[str, str] = {}  # sha256 -> object_id
        self._artifact_ids: dict[str, str] = {}  # key -> artifact_id
        self._created_artifact_ids: set[str] = set()  # artifact_ids created in this run

    # ── Phase 1: Inventory ──────────────────────────────────────────────

    def phase1_inventory(self) -> dict[str, list[InventoryItem]]:
        """Inventory legacy files without writing."""
        click.echo("Phase 1: Inventory...")
        inventory = run_inventory(self._data_root)
        total = sum(len(v) for v in inventory.values())
        click.echo(f"  Found {total} files across {len(inventory)} categories")
        for cat, items in inventory.items():
            click.echo(f"    {cat}: {len(items)}")
        return inventory

    # ── Phase 2: Source groups and source records ───────────────────────

    def phase2_sources(self, inventory: dict[str, list[InventoryItem]]) -> None:
        """Register source_groups and source_records."""
        click.echo("Phase 2: Source groups and records...")

        # Group raw files by creator_id
        creator_groups: dict[str, list[InventoryItem]] = {}
        for item in inventory["raw_files"]:
            key = item.creator_id or "unknown"
            creator_groups.setdefault(key, []).append(item)

        for creator_id, items in creator_groups.items():
            sg_key = f"{_infer_platform_from_creator(creator_id)}:{creator_id}"
            sg_id = self._ensure_source_group(
                source_type="directory",
                source_name=creator_id,
                source_platform=_infer_platform_from_creator(creator_id),
            )

            for item in items:
                self._ensure_source_record(
                    source_group_id=sg_id,
                    original_filename=item.path.name,
                    original_title=item.path.stem,
                    source_platform=item.source_platform,
                    content_hash=item.content_hash or "",
                    source_uri=str(item.path),
                )

        # Manifests as source records linked to a manifest-import group
        if inventory["manifests"]:
            sg_id = self._ensure_source_group(
                source_type="manifest_import",
                source_name="processed_manifests",
                source_platform="local",
            )
            for item in inventory["manifests"]:
                self._ensure_source_record(
                    source_group_id=sg_id,
                    original_filename=item.path.name,
                    original_title=item.path.stem,
                    source_platform=item.source_platform,
                    content_hash=item.content_hash or "",
                    source_uri=str(item.path),
                )

        click.echo(
            f"  Source groups: {self.stats.source_groups_total} "
            f"(new: {self.stats.source_groups_new}, existing: {self.stats.source_groups_existing})"
        )
        click.echo(
            f"  Source records: {self.stats.source_records_total} "
            f"(new: {self.stats.source_records_new}, existing: {self.stats.source_records_existing})"
        )

    # ── Phase 3: Content identities, versions, links ───────────────────

    def phase3_content_identity(
        self, inventory: dict[str, list[InventoryItem]]
    ) -> None:
        """Register content_identities, content_versions, and source_content_links."""
        click.echo("Phase 3: Content identity...")

        # Process manifests first — they have trusted content_ids
        for item in inventory["manifests"]:
            manifest = _load_manifest(item.path)
            content_id = manifest.get("content_id")
            if not content_id:
                continue

            stable_key = manifest.get("dedupe_fingerprint") or content_id
            self._ensure_content_identity(
                content_id=content_id,
                identity_scheme="manifest",
                stable_key=stable_key,
            )
            self._ensure_content_version(content_id, content_hash=item.content_hash)
            self.stats.content_versions += 1

        # Process raw files — generate content_id from creator + filename
        for item in inventory["raw_files"]:
            creator_id = item.creator_id or "unknown"
            stable_key = f"{creator_id}:{item.path.name}"
            content_id = self._ensure_content_identity(
                identity_scheme="raw_file",
                stable_key=stable_key,
            )
            self._ensure_content_version(content_id, content_hash=item.content_hash)
            self.stats.content_versions += 1

            # Link source record to content
            sr_key = f"{item.source_platform}:{item.path.name}:{item.content_hash}"
            sr_id = self._source_record_ids.get(sr_key)
            if sr_id:
                self._link_source_to_content(sr_id, content_id, "backfill_import")

        click.echo(
            f"  Content identities: {self.stats.content_identities_total} "
            f"(new: {self.stats.content_identities_new}, existing: {self.stats.content_identities_existing})"
        )
        click.echo(f"  Content versions: {self.stats.content_versions}")

    # ── Phase 4: Contents current-state rows ───────────────────────────

    def phase4_contents(
        self, inventory: dict[str, list[InventoryItem]]
    ) -> None:
        """Register contents current-state rows."""
        click.echo("Phase 4: Contents rows...")

        # From manifests
        for item in inventory["manifests"]:
            manifest = _load_manifest(item.path)
            content_id = manifest.get("content_id")
            if not content_id or content_id not in self._content_ids:
                continue

            self._upsert_content(
                content_id=content_id,
                content_type=manifest.get("source_type", "unclassified"),
                current_stage="F0",
                canonical_title=manifest.get("title"),
                frontend_display_name=manifest.get("title"),
            )

        # From raw files (only if not already covered by manifest)
        for item in inventory["raw_files"]:
            creator_id = item.creator_id or "unknown"
            stable_key = f"{creator_id}:{item.path.name}"
            content_id = self._content_ids.get(stable_key)
            if not content_id:
                continue

            # Check if already registered from manifest
            existing = self._conn.execute(
                "SELECT content_id FROM contents WHERE content_id = ?",
                (content_id,),
            ).fetchone()
            if existing:
                continue

            self._upsert_content(
                content_id=content_id,
                content_type=_infer_source_type_from_path(item.path, self._data_root / "raw"),
                current_stage="F0",
                canonical_title=item.path.stem,
                frontend_display_name=item.path.stem,
            )

    # ── Phase 5: Storage objects ────────────────────────────────────────

    def phase5_objects(
        self, inventory: dict[str, list[InventoryItem]]
    ) -> None:
        """Register payloads into storage_objects."""
        click.echo("Phase 5: Storage objects...")

        all_items = (
            inventory["raw_files"]
            + inventory["documents"]
            + inventory["transcripts"]
            + inventory["stage_outputs"]
        )

        for item in all_items:
            self._ensure_storage_object(item.path, item.content_hash or "")

        # Also register manifest files as objects
        for item in inventory["manifests"]:
            self._ensure_storage_object(item.path, item.content_hash or "")

        click.echo(f"  Storage objects: {len(self._object_ids)}")

    # ── Phase 6: F0/F1/F-stage artifacts ───────────────────────────────

    def phase6_artifacts(
        self, inventory: dict[str, list[InventoryItem]]
    ) -> None:
        """Register F0/F1/F-stage artifacts."""
        click.echo("Phase 6: Artifacts...")

        # Create F0 artifacts from raw files
        for item in inventory["raw_files"]:
            creator_id = item.creator_id or "unknown"
            stable_key = f"{creator_id}:{item.path.name}"
            content_id = self._content_ids.get(stable_key)
            if not content_id:
                continue

            obj_id = self._object_ids.get(item.content_hash or "")
            if not obj_id:
                continue

            self._ensure_artifact(
                content_id=content_id,
                stage="F0",
                artifact_type="raw_source",
                role="source",
                object_id=obj_id,
                schema_name="ContentRecord",
                metadata={"original_path": str(item.path)},
            )

        # Create artifacts from stage outputs
        for item in inventory["stage_outputs"]:
            stage = self._infer_stage_from_path(item.path)
            if not stage:
                continue

            # Try to find content_id from co-located manifest or filename heuristic
            content_id = self._infer_content_id_for_stage_output(item)
            if not content_id:
                continue

            obj_id = self._object_ids.get(item.content_hash or "")
            if not obj_id:
                continue

            self._ensure_artifact(
                content_id=content_id,
                stage=stage,
                artifact_type=f"{stage.lower()}_output",
                role="output",
                object_id=obj_id,
                metadata={"legacy_path": str(item.path)},
            )

        click.echo(f"  Artifacts: {self.stats.artifacts}")

    # ── Phase 7: Content blocks and topic blocks ───────────────────────

    def phase7_blocks(
        self, inventory: dict[str, list[InventoryItem]]
    ) -> None:
        """Register content_blocks, topic_blocks, and topic_block_members
        when source payloads contain F1/F1.5 outputs."""
        click.echo("Phase 7: Blocks and topics...")

        block_count = 0
        topic_count = 0

        for item in inventory["stage_outputs"]:
            stage = self._infer_stage_from_path(item.path)
            if stage not in ("F1", "F1_5"):
                continue

            content_id = self._infer_content_id_for_stage_output(item)
            if not content_id:
                continue

            try:
                data = json.loads(item.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if stage == "F1" and isinstance(data, dict):
                blocks = data.get("blocks", data.get("content_blocks", []))
                if isinstance(blocks, list):
                    for idx, block in enumerate(blocks):
                        if self._dry_run:
                            block_count += 1
                        else:
                            self._create_block(
                                content_id=content_id,
                                block_type=block.get("block_type", "text"),
                                order_index=idx,
                                text_excerpt=_truncate(block.get("text", ""), 200),
                            )
                            block_count += 1

            elif stage == "F1_5" and isinstance(data, dict):
                topics = data.get("topics", data.get("topic_blocks", []))
                if isinstance(topics, list):
                    for topic in topics:
                        if self._dry_run:
                            topic_count += 1
                        else:
                            self._create_topic_block(
                                content_id=content_id,
                                topic_title=topic.get("title", "Untitled"),
                                topic_type=topic.get("topic_type", "general"),
                            )
                            topic_count += 1

        click.echo(f"  Content blocks: {block_count}")
        click.echo(f"  Topic blocks: {topic_count}")

    # ── Phase 8: Artifact edges ────────────────────────────────────────

    def phase8_artifact_edges(self) -> None:
        """Build artifact_edges from stage lineage for backfill-created artifacts."""
        click.echo("Phase 8: Artifact edges...")

        if not self._created_artifact_ids:
            click.echo("  Artifact edges: 0 (no artifacts created)")
            return

        edge_count = 0
        # Group artifacts by content_id and build F0->F1->F2... chains
        # Only for artifacts created in this backfill run
        placeholders = ",".join(["?"] * len(self._created_artifact_ids))
        rows = self._conn.execute(
            f"""
            SELECT artifact_id, content_id, stage
            FROM artifacts
            WHERE is_canonical = 1 AND artifact_id IN ({placeholders})
            ORDER BY content_id, stage
            """,
            list(self._created_artifact_ids),
        ).fetchall()

        stage_order = ["F0", "F1", "F1_5", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]
        by_content: dict[str, dict[str, str]] = {}
        for row in rows:
            aid, cid, stage = row[0], row[1], row[2]
            by_content.setdefault(cid, {})[stage] = aid

        relation_map = {
            ("F0", "F1"): "standardizes",
            ("F1", "F1_5"): "assembles",
            ("F1", "F2"): "anchors",
            ("F1_5", "F2"): "anchors",
            ("F2", "F3"): "extracts_intent_from",
            ("F3", "F4"): "maps_policy_from",
            ("F3", "F5"): "executes_from",
            ("F4", "F5"): "executes_from",
            ("F5", "F6"): "reviews",
            ("F5", "F8"): "backtests",
        }

        for cid, stages in by_content.items():
            for i in range(len(stage_order) - 1):
                parent_stage = stage_order[i]
                for j in range(i + 1, len(stage_order)):
                    child_stage = stage_order[j]
                    parent_id = stages.get(parent_stage)
                    child_id = stages.get(child_stage)
                    if parent_id and child_id:
                        relation = relation_map.get((parent_stage, child_stage), "derived_from")
                        if not self._dry_run:
                            self._conn.execute(
                                """
                                INSERT OR IGNORE INTO artifact_edges
                                    (parent_artifact_id, child_artifact_id, relation)
                                VALUES (?, ?, ?)
                                """,
                                (parent_id, child_id, relation),
                            )
                        edge_count += 1

        if not self._dry_run:
            self._conn.commit()
        click.echo(f"  Artifact edges: {edge_count}")

    # ── Phase 9: Name bindings ─────────────────────────────────────────

    def phase9_name_bindings(
        self, inventory: dict[str, list[InventoryItem]]
    ) -> None:
        """Extract and normalize name_bindings."""
        click.echo("Phase 9: Name bindings...")

        # From manifests
        for item in inventory["manifests"]:
            manifest = _load_manifest(item.path)
            content_id = manifest.get("content_id")
            if not content_id:
                continue

            title = manifest.get("title")
            if title:
                self._bind_name(
                    subject_type="content",
                    subject_id=content_id,
                    namespace="manifest",
                    name_kind="title",
                    display_value=title,
                    stage="F0",
                    is_primary=True,
                )

            filename = manifest.get("metadata", {}).get("original_filename")
            if filename:
                self._bind_name(
                    subject_type="content",
                    subject_id=content_id,
                    namespace="source",
                    name_kind="filename",
                    display_value=filename,
                    stage="F0",
                )

        # From raw files
        for item in inventory["raw_files"]:
            creator_id = item.creator_id or "unknown"
            stable_key = f"{creator_id}:{item.path.name}"
            content_id = self._content_ids.get(stable_key)
            if not content_id:
                continue

            # Only add filename binding if not already covered by manifest
            existing = self._get_name_bindings(content_id, "source", "filename")
            if not existing:
                self._bind_name(
                    subject_type="content",
                    subject_id=content_id,
                    namespace="source",
                    name_kind="filename",
                    display_value=item.path.name,
                    stage="F0",
                )

            # Set primary title from filename stem if no manifest title
            existing_title = self._get_name_bindings(content_id, "manifest", "title")
            if not existing_title:
                self._bind_name(
                    subject_type="content",
                    subject_id=content_id,
                    namespace="source",
                    name_kind="title",
                    display_value=item.path.stem,
                    stage="F0",
                    is_primary=True,
                )

        click.echo(f"  Name bindings: {self.stats.name_bindings}")

    # ── Phase 10: Stage status ─────────────────────────────────────────

    def phase10_stage_status(self) -> None:
        """Build stage_status from artifacts."""
        click.echo("Phase 10: Stage status...")

        rows = self._conn.execute(
            """
            SELECT content_id, stage, MAX(artifact_id)
            FROM artifacts
            WHERE is_canonical = 1
            GROUP BY content_id, stage
            """
        ).fetchall()

        count = 0
        for content_id, stage, artifact_id in rows:
            if not self._dry_run:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO stage_status
                        (content_id, stage, status, latest_artifact_id, updated_at)
                    VALUES (?, ?, 'ready', ?, ?)
                    """,
                    (content_id, stage, artifact_id, _utc_now()),
                )
            count += 1

        if not self._dry_run:
            self._conn.commit()
        click.echo(f"  Stage status entries: {count}")

    # ── Phase 11: Asset index and FTS ──────────────────────────────────

    def phase11_asset_index(self) -> None:
        """Rebuild asset_index and asset_index_fts."""
        click.echo("Phase 11: Asset index and FTS...")

        if not self._dry_run:
            from finer.services.project_memory.asset_index import AssetIndexService

            svc = AssetIndexService(self._conn)
            count = svc.rebuild_all()
            self.stats.asset_index_entries = count
        else:
            # Count what would be built
            rows = self._conn.execute(
                """
                SELECT COUNT(*) FROM contents c
                JOIN stage_status ss ON ss.content_id = c.content_id
                WHERE ss.status IN ('ready', 'partial')
                """
            ).fetchone()
            self.stats.asset_index_entries = rows[0] if rows else 0

        click.echo(f"  Asset index entries: {self.stats.asset_index_entries}")

    # ── Phase 12: Integrity checks ─────────────────────────────────────

    def phase12_integrity(self) -> None:
        """Run integrity checks."""
        click.echo("Phase 12: Integrity checks...")

        warnings: list[str] = []

        # No current content row without identity
        rows = self._conn.execute(
            """
            SELECT content_id FROM contents
            WHERE content_id NOT IN (SELECT content_id FROM content_identities)
            """
        ).fetchall()
        if rows:
            warnings.append(f"{len(rows)} content rows without identity")

        # No content identity without any source link
        rows = self._conn.execute(
            """
            SELECT content_id FROM content_identities
            WHERE content_id NOT IN (SELECT content_id FROM source_content_links)
            """
        ).fetchall()
        if rows:
            warnings.append(f"{len(rows)} content identities without source links")

        # No canonical artifact without object payload
        rows = self._conn.execute(
            """
            SELECT artifact_id FROM artifacts
            WHERE is_canonical = 1
              AND object_id NOT IN (SELECT object_id FROM storage_objects)
            """
        ).fetchall()
        if rows:
            warnings.append(f"{len(rows)} canonical artifacts without object payload")

        # No content without primary display name
        rows = self._conn.execute(
            """
            SELECT c.content_id
            FROM contents c
            LEFT JOIN name_bindings n
              ON n.subject_type = 'content'
             AND n.subject_id = c.content_id
             AND n.is_primary = 1
             AND n.valid_to IS NULL
            WHERE n.name_binding_id IS NULL
            """
        ).fetchall()
        if rows:
            warnings.append(f"{len(rows)} content items without primary name")

        # No F1 topic member pointing at a missing block
        rows = self._conn.execute(
            """
            SELECT topic_block_id, block_id FROM topic_block_members
            WHERE block_id NOT IN (SELECT block_id FROM content_blocks)
            """
        ).fetchall()
        if rows:
            warnings.append(f"{len(rows)} topic members pointing at missing blocks")

        self.stats.integrity_warnings = warnings

        if warnings:
            for w in warnings:
                click.echo(f"  WARNING: {w}")
        else:
            click.echo("  All checks passed")

    # ── Internal helpers ───────────────────────────────────────────────

    def _ensure_source_group(
        self,
        source_type: str,
        source_name: str,
        source_platform: str,
    ) -> str:
        """Get or create a source_group. Returns source_group_id."""
        key = f"{source_type}:{source_name}"
        if key in self._source_group_ids:
            self.stats.source_groups_existing += 1
            return self._source_group_ids[key]

        sg_id = _deterministic_source_group_id(source_type, source_name)
        self._source_group_ids[key] = sg_id

        if not self._dry_run:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO source_groups
                    (source_group_id, source_type, source_name, source_platform,
                     importer, imported_at)
                VALUES (?, ?, ?, ?, 'backfill', ?)
                """,
                (sg_id, source_type, source_name, source_platform, _utc_now()),
            )
            self._conn.commit()

        self.stats.source_groups_new += 1
        return sg_id

    def _ensure_source_record(
        self,
        source_group_id: str,
        original_filename: str,
        original_title: str,
        source_platform: str,
        content_hash: str,
        source_uri: str,
    ) -> str:
        """Get or create a source_record. Returns source_record_id."""
        key = f"{source_platform}:{original_filename}:{content_hash}"
        if key in self._source_record_ids:
            self.stats.source_records_existing += 1
            return self._source_record_ids[key]

        sr_id = _deterministic_source_record_id(
            source_platform, original_filename, content_hash
        )
        self._source_record_ids[key] = sr_id

        if not self._dry_run:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO source_records
                    (source_record_id, source_group_id, external_id, source_uri,
                     original_filename, original_title, source_platform,
                     content_hash, imported_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported')
                """,
                (
                    sr_id, source_group_id, original_filename, source_uri,
                    original_filename, original_title, source_platform,
                    content_hash, _utc_now(),
                ),
            )
            self._conn.commit()

        self.stats.source_records_new += 1
        return sr_id

    def _ensure_content_identity(
        self,
        identity_scheme: str,
        stable_key: str,
        content_id: Optional[str] = None,
    ) -> str:
        """Get or create a content identity. Returns content_id."""
        if stable_key in self._content_ids:
            self.stats.content_identities_existing += 1
            return self._content_ids[stable_key]

        cid = content_id or _deterministic_content_id(identity_scheme, stable_key)
        self._content_ids[stable_key] = cid

        if not self._dry_run:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO content_identities
                    (content_id, identity_scheme, stable_key, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cid, identity_scheme, stable_key, _utc_now()),
            )
            self._conn.commit()

        self.stats.content_identities_new += 1
        return cid

    def _ensure_content_version(
        self,
        content_id: str,
        content_hash: Optional[str] = None,
    ) -> str:
        """Create a content version. Returns content_version_id."""
        version_id = _random_id("cv")
        if not self._dry_run:
            # Get next version number
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version_no), 0) FROM content_versions WHERE content_id = ?",
                (content_id,),
            ).fetchone()
            next_no = (row[0] if row else 0) + 1

            self._conn.execute(
                """
                INSERT INTO content_versions
                    (content_version_id, content_id, content_hash, version_no, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (version_id, content_id, content_hash, next_no, _utc_now()),
            )
            self._conn.commit()
        return version_id

    def _link_source_to_content(
        self,
        source_record_id: str,
        content_id: str,
        link_reason: str,
    ) -> None:
        """Link a source record to a content identity."""
        if not self._dry_run:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO source_content_links
                    (source_record_id, content_id, link_reason, confidence, created_at)
                VALUES (?, ?, ?, 1.0, ?)
                """,
                (source_record_id, content_id, link_reason, _utc_now()),
            )
            self._conn.commit()

    def _upsert_content(
        self,
        content_id: str,
        content_type: str,
        current_stage: str,
        canonical_title: Optional[str] = None,
        frontend_display_name: Optional[str] = None,
    ) -> None:
        """Insert or update a contents row."""
        if not self._dry_run:
            now = _utc_now()
            existing = self._conn.execute(
                "SELECT content_id FROM contents WHERE content_id = ?",
                (content_id,),
            ).fetchone()

            if existing is None:
                self._conn.execute(
                    """
                    INSERT INTO contents
                        (content_id, content_type, current_stage, canonical_title,
                         frontend_display_name, created_at, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (content_id, content_type, current_stage, canonical_title,
                     frontend_display_name, now, now),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE contents SET
                        content_type = COALESCE(?, content_type),
                        current_stage = COALESCE(?, current_stage),
                        canonical_title = COALESCE(?, canonical_title),
                        frontend_display_name = COALESCE(?, frontend_display_name),
                        updated_at = ?
                    WHERE content_id = ?
                    """,
                    (content_type, current_stage, canonical_title,
                     frontend_display_name, now, content_id),
                )
            self._conn.commit()

    def _ensure_storage_object(self, file_path: Path, content_hash: str) -> str:
        """Register a file as a storage object. Returns object_id."""
        if content_hash in self._object_ids:
            return self._object_ids[content_hash]

        object_id = _det_id("obj", content_hash) if content_hash else _random_id("obj")
        self._object_ids[content_hash] = object_id

        if not self._dry_run:
            # Copy file to content-addressed storage
            dest = (
                self._storage_root
                / "objects"
                / "sha256"
                / content_hash[:2]
                / content_hash[2:4]
                / content_hash
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                import shutil

                shutil.copy2(file_path, dest)

            self._conn.execute(
                """
                INSERT OR IGNORE INTO storage_objects
                    (object_id, sha256, storage_uri, byte_size, mime_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    object_id,
                    content_hash,
                    str(dest),
                    file_path.stat().st_size,
                    _mime_for_path(file_path),
                    _utc_now(),
                ),
            )
            self._conn.commit()

        return object_id

    def _ensure_artifact(
        self,
        content_id: str,
        stage: str,
        artifact_type: str,
        role: str,
        object_id: str,
        schema_name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create an artifact and mark it canonical. Returns artifact_id."""
        artifact_id = _det_id("art", content_id, stage, artifact_type, role, object_id)
        self.stats.artifacts += 1
        self._created_artifact_ids.add(artifact_id)

        if not self._dry_run:
            import json as _json

            # Get next version
            row = self._conn.execute(
                """
                SELECT COALESCE(MAX(artifact_version), 0) FROM artifacts
                WHERE content_id = ? AND stage = ? AND artifact_type = ?
                """,
                (content_id, stage, artifact_type),
            ).fetchone()
            next_version = (row[0] if row else 0) + 1

            # Idempotent insert: skip entirely if deterministic id already exists
            inserted = self._conn.execute(
                """
                INSERT OR IGNORE INTO artifacts
                    (artifact_id, content_id, stage, artifact_type, role, object_id,
                     schema_name, artifact_version, is_canonical, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    artifact_id, content_id, stage, artifact_type, role, object_id,
                    schema_name, next_version, _utc_now(),
                    _json.dumps(metadata) if metadata else None,
                ),
            )
            if inserted.rowcount > 0:
                # Mark canonical: clear siblings, then set this one
                self._conn.execute(
                    """
                    UPDATE artifacts SET is_canonical = 0
                    WHERE content_id = ? AND stage = ? AND artifact_type = ?
                      AND artifact_id != ?
                    """,
                    (content_id, stage, artifact_type, artifact_id),
                )
            self._conn.commit()

        return artifact_id

    def _create_block(
        self,
        content_id: str,
        block_type: str,
        order_index: int,
        text_excerpt: Optional[str] = None,
    ) -> str:
        """Create a content block. Returns block_id."""
        block_id = _random_id("blk")
        if not self._dry_run:
            self._conn.execute(
                """
                INSERT INTO content_blocks
                    (block_id, content_id, stage, block_type, order_index,
                     text_excerpt, created_at)
                VALUES (?, ?, 'F1', ?, ?, ?, ?)
                """,
                (block_id, content_id, block_type, order_index, text_excerpt, _utc_now()),
            )
            self._conn.commit()
        return block_id

    def _create_topic_block(
        self,
        content_id: str,
        topic_title: str,
        topic_type: str,
    ) -> str:
        """Create a topic block. Returns topic_block_id."""
        tid = _random_id("top")
        if not self._dry_run:
            self._conn.execute(
                """
                INSERT INTO topic_blocks
                    (topic_block_id, content_id, topic_title, topic_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tid, content_id, topic_title, topic_type, _utc_now()),
            )
            self._conn.commit()
        return tid

    def _bind_name(
        self,
        subject_type: str,
        subject_id: str,
        namespace: str,
        name_kind: str,
        display_value: str,
        stage: Optional[str] = None,
        is_primary: bool = False,
    ) -> str:
        """Create a name binding. Returns name_binding_id."""
        binding_id = _random_id("nb")
        self.stats.name_bindings += 1

        if not self._dry_run:
            self._conn.execute(
                """
                INSERT INTO name_bindings
                    (name_binding_id, subject_type, subject_id, stage,
                     namespace, name_kind, display_value, is_primary,
                     valid_from, valid_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    binding_id, subject_type, subject_id, stage,
                    namespace, name_kind, display_value,
                    1 if is_primary else 0, _utc_now(),
                ),
            )
            self._conn.commit()

        return binding_id

    def _get_name_bindings(
        self,
        subject_id: str,
        namespace: str,
        name_kind: str,
    ) -> list[dict]:
        """Get current name bindings for a subject."""
        rows = self._conn.execute(
            """
            SELECT * FROM name_bindings
            WHERE subject_id = ? AND namespace = ? AND name_kind = ?
              AND valid_to IS NULL
            """,
            (subject_id, namespace, name_kind),
        ).fetchall()
        return [dict(r) for r in rows]

    def _infer_stage_from_path(self, path: Path) -> Optional[str]:
        """Infer the canonical F-stage from a file path."""
        parts = path.parts
        for part in parts:
            if part in _LEGACY_STAGE_MAP:
                return _LEGACY_STAGE_MAP[part]
            if part in _CANONICAL_STAGES:
                return part
        return None

    def _infer_content_id_for_stage_output(self, item: InventoryItem) -> Optional[str]:
        """Try to find a content_id for a stage output file."""
        # Look for a co-located manifest or content_id in the path
        # Heuristic: check if parent dir name matches a known content_id
        parent_name = item.path.parent.name
        if parent_name in self._content_ids:
            return self._content_ids[parent_name]

        # Try to find by filename match in manifests
        for manifest in self._manifest_cache.values():
            if manifest.get("metadata", {}).get("original_filename") == item.path.name:
                return manifest.get("content_id")

        return None

    @property
    def _manifest_cache(self) -> dict[str, dict]:
        """Cache of loaded manifests keyed by content_id."""
        if not hasattr(self, "_manifest_cache_data"):
            self._manifest_cache_data = {}
            manifest_dir = self._data_root / "processed" / "manifests"
            if manifest_dir.exists():
                for p in manifest_dir.glob("*.json"):
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        cid = data.get("content_id")
                        if cid:
                            self._manifest_cache_data[cid] = data
                    except (json.JSONDecodeError, OSError):
                        continue
        return self._manifest_cache_data


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


# ── CLI ──────────────────────────────────────────────────────────────────────


@click.group()
@click.option(
    "--project-memory-db",
    type=click.Path(),
    default=str(PROJECT_MEMORY_DB),
    help="Path to finer.project.sqlite3",
)
@click.pass_context
def cli(ctx: click.Context, project_memory_db: str) -> None:
    """Project Memory legacy backfill tool."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(project_memory_db)
    ctx.obj["data_root"] = DATA_ROOT
    ctx.obj["storage_root"] = STORAGE_ROOT


@cli.command()
@click.pass_context
def inventory(ctx: click.Context) -> None:
    """Scan legacy directories and report what would be imported."""
    data_root: Path = ctx.obj["data_root"]
    click.echo(f"Scanning: {data_root}")
    click.echo()

    result = run_inventory(data_root)
    total = sum(len(v) for v in result.values())

    click.echo("=== Inventory ===")
    for category, items in result.items():
        click.echo(f"  {category}: {len(items)} files")
        for item in items[:5]:
            click.echo(f"    - {item.path.name} ({item.source_platform})")
        if len(items) > 5:
            click.echo(f"    ... and {len(items) - 5} more")
    click.echo()
    click.echo(f"Total: {total} files")


@cli.command()
@click.option("--write", is_flag=True, default=False, help="Enable actual writes (default is dry-run)")
@click.pass_context
def backfill(ctx: click.Context, write: bool) -> None:
    """Run the full backfill pipeline."""
    db_path: Path = ctx.obj["db_path"]
    data_root: Path = ctx.obj["data_root"]
    storage_root: Path = ctx.obj["storage_root"]
    dry_run = not write

    click.echo(f"Mode: {'dry-run' if dry_run else 'write'}")
    click.echo(f"Database: {db_path}")
    click.echo(f"Data root: {data_root}")
    click.echo()

    # Open DB connection
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    try:
        engine = BackfillEngine(
            conn=conn,
            data_root=data_root,
            storage_root=storage_root,
            dry_run=dry_run,
        )

        # Run all 12 phases
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

        # Print summary
        stats = engine.stats
        click.echo()
        click.echo("=== Backfill Summary ===")
        click.echo(f"Mode: {stats.mode}")
        click.echo(f"Source groups: {stats.source_groups_total} (new: {stats.source_groups_new}, existing: {stats.source_groups_existing})")
        click.echo(f"Source records: {stats.source_records_total} (new: {stats.source_records_new}, existing: {stats.source_records_existing})")
        click.echo(f"Content identities: {stats.content_identities_total} (new: {stats.content_identities_new}, existing: {stats.content_identities_existing})")
        click.echo(f"Content versions: {stats.content_versions}")
        click.echo(f"Artifacts: {stats.artifacts}")
        click.echo(f"Name bindings: {stats.name_bindings}")
        click.echo(f"Asset index entries: {stats.asset_index_entries}")
        click.echo(f"Integrity: {stats.integrity_status}")

    finally:
        conn.close()


if __name__ == "__main__":
    cli()
