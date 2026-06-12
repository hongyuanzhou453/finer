#!/usr/bin/env python3
"""harvest_rejected.py — 半真实 DPO 数据的核心步：跑基座模型拿真实失败做 rejected，规则校准出 chosen.

半真实方案（spec §4）：
  - evidence_text = 真实 KOL 段落（来自 select_passages.py）
  - rejected      = 基座 Qwen 的真实输出（过度承诺 / 编造价位），on-policy 负样本
  - chosen        = 对 rejected 做"证据对齐的克制"校准（去编造价位 / 证据不足则降级观望 / 内联证据）

校准是**确定性规则**（不再引入 agent 自由发挥），进一步压低 circularity；chosen 与 rejected
相同的对会被丢弃（基座答对了就没有学习信号）。

闸②（烧钱）：真实跑需 DASHSCOPE_API_KEY 调 qwen3-8b。脚本写出/校准/打包都不需要 key；
只有 `--model` 真实调用那步需要。无 key 时用 `--mock` 验证完整流程。

用法:
    # 无 key 验证全流程（mock 基座输出）
    python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl --out data/dpo/pairs.jsonl --mock

    # 真实跑（你的环境有 DASHSCOPE_API_KEY；on-policy 用 qwen3-8b）
    export DASHSCOPE_API_KEY=...   # 不要写进代码/日志
    python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl --out data/dpo/pairs.jsonl --model qwen3-8b

下游: python scripts/to_bailian.py --in data/dpo/pairs.jsonl --out data/dpo/data.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 复用 eval_compare 的溯源/承诺判定 helper（单一实现，避免漂移）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_compare import (  # noqa: E402
    ticker_in_text, number_in_text, is_committal, extract_cited_numbers,
    normalize_ticker, parse_output, validate_structure,
)

# 抽取 prompt / system 以 dpo_trainer 为真相源
try:
    from finer.ml.dpo_trainer import format_dpo_prompt, TRADE_ACTION_SYSTEM_PROMPT  # type: ignore
    _PROMPT_SOURCE = "finer.ml.dpo_trainer"
except Exception:  # pragma: no cover
    TRADE_ACTION_SYSTEM_PROMPT = "你是金融分析师助手，证据不足应观望，勿编造标的/价位，严格输出 JSON。"
    def format_dpo_prompt(evidence_text: str, include_schema: bool = False) -> str:  # type: ignore
        return f"从以下文本提取 TradeAction（证据不足应观望，勿编造）：\n{evidence_text}"
    _PROMPT_SOURCE = "fallback(hardcoded)"

# 实体注册表：中文名↔ticker（腾讯音乐→TME、阿特斯→CSIQ…），用于修字面匹配 bug
try:
    from finer.entity_registry import ENTITY_REGISTRY  # type: ignore
except Exception:  # pragma: no cover
    ENTITY_REGISTRY = {}

WATCHLIST_CHOSEN = {
    "ticker": "NONE", "direction": "watchlist", "conviction": 0.2,
    "action_chain": [{"action_type": "watch"}],
    "time_horizon": None,
    "rationale": "证据不足，观望（原文未提供可溯的标的/价位支撑）",
}

# validate_dpo_hq.REQUIRED_CHOSEN_KEYS 的镜像：HQ cleaned chosen 顶层 key 必须恰好是这 6 个
CHOSEN_KEYS = ("ticker", "direction", "conviction", "action_chain", "time_horizon", "rationale")

# committal 但标的不可溯时的 ticker 哨兵：区别于 NONE（"无标的观望"）。
# 表"有方向但标的待人工锚定"——不透传基座幻觉 ticker（如把泡泡玛特填成 002857.SZ）。
# 选 UNRESOLVED 而非 NONE：validate_dpo_hq.ticker_grounded 对 NONE 豁免检查（会让 committal
# 静默放行），对 UNRESOLVED 仍 flag，正确提示人工补标的。基座原始猜测另存 meta.ticker_guess。
UNRESOLVED_TICKER = "UNRESOLVED"


def normalize_chosen(obj: Dict[str, Any]) -> Dict[str, Any]:
    """chosen 收敛为 HQ 校验的 6 个顶层 key：多删（模型附带字段）、少补（time_horizon 缺省 None）。"""
    out = {k: obj.get(k) for k in CHOSEN_KEYS}
    if not isinstance(out["action_chain"], list):
        out["action_chain"] = []
    return out


def _norm_ticker_loose(t: str) -> str:
    """松规整：去 $、大写、主码去前导零，使 00700.HK ≡ 0700.HK。"""
    t = (t or "").strip().upper().lstrip("$")
    if "." in t:
        head, _, tail = t.partition(".")
        return head.lstrip("0") + "." + tail
    return t


def ticker_grounded(ticker: str, evidence_text: str) -> bool:
    """标的是否在原文可溯：① 字面子串(ticker_in_text) ② entity_registry 中文别名映射到同一 ticker。"""
    if ticker_in_text(ticker, evidence_text):
        return True
    tnorm = _norm_ticker_loose(ticker)
    if not tnorm or tnorm == "NONE":
        return False
    for alias, entry in ENTITY_REGISTRY.items():
        if alias and alias in evidence_text and _norm_ticker_loose(entry[0]) == tnorm:
            return True
    return False


# ---------------------------------------------------------------------------
# 基座模型调用（真实=DashScope qwen3-8b / mock=确定性过度承诺）
# ---------------------------------------------------------------------------
def _mock_overcommit(evidence_text: str) -> str:
    """确定性 mock：模拟基座"过度承诺 + 编造价位"，用于无 key 验证校准全流程。"""
    h = int(hashlib.sha1(evidence_text.encode("utf-8")).hexdigest(), 16)
    # 编造一个原文大概率没有的价位，触发去编造/降级分支
    fake_low = 100 + h % 400
    tickers = ["AAPL", "TSLA", "NVDA", "BABA", "0700.HK"]
    tk = tickers[h % len(tickers)]
    direction = "bullish" if h % 2 == 0 else "bearish"
    action = "long" if direction == "bullish" else "short"
    return json.dumps({
        "ticker": tk, "direction": direction,
        "action_chain": [{"action_type": action, "target_price_low": fake_low,
                          "target_price_high": fake_low + 10}],
        "rationale": "（mock）强烈看法",
    }, ensure_ascii=False)


def call_base_model(evidence_text: str, model: str, *, mock: bool, temperature: float) -> str:
    if mock:
        return _mock_overcommit(evidence_text)
    import os
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY 未设置。请 `export DASHSCOPE_API_KEY=...` 后重试，或用 --mock 验证流程。"
            "（密钥勿写入代码/日志/会话）"
        )
    from openai import OpenAI  # DashScope OpenAI 兼容端点
    client = OpenAI(api_key=key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TRADE_ACTION_SYSTEM_PROMPT},
            {"role": "user", "content": format_dpo_prompt(evidence_text)},
        ],
        temperature=temperature,
        extra_body={"enable_thinking": False},
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 规则校准：rejected → chosen（证据对齐的克制）
# ---------------------------------------------------------------------------
def evidence_quote(ticker: str, evidence_text: str, width: int = 40) -> Optional[str]:
    """取原文中含标的(ticker 或其中文别名)的一小段，作内联证据。"""
    cands = {ticker.strip().upper(), normalize_ticker(ticker), normalize_ticker(ticker).split(".")[0]}
    tnorm = _norm_ticker_loose(ticker)
    for alias, entry in ENTITY_REGISTRY.items():  # 映射到该 ticker 的中文别名
        if _norm_ticker_loose(entry[0]) == tnorm:
            cands.add(alias)
    for cand in cands:
        if not cand or len(cand) < 2:
            continue
        idx = evidence_text.upper().find(cand.upper())
        if idx >= 0:
            s = max(0, idx - width // 2)
            return evidence_text[s:s + width].strip()
    return None


def calibrate(rejected_raw: str, evidence_text: str) -> Dict[str, Any]:
    """把基座 rejected 校准为"证据对齐的克制"版 chosen。确定性。

    关键改动：证据不足时**降低 conviction 而非清零方向**；只有输出不可解析/结构破格
    才降级观望，标的不可溯时保留方向但 conviction 压到 0.3。标的可溯性走
    entity_registry，解决中文名↔ticker 字面匹配。chosen 顶层 key 收敛为 HQ 校验的 6 键。
    """
    obj = parse_output(rejected_raw)
    ok, _ = validate_structure(obj)
    if not ok or obj is None:
        c = dict(WATCHLIST_CHOSEN)
        c["rationale"] = "原输出不可解析或结构破格，保守观望"
        return normalize_chosen(c)

    ticker = str(obj.get("ticker", ""))
    grounded = ticker_grounded(ticker, evidence_text)

    # 去编造价位：原文找不到的 target_price 置空
    cited = extract_cited_numbers(obj)
    grounded_prices = [n for n in cited if number_in_text(n, evidence_text)]
    for step in obj.get("action_chain", []) or []:
        if not isinstance(step, dict):
            continue
        for k in ("target_price_low", "target_price_high"):
            v = step.get(k)
            if isinstance(v, (int, float)) and not number_in_text(float(v), evidence_text):
                step[k] = None

    committal = is_committal(obj)

    # 非承诺(neutral/risk_warning/watch)：保留方向，按可溯性给信念
    if not committal:
        obj["conviction"] = 0.5 if grounded else 0.3
        obj.setdefault("rationale", "原文未给出明确方向承诺")
        return normalize_chosen(obj)

    # 承诺：**降信念而非清零**。方向保留(源自真实 KOL 观点)、价位已去编造，
    # 用 conviction 表达证据强弱；标的可溯性(字面 or entity_registry)+价位可溯性 共同决定。
    if grounded and grounded_prices:
        conviction = 0.8          # 标的+价位都可溯，最强
    elif grounded and not cited:
        conviction = 0.6          # 标的可溯、无具体价位（纯方向观点）
    elif grounded:
        conviction = 0.45         # 标的可溯但引用价位是编的（已置空）→ 降信念
    else:
        conviction = 0.3          # 标的未验证到（即使价位可溯）→ 低信念保留（不清零）
    obj["conviction"] = conviction

    if not grounded:
        # 标的不可溯：**不透传基座幻觉 ticker**。基座常把"泡泡玛特"幻觉成 002857.SZ、
        # "禾赛"幻觉成 HES（Hess 石油），错误具体代码冒充"看似有标的"会注入有害训练锚定。
        # 置 UNRESOLVED 哨兵、保留方向（spec 决策3：不清零）；基座原始猜测由 harvest()
        # 另存 meta.ticker_guess，供人工签核参考（紫金 601899 等正确猜测也不丢）。
        obj["ticker"] = UNRESOLVED_TICKER
        obj["rationale"] = "基于原文方向（标的待核，需人工锚定）"
    else:
        quote = evidence_quote(ticker, evidence_text)
        obj["rationale"] = "基于原文可溯证据" + (f"：…{quote}…" if quote else "")
    return normalize_chosen(obj)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def harvest(
    candidates: List[Dict[str, Any]], *, model: str, mock: bool, temperature: float,
) -> Dict[str, Any]:
    pairs: List[Dict[str, Any]] = []
    stats = {"in": len(candidates), "called": 0, "call_failed": 0,
             "identical_dropped": 0, "calibrated_downgrade": 0, "kept": 0}
    for i, c in enumerate(candidates, 1):
        evidence = c.get("evidence_text", "")
        if not evidence:
            continue
        try:
            rejected_raw = call_base_model(evidence, model, mock=mock, temperature=temperature)
            # 清洗模型输出中的 markdown 代码围栏（```json ... ```）
            rejected_raw = parse_output(rejected_raw) or rejected_raw
            if isinstance(rejected_raw, dict):
                rejected_raw = json.dumps(rejected_raw, ensure_ascii=False)
            stats["called"] += 1
        except RuntimeError:
            raise  # key 缺失等致命错误，直接抛
        except Exception as e:  # 单条调用失败不致命
            stats["call_failed"] += 1
            print(f"  [warn] 候选 {i} 调用失败: {type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
            continue

        chosen_obj = calibrate(rejected_raw, evidence)
        chosen_raw = json.dumps(chosen_obj, ensure_ascii=False)

        if chosen_obj.get("direction") == "watchlist" and chosen_obj.get("ticker") == "NONE":
            stats["calibrated_downgrade"] += 1

        # 基座答对(校准后==原始) → 无偏好信号，丢弃
        if json.loads(chosen_raw) == (parse_output(rejected_raw) or {}):
            stats["identical_dropped"] += 1
            continue

        meta = {"passage_id": c.get("id"), "creator": c.get("creator"),
                "source_file": c.get("source_file"), "mock": mock,
                "hq_category": c.get("hq_category"),
                "hq_score": (c.get("signals") or {}).get("hq_score")}
        # ungrounded committal 的 chosen.ticker 已被 calibrate 置 UNRESOLVED；
        # 把基座原始 ticker 猜测留痕供人工锚定（不进 chosen，不污染训练文本）。
        if chosen_obj.get("ticker") == UNRESOLVED_TICKER:
            guess = str((parse_output(rejected_raw) or {}).get("ticker", "")).strip()
            if guess:
                meta["ticker_guess"] = guess

        pairs.append({
            "prompt": format_dpo_prompt(evidence),
            "chosen": chosen_raw,
            "rejected": rejected_raw,
            "meta": meta,
        })
        stats["kept"] += 1
    return {"pairs": pairs, "stats": stats}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="跑基座模型 harvest rejected + 规则校准 chosen → DPO 偏好对",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--in", dest="inp", type=str, required=True, help="candidates.jsonl")
    ap.add_argument("--out", type=str, required=True, help="输出 pairs.jsonl")
    ap.add_argument("--model", type=str, default="qwen3-8b", help="基座模型(on-policy 建议 qwen3-8b)")
    ap.add_argument("--mock", action="store_true", help="无 key 验证流程(确定性 mock 基座输出)")
    ap.add_argument("--temperature", type=float, default=0.7, help="采样温度(诱发过度承诺/多样性)")
    ap.add_argument("--limit", type=int, help="只处理前 N 条(试跑省钱)")
    args = ap.parse_args()

    candidates = load_jsonl(Path(args.inp))
    if args.limit:
        candidates = candidates[:args.limit]
    if not candidates:
        print("[error] 候选为空", file=sys.stderr)
        return 1

    print(f"prompt/system 真相源: {_PROMPT_SOURCE}")
    print(f"基座: {'MOCK(确定性,非真实)' if args.mock else args.model}  候选 {len(candidates)} 条")
    result = harvest(candidates, model=args.model, mock=args.mock, temperature=args.temperature)
    s = result["stats"]
    print(f"调用成功 {s['called']}  失败 {s['call_failed']}  "
          f"校准降级观望 {s['calibrated_downgrade']}  基座答对丢弃 {s['identical_dropped']}  "
          f"保留偏好对 {s['kept']}")

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        for p in result["pairs"]:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"已写入 {outp}（{s['kept']} 对）")
    if args.mock:
        print("⚠ MOCK 数据仅验证流程，不可用于真实训练；真实跑请去 --mock 并 export DASHSCOPE_API_KEY。")
    elif s["kept"] < 120:
        print(f"注意: 目标 ≥120 对，当前 {s['kept']}（基座答对的会被丢）；可增候选或调 temperature。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
