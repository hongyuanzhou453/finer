# Project Memory Storage v1

> Status: design draft
> Scope: F0-F8 durable storage, restart recovery, frontend asset loading
> Created: 2026-05-13
> Decision update: long-lived content identity, first-class block/topic tables,
> SQLite FTS5 asset search, multi-root service readiness, migration runner

## 1. Purpose

Project Memory Storage v1 defines the durable storage contract for Finer OS. It
replaces ad hoc filesystem scanning as the primary way to recover project state
after backend or frontend restart.

Project Memory is not a single cache table. It is the combination of:

1. SQLite durable catalog for identity, lineage, stage state, versions, and
   query indexes.
2. Content-addressed object store for raw and derived payload files.
3. Manifest files for portable per-content and per-artifact contract snapshots.
4. Rebuildable frontend asset index for fast F0-F8 browsing.

SQLite is the authoritative source for identity, lineage, and current stage
state. The object store is authoritative for payload bytes. Manifests are
portable snapshots and rebuild inputs. The frontend asset index is derived and
can be rebuilt.

## 2. Non-Goals

Project Memory v1 does not:

- Store large raw files, OCR outputs, transcripts, envelopes, or model payloads
  directly in SQLite.
- Use file names as stable business identities.
- Require synchronous full filesystem scans during backend startup.
- Treat legacy L0-L8 paths as canonical storage contracts.
- Replace F-stage schemas such as `ContentRecord`, `ContentEnvelope`,
  `TopicBlock`, `NormalizedInvestmentIntent`, `PolicyMappingResult`,
  `TradeAction`, or `BacktestResult`.

## 3. Relationship To Existing Specs

| Existing document | Relationship |
|---|---|
| `docs/specs/f-stage-contracts.md` | Remains the canonical F0-F8 pipeline contract. Project Memory stores references to each stage output. |
| `docs/specs/f0-project-memory-contract.md` | Becomes a legacy F0-only hot-index design. Project Memory v1 generalizes it across F0-F8. |
| `docs/specs/canonical-asset-v1-contract.md` | Defines the frontend `AssetFile` API shape. Project Memory v1 defines the backend storage source from which that shape is built. |
| `docs/specs/f1-standardization-contract.md` | Remains canonical for F1 `ContentEnvelope` and `ContentBlock`. Project Memory stores F1 artifact identity, lineage, and stage status. |

## 4. Confirmed Architecture Decisions

The following decisions are part of v1, not deferred open questions:

1. `content_id` is a long-lived logical content identity. It is not a file
   name, path, payload hash, or one-time import ID.
2. F1 `ContentBlock` and F1.5 `TopicBlock` become first-class SQLite-indexed
   records in v1. Large block payloads still live in the object store.
3. `asset_index.search_text` uses SQLite FTS5 in v1. The FTS table is derived
   and rebuildable.
4. The service layer supports multiple Project Memory roots. v1 runtime exposes
   one active project by default; multi-root APIs remain conservative.
5. Schema migration uses a formal migration runner and migration ledger.
   FastAPI startup validates schema but never auto-migrates.

## 5. Core Principles

1. SQLite is the single source of truth for stable IDs, lineage, stage state,
   schema versions, and queryable metadata.
2. Payload bytes live in a content-addressed object store, not in SQLite.
3. Every source, content item, object, artifact, stage status, and frontend
   asset has a stable ID independent of display names and filesystem paths.
4. Name lineage is first-class structured data, not only JSON metadata.
5. `/api/files` must be catalog-first. Filesystem scanning is only a degraded
   fallback and must report degraded source status.
6. Backend startup must be bounded. It may open SQLite, validate schema, and
   read summary counts, but must not recursively rebuild storage on the request
   path.
7. Derived indexes must be rebuildable from authoritative tables and manifests.
8. Schema changes are explicit migrations with checksums. Existing migration
   files are immutable after application.

## 6. Storage Root Layout

Canonical storage should be rooted under `data/project_memory/` and
`data/storage/`.

