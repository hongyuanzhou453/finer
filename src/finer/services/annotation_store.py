"""Annotation store — JSONL-backed annotation workbench storage and quality gates."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import ValidationError

from finer.paths import DATA_ROOT, REPO_ROOT
from finer.schemas.annotation import (
    ACCEPTED_SCHEMA_VERSIONS,
    ANNOTATION_SCHEMA_VERSION,
    AnnotationExportMode,
    AnnotationItemStatus,
    AnnotationQualityStatus,
    AnnotationTaskId,
    AnnotationTaskSummary,
    EvalGoldAnnotation,
    PairReviewAnnotation,
    utc_now,
)
from finer.services.annotation_validation import validate_extraction_json

_EVIDENCE_RE = re.compile(r"## 原文\n(.*?)\n\n## 提取要求", re.S)
_BLOCK_RE = re.compile(r"^###\s+\[([^\]]+)\]\s+(\S+)\s+\(([^)]+)\)\s*$", re.MULTILINE)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_IMAGE_MARKER = "[Image:"

_DIRECTION_WORDS = [
    "买入", "卖出", "加仓", "减仓", "看多", "看空", "支撑", "压力", "目标价",
    "止损", "止盈", "建仓", "入场", "埋伏", "超跌", "反弹", "减持", "增持",
    "风险", "回调", "突破", "跌破", "抄底", "逢低", "高位",
]
_HORIZON_LONG = ["长期", "长线", "年", "2026", "2027", "趋势", "确定性", "基本面"]
_HORIZON_SHORT = ["短期", "短线", "今天", "明天", "本周", "这周", "盘", "日内", "近期"]
_TICKER_RE = re.compile(r"[A-Z]{2,5}\b|\d{4,6}\.(?:HK|SH|SZ)|港股|A股|美股")
_PRICE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:元|美元|港币|港元|块)|"
    r"\d+(?:\.\d+)?\s*[-~]\s*\d+(?:\.\d+)?|PE|倍|亿"
)
_NOISE_MARKERS = [
    "DASHSCOPE_API_KEY", "fetch failed", "empty data", "merge_forward",
    "[Merged forward", "Error:", "fetch_failed",
]

DEFAULT_PAIR_SAMPLE_SIZE = 30
DEFAULT_PAIR_SAMPLE_SEED = 20260610
DEFAULT_EVAL_LIMIT = 30
DEFAULT_EVAL_SEED = 20260610
DEFAULT_EVAL_MIN_SIGNAL = 2
DEFAULT_EVAL_MIN_LEN = 40
DEFAULT_EVAL_MAX_LEN = 1200
MIN_FORMAL_EVAL_GOLD = 20

_EVAL_SOURCE_FIX_HINT = "请在页面的「任务准备」中重建 held-out 评测集。"
_PAIRS_SOURCE_FIX_HINT = (
    "偏好对任务源缺失。先完成 harvest："
    ".venv/bin/python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl "
    "--out data/dpo/pairs.jsonl --model qwen3-8b"
)

_TASK_TITLES: Dict[str, str] = {
    "eval_gold": "评测集 Gold 标注",
    "pairs_review": "DPO 偏好对抽检",
}


@dataclass
class JsonlReport:
    path: Path
    rows: List[Dict[str, Any]] = field(default_factory=list)
    bad_lines: List[Dict[str, Any]] = field(default_factory=list)
    invalid_rows: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def bad_count(self) -> int:
        return len(self.bad_lines) + len(self.invalid_rows)


def _read_jsonl_report(path: Path) -> JsonlReport:
    report = JsonlReport(path=path)
    if not path.exists():
        return report
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                report.bad_lines.append({"line": line_no, "error": str(exc)})
                continue
            if not isinstance(obj, dict):
                report.invalid_rows.append({"line": line_no, "error": "JSON 行必须是对象"})
                continue
            report.rows.append(obj)
    return report


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _as_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def _clean_text(raw: str) -> str:
    text = _HTML_RE.sub("", raw)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = _WS_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _split_blocks(text: str) -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []
    matches = list(_BLOCK_RE.finditer(text))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = _clean_text(text[start:end])
        blocks.append(
            {
                "timestamp": match.group(1),
                "creator_raw": match.group(2),
                "kind": match.group(3),
                "content": content,
            }
        )
    return blocks


def _signal_of(text: str) -> Dict[str, Any]:
    has_dir = any(word in text for word in _DIRECTION_WORDS)
    has_price = bool(_PRICE_RE.search(text))
    has_ticker = bool(_TICKER_RE.search(text))
    long_hits = sum(text.count(word) for word in _HORIZON_LONG)
    short_hits = sum(text.count(word) for word in _HORIZON_SHORT)
    horizon = "long" if long_hits > short_hits else ("short" if short_hits > long_hits else "unknown")
    return {
        "has_direction": has_dir,
        "has_price": has_price,
        "has_ticker": has_ticker,
        "horizon_hint": horizon,
        "signal_score": int(has_dir) + int(has_price) + int(has_ticker),
    }


def _is_noise(text: str) -> bool:
    return (not text) or any(marker in text for marker in _NOISE_MARKERS)


def _creator_of(path: Path) -> str:
    parts = path.parts
    for seg in ("maodaren", "9you"):
        if seg in parts or seg in path.name:
            return seg
    if "9友" in path.name or "9友" in str(path) or "20269" in path.name:
        return "9you"
    if "猫大人" in path.name:
        return "maodaren"
    return "unknown"


def _content_hash(text: str) -> str:
    norm = re.sub(r"\s+", "", text)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _find_chat_history(root: Path) -> List[Path]:
    return sorted(root.rglob("chat_history_*.md"))


def evidence_from_prompt(prompt: str) -> str:
    """Extract evidence text from a DPO prompt; fall back to the full prompt."""
    if not isinstance(prompt, str):
        return ""
    match = _EVIDENCE_RE.search(prompt)
    return match.group(1).strip() if match else prompt


def _merge_context(evidence_text: str, context_blocks: Any) -> str:
    """按 offset 顺序把并入的上下文块拼进证据文本（评测输入与标注者所见一致）。"""
    if not isinstance(context_blocks, list) or not context_blocks:
        return evidence_text
    valid = [
        b for b in context_blocks
        if isinstance(b, dict) and isinstance(b.get("offset"), int) and b.get("content")
    ]
    before = [b["content"] for b in sorted(valid, key=lambda b: b["offset"]) if b["offset"] < 0]
    after = [b["content"] for b in sorted(valid, key=lambda b: b["offset"]) if b["offset"] > 0]
    return "\n".join([*before, evidence_text, *after])


KOL_NOTE_CATEGORIES = frozenset({"style", "discipline", "preference", "track_record"})

_SLUG_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-一-鿿]")


def _safe_slug(value: str) -> str:
    """Sanitize creator slug for use as a filename (no path traversal)."""
    return _SLUG_SAFE_RE.sub("_", value.strip()) or "unknown"


class AnnotationStore:
    """File-backed annotation task storage. ``dpo_dir`` is injectable for tests."""

    def __init__(
        self,
        dpo_dir: Optional[Path] = None,
        kol_notes_dir: Optional[Path] = None,
        pairs_source_name: Optional[str] = None,
        full_pair_review_required: Optional[bool] = None,
    ) -> None:
        env_dpo_dir = os.environ.get("FINER_ANNOTATION_DPO_DIR")
        self.dpo_dir = dpo_dir or (_as_repo_path(env_dpo_dir) if env_dpo_dir else (DATA_ROOT / "dpo"))
        self.kol_notes_dir = kol_notes_dir or (DATA_ROOT / "kol_profiles" / "notes")
        self.pairs_source_name = pairs_source_name or os.environ.get(
            "FINER_ANNOTATION_PAIRS_SOURCE", "pairs.jsonl"
        )
        if full_pair_review_required is None:
            full_pair_review_required = os.environ.get("FINER_ANNOTATION_FULL_PAIR_REVIEW") == "1"
        self.full_pair_review_required = full_pair_review_required

    @property
    def eval_source(self) -> Path:
        return self.dpo_dir / "eval" / "passages.jsonl"

    @property
    def eval_annotations(self) -> Path:
        return self.dpo_dir / "eval" / "annotations.jsonl"

    @property
    def eval_export(self) -> Path:
        return self.dpo_dir / "eval" / "eval_set.jsonl"

    @property
    def eval_manifest(self) -> Path:
        return self.dpo_dir / "eval" / "manifest.json"

    @property
    def eval_drafts(self) -> Path:
        """模型初稿 sidecar（run_inference 跑 passages 产出 {id, output}），仅标注辅助。"""
        return self.dpo_dir / "eval" / "drafts.jsonl"

    @property
    def registry_gaps(self) -> Path:
        return self.dpo_dir / "registry_gaps.jsonl"

    @property
    def pairs_source(self) -> Path:
        return self.dpo_dir / self.pairs_source_name

    @property
    def pairs_annotations(self) -> Path:
        return self.dpo_dir / "pairs_review.jsonl"

    @property
    def pairs_export(self) -> Path:
        return self.dpo_dir / "pairs_cleaned.jsonl"

    # ---------------------------------------------------------------- source
    def _source_report(self, task_id: AnnotationTaskId) -> JsonlReport:
        report = _read_jsonl_report(self.eval_source if task_id == "eval_gold" else self.pairs_source)
        valid_rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(report.rows):
            if task_id == "eval_gold":
                if isinstance(row.get("id"), str) and isinstance(row.get("evidence_text"), str):
                    valid_rows.append(row)
                else:
                    report.invalid_rows.append({"line": idx + 1, "error": "缺少 id 或 evidence_text"})
            else:
                if all(isinstance(row.get(k), str) for k in ("prompt", "chosen", "rejected")):
                    meta = row.get("meta") or {}
                    pair_id = meta.get("passage_id") or f"pair_{idx:04d}"
                    valid_rows.append({**row, "pair_id": pair_id})
                else:
                    report.invalid_rows.append({"line": idx + 1, "error": "缺少 prompt/chosen/rejected"})
        report.rows = valid_rows
        return report

    def _annotation_report(self, task_id: AnnotationTaskId) -> JsonlReport:
        return _read_jsonl_report(
            self.eval_annotations if task_id == "eval_gold" else self.pairs_annotations
        )

    def _eval_source_rows(self) -> List[Dict[str, Any]]:
        return self._source_report("eval_gold").rows

    def _pairs_source_rows(self) -> List[Dict[str, Any]]:
        return self._source_report("pairs_review").rows

    def _train_ids(self) -> set[str]:
        ids: set[str] = set()
        for row in self._pairs_source_rows():
            passage_id = (row.get("meta") or {}).get("passage_id")
            if isinstance(passage_id, str) and passage_id:
                ids.add(passage_id)
        return ids

    # ------------------------------------------------------------ annotations
    def load_annotations(self, task_id: AnnotationTaskId) -> Dict[str, Dict[str, Any]]:
        """Read annotations as a last-wins merged view. Invalid rows are reported elsewhere."""
        key = "id" if task_id == "eval_gold" else "pair_id"
        merged: Dict[str, Dict[str, Any]] = {}
        for row in self._annotation_report(task_id).rows:
            value = row.get(key)
            if isinstance(value, str) and value:
                merged[value] = row
        return merged

    def _annotation_status(self, task_id: AnnotationTaskId, ann: Optional[Dict[str, Any]]) -> AnnotationItemStatus:
        if not ann:
            return "pending"
        if task_id == "eval_gold" and ann.get("sample_verdict") == "exclude":
            return "excluded"
        return "annotated"

    def _sample_pair_rows(
        self,
        rows: List[Dict[str, Any]],
        sample_size: Optional[int],
        seed: Optional[int],
    ) -> List[Dict[str, Any]]:
        if not sample_size or sample_size <= 0 or sample_size >= len(rows):
            return rows
        rng = random.Random(seed if seed is not None else DEFAULT_PAIR_SAMPLE_SEED)
        indexes = rng.sample(range(len(rows)), sample_size)
        return [rows[i] for i in indexes]

    def list_items(
        self,
        task_id: AnnotationTaskId,
        *,
        status: Optional[AnnotationItemStatus] = None,
        sample_size: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        annotations = self.load_annotations(task_id)
        items: List[Dict[str, Any]] = []
        if task_id == "eval_gold":
            drafts = self._eval_drafts_map()
            source_rows = self._eval_source_rows()
            for row in source_rows:
                ann = annotations.get(row["id"])
                item_status = self._annotation_status(task_id, ann)
                if status and item_status != status:
                    continue
                items.append(
                    {
                        "id": row["id"],
                        "evidence_text": row["evidence_text"],
                        "creator": row.get("creator"),
                        "source_file": row.get("source_file"),
                        "timestamp": row.get("timestamp"),
                        "signals": row.get("signals"),
                        "char_len": row.get("char_len"),
                        "status": item_status,
                        "annotation": ann,
                        "draft": drafts.get(row["id"]),
                    }
                )
        else:
            # full-review 模式返回全量、忽略 sample_size（与 _pairs_quality 一致）。
            # 修复: 前端无条件传 sample_size 曾把 full 模式降级为抽样，导致只能审 30 条。
            if self.full_pair_review_required:
                source_rows = self._pairs_source_rows()
            else:
                source_rows = self._sample_pair_rows(self._pairs_source_rows(), sample_size, seed)
            for row in source_rows:
                ann = annotations.get(row["pair_id"])
                item_status = self._annotation_status(task_id, ann)
                if status and item_status != status:
                    continue
                meta = row.get("meta") or {}
                items.append(
                    {
                        "pair_id": row["pair_id"],
                        "evidence_text": evidence_from_prompt(row["prompt"]),
                        "chosen": row["chosen"],
                        "rejected": row["rejected"],
                        "creator": meta.get("creator"),
                        "source_file": meta.get("source_file"),
                        "status": item_status,
                        "annotation": ann,
                    }
                )
        return items

    def _eval_drafts_map(self) -> Dict[str, str]:
        """模型初稿 {id: output}；文件缺失或行损坏时静默忽略（纯辅助数据）。"""
        drafts: Dict[str, str] = {}
        for row in _read_jsonl_report(self.eval_drafts).rows:
            draft_id, output = row.get("id"), row.get("output")
            if isinstance(draft_id, str) and isinstance(output, str):
                drafts[draft_id] = output
        return drafts

    # --------------------------------------------------------------- context
    def context(self, item_id: str, *, before: int = 5, after: int = 5) -> Dict[str, Any]:
        """返回 eval 段落在源 chat_history 文件中的邻近消息块。

        定位优先级：内容 hash（id 即 psg_{hash}）→ 块头 timestamp。
        """
        row = next((r for r in self._eval_source_rows() if r["id"] == item_id), None)
        if row is None:
            raise KeyError(f"id {item_id!r} 不在任务源 {_rel(self.eval_source)} 中")
        source_file = row.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            raise FileNotFoundError(f"段落 {item_id} 缺少 source_file，无法定位上下文")
        path = _as_repo_path(source_file)
        if not path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_file}")

        blocks = _split_blocks(path.read_text(encoding="utf-8", errors="ignore"))
        target_hash = item_id.removeprefix("psg_")
        idx = next(
            (i for i, b in enumerate(blocks) if _content_hash(b["content"]) == target_hash),
            None,
        )
        if idx is None:
            ts = row.get("timestamp")
            idx = next((i for i, b in enumerate(blocks) if b["timestamp"] == ts), None)
        if idx is None:
            raise ValueError(f"无法在 {source_file} 中定位段落 {item_id}（源文件可能已变更）")

        out: List[Dict[str, Any]] = []
        for i in range(max(0, idx - before), min(len(blocks), idx + after + 1)):
            out.append(
                {
                    "position": "self" if i == idx else ("before" if i < idx else "after"),
                    "offset": i - idx,
                    "timestamp": blocks[i]["timestamp"],
                    "content": blocks[i]["content"],
                }
            )
        return {
            "item_id": item_id,
            "source_file": source_file,
            "block_index": idx,
            "total_blocks": len(blocks),
            "blocks": out,
        }

    # -------------------------------------------------------------- sidecars
    def append_registry_gap(
        self,
        *,
        alias: str,
        suggested_ticker: str = "",
        market: str = "",
        item_id: str = "",
        reviewer_id: str,
    ) -> Dict[str, Any]:
        """实体库缺口候补（人工 review 后才进 entity_registry，标注端不直写 registry）。"""
        alias = alias.strip()
        if not alias:
            raise ValueError("alias 不能为空")
        record = {
            "alias": alias,
            "suggested_ticker": suggested_ticker.strip().upper(),
            "market": market.strip().upper(),
            "item_id": item_id,
            "reviewer_id": reviewer_id.strip(),
            "created_at": utc_now().isoformat(),
        }
        _append_jsonl(self.registry_gaps, record)
        total = len(_read_jsonl_report(self.registry_gaps).rows)
        return {"path": _rel(self.registry_gaps), "total": total}

    def append_kol_note(
        self,
        *,
        creator: str,
        category: str,
        text: str,
        source_item_id: str = "",
        source_file: str = "",
        reviewer_id: str,
    ) -> Dict[str, Any]:
        """KOL 风格速记，追加 data/kol_profiles/notes/{creator}.jsonl（append-only）。"""
        creator = creator.strip()
        if not creator:
            raise ValueError("creator 不能为空")
        if category not in KOL_NOTE_CATEGORIES:
            raise ValueError(f"category 必须属于 {sorted(KOL_NOTE_CATEGORIES)}")
        if not text.strip():
            raise ValueError("text 不能为空")
        path = self.kol_notes_dir / f"{_safe_slug(creator)}.jsonl"
        record = {
            "creator": creator,
            "category": category,
            "text": text.strip(),
            "source_item_id": source_item_id,
            "source_file": source_file,
            "reviewer_id": reviewer_id.strip(),
            "created_at": utc_now().isoformat(),
        }
        _append_jsonl(path, record)
        total = len(_read_jsonl_report(path).rows)
        return {"path": _rel(path), "creator": creator, "total_for_creator": total}

    # ---------------------------------------------------------------- submit
    def submit(self, task_id: AnnotationTaskId, annotation: Dict[str, Any]) -> Dict[str, Any]:
        if task_id == "eval_gold":
            model = EvalGoldAnnotation.model_validate(annotation)
            if model.annotation_schema_version != ANNOTATION_SCHEMA_VERSION:
                raise ValueError(
                    f"新提交必须使用当前 schema 版本 {ANNOTATION_SCHEMA_VERSION}"
                    f"（收到 {model.annotation_schema_version}）"
                )
            known = {row["id"] for row in self._eval_source_rows()}
            if model.id not in known:
                raise KeyError(f"id {model.id!r} 不在任务源 {_rel(self.eval_source)} 中")
            _append_jsonl(self.eval_annotations, model.model_dump(mode="json"))
        else:
            model = PairReviewAnnotation.model_validate(annotation)
            if model.annotation_schema_version != ANNOTATION_SCHEMA_VERSION:
                raise ValueError(
                    f"新提交必须使用当前 schema 版本 {ANNOTATION_SCHEMA_VERSION}"
                    f"（收到 {model.annotation_schema_version}）"
                )
            known = {row["pair_id"] for row in self._pairs_source_rows()}
            if model.pair_id not in known:
                raise KeyError(f"pair_id {model.pair_id!r} 不在任务源 {_rel(self.pairs_source)} 中")
            _append_jsonl(self.pairs_annotations, model.model_dump(mode="json"))
        return self.task_summary(task_id).model_dump(mode="json")

    # ------------------------------------------------------------- eval build
    def rebuild_eval_source(
        self,
        *,
        src: str = "data",
        limit: int = DEFAULT_EVAL_LIMIT,
        seed: int = DEFAULT_EVAL_SEED,
        min_signal: int = DEFAULT_EVAL_MIN_SIGNAL,
        min_len: int = DEFAULT_EVAL_MIN_LEN,
        max_len: int = DEFAULT_EVAL_MAX_LEN,
        exclude_image_placeholders: bool = True,
    ) -> Dict[str, Any]:
        root = _as_repo_path(src)
        if not root.exists():
            raise FileNotFoundError(f"源目录不存在: {_rel(root)}")
        files = _find_chat_history(root)
        if not files:
            raise FileNotFoundError(f"{_rel(root)} 下没找到 chat_history_*.md")

        train_ids = self._train_ids()
        seen_hashes: set[str] = set()
        pool: List[Dict[str, Any]] = []
        stats = {
            "files": len(files),
            "blocks": 0,
            "noise": 0,
            "too_short": 0,
            "too_long": 0,
            "low_signal": 0,
            "dup": 0,
            "train_overlap_excluded": 0,
            "image_placeholder_excluded": 0,
            "pool": 0,
            "selected": 0,
        }

        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            creator = _creator_of(path)
            for block in _split_blocks(text):
                stats["blocks"] += 1
                content = block["content"]
                if _is_noise(content):
                    stats["noise"] += 1
                    continue
                if exclude_image_placeholders and _IMAGE_MARKER in content:
                    stats["image_placeholder_excluded"] += 1
                    continue
                if len(content) < min_len:
                    stats["too_short"] += 1
                    continue
                if len(content) > max_len:
                    stats["too_long"] += 1
                    continue
                signals = _signal_of(content)
                if signals["signal_score"] < min_signal:
                    stats["low_signal"] += 1
                    continue
                h = _content_hash(content)
                passage_id = f"psg_{h}"
                if passage_id in train_ids:
                    stats["train_overlap_excluded"] += 1
                    continue
                if h in seen_hashes:
                    stats["dup"] += 1
                    continue
                seen_hashes.add(h)
                pool.append(
                    {
                        "id": passage_id,
                        "source_file": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
                        "creator": creator,
                        "timestamp": block["timestamp"],
                        "evidence_text": content,
                        "char_len": len(content),
                        "signals": signals,
                    }
                )

        stats["pool"] = len(pool)
        rng = random.Random(seed)
        if limit and limit < len(pool):
            selected = rng.sample(pool, limit)
        else:
            selected = list(pool)
        selected.sort(key=lambda row: row["id"])
        stats["selected"] = len(selected)

        _write_jsonl(self.eval_source, selected)
        manifest = {
            "manifest_id": f"eval_source_{utc_now().strftime('%Y%m%dT%H%M%SZ')}",
            "created_at": utc_now().astimezone(timezone.utc).isoformat(),
            "source_root": _rel(root),
            "output_path": _rel(self.eval_source),
            "params": {
                "limit": limit,
                "seed": seed,
                "min_signal": min_signal,
                "min_len": min_len,
                "max_len": max_len,
                "exclude_image_placeholders": exclude_image_placeholders,
            },
            "stats": stats,
            "train_ids_excluded_from": _rel(self.pairs_source),
            "annotations_preserved": True,
        }
        self.eval_manifest.parent.mkdir(parents=True, exist_ok=True)
        self.eval_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "source_path": _rel(self.eval_source),
            "manifest_path": _rel(self.eval_manifest),
            "selected": len(selected),
            "stats": stats,
            "manifest": manifest,
        }

    # --------------------------------------------------------------- quality
    def _legacy_missing_reviewer(self, rows: Iterable[Dict[str, Any]]) -> int:
        return sum(
            1
            for row in rows
            if not row.get("reviewer_id")
            or row.get("annotation_schema_version") not in ACCEPTED_SCHEMA_VERSIONS
        )

    def _invalid_annotations(self, task_id: AnnotationTaskId, rows: Iterable[Dict[str, Any]]) -> int:
        invalid = 0
        for row in rows:
            try:
                if task_id == "eval_gold":
                    EvalGoldAnnotation.model_validate(row)
                else:
                    PairReviewAnnotation.model_validate(row)
            except ValidationError:
                invalid += 1
        return invalid

    def _eval_quality(self) -> AnnotationQualityStatus:
        source_report = self._source_report("eval_gold")
        ann_report = self._annotation_report("eval_gold")
        annotations = self.load_annotations("eval_gold")
        source_ids = {row["id"] for row in source_report.rows}
        annotation_ids = {
            row.get("id") for row in ann_report.rows if isinstance(row.get("id"), str)
        }
        overlap = sorted(source_ids & self._train_ids())

        image_count = 0
        weak_count = 0
        unexcluded_image = 0
        unexcluded_weak = 0
        incomplete = 0
        excluded = 0
        effective_gold = 0
        invalid = self._invalid_annotations("eval_gold", ann_report.rows)
        legacy = self._legacy_missing_reviewer(ann_report.rows)

        for row in source_report.rows:
            has_image = _IMAGE_MARKER in row.get("evidence_text", "")
            weak = (row.get("signals") or {}).get("signal_score", 0) < DEFAULT_EVAL_MIN_SIGNAL
            image_count += int(has_image)
            weak_count += int(weak)
            ann = annotations.get(row["id"])
            if not ann:
                incomplete += 1
                continue
            if ann.get("sample_verdict") == "exclude":
                excluded += 1
                continue
            effective_gold += 1
            unexcluded_image += int(has_image)
            unexcluded_weak += int(weak)

        manifest = None
        if self.eval_manifest.exists():
            try:
                manifest = json.loads(self.eval_manifest.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest = None

        quality = AnnotationQualityStatus(
            bad_source_lines=source_report.bad_count,
            bad_annotation_lines=ann_report.bad_count,
            dangling_annotations=len(annotation_ids - source_ids),
            legacy_missing_reviewer=legacy,
            invalid_annotations=invalid,
            train_eval_overlap_ids=overlap,
            image_placeholder_items=image_count,
            weak_signal_items=weak_count,
            unexcluded_image_placeholder_items=unexcluded_image,
            unexcluded_weak_signal_items=unexcluded_weak,
            incomplete_items=incomplete,
            excluded_items=excluded,
            effective_gold_items=effective_gold,
            manifest_path=_rel(self.eval_manifest) if self.eval_manifest.exists() else None,
            manifest=manifest if isinstance(manifest, dict) else None,
        )
        quality.formal_blocking_reasons = self._eval_formal_blockers(quality, bool(source_report.rows))
        return quality

    def _pairs_quality(self) -> AnnotationQualityStatus:
        source_report = self._source_report("pairs_review")
        ann_report = self._annotation_report("pairs_review")
        annotations = self.load_annotations("pairs_review")
        source_ids = {row["pair_id"] for row in source_report.rows}
        annotation_ids = {
            row.get("pair_id") for row in ann_report.rows if isinstance(row.get("pair_id"), str)
        }
        sampled_rows = source_report.rows if self.full_pair_review_required else self._sample_pair_rows(
            source_report.rows,
            DEFAULT_PAIR_SAMPLE_SIZE,
            DEFAULT_PAIR_SAMPLE_SEED,
        )
        sample_ids = {row["pair_id"] for row in sampled_rows}
        reviewed_sample = sum(1 for pair_id in sample_ids if pair_id in annotations)

        quality = AnnotationQualityStatus(
            bad_source_lines=source_report.bad_count,
            bad_annotation_lines=ann_report.bad_count,
            dangling_annotations=len(annotation_ids - source_ids),
            legacy_missing_reviewer=self._legacy_missing_reviewer(ann_report.rows),
            invalid_annotations=self._invalid_annotations("pairs_review", ann_report.rows),
            incomplete_items=max(0, len(sample_ids) - reviewed_sample),
            pair_sample_size=len(sample_ids),
            pair_sample_reviewed=reviewed_sample,
        )
        quality.formal_blocking_reasons = self._pairs_formal_blockers(quality, bool(source_report.rows))
        return quality

    def _eval_formal_blockers(self, q: AnnotationQualityStatus, ready: bool) -> List[str]:
        reasons: List[str] = []
        if not ready:
            reasons.append("评测集任务源为空，请先重建任务源")
        if q.bad_source_lines:
            reasons.append(f"任务源有 {q.bad_source_lines} 行 JSONL/结构错误")
        if q.bad_annotation_lines:
            reasons.append(f"标注文件有 {q.bad_annotation_lines} 行 JSONL/结构错误")
        if q.dangling_annotations:
            reasons.append(f"存在 {q.dangling_annotations} 条悬空标注，请刷新或重建后重新标注")
        if q.legacy_missing_reviewer:
            reasons.append(f"存在 {q.legacy_missing_reviewer} 条旧标注缺少 reviewer_id 或 schema version")
        if q.invalid_annotations:
            reasons.append(f"存在 {q.invalid_annotations} 条不符合当前 schema 的标注")
        if q.train_eval_overlap_ids:
            reasons.append(f"训练/评测 id 重叠 {len(q.train_eval_overlap_ids)} 条")
        if q.incomplete_items:
            reasons.append(f"还有 {q.incomplete_items} 条样本未标 gold 或排除")
        if q.unexcluded_image_placeholder_items:
            reasons.append(f"还有 {q.unexcluded_image_placeholder_items} 条图片占位样本未排除")
        if q.unexcluded_weak_signal_items:
            reasons.append(f"还有 {q.unexcluded_weak_signal_items} 条弱信号样本未排除")
        if q.effective_gold_items < MIN_FORMAL_EVAL_GOLD:
            reasons.append(f"有效 gold 样本少于 {MIN_FORMAL_EVAL_GOLD} 条")
        return reasons

    def _pairs_formal_blockers(self, q: AnnotationQualityStatus, ready: bool) -> List[str]:
        reasons: List[str] = []
        if not ready:
            reasons.append("偏好对任务源为空，请先生成 pairs.jsonl")
        if q.bad_source_lines:
            reasons.append(f"偏好对任务源有 {q.bad_source_lines} 行 JSONL/结构错误")
        if q.bad_annotation_lines:
            reasons.append(f"抽检标注文件有 {q.bad_annotation_lines} 行 JSONL/结构错误")
        if q.dangling_annotations:
            reasons.append(f"存在 {q.dangling_annotations} 条悬空抽检标注")
        if q.legacy_missing_reviewer:
            reasons.append(f"存在 {q.legacy_missing_reviewer} 条旧抽检缺少 reviewer_id 或 schema version")
        if q.invalid_annotations:
            reasons.append(f"存在 {q.invalid_annotations} 条不符合当前 schema 的抽检标注")
        if q.incomplete_items:
            label = "全量审核队列" if self.full_pair_review_required else "默认抽样队列"
            reasons.append(f"{label} {q.pair_sample_reviewed}/{q.pair_sample_size}，尚未完成抽检")
        return reasons

    def task_summary(self, task_id: AnnotationTaskId) -> AnnotationTaskSummary:
        if task_id == "eval_gold":
            source, ann_path, export = self.eval_source, self.eval_annotations, self.eval_export
            rows = self._eval_source_rows()
            quality = self._eval_quality()
            fix_hint = _EVAL_SOURCE_FIX_HINT
        else:
            source, ann_path, export = self.pairs_source, self.pairs_annotations, self.pairs_export
            rows = self._pairs_source_rows()
            quality = self._pairs_quality()
            fix_hint = _PAIRS_SOURCE_FIX_HINT
        annotations = self.load_annotations(task_id)
        annotated = sum(1 for row in rows if self._annotation_status(task_id, annotations.get(row.get("id") or row.get("pair_id"))) != "pending")
        ready = len(rows) > 0
        return AnnotationTaskSummary(
            task_id=task_id,
            title=_TASK_TITLES[task_id],
            source_path=_rel(source),
            annotations_path=_rel(ann_path),
            export_path=_rel(export),
            ready=ready,
            total=len(rows),
            annotated=annotated,
            fix_hint=None if ready else fix_hint,
            quality=quality,
        )

    def task_summaries(self) -> List[AnnotationTaskSummary]:
        return [self.task_summary("eval_gold"), self.task_summary("pairs_review")]

    # ---------------------------------------------------------------- export
    def _assert_export_allowed(self, task_id: AnnotationTaskId, mode: AnnotationExportMode) -> None:
        if mode == "draft":
            return
        summary = self.task_summary(task_id)
        blockers = summary.quality.formal_blocking_reasons
        if blockers:
            raise ValueError("formal export 被阻断: " + "；".join(blockers))

    def export_eval_set(self, mode: AnnotationExportMode = "formal") -> Dict[str, Any]:
        self._assert_export_allowed("eval_gold", mode)
        annotations = self.load_annotations("eval_gold")
        source_rows = {row["id"]: row for row in self._eval_source_rows()}
        exported: List[Dict[str, Any]] = []
        excluded = 0
        for ann_id, ann in annotations.items():
            src = source_rows.get(ann_id)
            if src is None:
                continue
            if ann.get("sample_verdict") == "exclude":
                excluded += 1
                continue
            if mode == "draft":
                try:
                    EvalGoldAnnotation.model_validate(ann)
                except ValidationError:
                    continue
            gold = ann.get("gold")
            evidence_text = _merge_context(src["evidence_text"], ann.get("context_blocks"))
            exported.append(
                {
                    "id": ann_id,
                    "evidence_text": evidence_text,
                    "expected_abstain": bool(ann.get("expected_abstain")),
                    "gold": gold,
                    "alt_golds": ann.get("alt_golds") or [],
                    "meta": {
                        "creator": src.get("creator"),
                        "source_file": src.get("source_file"),
                        "reviewer_id": ann.get("reviewer_id"),
                        "annotated_at": ann.get("annotated_at"),
                        "notes": ann.get("notes"),
                        "annotation_schema_version": ann.get("annotation_schema_version"),
                        "context_blocks_merged": len(ann.get("context_blocks") or []),
                    },
                }
            )
        exported.sort(key=lambda row: row["id"])
        _write_jsonl(self.eval_export, exported)
        abstain = sum(1 for row in exported if row["expected_abstain"])
        return {
            "export_path": _rel(self.eval_export),
            "exported": len(exported),
            "excluded": excluded,
            "expected_abstain_count": abstain,
            "train_eval_overlap_ids": sorted({row["id"] for row in exported} & self._train_ids()),
            "mode": mode,
        }

    def export_pairs_cleaned(self, mode: AnnotationExportMode = "formal") -> Dict[str, Any]:
        self._assert_export_allowed("pairs_review", mode)
        annotations = self.load_annotations("pairs_review")
        kept: List[Dict[str, Any]] = []
        counts = {"accept": 0, "edit": 0, "reject": 0, "unreviewed": 0}
        sampled_ids = {
            row["pair_id"]
            for row in (
                self._pairs_source_rows()
                if self.full_pair_review_required
                else self._sample_pair_rows(
                    self._pairs_source_rows(), DEFAULT_PAIR_SAMPLE_SIZE, DEFAULT_PAIR_SAMPLE_SEED
                )
            )
        }
        for row in self._pairs_source_rows():
            ann = annotations.get(row["pair_id"])
            verdict = (ann or {}).get("verdict")
            if mode == "draft" and ann:
                try:
                    PairReviewAnnotation.model_validate(ann)
                except ValidationError:
                    ann = None
                    verdict = None
            if verdict == "reject":
                counts["reject"] += 1
                continue
            out = {key: row[key] for key in ("prompt", "chosen", "rejected")}
            out["meta"] = dict(row.get("meta") or {})
            if verdict == "edit":
                out["chosen"] = ann["edited_chosen"]
                out["meta"]["review_verdict"] = "edit"
                out["meta"]["reviewer_id"] = ann.get("reviewer_id")
                counts["edit"] += 1
            elif verdict == "accept":
                out["meta"]["review_verdict"] = "accept"
                out["meta"]["reviewer_id"] = ann.get("reviewer_id")
                counts["accept"] += 1
            else:
                counts["unreviewed"] += 1
            if out["chosen"] == out["rejected"]:
                counts["reject"] += 1
                continue
            if row["pair_id"] in sampled_ids:
                out["meta"]["review_sampled"] = True
            kept.append(out)
        _write_jsonl(self.pairs_export, kept)
        return {
            "export_path": _rel(self.pairs_export),
            "exported": len(kept),
            "sample_size": len(sampled_ids),
            "mode": mode,
            **counts,
        }

    def export(self, task_id: AnnotationTaskId, mode: AnnotationExportMode = "formal") -> Dict[str, Any]:
        if task_id == "eval_gold":
            return self.export_eval_set(mode)
        return self.export_pairs_cleaned(mode)

    # ---------------------------------------------------------------- enums
    def enums(self) -> Dict[str, Any]:
        from finer.entity_registry import ENTITY_REGISTRY
        from finer.schemas.trade_action import ActionType, TradeDirection

        entity_aliases: Dict[str, Dict[str, str]] = {}
        for alias, (ticker, market, _etype) in ENTITY_REGISTRY.items():
            entity_aliases[alias] = {"ticker": ticker, "market": market}

        return {
            "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
            "directions": [item.value for item in TradeDirection],
            "action_types": [item.value for item in ActionType],
            "eval_exclude_reasons": [
                "image_placeholder",
                "insufficient_context",
                "non_investment",
                "duplicate",
                "other",
            ],
            "pair_sample_size": (
                len(self._pairs_source_rows())
                if self.full_pair_review_required
                else DEFAULT_PAIR_SAMPLE_SIZE
            ),
            "pair_sample_seed": DEFAULT_PAIR_SAMPLE_SEED,
            "entity_aliases": entity_aliases,
        }
