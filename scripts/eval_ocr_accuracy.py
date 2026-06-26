#!/usr/bin/env python
"""OCR accuracy eval — MiMo output vs human gold, OmniDocBench-style metrics.

OmniDocBench scores models on *its* documents; this scores MiMo on *our* research
screenshots. We mirror its metric family (normalized edit distance for text, plus
number-level recall/precision because numbers are what investment research lives
or dies on) against a human-transcribed gold set.

Gold files: data/F1_gold_sets/ocr_accuracy/*.json — each is a human (Claude-as-
annotator) transcription that IS the ground truth:

    {
      "content_id": "local_...",                 # matches F1_standardized/<id>/
      "note": "财务表格 / 指数涨跌 / 长文 ...",
      "gold_text": "逐字转写的正确文本（可只覆盖关键段）",
      "gold_numbers": ["114583", "15.4", "-3.79", ...]  # canonical (commas/%% stripped)
    }

Metrics per image + aggregate:
- char_similarity : difflib ratio(gold_text, pred_text)  ~ (1 - CER) proxy
- number_recall   : |gold∩pred| / |gold|   — did MiMo capture the real numbers
- number_precision: |gold∩pred| / |pred|   — did MiMo invent numbers (hallucination)

    python scripts/eval_ocr_accuracy.py
"""

from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def canonical_numbers(text: str) -> set[str]:
    """Extract numbers (commas stripped, accounting parens = negative).

    Financial OCR convention: (1,234) and （31.2%） mean -1234 / -31.2. We
    normalize parenthesized numbers to a leading minus before extraction so they
    match negative gold values.
    """
    if not text:
        return set()
    text = re.sub(r"[(（]\s*(\d[\d,]*\.?\d*)\s*%?\s*[)）]", lambda m: "-" + m.group(1), text)
    out: set[str] = set()
    for m in _NUM_RE.findall(text):
        v = m.replace(",", "").rstrip(".")
        if v in ("", "-", "0", "-0"):
            continue
        out.add(v)
    return out


def envelope_text(env: dict) -> str:
    return "\n".join((b.get("text") or "") for b in env.get("blocks", []))


def load_pred(data_root: Path, content_id: str) -> str | None:
    p = data_root / "F1_standardized" / content_id / "content_envelope.json"
    if not p.exists():
        return None
    try:
        return envelope_text(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


def main() -> None:
    data_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    gold_dir = data_root / "F1_gold_sets" / "ocr_accuracy"
    gold_files = sorted(gold_dir.glob("*.json"))
    if not gold_files:
        print(f"No gold files in {gold_dir}.")
        print("Annotate a few first: each JSON needs content_id + gold_text + gold_numbers.")
        raise SystemExit(1)

    rows = []
    for gf in gold_files:
        gold = json.loads(gf.read_text(encoding="utf-8"))
        cid = gold["content_id"]
        pred_text = load_pred(data_root, cid)
        if pred_text is None:
            rows.append({"content_id": cid, "note": gold.get("note", ""), "status": "no_pred"})
            continue

        gold_text = gold.get("gold_text", "")
        char_sim = SequenceMatcher(None, gold_text, pred_text).ratio() if gold_text else None

        gold_nums = set(gold.get("gold_numbers", []))
        pred_nums = canonical_numbers(pred_text)
        inter = gold_nums & pred_nums
        recall = len(inter) / len(gold_nums) if gold_nums else None
        prec = len(inter) / len(pred_nums) if pred_nums else None
        missed = sorted(gold_nums - pred_nums)

        rows.append({
            "content_id": cid,
            "note": gold.get("note", ""),
            "status": "ok",
            "char_sim": char_sim,
            "n_gold_num": len(gold_nums),
            "recall": recall,
            "precision": prec,
            "missed_numbers": missed,
        })

    ok = [r for r in rows if r["status"] == "ok"]
    print(f"=== OCR accuracy eval ({len(ok)}/{len(rows)} scored) ===\n")
    print(f"{'note':14s} {'char_sim':>8s} {'#num':>5s} {'recall':>7s} {'prec':>7s}  missed")
    for r in rows:
        if r["status"] != "ok":
            print(f"{r['note'][:14]:14s}  [{r['status']}] {r['content_id']}")
            continue
        cs = f"{r['char_sim']:.3f}" if r["char_sim"] is not None else "  -  "
        rc = f"{r['recall']:.3f}" if r["recall"] is not None else "  -  "
        pr = f"{r['precision']:.3f}" if r["precision"] is not None else "  -  "
        missed = ",".join(r["missed_numbers"][:6])
        print(f"{r['note'][:14]:14s} {cs:>8s} {r['n_gold_num']:>5d} {rc:>7s} {pr:>7s}  {missed}")

    def avg(key):
        vals = [r[key] for r in ok if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    print("\n=== aggregate ===")
    for k, label in [("char_sim", "char similarity"), ("recall", "number recall"), ("precision", "number precision")]:
        a = avg(k)
        print(f"  {label:18s}: {a:.3f}" if a is not None else f"  {label:18s}: -")
    tot_gold = sum(r["n_gold_num"] for r in ok)
    tot_missed = sum(len(r["missed_numbers"]) for r in ok)
    print(f"  numbers: {tot_gold - tot_missed}/{tot_gold} matched ({tot_missed} missed across {len(ok)} imgs)")


if __name__ == "__main__":
    main()
