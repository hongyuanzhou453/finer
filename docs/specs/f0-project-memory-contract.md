# F0 Project Memory Contract

## Overview

F0 Project Memory is a SQLite-based hot index over the F0 intake layer's manifest files. It replaces the current `get_manifests_index()` approach that performs a full `os.walk` on every query, providing O(1) lookups and enabling the Import Console to display intake status without filesystem scanning.

The index is a **derived cache** -- the raw files and `ContentRecord`/manifest JSON remain the source of truth. The SQLite DB can be safely deleted and rebuilt from disk at any time.

## SQLite Schema

### content_records

Primary table storing one row per imported content item.

| Column | Type | Description |
|--------|------|-------------|
| content_id | TEXT PRIMARY KEY | Unique content identifier |
| source_type | TEXT NOT NULL | Content type: video, article, chat, etc. |
| source_platform | TEXT NOT NULL | Origin platform: feishu, bilibili, wechat, etc. |
| creator_id | TEXT | Platform-specific creator ID |
| creator_name | TEXT | Display name of the creator |
| title | TEXT | Content title |
| raw_path | TEXT NOT NULL | Relative path to raw file under data/raw/ |
| file_type | TEXT NOT NULL | File extension / MIME category |
| published_at | TEXT | Original publish timestamp (ISO 8601) |
| collected_at | TEXT NOT NULL | When the item was ingested (ISO 8601) |
| source_url | TEXT | Original URL on the source platform |
| external_source_id | TEXT | Platform-native ID (e.g. BV号, message_id) |
| dedupe_fingerprint | TEXT | Hash for duplicate detection |
| manifest_path | TEXT | Relative path to manifest JSON |
| import_run_id | TEXT | FK to import_runs.run_id |
| created_at | TEXT NOT NULL | Row creation timestamp |
| updated_at | TEXT NOT NULL | Row last-update timestamp |

### import_runs

Tracks each import execution for audit and retry.

| Column | Type | Description |
|--------|------|-------------|
| run_id | TEXT PRIMARY KEY | UUID of the import run |
| source_channel | TEXT NOT NULL | Channel: feishu, bilibili, wechat, local, notebooklm |
| started_at | TEXT NOT NULL | Run start timestamp (ISO 8601) |
| finished_at | TEXT | Run end timestamp (null if in progress) |
| status | TEXT NOT NULL | pending, running, completed, failed, partial |
| records_created | INTEGER DEFAULT 0 | New records inserted |
| records_skipped | INTEGER DEFAULT 0 | Duplicates or invalid records skipped |
| error_code | TEXT | Canonical error code if failed |
| error_message | TEXT | Human-readable error summary |

### index_metadata

Key-value store for index-level metadata.

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PRIMARY KEY | Metadata key |
| value | TEXT NOT NULL | Metadata value |

Reserved keys:
- `schema_version` -- current schema version for migration detection
- `last_rebuild_at` -- ISO 8601 timestamp of last full rebuild
- `last_rebuild_duration_ms` -- rebuild elapsed time in milliseconds
- `manifest_count_at_rebuild` -- manifest file count at last rebuild

## Query Shape

`F0IndexQuery` defines the canonical query interface:

```python
@dataclass(frozen=True)
class F0IndexQuery:
    source_type: str | None = None       # filter by content type
    source_platform: str | None = None   # filter by platform
    creator_id: str | None = None        # filter by creator
    sort_by: str = "collected_at"        # sort column
    sort_order: str = "desc"             # asc or desc
    limit: int = 50                      # page size
    offset: int = 0                      # pagination offset
```

All filter fields are optional; `None` means no filter on that dimension.

`F0IndexResult` wraps paginated results:

```python
@dataclass(frozen=True)
class F0IndexResult:
    records: list[dict]    # list of content_records rows as dicts
    total_count: int       # total matching records (before limit)
    page: int              # current page number (0-based)
    page_size: int         # limit value
    has_more: bool         # true if more pages exist
```

## Health Model

`F0IndexHealth` reports index status for the Import Console:

```python
@dataclass(frozen=True)
class F0IndexHealth:
    status: Literal["healthy", "stale", "missing", "rebuilding"]
    record_count: int                # rows in content_records
    last_rebuild_at: str | None      # ISO 8601
    last_rebuild_duration_ms: int | None
    manifest_count_on_disk: int      # current manifest file count
    drift: int                       # manifest_count - record_count
    db_path: str                     # absolute path to .db file
    db_size_bytes: int               # file size on disk
```

Status meanings:
- **healthy**: index exists, drift == 0
- **stale**: index exists but drift != 0
- **missing**: no .db file on disk
- **rebuilding**: rebuild in progress

`needs_rebuild` property returns `True` when status is `missing` or `stale`, or when `drift != 0`.

