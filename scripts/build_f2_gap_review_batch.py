#!/usr/bin/env python
"""Build a deduplicated human-review batch from F2 gap candidates."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PREFERRED_CANDIDATE_TYPES = {
    "cn_entity_phrase": 0,
    "known_format_upper_token": 1,
}
MAX_SUPPORTING_EXAMPLES = 3
FORBIDDEN_OUTPUT_KEYS = {"ticker", "market", "entity_id"}
GENERIC_ALIAS_TERMS = {
    "科技企业",
    "集团总计",
    "集团整体",
    "本集团",
    "金融科技",
    "能源",
    "集团",
    "港股科技",
    "算力的资产证券",
    "银行",
    "保险",
    "证券",
    "科技",
    "电子",
    "半导体",
    "半导体设备",
    "机器人",
    "汽车",
}
BAD_ALIAS_PREFIXES = (
    "的",
    "了",
    "和",
    "及",
    "与",
    "在",
    "对",
    "冲",
    "反弹",
    "买",
    "卖",
    "个",
    "促进",
    "一如",
    "应用",
    "品及",
    "乃根据",
    "中概",
    "据",
    "石油",
)
BAD_ALIAS_CONTAINS = (
    "和",
    "以及",
    "或者",
    "出货量",
    "品牌",
    "相关股",
    "产业的",
    "产业链",
    "投资机",
    "也都",
    "充裕",
    "拥有",
    "盘面",
    "补跌",
    "一直",
    "科技和",
    "科技权重",
    "也继续",
    "对非存款",
    "抵押品",
    "收紧信贷",
    "奢侈品",
    "煤炭",
    "报业",
    "主管",
    "连续个",
    "车载",
    "研究院",
    "交付量",
    "资产证券",
    "资产证券化",
    "更活跃",
    "一如既往",
    "本集团",
    "应用的",
    "用于",
    "乃根据",
    "企业服",
    "机器人及",
    "激光雷达产",
    "主激光雷达",
    "净利润",
    "剔除",
    "注销",
    "回购",
    "同比",
    "环比",
)
BAD_ALIAS_SUFFIXES = (
    "需要",
    "走势",
    "回补",
    "下沿",
    "本质上",
    "企业",
    "指数",
    "总计",
    "整体",
    "继续",
    "总销量",
    "销量",
    "商店",
    "过去",
    "出",
    "产",
    "初",
    "于",
    "可",
    "拖",
    "少",
    "交",
    "服",
    "机",
    "股",
    "都",
    "和",
    "及",
)
STRONG_ALIAS_SUFFIXES = (
    "出行",
    "科技",
    "集团",
    "股份",
    "控股",
    "汽车",
    "能源",
    "药业",
    "电子",
    "半导体",
    "机器人",
    "银行",
    "证券",
    "保险",
    "聚创",
)


@dataclass
class ReviewBatchPlan:
    candidates_in: Path
    scanned: int
    skipped_existing_registry_gaps: int
    unique_aliases: int
    selected: int
    rows: list[dict[str, Any]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            count += 1
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return count


def _alias_key(row: dict[str, Any]) -> str:
    return str(row.get("alias_candidate") or "").strip().casefold()


def _existing_registry_gap_aliases(dpo_dir: Path | None) -> set[str]:
    if dpo_dir is None:
        return set()
    path = dpo_dir / "registry_gaps.jsonl"
    if not path.exists():
        return set()

    aliases: set[str] = set()
    for row in _read_jsonl(path):
        alias = str(row.get("alias") or row.get("alias_candidate") or "").strip().casefold()
        if alias:
            aliases.add(alias)
    return aliases


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, float, int, str, str]:
    candidate_type = str(row.get("candidate_type") or "")
    type_rank = PREFERRED_CANDIDATE_TYPES.get(candidate_type, 99)
    score = float(row.get("score") or 0.0)
    alias = str(row.get("alias_candidate") or "")
    context = str(row.get("context_snippet") or "")
    return (type_rank, -score, -len(context), alias, str(row.get("source_record_id") or ""))


def _markdown_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text


def _is_reviewable_alias(row: dict[str, Any]) -> bool:
    alias = str(row.get("alias_candidate") or "").strip()
    if not alias or alias in GENERIC_ALIAS_TERMS:
        return False
    context = str(row.get("context_snippet") or "")
    if alias == "美国银行" and any(
        term in context for term in ("对非存款", "非存款金融机构", "私募信贷", "贷款已达")
    ):
        return False
    if alias.startswith(BAD_ALIAS_PREFIXES) or alias.endswith(BAD_ALIAS_SUFFIXES):
        return False
    if any(term in alias for term in BAD_ALIAS_CONTAINS):
        return False
    if row.get("candidate_type") == "cn_entity_phrase":
        if not (3 <= len(alias) <= 8):
            return False
        return alias.endswith(STRONG_ALIAS_SUFFIXES)
    return True


def _supporting_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for row in sorted(rows, key=_candidate_sort_key)[:MAX_SUPPORTING_EXAMPLES]:
        examples.append(
            {
                "source_record_id": str(row.get("source_record_id") or "").strip(),
                "block_id": str(row.get("block_id") or "").strip(),
                "raw_path": str(row.get("raw_path") or "").strip(),
                "context_snippet": str(row.get("context_snippet") or "").strip(),
                "reason": str(row.get("reason") or "").strip(),
                "score": float(row.get("score") or 0.0),
            }
        )
    return examples


def _clean_review_row(
    row: dict[str, Any],
    *,
    support_count: int,
    supporting_examples: list[dict[str, Any]],
) -> dict[str, Any]:
    cleaned = {
        "alias_candidate": str(row.get("alias_candidate") or "").strip(),
        "source_record_id": str(row.get("source_record_id") or "").strip(),
        "block_id": str(row.get("block_id") or "").strip(),
        "raw_path": str(row.get("raw_path") or "").strip(),
        "context_snippet": str(row.get("context_snippet") or "").strip(),
        "reason": str(row.get("reason") or "").strip(),
        "candidate_type": str(row.get("candidate_type") or "").strip(),
        "score": float(row.get("score") or 0.0),
        "support_count": support_count,
        "supporting_examples": supporting_examples,
        "review_status": "",
    }
    for key in FORBIDDEN_OUTPUT_KEYS:
        cleaned.pop(key, None)
    return cleaned


def build_review_batch(
    candidates_in: Path,
    *,
    limit: int = 50,
    include_upper_tokens: bool = False,
    dpo_dir: Path | None = None,
) -> ReviewBatchPlan:
    rows = _read_jsonl(candidates_in)
    existing_registry_gap_aliases = _existing_registry_gap_aliases(dpo_dir)
    skipped_existing = 0
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        alias = _alias_key(row)
        if not alias:
            continue
        if alias in existing_registry_gap_aliases:
            skipped_existing += 1
            continue
        if not include_upper_tokens and row.get("candidate_type") == "known_format_upper_token":
            continue
        if not _is_reviewable_alias(row):
            continue
        grouped.setdefault(alias, []).append(row)

    selected: list[dict[str, Any]] = []
    for alias_rows in grouped.values():
        sorted_rows = sorted(alias_rows, key=_candidate_sort_key)
        best = sorted_rows[0]
        selected.append(
            _clean_review_row(
                best,
                support_count=len(alias_rows),
                supporting_examples=_supporting_examples(sorted_rows),
            )
        )
    selected.sort(key=_candidate_sort_key)

    return ReviewBatchPlan(
        candidates_in=candidates_in,
        scanned=len(rows),
        skipped_existing_registry_gaps=skipped_existing,
        unique_aliases=len(grouped),
        selected=min(limit, len(selected)),
        rows=selected[:limit],
    )


def write_markdown_review(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# F2 Gap Candidate Review Batch",
        "",
        "| Alias | Type | Score | Support | Review | Source | Context |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row.get("alias_candidate")),
                    _markdown_cell(row.get("candidate_type")),
                    f"{float(row.get('score') or 0.0):.2f}",
                    str(int(row.get("support_count") or 0)),
                    "",
                    _markdown_cell(row.get("source_record_id")),
                    _markdown_cell(row.get("context_snippet")),
                ]
            )
            + " |"
        )
        for example in row.get("supporting_examples") or []:
            lines.append(
                f"<!-- support {row.get('alias_candidate')}: "
                f"{_markdown_cell(example.get('source_record_id'))} "
                f"{_markdown_cell(example.get('block_id'))} "
                f"{_markdown_cell(example.get('raw_path'))} "
                f"{_markdown_cell(example.get('context_snippet'))} -->"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_plan(plan: ReviewBatchPlan, *, out: Path | None) -> None:
    print(f"candidates: {plan.candidates_in}")
    print(f"scanned:    {plan.scanned}")
    print(f"existing:   {plan.skipped_existing_registry_gaps}")
    print(f"unique:     {plan.unique_aliases}")
    print(f"selected:   {plan.selected}")
    if out:
        print(f"out:        {out}")
    if plan.rows:
        print("\nReview batch sample:")
        for row in plan.rows[:20]:
            print(
                f"  {row['alias_candidate']}  "
                f"{row['candidate_type']}  "
                f"score={row['score']:.2f}  "
                f"support={row['support_count']}  "
                f"{row['source_record_id']}"
            )
        remaining = len(plan.rows) - 20
        if remaining > 0:
            print(f"  ... {remaining} more")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-in", type=Path, required=True)
    parser.add_argument(
        "--dpo-dir",
        type=Path,
        help="Optional DPO dir; skips candidates already present in registry_gaps.jsonl",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--include-upper-tokens",
        action="store_true",
        help="Include upper-case token candidates; default keeps Chinese entity phrases only",
    )
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")

    plan = build_review_batch(
        args.candidates_in,
        limit=args.limit,
        include_upper_tokens=args.include_upper_tokens,
        dpo_dir=args.dpo_dir,
    )
    if args.out:
        _write_jsonl(args.out, plan.rows)
    if args.markdown_out:
        write_markdown_review(args.markdown_out, plan.rows)
    _print_plan(plan, out=args.out)
    if args.markdown_out:
        print(f"markdown:   {args.markdown_out}")


if __name__ == "__main__":
    main()
