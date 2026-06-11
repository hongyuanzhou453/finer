#!/usr/bin/env python3
"""select_passages.py — 从真实 KOL 聊天转写选取候选 evidence_text 段落.

半真实 DPO 方案第 1 步（零 key、零费用）：把 data/ 下的 chat_history_*.md 真实投研问答
拆成消息块，过滤噪声(vision OCR 失败桩 / 空块 / 无投研信号)，去重，输出候选段落。
下游 harvest_rejected.py 用这些真实段落跑基座模型拿 rejected。

详见 docs/specs/2026-06-07-dpo-bailian-training-line.md §4（半真实来源）。

用法:
    python scripts/select_passages.py --out data/dpo/candidates.jsonl
    python scripts/select_passages.py --out data/dpo/candidates.jsonl --limit 120 --per-creator 60
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 消息块头: ### [2026-03-12 15:36:00] ou_xxx (text)
_BLOCK_RE = re.compile(r"^###\s+\[([^\]]+)\]\s+(\S+)\s+\(([^)]+)\)\s*$", re.MULTILINE)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")

# 投研信号
_DIRECTION_WORDS = ["买入", "卖出", "加仓", "减仓", "看多", "看空", "支撑", "压力", "目标价",
                    "止损", "止盈", "建仓", "入场", "埋伏", "超跌", "反弹", "减持", "增持",
                    "风险", "回调", "突破", "跌破", "抄底", "逢低", "高位"]
_HORIZON_LONG = ["长期", "长线", "年", "2026", "2027", "趋势", "确定性", "基本面"]
_HORIZON_SHORT = ["短期", "短线", "今天", "明天", "本周", "这周", "盘", "日内", "近期"]
_TICKER_RE = re.compile(r"[A-Z]{2,5}\b|\d{4,6}\.(?:HK|SH|SZ)|港股|A股|美股")
_PRICE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:元|美元|港币|港元|块)|\d+(?:\.\d+)?\s*[-~]\s*\d+(?:\.\d+)?|PE|倍|亿")

# 噪声标记
_NOISE_MARKERS = ["DASHSCOPE_API_KEY", "fetch failed", "empty data", "merge_forward",
                  "[Merged forward", "Error:", "fetch_failed"]


def clean_text(raw: str) -> str:
    """去 HTML、去 Q:/A: 前缀冗余、规范空白。"""
    t = _HTML_RE.sub("", raw)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = _WS_RE.sub(" ", t)
    lines = [ln.strip() for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def split_blocks(text: str) -> List[Dict[str, str]]:
    """按消息块头切分，返回 [{timestamp, kind, content}]。"""
    blocks: List[Dict[str, str]] = []
    matches = list(_BLOCK_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = clean_text(text[start:end])
        blocks.append({"timestamp": m.group(1), "kind": m.group(3), "content": content})
    return blocks


def signal_of(text: str) -> Dict[str, Any]:
    """轻量启发式信号：方向/价位/标的 + 周期/方向偏向（辅助 12 格覆盖，非精确标注）。"""
    has_dir = any(w in text for w in _DIRECTION_WORDS)
    has_price = bool(_PRICE_RE.search(text))
    has_ticker = bool(_TICKER_RE.search(text))
    long_hits = sum(text.count(w) for w in _HORIZON_LONG)
    short_hits = sum(text.count(w) for w in _HORIZON_SHORT)
    horizon = "long" if long_hits > short_hits else ("short" if short_hits > long_hits else "unknown")
    return {
        "has_direction": has_dir, "has_price": has_price, "has_ticker": has_ticker,
        "horizon_hint": horizon,
        "signal_score": int(has_dir) + int(has_price) + int(has_ticker),
    }


def is_noise(text: str) -> bool:
    return (not text) or any(m in text for m in _NOISE_MARKERS)


def creator_of(path: Path) -> str:
    parts = path.parts
    for seg in ("maodaren", "9you"):
        if seg in parts or seg in path.name:
            return seg
    if "9友" in path.name or "9友" in str(path) or "20269" in path.name:
        return "9you"
    if "猫大人" in path.name:
        return "maodaren"
    return "unknown"


def content_hash(text: str) -> str:
    norm = re.sub(r"\s+", "", text)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def select(
    files: List[Path], *, min_signal: int, min_len: int, max_len: int,
    limit: Optional[int], per_creator: Optional[int],
) -> Dict[str, Any]:
    seen_hashes = set()
    kept: List[Dict[str, Any]] = []
    stats = {"files": len(files), "blocks": 0, "noise": 0, "too_short": 0,
             "too_long": 0, "low_signal": 0, "dup": 0, "kept": 0}
    per_creator_count: Dict[str, int] = {}

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        creator = creator_of(path)
        for blk in split_blocks(text):
            stats["blocks"] += 1
            content = blk["content"]
            if is_noise(content):
                stats["noise"] += 1
                continue
            if len(content) < min_len:
                stats["too_short"] += 1
                continue
            if len(content) > max_len:
                stats["too_long"] += 1
                continue
            sig = signal_of(content)
            if sig["signal_score"] < min_signal:
                stats["low_signal"] += 1
                continue
            h = content_hash(content)
            if h in seen_hashes:
                stats["dup"] += 1
                continue
            if per_creator and per_creator_count.get(creator, 0) >= per_creator:
                continue
            seen_hashes.add(h)
            per_creator_count[creator] = per_creator_count.get(creator, 0) + 1
            kept.append({
                "id": f"psg_{h}",
                "source_file": str(path),
                "creator": creator,
                "timestamp": blk["timestamp"],
                "evidence_text": content,
                "char_len": len(content),
                "signals": sig,
            })
            stats["kept"] += 1
            if limit and len(kept) >= limit:
                stats["kept"] = len(kept)
                return {"items": kept, "stats": stats, "by_creator": per_creator_count}
    return {"items": kept, "stats": stats, "by_creator": per_creator_count}


def find_chat_history(root: Path) -> List[Path]:
    """优先取规范来源；同名内容靠 content_hash 去重，无需路径去重。"""
    return sorted(root.rglob("chat_history_*.md"))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从真实 KOL 聊天转写选取候选 evidence_text 段落",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--src", type=str, default="data", help="搜索 chat_history_*.md 的根目录")
    ap.add_argument("--out", type=str, help="输出 candidates.jsonl（不给则只打印统计）")
    ap.add_argument("--min-signal", type=int, default=2, help="最小信号分(方向/价位/标的命中数)")
    ap.add_argument("--min-len", type=int, default=40, help="最小字符数")
    ap.add_argument("--max-len", type=int, default=1200, help="最大字符数")
    ap.add_argument("--limit", type=int, help="最多保留多少段")
    ap.add_argument("--per-creator", type=int, help="每个 creator 上限(平衡来源)")
    args = ap.parse_args()

    root = Path(args.src)
    if not root.exists():
        print(f"[error] 源目录不存在: {root}", file=sys.stderr)
        return 1
    files = find_chat_history(root)
    if not files:
        print(f"[error] {root} 下没找到 chat_history_*.md", file=sys.stderr)
        return 1

    result = select(files, min_signal=args.min_signal, min_len=args.min_len,
                    max_len=args.max_len, limit=args.limit, per_creator=args.per_creator)
    s = result["stats"]
    print(f"扫描 {s['files']} 文件 / {s['blocks']} 消息块")
    print(f"过滤: 噪声 {s['noise']}  过短 {s['too_short']}  过长 {s['too_long']}  "
          f"信号不足 {s['low_signal']}  重复 {s['dup']}")
    print(f"保留 {s['kept']} 段  按来源: {result['by_creator']}")
    # 周期分布(辅助看 12 格覆盖)
    hor = {"long": 0, "short": 0, "unknown": 0}
    for it in result["items"]:
        hor[it["signals"]["horizon_hint"]] += 1
    print(f"周期启发分布: {hor}")

    if not args.out:
        if result["items"]:
            print("\n=== 候选段样例(首条) ===")
            ex = result["items"][0]
            print(f"[{ex['creator']} {ex['timestamp']}] {ex['evidence_text'][:120]}...")
        print("\n(未指定 --out，仅统计；加 --out 写出 candidates.jsonl)")
        return 0

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        for it in result["items"]:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"\n已写入 {outp}（{s['kept']} 段候选）")
    if s["kept"] < 120:
        print(f"注意: 目标 ≥120 段，当前 {s['kept']}；可调低 --min-signal 或放宽 --max-len。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
