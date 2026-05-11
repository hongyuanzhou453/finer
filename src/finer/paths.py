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
        data_root / "backtests",
    ]:
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))

    for folder in RAW_FOLDERS:
        raw_path = data_root / "raw" / "trader_ji" / folder
        raw_path.mkdir(parents=True, exist_ok=True)
        created.append(str(raw_path))

    return created


# F0 Project Memory SQLite index path
F0_INDEX_DB_PATH = DATA_ROOT / "f0_index.db"
