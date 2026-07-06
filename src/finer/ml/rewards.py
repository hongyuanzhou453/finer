"""finer.ml.rewards — F+ Training 的单一确定性奖励真相源.

本模块把原先散落在 ``scripts/eval_compare.py`` / ``scripts/validate_dpo_hq.py`` /
``scripts/harvest_rejected.py`` 的 verifier 逻辑收敛为一处，供：

  1. HQ 硬门校验（``validate_dpo_hq.py`` 的 grounding 判定）
  2. 未来 k-best 采样的候选打分与偏好对构造（``score_extraction`` / ``pair_preference``）

设计契约见 ``docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md`` §4 与
``docs/specs/2026-06-30-self-evolving-skill-pattern.md`` §7 M2。

红线（不变量，禁止迭代触碰）:
  - verifier 永远做查表 + 确定性裁决，绝不做语义判断。
  - reward 只能看 ``output`` / ``evidence_text``，不得看未来收益、F8 回测或 KOL 事后表现。
  - 枚举以 ``finer.schemas.trade_action`` 为真相源。

可调面（属 ``dpo-rlvr-loop`` Skill，见 skills-registry）:
  - ``DEFAULT_WEIGHTS``（grounding/calibration/abstention 权重）
  - ``CONVICTION_BUCKETS``（信念-证据强度匹配桶）
  - structure 为硬门，不参与加权。

> 收敛进度：本步（M2 第一步）让 ``validate_dpo_hq.py`` 改从此处取 grounding，
> 修正了旧 ``ticker_grounded`` 的后缀归一化 bug（``601899`` vs ``601899.SH``）。
> ``eval_compare.py`` 的原语合并为后续子步。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# 枚举：以 schemas/trade_action.py 为真相源（导不到则 fallback，并标注漂移风险）
# ---------------------------------------------------------------------------
try:
    from finer.schemas.trade_action import ActionType, TradeDirection  # type: ignore

    VALID_DIRECTIONS = {d.value for d in TradeDirection}
    VALID_ACTION_TYPES = {a.value for a in ActionType}
    ENUM_SOURCE = "finer.schemas.trade_action"
except Exception:  # pragma: no cover - 仅在脱离 venv 运行时触发
    VALID_DIRECTIONS = {"bullish", "bearish", "neutral", "watchlist", "risk_warning"}
    VALID_ACTION_TYPES = {
        "long", "short", "close_long", "close_short", "buy_call", "sell_call",
        "buy_put", "sell_put", "hold", "watch", "buy_and_hold",
    }
    ENUM_SOURCE = "fallback(hardcoded) — 未能 import finer.schemas，枚举可能漂移"

# 承诺性（committal）= 做出可交易方向的承诺
COMMITTAL_DIRECTIONS = {"bullish", "bearish"}
COMMITTAL_ACTIONS = {
    "long", "short", "buy_call", "sell_call", "buy_put", "sell_put",
    "close_long", "close_short",
}

# 表示"无标的/未解析"的哨兵 ticker（committal 时出现 = reward 红旗，非真实标的）
ABSTAIN_TICKERS = {"NONE", ""}
SENTINEL_TICKERS = {"UNRESOLVED", "UNSPECIFIED", "UNSP", "未明确", "未指定", "N/A", "NA"}

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# --- 可调面（属 dpo-rlvr-loop Skill；当前为 v1 默认值） ---
DEFAULT_WEIGHTS: Dict[str, float] = {"grounding": 0.50, "calibration": 0.40, "abstention": 0.10}
CONVICTION_BUCKETS: Tuple[float, float, float, float] = (0.8, 0.6, 0.45, 0.3)


# ---------------------------------------------------------------------------
# 解析与结构校验（与 eval_compare 语义一致；此处为 canonical 副本）
# ---------------------------------------------------------------------------
def strip_code_fences(s: str) -> str:
    """去掉 ```json ... ``` 围栏，返回内部内容。"""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def parse_output(raw: Any) -> Optional[Dict[str, Any]]:
    """把原始模型输出串解析为 dict；失败返回 None。已是 dict 则原样返回。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    import json

    try:
        obj = json.loads(strip_code_fences(raw))
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def validate_structure(d: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """轻量 ExtractionOutput 校验（非完整 canonical TradeAction）。"""
    if d is None:
        return False, "无法解析为 JSON 对象"

    ticker = d.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        return False, "ticker 缺失或非空字符串"

    direction = d.get("direction")
    if direction not in VALID_DIRECTIONS:
        return False, f"direction 非法: {direction!r}"

    chain = d.get("action_chain", [])
    if chain is None:
        chain = []
    if not isinstance(chain, list):
        return False, "action_chain 必须是数组"

    for i, step in enumerate(chain):
        if not isinstance(step, dict):
            return False, f"action_chain[{i}] 非对象"
        at = step.get("action_type")
        if at not in VALID_ACTION_TYPES:
            return False, f"action_chain[{i}].action_type 非法: {at!r}"
        lo, hi = step.get("target_price_low"), step.get("target_price_high")
        for name, v in (("target_price_low", lo), ("target_price_high", hi)):
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                return False, f"action_chain[{i}].{name} 非法: {v!r}"
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
            return False, f"action_chain[{i}] 价格区间倒挂: {lo} > {hi}"

    return True, "ok"


# ---------------------------------------------------------------------------
# 承诺性与证据溯源
# ---------------------------------------------------------------------------
def normalize_ticker(t: str) -> str:
    return (t or "").strip().upper().lstrip("$")


def is_committal(d: Dict[str, Any]) -> bool:
    if d.get("direction") in COMMITTAL_DIRECTIONS:
        return True
    for step in d.get("action_chain", []) or []:
        if isinstance(step, dict) and step.get("action_type") in COMMITTAL_ACTIONS:
            return True
    return False


def extract_cited_numbers(d: Dict[str, Any]) -> List[float]:
    """收集输出中引用的价格数字：target_price_low/high + trigger_condition 内数字。"""
    nums: List[float] = []
    for step in d.get("action_chain", []) or []:
        if not isinstance(step, dict):
            continue
        for key in ("target_price_low", "target_price_high"):
            v = step.get(key)
            if isinstance(v, (int, float)):
                nums.append(float(v))
        trig = step.get("trigger_condition")
        if isinstance(trig, str):
            nums.extend(float(m) for m in _NUM_RE.findall(trig))
    return nums


def number_in_text(num: float, text: str) -> bool:
    """数字是否在原文出现（容忍整数/小数两种写法）。"""
    candidates = set()
    if num == int(num):
        candidates.add(str(int(num)))
        candidates.add(f"{int(num)}.0")
    candidates.add(str(num))
    candidates.add(f"{num:.2f}".rstrip("0").rstrip("."))
    return any(c and c in text for c in candidates)


def ticker_in_text(ticker: str, text: str) -> bool:
    """ticker 是否字面出现在原文（含主码部分）。"""
    if not ticker:
        return False
    t = (text or "").upper()
    raw, norm = ticker.strip().upper(), normalize_ticker(ticker)
    if raw and raw in t:
        return True
    if norm and norm in t:
        return True
    base = norm.split(".")[0]
    return bool(base) and len(base) >= 2 and base in t


# ---------------------------------------------------------------------------
# Registry-aware grounding（M2 第一步：修正 loose_ticker 后缀归一化 bug）
# ---------------------------------------------------------------------------
def _split_ticker(ticker: str) -> Tuple[str, str]:
    """拆为 (基码, 市场后缀)。基码：大写、去 ``$``、纯数字去前导零；后缀如 SH/SZ/HK。"""
    t = (ticker or "").strip().upper().lstrip("$")
    if not t:
        return "", ""
    if "." in t:
        head, _, suf = t.partition(".")
        head, suf = head.strip(), suf.strip()
    else:
        head, suf = t, ""
    if head.isdigit():
        head = head.lstrip("0") or "0"
    return head, suf


def ticker_base(ticker: str) -> str:
    """ticker 的基码（去后缀、纯数字去前导零），用于分组/展示。"""
    return _split_ticker(ticker)[0]


def tickers_match(a: str, b: str) -> bool:
    """两个 ticker 是否同一标的（市场感知）。

    - 基码必须一致（``601899`` == ``601899.SH``，裸码与带后缀同源）。
    - 若两侧都带市场后缀且不同 → 不同标的（避免 ``000001.SH``上证 / ``000001.SZ``平安 /
      ``00001.HK``长和 因去零后基码同为 ``1`` 而跨市场误配）。
    旧 ``validate_dpo_hq.loose_ticker`` 用严格相等（保留后缀），导致 ``601899`` != ``601899.SH``
    名↔码反查失效——本函数即修正点，同时不引入跨市场碰撞。
    """
    ha, sa = _split_ticker(a)
    hb, sb = _split_ticker(b)
    if not ha or ha != hb:
        return False
    if sa and sb and sa != sb:
        return False
    return True


_REGISTRY_CACHE: Optional[Dict[str, Any]] = None


def _default_registry() -> Dict[str, Any]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        try:
            from finer.entity_registry import ENTITY_REGISTRY

            _REGISTRY_CACHE = ENTITY_REGISTRY
        except Exception:
            _REGISTRY_CACHE = {}
    return _REGISTRY_CACHE


def ticker_grounded(
    ticker: str,
    evidence: str,
    registry: Optional[Dict[str, Any]] = None,
) -> bool:
    """chosen.ticker 是否被证据支持。

    判定顺序（任一命中即 grounded）：
      1. ticker 字面（或主码）出现在证据中（``ticker_in_text``）。
      2. registry 名↔码：证据中出现某公司别名，且该别名的 registry ticker 基码
         与 chosen ticker 基码一致（``ticker_base`` 后缀容忍比对）。

    ``NONE`` / 空 ticker 视为豁免（非承诺性，不计入 grounding 分母）。
    ``UNSPECIFIED`` / ``未明确`` 等哨兵不会被 registry 命中，故 committal 时仍判未 grounded。
    """
    if not ticker or ticker.strip().upper() == "NONE":
        return True
    ev = evidence or ""
    if ticker_in_text(ticker, ev):
        return True
    if not ticker_base(ticker):
        return False
    reg = _default_registry() if registry is None else registry
    for alias, entry in reg.items():
        if not alias or alias not in ev:
            continue
        try:
            entry_ticker = entry[0] if isinstance(entry, (list, tuple)) else entry
        except Exception:
            continue
        if tickers_match(ticker, str(entry_ticker)):
            return True
    return False


# ---------------------------------------------------------------------------
# Reward 聚合（k-best 采样 / 偏好对构造的单一打分入口）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RewardBreakdown:
    """一次抽取的奖励拆解。``total`` 归一到 [0,1]。

    structure 为硬门：解析/结构失败 → ``total=0`` 且失去 chosen 资格；structure 字段
    仅作诊断（解析失败时 grounding/calibration 无法计算）。
    """

    total: float
    structure: float
    grounding: float
    calibration: float
    abstention: float
    committal: bool
    penalties: Dict[str, float] = field(default_factory=dict)
    flags: Dict[str, bool] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _grounding_score(d: Dict[str, Any], evidence: str) -> Tuple[float, Dict[str, bool], List[str]]:
    """committal 输出的证据挂靠分。ticker 与引用价格须可溯，幻觉重罚。"""
    flags: Dict[str, bool] = {}
    reasons: List[str] = []
    ticker = str(d.get("ticker", ""))
    grounded = ticker_grounded(ticker, evidence)
    flags["ticker_grounded"] = grounded
    if not grounded:
        reasons.append(f"ticker not grounded: {ticker!r}")
    # 引用价格挂靠
    prices = extract_cited_numbers(d)
    if prices:
        missing = [n for n in prices if not number_in_text(n, evidence)]
        price_ok = not missing
        flags["prices_grounded"] = price_ok
        if missing:
            reasons.append(f"prices not in evidence: {missing}")
    else:
        price_ok = True  # 无引用价格不扣分
    # ticker 是必要条件；价格作次要权重
    score = (0.7 if grounded else 0.0) + (0.3 if price_ok else 0.0)
    return _clamp01(score), flags, reasons


def _calibration_score(d: Dict[str, Any], grounding: float, committal: bool) -> Tuple[float, List[str]]:
    """信念与证据强度匹配：惩罚"证据弱却高 conviction"的过度自信。"""
    reasons: List[str] = []
    conv = d.get("conviction")
    if not isinstance(conv, (int, float)):
        return 0.0, ["conviction 非数值"]
    conv = float(conv)
    # 证据支撑的 conviction 上限（桶）
    if not committal:
        ceiling = CONVICTION_BUCKETS[3]          # 0.3 abstention 形态
    elif grounding >= 0.99:
        ceiling = CONVICTION_BUCKETS[0]          # 0.8 标的+价格全溯
    elif grounding >= 0.7:
        ceiling = CONVICTION_BUCKETS[1]          # 0.6 标的可溯、价格缺
    else:
        ceiling = CONVICTION_BUCKETS[2]          # 0.45 标的都不可溯
    if conv <= ceiling + 1e-9:
        return 1.0, reasons
    over = conv - ceiling
    reasons.append(f"overconfident: conviction {conv} > 证据上限 {ceiling}")
    return _clamp01(1.0 - over), reasons


def _penalties(d: Dict[str, Any], committal: bool) -> Dict[str, float]:
    pen: Dict[str, float] = {}
    ticker = str(d.get("ticker", "")).strip().upper()
    if committal and ticker in SENTINEL_TICKERS:
        pen["sentinel_ticker_committal"] = 0.5  # committal 却给哨兵 ticker
    rationale = d.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        pen["empty_rationale"] = 0.2
    return pen


def score_extraction(
    output: Any,
    evidence_text: str,
    weights: Optional[Dict[str, float]] = None,
) -> RewardBreakdown:
    """对单条抽取相对证据打分。structure 为硬门；其余维度按可适用性归一到 [0,1]。"""
    w = weights or DEFAULT_WEIGHTS
    d = parse_output(output)
    ok, reason = validate_structure(d)
    if not ok or d is None:
        return RewardBreakdown(
            total=0.0, structure=0.0, grounding=0.0, calibration=0.0, abstention=0.0,
            committal=False, penalties={}, flags={"structure_ok": False},
            reasons=[f"structure gate failed: {reason}"],
        )

    committal = is_committal(d)
    grounding, g_flags, g_reasons = _grounding_score(d, evidence_text or "")
    calibration, c_reasons = _calibration_score(d, grounding, committal)
    abstention = 0.0 if committal else 1.0
    penalties = _penalties(d, committal)

    # 可适用维度按权重归一：committal → grounding+calibration；abstention 形态 → calibration+abstention
    if committal:
        applicable = w["grounding"] + w["calibration"]
        base = (w["grounding"] * grounding + w["calibration"] * calibration) / applicable
    else:
        applicable = w["calibration"] + w["abstention"]
        base = (w["calibration"] * calibration + w["abstention"] * abstention) / applicable

    total = _clamp01(base - sum(penalties.values()))
    flags = {"structure_ok": True, **g_flags}
    return RewardBreakdown(
        total=total, structure=1.0, grounding=grounding, calibration=calibration,
        abstention=abstention, committal=committal, penalties=penalties, flags=flags,
        reasons=[*g_reasons, *c_reasons],
    )


@dataclass(frozen=True)
class ScoredCandidate:
    candidate_id: str
    output_raw: Any
    reward: RewardBreakdown


@dataclass(frozen=True)
class PreferenceDecision:
    status: Literal["pair", "near_tie", "all_failed"]
    chosen: Optional[ScoredCandidate]
    rejected: Optional[ScoredCandidate]
    margin: Optional[float]
    reasons: List[str] = field(default_factory=list)


def pair_preference(
    candidates: List[ScoredCandidate],
    *,
    min_chosen_score: float,
    min_margin: float,
) -> PreferenceDecision:
    """从 k-best 候选里挑 chosen/rejected 构造 DPO draft。

    - 最高分 < ``min_chosen_score`` → ``all_failed``（无人达标，不构对）。
    - 最高与最低分差 < ``min_margin`` → ``near_tie``（区分度不足，留待人工）。
    - 否则 ``pair``：chosen=最高、rejected=最低。
    """
    valid = [c for c in candidates if c is not None]
    if not valid:
        return PreferenceDecision("all_failed", None, None, None, ["无候选"])
    ranked = sorted(valid, key=lambda c: c.reward.total, reverse=True)
    best, worst = ranked[0], ranked[-1]
    if best.reward.total < min_chosen_score:
        return PreferenceDecision(
            "all_failed", None, None, None,
            [f"最高分 {best.reward.total:.3f} < min_chosen_score {min_chosen_score}"],
        )
    margin = best.reward.total - worst.reward.total
    if margin < min_margin:
        return PreferenceDecision(
            "near_tie", None, None, margin,
            [f"margin {margin:.3f} < min_margin {min_margin}"],
        )
    return PreferenceDecision("pair", best, worst, margin, [])
