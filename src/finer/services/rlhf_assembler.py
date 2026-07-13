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
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from finer.schemas.trade_action import PipelineSnapshot, TradeAction

logger = logging.getLogger(__name__)


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


def action_to_extraction_dict(action: "TradeAction") -> Dict[str, Any]:
    """Bootstrap an original_extraction dict from the reviewed TradeAction.

    Keeps evidence_text — DPOExporter refuses pairs without it, and the
    corrections normalization path (extraction_to_dict) drops it, which is
    why client-supplied original_extraction alone made every export empty.
    """
    return {
        "ticker": action.target.ticker,
        "direction": action.direction.value,
        "action_chain": [
            {
                "action_type": step.action_type.value,
                "trigger_condition": step.trigger_condition,
                "target_price_low": step.target_price_low,
                "target_price_high": step.target_price_high,
                "sequence": step.sequence,
            }
            for step in action.action_chain
        ],
        "rationale": action.rationale,
        "evidence_text": action.source.evidence_text if action.source else "",
    }


def build_pipeline_snapshot(
    action: "TradeAction",
    source_file: Optional[str] = None,
) -> "PipelineSnapshot":
    """Assemble the pipeline version anchor for one reviewed action.

    Version truth order: the action's own version_info (stamped by the
    canonical composer), then the wrapper's model label read from the F5
    source file, then the current global constants as a last resort for
    unstamped legacy actions.
    """
    from finer.schemas.trade_action import PipelineSnapshot
    from finer.services.versioning import (
        CURRENT_PROMPT_VERSION,
        CURRENT_SCHEMA_VERSION,
    )

    f5_model: Optional[str] = None
    if source_file:
        try:
            wrapper = json.loads(Path(source_file).read_text(encoding="utf-8"))
            if isinstance(wrapper, dict):
                f5_model = wrapper.get("model")
        except Exception as exc:  # snapshot is best-effort, never blocks submit
            logger.warning("Could not read F5 wrapper %s: %s", source_file, exc)

    vi = action.version_info
    return PipelineSnapshot(
        f5_model=f5_model,
        extractor_version=action.model_version,
        prompt_version=vi.prompt_version if vi else CURRENT_PROMPT_VERSION,
        schema_version=vi.schema_version if vi else CURRENT_SCHEMA_VERSION,
        config_hash=vi.extraction_config_hash if vi else None,
        trade_action_source_file=source_file,
        action_snapshot=action_to_extraction_dict(action),
    )


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
