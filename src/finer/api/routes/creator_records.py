"""信源历史记录卡只读 API（CRD-1 的消费入口，/discover 页的数据源）。

route 只做参数解析与响应格式化；聚合在 ``credibility/record_card.py``
（内部复用 build_scorecard + CRD-2 效力门）。

性能形态：load_all_actions 扫 4,400+ 文件（数秒级），进程内 TTL 缓存
（120s）——PROJ-1 投影表前的过渡，接口契约按投影消费方设计。

口径纪律：列表**不是排行榜**。顺序 = 已结算样本量降序（UI-1 拍板的
稳定输出序）；每张卡自带 sufficiency（含预测性主张裁决），前端必须按
display_policy 呈现——这条在 schema 层强制，绕不过。
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional

from fastapi import APIRouter, Query

from finer.credibility.record_card import build_record_cards
from finer.errors.exceptions import FinerError
from finer.paths import DATA_ROOT
from finer.schemas.credibility import CreatorRecordCard

router = APIRouter()

_TTL_SECONDS = 120.0
_lock = threading.Lock()
_cards_cache: dict = {}     # signal_class -> (built_at, List[CreatorRecordCard])


def _load_cards(signal_class: Optional[str]) -> List[CreatorRecordCard]:
    key = signal_class or "__all__"
    with _lock:
        now = time.monotonic()
        hit = _cards_cache.get(key)
        if hit is not None and (now - hit[0]) < _TTL_SECONDS:
            return hit[1]
        from finer.services.repository import TradeActionRepository

        repo = TradeActionRepository(
            db_path=DATA_ROOT / "cache" / "trade_actions.db",
            action_dir=DATA_ROOT / "F5_executed",
        )
        cards = build_record_cards(
            repo.load_all_actions(), signal_class=signal_class
        )
        _cards_cache[key] = (now, cards)
        return cards


@router.get("/records")
def list_creator_records(
    signal_class: Optional[str] = Query(
        default="broker_recommendation",
        description="记录口径；R6：券商与 KOL 不混在同一批卡里比较",
    ),
) -> dict:
    """全部信源的历史记录卡。顺序是稳定输出序（按已结算样本量），不是排名。"""
    cards = _load_cards(signal_class)
    return {
        "ok": True,
        "data": {
            "cards": [c.model_dump(mode="json") for c in cards],
            "signal_class": signal_class,
        },
    }


@router.get("/{creator_id}/record")
def get_creator_record(
    creator_id: str,
    signal_class: Optional[str] = Query(default="broker_recommendation"),
) -> dict:
    """单个信源的历史记录卡。"""
    for card in _load_cards(signal_class):
        if card.creator_id == creator_id:
            return {"ok": True, "data": card.model_dump(mode="json")}
    raise FinerError(
        "API_NTF_001",
        f"信源 {creator_id!r} 在口径 {signal_class!r} 下没有记录",
        stage="F5",
        operation="creator_record",
        retryable=False,
        fix_hint="确认 creator_id 写法（与 configs/creators/*.yaml 的 raw id 一致），"
                 "或改用 /api/creator/records 查看全部可用信源",
    )
