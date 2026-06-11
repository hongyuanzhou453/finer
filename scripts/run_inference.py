#!/usr/bin/env python3
"""run_inference.py — 在评测集上跑模型，产出 eval_compare 需要的 before/after.jsonl.

环 A 评测步：分别用基座(before)和微调后(after)模型在同一评测集上推理，
输出 `{"id","output":"<模型原始抽取JSON串>"}` 供 scripts/eval_compare.py 对比。

- before：基座 qwen3-8b（DashScope）。
- after ：百炼部署的 DPO-LoRA 微调模型（同 OpenAI 兼容接口，换 --model 为部署模型 id；
          如自定义网关再加 --base-url）。

闸②：真实推理需 DASHSCOPE_API_KEY；无 key 用 --mock 验证 harness。

用法:
    # 验证 harness（无 key）
    python scripts/run_inference.py --eval-set data/dpo/eval/eval_set.jsonl --out /tmp/before.jsonl --mock

    # before（基座）
    export DASHSCOPE_API_KEY=...
    python scripts/run_inference.py --eval-set data/dpo/eval/eval_set.jsonl --out data/dpo/eval/before.jsonl --model qwen3-8b

    # after（百炼部署的微调模型 id）
    python scripts/run_inference.py --eval-set data/dpo/eval/eval_set.jsonl --out data/dpo/eval/after.jsonl --model <你的部署模型id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from finer.ml.dpo_trainer import format_dpo_prompt, TRADE_ACTION_SYSTEM_PROMPT  # type: ignore
except Exception:  # pragma: no cover
    TRADE_ACTION_SYSTEM_PROMPT = "你是金融分析师助手，证据不足应观望，勿编造标的/价位，严格输出 JSON。"
    def format_dpo_prompt(evidence_text: str, include_schema: bool = False) -> str:  # type: ignore
        return f"从以下文本提取 TradeAction（证据不足应观望，勿编造）：\n{evidence_text}"

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _mock_infer(prompt: str) -> str:
    """确定性 mock：返回一个合规的简化抽取 JSON（验证 harness 用）。"""
    h = int(hashlib.sha1(prompt.encode("utf-8")).hexdigest(), 16)
    if h % 3 == 0:  # 1/3 输出观望，模拟克制
        return json.dumps({"ticker": "NONE", "direction": "watchlist",
                           "action_chain": [{"action_type": "watch"}]}, ensure_ascii=False)
    direction = "bullish" if h % 2 == 0 else "bearish"
    action = "long" if direction == "bullish" else "short"
    return json.dumps({"ticker": "AAPL", "direction": direction,
                       "action_chain": [{"action_type": action}]}, ensure_ascii=False)


def infer(prompt: str, model: str, base_url: str, *, mock: bool, temperature: float) -> str:
    if mock:
        return _mock_infer(prompt)
    import os
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("DASHSCOPE_API_KEY 未设置；export 后重试，或用 --mock。（密钥勿入代码/日志）")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TRADE_ACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def prompt_of(item: Dict[str, Any]) -> Optional[str]:
    """评测项取 prompt：优先 item['prompt']，否则由 evidence_text 构造。"""
    if item.get("prompt"):
        return item["prompt"]
    ev = item.get("evidence_text")
    return format_dpo_prompt(ev) if ev else None


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
        description="在评测集上跑模型 → before/after.jsonl",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--eval-set", required=True, help="eval_set.jsonl（含 id + prompt 或 evidence_text）")
    ap.add_argument("--out", required=True, help="输出 {id, output} jsonl")
    ap.add_argument("--model", default="qwen3-8b", help="模型 id：基座 qwen3-8b / 微调后填部署 id")
    ap.add_argument("--base-url", default=DASHSCOPE_BASE, help="OpenAI 兼容端点")
    ap.add_argument("--mock", action="store_true", help="无 key 验证 harness")
    ap.add_argument("--temperature", type=float, default=0.0, help="评测建议 0（可复现）")
    ap.add_argument("--limit", type=int, help="只跑前 N 条")
    args = ap.parse_args()

    items = load_jsonl(Path(args.eval_set))
    if args.limit:
        items = items[:args.limit]
    if not items:
        print("[error] 评测集为空", file=sys.stderr)
        return 1

    print(f"模型: {'MOCK' if args.mock else args.model}  评测集 {len(items)} 条  base_url={args.base_url}")
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    ok = fail = skipped = 0
    with open(outp, "w", encoding="utf-8") as f:
        for i, it in enumerate(items, 1):
            eid = it.get("id")
            prompt = prompt_of(it)
            if not eid or not prompt:
                skipped += 1
                continue
            try:
                output = infer(prompt, args.model, args.base_url, mock=args.mock, temperature=args.temperature)
                ok += 1
            except RuntimeError:
                raise
            except Exception as e:
                fail += 1
                print(f"  [warn] {eid} 推理失败: {type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
                continue
            f.write(json.dumps({"id": eid, "output": output}, ensure_ascii=False) + "\n")
    print(f"成功 {ok}  失败 {fail}  跳过 {skipped} → {outp}")
    if args.mock:
        print("⚠ MOCK 输出仅验证 harness，不可当真实评测。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
