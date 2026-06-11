#!/usr/bin/env python3
"""to_bailian.py — 把内部 DPO 偏好对转成百炼(Model Studio) DPO ChatML 格式.

闸③已核实（阿里云百炼官方帮助中心）：
  - DPO 训练数据是 ChatML，`chosen`/`rejected` 是**对象** {role, content}，非字符串。
  - 与 HF/TRL 的 {prompt, chosen, rejected}(纯字符串) 不同，故需本转换器。
  - Qwen3-8B(qwen3-8b) 支持 DPO full + DPO LoRA；DPO 需上百条偏好数据。

百炼一行结构:
  {"messages": [{"role":"system","content":...},{"role":"user","content":...}],
   "chosen":   {"role":"assistant","content":"赞同的期望输出"},
   "rejected": {"role":"assistant","content":"反对的期望输出"}}

输入(内部格式, 每行): {"prompt": "...", "chosen": "<JSON串>", "rejected": "<JSON串>"}
输出: data.jsonl(百炼 ChatML)

用法:
    python scripts/to_bailian.py --demo
    python scripts/to_bailian.py --in data/dpo/pairs.jsonl --out data/dpo/data.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def as_content(x: Any) -> str:
    """chosen/rejected 内容统一为字符串(若为 dict 则 json 序列化)。"""
    if isinstance(x, str):
        return x
    return json.dumps(x, ensure_ascii=False)


# 转换器以包内 finer.ml.dpo_trainer 为单一真相源（正确依赖方向：脚本依赖包）。
# DPOExporter.save_bailian_format 与本脚本共用同一 to_bailian_record。
try:
    from finer.ml.dpo_trainer import (  # type: ignore
        to_bailian_record, TRADE_ACTION_SYSTEM_PROMPT as DEFAULT_SYSTEM,
    )
    _SYS_SOURCE = "finer.ml.dpo_trainer"
except Exception:  # pragma: no cover
    DEFAULT_SYSTEM = (
        "你是一位专业的金融分析师助手，擅长从文本中提取结构化的交易观点。"
        "证据不足时应明确观望(hold/watchlist)，不得编造原文没有的标的或价位。"
        "输出必须严格遵循指定的 JSON Schema 格式。"
    )
    _SYS_SOURCE = "fallback(hardcoded)"

    def to_bailian_record(prompt, chosen, rejected, system=None):  # type: ignore
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return {
            "messages": messages,
            "chosen": {"role": "assistant", "content": as_content(chosen)},
            "rejected": {"role": "assistant", "content": as_content(rejected)},
        }


def validate_pair(rec: Dict[str, Any]) -> Tuple[bool, str]:
    """校验输入偏好对最小要求。"""
    for k in ("prompt", "chosen", "rejected"):
        if k not in rec:
            return False, f"缺字段 {k}"
    if not isinstance(rec["prompt"], str) or not rec["prompt"].strip():
        return False, "prompt 为空"
    if as_content(rec["chosen"]) == as_content(rec["rejected"]):
        return False, "chosen 与 rejected 相同(无偏好信号)"
    return True, "ok"


def is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except (json.JSONDecodeError, ValueError, TypeError):
        return False


def convert(
    rows: List[Dict[str, Any]], *, system: Optional[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    out: List[Dict[str, Any]] = []
    stats = {"total_in": len(rows), "converted": 0, "dropped": 0,
             "chosen_json": 0, "rejected_json": 0}
    for i, rec in enumerate(rows, 1):
        ok, reason = validate_pair(rec)
        if not ok:
            stats["dropped"] += 1
            print(f"  [drop] line {i}: {reason}", file=sys.stderr)
            continue
        if is_json(as_content(rec["chosen"])):
            stats["chosen_json"] += 1
        if is_json(as_content(rec["rejected"])):
            stats["rejected_json"] += 1
        out.append(to_bailian_record(rec["prompt"], rec["chosen"], rec["rejected"], system=system))
        stats["converted"] += 1
    return out, stats


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


def demo_rows() -> List[Dict[str, Any]]:
    def aj(**kw):
        return json.dumps(kw, ensure_ascii=False)
    return [
        {"prompt": "从以下文本提取 TradeAction（证据不足应观望，勿编造）：\n苹果 AAPL 在 150 附近支撑，回踩 148-152 可建仓。",
         "chosen": aj(ticker="AAPL", direction="bullish",
                      action_chain=[{"action_type": "long", "target_price_low": 148, "target_price_high": 152}]),
         "rejected": aj(ticker="AAPL", direction="bullish",
                        action_chain=[{"action_type": "long", "target_price_low": 200, "target_price_high": 210}])},
        {"prompt": "从以下文本提取 TradeAction（证据不足应观望，勿编造）：\n大盘震荡，没明确机会，注意风险。",
         "chosen": aj(ticker="NONE", direction="watchlist", action_chain=[{"action_type": "watch"}]),
         "rejected": aj(ticker="TSLA", direction="bullish",
                        action_chain=[{"action_type": "long", "target_price_low": 250}])},
    ]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="内部 DPO 偏好对 → 百炼 DPO ChatML(data.jsonl)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--in", dest="inp", type=str, help="输入 {prompt,chosen,rejected} jsonl")
    ap.add_argument("--out", type=str, help="输出百炼 data.jsonl")
    ap.add_argument("--demo", action="store_true", help="用内置玩具数据演示转换(打印首条)")
    ap.add_argument("--no-system", action="store_true", help="不写入 system 角色")
    ap.add_argument("--system", type=str, help="自定义 system 内容(默认取抽取系统提示)")
    args = ap.parse_args()

    system = None if args.no_system else (args.system or DEFAULT_SYSTEM)

    if args.demo:
        rows = demo_rows()
    else:
        if not args.inp:
            ap.error("需 --in（或 --demo）")
        rows = load_jsonl(Path(args.inp))

    out, stats = convert(rows, system=system)

    print(f"system 真相源: {_SYS_SOURCE}{' (未写入)' if system is None else ''}")
    print(f"输入 {stats['total_in']} → 转换 {stats['converted']}，丢弃 {stats['dropped']}")
    print(f"chosen 合法 JSON: {stats['chosen_json']}/{stats['converted']}  "
          f"rejected 合法 JSON: {stats['rejected_json']}/{stats['converted']}")

    if args.demo:
        print("\n=== 百炼 ChatML 首条样例 ===")
        print(json.dumps(out[0], ensure_ascii=False, indent=2))
        if stats["converted"] < 120:
            print(f"\n注意: 百炼 DPO 需上百条；当前仅 {stats['converted']} 条(demo)。")
        return 0

    if not args.out:
        ap.error("需 --out 写出 data.jsonl")
    if not out:
        print("[error] 无可写记录", file=sys.stderr)
        return 1

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"已写入 {outp}（{stats['converted']} 行百炼 ChatML）")
    if stats["converted"] < 120:
        print(f"注意: 百炼 DPO 建议上百条；当前 {stats['converted']} 条，偏少。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
