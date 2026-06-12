#!/usr/bin/env python3
"""Select a stratified high-quality candidate pool for DPO HQ v1.

This script only reads real chat-history text and writes candidate metadata. It
does not call paid APIs, does not generate chosen/rejected pairs, and does not
touch the legacy data/dpo/pairs.jsonl or data/dpo/data.jsonl files.

Default output:
  data/dpo/hq_v1/source_candidates.jsonl
  data/dpo/hq_v1/source_candidates_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


BLOCK_RE = re.compile(r"^###\s+\[([^\]]+)\]\s+(\S+)\s+\(([^)]+)\)\s*$", re.MULTILINE)
HTML_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t]+")
TICKER_RE = re.compile(r"\$?[A-Z]{2,5}\b|\d{4,6}\.(?:HK|SH|SZ)|\b\d{6}\b")
# 严格标的代码：A股6位(可带 .SH/.SZ/.BJ) 或 港股4-5位.HK。刻意排除裸 [A-Z]{2,5}
# （链接/英文词易误命中，是飞书闲聊混入候选的根因）。用于 groundable_entity_hits。
STRICT_CODE_RE = re.compile(r"\b\d{6}(?:\.(?:SH|SZ|BJ))?\b|\b\d{4,5}\.HK\b")
PRICE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:元|美元|港币|港元|块)|"
    r"\d+(?:\.\d+)?\s*[-~]\s*\d+(?:\.\d+)?|PE|倍|亿|%"
)

BULLISH_WORDS = [
    "买入", "买", "加仓", "建仓", "入场", "埋伏", "看多", "逢低", "抄底",
    "突破", "反弹", "增持", "修复空间", "上限", "弹性", "配置",
]
BEARISH_WORDS = [
    "卖出", "减仓", "看空", "止损", "跌破", "高位", "回避", "避开",
    "风险", "不碰", "撤", "先走", "谨慎",
]
ABSTAIN_WORDS = [
    "观望", "不好预判", "不太好预判", "不确定", "没明确", "没什么机会",
    "看不清", "等一等", "注意风险", "不好说", "证据不足", "先不",
]
MULTI_HINT_WORDS = ["同时", "另外", "相比", "和", "与", "以及", "都", "分别"]
LONG_WORDS = ["长期", "长线", "年", "2026", "2027", "趋势", "确定性", "基本面"]
SHORT_WORDS = ["短期", "短线", "今天", "明天", "本周", "这周", "盘", "日内", "近期"]
NOISE_MARKERS = [
    "DASHSCOPE_API_KEY", "fetch failed", "empty data", "merge_forward",
    "[Merged forward", "Error:", "fetch_failed", "[Image:",
]

DEFAULT_QUOTAS = {
    "bullish_action": 70,
    "bearish_risk": 45,
    "abstain": 55,
    "multi_context": 50,
}


def clean_text(raw: str) -> str:
    text = HTML_RE.sub("", raw)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = WS_RE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def split_blocks(text: str) -> List[Dict[str, str]]:
    matches = list(BLOCK_RE.finditer(text))
    blocks: List[Dict[str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(
            {
                "timestamp": match.group(1),
                "creator_raw": match.group(2),
                "kind": match.group(3),
                "content": clean_text(text[start:end]),
            }
        )
    return blocks


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


def load_exclude_ids(paths: Sequence[Path]) -> Set[str]:
    ids: Set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row_id = row.get("id") or (row.get("meta") or {}).get("passage_id")
                if isinstance(row_id, str) and row_id:
                    ids.add(row_id)
    return ids


def entity_hits(text: str) -> List[str]:
    hits = {m.group(0).lstrip("$").upper() for m in TICKER_RE.finditer(text)}
    try:
        from finer.entity_registry import ENTITY_REGISTRY
    except Exception:
        ENTITY_REGISTRY = {}
    for alias, entry in ENTITY_REGISTRY.items():
        if len(alias) >= 2 and alias in text:
            hits.add(str(entry[0]).upper())
    return sorted(hits)


def _groundable_key(ticker: str) -> str:
    ticker = (ticker or "").strip().upper().lstrip("$")
    if "." not in ticker:
        return ticker.lstrip("0") or ticker
    head, _, tail = ticker.partition(".")
    # A-share registry aliases may include .SH/.SZ while source text often has bare 6 digits.
    if len(head) == 6 and tail in {"SH", "SZ", "BJ"}:
        return head.lstrip("0") or head
    return f"{head.lstrip('0') or head}.{tail}"


def groundable_entity_hits(text: str) -> List[str]:
    """强标的信号：entity_registry 中文别名命中 + 严格代码格式（STRICT_CODE_RE）。

    刻意排除裸 [A-Z]{2,5}（TICKER_RE 会把飞书链接 feishu.cn/docx/X26ud… 里的英文串
    误当 ticker，导致闲聊混入候选）。用于 ① 纯闲聊硬过滤 ② committal 必须有可锚标的。
    """
    hits_by_key = {_groundable_key(m.group(0)): m.group(0).upper() for m in STRICT_CODE_RE.finditer(text)}
    try:
        from finer.entity_registry import ENTITY_REGISTRY
    except Exception:
        ENTITY_REGISTRY = {}
    for alias, entry in ENTITY_REGISTRY.items():
        if len(alias) >= 2 and alias in text:
            ticker = str(entry[0]).upper()
            hits_by_key.setdefault(_groundable_key(ticker), ticker)
    return sorted(hits_by_key.values())


def count_words(text: str, words: Iterable[str]) -> int:
    return sum(text.count(word) for word in words)


def horizon_hint(text: str) -> str:
    long_hits = count_words(text, LONG_WORDS)
    short_hits = count_words(text, SHORT_WORDS)
    if long_hits > short_hits:
        return "long"
    if short_hits > long_hits:
        return "short"
    return "unknown"


def classify(text: str) -> Tuple[str, Dict[str, Any]]:
    bullish = count_words(text, BULLISH_WORDS)
    bearish = count_words(text, BEARISH_WORDS)
    abstain = count_words(text, ABSTAIN_WORDS)
    multi_hint = count_words(text, MULTI_HINT_WORDS)
    entities = entity_hits(text)
    groundable = groundable_entity_hits(text)  # 强标的信号（排除裸字母误命中）
    has_price = bool(PRICE_RE.search(text))
    # has_multi 用 groundable 而非 entities：避免链接里的英文串凑成"多标的"误判 multi_context
    has_multi = len(groundable) >= 2 or (len(groundable) >= 1 and multi_hint >= 2)

    if has_multi:
        category = "multi_context"
    elif bearish > 0 and bearish >= bullish:
        category = "bearish_risk"
    elif bullish > 0:
        category = "bullish_action"
    elif abstain > 0:
        category = "abstain"
    else:
        category = "abstain"

    # 根因2：committal 类别必须有可锚标的；无强标的的方向观点降级 abstain
    # （保留为观望训练样本，避免下游 harvest 对无标的内容硬配/幻觉 ticker）。
    if category in ("bullish_action", "bearish_risk", "multi_context") and not groundable:
        category = "abstain"

    signal_score = int(bullish > 0 or bearish > 0) + int(has_price) + int(bool(entities))
    score = (
        signal_score * 20
        + min(len(entities), 4) * 8
        + min(bullish + bearish + abstain, 6) * 4
        + int(has_price) * 6
        + int(horizon_hint(text) != "unknown") * 4
        + int(has_multi) * 8
    )
    return category, {
        "bullish_hits": bullish,
        "bearish_hits": bearish,
        "abstain_hits": abstain,
        "multi_hint_hits": multi_hint,
        "has_price": has_price,
        "entity_hits": entities,
        "groundable_hits": groundable,
        "horizon_hint": horizon_hint(text),
        "signal_score": signal_score,
        "hq_score": score,
    }


def is_noise(text: str, *, min_len: int, max_len: int) -> bool:
    return (
        not text
        or len(text) < min_len
        or len(text) > max_len
        or any(marker in text for marker in NOISE_MARKERS)
    )


def find_chat_files(root: Path) -> List[Path]:
    return sorted(root.rglob("chat_history_*.md"))


def collect_candidates(
    src: Path,
    *,
    min_len: int,
    max_len: int,
    exclude_ids: Set[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    files = find_chat_files(src)
    seen_hashes: Set[str] = set()
    rows: List[Dict[str, Any]] = []
    stats = Counter(files=len(files), blocks=0, noise=0, duplicate=0, excluded_id=0)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        creator = creator_of(path)
        for block in split_blocks(text):
            stats["blocks"] += 1
            content = block["content"]
            if is_noise(content, min_len=min_len, max_len=max_len):
                stats["noise"] += 1
                continue
            h = content_hash(content)
            passage_id = f"psg_{h}"
            if h in seen_hashes:
                stats["duplicate"] += 1
                continue
            if passage_id in exclude_ids:
                stats["excluded_id"] += 1
                continue
            category, signals = classify(content)
            # 纯闲聊/无效硬过滤：无强标的 + 无价格 + 无任何多空/观望信号
            # （飞书文档分享、小龙虾闲聊等：旧逻辑因链接英文串误命中 entity 而漏过）。
            if (
                not signals["groundable_hits"]
                and not signals["has_price"]
                and signals["bullish_hits"] == 0
                and signals["bearish_hits"] == 0
                and signals["abstain_hits"] == 0
            ):
                stats["noise"] += 1
                continue
            seen_hashes.add(h)
            rows.append(
                {
                    "id": passage_id,
                    "source_file": str(path),
                    "creator": creator,
                    "timestamp": block["timestamp"],
                    "evidence_text": content,
                    "char_len": len(content),
                    "signals": signals,
                    "hq_category": category,
                }
            )
    stats["pool"] = len(rows)
    return rows, dict(stats)


def stratified_select(
    rows: List[Dict[str, Any]],
    *,
    quotas: Dict[str, int],
    limit: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row = dict(row)
        row["_tie"] = rng.random()
        by_category[row["hq_category"]].append(row)
    for bucket in by_category.values():
        bucket.sort(key=lambda r: (-int((r.get("signals") or {}).get("hq_score", 0)), r["_tie"]))

    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()
    for category, quota in quotas.items():
        for row in by_category.get(category, [])[:quota]:
            selected.append(row)
            selected_ids.add(row["id"])

    if len(selected) < limit:
        remainder = [row for row in rows if row["id"] not in selected_ids]
        remainder.sort(key=lambda r: (-int((r.get("signals") or {}).get("hq_score", 0)), r["id"]))
        for row in remainder[: limit - len(selected)]:
            selected.append(row)

    selected = selected[:limit]
    selected.sort(key=lambda r: (r["hq_category"], -int((r.get("signals") or {}).get("hq_score", 0)), r["id"]))
    for row in selected:
        row.pop("_tie", None)
    return selected


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select stratified real-text candidates for DPO HQ v1",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--src", default="data", help="Root to search for chat_history_*.md")
    parser.add_argument("--out", default="data/dpo/hq_v1/source_candidates.jsonl")
    parser.add_argument("--manifest", default="data/dpo/hq_v1/source_candidates_manifest.json")
    parser.add_argument("--limit", type=int, default=220)
    parser.add_argument("--seed", type=int, default=20260611)
    parser.add_argument("--min-len", type=int, default=40)
    parser.add_argument("--max-len", type=int, default=1600)
    parser.add_argument("--exclude", action="append", default=[
        "data/dpo/eval/passages.jsonl",
        "data/dpo/eval/eval_set.jsonl",
    ], help="JSONL files whose id/meta.passage_id should be excluded")
    parser.add_argument("--quota-bullish", type=int, default=DEFAULT_QUOTAS["bullish_action"])
    parser.add_argument("--quota-bearish", type=int, default=DEFAULT_QUOTAS["bearish_risk"])
    parser.add_argument("--quota-abstain", type=int, default=DEFAULT_QUOTAS["abstain"])
    parser.add_argument("--quota-multi", type=int, default=DEFAULT_QUOTAS["multi_context"])
    args = parser.parse_args()

    src = Path(args.src)
    if not src.exists():
        raise SystemExit(f"[error] source root does not exist: {src}")

    exclude_paths = [Path(p) for p in args.exclude]
    exclude_ids = load_exclude_ids(exclude_paths)
    quotas = {
        "bullish_action": args.quota_bullish,
        "bearish_risk": args.quota_bearish,
        "abstain": args.quota_abstain,
        "multi_context": args.quota_multi,
    }
    pool, stats = collect_candidates(
        src,
        min_len=args.min_len,
        max_len=args.max_len,
        exclude_ids=exclude_ids,
    )
    selected = stratified_select(pool, quotas=quotas, limit=args.limit, seed=args.seed)

    out = Path(args.out)
    manifest_path = Path(args.manifest)
    write_jsonl(out, selected)

    category_counts = Counter(row["hq_category"] for row in selected)
    creator_counts = Counter(row.get("creator", "unknown") for row in selected)
    manifest = {
        "manifest_id": f"dpo_hq_candidates_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(src),
        "output_path": str(out),
        "params": {
            "limit": args.limit,
            "seed": args.seed,
            "min_len": args.min_len,
            "max_len": args.max_len,
            "quotas": quotas,
            "exclude": [str(p) for p in exclude_paths],
        },
        "stats": stats,
        "excluded_ids_loaded": len(exclude_ids),
        "selected": len(selected),
        "category_counts": dict(category_counts),
        "creator_counts": dict(creator_counts),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"scanned_files={stats.get('files', 0)} pool={stats.get('pool', 0)} selected={len(selected)}")
    print(f"category_counts={dict(category_counts)}")
    print(f"creator_counts={dict(creator_counts)}")
    print(f"wrote {out}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