```text
data/
  project_memory/
    project_registry.sqlite3
    finer.project.sqlite3
    schema/
      001_initial.sql
      002_*.sql
    snapshots/
      schema_snapshot.json
      storage_health.json

  storage/
    objects/
      sha256/
        ab/
          cd/
            <sha256>
    manifests/
      content/
        <content_id>/
          manifest.v1.json
      artifacts/
        <artifact_id>.json
    materialized/
      F0/
      F1/
      F1_5/
      F2/
      F3/
      F4/
      F5/
      F6/
      F7/
      F8/
    runs/
      <run_id>/
```

Legacy directories such as `data/raw/`, `data/processed/`, `data/F0_intake/`,
`data/F1_standardized/`, and deprecated `data/L*` paths may be read during
backfill or degraded recovery. They must not be the primary runtime query path
after Project Memory v1 is enabled.

`project_registry.sqlite3` is optional for single-root deployments but required
when one backend manages multiple Project Memory roots. Each project root still
owns its own `finer.project.sqlite3`.

## 7. ID Contract

| ID | Owner | Stability rule |
|---|---|---|
| `project_id` | Project registry | Backend-visible project handle. Stable across process restarts. |
| `project_instance_id` | Project Memory | Created once per project storage root. |
| `source_group_id` | Source layer | Stable per import batch, connector, folder, chat, notebook, or source collection. |
| `source_record_id` | Source layer | Stable per imported source item. Prefer deterministic ID from source type + external ID + content hash. |
| `content_id` | Content identity layer | Long-lived Finer OS identity for one logical content item. Must not depend on display name, materialized path, or payload hash. |
| `content_version_id` | Content identity layer | Stable identity for one version or revision of a logical content item. |
| `block_id` | F1 block layer | Stable identity for a canonical F1 block within a content version. |
| `topic_block_id` | F1.5 topic layer | Stable identity for an assembled semantic topic block. |
| `object_id` | Object store | Stable content-addressed object ID, usually `sha256:<hash>`. |
| `artifact_id` | Artifact layer | Stable per stage output artifact. Deterministic when stage + content + artifact type + payload hash are known. |
| `run_id` | Runtime layer | Unique per pipeline or import execution. |
| `asset_id` | Frontend index | Stable derived ID for a content-stage view. Usually `<stage>:<content_id>` unless one content has multiple visible assets in the same stage. |

IDs must be generated by storage services, not by frontend code.

`content_hash` is dedupe evidence, not the long-lived business identity. A minor
source edit should create a new `content_version_id`, not necessarily a new
`content_id`. A repost or duplicate import should create a new
`source_record_id` and link to an existing `content_id` only when identity
confidence is high enough.

## 8. SQLite Schema

### 8.1 Project Registry, Metadata, And Migration Tables

```sql
CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  project_instance_id TEXT NOT NULL UNIQUE,
  project_name TEXT NOT NULL,
  project_root TEXT NOT NULL,
  storage_root TEXT NOT NULL,
  status TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE project_memory_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL,
  applied_by TEXT,
  execution_ms INTEGER NOT NULL
);
```

Reserved `project_memory_meta.key` values:

| Key | Meaning |
|---|---|
| `schema_version` | Current Project Memory schema version. |
| `project_instance_id` | Stable ID for this project memory root. |
| `storage_root` | Absolute or project-relative storage root. |
| `object_store_root` | Object payload root. |
| `created_at` | Project Memory creation time. |
| `last_rebuild_at` | Last full derived-index rebuild time. |
| `last_health_check_at` | Last storage health check time. |

Migration rules:

1. Migrations are stored as immutable SQL files.
2. Startup validates applied versions and checksums, but never runs migrations.
3. A checksum mismatch is `schema_mismatch`.
4. Any schema change after a migration is applied requires a new migration file.

Recommended migration layout:

```text
src/finer/services/project_memory/migrations/
  001_initial_project_memory.sql
  002_content_identity.sql
  003_blocks_and_topics.sql
  004_asset_fts.sql
```

Recommended commands:

```bash
python -m finer.scripts.project_memory_migrate status
python -m finer.scripts.project_memory_migrate upgrade
python -m finer.scripts.project_memory_migrate verify
```

### 8.2 Source Tables

