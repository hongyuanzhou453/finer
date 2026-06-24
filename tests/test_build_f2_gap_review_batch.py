"""Tests for scripts/build_f2_gap_review_batch.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_f2_gap_review_batch import build_review_batch


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _candidate(
    alias: str,
    *,
    candidate_type: str = "cn_entity_phrase",
    score: float = 0.85,
    source_record_id: str = "local_1",
    context_snippet: str = "context",
) -> dict:
    return {
        "alias_candidate": alias,
        "source_record_id": source_record_id,
        "block_id": f"block_{source_record_id}",
        "raw_path": f"data/raw/{source_record_id}.png",
        "context_snippet": context_snippet,
        "reason": "zero_anchor",
        "candidate_type": candidate_type,
        "score": score,
        "review_status": "",
    }


def test_build_review_batch_deduplicates_and_prefers_best_context(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate("星河出行科技", score=0.6, source_record_id="local_low"),
            _candidate(
                "星河出行科技",
                score=0.9,
                source_record_id="local_high",
                context_snippet="longer useful context",
            ),
            _candidate("未来机器人", score=0.8, source_record_id="local_robot"),
        ],
    )

    plan = build_review_batch(candidates, limit=10)

    assert plan.scanned == 3
    assert plan.unique_aliases == 2
    assert plan.selected == 2
    assert plan.rows[0]["alias_candidate"] == "星河出行科技"
    assert plan.rows[0]["source_record_id"] == "local_high"
    assert plan.rows[0]["support_count"] == 2
    assert len(plan.rows[0]["supporting_examples"]) == 2
    assert plan.rows[0]["supporting_examples"][0]["source_record_id"] == "local_high"
    assert plan.rows[0]["review_status"] == ""


def test_build_review_batch_defaults_to_cn_entity_phrases(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate(
                "NOA",
                candidate_type="known_format_upper_token",
                score=0.95,
                source_record_id="local_upper",
            ),
            _candidate("星河出行科技", score=0.85, source_record_id="local_cn"),
        ],
    )

    default_plan = build_review_batch(candidates, limit=10)
    upper_plan = build_review_batch(candidates, limit=10, include_upper_tokens=True)

    assert [row["alias_candidate"] for row in default_plan.rows] == ["星河出行科技"]
    assert {row["alias_candidate"] for row in upper_plan.rows} == {
        "NOA",
        "星河出行科技",
    }


def test_build_review_batch_filters_non_entity_phrases(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate("集团总计", score=0.95),
            _candidate("科技企业", score=0.95),
            _candidate("银行", score=0.95),
            _candidate("的主流芯片", score=0.95),
            _candidate("半导体破下沿", score=0.95),
            _candidate("电网设备和半导体", score=0.95),
            _candidate("净利润剔除了股份", score=0.95),
            _candidate("注销回购股份", score=0.95),
            _candidate("半导体", score=0.95),
            _candidate("半导体设备", score=0.95),
            _candidate("冲科技", score=0.95),
            _candidate("激光雷达出货量", score=0.95),
            _candidate("反弹买保险", score=0.95),
            _candidate("机器人", score=0.95),
            _candidate("个机器人", score=0.95),
            _candidate("科技", score=0.95),
            _candidate("电子", score=0.95),
            _candidate("汽车", score=0.95),
            _candidate("芯片产业的投资机", score=0.95),
            _candidate("日本半导体相关股", score=0.95),
            _candidate("机器人创新药也都", score=0.95),
            _candidate("能源充裕到拥有", score=0.95),
            _candidate("盘面看能源补跌可", score=0.95),
            _candidate("机器人商店", score=0.95),
            _candidate("中概等科技权重拖", score=0.95),
            _candidate("美国银行对非存款", score=0.95),
            _candidate("银行抵押品缩水", score=0.95),
            _candidate("银行收紧信贷", score=0.95),
            _candidate("石油银行煤炭是少", score=0.95),
            _candidate("上海报业集团主管", score=0.95),
            _candidate("连续个机器人反弹", score=0.95),
            _candidate("车载主激光雷达", score=0.95),
            _candidate("据盖世汽车研究院", score=0.95),
            _candidate("汽车交付量", score=0.95),
            _candidate("促进股份更活跃交", score=0.95),
            _candidate("一如既往的银行和", score=0.95),
            _candidate("本集团", score=0.95),
            _candidate("本集团于", score=0.95),
            _candidate("应用的激光雷达产", score=0.95),
            _candidate("品及用于机器人及", score=0.95),
            _candidate("乃根据本集团的初", score=0.95),
            _candidate("金融科技", score=0.95),
            _candidate("金融科技及企业服", score=0.95),
            _candidate("港股科技", score=0.95),
            _candidate("算力的资产证券", score=0.95),
            _candidate(
                "美国银行",
                score=0.95,
                context_snippet="美国银行对非存款金融机构（含私募信贷）的贷款已达1.2万亿美元",
            ),
            _candidate("新华保险", score=0.85, source_record_id="local_insurance"),
            _candidate("吉利汽车", score=0.85, source_record_id="local_auto"),
            _candidate("速腾聚创", score=0.85, source_record_id="local_robosense"),
        ],
    )

    plan = build_review_batch(candidates, limit=10)
    aliases = [row["alias_candidate"] for row in plan.rows]

    assert aliases == ["吉利汽车", "新华保险", "速腾聚创"]


def test_build_review_batch_skips_existing_registry_gaps(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    dpo_dir = tmp_path / "dpo"
    _write_jsonl(
        candidates,
        [
            _candidate("曹操出行", source_record_id="local_existing"),
            _candidate("曹操出行", source_record_id="local_other"),
            _candidate("新华保险", source_record_id="local_new"),
        ],
    )
    _write_jsonl(
        dpo_dir / "registry_gaps.jsonl",
        [{"alias": "曹操出行", "item_id": "local_existing"}],
    )

    plan = build_review_batch(candidates, limit=10, dpo_dir=dpo_dir)

    assert plan.scanned == 3
    assert plan.skipped_existing_registry_gaps == 2
    assert [row["alias_candidate"] for row in plan.rows] == ["新华保险"]


def test_build_review_batch_output_has_no_grounded_fields(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(
        candidates,
        [
            {
                **_candidate("星河出行科技"),
                "ticker": "FAKE",
                "market": "US",
                "entity_id": "fake",
            }
        ],
    )

    plan = build_review_batch(candidates, limit=10)

    assert plan.rows
    row = plan.rows[0]
    assert "ticker" not in row
    assert "market" not in row
    assert "entity_id" not in row
    assert "ticker" not in row["supporting_examples"][0]
    assert "market" not in row["supporting_examples"][0]
    assert "entity_id" not in row["supporting_examples"][0]


def test_build_review_batch_cli_writes_only_with_explicit_outputs(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    dpo_dir = tmp_path / "dpo"
    out = tmp_path / "review_batch.jsonl"
    markdown_out = tmp_path / "review_batch.md"
    script = Path("scripts/build_f2_gap_review_batch.py").resolve()
    _write_jsonl(
        candidates,
        [
            _candidate("星河出行科技", source_record_id="local_existing"),
            _candidate("未来机器人", source_record_id="local_new"),
        ],
    )
    _write_jsonl(
        dpo_dir / "registry_gaps.jsonl",
        [{"alias": "星河出行科技", "item_id": "local_existing"}],
    )

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--candidates-in",
            str(candidates),
            "--limit",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not out.exists()
    assert not markdown_out.exists()

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--candidates-in",
            str(candidates),
            "--dpo-dir",
            str(dpo_dir),
            "--out",
            str(out),
            "--markdown-out",
            str(markdown_out),
            "--limit",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = _read_jsonl(out)
    assert len(rows) == 1
    assert rows[0]["alias_candidate"] == "未来机器人"
    markdown = markdown_out.read_text(encoding="utf-8")
    assert "F2 Gap Candidate Review Batch" in markdown
    assert "未来机器人" in markdown
    assert "星河出行科技" not in markdown
