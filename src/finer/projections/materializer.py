"""PROJ-1 读模型物化 —— 把 CRD-1/CRD-3 视图物化到 SQLite 投影表。

架构地位（roadmap §6.6）：**投影是可随时从文件真值重建的缓存，不是真相源。**
payload 存 pydantic JSON 整体——投影表不复刻字段结构，schema 演进只发生在
`schemas/credibility.py` 一处，表不跟着漂移。

写入原子性：先写临时库文件，成功后 ``os.replace`` 覆盖——读方（API）任一
时刻打开的都是完整一致的库，没有半成品状态。

表结构（2026-08-04 用户授权新建）：

    creator_record_cards(creator_id, signal_class, payload, computed_at)
    ticker_consensus(ticker, payload, computed_at)
    projection_meta(key, value)          -- computed_at 水印、来源计数
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from finer.credibility.consensus import build_all_ticker_consensus
from finer.credibility.record_card import build_record_cards
from finer.schemas.credibility import CreatorRecordCard, TickerConsensusView

logger = logging.getLogger(__name__)

PROJECTION_FILENAME = "projections.sqlite3"

#: 投影 payload 的 schema 版本。**改了 CRD 视图的字段就要 +1。**
#: 没有它的话，加字段后忘记重跑物化，读侧会静默返回缺字段的旧 payload——
#: 2026-08-05 实测踩到：加了 latest_report_date 后 /ticker 的陈旧度横幅
#: 一直不出现，而 API 与前端都「正常」，因为 None 是合法值。
PROJECTION_SCHEMA_VERSION = "2"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS creator_record_cards (
    creator_id   TEXT NOT NULL,
    signal_class TEXT NOT NULL DEFAULT '',
    payload      TEXT NOT NULL,
    computed_at  TEXT NOT NULL,
    PRIMARY KEY (creator_id, signal_class)
);
CREATE TABLE IF NOT EXISTS ticker_consensus (
    ticker      TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    computed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def projection_path(data_root: Path) -> Path:
    return data_root / PROJECTION_FILENAME


def materialize_projections(
    data_root: Path,
    *,
    signal_classes: tuple = ("broker_recommendation",),
) -> Dict[str, int]:
    """从文件真值重建全部投影。返回各表行数（供 CLI 报告与断言）。"""
    from finer.services.repository import TradeActionRepository

    computed_at = datetime.now().isoformat(timespec="seconds")

    intents = []
    for path in glob.glob(str(data_root / "F3_intents" / "bri_*.json")):
        try:
            intents.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue

    repo = TradeActionRepository(
        db_path=data_root / "cache" / "trade_actions.db",
        action_dir=data_root / "F5_executed",
    )
    actions = repo.load_all_actions()

    views = build_all_ticker_consensus(intents)
    cards_by_class = {
        sc: build_record_cards(actions, signal_class=sc) for sc in signal_classes
    }

    target = projection_path(data_root)
    tmp = target.with_suffix(".sqlite3.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(_SCHEMA)
        for sc, cards in cards_by_class.items():
            conn.executemany(
                "INSERT INTO creator_record_cards VALUES (?, ?, ?, ?)",
                [
                    (c.creator_id, sc or "", c.model_dump_json(), computed_at)
                    for c in cards
                ],
            )
        conn.executemany(
            "INSERT INTO ticker_consensus VALUES (?, ?, ?)",
            [
                (ticker, view.model_dump_json(), computed_at)
                for ticker, view in views.items()
            ],
        )
        conn.executemany(
            "INSERT INTO projection_meta VALUES (?, ?)",
            [
                ("schema_version", PROJECTION_SCHEMA_VERSION),
                ("computed_at", computed_at),
                ("source_intents", str(len(intents))),
                ("source_actions", str(len(actions))),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, target)

    return {
        "creator_record_cards": sum(len(c) for c in cards_by_class.values()),
        "ticker_consensus": len(views),
        "source_intents": len(intents),
        "source_actions": len(actions),
    }


# ---------------------------------------------------------------------------
# 读侧（API 消费）
# ---------------------------------------------------------------------------


def _schema_current(conn: sqlite3.Connection) -> bool:
    """投影 payload 版本是否与当前代码一致；不一致视同不可用，回退活算。

    宁可慢也不能供错——缺字段的旧 payload 在 schema 上完全合法，
    只会让新功能静默失效。
    """
    try:
        row = conn.execute(
            "SELECT value FROM projection_meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.Error:
        return False
    if row is None or row[0] != PROJECTION_SCHEMA_VERSION:
        logger.warning(
            "投影 schema 版本为 %s，当前代码需要 %s —— 回退活算。"
            "请跑 scripts/materialize_projections.py 重建。",
            row[0] if row else "(缺失)", PROJECTION_SCHEMA_VERSION,
        )
        return False
    return True


def read_consensus(data_root: Path, canonical: str) -> Optional[TickerConsensusView]:
    """从投影读一只标的；库不存在/版本过期/无此行返回 None（调用方回退活算）。"""
    path = projection_path(data_root)
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        if not _schema_current(conn):
            return None
        row = conn.execute(
            "SELECT payload FROM ticker_consensus WHERE ticker = ?", (canonical,)
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return TickerConsensusView.model_validate_json(row[0]) if row else None


def read_record_cards(
    data_root: Path, signal_class: Optional[str]
) -> Optional[list]:
    """从投影读记录卡列表（保持物化时的稳定输出序）；不可用返回 None。"""
    path = projection_path(data_root)
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        if not _schema_current(conn):
            return None
        rows = conn.execute(
            "SELECT payload FROM creator_record_cards WHERE signal_class = ?",
            (signal_class or "",),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not rows:
        return None
    cards = [CreatorRecordCard.model_validate_json(r[0]) for r in rows]
    cards.sort(key=lambda c: -c.n_settled)
    return cards