```sql
CREATE TABLE source_groups (
  source_group_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_platform TEXT,
  importer TEXT,
  source_uri TEXT,
  imported_at TEXT NOT NULL,
  metadata_json TEXT
);

CREATE TABLE source_records (
  source_record_id TEXT PRIMARY KEY,
  source_group_id TEXT NOT NULL REFERENCES source_groups(source_group_id),
  external_id TEXT,
  source_uri TEXT,
  original_filename TEXT,
  original_title TEXT,
  source_platform TEXT,
  content_hash TEXT,
  imported_at TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT
);

CREATE INDEX idx_source_records_group
  ON source_records(source_group_id);

CREATE INDEX idx_source_records_hash
  ON source_records(content_hash);
```

`source_groups` describes the import context: Feishu chat, Feishu folder,
local upload batch, WeChat account, Bilibili creator, NotebookLM notebook, or
manual import group.

`source_records` describes one imported item before Finer pipeline
standardization.

### 8.3 Long-Lived Content Identity Tables

```sql
CREATE TABLE content_identities (
  content_id TEXT PRIMARY KEY,
  identity_scheme TEXT NOT NULL,
  stable_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retired_at TEXT,
  metadata_json TEXT,
  UNIQUE(identity_scheme, stable_key)
);

CREATE TABLE content_versions (
  content_version_id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES content_identities(content_id),
  content_hash TEXT,
  manifest_id TEXT,
  version_no INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  change_reason TEXT,
  metadata_json TEXT,
  UNIQUE(content_id, version_no)
);

CREATE TABLE source_content_links (
  source_record_id TEXT NOT NULL REFERENCES source_records(source_record_id),
  content_id TEXT NOT NULL REFERENCES content_identities(content_id),
  link_reason TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  created_at TEXT NOT NULL,
  PRIMARY KEY (source_record_id, content_id)
);

CREATE TABLE contents (
  content_id TEXT PRIMARY KEY REFERENCES content_identities(content_id),
  active_content_version_id TEXT REFERENCES content_versions(content_version_id),
  primary_source_record_id TEXT REFERENCES source_records(source_record_id),
  content_type TEXT,
  current_stage TEXT NOT NULL,
  canonical_title TEXT,
  frontend_display_name TEXT,
  latest_manifest_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE INDEX idx_content_versions_content
  ON content_versions(content_id, version_no DESC);

CREATE INDEX idx_source_content_links_content
  ON source_content_links(content_id);

CREATE INDEX idx_contents_primary_source
  ON contents(primary_source_record_id);

CREATE INDEX idx_contents_current_stage
  ON contents(current_stage, status, updated_at DESC);
```

`content_identities` owns the long-lived logical identity. `content_versions`
tracks revisions and changed payloads. `source_content_links` records how one
or more imported source records map to a logical content item. `contents` is the
current-state projection for a logical content item and keeps high-frequency
fields convenient for stage queries.

Content ID generation policy:

| Input condition | Policy |
|---|---|
| Stable external ID exists | Use deterministic identity from source platform + external ID under project namespace. |
| Existing manifest already has a trusted `content_id` | Preserve it and register it in `content_identities`. |
| Local/manual upload without stable external ID | Generate a long-lived `cnt_<uuid>` identity on first import. |
| Same payload appears from multiple sources | Link multiple `source_record_id` rows to one `content_id` only after explicit dedupe confidence. |
| Source content is revised | Keep `content_id`, create a new `content_version_id`. |

### 8.4 Object And Manifest Tables

```sql
CREATE TABLE storage_objects (
  object_id TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  storage_uri TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  mime_type TEXT,
  created_at TEXT NOT NULL,
  exists_verified_at TEXT
);

CREATE TABLE manifests (
  manifest_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  schema_name TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  object_id TEXT NOT NULL REFERENCES storage_objects(object_id),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_manifests_subject
  ON manifests(subject_type, subject_id, created_at DESC);
```

`storage_uri` should be project-relative unless an external object store is
explicitly configured. The object store should use atomic writes and verify
SHA-256 before registration.

### 8.5 Artifact Tables

