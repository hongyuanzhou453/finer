#!/usr/bin/env python
"""F2 deterministic backfill — build F2-anchored envelopes from F1.

Default scope is ``curated-pdf``: strategy/research/live-transcript PDFs that
have canonical F0 records and F1 ContentEnvelopes. Dry-run is the default; pass
``--write`` only after explicit approval to emit JSON under
``data/F2_anchored/{source_record_id}.json``.

    python scripts/backfill_f2_anchor.py --dry-run
    python scripts/backfill_f2_anchor.py --scope all-local --dry-run
    python scripts/backfill_f2_anchor.py --scope curated-pdf --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from finer.enrichment.entity_anchoring import build_f2_deterministic_envelope  # noqa: E402
from finer.schemas.content import ContentRecord  # noqa: E402
from finer.schemas.content_envelope import ContentEnvelope  # noqa: E402


CURATED_PDF_F0_SOURCE_TYPES = frozenset(
    {"livestream_audio", "research_report", "weekly_strategy"}
)

LOW_HIT_RATE_THRESHOLD = 0.2
THIN_TEXT_CHAR_THRESHOLD = 40
THIN_BLOCK_TEXT_CHAR_THRESHOLD = 8
MAX_GAP_CANDIDATES_PER_ITEM = 5
LOW_HIT_BLOCK_SAMPLE_LIMIT = 3
SOURCE_LEADERBOARD_LIMIT = 10
STDOUT_DIAGNOSTIC_LIMIT = 10
GAP_CANDIDATE_REVIEW_FIELDS = (
    "alias_candidate",
    "source_record_id",
    "block_id",
    "raw_path",
    "context_snippet",
    "reason",
    "candidate_type",
    "score",
    "review_status",
)
_UPPER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,4}(?:\.[A-Z]{1,4})?(?![A-Za-z0-9])")
_CN_CANDIDATE_RE = re.compile(r"[\u4e00-\u9fff]{2,8}")
_NOISY_UPPER_TOKENS = {
    "AI",
    "ADAS",
    "AND",
    "API",
    "APP",
    "ASR",
    "BBG",
    "BPS",
    "BRN0W",
    "CIPS",
    "CAGR",
    "CCL",
    "CEO",
    "CFO",
    "CNBC",
    "CUDA",
    "DDTL",
    "DJT",
    "CPI",
    "CTA",
    "DRAM",
    "ETF",
    "FIFO",
    "FINRA",
    "FILA",
    "FIRE",
    "FSD",
    "GAAP",
    "GDP",
    "GPU",
    "GTC",
    "HBM",
    "HSD",
    "IEA",
    "IDEF",
    "IFRS",
    "IPO",
    "IRR",
    "IP",
    "LABUBU",
    "LTCM",
    "LLM",
    "MOLLY",
    "MORE",
    "NAND",
    "NEW",
    "NOA",
    "OCR",
    "PCB",
    "PDF",
    "PE",
    "PEG",
    "PCE",
    "PROHIBITED",
    "PPI",
    "PSG",
    "PO",
    "PS",
    "PPT",
    "REASONABLE",
    "REGIME",
    "ROE",
    "ROI",
    "RSI",
    "SOFR",
    "SP",
    "TACO",
    "TRUMP",
    "TPU",
    "TV",
    "CN",
    "HK",
    "US",
    "USA",
    "USD",
    "WATCH",
    "I",
    "II",
    "III",
    "IV",
    "V",
    # --- Financial metrics / ratios (a measure, never an investable entity) ---
    "EPS",
    "AUM",
    "ASP",
    "NP",
    "NPM",
    "ER",
    "PB",
    "PIK",
    # --- Time / date tokens (timestamps in KOL screenshots, not entities) ---
    "AM",
    "PM",
    "GMT",
    "UTC",
    # --- Currency codes (consistent with USD above) ---
    "RMB",
    "CNY",
    "HKD",
    "JPY",
    "EUR",
    "GBP",
    # --- Career / desk abbreviations ---
    "IBD",
    # --- Pop Mart IP product lines (consistent with LABUBU / MOLLY) ---
    "DIMOO",
    "PUCKY",
    "YOKI",
    "JELLY",
    "PINO",
    # --- Generic English words / interjections ---
    "JUST",
    "OK",
}
_CN_ENTITY_CUES = (
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
    "光伏",
    "电池",
    "雷达",
    "芯片",
    "聚创",
)
_CN_GENERIC_CANDIDATE_TERMS = (
    "目标",
    "图片",
    "价值",
    "区间",
    "情绪",
    "以上",
    "以下",
    "背景",
    "关键",
    "数据",
    "收入",
    "百万元",
    "占比",
    "提升",
    "提升至",
    "提升到了",
    "去年",
    "方面",
    "一方面",
    "品牌",
    "截止",
    "基于",
    "公开",
    "信息",
    "参考",
    "分析",
    "订单",
    "毛利",
    "产能",
    "业务",
    "公司",
    "策略",
    "操作",
    "风险",
    "来自",
    "分钟",
    "前",
    "转发",
    "评论",
    "保守",
    "止盈",
    "波段",
    "位置",
    "流通",
    "相关股",
    "也继续",
    "产业链",
    "产业的",
    "投资机",
    "总销量",
    "销量",
    "交付量",
    "商店",
    "研究院",
    "金融科技",
    "资产证券",
    "资产证券化",
    "非存款",
    "抵押品",
    "信贷",
    "权重",
    "盘面",
    "补跌",
    "奢侈品",
    "煤炭",
    "主管",
    "报业",
    "活跃",
    "一如既往",
    "企业服",
    "本集团",
    "激光雷达产",
    "非常",
    "点赞",
    "收藏",
    "回复",
    "讨论",
    "最热",
    "最新",
    "最早",
    "下午",
    "猫大人",
    "出货量",
)
_CN_EXACT_GENERIC_CANDIDATE_TERMS = {
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
_BAD_CN_CANDIDATE_PREFIXES = (
    "的",
    "了",
    "和",
    "及",
    "与",
    "在",
    "对",
    "本人",
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
_BAD_CN_CANDIDATE_CONTAINS = (
    "未取得",
    "证券投",
    "破下沿",
    "其他",
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
_BAD_CN_CANDIDATE_SUFFIXES = (
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
    "出货量",
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
_CN_COMPANY_SUFFIX_CUES = (
    "出行",
    "科技",
    "集团",
    "股份",
    "控股",
    "汽车",
    "能源",
    "药业",
    "电子",
    "银行",
    "证券",
    "保险",
    "聚创",
)
_MACRO_OR_NON_FINANCIAL_TERMS = {
    "冲突",
    "战争",
    "地缘",
    "美伊",
    "政策",
    "关税",
    "通胀",
    "降息",
    "非农",
    "会议",
    "教程",
    "工具",
}
_FINANCIAL_CONTEXT_TERMS = (
    "目标价",
    "上市",
    "订单",
    "收入",
    "利润",
    "估值",
    "股价",
    "市值",
    "涨",
    "跌",
    "买",
    "卖",
    "仓",
    "持有",
    "港股",
    "美股",
    "A股",
    "公司",
    "财报",
    "业绩",
    "行业",
)
_MISSED_BLOCK_REASON_ORDER = {
    "registry_gap_candidate": 0,
    "financial_text_no_candidate": 1,
    "non_financial_or_macro": 2,
    "no_financial_context": 3,
    "ocr_thin": 4,
    "empty_text": 5,
}


@dataclass
class PlannedEnvelope:
    """One selected envelope and its generated F2 output."""

    content_id: str
    f1_path: Path
    out_path: Path
    raw_path: str
    source_type: str
    f0_source_type: str
    block_count: int
    hit_block_count: int
    anchor_count: int
    temporal_anchor_count: int
    temporal_evidence_span_count: int
    evidence_span_count: int
    status: str
    envelope: ContentEnvelope


@dataclass
class BackfillPlan:
    """Aggregate dry-run/write plan."""

    scope: str = ""
    scanned: int = 0
    selected: int = 0
    existing: int = 0
    todo: int = 0
    written: int = 0
    skipped_missing_f0: int = 0
    items: list[PlannedEnvelope] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def block_count(self) -> int:
        return sum(i.block_count for i in self.items)

    @property
    def hit_block_count(self) -> int:
        return sum(i.hit_block_count for i in self.items)

    @property
    def anchor_count(self) -> int:
        return sum(i.anchor_count for i in self.items)

    @property
    def temporal_anchor_count(self) -> int:
        return sum(i.temporal_anchor_count for i in self.items)

    @property
    def temporal_evidence_span_count(self) -> int:
        return sum(i.temporal_evidence_span_count for i in self.items)

    @property
    def evidence_span_count(self) -> int:
        return sum(i.evidence_span_count for i in self.items)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_stable(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_jsonl_stable(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in rows
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text((payload + "\n") if payload else "", encoding="utf-8")
    tmp.replace(path)
    return 0 if not payload else payload.count("\n") + 1


def _norm_path(value: str | None) -> str:
    return (value or "").replace("\\", "/")


def _safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _block_to_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json")
    return {}


def load_f0_records(data_root: Path) -> dict[str, ContentRecord]:
    records: dict[str, ContentRecord] = {}
    root = data_root / "F0_intake" / "local"
    for path in sorted(root.rglob("*.json")):
        try:
            record = ContentRecord.model_validate(_read_json(path))
        except Exception:
            continue
        records[record.content_id] = record
    return records


def iter_f1_envelopes(data_root: Path) -> Iterable[tuple[Path, ContentEnvelope]]:
    root = data_root / "F1_standardized"
    for path in sorted(root.glob("*/content_envelope.json")):
        if path.parent.name.startswith("_"):
            continue
        yield path, ContentEnvelope.model_validate(_read_json(path))


def _scope_match(
    envelope: ContentEnvelope,
    scope: str,
    *,
    f0_record: ContentRecord | None,
) -> bool:
    raw_path = _norm_path(envelope.raw_path)
    if scope == "curated-pdf":
        return (
            envelope.source_type == "pdf"
            and f0_record is not None
            and f0_record.source_type in CURATED_PDF_F0_SOURCE_TYPES
        )
    if scope == "all-local":
        return raw_path.startswith("data/")
    raise ValueError(f"unsupported scope: {scope}")


def _item_from_envelope(
    *,
    data_root: Path,
    f1_path: Path,
    envelope: ContentEnvelope,
    f0_records: dict[str, ContentRecord],
    force: bool,
) -> PlannedEnvelope:
    content_id = envelope.source_record_id or f1_path.parent.name
    f0_record = f0_records.get(content_id)
    f2_env = build_f2_deterministic_envelope(envelope, f0_record=f0_record)
    f2_meta = (f2_env.metadata or {}).get("f2_anchor") or {}
    out_path = data_root / "F2_anchored" / f"{content_id}.json"
    status = "todo"
    if out_path.exists() and not force:
        status = "exists"
    return PlannedEnvelope(
        content_id=content_id,
        f1_path=f1_path,
        out_path=out_path,
        raw_path=_norm_path(envelope.raw_path),
        source_type=envelope.source_type,
        f0_source_type=f0_record.source_type if f0_record else "",
        block_count=int(f2_meta.get("total_block_count") or len(f2_env.blocks)),
        hit_block_count=int(f2_meta.get("hit_block_count") or 0),
        anchor_count=int(f2_meta.get("entity_anchor_count") or len(f2_env.entity_anchors)),
        temporal_anchor_count=int(
            f2_meta.get("temporal_anchor_count") or len(f2_env.temporal_anchors)
        ),
        temporal_evidence_span_count=int(f2_meta.get("temporal_evidence_span_count") or 0),
        evidence_span_count=int(f2_meta.get("evidence_span_count") or 0),
        status=status,
        envelope=f2_env,
    )


def plan_backfill(data_root: Path, *, scope: str, force: bool = False) -> BackfillPlan:
    result = BackfillPlan(scope=scope)
    f0_records = load_f0_records(data_root)
    for f1_path, envelope in iter_f1_envelopes(data_root):
        result.scanned += 1
        content_id = envelope.source_record_id or f1_path.parent.name
        f0_record = f0_records.get(content_id)
        if not _scope_match(envelope, scope, f0_record=f0_record):
            continue
        result.selected += 1
        try:
            item = _item_from_envelope(
                data_root=data_root,
                f1_path=f1_path,
                envelope=envelope,
                f0_records=f0_records,
                force=force,
            )
        except Exception as exc:
            result.errors.append(f"{f1_path}: {type(exc).__name__}: {exc}")
            continue
        if not item.f0_source_type:
            result.skipped_missing_f0 += 1
        if item.status == "exists":
            result.existing += 1
        else:
            result.todo += 1
        result.items.append(item)
    return result


def _empty_bucket() -> dict[str, int | float]:
    return {
        "items": 0,
        "blocks": 0,
        "hit_blocks": 0,
        "hit_rate": 0.0,
        "anchors": 0,
        "temporal_anchors": 0,
        "temporal_items": 0,
        "temporal_spans": 0,
        "spans": 0,
        "zero_anchor": 0,
    }


def _bucket_for_items(items: Iterable[PlannedEnvelope]) -> dict[str, int | float]:
    bucket = _empty_bucket()
    for item in items:
        bucket["items"] += 1
        bucket["blocks"] += item.block_count
        bucket["hit_blocks"] += item.hit_block_count
        bucket["anchors"] += item.anchor_count
        bucket["temporal_anchors"] += item.temporal_anchor_count
        if item.temporal_anchor_count:
            bucket["temporal_items"] += 1
        bucket["temporal_spans"] += item.temporal_evidence_span_count
        bucket["spans"] += item.evidence_span_count
        if item.anchor_count == 0:
            bucket["zero_anchor"] += 1
    bucket["hit_rate"] = _safe_rate(int(bucket["hit_blocks"]), int(bucket["blocks"]))
    return bucket


def _group_summary(
    items: Iterable[PlannedEnvelope],
    key_fn,
) -> dict[str, dict[str, int | float]]:
    groups: dict[str, list[PlannedEnvelope]] = defaultdict(list)
    for item in items:
        key = key_fn(item) or "(missing)"
        groups[key].append(item)
    return {
        key: _bucket_for_items(group_items)
        for key, group_items in sorted(groups.items())
    }


def _worst_buckets(
    buckets: dict[str, dict[str, int | float]],
    *,
    limit: int = SOURCE_LEADERBOARD_LIMIT,
) -> list[dict[str, int | float | str]]:
    rows: list[dict[str, int | float | str]] = []
    for key, bucket in buckets.items():
        if int(bucket["blocks"]) == 0:
            continue
        rows.append({"key": key, **bucket})
    rows.sort(
        key=lambda row: (
            float(row["hit_rate"]),
            -int(row["zero_anchor"]),
            -int(row["blocks"]),
            str(row["key"]),
        )
    )
    return rows[:limit]


def _temporal_anchor_to_dict(anchor: Any) -> dict[str, Any]:
    if isinstance(anchor, dict):
        return anchor
    if hasattr(anchor, "model_dump"):
        return anchor.model_dump(mode="json")
    return {}


def _counter_to_sorted_dict(counter: Counter[str]) -> dict[str, int]:
    return {
        key: counter[key]
        for key in sorted(counter)
    }


def _temporal_breakdowns(items: Iterable[PlannedEnvelope]) -> dict[str, dict[str, int]]:
    rules: Counter[str] = Counter()
    strategies: Counter[str] = Counter()
    granularities: Counter[str] = Counter()

    for item in items:
        for anchor in item.envelope.temporal_anchors or []:
            data = _temporal_anchor_to_dict(anchor)
            metadata = data.get("metadata") or {}
            rule = str(metadata.get("rule") or metadata.get("source_field") or "(missing)")
            strategy = str(data.get("resolution_strategy") or "(missing)")
            granularity = str(metadata.get("temporal_granularity") or "instant")
            rules[rule] += 1
            strategies[strategy] += 1
            granularities[granularity] += 1

    return {
        "temporal_rules": _counter_to_sorted_dict(rules),
        "temporal_strategies": _counter_to_sorted_dict(strategies),
        "temporal_granularity": _counter_to_sorted_dict(granularities),
    }


def summarize_plan(plan: BackfillPlan) -> dict[str, Any]:
    """Build aggregate coverage summaries for stdout and JSON reports."""
    by_f0_source_type = _group_summary(plan.items, lambda item: item.f0_source_type)
    by_f1_source_type = _group_summary(plan.items, lambda item: item.source_type)
    return {
        "scope": plan.scope,
        "totals": {
            **_bucket_for_items(plan.items),
            "scanned": plan.scanned,
            "selected": plan.selected,
            "existing": plan.existing,
            "todo": plan.todo,
            "written": plan.written,
            "errors": len(plan.errors),
        },
        **_temporal_breakdowns(plan.items),
        "by_f0_source_type": by_f0_source_type,
        "by_f1_source_type": by_f1_source_type,
        "worst_f0_source_types": _worst_buckets(by_f0_source_type),
        "worst_f1_source_types": _worst_buckets(by_f1_source_type),
        "by_status": _group_summary(
            plan.items,
            lambda item: item.status if item.anchor_count else "zero_anchor",
        ),
    }


def _blocks_without_spans(item: PlannedEnvelope) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in item.envelope.blocks:
        data = _block_to_dict(block)
        if not data:
            continue
        if data.get("evidence_spans"):
            continue
        blocks.append(data)
    return blocks


def _text_stats(item: PlannedEnvelope) -> tuple[int, int]:
    blocks = [_block_to_dict(block) for block in item.envelope.blocks]
    texts = [(block.get("text") or "").strip() for block in blocks if block]
    return sum(len(text) for text in texts), sum(1 for text in texts if text)


def _context_snippet(text: str, needle: str, *, radius: int = 32) -> str:
    if not text:
        return ""
    idx = text.find(needle)
    if idx < 0:
        return text[: radius * 2].strip()
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    return text[start:end].strip()


def _clean_cn_candidate(candidate: str) -> str:
    candidate = candidate.strip(" ，。；：、（）()【】[]《》<>“”\"'0123456789")
    stopwords = (
        "这个",
        "那个",
        "我们",
        "他们",
        "一个",
        "没有",
        "什么",
        "因为",
        "所以",
        "但是",
        "如果",
        "就是",
        "可以",
        "不是",
        "现在",
        "今天",
        "明天",
        "昨天",
    )
    for word in stopwords:
        candidate = candidate.replace(word, "")
    best_end = 0
    for cue in _CN_COMPANY_SUFFIX_CUES:
        start = candidate.find(cue)
        while start >= 0:
            best_end = max(best_end, start + len(cue))
            start = candidate.find(cue, start + 1)
    if best_end:
        candidate = candidate[:best_end]
    return candidate.strip()


def _is_plausible_cn_gap_candidate(candidate: str) -> bool:
    if len(candidate) < 2:
        return False
    if (
        candidate in _CN_EXACT_GENERIC_CANDIDATE_TERMS
        or candidate.startswith(_BAD_CN_CANDIDATE_PREFIXES)
        or candidate.endswith(_BAD_CN_CANDIDATE_SUFFIXES)
        or any(term in candidate for term in _BAD_CN_CANDIDATE_CONTAINS)
    ):
        return False
    if any(term in candidate for term in _CN_GENERIC_CANDIDATE_TERMS):
        return False
    return any(cue in candidate for cue in _CN_ENTITY_CUES)


def _is_noisy_contextual_cn_candidate(alias: str, context: str) -> bool:
    if alias == "美国银行" and any(
        term in context for term in ("对非存款", "非存款金融机构", "私募信贷", "贷款已达")
    ):
        return True
    return False


def _upper_candidate_score(alias: str) -> float:
    score = 0.58
    if "." in alias:
        score += 0.12
    if any(char.isdigit() for char in alias):
        score += 0.08
    return round(min(score, 0.8), 2)


def _cn_candidate_score(alias: str) -> float:
    score = 0.55
    if any(cue in alias for cue in _CN_ENTITY_CUES):
        score += 0.25
    if 2 <= len(alias) <= 4:
        score += 0.05
    if len(alias) > 6:
        score -= 0.05
    return round(max(0.0, min(score, 1.0)), 2)


def _is_noisy_upper_token(alias: str) -> bool:
    return alias in _NOISY_UPPER_TOKENS or alias.startswith("CAGR") or (
        len(alias) == 2 and alias[0].isalpha() and alias[1].isdigit()
    )


def _gap_candidates_for_block(
    item: PlannedEnvelope,
    block: dict[str, Any],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    text = block.get("text") or ""
    block_id = block.get("block_id") or ""
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []

    for match in _UPPER_TOKEN_RE.finditer(text):
        alias = match.group(0)
        if _is_noisy_upper_token(alias) or alias in seen:
            continue
        seen.add(alias)
        candidates.append(
            {
                "alias_candidate": alias,
                "source_record_id": item.content_id,
                "block_id": block_id,
                "raw_path": item.raw_path,
                "context_snippet": _context_snippet(text, alias),
                "reason": reason,
                "candidate_type": "known_format_upper_token",
                "score": _upper_candidate_score(alias),
            }
        )
        if len(candidates) >= MAX_GAP_CANDIDATES_PER_ITEM:
            return candidates

    for match in _CN_CANDIDATE_RE.finditer(text):
        alias = _clean_cn_candidate(match.group(0))
        if not _is_plausible_cn_gap_candidate(alias) or alias in seen:
            continue
        if _is_noisy_contextual_cn_candidate(alias, text):
            continue
        seen.add(alias)
        candidates.append(
            {
                "alias_candidate": alias,
                "source_record_id": item.content_id,
                "block_id": block_id,
                "raw_path": item.raw_path,
                "context_snippet": _context_snippet(text, alias),
                "reason": reason,
                "candidate_type": "cn_entity_phrase",
                "score": _cn_candidate_score(alias),
            }
        )
        if len(candidates) >= MAX_GAP_CANDIDATES_PER_ITEM:
            return candidates
    return candidates


def _has_financial_context(text: str) -> bool:
    return any(term in text for term in _FINANCIAL_CONTEXT_TERMS)


def _missed_block_diagnostic(
    item: PlannedEnvelope,
    block: dict[str, Any],
) -> dict[str, Any]:
    text = (block.get("text") or "").strip()
    candidates: list[dict[str, Any]] = []
    if text:
        candidates = _gap_candidates_for_block(item, block, reason="low_hit_rate")
    has_financial_context = _has_financial_context(text)

    if not text:
        reason = "empty_text"
    elif any(term in text for term in _MACRO_OR_NON_FINANCIAL_TERMS):
        reason = "non_financial_or_macro"
    elif candidates:
        reason = "registry_gap_candidate"
    elif len(text) < THIN_BLOCK_TEXT_CHAR_THRESHOLD:
        reason = "ocr_thin"
    elif has_financial_context:
        reason = "financial_text_no_candidate"
    else:
        reason = "no_financial_context"

    return {
        "block_id": str(block.get("block_id") or ""),
        "reason": reason,
        "text_chars": len(text),
        "has_financial_context": has_financial_context,
        "candidate_count": len(candidates),
        "candidate_aliases": [
            str(candidate["alias_candidate"])
            for candidate in candidates[:MAX_GAP_CANDIDATES_PER_ITEM]
        ],
        "context_snippet": text[:120],
    }


def _missed_block_diagnostics(item: PlannedEnvelope) -> list[dict[str, Any]]:
    diagnostics = [
        _missed_block_diagnostic(item, block)
        for block in _blocks_without_spans(item)
    ]
    diagnostics.sort(
        key=lambda row: (
            _MISSED_BLOCK_REASON_ORDER.get(str(row["reason"]), 99),
            -int(row["text_chars"]),
            str(row["block_id"]),
        )
    )
    return diagnostics


def _zero_anchor_reason(item: PlannedEnvelope) -> str:
    text_chars, nonempty_blocks = _text_stats(item)
    if nonempty_blocks == 0:
        return "empty_text"
    if text_chars < THIN_TEXT_CHAR_THRESHOLD:
        return "ocr_thin"

    joined = "\n".join(
        (_block_to_dict(block).get("text") or "")
        for block in item.envelope.blocks
    )
    if any(term in joined for term in _MACRO_OR_NON_FINANCIAL_TERMS):
        return "non_financial_or_macro"
    return "registry_gap_likely"


def _gap_scan_reason(item: PlannedEnvelope) -> str | None:
    if item.anchor_count == 0:
        zero_reason = _zero_anchor_reason(item)
        return "zero_anchor" if zero_reason == "registry_gap_likely" else None
    if _safe_rate(item.hit_block_count, item.block_count) < LOW_HIT_RATE_THRESHOLD:
        return "low_hit_rate"
    return None


def _low_hit_diagnostics(plan: BackfillPlan) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for item in plan.items:
        if item.anchor_count == 0:
            continue
        hit_rate = _safe_rate(item.hit_block_count, item.block_count)
        if hit_rate >= LOW_HIT_RATE_THRESHOLD:
            continue
        missed_blocks = _missed_block_diagnostics(item)
        missed_reasons = Counter(str(block["reason"]) for block in missed_blocks)
        diagnostics.append(
            {
                "source_record_id": item.content_id,
                "raw_path": item.raw_path,
                "f0_source_type": item.f0_source_type,
                "f1_source_type": item.source_type,
                "block_count": item.block_count,
                "hit_block_count": item.hit_block_count,
                "hit_rate": hit_rate,
                "missed_block_count": max(0, item.block_count - item.hit_block_count),
                "anchors": item.anchor_count,
                "spans": item.evidence_span_count,
                "reason": "low_hit_rate",
                "missed_block_reasons": _counter_to_sorted_dict(missed_reasons),
                "missed_block_samples": missed_blocks[:LOW_HIT_BLOCK_SAMPLE_LIMIT],
            }
        )
    diagnostics.sort(
        key=lambda item: (
            float(item["hit_rate"]),
            -int(item["missed_block_count"]),
            str(item["source_record_id"]),
        )
    )
    return diagnostics


def _low_hit_reason_summary(low_hit_diagnostics: Iterable[dict[str, Any]]) -> dict[str, int]:
    reasons: Counter[str] = Counter()
    for diagnostic in low_hit_diagnostics:
        for reason, count in (diagnostic.get("missed_block_reasons") or {}).items():
            reasons[str(reason)] += int(count)
    return _counter_to_sorted_dict(reasons)


def _low_hit_reason_summary_by(
    low_hit_diagnostics: Iterable[dict[str, Any]],
    *,
    key: str,
) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for diagnostic in low_hit_diagnostics:
        group = str(diagnostic.get(key) or "(missing)")
        for reason, count in (diagnostic.get("missed_block_reasons") or {}).items():
            grouped[group][str(reason)] += int(count)
    return {
        group: _counter_to_sorted_dict(counter)
        for group, counter in sorted(grouped.items())
    }


def build_gap_report(plan: BackfillPlan) -> dict[str, Any]:
    """Build a report of coverage diagnostics and ungrounded alias candidates."""
    summary = summarize_plan(plan)
    diagnostics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    low_hit_diagnostics = _low_hit_diagnostics(plan)

    for item in plan.items:
        if item.anchor_count != 0:
            continue
        reason = _zero_anchor_reason(item)
        text_chars, nonempty_blocks = _text_stats(item)
        diagnostics.append(
            {
                "source_record_id": item.content_id,
                "raw_path": item.raw_path,
                "f0_source_type": item.f0_source_type,
                "f1_source_type": item.source_type,
                "reason": reason,
                "block_count": item.block_count,
                "text_chars": text_chars,
                "nonempty_blocks": nonempty_blocks,
            }
        )

    for item in plan.items:
        reason = _gap_scan_reason(item)
        if reason is None:
            continue
        for block in _blocks_without_spans(item):
            text = block.get("text") or ""
            if reason == "low_hit_rate" and not any(
                term in text for term in _FINANCIAL_CONTEXT_TERMS
            ):
                continue
            for candidate in _gap_candidates_for_block(item, block, reason=reason):
                if _is_noisy_upper_token(candidate["alias_candidate"]):
                    continue
                candidates.append(candidate)
                if len(candidates) >= 200:
                    break
            if len(candidates) >= 200:
                break
        if len(candidates) >= 200:
            break

    return {
        "summary": summary,
        "zero_anchor_diagnostics": diagnostics,
        "low_hit_diagnostics": low_hit_diagnostics,
        "low_hit_reason_summary": _low_hit_reason_summary(low_hit_diagnostics),
        "low_hit_reason_by_f0_source_type": _low_hit_reason_summary_by(
            low_hit_diagnostics,
            key="f0_source_type",
        ),
        "low_hit_reason_by_f1_source_type": _low_hit_reason_summary_by(
            low_hit_diagnostics,
            key="f1_source_type",
        ),
        "gap_candidates": candidates,
        "errors": plan.errors,
    }


def build_gap_candidate_review_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert report candidates into a human-review JSONL shape."""
    rows: list[dict[str, Any]] = []
    for candidate in report.get("gap_candidates") or []:
        row = {
            "alias_candidate": candidate.get("alias_candidate", ""),
            "source_record_id": candidate.get("source_record_id", ""),
            "block_id": candidate.get("block_id", ""),
            "raw_path": candidate.get("raw_path", ""),
            "context_snippet": candidate.get("context_snippet", ""),
            "reason": candidate.get("reason", ""),
            "candidate_type": candidate.get("candidate_type", ""),
            "score": candidate.get("score", 0.0),
            "review_status": "",
        }
        rows.append(row)
    return rows


