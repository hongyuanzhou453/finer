"""Tests for scripts/backfill_f2_anchor.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.backfill_f2_anchor import (
    build_gap_candidate_review_rows,
    build_gap_report,
    plan_backfill,
    summarize_plan,
    write_plan,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _quality() -> dict:
    return {
        "readability_score": 0.9,
        "semantic_completeness_score": 0.9,
        "financial_relevance_score": 0.8,
        "entity_resolution_score": 0.0,
        "temporal_resolution_score": 0.0,
        "evidence_traceability_score": 0.8,
    }


def _block(block_id: str, text: str, *, order_index: int = 0) -> dict:
    return {
        "block_id": block_id,
        "block_type": "paragraph",
        "text": text,
        "order_index": order_index,
        "page_index": 0,
        "quality": {
            "readability": 0.9,
            "extraction_confidence": 0.9,
            "structural_confidence": 0.8,
            "completeness": 1.0,
            "noise_score": 0.1,
            "quality_flags": [],
        },
        "provenance": {
            "raw_path": "data/raw/sample.pdf",
            "extractor": "test",
            "extractor_version": "1.0",
        },
    }


def _f0_record(content_id: str, raw_path: str, source_type: str = "livestream_audio") -> dict:
    return {
        "content_id": content_id,
        "source_type": source_type,
        "source_platform": "local",
        "creator_id": "trader_ji",
        "creator_name": "trader_ji",
        "raw_path": raw_path,
        "file_type": "pdf",
    }


def _f1_envelope(
    content_id: str,
    raw_path: str,
    text: str | list[str] = "腾讯和NVDA",
    published_at: str | None = "2026-06-13T09:30:00+08:00",
) -> dict:
    texts = [text] if isinstance(text, str) else text
    return {
        "envelope_id": f"env_{content_id}",
        "source_record_id": content_id,
        "schema_version": "v1.0",
        "source_type": "pdf",
        "standardization_profile": "pdf_layout_v1",
        "source_uri": raw_path,
        "source_title": Path(raw_path).name,
        "raw_path": raw_path,
        "creator_name": "trader_ji",
        "published_at": published_at,
        "ingested_at": "2026-06-14T00:00:00",
        "blocks": [
            _block(f"b{index + 1}", block_text, order_index=index)
            for index, block_text in enumerate(texts)
        ],
        "quality_card": _quality(),
        "metadata": {},
    }


def _seed_pair(
    data_root: Path,
    content_id: str,
    raw_path: str,
    *,
    f0_source_type: str = "livestream_audio",
    f1_source_type: str = "pdf",
    text: str | list[str] = "腾讯和NVDA",
) -> None:
    f1_payload = _f1_envelope(content_id, raw_path, text=text)
    f1_payload["source_type"] = f1_source_type
    _write_json(
        data_root / "F0_intake" / "local" / "trader_ji" / f"{content_id}.json",
        _f0_record(content_id, raw_path, source_type=f0_source_type),
    )
    _write_json(
        data_root / "F1_standardized" / content_id / "content_envelope.json",
        f1_payload,
    )


def test_plan_backfill_dry_run_writes_nothing(tmp_path: Path):
    _seed_pair(tmp_path, "local_test", "data/raw/trader/sample.pdf")

    plan = plan_backfill(tmp_path, scope="curated-pdf")

    assert plan.scanned == 1
    assert plan.selected == 1
    assert plan.todo == 1
    assert plan.existing == 0
    assert plan.block_count == 1
    assert plan.hit_block_count == 1
    assert plan.anchor_count == 2
    assert plan.temporal_anchor_count == 1
    assert plan.temporal_evidence_span_count == 0
    assert not (tmp_path / "F2_anchored" / "local_test.json").exists()


def test_write_plan_is_idempotent_and_skips_existing(tmp_path: Path):
    _seed_pair(tmp_path, "local_test", "data/raw/trader/sample.pdf")

    first = plan_backfill(tmp_path, scope="curated-pdf")
    write_plan(first)
    out = tmp_path / "F2_anchored" / "local_test.json"
    before = out.read_bytes()

    second = plan_backfill(tmp_path, scope="curated-pdf")
    assert second.todo == 0
    assert second.existing == 1
    write_plan(second)
    after = out.read_bytes()

    assert first.written == 1
    assert second.written == 0
    assert before == after


def test_force_rewrites_same_bytes(tmp_path: Path):
    _seed_pair(tmp_path, "local_test", "data/raw/trader/sample.pdf")
    first = plan_backfill(tmp_path, scope="curated-pdf")
    write_plan(first)
    out = tmp_path / "F2_anchored" / "local_test.json"
    before = out.read_bytes()

    forced = plan_backfill(tmp_path, scope="curated-pdf", force=True)
    assert forced.todo == 1
    assert forced.existing == 0
    write_plan(forced)

    assert out.read_bytes() == before


def test_scope_curated_pdf_excludes_non_curated_envelope(tmp_path: Path):
    _seed_pair(tmp_path, "local_curated", "data/raw/trader/strategy.pdf")
    _seed_pair(
        tmp_path,
        "local_unclassified",
        "data/raw/trader/random.pdf",
        f0_source_type="unclassified",
    )
    _seed_pair(
        tmp_path,
        "local_image",
        "data/raw/trader/screenshot.png",
        f1_source_type="image",
    )

    plan = plan_backfill(tmp_path, scope="curated-pdf")

    assert plan.selected == 1
    assert [item.content_id for item in plan.items] == ["local_curated"]


def test_f0_source_type_is_carried_to_f2_metadata(tmp_path: Path):
    _seed_pair(tmp_path, "local_test", "data/raw/trader/sample.pdf")

    plan = plan_backfill(tmp_path, scope="curated-pdf")
    write_plan(plan)
    payload = json.loads(
        (tmp_path / "F2_anchored" / "local_test.json").read_text(encoding="utf-8")
    )

    assert payload["source_type"] == "pdf"
    assert payload["metadata"]["f0_source_type"] == "livestream_audio"
    assert payload["entity_anchors"]
    assert payload["temporal_anchors"]
    assert payload["temporal_anchors"][0]["anchor_type"] == "published_at"
    assert payload["metadata"]["f2_anchor"]["temporal_anchor_count"] == 1
    assert payload["metadata"]["f2_anchor"]["temporal_evidence_span_count"] == 0
    assert payload["blocks"][0]["evidence_spans"]


def test_summarize_plan_groups_coverage_by_source_type(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_pdf",
        "data/raw/trader/strategy.pdf",
        f0_source_type="livestream_audio",
        text="腾讯和NVDA，今天复盘。",
    )
    _seed_pair(
        tmp_path,
        "local_image",
        "data/raw/trader/chart.png",
        f0_source_type="unclassified",
        f1_source_type="image",
        text="星河出行科技激光雷达业务持续放量但代码待人工核验",
    )

    plan = plan_backfill(tmp_path, scope="all-local")
    summary = summarize_plan(plan)

    assert summary["scope"] == "all-local"
    assert summary["totals"]["items"] == 2
    assert summary["totals"]["temporal_anchors"] == 3
    assert summary["totals"]["temporal_items"] == 2
    assert summary["totals"]["temporal_spans"] == 1
    assert summary["temporal_rules"]["published_at"] == 2
    assert summary["temporal_rules"]["relative_day_from_published_at"] == 1
    assert summary["temporal_strategies"]["explicit_date"] == 2
    assert summary["temporal_strategies"]["relative_date"] == 1
    assert summary["temporal_granularity"]["day"] == 1
    assert summary["temporal_granularity"]["instant"] == 2
    assert summary["by_f0_source_type"]["livestream_audio"]["items"] == 1
    assert summary["by_f0_source_type"]["unclassified"]["items"] == 1
    assert summary["by_f1_source_type"]["pdf"]["anchors"] == 2
    assert summary["by_f1_source_type"]["pdf"]["temporal_anchors"] == 2
    assert summary["by_f1_source_type"]["image"]["zero_anchor"] == 1


def test_gap_report_marks_zero_anchor_and_candidate_fields(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_gap",
        "data/raw/trader/gap.pdf",
        text=(
            "星河出行科技激光雷达品牌在智能驾驶产业链反复被提及，"
            "星河出行科技新品发布后关注度继续提升，需要人工核验。"
        ),
    )

    report = build_gap_report(plan_backfill(tmp_path, scope="curated-pdf"))

    assert report["zero_anchor_diagnostics"]
    assert report["zero_anchor_diagnostics"][0]["source_record_id"] == "local_gap"
    assert report["zero_anchor_diagnostics"][0]["reason"] in {
        "empty_text",
        "ocr_thin",
        "registry_gap_likely",
        "non_financial_or_macro",
        "parse_error",
    }
    assert report["gap_candidates"]
    candidate = report["gap_candidates"][0]
    assert set(candidate) == {
        "alias_candidate",
        "source_record_id",
        "block_id",
        "raw_path",
        "context_snippet",
        "reason",
        "candidate_type",
        "score",
    }
    assert candidate["candidate_type"] in {
        "known_format_upper_token",
        "cn_entity_phrase",
    }
    assert 0.0 <= candidate["score"] <= 1.0
    assert "ticker" not in candidate
    assert "market" not in candidate


def test_gap_report_marks_low_hit_without_zero_duplication(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_low",
        "data/raw/trader/low.pdf",
        text=[
            "腾讯目标价继续上修，已有实体命中。",
            "星河出行科技，收入增长但实体待人工核验。",
            "云图出行，订单增长但实体待人工核验。",
            "行业景气度继续修复。",
            "财报结构仍需人工复核。",
            "估值分位仍有争议。",
        ],
    )
    _seed_pair(
        tmp_path,
        "local_zero",
        "data/raw/trader/zero.pdf",
        text="星河出行科技，智能驾驶产业链反复被提及，需要人工核验。",
    )

    report = build_gap_report(plan_backfill(tmp_path, scope="curated-pdf"))

    low_ids = {item["source_record_id"] for item in report["low_hit_diagnostics"]}
    assert "local_low" in low_ids
    assert "local_zero" not in low_ids
    low = next(
        item
        for item in report["low_hit_diagnostics"]
        if item["source_record_id"] == "local_low"
    )
    assert low["reason"] == "low_hit_rate"
    assert low["hit_rate"] < 0.2
    assert low["missed_block_count"] == 5
    assert low["anchors"] > 0
    assert low["missed_block_reasons"]["registry_gap_candidate"] == 2
    assert low["missed_block_reasons"]["financial_text_no_candidate"] == 3
    assert low["missed_block_samples"]
    sample = low["missed_block_samples"][0]
    assert set(sample) == {
        "block_id",
        "reason",
        "text_chars",
        "has_financial_context",
        "candidate_count",
        "candidate_aliases",
        "context_snippet",
    }
    assert sample["reason"] == "registry_gap_candidate"
    assert sample["candidate_count"] >= 1
    assert "ticker" not in sample
    assert "market" not in sample
    assert report["low_hit_reason_summary"]["registry_gap_candidate"] == 2
    assert report["low_hit_reason_summary"]["financial_text_no_candidate"] == 3
    assert (
        report["low_hit_reason_by_f0_source_type"]["livestream_audio"][
            "registry_gap_candidate"
        ]
        == 2
    )
    assert (
        report["low_hit_reason_by_f1_source_type"]["pdf"][
            "financial_text_no_candidate"
        ]
        == 3
    )
    assert report["zero_anchor_diagnostics"][0]["source_record_id"] == "local_zero"


def test_source_leaderboard_orders_low_hit_sources_first(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_good",
        "data/raw/trader/good.pdf",
        f0_source_type="livestream_audio",
        f1_source_type="pdf",
        text="腾讯和NVDA",
    )
    _seed_pair(
        tmp_path,
        "local_low",
        "data/raw/trader/low.png",
        f0_source_type="unclassified",
        f1_source_type="image",
        text=[
            "腾讯目标价继续上修。",
            "行业景气度继续修复。",
            "财报结构仍需人工复核。",
            "估值分位仍有争议。",
            "订单增长但实体待核验。",
            "收入改善但实体待核验。",
        ],
    )

    summary = summarize_plan(plan_backfill(tmp_path, scope="all-local"))

    assert summary["worst_f0_source_types"][0]["key"] == "unclassified"
    assert summary["worst_f1_source_types"][0]["key"] == "image"


def test_gap_candidates_filter_generic_terms_and_keep_entity_phrase(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_noise",
        "data/raw/trader/noise.pdf",
        text=(
            "图片 收入 百万元 占比 提升到了。F2 A3。"
            "NOA CAGR CAGR35 PS RSI DRAM GAAP PPI。"
            "PROHIBITED REASONABLE SKULLPANDA CRYBABY。"
            "本人未取得证券投，半导体，半导体设备，半导体破下沿，"
            "半导体指数，日本其他半导体方，冲科技，激光雷达出货量，反弹买保险。"
            "366 名群成员 | 1 个机器人。科技 电子。"
            "芯片产业的投资机，日本半导体相关股，机器人创新药也都，能源充裕到拥有。"
            "盘面看能源补跌可，机器人商店过去，中概等科技权重拖。"
            "美国银行对非存款，银行抵押品缩水，银行收紧信贷。"
            "石油银行煤炭是少，上海报业集团主管，连续个机器人反弹。"
            "车载主激光雷达，据盖世汽车研究院，汽车交付量。"
            "促进股份更活跃交，一如既往的银行和，本集团于，本集团的激光雷达。"
            "应用的激光雷达产，品及用于机器人及，乃根据本集团的初，金融科技及企业服。"
            "港股科技继续回调，算力的资产证券化开始讨论，集团整体仍需观察。"
            "星河出行科技激光雷达品牌在智能驾驶产业链反复被提及。"
            "云图出行，收入增长，公司业务被提及，需要人工核验。"
        ),
    )

    report = build_gap_report(plan_backfill(tmp_path, scope="curated-pdf"))
    aliases = {candidate["alias_candidate"] for candidate in report["gap_candidates"]}

    assert "云图出行" in aliases
    assert "图片" not in aliases
    assert "收入" not in aliases
    assert "百万元" not in aliases
    assert "占比" not in aliases
    assert "提升到了" not in aliases
    assert "F2" not in aliases
    assert "A3" not in aliases
    assert "NOA" not in aliases
    assert "CAGR" not in aliases
    assert "CAGR35" not in aliases
    assert "PS" not in aliases
    assert "RSI" not in aliases
    assert "DRAM" not in aliases
    assert "GAAP" not in aliases
    assert "PPI" not in aliases
    assert "PROHIBITED" not in aliases
    assert "REASONABLE" not in aliases
    assert "SKULLPANDA" not in aliases
    assert "CRYBABY" not in aliases
    assert "本人未取得证券投" not in aliases
    assert "半导体" not in aliases
    assert "半导体设备" not in aliases
    assert "半导体破下沿" not in aliases
    assert "半导体指数" not in aliases
    assert "日本其他半导体方" not in aliases
    assert "冲科技" not in aliases
    assert "激光雷达出货量" not in aliases
    assert "反弹买保险" not in aliases
    assert "机器人" not in aliases
    assert "个机器人" not in aliases
    assert "科技" not in aliases
    assert "电子" not in aliases
    assert "汽车" not in aliases
    assert "芯片产业的投资机" not in aliases
    assert "日本半导体相关股" not in aliases
    assert "机器人创新药也都" not in aliases
    assert "能源充裕到拥有" not in aliases
    assert "盘面看能源补跌可" not in aliases
    assert "机器人商店" not in aliases
    assert "机器人商店过去" not in aliases
    assert "中概等科技权重拖" not in aliases
    assert "美国银行对非存款" not in aliases
    assert "美国银行" not in aliases
    assert "银行抵押品缩水" not in aliases
    assert "银行收紧信贷" not in aliases
    assert "石油银行煤炭是少" not in aliases
    assert "上海报业集团主管" not in aliases
    assert "连续个机器人反弹" not in aliases
    assert "车载主激光雷达" not in aliases
    assert "据盖世汽车研究院" not in aliases
    assert "汽车交付量" not in aliases
    assert "促进股份更活跃交" not in aliases
    assert "一如既往的银行和" not in aliases
    assert "本集团" not in aliases
    assert "本集团于" not in aliases
    assert "应用的激光雷达产" not in aliases
    assert "品及用于机器人及" not in aliases
    assert "乃根据本集团的初" not in aliases
    assert "金融科技" not in aliases
    assert "金融科技及企业服" not in aliases
    assert "港股科技" not in aliases
    assert "算力的资产证券" not in aliases
    assert "集团" not in aliases
    assert "集团整体" not in aliases
    assert "星河出行科技" in aliases
    assert "星河出行科技激" not in aliases
    candidate = next(
        candidate
        for candidate in report["gap_candidates"]
        if candidate["alias_candidate"] == "云图出行"
    )
    assert candidate["candidate_type"] == "cn_entity_phrase"
    assert 0.0 <= candidate["score"] <= 1.0
    assert "ticker" not in candidate
    assert "market" not in candidate


def test_gap_candidates_filter_metric_time_and_currency_tokens(tmp_path: Path):
    """Metrics, time/currency tokens, desk abbrevs, and Pop Mart IPs are noise, not entities."""
    _seed_pair(
        tmp_path,
        "local_metric_noise",
        "data/raw/trader/metric_noise.pdf",
        text=(
            "EPS (Rmb) 9.68，AUM 占比 40%，ASP 提升，NP 与 NPM 改善，ER 和 PB 估值，PIK 利息。"
            "04:37 PM GMT，7:26 AM，UTC 时区更新。"
            "汇率 RMB CNY HKD JPY EUR GBP 结算。"
            "海外金融进了 IBD。自主IP DIMOO PUCKY YOKI JELLY PINO 销量。"
            "OK 就这样，JUST 观望。云图出行收入增长，被反复提及，需要人工核验。"
        ),
    )

    report = build_gap_report(plan_backfill(tmp_path, scope="curated-pdf"))
    aliases = {c["alias_candidate"] for c in report["gap_candidates"]}

    # A real CN entity phrase still surfaces for human review.
    assert "云图出行" in aliases
    # Financial metrics / ratios are a measure, never an investable entity.
    for metric in ("EPS", "AUM", "ASP", "NP", "NPM", "ER", "PB", "PIK"):
        assert metric not in aliases
    # Time-of-day / timezone and currency codes are not entities.
    for token in ("AM", "PM", "GMT", "UTC", "RMB", "CNY", "HKD", "JPY", "EUR", "GBP"):
        assert token not in aliases
    # Desk abbreviation + Pop Mart IP product lines (consistent with LABUBU / MOLLY).
    for token in ("IBD", "DIMOO", "PUCKY", "YOKI", "JELLY", "PINO"):
        assert token not in aliases
    # Generic English words / interjections.
    assert "OK" not in aliases
    assert "JUST" not in aliases


def test_gap_candidate_review_rows_add_blank_review_status(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_gap",
        "data/raw/trader/gap.pdf",
        text=(
            "星河出行科技，订单持续增长，公司业务被提及，需要人工核验。"
            "星河出行科技在智能驾驶产业链反复出现，后续需要人工确认实体。"
        ),
    )

    rows = build_gap_candidate_review_rows(
        build_gap_report(plan_backfill(tmp_path, scope="curated-pdf"))
    )

    assert rows
    row = rows[0]
    assert set(row) == {
        "alias_candidate",
        "source_record_id",
        "block_id",
        "raw_path",
        "context_snippet",
        "reason",
        "candidate_type",
        "score",
        "review_status",
    }
    assert row["review_status"] == ""
    assert "ticker" not in row
    assert "market" not in row
    assert "entity_id" not in row


def test_report_out_is_explicit_cli_side_effect(tmp_path: Path):
    _seed_pair(
        tmp_path,
        "local_test",
        "data/raw/trader/sample.pdf",
        text=(
            "星河出行科技，订单持续增长，公司业务被提及，需要人工核验。"
            "星河出行科技在智能驾驶产业链反复出现，后续需要人工确认实体。"
        ),
    )
    script = Path("scripts/backfill_f2_anchor.py").resolve()
    report_path = tmp_path / "f2_report.json"
    gap_candidates_path = tmp_path / "gap_candidates.jsonl"

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--data-root",
            str(tmp_path),
            "--scope",
            "curated-pdf",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not report_path.exists()
    assert not gap_candidates_path.exists()

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--data-root",
            str(tmp_path),
            "--scope",
            "curated-pdf",
            "--dry-run",
            "--report-out",
            str(report_path),
            "--gap-candidates-out",
            str(gap_candidates_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["scope"] == "curated-pdf"
    assert payload["summary"]["totals"]["selected"] == 1
    assert payload["summary"]["totals"]["temporal_anchors"] == 1
    assert payload["summary"]["totals"]["temporal_spans"] == 0
    assert "temporal_rules" in payload["summary"]
    assert "temporal_strategies" in payload["summary"]
    assert "temporal_granularity" in payload["summary"]
    assert "worst_f0_source_types" in payload["summary"]
    assert "worst_f1_source_types" in payload["summary"]
    assert "low_hit_diagnostics" in payload
    assert "low_hit_reason_summary" in payload
    assert "low_hit_reason_by_f0_source_type" in payload
    assert "low_hit_reason_by_f1_source_type" in payload

    rows = [
        json.loads(line)
        for line in gap_candidates_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    assert rows[0]["review_status"] == ""
    assert "ticker" not in rows[0]
    assert "market" not in rows[0]
    assert "entity_id" not in rows[0]