```sql
CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES contents(content_id),
  stage TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  role TEXT NOT NULL,
  object_id TEXT NOT NULL REFERENCES storage_objects(object_id),
  manifest_id TEXT REFERENCES manifests(manifest_id),
  schema_name TEXT,
  schema_version TEXT,
  run_id TEXT,
  artifact_version INTEGER NOT NULL,
  is_canonical INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  metadata_json TEXT
);

CREATE TABLE artifact_edges (
  parent_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  child_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  relation TEXT NOT NULL,
  PRIMARY KEY (parent_artifact_id, child_artifact_id, relation)
);

CREATE INDEX idx_artifacts_content_stage
  ON artifacts(content_id, stage, is_canonical DESC, created_at DESC);

CREATE INDEX idx_artifacts_stage_type
  ON artifacts(stage, artifact_type, created_at DESC);
```

Allowed `artifacts.stage` values are canonical F-stage names:

```text
F0, F1, F1_5, F2, F3, F4, F5, F6, F7, F8, F_PLUS
```

Legacy values such as `L0`, `L1`, or `V0` must not be inserted into new rows.
When legacy inputs are backfilled, their legacy path may be stored in
`metadata_json`, but canonical `stage` must use F-stage naming.

Common `artifact_edges.relation` values:

| Relation | Meaning |
|---|---|
| `derived_from` | Child payload was derived from parent payload. |
| `standardizes` | F1 artifact standardizes an F0 artifact. |
| `assembles` | F1.5 topic artifact assembles F1 blocks. |
| `anchors` | F2 artifact anchors F1/F1.5 evidence. |
| `extracts_intent_from` | F3 intent artifact extracts from upstream evidence. |
| `maps_policy_from` | F4 policy artifact maps an F3 intent. |
| `executes_from` | F5 trade action artifact executes from F3/F4 canonical inputs. |
| `reviews` | F6 review artifact reviews an upstream action or evidence. |
| `backtests` | F8 artifact backtests an upstream action or policy. |

### 8.6 First-Class Block And Topic Tables

F1 blocks and F1.5 topic blocks are first-class query records in v1. SQLite
stores identity, ordering, references, short excerpts, and metadata. Full text
or large structured payloads stay in `storage_objects`.

```sql
CREATE TABLE content_blocks (
  block_id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES content_identities(content_id),
  content_version_id TEXT REFERENCES content_versions(content_version_id),
  artifact_id TEXT REFERENCES artifacts(artifact_id),
  stage TEXT NOT NULL,
  block_type TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  parent_block_id TEXT REFERENCES content_blocks(block_id),
  text_object_id TEXT REFERENCES storage_objects(object_id),
  text_excerpt TEXT,
  start_offset INTEGER,
  end_offset INTEGER,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE topic_blocks (
  topic_block_id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES content_identities(content_id),
  source_artifact_id TEXT REFERENCES artifacts(artifact_id),
  topic_title TEXT NOT NULL,
  topic_type TEXT NOT NULL,
  start_block_index INTEGER,
  end_block_index INTEGER,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE topic_block_members (
  topic_block_id TEXT NOT NULL REFERENCES topic_blocks(topic_block_id),
  block_id TEXT NOT NULL REFERENCES content_blocks(block_id),
  order_index INTEGER NOT NULL,
  PRIMARY KEY (topic_block_id, block_id)
);

CREATE INDEX idx_content_blocks_content_order
  ON content_blocks(content_id, stage, order_index);

CREATE INDEX idx_content_blocks_version
  ON content_blocks(content_version_id, order_index);

CREATE INDEX idx_topic_blocks_content
  ON topic_blocks(content_id, created_at DESC);
```

Rules:

1. F1 creates `content_blocks` for canonical `ContentBlock` records.
2. F1.5 creates `topic_blocks` and `topic_block_members`.
3. F2 evidence may reference `block_id` or `topic_block_id`, not only raw
   payload paths.
4. `text_excerpt` is for preview and search hints only; it must not become the
   canonical full text store.

### 8.7 Name Lineage Tables

