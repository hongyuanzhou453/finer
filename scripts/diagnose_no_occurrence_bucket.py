#!/usr/bin/env python3
"""诊断定向验证的 no_occurrence 桶：T3 幻觉 还是 F1 文本层缺失？（P1.5）

对随机抽样的搁浅 intent，把三层文本对照：

  A. F1/F2 信封正文（流水线实际看到的）
  B. ``pdftotext`` 直抽原始 PDF（PDF 文本层的全部内容）
  C. T3 声明的 symbol / name

判定：
  * ``f1_text_gap``  —— PDF 文本层里有，F1 信封里没有 → F1 抽取丢内容（可修）
  * ``image_only``   —— PDF 文本层几乎为空（图片型研报）→ 归 OCR 决策收益侧
  * ``t3_hallucination`` —— PDF 文本层充足但确实找不到 → T3 抽取幻觉，计入污染率
  * ``verified_elsewhere`` —— 只以别的写法出现（如去后缀/中文名）→ 门可再放宽

只读，不写任何流水线数据。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.targeted_anchor import verify_declared_target  # noqa: E402

MIN_TEXT_LAYER_CHARS = 400  # 低于此判为图片型 PDF


def _pdftotext(path: Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["pdftotext", "-q", str(path), "-"],
            capture_output=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.decode("utf-8", errors="replace") if out.returncode == 0 else None


def _envelope_index(data_root: Path) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    pattern = re.compile(r'"envelope_id"\s*:\s*"([^"]+)"')
    for path in (data_root / "F2_anchored").glob("broker_*.json"):
        try:
            head = path.read_text(encoding="utf-8")[:600]
        except OSError:
            continue
        m = pattern.search(head)
        if m:
            index[m.group(1)] = path
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    data_root = args.data_root.resolve()

    actioned = set()
    for f in (data_root / "F5_executed").glob("bri_*_actions.json"):
        try:
            for a in json.loads(f.read_text(encoding="utf-8")).get("actions", []):
                if a.get("intent_id"):
                    actioned.add(a["intent_id"])
        except (OSError, json.JSONDecodeError):
            continue

    env_index = _envelope_index(data_root)
    env_cache: Dict[str, Dict[str, Any]] = {}
    candidates: List[Dict[str, Any]] = []

    for f in (data_root / "F3_intents").glob("bri_*.json"):
        try:
            intent = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if intent.get("intent_id") in actioned:
            continue
        path = env_index.get(intent.get("envelope_id"))
        if path is None:
            continue
        key = str(path)
        if key not in env_cache:
            try:
                env_cache[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                env_cache[key] = {}
        env = env_cache[key]
        if not env:
            continue
        res = verify_declared_target(
            env, intent.get("target_symbol") or "", intent.get("target_name")
        )
        if res.status == "no_occurrence":
            candidates.append({"intent": intent, "env": env})

    print(f"no_occurrence 候选: {len(candidates)}")
    random.seed(args.seed)
    sample = random.sample(candidates, min(args.n, len(candidates)))

    verdicts: Counter = Counter()
    rows: List[Dict[str, Any]] = []

    for entry in sample:
        intent, env = entry["intent"], entry["env"]
        symbol = (intent.get("target_symbol") or "").strip()
        name = (intent.get("target_name") or "").strip()
        base = symbol.split(".")[0]

        f1_text = "\n".join((b.get("text") or "") for b in env.get("blocks") or [])
        raw_path = Path(env.get("raw_path") or "")
        pdf_text = _pdftotext(raw_path) if raw_path.is_file() else None

        needles = [n for n in {symbol, base, name} if n and len(n) >= 2]
        in_f1 = any(n in f1_text for n in needles)
        in_pdf = bool(pdf_text) and any(n in pdf_text for n in needles)

        if pdf_text is None:
            verdict = "pdf_unreadable"
        elif len(pdf_text.strip()) < MIN_TEXT_LAYER_CHARS:
            verdict = "image_only"
        elif in_f1:
            verdict = "verified_elsewhere"   # 门拒了，但字面确实在 F1 文本里
        elif in_pdf:
            verdict = "f1_text_gap"
        else:
            verdict = "t3_hallucination"

        verdicts[verdict] += 1
        rows.append({
            "intent_id": intent.get("intent_id"),
            "symbol": symbol, "name": name, "verdict": verdict,
            "f1_chars": len(f1_text), "pdf_chars": len(pdf_text or ""),
            "file": raw_path.name,
        })

    print(f"\n== 判定分布（n={len(rows)}）==")
    for k, v in verdicts.most_common():
        print(f"  {k}: {v}  ({v / max(1, len(rows)):.1%})")

    print("\n== 明细 ==")
    for r in rows:
        print(f"  {r['verdict']:<20} {r['symbol']:<14} {r['name'][:24]:<24} "
              f"f1={r['f1_chars']:>7} pdf={r['pdf_chars']:>7}")

    out = data_root / "_audit" / "no_occurrence_diagnosis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"n": len(rows), "verdicts": dict(verdicts), "rows": rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
