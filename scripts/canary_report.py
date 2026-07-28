#!/usr/bin/env python3
"""C10 金丝雀批次报告（只读）。

把一次放量批次的吞吐、失败分布、token 消耗、磁盘增量与下游漏斗汇总成
可复现的 markdown —— 金丝雀的产出必须是可审计的报表，不是手工拼的数字。

批次身份由 ``--manifest``（候选清单）与 ``--batch-id``（run_state checkpoint）
共同确定：清单给出「计划处理哪些文件」，checkpoint 给出「实际处理了什么、
用了多久」，两者的差就是失败与漏处理。

    python scripts/canary_report.py --manifest data/_candidates/t9_canary_1k.jsonl \\
        --batch-id c10_canary_t9 --out docs/specs/2026-07-XX-c10-canary-report.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _year_of(filepath: str) -> str:
    if "/2026年/" in filepath:
        return "2026"
    if "/2025年/" in filepath:
        return "2025"
    return "other"


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        out = subprocess.run(
            ["du", "-sk", str(path)], capture_output=True, text=True, timeout=120
        ).stdout.split()[0]
        return int(out) * 1024
    except Exception:  # noqa: BLE001
        return 0


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--since", default=None,
                        help="只统计此 ISO 时间之后的 token 记录（默认取 checkpoint 起点）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    manifest = _read_jsonl(args.manifest)
    checkpoint = _read_jsonl(data_root / "run_state" / f"{args.batch_id}.checkpoint.jsonl")

    # ── 批次身份 ────────────────────────────────────────────────────────
    planned_years = Counter(_year_of(m.get("filepath", "")) for m in manifest)
    brokers = Counter(m.get("broker") for m in manifest)

    # ── F1 吞吐 ─────────────────────────────────────────────────────────
    status = Counter(r.get("status") for r in checkpoint)
    times = sorted(
        datetime.fromisoformat(r["ts"]) for r in checkpoint if r.get("ts")
    )
    span_min = (times[-1] - times[0]).total_seconds() / 60 if len(times) > 1 else 0.0
    rate = len(checkpoint) / span_min if span_min else 0.0
    errors = Counter(
        r.get("error_code") for r in checkpoint if r.get("status") != "done"
    )

    # ── 各 F-stage 落地量（限定本批 content_id）────────────────────────
    batch_ids = {r["content_id"] for r in checkpoint if r.get("content_id")}
    f1_ok = sum(
        1 for cid in batch_ids
        if (data_root / "F1_standardized" / cid / "content_envelope.json").exists()
    )
    f2_ok = sum(1 for cid in batch_ids if (data_root / "F2_anchored" / f"{cid}.json").exists())
    f5_ok = sum(
        1 for cid in batch_ids
        if (data_root / "F5_executed" / f"bri_{cid}_actions.json").exists()
        or (data_root / "F5_executed" / f"t9i_{cid}_actions.json").exists()
    )

    # 正文规模（F1 质量的粗指标：空/薄信封说明图片型 PDF 被静默跳过）
    size_buckets: Counter = Counter()
    for cid in batch_ids:
        env = data_root / "F1_standardized" / cid / "content_envelope.json"
        if not env.exists():
            continue
        try:
            doc = json.loads(env.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            size_buckets["unreadable"] += 1
            continue
        chars = sum(len(b.get("text") or "") for b in (doc.get("blocks") or []))
        if chars == 0:
            size_buckets["空(0)"] += 1
        elif chars < 500:
            size_buckets["薄(<500)"] += 1
        elif chars < 5000:
            size_buckets["500-5k"] += 1
        else:
            size_buckets["5k+"] += 1

    # ── token 消耗 ──────────────────────────────────────────────────────
    since = args.since or (times[0].isoformat() if times else None)
    usage = _read_jsonl(data_root / "llm_usage" / "usage.jsonl")
    if since:
        usage = [u for u in usage if (u.get("ts") or "") >= since]
    by_tag: Dict[Optional[str], Dict[str, int]] = {}
    for record in usage:
        tag = record.get("caller_tag") or "(untagged)"
        slot = by_tag.setdefault(tag, {"calls": 0, "tokens": 0, "null_token_calls": 0})
        slot["calls"] += 1
        total = record.get("total_tokens")
        if total:
            slot["tokens"] += int(total)
        else:
            slot["null_token_calls"] += 1

    lines: List[str] = []
    add = lines.append
    add(f"# C10 金丝雀批次报告 — `{args.batch_id}`")
    add("")
    add(f"- 清单：`{args.manifest}`（{len(manifest)} 份）")
    add(f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}")
    add("")

    add("## 1. 批次构成（外推有效性的前提）")
    add("")
    add("| 维度 | 分布 |")
    add("|---|---|")
    add(f"| 年份 | {', '.join(f'{k} {v}' for k, v in sorted(planned_years.items()))} |")
    add(f"| 券商（前 6） | {', '.join(f'{k} {v}' for k, v in brokers.most_common(6))} |")
    add("")

    add("## 2. F1 吞吐")
    add("")
    add("| 指标 | 值 |")
    add("|---|---|")
    add(f"| checkpoint 条数 | {len(checkpoint)} |")
    add(f"| 状态分布 | {dict(status)} |")
    add(f"| 耗时（首末 checkpoint） | {span_min:.1f} 分钟 |")
    add(f"| 速率 | **{rate:.1f} 份/分钟** |")
    if errors:
        add(f"| 失败原因 | {dict(errors)} |")
    add("")

    add("## 3. 各 F-stage 落地（限本批）")
    add("")
    add("| 阶段 | 完成数 | 占本批 |")
    add("|---|---:|---:|")
    total_batch = len(batch_ids) or 1
    for label, count in (("F1 envelope", f1_ok), ("F2 anchored", f2_ok), ("F5 actions", f5_ok)):
        add(f"| {label} | {count} | {count / total_batch * 100:.1f}% |")
    add("")
    add(f"F1 正文规模分布：{dict(size_buckets)}")
    add("")
    add("> 空/薄信封是图片型 PDF 被静默跳过的信号 —— 该数必须为 0，否则 OCR 未生效。")
    add("")

    add("## 4. Token 消耗")
    add("")
    if not by_tag:
        add("本批**零 LLM 调用**。昂贵的抽取（T3/T9）在烧录阶段已付，")
        add("F0→F5 全链为确定性路径（F2 锚定、A3/D1 适配器、F4 规则、F5 composer 均无 LLM）。")
    else:
        add("| caller_tag | 调用数 | token 合计 | 无 token 记录 |")
        add("|---|---:|---:|---:|")
        for tag, slot in sorted(by_tag.items(), key=lambda kv: -kv[1]["tokens"]):
            add(f"| {tag} | {slot['calls']} | {slot['tokens']:,} | {slot['null_token_calls']} |")
        add("")
        add("> `无 token 记录` 非零说明该路径的响应未带 usage —— 成本会被低估，需核查。")
    add("")

    add("## 5. 磁盘增量")
    add("")
    add("| 目录 | 大小 |")
    add("|---|---:|")
    for name in ("F0_intake", "F1_standardized", "F2_anchored", "F5_executed", "raw/broker"):
        add(f"| `data/{name}` | {_fmt_bytes(_dir_bytes(data_root / name))} |")
    add("")

    output = "\n".join(lines) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