Name lineage must be queryable. JSON-only lineage is insufficient because the
frontend and pipeline need stable mappings across source names, F0 display
names, F1 envelope names, split block names, and materialized filenames.

```sql
CREATE TABLE name_bindings (
  name_binding_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  stage TEXT,
  namespace TEXT NOT NULL,
  name_kind TEXT NOT NULL,
  display_value TEXT NOT NULL,
  normalized_value TEXT,
  path_safe_value TEXT,
  is_primary INTEGER NOT NULL DEFAULT 0,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE INDEX idx_name_bindings_subject
  ON name_bindings(subject_type, subject_id, namespace, name_kind);

CREATE INDEX idx_name_bindings_primary
  ON name_bindings(subject_type, subject_id, stage, is_primary);
```

`subject_type` values:

```text
source_group, source_record, content, content_version, artifact, block,
topic_block, asset
```

Recommended `namespace.name_kind` values:

| Namespace | Name kind | Example meaning |
|---|---|---|
| `source` | `original_filename` | File name from local disk, Feishu, WeChat, Bilibili, or upload source. |
| `source` | `original_title` | Title from source system. |
| `f0` | `frontend_display_name` | Name shown in F0 intake UI. |
| `f1` | `envelope_title` | Canonical `ContentEnvelope.title`. |
| `f1` | `block_title` | Derived title for a `ContentBlock`. |
| `f1` | `split_filename` | File name used when a long content item is split into materialized parts. |
| `f1_5` | `topic_title` | `TopicBlock.topic_title`. |
| `artifact` | `materialized_filename` | Actual filename written under `data/storage/materialized/`. |
| `export` | `display_name` | User-facing export name. |

Rules:

1. Every `content_id` must have at least one primary display name.
2. Every materialized artifact must have a `materialized_filename` binding.
3. If a file is split, the split artifact must preserve both the parent content
   display name and its own split name.
4. Name changes insert new bindings and close old bindings with `valid_to`;
   historical bindings must not be overwritten in place unless correcting an
   invalid backfill.

### 8.8 Pipeline Runtime Tables

```sql
CREATE TABLE pipeline_runs (
  run_id TEXT PRIMARY KEY,
  run_type TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  input_ref TEXT,
  summary_json TEXT
);

CREATE TABLE stage_status (
  content_id TEXT NOT NULL REFERENCES contents(content_id),
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  latest_artifact_id TEXT REFERENCES artifacts(artifact_id),
  error_code TEXT,
  error_message TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (content_id, stage)
);

CREATE INDEX idx_stage_status_stage
  ON stage_status(stage, status, updated_at DESC);

CREATE INDEX idx_pipeline_runs_status
  ON pipeline_runs(run_type, status, started_at DESC);
```

`stage_status.status` values:

```text
missing, queued, running, ready, partial, failed, skipped, deprecated
```

Restart recovery uses `stage_status`, not recursive directory scans.

### 8.9 Frontend Asset Index And FTS5 Search

`asset_index` is a derived table for frontend performance. It is not the
authoritative storage layer and may be rebuilt from `contents`, `stage_status`,
`artifacts`, `name_bindings`, `source_records`, blocks, topics, and manifests.

```sql
CREATE TABLE asset_index (
  asset_id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL REFERENCES contents(content_id),
  stage TEXT NOT NULL,
  display_name TEXT NOT NULL,
  subtitle TEXT,
  source_platform TEXT,
  source_type TEXT,
  content_type TEXT,
  source_group_id TEXT,
  latest_artifact_id TEXT REFERENCES artifacts(artifact_id),
  manifest_id TEXT REFERENCES manifests(manifest_id),
  status TEXT NOT NULL,
  sort_key TEXT,
  updated_at TEXT NOT NULL,
  search_text TEXT,
  metadata_json TEXT
);

CREATE INDEX idx_asset_index_stage
  ON asset_index(stage, status, sort_key DESC);

CREATE INDEX idx_asset_index_content
  ON asset_index(content_id, stage);

CREATE INDEX idx_asset_index_source_group
  ON asset_index(source_group_id, stage);

CREATE VIRTUAL TABLE asset_index_fts USING fts5(
  asset_id UNINDEXED,
  display_name,
  subtitle,
  search_text,
  content='asset_index',
  content_rowid='rowid'
);
```