def write_plan(plan: BackfillPlan) -> None:
    for item in plan.items:
        if item.status == "exists":
            continue
        _write_json_stable(item.out_path, item.envelope.model_dump(mode="json"))
        plan.written += 1


def _print_distribution(title: str, counter: Counter[str]) -> None:
    print(f"{title}:")
    if not counter:
        print("  (none)")
        return
    for key, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key or '(missing)':28s} {count}")


def _print_bucket_table(title: str, buckets: dict[str, dict[str, int | float]]) -> None:
    print(f"{title}:")
    if not buckets:
        print("  (none)")
        return
    print("  key                           items blocks hits  hit_rate anchors time tspans spans zero")
    for key, bucket in sorted(
        buckets.items(),
        key=lambda kv: (-int(kv[1]["items"]), kv[0]),
    ):
        print(
            f"  {key:28s} "
            f"{int(bucket['items']):5d} "
            f"{int(bucket['blocks']):6d} "
            f"{int(bucket['hit_blocks']):4d} "
            f"{float(bucket['hit_rate']):8.1%} "
            f"{int(bucket['anchors']):7d} "
            f"{int(bucket['temporal_anchors']):4d} "
            f"{int(bucket['temporal_spans']):6d} "
            f"{int(bucket['spans']):5d} "
            f"{int(bucket['zero_anchor']):4d}"
        )


