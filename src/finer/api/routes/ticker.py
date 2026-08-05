"""个股共识只读 API（CRD-3 的消费入口，UI-3 /ticker 页的数据源）。

route 只做参数解析与响应格式化；聚合逻辑在 ``credibility/consensus.py``。

性能形态：每次请求扫 5,800+ 个 F3 intent 文件不可行，因此进程内维持一份
带 TTL 的 intent 缓存（60s，模式同 kol_registry / audit_assembler）。这是
PROJ-1 投影表落地前的过渡——接口契约按投影消费方设计，届时只换数据源。
"""

from __future__ import annotations

import glob
import json
import threading
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter

from finer.credibility.consensus import (
    _canonical,
    build_ticker_consensus,
    with_staleness,
)
from finer.projections.materializer import read_consensus
from finer.errors.exceptions import FinerError
from finer.paths import DATA_ROOT
from finer.schemas.credibility import TickerConsensusView

router = APIRouter()

_TTL_SECONDS = 60.0
_lock = threading.Lock()
_cache: Optional[List[dict]] = None
_built_at: float = 0.0


def _load_intents(data_root: Path) -> List[dict]:
    global _cache, _built_at
    with _lock:
        now = time.monotonic()
        if _cache is not None and (now - _built_at) < _TTL_SECONDS:
            return _cache
        intents: List[dict] = []
        for path in glob.glob(str(data_root / "F3_intents" / "bri_*.json")):
            try:
                intents.append(json.loads(Path(path).read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue  # 单个坏文件不挡整个视图
        _cache, _built_at = intents, now
        return intents


@router.get("/{symbol}/consensus")
def get_ticker_consensus(symbol: str) -> dict:
    """这只票，谁说过什么 —— 等权共识记录（非预测，见 view.notes）。"""
    # 投影优先（PROJ-1）；库缺失/未覆盖时回退活算，开发环境不依赖物化
    view: Optional[TickerConsensusView] = None
    canonical = _canonical(symbol)
    if canonical is not None:
        view = read_consensus(DATA_ROOT, canonical)
    if view is None:
        view = build_ticker_consensus(_load_intents(DATA_ROOT), symbol)
    if view is not None:
        # 读取时算陈旧度：距今天数每天在变，物化固化第二天就是错的。
        view = with_staleness(view)
    if view is None:
        raise FinerError(
            "API_NTF_001",
            f"标的 {symbol!r} 无法归一化或没有任何已入库的立场记录",
            stage="F3",
            operation="ticker_consensus",
            retryable=False,
            fix_hint="确认代码写法（如 0700.HK / NVDA / AZN.L）；"
                     "或该标的确实未被任何已接入信源覆盖",
        )
    return {"ok": True, "data": view.model_dump(mode="json")}