The frontend may query `asset_index` directly through `/api/files`, but any
write to `asset_index` must be treated as projection maintenance. If
`asset_index` is empty or stale while authoritative tables are healthy, the
backend should rebuild it or return a `degraded` diagnostic, not fall back to
legacy scanning silently.

`asset_index_fts` is also derived. It may be deleted and rebuilt from
`asset_index`. Search requests use `asset_index_fts JOIN asset_index`; normal
tier browsing uses `asset_index` without FTS.

## 9. Stage-To-Storage Mapping

| Stage | Input identity | Required stored output |
|---|---|---|
| F0 | `source_record_id` | `content_id`, `content_version_id`, F0 artifact, source name bindings, `stage_status(F0)` |
| F1 | `content_id` + `content_version_id` + F0 artifact | `ContentEnvelope` artifact, `content_blocks`, F1 name bindings, `stage_status(F1)` |
| F1.5 | F1 envelope/block artifact + `content_blocks` | `TopicAssemblyResult` artifact, `topic_blocks`, `topic_block_members`, topic name bindings, `stage_status(F1_5)` |
| F2 | F1/F1.5 artifacts | quality/entity/temporal anchor artifacts, `stage_status(F2)` |
| F3 | F2 evidence artifacts | intent artifacts, `stage_status(F3)` |
| F4 | F3 intent artifacts | policy mapping artifacts, `stage_status(F4)` |
| F5 | F3 intent + F4 policy artifacts | canonical trade action artifacts, `stage_status(F5)` |
| F6 | F5 or evidence artifacts | review feedback artifacts, `stage_status(F6)` |
| F7 | content and viewpoint artifacts | timeline artifacts, `stage_status(F7)` |
| F8 | F5/F7 artifacts | backtest result artifacts, `stage_status(F8)` |

F5 must not create canonical `TradeAction` directly from raw text. Project
Memory should make this visible by recording artifact edges from F3 and F4 into
F5. Any F5 artifact missing those edges is `non_canonical`.

## 10. API Query Contract

### 10.1 `/api/files`

`GET /api/files?tier=F1&limit=50&offset=0`

Primary query path:

1. Validate Project Memory schema version.
2. Query `asset_index` by canonical F-stage.
3. If `q` is present, query `asset_index_fts` and join back to `asset_index`.
4. If `asset_index` is stale, rebuild projection from authoritative tables when
   safe.
5. Return `source: "catalog"` when served from Project Memory.
6. Return `source: "degraded_scan"` only when Project Memory is unavailable and
   explicit degraded fallback is enabled.

Response metadata should include:

```json
{
  "source": "catalog",
  "projectMemory": {
    "projectId": "<active_project_id>",
    "schemaVersion": "1",
    "dbPath": "data/project_memory/finer.project.sqlite3",
    "assetIndexUpdatedAt": "2026-05-13T00:00:00Z",
    "degraded": false
  }
}
```

Each returned asset should expose:

```json
{
  "id": "F1:<content_id>",
  "contentId": "<content_id>",
  "contentVersionId": "<content_version_id>",
  "stage": "F1",
  "name": "<frontend display name>",
  "sourceRecordId": "<source_record_id>",
  "sourceGroupId": "<source_group_id>",
  "latestArtifactId": "<artifact_id>",
  "manifestId": "<manifest_id>",
  "nameLineage": {
    "originalFilename": "...",
    "f0DisplayName": "...",
    "f1EnvelopeTitle": "...",
    "splitFilename": "...",
    "materializedFilename": "..."
  }
}
```

### 10.2 `/api/system/diagnostics`

Diagnostics must explicitly report whether Project Memory is active.

Required fields:

```json
{
  "projectMemory": {
    "status": "healthy|degraded|missing|corrupt|schema_mismatch",
    "projectId": "<active_project_id>",
    "schemaVersion": "1",
    "dbPath": "...",
    "contentCount": 0,
    "contentVersionCount": 0,
    "blockCount": 0,
    "topicBlockCount": 0,
    "objectCount": 0,
    "artifactCount": 0,
    "assetIndexCount": 0,
    "assetFtsCount": 0,
    "lastRebuildAt": null
  }
}
```