def print_plan(plan: BackfillPlan, *, mode: str) -> None:
    report = build_gap_report(plan)
    summary = report["summary"]
    totals = summary["totals"]
    print(f"mode:       {mode}")
    print(f"scope:      {plan.scope}")
    print(f"scanned:    {plan.scanned}")
    print(f"selected:   {plan.selected}")
    print(f"existing:   {plan.existing}")
    print(f"todo:       {plan.todo}")
    if mode == "write":
        print(f"written:    {plan.written}")
    print(f"blocks:     {plan.block_count}")
    print(
        "hit blocks: "
        f"{plan.hit_block_count} "
        f"({plan.hit_block_count / plan.block_count:.1%})"
        if plan.block_count
        else "hit blocks: 0"
    )
    print(f"anchors:    {plan.anchor_count}")
    print(f"temporal:   {plan.temporal_anchor_count}")
    print(f"time spans: {plan.temporal_evidence_span_count}")
    print(f"spans:      {plan.evidence_span_count}")
    print(f"zero items: {int(totals['zero_anchor'])}")
    print()
    _print_distribution("Temporal rules", Counter(summary["temporal_rules"]))
    print()
    _print_distribution("By F0 source_type", Counter(i.f0_source_type for i in plan.items))
    print()
    _print_bucket_table("Coverage by F0 source_type", summary["by_f0_source_type"])
    print()
    _print_bucket_table("Coverage by F1 source_type", summary["by_f1_source_type"])
    print()
    _print_distribution(
        "By status",
        Counter(i.status if i.anchor_count else "zero_anchor" for i in plan.items),
    )
    if report["zero_anchor_diagnostics"]:
        print("\nZero-anchor envelopes:")
        for diag in report["zero_anchor_diagnostics"][:STDOUT_DIAGNOSTIC_LIMIT]:
            print(
                f"  {diag['source_record_id']}  "
                f"{diag['reason']:22s}  "
                f"{diag['raw_path']}"
            )
        remaining = len(report["zero_anchor_diagnostics"]) - STDOUT_DIAGNOSTIC_LIMIT
        if remaining > 0:
            print(f"  ... {remaining} more; use --report-out for full JSON")
    if report["low_hit_diagnostics"]:
        print("\nLow-hit envelopes:")
        for diag in report["low_hit_diagnostics"][:STDOUT_DIAGNOSTIC_LIMIT]:
            print(
                f"  {diag['source_record_id']}  "
                f"{float(diag['hit_rate']):6.1%}  "
                f"missed={diag['missed_block_count']}  "
                f"{diag['raw_path']}"
            )
        print("\nLow-hit missed-block reasons:")
        for reason, count in report["low_hit_reason_summary"].items():
            print(f"  {reason:28s} {count}")
    if report["gap_candidates"]:
        print("\nGap candidate samples:")
        for candidate in report["gap_candidates"][:STDOUT_DIAGNOSTIC_LIMIT]:
            print(
                f"  {candidate['alias_candidate']}  "
                f"{candidate['candidate_type']}  "
                f"{float(candidate['score']):.2f}  "
                f"{candidate['source_record_id']}  "
                f"{candidate['block_id']}  "
                f"{candidate['reason']}"
            )
    if plan.errors:
        print(f"\nERRORS ({len(plan.errors)}):")
        for err in plan.errors[:20]:
            print(f"  {err}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--scope",
        choices=("curated-pdf", "all-local"),
        default="curated-pdf",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only; default mode")
    parser.add_argument("--write", action="store_true", help="Write F2 artifacts")
    parser.add_argument("--force", action="store_true", help="Overwrite existing F2 files")
    parser.add_argument(
        "--report-out",
        type=Path,
        help="Optional JSON report path for coverage diagnostics and gap candidates",
    )
    parser.add_argument(
        "--gap-candidates-out",
        type=Path,
        help="Optional JSONL path for human review of gap candidates",
    )
    args = parser.parse_args()

    if args.dry_run and args.write:
        print("--dry-run and --write are mutually exclusive", file=sys.stderr)
        raise SystemExit(2)

    mode = "write" if args.write else "dry-run"
    plan = plan_backfill(args.data_root, scope=args.scope, force=args.force)
    if args.write:
        write_plan(plan)
    print_plan(plan, mode=mode)
    report = build_gap_report(plan)
    if args.report_out:
        _write_json_stable(args.report_out, report)
        print(f"\nreport:     {args.report_out}")
    if args.gap_candidates_out:
        rows = build_gap_candidate_review_rows(report)
        row_count = _write_jsonl_stable(args.gap_candidates_out, rows)
        print(f"\ngap review: {args.gap_candidates_out} ({row_count} rows)")

    if plan.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
