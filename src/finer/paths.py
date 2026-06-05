from __future__ import annotations

from pathlib import Path

# Canonical project root (3 levels up: paths.py → finer/ → src/ → repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"


RAW_FOLDERS = [
    "weekly_strategy",
    "daily_pre",
    "daily_post",
    "bilibili_video",
    "livestream",
    "wechat",
]

PROCESSED_FOLDERS = [
    "manifests",
    "documents",
    "transcripts",
    "candidate_events",
    "review_store",
    "approved_events",
]


def ensure_storage(root: Path) -> list[str]:
    created: list[str] = []

    data_root = root / "data"
    for path in [
        data_root / "raw" / "trader_ji",
        data_root / "raw" / "_inbox" / "unclassified",    # Feishu fallback
        data_root / "raw" / "_research" / "research_report",
        data_root / "raw" / "wechat",                      # WeChat articles
        data_root / "raw" / "bilibili" / "video",          # BBDown video
        data_root / "raw" / "bilibili" / "audio",          # BBDown audio
        data_root / "raw" / "bilibili" / "subtitle",       # BBDown subtitles
        data_root / "cache" / "wechat",                    # WeChat credentials cache
        data_root / "inbox",                                # Feishu download staging
        data_root / "processed" / "manifests",
        data_root / "processed" / "documents",
        data_root / "processed" / "transcripts",
        data_root / "processed" / "candidate_events",
        data_root / "processed" / "review_store",
        data_root / "processed" / "approved_events",
        data_root / "market" / "tushare" / "parquet",  # Tushare Parquet storage
    ]:
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))

    for folder in RAW_FOLDERS:
        raw_path = data_root / "raw" / "trader_ji" / folder
        raw_path.mkdir(parents=True, exist_ok=True)
        created.append(str(raw_path))

    return created


# F0 Project Memory SQLite index path — backed by Project Memory v1 DB
F0_INDEX_DB_PATH = DATA_ROOT / "project_memory" / "finer.project.sqlite3"

# Project Memory Storage v1
PROJECT_MEMORY_ROOT = DATA_ROOT / "project_memory"
PROJECT_MEMORY_DB = PROJECT_MEMORY_ROOT / "finer.project.sqlite3"
STORAGE_ROOT = DATA_ROOT / "storage"

# Market data (Tushare A-share local pipeline)
MARKET_DATA_ROOT = DATA_ROOT / "market" / "tushare"
MARKET_PARQUET_DIR = MARKET_DATA_ROOT / "parquet"
MARKET_DUCKDB_PATH = MARKET_DATA_ROOT / "meta.duckdb"


# ─────────────────────────────────────────────────────────────────────────────
# F0 canonical landing rules (shared contract — GATE freeze)
#
# Every channel adapter MUST land F0 outputs through these helpers so the disk
# layout is uniform across feishu / local upload / NotebookLM / wechat /
# wechat_channels / bilibili:
#
#   raw archive   -> data/raw/{platform}/...
#   ContentRecord -> data/F0_intake/{platform}/{content_id}.json
#   ImportReceipt -> data/F0_intake/{platform}/{content_id}.receipt.json
#
# These are pure path helpers: they DO NOT migrate existing data, create dirs,
# or write files. Callers decide when to mkdir/persist.
# ─────────────────────────────────────────────────────────────────────────────

RAW_ROOT = DATA_ROOT / "raw"
F0_INTAKE_ROOT = DATA_ROOT / "F0_intake"


def f0_raw_dir(platform: str, *subparts: str) -> Path:
    """Canonical raw-archive directory for a channel: ``data/raw/{platform}/<subparts...>``.

    ``subparts`` lets a channel namespace its raw payloads (e.g. creator id,
    media kind) without inventing its own root.
    """
    return RAW_ROOT.joinpath(platform, *subparts)


def f0_intake_dir(platform: str) -> Path:
    """Canonical F0 intake directory for a channel: ``data/F0_intake/{platform}``."""
    return F0_INTAKE_ROOT / platform


def f0_record_path(platform: str, content_id: str) -> Path:
    """Canonical ContentRecord path: ``data/F0_intake/{platform}/{content_id}.json``."""
    return f0_intake_dir(platform) / f"{content_id}.json"


def f0_receipt_path(platform: str, content_id: str) -> Path:
    """Canonical ImportReceipt path: ``data/F0_intake/{platform}/{content_id}.receipt.json``."""
    return f0_intake_dir(platform) / f"{content_id}.receipt.json"