If diagnostics do not include `projectMemory`, the runtime should be considered
not using Project Memory Storage v1.

## 11. Startup And Restart Recovery

Backend startup sequence:

1. Resolve the active Project Memory root from configuration or project
   registry.
2. Open SQLite in WAL mode.
3. Validate schema version and required tables.
4. Load counts and health metadata.
5. Mark Project Memory `healthy`, `degraded`, `missing`, `corrupt`, or
   `schema_mismatch`.
6. Serve catalog queries from SQLite if healthy or degraded with readable
   authoritative tables.
7. Schedule non-blocking repairs only when configured.

Startup must not:

- Recursively walk `data/`.
- Materialize F1 artifacts synchronously.
- Rewrite manifests.
- Perform schema migrations unless explicitly invoked by a migration command.
- Hide schema mismatch behind scan fallback.
- Auto-switch to another project root without explicit configuration.

The expected restart result is:

1. F0, F1, F1.5, F2, F3, F4, F5, F6, F7, and F8 sidebar counts load from
   `stage_status` and `asset_index`.
2. Clicking a tier queries SQLite and returns bounded paginated assets.
3. Missing payload files are reported as broken artifact/object references, not
   as missing content rows.
4. Name lineage remains available even if the materialized file has to be
   regenerated.

## 12. Multi-Root Runtime Model

Project Memory v1 supports multiple roots at the service layer while keeping the
default API surface single-project.

Runtime rules:

1. One backend may register multiple projects in `projects` or
   `project_registry.sqlite3`.
2. Exactly one project is active for default routes such as `/api/files`.
3. Project-scoped APIs may be added as `/api/projects/{project_id}/...`, but v1
   does not require broad multi-project frontend UX.
4. A request must never mix artifacts or source records from different project
   roots.
5. Switching the active project is an explicit administrative operation, not a
   side effect of startup fallback.

## 13. Backfill Strategy

Backfill from existing disk data should be explicit and idempotent.

Phases:

1. Inventory legacy files and manifests without writing.
2. Register `source_groups` and `source_records`.
3. Register `content_identities`, `content_versions`, and
   `source_content_links`.
4. Register `contents` current-state rows.
5. Register payloads into `storage_objects`.
6. Register F0/F1/F-stage artifacts.
7. Register `content_blocks`, `topic_blocks`, and `topic_block_members` when
   source payloads contain F1/F1.5 outputs.
8. Build `artifact_edges`.
9. Extract and normalize `name_bindings`.
10. Build `stage_status`.
11. Rebuild `asset_index` and `asset_index_fts`.
12. Run integrity checks.

Default mode must be dry-run. Write mode must be explicit.

Backfill must preserve:

- Original source filename.
- Original source title.
- F0 frontend display name.
- F1 envelope title.
- Split block or topic names.
- Materialized artifact filename.
- Legacy source path for audit.
- Existing trusted `content_id` values where available.

## 14. Integrity Checks

Minimum production checks:

```sql
-- No current content row without identity.
SELECT content_id FROM contents
WHERE content_id NOT IN (SELECT content_id FROM content_identities);

-- No content identity without any source link.
SELECT content_id FROM content_identities
WHERE content_id NOT IN (SELECT content_id FROM source_content_links);

-- No canonical artifact without object payload.
SELECT artifact_id FROM artifacts
WHERE is_canonical = 1
  AND object_id NOT IN (SELECT object_id FROM storage_objects);

-- No content without primary display name.
SELECT c.content_id
FROM contents c
LEFT JOIN name_bindings n
  ON n.subject_type = 'content'
 AND n.subject_id = c.content_id
 AND n.is_primary = 1
 AND n.valid_to IS NULL
WHERE n.name_binding_id IS NULL;

-- No visible frontend asset without status.
SELECT asset_id FROM asset_index
WHERE content_id NOT IN (SELECT content_id FROM contents);

-- No F1 topic member pointing at a missing block.
SELECT topic_block_id, block_id FROM topic_block_members
WHERE block_id NOT IN (SELECT block_id FROM content_blocks);
```

