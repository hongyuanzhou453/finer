#!/usr/bin/env python3
"""eval_compare.py — DPO 微调前/后三指标对比评测器.

服务于 docs/specs/2026-06-07-dpo-bailian-training-line.md 的"证据对齐的克制"原则。
计算三项指标，对齐 before.jsonl / after.jsonl 输出"前/后"对比：

  1. 结构合规率 structure_compliance_rate  —— 确定性、免费
  2. 证据挂靠率 evidence_attachment_rate    —— 确定性、免费、直测"不编造"
  3. 偏好胜率   preference_win_rate          —— 需 judge（ref-match 免费 / llm 需 API）

红线：本脚本只算指标，不产模型。`--demo` 用玩具数据自检，输出明确标注"非真实成绩"。

用法:
    # 自检（零外部文件、零依赖、零费用，证明指标能算）
    python scripts/eval_compare.py --demo

    # 真实对比（百炼实跑回填 after.jsonl 后）
    python scripts/eval_compare.py \
        --eval-set data/dpo/eval/eval_set.jsonl \
        --before   data/dpo/eval/before.jsonl \
        --after    data/dpo/eval/after.jsonl \
        --judge ref --out report.json

数据契约见 spec 第 6 节。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 枚举：以 schemas/trade_action.py 为真相源（导不到则 fallback，并告警）
# ---------------------------------------------------------------------------
try:
    from finer.schemas.trade_action import TradeDirection, ActionType  # type: ignore

    VALID_DIRECTIONS = {d.value for d in TradeDirection}
    VALID_ACTION_TYPES = {a.value for a in ActionType}
    _ENUM_SOURCE = "finer.schemas.trade_action"
except Exception:  # pragma: no cover - 仅在脱离 venv 运行时触发
    VALID_DIRECTIONS = {"bullish", "bearish", "neutral", "watchlist", "risk_warning"}
    VALID_ACTION_TYPES = {
        "long", "short", "close_long", "close_short", "buy_call", "sell_call",
        "buy_put", "sell_put", "hold", "watch", "buy_and_hold",
    }
    _ENUM_SOURCE = "fallback(hardcoded) — 未能 import finer.schemas，枚举可能漂移"

# 承诺性（committal）= 做出可交易方向的承诺
COMMITTAL_DIRECTIONS = {"bullish", "bearish"}
COMMITTAL_ACTIONS = {
    "long", "short", "buy_call", "sell_call", "buy_put", "sell_put",
    "close_long", "close_short",
}

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


# ---------------------------------------------------------------------------
# 解析与校验
# ---------------------------------------------------------------------------
def strip_code_fences(s: str) -> str:
    """去掉 ```json ... ``` 围栏，返回内部内容。"""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def parse_output(raw: str) -> Optional[Dict[str, Any]]:
    """把原始模型输出串解析为 dict；失败返回 None。"""
    if not isinstance(raw, str):
        return None
    try:
        obj = json.loads(strip_code_fences(raw))
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def validate_structure(d: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """轻量 ExtractionOutput 校验（非完整 canonical TradeAction）。

    要求：ticker 非空 str；direction ∈ VALID_DIRECTIONS；
    action_chain 每步 action_type ∈ VALID_ACTION_TYPES；价格 ≥0 且 low ≤ high。
    """
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
    return t.strip().upper().lstrip("$")


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
    """数字是否在原文出现（容忍整数/小数两种写法；格式化差异见 spec Open Issues）。"""
    candidates = set()
    if num == int(num):
        candidates.add(str(int(num)))
        candidates.add(f"{int(num)}.0")
    candidates.add(str(num))
    candidates.add(f"{num:.2f}".rstrip("0").rstrip("."))
    return any(c and c in text for c in candidates)


def ticker_in_text(ticker: str, text: str) -> bool:
    if not ticker:
        return False
    t = text.upper()
    raw, norm = ticker.strip().upper(), normalize_ticker(ticker)
    if raw and raw in t:
        return True
    if norm and norm in t:
        return True
    # 形如 0700.HK 的，主码部分也算（0700）
    base = norm.split(".")[0]
    return bool(base) and len(base) >= 2 and base in t


def assess_evidence(d: Dict[str, Any], evidence_text: str) -> Dict[str, bool]:
    """返回 {committal, grounded, hallucinated}。非承诺性输出不计入挂靠率分母。"""
    committal = is_committal(d)
    if not committal:
        return {"committal": False, "grounded": False, "hallucinated": False}

    ticker_ok = ticker_in_text(str(d.get("ticker", "")), evidence_text)
    nums = extract_cited_numbers(d)
    nums_ok = all(number_in_text(n, evidence_text) for n in nums)
    grounded = ticker_ok and nums_ok
    return {"committal": True, "grounded": grounded, "hallucinated": not grounded}


# ---------------------------------------------------------------------------
# 偏好 judge
# ---------------------------------------------------------------------------
def ref_score(d: Optional[Dict[str, Any]], gold: Dict[str, Any]) -> int:
    """ref-match：与 gold 的字段一致性（direction / ticker / 承诺一致）。范围 0-3。

    注意：ref-match 只看与 gold 的字段匹配，看不到证据是否真实溯源——
    它可能在 before 编造价位但方向/标的恰好对时给高分。这正是为何
    证据挂靠率与偏好胜率要并列看（见 spec §5.3 注意事项）。
    """
    if d is None:
        return 0
    score = 0
    if d.get("direction") == gold.get("direction"):
        score += 1
    if normalize_ticker(str(d.get("ticker", ""))) == normalize_ticker(str(gold.get("ticker", ""))):
        score += 1
    try:
        if is_committal(d) == is_committal(gold):
            score += 1
    except Exception:
        pass
    return score


def ref_score_multi(d: Optional[Dict[str, Any]], item: Dict[str, Any]) -> int:
    """多标的样本 match-any：对 [gold, *alt_golds] 取最高 ref_score。

    一段多标的文本，模型抽出任何一个正确意图都应得分（抽取合同是单对象，
    模型对同一输入只输出一个抽取）。
    """
    golds = [item.get("gold")] + [
        g for g in (item.get("alt_golds") or []) if isinstance(g, dict)
    ]
    golds = [g for g in golds if isinstance(g, dict)]
    if not golds:
        return 0
    return max(ref_score(d, g) for g in golds)


def _llm_call(messages: List[Dict[str, str]]) -> str:  # pragma: no cover
    """LLM judge 的唯一传输接缝。闸②（harvest 阶段）接入 services/llm 后实现。

    现在故意抛错而非静默伪造，守住"不编造"红线。
    """
    raise NotImplementedError(
        "LLM judge 传输层未接线。到闸②（harvest）接入 finer.services.llm 后，"
        "在此实现 _llm_call 即可启用 --judge llm。pairwise 编排逻辑已就绪。"
    )


def llm_pairwise_judge(prompt: str, evidence: str, before_out: str, after_out: str) -> str:
    """LLM pairwise：A/B 位置互换跑两遍，仅一致胜才算。返回 'after'|'before'|'tie'。

    rubric = 证据对齐的克制（spec §3）。传输层 _llm_call 待闸②接入。
    """
    rubric = (
        "你是投研抽取质检员。评判标准（证据对齐的克制）：证据充分时给对方向且引用"
        "原文可溯证据；证据不足时应弃权(hold/watchlist)而非硬给方向，不得编造原文没有"
        "的标的或价位。只输出 A 或 B，代表哪个更符合标准。"
    )

    def ask(first: str, second: str) -> str:
        msgs = [
            {"role": "system", "content": rubric},
            {"role": "user", "content": (
                f"原文:\n{evidence}\n\n任务:\n{prompt}\n\n"
                f"候选A:\n{first}\n\n候选B:\n{second}\n\n哪个更符合标准？只回 A 或 B。"
            )},
        ]
        return _llm_call(msgs).strip().upper()[:1]

    r1 = ask(after_out, before_out)   # A=after
    r2 = ask(before_out, after_out)   # A=before
    after_wins = (r1 == "A") + (r2 == "B")
    before_wins = (r1 == "B") + (r2 == "A")
    if after_wins == 2:
        return "after"
    if before_wins == 2:
        return "before"
    return "tie"


# ---------------------------------------------------------------------------
# 指标聚合
# ---------------------------------------------------------------------------
def compute_side(outputs: Dict[str, str], eval_items: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """对单侧（before 或 after）算结构合规率 + 证据挂靠率。"""
    total = 0
    compliant = 0
    committal = 0
    grounded = 0
    for eid, item in eval_items.items():
        raw = outputs.get(eid)
        if raw is None:
            continue
        total += 1
        d = parse_output(raw)
        ok, _ = validate_structure(d)
        if ok:
            compliant += 1
        if d is not None and ok:
            ev = assess_evidence(d, item.get("evidence_text", ""))
            if ev["committal"]:
                committal += 1
                if ev["grounded"]:
                    grounded += 1
    return {
        "total": total,
        "compliant": compliant,
        "structure_compliance_rate": _safe_div(compliant, total),
        "committal": committal,
        "grounded": grounded,
        "evidence_attachment_rate": _safe_div(grounded, committal),
        "hallucination_rate": _safe_div(committal - grounded, committal),
    }


def compute_preference(
    before: Dict[str, str],
    after: Dict[str, str],
    eval_items: Dict[str, Dict[str, Any]],
    judge: str,
) -> Dict[str, Any]:
    wins = ties = losses = considered = 0
    for eid, item in eval_items.items():
        b_raw, a_raw = before.get(eid), after.get(eid)
        if b_raw is None or a_raw is None:
            continue
        if judge == "ref":
            gold = item.get("gold")
            if not isinstance(gold, dict):
                continue  # ref-match 需要 gold
            considered += 1
            bs = ref_score_multi(parse_output(b_raw), item)
            as_ = ref_score_multi(parse_output(a_raw), item)
            if as_ > bs:
                wins += 1
            elif as_ < bs:
                losses += 1
            else:
                ties += 1
        elif judge == "llm":
            considered += 1
            verdict = llm_pairwise_judge(
                item.get("prompt", ""), item.get("evidence_text", ""), b_raw, a_raw
            )
            wins += verdict == "after"
            losses += verdict == "before"
            ties += verdict == "tie"
        else:
            return {"judge": judge, "win_rate": None, "note": "judge=none，跳过偏好胜率"}
    win_rate = _safe_div(wins + 0.5 * ties, considered)
    return {
        "judge": judge, "considered": considered,
        "wins": wins, "ties": ties, "losses": losses, "win_rate": win_rate,
    }


def _safe_div(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [warn] {path.name}:{i} 跳过非法行: {e}", file=sys.stderr)
    return rows


def index_outputs(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    return {r["id"]: r.get("output", "") for r in rows if "id" in r}


def index_eval(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {r["id"]: r for r in rows if "id" in r}


# ---------------------------------------------------------------------------
# Demo（自检）数据：玩具、说明性，绝非真实成绩
# ---------------------------------------------------------------------------
def demo_data() -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """5 条覆盖：证据足/不足、结构破格、错失方向、应弃权。

    before = 过度承诺 / 编造 / 破格；after = 证据对齐的克制版。
    """
    def j(**kw) -> str:
        return json.dumps(kw, ensure_ascii=False)

    eval_set = [
        {"id": "ev1", "prompt": "提取 TradeAction", "expected_abstain": False,
         "evidence_text": "苹果 AAPL 在 150 美元附近形成强支撑，若回踩 148-152 区间可逢低建仓，看好反弹。",
         "gold": {"ticker": "AAPL", "direction": "bullish",
                  "action_chain": [{"action_type": "long", "target_price_low": 148, "target_price_high": 152}]}},
        {"id": "ev2", "prompt": "提取 TradeAction", "expected_abstain": True,
         "evidence_text": "今天大盘震荡，市场情绪偏谨慎，没什么特别明确的机会，注意风险。",
         "gold": {"ticker": "NONE", "direction": "watchlist", "action_chain": [{"action_type": "watch"}]}},
        {"id": "ev3", "prompt": "提取 TradeAction", "expected_abstain": False,
         "evidence_text": "腾讯 0700.HK 跌破关键支撑 380，短线偏弱，可考虑减仓离场。",
         "gold": {"ticker": "0700.HK", "direction": "bearish",
                  "action_chain": [{"action_type": "close_long", "trigger_condition": "price < 380"}]}},
        {"id": "ev4", "prompt": "提取 TradeAction", "expected_abstain": False,
         "evidence_text": "英伟达 NVDA 若有效跌破 800，趋势转弱，建议离场观望。",
         "gold": {"ticker": "NVDA", "direction": "bearish",
                  "action_chain": [{"action_type": "short", "trigger_condition": "price < 800"}]}},
        {"id": "ev5", "prompt": "提取 TradeAction", "expected_abstain": True,
         "evidence_text": "周末没什么消息，下周再看吧。",
         "gold": {"ticker": "NONE", "direction": "watchlist", "action_chain": [{"action_type": "watch"}]}},
    ]
    # before：过度承诺/编造/破格
    before = [
        {"id": "ev1", "output": j(ticker="AAPL", direction="bullish",
                                  action_chain=[{"action_type": "long", "target_price_low": 200, "target_price_high": 210}])},
        {"id": "ev2", "output": j(ticker="TSLA", direction="bullish",
                                  action_chain=[{"action_type": "long", "target_price_low": 250, "target_price_high": 260}])},
        {"id": "ev3", "output": '{"ticker": "0700.HK", "direction": "bearish", '},  # 截断 → 破格
        {"id": "ev4", "output": j(ticker="NVDA", direction="neutral", action_chain=[{"action_type": "hold"}])},
        {"id": "ev5", "output": j(ticker="BABA", direction="bullish",
                                  action_chain=[{"action_type": "buy_call", "target_price_low": 90, "target_price_high": 95}])},
    ]
    # after：证据对齐的克制
    after = [
        {"id": "ev1", "output": j(ticker="AAPL", direction="bullish",
                                  action_chain=[{"action_type": "long", "target_price_low": 148, "target_price_high": 152}],
                                  rationale="原文 148-152 支撑区间")},
        {"id": "ev2", "output": j(ticker="NONE", direction="watchlist",
                                  action_chain=[{"action_type": "watch"}], rationale="证据不足，观望")},
        {"id": "ev3", "output": j(ticker="0700.HK", direction="bearish",
                                  action_chain=[{"action_type": "close_long", "trigger_condition": "price < 380"}])},
        {"id": "ev4", "output": j(ticker="NVDA", direction="bearish",
                                  action_chain=[{"action_type": "short", "trigger_condition": "price < 800"}])},
        {"id": "ev5", "output": j(ticker="NONE", direction="watchlist",
                                  action_chain=[{"action_type": "watch"}], rationale="无消息，观望")},
    ]
    return eval_set, before, after


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def _fmt(v: Optional[float]) -> str:
    return "  n/a" if v is None else f"{v:5.2f}"


def _delta(a: Optional[float], b: Optional[float]) -> str:
    if a is None or b is None:
        return "   —"
    d = b - a
    sign = "+" if d >= 0 else "-"
    return f"{sign}{abs(d):4.2f}"


def render_report(before_m: Dict, after_m: Dict, pref: Dict, *, demo: bool) -> str:
    lines = []
    if demo:
        lines += [
            "╔══════════════════════════════════════════════════════════════╗",
            "║  ⚠ DEMO — 玩具数据，说明性，非真实模型对比，不可当成绩引用  ║",
            "╚══════════════════════════════════════════════════════════════╝",
        ]
    lines += [
        f"枚举真相源: {_ENUM_SOURCE}",
        f"样本数: before={before_m['total']}  after={after_m['total']}",
        "",
        f"{'指标':<26}{'before':>9}{'after':>9}{'Δ':>8}",
        "─" * 52,
        f"{'结构合规率':<24}{_fmt(before_m['structure_compliance_rate']):>9}"
        f"{_fmt(after_m['structure_compliance_rate']):>9}"
        f"{_delta(before_m['structure_compliance_rate'], after_m['structure_compliance_rate']):>8}",
        f"{'证据挂靠率(承诺性输出)':<18}{_fmt(before_m['evidence_attachment_rate']):>9}"
        f"{_fmt(after_m['evidence_attachment_rate']):>9}"
        f"{_delta(before_m['evidence_attachment_rate'], after_m['evidence_attachment_rate']):>8}",
        f"{'  └ 编造率(越低越好)':<19}{_fmt(before_m['hallucination_rate']):>9}"
        f"{_fmt(after_m['hallucination_rate']):>9}"
        f"{_delta(before_m['hallucination_rate'], after_m['hallucination_rate']):>8}",
    ]
    if pref.get("win_rate") is not None:
        lines.append("─" * 52)
        lines.append(
            f"偏好胜率 after≻before  = {pref['win_rate']:.2f}  "
            f"[judge={pref['judge']}  W/T/L={pref['wins']}/{pref['ties']}/{pref['losses']}  "
            f"n={pref['considered']}]"
        )
    else:
        lines.append("─" * 52)
        lines.append(f"偏好胜率: {pref.get('note', 'n/a')}")
    lines.append("")
    lines.append("提示: 证据挂靠率/编造率是确定性指标(测真东西)；偏好胜率须用训练未见的独立评测集，否则虚高。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="DPO 微调前/后三指标对比评测器",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--demo", action="store_true", help="用内置玩具数据自检（零外部文件）")
    ap.add_argument("--eval-set", type=str, help="eval_set.jsonl 路径")
    ap.add_argument("--before", type=str, help="before.jsonl（基座模型输出）")
    ap.add_argument("--after", type=str, help="after.jsonl（微调后输出）")
    ap.add_argument("--judge", choices=["none", "ref", "llm"], default="ref",
                    help="偏好胜率 judge：ref=与gold字段匹配(免费) / llm=pairwise(需API,闸②) / none=跳过")
    ap.add_argument("--out", type=str, help="将 JSON 报告写到此路径")
    args = ap.parse_args()

    if args.demo:
        eval_rows, before_rows, after_rows = demo_data()
    else:
        if not (args.eval_set and args.before and args.after):
            ap.error("非 --demo 模式必须提供 --eval-set / --before / --after")
        eval_rows = load_jsonl(Path(args.eval_set))
        before_rows = load_jsonl(Path(args.before))
        after_rows = load_jsonl(Path(args.after))

    eval_items = index_eval(eval_rows)
    before = index_outputs(before_rows)
    after = index_outputs(after_rows)

    if not eval_items:
        print("[error] 评测集为空", file=sys.stderr)
        return 1

    missing = [eid for eid in eval_items if eid not in before or eid not in after]
    if missing:
        print(f"  [warn] {len(missing)} 个 id 在 before/after 中缺失，将跳过: {missing[:5]}...",
              file=sys.stderr)

    before_m = compute_side(before, eval_items)
    after_m = compute_side(after, eval_items)
    pref = compute_preference(before, after, eval_items, args.judge)

    print(render_report(before_m, after_m, pref, demo=args.demo))

    if args.out:
        report = {
            "demo": args.demo,
            "enum_source": _ENUM_SOURCE,
            "before": before_m,
            "after": after_m,
            "preference": pref,
        }
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告已写入 {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
