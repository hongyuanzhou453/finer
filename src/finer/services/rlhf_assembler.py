"""F6 RLHF assembler — 把人工审核的 corrections 组装成 DPO Preference.

环 B 关键桥：`corrections + original_extraction → Preference{chosen, rejected, is_original_correct}`。
业务逻辑放 service 层（CLAUDE.md §3：route 不写业务逻辑）；rlhf.py /submit 仅调用本模块。

映射规范见 docs/specs/2026-06-07-f6-rlhf-to-dpo-mapping.md §6。

设计要点：
- rejected = 原始抽取（模型输出）；chosen = 应用 corrections 后的修正抽取。
- 兼容前端 camelCase（actionType/targetPriceLow）与后端 snake_case，统一规整为简化抽取 JSON。
- 无 correction 且未标记异常 → is_original_correct=True（DPOExporter 会跳过，无学习信号）。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pick(d: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def normalize_action_step(step: Dict[str, Any]) -> Dict[str, Any]:
    """单个 action step：camelCase/snake_case → 规整 snake_case，丢空字段。"""
    if not isinstance(step, dict):
        return {}
    out = {
        "action_type": _pick(step, "action_type", "actionType"),
        "instrument_type": _pick(step, "instrument_type", "instrumentType"),
        "trigger_condition": _pick(step, "trigger_condition", "triggerCondition"),
        "target_price_low": _num(_pick(step, "target_price_low", "targetPriceLow")),
        "target_price_high": _num(_pick(step, "target_price_high", "targetPriceHigh")),
        "sequence_order": _pick(step, "sequence_order", "sequenceOrder", "sequence"),
    }
    return {k: v for k, v in out.items() if v is not None}


def extraction_to_dict(ex: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """任意来源的抽取（前端 item / 原始 extraction）→ 规整简化抽取 dict（snake_case）。"""
    ex = ex or {}
    chain = ex.get("action_chain")
    if chain is None:
        chain = ex.get("actionChain")
    chain = chain or []
    result: Dict[str, Any] = {
        "ticker": ex.get("ticker", "") or "",
        "direction": ex.get("direction", "") or "",
        "action_chain": [normalize_action_step(s) for s in chain if isinstance(s, dict)],
    }
    horizon = _pick(ex, "time_horizon", "timeHorizon")
    if horizon is not None:
        result["time_horizon"] = horizon
    if ex.get("rationale"):
        result["rationale"] = ex["rationale"]
    return result


def _has_corrections(corrections: Optional[Dict[str, Any]]) -> bool:
    if not corrections:
        return False
    ac = corrections.get("action_chain")
    if ac is None:
        ac = corrections.get("actionChain")
    return bool(corrections.get("ticker") or corrections.get("direction") or ac)


def apply_corrections(
    original: Dict[str, Any], corrections: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """在规整后的 original 上覆盖 corrections，返回修正后的简化抽取 dict。"""
    corrected = dict(original)
    if not corrections:
        return corrected
    if corrections.get("ticker"):
        corrected["ticker"] = corrections["ticker"]
    if corrections.get("direction"):
        corrected["direction"] = corrections["direction"]
    ac = corrections.get("action_chain")
    if ac is None:
        ac = corrections.get("actionChain")
    if ac is not None:
        corrected["action_chain"] = [normalize_action_step(s) for s in ac if isinstance(s, dict)]
    return corrected


def build_preference(
    original_extraction: Optional[Dict[str, Any]],
    corrections: Optional[Dict[str, Any]] = None,
    flagged_as_error: bool = False,
) -> Dict[str, Any]:
    """corrections + original → Preference dict {chosen, rejected, is_original_correct}.

    chosen=修正抽取 JSON 串；rejected=原始抽取 JSON 串；
    is_original_correct = 无 correction 且未标记异常。
    """
    original = extraction_to_dict(original_extraction)
    corrected = apply_corrections(original, corrections)
    is_correct = (not _has_corrections(corrections)) and (not flagged_as_error)
    return {
        "chosen": json.dumps(corrected, ensure_ascii=False),
        "rejected": json.dumps(original, ensure_ascii=False),
        "is_original_correct": is_correct,
    }