Additional application-level checks:

- Every F1 canonical artifact has a `source_record_id` reachable through
  `contents`.
- Every F1 materialized artifact has `name_bindings` for original name and
  materialized filename.
- No new row uses `L0-L8` or `V0-V6` as canonical stage.
- `asset_index` counts match `stage_status` for ready and partial rows.
- `asset_index_fts` can be rebuilt from `asset_index`.
- `/api/files` returns bounded results and never triggers LLM calls.
- Restarting backend preserves content, artifact, and asset counts.

## 15. Worktree Isolation Plan

Implementation must happen outside the dirty `main` worktree.

Recommended layout:

```text
/Users/zhouhongyuan/Desktop/finer/                 # current worktree, no storage implementation edits
/Users/zhouhongyuan/Desktop/finer-project-memory/  # isolated implementation worktree
```

Recommended implementation branch:

```text
codex/project-memory-storage-v1
```

Implementation agents must own disjoint scopes:

| Agent | Scope | Write boundary |
|---|---|---|
| Migration agent | Migration runner, SQL files, schema verification | `src/finer/services/project_memory/migrations/`, `src/finer/scripts/project_memory_migrate.py`, migration tests |
| Content identity agent | Long-lived content IDs, versions, source links | `src/finer/services/project_memory/identity.py`, identity tests |
| Storage schema agent | Connection layer and schema inspection | `src/finer/services/project_memory/connection.py`, `schema.py`, storage tests |
| Object/artifact agent | Object store and artifact ledger | `src/finer/services/project_memory/object_store.py`, `artifact_store.py`, artifact tests |
| Block/topic agent | F1 block and F1.5 topic storage | `src/finer/services/project_memory/block_store.py`, block/topic tests |
| Asset index/FTS agent | Rebuildable asset projection and FTS search | `src/finer/services/project_memory/asset_index.py`, FTS tests |
| Backfill agent | Legacy inventory and idempotent backfill | `src/finer/scripts/`, backfill tests |
| API agent | `/api/files` and diagnostics catalog-first behavior | `src/finer/api/routes/`, API tests |
| Frontend contract agent | TypeScript contracts and tier loading states | `src/finer_dashboard/`, frontend tests |
| Docs/validation agent | Spec updates and restart verification checklist | `docs/specs/`, validation docs |

Agents must not modify each other's write boundaries without coordination.

## 16. Acceptance Criteria

Project Memory Storage v1 is production-ready only when all checks pass:

1. Backend restart loads Project Memory without recursive directory scanning.
2. `/api/system/diagnostics` reports Project Memory status and counts.
3. `/api/files?tier=F0` returns from `source: "catalog"` with stable
   `contentId`, `sourceRecordId`, and name lineage.
4. `/api/files?tier=F1` returns from `source: "catalog"` with canonical F1
   artifact references and `content_blocks`.
5. F0 and F1 frontend tier switching works immediately after backend and
   frontend restart.
6. Deleting and rebuilding only `asset_index` does not lose content, artifact,
   or name lineage records.
7. Deleting and rebuilding `asset_index_fts` does not affect tier browsing.
8. Missing payload files are reported as integrity errors while catalog identity
   rows remain visible.
9. No startup path performs schema migration, full backfill, synchronous
   materialization, or LLM calls.
10. Legacy `f0-project-memory-contract.md` behavior is either migrated into
   Project Memory v1 or explicitly marked as superseded.
11. Existing F-stage contracts continue to use canonical F0-F8 naming only.
12. Migration status and checksum verification pass before runtime is marked
    healthy.

## 17. Deferred Decisions

These are intentionally deferred beyond v1:

1. Whether the frontend should expose full multi-project switching in v1 UI.
2. Whether FTS5 ranking should be replaced or supplemented by an external
   semantic/vector search layer.
3. Whether block-level full text should remain object-store only or gain a
   dedicated excerpt/search projection beyond `asset_index_fts`.
4. Whether artifact payloads should support remote object stores in addition to
   local filesystem storage.
