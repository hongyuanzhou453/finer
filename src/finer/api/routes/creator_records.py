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

from fastapi import APIRouter, HTTPException, Query

from finer.credibility.aggregates import build_corpus_aggregates
from finer.credibility.ratio_slices import build_ratio_slices
from finer.credibility.record_card import build_record_cards
from finer.projections.materializer import read_record_cards
from finer.errors.exceptions import FinerError
from finer.paths import DATA_ROOT
from finer.schemas.credibility import (
    CorpusRatioSlices,
    CreatorRecordCard,
    RecordCorpusAggregates,
)

router = APIRouter()

_TTL_SECONDS = 120.0
_lock = threading.Lock()
_cards_cache: dict = {}     # signal_class -> (built_at, List[CreatorRecordCard])
_aggregates_cache: dict = {}  # signal_class -> (built_at, RecordCorpusAggregates)
_slices_cache: dict = {}      # (signal_class, dimension) -> (built_at, CorpusRatioSlices)


def _load_actions():
    """全量 F5 action（重扫描，数秒级）；只在 TTL 失效时走到这里。"""
    from finer.services.repository import TradeActionRepository

    repo = TradeActionRepository(
        db_path=DATA_ROOT / "cache" / "trade_actions.db",
        action_dir=DATA_ROOT / "F5_executed",
    )
    return repo.load_all_actions()


def _load_cards(signal_class: Optional[str]) -> List[CreatorRecordCard]:
    key = signal_class or "__all__"
    with _lock:
        now = time.monotonic()
        hit = _cards_cache.get(key)
        if hit is not None and (now - hit[0]) < _TTL_SECONDS:
            return hit[1]
        # 投影优先（PROJ-1）；不可用时回退扫文件活算
        projected = read_record_cards(DATA_ROOT, signal_class)
        if projected is not None:
            _cards_cache[key] = (now, projected)
            return projected
        cards = build_record_cards(_load_actions(), signal_class=signal_class)
        _cards_cache[key] = (now, cards)
        return cards


def _load_aggregates(signal_class: Optional[str]) -> RecordCorpusAggregates:
    """语料构成聚合（纯计数）。无投影表：聚合始终活算 + TTL 缓存。

    刻意不加投影表——新增 SQLite 表结构按项目规范需要单独确认；计数聚合
    单次全量扫描数秒级，TTL 内摊薄后可接受。
    """
    key = signal_class or "__all__"
    with _lock:
        now = time.monotonic()
        hit = _aggregates_cache.get(key)
        if hit is not None and (now - hit[0]) < _TTL_SECONDS:
            return hit[1]
        aggregates = build_corpus_aggregates(
            _load_actions(), signal_class=signal_class
        )
        _aggregates_cache[key] = (now, aggregates)
        return aggregates


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


def _load_slices(signal_class: Optional[str], dimension: str) -> CorpusRatioSlices:
    """胜率切片（每片过 CRD-2 门）。活算 + TTL，与聚合同一策略。"""
    key = (signal_class or "__all__", dimension)
    with _lock:
        now = time.monotonic()
        hit = _slices_cache.get(key)
        if hit is not None and (now - hit[0]) < _TTL_SECONDS:
            return hit[1]
        slices = build_ratio_slices(
            _load_actions(), signal_class=signal_class, dimension=dimension
        )
        _slices_cache[key] = (now, slices)
        return slices


@router.get("/records/slices")
def get_record_slices(
    signal_class: Optional[str] = Query(
        default="broker_recommendation",
        description="记录口径；R6：不同口径的切片不可并排比较",
    ),
    dimension: str = Query(
        default="market",
        description="切片维度：market（真实市场）或 month（signal clock 归月）",
    ),
) -> dict:
    """当前口径的胜率切片集——每片强制携带 SampleSufficiency。

    前端义务（CRD-2）：count_only 的片不得渲染任何比率；比率必须与
    95% 区间并排。注册先于 ``/{creator_id}/record``（同 aggregates）。
    """
    if dimension not in ("market", "month"):
        raise HTTPException(
            status_code=422,
            detail=f"unknown dimension {dimension!r}; expected market|month",
        )
    slices = _load_slices(signal_class, dimension)
    return {
        "ok": True,
        "data": {"slices": slices.model_dump(mode="json")},
    }


@router.get("/records/aggregates")
def get_record_aggregates(
    signal_class: Optional[str] = Query(
        default="broker_recommendation",
        description="记录口径；R6：不同口径的计数不可相加",
    ),
) -> dict:
    """当前口径的语料构成计数（月度/方向/市场/离场原因/期限档）。

    只有计数，没有比率——图表数据源，不构成评价。注册必须先于
    ``/{creator_id}/record``，避免 creator_id 恰为 "records" 时被参数路由吞掉。
    """
    aggregates = _load_aggregates(signal_class)
    return {
        "ok": True,
        "data": {"aggregates": aggregates.model_dump(mode="json")},
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