## Startup Rules

### Startup State Machine

`F0IndexStartupState` enumerates all possible index states at application boot:

| State | Condition | Behavior |
|-------|-----------|----------|
| `READY` | DB exists, schema valid, drift == 0 | Load index into memory, proceed |
| `STALE` | DB exists, schema valid, drift != 0 | Load stale data, schedule background rebuild |
| `MISSING` | No `.db` file on disk | Return missing status, do NOT scan raw dirs |
| `CORRUPT` | DB exists but cannot be opened or schema mismatch | Return corrupt status, do NOT scan raw dirs |

### `check_f0_index_on_startup`

Signature: `check_f0_index_on_startup(db_path: Path = F0_INDEX_DB_PATH) -> F0StartupResult`

Behavior rules:
1. If index exists and healthy → load, return `READY` with `action_taken = "loaded"`
2. If index exists but stale → load stale data, schedule background rebuild, return `STALE` with `action_taken = "background_rebuild_scheduled"`
3. If index missing → return `MISSING` with `action_taken = "none"`
4. If index corrupt → return `CORRUPT` with `action_taken = "none"`

**Prohibited operations** (must never execute at startup):
- Recursively scan `data/raw/`
- Walk `data/processed/manifests/`
- Block startup thread for rebuild
- Execute any `CREATE TABLE` or schema migration

### `rebuild_f0_index`

Signature: `rebuild_f0_index(db_path: Path = F0_INDEX_DB_PATH, *, background: bool = True) -> str`

Behavior rules:
1. Reads all manifest JSONs from `data/processed/manifests/`
2. Upserts into `content_records` table
3. Updates `index_metadata` with rebuild timestamp and duration
4. Does NOT read raw files — manifests are the source of truth
5. If `background=True`, runs in a background thread and returns `task_id`
6. If `background=False`, runs synchronously and returns `"sync_complete"`

### Red Lines

- Startup MUST NOT trigger synchronous full rebuild — at most schedule a background task
- Startup MUST NOT walk the filesystem to discover manifests
- Index is always derivable from manifests; corrupt/missing index is non-fatal

## API Contract

### `GET /api/f0-index/records`

Query F0 content records from the SQLite index.

**Parameters** (query string):

| Name | Type | Default | Description |
|------|------|---------|-------------|
| source_type | str? | null | Filter by content type (video, article, chat) |
| source_platform | str? | null | Filter by platform (feishu, bilibili, wechat) |
| creator_id | str? | null | Filter by creator |
| sort_by | str | "collected_at" | Sort column |
| sort_order | str | "desc" | Sort direction: asc or desc |
| limit | int | 50 (max 200) | Page size |
| offset | int | 0 | Pagination offset |

**Response shape**:
```json
{
  "ok": true,
  "data": {
    "records": [<content_record_row>, ...],
    "total_count": 123,
    "page": 0,
    "page_size": 50,
    "has_more": true
  }
}
```

**Error codes**: `F0_INDEX_001` (index missing, 503), `F0_INDEX_002` (query failed, 500)

---

### `GET /api/f0-index/health`

Return F0 index health status for the Import Console.

**Parameters**: none

**Response shape**:
```json
{
  "ok": true,
  "data": {
    "status": "healthy|stale|missing|rebuilding",
    "record_count": 42,
    "last_rebuild_at": "2026-05-11T10:00:00Z",
    "last_rebuild_duration_ms": 350,
    "manifest_count_on_disk": 42,
    "drift": 0,
    "db_path": "/absolute/path/to/f0_index.db",
    "db_size_bytes": 32768
  }
}
```

**Error codes**: `F0_INDEX_001` (index missing, 503), `F0_INDEX_002` (query failed, 500)

---

### `POST /api/f0-index/rebuild`

Explicitly trigger F0 index rebuild.

**Parameters** (query string):

| Name | Type | Default | Description |
|------|------|---------|-------------|
| background | bool | true | If true, rebuild runs in background and returns task_id; if false, blocks until complete |

**Response shape** (background=true):
```json
{
  "ok": true,
  "data": {
    "task_id": "uuid-string",
    "status": "started"
  }
}
```

**Response shape** (background=false):
```json
{
  "ok": true,
  "data": {
    "status": "completed",
    "records_upserted": 42,
    "duration_ms": 350
  }
}
```

**Error codes**: `F0_INDEX_003` (rebuild failed, 500)

## Red Lines

- First round does **not** create a real `.db` file or execute `CREATE TABLE`
- Schema contract is frozen before any implementation agent writes index code
- The raw files and manifest JSON remain the source of truth; SQLite is always derivable
- `content_records` must not store full content text -- only metadata and paths
- `import_runs.error_message` must not contain tokens, secrets, or auth headers
